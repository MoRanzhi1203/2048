# V5/V6 AI 方向提示 —— B 层流光通道分布修复报告（Channel Distribution Fix）

- 仓库：`e:\PyQt5_demo\2048`
- 基线 HEAD：`d71a7a3`（本轮未提交）
- 运行环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`
- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261012_ai_hint_channels/`（本轮新增，不覆盖旧实验）
- 硬约束：不在棋盘外轮廓外新增像素；不覆盖瓦片/数字；保留 A 层暖白与单时钟/局部刷新/静态缓存；保护 V1–V4、存档、模型；不自动提交 Git。**人工视觉结论保持 `UNVERIFIED`。**

---

## 1. 根因（专项：B 层通道被截断）

- 代码事实：`_SolverHintOverlay._STREAK_COUNT = 2`，且 `_gap_centers()` 以
  `return centers[:2] if self._STREAK_COUNT <= 2 else centers` **固定截取三条内部缝隙中的前两条**。
- 后果：`up/down` 只有靠左的两条**纵向**缝隙、`left/right` 只有靠上的两条**横向**缝隙参与流光；第三条通道长期缺失。
- 真实截图量化（修复前整窗截图裁剪后按通道计数，阈值 L>190）：

| 版本/方向 | 通道1 | 通道2 | **通道3** |
| --- | --- | --- | --- |
| v5 up/down/left/right | 90/87/90/90 | 90/90/90/90 | **0 / 0 / 0 / 0** |
| v6 up/down/left/right | 90/90/87/87 | 86/90/90/90 | **0 / 0 / 0 / 0** |

第 3 通道恒为 **0** —— 与用户日志描述完全一致。

---

## 2. 修改清单（本轮增量）

| 文件 | 改动 |
| --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | `_STREAK_COUNT: 2 → 3`；`_gap_centers()` **删除 `centers[:2]` 截断**，恒返回三条内部缝隙中心；更新类 docstring |
| `v5_pyqt_2048_solver/test_solver.py` | 新增 `test_hint_flow_three_channels_all_directions`（四方向三通道覆盖 + 多相位无空通道 + 逐通道朝目标边运动） |
| `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py` | 新增同名测试（验证 V6 继承同一实现且三通道行为一致） |

核心改动（`_gap_centers`，通道中心全部由只读常量推导，无写死坐标）：

```python
def _gap_centers(self):
    pad = float(v4.BOARD_PADDING); size = float(v4.TILE_SIZE); gap = float(v4.TILE_GAP)
    step = size + gap
    return [pad + size + gap / 2.0 + k * step for k in range(3)]
```

相位错开沿用既有的 `tt = (self._phase + i / n) % 1.0`（n=3），三条光梭轻微错相、可见度相近；A 层、裁剪、单时钟、dirty-rect、QPixmap 缓存、A-only 降级路径均**未改动**。

---

## 3. 通道坐标（4×4 棋盘，逻辑像素）

由 `BOARD_PADDING=10`、`TILE_SIZE=96`、`TILE_GAP=10`（step=106）推导：

> **中心 = 10 + 96 + 5 + k × 106 = 111 + 106k → {111, 217, 323}**（k=0,1,2）

| 方向 | 参与缝隙 | 通道中心 | 光梭运动轴范围 |
| --- | --- | --- | --- |
| up / down | **全部 3 条纵向缝隙** | x = 111, 217, 323 | y ∈ [12, 422] |
| left / right | **全部 3 条横向缝隙** | y = 111, 217, 323 | x ∈ [12, 422] |

---

## 4. 前后对照

### 4.1 三通道覆盖（真实 Qt 渲染，逐帧采样，DPR 1.0）

| 方向 | 通道1 最小/帧 | 通道2 最小/帧 | 通道3 最小/帧 | 永久空通道 |
| --- | --- | --- | --- | --- |
| up | 138 | 136 | 136 | 无 |
| down | 136 | 136 | 136 | 无 |
| left | 136 | 136 | 136 | 无 |
| right | 136 | 136 | 136 | 无 |

（DPR 1.25：三通道最小 190–192；DPR 1.5：最小 266–269。全部方向无空通道。）

### 4.2 运动方向（决定性几何，逐通道按其自身相位扫掠）

`_flow_items` 头部坐标随自身相位变化：down/right **单调递增**、up/left **单调递减**，四方向 × 三通道全部成立
（`motion_direction_toward_target = {up:true, down:true, left:true, right:true}`）。

### 4.3 真实整窗截图裁剪（无后期美化）三通道计数

| 版本/方向 | 通道1 | 通道2 | 通道3 |
| --- | --- | --- | --- |
| v5 up | 90 | 90 | **90** |
| v5 down | 90 | 88 | **90** |
| v5 left | 90 | 90 | **90** |
| v5 right | 87 | 87 | **90** |
| v6 up/down/left/right | 87/87/90/87 | 87/87/90/87 | **90/90/90/90** |

第 3 通道由 0 → **≈87–90**，与前两条通道相当。运动帧（down，4 相位）三通道同样恒有流光：

```
MOTION v5 p200/500/800/1100 : [90,88,90] / [90,90,90] / [86,90,90] / [87,90,90]
MOTION v6 p200/500/800/1100 : [90,88,87] / [90,90,90] / [86,90,90] / [90,87,90]
```

### 4.4 交付图像

- **修复前**整窗四方向：`before_{v5,v6}_{up,down,left,right}.png`
- **修复后**整窗四方向（真实 Windows，含原生标题栏）：`after_{v5,v6}_{up,down,left,right}.png`，并同步写入各版本 `screenshots/full_suggest_*.png`
- 棋盘局部（原图直接裁剪）：`board_after_{v5,v6}_{up,down,left,right}.png`
- 四方向对照拼图：`hint_channels_directions_after_{v5,v6}.png`
- 流光运动帧（4 相位）+ 拼图：`boardmotion_after_{v5,v6}_p{200,500,800,1100}.png`、`hint_channels_motion_after_{v5,v6}.png`
- 捕获日志：`gui_capture_channels.jsonl`（8 条，全部 `ok=true`）

---

## 5. 性能对照（Overlay paintEvent，N=200）

| DPR | 无提示 mean/p95 (ms) | A mean/p95 | **A+B mean/p95** |
| --- | --- | --- | --- |
| 1.00 | 0.0146 / 0.0183 | 0.0894 / 0.1613 | **0.5866 / 0.9661** |
| 1.25（受控模拟） | 0.0126 / 0.0179 | 0.2251 / 0.3732 | **0.7412 / 1.1188** |
| 1.50（受控模拟） | 0.0147 / 0.0210 | 0.1886 / 0.3147 | **0.7431 / 1.0950** |

- 预算（目标）：A+B 平均 ≤2ms、P95 ≤5ms —— **三档 DPR 全部满足**。
- 由 2 条增至 3 条流光后，DPR 1.0 的 A+B 平均由上一轮 0.368ms 升至 0.587ms（+0.22ms），仍在预算内，
  **因此无需降低 FPS 或缩短光梭长度**；三条通道全部保留（未按降级裁掉第三条）。

---

## 6. 硬边界复测（三档 DPR，逐帧采样）

- `outside_outer = 0`、`on_tile = 0`、`other_bands = 0` —— 四方向 × DPR 1.00/1.25/1.50 全部为 0。
- 几何裁剪与 AA 容差沿用上一轮（瓦片/内部各内缩 1 设备像素；外轮廓按圆角矩形判定，不额外膨胀）。

---

## 7. 测试与退出码

| 运行 | 命令 | 用例数 | 结果 | 退出码 |
| --- | --- | --- | --- | --- |
| V5 全量 | `python -m unittest test_solver`（cwd=`v5_pyqt_2048_solver`） | **93** | OK | **0** |
| V6 全量 | `python -m unittest discover -p "test_*.py"`（cwd=`v6_pyqt_2048_accelerated/tests`） | **41** | OK | **0** |

- 注：V5 首次全量运行（机器负载较高时）出现过 1 次与本次改动无关的**时序型偶发失败**（`AssertionError: False is not true`，无 msg，非新增用例）；
  单跑 GUI 类（71 项）与随后两次全量重跑均 `OK`。已如实记录。

---

## 8. 门禁状态

| 门禁 | 状态 |
| --- | --- |
| CHANNEL_COVERAGE_3（四方向三通道均出现流光） | PASS |
| NO_PERMANENT_EMPTY_CHANNEL（多相位最小覆盖 > 0） | PASS |
| MOTION_TOWARD_TARGET_3CH（四方向 × 三通道朝目标边） | PASS |
| BORDER_CONTAINMENT（外轮廓外/瓦片/其他三边 = 0，3 DPR） | PASS |
| A_LAYER_PRESERVED（暖白目标边不变） | PASS |
| PERF_BUDGET（A+B 平均≤2ms、P95≤5ms × 3 DPR） | PASS |
| V5_HINT_RENDER / V6_HINT_RENDER | PASS |
| KEYBOARD_REGRESSION / FOLLOW_HINT_STATE | PASS |
| GUI_AUTOMATED（CAPTURE/STRUCTURE/TEXT） | PASS |
| **GUI_VISUAL** | **UNVERIFIED** |
| **DPI_VISUAL（真实 125%/150%）** | **UNVERIFIED** |

---

## 9. 未验证事项

1. `GUI_VISUAL`：三条流光是否“看起来均匀且不拥挤”须由用户目视确认；自动像素计数不等于人工视觉通过。
2. `DPI_VISUAL`：真实 Windows 125%/150% 未测；本节 1.25/1.50 仅为 `QT_SCALE_FACTOR` **受控模拟**。
3. 独立问题（本轮未改动）：单步跟随模式下求解在途时的用户合法按键仍会被忽略——既有并发语义。
4. 捕获进程偶发在退出阶段返回 `0xC0000005`（Qt 退出期访问冲突），PNG/JSON 仍完整写出；对证据无影响。
