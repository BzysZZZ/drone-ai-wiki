# SLAM 系统横向对比与选型指南

> **类型**: comparison（对比综述）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

为无人机工程项目选择合适的 SLAM 系统，需综合考虑传感器类型、算力平台、环境类型、精度要求等因素。本页提供完整的选型矩阵和各系统优劣对比。

## 选型决策树

```
需要 SLAM？
│
├── 传感器类型？
│   ├── 仅相机（低成本）
│   │   ├── 单目 → VINS-Mono 或 ORB-SLAM3（Mono-Inertial）
│   │   ├── 双目 → ORB-SLAM3（Stereo）
│   │   └── RGB-D → ORB-SLAM3（RGB-D）
│   │
│   ├── 相机 + IMU（无人机主流）
│   │   ├── 实时精度优先 → VINS-Fusion / VINS-Mono
│   │   ├── 轻量嵌入式 → SVO + GTSAM / Basalt
│   │   └── 研究/最优精度 → ORB-SLAM3 Inertial
│   │
│   ├── LiDAR（户外精度优先）
│   │   ├── 固态LiDAR（Livox）→ FAST-LIO2
│   │   ├── 旋转LiDAR（Velodyne）→ LOAM / LIO-SAM
│   │   └── 需要回环 → LIO-SAM / KISS-ICP
│   │
│   └── LiDAR + 相机 + IMU（最高精度）
│       → LVI-SAM / R3LIVE / Fast-LIVO
│
├── 算力平台？
│   ├── Jetson Orin NX（主流无人机）→ 多数系统可跑
│   ├── Jetson Nano（低端）→ SVO / FAST-LIO2
│   └── ARM 嵌入式（Cortex-A）→ MSCKF / SVO
│
└── 环境类型？
    ├── 室内（有纹理）→ ORB-SLAM3 / VINS
    ├── 室内（无纹理）→ LiDAR SLAM
    ├── 室外（大场景）→ LIO-SAM（GPS辅助）
    └── 室外（高速飞行）→ SVO / FAST-LIO2
```

## 完整性能对比

### 视觉/视觉惯性 SLAM

| 系统 | 传感器 | CPU占用 | ATE（m） | 重定位 | 建图 | 开源 |
|------|--------|--------|---------|--------|------|------|
| ORB-SLAM3 | Mono/Stereo/RGBD/IMU | 中高 | 0.01~0.1 | ✅ DBoW2 | 稀疏 | ✅ |
| VINS-Mono | Mono+IMU | 中 | 0.05~0.15 | ✅ | 稀疏 | ✅ |
| VINS-Fusion | 多相机+GPS | 中高 | 0.02~0.08 | ✅ | 稀疏 | ✅ |
| SVO | Mono/Stereo | 低（轻量） | 0.05~0.2 | ❌ | 稀疏 | 部分 |
| DSO | Mono | 低 | 0.05~0.3 | ❌ | 半稠密 | ✅ |
| OpenVINS | Mono/Stereo+IMU | 低中 | 0.05~0.15 | ❌ | 无 | ✅ |
| Basalt | Stereo+IMU | 低中 | 0.02~0.1 | ❌ | 无 | ✅ |

### LiDAR SLAM

| 系统 | 传感器 | CPU占用 | 精度 | 回环 | 地图 | 开源 |
|------|--------|--------|------|------|------|------|
| LOAM | LiDAR | 高 | 中高 | ❌ | 稠密 | ✅ |
| LeGO-LOAM | LiDAR | 中 | 中 | ✅ | 稠密 | ✅ |
| LIO-SAM | LiDAR+IMU | 中高 | 高 | ✅ GPS | 稠密 | ✅ |
| FAST-LIO2 | LiDAR+IMU | **低** | 高 | ❌ | 稠密点云 | ✅ |
| KISS-ICP | LiDAR | 极低 | 中 | ❌ | 无 | ✅ |
| LVI-SAM | LiDAR+Camera+IMU | 高 | **极高** | ✅ | 稠密 | ✅ |

## 各环境测试数据集

| 数据集 | 场景 | 传感器 | 特点 |
|--------|------|--------|------|
| TUM RGB-D | 室内桌面 | RGBD+IMU | 经典室内基准 |
| EuRoC MAV | 室内工厂 | Stereo+IMU | 无人机视觉惯性基准 |
| KITTI | 室外道路 | LiDAR+Camera | 自动驾驶基准 |
| HiltiSLAM | 建筑工地 | LiDAR+Camera+IMU | 挑战室内 |
| M2DGR | 多模态校园 | LiDAR+Camera+IMU+GPS | 最新综合基准 |

## 建图格式选择

```
稀疏点云（ORB-SLAM风格）→ 适合定位重定位
半稠密（DSO）→ 视觉里程计，障碍物感知有限
OctoMap 体素 → 适合路径规划（3D避障）
NDT/Voxel Grid → 激光里程计匹配
TSDF → 适合三维重建（VoxBlox）
NeRF/3DGS → 高精度视觉重建（offline）
```

## 论文引用

- [1] **ORB-SLAM3** — Campos et al., "ORB-SLAM3: An Accurate Open-Source Library for Visual, Visual-Inertial, and Multimap SLAM," IEEE TRO 2021.
- [2] **VINS-Mono** — Qin et al., "VINS-Mono: A Robust and Versatile Monocular Visual-Inertial State Estimator," IEEE TRO 2018.
- [3] **SVO2** — Forster et al., "SVO: Semidirect Visual Odometry for Monocular and Multicamera Systems," IEEE TRO 2017.
- [4] **FAST-LIO2** — Xu et al., "FAST-LIO2: Fast Direct LiDAR-Inertial Odometry," IEEE TRO 2022.
- [5] **LIO-SAM** — Shan et al., "LIO-SAM: Tightly-coupled Lidar Inertial Odometry via Smoothing and Mapping," IROS 2020.
- [6] **KISS-ICP** — Vizzo et al., "KISS-ICP: In Defense of Point-to-Point ICP – Simple, Accurate, and Robust Registration," IEEE RA-L 2023.
- [7] **EuRoC** — Burri et al., "The EuRoC Micro Aerial Vehicle Datasets," IJRR 2016. [无人机SLAM基准]
- [8] **SLAM综述** — Cadena et al., "Past, Present, and Future of SLAM," IEEE TRO 2016.
- [9] **LVI-SAM** — Shan et al., "LVI-SAM: Tightly-coupled Lidar-Visual-Inertial Odometry," ICRA 2021.
- [10] **OpenVINS** — Geneva et al., "OpenVINS: A Research Platform for Visual-Inertial Estimation," ICRA 2020.

## 关联

- 相关概念: [[concept-slam]], [[concept-multi-sensor-fusion]]
- 相关实体: [[entities/org-eth-asl]]
- 参见: [[topics/topic-perception-stack]], [[topics/topic-precision-localization]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——选型决策树、完整性能对比表、数据集列表、建图格式对比、10篇论文引用
