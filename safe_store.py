#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048 跨版本安全存档工具（纯标准库，v2–v5 共用）

能力：
    - 原子写入：同目录临时文件 + flush/fsync + os.replace（不先删旧文件）
    - 数据校验：JSON 合法性、4×4 棋盘、方块值、分数、布尔字段
    - 备份与回退：主文件损坏时回退到上一份有效备份
    - 存档版本标记：写入 schema/version 字段，读取时兼容旧格式
    - 单实例锁：避免同一版本多进程互相覆盖存档

设计原则：
    - 不修改调用方的业务规则；仅提供“安全落盘 / 安全读取”的能力。
    - 所有异常都被收敛为函数返回值，调用方自行决定提示与降级。
"""

import datetime
import json
import os
import shutil
import tempfile

SCHEMA_VERSION = 2


# =====================================================================
# 原子写入
# =====================================================================
def atomic_write_bytes(path, data):
    """把 bytes 原子地写入 path（同目录临时文件 -> fsync -> os.replace）。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # 同盘 rename，原子生效；旧文件不会被提前删除
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def atomic_write_text(path, text, encoding="utf-8"):
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path, obj, ensure_ascii=False, indent=2):
    atomic_write_text(path, json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent))


def atomic_write_csv(path, header, rows, encoding="utf-8"):
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    if header:
        writer.writerow(header)
    writer.writerows(rows)
    atomic_write_text(path, buf.getvalue(), encoding)


# =====================================================================
# 读取与备份
# =====================================================================
def read_json(path):
    """读取 JSON，返回 (ok, data, error)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return True, json.load(f), None
    except FileNotFoundError:
        return False, None, "not_found"
    except (json.JSONDecodeError, ValueError) as exc:
        return False, None, "invalid_json:%s" % exc
    except OSError as exc:
        return False, None, "io_error:%s" % exc


def backup_copy(path, backup_path):
    """把 path 的当前内容复制为备份（原子）。不存在则返回 False。"""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "rb") as f:
            data = f.read()
        atomic_write_bytes(backup_path, data)
        return True
    except OSError:
        return False


def load_json_validated(path, validator, backup_path=None):
    """
    优先读取主文件并校验；主文件缺失/损坏时回退备份。

    :return: (data, used_backup, error)
        - 成功：data 为校验通过的对象，used_backup 标记是否用了备份，error 为 None
              （回退备份时 error 会带上主文件的失败原因，便于界面提示）
        - 失败：data 为 None，error 为失败原因
    """
    ok, data, err = read_json(path)
    if ok:
        good, msg = validator(data)
        if good:
            return data, False, None
        err = msg
    if backup_path:
        ok2, data2, err2 = read_json(backup_path)
        if ok2:
            good2, msg2 = validator(data2)
            if good2:
                return data2, True, ("primary_invalid:%s" % err)
    return None, False, err


# =====================================================================
# 校验
# =====================================================================
def valid_tile(value):
    """合法方块值：0，或 2 的幂（2..2^20）。"""
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= 0 and value <= (1 << 20)
            and (value == 0 or (value & (value - 1)) == 0))


def validate_grid(grid, size=4):
    if not isinstance(grid, list) or len(grid) != size:
        return False
    for row in grid:
        if not isinstance(row, list) or len(row) != size:
            return False
        for value in row:
            if not valid_tile(value):
                return False
    return True


def validate_game_state(state, size=4):
    """返回 (ok, message)。兼容无 schema 的旧存档。"""
    if not isinstance(state, dict):
        return False, "存档不是 JSON 对象"
    if not validate_grid(state.get("grid"), size):
        return False, "棋盘数据非法（需 %d×%d 且值为 0/2 的幂）" % (size, size)
    for key in ("score", "best_score", "current_move"):
        value = state.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False, "字段 %s 非法" % key
    for key in ("game_over", "won"):
        value = state.get(key, False)
        if not isinstance(value, bool):
            return False, "字段 %s 非法" % key
    snapshot = state.get("undo_stack")
    if snapshot is not None and not isinstance(snapshot, list):
        return False, "undo_stack 非法"
    return True, None


def now_iso():
    return datetime.datetime.now().isoformat()


def wrap_state(state, version_tag):
    """给状态加上 schema/version 标记（兼容旧读取）。"""
    env = dict(state)
    env["schema"] = SCHEMA_VERSION
    env["version"] = version_tag
    return env


# =====================================================================
# 单实例锁（避免多进程互相覆盖存档）
# =====================================================================
def _pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            return code.value == 259          # STILL_ACTIVE
        except Exception:                     # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:                         # noqa: BLE001
        return False


class InstanceLock:
    """基于锁文件的单实例协调：同版本已有活动进程时，新进程应进入只读模式。"""

    def __init__(self, path):
        self.path = path
        self.acquired = False

    def acquire(self):
        """返回 True=拿到写权限；False=同版本另一进程仍在运行（应只读运行）。"""
        payload = {"pid": os.getpid(), "time": now_iso()}
        if os.path.exists(self.path):
            ok, data, _ = read_json(self.path)
            if ok and isinstance(data, dict) and _pid_alive(data.get("pid")):
                self.acquired = False
                return False
            # 陈旧锁（进程已退出）：接管
        try:
            atomic_write_json(self.path, payload)
            self.acquired = True
            return True
        except OSError:
            # 无法写锁（权限/占用）：保守视为“可写”，避免误伤正常使用
            self.acquired = True
            return True

    def release(self):
        if not self.acquired:
            return
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("pid") == os.getpid():
                    os.remove(self.path)
        except (OSError, ValueError):
            pass
        finally:
            self.acquired = False


def safe_makedirs(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def resolve_history_dir(fallback, version_tag):
    """
    解析存档目录：
        - 默认使用各版本目录下的 game_history（稳定，不依赖当前工作目录）；
        - 若设置了环境变量 2048_HISTORY_DIR，则使用 <该目录>/<version_tag>，
          便于测试隔离（各版本仍互不干扰）。
    """
    env = os.environ.get("2048_HISTORY_DIR")
    if env:
        try:
            return os.path.join(os.path.abspath(env), version_tag)
        except OSError:
            return fallback
    return fallback


def copy_tree(src, dst):
    """尽力复制目录（用于备份/迁移），失败返回 False。"""
    try:
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return True
    except OSError:
        return False
