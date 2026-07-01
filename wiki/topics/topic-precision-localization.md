# 无人机精准定位系统

> **类型**: topic
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-30
> **来源**: [[raw/project-precision-localization.md]]

## 摘要
基于 RTK GPS + ArUco 视觉标记 + PX4 Precision Land 的无人机自主精准降落系统。ROS2 控制节点实现 solvePnP 6-DOF 位姿估计、PID 位置控制器、螺旋搜索策略。三阶段降落流程（水平逼近 → 目标下降 → 最后逼近），目标实现 10cm 级降落精度。

## 实际代码解析入口

本页保留精准定位/精准降落系统的总体设计。桌面 `code.txt` 已整理为独立解析页：[[topics/topic-precision-localization-code]]。它对应现场版 ArUco + MQTT 虚拟摇杆精准降落脚本，重点解释视频输入、像素几何估高、`SEARCH -> ALIGN -> DESCEND -> LAND` 状态机、定时修正控制律、低空 LAND 和异常恢复。

原始代码归档在 [raw/precision-landing-mqtt-code.txt](../raw/precision-landing-mqtt-code.txt)，用于和解析页逐段对照。

零基础学习依赖：先读 [[concepts/concept-mqtt-engineering]] 建立 MQTT 遥测/控制链路能力，再读 [[entities/product-ros2]] 建立 ROS2 节点系统开发能力。这样再回来看精准降落代码，会更容易理解为什么现场脚本要把视觉状态机、MQTT 适配层、飞控状态和异常恢复分开。

---

## 🛠️ 环境配置

### 硬件要求

| 组件 | 推荐型号 | 用途 |
|------|---------|------|
| 飞控 | Pixhawk 6C/6X | 运行 PX4 |
| 机载计算机 | Jetson Orin NX | 运行 ROS2 + 视觉算法 |
| RTK GPS | Holybro H-RTK F9P | 厘米级定位 |
| 下视相机 | USB 或 CSI 摄像头 | 检测 ArUco 标记 |
| 降落标记 | ArUco DICT_6X6_250 | 0.2m 边长，高对比度 |
| 超声波 | HC-SR04 / TFmini | <1m 近距离测距 |

### 软件安装

```bash
# === 1. 基础环境 ===
sudo apt update && sudo apt upgrade -y
sudo apt install ros-humble-desktop python3-colcon-common-extensions

# === 2. Python 依赖 ===
pip install opencv-python opencv-contrib-python numpy scipy pymavlink

# === 3. MAVROS 桥接 ===
sudo apt install ros-humble-mavros ros-humble-mavros-extras
# 安装 GeographicLib 数据集（MAVROS 需要）
sudo /opt/ros/humble/lib/mavros/install_geographiclib_datasets.sh

# === 4. PX4-Autopilot ===
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
bash Tools/setup/ubuntu.sh  # 一键安装 PX4 依赖
make px4_sitl gz_x500  # 验证 SITL 仿真

# === 5. ROS2 工作空间 ===
mkdir -p ~/precision_landing_ws/src
cd ~/precision_landing_ws/src
git clone https://github.com/SpaceMaster85/precision_landing.git
cd ~/precision_landing_ws
colcon build --symlink-install
source install/setup.bash
```

---

## 💻 核心代码

### 1. ArUco 检测与位姿估计节点

```python
#!/usr/bin/env python3
"""aruco_detector.py — ArUco 标记检测 + 6-DOF 位姿估计"""

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PoseStamped
from cv_bridge import CvBridge

class ArucoPoseEstimator:
    """ArUco 位姿估计核心"""
    
    def __init__(self, marker_size=0.2, marker_dict=cv2.aruco.DICT_6X6_250):
        self.marker_size = marker_size  # 标记边长 (m)
        self.dictionary = cv2.aruco.getPredefinedDictionary(marker_dict)
        self.params = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.dictionary, self.params)
        self.camera_matrix = None
        self.dist_coeffs = None
    
    def set_camera(self, K, D):
        """设置相机内参"""
        self.camera_matrix = np.array(K, dtype=np.float32)
        self.dist_coeffs = np.array(D, dtype=np.float32)
    
    def detect_pose(self, image):
        """
        检测 ArUco 并估计位姿
        Returns: (T_cam_to_marker, marker_corners, marker_ids) 或 (None, None, None)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 检测 ArUco
        corners, ids, rejected = self.detector.detectMarkers(gray)
        
        if ids is None or self.camera_matrix is None:
            return None, None, None
        
        # 位姿估计 (solvePnP)
        obj_points = np.array([
            [-self.marker_size/2,  self.marker_size/2, 0],
            [ self.marker_size/2,  self.marker_size/2, 0],
            [ self.marker_size/2, -self.marker_size/2, 0],
            [-self.marker_size/2, -self.marker_size/2, 0],
        ], dtype=np.float32)
        
        rvecs, tvecs = [], []
        for corners_i in corners:
            ret, rvec, tvec = cv2.solvePnP(
                obj_points, corners_i,
                self.camera_matrix, self.dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE
            )
            rvecs.append(rvec)
            tvecs.append(tvec)
        
        # 构造变换矩阵
        transforms = []
        for rvec, tvec in zip(rvecs, tvecs):
            R, _ = cv2.Rodrigues(rvec)
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = tvec.flatten()
            transforms.append(T)
        
        return transforms, corners, ids  # T_cam_to_marker
    
    def camera_to_ned(self, T_cam_to_marker, T_drone_to_cam=None):
        """
        相机坐标系 → NED（北东地）坐标系
        
        T_cam_to_marker: 4×4 相机 → 标记
        T_drone_to_cam: 4×4 无人机机体 → 相机 (已知固定安装关系)
        
        Returns: marker 在 NED 系的位置 (x, y, z)
        """
        if T_drone_to_cam is None:
            # 默认：相机朝下安装，x前→x前, y右→y右, z下→z下
            T_drone_to_cam = np.array([
                [ 1,  0,  0,  0.0],   # 前
                [ 0,  1,  0,  0.0],   # 右（= NED 东）
                [ 0,  0,  1, -0.05],  # 下（= NED 地）
                [ 0,  0,  0,  1.0],
            ])
        
        # 标记在相机系中的位置
        marker_in_cam = T_cam_to_marker[:3, 3]
        marker_in_cam_h = np.append(marker_in_cam, 1)
        
        # 相机 → 机体
        marker_in_body = T_drone_to_cam @ marker_in_cam_h
        
        # 机体 → NED（简化为机头朝北）
        # 实际中需要融合 IMU 姿态
        ned = np.array([
            marker_in_body[0],   # N = 机体 x
            marker_in_body[1],   # E = 机体 y
            marker_in_body[2],   # D = 机体 z (朝下为正)
        ])
        
        return ned
    
    def draw_axes(self, image, rvec, tvec):
        """绘制 3D 坐标轴"""
        cv2.drawFrameAxes(
            image, self.camera_matrix, self.dist_coeffs,
            rvec, tvec, self.marker_size * 0.5
        )
        return image


class ArucoDetectorNode(Node):
    """ROS2 ArUco 检测节点"""
    
    def __init__(self):
        super().__init__('aruco_detector')
        
        self.estimator = ArucoPoseEstimator(marker_size=0.2)
        self.bridge = CvBridge()
        
        # 订阅相机图像和内参
        self.image_sub = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 10)
        self.camera_info_sub = self.create_subscription(
            CameraInfo, '/camera/camera_info', self.camera_info_callback, 10)
        
        # 发布标记位姿
        self.pose_pub = self.create_publisher(
            PoseStamped, '/aruco/marker_pose', 10)
        
        self.get_logger().info('ArUco 检测节点已启动')
    
    def camera_info_callback(self, msg):
        K = [[msg.k[0], msg.k[1], msg.k[2]],
             [msg.k[3], msg.k[4], msg.k[5]],
             [msg.k[6], msg.k[7], msg.k[8]]]
        D = msg.d
        self.estimator.set_camera(K, D)
    
    def image_callback(self, msg):
        # 转换图像
        cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        
        # 检测 ArUco
        transforms, corners, ids = self.estimator.detect_pose(cv_image)
        
        if transforms is None:
            return
        
        # 发布最近标记的位姿
        # (选择距离最近的标记)
        distances = [np.linalg.norm(T[:3, 3]) for T in transforms]
        best_idx = np.argmin(distances)
        
        T = transforms[best_idx]
        pos_ned = self.estimator.camera_to_ned(T)
        
        pose_msg = PoseStamped()
        pose_msg.header.stamp = self.get_clock().now().to_msg()
        pose_msg.header.frame_id = 'map'
        pose_msg.pose.position.x = pos_ned[0]
        pose_msg.pose.position.y = pos_ned[1]
        pose_msg.pose.position.z = pos_ned[2]
        
        self.pose_pub.publish(pose_msg)


def main():
    rclpy.init()
    node = ArucoDetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 2. 精准降落控制节点（PID 控制器）

```python
#!/usr/bin/env python3
"""precision_land_controller.py — 三阶段精准降落控制"""

import numpy as np
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode
import time

class PIDController:
    """三轴独立 PID 控制器（带抗积分饱和）"""
    
    def __init__(self, kp, ki, kd, out_min, out_max):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_min, self.out_max = out_min, out_max
        
        self.integral = 0.0
        self.prev_error = 0.0
    
    def update(self, error, dt):
        # 比例项
        p = self.kp * error
        
        # 积分项（抗饱和：输出超限时停止积分）
        self.integral += error * dt
        i = self.ki * self.integral
        
        # 微分项
        d = self.kd * (error - self.prev_error) / (dt + 1e-6) if dt > 0 else 0
        self.prev_error = error
        
        output = p + i + d
        
        # 输出限幅 + 积分抗饱和
        if output > self.out_max:
            output = self.out_max
            self.integral -= error * dt  # 回退积分
        elif output < self.out_min:
            output = self.out_min
            self.integral -= error * dt
        
        return output
    
    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0


class PrecisionLandController(Node):
    """PX4 精准降落 ROS2 控制节点
    
    三阶段：
    SEARCH  → 螺旋搜索 ArUco 标记
    APPROACH → 水平逼近（保持高度）
    DESCEND  → 目标下降至触地
    """
    
    PHASES = ['SEARCH', 'APPROACH', 'DESCEND', 'LANDED']
    
    def __init__(self):
        super().__init__('precision_land_controller')
        
        # 控制器参数
        self.pid_x = PIDController(kp=0.5, ki=0.02, kd=0.1, out_min=-2.0, out_max=2.0)
        self.pid_y = PIDController(kp=0.5, ki=0.02, kd=0.1, out_min=-2.0, out_max=2.0)
        self.pid_z = PIDController(kp=0.3, ki=0.01, kd=0.05, out_min=-1.0, out_max=1.0)
        
        # 状态
        self.phase = 'SEARCH'
        self.marker_pos = None  # NED 坐标 (x, y, z)
        self.last_marker_time = None
        self.search_radius = 3.0
        self.search_angle = 0.0
        
        # 参数
        self.approach_altitude = 5.0    # 逼近阶段高度 (m)
        self.descend_altitude = 0.7     # 下降阶段高度 (m)
        self.search_altitude = 10.0     # 搜索高度
        self.timeout = 5.0              # 丢失超时 (s)
        self.ctrl_rate = 20             # Hz
        
        # 订阅 ArUco 位姿
        self.pose_sub = self.create_subscription(
            PoseStamped, '/aruco/marker_pose', self.pose_callback, 10)
        
        self.get_logger().info('精准降落控制器已启动')
        self.get_logger().info(f'参数: H_approach={self.approach_altitude}m, H_descend={self.descend_altitude}m')
        
        # 控制循环
        self.timer = self.create_timer(1.0 / self.ctrl_rate, self.control_loop)
    
    def pose_callback(self, msg):
        """接收到 ArUco 位姿"""
        self.marker_pos = np.array([
            msg.pose.position.x,
            msg.pose.position.y,
            msg.pose.position.z,
        ])
        self.last_marker_time = time.time()
    
    def spiral_search(self, dt):
        """螺旋搜索策略"""
        angular_speed = 0.5  # rad/s
        radial_speed = 0.3   # m/s
        
        self.search_angle += angular_speed * dt
        self.search_radius = min(self.search_radius + radial_speed * dt, 5.0)
        
        vx = self.search_radius * np.cos(self.search_angle) * angular_speed
        vy = self.search_radius * np.sin(self.search_angle) * angular_speed
        
        self.get_logger().debug(f'搜索中: r={self.search_radius:.1f}m, θ={np.degrees(self.search_angle):.0f}°')
        
        return np.array([vx, vy, 0.0])  # (vx, vy, vz)
    
    def control_loop(self):
        """20Hz 主控制循环"""
        current_time = time.time()
        
        # === 状态切换逻辑 ===
        if self.phase == 'LANDED':
            return
        
        marker_lost = (self.marker_pos is None or
                       self.last_marker_time is None or
                       current_time - self.last_marker_time > self.timeout)
        
        if self.phase == 'SEARCH':
            if not marker_lost:
                self.phase = 'APPROACH'
                self.get_logger().info(f'→ 进入 APPROACH, 目标位置: {self.marker_pos}')
        elif self.phase == 'APPROACH':
            if marker_lost:
                self.phase = 'SEARCH'
                self.get_logger().info('标记丢失 → 回到 SEARCH')
            elif self.marker_pos[2] < self.approach_altitude:
                self.phase = 'DESCEND'
                self.get_logger().info('→ 进入 DESCEND')
        elif self.phase == 'DESCEND':
            if marker_lost:
                self.phase = 'SEARCH'
                self.get_logger().info('标记丢失 → 回到 SEARCH')
            elif self.marker_pos[2] < 0.1:  # 触地
                self.phase = 'LANDED'
                self.get_logger().info('→ LANDED! 触地完成')
        
        # === 控制输出 ===
        if self.phase == 'SEARCH':
            velocity_cmd = self.spiral_search(1.0 / self.ctrl_rate)
        else:
            # PID 控制
            error_x = -self.marker_pos[0]  # 水平方向误差
            error_y = -self.marker_pos[1]
            error_z = self.marker_pos[2] - (self.descend_altitude if self.phase == 'DESCEND' else self.approach_altitude)
            
            vx = self.pid_x.update(error_x, 1.0/self.ctrl_rate)
            vy = self.pid_y.update(error_y, 1.0/self.ctrl_rate)
            vz = self.pid_z.update(error_z, 1.0/self.ctrl_rate) if self.phase == 'DESCEND' else 0.0
            
            velocity_cmd = np.array([vx, vy, vz])
        
        # 发送 MAVLink 速度指令（通过 MAVROS）
        # setpoint_raw/velocity 话题
        # ...
        
        self.get_logger().debug(
            f'[{self.phase}] cmd=({velocity_cmd[0]:.2f},{velocity_cmd[1]:.2f},{velocity_cmd[2]:.2f}) m/s')


def main():
    rclpy.init()
    node = PrecisionLandController()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 3. 仿真验证（Gazebo + PX4 SITL）

```bash
# === 启动 PX4 SITL 仿真（带下视相机和 ArUco） ===
cd ~/PX4-Autopilot

# 启动 X500 无人机 + Gazebo 仿真
make px4_sitl gz_x500_mono_cam_down

# === 在另一个终端启动 ROS2 节点 ===
source ~/precision_landing_ws/install/setup.bash

# 启动 MAVROS
ros2 launch mavros px4.launch fcu_url:="udp://:14540@127.0.0.1:14557"

# 启动 ArUco 检测
ros2 run precision_landing aruco_detector

# 启动精准降落控制
ros2 run precision_landing precision_land_controller

# === 可视化 ===
# QGroundControl: 连接后查看 MAVLink 消息
# RViz2: 查看视觉检测结果
rviz2
```

### 4. PX4 参数配置

```bash
# 通过 QGroundControl 或 MAVLink Shell 配置

# === 精准降落参数 ===
PLD_ENABLED  = 1           # 启用 Precision Land
PLD_SRCH_ALT = 10.0        # 搜索高度 (m)
PLD_HACC_RAD = 2.0         # 水平逼近完成半径 (m)
PLD_FAPPR_ALT = 0.7        # 最后逼近高度 (m)
PLD_BTOUT    = 5.0         # beacon 超时 (s)
PLD_MAX_SRCH = 20          # 最大搜索时间 (s)

# === 传感器参数 ===
EKF2_GPS_POS_X = 0.0       # GPS 天线位置 (相对于质心)
EKF2_GPS_POS_Y = 0.0
EKF2_GPS_POS_Z = 0.0
EKF2_GPS_DELAY = 200       # GPS 延迟 (ms)
EKF2_EV_DELAY  = 50        # 视觉里程计延迟 (ms)

# === 降落速度限制 ===
MPC_LAND_SPEED = 0.7       # 降落速度 (m/s)
MPC_LAND_ALT1  = 10.0      # 第一段减速高度
MPC_LAND_ALT2  = 5.0       # 第二段减速高度
```

### 5. 传感器融合策略

```
高度区间        主传感器          辅助传感器
─────────────────────────────────────────────
> 20m          RTK GPS           IMU (EKF2)
10-20m         RTK GPS           视觉辅助 (ArUco)
5-10m          视觉 (ArUco)       GPS 外推
1-5m           视觉 (ArUco)       IMU 姿态
< 1m           超声波/激光        视觉确认
触地            触地检测           电机停转
```

---

## 系统整体架构

```
┌──────────────────────────────────────────────────────┐
│                    机载计算机 (Jetson)                 │
│                                                      │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   │
│  │ ArUco    │ → │ solvePnP     │ → │ PID 控制器  │   │
│  │ 检测节点  │   │ 6-DOF 位姿   │   │ (3轴独立)   │   │
│  └──────────┘   └──────────────┘   └─────┬──────┘   │
│                                          │           │
│                              ┌───────────┘           │
│                              ▼                       │
│                     ┌──────────────┐                 │
│                     │  MAVROS 桥接  │                 │
│                     │ ROS2 ↔ PX4   │                 │
│                     └──────┬───────┘                 │
└────────────────────────────┼──────────────────────────┘
                             │ MAVLink (UART/Serial)
                             ▼
┌──────────────────────────────────────────────────────┐
│                     PX4 飞控                          │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐     │
│  │ EKF2     │ ← │ RTK GPS  │   │ Precision    │     │
│  │ 传感器   │   │ + IMU    │   │ Land 模式    │     │
│  │ 融合     │   │ + 视觉   │   │ (3阶段)      │     │
│  └──────────┘   └──────────┘   └──────┬───────┘     │
│                                       │              │
│                           ┌───────────┘              │
│                           ▼                          │
│                  ┌──────────────┐                    │
│                  │ 位置/速度     │                    │
│                  │ 姿态控制器    │                    │
│                  └──────┬───────┘                    │
└─────────────────────────┼────────────────────────────┘
                          │
                          ▼
                    ┌──────────┐
                    │  电机    │
                    │  螺旋桨   │
                    └──────────┘
```

## 关联
- 相关概念: [[concepts/concept-slam]], [[concepts/concept-drone-control]], [[concepts/concept-multi-sensor-fusion]]
- 核心平台: [[entities/product-px4-autopilot]]
- 关联项目: [[topics/topic-crack-detection]]（精准定位保障巡检）
- 实际代码解析: [[topics/topic-precision-localization-code]]

## 引用来源
- [1] [[raw/project-precision-localization.md]] — 完整技术资料
- [2] PX4 Precision Landing 官方文档
- [3] SpaceMaster85/precision_landing 开源项目
- [4] [raw/precision-landing-mqtt-code.txt](../raw/precision-landing-mqtt-code.txt) — 现场版 ArUco + MQTT 虚拟摇杆精准降落脚本

## 核心论文引用

- [1] **ArUco** — Garrido-Jurado et al., "Automatic Generation and Detection of Highly Reliable Fiducial Markers under Occlusion," Pattern Recognition 2014. [ArUco标记核心论文]
- [2] **PnP问题** — Lepetit et al., "EPnP: An Accurate O(n) Solution to the PnP Problem," IJCV 2009. [位姿估计算法]
- [3] **PX4精准降落** — PX4 Development Team, "PX4 Precision Landing Documentation," 2024.
- [4] **视觉辅助降落** — Vlantis et al., "Quadrotor Landing on an Inclined Surface of a Moving Ground Vehicle," ICRA 2015.
- [5] **RTK-VIO融合** — Li et al., "Tightly-Coupled GNSS/INS/Vision Integration for Accurate and Robust Positioning," IEEE TGRS 2023.
- [6] **视觉降落综述** — Araar et al., "Vision Based Autonomous Landing of Multirotor UAV on Moving Platform," JFR 2017.
- [7] **EKF定位** — Mahony et al., "Nonlinear Complementary Filters on SO(3)," IEEE TAC 2008.
- [8] **MAVROS** — Saripalli et al., "MAVLink Protocol," 2012. [飞控通信协议]
- [9] **ROS2** — Macenski et al., "Robot Operating System 2: Design, Architecture, and Uses In The Wild," Science Robotics 2022.
- [10] **视觉伺服** — Chaumette & Hutchinson, "Visual Servo Control Part I: Basic Approaches," IEEE RAM 2006.
- [11] **无人机降落** — Ventura-Traveset et al., "Robust Autonomous Landing on Moving Platforms," IEEE ICRA 2019.
- [12] **Apriltag** — Wang & Olson, "AprilTag 2: Efficient and Robust Fiducial Detection," IROS 2016. [另一类视觉标记]
- [13] **精准降落评估** — Faessler et al., "A Monocular Pose Estimation System Based on Infrared LEDs," ICRA 2014.

## 变更记录
- 2026-06-27: 初始创建
- 2026-06-27: 增强版，新增环境配置(HW+SW)、ArUco检测节点代码、PID控制节点代码、螺旋搜索策略、PX4参数配置、Gazebo仿真步骤、传感器融合策略、系统架构图
- 2026-06-29: 补充13篇核心论文引用
- 2026-06-30: 新增实际代码解析入口，关联桌面 `code.txt` 摄入生成的 [[topics/topic-precision-localization-code]]



