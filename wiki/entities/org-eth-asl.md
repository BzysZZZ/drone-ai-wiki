# ETH Zurich ASL（自主系统实验室）

> **类型**: entity（机构）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: 知识库初始化（AI综合整理）
> **标签**: #前沿 #SLAM #控制 #规划

## 摘要

ETH Zurich Autonomous Systems Lab（ASL）是全球无人机自主系统领域最顶尖的研究机构之一，发布了 ORB-SLAM、VINS-Mono、Agile Autonomy 等众多里程碑级开源项目。

## 详情

### 基本信息

- **全称**：Autonomous Systems Lab, ETH Zürich
- **网址**：https://asl.ethz.ch/
- **重要PI**：Roland Siegwart（开创者），Davide Scaramuzza

### Davide Scaramuzza（RPG 实验室）

> 注：Scaramuzza 领导的是独立的 Robotics and Perception Group (RPG)，与 ASL 紧密合作

- **主攻方向**：敏捷无人机飞行、事件相机、深度学习导航
- **代表工作**：Agile Autonomy、UZH-FPV 数据集、事件相机 SLAM

### 重要开源贡献

| 项目 | 领域 | 链接 |
|------|------|------|
| **ORB-SLAM3** | 视觉/VIO SLAM | GitHub |
| **Rotors Simulator** | Gazebo 无人机仿真 | GitHub |
| **ethzasl_msf** | 多传感器融合 | GitHub |
| **kalibr** | 传感器标定 | GitHub |
| **maplab** | 视觉地图框架 | GitHub |
| **Agile Autonomy** | RL 敏捷飞行 | GitHub |
| **flightmare** | RL 训练仿真器 | GitHub |

### 影响力

- 无人机自主领域 ICRA/IROS/RSS 大量顶会论文
- 孵化了多家自动驾驶/无人机公司
- PX4 最早核心开发团队来自 ETH

## 关联
- 相关机构: [[entities/org-zhejiang-u-fast-lab]], [[entities/org-hkust-mars-lab]]
- 相关概念: [[concepts/concept-slam]], [[concepts/concept-reinforcement-learning]], [[concepts/concept-path-planning]]
- 相关产品: [[entities/product-px4-autopilot]]

## 引用来源 / 代表性论文

- [1] **Agile Autonomy** — Loquercio et al., "Learning High-Speed Flight in the Wild," Science Robotics 2021.
- [2] **Kalibr** — Furgale et al., "Unified Temporal and Spatial Calibration for Multi-Sensor Systems," IROS 2013.
- [3] **Rotors Simulator** — Furrer et al., "RotorS—A Modular Gazebo MAV Simulator Framework," RSSO 2016.
- [4] **maplab** — Schneider et al., "maplab: An Open Framework for Research in Visual-Inertial Mapping and Localization," IEEE RA-L 2018.
- [5] **Champion Racing** — Kaufmann et al., "Champion-level Drone Racing Using Deep Reinforcement Learning," Nature 2023.
- [6] **事件相机SLAM** — Rebecq et al., "ESVO: Event-Based Stereo Visual Odometry," IEEE TRO 2021.
- [7] **UZH-FPV** — Delmerico et al., "Are We Ready for Autonomous Drone Racing? The UZH-FPV Drone Racing Dataset," ICRA 2019.
- [8] **Flightmare** — Song et al., "Flightmare: A Flexible Quadrotor Simulator," CoRL 2020.

## 变更记录
- 2026-06-27: 初始创建，知识库初始化
- 2026-06-29: 补充8篇代表性论文引用
