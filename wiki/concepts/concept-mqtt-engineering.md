# MQTT 工程开发教程：从零基础到无人机遥测与控制

> **类型**: concept
> **创建时间**: 2026-06-30
> **最后更新**: 2026-06-30
> **标签**: #MQTT #物联网 #无人机 #遥测 #控制 #Python #工程

## 摘要

MQTT 是一种面向弱网络、低带宽、跨语言设备通信的发布/订阅协议。它特别适合无人机、机器人、边缘设备和云平台之间传递遥测、状态、控制命令与命令回复。

这篇教程面向零经验学习者。你不需要先懂物联网协议，只要知道“一个程序发消息，另一个程序收消息”。学完后，你应该能做到四件事：

- 用 Mosquitto 在本机跑通 MQTT Broker、发布者和订阅者。
- 用 Python Paho 写出可靠的 MQTT 客户端。
- 设计无人机遥测、命令、回复、控制权和安全主题。
- 看懂精准降落实际代码里的 `MqttAdapter` 为什么这样组织。

---

## 学习路线

| 阶段 | 目标 | 你要会什么 |
|------|------|------------|
| 0. 建立直觉 | 知道 MQTT 为什么存在 | Broker、Client、Topic、Message |
| 1. 跑通工具 | 本机能发一条消息、收一条消息 | `mosquitto`, `mosquitto_pub`, `mosquitto_sub` |
| 2. 写程序 | Python 能订阅、发布、重连 | Paho、JSON、回调、loop |
| 3. 懂协议 | 知道消息可靠性怎么选 | QoS、Retain、Will、Session |
| 4. 做工程 | 能设计设备主题和安全策略 | Topic 规范、ACL、TLS、超时、幂等 |
| 5. 用到无人机 | 能理解遥测/控制链路 | OSD、命令服务、回复、虚拟摇杆 |

最推荐的学习方式是：每一节先跑命令，再读解释，然后改一个参数观察现象。

---

## MQTT 解决什么问题

### 直接 HTTP 调用的问题

假设无人机、地面站、云平台之间都用 HTTP 直接互相请求：

```text
无人机 -> 云平台: 上传位置
云平台 -> 无人机: 发降落命令
地面站 -> 无人机: 发虚拟摇杆
无人机 -> 地面站: 返回执行结果
```

这会遇到几个工程问题：

- 设备经常在 NAT、4G/5G、校园网、内网里，云端不一定能直接访问设备。
- 设备网络会抖动，HTTP 请求失败后要自己写重试、排队和状态恢复。
- 接收者可能不止一个：地面站、日志服务、监控页面都想看同一份遥测。
- 控制命令需要明确回复，否则不知道命令是没收到、被拒绝，还是已经执行。

### MQTT 的核心思路

MQTT 用一个 Broker 做中转。所有设备都主动连 Broker：

```text
无人机 Client  ─┐
地面站 Client  ├── MQTT Broker ── 云端服务 Client
日志服务 Client ┘
```

发送方不直接关心谁接收，只把消息发布到某个 Topic。接收方订阅 Topic，Broker 负责把消息转发过去。

这带来三个好处：

- **解耦**：无人机只发布 `drone/001/osd`，地面站和日志服务都能订阅。
- **穿透性更好**：设备主动连 Broker，通常比云端反连设备更容易。
- **多语言**：Python、C++、Java、Go、Node.js 都有 MQTT 客户端。

---

## 协议模型

### Broker

Broker 是 MQTT 的消息服务器。常见 Broker：

- Eclipse Mosquitto：轻量，适合学习、边缘设备、小规模部署。
- EMQX：功能更完整，适合企业级集群、规则引擎、可视化运维。
- HiveMQ：商业生态较成熟。

初学阶段用 Mosquitto 最合适。

### Client

Client 是连接 Broker 的程序。无人机脚本、地面站、云端服务、测试命令行工具都可以是 Client。

每个 Client 应该有稳定的 `client_id`。不要让两台设备使用同一个 `client_id`，否则 Broker 通常会把旧连接踢下线。

### Topic

Topic 是消息地址，例如：

```text
drone/001/osd
drone/001/cmd/land
drone/001/reply/8f3a2c
```

Topic 只是字符串层级，不等于文件路径，也不自动拥有权限。权限要靠 Broker 的 ACL 配置。

### Message

Message 是发布到 Topic 的 payload。MQTT 不规定 payload 格式，可以是：

- 文本
- JSON
- Protobuf
- MessagePack
- 二进制图像片段

无人机遥测和控制建议初期用 JSON，因为可读、可调试。

### Session

Session 描述 Broker 是否要为离线 Client 保存订阅关系和排队消息。MQTT 3.1.1 常说 `clean_session`，MQTT 5 拆成 `clean_start` 和 `session_expiry_interval`。

初学建议：

- 实时遥测：使用干净会话，不保存离线消息。
- 可靠命令：不要盲目依赖离线排队，最好用在线状态、命令编号、超时和回复机制自己兜底。

---

## 从零跑通 Mosquitto

### 1. 安装 Broker 和命令行客户端

Ubuntu：

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

查看服务：

```bash
systemctl status mosquitto
```

如果只是本机学习，也可以手动前台启动：

```bash
mosquitto -v
```

`-v` 会输出连接、订阅、发布等日志，适合学习。

### 2. 开两个终端做最小实验

终端 A 订阅：

```bash
mosquitto_sub -h localhost -t 'demo/hello' -v
```

终端 B 发布：

```bash
mosquitto_pub -h localhost -t 'demo/hello' -m 'hello mqtt'
```

终端 A 应该看到：

```text
demo/hello hello mqtt
```

这就是 MQTT 的最小闭环。

### 3. 订阅通配符

订阅一个无人机所有状态：

```bash
mosquitto_sub -h localhost -t 'drone/001/+/+' -v
```

发布两条消息：

```bash
mosquitto_pub -h localhost -t 'drone/001/state/battery' -m '{"percent":87}'
mosquitto_pub -h localhost -t 'drone/001/state/gps' -m '{"lat":30.1,"lon":120.2}'
```

`+` 匹配一个层级，`#` 匹配剩余所有层级：

```bash
mosquitto_sub -h localhost -t 'drone/001/#' -v
```

工程建议：测试时可以用 `#`，生产代码尽量订阅明确范围，避免收到无关消息。

---

## Topic 设计规则

Topic 设计决定系统后期是否容易维护。不要随手起名。

### 推荐结构

无人机系统可以采用：

```text
drone/{sn}/telemetry/osd
drone/{sn}/telemetry/battery
drone/{sn}/telemetry/gps
drone/{sn}/state/fly_mode
drone/{sn}/state/control_authority
drone/{sn}/cmd/land
drone/{sn}/cmd/joystick
drone/{sn}/cmd/gimbal
drone/{sn}/reply/{request_id}
drone/{sn}/event/warning
drone/{sn}/event/error
```

含义：

| 层级 | 示例 | 含义 |
|------|------|------|
| 系统域 | `drone` | 设备类型或业务域 |
| 设备 ID | `001` | 无人机序列号、SN 或逻辑编号 |
| 消息类别 | `telemetry`, `state`, `cmd`, `reply`, `event` | 区分数据方向和用途 |
| 具体资源 | `osd`, `land`, `joystick` | 具体状态或命令 |

### 命名原则

- 全部小写，少用空格和中文。
- 用 `/` 表示层级，不要把所有信息塞进一个长字符串。
- 上行遥测和下行命令分开。
- 命令必须有 `request_id`，回复必须能对应回原命令。
- 控制类 Topic 要单独做 ACL，不能和只读遥测放在一起。

### 不推荐的 Topic

```text
message
test
drone001
control
uav_data
topic1
```

这些名字的问题是：看不出方向、设备、数据类型和权限边界。

---

## QoS、Retain、Will、Session

### QoS 0：最多一次

QoS 0 是“发出去就不管”。消息可能丢，但开销最低。

适合：

- 高频 OSD
- 姿态角
- 视频统计
- 调试日志

不适合：

- 起飞
- 降落
- 解锁
- 切模式

### QoS 1：至少一次

QoS 1 会确认投递，但可能重复。接收端必须能处理重复消息。

适合：

- 控制命令
- 参数设置
- 任务状态
- 告警事件

工程要点：命令 payload 里放 `request_id`，接收端记录已处理请求，避免重复执行。

### QoS 2：刚好一次

QoS 2 协议层保证一次投递，握手更重。大多数无人机控制场景不用它，除非你非常清楚代价和值得性。

### Retain：保留最后一条

Retain 表示 Broker 保存这个 Topic 的最后一条消息。新订阅者一连上就能收到。

适合：

- 设备在线状态
- 当前配置版本
- 最新任务概要

不适合：

- 摇杆控制
- 起飞/降落命令
- 一次性动作命令

危险例子：

```bash
mosquitto_pub -r -t 'drone/001/cmd/land' -m '{"request_id":"old","action":"land"}'
```

如果这个命令被 retain，新客户端订阅后可能收到旧降落命令。控制命令不要 retain。

清除 retained 消息：

```bash
mosquitto_pub -r -n -t 'drone/001/cmd/land'
```

### Will：异常离线遗嘱

Will 是客户端连接时告诉 Broker 的“如果我异常断开，请帮我发布这条消息”。

适合做在线状态：

```text
drone/001/state/online = false
```

正常上线时发布：

```text
drone/001/state/online = true
```

异常掉线时 Broker 自动发布 `false`。

### Session：离线期间要不要保存

实时控制系统不要把 Session 当成可靠控制的唯一保障。原因是：

- 离线期间排队的控制命令可能过期。
- 网络恢复后旧命令可能突然执行。
- 对飞行器来说，过期命令比丢命令更危险。

建议：

- 命令 payload 带 `timestamp` 和 `expires_ms`。
- 接收端检查过期时间。
- 所有危险命令都需要回复。

---

## Paho Python 最小程序

安装：

```bash
python3 -m pip install paho-mqtt
```

### 订阅程序

保存为 `sub.py`：

```python
import json
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC = "drone/001/telemetry/osd"


def on_connect(client, userdata, flags, reason_code, properties):
    print("connected:", reason_code)
    client.subscribe(TOPIC, qos=0)


def on_message(client, userdata, msg):
    text = msg.payload.decode("utf-8")
    print(msg.topic, text)
    try:
        data = json.loads(text)
        print("height:", data.get("height"))
    except json.JSONDecodeError:
        print("payload is not json")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="demo-sub")
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=30)
client.loop_forever()
```

### 发布程序

保存为 `pub.py`：

```python
import json
import time
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC = "drone/001/telemetry/osd"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="demo-pub")
client.connect(BROKER, PORT, keepalive=30)
client.loop_start()

try:
    while True:
        payload = {
            "sn": "001",
            "height": 12.3,
            "battery": 87,
            "timestamp": time.time(),
        }
        client.publish(TOPIC, json.dumps(payload), qos=0, retain=False)
        print("published", payload)
        time.sleep(1.0)
finally:
    client.loop_stop()
    client.disconnect()
```

运行：

```bash
python3 sub.py
python3 pub.py
```

如果你的 Paho 版本较老，没有 `CallbackAPIVersion.VERSION2`，升级 Paho，或者按旧版回调签名改写。工程项目建议固定依赖版本，避免线上环境和开发机行为不一致。

---

## 工程化客户端

最小程序能跑，但还不能用于飞行器。工程代码至少要处理：

- 连接失败
- 重连
- 命令编号
- 回复超时
- JSON 解析失败
- 重复命令
- 退出时清理控制状态

下面是一个简化的命令客户端骨架：

```python
import json
import time
import uuid
import threading
import paho.mqtt.client as mqtt


class DroneMqttClient:
    def __init__(self, broker, port, sn):
        self.broker = broker
        self.port = port
        self.sn = sn
        self.connected = threading.Event()
        self.pending = {}
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"ground-control-{sn}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def connect(self):
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(timeout=5):
            raise TimeoutError("MQTT connect timeout")

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print("connected:", reason_code)
        self.connected.set()
        client.subscribe(f"drone/{self.sn}/reply/+", qos=1)
        client.subscribe(f"drone/{self.sn}/telemetry/osd", qos=0)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        print("disconnected:", reason_code)
        self.connected.clear()

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            print("bad json:", msg.topic, msg.payload)
            return

        if msg.topic.startswith(f"drone/{self.sn}/reply/"):
            request_id = msg.topic.rsplit("/", 1)[-1]
            event = self.pending.get(request_id)
            if event:
                event["reply"] = data
                event["done"].set()
            return

        if msg.topic == f"drone/{self.sn}/telemetry/osd":
            print("osd:", data)

    def send_command(self, name, body, timeout=3.0):
        request_id = uuid.uuid4().hex
        topic = f"drone/{self.sn}/cmd/{name}"
        payload = {
            "request_id": request_id,
            "timestamp": time.time(),
            "expires_ms": int(timeout * 1000),
            "body": body,
        }
        done = threading.Event()
        self.pending[request_id] = {"done": done, "reply": None}
        self.client.publish(topic, json.dumps(payload), qos=1, retain=False)

        if not done.wait(timeout=timeout):
            self.pending.pop(request_id, None)
            raise TimeoutError(f"command {name} timeout")

        reply = self.pending.pop(request_id)["reply"]
        if not reply.get("ok", False):
            raise RuntimeError(f"command rejected: {reply}")
        return reply
```

这个例子还不是完整飞控系统，但它已经体现了几个关键习惯：

- 命令带 `request_id`。
- 回复用 `drone/{sn}/reply/{request_id}` 对齐。
- QoS 1 用于命令，但接收端仍要防重复。
- 控制命令不 retain。
- 每个命令都有超时。

---

## 无人机遥测与控制主题设计

### 遥测上行

无人机发布：

```text
drone/001/telemetry/osd
drone/001/telemetry/gps
drone/001/telemetry/battery
drone/001/telemetry/attitude
drone/001/telemetry/link
```

示例 payload：

```json
{
  "sn": "001",
  "timestamp": 1782800000.123,
  "height": 12.4,
  "radar_height": 1.8,
  "fly_mode": "GPS_NORMAL",
  "battery_percent": 82,
  "latitude": 30.1234567,
  "longitude": 120.1234567,
  "yaw_deg": 86.2
}
```

遥测通常 QoS 0，因为新数据会不断覆盖旧数据。

### 控制下行

地面站或算法服务发布：

```text
drone/001/cmd/takeoff
drone/001/cmd/land
drone/001/cmd/joystick
drone/001/cmd/set_mode
drone/001/cmd/gimbal
```

虚拟摇杆 payload：

```json
{
  "request_id": "a8c4",
  "timestamp": 1782800001.000,
  "expires_ms": 300,
  "body": {
    "x": 0.0,
    "y": 0.12,
    "z": -0.08,
    "yaw": 0.0
  }
}
```

摇杆类控制通常是高频短有效期命令。即使使用 QoS 0，也要高频刷新并设置超时；如果使用 QoS 1，也不能执行过期摇杆。

### 命令回复

无人机回复：

```text
drone/001/reply/a8c4
```

payload：

```json
{
  "request_id": "a8c4",
  "ok": true,
  "code": 0,
  "message": "accepted",
  "timestamp": 1782800001.035
}
```

命令回复的作用不是“看起来完整”，而是解决三个问题：

- 发布方知道 Broker 收到不等于无人机执行了。
- 无人机可以拒绝危险命令。
- 调试时能定位是链路问题、权限问题、模式问题还是飞控拒绝。

### 控制权主题

无人机控制必须有控制权概念。否则多个客户端同时发命令，会出现抢控制。

可以设计：

```text
drone/001/state/control_owner
drone/001/cmd/acquire_control
drone/001/cmd/release_control
```

控制命令 payload 中加入：

```json
{
  "owner": "precision-landing-service",
  "lease_ms": 5000
}
```

无人机侧只接受当前 owner 的控制命令。owner 过期后自动释放。

---

## 和精准降落代码的映射

你的精准降落实际代码里，`MqttAdapter` 承担的就是“把控制器输出变成 MQTT 工程协议”的责任。

可以按这张表理解：

| 教程概念 | 精准降落代码中的角色 |
|----------|----------------------|
| Client | `MqttAdapter` 内部 MQTT 客户端 |
| Broker | 无人机/平台连接的 MQTT 服务 |
| 遥测 Topic | OSD、飞行模式、高度、摇杆状态订阅 |
| 命令 Topic | land、lock、virtual joystick、PVA、模式切换 |
| Reply | 命令回复、拒绝、超时判断 |
| QoS/重试 | 控制命令的发送确认和响应等待 |
| Session/状态恢复 | 启动前状态快照、退出时恢复摇杆/PVA/模式 |
| 安全门控 | LAND 状态、启动保护、自动模式检查、异常收尾 |

精准降落代码没有把 MQTT 当作简单的 `publish()`，而是把它做成一层适配器。原因是视觉控制器只应该关心“此刻要往哪里修正”，不应该直接关心 Broker、Topic、命令回复、摇杆死区和飞控模式。

这就是工程边界：

```text
ArucoLandingController
  负责：检测、估计、状态机、控制意图

MqttAdapter
  负责：连接、订阅、命令协议、飞控状态、发送门控、安全恢复
```

如果以后把控制链路从 MQTT 换成 ROS2、MAVSDK 或 MAVLink，理想情况下主要替换适配层，而不是重写视觉状态机。

---

## 安全与部署

### 不要把匿名 Broker 暴露到公网

学习阶段可以：

```conf
listener 1883
allow_anonymous true
```

生产环境不要这样做。至少要：

```conf
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl
```

创建账号：

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd ground
sudo mosquitto_passwd /etc/mosquitto/passwd drone001
```

ACL 示例：

```conf
user drone001
topic readwrite drone/001/telemetry/#
topic readwrite drone/001/state/#
topic read drone/001/cmd/#
topic write drone/001/reply/#

user ground
topic read drone/001/telemetry/#
topic read drone/001/state/#
topic write drone/001/cmd/#
topic read drone/001/reply/#
```

真实系统还要更细：普通监控账号只能读，控制账号才能写 `cmd/#`。

### TLS

如果 Broker 跨公网，必须考虑 TLS。否则账号密码和控制命令都可能明文暴露。

典型配置方向：

```conf
listener 8883
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key
require_certificate false
```

初学阶段先理解账号、ACL、Topic 权限，再上 TLS。不要一开始把所有安全机制混在一起调。

### 部署检查

部署前检查：

- Broker 是否开机自启。
- 防火墙是否只放行必要端口。
- 匿名访问是否关闭。
- 控制 Topic 是否只允许控制服务写。
- retained 控制命令是否清理。
- 客户端是否有唯一 client_id。
- 断线后飞控是否进入安全状态。

---

## 调试清单

### 连不上 Broker

检查：

```bash
ping <broker-ip>
nc -vz <broker-ip> 1883
mosquitto_sub -h <broker-ip> -t '$SYS/#' -v
```

常见原因：

- Broker 没启动。
- 防火墙没放行。
- 监听只绑定了 localhost。
- 用户名密码错误。
- 云服务器安全组没开放端口。

### 收不到消息

检查：

```bash
mosquitto_sub -h <broker-ip> -t 'drone/001/#' -v
```

常见原因：

- Topic 拼错。
- 发布到 `drone/1/osd`，订阅的是 `drone/001/osd`。
- 订阅通配符层级不匹配。
- ACL 不允许读。
- 客户端还没连接成功就 publish。

### 消息重复

常见原因：

- 使用 QoS 1，网络抖动导致重投递。
- 代码重复订阅。
- 多个客户端使用同一个 client_id 被反复踢下线重连。

处理：

- 命令加 `request_id`。
- 接收端做幂等。
- 检查 client_id 唯一性。

### 收到旧消息

常见原因：

- Topic 上有 retained 消息。
- 使用持久 session，离线消息恢复后继续投递。

处理：

```bash
mosquitto_pub -h <broker-ip> -r -n -t 'drone/001/cmd/land'
```

控制命令不要 retain。

### 摇杆控制没反应

检查：

- 飞控是否允许虚拟摇杆。
- 是否拿到控制权。
- 当前模式是否允许外部控制。
- 摇杆值是否低于最小生效阈值。
- 指令是否过期。
- 坐标轴方向是否反了。

这正是精准降落代码里要处理 `min effective joystick`、模式状态和异常恢复的原因。

---

## 练习项目

### 练习 1：本机消息总线

目标：本机启动 Mosquitto，一个终端发布，一个终端订阅。

验收：

- 能看到 `demo/hello hello mqtt`。
- 能解释 `-t`、`-m`、`-h` 的含义。

### 练习 2：无人机 OSD 模拟器

目标：写一个 Python 程序每秒发布高度、电量、飞行模式。

验收：

- `mosquitto_sub -t 'drone/001/telemetry/osd' -v` 能看到 JSON。
- payload 里包含 `timestamp`。

### 练习 3：命令与回复

目标：写一个地面站发布 `land` 命令，一个无人机模拟器回复 `accepted`。

验收：

- 命令带 `request_id`。
- 回复 Topic 包含同一个 `request_id`。
- 地面站能处理超时。

### 练习 4：控制安全

目标：给命令加 `expires_ms`，模拟延迟后拒绝过期命令。

验收：

- 过期命令不会执行。
- 回复中说明 `expired`。

### 练习 5：映射精准降落代码

目标：打开 [[topics/topic-precision-localization-code]]，把 `MqttAdapter` 中的订阅、发布、命令回复、状态恢复逐项标注到本页概念。

验收：

- 能说出 `MqttAdapter` 和 `ArucoLandingController` 的边界。
- 能解释为什么 LAND、lock、joystick 不应该当成普通日志消息处理。

---

## 常见误区

### 误区 1：QoS 1 等于命令一定安全执行

QoS 1 只保证协议层至少投递一次，不保证业务安全。无人机命令还需要权限、模式检查、过期时间、幂等和回复。

### 误区 2：Retain 很方便，所以所有消息都 retain

Retain 适合状态，不适合动作。保留一条旧降落命令是危险设计。

### 误区 3：Topic 只是字符串，后面再整理

Topic 是系统接口。一旦设备、云端和地面站都依赖它，后期改名成本很高。

### 误区 4：能 publish 就算 MQTT 学会了

真正的工程能力是：断线能恢复，命令有回复，权限能隔离，旧消息不会误触发，日志能定位问题。

---

## 相关页面

- [[topics/topic-precision-localization-code]] — 精准降落实际代码解析
- [[topics/topic-precision-localization]] — 无人机精准定位系统
- [[entities/product-ros2]] — ROS2 工程开发教程
- [[concepts/concept-drone-control]] — 无人机飞控与控制
- [[concepts/method-model-deployment]] — 模型部署与推理加速

---

## 引用来源

- [1] [MQTT.org: Getting started](https://mqtt.org/getting-started/) — MQTT 入门与协议入口。
- [2] [OASIS MQTT Version 5.0 Specification](https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html) — MQTT 5.0 官方规范。
- [3] [Eclipse Mosquitto Documentation](https://mosquitto.org/documentation/) — Mosquitto Broker 与命令行工具文档。
- [4] [Eclipse Paho Python Client](https://eclipse.dev/paho/index.php?page=clients/python/index.php) — Python MQTT 客户端文档。
- [5] [[topics/topic-precision-localization-code]] — 本知识库精准降落实际代码解析。

---

## 变更记录

- 2026-06-30: 新增 MQTT 从零基础到无人机遥测与控制工程教程，串联 Mosquitto、Paho Python、Topic 设计、QoS、Retain、Will、安全部署与精准降落代码中的 `MqttAdapter`。
