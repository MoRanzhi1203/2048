# AI 推荐方向提示 A 层「内嵌明暗轮廓」优化报告（2026-10-12）

- 仓库：`e:\PyQt5_demo\2048`｜分支 `main`｜基线 HEAD：`4c75d80`
- 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`｜真实 Windows 图形平台
- 硬约束：V1–V4 只读；保护真实存档与正式 RL 模型；未重训；未改算法/按键分发/单步跟随；未自动 Git 提交

---

## 一、根因（实测，真实 Qt 渲染）

旧 A 层在 10px 边框带内只铺一层「沿边渐变暖白」（#FFF4E7/#FFF9F2，峰 alpha 0.90）+ 靠瓦片侧 1.6px 暖灰棕过渡。
逐像素实测（`metrics_before_v5.json`，四方向一致）：

| 采样 | L（Rec709） | RGB |
| --- | --- | --- |
| 主亮面复合色 | 80.84 | 239.0, 231.1, 222.6 |
| 窗外围米白背景 | 93.69 | 250, 248, 239 |
| 对侧普通边框（棋盘棕 #bbada0） | 42.99 | 187, 173, 160 |

- 主亮面与**外围米白背景**亮度接近：ΔL 仅 **−12.85**、ΔE 仅 **5.86**；
- 主亮面与棋盘外沿之间**没有任何深色分隔**（旧实现并无隔离槽：隔离槽采样与亮面同值，ΔE = 0）；
- 边界又被 0.96 跨度的宽渐变摊薄。

⇒ 「白色目标边 / 棋盘棕边 / 米白背景」三层亮度接近且无明暗轮廓，方向识别不清。

---

## 二、方案比选（A/B/C 静态对照，选择 A）

在真实现有 10px 边框带内做三段式「明暗轮廓分离」横截面（自外向内）：

| 方案 | 隔离槽 | 主亮面 | 过渡 | 隔离槽 L | 亮面 L | **ΔE(槽↔亮面)** | ΔE(亮面↔普通边框) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 现状（前） | —（无槽） | #FFF4E7 | #9E8D7F | 80.8 | 80.8 | **0.0** | 20.9 |
| **A 深棕+奶油白（选定）** | **#705B4C** | **#FFF5E8** | **#E0C4A5** | **12.5** | 92.4 | **55.4** | 25.5 |
| B 暖灰+亮白 | #8A7566 | #FFFBF4 | #E6D0B6 | 20.1 | 96.8 | 47.7 | 28.5 |
| C 深棕+纯白 | #5C4636 | #FFFFFF | #C9A177 | 7.9 | 100.0 | 67.9 | 30.6 |

- B 的隔离槽偏浅、分离最弱；C 的纯白亮面 + 极深槽对比最强但偏硬。
- **A** 以「深槽↔亮面」形成 ΔE 55.4 / ΔL −79.9 的明暗轮廓分离，且与项目暖色调一致、不过分刺眼 → **采用 A**。
- 对照图：`compare_ABC_v5_{up,down,left,right}.png`；前/后：`compare_before_after_v5_up.png`。

---

## 三、最终正式样式（仅保留一套）

横截面（外→内，单位=逻辑像素，铺满 10px 边框带）：

| 段 | 颜色 | 厚度 | 不透明度 |
| --- | --- | --- | --- |
| ① 外侧深色隔离槽 | `#705B4C` | ≈1.8px | 0.85（外缘）→0.95（芯部） |
| ② 中部奶油暖白主亮面 | `#FFF5E8` | ≈5.0px | 1.00 |
| ③ 内侧暖杏过渡 | `#E0C4A5` | ≈1.8px | 0.95 → 0.62 → 0（向瓦片侧消隐） |

- 沿边包络：0.5 位置在 **11.5%/88.5%**（两端柔和消隐），亮面识别区 ≈ **77%** 边长；其余三边完全不变。
- B 层三通道短梭形汇聚流光、单时钟 26FPS、局部脏矩形刷新、A 静态层 QPixmap 缓存、A-only 降级**全部保留**。
- 未新增任何可见外围组件（无外侧光轨/箭头/光晕）；不越出外轮廓、不覆盖瓦片。

---

## 四、修改清单（自 `4c75d80`）

| 文件 | 变更 |
| --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | `_SolverHintOverlay`：A 层改为「深色隔离槽 + 奶油暖白亮面 + 暖杏过渡」三段式横截面；新增 `_cross_section()`（横截面渐变）与 `_along_envelope()`（沿边消隐包络），移除旧「单层暖白 + 暖灰棕过渡」；`_edge_pixmap()` 改为**两阶段**：先在**无裁剪**临时层用 `DestinationIn` 合成「横截面 × 沿边包络」（规避 Qt 在抗锯齿裁剪边界上 alpha 相乘错误导致的圆角碎片），再以「外轮廓 ∖ 16 瓦片」裁剪 `SourceOver` 贴出。 |
| `v5_pyqt_2048_solver/test_solver.py` | A 亮区占比断言 65–80% → **72–82%**；新增三段式结构断言（外侧隔离槽像素显著暗于主亮面 ≥60）。 |
| `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py` | 同步（V6 复用 V5 渲染器）。 |

> 关键修复：`DestinationIn` 与**抗锯齿裁剪路径**同用时，Qt 光栅器在裁剪边界像素上 alpha 相乘不正确（旧写法在 DPR1.25 圆角处残留 6 个 α8–64 碎片，严格判定为「越界」）。改为「无裁剪合成 → 裁剪 SourceOver 贴出」后，3 档 DPR 严格判定**全 0**。

---

## 五、实测结果（真实 Windows / 真实 Qt 渲染）

### 5.1 目标边 vs 外围背景/普通边框（`metrics_after_{v5,v6}.json`，四方向一致）

| 采样 | L | RGB |
| --- | --- | --- |
| ① 隔离槽 | **12.5** | — |
| ② 主亮面 | **92.4** | (255, 245, 232) |
| ③ 暖杏过渡 | 48.5 | (224, 196, 165) |
| 外围米白背景 | 93.7 | (250, 248, 239) |
| 对侧普通边框 | 43.0 | (187, 173, 160) |

- **ΔE(隔离槽↔主亮面) = 55.4，ΔL = −79.9** → 明暗轮廓分离成立（旧实现为 0.0）。
- ΔE(主亮面↔普通边框) = 25.5，ΔL = +49.4 → 亮面相对棋盘边框仍清晰。
- 静止状态下**四方向**（up/down/left/right）数值完全一致，识别度对等。

### 5.2 边界与结构（`verify_{v5,v6}_dpr{1.0,1.25,1.5}.json`）

| 指标 | V5 | V6 |
| --- | --- | --- |
| 外轮廓越界（像素中心法，3 DPR） | 0 / 0 / 0 | 0 / 0 / 0 |
| 覆盖瓦片像素 | 0 / 0 / 0 | 0 / 0 / 0 |
| 其他三边被改动 | 0 / 0 / 0 | 0 / 0 / 0 |
| 亮面识别区占比 | 77.0 / 77.3 / 77.1 % | 同 |
| 隔离槽↔亮面 R 差（BGRA 序 index2） | ≈149–153 | 同 |
| 叠加层几何 = 棋盘几何（含折叠/展开/缩放） | 全部 True | 全部 True |

### 5.3 性能（复刻 paintEvent 两步绘制，mean/p95，ms）

| DPR | V5 A-only | V5 A+B | V6 A+B | 缓存重建（一次性） |
| --- | --- | --- | --- | --- |
| 1.0 | 0.058/0.060 | **0.585/0.771** | 0.784/1.079 | ≈1.9–3.6 |
| 1.25 | 0.253/0.383 | **1.104/1.684** | 1.080/1.681 | ≈3.2–4.9 |
| 1.5 | 0.350/0.488 | **0.961/1.107** | 1.506/2.210 | ≈4.0–6.3 |

均在既有预算 **≤2ms mean / ≤5ms p95** 内；未降 FPS、未裁通道。

---

## 六、验证矩阵（真实 Windows）

- **V5/V6 四方向**（up/down/left/right）：整窗截图 `after_{v5,v6}_{up,down,left,right}.png`；叠加层越界/瓦片/其他三边全 0，识别区 77%。
- **右栏展开/折叠**：`after_{v5,v6}_collapsed.png`；折叠/展开前后叠加层几何 == 棋盘几何（`geometry.collapsed/expanded` True）。
- **窗口缩放**：棋盘为固定尺寸（`BOARD_SIDE=434`），缩放窗口不改变棋盘；叠加层始终与之等尺寸且不越界（`resize_640x700 / resize_920x820 / resize_back` 均 True）。
- **受控 125%/150% DPI**：`QT_SCALE_FACTOR=1.25/1.5`（真实 DPR 1.25/1.5，见 `dpr_actual`）下越界/瓦片/三边全 0；真实 Windows 系统 125%/150% 缩放仍标记 **UNVERIFIED**（详见第八节）。

---

## 七、测试与退出码

| 运行 | 命令（工作目录） | 用例数 | 结果 | 退出码 |
| --- | --- | --- | --- | --- |
| V5 | `python -m unittest test_solver`（`v5_pyqt_2048_solver/`） | 93 | OK | **0** |
| V6 | `python -m unittest discover -v`（`v6_pyqt_2048_accelerated/tests/`） | 41 | OK | **0** |

> V6 测试为非包目录，需在 `tests/` 目录内执行 `discover`（仓库根 `discover` 不递归到该目录，退出码 5「0 tests」）。

---

## 八、门禁状态

| 门禁 | 状态 |
| --- | --- |
| `CAPTURE_PASS` | PASS（capure_gui `ok=true`，DWM 外框 + screen BitBlt，含原生标题栏） |
| `STRUCTURE_PASS` | PASS（标题栏/图标/控件可见，非空白） |
| `TEXT_PASS` | PASS（全部必需文字对比度 > 0） |
| `VISUAL_PASS` | **UNVERIFIED**（须人工目视确认） |
| `GUI_SCREENSHOT_PASS` | **UNVERIFIED**（依赖 VISUAL_PASS） |
| `BOUNDARY_PASS` | PASS（3 DPR × 2 版本：越界/瓦片/三边均 0） |
| `TEST_PASS` | PASS（V5 93 / V6 41，EXIT=0） |
| `DPI_VISUAL` | **UNVERIFIED**（真实系统 125%/150% 未测，仅 `QT_SCALE_FACTOR` 受控模拟） |

---

## 九、证据文件

- 对照（方案比选）：`compare_ABC_v5_{up,down,left,right}.png`、`cmp_v5_{A,B,C}_up.png`
- 前/后：`compare_before_after_v5_up.png`、`before_v5_*.png` / `after_v5_*.png`
- 最终四方向棋盘+放大：`final_4dir_{v5,v6}.png`、`board_{v5,v6}_A_{up,down,left,right}.png`
- 整窗（前）：`before_{v5,v6}_{up,down,left,right}.png`；（后）：`after_{v5,v6}_{up,down,left,right,collapsed}.png`
- 实测 JSON：`metrics_before_v5.json`、`metrics_{A,B,C}_v5.json`、`metrics_after_{v5,v6}.json`、`verify_{v5,v6}_dpr{1.0,1.25,1.5}.json`

---

## 十、补充（2026-10-12）：自动连走（auto）同样显示该高亮

**变更**：`v5_pyqt_2048_solver.py` 的 `_on_solver_result` 自动连走分支，在 `_ai_apply(direction)` 之前调用 `self._show_hint(direction)`
——即「自动连走」也复用同一套 V5 `_SolverHintOverlay`（A 内嵌明暗轮廓 + B 三通道流光），高亮 AI 本步所走方向；
停止/结束/新游戏/继续/切换模式即清除（沿用既有 `_clear_hint` 生命周期）。
同步微调模式下拉与面板就绪提示文案（说明两种模式都会高亮）。

**运行期实测**（`hint_auto_check.py`，真实 Qt）：auto 运行 4s，214 次采样中 213 次高亮层可见，
`hint_directions_seen={down,left}`、`flow_timer_active=true`、`overlay_geometry == board_geometry == [434,434]`；
停止后 `_hint_direction=None`、高亮层隐藏、动画时钟停止。

**测试**：V5 新增 `test_auto_mode_also_shows_hint`；`python -m unittest test_solver` **94 PASS / EXIT=0**；
V6 `discover -v` **41 PASS / EXIT=0**。

**整窗截图**：`auto_v5_hint.png`、`auto_v6_hint.png`（`tools/capture_gui.py --version v5|v6 --scene auto`，新增 `auto` 场景）。
门禁：CAPTURE/STRUCTURE/TEXT PASS；`VISUAL_PASS` 保持 **UNVERIFIED**。

---

## 十一、补充（2026-10-12）：求解进行中可切换算法模型（热切换）

**变更**：`v5_pyqt_2048_solver.py`
- 新增 `_hot_update_solver_config()`：求解进行中切换「算法」或「运行方式（强度）」时，**热更新** `_solver_config`；
  自增 `_job_id` 作废旧任务身份、置位在途取消令牌（协作式取消）、清空 `_solve_in_flight/_pending_result`，
  写日志「切换算法：…（后续步骤按新算法计算）」后立即 `_request_decision()` 按新算法重算。
- `_on_strategy_changed()` 末尾接入热切换；新增 `_on_preset_changed()` 并连接 `solver_depth.currentIndexChanged`（未运行时仅刷新文案）。
- `new_session()` 新增 `strategy_changes` 记录；`session_rows()` 的算法列按「起始 → 后续」链路展示，避免导出会话与实际过程不符。
- 算法下拉补充提示「求解进行中切换会立即生效」。

**V5 运行期实测**：单步建议下 heuristic→MCTS 切换，`_solver_config.strategy` 热更新为 `mcts`、`_job_id` 自增、
在途取消令牌被置位、会话记录 2 次切换、摘要显示「启发式 → MCTS」；新算法给出建议后仍处跟随状态；停止即清除高亮。

**V6 运行期实测**（复用 V5 GUI，numba/cpp 后端）：heuristic 给出建议「向下」→ 切换 MCTS →
`session_row_strategy = 启发式 → MCTS`、`job_bumped = true`、切换后新建议到达（MCTS 深度 16，118.8ms）、停止后高亮清除。

**测试**：V5 新增 `test_strategy_switch_while_running`（含「在途计算期间再次切换」路径）；
`python -m unittest test_solver` **95 PASS / EXIT=0**；V6 `discover -v` **41 PASS / EXIT=0**。

**V6 同步补齐（同日追加）**：
- `v6_pyqt_2048_accelerated/tests/test_gui_integration.py` 新增 3 条回归：`test_auto_mode_shows_hint`、
  `test_strategy_switch_while_running`（含会话 `strategy_changes` 与 `session_rows` 链路）、
  `test_ui_config_guard_not_defeated_by_backend`；该类的 `setUpClass/tearDownClass` 增加
  `V6_RESULT_DIR/V6_EXPORT_DIR/V6_SESSIONS_FILE` 临时目录重定向（用例会真实启停求解，避免污染仓库 `solver_results/`）。
- 守卫修正（V5，通用）：`_hot_update_solver_config` 改为与「界面产出配置快照」`self._ui_solver_config`
  比较（`_init_solver`/`_start_solver` 中同步维护），不再因 V6 向 `_solver_config` 注入 `backend` 而失去早退。
- 复跑：V5 **95 PASS / EXIT=0**；V6 **44 PASS / EXIT=0**（41 + 3）。


> 说明：未改动的既有约束——「模式（自动连走/单步建议）」仍在「开始求解」时读取；本次仅按需求放开「算法模型」的运行时切换。


