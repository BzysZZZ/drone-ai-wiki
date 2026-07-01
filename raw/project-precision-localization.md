# 项目资料：无人机精准定位/精准降落（完整版）

> **来源类型**: 技术调研 + 官方文档 + 开源项目分析
> **采集日期**: 2026-06-27
> **项目背景**: 基于 ArUco 视觉标记 + PX4 飞控 + ROS2 的无人机自主精准降落系统

---

## 项目概述

传统 GPS 定位精度仅 3-5m，无法满足精准降落（如充电坪、移动平台着陆）需求。本系统融合 **RTK 厘米级定位 + 视觉 ArUco 标记 + PX4 精准降落模式 + ROS2/MAVROS 通信**，实现 10cm 级自主降落。

---

## 系统架构

```
┌────────────────────────────────────────────┐
│                    机载端 (Onboard)          │
│                                            │
│  ┌──────────┐   ┌──────────┐  ┌─────────┐ │
│  │ 下视相机  │   │ RTK GPS  │  │  IMU    │ │
│  │ (USB/CSI)│   │  (cm级)  │  │         │ │
│  └────┬─────┘   └────┬─────┘  └────┬────┘ │
│       ▼               ▼             ▼      │
│  ┌──────────────────────────────────────┐  │
│  │          ROS2 (机载计算机)             │  │
│  │  ┌─────────┐  ┌──────────────┐      │  │
│  │  │ ArUco   │  │ MAVROS 桥接   │      │  │
│  │  │ 检测节点 │  │ (与PX4通信)   │      │  │
│  │  └────┬────┘  └──────┬───────┘      │  │
│  │       ▼               ▼              │  │
│  │  ┌───────────────────────────┐       │  │
│  │  │   精准降落控制节点          │       │  │
│  │  │  - solvePnP 位姿估计      │       │  │
│  │  │  - PID 位置控制器         │       │  │
│  │  │  - 螺旋搜索路径规划      │        │  │
│  │  └───────────────────────────┘       │  │
│  └──────────────────────────────────────┘  │
│       │                                     │
│       ▼ MAVLink (UART/USB)                  │
│  ┌──────────────────────────────────────┐  │
│  │           PX4 飞控                    │  │
│  │  - Precision Land 模式               │  │
│  │  - EKF2 融合 (视觉+GPS+IMU)          │  │
│  │  - 位置/速度/姿态控制                │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
       │
       │ 降落
       ▼
┌──────────────────┐
│  ArUco 标记 (地面) │
│  已知尺寸 & 世界坐标│
└──────────────────┘
```

---

## 三阶段降落策略（PX4 Precision Land）

PX4 精准降落分为三个阶段：

```
Phase 1: 水平逼近 (Horizontal Approach)
  ├─ 高度保持，水平靠近目标上方
  ├─ 条件: 相对位置 < PLD_HACC_RAD (默认 2.0m)
  └─ 丢失目标 → 搜索/正常降落

Phase 2: 目标上空下降 (Descent over Target)
  ├─ 保持目标居中，垂直下降
  ├─ 条件: 高度 > PLD_FAPPR_ALT (默认 0.7m)
  └─ 丢失目标 → 搜索/正常降落

Phase 3: 最后逼近 (Final Approach)
  ├─ 近地面 (高度 < PLD_FAPPR_ALT)
  ├─ 直接下降，不中断
  └─ 触地检测 → 锁定电机
```

### PX4 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| PLD_SRCH_ALT | 10m | 搜索阶段高度 |
| PLD_SRCH_TOUT | 30s | 搜索超时时间 |
| PLD_HACC_RAD | 2.0m | 水平逼近完成半径 |
| PLD_FAPPR_ALT | 0.7m | 最后逼近起始高度 |
| PLD_BTOUT | 5.0s | 目标丢失容忍时间 |
| PLD_MAX_SRCH | 3 | 最大搜索次数 |
| PLD_YAW_EN | 0 | 是否跟随目标偏航角 |

---

## 核心代码实现

### 1. ArUco 标记检测 + solvePnP 位姿估计

```python
import cv2
import numpy as np

class ArucoDetector:
    """ArUco 标记检测 + 6-DOF 位姿估计"""
    def __init__(self, camera_matrix, dist_coeffs, marker_length=0.2):
        """
        camera_matrix: 相机内参 (3×3)
        dist_coeffs: 畸变系数
        marker_length: ArUco 标记实际边长 (米), 如 0.2m = 20cm
        """
        self.K = camera_matrix
        self.D = dist_coeffs
        self.marker_length = marker_length

        # ArUco 字典 (DICT_4X4_50 ~ DICT_7X7_1000)
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
        self.params = cv2.aruco.DetectorParameters()

        # 标记3D角点 (以标记中心为原点)
        half = marker_length / 2
        self.obj_points = np.array([
            [-half,  half, 0],  # 左上
            [ half,  half, 0],  # 右上
            [ half, -half, 0],  # 右下
            [-half, -half, 0],  # 左下
        ], dtype=np.float32)

    def detect(self, image):
        """返回: (tvec, rvec) 相机坐标系下标记的位置和姿态"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(
            gray, self.dictionary, parameters=self.params
        )

        if ids is None:
            return None, None

        # solvePnP 计算位姿
        for corner_set in corners:
            ret, rvec, tvec = cv2.solvePnP(
                self.obj_points, corner_set,
                self.K, self.D,
                flags=cv2.SOLVEPNP_IPPE_SQUARE  # 针对平面标记优化
            )
            if ret:
                # tvec: (3,1) 平移向量 [x, y, z] (米)
                # rvec: (3,1) 旋转向量 → Rodrigues 转为旋转矩阵
                return tvec, rvec
        return None, None

    def get_landing_target(self, image, drone_altitude):
        """
        返回降落目标位置 (NED坐标系, 前-右-下)
        x: 前向偏移 (北)
        y: 右侧偏移 (东)
        z: 当前高度 (下)
        """
        tvec, rvec = self.detect(image)
        if tvec is None:
            return None

        # tvec = [x, y, z] 其中:
        # x → 水平方向 (相机坐标系)
        # y → 垂直方向
        # z → 前方距离

        # 转换为无人机 NED 坐标系
        # 下视相机: 相机前=无人机前, 相机右=无人机右
        ned_x = tvec[2][0]  # 相机前方 → 无人机前方
        ned_y = tvec[0][0]  # 相机右方 → 无人机右方
        ned_z = -drone_altitude  # 负高度表示下方

        return np.array([ned_x, ned_y, ned_z])
```

### 2. ROS2 精准降落控制节点

```python
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from px4_msgs.msg import VehicleCommand, VehicleLocalPosition
import numpy as np

class PrecisionLandingNode(Node):
    def __init__(self):
        super().__init__('precision_landing')

        # ArUco 检测器
        self.detector = ArucoDetector(
            camera_matrix=np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]]),
            dist_coeffs=np.zeros(5),
            marker_length=0.15  # 15cm 标记
        )

        # PID 控制器
        self.Kp = np.array([0.5, 0.5, 0.3])
        self.Ki = np.array([0.02, 0.02, 0.01])
        self.Kd = np.array([0.1, 0.1, 0.05])
        self.integral = np.zeros(3)
        self.prev_error = np.zeros(3)

        # 状态机
        self.state = "SEARCH"  # SEARCH → APPROACH → DESCEND → LANDED
        self.target_found = False

        # ROS2 发布/订阅
        self.cmd_pub = self.create_publisher(
            VehicleCommand, '/fmu/in/vehicle_command', 10)
        self.local_pos_sub = self.create_subscription(
            VehicleLocalPosition, '/fmu/out/vehicle_local_position',
            self.pos_callback, 10)

        # 相机图像订阅（仿真/实机）
        self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 10)

        self.timer = self.create_timer(0.05, self.control_loop)  # 20Hz

    def image_callback(self, msg):
        """处理相机图像"""
        # ROS Image → OpenCV
        cv_image = self.bridge.imgmsg_to_cv2(msg)
        target = self.detector.get_landing_target(
            cv_image, self.current_altitude)
        if target is not None:
            self.target_pos = target
            self.target_found = True
        else:
            self.target_found = False

    def control_loop(self):
        """20Hz 控制循环"""
        if self.state == "SEARCH":
            self.search_pattern()
        elif self.state == "APPROACH":
            self.approach_target()
        elif self.state == "DESCEND":
            self.descend()
        elif self.state == "LANDED":
            self.disarm()

    def search_pattern(self):
        """螺旋搜索模式"""
        # 逐渐扩大的螺旋半径
        radius = self.search_step * 0.5
        angle = self.search_step * 0.3
        x_cmd = radius * np.cos(angle)
        y_cmd = radius * np.sin(angle)
        self.send_velocity_command(x_cmd, y_cmd, 0)
        self.search_step += 1

        if self.target_found:
            self.state = "APPROACH"
            self.search_step = 0

    def approach_target(self):
        """PID 水平逼近"""
        if not self.target_found:
            self.state = "SEARCH"
            return

        error = self.target_pos

        # PID 计算
        self.integral += error * 0.05
        derivative = (error - self.prev_error) / 0.05
        cmd = self.Kp * error + self.Ki * self.integral + self.Kd * derivative

        # 限幅
        cmd = np.clip(cmd, -2.0, 2.0)

        self.send_velocity_command(cmd[0], cmd[1], 0)
        self.prev_error = error

        # 水平误差 < 0.1m → 进入下降
        if np.linalg.norm(error[:2]) < 0.1:
            self.state = "DESCEND"

    def descend(self):
        """PID 下降"""
        error = self.target_pos
        cmd = self.Kp * error + self.Ki * self.integral

        # 增加下降速度
        cmd[2] = -0.5  # 0.5m/s 下降

        self.send_velocity_command(cmd[0], cmd[1], cmd[2])

        # 触地检测 (高度 < 0.2m)
        if self.current_altitude < 0.2:
            self.state = "LANDED"

    def send_velocity_command(self, vx, vy, vz):
        """发送速度指令到 PX4"""
        cmd = VehicleCommand()
        cmd.command = VehicleCommand.VEHICLE_CMD_DO_SET_VELOCITY
        cmd.param1 = float(vx)
        cmd.param2 = float(vy)
        cmd.param3 = float(vz)
        cmd.target_system = 1
        cmd.target_component = 1
        self.cmd_pub.publish(cmd)
```

### 3. 仿真启动 (Gazebo + PX4 SITL)

```bash
# 终端1: 启动 PX4 SITL + Gazebo (下视相机 + ArUco 地面标记)
make px4_sitl gz_x500_mono_cam_down_aruco

# 终端2: MicroXRCEAgent (PX4 ↔ ROS2 通信)
MicroXRCEAgent udp4 -p 8888

# 终端3: ros_gz_bridge (Gazebo 相机 → ROS2 Image topic)
ros2 run ros_gz_bridge parameter_bridge \
    /world/aruco/model/x500_mono_cam_down_0/link/camera_link/sensor/imager/image@sensor_msgs/msg/Image@gz.msgs.Image

ros2 run ros_gz_bridge parameter_bridge \
    /world/aruco/model/x500_mono_cam_down_0/link/camera_link/sensor/imager/camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo

# 终端4: 启动精准降落节点
ros2 run precision_landing landing_node

# 终端5: QGroundControl 监控
./QGroundControl.AppImage
```

---

## 传感器融合策略

| 高度区间 | 主要传感器 | 融合方案 |
|---------|-----------|---------|
| > 20m | RTK GPS + IMU | EKF2 |
| 5~20m | RTK GPS + ArUco 视觉 | 视觉辅助修正 |
| 1~5m | ArUco 视觉为主 | 纯视觉定位 |
| < 1m | ArUco + 超声波/激光 | 最终触地 |

---

## 抗干扰策略

| 问题 | 方案 |
|------|------|
| ArUco 标记被遮挡 | 多标记冗余 (6个以上)，EKF 预测维持 |
| 光照剧烈变化 | 自适应阈值 + 直方图均衡化 |
| 运动模糊 | 低曝光 (1/500s) + 短焦距 |
| 标记尺寸不匹配 | 多尺度检测 (标记金字塔) |
| GPS 信号弱 | 视觉惯性里程计 (VIO) 补偿 |
| 风吹偏移 | 增大 PID 的 D 项 + 前馈补偿 |

---

## 性能指标

| 指标 | 目标值 |
|------|--------|
| GPS+RTK 静态定位精度 | < 5cm (CEP) |
| 视觉定位精度 (5m高) | < 3cm |
| 最终降落误差 (CEP50) | < 10cm |
| ArUco 检测距离 | > 15m (20cm标记) |
| 检测帧率 | > 30 FPS |
| 降落成功率 | > 98% |

---

## 开源项目参考

| 项目 | 技术栈 | 说明 |
|------|--------|------|
| [precision_landing](https://github.com/SpaceMaster85/precision_landing) | ROS2 + PX4 + ArUco | 螺旋搜索 + PID 控制 |
| [PX4 Precision Land](https://docs.px4.io/main/en/advanced_features/precland) | PX4 官方 | 内置精准降落模式 |
| [ARK Precision Landing](https://docs.arkelectron.com/tutorials/ros2-and-px4/mastering-precision-landing-with-px4-and-ros2) | ROS2 + PX4 | 完整教程 |
| [IR-Lock](https://irlock.com) | PX4 + IR 信标 | 红外信标精准降落 |

---

## 简历包装核心关键词

- 多传感器融合定位: RTK GPS (cm级) + 视觉 ArUco 标记 + IMU
- solvePnP 6-DOF 位姿估计，相机坐标系→NED坐标系转换
- PX4 Precision Land 三阶段控制：水平逼近→目标下降→最后逼近
- ROS2 + MAVROS/px4_ros2 实时通信，20Hz 控制回路
- PID 控制器 (含抗积分饱和 + 前馈补偿)，抗风扰动
- 螺旋搜索策略 + 目标丢失 EKF 预测
- Gazebo SITL 仿真验证 + 实机部署
- 最终降落误差 CEP50 【填写值】cm，成功率 【填写值】%
