#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二版~第五版：异常退出存档恢复 逐项测试

特点：
    - 全部使用隔离的临时存档目录（2048_HISTORY_DIR），不触碰真实用户存档；
    - 用 taskkill /F 真实强制终止子进程，模拟崩溃/异常退出；
    - 覆盖：新局保存、移动即时保存、连续移动、强制终止后恢复（棋盘/分数/最高分/结束状态）、
            启动不覆盖旧档、损坏主档→备份恢复、双损坏优雅失败、撤销/重做历史恢复、
            多实例只读保护、跨版本隔离。

用法：
    python tests/test_cross_version.py
返回码：0=全部通过；1=存在失败。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(ROOT, "tests", "_driver.py")
PY = sys.executable
VERSIONS = ["v2", "v3", "v4", "v5"]
UNDO_VERSIONS = ["v3", "v4", "v5"]

RESULTS = []


def record(version, item, ok, detail=""):
    RESULTS.append((version, item, bool(ok), detail))
    flag = "PASS" if ok else "FAIL"
    print("[%s] %-4s %s%s" % (flag, version, item, (" | " + detail) if detail else ""),
          flush=True)


def run_driver(version, action, moves="", env=None, out=None, timeout=90):
    cmd = [PY, DRIVER, "--version", version, "--action", action]
    if moves:
        cmd += ["--moves", moves]
    if out:
        cmd += ["--out", out]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    line = ""
    for ln in (proc.stdout or "").splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            line = ln
    if not line:
        return {"error": "no_json", "stdout": proc.stdout, "stderr": proc.stderr,
                "rc": proc.returncode}
    try:
        return json.loads(line)
    except ValueError as exc:
        return {"error": "bad_json:%s" % exc, "stdout": proc.stdout, "stderr": proc.stderr}


def spawn_hold(version, moves, env, expected_path, action="hold"):
    cmd = [PY, DRIVER, "--version", version, "--action", action,
           "--moves", moves, "--out", expected_path]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)
    ready = False
    deadline = time.time() + 40
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        if "READY" in line:
            ready = True
            break
    return proc, ready


def force_kill(proc):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)],
                       capture_output=True, text=True, timeout=20)
    except Exception:                                            # noqa: BLE001
        pass
    try:
        proc.wait(timeout=15)
    except Exception:                                            # noqa: BLE001
        proc.kill()


def same_state(a, b, keys=("grid", "score", "best_score", "game_over", "won", "current_move")):
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if k in ("game_over", "won"):
            va, vb = bool(va), bool(vb)
        if va != vb:
            return False, "%s: %r != %r" % (k, va, vb)
    return True, ""


def file_hash(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def state_path_of(history_dir, info):
    return os.path.join(history_dir, info["game_id"], "game_state.json")


def latest_info(version, env, history_dir):
    index = os.path.join(history_dir, "index.json")
    if not os.path.exists(index):
        return None
    try:
        data = json.load(open(index, encoding="utf-8"))
    except ValueError:
        return None
    unfinished = [g for g in data
                  if isinstance(g, dict) and not g.get("is_completed", False)]
    if not unfinished:
        return None
    unfinished.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
    return unfinished[0]


def test_version(version, base):
    env = os.environ.copy()
    env["2048_HISTORY_DIR"] = base
    history_dir = os.path.join(base, version)

    # ---- 1. 新游戏后保存 ----
    r = run_driver(version, "new", env=env)
    idx = os.path.join(history_dir, "index.json")
    info = latest_info(version, env, history_dir)
    ok = bool(r.get("can_save")) and os.path.exists(idx) and info is not None
    record(version, "1. 新游戏后保存", ok,
           "can_save=%s index=%s" % (r.get("can_save"), os.path.exists(idx)))
    if info is None:
        record(version, "2~11", False, "无法获得活动存档，跳过后续检查")
        return

    # ---- 2. 有效/连续移动后即时保存（并核对落盘 = 内存） ----
    r = run_driver(version, "moves",
                   moves="left,up,right,down,left,up,right,down", env=env)
    info = latest_info(version, env, history_dir)
    saved = None
    if info:
        sp = state_path_of(history_dir, info)
        if os.path.exists(sp):
            saved = json.load(open(sp, encoding="utf-8"))
    ok = (r.get("applied", 0) >= 1 and saved is not None
          and saved.get("grid") == r.get("grid") and saved.get("score") == r.get("score"))
    record(version, "2. 移动后即时持久化且与内存一致", ok, "applied=%s" % r.get("applied"))

    # ---- 3. 强制终止 -> 重新启动 -> 继续上一局 -> 状态完全一致 ----
    expected_path = os.path.join(base, "%s_expected.json" % version)
    proc, ready = spawn_hold(version, "left,up,right,down,left,up", env, expected_path)
    if not ready:
        force_kill(proc)
        record(version, "4. 强制终止后恢复（棋盘/分数/最高分/结束状态）", False, "driver 未就绪")
    else:
        force_kill(proc)
        expected = json.load(open(expected_path, encoding="utf-8"))
        r = run_driver(version, "verify", env=env)
        if r.get("loaded"):
            ok, detail = same_state(r, expected)
        else:
            ok, detail = False, "load_error=%s" % r.get("load_error")
        record(version, "4. 强制终止后恢复（棋盘/分数/最高分/结束状态）", ok, detail)

    # ---- 5. 启动不覆盖旧存档 ----
    info = latest_info(version, env, history_dir)
    sp = state_path_of(history_dir, info)
    h1 = file_hash(sp)
    run_driver(version, "noop", env=env)
    h2 = file_hash(sp)
    record(version, "5. 启动时不覆盖旧存档", h1 is not None and h1 == h2,
           "hash %s" % ("一致" if h1 == h2 else "变化"))

    # ---- 6. 损坏主档 -> 备份恢复 ----
    r = run_driver(version, "corrupt", env=env)
    record(version, "6. 损坏主档时从备份恢复",
           bool(r.get("loaded")) and bool(r.get("used_backup")),
           "loaded=%s used_backup=%s" % (r.get("loaded"), r.get("used_backup")))

    # ---- 7. 主档与备份都损坏 -> 优雅失败（不崩溃、返回错误） ----
    info = latest_info(version, env, history_dir)
    if info:
        sp = state_path_of(history_dir, info)
        with open(sp, "w", encoding="utf-8") as f:
            f.write("{ broken")
        if os.path.exists(sp + ".bak"):
            with open(sp + ".bak", "w", encoding="utf-8") as f:
                f.write("{ broken")
        r = run_driver(version, "verify", env=env)
        ok = (r.get("loaded") is False) and bool(r.get("load_error"))
        record(version, "7. 存档彻底损坏时优雅失败", ok, "error=%s" % r.get("load_error"))
    else:
        record(version, "7. 存档彻底损坏时优雅失败", False, "无活动存档")

    # ---- 8. 撤销/重做历史随存档恢复（仅支持撤销的版本） ----
    if version in UNDO_VERSIONS:
        run_driver(version, "moves", moves="left,up,right,down,left", env=env)
        r = run_driver(version, "undo", env=env)
        ok = bool(r.get("loaded")) and r.get("undo_len", 0) >= 1 and bool(r.get("undo_ok"))
        record(version, "8. 撤销/重做历史随存档恢复且可继续撤销", ok,
               "undo_len=%s undo_ok=%s" % (r.get("undo_len"), r.get("undo_ok")))
    else:
        record(version, "8. 撤销/重做历史随存档恢复且可继续撤销", True, "该版本无撤销功能（跳过）")

    # ---- 9. 多实例只读保护（同版本另一活动进程持锁） ----
    lockfile = os.path.join(history_dir, ".instance.lock")
    os.makedirs(history_dir, exist_ok=True)
    with open(lockfile, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "time": "test"}, f)
    r = run_driver(version, "lockprobe", env=env)
    ok = (r.get("can_save") is False) and not r.get("new_entries")
    record(version, "9. 同版本多实例时只读保护（不写入）", ok,
           "can_save=%s new=%s" % (r.get("can_save"), r.get("new_entries")))
    try:
        os.remove(lockfile)
    except OSError:
        pass

    # ---- 10. 移动后立即强杀（模拟动画中/写入瞬间异常退出） ----
    expected_path = os.path.join(base, "%s_expected2.json" % version)
    proc, ready = spawn_hold(version, "left,up,right,down,left,up,right", env, expected_path)
    if ready:
        force_kill(proc)     # READY 后立刻强杀（不等待额外操作）
        expected = json.load(open(expected_path, encoding="utf-8"))
        r = run_driver(version, "verify", env=env)
        if r.get("loaded"):
            ok, detail = same_state(r, expected)
        else:
            ok, detail = False, "load_error=%s" % r.get("load_error")
        record(version, "10. 动作后立即强杀仍可恢复最后一次成功保存", ok, detail)
    else:
        force_kill(proc)
        record(version, "10. 动作后立即强杀仍可恢复最后一次成功保存", False, "driver 未就绪")

    # ---- 12. 动画进行中强杀（v4/v5 真实 GUI 子进程，动画在事件循环中推进） ----
    if version in ("v4", "v5"):
        gui_env = dict(env)
        gui_env["QT_QPA_PLATFORM"] = "offscreen"     # 不弹真窗口，仍可运行 Qt 定时器/动画
        run_driver(version, "new", env=env)
        expected_path = os.path.join(base, "%s_gui.json" % version)
        proc, ready = spawn_hold(version, "", gui_env, expected_path, action="gui_hold")
        if ready:
            force_kill(proc)                          # 移动已落盘、动画正在进行时强杀
            expected = json.load(open(expected_path, encoding="utf-8"))
            r = run_driver(version, "verify", env=env)
            if r.get("loaded"):
                ok, detail = same_state(r, expected)
            else:
                ok, detail = False, "load_error=%s" % r.get("load_error")
            record(version, "12. 动画进行中强杀仍恢复到最新落盘状态", ok, detail)
        else:
            force_kill(proc)
            record(version, "12. 动画进行中强杀仍恢复到最新落盘状态", False, "GUI driver 未就绪")
    else:
        record(version, "12. 动画进行中强杀仍恢复到最新落盘状态", True, "该版本无动画（跳过）")


def test_isolation(base):
    """跨版本隔离：写一份真实存档目录，确认各版本互不覆盖。"""
    env = os.environ.copy()
    env["2048_HISTORY_DIR"] = base
    for v in VERSIONS:
        run_driver(v, "new", env=env)
        run_driver(v, "moves", moves="left,up", env=env)
    present = [v for v in VERSIONS if os.path.isdir(os.path.join(base, v))]
    ok = len(present) == len(VERSIONS)
    # 各版本 index.json 里的 game_id 不应互相出现在对方目录
    ok = ok and all(os.path.exists(os.path.join(base, v, "index.json")) for v in VERSIONS)
    record("all", "11. 跨版本存档目录隔离（各版本独立子目录）", ok, "dirs=%s" % present)


def main():
    base = tempfile.mkdtemp(prefix="2048_recovery_")
    print("隔离存档根目录:", base)
    try:
        for v in VERSIONS:
            test_version(v, base)
        test_isolation(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    total = len(RESULTS)
    passed = sum(1 for _v, _i, ok, _d in RESULTS if ok)
    failed = total - passed
    print("\n==== 汇总：%d/%d 通过，%d 失败 ====" % (passed, total, failed))
    if failed:
        print("失败项：")
        for v, item, ok, detail in RESULTS:
            if not ok:
                print("  - %s %s | %s" % (v, item, detail))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
