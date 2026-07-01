# 多传感器融合（Multi-Sensor Fusion）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

多传感器融合将来自 IMU、相机、LiDAR、GPS/RTK、气压计等异构传感器的数据进行时空对齐与信息融合，以获得比单一传感器更鲁棒、精确的状态估计。无人机导航的核心基础。

## 传感器特性速查

| 传感器 | 频率 | 精度 | 优势 | 局限 |
|--------|------|------|------|------|
| IMU | 200~1000Hz | 短期高 | 高频姿态，完全自主 | 长期漂移 |
| 单目相机 | 30~120Hz | 中 | 成本低，纹理丰富 | 无尺度，光照敏感 |
| 双目相机 | 30~60Hz | 中高 | 有尺度，无需标定IMU | 基线限制距离 |
| RGB-D | 30Hz | 高（近距） | 直接深度 | 室外失效，范围有限 |
| LiDAR | 10~20Hz | 极高 | 直接3D，无纹理要求 | 重量大，成本高 |
| GPS | 1~10Hz | 1~5m | 全球定位 | 室内失效，多路径误差 |
| RTK GPS | 1~10Hz | 2cm | 厘米级 | 需基站，初始化慢 |
| 气压计 | 20~100Hz | ±1m | 高度辅助 | 气压波动影响 |

## 主流融合框架

### 松耦合 vs 紧耦合 vs 深度耦合

```
松耦合（Loosely Coupled）:
  各传感器独立输出 → 融合估计量
  优点：模块化，任一传感器失效不崩溃
  缺点：信息损失，精度次于紧耦合

紧耦合（Tightly Coupled）:
  原始测量值 → 统一优化框架
  优点：精度最高，充分利用原始信息
  缺点：计算复杂，任一传感器异常需特殊处理

深度耦合（Deeply Coupled）:
  传感器底层信号级融合（如 GPS 相关器 + INS）
  优点：抗干扰最强
  应用：军事级高精度系统
```

### 扩展卡尔曼滤波（EKF）

```python
"""
EKF 用于非线性系统的传感器融合经典方法
状态向量: x = [p, v, q, b_a, b_g]
  p: 位置 3D
  v: 速度 3D  
  q: 姿态四元数 4D
  b_a: 加速度计偏置 3D
  b_g: 陀螺仪偏置 3D
共 16 维
"""
class EKF:
    def predict(self, imu_data, dt):
        """IMU 预测步：高频，200-1000Hz"""
        # 姿态传播
        q_new = q ⊗ exp(ω*dt/2)
        # 位置/速度传播  
        p_new = p + v*dt + 0.5*(R@a + g)*dt²
        v_new = v + (R@a + g)*dt
        # 协方差传播
        P_new = F @ P @ F.T + Q

    def update(self, measurement, H, R_noise):
        """测量更新步：相机/GPS，低频"""
        # 卡尔曼增益
        K = P @ H.T @ inv(H @ P @ H.T + R_noise)
        # 状态更新
        x = x + K @ (z - H@x)
        P = (I - K@H) @ P
```

### 误差状态卡尔曼滤波（ESKF）

ESKF 是 EKF 在旋转流形上的正确实现：

```
状态: δx = [δp, δv, δθ, δb_a, δb_g]（误差量，15维）
优点:
  - 误差状态小量，线性化精度更高
  - 四元数在 SO(3) 上正确更新
  - FAST-LIO2, PX4 EKF2 均采用此方案
```

### 图优化方法（因子图）

```python
"""
GTSAM / g2o 因子图融合示例
每个传感器测量 → 因子边
状态节点 → 位姿、速度、偏置
"""
graph = gtsam.NonlinearFactorGraph()

# IMU 预积分因子
imu_factor = gtsam.ImuFactor(
    pose_key_i, vel_key_i, bias_key_i,
    pose_key_j, vel_key_j, bias_key_j,
    preintegrated_imu
)
graph.add(imu_factor)

# GPS 位置因子
gps_factor = gtsam.GPSFactor(pose_key_j, gps_measurement, gps_noise)
graph.add(gps_factor)

# 视觉重投影因子
visual_factor = gtsam.GenericProjectionFactor(
    pixel, K, pose_key, landmark_key, noise
)
graph.add(visual_factor)

# 非线性优化
optimizer = gtsam.LevenbergMarquardtOptimizer(graph, initial_values)
result = optimizer.optimize()
```

## 标定

### 时间标定（时间戳对齐）

```python
# 各传感器存在触发延迟差异
# IMU: 硬件触发，最准确
# 相机: 曝光时间 + 传输延迟（通常 5~30ms）
# GPS: PPS 同步信号

# Kalibr 时间标定:
rosrun kalibr kalibr_calibrate_imu_camera \
  --bag data.bag \
  --cam cam.yaml \
  --imu imu.yaml \
  --target april_grid.yaml
```

### 空间标定（外参标定）

| 标定对 | 工具 | 方法 |
|--------|------|------|
| Camera-IMU | Kalibr | 激励运动，最小化重投影误差 |
| Camera-LiDAR | LCECalib, targetless | 线/面特征匹配 |
| Camera-Camera（双目） | OpenCV stereo | 棋盘格 |
| LiDAR-IMU | LI-Init | 退化运动检测 |

## VIO（视觉惯性里程计）详解

VIO 是无人机最常用的自主定位方案：

```
输入: 图像序列 + IMU 数据流
输出: 6DoF 位姿 + 稀疏地图

主流方案:
  VINS-Mono → 滑窗优化，单目+IMU，港科大
  VINS-Fusion → 多相机+GPS，灵活扩展
  OpenVINS → 开源VIO框架，MSCKF变种
  MSCKF → 多状态约束卡尔曼，轻量
  Basalt → 预积分+非线性优化
```

## 论文引用

- [1] **Kalman Filter** — Kalman, "A New Approach to Linear Filtering and Prediction Problems," JBE 1960. [经典奠基]
- [2] **EKF-SLAM** — Smith et al., "Estimating Uncertain Spatial Relationships in Robotics," AAAI 1986.
- [3] **IMU预积分** — Forster et al., "IMU Preintegration on Manifold for Efficient Visual-Inertial Maximum-a-Posteriori Estimation," RSS 2015. [必读]
- [4] **ESKF** — Joan Sola, "Quaternion Kinematics for the Error-State Kalman Filter," arXiv 2017. [ESKF经典教材]
- [5] **VINS-Mono** — Qin et al., "VINS-Mono: A Robust and Versatile Monocular Visual-Inertial State Estimator," IEEE TRO 2018.
- [6] **OpenVINS** — Geneva et al., "OpenVINS: A Research Platform for Visual-Inertial Estimation," ICRA 2020.
- [7] **MSCKF** — Mourikis & Roumeliotis, "A Multi-State Constraint Kalman Filter for Vision-aided Inertial Navigation," ICRA 2007.
- [8] **FAST-LIO2** — Xu et al., "FAST-LIO2: Fast Direct LiDAR-Inertial Odometry," IEEE TRO 2022.
- [9] **Kalibr** — Furgale et al., "Unified Temporal and Spatial Calibration for Multi-Sensor Systems," IROS 2013.
- [10] **LVI-SAM** — Shan et al., "LVI-SAM: Tightly-coupled Lidar-Visual-Inertial Odometry via Smoothing and Mapping," ICRA 2021.
- [11] **R3LIVE** — Lin & Zhang, "R3LIVE: A Robust, Real-time, RGB-colored, LiDAR-Inertial-Visual tightly-coupled state Estimation and mapping package," ICRA 2022.
- [12] **Basalt** — Usenko et al., "Visual-Inertial Mapping with Non-Linear Factor Recovery," IEEE RA-L 2020.
- [13] **GTSAM** — Dellaert & GTSAM contributors, "Factor Graphs and GTSAM: A Hands-on Introduction," GT TR 2012.
- [14] **RTK-VIO融合** — Liu et al., "Tightly-coupled GNSS/INS Integration with Robust Initialization," 2022.
- [15] **联合标定** — Rehder et al., "Extending Kalibr: Calibrating the Extrinsics of Multiple IMUs and of Individual Axes," ICRA 2016.

## 关联

- 相关概念: [[concept-slam]], [[concept-drone-control]], [[concept-path-planning]]
- 相关实体: [[entities/product-px4-autopilot]], [[entities/org-eth-asl]]
- 参见: [[topics/topic-precision-localization]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——传感器对比表、EKF/ESKF代码、因子图代码、标定工具、VIO框架对比、15篇论文引用
