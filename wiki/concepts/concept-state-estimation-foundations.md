# 状态估计基本功

> **类型**: concept
> **创建时间**: 2026-06-29
> **最后更新**: 2026-06-29
> **来源**: AI综合，见引用来源
> **标签**: #状态估计 #SLAM #多传感器融合 #机器人 #基本功

## 摘要

状态估计负责回答“无人机现在在哪里、姿态如何、速度多少、传感器偏置是多少”。它是飞控、VIO、SLAM、精准降落、目标跟踪和多传感器融合的共同底座。核心思想是用带噪声的运动模型和观测模型，在不确定性下估计隐藏状态。

---

## 知识地图

```
状态估计
├── 概率基础
│   ├── Bayes Rule
│   ├── Markov Assumption
│   └── Gaussian / Covariance
├── 滤波
│   ├── Kalman Filter
│   ├── Extended Kalman Filter
│   ├── Unscented Kalman Filter
│   └── Particle Filter
├── 平滑与优化
│   ├── Least Squares
│   ├── Bundle Adjustment
│   ├── Factor Graph
│   └── iSAM / GTSAM
├── 机器人状态
│   ├── SE(3) / SO(3)
│   ├── IMU Preintegration
│   └── Error-State Kalman Filter
└── 工程应用
    ├── VIO / SLAM
    ├── EKF2 / PX4
    ├── 目标跟踪 Kalman
    └── 传感器标定
```

---

## Bayes Filter 总公式

机器人状态估计可以抽象为递推：

```
预测:
  bel_bar(x_t) = ∫ p(x_t | u_t, x_{t-1}) bel(x_{t-1}) dx_{t-1}

更新:
  bel(x_t) = η p(z_t | x_t) bel_bar(x_t)
```

其中：

- `x_t`：当前状态，如位置、速度、姿态、IMU bias。
- `u_t`：控制量或运动输入，如 IMU 积分、里程计。
- `z_t`：观测，如 GPS、视觉位姿、LiDAR 匹配、气压计。
- `bel(x_t)`：状态的后验分布。

Kalman、EKF、UKF、粒子滤波都是 Bayes Filter 在不同假设下的具体实现。

---

## Kalman Filter 速查

线性高斯系统：

```
x_t = A x_{t-1} + B u_t + w_t,   w_t ~ N(0, Q)
z_t = H x_t + v_t,               v_t ~ N(0, R)
```

预测：

```
x_pred = A x + B u
P_pred = A P A^T + Q
```

更新：

```
y = z - H x_pred
S = H P_pred H^T + R
K = P_pred H^T S^{-1}
x = x_pred + K y
P = (I - K H) P_pred
```

工程解释：

- `Q` 越大，越不相信运动模型。
- `R` 越大，越不相信传感器观测。
- `P` 是状态不确定性，不是误差本身。
- `K` 是在预测和观测之间分配信任的权重。

---

## 滤波、平滑、因子图对比

| 方法 | 处理方式 | 优点 | 代价 | 典型系统 |
|------|----------|------|------|----------|
| Kalman Filter | 在线递推 | 快、可解释 | 线性高斯假设 | 目标跟踪、简单融合 |
| EKF/ESKF | 非线性线性化 | 适合 IMU/姿态 | 线性化误差、调参敏感 | PX4 EKF2、VIO |
| UKF | Sigma 点传播 | 比 EKF 更少推导 Jacobian | 计算更重 | 非线性传感器融合 |
| Particle Filter | 粒子表示分布 | 可表达多峰分布 | 粒子退化、计算重 | MCL、定位 |
| Bundle Adjustment | 批量非线性最小二乘 | 精度高 | 延迟和计算量高 | SfM、视觉 SLAM 后端 |
| Factor Graph | 图优化表达约束 | 模块化、可增量 | 建模复杂 | GTSAM、iSAM、现代 SLAM |

---

## 因子图直觉

因子图把状态估计写成“变量节点 + 约束因子”的图：

```
x0 ---- odom ---- x1 ---- odom ---- x2
 |                 |                 |
gps              vision            loop
```

目标函数：

```
min_X Σ_i || r_i(X_i) ||^2_{Σ_i}
```

每个因子贡献一个残差 `r_i` 和协方差 `Σ_i`。视觉重投影、IMU 预积分、GPS 位置、回环约束都可以作为因子接入。这也是现代 VIO/SLAM 后端喜欢因子图的原因：不同传感器可以以统一的残差形式融合。

---

## 无人机工程中的状态向量

常见 ESKF 状态：

```
x = [
  p_WB,      # 位置
  v_WB,      # 速度
  q_WB,      # 姿态四元数
  b_a,       # 加速度计 bias
  b_g,       # 陀螺仪 bias
  g_W        # 重力方向，可选
]
```

观测可以来自：

| 传感器 | 观测量 | 典型问题 |
--------|--------|----------|
| IMU | 角速度、加速度 | bias 漂移、时间同步 |
| GPS/RTK | 全局位置 | 多路径、遮挡、低频 |
| Camera | 特征重投影/视觉位姿 | 光照、模糊、尺度 |
| LiDAR | 点云匹配位姿 | 退化场景、外参 |
| Barometer | 高度 | 气压扰动 |
| Magnetometer | 航向 | 电磁干扰 |

---

## 调参排错表

| 现象 | 可能原因 | 排查动作 |
|------|----------|----------|
| 位置慢慢漂 | IMU bias 估计不足或观测太弱 | 检查 bias 曲线、增加外部观测 |
| 融合后抖动 | 观测噪声 R 设太小 | 增大对应传感器 R |
| 响应迟缓 | 过程噪声 Q 设太小 | 增大运动模型噪声 |
| GPS 一来就跳 | 坐标系或时间戳错误 | 检查 ENU/NED、时间同步 |
| 视觉融合发散 | 外参/延迟/尺度错误 | 重标定相机-机体外参，检查 EV delay |
| 协方差不收敛 | 模型不可观或噪声错误 | 检查观测可观性和单位 |

---

## 与现有知识库的关系

| 页面 | 状态估计支撑点 |
|------|----------------|
| [[concepts/concept-multi-sensor-fusion]] | EKF/ESKF、传感器噪声、外参、时间同步 |
| [[concepts/concept-slam]] | 滤波 SLAM、图优化 SLAM、回环约束 |
| [[topics/topic-precision-localization]] | RTK + 视觉 + IMU 融合 |
| [[entities/product-px4-autopilot]] | EKF2 参数、传感器融合链路 |
| [[topics/topic-illegal-parking-system]] | Kalman Filter 目标跟踪状态预测 |

---

## 学习检验

1. 写出一维 Kalman Filter 并画出 `Q/R` 改变后的估计曲线。
2. 解释 EKF 为什么需要 Jacobian，UKF 为什么不显式求 Jacobian。
3. 说明滤波和平滑的区别。
4. 把 GPS、视觉位姿、IMU 预积分分别建模成因子图残差。
5. 解释 ENU/NED/Body/Camera 坐标系转换为什么会导致定位跳变。

---

## 关联

- 总书单: [[topics/topic-foundational-reading-list]]
- 多传感器融合: [[concepts/concept-multi-sensor-fusion]]
- SLAM: [[concepts/concept-slam]]
- 视觉几何: [[concepts/concept-vision-geometry-foundations]]
- PX4: [[entities/product-px4-autopilot]]

## 引用来源

- [1] Kalman, R. E. (1960). **A New Approach to Linear Filtering and Prediction Problems**. Journal of Basic Engineering.
- [2] Thrun, S., Burgard, W., & Fox, D. **Probabilistic Robotics**. MIT Press, 2005. https://mitpress.mit.edu/9780262201629/probabilistic-robotics/
- [3] Barfoot, T. D. **State Estimation for Robotics**. Cambridge University Press, 2017. https://asrl.utias.utoronto.ca/~tdb/bib/barfoot_ser17.pdf
- [4] Dellaert, F., & Kaess, M. (2017). **Factor Graphs for Robot Perception**. Foundations and Trends in Robotics.
- [5] Cadena, C., et al. (2016). **Past, Present, and Future of Simultaneous Localization and Mapping**. IEEE TRO.
- [6] Labbe, R. **Kalman and Bayesian Filters in Python**. https://github.com/rlabbe/Kalman-and-Bayesian-Filters-in-Python

## 变更记录

- 2026-06-29: 初始创建，补充 Bayes Filter、Kalman、因子图、无人机状态向量和排错表。
