# SLAM（同步定位与建图）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

SLAM（Simultaneous Localization and Mapping）是机器人在未知环境中同时估计自身位姿并构建地图的核心技术。无人机领域主要使用视觉 SLAM（V-SLAM）、视觉惯性 SLAM（VI-SLAM）和激光 SLAM（LiDAR SLAM）。

## 算法分类体系

```
SLAM
├── 激光 SLAM
│   ├── 2D：Gmapping、Cartographer、Hector SLAM
│   └── 3D：LOAM、LeGO-LOAM、LIO-SAM、FAST-LIO2
├── 视觉 SLAM
│   ├── 特征点法：ORB-SLAM3、VINS-Mono
│   ├── 直接法：LSD-SLAM、DSO
│   └── 半直接法：SVO
└── 深度学习 SLAM
    ├── 端到端：DeepVO、ESP-VO
    ├── 场景理解辅助：SemanticFusion、ElasticFusion
    └── NeRF-SLAM：NeRF-SLAM、NICE-SLAM、SplaTAM
```

## 主流系统详解

### 视觉 SLAM

#### ORB-SLAM3（无人机首选）
```yaml
特点:
  - 支持单目/双目/RGB-D/鱼眼
  - 多地图系统，支持地图合并
  - Atlas框架：多会话建图
  - IMU 紧耦合（Monoc-Inertial 模式）
适用场景: 室内外通用，算力要求中等
关键参数:
  nFeatures: 1000    # ORB特征点数量
  scaleFactor: 1.2   # 图像金字塔缩放因子
  nLevels: 8        # 金字塔层数
```

#### VINS-Mono（港科大，学术标杆）
```yaml
特点:
  - 单目 + IMU 紧耦合
  - 滑窗优化 + 回环检测
  - 初始化自动化，无需人工标定
  - 支持重定位
优势: 对快速运动和退化环境鲁棒
```

#### SVO（Swiss-Mile，速度之王）
```yaml
特点:
  - 半直接法（关键点+直接对齐）
  - CPU 实时 > 100FPS（单目）
  - 无回环检测（需配合 posegraph）
适用: 嵌入式/轻量化无人机
```

### 激光 SLAM

#### FAST-LIO2（2022 最优 LiDAR-IMU）
```yaml
特点:
  - 迭代扩展卡尔曼滤波（iEKF）
  - ikd-tree 动态体素增量更新
  - 支持 Livox 固态激光雷达
  - CPU 单核即可实时
频率: 100Hz IMU + 10~20Hz LiDAR
```

#### LIO-SAM（地面无人车标配）
```yaml
特点:
  - 因子图（GTSAM库）
  - GPS 因子 + 回环因子
  - IMU 预积分
适用: 户外大场景，配合 GPS 漂移修正
```

## 前端与后端详解

### 前端（里程计）

| 方法 | 代表算法 | 原理 |
|------|---------|------|
| 特征点法 | ORB-SLAM, VINS | ORB/SURF特征提取→匹配→对极几何/PnP求解 |
| 直接法 | LSD-SLAM, DSO | 最小化光度误差，利用所有像素 |
| 半直接 | SVO | 关键点稀疏对齐，不提取描述子 |
| 激光点云 | LOAM, FAST-LIO | 点云配准ICP/NDT/特征线面提取 |

### 后端（优化）

**滤波器方法（轻量）**
```
EKF → ESKF（误差状态卡尔曼）→ iEKF（迭代）
特点：O(n)复杂度，适合嵌入式
代表：FAST-LIO2
```

**图优化方法（精度高）**
```
位姿图 → 因子图（GTSAM/g2o/Ceres）
最小化：Σ ρ(||r_ij||²_Σ)
特点：全局最优，支持回环
代表：ORB-SLAM3, LIO-SAM
```

### 回环检测

| 方法 | 描述 | 代表 |
|------|------|------|
| BoW词袋 | 视觉词典匹配 | DBoW2，ORB-SLAM系列 |
| NetVLAD | 深度特征全局描述 | 室外场景鲁棒 |
| Scan Context | 激光点云极坐标描述子 | LiDAR 回环 |
| OverlapNet | 深度学习点云回环 | 2020 |

## 无人机 SLAM 特殊挑战

1. **快速运动模糊**：需高帧率相机（60fps+）或 IMU 辅助
2. **纹理缺乏**：蓝天/地面导致特征匹配失败 → 直接法或深度预测辅助
3. **计算受限**：边缘端算力有限 → SVO/FAST-LIO2/轻量版ORB-SLAM
4. **尺度漂移**：单目 SLAM 无绝对尺度 → 必须加 IMU 或 RGB-D
5. **动态目标**：移动的行人/车辆干扰建图 → DynaSLAM, SaD-SLAM

## 建图地图类型

| 地图类型 | 精度 | 存储 | 代表系统 | 用途 |
|---------|------|------|---------|------|
| 稀疏点云 | 低 | 极小 | ORB-SLAM3 | 定位、路径规划 |
| 半稠密 | 中 | 中 | DSO, LSD-SLAM | 障碍物感知 |
| 稠密点云 | 高 | 大 | RTAB-Map, ElasticFusion | 三维重建 |
| 八叉树（OctoMap） | 高 | 中 | OctoMap + 任意SLAM | 三维规划 |
| NeRF/3DGS | 极高 | 极大 | SplaTAM, MonoGS | 高精地图 |

## 论文引用

- [1] **SLAM综述** — Cadena et al., "Past, Present, and Future of Simultaneous Localization and Mapping: Toward the Robust-Perception Age," IEEE TRO 2016. [必读综述]
- [2] **ORB-SLAM** — Mur-Artal et al., "ORB-SLAM: A Versatile and Accurate Monocular SLAM System," IEEE TRO 2015.
- [3] **ORB-SLAM2** — Mur-Artal & Tardós, "ORB-SLAM2: An Open-Source SLAM System for Monocular, Stereo, and RGB-D Cameras," IEEE TRO 2017.
- [4] **ORB-SLAM3** — Campos et al., "ORB-SLAM3: An Accurate Open-Source Library for Visual, Visual–Inertial, and Multimap SLAM," IEEE TRO 2021.
- [5] **VINS-Mono** — Qin et al., "VINS-Mono: A Robust and Versatile Monocular Visual-Inertial State Estimator," IEEE TRO 2018.
- [6] **SVO** — Forster et al., "SVO: Fast Semi-Direct Monocular Visual Odometry," ICRA 2014.
- [7] **DSO** — Engel et al., "Direct Sparse Odometry," IEEE TPAMI 2018.
- [8] **LOAM** — Zhang & Singh, "LOAM: Lidar Odometry and Mapping in Real-time," RSS 2014.
- [9] **LIO-SAM** — Shan et al., "LIO-SAM: Tightly-coupled Lidar Inertial Odometry via Smoothing and Mapping," IROS 2020.
- [10] **FAST-LIO** — Xu et al., "FAST-LIO: A Fast, Robust LiDAR-Inertial Odometry Package," IEEE RA-L 2021.
- [11] **FAST-LIO2** — Xu et al., "FAST-LIO2: Fast Direct LiDAR-Inertial Odometry," IEEE TRO 2022.
- [12] **NICE-SLAM** — Zhu et al., "NICE-SLAM: Neural Implicit Scalable Encoding for SLAM," CVPR 2022. [NeRF-SLAM]
- [13] **SplaTAM** — Keetha et al., "SplaTAM: Splat Track & Map 3D Gaussians for Dense RGB-D SLAM," CVPR 2024. [3DGS-SLAM]
- [14] **DynaSLAM** — Bescos et al., "DynaSLAM: Tracking, Mapping, and Inpainting in Dynamic Scenes," IEEE RA-L 2018.
- [15] **Kimera** — Rosinol et al., "Kimera: an Open-Source Library for Real-Time Metric-Semantic Simultaneous Localization and Mapping," ICRA 2020.
- [16] **RTAB-Map** — Labbé & Michaud, "RTAB-Map as an Open-Source Lidar and Visual SLAM Library for Large-Scale and Long-Term Online Operation," JFR 2019.
- [17] **NetVLAD** — Arandjelović et al., "NetVLAD: CNN Architecture for Weakly Supervised Place Recognition," CVPR 2016.
- [18] **Scan Context** — Kim & Kim, "Scan Context: Egocentric Spatial Descriptor for Place Recognition Within 3D Point Cloud Map," IROS 2018.

## 关联

- 相关概念: [[concept-multi-sensor-fusion]], [[concept-path-planning]], [[concept-drone-control]]
- 相关实体: [[entities/org-eth-asl]], [[entities/org-zhejiang-u-fast-lab]], [[entities/product-px4-autopilot]]
- 参见: [[topics/topic-slam-systems-comparison]], [[topics/topic-perception-stack]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——增加完整分类树、各系统参数对比、前端/后端/回环详解、地图类型对比、18篇论文引用
