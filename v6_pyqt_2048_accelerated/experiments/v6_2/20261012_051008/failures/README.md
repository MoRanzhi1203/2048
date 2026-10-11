# failures/ —— 本轮无失败项

run_id `20261012_051008` 的全部真实测试与门禁均通过：

- V6 `unittest discover`：62 tests，OK，EXIT 0
- V5 `unittest test_solver`：95 tests，OK，EXIT 0
- C++ `bitboard_tests.exe`：ALL TESTS PASSED，EXIT 0
- 隔离复核：`isolation_pass=true`，无意外改动

因此本目录为空。若后续复现出任何一致性/取消/回退失败，请将最小复现
（seed / 棋盘 / 输入 / 输出 / 完整命令）写入本目录，并在 `test_results.json.failures`
登记，同时按 N2–N4 门禁要求禁用该 native engine 的默认开关。
