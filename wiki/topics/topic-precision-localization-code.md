# 无人机精准降落实际代码解析：ArUco + MQTT 虚拟摇杆

> **类型**: topic
> **创建时间**: 2026-06-30
> **最后更新**: 2026-06-30
> **来源**: [raw/precision-landing-mqtt-code.txt](../raw/precision-landing-mqtt-code.txt)
> **标签**: #无人机 #精准降落 #ArUco #OpenCV #MQTT #PX4 #控制 #工程

## 摘要

这份实际代码不是一个标准 ROS2/PX4 Offboard 示例，而是一套面向现场部署的单文件精准降落控制程序。它从 H.264 视频流或普通 OpenCV 输入中读取下视画面，用 OpenCV ArUco 检测指定降落标记，基于标记中心像素偏差和标记像素宽度估计横向误差与高度，再通过 MQTT 调用飞控服务，把控制量转换为虚拟摇杆、速度或目标控制命令。

代码的工程重点不在“写一个 PID”，而在四件现场最容易出问题的事：控制权获取、方向标定、低空死区、异常收尾。它用 `MqttAdapter` 处理飞控状态、命令回复和安全恢复，用 `ArucoLandingController` 管理 SEARCH/ALIGN/DESCEND/LAND 状态机，用“悬停测量 -> 定时拨杆 -> 再测量”的闭环替代每帧连续 PID，以适配虚拟摇杆的最小生效阈值和现场风扰。

## MQTT/ROS2 学习入口

如果你是从 0 经验开始读这份代码，建议先补两条工程基础：

- [[concepts/concept-mqtt-engineering]] — 先理解 Broker、Topic、QoS、命令回复、Retain、Will、ACL 和 Paho Python，再看 `MqttAdapter` 为什么要处理连接、状态、回复、超时和异常恢复。
- [[entities/product-ros2]] — 先理解 Node、Topic、Service、Action、Parameter、Launch、TF2 和 rosbag，再看这份单脚本将来如何拆成相机节点、检测节点、控制节点和飞控桥接节点。

这两页对应本代码的两条主线：MQTT 负责跨网络遥测/控制，ROS2 负责机载算法系统的节点化组织。

---
## 代码整体定位

### 这份代码解决的问题

精准降落的目标可以写成一句控制问题：

> 让无人机在下降过程中，使地面 ArUco 标记中心持续靠近相机投影目标点，并在低空满足安全阈值后进入降落与落锁流程。

实际代码把这个问题拆成五层：

| 层级 | 代码组件 | 责任 |
|------|----------|------|
| 输入层 | `OpenCVVideoSource`, `TailH264Source` | 从摄像头、视频文件、RTSP 或持续追加的 H.264 文件中取帧 |
| 感知层 | `ArucoLandingController.detect()` | 检测指定 marker id，输出中心点、角点、像素边长 |
| 估计层 | `estimate_height_from_marker()`, `estimate_body_error_m()` | 用针孔模型把像素误差换成高度和机体系横向误差 |
| 决策层 | `ArucoLandingController.update()` | SEARCH/ALIGN/DESCEND/LAND 状态机，决定当前动作 |
| 执行层 | `MqttAdapter` | 通过 MQTT 下发虚拟摇杆、速度、目标控制、降落、落锁和恢复命令 |

### 和理想化 ROS2 版本的区别

现有总览页里的示例偏“教科书版本”：相机图像进入 ROS2 节点，ArUco 角点进入 `solvePnP`，再把 6-DOF 位姿发布给控制器。`code.txt` 里的实际脚本更像现场工程版本：

| 对比项 | 教科书/ROS2 示例 | 实际脚本 |
|--------|------------------|----------|
| 运行形态 | 多节点 ROS2 工程 | 单 Python 脚本 |
| 位姿估计 | `solvePnP` 输出完整 `rvec/tvec` | 用 marker 中心和像素宽度估计横向误差/高度 |
| 控制接口 | MAVROS/PX4 Offboard | MQTT 服务 + 虚拟摇杆优先 |
| 控制方式 | 连续 PID/速度控制 | 悬停测量 + 定时动作 + 响应增益自适应 |
| 现场保护 | 示例级 | 控制权获取、OSD 状态确认、拒绝处理、中断恢复、落地收尾 |

这不是退化，而是工程取舍：现场最关键的是稳定、可调、能收尾。完整 6-DOF 姿态在精准降落中当然有价值，但如果下视相机基本正装、marker 平面近似水平，中心偏差和边长已经足够驱动低速对准。

---

## 主程序生命周期

脚本入口是 `run_with_interrupt_cleanup()`。它比普通 `main()` 多了一层安全壳，任何 `KeyboardInterrupt` 或异常都会尽量释放控制权。

运行流程如下：

```text
解析命令行参数
  -> 计算 camera_radar_height_offset
  -> 连接 MQTT
  -> 捕获启动前 fly_mode / joystick_state / pva_state
  -> 初始化飞行模式、虚拟摇杆状态、手动速度限制
  -> 打开视频源
  -> 创建 ArucoLandingController
  -> 循环读取图像
      -> resize 到配置分辨率
      -> controller.update(frame) 得到动作
      -> controller.maybe_send_command(cmd, action) 下发控制
      -> LAND 后确认触地并落锁
      -> 可选 preview 叠加显示
  -> finally 释放视频、断开 MQTT、关闭窗口
```

这里最值得注意的是“启动前状态快照”。脚本会记录进入精准降落前的飞行模式、摇杆状态和 PVA 状态，结束或中断时尽量恢复，而不是简单地把飞机留在一个被脚本接管过的半控制状态。

---

## 数据模型

### `ControlCommand`

`ControlCommand` 是控制输出的统一中间表示：

```python
class ControlCommand(object):
    def __init__(self, vx=0.0, vy=0.0, vz=0.0, yaw_rate=0.0):
        self.vx = float(vx)
        self.vy = float(vy)
        self.vz = float(vz)
        self.yaw_rate = float(yaw_rate)
```

它不直接等于飞控协议。它先表示机体系或控制接口期望的速度，再由 `MqttAdapter` 根据 `--control-method` 转换成：

- `setJoystickValue` 的 `x/y/z/yaw`
- `velocityCtrl` 的 `vx/vy/vz/yawRate`
- `targetCtrl` 的速度、加速度和姿态约束字段

这种中间层的好处是状态机不用关心最终是虚拟摇杆还是速度控制。坏处是轴向符号、速度上限、摇杆死区都集中到适配层，调试时必须区分“控制器想让它往哪走”和“协议实际发了什么”。

### `DetectionResult`

`DetectionResult` 是视觉检测结果：

```python
class DetectionResult(object):
    def __init__(self):
        self.detected = False
        self.marker_center = None
        self.pixel_width = 0.0
        self.marker_corners = None
        self.ids = None
```

它只保留降落需要的最小信息：

- `marker_center`: 四个角点均值，表示 marker 在图像中的中心。
- `pixel_width`: 四条边像素长度的均值，用于估算相机到 marker 的距离。
- `marker_corners`: 画预览和计算边长。
- `ids`: 用于过滤指定 `--marker-id`。

实际降落控制并不需要每帧输出完整姿态矩阵。只要知道“目标在图像里偏左/偏右/偏上/偏下，以及大概多高”，就能做低速对准。

---

## 视觉测量模型

### ArUco 检测

检测逻辑在 `ArucoLandingController.detect(frame_bgr)` 中：

```text
BGR 图像 -> 灰度图
  -> aruco.detectMarkers()
  -> 找到指定 marker_id
  -> 计算四角点均值作为 marker_center
  -> 计算四条边长度均值作为 pixel_width
```

如果画面中有多个 marker，脚本只取 `--marker-id` 指定的那个。这一点很重要：现场可以同时放多个标记，但用于降落的标记必须唯一，否则飞机可能追错目标。

### 用标记边长估高

代码使用：

```python
height = camera_fx * marker_size / pixel_width
```

它来自针孔相机模型。对于一个真实宽度为 `L` 的平面标记，如果它正对相机、深度为 `Z`，投影宽度近似为：

```text
pixel_width = fx * L / Z
```

所以：

```text
Z = fx * L / pixel_width
```

这里的 `Z` 被当成“相机到地面标记的高度”。这个估计有三个前提：

1. 相机近似垂直向下。
2. marker 平面近似水平。
3. marker 在图像里不是极端倾斜或严重畸变。

如果这些前提不成立，`solvePnP` 会更严谨；但在低速降落场景里，边长估高简单、快速、参数少，很适合做控制阈值判断。

### 用像素偏差估横向误差

相机针孔模型：

```text
u = cx + fx * X / Z
v = cy + fy * Y / Z
```

反过来：

```text
X = Z * (u - cx) / fx
Y = Z * (v - cy) / fy
```

实际代码不是直接使用 `(u-cx, v-cy)`，而是先计算动态目标像素：

```python
u_target = camera_cx - camera_fx * camera_offset_x / camera_height
v_target = camera_cy - camera_fy * camera_offset_y / camera_height
du = marker_center_x - u_target
dv = marker_center_y - v_target
```

这样可以补偿相机安装位置不在机体中心的问题。相机离机体中心越远，高空时目标点偏移越小，低空时投影偏移越明显，因此补偿项要除以高度。

然后估算机体系误差：

```python
body_x = camera_h * dv / camera_fy
body_y = camera_h * du / camera_fx
```

这里 `dv` 影响前后轴，`du` 影响左右轴，是下视相机常见坐标约定的结果。实际方向还会经过：

- `--swap-xy`
- `--invert-x`
- `--invert-y`
- `--image-yaw-comp-deg`

现场调试时，第一优先级不是调增益，而是确认方向：目标在画面右侧时，飞机到底应该向哪边移动。如果方向错，任何控制器都会越调越偏。

---

## MQTT 适配层

`MqttAdapter` 是整份代码最工程化的部分。它不是简单 `publish()`，而是同时处理命令、状态、回复、模式、保护和收尾。

### 主题设计

脚本根据 `product_id` 组织三个 MQTT 主题：

| 主题 | 用途 |
|------|------|
| `qyhk/onboard/flight/thing/product/{product_id}/services` | 下发控制服务调用 |
| `qyhk/onboard/thing/product/{product_id}/osd` | 接收飞行状态、相对高度、垂直速度、模式 |
| `qyhk/onboard/flight/thing/product/{product_id}/services_reply` | 接收服务调用回复 |

每条服务命令都有 `tid`、`bid`、`method`、`timestamp` 和可选 `data`。`tid` 用于把回复和请求关联起来。

### OSD 状态的作用

OSD 回调会提取：

- `relativeAlt`: 对地或相对高度。
- `verticalSpeed`: 垂直速度，用于触地确认。
- `flyMode`: 当前飞行模式。
- `stateType`: 飞控状态。
- `joystickState`: 虚拟摇杆是否启用。
- `pvaControllerState`: PVA 控制器是否启用。

这些状态不是为了显示，而是控制门禁。脚本在下发运动命令前会检查：

```text
飞行模式是否是 posctl/attitude
虚拟摇杆是否启用
如果不是 joystick 控制，PVA 是否启用
当前是否处于 RTL/LAND/TAKEOFF/POINT 等自动模式
最近是否有运动命令被拒绝
```

这就是现场脚本和 demo 脚本的区别：demo 假设控制链路已经准备好，现场脚本必须证明控制链路准备好了。

### 控制方式

`--control-method` 支持三种：

| 方式 | MQTT method | 特点 |
|------|-------------|------|
| `joystick` | `setJoystickValue` | 默认方式，适合接管虚拟摇杆 |
| `velocity` | `velocityCtrl` | 直接速度控制 |
| `target` | `targetCtrl` | 目标/速度/加速度组合控制 |

默认 `joystick` 是合理的现场选择。很多飞控或云控平台对 Offboard/PVA 的状态要求更高，而虚拟摇杆模式更接近人工遥控接管，容易和现有产品控制链路兼容。

### 虚拟摇杆映射

控制器输出速度，适配器要映射到摇杆值：

```text
joystick_axis = sign * joystick_max * velocity / axis_speed_max
```

其中符号由参数控制：

- `--joystick-pitch-sign`
- `--joystick-roll-sign`
- `--joystick-throttle-sign`
- `--joystick-yaw-sign`

这几个符号必须现场验证。比如注释中默认 `pitch_sign=-1`，表示协议定义里 `x=-1000` 是前进。若平台定义不同，需要改符号而不是改控制器。

### 最小有效摇杆补偿

脚本有一套很重要的死区处理：

- `--joystick-xy-min-effective-value`
- `--joystick-xy-force-value`
- `--joystick-z-min-effective-value`
- `--joystick-z-force-value`
- `--joystick-min-effective-mode`

原因是很多飞控或上层平台存在摇杆死区：小于某个杆量，飞机不动；刚超过阈值，又可能动作偏大。代码提供两种补偿：

| 模式 | 逻辑 | 适用 |
|------|------|------|
| `hold` | 小杆量触发后，强制保持固定有效杆量一小段时间 | 默认，更稳定 |
| `pulse` | 周期性输出有效杆量和 0，靠占空比模拟小动作 | 需要更细腻微动时 |

这解释了为什么脚本没有直接用小速度连续控制。现场系统里“0.03 m/s”可能根本不生效，必须先跨过执行器死区。

---

## 状态机

`ArucoLandingController` 有四个状态：

```python
SEARCH = 0
ALIGN = 1
DESCEND = 2
LAND = 3
```

### SEARCH：等待目标

SEARCH 状态会重置对准周期。如果启动保护时间已过，并且检测到目标，就进入 ALIGN。

启动保护由两个条件组成：

- `--startup-guard-time`: 启动后等待一段时间，避免脚本刚启动就误判。
- `--min-startup-radar-height` 或 `--min-startup-camera-height`: 二次起飞或低空重启时，防止过低高度直接进入自动降落流程。

### ALIGN：悬停测量与水平修正

ALIGN 是核心状态。它并不是每帧看到偏差就立刻输出速度，而是分成两个子阶段：

```text
measure: 悬停采样 hover_measure_time，收集 du/dv/height
actuate: 根据平均误差生成定时动作，保持一段时间
```

这种“测量-动作-再测量”的控制方式适合三类现场问题：

1. 画面检测抖动，单帧误差不可靠。
2. 虚拟摇杆有死区，连续小命令无效。
3. 风扰和飞控响应延迟导致闭环不能太激进。

当采样完成后，脚本用均值生成 `measure`：

```text
du/dv 平均值
camera_h 平均值
uav_h 平均值
body_x_m/body_y_m
tol_x_m/tol_y_m
stage_name
sample_count
```

如果横向误差已经小于当前阶段容差，就进入下降或 LAND；否则构建一次定时修正计划。

### DESCEND：分阶段垂直下降

DESCEND 状态只输出垂直下降速度：

```python
vz_des = -descent_speed
```

当无人机高度到达当前阶段目标高度附近，就回到 ALIGN 重新测量。阶段由高度划分：

| 阶段 | 条件 | 目标 |
|------|------|------|
| `HIGH_ALIGN` | `uav_h > stage_high_alt_height` | 下降到高/中空分界 |
| `MID_ALIGN` | `final_direct_land_height < uav_h <= stage_high_alt_height` | 下降到最后逼近高度 |
| `FINAL_ALIGN` | `uav_h <= final_direct_land_height` | 对准后进入 LAND |

默认参数大致是 2.0 m 和 0.70 m 两个关键高度。

### LAND：降落与收尾

进入 LAND 后，脚本只发送一次 `land` 命令，然后等待触地确认或超时。触地确认使用：

- 高度阈值：`touchdown_radar_height` 或 `touchdown_camera_height`
- 垂直速度阈值：`touchdown_vertical_speed`
- 持续时间：`touchdown_confirm_time`

满足条件后执行：

```text
发送零运动
重复 disarm
释放控制
恢复启动前状态
```

如果没有触地确认，超过 `land_finalize_timeout` 也会收尾，避免脚本永远停在 LAND 等待。

---

## 定时修正控制律

### 为什么不用简单 PID

传统 PID 假设控制输出和系统响应在小范围内近似线性。但虚拟摇杆链路常见问题是：

- 小杆量被死区吞掉。
- 平台内部限速、限倾角。
- MQTT 与视频存在延迟。
- 风扰让小修正看起来无效。
- 低空时过度连续修正容易来回摆。

所以脚本采用定时修正：

```text
测得横向误差 -> 计算需要修正的距离 -> 生成一个足够生效的杆量 -> 保持一段时间 -> 再测量实际效果
```

这更像“离散伺服校正”，而不是连续 PID。

### 修正计划的计算

核心函数是 `build_timed_actuation_plan(measure)`。

对单轴，逻辑可以概括为：

```text
residual = max(0, abs(body_dist) - deadband_scale * tol_m)
joystick = stage_min_joystick + wind_bias + distance_gain * residual
joystick = clamp(joystick, stage_min_joystick, joystick_max)
theoretical_speed = manual_hor_spd_max * joystick / joystick_max
effective_speed = theoretical_speed * axis_response_gain
actuation_time = residual / effective_speed
actuation_time = clamp(actuation_time, min_time, stage_max_time)
```

重要参数：

| 参数 | 含义 |
|------|------|
| `timed-stage-min-joystick-*` | 各高度阶段最小有效水平杆量 |
| `timed-wind-bias-joystick-*` | 各阶段风补偿杆量 |
| `timed-joystick-distance-gain` | 横向距离转附加杆量的增益 |
| `timed-actuation-min-time` | 单次动作最短持续时间 |
| `timed-actuation-max-time-*` | 各阶段单次动作最长持续时间 |
| `timed-distance-deadband-scale` | 米级死区缩放 |

### 单轴与多轴

`--axis-mode` 控制水平修正方式：

| 模式 | 行为 | 优点 | 风险 |
|------|------|------|------|
| `single` | 每次只修正误差更大的轴 | 更稳，轴间耦合少，适合现场默认 | 收敛慢 |
| `multi` | 前后/左右同时修正 | 收敛快 | 方向标定错时更难排查，容易斜向过冲 |

默认 `single` 是保守选择。调试新飞机、新相机、新协议时，应先用单轴确认方向，再考虑多轴。

### 响应增益自适应

脚本维护：

```python
self._axis_response_gain = {'x': init_gain, 'y': init_gain}
```

每次动作后重新测量误差，估计“实际移动量 / 预测移动量”，再更新响应增益：

```text
ratio = actual_move / predicted_move
target_gain = old_gain * ratio
new_gain = (1-alpha) * old_gain + alpha * target_gain
```

如果飞机实际动得比预测少，后续会延长动作或提高等效补偿；如果动得过多，后续会保守。这是这份代码最有现场价值的设计之一：它承认模型不准，并用每轮对准结果在线修正。

---

## 高度源与几何偏移

脚本支持两种整体高度判断：

```text
--height-judge-source radar
--height-judge-source vision
```

### radar 模式

`raw_radar_height()` 从 OSD `relativeAlt` 获取高度。若控制中需要相机到地高度，则加上：

```text
camera_radar_height_offset = camera_ground_offset - radar_ground_offset
```

这适合有可靠对地雷达或测距模块的场景。

### vision 模式

`vision_height()` 使用 ArUco 像素宽度估高。若需要无人机离地高度，则：

```text
uav_h = vision_height - camera_ground_offset
```

这适合没有稳定雷达、但 marker 清晰可见的场景。风险是低空大角度、模糊、遮挡会影响估高。

### 偏移参数

| 参数 | 含义 |
|------|------|
| `camera-offset-x/y` | 相机相对机体中心的水平安装偏移 |
| `camera-ground-offset` | 相机离起落架触地点高度 |
| `radar-ground-offset` | 雷达离起落架触地点高度 |
| `offset-comp-disable-below` | 低于该相机高度后关闭偏移补偿 |

低空关闭偏移补偿是保守策略：高度很低时，除以高度的投影补偿会变大，容易因为估高噪声引起目标点跳动。

---

## 视频输入层

### `OpenCVVideoSource`

适合：

- USB 摄像头：`--input 0 --input-mode opencv`
- RTSP：`--input rtsp://... --input-mode opencv`
- 本地视频文件

它简单可靠，但对持续追加的裸 H.264 文件不够友好。

### `TailH264Source`

默认输入模式是 `tail_h264`，说明现场视频链路很可能是一个不断追加的 `received_video.h264` 文件。该类做了三件事：

1. 轮询 H.264 文件，像 `tail -f` 一样读新增字节。
2. 把字节喂给 FFmpeg stdin。
3. 从 FFmpeg stdout 读 `bgr24` raw frame，再交给 OpenCV。

FFmpeg 参数强调低延迟：

```text
-fflags nobuffer
-flags low_delay
-analyzeduration 0
-probesize 小值
-avioflags direct
```

`tail_start_mode=warm` 会从文件尾部往前读一段历史字节，帮助 FFmpeg 拿到 SPS/PPS/IDR，否则裸 H.264 中途接入时可能无法立即解码。

`tail_require_live_data=True` 又避免直接拿上一次飞行残留的旧帧做降落决策。这个细节很关键：无人机控制不能用过期画面。

---

## 发送门控与安全收尾

### 发送门控

`maybe_send_command()` 不会每次状态机输出都立即发 MQTT。它会检查：

- 是否处于 LAND。
- 是否在 hold/none。
- 是否超过 `control_rate`。
- 是否处于自动模式，自动模式下不抢控制。
- 最近是否有运动控制拒绝。
- 手动控制是否 ready。
- 是否满足最小发送间隔 `min_velocity_send_interval`。
- 是否满足帧间隔或命令变化阈值。

这能避免 MQTT 刷屏、重复命令、抢自动模式控制，也能让拒绝后的系统有时间稳定。

### 视觉丢失处理

ALIGN 中如果丢失目标或检测超时，会：

```text
可选发送 brake/零摇杆
退回 SEARCH
重置对准周期
```

在 joystick 模式下，`send_brake()` 不切 Hold，而是发送零摇杆，避免中途改变飞行模式。

### 中断恢复

`restore_after_interrupt()` 的目标很明确：

1. 连续发送零运动。
2. 释放虚拟摇杆或 PVA 控制权。
3. 恢复启动前飞行模式和状态。

所以运行现场脚本时，不应该用强制杀进程作为常规停止方式。优先 Ctrl+C，让脚本执行恢复逻辑。

---

## 参数调试顺序

### 1. 先确认视频和 marker

推荐启动：

```bash
python3 landing.py --input received_video.h264 --preview
```

确认预览中：

- 能画出 marker 轮廓。
- `marker_detected=True` 稳定。
- `pixel_width` 随高度降低而变大。
- `camera_h` 与实际高度量级一致。

### 2. 校准相机内参与 marker 尺寸

必须确认：

```text
camera_fx / camera_fy / camera_cx / camera_cy
marker_size
image_width / image_height
```

如果 `marker_size` 写小，高度会估小；写大，高度会估大。高度错会影响阶段切换、容差换算和 LAND 触发。

### 3. 校准方向

从小杆量、单轴开始：

```bash
--axis-mode single --preview
```

观察目标在画面偏右、偏左、偏上、偏下时，飞机动作是否让误差变小。若变大，依次调整：

```text
--invert-x
--invert-y
--swap-xy
--image-yaw-comp-deg
--joystick-pitch-sign
--joystick-roll-sign
```

方向没有确认前，不要调增益。

### 4. 找最小有效杆量

默认现场参数大致是：

```text
joystick_xy_min_effective_value = 150
joystick_xy_force_value = 170
joystick_max_value = 300
```

如果飞机对小误差完全不动，提高 `force_value` 或 `stage_min_joystick`。如果动作太冲，降低 `manual_hor_spd_max` 或缩短 `timed_actuation_max_time_*`。

### 5. 调阶段容差

容差按高度分三段：

```text
high_alt_center_tolerance
mid_alt_center_tolerance
final_alt_center_tolerance
land_center_tolerance
```

高空容差可以大一些，因为高空小像素误差对应更大实际距离，且风扰更明显。低空容差必须收紧，但不能小到因为检测噪声反复横跳。

### 6. 调 LAND 阈值

重点参数：

```text
land_camera_trigger_height
force_land_camera_height
touchdown_camera_height
touchdown_vertical_speed
touchdown_confirm_time
land_finalize_timeout
```

LAND 触发太早会偏，太晚会低空纠偏过多。建议先保守，确保最终阶段对准稳定，再逐步降低 LAND 触发高度。

---

## 常见故障定位

| 现象 | 优先检查 | 解释 |
|------|----------|------|
| 首页预览有画面但不识别 | `aruco_dict_name`, `marker_id`, `min_marker_perimeter_rate` | 字典或 id 不一致最常见 |
| 高度明显不对 | `marker_size`, `camera_fx`, 图像分辨率 | 边长估高依赖这些参数 |
| 目标越修越远 | `invert-x/y`, `swap-xy`, joystick sign | 方向错比增益错更危险 |
| 小偏差不动 | `joystick_*_min_effective_value`, `stage_min_joystick` | 虚拟摇杆死区吞掉小命令 |
| 动作一顿一顿 | `hover_measure_time`, `timed_actuation_*` | 这是设计特征，靠离散动作收敛 |
| 控制命令被拒绝 | OSD flyMode、joystickState、PVA 状态、服务回复 | 飞控未处于可接管状态 |
| 刚启动就进入降落 | `startup_guard_time`, `min_startup_*_height` | 启动保护过短或高度源异常 |
| 低空来回摆 | `final_alt_center_tolerance`, `direct_vertical_*`, `land_*_trigger_height` | 低空应少纠偏、快收尾 |
| H.264 延迟大 | `tail_start_mode`, `tail_warm_bytes`, FFmpeg 参数 | 需要拿到新鲜帧和关键帧 |

---

## 教科书式伪代码

下面是去掉 MQTT 和视频细节后的控制核心：

```text
while running:
    frame = read_video()
    detection = detect_aruco(frame)

    if state == SEARCH:
        if startup_guard_ok and detection.valid:
            state = ALIGN
            reset_measurement()

    if state == ALIGN:
        if detection.lost:
            send_zero_or_brake()
            state = SEARCH
            continue

        height = estimate_height(detection.pixel_width)
        target_pixel = compensate_camera_offset(height)
        du, dv = marker_center - target_pixel
        body_error = pixel_error_to_body_error(du, dv, height)
        collect_sample(body_error)

        if enough_samples:
            measure = average_samples()
            if abs(measure.x) <= tolerance_x and abs(measure.y) <= tolerance_y:
                if final_stage:
                    state = LAND
                else:
                    state = DESCEND
            else:
                plan = build_timed_actuation(measure)
                execute(plan)
                reset_measurement()

    if state == DESCEND:
        send_vertical_velocity(-descent_speed)
        if reached_next_stage_height:
            state = ALIGN

    if state == LAND:
        send_land_once()
        if touchdown_confirmed or timeout:
            disarm_and_restore()
            break
```

这个伪代码说明了脚本的本质：它是一个带视觉观测的分段离散闭环控制器。

---

## 与知识库其他页面的关系

- 总览与传统 ROS2/PX4 精准降落架构见 [[topics/topic-precision-localization]]。
- ArUco、PnP、相机模型等基础见 [[concepts/concept-vision-geometry-foundations]]。
- 飞控模式、PX4 控制接口和 Offboard 概念见 [[entities/product-px4-autopilot]]。
- PID、MPC、控制基本概念见 [[concepts/concept-planning-control-foundations]] 和 [[concepts/concept-drone-control]]。

---

## 引用来源

- [1] [raw/precision-landing-mqtt-code.txt](../raw/precision-landing-mqtt-code.txt) — 实际精准降落脚本，包含 ArUco 检测、MQTT 虚拟摇杆控制、H.264 视频输入、分阶段状态机与安全收尾。
- [2] [[raw/project-precision-localization.md]] — 精准定位/精准降落项目原始技术资料。

## 变更记录

- 2026-06-30: 从桌面 `code.txt` 摄入实际精准降落代码，新增代码级解析页；重点拆解 MQTT 控制适配、ArUco 像素几何、分阶段状态机、定时摇杆修正、低空落地与异常恢复。

