#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H2：强化学习工程化验证（schema / 独立 holdout 门禁 / 检查点与备份回滚）

覆盖：
    test_rl_schema          —— schema、权重 shape/dtype、NaN/Inf 校验；旧版(V1)兼容加载路径
    test_rl_holdout_gate    —— 训练/验证/门禁三随机数家族隔离；配对差值 + bootstrap CI 判据
    test_rl_checkpoint      —— 原子写、best/latest 检查点、版本化备份与回滚、元数据持久化

安全约束：所有写入都在临时目录；结束时校验仓库正式 rl_model.npz 哈希未变化。

运行：python tests/test_rl_model_management.py
返回码：0=全部通过；1=存在失败。
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import rl_2048 as rl                                              # noqa: E402

OFFICIAL = os.path.join(V5, "rl_model.npz")
LEGACY = os.path.join(ROOT, "experiments", "baseline", "rl_model_v1.npz")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _base_net():
    if os.path.exists(LEGACY):
        return rl.load_legacy_model(LEGACY)
    return rl.init_net(np.random.RandomState(0))


class RLModelManagementTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rl_mm_")
        self.official_sha_before = _sha(OFFICIAL) if os.path.exists(OFFICIAL) else None

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.official_sha_before is not None:
            self.assertEqual(_sha(OFFICIAL), self.official_sha_before,
                             "测试不得修改仓库正式模型")

    # ---------------- test_rl_schema ----------------
    def test_rl_schema(self):
        net = rl.init_net(np.random.RandomState(1))
        p = os.path.join(self.tmp, "m.npz")
        rl.save_model(net, p, meta={"note": "schema"})
        loaded = rl.load_model(p)
        for k in rl.EXPECTED_SHAPES:
            self.assertEqual(loaded[k].shape, rl.EXPECTED_SHAPES[k])
            self.assertEqual(loaded[k].dtype, np.float32)
            np.testing.assert_array_equal(loaded[k], net[k].astype(np.float32))
        self.assertEqual(rl.load_meta(p).get("note"), "schema")

        # 形状错误 → 拒绝
        bad = {k: v.copy() for k, v in net.items()}
        bad["W2"] = bad["W2"][:, :-1]
        with self.assertRaises(ValueError):
            rl.validate_net(bad, "坏模型")

        # NaN/Inf → 拒绝
        nan = {k: v.copy() for k, v in net.items()}
        nan["b1"][0] = np.inf
        with self.assertRaises(ValueError):
            rl.validate_net(nan, "含Inf")

        # 错误 dtype（整数）→ 拒绝
        intish = {k: v.copy() for k, v in net.items()}
        intish["bv"] = np.zeros(1, dtype=np.int64)
        with self.assertRaises(ValueError):
            rl.validate_net(intish, "整型")

        # 缺失 _schema 的旧模型：严格加载拒绝，专用兼容路径接受
        if os.path.exists(LEGACY):
            with self.assertRaises(ValueError):
                rl.load_model(LEGACY)
            legacy = rl.load_legacy_model(LEGACY)
            self.assertEqual(set(legacy), set(rl.EXPECTED_SHAPES))

        # _schema 不匹配 → 拒绝
        wrong = os.path.join(self.tmp, "wrong.npz")
        np.savez(wrong, **{k: np.asarray(v) for k, v in net.items()},
                 _schema=np.array([999]))
        with self.assertRaises(ValueError):
            rl.load_model(wrong)

    # ---------------- test_rl_holdout_gate ----------------
    def test_rl_holdout_gate(self):
        # 三个随机数家族互不相同
        self.assertEqual(len({rl.DEFAULT_TRAIN_SEED, rl.DEFAULT_VALID_SEED,
                              rl.DEFAULT_HOLDOUT_SEED}), 3)
        net = _base_net()

        # 同一模型自比：配对差值应≈0，且判据为“未显著更优”
        g0 = rl.gate_compare(net, net, games=6, holdout_seed=rl.DEFAULT_HOLDOUT_SEED)
        self.assertEqual(g0["mean_diff"], 0.0)
        self.assertFalse(g0["improved"], "同一模型不应被判为显著更优")

        # 门禁使用 holdout 种子家族（与验证家族不同）
        self.assertEqual(g0["seed_range"][0], rl.DEFAULT_HOLDOUT_SEED)
        self.assertNotEqual(g0["holdout_seed"], rl.DEFAULT_VALID_SEED)
        self.assertNotEqual(g0["holdout_seed"], rl.DEFAULT_TRAIN_SEED)

        # 固定 holdout seed → 可复现
        g1 = rl.gate_compare(net, net, games=6, holdout_seed=rl.DEFAULT_HOLDOUT_SEED)
        self.assertEqual(g0["old_avg"], g1["old_avg"])

        # CI 判据方向：明显更差的“新模型”必须被判为不改进
        rng = np.random.RandomState(7)
        worse = rl.init_net(rng)                     # 随机初始化 = 明显更差
        gw = rl.gate_compare(net, worse, games=6, holdout_seed=rl.DEFAULT_HOLDOUT_SEED)
        self.assertFalse(gw["improved"])
        self.assertLess(gw["mean_diff"], 0)

    # ---------------- test_rl_checkpoint ----------------
    def test_rl_checkpoint(self):
        net = rl.init_net(np.random.RandomState(3))
        base = os.path.join(self.tmp, "rl.pt")
        out = base + ".npz"

        # 原子写：不残留 .tmp
        rl.save_model(net, out, meta={"games": 0})
        self.assertTrue(os.path.exists(out))
        self.assertFalse(os.path.exists(out + ".tmp.npz"))

        # 版本化备份 + 回滚
        bak = rl.versioned_backup(out)
        self.assertIsNotNone(bak)
        self.assertTrue(os.path.exists(bak))
        changed = {k: (v + 1.0).astype(np.float32) for k, v in net.items()}
        rl.save_model(changed, out, meta={"games": 1})
        self.assertFalse(np.array_equal(rl.load_model(out)["W1"], net["W1"]))
        rl.rollback_model(out, bak)
        np.testing.assert_array_equal(rl.load_model(out)["W1"], net["W1"])

        # 训练落盘 best/latest（best 由验证集选择）
        prefix = os.path.join(self.tmp, "ck")
        _, stats = rl.train(games=9, init=net, progress=False, seed=2,
                            eval_every=3, eval_games=3, eval_seed=rl.DEFAULT_VALID_SEED,
                            ckpt_prefix=prefix)
        self.assertTrue(os.path.exists(prefix + ".latest.npz"))
        self.assertTrue(os.path.exists(prefix + ".best.npz"))
        self.assertIsNotNone(stats["best_eval"])
        self.assertEqual(stats["train_seed"], 2)
        self.assertEqual(stats["valid_seed"], rl.DEFAULT_VALID_SEED)
        d = stats["diagnostics"]
        for key in ("episode_len_avg", "grad_norm_avg", "entropy_avg",
                    "value_mse_avg", "grad_clip_ratio"):
            self.assertIn(key, d)
        # 元数据随检查点持久化
        meta = rl.load_meta(prefix + ".best.npz")
        self.assertEqual(meta.get("train_seed"), 2)
        self.assertIn("lr", meta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
