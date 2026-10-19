# ARCHIVE · V6 后台求解交付收口（2026-10-12）

## 范围
本轮仅针对 V6/V6.1/V6.2 正式程序的后台求解，完成：

1. **UI 简化**：删除「结果回传」配置区、N 步/N 时间选择器、间隔下拉、冗余说明与重复状态栏；
   进度并入既有求解状态区；后台隐藏无意义进度条；保留唯一一套 开始/暂停/继续/停止。
2. **固定回传**：内部单一常量（当前 **500ms**）；偏好迁移 v3（清理旧 `report_mode/report_value`）。
3. **暂停“未响应”根因修复**：GUI 主线程不再逐笔落盘——回放期延迟 I/O，校验后**单次原子提交**。
   536 步暂停：**111,009 ms → 58 ms**；暂停期写入 1072 CSV+1486 JSON → **1 CSV+3 JSON**。
4. **暂停后不再发周期回传**：回传前先判定取消/暂停；GUI 在 PAUSING/STOPPING 丢弃在途帧。
5. **暂停常驻期 stop 可协作退出**（此前被等待循环忽略）。
6. **跨会话 revision 重置**（修复“第二次开始前盘收不到数据”）；
   时间策略**首步立即回传**（缩短开始空窗）。
7. **每批只渲染最新一帧**（合并旧帧，避免末尾连闪多批步长切片）。
8. **三模式观效**：standard 粒子+A/B 动态；fast 关粒子、保留动态方向光；
   background 关粒子/仅步动画/流光计时器，静态方向提示。

## 修改文件
- `v6_pyqt_2048_accelerated/v6_background.py`
- `v6_pyqt_2048_accelerated/v6_speed.py`
- `v6_pyqt_2048_accelerated/headless/game_loop.py`
- `v6_pyqt_2048_accelerated/headless/worker_main.py`
- `v6_pyqt_2048_accelerated/tests/test_v6_headless.py`
- `v6_pyqt_2048_accelerated/tests/test_v6_report_policy.py`
- `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py`
- `v6_pyqt_2048_accelerated/tests/test_gui_integration.py`
- `v6_pyqt_2048_accelerated/config/ui_prefs.json`（迁移结果：`report_prefs_version=3`, `report_interval_ms=500`）
- `README.md`（系列博客排版优化）

## 门禁（真实退出码）
| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s .`（cwd=`tests`） | **105 tests OK（skipped=3），EXIT 0** |
| `V6_RUN_IPC_E2E=1 … WorkerOwnershipLifecycleTest WorkerE2ETest` | **3 tests OK，EXIT 0** |

关键实测：500ms 回传间隔均值 **507.4ms**；运行期 GUI 主线程最大阻塞 **47.9ms**；
暂停（301 方向）回放 **23.4ms**、暂停墙钟 **145.7ms**、含暂停最大阻塞 **128.3ms**。

## 证据索引
- `20261012_bg_closure/`：UI 简化报告、7 张真实整窗截图、1000ms 时间线、各轮门禁日志
- `20261012_bg_pause_fix/`：暂停根因与修复报告、暂停耗时前后对比、1000 步实测、
  500ms 时间线与 GUI 校验、跨会话/首帧复现、各轮门禁日志

> 运行时 `*_staging/` 检查点目录不纳入归档。

## 安全声明
V1–V5 源文件、正式对局存档、最高分与撤销历史、`rl_model.npz`、历史实验均**未修改**；
未重新训练；常驻 worker 均通过受支持的控制通道（`control.json: quit`）清理；
**本次仅本地提交，未 push**。
