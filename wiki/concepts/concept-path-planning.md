# 路径规划（Path Planning）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

路径规划是指在已知或未知环境中，为无人机计算从起点到终点的安全、高效轨迹。分为全局规划（基于地图先验）和局部规划（实时避障），无人机领域核心挑战是高速三维空间中的实时规划与动力学约束。

## 算法体系

```
路径规划
├── 图搜索算法（全局，离散）
│   ├── Dijkstra
│   ├── A*
│   └── JPS（Jump Point Search）
├── 采样规划（全局，连续）
│   ├── RRT
│   ├── RRT*（渐进最优）
│   ├── Informed RRT*
│   └── BIT*
├── 势场法（局部，实时）
│   ├── APF（人工势场）
│   └── DWA（动态窗口法）
├── 基于优化的规划（高精度轨迹）
│   ├── CHOMP
│   ├── TEB（时间弹性带）
│   └── GCOPTER / MINCO
└── 学习型规划
    ├── 模仿学习
    └── 强化学习（PPO, SAC）
```

## 核心算法详解

### A* 算法
```python
import heapq

def astar(grid, start, goal):
    """
    A* 路径规划（3D 栅格可直接扩展）
    g(n): 起点到 n 的实际代价
    h(n): n 到终点的启发式估计（欧氏距离）
    f(n) = g(n) + h(n)
    """
    def heuristic(a, b):
        return ((a[0]-b[0])**2 + (a[1]-b[1])**2)**0.5
    
    open_set = [(0, start)]
    came_from = {}
    g_score = {start: 0}
    
    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            # 回溯路径
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            return path[::-1]
        
        for neighbor in get_neighbors(grid, current):
            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor, goal)
                heapq.heappush(open_set, (f, neighbor))
    return None
```

### RRT* 采样规划
```python
"""
RRT* 关键改进：
1. 邻域重连（Rewire）：找到代价更小的父节点
2. 渐进最优性保证
3. 实际无人机用 RRT* 变种 + 动力学模型
"""
def rrt_star_extend(tree, q_rand, radius=5.0):
    q_near = nearest(tree, q_rand)
    q_new = steer(q_near, q_rand, step_size=1.0)
    if is_collision_free(q_near, q_new):
        # 找邻域节点
        neighbors = within_radius(tree, q_new, radius)
        # 选最优父节点
        q_min = min(neighbors, key=lambda q: cost(q) + dist(q, q_new))
        tree.add(q_new, parent=q_min)
        # 重连邻域
        for q_nbr in neighbors:
            if cost(q_new) + dist(q_new, q_nbr) < cost(q_nbr):
                tree.rewire(q_nbr, parent=q_new)
```

### MINCO 轨迹优化（2022 最优方案）

MINCO（Minimum Control）是浙大 FAST-Lab 提出的高效轨迹表示方法：

```
优化目标: min ∫||u(t)||² dt + λ·T
约束:
  - 起点/终点位姿
  - 动力学可行性（速度、加速度限制）
  - 障碍物约束（ESDF 梯度）
  - 走廊约束（Convex Decomposition）

关键创新:
  - C²连续多项式轨迹
  - 时空联合优化（空间形状 + 时间分配）
  - 比 B-spline 计算速度快 10×
```

### EGO-Planner（无 ESDF，更轻量）

```yaml
论文: EGO-Planner: An ESDF-free Gradient-based Local Planner for Quadrotors
核心创新:
  - 不需要 ESDF（欧氏符号距离场），减少 90% 计算
  - 使用障碍物点直接产生排斥梯度
  - B-spline 轨迹表示
  - 重规划频率: 10Hz
计算延迟: <10ms（板载嵌入式）
```

### EGO-Planner-v2 / FASTER

| 规划器 | 特点 | 最大速度 | 重规划延迟 |
|--------|------|---------|-----------|
| EGO-Planner | 无ESDF，轻量 | ~3m/s | <10ms |
| EGO-Planner-v2 | 支持集群 | ~5m/s | <15ms |
| FASTER | 后端使用MIQP，保安全 | ~7m/s | <50ms |
| GCOPTER | MINCO轨迹，走廊约束 | ~6m/s | <30ms |
| Agile | 学习型，神经网络策略 | ~10m/s | 网络推理时间 |

## 全局规划 vs 局部规划

| 维度 | 全局规划 | 局部规划 |
|------|---------|---------|
| 地图要求 | 需先验地图 | 实时感知即可 |
| 计算量 | 可离线 | 必须实时 |
| 路径质量 | 全局最优 | 局部最优 |
| 未知障碍 | 无法处理 | 实时避障 |
| 代表算法 | A*, Dijkstra, RRT* | DWA, EGO-Planner, APF |

## 无人机特殊约束

```
动力学约束:
  - 最大速度: 通常 8~15 m/s
  - 最大加速度: 3~6 m/s²
  - 最大角速度: 300 deg/s

安全约束:
  - 与障碍物安全距离: ≥0.3m（室内）, ≥1m（室外）
  - 不得进入禁飞区
  - 飞行走廊约束（Convex Decomposition）

能耗约束:
  - 时间最优 vs 能耗最优 权衡
  - 平滑轨迹减少电机抖动
```

## 三维地图表示

| 地图类型 | 内存 | 更新速度 | 代表 |
|---------|------|---------|------|
| 占用栅格（Voxel Grid） | 大 | 快 | OctoMap |
| 八叉树（OctoMap） | 中 | 中 | OctoMap |
| ESDF | 大 | 慢 | EfficientMap |
| 点云 | 小 | 极快 | EGO-Planner |
| TSDF | 中 | 中 | VoxBlox |

## 论文引用

- [1] **A*** — Hart et al., "A Formal Basis for the Heuristic Determination of Minimum Cost Paths," IEEE TSSC 1968. [经典，必读]
- [2] **RRT** — LaValle, "Rapidly-Exploring Random Trees: A New Tool for Path Planning," TR 1998.
- [3] **RRT*** — Karaman & Frazzoli, "Sampling-based Algorithms for Optimal Motion Planning," IJRR 2011.
- [4] **CHOMP** — Ratliff et al., "CHOMP: Covariant Hamiltonian Optimization for Motion Planning," ICRA 2009.
- [5] **TEB** — Rösmann et al., "Timed-Elastic-Band Local Planner and Its Application to Car-Like Robots," IROS 2013.
- [6] **EGO-Planner** — Zhou et al., "EGO-Planner: An ESDF-free Gradient-based Local Planner for Quadrotors," IEEE RA-L 2021. [必读，无人机规划SOTA]
- [7] **GCOPTER** — Wang et al., "Geometrically Constrained Trajectory Optimization for Multicopters," IEEE TRO 2022.
- [8] **MINCO** — Wang et al., "Generating Large-Scale Trajectories Efficiently Using Double Description Method," ICRA 2022.
- [9] **FASTER** — Tordesillas & How, "FASTER: Fast and Safe Trajectory Planner for Flights in Unknown Environments," IEEE TRO 2022.
- [10] **Agile** — Loquercio et al., "Learning High-Speed Flight in the Wild," Science Robotics 2021. [深度学习规划]
- [11] **Champion-level Drone Racing** — Kaufmann et al., "Champion-level Drone Racing Using Deep Reinforcement Learning," Nature 2023.
- [12] **Convex Decomposition** — Liu et al., "Convex Feasible Set Algorithm for Non-convex Trajectory Optimization," IROS 2017.
- [13] **FUEL** — Zhou et al., "FUEL: Fast UAV Exploration Using Incremental Frontier Structure and Hierarchical Planning," IEEE RA-L 2021.
- [14] **DWA** — Fox et al., "The Dynamic Window Approach to Collision Avoidance," IEEE RAM 1997.
- [15] **BIT*** — Gammell et al., "Batch Informed Trees (BIT*): Sampling-Based Optimal Planning via the Heuristically Guided Search of Implicit Random Geometric Graphs," ICRA 2020.

## 关联

- 相关概念: [[concept-slam]], [[concept-drone-control]], [[concept-reinforcement-learning]]
- 相关实体: [[entities/org-zhejiang-u-fast-lab]], [[entities/product-px4-autopilot]]
- 参见: [[topics/topic-sim-to-real]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——增加完整算法体系、A*/RRT*代码、MINCO/EGO-Planner详解、对比表格、15篇论文引用
