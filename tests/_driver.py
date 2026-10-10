#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨版本存档恢复测试驱动（由 tests/test_cross_version.py 以子进程方式调用）

用法（内部）：
    python tests/_driver.py --version v4 --action moves --moves left,up --out out.json
动作：
    new        新建一局并保存
    moves      执行若干有效移动并保存
    hold       执行移动 -> 写出期望状态 -> 打印 READY -> 挂起等待被强制终止
    verify     重新构造对象 -> 读取活动存档 -> 加载并输出恢复后的状态
    noop       仅探查活动存档（用于验证“启动不覆盖旧档”）
    lockprobe  在（可能）只读模式下尝试新建+走子，报告 can_save 与新增目录
    corrupt    把主存档写坏，验证是否能从备份恢复
    undo       加载后执行一次撤销（验证撤销/重做历史是否随存档恢复）
"""

import argparse
import importlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

VERSION_DIRS = {
    "v2": os.path.join(ROOT, "v2_console_2048_with_history"),
    "v3": os.path.join(ROOT, "v3_pyqt_2048"),
    "v4": os.path.join(ROOT, "v4_pyqt_2048_animated"),
    "v5": os.path.join(ROOT, "v5_pyqt_2048_solver"),
}
VERSION_MODULES = {
    "v2": "v2_console_2048_with_history",
    "v3": "v3_pyqt_2048_with_history",
    "v4": "v4_pyqt_2048_animated",
}


def _ensure_paths(version):
    for d in (VERSION_DIRS.get(version), VERSION_DIRS["v4"], VERSION_DIRS["v3"]):
        if d and d not in sys.path:
            sys.path.insert(0, d)


def build_model(version):
    # 确保目标版本目录、v4/v3 目录都在 sys.path 最前（避免被同名目录的命名空间包遮蔽）
    _ensure_paths(version)
    if version == "v2":
        mod = importlib.import_module(VERSION_MODULES["v2"])
        return mod.Console2048WithHistory()
    if version == "v3":
        mod = importlib.import_module(VERSION_MODULES["v3"])
        return mod.GameCore()
    mod = importlib.import_module(VERSION_MODULES["v4"])
    model = mod.AnimatedGameCore()
    if version == "v5":
        import safe_store as _store
        model.set_history_dir(
            _store.resolve_history_dir(os.path.join(VERSION_DIRS["v5"], "game_history"), "v5"),
            "v5")
    return model


def do_move(model, version, direction):
    if version == "v2":
        before = model.score
        if model._move(direction):
            after = [row[:] for row in model.grid]
            model.add_new_tile()
            model.record_move("向%s移动" % direction, model.score - before, after, model.grid)
            model.update_index()
            return True
        return False
    return bool(model.apply_move(direction))


def snapshot(model):
    return {
        "grid": [row[:] for row in model.grid],
        "score": model.score,
        "best_score": model.best_score,
        "game_over": bool(model.game_over),
        "won": bool(model.won),
        "current_move": model.current_move,
        "undo_len": len(getattr(model, "undo_stack", []) or []),
        "redo_len": len(getattr(model, "redo_stack", []) or []),
    }


def recent_info(model, version):
    if version == "v2":
        return model.get_last_unfinished_game()
    return model.get_recent_game_info()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--action", required=True)
    ap.add_argument("--moves", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    _ensure_paths(args.version)
    result = {"version": args.version, "action": args.action}
    directions = [d for d in args.moves.split(",") if d]

    if args.action == "gui_hold":
        # 真实 GUI（v4/v5）：触发一次移动（带动画）后进入事件循环，等待被强杀
        from PyQt5.QtWidgets import QApplication
        app = QApplication(sys.argv[:1])
        if args.version == "v5":
            mod = importlib.import_module("v5_pyqt_2048_solver")
        else:
            mod = importlib.import_module(VERSION_MODULES["v4"])
        win = mod.MainWindow()
        win.show()
        app.processEvents()
        win.start_new_game()
        win.model.grid = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        win.model.score = 0
        win.board_view.render(win.model.grid)
        win.refresh()
        app.processEvents()
        win.on_move("left")               # 触发移动 + 动画（动画在事件循环中推进）
        app.processEvents()
        snap = snapshot(win.model)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        print("READY", flush=True)
        app.exec_()
        return

    model = build_model(args.version)

    if args.action == "new":
        model.start_new_game()
        result.update(snapshot(model))
        result["can_save"] = model.can_save
        result["history_dir"] = model.history_dir

    elif args.action == "moves":
        model.start_new_game()            # 每个驱动进程独立：先开新局再走子
        applied = 0
        for d in directions:
            if do_move(model, args.version, d):
                applied += 1
        result.update(snapshot(model))
        result["applied"] = applied

    elif args.action == "hold":
        model.start_new_game()            # 新局后走子，再挂起等待被强制终止
        for d in directions:
            do_move(model, args.version, d)
        snap = snapshot(model)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        print("READY", flush=True)
        time.sleep(120)

    elif args.action == "verify":
        info = recent_info(model, args.version)
        if not info:
            result["loaded"] = False
            result["error"] = "no_recent_game"
        else:
            ok = model.load_game_state(info["game_id"])
            result["loaded"] = bool(ok)
            result["used_backup"] = bool(getattr(model, "last_load_used_backup", False))
            result["load_error"] = getattr(model, "last_load_error", None)
            if ok:
                result.update(snapshot(model))

    elif args.action == "noop":
        info = recent_info(model, args.version)
        result["has_recent"] = bool(info)
        result["can_save"] = model.can_save

    elif args.action == "lockprobe":
        result["can_save"] = model.can_save
        base = model.history_dir
        before = set(os.listdir(base)) if os.path.isdir(base) else set()
        model.start_new_game()
        for d in ("left", "up", "right", "down"):
            do_move(model, args.version, d)
        after = set(os.listdir(base)) if os.path.isdir(base) else set()
        result["new_entries"] = sorted(after - before)

    elif args.action == "corrupt":
        info = recent_info(model, args.version)
        if not info:
            result["loaded"] = False
            result["error"] = "no_recent_game"
        else:
            gid = info["game_id"]
            state_file = os.path.join(model.history_dir, gid, "game_state.json")
            with open(state_file, "w", encoding="utf-8") as f:
                f.write("{ invalid json !!!")
            ok = model.load_game_state(gid)
            result["loaded"] = bool(ok)
            result["used_backup"] = bool(getattr(model, "last_load_used_backup", False))
            result["load_error"] = getattr(model, "last_load_error", None)
            if ok:
                result.update(snapshot(model))

    elif args.action == "undo":
        info = recent_info(model, args.version)
        if not info:
            result["loaded"] = False
            result["error"] = "no_recent_game"
        else:
            ok = model.load_game_state(info["game_id"])
            result["loaded"] = bool(ok)
            result["undo_len"] = len(getattr(model, "undo_stack", []) or [])
            if ok and hasattr(model, "undo"):
                result["undo_ok"] = bool(model.undo())
                result["after_undo"] = snapshot(model)

    if args.action != "hold":
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
