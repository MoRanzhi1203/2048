# 归档：V5/V6 方向键冲突修复 + 单步建议常驻跟随预测（2026-10-11）

- 仓库：`e:\PyQt5_demo\2048`｜分支 `main`（`origin=https://github.com/MoRanzhi1203/2048.git`）
- 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`
- 关联上游：V6.1（原生搜索性能/发布收口）证据目录 `v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`

## 一、本轮交付内容
1. **单步建议 → 常驻跟随预测（V5 实现，V6 继承）**：给出建议后保持待命；用户每走一步，动画结束后自动重算下一步最优解；棋盘上高亮建议方向；点「停止」结束并清除高亮。
2. **方向键冲突修复（V5/V6）**：四个方向键在游戏页统一只走棋盘，聚焦控件（QComboBox/QPushButton/QSplitter）不再抢占。
3. **测试隔离缺陷修复**：消除 GUI 测试类“只 hide 不 close”导致的单实例锁模态死锁。

## 二、问题根因与直接证据
### 2.1 方向键被聚焦控件抢占（静态审计 + QTest 复现）
- 方向键仅在“获得焦点的子控件**忽略**它”时才冒泡到 `v4.MainWindow.keyPressEvent`。
- `QComboBox` 消费 `Up/Down` → 改变选项且棋盘不动；`QAbstractButton::keyPressEvent` 消费四方向键（autoExclusive 焦点导航）→ 棋盘不动。
- 复现（离屏 QTest，逐键复位）：`QComboBox` 聚焦 + `Up/Down` → `combo_changed=True, board_moved=False`；`QPushButton` 聚焦 + 任意方向键 → `board_moved=False`。

### 2.2 联合运行死锁（faulthandler 阻塞栈，独立子进程 25s 超时）
```
test_arrow_keys_map_to_moves (...) ... Timeout (0:00:25)!
Thread (most recent call first):
  ui_theme.py:214 exec_choice
  ui_theme.py:237 show_warning
  v4_pyqt_2048_animated.py:1829 _warn_readonly
  test_arrow_keys.py:36  pump
  test_arrow_keys.py:111 test_arrow_keys_map_to_moves
```
- **根因**：`test_storage_isolation`/`test_gui_integration` 只 `hide()` 窗口、不 `close()`，遗留窗口占用**同一存档目录**的单实例锁；后建窗口抢锁失败进入只读，经**延迟定时器**排队模态“只读运行”提示；当后续测试 `pump()` 转起事件循环时模态被弹出，离屏无法关闭 → 死锁。
- **次因**：`test_arrow_keys` 曾在**模块导入期**改写 `2048_HISTORY_DIR`，污染 `test_storage_isolation.test_paths_under_v6`。

## 三、修复差异（仅测试/子类，未改 V1–V4 源码，未删锁、未关测试）
| 文件 | 变更 |
| --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | 新增 `_ArrowKeyRouter` + `_consume_arrow`（应用内单一方向键入口）；单步建议改为常驻跟随；新增 `_SolverHintOverlay` 方向高亮；`closeEvent` 移除过滤器 |
| `v5_pyqt_2048_solver/test_solver.py` | 更新 3 个单步用例至新语义；新增 9 项方向键 QTest 回归 + 1 项跟随用例 |
| `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py` | 新增：V6 方向键回归 7 项（含后端切换一致性） |
| `v6_pyqt_2048_accelerated/tests/test_storage_isolation.py` | `tearDownClass` 由 `hide()` 改为**完整 `close()`** + `processEvents` |
| `v6_pyqt_2048_accelerated/tests/test_gui_integration.py` | `setUpClass` 隔离 `2048_HISTORY_DIR`（独立临时目录，保存旧值）；`tearDownClass` **完整 `close()`** + 异常安全恢复环境 |
| `tools/capture_gui.py` | `suggest` 场景文案改为跟随语义并展示棋盘高亮 |
| `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py`（新增） | 不在导入期改环境；`setUpClass` 隔离 + `tearDownClass` `close()`/恢复 |

方向键路由规则（`_consume_arrow`）：仅当“本窗口可见 + 焦点在本窗口内 + 无模态对话框 + 非输入控件”时生效；游戏页可见 → `on_move` 一次移动；其他页 → 仅消费不操作；否则放行原生。过滤器由 V5 安装一次，V6 继承不重复安装。

## 四、测试与门禁（实际退出码）
| 运行 | 数量 | 退出码 |
| --- | --- | --- |
| storage+gui+arrow（正序） | 18 | 0 |
| arrow+gui+storage（反序） | 18 | 0 |
| V6 完整回归（6 模块） | 39 | 0 |
| V5 受影响回归 `test_solver` | 89 | 0 |
| 根跨版本 7 脚本（expectimax/mcts/rl/cross_version/popups/bench） | 全部 OK | 0 |

| 门禁 | 状态 |
| --- | --- |
| V5_KEYBOARD_ROUTING | PASS |
| V6_KEYBOARD_ROUTING | PASS |
| TEST_ISOLATION | PASS |
| GUI_VISUAL / DPI | UNVERIFIED（未人工目视） |

## 五、截图与未验证
- V6 整窗截图（含 `full_suggest.png` 展示方向高亮）：`CAPTURE/STRUCTURE/TEXT=PASS`，`VISUAL=UNVERIFIED`；采集记录 `experiments/v6_1/20261011_195221/gui_capture_after_follow_mode.jsonl`。
- 未验证：GUI 人工视觉、真实 125%/150% DPI。
- 约束遵守：未重训 RL、未大规模对局、未改 V1–V4 源码、未在有证据前猜测改动。
