# 无人机 AI 算法工程师学习路线图

> **类型**: topic（学习路线）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: 知识库初始化（AI综合整理）
> **标签**: #工程 #深度学习 #感知 #规划 #控制 #SLAM

## 摘要

本页面整理了成为无人机 AI 算法工程师所需的完整知识体系与学习路径，分为数学基础、核心算法、工程实践三大层次，并给出推荐学习顺序、必读论文清单和配套代码资源。学习周期约 12-18 个月，面向有一定编程基础的学习者。

## 详情

### 技能全景图

```
┌─────────────────────────────────────────────────────────────┐
│                 无人机 AI 算法工程师技能树                    │
├────────────┬────────────┬──────────┬─────────────────────────┤
│  感知层     │  规划层    │  控制层  │       工程基础           │
│            │            │          │                         │
│ 目标检测   │ 路径规划   │ 飞控原理  │ Python/C++ (Eigen/PCL)  │
│ 语义分割   │ 轨迹优化   │ PID/MPC   │ ROS2 (DDS/Action/TF2)  │
│ 深度估计   │ 全局规划   │ 强化学习  │ Linux/Git/CMake/Docker  │
│ 目标跟踪   │ 局部规划   │ 动力学   │ CUDA/TensorRT/RKNN     │
├────────────┴────────────┴──────────┼─────────────────────────┤
│         状态估计与建图               │      仿真与验证          │
│  SLAM / VIO / LiDAR-SLAM           │ Gazebo / AirSim        │
│  多传感器融合 / Kalibr标定          │ IsaacGym / Flightmare  │
│  EKF / 因子图 / IMU预积分           │ SIL → HIL → 真机测试   │
└───────────────────────────────────┴─────────────────────────┘
```

### 数学基础（优先级最高）

| 领域 | 核心内容 | 推荐资源 | 必要性 |
|------|----------|----------|--------|
| 线性代数 | 矩阵/特征值/SVD/PCA推导 | 3Blue1Brown, MIT 18.06 | ★★★★★ |
| 概率统计 | 贝叶斯/高斯分布/MLE/MAP | 《概率机器人》 | ★★★★★ |
| 微积分与优化 | 梯度下降/拉格朗日/凸优化 | Boyd《Convex Optimization》 | ★★★★ |
| 旋转理论 | SO(3)/SE(3)/李代数/李群 | 《视觉 SLAM 十四讲》附录 | ★★★★★ |
| 图论 | 图搜索/因子图/最大后验估计 | SLAM 后端必备 | ★★★ |
| 信息论 | 熵/KL散度/互信息 | 深度学习理论基础 | ★★★ |

### 阶段一：编程与工具基础（1-3 个月）

```
Python → NumPy/OpenCV/Matplotlib/PyTorch
C++ → STL/Eigen3/PCL/OpenCV
Linux → Shell/Git/CMake/Docker/systemd
ROS2 → 节点/话题/服务/动作/TF2/launch
```

**里程碑**：能独立运行 ROS2 小乌龟 + 简单 Publisher/Subscriber + 能用 CMake 编译 C++ ROS2 节点

**关键代码：ROS2 Publisher 模板**

```cpp
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>

class DroneControlNode : public rclcpp::Node {
public:
    DroneControlNode() : Node("drone_control") {
        pub_ = create_publisher<geometry_msgs::msg::PoseStamped>(
            "/mavros/setpoint_position/local", 10);
        timer_ = create_wall_timer(
            std::chrono::milliseconds(100),
            std::bind(&DroneControlNode::timer_cb, this));
    }
private:
    void timer_cb() {
        auto msg = geometry_msgs::msg::PoseStamped();
        msg.header.stamp = now();
        msg.header.frame_id = "map";
        msg.pose.position.x = 0.0;
        msg.pose.position.y = 0.0;
        msg.pose.position.z = 5.0;  // 悬停 5m
        pub_->publish(msg);
    }
    rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pub_;
    rclcpp::TimerBase::SharedPtr timer_;
};
```

### 阶段二：深度学习与感知（2-4 个月）

```
深度学习基础（CNN/Transformer/训练技巧）→ 参见 [[concepts/concept-deep-learning-basics]]
    ↓
骨干网络（ResNet/MobileNet/ViT/SwinT）→ 参见 [[concepts/concept-cv-classic-backbones]]
    ↓
YOLOv8 目标检测（VisDrone 数据集实战）→ 参见 [[concepts/concept-object-detection]]
    ↓
语义分割（SegFormer）→ 参见 [[topics/topic-crack-detection]]
    ↓
目标跟踪（ByteTrack/StrongSORT）→ 参见 [[topics/topic-illegal-parking-system]]
```

**里程碑**：在 VisDrone 数据集上训练/评估 YOLOv8，mAP50 > 25%

### 阶段三：SLAM 与状态估计（2-4 个月）

```
针孔相机模型 + 对极几何（E/F/H矩阵推导）
    ↓
视觉里程计（手写 VO，BA优化）
    ↓
ORB-SLAM3（运行+阅读源码）→ 参见 [[concepts/concept-slam]]
    ↓
VIO：VINS-Mono（相机+IMU松紧耦合）
    ↓
LiDAR SLAM：FAST-LIO2（ESKF+ikd-Tree）
    ↓
多传感器融合 → 参见 [[concepts/concept-multi-sensor-fusion]]
```

**推荐书籍**：《视觉 SLAM 十四讲》（高翔 著）— 中文领域最佳 SLAM 教材

**关键实验**：Kalibr 标定相机-IMU（`kalibr_calibrate_imu_camera`），获取 T_cam_imu 和 IMU noise model

### 阶段四：规划与控制（2-3 个月）

```
无人机动力学模型（刚体动力学 + 旋翼模型）
    ↓
PID 调参（PX4 + Gazebo 仿真）→ 参见 [[entities/product-px4-autopilot]]
    ↓
A* / RRT 全局规划（栅格地图/ESDF）
    ↓
EGO-Planner 局部规划（无ESDF，球形SFC）→ 参见 [[concepts/concept-path-planning]]
    ↓
Minimum Snap / MINCO 轨迹优化
    ↓
MPC 控制（cvxpy/acados）→ 参见 [[concepts/concept-drone-control]]
```

**里程碑**：PX4 + Gazebo 中实现自主避障飞行，能可视化规划轨迹

### 阶段五：工程部署（1-2 个月）

```
ONNX 导出 → 参见 [[concepts/method-model-deployment]]
    ↓
TensorRT FP16 推理加速（Jetson Orin）
    ↓
RKNN 部署（RK3588）
    ↓
ROS2 + PX4 系统集成（MAVROS / px4_ros_com）
    ↓
完整 Perception-Planning-Control 链路联调
```

### 阶段六：前沿研究（持续）

```
强化学习飞行控制（PPO + IsaacGym）→ 参见 [[concepts/concept-reinforcement-learning]]
    ↓
Sim-to-Real Gap 处理（域随机化）→ 参见 [[topics/topic-sim-to-real]]
    ↓
多机协同（MARL，Centralized Training Decentralized Execution）
    ↓
NeRF/3DGS 场景重建与导航 → 参见 [[topics/topic-perception-stack]]
    ↓
LLM/VLM + 无人机任务规划（SayPlan, VoxPoser）
    ↓
持续跟踪顶会论文（ICRA/IROS/RSS/CVPR/NeurIPS）
```

### 推荐书单

| 书名 | 方向 | 难度 | 推荐指数 |
|------|------|------|---------|
| 《视觉 SLAM 十四讲》（高翔） | SLAM | ⭐⭐⭐ | ★★★★★ |
| 《概率机器人》（Thrun et al.） | 状态估计 | ⭐⭐⭐⭐ | ★★★★★ |
| 《深度学习》（Goodfellow et al.） | 深度学习 | ⭐⭐⭐⭐ | ★★★★ |
| 《多旋翼飞行器设计与控制》 | 飞控 | ⭐⭐⭐ | ★★★★ |
| Convex Optimization（Boyd） | 优化 | ⭐⭐⭐⭐⭐ | ★★★★ |
| State Estimation for Robotics（Barfoot） | 状态估计/李代数 | ⭐⭐⭐⭐⭐ | ★★★★★ |
| 《机器人学：建模、规划与控制》 | 规划控制 | ⭐⭐⭐⭐ | ★★★ |

### 顶会/期刊列表

| 类型 | 名称 | 方向 | 录取率 |
|------|------|------|-------|
| 会议 | ICRA | 机器人综合 | ~40% |
| 会议 | IROS | 机器人综合 | ~45% |
| 会议 | RSS | 机器人顶级小会 | ~25% |
| 会议 | CVPR | 计算机视觉 | ~25% |
| 会议 | NeurIPS, ICLR | 深度学习/RL | ~25% |
| 期刊 | IEEE T-RO | 机器人顶刊 | — |
| 期刊 | IEEE RA-L | 机器人快报 | — |
| 期刊 | IJRR | 机器人研究 | — |

### 必读论文清单（按主题）

**感知**：YOLOv8 技术报告, DETR, Swin Transformer, SegFormer, ByteTrack, DepthAnything V2

**SLAM**：ORB-SLAM3, VINS-Mono, FAST-LIO2, LIO-SAM, NeRF, 3DGS

**规划**：EGO-Planner, GCOPTER, MINCO, FASTER, Agile Autonomy

**控制**：Geometric Control, PPO for Quadrotor, L1 Adaptive Control

**融合**：MSCKF, GTSAM, iSAM2, OpenCalib

## 关联
- 相关概念: [[concepts/concept-object-detection]], [[concepts/concept-slam]], [[concepts/concept-path-planning]], [[concepts/concept-drone-control]], [[concepts/concept-reinforcement-learning]], [[concepts/method-model-deployment]], [[concepts/concept-multi-sensor-fusion]]
- 相关机构: [[entities/org-eth-asl]], [[entities/org-zhejiang-u-fast-lab]]
- 相关主题: [[topics/topic-perception-stack]], [[topics/topic-sim-to-real]]

## 引用来源

### SLAM 经典
- [1] Mur-Artal, R., & Tardós, J. D. (2017). **ORB-SLAM2: An Open-Source SLAM System for Monocular, Stereo, and RGB-D Cameras**. IEEE T-RO 33(5). — 视觉 SLAM 必学
- [2] Campos, C., et al. (2021). **ORB-SLAM3: An Accurate Open-Source Library for Visual, Visual–Inertial, and Multimap SLAM**. IEEE T-RO 37(6). — ORB-SLAM3，VIO+多地图
- [3] Qin, T., et al. (2018). **VINS-Mono: A Robust and Versatile Monocular Visual-Inertial State Estimator**. IEEE T-RO 34(4). — VIO 标志性工作
- [4] Xu, W., et al. (2022). **FAST-LIO2: Fast Direct LiDAR-Inertial Odometry**. IEEE T-RO 38(4). — LiDAR-IMU SLAM SOTA

### 感知基础
- [5] He, K., et al. (2016). **Deep Residual Learning for Image Recognition**. CVPR 2016. — ResNet，深度学习里程碑
- [6] Dosovitskiy, A., et al. (2021). **An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale**. ICLR 2021. — ViT，感知基础
- [7] Vaswani, A., et al. (2017). **Attention Is All You Need**. NeurIPS 2017. — Transformer 原始论文
- [8] Lin, T. Y., et al. (2017). **Focal Loss for Dense Object Detection**. ICCV 2017. — RetinaNet，Focal Loss

### 规划控制
- [9] Zhou, X., et al. (2021). **EGO-Planner: An ESDF-Free Gradient-Based Local Planner for Quadrotors**. IEEE RA-L 6(2). — 无ESDF局部规划
- [10] Wang, Z., et al. (2022). **Geometrically Constrained Trajectory Optimization for Multicopters**. IEEE T-RO 38(5). — GCOPTER/MINCO
- [11] Mellinger, D., & Kumar, V. (2011). **Minimum Snap Trajectory Generation and Control for Quadrotors**. ICRA 2011. — 最小 snap 轨迹优化经典
- [12] Lee, T., et al. (2010). **Geometric Tracking Control of a Quadrotor UAV on SE(3)**. IEEE CDC. — 几何控制无人机

### 工程部署
- [13] Li, Y., et al. (2020). **TASO: Optimizing Deep Learning Computation with Automatic Generation of Graph Substitutions**. SOSP 2019. — 推理图优化基础
- [14] Han, S., et al. (2016). **Deep Compression: Compressing Deep Neural Networks with Pruning, Trained Quantization and Huffman Coding**. ICLR 2016. — 压缩部署经典

### 前沿方向
- [15] Kaufmann, E., et al. (2023). **Champion-Level Drone Racing Using Deep Reinforcement Learning**. Nature 2023. — RL 飞行世界冠军级应用
- [16] Mildenhall, B., et al. (2020). **NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis**. ECCV 2020. — 神经场景重建
- [17] Kerbl, B., et al. (2023). **3D Gaussian Splatting for Real-Time Radiance Field Rendering**. SIGGRAPH 2023. — 实时重建 SOTA

## 变更记录
- 2026-06-27: 初始创建，知识库初始化
- 2026-06-27: 大规模扩写，补充17篇论文引用、代码示例、详细书单和路线细化
