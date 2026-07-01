# 规划与控制基本功

> **类型**: concept
> **创建时间**: 2026-06-29
> **最后更新**: 2026-06-29
> **来源**: AI综合，见引用来源
> **标签**: #规划 #控制 #机器人 #无人机 #基本功

## 摘要

规划与控制共同决定无人机“往哪里飞、怎么飞过去、飞行中如何保持稳定”。规划负责从任务目标和环境约束中生成路径/轨迹，控制负责让真实机体跟踪轨迹并抵抗扰动。对无人机 AI 工程师来说，A*/RRT*/轨迹优化、PID/LQR/MPC、四旋翼微分平坦性和几何控制都是必须掌握的基本功。

---

## 知识地图

```
规划与控制
├── 离散路径搜索
│   ├── Dijkstra
│   ├── A*
│   └── D* / D* Lite
├── 采样运动规划
│   ├── PRM
│   ├── RRT
│   └── RRT*
├── 轨迹优化
│   ├── Minimum Snap
│   ├── Polynomial Trajectory
│   ├── CHOMP / TrajOpt
│   └── MINCO / EGO-Planner
├── 控制
│   ├── PID
│   ├── LQR
│   ├── MPC
│   └── Geometric Control on SE(3)
└── 无人机动力学
    ├── 坐标系与姿态
    ├── 欠驱动系统
    ├── 微分平坦性
    └── 轨迹跟踪
```

---

## 规划算法对比

| 方法 | 空间 | 优点 | 局限 | 无人机场景 |
|------|------|------|------|------------|
| Dijkstra | 图/栅格 | 最优、无启发要求 | 慢 | 小地图全局规划 |
| A* | 图/栅格 | 启发式加速、可最优 | 依赖地图分辨率 | 2D/3D 栅格路径 |
| D* Lite | 动态图 | 适合增量重规划 | 实现复杂 | 地图逐步更新 |
| PRM | 连续空间 | 多查询效率高 | 窄通道困难 | 静态环境路线库 |
| RRT | 连续空间 | 高维可行性强 | 路径粗糙、非最优 | 快速可行路径 |
| RRT* | 连续空间 | 渐近最优 | 收敛慢 | 需要更优路径时 |
| Minimum Snap | 连续轨迹 | 平滑、适合四旋翼 | 需要走廊/约束 | 航点轨迹生成 |
| EGO-Planner/MINCO | 连续轨迹 | 实时局部规划 | 工程复杂 | 高速避障与重规划 |

---

## A* 最小实现

```python
import heapq

def astar(start, goal, neighbors, heuristic):
    open_set = [(0.0, start)]
    came_from = {}
    g = {start: 0.0}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return path[::-1]

        for nxt, cost in neighbors(current):
            tentative = g[current] + cost
            if tentative < g.get(nxt, float("inf")):
                came_from[nxt] = current
                g[nxt] = tentative
                f = tentative + heuristic(nxt, goal)
                heapq.heappush(open_set, (f, nxt))
    return None
```

关键条件：如果 heuristic 不高估真实代价，A* 保证最优；如果 heuristic 越接近真实代价，搜索越快。

---

## 四旋翼控制分层

```
任务层:      航点 / 巡检区域 / 降落点
规划层:      路径 + 时间参数化轨迹
位置控制:    期望加速度 / 期望姿态
姿态控制:    期望角速度 / 力矩
电机混控:    四个电机推力
```

常见工程接口：

| 输入 | 输出 | 模块 |
|------|------|------|
| 目标点 + 地图 | 路径 | 全局规划 |
| 当前状态 + 局部障碍 | 局部轨迹 | 局部规划 |
| 期望轨迹 + 当前状态 | 期望姿态/推力 | 位置控制 |
| 期望姿态 + 当前姿态 | 角速度/力矩 | 姿态控制 |
| 力矩 + 总推力 | 电机 PWM | 混控 |

---

## PID、LQR、MPC 对比

| 控制器 | 思想 | 优点 | 局限 | 适用 |
|--------|------|------|------|------|
| PID | 误差比例/积分/微分反馈 | 简单、鲁棒、易调 | 多变量耦合处理弱 | 工业默认、底层控制 |
| LQR | 线性系统二次型最优控制 | 有理论稳定性、可解释 | 需要线性化 | 姿态/位置小扰动 |
| MPC | 滚动优化未来轨迹 | 可处理约束 | 计算量大 | 高性能轨迹跟踪 |
| Geometric Control | 直接在 SE(3) 上控制 | 避免欧拉角奇异 | 推导门槛高 | 四旋翼高机动飞行 |

---

## Minimum Snap 轨迹直觉

四旋翼位置轨迹常用多项式表示：

```
p(t) = a0 + a1 t + a2 t^2 + ... + an t^n
```

Minimum Snap 优化目标：

```
min ∫ || d^4 p(t) / dt^4 ||^2 dt
```

为什么是 snap：四旋翼的姿态和推力与加速度相关，更高阶导数影响控制输入变化的平滑性。最小化 snap 能得到更容易跟踪、对电机更友好的轨迹。

---

## 经典论文与算法

| 论文/算法 | 年份 | 核心贡献 | 工程位置 |
|-----------|------|----------|----------|
| A* | 1968 | 启发式最短路搜索 | 栅格路径规划 |
| PRM | 1996 | 概率路图 | 多查询运动规划 |
| RRT | 1998/2001 | 快速探索随机树 | 高维可行路径搜索 |
| RRT* | 2011 | 渐近最优采样规划 | 更优采样路径 |
| D* Lite | 2002 | 动态重规划 | 在线地图更新 |
| Minimum Snap Trajectory | 2011 | 四旋翼多项式轨迹 | 航点轨迹生成 |
| Geometric Tracking Control | 2010 | SE(3) 四旋翼控制 | 高机动飞行控制 |
| EGO-Planner | 2021 | ESDF-free 局部规划 | 无人机实时避障 |

---

## 工程排错表

| 现象 | 可能原因 | 排查动作 |
|------|----------|----------|
| 路径可行但飞不过去 | 路径没有动力学约束 | 做时间参数化和最大速度/加速度检查 |
| 局部规划抖动 | 障碍代价或重规划频率不合适 | 可视化局部轨迹和障碍物梯度 |
| 轨迹跟踪超调 | PID 增益过大或速度前馈不足 | 分别调位置环、速度环、姿态环 |
| 飞行中震荡 | 姿态环/电机响应/滤波延迟问题 | 检查日志中的 rate setpoint 与 gyro |
| 避障过保守 | 安全距离或膨胀半径过大 | 对比地图分辨率、机体半径、定位误差 |
| 穿障 | 地图延迟或坐标系错误 | 检查感知时间戳和 map/body 变换 |

---

## 与现有知识库的关系

| 页面 | 规划控制支撑点 |
|------|----------------|
| [[concepts/concept-path-planning]] | A*/RRT*/EGO-Planner/MINCO 的深入应用 |
| [[concepts/concept-drone-control]] | PID/MPC/姿态控制和飞控架构 |
| [[concepts/concept-reinforcement-learning]] | 学习型控制与规划的基础 |
| [[topics/topic-sim-to-real]] | 控制器从仿真到真机的参数迁移 |
| [[entities/product-px4-autopilot]] | PX4 Offboard 与控制接口 |

---

## 学习检验

1. 手写 A*，并解释启发函数 admissible 的含义。
2. 画出 RRT 与 RRT* 的区别：扩展、rewire、渐近最优。
3. 给 5 个航点生成一条分段多项式轨迹，检查速度/加速度连续性。
4. 解释 PID 中积分项为什么会 windup，以及如何 anti-windup。
5. 说明 LQR 中 Q/R 矩阵分别影响什么。
6. 解释为什么四旋翼是欠驱动系统，但位置轨迹仍可通过姿态和推力跟踪。

---

## 关联

- 总书单: [[topics/topic-foundational-reading-list]]
- 路径规划: [[concepts/concept-path-planning]]
- 无人机控制: [[concepts/concept-drone-control]]
- 强化学习: [[concepts/concept-reinforcement-learning]]
- PX4: [[entities/product-px4-autopilot]]

## 引用来源

- [1] LaValle, S. M. **Planning Algorithms**. Cambridge University Press, 2006. https://lavalle.pl/planning/
- [2] Åström, K. J., & Murray, R. M. **Feedback Systems: An Introduction for Scientists and Engineers**. https://fbswiki.org/
- [3] Lynch, K. M., & Park, F. C. **Modern Robotics**. Cambridge University Press, 2017. https://modernrobotics.northwestern.edu/
- [4] Tedrake, R. **Underactuated Robotics**. https://underactuated.mit.edu/
- [5] Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). **A Formal Basis for the Heuristic Determination of Minimum Cost Paths**. IEEE TSSC.
- [6] Kavraki, L. E., et al. (1996). **Probabilistic Roadmaps for Path Planning in High-Dimensional Configuration Spaces**. IEEE TRA.
- [7] Karaman, S., & Frazzoli, E. (2011). **Sampling-based Algorithms for Optimal Motion Planning**. IJRR. https://arxiv.org/abs/1105.1186
- [8] Mellinger, D., & Kumar, V. (2011). **Minimum Snap Trajectory Generation and Control for Quadrotors**. ICRA.
- [9] Lee, T., Leok, M., & McClamroch, N. H. (2010). **Geometric Tracking Control of a Quadrotor UAV on SE(3)**. CDC.

## 变更记录

- 2026-06-29: 初始创建，补充规划控制知识地图、A* 代码、四旋翼控制分层和排错表。
