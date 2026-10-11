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
import time
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import rl_2048 as rl                                              # noqa: E402
import solver_2048 as S                                           # noqa: E402

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

    # ---------------- H2.9 RL 推理模型缓存（正确性 + 文件替换失效） ----------------
    def test_rl_inference_cache(self):
        net = rl.init_net(np.random.RandomState(5))
        p = os.path.join(self.tmp, "cached_model.npz")
        rl.save_model(net, p, meta={"gen": 0})
        S._RL_MODEL_CACHE["key"] = None                    # 清空缓存，隔离测试
        S._RL_MODEL_CACHE["net"] = None
        calls = {"n": 0}

        def loader(path):
            calls["n"] += 1
            return rl.load_model(path)

        a = S._load_rl_model_cached(p, loader)
        b = S._load_rl_model_cached(p, loader)
        self.assertIs(a, b, "同文件第二次应命中缓存（同一对象）")
        self.assertEqual(calls["n"], 1, "同文件不应重复读盘")
        np.testing.assert_array_equal(a["W1"], net["W1"].astype(np.float32))

        # 文件被原子替换（身份变化）→ 缓存必须失效并重载，不得返回陈旧模型
        time.sleep(0.02)
        net2 = {k: (v + 1.0).astype(np.float32) for k, v in net.items()}
        rl.save_model(net2, p, meta={"gen": 123456})       # 变更内容/大小，确保身份改变
        c = S._load_rl_model_cached(p, loader)
        self.assertEqual(calls["n"], 2, "文件替换后应重新加载")
        self.assertFalse(np.array_equal(c["W1"], a["W1"]), "缓存返回了陈旧模型")

        # cold / warm 延迟（仅测量并打印；不作为加速比结论，避免把 I/O 占比当收益）
        S._RL_MODEL_CACHE["key"] = None
        S._RL_MODEL_CACHE["net"] = None
        t0 = time.perf_counter()
        S._load_rl_model_cached(p, loader)
        cold_ms = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        for _ in range(20):
            S._load_rl_model_cached(p, loader)
        warm_ms = (time.perf_counter() - t0) * 1000.0 / 20.0
        print("\n[RL cache] cold=%.3fms warm=%.4fms (warm=命中缓存, 无磁盘读)" % (cold_ms, warm_ms))

    # ---------------- H2.5 --resume 语义：warm start（非精确断点续训） ----------------
    def test_rl_warm_start_resume_is_not_exact(self):
        """核实 --resume 只恢复权重/元数据（warm start），不恢复 RNG → 非精确续训。

        调用方（CLI）在 --resume 时读取 latest 检查点并交给 train(init=...)，train 内部
        以固定 seed 新建 RNG（不恢复历史 RNG 状态）。因此“连续 N 局”与“K 局后恢复 N-K 局”
        不保证逐位一致——本测试用确定性训练固化这一语义，防止被误宣称成精确断点续训。
        """
        net = rl.init_net(np.random.RandomState(11))
        # 连续 4 局
        cont, _ = rl.train(games=4, init=net, progress=False, seed=42)
        # 先训 2 局，再以“新 RNG（同 seed）”从该权重续训 2 局（模拟 warm start）
        mid, _ = rl.train(games=2, init=net, progress=False, seed=42)
        resumed, _ = rl.train(games=2, init={k: v.copy() for k, v in mid.items()},
                              progress=False, seed=42)
        # warm start 可复现（同输入→同输出）
        resumed2, _ = rl.train(games=2, init={k: v.copy() for k, v in mid.items()},
                               progress=False, seed=42)
        for k in cont:
            np.testing.assert_array_equal(resumed[k], resumed2[k])
        # 但非精确续训：与连续训练结果不同（RNG 未恢复）
        self.assertFalse(np.array_equal(cont["W1"], resumed["W1"]),
                         "warm start 结果与连续训练逐位相同，语义存疑")


if __name__ == "__main__":
    unittest.main(verbosity=2)
