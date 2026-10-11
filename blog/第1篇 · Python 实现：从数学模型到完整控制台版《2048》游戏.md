# 第1篇 · Python 实现：从数学模型到完整控制台版《2048》游戏

**2048** 的规则可概括为一句话：在 4×4 棋盘上把方块整体推向某个方向，相同的数字合并成两倍，随后系统在空位随机补一块，直到无法移动（或合出 2048）。规则简单并不意味着实现可以随意，它的每一步都能写成明确的数学对象：状态矩阵、转移函数、随机生成分布与判定函数。

如果说后面几篇的 PyQt5 版本是上层建筑，那么这一篇搭建的是它的**地基与承重结构**：界面、动画、AI 求解都只是在同一套规则之上更换渲染与决策方式，规则本身一行都不改。

先用控制台版起步，是为了让这套基础逻辑可验证：没有界面干扰，逻辑对错可直接观察并逐条单测；若一开始就编写 GUI，规则缺陷会与界面缺陷相互耦合，难以定位。代价是交互形式简单：每次移动都要整屏刷新，且只能使用键盘。

本文将从**状态表示、方块移动与合并、胜负判定、控制台显示与主循环**等方面，结合完整 Python 代码，系统讲解 2048 的数学模型与实现。

**导入库**：

```python
import random
import os
import msvcrt  # Windows下的键盘输入处理
```

------



## 1 模块 1：状态表示与初始化

### 1.1 模块 1 - 数学模型

#### 1.1.1 状态矩阵定义

定义游戏在时刻 $t$ 的状态矩阵为：
$$
 S_t =
 \begin{bmatrix}
 s_{11}(t) & s_{12}(t) & \dots & s_{1n}(t) \\
 s_{21}(t) & s_{22}(t) & \dots & s_{2n}(t) \\
 \vdots & \vdots & \ddots & \vdots \\
 s_{n1}(t) & s_{n2}(t) & \dots & s_{nn}(t)
 \end{bmatrix}
$$


其中
$$
s_{ij}(t) \in \{0, 2, 4, 8, \dots\}, \quad i, j \in \{1,2,3,4\}
$$
表示第 $i$ 行第 $j$ 列方格中的数值。若 $s_{ij}(t) = 0$，则该格为空。

#### 1.1.2 游戏全局状态

定义整体游戏状态为：
$$
S_t^{\text{game}} = (S_t, \text{score}_t, \text{best\_score}_t, \text{won}_t, \text{game\_over}_t)
$$
初始状态为：
$$
S_0^{\text{game}} = (S_0', 0, 0, \text{False}, \text{False}), \quad
 S_0' = S_0 + P_1 + P_2
$$
其中 $P_1, P_2$ 为随机生成的初始方块矩阵。

#### 1.1.3 随机生成新方块

空格集合定义为：
$$
E_t = \{(i,j) \mid s_{i,j}(t) = 0\}
$$
在空格集合中随机选择位置：
$$
(i^*, j^*) = \text{随机选择}(E_t)
$$
生成新方块值：
$$
s_{i^*,j^*}(t+1) =
 \begin{cases}
 2, & \text{概率 } 0.9 \\
 4, & \text{概率 } 0.1
 \end{cases}
$$



### 1.2 模块 1 - 代码实现


下面展示该部分的 Python 实现，对应公式的每一个步骤：

```python
def __init__(self, grid_size=4):
    """初始化游戏"""
    self.grid_size = grid_size
    self.grid = [[0] * grid_size for _ in range(grid_size)]
    self.score = 0
    self.best_score = 0
    self.game_over = False
    self.won = False

    # 初始化游戏，添加两个方块
    for _ in range(2):
        self.add_new_tile()

def add_new_tile(self):
    """在随机空位置添加新方块（2或4）"""
    # 找出所有空白格坐标
    empty_cells = [(i, j) for i in range(self.grid_size)
                   for j in range(self.grid_size) if self.grid[i][j] == 0]
    if not empty_cells:
        return False

    # 随机选取空格
    i, j = random.choice(empty_cells)

    # 以90%概率生成2，10%概率生成4
    self.grid[i][j] = 2 if random.random() < 0.9 else 4
    return True
```



### 1.3 模块 1 - 逻辑说明

**初始化阶段：**

- 创建一个 $4\times4$ 的零矩阵；
- 随机生成两个初始方块；
- 初始化分数、最高分及游戏状态。

**数学意义：**

- 游戏从空棋盘（零矩阵）开始，随机性使每局初始状态不同，形成状态空间的多样性。



### 1.4 初始状态可视化示例

初始状态可能如下（用矩阵形式）：
$$
S_0' =
 \begin{bmatrix}
 0 & 2 & 0 & 0 \\
 0 & 0 & 0 & 0 \\
 0 & 0 & 0 & 4 \\
 0 & 0 & 0 & 0
 \end{bmatrix}
$$

------



## 2 模块 2：方块移动与合并

### 2.1 模块 2 - 数学模型

#### 2.1.1 单行压缩与合并

对一行向量 $L = [s_1, s_2, s_3, s_4]$ 先去除零元素：
$$
L' = [s_i \mid s_i \neq 0]
$$
合并规则：
$$
s_j' =
 \begin{cases}
 2 s_j, & s_j = s_{j+1} \\
 s_j, & \text{否则}
 \end{cases}
$$
合并后删除重复元素，并在右端填充零：
$$
 L'' = \text{补零}(L')
$$
分数更新为：
$$
\text{score}_{t+1} = \text{score}_t + \sum_{\text{合并的方块}} s_j
$$


#### 2.1.2 四个方向的移动矩阵

- 向左（Left）：
  $$
  S_t' = [\_merge\_line(R_i) \mid R_i \in S_t]
  $$

- 向右（Right）：
  $$
  S_t' = [\text{反转}(\_merge\_line(\text{反转}(R_i))) \mid R_i \in S_t]
  $$

- 向上（Up）：
  $$
  S_t' = \text{转置}([\_merge\_line(R_i) \mid R_i \in \text{转置}(S_t)])
  $$

- 向下（Down）：
  $$
  S_t' = \text{转置}([\text{反转}(\_merge\_line(\text{反转}(R_i))) \mid R_i \in \text{转置}(S_t)])
  $$



### 2.2 模块 2 - 代码实现

```python
# ========= 移动与合并逻辑 =========
def _merge_line(self, line):
    """
    合并单行（核心算法）
    返回新行和是否发生移动的标志
    """
    original = list(line)
    # 1. 压缩非零元素
    compressed = [num for num in line if num != 0]
    
    # 2. 合并相邻相同数字（合并后索引一次跳两格，避免 [x, x, x, x] 下标错位）
    merged = []
    i = 0
    while i < len(compressed):
        if i + 1 < len(compressed) and compressed[i] == compressed[i + 1]:
            merged.append(compressed[i] * 2)
            self.score += compressed[i] * 2
            i += 2
        else:
            merged.append(compressed[i])
            i += 1
    
    # 3. 补零到原始长度
    merged += [0] * (self.grid_size - len(merged))
    
    # 4. 返回新行与是否移动
    return merged, merged != original

def _move(self, direction):
    """
    通用移动逻辑
    direction: 'up', 'down', 'left', 'right'
    """
    moved = False
    
    # 上/下移动需要先转置
    if direction in ('up', 'down'):
        self.grid = [list(row) for row in zip(*self.grid)]
    
    for i in range(self.grid_size):
        row = self.grid[i][::-1] if direction in ('right', 'down') else self.grid[i]
        new_row, has_moved = self._merge_line(row)
        if direction in ('right', 'down'):
            new_row.reverse()
        self.grid[i] = new_row
        moved = moved or has_moved
    
    # 上/下移动还原
    if direction in ('up', 'down'):
        self.grid = [list(row) for row in zip(*self.grid)]
    
    return moved
```



### 2.3 模块 2 - 逻辑说明

1. **单行处理核心：** `_merge_line` 统一完成压缩、合并、补零和得分更新。
2. **方向抽象化：** `_move` 根据方向决定是否需要行翻转或矩阵转置，从而只用一套逻辑处理四个方向。
3. **移动标志：** 每次移动会返回 `moved=True` 或 `False`，用于判断是否生成新方块。



### 2.4 示意矩阵变化

假设某行初始状态：
$$
R = [2, 0, 2, 4]
$$

- **压缩非零元素：**
   $$
   [2, 2, 4]
   $$
- **合并：**
   $$
   [4, 4, 0]
   $$

- **得分增加 4（2+2）**
- **补零完成最终行：**
   $$
   [4, 4, 0, 0]
   $$

------



## 3 模块 3：胜负判断与游戏结束检测

### 3.1 模块 3 - 数学模型

#### 3.1.1 胜利条件

若存在某格值为 $2048$，则胜利：
$$
\text{won}_t =
 \begin{cases}
 \text{True}, & \exists i,j: s_{i,j}(t) = 2048 \\
 \text{False}, & \text{否则}
 \end{cases}
$$


#### 3.1.2 游戏结束条件

若无法移动，则游戏结束。具体条件为：

1. 棋盘无空格：
   $$
   \forall i,j: s_{i,j}(t) \neq 0
   $$

2. 水平方向和垂直方向不存在相邻相同方块：

   $$
    \forall i,j<4: s_{i,j} \neq s_{i,j+1} \text{ 且 } s_{j,i} \neq s_{j+1,i}
   $$

若满足以上条件，则：
$$
\text{game\_over}_t = \text{True}
$$

#### 3.1.3 重置游戏

更新最高分：

$$
\text{best\_score}_{t+1} = \max(\text{best\_score}_t, \text{score}_t), \quad \text{score}_{t+1} = 0
$$
清空棋盘并重置状态：

$$
S_{t+1} = O_{4\times4}, \quad \text{won}_{t+1} = \text{game\_over}_{t+1} = \text{False}
$$
随机生成两个初始方块：

$$
S_0' = S_0 + P_1 + P_2
$$



### 3.2 模块 3 - 代码实现

```python
# ========= 状态检测 =========
def check_win(self):
    """检查是否有 2048 方块"""
    if any(2048 in row for row in self.grid):
        self.won = True

def check_game_over(self):
    """检查是否无法移动"""
    # 1. 检查是否有空格子
    if any(0 in row for row in self.grid):
        return False
    
    # 2. 检查水平和垂直方向是否有可合并方块
    for i in range(self.grid_size):
        for j in range(self.grid_size - 1):
            if self.grid[i][j] == self.grid[i][j + 1]:
                return False
            if self.grid[j][i] == self.grid[j + 1][i]:
                return False
    
    # 3. 无法移动，则游戏结束
    self.game_over = True
    return True

def reset_game(self):
    """重置游戏"""
    # 更新最高分
    self.best_score = max(self.best_score, self.score)
    self.score = 0
    self.game_over = self.won = False
    
    # 清空棋盘
    self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
    
    # 初始化两个方块
    for _ in range(2):
        self.add_new_tile()
```



### 3.3 模块 3 - 逻辑说明

1. **胜利检测**
   - 使用 `any()` 判断棋盘中是否存在 2048 方块。
   - 一旦出现，设置 `self.won = True`，但游戏可继续进行以追求更高分数。
2. **游戏结束检测**
   - 首先检查是否存在空格子，有空格子则游戏未结束。
   - 然后检查所有相邻行列是否有相同方块，有则可合并，游戏未结束。
   - 如果没有空格子且无法合并，则游戏结束。
3. **重置游戏**
   - 保存最高分。
   - 清空棋盘和分数，重置状态标志。
   - 随机生成两个新方块，重新开始游戏。

------



## 4 模块 4：控制台显示与用户界面

### 4.1 模块 4 - 数学模型

#### 4.1.1 棋盘显示矩阵

$$
\text{显示}(G_t) =
\begin{bmatrix}
g_{1,1} & g_{1,2} & g_{1,3} & g_{1,4} \\
g_{2,1} & g_{2,2} & g_{2,3} & g_{2,4} \\
g_{3,1} & g_{3,2} & g_{3,3} & g_{3,4} \\
g_{4,1} & g_{4,2} & g_{4,3} & g_{4,4}
\end{bmatrix}, \quad
g_{i,j} =
\begin{cases}
s_{i,j}(t), & s_{i,j}(t) \neq 0 \\
空格, & s_{i,j}(t) = 0
\end{cases}
$$

#### 4.1.2 操作与状态提示

1. 清屏：
   $$
   \text{清屏}() \implies \text{删除上一帧显示}
   $$

2. 分数显示：
   $$
   \text{score}_t \to \text{显示当前分数}, \quad \text{best\_score}_t \to \text{显示历史最高分}
   $$

3. 棋盘行输出：
   $$
   \text{输出行}(R_i) = | d_{i,1} | d_{i,2} | d_{i,3} | d_{i,4} |
   $$

4. 状态输出：
   $$
    \text{输出状态}(\text{won}_t, \text{game\_over}_t)
   $$

该函数满足：

- 若 $\text{won}_t = \text{True}$，显示“恭喜你赢了！”
- 若 $\text{game\_over}_t = \text{True}$，显示“游戏结束！”
- 否则显示当前棋盘与分数信息。



### 4.2 模块 4 - 代码实现

```python
def display_grid(self):
    """在控制台显示游戏网格和状态"""
    # 清屏
    os.system('cls' if os.name == 'nt' else 'clear')

    # 显示标题和分数
    print("=" * 30)
    print(" " * 10 + "2048 游戏" + " " * 10)
    print("=" * 30)
    print(f"分数: {self.score:<8}最高分: {self.best_score}")
    print("-" * 30)

    # 显示棋盘网格
    for row in self.grid:
        row_str = "|".join(f"{val:^6}" if val else " " * 6 for val in row)
        print(f"|{row_str}|")
        print("-" * 30)

    # 显示操作提示
    print("使用方向键或 WASD 移动方块，'Q' 退出游戏")

    # 显示游戏状态
    if self.won:
        print("恭喜你赢了！继续挑战更高分数！")
    elif self.game_over:
        print("游戏结束！按任意键重新开始")
```



### 4.3 模块 4 - 逻辑说明

1. **清屏**
   使用系统命令 `cls` (Windows) 或 `clear` (Linux/macOS) 清除之前输出。
2. **显示标题与分数**
   格式化输出当前分数和最高分，便于玩家查看。
3. **显示棋盘网格**
   - 遍历棋盘矩阵的每一行。
   - 使用固定宽度格式化每个方块值，使网格整齐。
   - 空方块显示为空格。
4. **显示操作提示**
   指示玩家使用方向键或 WASD 移动方块。
5. **显示游戏状态提示**
   根据 `won` 和 `game_over` 标志显示不同信息。



### 4.4 界面设计

```txt
==============================
          2048 游戏
==============================
分数: 0       最高分: 0

------------------------------
|      |  2   |      |      |

------------------------------
|      |      |      |      |

------------------------------
|      |      |      |  4   |

------------------------------
|      |      |      |      |

------------------------------
使用方向键或 WASD 移动方块，'Q' 退出游戏

```

------



## 5 模块 5：主循环与用户交互

### 5.1 游戏主循环

在每一帧交互中，定义用户输入函数：
$$
U_t = \text{get\_key}()
$$
输入空间：
$$
U_t \in \{\text{up}, \text{down}, \text{left}, \text{right}, \text{quit}\}
$$
状态转移函数为：
$$
S_{t+1} = f(S_t, U_t)
$$
其中：

- 若 $U_t = \text{方向}$，则调用 `_move(U_t)`；
- 若棋盘状态变化，则调用 `add_new_tile()`；
- 若 $U_t = \text{quit}$，则退出循环。



### 5.2 模块 5 - 代码实现

```python
def run(self):
    """运行游戏主循环"""
    while True:
        # 显示网格
        self.display_grid()  # 显示当前状态
        self.check_win()  # 检查是否赢了

        # 检查是否游戏结束
        if self.check_game_over():  # 如果游戏结束
            self.display_grid()  # 显示最终状态
            input("按回车键重新开始...")
            self.reset_game()  # 重置游戏
            continue

        # 获取用户输入
        key = self.get_key()
        if key == 'quit':  # 如果用户选择退出
            print("感谢游玩！再见！")
            break

        if key in ('up', 'down', 'left', 'right'):  # 处理用户移动
            if self._move(key):  # 如果移动成功
                self.add_new_tile()  # 添加新方块
                self.best_score = max(self.best_score, self.score)  # 实时刷新最高分

def get_key(self):
    """获取键盘输入"""
    key_map = {'w': 'up', 's': 'down', 'a': 'left', 'd': 'right', 'q': 'quit'}  # 定义按键映射
    arrow_map = {'H': 'up', 'P': 'down', 'K': 'left', 'M': 'right'}  # 方向键后缀映射
    while True:
        key = msvcrt.getch()  # 获取用户输入
        if key in (b'\xe0', b'\x00'):  # 方向键前缀，再读一个字节
            ext = msvcrt.getch().decode('utf-8', errors='ignore')
            if ext in arrow_map:
                return arrow_map[ext]
            continue
        ch = key.decode('utf-8', errors='ignore').lower()  # 安全解码，忽略无法解析的字节
        if ch in key_map:
            return key_map[ch]
```



### 5.3 模块 5 - 逻辑说明

1. **事件循环结构：** 游戏逻辑以无限循环运行，每帧更新状态。
2. **按键捕获机制：** `msvcrt.getch()` 可监听方向键或 WASD 键，实现即时响应。
3. **输入映射层：** 将低级字节码输入（如 `b'H'`）映射为方向命令，便于逻辑统一。
4. **状态控制：** 若本轮操作导致棋盘变化，则随机生成新方块并进入下一轮循环。

------



## 6 模块 6：程序入口与启动

### 6.1 模块 6 - 代码实现

> 说明：下面给出类的整体结构与程序入口；各方法的具体实现已在前五个模块中逐一给出，此处从略。

```python
import random
import os
import msvcrt  # Windows下的键盘输入处理

class Console2048:
    def __init__(self, grid_size=4):
        """初始化游戏"""

    def add_new_tile(self):
        """在随机空位置添加新方块（2或4）"""

    def display_grid(self):
        """在控制台显示游戏网格"""

    # ========= 移动与合并逻辑 =========
    def _merge_line(self, line):
        """合并单行（核心算法），返回新行与是否移动标志"""

    def _move(self, direction):
        """通用移动逻辑（方向: up/down/left/right）"""

    # ========= 状态检测 =========
    def check_win(self):
        """检查是否有 2048 方块"""

    def check_game_over(self):
        """检查是否无法移动"""

    def reset_game(self):
        """重置游戏"""

    # ========= 输入与控制 =========
    def get_key(self):
        """获取键盘输入"""

    # ========= 主循环 =========
    def run(self):
        """运行游戏主循环"""


if __name__ == "__main__":
    print("2048 控制台版游戏")
    print("使用方向键或 WASD 键移动方块，按 'Q' 退出游戏")
    input("按回车键开始游戏...")
    Console2048().run()
```



### 6.2 模块 6 - 逻辑说明

1. **程序入口判断：** 使用 Python 标准写法 `if __name__ == "__main__"` 保证独立运行。
2. **初始化提示信息：** 以交互方式提示玩家游戏说明。
3. **实例化与运行：** 调用类 `Console2048` 的 `run()` 方法进入主循环，实现完整的控制台游戏体验。

------



## 7 小结

本文从数学建模视角梳理了 **2048 控制台版游戏** 的程序逻辑。
 从状态矩阵定义到用户交互主循环，构建了一个由五个核心方程驱动的有限状态系统：
$$
\begin{cases} S_{t+1} = f(S_t, U_t) \\
\text{score}_{t+1} = \text{score}_t + \sum \text{合并值} \\ 
\text{won}_t = [\exists s_{ij}=2048] \\ 
\text{game\_over}_t = [\forall s_{ij}\neq 0 \land 无相邻相等] \\ 
E_t = \{(i,j)\mid s_{ij}=0\} \end{cases}
$$


这一结构展示了如何用**数学模型统一游戏逻辑与程序实现**：

1. 状态矩阵描述棋盘状态；
2. 转移函数刻画玩家动作；
3. 概率分布控制随机生成；
4. 判定函数定义系统边界。

这套规则内核适合命令行交互、单元测试与批量对局实验（`ai_solver_2048.py` 就复用了它），但不适合追求交互与观感，需从第 3 篇的 PyQt5 版开始。
---

**本篇是系列第 1 篇**（共 7 篇）。

**下一篇**：[第 2 篇 · 如何实现带历史记录功能的控制台2048游戏](第2篇%20·%20如何实现带历史记录功能的控制台2048游戏.md)，把每一局的操作步骤、网格状态与得分落盘，并支持下次启动续玩。
