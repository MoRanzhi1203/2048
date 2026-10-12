#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 后台求解「所有权 / 心跳 / 恢复」测试（无 Qt，可独立运行）。

覆盖：身份验证（进程不存在 / PID 复用 / 心跳超时 / 镜像不符）、安全释放（活动 owner
拒绝释放、session 不匹配拒绝释放、TOCTOU 二次校验）、原子释放后所有权为空、
最新检查点选择与棋盘恢复、worker 生命周期（写 owner + 退出时释放）。
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V6_DIR)
sys.path.insert(0, os.path.join(V6_DIR, 'headless'))
sys.path.insert(0, os.path.dirname(V6_DIR))

import core                                                          # noqa: E402
import ownership as own                                              # noqa: E402

PY = sys.executable


class OwnershipAuditTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='v6_own_')

    def test_absent(self):
        self.assertEqual(own.owner_status(self.dir)['state'], 'absent')

    def test_records_real_identity_not_just_pid(self):
        rec = own.write_owner(self.dir, os.getpid(), 'sess-A')
        self.assertTrue(str(rec['image']).lower().startswith('python'),
                        '必须记录真实镜像名而非仅 PID')
        self.assertIsNotNone(rec['create_time'], '必须记录进程创建时间（PID 复用判定）')
        self.assertEqual(own.owner_status(self.dir)['state'], 'alive',
                         '刚写入且心跳新鲜的 owner 应判为 alive')

    def test_pid_reuse_detected_by_create_time(self):
        own.write_owner(self.dir, os.getpid(), 'sess-A')
        rec = own.read_owner(self.dir)
        rec['create_time'] = (rec['create_time'] or 0) + 999.0      # 伪造不同的创建时间
        own._store.atomic_write_json(own.owner_path(self.dir), rec)
        st = own.owner_status(self.dir)
        self.assertEqual(st['state'], 'stale')
        self.assertIn('PID 复用', st['reason'])

    def test_dead_pid_is_stale(self):
        rec = {'pid': 999999, 'session_id': 's', 'revision': 0, 'kind': 'worker',
               'create_time': 1.0, 'image': 'python.exe',
               'started_at': own.now_iso(), 'heartbeat_at': own.now_iso()}
        own._store.atomic_write_json(own.owner_path(self.dir), rec)
        st = own.owner_status(self.dir)
        self.assertEqual(st['state'], 'stale')
        self.assertIn('进程不存在', st['reason'])

    def test_heartbeat_timeout_is_stale(self):
        rec = own.write_owner(self.dir, os.getpid(), 'sess-A')
        rec['create_time'] = own.proc_identity(os.getpid())['create_time']
        own._store.atomic_write_json(own.owner_path(self.dir), rec)
        st = own.owner_status(self.dir, max_age=-1.0)               # 强制超时
        self.assertEqual(st['state'], 'stale')
        self.assertIn('心跳超时', st['reason'])

    def test_alive_owner_with_fresh_heartbeat(self):
        own.write_owner(self.dir, os.getpid(), 'sess-A')
        own.touch_heartbeat(self.dir, os.getpid(), 'sess-A', 3, 7, 123, 900.0)
        st = own.owner_status(self.dir)
        self.assertEqual(st['state'], 'alive')
        self.assertEqual(st['heartbeat']['step'], 7)

    def test_alive_owner_refuses_release(self):
        own.write_owner(self.dir, os.getpid(), 'sess-A')
        own.touch_heartbeat(self.dir, os.getpid(), 'sess-A', 1, 1, 1, 1.0)
        rel = own.release_stale(self.dir)
        self.assertFalse(rel['released'])
        self.assertEqual(rel['state'], 'alive')

    def test_session_mismatch_refuses_release(self):
        rec = {'pid': 999999, 'session_id': 'sess-A', 'revision': 0, 'kind': 'worker',
               'create_time': 1.0, 'image': 'python.exe',
               'started_at': own.now_iso(), 'heartbeat_at': own.now_iso()}
        own._store.atomic_write_json(own.owner_path(self.dir), rec)
        rel = own.release_stale(self.dir, expected_session_id='sess-OTHER')
        self.assertFalse(rel['released'])
        rel2 = own.release_stale(self.dir, expected_session_id='sess-A')
        self.assertTrue(rel2['released'])
        self.assertEqual(own.owner_status(self.dir)['state'], 'absent')
        self.assertIsNotNone(own.released_marker(self.dir))

    def test_malformed_record(self):
        with open(own.owner_path(self.dir), 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertEqual(own.owner_status(self.dir)['state'], 'malformed')


class CheckpointRestoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='v6_ckpt_')

    def _write_ck(self, name, steps, score, board, age):
        snap = core.build_snapshot(board, score, score,
                                   core.rng_state_to_json(random.getstate()), 'g', steps,
                                   'expectimax', 'fast')
        p = os.path.join(self.dir, name)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'schema': 1, 'status': 'running', 'steps': steps,
                       'snapshot': core.snapshot_to_json(snap)}, f)
        os.utime(p, (time.time() - age, time.time() - age))
        return p

    def test_latest_valid_checkpoint_selected(self):
        self._write_ck('a_checkpoint.json', 1, 10, [[2, 0, 0, 0]] + [[0] * 4] * 3, 100)
        p2 = self._write_ck('b_resume.json', 9, 90, [[4, 0, 0, 0]] + [[0] * 4] * 3, 1)
        ck = own.latest_checkpoint(self.dir)
        self.assertIsNotNone(ck)
        self.assertEqual(ck[0], p2)
        snap = core.snapshot_from_json(ck[1]['snapshot'])
        self.assertEqual(snap['score'], 90)

    def test_corrupt_checkpoint_skipped(self):
        with open(os.path.join(self.dir, 'bad_checkpoint.json'), 'w', encoding='utf-8') as f:
            f.write('{broken')
        p = self._write_ck('good_checkpoint.json', 2, 20, [[8, 0, 0, 0]] + [[0] * 4] * 3, 1)
        ck = own.latest_checkpoint(self.dir)
        self.assertEqual(ck[0], p)


_IPC_E2E = os.environ.get('V6_RUN_IPC_E2E') == '1'


@unittest.skipUnless(_IPC_E2E, 'IPC E2E（需 V6_RUN_IPC_E2E=1）：会真实拉起 worker 子进程并读写'
                               '暂存检查点，为保持默认门禁快速/确定性而默认跳过，可单独运行取证。'
                               '（原首解冷启动卡死已修复：cpp 求解路径不再冷导入 numpy）')
class WorkerOwnershipLifecycleTest(unittest.TestCase):
    def test_worker_writes_and_releases_owner(self):
        tmp = tempfile.mkdtemp(prefix='v6_worker_own_')
        staging = os.path.join(tmp, 'ck.json')
        snap = core.build_snapshot([[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256],
                                    [0, 0, 0, 0]], 0, 0,
                                   core.rng_state_to_json(random.getstate()), 'own', 0,
                                   'expectimax', 'fast')
        sp = os.path.join(tmp, 'snap.json')
        with open(sp, 'w', encoding='utf-8') as f:
            f.write(core.snapshot_to_json(snap))
        env = dict(os.environ, PYTHONNOUSERSITE='1')
        proc = subprocess.Popen([PY, '-m', 'headless.worker_main'], cwd=V6_DIR, env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, bufsize=1)
        lines = []
        drained = threading.Event()

        def _drain():
            # 必须持续读取 stdout：否则管道缓冲写满后 worker 会阻塞在写进度上
            while True:
                ln = proc.stdout.readline()
                if not ln:
                    break
                lines.append(ln)
            drained.set()

        threading.Thread(target=_drain, daemon=True).start()

        def wait_line(pred, timeout, what):
            """事件驱动等待：轮询已排空的输出行，而非固定 sleep 猜时序。"""
            t0 = time.time()
            while time.time() - t0 < timeout:
                if any(pred(ln) for ln in list(lines)):
                    return True
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            raise AssertionError('等待 %s 超时（%.0fs）；stderr=%s；lines=%s'
                                 % (what, timeout, proc.stderr.read()[-400:] if proc.stderr else '',
                                    [ln.strip()[:80] for ln in lines[-6:]]))

        try:
            wait_line(lambda ln: '"ready"' in ln, 180, 'ready')
            proc.stdin.write(json.dumps({'cmd': 'start', 'snapshot_path': sp,
                                         'limits': {'max_steps': 500, 'max_seconds': 60,
                                                    'progress_interval_s': 0.05},
                                         'backend': 'cpp', 'staging': staging,
                                         'ownership': tmp}) + '\n')
            proc.stdin.flush()
            # 所有权在预热**之前**登记，因此 ack 后即可观察；此处仍给足上限，避免机器负载抖动
            wait_line(lambda ln: '"ack"' in ln, 180, 'ack(start)')
            deadline = time.time() + 180
            while time.time() < deadline:
                if own.owner_status(tmp)['state'] == 'alive':
                    break
                time.sleep(0.05)
            st = own.owner_status(tmp)
            self.assertEqual(st['state'], 'alive', 'worker 未登记有效所有权')
            self.assertEqual(st['record']['session_id'], 'own')
            proc.stdin.write('{"cmd":"stop"}\n')
            proc.stdin.flush()
            wait_line(lambda ln: '"final"' in ln, 180, 'final')
            wait_line(lambda ln: '"exited"' in ln, 180, 'exited')
            proc.wait(timeout=120)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(own.owner_status(tmp)['state'], 'absent',
                             'worker 退出后所有权未释放')
        finally:
            if proc.poll() is None:
                proc.kill()


if __name__ == '__main__':
    unittest.main(verbosity=2)
