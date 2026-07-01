# PX4 Autopilot

> **类型**: entity（产品/开源项目）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: 知识库初始化（AI综合整理）
> **标签**: #控制 #工程 #飞控 #ROS2 #MAVLink

## 摘要

PX4 是全球最广泛使用的开源无人机飞控固件，支持多旋翼、固定翼、垂起等多种机型，提供完整的导航、控制、任务管理功能，是无人机 AI 算法工程师连接算法与飞行器硬件的核心工程平台。通过 Offboard 模式，外部 AI 算法可以实时控制飞行器位置、速度、姿态。

## 详情

### 基本信息

- **项目地址**：https://github.com/PX4/PX4-Autopilot
- **许可协议**：BSD 3-Clause
- **开发组织**：Dronecode Foundation（Linux Foundation 旗下）
- **主要贡献者**：ETH Zurich（早期），Holybro、Auterion 等企业
- **编程语言**：C++（核心），Python（工具链）
- **当前稳定版**：v1.14.x

### 核心架构

```
┌─────────────────────────────────────────────┐
│              PX4 飞控固件架构                  │
├─────────────────────────────────────────────┤
│  硬件抽象层（NuttX RTOS + 驱动）              │
│  ├── IMU 驱动（ICM-42688-P）                 │
│  ├── GPS 驱动（u-blox M9N）                  │
│  ├── 气压计（BMP390）                         │
│  └── 磁力计（IST8310）                        │
├─────────────────────────────────────────────┤
│  uORB 消息总线（发布-订阅）                    │
├─────────────────────────────────────────────┤
│  状态估计（EKF2）                             │
│  ├── 传感器融合（IMU + GPS + 气压计 + 视觉）   │
│  ├── 时间延迟补偿（Delay Compensation）       │
│  └── 风速估计                                 │
├─────────────────────────────────────────────┤
│  控制器                                       │
│  ├── 位置控制（mc_pos_control）               │
│  ├── 姿态控制（mc_att_control）               │
│  ├── 速率控制（mc_rate_control）              │
│  └── 混控（Mixer）                            │
├─────────────────────────────────────────────┤
│  导航（Navigator）                            │
│  ├── 任务模式（Mission / Waypoint）           │
│  ├── 返航（RTL）                              │
│  ├── 精准降落（Land / Precision Land）        │
│  └── 跟随模式（Follow-Me）                   │
├─────────────────────────────────────────────┤
│  通信                                         │
│  ├── MAVLink（地面站/MAVROS）                 │
│  └── uXRCE-DDS（ROS2 原生，v1.14+）          │
└─────────────────────────────────────────────┘
```

### uORB 消息总线

PX4 的核心通信机制（发布-订阅模式），类似 ROS Topic 但运行在实时操作系统内：

```cpp
#include <uORB/uORB.h>
#include <uORB/topics/sensor_combined.h>
#include <uORB/topics/vehicle_attitude_setpoint.h>

// 订阅传感器数据
int sensor_sub = orb_subscribe(ORB_ID(sensor_combined));
sensor_combined_s sensor_data;
orb_copy(ORB_ID(sensor_combined), sensor_sub, &sensor_data);

// 发布姿态控制指令
orb_advert_t att_sp_pub = orb_advertise(
    ORB_ID(vehicle_attitude_setpoint), nullptr);
vehicle_attitude_setpoint_s att_sp{};
att_sp.roll_body  = 0.0f;
att_sp.pitch_body = 0.1f;  // 俯仰 5.7°
att_sp.yaw_body   = 0.0f;
att_sp.thrust_body[2] = -0.6f;
orb_publish(ORB_ID(vehicle_attitude_setpoint), att_sp_pub, &att_sp);
```

### 与外部 AI 算法的接口

| 接口 | 用途 | 协议 | 推荐版本 |
|------|------|------|---------|
| **MAVROS（ROS1）** | ROS 连接 PX4 | MAVLink over UDP/Serial | ROS Noetic |
| **px4_ros_com（ROS2）** | ROS2 原生接口 | uXRCE-DDS | PX4 v1.14+ |
| **MAVLink SDK** | 纯 MAVLink 控制 | UDP/TCP | 任意 |
| **pymavlink** | Python MAVLink | UDP | 快速原型 |

**ROS2 Offboard 控制完整示例**（精准定位项目核心，参见 [[topics/topic-precision-localization]]）：

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from px4_msgs.msg import (OffboardControlMode, TrajectorySetpoint,
                           VehicleCommand, VehicleStatus)

class OffboardController(Node):
    def __init__(self):
        super().__init__('offboard_controller')

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Publishers
        self.offboard_mode_pub = self.create_publisher(
            OffboardControlMode, '/fmu/in/offboard_control_mode', qos)
        self.trajectory_pub = self.create_publisher(
            TrajectorySetpoint, '/fmu/in/trajectory_setpoint', qos)
        self.vehicle_cmd_pub = self.create_publisher(
            VehicleCommand, '/fmu/in/vehicle_command', qos)

        # Subscribers
        self.status_sub = self.create_subscription(
            VehicleStatus, '/fmu/out/vehicle_status',
            self.status_cb, qos)

        self.timer = self.create_timer(0.1, self.timer_cb)  # 10Hz
        self.counter = 0
        self.armed = False

    def status_cb(self, msg):
        self.armed = (msg.arming_state == VehicleStatus.ARMING_STATE_ARMED)

    def publish_offboard_mode(self):
        msg = OffboardControlMode()
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.offboard_mode_pub.publish(msg)

    def publish_setpoint(self, x, y, z, yaw=0.0):
        msg = TrajectorySetpoint()
        msg.position = [x, y, z]  # NED 坐标系，z 为负值表示向上
        msg.yaw = yaw
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.trajectory_pub.publish(msg)

    def arm(self):
        msg = VehicleCommand()
        msg.command = VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM
        msg.param1 = 1.0
        msg.target_system = 1
        msg.source_system = 1
        msg.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.vehicle_cmd_pub.publish(msg)

    def timer_cb(self):
        self.publish_offboard_mode()  # 必须持续发送，否则退出 Offboard

        if self.counter == 10:  # 先发 10 次 Offboard 指令再解锁
            self.arm()
            self.send_offboard_mode_command()

        # 发送悬停在 (0, 0, -5) —— NED 坐标系，-5 表示向上 5m
        self.publish_setpoint(0.0, 0.0, -5.0, yaw=0.0)
        self.counter += 1
```

### EKF2 状态估计器

PX4 内置的扩展卡尔曼滤波器，支持多传感器融合：

```
输入传感器：
├── IMU（必须，100-400Hz）
├── GPS（默认位置源，1-10Hz）
├── 气压计（高度辅助，25Hz）
├── 磁力计（偏航辅助，10Hz）
├── 光流（室内，视觉辅助，可选）
├── 视觉位姿（VIO/SLAM，可选）
│   └── /mavros/vision_pose/pose → EKF2_AID_MASK
└── 测距仪（高度精确，可选）

关键参数：
EKF2_AID_MASK = 24  (GPS + 视觉位姿，二进制 011000)
EKF2_HGT_MODE = 3   (视觉作为主高度源)
EKF2_EV_DELAY = 20  (视觉延迟补偿，ms)
```

**视觉位姿融合（VIO接入PX4）**：

```python
# 将 SLAM 位姿发布到 MAVROS 接口
from geometry_msgs.msg import PoseStamped

def publish_vision_pose(slam_pose: PoseStamped):
    """将 ORB-SLAM3 / VINS-Mono 位姿桥接到 PX4 EKF2"""
    # 注意：需要将 slam 坐标系转换为 ENU（ROS标准）
    # PX4 内部使用 NED，MAVROS 自动完成 ENU→NED 转换
    vision_pub.publish(slam_pose)
```

### 仿真支持

| 仿真器 | 特点 | 推荐场景 |
|--------|------|---------|
| **Gazebo Classic** | ROS1 生态成熟 | 旧项目维护 |
| **Gazebo Harmonic (gz)** | ROS2 原生，新标准 | 新项目首选 |
| **AirSim** | UE4 渲染，逼真 | 视觉算法测试 |
| **jMAVSim** | 极轻量，Java | 快速功能测试 |
| **Flightmare** | Unity，RL训练 | 强化学习 |

**Gazebo 一键启动**：

```bash
# 启动 PX4 + Gazebo Classic 仿真
cd ~/PX4-Autopilot
make px4_sitl gazebo-classic_iris

# 同时启动 MAVROS (另一个终端)
ros2 launch mavros px4.launch fcu_url:="udp://:14540@localhost:14557"

# 解锁并起飞（另一个终端）
ros2 run mavros mavsys mode -c OFFBOARD
ros2 run mavros mavsafety arm
```

### AI 算法集成最佳实践

```
感知 AI 算法（Python/C++）
    │
    ├── 检测/跟踪结果（BBox, ID, 类别）
    │       ↓
    │   坐标系变换（像素 → 相机 → 世界）
    │       ↓
    │   决策逻辑（如：目标在视野中心则接近）
    │       ↓
    │   速度/位置 Setpoint 生成
    │
    ↓ px4_ros_com / MAVROS
PX4 Offboard 模式
    ↓ uORB (10-50Hz)
飞控内环（EKF2 估计 + 位置/姿态/速率 PID）
    ↓ PWM / UAVCAN
ESC + 电机（电调）
```

### 关键参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MPC_XY_VEL_MAX` | 12 m/s | XY 最大速度 |
| `MPC_Z_VEL_MAX_UP` | 3 m/s | 上升最大速度 |
| `MPC_LAND_SPEED` | 0.7 m/s | 降落速度 |
| `MC_PITCH_P` | 6.5 | 俯仰比例增益 |
| `MC_ROLL_P` | 6.5 | 横滚比例增益 |
| `EKF2_AID_MASK` | 1 | 辅助传感器掩码 |
| `COM_RCL_ACT` | 0 | 遥控丢失动作（0=返航） |

### 版本说明

- **PX4 v1.14+**：支持 uXRCE-DDS，ROS2 原生通信，**新项目强烈推荐**
- **PX4 v1.13 及以前**：MAVROS over MAVLink，稳定但接口较旧

## 关联
- 相关概念: [[concepts/concept-drone-control]], [[concepts/method-model-deployment]], [[concepts/concept-multi-sensor-fusion]]
- 相关主题: [[topics/topic-precision-localization]], [[topics/topic-sim-to-real]], [[topics/roadmap-drone-ai-engineer]]
- 相关实体: [[entities/org-eth-asl]], [[entities/org-zhejiang-u-fast-lab]]

## 引用来源

### PX4 系统设计论文
- [1] Meier, L., et al. (2015). **PX4: A Node-Based Multithreaded Open Source Robotics Framework for Deeply Embedded Platforms**. ICRA 2015. — PX4 原始设计论文，uORB 消息总线
- [2] Furrer, F., et al. (2016). **RotorS - A Modular Gazebo MAV Simulator Framework**. Robot Operating System (ROS) 2016. — Gazebo 仿真框架，配合 PX4 使用
- [3] Quigley, M., et al. (2009). **ROS: An Open-Source Robot Operating System**. ICRA Workshop 2009. — ROS 奠基论文，MAVROS 基础

### 状态估计
- [4] Madyastha, V., et al. (2011). **Extended Kalman Filter vs. Error State Kalman Filter for Aircraft Attitude Estimation**. AIAA Guidance. — EKF vs ESKF 对比，EKF2 理论基础
- [5] Mourikis, A. I., & Roumeliotis, S. I. (2007). **A Multi-State Constraint Kalman Filter for Vision-aided Inertial Navigation**. ICRA 2007. — MSCKF，视觉辅助 IMU 融合
- [6] Leutenegger, S., et al. (2015). **Keyframe-Based Visual-Inertial Odometry Using Nonlinear Optimization**. IJRR 34(3). — OKVIS，非线性优化 VIO

### 控制理论
- [7] Lee, T., et al. (2010). **Geometric Tracking Control of a Quadrotor UAV on SE(3)**. IEEE CDC 2010. — 几何控制，PX4 位置控制理论基础
- [8] Mellinger, D., & Kumar, V. (2011). **Minimum Snap Trajectory Generation and Control for Quadrotors**. ICRA 2011. — 最小 snap 轨迹，PX4 任务执行参考
- [9] Mueller, M. W., & D'Andrea, R. (2013). **A Model Predictive Controller for Quadrotor State Interception**. ECC 2013. — MPC 控制四旋翼

### 精准降落/视觉辅助
- [10] Falanga, D., et al. (2017). **Aggressive Quadrotor Flight through Narrow Gaps with Onboard Sensing and Computing Using Active Vision**. ICRA 2017. — ETH 高速飞行，PX4+视觉感知
- [11] Pestana, J., et al. (2014). **Vision-Based Aerial Localization and Tracking for UAV Control**. ICRA 2014. — 视觉辅助 UAV 控制
- [12] Olson, E. (2011). **AprilTag: A Robust and Flexible Visual Fiducial System**. ICRA 2011. — AprilTag，精准降落视觉基准
- [13] Garrido-Jurado, S., et al. (2014). **Automatic Generation and Detection of Highly Reliable Fiducial Markers under Occlusion**. Pattern Recognition 2014. — ArUco 标记检测，[[topics/topic-precision-localization]] 核心

### 强化学习控制
- [14] Koch, W., et al. (2019). **Reinforcement Learning for UAV Attitude Control**. ACM THRI 2019. — RL 飞控，PX4 替代控制器
- [15] Kaufmann, E., et al. (2023). **Champion-Level Drone Racing Using Deep Reinforcement Learning**. Nature 2023. — RL 无人机竞速，世界冠军级别

## 变更记录
- 2026-06-27: 初始创建，知识库初始化
- 2026-06-27: 大规模扩写，补充15篇论文引用、完整 ROS2 Offboard 代码、EKF2 参数表、架构图
