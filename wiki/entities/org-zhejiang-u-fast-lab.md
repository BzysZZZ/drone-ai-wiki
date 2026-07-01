# 浙江大学 FAST-Lab（高飞实验室）

> **类型**: entity（机构）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: 知识库初始化（AI综合整理）
> **标签**: #规划 #SLAM #前沿

## 摘要

浙江大学 Fast-Lab（高性能机器人与智能系统实验室）由高飞教授领导，是国内无人机路径规划与自主飞行领域最具影响力的研究团队，发布了 Fast-Planner、EGO-Planner 等全球广泛使用的开源规划框架。

## 详情

### 基本信息

- **所属机构**：浙江大学控制科学与工程学院
- **负责人**：高飞（Fei Gao）教授
- **网址**：https://github.com/FAST-Lab

### 核心开源贡献

| 项目 | 功能 | 引用/Star |
|------|------|-----------|
| **Fast-Planner** | 高速无人机路径规划框架 | 极高 |
| **EGO-Planner** | 基于 ESDF 梯度的局部规划 | 极高 |
| **EGO-Planner-v2** | 多机 EGO 规划，全局-局部联合 | 高 |
| **FUEL** | 基于前沿的自主探索 | 高 |
| **Swarm-Formation** | 无人机编队飞行 | 中 |
| **MARSIM** | 轻量无人机仿真 | 中 |

### EGO-Planner 技术亮点

- 使用 ESDF（Euclidean Signed Distance Field）表示障碍信息
- 贝塞尔曲线轨迹参数化
- 梯度信息直接驱动轨迹优化，**无需地图占用查询**，速度极快
- 支持 ROS1/ROS2，Gazebo 仿真，真机飞行验证

### 研究方向

1. 无人机运动规划（局部/全局/拓扑）
2. 多机协同规划与编队
3. 自主探索（Exploration）
4. 3D 场景感知与地图构建

### 影响力

- EGO-Planner 是国内外实验室无人机规划研究的标准 baseline
- 论文发表于 T-RO、ICRA、IROS 等顶级期刊/会议
- 开源代码广泛应用于学术界和工业界

## 关联
- 相关机构: [[entities/org-eth-asl]], [[entities/org-hkust-mars-lab]]
- 相关概念: [[concepts/concept-path-planning]], [[concepts/concept-slam]]
- 相关主题: [[topics/topic-planning-stack]]

## 引用来源 / 代表性论文

- [1] **Fast-Planner** — Zhou et al., "Robust and Efficient Quadrotor Trajectory Generation for Fast Autonomous Flight," IEEE RA-L 2019.
- [2] **EGO-Planner** — Zhou et al., "EGO-Planner: An ESDF-free Gradient-based Local Planner for Quadrotors," IEEE RA-L 2021.
- [3] **EGO-Planner-v2** — Zhou et al., "Swarm of Micro Flying Robots in the Wild," Science Robotics 2022.
- [4] **FUEL** — Zhou et al., "FUEL: Fast UAV Exploration Using Incremental Frontier Structure and Hierarchical Planning," IEEE RA-L 2021.
- [5] **GCOPTER** — Wang et al., "Geometrically Constrained Trajectory Optimization for Multicopters," IEEE TRO 2022.
- [6] **MINCO** — Wang et al., "Generating Large-Scale Trajectories Efficiently using Double Description Method," ICRA 2022.
- [7] **Swarm Formation** — Zhou et al., "EGO-Swarm: A Fully Autonomous and Decentralized Quadrotor Swarm System in Cluttered Environments," ICRA 2021.
- [8] **MARSIM** — Kong et al., "MARSIM: A Light-weight Point-realistic Simulator for LiDAR-based UAVs," IEEE RA-L 2023.

## 变更记录
- 2026-06-27: 初始创建，知识库初始化
- 2026-06-29: 补充8篇代表性论文引用
