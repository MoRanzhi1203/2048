"""V6 Phase 0-F benchmark harness smoke gate.

Purpose
-------
Prove the benchmark harness conditions are runnable and reproducible, and record
a REFERENCE baseline using the FROZEN V5 pure-Python kernel.

This script does NOT measure and does NOT claim any V6 acceleration. The
numpy / numba / cpp backends are probed for availability and reported as
NOT_AVAILABLE until the V6 kernels are implemented (later phases).

Fairness conditions exercised here (see benchmark_spec.md):
  * identical, fixed, reproducible board set (boards.jsonl + sha256 check)
  * recorded seed / python / package versions / thread env
  * separated warm-up and measurement phases
  * structured JSON + CSV output under a timestamped run directory
"""
import argparse
import csv
import gc
import hashlib
import json
import os
import platform
import statistics
import sys
import time

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(BENCH_DIR))
V5_DIR = os.path.join(REPO_ROOT, "v5_pyqt_2048_solver")


def load_boards(path, sha_path):
    with open(sha_path, "r", encoding="ascii") as f:
        expected = f.read().strip()
    with open(path, "rb") as f:
        raw = f.read()
    actual = hashlib.sha256(raw).hexdigest()
    boards = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return boards, expected, actual


def probe_backends():
    """Return a dict backend -> (available, reason, kernel_container)."""
    out = {}

    # reference (frozen V5 pure python) -- always expected to work
    try:
        sys.path.insert(0, V5_DIR)
        import solver_2048 as S
        out["reference"] = (True, "v5_pyqt_2048_solver/solver_2048.py", S)
    except Exception as e:  # pragma: no cover
        out["reference"] = (False, "import failed: %r" % (e,), None)

    for name, mod in (("numpy", "numpy"), ("numba", "numba")):
        try:
            __import__(mod)
            out[name] = (False, "package present but V6 %s kernel not implemented yet" % name, None)
        except Exception as e:
            out[name] = (False, "package missing: %r" % (e,), None)

    out["cpp"] = (False, "V6 bitboard extension not built yet (Phase 0-D only verified the toolchain)", None)
    return out


def make_kernels(S):
    def move_all_dirs(board):
        for d in S.DIRECTIONS:
            S.move_grid(board, d)

    def evaluate(board):
        S.evaluate(board)

    return {"move_all_dirs": move_all_dirs, "evaluate": evaluate}


def timeit(fn, warmup, repeat):
    for _ in range(warmup):
        fn()
    samples = []
    gc.disable()
    try:
        for _ in range(repeat):
            t0 = time.perf_counter_ns()
            fn()
            samples.append(time.perf_counter_ns() - t0)
    finally:
        gc.enable()
    return samples


def stats(samples):
    return {
        "n": len(samples),
        "mean_ns": statistics.fmean(samples),
        "median_ns": statistics.median(samples),
        "std_ns": statistics.pstdev(samples),
        "min_ns": min(samples),
        "max_ns": max(samples),
        "p95_ns": sorted(samples)[min(len(samples) - 1, int(round(0.95 * (len(samples) - 1))))],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default=os.path.join(BENCH_DIR, "boards.jsonl"))
    ap.add_argument("--boards-sha", default=os.path.join(BENCH_DIR, "boards.sha256"))
    ap.add_argument("--out-dir", default=os.path.join(BENCH_DIR, "reports"))
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--repeat", type=int, default=30)
    args = ap.parse_args()

    boards, expected_sha, actual_sha = load_boards(args.boards, args.boards_sha)
    sha_ok = (expected_sha == actual_sha)

    backends = probe_backends()
    ref_ok, ref_reason, S = backends["reference"]
    if not ref_ok:
        print("RESULT=FAIL reference backend unavailable: %s" % ref_reason)
        return 2

    kernels = make_kernels(S)
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(args.out_dir, "phase0_smoke_" + ts)
    os.makedirs(run_dir, exist_ok=True)

    results = []
    csv_rows = []
    for kname, kfn in kernels.items():
        wrapped = (lambda f=kfn: [f(b["board"]) for b in boards])
        samples = timeit(wrapped, args.warmup, args.repeat)
        st = stats(samples)
        per_board = st["median_ns"] / len(boards)
        results.append({
            "backend": "reference", "kernel": kname,
            "units_per_iteration": len(boards),
            "median_ns_per_iteration": st["median_ns"],
            "median_ns_per_unit": per_board,
            "stats": st,
        })
        for i, s in enumerate(samples):
            csv_rows.append([ "reference", kname, i, s ])

    meta = {
        "phase": "V6 Phase 0-F smoke gate",
        "run_id": ts,
        "note": "REFERENCE baseline only; no V6 acceleration is measured or claimed",
        "python": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "thread_env": {k: os.environ.get(k) for k in
                       ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
        "warmup_iterations": args.warmup,
        "measured_iterations": args.repeat,
        "boards_file": os.path.relpath(args.boards, REPO_ROOT).replace("\\", "/"),
        "boards_count": len(boards),
        "boards_sha256_expected": expected_sha,
        "boards_sha256_actual": actual_sha,
        "boards_sha256_match": sha_ok,
        "backend_availability": {k: {"available": v[0], "reason": v[1]} for k, v in backends.items()},
        "timing_boundary": "warm-up separated from measured loop; gc disabled during measurement",
        "results": results,
    }

    with open(os.path.join(run_dir, "smoke.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    with open(os.path.join(run_dir, "smoke.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["backend", "kernel", "iteration", "duration_ns"])
        w.writerows(csv_rows)

    print("run_dir=", run_dir)
    print("boards=", len(boards), "sha256_match=", sha_ok)
    for k, v in backends.items():
        print("backend %-10s available=%s (%s)" % (k, v[0], v[1]))
    for r in results:
        print("kernel %-14s median=%.1f us/iter  %.3f us/board"
              % (r["kernel"], r["median_ns_per_iteration"] / 1000.0,
                 r["median_ns_per_unit"] / 1000.0))
    print("RESULT=" + ("OK" if sha_ok else "FAIL:boards_sha256_mismatch"))
    return 0 if sha_ok else 1


if __name__ == "__main__":
    sys.exit(main())
