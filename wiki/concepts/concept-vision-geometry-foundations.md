# 视觉几何基本功

> **类型**: concept
> **创建时间**: 2026-06-29
> **最后更新**: 2026-06-29
> **来源**: AI综合，见引用来源
> **标签**: #感知 #视觉几何 #SLAM #标定 #基本功

## 摘要

视觉几何是无人机感知、定位、SLAM、三维重建、精准降落的底层语言。深度学习模型可以直接输出框、mask 或深度，但工程落地时仍要处理相机模型、坐标变换、标定、PnP、RANSAC、光流、特征匹配和多视图几何。

---

## 知识地图

```
视觉几何
├── 相机模型
│   ├── 针孔模型 / 内参 K / 外参 R,t
│   ├── 畸变模型 / 去畸变
│   └── 张正友标定
├── 单视图几何
│   ├── 投影 / 反投影
│   ├── PnP 位姿估计
│   └── Homography 单应矩阵
├── 双目与多视图
│   ├── Epipolar Geometry
│   ├── Essential / Fundamental Matrix
│   ├── Triangulation
│   └── Bundle Adjustment
├── 局部特征
│   ├── Harris / FAST / ORB
│   ├── SIFT / HOG
│   └── Descriptor Matching
└── 运动估计
    ├── Optical Flow
    ├── Visual Odometry
    └── RANSAC 鲁棒估计
```

---

## 必读书

| 书 | 章节重点 | 作用 |
|----|----------|------|
| Computer Vision: Algorithms and Applications | 相机模型、特征、运动、重建 | CV 总览，适合建立地图 |
| Multiple View Geometry | 投影几何、极几何、三角化、BA | 多视图几何根教材 |
| An Invitation to 3-D Vision | 相机、运动、重建 | 更适合配合 SLAM/VIO 阅读 |
| State Estimation for Robotics | 李群、最小二乘、状态估计 | 把视觉几何和优化估计接起来 |

---

## 核心公式

### 针孔相机模型

```
s [u, v, 1]^T = K [R | t] [X, Y, Z, 1]^T

K = [[fx, 0,  cx],
     [0,  fy, cy],
     [0,  0,  1 ]]
```

其中 `K` 是内参，`R,t` 是世界坐标到相机坐标的外参，`s` 是尺度。工程上最容易错的是坐标系方向：OpenCV 相机坐标通常为 x 右、y 下、z 前。

### 单应矩阵 Homography

对于平面场景或纯旋转相机，有：

```
x' ~ H x
```

典型用途：图像拼接、地面平面映射、透视矫正、ArUco/AprilTag 平面位姿初值。

### 极几何

```
x'^T F x = 0
E = K'^T F K
```

`F` 是基础矩阵，约束两张图像中匹配点必须落在对应极线上；`E` 是本质矩阵，适用于归一化相机坐标。

---

## 经典论文与算法

| 论文/算法 | 年份 | 核心贡献 | 工程位置 |
|-----------|------|----------|----------|
| Canny Edge Detector | 1986 | 多阶段边缘检测 | 传统边缘、裂缝候选、预处理 |
| Lucas-Kanade Optical Flow | 1981 | 局部光流估计 | KLT 跟踪、VIO 特征跟踪 |
| Horn-Schunck Optical Flow | 1981 | 全局光流约束 | 稠密运动估计基础 |
| Harris Corner | 1988 | 角点响应函数 | 特征检测基础 |
| RANSAC | 1981 | 鲁棒模型估计 | PnP、F/E/H 矩阵估计 |
| SIFT | 2004 | 尺度不变特征 | 经典匹配、SfM、定位 |
| HOG | 2005 | 梯度方向直方图 | 行人检测、传统特征 baseline |
| Zhang Calibration | 2000 | 平面棋盘格相机标定 | OpenCV 标定主流方法 |

---

## PnP 工程流程

```
输入:
  3D 点 P_i: 世界/标签坐标系下的点
  2D 点 p_i: 图像像素点
  相机内参 K 与畸变参数

流程:
  1. 去畸变或直接传入畸变参数
  2. solvePnP 求 R,t
  3. projectPoints 回投影检查误差
  4. 用 RANSAC 版本剔除错匹配
  5. 将相机位姿转换到无人机/世界坐标系
```

### 位姿估计排错表

| 现象 | 常见原因 | 检查方式 |
|------|----------|----------|
| 位姿跳变 | 角点顺序错误或误匹配 | 可视化 2D-3D 点编号 |
| 距离尺度不对 | 标记物真实尺寸填错 | 检查单位 m/mm 是否混用 |
| 姿态方向反了 | 坐标系定义不一致 | 画出 camera/body/world 三轴 |
| 回投影误差大 | 内参或畸变错误 | 用标定图重算 reprojection error |
| RANSAC 内点少 | 特征重复纹理或模糊 | 提高快门速度，筛匹配距离 |

---

## 与现有知识库的关系

| 页面 | 视觉几何支撑点 |
|------|----------------|
| [[topics/topic-precision-localization]] | ArUco、solvePnP、相机到机体系转换 |
| [[concepts/concept-slam]] | 特征匹配、PnP、三角化、BA |
| [[concepts/concept-multi-sensor-fusion]] | 相机-IMU 外参、视觉观测模型 |
| [[topics/topic-perception-stack]] | 深度估计、三维重建、感知到规划坐标转换 |
| [[topics/topic-crack-detection]] | 透视校正、像素到真实尺寸映射 |

---

## 学习检验

1. 写出像素坐标到归一化相机坐标的转换。
2. 解释 `F`、`E`、`H` 三个矩阵各自适用场景。
3. 用 OpenCV 完成一次棋盘格标定，并解释 reprojection error。
4. 用 RANSAC 估计单应矩阵，观察 outlier 对结果的影响。
5. 用 `solvePnP` 估计 ArUco 标签位姿，并把位姿转换到机体系。

---

## 关联

- 总书单: [[topics/topic-foundational-reading-list]]
- SLAM: [[concepts/concept-slam]]
- 多传感器融合: [[concepts/concept-multi-sensor-fusion]]
- 精准定位项目: [[topics/topic-precision-localization]]
- 感知全栈: [[topics/topic-perception-stack]]

## 引用来源

- [1] Szeliski, R. **Computer Vision: Algorithms and Applications**. https://szeliski.org/Book/
- [2] Hartley, R., & Zisserman, A. **Multiple View Geometry in Computer Vision**. https://www.robots.ox.ac.uk/~vgg/hzbook/
- [3] Fischler, M. A., & Bolles, R. C. (1981). **Random Sample Consensus**. Communications of the ACM.
- [4] Lowe, D. G. (2004). **Distinctive Image Features from Scale-Invariant Keypoints**. IJCV. https://www.cs.ubc.ca/~lowe/papers/ijcv04.pdf
- [5] Zhang, Z. (2000). **A Flexible New Technique for Camera Calibration**. IEEE TPAMI. https://www.microsoft.com/en-us/research/publication/a-flexible-new-technique-for-camera-calibration/
- [6] Lucas, B. D., & Kanade, T. (1981). **An Iterative Image Registration Technique with an Application to Stereo Vision**. IJCAI.
- [7] Harris, C., & Stephens, M. (1988). **A Combined Corner and Edge Detector**. Alvey Vision Conference.

## 变更记录

- 2026-06-29: 初始创建，补充相机模型、多视图几何、特征与 PnP 工程排错表。
