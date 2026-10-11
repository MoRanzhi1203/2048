# 归档：AI 方向提示 A+B 暖白边+流光 → 辨识度增强 → 三通道分布修复（2026-10-12）

- 仓库：`e:\PyQt5_demo\2048`｜分支 `main`（`origin=https://github.com/MoRanzhi1203/2048.git`）
- 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`｜基线 HEAD：`d71a7a3`
- 本轮自 `d71a7a3` 起共有**三轮连续未提交工作**，本归档一并收口。
- 硬约束：V1–V4 只读；保护存档/模型；未重训 RL；未改布局；不在棋盘外轮廓外新增像素；人工视觉保持 `UNVERIFIED`。

## 一、交付内容（三轮）
1. **A+B 暖白边 + 内向流光**（`20261011_ai_hint_ab/`）：用「原生内侧边框暖白高亮（A）+ 格间留白短流光（B）」替换旧的深棕核心高亮。
2. **A+B 辨识度增强**（`20261012_ai_hint_vis_enhance/`）：修复“几乎不可见”——A 改“双层明暗”（峰 0.90 + 暖灰棕过渡边），B 改“短梭形亮段”（2 条、半宽 2.2px、alpha 0.80、26FPS）；A 静态层改 QPixmap 缓存。
3. **B 层三通道分布修复**（`20261012_ai_hint_channels/`）：`_STREAK_COUNT: 2→3` 并删除 `_gap_centers()` 的 `centers[:2]` 截断，使 up/down 用全部 3 条纵向缝隙、left/right 用全部 3 条横向缝隙。

## 二、关键根因与证据
### 2.1 旧 A+B “不明显”
- 真实 Qt 渲染测量：A 层 ΔL≥30 沿边覆盖仅 **≈44%**（暖白被宽渐变摊薄，峰仅 0.80）；B 流光峰 ΔL **≈22**、ΔL≥30 面积 **= 0**（细长白线 alpha 0.32，等同不可见）。
- 无剪裁/坐标/遮挡缺陷。

### 2.2 B 层第 3 通道长期缺失
- 代码：`_STREAK_COUNT=2` 且 `return centers[:2] if self._STREAK_COUNT <= 2 else centers`。
- 真实截图逐通道计数（阈值 L>190）：修复前第 3 通道 **恒为 0**；修复后三通道均 **≈87–90**。

## 三、修复后实测（摘要）
| 指标 | 结果 |
| --- | --- |
| A 沿边亮区占比 | 44% → **73.7%**（目标区间 65%–80%） |
| B 流光峰值 ΔL | 22 → **≈59**；ΔL≥30 面积 0 → **≈124px** |
| 真实截图目标边亮度 | 227.4 vs 其余三边 175.7（**ΔL +51.7**，四方向一致） |
| 三通道覆盖（真实渲染逐帧最小） | DPR1.0 136–138｜1.25 190–192｜1.5 266–269，无空通道 |
| 真实截图三通道计数 | 修复前 `[…, …, 0]` → 修复后 `≈[87‑90, 87‑90, 87‑90]` |
| 运动方向 | 四方向×三通道全部朝目标边（down/right 递增、up/left 递减） |
| 硬边界（3 DPR） | `outside_outer=0 / on_tile=0 / other_bands=0` |
| Overlay A+B 绘制 | mean/p95(ms)：1.0 → 0.587/0.966｜1.25 → 0.741/1.119｜1.5 → 0.743/1.095（均 ≤2/≤5ms 预算） |
| 通道中心 | 由常量推导：`111 + 106k = {111, 217, 323}`（无写死坐标） |

## 四、测试与退出码
| 运行 | 用例数 | 结果 | 退出码 |
| --- | --- | --- | --- |
| V5 `python -m unittest test_solver` | 93 | OK | 0 |
| V6 `python -m unittest discover` | 41 | OK | 0 |

> 备注：V5 曾有一次全量运行在机器高负载下出现 1 次与本次改动无关的时序偶发失败；单跑 GUI 类（71）与两次全量重跑均 OK。

## 五、代码改动
| 文件 | 变更 |
| --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | 重写 `_SolverHintOverlay`（A 双层暖白 + B 短梭形；QPixmap 缓存；三通道全参与） |
| `v5_pyqt_2048_solver/test_solver.py` | A+B 亮度/边界测试更新；新增三通道覆盖测试 |
| `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py` | 同步 A+B 共享渲染器断言 + 三通道覆盖测试 |
| `tools/capture_gui.py` | 沿用（四方向 `suggest_*` 场景） |

## 六、证据目录（均已随本次归档提交）
- `v6_pyqt_2048_accelerated/experiments/v6_1/20261011_ai_hint_ab/`
- `v6_pyqt_2048_accelerated/experiments/v6_1/20261012_ai_hint_vis_enhance/`
- `v6_pyqt_2048_accelerated/experiments/v6_1/20261012_ai_hint_channels/`

## 七、未验证事项（持续有效）
1. `GUI_VISUAL`：三轮的“是否足够明显/三条流光是否均匀”均须用户目视确认；自动像素/亮度达标不等于人工视觉通过。
2. `DPI_VISUAL`：真实 Windows 125%/150% 未测，仅 `QT_SCALE_FACTOR` 受控模拟。
3. 独立问题（未改动）：单步跟随模式下求解在途时用户合法按键被忽略——既有并发语义。
4. 捕获进程偶发在退出阶段返回 `0xC0000005`（Qt 退出期访问冲突），PNG/JSON 仍完整写出。
