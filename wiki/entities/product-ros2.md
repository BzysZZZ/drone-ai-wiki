# ROS2 工程开发教程：从零基础到无人机节点系统

> **类型**: entity
> **创建时间**: 2026-06-30
> **最后更新**: 2026-06-30
> **标签**: #ROS2 #机器人 #无人机 #节点 #Topic #Service #Action #Launch #TF2 #工程

## 摘要

ROS2 是机器人系统的工程框架。它不是一个单纯的通信库，也不是飞控固件，而是一套把传感器、算法、控制器、可视化、日志、仿真和部署组织成“节点系统”的工具链。

这篇教程面向零经验学习者。学完后，你应该能做到：

- 解释 ROS2 中 Node、Topic、Service、Action、Parameter、Launch 的区别。
- 从零创建工作空间和 Python 包。
- 写出发布者、订阅者、服务、参数和 launch 文件。
- 用 CLI、rosbag、RViz、日志定位问题。
- 把精准降落单脚本拆成无人机工程中的 ROS2 多节点系统。

---

## 学习路线

| 阶段 | 目标 | 你要会什么 |
|------|------|------------|
| 0. 建立直觉 | 知道 ROS2 为什么存在 | 节点图、消息、分布式系统 |
| 1. 跑通环境 | 能启动官方示例 | `ros2 run`, `ros2 topic`, `ros2 node` |
| 2. 写节点 | Python 发布订阅 | `rclpy`, Publisher, Subscriber, Timer |
| 3. 写接口 | 请求、长任务、参数 | Service, Action, Parameter |
| 4. 做工程 | 多节点启动和配置 | Launch、命名空间、remap、日志 |
| 5. 做无人机系统 | 视觉、定位、控制串起来 | Camera、ArUco、TF2、rosbag、PX4 bridge |

ROS2 学习不要从“背命令”开始，而要从“节点之间怎么交换信息”开始。

---

## ROS2 解决什么问题

无人机 AI 系统通常不是一个程序能解决的。真实系统会有：

- 相机驱动
- 图像处理
- ArUco/目标检测
- 状态估计
- 路径规划
- 控制器
- 飞控桥接
- 可视化
- 日志记录
- 参数配置

如果全部写在一个 Python 文件里，开始很快，但后期会出现：

- 一个模块崩溃拖垮整个系统。
- 很难单独重放传感器数据。
- 很难替换检测算法或控制器。
- 很难查看系统当前谁在发布、谁在订阅。
- 真机调试时无法快速定位是图像、算法、控制还是飞控桥接出问题。

ROS2 的工程思路是：把系统拆成多个节点，每个节点做一件清楚的事，通过标准接口通信。

```text
camera_node
  -> /camera/image_raw
aruco_detector_node
  -> /landing/marker_pose
landing_controller_node
  -> /cmd_vel
flight_bridge_node
  -> 飞控/MQTT/MAVLink/PX4
```

---

## ROS2 图模型

### Node

Node 是一个运行中的功能单元。一个节点可以是：

- 相机驱动节点
- ArUco 检测节点
- 控制器节点
- MQTT 桥接节点
- 日志记录节点

判断一个功能是否适合做节点，可以问三个问题：

- 它能不能独立启动和停止？
- 它的输入输出是否清楚？
- 它是否值得单独调试、替换或复用？

### Topic

Topic 是连续数据流，适合“发布者不断发，订阅者不断收”。

典型 Topic：

```text
/camera/image_raw
/imu/data
/gps/fix
/landing/marker_pose
/cmd_vel
```

适合 Topic 的数据：

- 图像
- IMU
- 位姿
- 速度命令
- 目标检测结果

### Service

Service 是一次请求、一次响应，适合短时间完成的动作。

典型 Service：

```text
/landing/reset
/camera/set_exposure
/flight/set_mode
/mission/clear
```

适合 Service 的任务：

- 查询状态
- 重置模块
- 设置某个参数
- 请求一次短操作

不要用 Service 做长时间任务。长任务用 Action。

### Action

Action 适合“需要一段时间执行，并且中间有反馈，可以取消”的任务。

典型 Action：

```text
/navigate_to_pose
/takeoff
/precision_land
/scan_marker
```

Action 的特点：

- Goal：开始一个目标。
- Feedback：执行过程中的进度。
- Result：最终结果。
- Cancel：可以取消。

### Parameter

Parameter 是节点运行时可配置的参数。

例如精准降落节点可以有：

```text
marker_size: 0.2
camera_fx: 615.0
align_tolerance_m: 0.08
max_descent_speed: 0.3
control_method: velocity
```

原则：

- 会随场地、相机、飞机变化的值做成参数。
- 不要把业务状态当参数。
- 参数文件要能放进版本管理。

### Launch

Launch 是“启动系统”的入口。它负责一次启动多个节点，并传入参数、命名空间、remap、日志配置。

无人机工程不要依赖人工开十几个终端。最终应该用 launch 启动系统。

---

## 安装与环境

### 选择发行版

ROS2 有多个发行版。无人机工程建议优先选 LTS 发行版。例如 Ubuntu 24.04 常用 ROS2 Jazzy。具体安装命令以官方文档对应发行版为准。

本教程示例以 Ubuntu + ROS2 Jazzy 风格为主。

### 安装 ROS2

典型 Ubuntu 安装流程：

```bash
sudo apt update
sudo apt install -y software-properties-common curl
sudo add-apt-repository universe

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-jazzy-desktop python3-colcon-common-extensions
```

加载环境：

```bash
source /opt/ros/jazzy/setup.bash
```

建议加入 `~/.bashrc`：

```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```

验证：

```bash
ros2 --help
ros2 run demo_nodes_cpp talker
```

另开终端：

```bash
ros2 run demo_nodes_py listener
```

如果 listener 能看到消息，说明基础环境可用。

---

## 工作空间与包

### 工作空间

ROS2 工作空间是放源码、编译产物和安装产物的目录。

```bash
mkdir -p ~/drone_ws/src
cd ~/drone_ws
colcon build
source install/setup.bash
```

目录结构：

```text
drone_ws/
  src/       # 源码包
  build/     # 构建中间产物
  install/   # 安装后的可运行环境
  log/       # 构建日志
```

每次新增包或重新编译后，要重新：

```bash
source install/setup.bash
```

### 创建 Python 包

```bash
cd ~/drone_ws/src
ros2 pkg create drone_basics --build-type ament_python --dependencies rclpy std_msgs geometry_msgs
```

生成结构大致是：

```text
drone_basics/
  package.xml
  setup.py
  resource/drone_basics
  drone_basics/
    __init__.py
```

`package.xml` 描述依赖和元数据，`setup.py` 描述 Python 可执行入口。

---

## Python 发布订阅

### 发布者

创建 `drone_basics/osd_publisher.py`：

```python
import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class OsdPublisher(Node):
    def __init__(self):
        super().__init__("osd_publisher")
        self.publisher = self.create_publisher(String, "/drone/osd", 10)
        self.timer = self.create_timer(1.0, self.publish_osd)
        self.height = 10.0

    def publish_osd(self):
        self.height -= 0.1
        msg = String()
        msg.data = json.dumps({
            "timestamp": time.time(),
            "height": round(self.height, 2),
            "battery_percent": 88,
            "fly_mode": "GPS_NORMAL",
        })
        self.publisher.publish(msg)
        self.get_logger().info(f"publish {msg.data}")


def main():
    rclpy.init()
    node = OsdPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
```

### 订阅者

创建 `drone_basics/osd_subscriber.py`：

```python
import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class OsdSubscriber(Node):
    def __init__(self):
        super().__init__("osd_subscriber")
        self.subscription = self.create_subscription(
            String,
            "/drone/osd",
            self.on_osd,
            10,
        )

    def on_osd(self, msg):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning(f"bad osd json: {msg.data}")
            return

        self.get_logger().info(
            f"height={data.get('height')} battery={data.get('battery_percent')}"
        )


def main():
    rclpy.init()
    node = OsdSubscriber()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
```

### 注册入口

修改 `setup.py` 中的 `entry_points`：

```python
entry_points={
    "console_scripts": [
        "osd_publisher = drone_basics.osd_publisher:main",
        "osd_subscriber = drone_basics.osd_subscriber:main",
    ],
},
```

构建：

```bash
cd ~/drone_ws
colcon build --packages-select drone_basics
source install/setup.bash
```

运行：

```bash
ros2 run drone_basics osd_publisher
ros2 run drone_basics osd_subscriber
```

观察 Topic：

```bash
ros2 topic list
ros2 topic echo /drone/osd
ros2 topic hz /drone/osd
```

---

## Service

Service 适合短请求。下面做一个“重置降落控制器”的服务。

创建 `drone_basics/reset_service.py`：

```python
import rclpy
from rclpy.node import Node
from example_interfaces.srv import Trigger


class ResetService(Node):
    def __init__(self):
        super().__init__("reset_service")
        self.service = self.create_service(Trigger, "/landing/reset", self.on_reset)

    def on_reset(self, request, response):
        response.success = True
        response.message = "landing controller reset"
        self.get_logger().info(response.message)
        return response


def main():
    rclpy.init()
    node = ResetService()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

注册入口：

```python
"reset_service = drone_basics.reset_service:main",
```

构建后运行：

```bash
ros2 run drone_basics reset_service
ros2 service call /landing/reset example_interfaces/srv/Trigger "{}"
```

Service 的工程边界：

- 重置、查询、设置短参数适合 Service。
- “自动降落直到完成”不适合 Service，应该用 Action。

---

## Action

Action 用于长任务。精准降落、导航到目标点、自动扫描都适合 Action。

一个 `precision_land` Action 可以抽象成：

```text
Goal:
  target_marker_id
  final_height

Feedback:
  current_state
  horizontal_error
  height

Result:
  success
  message
  landing_error
```

对于初学者，先理解 Action 的使用场景，再开始写自定义 action 文件。工程上不要把长任务塞进 Service，否则调用方只能卡住等待，无法看到进度，也很难取消。

---

## Parameter

参数让同一套节点适配不同相机、飞机和场地。

创建 `drone_basics/landing_params.py`：

```python
import rclpy
from rclpy.node import Node


class LandingParams(Node):
    def __init__(self):
        super().__init__("landing_params")
        self.declare_parameter("marker_size", 0.2)
        self.declare_parameter("align_tolerance", 0.08)
        self.declare_parameter("max_descent_speed", 0.3)

        self.timer = self.create_timer(1.0, self.print_params)

    def print_params(self):
        marker_size = self.get_parameter("marker_size").value
        tolerance = self.get_parameter("align_tolerance").value
        speed = self.get_parameter("max_descent_speed").value
        self.get_logger().info(
            f"marker_size={marker_size} tolerance={tolerance} speed={speed}"
        )


def main():
    rclpy.init()
    node = LandingParams()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

运行时传参：

```bash
ros2 run drone_basics landing_params --ros-args -p marker_size:=0.18 -p align_tolerance:=0.05
```

查看参数：

```bash
ros2 param list
ros2 param get /landing_params marker_size
ros2 param set /landing_params align_tolerance 0.06
```

参数文件示例 `config/landing.yaml`：

```yaml
landing_params:
  ros__parameters:
    marker_size: 0.2
    align_tolerance: 0.08
    max_descent_speed: 0.3
```

---

## Launch、命名空间、Remap

### 为什么需要 Launch

当系统有多个节点时，不应该靠手动开终端：

```bash
ros2 run camera camera_node
ros2 run landing aruco_detector
ros2 run landing landing_controller
ros2 run bridge flight_bridge
```

Launch 文件把系统启动方式固化下来。

创建 `launch/landing_demo.launch.py`：

```python
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="drone_basics",
            executable="osd_publisher",
            name="osd_publisher",
            namespace="drone001",
            output="screen",
        ),
        Node(
            package="drone_basics",
            executable="osd_subscriber",
            name="osd_subscriber",
            namespace="drone001",
            output="screen",
            remappings=[
                ("/drone/osd", "/drone001/drone/osd"),
            ],
        ),
    ])
```

运行：

```bash
ros2 launch drone_basics landing_demo.launch.py
```

### 命名空间

多无人机时不要把所有 Topic 混在根目录：

```text
/drone001/camera/image_raw
/drone001/landing/marker_pose
/drone001/cmd_vel

/drone002/camera/image_raw
/drone002/landing/marker_pose
/drone002/cmd_vel
```

命名空间让同一套节点可以启动多份。

### Remap

Remap 用于把节点内部默认 Topic 改成系统实际 Topic。

例子：

```bash
ros2 run drone_basics osd_subscriber --ros-args -r /drone/osd:=/drone001/telemetry/osd
```

工程建议：节点内部用清晰的默认名，系统集成时用 launch 统一 remap。

---

## TF2、rosbag、RViz 和 CLI 调试

### TF2

TF2 管理坐标系关系。无人机视觉系统常见坐标系：

```text
map
odom
base_link
camera_link
camera_optical_frame
landing_marker
```

精准降落里，最重要的是知道：

- ArUco 检测结果在哪个相机坐标系下。
- 相机坐标系如何变换到机体系。
- 控制器需要的是机体系误差、世界系误差，还是图像平面误差。

如果坐标系没理清，控制方向很容易反。

常用命令：

```bash
ros2 run tf2_tools view_frames
ros2 run tf2_ros tf2_echo base_link camera_link
```

### rosbag

rosbag 用于录制和回放 Topic。无人机开发中它非常关键，因为真机飞一次成本很高。

录制：

```bash
ros2 bag record /camera/image_raw /imu/data /landing/marker_pose /cmd_vel
```

回放：

```bash
ros2 bag play <bag-directory>
```

工程习惯：

- 每次真机测试录 bag。
- 算法改动先用 bag 回放验证。
- 事故或异常先看 bag，再猜原因。

### RViz

RViz 用于可视化：

- 图像
- 点云
- TF
- Marker
- 路径
- 位姿

精准降落开发时，建议把 ArUco 目标位置、无人机位姿、相机坐标系都可视化出来。

### CLI 调试命令

```bash
ros2 node list
ros2 node info /landing_controller
ros2 topic list
ros2 topic info /landing/marker_pose
ros2 topic echo /landing/marker_pose
ros2 topic hz /camera/image_raw
ros2 service list
ros2 param list
ros2 doctor
```

调试顺序：

1. 节点是否存在。
2. Topic 是否存在。
3. 发布频率是否正常。
4. 消息内容是否合理。
5. 参数是否加载。
6. 坐标系是否连通。

---

## 无人机节点系统设计

一个可维护的精准降落 ROS2 系统可以拆成：

```text
camera_node
  发布 /camera/image_raw

aruco_detector_node
  订阅 /camera/image_raw
  发布 /landing/marker_detection
  发布 /tf: camera -> landing_marker

landing_estimator_node
  订阅 /landing/marker_detection
  订阅 /tf
  发布 /landing/target_error

landing_controller_node
  订阅 /landing/target_error
  订阅 /flight/state
  发布 /flight/cmd_vel
  提供 /landing/reset service
  提供 /precision_land action

flight_bridge_node
  订阅 /flight/cmd_vel
  发布 /flight/state
  对接 PX4、MAVLink、MQTT 或厂商 SDK

logger_node
  录制关键 Topic 或触发 rosbag
```

每个节点的责任要清楚：

| 节点 | 不该做的事 |
|------|------------|
| 相机节点 | 不做控制决策 |
| 检测节点 | 不直接发飞控命令 |
| 控制节点 | 不关心相机驱动细节 |
| 飞控桥接节点 | 不做视觉算法 |
| 日志节点 | 不影响控制闭环 |

这种拆分的好处是：相机、检测器、控制器、飞控接口都能单独替换。

---

## 从单脚本迁移到 ROS2 工程

你的精准降落实际代码是单脚本工程，核心组件包括：

- `OpenCVVideoSource` / `TailH264Source`
- `ArucoLandingController`
- `MqttAdapter`
- 主循环

迁移到 ROS2 时可以这样拆：

| 单脚本组件 | ROS2 节点/模块 |
|------------|----------------|
| `OpenCVVideoSource` | `camera_node` 或视频输入节点 |
| `detect()` | `aruco_detector_node` |
| `estimate_height_from_marker()` | `landing_estimator_node` |
| `ArucoLandingController.update()` | `landing_controller_node` |
| `MqttAdapter` | `mqtt_bridge_node` 或 `flight_bridge_node` |
| `preview` | RViz/Image View/调试节点 |
| 日志 print | ROS2 logger + rosbag |

迁移时不要一次性重写全部代码。推荐顺序：

1. 保留原脚本作为 baseline。
2. 先把视频输入和检测拆出来，发布检测结果。
3. 用 rosbag 录制图像和检测结果。
4. 把状态机控制器拆成节点，订阅检测结果。
5. 把 MQTT 发送封装成 bridge 节点。
6. 最后用 launch 串起来。

这样每一步都有可运行结果，不会陷入“大重构后不知道哪里坏了”。

---

## ROS2 与 MQTT 的关系

ROS2 和 MQTT 不是互相替代关系。

| 维度 | ROS2 | MQTT |
|------|------|------|
| 典型位置 | 机载计算机内部、机器人局域网 | 设备到云端、地面站、弱网络 |
| 通信模型 | DDS 数据分发，机器人节点图 | Broker 中转，发布/订阅 |
| 适合数据 | 传感器、控制、TF、机器人内部状态 | 遥测、远程命令、事件、云端集成 |
| 调试工具 | `ros2 topic`, RViz, rosbag | `mosquitto_sub`, Broker 日志 |
| 典型风险 | 坐标系、QoS profile、节点生命周期 | 权限、旧消息、重连、命令幂等 |

无人机工程中常见组合：

```text
ROS2 内部:
  camera -> detector -> estimator -> controller

MQTT 外部:
  telemetry -> cloud/ground station
  remote command -> bridge -> ROS2/flight controller
```

也就是说，ROS2 负责机载算法系统的结构化开发，MQTT 负责跨网络的遥测和远程控制。

---

## 部署、日志和故障定位

### 部署方式

开发阶段：

```bash
source /opt/ros/jazzy/setup.bash
source ~/drone_ws/install/setup.bash
ros2 launch drone_bringup precision_landing.launch.py
```

长期运行可以用 systemd：

```ini
[Unit]
Description=Drone Precision Landing ROS2 System
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/drone_ws
ExecStart=/bin/bash -lc 'source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 launch drone_bringup precision_landing.launch.py'
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 日志

ROS2 节点用：

```python
self.get_logger().info("message")
self.get_logger().warning("message")
self.get_logger().error("message")
```

不要在工程节点里只用 `print()`。日志级别有助于筛选问题。

### 故障定位模板

图像没有进来：

```bash
ros2 topic list | grep camera
ros2 topic hz /camera/image_raw
ros2 topic echo /camera/camera_info
```

检测没有结果：

```bash
ros2 topic echo /landing/marker_detection
ros2 param get /aruco_detector marker_id
ros2 param get /aruco_detector marker_size
```

控制不动：

```bash
ros2 topic echo /landing/target_error
ros2 topic echo /flight/cmd_vel
ros2 topic echo /flight/state
```

方向反了：

```bash
ros2 run tf2_ros tf2_echo base_link camera_link
ros2 topic echo /landing/target_error
```

真机表现和仿真不同：

- 录制 rosbag。
- 回放图像和状态。
- 比较参数文件。
- 检查相机安装角、曝光、延迟、时间戳。

---

## 练习项目

### 练习 1：跑通 talker/listener

目标：运行官方示例。

验收：

- `talker` 能发布。
- `listener` 能接收。
- `ros2 topic list` 能看到 Topic。

### 练习 2：写 OSD 发布订阅

目标：实现本页 `osd_publisher` 和 `osd_subscriber`。

验收：

- `ros2 topic echo /drone/osd` 能看到 JSON。
- 订阅者能解析高度和电量。

### 练习 3：做 reset service

目标：写 `/landing/reset`。

验收：

- `ros2 service call` 能得到 `success: true`。
- 节点日志能看到 reset 信息。

### 练习 4：参数化降落控制

目标：把 `marker_size`、`align_tolerance`、`max_descent_speed` 做成参数。

验收：

- 命令行传参生效。
- YAML 参数文件能加载。

### 练习 5：设计精准降落节点图

目标：画出从相机到飞控桥接的节点图。

验收：

- 每个节点只有一个清楚职责。
- 每条 Topic 的消息方向明确。
- 能解释哪些数据需要 rosbag 录制。

### 练习 6：把 MQTT 接进 ROS2

目标：设计一个 `mqtt_bridge_node`。

输入：

- MQTT `drone/001/telemetry/osd`
- MQTT `drone/001/cmd/land`

输出：

- ROS2 `/flight/state`
- ROS2 `/landing/start` 或 Action goal

验收：

- 能解释 MQTT 和 ROS2 的边界。
- 控制命令有超时和回复。
- 不把 MQTT 回调和控制状态机混成一个大函数。

---

## 常见误区

### 误区 1：ROS2 只是比 socket 高级一点的通信库

ROS2 的价值不只是通信，而是节点组织、接口规范、参数、launch、日志、可视化、录包和生态。

### 误区 2：所有东西都拆成节点

拆节点不是越多越好。高频、强耦合、只在一个进程内部使用的逻辑可以保留在模块里。节点边界应该对应清楚的运行和调试边界。

### 误区 3：Topic 能解决所有通信

Topic 适合连续数据流。短请求用 Service，长任务用 Action，配置用 Parameter。

### 误区 4：没有 rosbag 也能调真机

没有录包，很多问题只能靠猜。无人机真机调试应默认录制关键 Topic。

### 误区 5：坐标系靠感觉调

控制方向、相机安装、机体系转换必须用 TF 和明确约定管理。靠试错很容易在低空控制时出危险。

---

## 相关页面

- [[concepts/concept-mqtt-engineering]] — MQTT 工程开发教程
- [[topics/topic-precision-localization-code]] — 精准降落实际代码解析
- [[topics/topic-precision-localization]] — 无人机精准定位系统
- [[concepts/concept-drone-control]] — 无人机飞控与控制
- [[concepts/concept-state-estimation-foundations]] — 状态估计基本功
- [[concepts/concept-vision-geometry-foundations]] — 视觉几何基本功
- [[concepts/method-model-deployment]] — 模型部署与推理加速

---

## 引用来源

- [1] [ROS2 Documentation](https://docs.ros.org/) — ROS2 官方文档入口。
- [2] [ROS2 Jazzy Installation: Ubuntu Debian Packages](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html) — Ubuntu 安装说明。
- [3] [ROS2 Tutorials: Beginner Client Libraries](https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries.html) — 工作空间、包、发布订阅等入门教程。
- [4] [ROS2 Concepts](https://docs.ros.org/en/jazzy/Concepts.html) — ROS2 图、节点、Topic、Service、Action、参数等概念。
- [5] [PX4 ROS 2 User Guide](https://docs.px4.io/main/en/ros2/user_guide.html) — PX4 与 ROS2 集成方向。
- [6] [[topics/topic-precision-localization-code]] — 本知识库精准降落实际代码解析。

---

## 变更记录

- 2026-06-30: 新增 ROS2 从零基础到无人机节点系统开发教程，覆盖工作空间、Python 节点、Topic、Service、Action、Parameter、Launch、TF2、rosbag、无人机节点拆分，以及从精准降落单脚本迁移到 ROS2 工程的方法。
