#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function
"""
已将常用现场参数内置为默认值，日常运行通常只需要传：
  --input, --preview, --invert-x
如需改无人机编号/主机，也只需要额外传 --product-id / --mqtt-host。
"""

# =============================================================================
# 初学者阅读指南
# =============================================================================
# 警告：这不是纯算法演示。默认 MQTT 地址和 product_id 可能连接真实设备；
# 没有拆桨、系留、急停和人工接管方案时，不要直接运行它控制无人机。
#
# 数据链：视频 -> ArUco -> 像素误差 -> 水平误差（米） -> 状态机
# -> 期望速度 -> 虚拟摇杆/速度协议 -> MQTT -> 飞控。
#
# 本脚本不是 PID，而是“悬停采样 -> 平均误差 -> 定时打杆 -> 再次测量”控制。
# 推荐阅读：数据类 -> detect() -> build_timed_actuation_plan() -> update()
# -> send_velocity() -> run_with_interrupt_cleanup()。
#
# =============================================================================
# 第一章：先建立完整的控制系统地图
# =============================================================================
#
# 1. 本程序不直接控制电机。姿态环、角速度环和电机分配仍由飞控完成。
# 本程序属于外层引导：观察降落标志，再要求飞控产生水平或垂直速度。
#
#   飞控内环：期望速度/杆量 -> 姿态与电机 -> 无人机真实运动
#   Python外环：相机画面 -> ArUco偏差 -> 速度命令 -> 飞控
#
# 2. 外环使用两类反馈。
# 视觉反馈给出目标中心、像素边长和是否检测成功；OSD 遥测给出高度、
# 垂直速度、飞行模式以及摇杆/PVA 控制权。反馈过期会使决策落后于飞机。
#
# 3. 重要坐标和单位。
# 图像 u 向右为正、v 向下为正，单位 px；vx/vy 是水平速度，单位 m/s；
# vz 正值上升、负值下降；yaw_rate 是 degree/s；协议摇杆是无量纲整数。
#
# 图像向右不必然等于飞机向右。相机安装、机体系和协议方向可能不同，代码
# 要经过 swap_xy、invert_x/y、图像 yaw 补偿和摇杆 sign。真机前必须拆桨逐轴
# 验证方向，否则负反馈会变成正反馈，误差越修越大。
#
# 4. 为什么不是逐帧 PID？
# 虚拟摇杆存在死区，小杆量可能完全不动。代码采用：悬停采样 -> 平均误差
# -> 计算越过死区的杆量和保持时间 -> 停止 -> 再测量。这是离散的
# measure-actuate 控制。优点是适应死区，缺点是动作期间不是连续视觉闭环。
#
# 5. 安全边界。
# 学习版的可执行语句与现场版相同。运行会连接默认 broker，并可能发送
# setFlyMode、setJoystickState、land 和 disarm。离线学习只做阅读、AST 和编译。

import argparse
import json
import os
import sys
import time
import uuid
import threading
import subprocess

import numpy as np
import cv2

try:
    import cv2.aruco as aruco
except Exception:
    aruco = None

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None


class ControlCommand(object):
    # 控制器内部统一使用速度命令，不关心底层使用哪一种飞控协议。
    # vx/vy 是水平速度（m/s）；vz 正值上升、负值下降；yaw_rate 是偏航角速度。
    def __init__(self, vx=0.0, vy=0.0, vz=0.0, yaw_rate=0.0):
        self.vx = float(vx)
        self.vy = float(vy)
        self.vz = float(vz)
        self.yaw_rate = float(yaw_rate)


class DetectionResult(object):
    # 单帧检测结果：是否发现目标、中心位置、像素边长、四角点和全部 ID。
    def __init__(self):
        self.detected = False
        self.marker_center = None
        self.pixel_width = 0.0
        self.marker_corners = None
        self.ids = None


class MqttAdapter(object):
    #
    # -------------------------------------------------------------------------
    # MQTT 初学者补课
    # -------------------------------------------------------------------------
    # MQTT 是发布/订阅协议。本程序向 broker 的 topic 发布 JSON，机载程序订阅后
    # 解释 method/data。services 是命令，osd 是周期遥测，services_reply 是结果。
    # publish 成功只说明消息进入网络层，不说明飞机完成动作，重要命令还要看 reply。
    #
    # 请求与回复为何需要 tid？网络是异步的，连续发送 A、B 后回复可能稍晚到达。
    # 每条请求生成唯一 tid，回调存入 _replies_by_tid[tid]；wait_reply 只取自己的
    # tid，避免把 B 的回复误认为 A。bid 是协议业务标识，不参与这里的等待匹配。
    #
    # 线程模型：主线程处理视频和控制；paho loop_start 建立网络线程执行回调；
    # Condition 保护回复字典，并让主线程睡眠等待。relative_alt、fly_mode 等由
    # 网络线程写、主线程读，它们不是事务快照，可能出现新高度配旧模式的短暂组合。
    #
    # 控制权并不等于“MQTT 已连接”。命令生效还要求飞行模式允许、joystickState
    # 已开启，非 joystick 协议还要 PVA 开启，并且飞机未进入 RTL/LAND 等自主模式。
    # initialize_for_run 先释放残留控制权再重新申请；运行中若别的控制源切入自主
    # 模式，本程序停止运动命令，避免两个控制器争夺飞机。
    #
    # capture_startup_state 保存进入前状态。退出顺序是零命令 -> 关闭控制器 ->
    # 恢复模式。直接断开 MQTT 可能使最后一条非零命令在飞控超时前继续生效。
    #
    # 速度到摇杆的换算：
    #   stick = sign * joystick_max * requested_speed / allowed_speed
    # 例：max=300，水平上限 2.0 m/s，请求 0.4 m/s，杆量绝对值=300*0.4/2=60。
    # 若 pitch_sign=-1，最终 x=-60。协议杆量是无量纲整数，不再具有 m/s 单位。
    #
    # 现场死区约 150，60 可能完全不动。hold 模式将它抬到 170 并保持最短时间；
    # pulse 模式使用 duty=abs(raw)/effective。上例 duty=60/170≈0.353；周期 0.4 s
    # 时开启约 0.141 s，时间平均杆量约为 60。on_min/on_max 防止脉冲过短或过长。
    # force=True 用于退出零命令，会清空补偿状态，否则“停下”的 0 可能仍被 hold
    # 替换为 170，形成危险残留运动。
    #
    # 控制 method：setJoystickValue 发整数杆量；velocityCtrl 发 m/s；targetCtrl
    # 还带加速度目标和限制；hold/brake 停止运动；land 交给飞控最终降落；disarm
    # 停止电机，只能在可靠接地后执行。
    #
    # 发送有两层限频：maybe_send_command 管业务频率、帧间隔和变化阈值；
    # send_velocity 用 command_keepalive 去重相同 payload。相同命令到期仍重发，
    # 防止飞控因长时间收不到外部命令而退出控制。
    #
    # QoS=0 延迟低但可能丢包；QoS=1 至少一次但可能重复。两者都不是安全保证，
    # 网络中断后的行为必须由飞控 failsafe 兜底。
    # MQTT 适配层负责通信和飞控协议转换。控制器只提交 ControlCommand，
    # 本类再转换成 joystick、velocityCtrl 或 targetCtrl 消息。
    def __init__(self, args):
        self.enable = bool(args.mqtt_enable)
        self.product_id = args.product_id
        # services 是命令入口；osd 是遥测；services_reply 是执行结果。
        # product_id 配错可能把命令路由到错误设备。
        self.pub_topic = 'qyhk/onboard/flight/thing/product/{}/services'.format(self.product_id)
        self.osd_topic = 'qyhk/onboard/thing/product/{}/osd'.format(self.product_id)
        self.services_reply_topic = 'qyhk/onboard/flight/thing/product/{}/services_reply'.format(self.product_id)
        self.client = None
        self.connected = False
        self.last_osd = None
        # 这些反馈由 MQTT 网络线程异步更新；None 表示尚未收到有效遥测。
        self.relative_alt = None
        self.vertical_speed = None
        self.fly_mode = None
        self.state_type = None
        self.joystick_state = None
        self.pva_state = None
        self._args = args
        # Condition 配合 tid，将异步回复交给正在等待该请求的主线程。
        self._reply_cond = threading.Condition()
        self._replies_by_tid = {}
        self._last_reply_by_method = {}
        self._last_velocity_sig = None
        self._last_velocity_send_ts = 0.0
        self._ready_warn_ts = 0.0
        self._last_recover_ts = 0.0
        self._recent_motion_reject_ts = 0.0
        self._recent_motion_reject_code = None
        self._recent_motion_reject_msg = None
        self._manual_limits_applied = False
        self._manual_limits_signature = None
        self._startup_state_captured = False
        self._startup_fly_mode = None
        self._startup_joystick_state = None
        self._startup_pva_state = None
        self._auto_mode_warn_ts = 0.0
        # 记录死区补偿状态，避免有效杆量刚发出就被下一帧零值覆盖。
        self._axis_effective_state = {k: {'hold_until': 0.0, 'sign': 0, 'value': 0} for k in ('x', 'y', 'z')}

        if self.enable:
            if mqtt is None:
                raise RuntimeError('paho-mqtt 未安装，请先执行: pip3 install paho-mqtt')
            self.client = mqtt.Client(client_id=args.mqtt_client_id or ('aruco_landing_' + uuid.uuid4().hex[:8]))
            if args.mqtt_username:
                self.client.username_pw_set(args.mqtt_username, args.mqtt_password or '')
            self.keepalive = int(args.mqtt_keepalive) if args.mqtt_keepalive else 60
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect

    @staticmethod
    def _clamp(v, lo, hi):
        return max(lo, min(hi, float(v)))

    def _on_connect(self, client, userdata, flags, rc):
        # rc == 0 才成功；在回调中订阅可保证重连后恢复订阅。
        self.connected = (rc == 0)
        print('[MQTT] connected rc={}'.format(rc))
        if self._args.mqtt_subscribe_osd:
            client.subscribe(self.osd_topic, qos=0)
            print('[MQTT] subscribed OSD: {}'.format(self.osd_topic))
        if self._args.mqtt_subscribe_reply or self._args.mqtt_wait_reply:
            client.subscribe(self.services_reply_topic, qos=0)
            print('[MQTT] subscribed reply: {}'.format(self.services_reply_topic))

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        print('[MQTT] disconnected rc={}'.format(rc))

    def _remember_reply(self, data):
        # 保存最近回复，并识别飞控是否拒绝运动命令。
        method = data.get('method')
        if method:
            self._last_reply_by_method[method] = data
            try:
                result = data.get('data', {}).get('result')
                msg = data.get('data', {}).get('msg', '')
            except Exception:
                result = None
                msg = ''
            if method in ('velocityCtrl', 'targetCtrl', 'setJoystickValue') and result not in (0, None):
                self._recent_motion_reject_ts = time.time()
                self._recent_motion_reject_code = result
                self._recent_motion_reject_msg = msg
                print('[MQTT_WARN] motion control rejected: method={} code={} msg={}'.format(method, result, msg))

    def _on_message(self, client, userdata, msg):
        # MQTT 网络线程入口，只解析和更新状态，不在此运行视觉算法。
        try:
            payload = msg.payload.decode('utf-8', errors='ignore')
            data = json.loads(payload)
        except Exception as e:
            print('[MQTT] message parse error on {}: {}'.format(msg.topic, e))
            return

        if msg.topic == self.osd_topic:
            # OSD 是反馈；控制状态未就绪时，飞控不会接受外部运动命令。
            self.last_osd = data
            try:
                fd = data.get('data', {}).get('flightData', {})
                sd = data.get('data', {}).get('stateData', {})
                posi = fd.get('posi', {}) or {}
                self.relative_alt = posi.get('relativeAlt', self.relative_alt)
                self.vertical_speed = fd.get('verticalSpeed', self.vertical_speed)
                self.fly_mode = fd.get('flyMode', self.fly_mode)
                self.state_type = sd.get('stateType', self.state_type)
                self.joystick_state = sd.get('joystickState', self.joystick_state)
                self.pva_state = sd.get('pvaControllerState', self.pva_state)
            except Exception:
                pass
            return

        if msg.topic == self.services_reply_topic:
            # tid 是事务编号；notify_all() 唤醒 wait_reply() 的等待线程。
            with self._reply_cond:
                tid = data.get('tid')
                if tid:
                    self._replies_by_tid[tid] = data
                    self._reply_cond.notify_all()
            self._remember_reply(data)
            print('[MQTT_REPLY] {}'.format(json.dumps(data, ensure_ascii=False)))

    def connect(self):
        if not self.enable:
            return
        self.client.connect(self._args.mqtt_host, int(self._args.mqtt_port), keepalive=self.keepalive)
        self.client.loop_start()
        deadline = time.time() + 5.0
        while time.time() < deadline and not self.connected:
            time.sleep(0.05)
        if not self.connected:
            raise RuntimeError('MQTT 连接失败: {}:{}'.format(self._args.mqtt_host, self._args.mqtt_port))

    def close(self):
        if self.client is not None:
            try:
                self.client.loop_stop()
            except Exception:
                pass
            try:
                self.client.disconnect()
            except Exception:
                pass

    def make_msg(self, method, data=None):
        # tid 标识请求，bid 标识业务消息，timestamp 使用 Unix 毫秒时间。
        msg = {
            'tid': uuid.uuid4().hex,
            'bid': uuid.uuid4().hex,
            'method': method,
            'timestamp': int(time.time() * 1000),
        }
        if data is not None:
            msg['data'] = data
        return msg

    def wait_reply(self, tid, timeout=None):
        # 循环等待可处理无关消息唤醒和线程伪唤醒。
        timeout = float(timeout if timeout is not None else self._args.mqtt_reply_timeout)
        if timeout <= 0:
            return None
        deadline = time.time() + timeout
        with self._reply_cond:
            while time.time() < deadline:
                if tid in self._replies_by_tid:
                    return self._replies_by_tid.pop(tid, None)
                self._reply_cond.wait(min(0.05, max(0.0, deadline - time.time())))
        return None

    def publish_method(self, method, data=None, wait_reply=False, quiet=False):
        # MQTT QoS 不代表飞控执行成功；实际结果仍要看 reply.result。
        msg = self.make_msg(method, data)
        line = json.dumps(msg, ensure_ascii=False)
        if not quiet:
            print('[MQTT_CMD] topic={} payload={}'.format(self.pub_topic, line))
        if self.enable:
            info = self.client.publish(self.pub_topic, line, qos=int(self._args.mqtt_qos), retain=False)
            if int(self._args.mqtt_qos) > 0:
                try:
                    info.wait_for_publish(timeout=1.0)
                except Exception:
                    pass
        if wait_reply and self.enable and (self._args.mqtt_subscribe_reply or self._args.mqtt_wait_reply):
            reply = self.wait_reply(msg['tid'])
            if reply is None:
                print('[MQTT_WARN] {} reply timeout'.format(method))
                return msg, None
            try:
                result = reply.get('data', {}).get('result')
                rmsg = reply.get('data', {}).get('msg', '')
                if result not in (0, None):
                    print('[MQTT_WARN] {} reply result={} msg={}'.format(method, result, rmsg))
            except Exception:
                pass
            return msg, reply
        return msg, None

    def get_last_reply(self, method):
        return self._last_reply_by_method.get(method)

    def _reply_ok(self, reply):
        if reply is None:
            return False
        try:
            return reply.get('data', {}).get('result') in (0, None)
        except Exception:
            return False

    def capture_startup_state(self, timeout=1.0):
        # 夺取控制权前保存状态，退出时尽量恢复启动前的模式。
        if self._startup_state_captured:
            return
        deadline = time.time() + float(timeout)
        if self._args.mqtt_subscribe_osd:
            while time.time() < deadline:
                if self.fly_mode is not None or self.joystick_state is not None or self.pva_state is not None:
                    break
                time.sleep(0.05)
        self._startup_fly_mode = self.fly_mode
        self._startup_joystick_state = self.joystick_state
        self._startup_pva_state = self.pva_state
        self._startup_state_captured = True
        print('[MQTT] startup snapshot: fly_mode={} joystick_state={} pva_state={}'.format(
            self._startup_fly_mode, self._startup_joystick_state, self._startup_pva_state))

    def _desired_exit_fly_mode(self, args):
        if self._startup_fly_mode is not None and str(self._startup_fly_mode).strip() != '':
            return self._startup_fly_mode
        return args.interrupt_restore_fly_mode

    def _desired_exit_joystick_state(self):
        if self._startup_joystick_state in (0, 1):
            return int(self._startup_joystick_state)
        return 0

    def _desired_exit_pva_state(self):
        if self._startup_pva_state in (0, 1):
            return int(self._startup_pva_state)
        return 0

    def uses_joystick_control(self, args=None):
        cfg = args if args is not None else self._args
        return str(getattr(cfg, 'control_method', 'joystick')).strip().lower() == 'joystick'

    def _sanitize_setup_args(self, args):
        # 给速度和倾角加硬边界以防误输入；不代表上限适合所有机型。
        args.manual_hor_spd_max = self._clamp(args.manual_hor_spd_max, 0.1, 25.0)
        args.manual_cli_spd_max = self._clamp(args.manual_cli_spd_max, 0.1, 8.0)
        args.manual_land_spd_max = self._clamp(args.manual_land_spd_max, 0.2, 5.0)
        args.tilt_angle = self._clamp(args.tilt_angle, 1.0, 89.0)
        args.yaw_spd_max = self._clamp(args.yaw_spd_max, 1.0, 180.0)
        args.land_speed = self._clamp(args.land_speed, 0.2, 5.0)
        args.land_ground_speed = self._clamp(args.land_ground_speed, 0.2, 0.6)
        args.precision_land_error = self._clamp(args.precision_land_error, 0.05, 1.0)

    def normalize_fly_mode(self, mode):
        # 将不同固件、中英文模式名称统一为少数内部枚举。
        if mode is None:
            return None
        s = str(mode).strip().lower()
        s_compact = s.replace(' ', '')
        mapping = {
            'posctl': 'posctl',
            'position': 'posctl',
            'positionhold': 'posctl',
            '定点': 'posctl',
            '定点模式': 'posctl',
            '自动定点': 'posctl',
            '姿态': 'attitude',
            '姿态模式': 'attitude',
            'attitude': 'attitude',
            'hold': 'hold',
            '悬停': 'hold',
            '自动悬停': 'hold',
            'autohover': 'hold',
            'rtl': 'rtl',
            '返航': 'rtl',
            '自动返航': 'rtl',
            'autortl': 'rtl',
            'land': 'land',
            '降落': 'land',
            '自动降落': 'land',
            'autoland': 'land',
            'takeoff': 'takeoff',
            '起飞': 'takeoff',
            '自动起飞': 'takeoff',
            'autotakeoff': 'takeoff',
            'point': 'point',
            '指点': 'point',
            '指点飞行': 'point',
        }
        if s_compact in mapping:
            return mapping[s_compact]
        contains_rules = [
            (('rtl', '返航'), 'rtl'),
            (('land', '降落'), 'land'),
            (('takeoff', '起飞'), 'takeoff'),
            (('point', '指点'), 'point'),
            (('attitude', '姿态'), 'attitude'),
            (('posctl', 'position', '定点'), 'posctl'),
            (('hold', '悬停'), 'hold'),
        ]
        for keys, normalized in contains_rules:
            if any(k in s_compact for k in keys):
                return normalized
        return s_compact

    def is_autonomous_mode(self, mode=None):
        # RTL/LAND/TAKEOFF/POINT 由自主任务接管，脚本不应抢控制权。
        mode = self.normalize_fly_mode(self.fly_mode if mode is None else mode)
        return bool(mode in ('rtl', 'land', 'takeoff', 'point'))

    def maybe_warn_auto_mode_block(self):
        now = time.time()
        if now - self._auto_mode_warn_ts < 1.0:
            return
        self._auto_mode_warn_ts = now
        print('[MQTT_WARN] auto mode blocks joystick control: raw_fly_mode={} norm_fly_mode={} joystick_state={} stateType={}'.format(
            self.fly_mode, self.normalize_fly_mode(self.fly_mode), self.joystick_state, self.state_type))

    def is_motion_mode_ready(self):
        """Only true when current OSD really shows a motion-control-capable mode."""
        if not self._args.mqtt_subscribe_osd:
            return True
        mode = self.normalize_fly_mode(self.fly_mode)
        return bool(mode in ('posctl', 'attitude'))

    def is_manual_control_ready(self):
        # MQTT 已连接不等于可控制，还要检查模式和摇杆/PVA 状态。
        if not self._args.require_osd_ready:
            return True
        if not self._args.mqtt_subscribe_osd:
            return True
        mode_ok = self.is_motion_mode_ready()
        js_ok = (self.joystick_state == 1)
        if self.uses_joystick_control():
            return bool(mode_ok and js_ok)
        pva_ok = (self.pva_state == 1)
        return bool(mode_ok and js_ok and pva_ok)

    def maybe_warn_not_ready(self):
        now = time.time()
        if now - self._ready_warn_ts < 1.0:
            return
        self._ready_warn_ts = now
        print('[MQTT_WARN] manual control not ready: raw_fly_mode={} norm_fly_mode={} joystick_state={} pva_state={} stateType={}'.format(
            self.fly_mode, self.normalize_fly_mode(self.fly_mode), self.joystick_state, self.pva_state, self.state_type))

    def send_hold(self, wait_reply=False):
        # joystick 模式下 hold 只发零杆量，不切换飞行模式。
        if self.uses_joystick_control():
            return self.set_joystick_value(0, 0, 0, 0, wait_reply=wait_reply, quiet=False)
        return self.publish_method('hold', None, wait_reply=wait_reply)

    def send_brake(self, wait_reply=False):
        if self.uses_joystick_control():
            # Joystick mode: do NOT switch to hold mid-flight.
            # Only send neutral joystick so the current flight mode stays unchanged.
            return self.set_joystick_value(0, 0, 0, 0, wait_reply=wait_reply, quiet=False)
        return self.publish_method('pvaBrake', None, wait_reply=wait_reply)

    def send_disarm(self, wait_reply=False):
        return self.publish_method('disarm', None, wait_reply=wait_reply)

    def set_fly_mode(self, fly_mode, wait_reply=True, quiet=False):
        return self.publish_method('setFlyMode', {'flyMode': fly_mode}, wait_reply=wait_reply, quiet=quiet)

    def set_joystick_state(self, enable, wait_reply=True, quiet=False):
        return self.publish_method('setJoystickState', {'enable': int(enable)}, wait_reply=wait_reply, quiet=quiet)

    def joystick_effective_max_value(self, args=None):
        cfg = args if args is not None else self._args
        requested = int(max(1, abs(int(getattr(cfg, 'joystick_max_value', 300)))))
        hard_limit = int(max(1, abs(int(getattr(cfg, 'joystick_hard_limit', requested)))))
        return int(min(requested, hard_limit))

    def set_joystick_value(self, x, y, z, yaw, wait_reply=False, quiet=False):
        maxv = self.joystick_effective_max_value()
        data = {
            'x': int(max(-maxv, min(maxv, int(round(x))))),
            'y': int(max(-maxv, min(maxv, int(round(y))))),
            'z': int(max(-maxv, min(maxv, int(round(z))))),
            'yaw': int(max(-maxv, min(maxv, int(round(yaw))))),
        }
        return self.publish_method('setJoystickValue', data, wait_reply=wait_reply, quiet=quiet)

    def set_pva_state(self, enable, wait_reply=True, quiet=False):
        return self.publish_method('setPvaControllerState', {'enable': int(enable)}, wait_reply=wait_reply, quiet=quiet)

    def set_manual_limits(self, args, quiet=False, force=False):
        # 将限制逐项写入飞控；signature 避免重复设置相同参数。
        sig = (float(args.manual_hor_spd_max), float(args.manual_cli_spd_max), float(args.manual_land_spd_max),
               float(args.tilt_angle), float(args.yaw_spd_max), float(args.precision_land_error),
               float(args.land_ground_speed), float(args.land_speed))
        if (not force) and self._manual_limits_applied and self._manual_limits_signature == sig:
            return True
        methods = [
            ('setManualHorizontalSpeed', {'speed': float(args.manual_hor_spd_max)}),
            ('setManualClimbSpeed', {'speed': float(args.manual_cli_spd_max)}),
            ('setManualLandSpeed', {'speed': float(args.manual_land_spd_max)}),
            ('setTiltAngle', {'angle': float(args.tilt_angle)}),
            ('setYawSpeed', {'yawSpeed': float(args.yaw_spd_max)}),
            ('setPrecisionLandError', {'errorValue': float(args.precision_land_error)}),
            ('setLandGroundSpeed', {'landGroundSpeed': float(args.land_ground_speed)}),
            ('setLandSpeed', {'landSpeed': float(args.land_speed)}),
        ]
        ok_all = True
        for method, data in methods:
            _, reply = self.publish_method(method, data, wait_reply=self._args.mqtt_wait_reply, quiet=quiet)
            if self._args.mqtt_wait_reply and reply is not None and not self._reply_ok(reply):
                ok_all = False
            time.sleep(float(args.setup_cmd_interval))
        if ok_all:
            self._manual_limits_applied = True
            self._manual_limits_signature = sig
        return ok_all

    def send_zero_velocity(self, args, repeat=1, interval=0.05, quiet=False):
        cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)
        sent = False
        for _ in range(max(1, int(repeat))):
            sent = self.send_velocity(cmd, args, force=True, quiet=quiet) or sent
            time.sleep(float(interval))
        return sent

    def release_control(self, args, reason='release'):
        # 先发零命令，再关闭控制器，最后恢复模式，避免残留命令生效。
        print('[MQTT] releasing control: {}'.format(reason))
        if self.is_motion_mode_ready():
            try:
                self.send_zero_velocity(args, repeat=3, interval=0.05, quiet=True)
            except Exception:
                pass
        if not self.uses_joystick_control(args):
            self.set_pva_state(0, wait_reply=self._args.mqtt_wait_reply, quiet=False)
            time.sleep(0.08)
        self.set_joystick_state(0, wait_reply=self._args.mqtt_wait_reply, quiet=False)
        time.sleep(0.08)

    def restore_after_interrupt(self, args, reason='keyboard interrupt cleanup'):
        # Ctrl+C/异常也是安全路径：重复发零命令，再归还启动前状态。
        """Best-effort cleanup when the user aborts the script with Ctrl+C.

        Goal:
        1) Send several zero-joystick / zero-motion packets.
        2) Release virtual-joystick ownership.
        3) Restore the pre-run mode/state when available; otherwise fall back to the
           configured interrupt restore mode.
        """
        print('[MQTT] interrupt cleanup start: {}'.format(reason))
        try:
            if self.is_motion_mode_ready():
                self.send_zero_velocity(args, repeat=int(args.interrupt_zero_repeat),
                                        interval=float(args.interrupt_zero_interval), quiet=False)
        except Exception as e:
            print('[MQTT_WARN] interrupt zero motion failed: {}'.format(e))

        desired_pva = self._desired_exit_pva_state()
        desired_js = self._desired_exit_joystick_state()

        if not self.uses_joystick_control(args):
            try:
                self.set_pva_state(desired_pva, wait_reply=self._args.mqtt_wait_reply, quiet=False)
                time.sleep(0.08)
            except Exception as e:
                print('[MQTT_WARN] interrupt restore PVA failed: {}'.format(e))

        try:
            self.set_joystick_state(desired_js, wait_reply=self._args.mqtt_wait_reply, quiet=False)
            time.sleep(0.08)
        except Exception as e:
            print('[MQTT_WARN] interrupt restore joystick failed: {}'.format(e))

        restore_mode = self._desired_exit_fly_mode(args)
        if args.restore_mode_on_interrupt and restore_mode:
            try:
                self.set_fly_mode(restore_mode,
                                  wait_reply=self._args.mqtt_wait_reply, quiet=False)
                time.sleep(float(args.setup_cmd_interval))
            except Exception as e:
                print('[MQTT_WARN] interrupt restore fly mode failed: {}'.format(e))

        print('[MQTT] interrupt cleanup finished.')

    def initialize_for_run(self, args):
        """Reset previous run ownership first, then reacquire control cleanly.

        For joystick control we only request the fly mode + joystick state + manual
        speed/tilt limits. We intentionally do not enable PVA here.
        """
        # 先清理上次可能残留的控制权，再重新申请。
        self._sanitize_setup_args(args)
        self.release_control(args, reason='startup reset')
        time.sleep(float(args.init_release_pause))

        deadline = time.time() + float(args.force_ready_timeout)
        while time.time() < deadline:
            self.set_fly_mode(args.fly_mode, wait_reply=self._args.mqtt_wait_reply, quiet=False)
            time.sleep(float(args.setup_cmd_interval))
            self.set_joystick_state(1, wait_reply=self._args.mqtt_wait_reply, quiet=False)
            time.sleep(float(args.setup_cmd_interval))
            if not self.uses_joystick_control(args):
                self.set_pva_state(1, wait_reply=self._args.mqtt_wait_reply, quiet=False)
                time.sleep(float(args.setup_cmd_interval))
            self.set_manual_limits(args, quiet=False, force=False)
            time.sleep(0.15)
            if self.is_manual_control_ready():
                print('[MQTT] control initialized and ready.')
                return True
            self.maybe_warn_not_ready()
            time.sleep(float(args.ready_retry_interval))
        print('[MQTT] ERROR: initialize_for_run failed. raw_fly_mode={} norm_fly_mode={} js={} pva={}'.format(
            self.fly_mode, self.normalize_fly_mode(self.fly_mode), self.joystick_state, self.pva_state))
        return False

    def ensure_motion_mode_before_velocity(self, args):
        mode = self.normalize_fly_mode(self.fly_mode)

        # Avoid stealing control when teammate has already entered autonomous modes.
        if mode in ('rtl', 'land', 'takeoff', 'point'):
            print('[MQTT] skip setFlyMode because current mode is {}'.format(mode))
            return False

        # Already in a motion-capable mode.
        if mode in ('posctl', 'attitude'):
            return True

        self.set_fly_mode(args.fly_mode, wait_reply=self._args.mqtt_wait_reply, quiet=False)
        time.sleep(float(args.setup_cmd_interval))
        return self.is_motion_mode_ready()

    def recover_motion_control(self, args, reason='motion rejected'):
        now = time.time()
        if now - self._last_recover_ts < float(args.recover_cooldown):
            return False
        self._last_recover_ts = now
        mode = self.normalize_fly_mode(self.fly_mode)
        if self.is_autonomous_mode(mode):
            self.maybe_warn_auto_mode_block()
            return False
        print('[MQTT] recovering control because {}. last_reject_code={} last_reject_msg={}'.format(
            reason, self._recent_motion_reject_code, self._recent_motion_reject_msg))
        if mode not in ('posctl', 'attitude'):
            self.set_fly_mode(args.fly_mode, wait_reply=self._args.mqtt_wait_reply, quiet=False)
            time.sleep(float(args.setup_cmd_interval))
        self.set_joystick_state(1, wait_reply=self._args.mqtt_wait_reply, quiet=False)
        time.sleep(float(args.setup_cmd_interval))
        if not self.uses_joystick_control(args):
            self.set_pva_state(1, wait_reply=self._args.mqtt_wait_reply, quiet=False)
            time.sleep(float(args.setup_cmd_interval))
        self.set_manual_limits(args, quiet=True, force=False)
        time.sleep(0.10)
        return self.is_manual_control_ready()

    def has_recent_motion_reject(self, recent_sec):
        return (time.time() - self._recent_motion_reject_ts) <= float(recent_sec)

    def _velocity_payload(self, cmd, args):
        # 限制算法输出；上升和下降分别使用不同速度边界。
        vx = self._clamp(cmd.vx, -args.manual_hor_spd_max, args.manual_hor_spd_max)
        vy = self._clamp(cmd.vy, -args.manual_hor_spd_max, args.manual_hor_spd_max)
        vz = self._clamp(cmd.vz, -args.manual_land_spd_max, args.manual_cli_spd_max)
        yaw_rate = self._clamp(cmd.yaw_rate, -args.yaw_spd_max, args.yaw_spd_max)
        return {
            'vx': float(vx),
            'vy': float(vy),
            'vz': float(vz),
            'yawRate': float(yaw_rate),
            'manualHorSpdMax': float(args.manual_hor_spd_max),
            'manualCliSpdMax': float(args.manual_cli_spd_max),
            'manualLandSpdMax': float(args.manual_land_spd_max),
            'yawSpdMax': float(args.yaw_spd_max),
        }

    def _axis_to_joystick_value(self, value, axis_max, sign, joystick_max):
        # stick = sign * joystick_max * requested_speed / allowed_speed。
        # sign 协调算法坐标与飞控协议的正方向。
        axis_max = max(1e-6, float(axis_max))
        scaled = float(sign) * float(joystick_max) * float(value) / axis_max
        return int(round(self._clamp(scaled, -float(joystick_max), float(joystick_max))))

    def _joystick_payload(self, cmd, args):
        # x/y/z/yaw 是无量纲杆量，不再是 m/s；z 按上升/下降上限换算。
        payload = self._velocity_payload(cmd, args)
        maxv = self.joystick_effective_max_value(args)
        x = self._axis_to_joystick_value(payload['vx'], args.manual_hor_spd_max, args.joystick_pitch_sign, maxv)
        y = self._axis_to_joystick_value(payload['vy'], args.manual_hor_spd_max, args.joystick_roll_sign, maxv)
        if payload['vz'] >= 0.0:
            z_max = max(1e-6, float(args.manual_cli_spd_max))
        else:
            z_max = max(1e-6, float(args.manual_land_spd_max))
        z = self._axis_to_joystick_value(payload['vz'], z_max, args.joystick_throttle_sign, maxv)
        yaw = self._axis_to_joystick_value(payload['yawRate'], args.yaw_spd_max, args.joystick_yaw_sign, maxv)
        return {'x': int(x), 'y': int(y), 'z': int(z), 'yaw': int(yaw)}

    def _clear_axis_effective_state(self, axis_name=None):
        if axis_name is None:
            for k in self._axis_effective_state:
                self._axis_effective_state[k]['hold_until'] = 0.0
                self._axis_effective_state[k]['sign'] = 0
                self._axis_effective_state[k]['value'] = 0
            return
        st = self._axis_effective_state.get(axis_name)
        if st is None:
            return
        st['hold_until'] = 0.0
        st['sign'] = 0
        st['value'] = 0

    def _apply_joystick_axis_min_effective(self, axis_name, raw_value, trigger_value, effective_value,
                                           bypass_value, now, args, pulse_period=None,
                                           pulse_on_min=None, pulse_on_max=None):
        # 最小有效杆量相当于执行器死区：过小非零杆量可能完全不动。
        # hold 抬高并保持；pulse 在有效值与 0 间切换，用时间平均减小效果。
        raw_value = int(raw_value)
        trigger_value = int(abs(trigger_value))
        effective_value = int(abs(effective_value))
        bypass_value = int(abs(bypass_value))
        if trigger_value <= 0 or effective_value <= 0:
            self._clear_axis_effective_state(axis_name)
            return raw_value

        if bypass_value <= 0:
            bypass_value = trigger_value
        effective_value = max(trigger_value, effective_value)
        mode = str(getattr(args, 'joystick_min_effective_mode', 'hold')).strip().lower()
        st = self._axis_effective_state.get(axis_name)
        if st is None:
            self._axis_effective_state[axis_name] = {'hold_until': 0.0, 'sign': 0, 'value': 0}
            st = self._axis_effective_state[axis_name]

        if raw_value == 0:
            if mode == 'hold' and now < float(st.get('hold_until', 0.0)) and int(st.get('sign', 0)) != 0:
                return int(st.get('value', 0))
            self._clear_axis_effective_state(axis_name)
            return 0

        if abs(raw_value) >= trigger_value or abs(raw_value) >= bypass_value:
            self._clear_axis_effective_state(axis_name)
            return raw_value

        sign = 1 if raw_value > 0 else -1
        forced_value = int(sign * effective_value)

        if mode == 'hold':
            hold_time = max(0.0, float(getattr(args, 'joystick_min_hold_time', 0.0)))
            st['sign'] = sign
            st['value'] = forced_value
            st['hold_until'] = now + hold_time
            return forced_value

        period = float(pulse_period if pulse_period is not None else 0.0)
        if period <= 1e-6:
            st['sign'] = sign
            st['value'] = forced_value
            st['hold_until'] = now
            return forced_value

        on_min = max(0.0, float(pulse_on_min if pulse_on_min is not None else 0.0))
        on_max = max(on_min, float(pulse_on_max if pulse_on_max is not None else 0.0))
        # 例如期望 85、最低有效值 170，则让 170 约一半时间开启。
        duty = min(1.0, max(0.0, float(abs(raw_value)) / float(effective_value)))
        on_time = period * duty
        if duty > 1e-6:
            on_time = min(max(on_time, on_min), on_max)
        else:
            on_time = 0.0

        phase = now % period
        if phase <= on_time:
            st['sign'] = sign
            st['value'] = forced_value
            st['hold_until'] = now
            return forced_value

        self._clear_axis_effective_state(axis_name)
        return 0

    def _apply_joystick_xy_min_effective(self, payload, now, args):
        trigger_value = int(abs(getattr(args, 'joystick_xy_min_effective_value', 0)))
        effective_value = int(abs(getattr(args, 'joystick_xy_force_value', 0)))
        bypass_value = int(abs(getattr(args, 'joystick_xy_bypass_value', 0)))
        if trigger_value <= 0 or effective_value <= 0:
            return payload

        out = dict(payload)
        out['x'] = self._apply_joystick_axis_min_effective(
            'x', out.get('x', 0), trigger_value, effective_value, bypass_value, now, args,
            pulse_period=float(getattr(args, 'joystick_xy_pulse_period', 0.0) or getattr(args, 'xy_pulse_period', 0.0)),
            pulse_on_min=float(getattr(args, 'joystick_xy_pulse_on_min', 0.0) or getattr(args, 'xy_pulse_on_min', 0.0)),
            pulse_on_max=float(getattr(args, 'joystick_xy_pulse_on_max', 0.0) or getattr(args, 'xy_pulse_on_max', 0.0)))
        out['y'] = self._apply_joystick_axis_min_effective(
            'y', out.get('y', 0), trigger_value, effective_value, bypass_value, now, args,
            pulse_period=float(getattr(args, 'joystick_xy_pulse_period', 0.0) or getattr(args, 'xy_pulse_period', 0.0)),
            pulse_on_min=float(getattr(args, 'joystick_xy_pulse_on_min', 0.0) or getattr(args, 'xy_pulse_on_min', 0.0)),
            pulse_on_max=float(getattr(args, 'joystick_xy_pulse_on_max', 0.0) or getattr(args, 'xy_pulse_on_max', 0.0)))
        return out

    def _apply_joystick_z_min_effective(self, payload, now, args):
        trigger_value = int(abs(getattr(args, 'joystick_z_min_effective_value', 0)))
        effective_value = int(abs(getattr(args, 'joystick_z_force_value', 0)))
        bypass_value = int(abs(getattr(args, 'joystick_z_bypass_value', 0)))
        if trigger_value <= 0 or effective_value <= 0:
            return payload
        out = dict(payload)
        out['z'] = self._apply_joystick_axis_min_effective(
            'z', out.get('z', 0), trigger_value, effective_value, bypass_value, now, args,
            pulse_period=float(getattr(args, 'joystick_z_pulse_period', 0.0) or getattr(args, 'joystick_xy_pulse_period', 0.0) or getattr(args, 'xy_pulse_period', 0.0)),
            pulse_on_min=float(getattr(args, 'joystick_z_pulse_on_min', 0.0) or getattr(args, 'joystick_xy_pulse_on_min', 0.0) or getattr(args, 'xy_pulse_on_min', 0.0)),
            pulse_on_max=float(getattr(args, 'joystick_z_pulse_on_max', 0.0) or getattr(args, 'joystick_xy_pulse_on_max', 0.0) or getattr(args, 'xy_pulse_on_max', 0.0)))
        return out

    def send_velocity(self, cmd, args, force=False, quiet=False):
        # 此处才选择协议。force 用于退出零命令，会绕过死区补偿。
        method = str(args.control_method).strip().lower()
        payload = self._velocity_payload(cmd, args)
        now = time.time()
        if method == 'joystick':
            out_payload = self._joystick_payload(cmd, args)
            if force:
                self._clear_axis_effective_state()
            else:
                out_payload = self._apply_joystick_xy_min_effective(out_payload, now, args)
                out_payload = self._apply_joystick_z_min_effective(out_payload, now, args)
            sig = (out_payload['x'], out_payload['y'], out_payload['z'], out_payload['yaw'], method)
        else:
            out_payload = payload
            sig = (
                round(payload['vx'], int(args.cmd_round_digits)),
                round(payload['vy'], int(args.cmd_round_digits)),
                round(payload['vz'], int(args.cmd_round_digits)),
                round(payload['yawRate'], int(args.cmd_round_digits)),
                method,
            )
        # 相同命令短期不重复；超过 keepalive 后重发，防止控制超时。
        if (not force) and self._last_velocity_sig == sig and (now - self._last_velocity_send_ts) < float(args.command_keepalive):
            return False
        self._last_velocity_sig = sig
        self._last_velocity_send_ts = now
        if method == 'target':
            data = {
                'vx': payload['vx'], 'vy': payload['vy'], 'vz': payload['vz'],
                'ax': 0.0, 'ay': 0.0, 'az': 0.0,
                'yawRate': payload['yawRate'],
                'manualHorSpdMax': float(args.manual_hor_spd_max),
                'manualCliSpdMax': float(args.manual_cli_spd_max),
                'manualLandSpdMax': float(args.manual_land_spd_max),
                'tiltAngle': float(args.tilt_angle),
                'yawSpdMax': float(args.yaw_spd_max),
            }
            self.publish_method('targetCtrl', data, wait_reply=False, quiet=quiet)
        elif method == 'velocity':
            self.publish_method('velocityCtrl', payload, wait_reply=False, quiet=quiet)
        else:
            self.set_joystick_value(out_payload['x'], out_payload['y'], out_payload['z'], out_payload['yaw'],
                                    wait_reply=False, quiet=quiet)
        return True

    def send_land(self, args):
        # LAND 不等于一直发下降速度，它把最终接地交给飞控内置逻辑。
        args.land_speed = self._clamp(args.land_speed, 0.2, 5.0)
        args.land_ground_speed = self._clamp(args.land_ground_speed, 0.2, 0.6)
        args.precision_land_error = self._clamp(args.precision_land_error, 0.05, 1.0)
        self.publish_method(
            'land',
            {
                'landSpeed': float(args.land_speed),
                'landGroundSpeed': float(args.land_ground_speed),
                'precisionLandError': float(args.precision_land_error),
            },
            wait_reply=self._args.mqtt_wait_reply,
        )

    def shutdown_after_land(self, args):
        # Preserve field behavior: after landing we still send zero joystick, disarm,
        # and then restore the startup mode / joystick state captured before setup.
        # 接地后先发零命令，再重复 disarm，最后归还控制状态。
        print('[LAND] finalize landing -> disarm -> restore pre-run mode/state')
        if self.is_motion_mode_ready():
            self.send_zero_velocity(args, repeat=3, interval=0.06, quiet=True)
        for _ in range(int(args.disarm_repeat)):
            self.send_disarm(wait_reply=False)
            time.sleep(float(args.disarm_repeat_interval))
        time.sleep(float(args.post_land_release_delay))
        self.restore_after_interrupt(args, reason='post-land restore')


class ArucoLandingController(object):
    #
    # =========================================================================
    # 第二章：视觉几何和控制数学
    # =========================================================================
    #
    # 一、图像坐标到真实距离
    #
    # 相机针孔模型的核心关系是“相似三角形”：
    #
    #   像素尺寸 / 焦距像素 = 真实尺寸 / 深度
    #
    # 已知 ArUco 真实边长 L、图像平均边长 w、水平焦距 fx，可估算深度：
    #
    #   h ≈ fx * L / w
    #
    # 默认 fx=550 px、L=0.20 m。若检测边长 w=110 px，则 h≈550*0.2/110=1 m。
    # 若 w=55 px，则 h≈2 m。目标越远，在图像中越小。
    #
    # 目标中心相对期望像素差为 du、dv。小角度且地面水平、相机垂直时：
    #
    #   body_x ≈ h * dv / fy
    #   body_y ≈ h * du / fx
    #
    # 例：h=2 m、du=80 px、fx=550 px，则横向距离约 2*80/550=0.291 m。
    # 相同 80 px 在 h=0.5 m 时只有 0.073 m，所以像素容差不能脱离高度理解。
    #
    # 这些不是完整三维位姿。代码没有使用相机畸变参数、solvePnP、标志法向量或
    # 无人机 roll/pitch。若飞机倾斜，w 变小不一定是高度增加，du/dv 也混入姿态
    # 投影。精度要求更高时应标定相机、用 PnP 求 6DoF，并把 IMU 姿态纳入变换。
    #
    # 二、四套坐标不要混在一起
    #
    # 1. 图像坐标：u 向右、v 向下。
    # 2. 相机几何：光轴指向地面，水平轴由安装方向决定。
    # 3. 机体坐标：通常前/右/下或前/右/上，需以飞控协议为准。
    # 4. 摇杆协议：本项目文档规定 x=-1000 表示前进，因此 pitch_sign 默认 -1。
    #
    # transform_xy_pair 处理 swap_xy 和 invert；image_yaw_comp_deg 在图像平面旋转
    # du/dv；_joystick_payload 再应用 pitch/roll/throttle/yaw sign。它们作用层级
    # 不同，不能靠同时改多个 sign 来“试到能飞”，否则后续很难判断真实坐标关系。
    #
    # 推荐标定步骤：拆桨固定机体，在画面中将标志移向右侧，确认 du>0；根据期望
    # 无人机应怎样移动来追踪标志，逐层检查 body 命令和最终 MQTT 杆量符号。
    #
    # 三、高度为什么有三种表达
    #
    # raw_radar_height 是传感器到地距离；vision_height 是相机到标志平面的距离；
    # selected_uav_height 扣除传感器机械安装高度，近似机体最低点/参考点离地高度。
    # 水平几何需要相机高度，状态分段需要机体高度，二者混用会让 0.7 m 阈值整体
    # 偏移。camera_radar_height_offset = camera_ground_offset-radar_ground_offset。
    #
    # 四、低通滤波
    #
    # 一阶低通公式：
    #
    #   filtered_t = (1-alpha)*filtered_(t-1) + alpha*measurement_t
    #
    # alpha=0.25 时，旧值占 75%，新帧只占 25%，抖动小但响应慢。假设旧 du=100，
    # 新 du=20，结果为 0.75*100+0.25*20=80，不会一帧跳到 20。
    # alpha=0.75 时结果为 40，更跟手但更容易把检测噪声变成运动命令。
    # 代码高空使用较小 alpha 抗远距离角点抖动，低空使用较大 alpha 减少延迟。
    # error LPF 平滑测量，command LPF 平滑输出；串联会增加总延迟，不能只追求平稳。
    #
    # 五、分阶段降落
    #
    # HIGH_ALIGN：机体高于 2 m，容差宽，动作时间允许较长。
    # MID_ALIGN：0.7~2 m，容差和动作时间收紧。
    # FINAL_ALIGN：不高于 0.7 m，要求最严格，满足后进入 LAND。
    #
    # 高空目标小、像素噪声大，过严容差会永远对不准；低空同样像素误差代表更小
    # 米级距离，但横移风险更高，所以要降低单次动作时间和风补偿。
    #
    # 六、测量-执行控制器的完整推导
    #
    # measure 阶段悬停 hover_measure_time，至少收集 hover_measure_min_samples 个样本。
    # summarize_measure 对 du、dv、高度取均值，再换成 body_x/body_y。均值抑制零均值
    # 噪声，但若风持续推动飞机，均值描述的是一段运动轨迹的平均，不是严格当前值。
    #
    # 当前阶段像素容差也换算成米。某轴真正需要修正的距离是：
    #
    #   residual = max(0, abs(body_distance) - deadband_scale*tol_m)
    #
    # 例：误差 0.291 m、允许 0.08 m，residual=0.211 m。控制器只试图移动到容差
    # 边缘，不追求数学上的零误差，避免在中心附近来回振荡。
    #
    # 杆量计划：
    #
    #   joy = stage_min_joy + wind_bias + distance_gain*residual
    #
    # 假设 stage_min=165、wind_bias=12、distance_gain=90 joystick/m、residual=0.211，
    # joy≈165+12+18.99=196。若 maxv=300、manual_hor_spd_max=2 m/s，则理论速度：
    #
    #   theoretical_speed = 2 * 196/300 ≈ 1.307 m/s
    #
    # 飞机未必达到理论速度，因此乘轴响应系数 response_gain。若 gain=0.9：
    # effective_speed≈1.176 m/s，理想保持时间：
    #
    #   act_time = residual/effective_speed ≈ 0.211/1.176 = 0.179 s
    #
    # 最后 clip 到 timed_actuation_min_time 和当前阶段 max_time。这里会被最小 0.18 s
    # 略微抬高。actuate 阶段在这 0.18 s 内保持同一命令，不逐帧改变。
    #
    # 七、单轴与双轴
    #
    # single 只选 residual 更大的轴。优点是容易观察响应、不易同时倾斜造成耦合；
    # 缺点是两个轴串行修正，耗时更长，另一轴可能在等待期间受风漂移。
    # multi 同时修正 x/y，并用较长轴时间作为共同持续时间，再反算每轴速度，使两个
    # 轴理论上同时结束。它效率高，但更依赖坐标标定和独立轴响应模型。
    #
    # 八、响应系数怎样学习
    #
    # 执行前误差 prev，执行后误差 curr。若没有越过中心：actual_move=|prev|-|curr|；
    # 若符号翻转表示越过中心：actual_move=|prev|+|curr|。然后：
    #
    #   ratio = actual_move/predicted_move
    #   target_gain = old_gain*ratio
    #   new_gain = (1-alpha)*old_gain + alpha*target_gain
    #
    # 实际移动不足时 ratio<1，gain 下降，下一次同样距离会计算更长 act_time；实际
    # 移动过多则相反。ratio 和 gain 都限幅，防止一次误检把模型改得极端。
    # 这只是每轴标量自适应，不是 EKF，也不估计风速、速度惯性或轴间耦合。
    # 精准降落的核心控制器。它每收到一帧图像就更新视觉信息和状态机，
    # 输出 ControlCommand，但不直接操作 MQTT。
    #
    # 四个状态：
    # SEARCH  等待目标；ALIGN 悬停测量并水平纠偏；
    # DESCEND 只做分段垂直下降；LAND 把最终接地交给飞控。
    SEARCH = 0
    ALIGN = 1
    DESCEND = 2
    LAND = 3

    def __init__(self, args, mqtt_adapter):
        self.args = args
        self.mqtt = mqtt_adapter
        self.state_machine = self.SEARCH
        self.marker_detected = False
        self.marker_center = None
        self.pixel_width = 0.0
        self.last_detection_time = time.time()
        self.align_start_time = None
        self.last_check_time = time.time()
        self.target_hold_height = None
        self.last_cmd_time = 0.0
        self.frame_index = 0
        self.last_h_est = None
        self.last_detection = DetectionResult()
        self.aruco_dict = None
        self.detector_parameters = None
        self._init_aruco()
        self._vision_lost_brake_sent = False
        self._last_action = 'velocity'
        self._land_cmd_sent = False
        self._land_start_time = None
        self._descent_started_once = False
        self._touchdown_start_ts = None
        self._startup_guard_until = time.time() + float(args.startup_guard_time)
        self._last_stage_name = 'SEARCH'
        self._last_du = None
        self._last_dv = None
        self._near_center_pause_until = 0.0
        self._last_sent_velocity_cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)
        self._last_velocity_logic_send_ts = 0.0
        self._last_velocity_logic_frame = -999999
        self._last_idle_zero_ts = 0.0
        self._filtered_du = None
        self._filtered_dv = None
        self._filtered_vx = 0.0
        self._filtered_vy = 0.0
        self._last_raw_du = None
        self._last_raw_dv = None
        # ALIGN 内部又分 measure/actuate 两相：测量时发零水平速度并积累样本，
        # 执行时保持一次计算好的速度直到 _actuate_until。
        self._measure_samples = []
        self._align_phase = 'measure'
        self._actuate_cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)
        self._actuate_until = 0.0
        self._last_measure_result = None
        self._last_actuation_plan = None
        init_gain = float(getattr(args, 'timed_axis_response_gain_init', 0.90))
        # 响应系数描述“理论移动量有多少真正变成实际位移”，会在每轮测量后更新。
        self._axis_response_gain = {'x': init_gain, 'y': init_gain}
        self._descend_target_uav_h = None

    def _init_aruco(self):
        if aruco is None:
            raise RuntimeError('当前 OpenCV 没有 cv2.aruco 模块，请安装带 contrib 的版本')
        try:
            self.aruco_dict = aruco.Dictionary_get(getattr(aruco, self.args.aruco_dict_name))
        except Exception:
            self.aruco_dict = aruco.getPredefinedDictionary(getattr(aruco, self.args.aruco_dict_name))
        try:
            self.detector_parameters = aruco.DetectorParameters_create()
        except Exception:
            self.detector_parameters = aruco.DetectorParameters()
        try:
            self.detector_parameters.minMarkerPerimeterRate = float(self.args.min_marker_perimeter_rate)
        except Exception:
            pass

    def raw_radar_height(self):
        # OSD relativeAlt 在本项目中被当作雷达到地高度。实际含义必须与固件核对。
        if self.mqtt.relative_alt is None:
            return None
        try:
            return float(self.mqtt.relative_alt)
        except Exception:
            return None

    def camera_height_from_osd(self):
        # 雷达和相机安装高度不同，控制几何需要的是相机到地面的距离。
        raw = self.raw_radar_height()
        if raw is None:
            return None
        return raw + float(self.args.camera_radar_height_offset)

    def vision_height(self):
        if self.last_h_est is None:
            return None
        try:
            return float(self.last_h_est)
        except Exception:
            return None

    def selected_height_source(self):
        return str(self.args.height_judge_source).strip().lower()

    def selected_height(self):
        src = self.selected_height_source()
        if src == 'radar':
            return self.raw_radar_height()
        if src == 'vision':
            return self.vision_height()
        return None

    def selected_height_for_control(self):
        # 水平像素转米必须使用相机高度；选定源缺失时临时回退到另一来源。
        src = self.selected_height_source()
        if src == 'radar':
            h_cam = self.camera_height_from_osd()
            if h_cam is not None:
                return h_cam
        elif src == 'vision':
            h_vis = self.vision_height()
            if h_vis is not None:
                return h_vis
        # fallback keeps behavior usable when the selected source is temporarily missing
        h_cam = self.camera_height_from_osd()
        if h_cam is not None:
            return h_cam
        return self.vision_height()

    def selected_uav_height(self):
        # 阶段判断使用机体离地高度，因此要扣除传感器自身的机械安装高度。
        src = self.selected_height_source()
        if src == 'vision':
            h = self.vision_height()
            if h is None:
                return None
            return h - float(self.args.camera_ground_offset)
        raw = self.raw_radar_height()
        if raw is None:
            return None
        return raw - float(self.args.radar_ground_offset)

    def get_stage_center_tolerance(self, uav_height):
        # 高空允许较大像素误差，低空要求更严格。像素阈值并非固定米级精度：
        # 同样 20 px 在不同高度代表不同水平距离。
        if uav_height is None:
            return float(self.args.high_alt_center_tolerance)
        if uav_height > float(self.args.stage_high_alt_height):
            return float(self.args.high_alt_center_tolerance)
        if uav_height > float(self.args.final_direct_land_height):
            return float(self.args.mid_alt_center_tolerance)
        return float(self.args.final_alt_center_tolerance)

    def get_stage_name(self, uav_height):
        # 默认分为 >2 m、0.7~2 m、<=0.7 m 三段。
        if uav_height is None:
            return 'UNKNOWN'
        if uav_height > float(self.args.stage_high_alt_height):
            return 'HIGH_ALIGN'
        if uav_height > float(self.args.final_direct_land_height):
            return 'MID_ALIGN'
        return 'FINAL_ALIGN'

    def get_stage_vel_gain_scale(self, uav_height):
        if uav_height is None:
            return float(self.args.vel_gain_mid_scale)
        if uav_height > float(self.args.stage_high_alt_height):
            return float(self.args.vel_gain_high_scale)
        if uav_height > float(self.args.final_direct_land_height):
            return float(self.args.vel_gain_mid_scale)
        return float(self.args.vel_gain_final_scale)

    def get_stage_error_lpf_alpha(self, uav_height):
        if uav_height is None:
            return float(self.args.error_lpf_alpha_mid)
        if uav_height > float(self.args.stage_high_alt_height):
            return float(self.args.error_lpf_alpha_high)
        if uav_height > float(self.args.final_direct_land_height):
            return float(self.args.error_lpf_alpha_mid)
        return float(self.args.error_lpf_alpha_final)

    def get_stage_cmd_lpf_alpha(self, uav_height):
        if uav_height is None:
            return float(self.args.xy_cmd_lpf_alpha_mid)
        if uav_height > float(self.args.stage_high_alt_height):
            return float(self.args.xy_cmd_lpf_alpha_high)
        if uav_height > float(self.args.final_direct_land_height):
            return float(self.args.xy_cmd_lpf_alpha_mid)
        return float(self.args.xy_cmd_lpf_alpha_final)

    def filter_detection_error(self, du, dv, uav_height):
        # 一阶低通：filtered = (1-alpha)*old + alpha*new。
        # alpha 小更稳但延迟大；低空 alpha 较大，以便快速响应近地误差。
        alpha = max(0.0, min(1.0, self.get_stage_error_lpf_alpha(uav_height)))
        if self._filtered_du is None or self._filtered_dv is None:
            self._filtered_du = float(du)
            self._filtered_dv = float(dv)
        else:
            self._filtered_du = (1.0 - alpha) * float(self._filtered_du) + alpha * float(du)
            self._filtered_dv = (1.0 - alpha) * float(self._filtered_dv) + alpha * float(dv)
        return float(self._filtered_du), float(self._filtered_dv)

    def smooth_xy_command(self, vx, vy, uav_height):
        # 对命令再做一层低通，避免视觉噪声直接变成机身左右抖动。
        alpha = max(0.0, min(1.0, self.get_stage_cmd_lpf_alpha(uav_height)))
        self._filtered_vx = (1.0 - alpha) * float(self._filtered_vx) + alpha * float(vx)
        self._filtered_vy = (1.0 - alpha) * float(self._filtered_vy) + alpha * float(vy)
        return float(self._filtered_vx), float(self._filtered_vy)

    def transform_xy_pair(self, vx_cmd, vy_cmd):
        # 相机安装方向、图像轴和机体前后/左右轴可能不一致。
        # swap/invert 是现场标定手段，首次上机必须小杆量验证正负方向。
        if self.args.swap_xy:
            vx_cmd, vy_cmd = vy_cmd, vx_cmd
        if self.args.invert_x:
            vx_cmd = -vx_cmd
        if self.args.invert_y:
            vy_cmd = -vy_cmd
        return vx_cmd, vy_cmd

    def select_single_axis_command(self, du, dv, uav_height=None):
        """Single-axis correction: each frame only correct the image axis with larger error."""
        # 旧的逐帧比例控制路径：像素误差除以焦距得到近似视线角，再乘增益。
        # single 每帧只修正误差更大的轴，可减少两个方向同时耦合摆动。
        gain = float(self.args.vel_gain) * self.get_stage_vel_gain_scale(uav_height)
        base_x_from_dv = gain * dv / self.args.camera_fy
        base_y_from_du = gain * du / self.args.camera_fx

        cmd_from_du = self.transform_xy_pair(0.0, base_y_from_du)
        cmd_from_dv = self.transform_xy_pair(base_x_from_dv, 0.0)

        if abs(du) >= abs(dv):
            return cmd_from_du[0], cmd_from_du[1], abs(base_y_from_du)
        return cmd_from_dv[0], cmd_from_dv[1], abs(base_x_from_dv)

    def select_multi_axis_command(self, du, dv, uav_height=None):
        """Multi-axis correction: correct both horizontal axes in the same frame."""
        # multi 同时输出前后和左右命令，速度更快，但对轴映射和机体耦合更敏感。
        gain = float(self.args.vel_gain) * self.get_stage_vel_gain_scale(uav_height)
        base_x_from_dv = gain * dv / self.args.camera_fy
        base_y_from_du = gain * du / self.args.camera_fx
        vx_cmd, vy_cmd = self.transform_xy_pair(base_x_from_dv, base_y_from_du)
        raw_axis_speed = max(abs(base_x_from_dv), abs(base_y_from_du))
        return vx_cmd, vy_cmd, raw_axis_speed

    def select_xy_command(self, du, dv, uav_height=None):
        axis_mode = str(getattr(self.args, 'axis_mode', 'single')).strip().lower()
        if axis_mode == 'multi':
            return self.select_multi_axis_command(du, dv, uav_height)
        return self.select_single_axis_command(du, dv, uav_height)

    def apply_auto_pulse_xy(self, vx, vy, raw_axis_speed, now):
        # 兼容旧控制路径：期望速度低于最小有效速度时，通过脉冲占空比实现平均小速度。
        if abs(vx) < 1e-6 and abs(vy) < 1e-6:
            return vx, vy

        min_eff = float(self.args.xy_min_effective_speed)
        if min_eff <= 1e-6:
            return vx, vy

        period = float(self.args.xy_pulse_period)
        if period <= 1e-6:
            # backward-compatible fallback
            period = float(self.args.xy_pulse_on) + float(self.args.xy_pulse_off)
        if period <= 1e-6:
            return vx, vy

        on_min = max(0.0, float(self.args.xy_pulse_on_min))
        on_max = max(on_min, float(self.args.xy_pulse_on_max))

        cmd_mag = max(abs(vx), abs(vy))
        if cmd_mag <= 1e-6:
            return 0.0, 0.0

        # If command already exceeds effective threshold, keep continuous output.
        if raw_axis_speed >= min_eff and cmd_mag >= min_eff:
            return vx, vy

        # Raise to minimum effective speed while preserving direction.
        scale = min_eff / cmd_mag
        eff_vx = vx * scale
        eff_vy = vy * scale

        duty = 0.0 if raw_axis_speed <= 1e-6 else min(1.0, max(0.0, raw_axis_speed / min_eff))
        on_time = period * duty
        if duty > 1e-6:
            on_time = min(max(on_time, on_min), on_max)
        else:
            on_time = 0.0

        phase = now % period
        if phase <= on_time:
            return eff_vx, eff_vy
        return 0.0, 0.0


    def reset_measure_phase(self):
        # 开始一次新的悬停测量窗口，清掉上一轮样本和执行命令。
        self._measure_samples = []
        self._align_phase = 'measure'
        self._actuate_until = 0.0
        self._actuate_cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)

    def reset_alignment_cycle(self):
        self.reset_measure_phase()
        self._last_measure_result = None
        self._last_actuation_plan = None
        self._filtered_du = None
        self._filtered_dv = None
        self._filtered_vx = 0.0
        self._filtered_vy = 0.0

    def collect_measure_sample(self, du, dv, camera_h, uav_h):
        # 一帧只是带噪测量。累积多帧后取平均，可削弱检测抖动和短时风扰。
        self._measure_samples.append({'du': float(du), 'dv': float(dv), 'camera_h': float(camera_h), 'uav_h': None if uav_h is None else float(uav_h)})
        horizon = max(0.2, float(self.args.hover_measure_time))
        cutoff = time.time() - horizon
        if len(self._measure_samples) > 500:
            self._measure_samples = self._measure_samples[-500:]
        if self._measure_samples and 'ts' in self._measure_samples[0]:
            self._measure_samples = [s for s in self._measure_samples if s['ts'] >= cutoff]

    def estimate_body_error_m(self, du, dv, camera_h):
        # 针孔近似：x ~= h*dv/fy，y ~= h*du/fx。
        # h 是相机到地高度；公式假设相机近似垂直向下、地面和标志近似水平。
        if camera_h is None:
            return None, None
        fx = max(1e-6, float(self.args.camera_fx))
        fy = max(1e-6, float(self.args.camera_fy))
        bx, by = self.transform_xy_pair(float(camera_h) * float(dv) / fy,
                                        float(camera_h) * float(du) / fx)
        return float(bx), float(by)

    def get_timed_stage_name(self, uav_h):
        return self.get_stage_name(uav_h)

    def get_stage_target_height(self, uav_h):
        # 高空对准后只下降到 2 m，中空对准后只下降到 0.7 m，然后重新测量。
        # 分段可避免从高空一次直降期间累计过多横向漂移。
        if uav_h is None:
            return None
        if uav_h > float(self.args.stage_high_alt_height):
            return float(self.args.stage_high_alt_height)
        if uav_h > float(self.args.final_direct_land_height):
            return float(self.args.final_direct_land_height)
        return None

    def get_stage_min_joystick(self, stage_name):
        if stage_name == 'HIGH_ALIGN':
            return int(self.args.timed_stage_min_joystick_high)
        if stage_name == 'MID_ALIGN':
            return int(self.args.timed_stage_min_joystick_mid)
        return int(self.args.timed_stage_min_joystick_final)

    def get_stage_wind_bias(self, stage_name):
        if stage_name == 'HIGH_ALIGN':
            return int(self.args.timed_wind_bias_joystick_high)
        if stage_name == 'MID_ALIGN':
            return int(self.args.timed_wind_bias_joystick_mid)
        return int(self.args.timed_wind_bias_joystick_final)

    def get_stage_max_actuation_time(self, stage_name):
        if stage_name == 'HIGH_ALIGN':
            return float(self.args.timed_actuation_max_time_high)
        if stage_name == 'MID_ALIGN':
            return float(self.args.timed_actuation_max_time_mid)
        return float(self.args.timed_actuation_max_time_final)

    def summarize_measure(self):
        # 把一个测量窗口压缩为平均像素误差、平均高度、米级机体误差和容差。
        if len(self._measure_samples) < int(self.args.hover_measure_min_samples):
            return None
        # 这里用均值而不是最后一帧，控制决策对单帧误检不那么敏感。
        du = float(np.mean([s['du'] for s in self._measure_samples]))
        dv = float(np.mean([s['dv'] for s in self._measure_samples]))
        cam_h_vals = [s['camera_h'] for s in self._measure_samples if s['camera_h'] is not None]
        if not cam_h_vals:
            return None
        camera_h = float(np.mean(cam_h_vals))
        uav_vals = [s['uav_h'] for s in self._measure_samples if s['uav_h'] is not None]
        uav_h = float(np.mean(uav_vals)) if uav_vals else None
        body_x_m, body_y_m = self.estimate_body_error_m(du, dv, camera_h)
        stage_tol_px = self.get_stage_center_tolerance(uav_h)
        tol_body_x_m, tol_body_y_m = self.estimate_body_error_m(stage_tol_px, stage_tol_px, camera_h)
        tol_x_m = abs(float(tol_body_x_m)) if tol_body_x_m is not None else 0.0
        tol_y_m = abs(float(tol_body_y_m)) if tol_body_y_m is not None else 0.0
        return {
            'du': du, 'dv': dv,
            'camera_h': camera_h,
            'uav_h': uav_h,
            'body_x_m': body_x_m,
            'body_y_m': body_y_m,
            'tol_x_m': tol_x_m,
            'tol_y_m': tol_y_m,
            'stage_name': self.get_timed_stage_name(uav_h),
            'sample_count': len(self._measure_samples),
        }

    def update_axis_response_from_measure(self, measure):
        # 一轮打杆后比较“预测移动量”和“实际误差减少量”，在线修正轴响应系数。
        # 若越过目标中心，实际移动量按前后两段距离相加计算。
        plan = self._last_actuation_plan
        if not plan or measure is None:
            return
        alpha = max(0.0, min(1.0, float(self.args.timed_axis_response_update_alpha)))
        gmin = float(self.args.timed_axis_response_gain_min)
        gmax = float(self.args.timed_axis_response_gain_max)
        for axis in plan.get('axes', []):
            old_gain = float(self._axis_response_gain.get(axis, 1.0))
            prev_abs = abs(float(plan['pre_body'][axis]))
            curr_val = float(measure['body_x_m'] if axis == 'x' else measure['body_y_m'])
            curr_abs = abs(curr_val)
            prev_val = float(plan['pre_body'][axis])
            if prev_val == 0.0:
                continue
            if np.sign(prev_val) != np.sign(curr_val) and curr_abs > 1e-6:
                actual_move = prev_abs + curr_abs
            else:
                actual_move = prev_abs - curr_abs
            predicted_move = max(1e-3, abs(float(plan['predicted_move'].get(axis, 0.0))))
            # ratio>1 表示实际比预测更灵敏；ratio<1 表示风或飞控响应让移动不足。
            ratio = actual_move / predicted_move
            ratio = max(0.40, min(1.60, ratio))
            target_gain = old_gain * ratio
            new_gain = (1.0 - alpha) * old_gain + alpha * target_gain
            self._axis_response_gain[axis] = max(gmin, min(gmax, new_gain))
        self._last_actuation_plan = None

    def build_timed_actuation_plan(self, measure):
        # 这是主要水平控制器，不是 PID：根据剩余距离一次性计算杆量和保持时间。
        # residual = |测量距离| - 允许死区；落在死区内就不再横移。
        if measure is None:
            return None
        stage_name = measure['stage_name']
        maxv = float(self.mqtt.joystick_effective_max_value(self.args))
        man = max(1e-6, float(self.args.manual_hor_spd_max))
        min_time = max(0.05, float(self.args.timed_actuation_min_time))
        max_time = max(min_time, self.get_stage_max_actuation_time(stage_name))
        dist_gain = float(self.args.timed_joystick_distance_gain)
        stage_min_joy = float(self.get_stage_min_joystick(stage_name))
        wind_bias = float(self.get_stage_wind_bias(stage_name))
        tol_scale = max(0.0, float(self.args.timed_distance_deadband_scale))

        def axis_plan(axis_name, body_dist, tol_m):
            # 杆量 = 阶段最小有效杆量 + 风补偿 + 距离增益*剩余距离。
            # 先由杆量估计理论速度，再乘响应系数得到预期有效速度。
            residual = max(0.0, abs(float(body_dist)) - tol_scale * abs(float(tol_m)))
            if residual <= 1e-4:
                return None
            joy = stage_min_joy + wind_bias + dist_gain * residual
            joy = max(stage_min_joy, min(maxv, joy))
            theoretical_speed = man * joy / maxv
            resp_gain = max(0.05, float(self._axis_response_gain.get(axis_name, 1.0)))
            eff_speed = max(0.03, theoretical_speed * resp_gain)
            # 基本物理关系 t = s/v；随后限制在当前高度阶段允许的时间区间。
            act_time = residual / eff_speed
            act_time = max(min_time, min(max_time, act_time))
            cmd_speed = theoretical_speed
            return {
                'axis': axis_name,
                'sign': 1.0 if body_dist >= 0.0 else -1.0,
                'residual_m': residual,
                'joystick': joy,
                'speed': cmd_speed,
                'time': act_time,
                'predicted_move_m': min(residual, theoretical_speed * resp_gain * act_time),
            }

        px = axis_plan('x', measure['body_x_m'], measure['tol_x_m'])
        py = axis_plan('y', measure['body_y_m'], measure['tol_y_m'])
        if px is None and py is None:
            return None
        axis_mode = str(getattr(self.args, 'axis_mode', 'single')).strip().lower()
        # single 模式选择剩余距离更大的轴；multi 模式让两个轴同时结束本轮动作。
        if axis_mode != 'multi' or px is None or py is None:
            chosen = px if py is None else py if px is None else (px if px['residual_m'] >= py['residual_m'] else py)
            cmd = ControlCommand(vx=chosen['sign'] * chosen['speed'] if chosen['axis'] == 'x' else 0.0,
                                 vy=chosen['sign'] * chosen['speed'] if chosen['axis'] == 'y' else 0.0,
                                 vz=0.0, yaw_rate=0.0)
            return {
                'cmd': cmd,
                'duration': chosen['time'],
                'axes': [chosen['axis']],
                'pre_body': {'x': float(measure['body_x_m']), 'y': float(measure['body_y_m'])},
                'predicted_move': {chosen['axis']: chosen['predicted_move_m']},
                'stage_name': stage_name,
                'joystick_preview': {chosen['axis']: chosen['joystick']},
            }

        hold_time = max(px['time'], py['time'])
        resp_x = max(0.05, float(self._axis_response_gain.get('x', 1.0)))
        resp_y = max(0.05, float(self._axis_response_gain.get('y', 1.0)))
        speed_x = px['residual_m'] / max(hold_time * resp_x, 1e-6)
        speed_y = py['residual_m'] / max(hold_time * resp_y, 1e-6)
        joy_x = max(stage_min_joy, min(maxv, maxv * speed_x / man + wind_bias))
        joy_y = max(stage_min_joy, min(maxv, maxv * speed_y / man + wind_bias))
        speed_x = man * joy_x / maxv
        speed_y = man * joy_y / maxv
        cmd = ControlCommand(vx=px['sign'] * speed_x, vy=py['sign'] * speed_y, vz=0.0, yaw_rate=0.0)
        return {
            'cmd': cmd,
            'duration': max(min_time, min(max_time, hold_time)),
            'axes': ['x', 'y'],
            'pre_body': {'x': float(measure['body_x_m']), 'y': float(measure['body_y_m'])},
            'predicted_move': {
                'x': min(px['residual_m'], speed_x * resp_x * hold_time),
                'y': min(py['residual_m'], speed_y * resp_y * hold_time),
            },
            'stage_name': stage_name,
            'joystick_preview': {'x': joy_x, 'y': joy_y},
        }

    def begin_actuation(self, plan, now):
        # 锁定本轮命令和结束时刻；执行期间不根据每帧噪声频繁改变方向。
        self._align_phase = 'actuate'
        self._actuate_cmd = plan['cmd']
        self._actuate_until = now + float(plan['duration'])
        self._last_actuation_plan = plan
        self._measure_samples = []

    def begin_descend_to_target(self, target_uav_h):
        self._descend_target_uav_h = float(target_uav_h)
        self.state_machine = self.DESCEND
        self.reset_measure_phase()

    def compute_target_pixel(self, camera_height):
        # 若相机不在机体控制中心正下方，真正目标像素并不总是图像中心。
        # 高度越高，固定机械偏移投影成的像素补偿越小；低空为防过补偿直接关闭。
        if camera_height is None or camera_height <= 0.0:
            return (self.args.camera_cx, self.args.camera_cy)
        if camera_height < float(self.args.offset_comp_disable_below):
            return (self.args.camera_cx, self.args.camera_cy)
        u_target = self.args.camera_cx - self.args.camera_fx * self.args.camera_offset_x / camera_height
        v_target = self.args.camera_cy - self.args.camera_fy * self.args.camera_offset_y / camera_height
        return (u_target, v_target)

    def estimate_height_from_marker(self, pixel_width):
        # 针孔估高 h = fx * marker_size / pixel_width。
        # 它忽略镜头畸变和标志倾斜，不能替代完整相机标定与 solvePnP。
        if pixel_width is None or pixel_width <= 1e-6:
            return None
        return (self.args.camera_fx * self.args.marker_size) / float(pixel_width)

    def get_current_height(self):
        return self.selected_height_for_control()

    def startup_guard_ok(self):
        # 防止脚本刚启动、尚未获得稳定图像/高度时立即进入自动降落。
        # 二次起飞高度过低时也拒绝开始，避免起落状态误判。
        if time.time() < self._startup_guard_until:
            return False
        src = self.selected_height_source()
        if src == 'vision':
            h_vis = self.vision_height()
            if h_vis is None:
                return True
            return h_vis >= float(self.args.min_startup_camera_height)
        raw = self.raw_radar_height()
        if raw is None:
            return True
        return raw >= float(self.args.min_startup_radar_height)

    def detect(self, frame_bgr):
        # OpenCV ArUco 返回每个方形码的四角点。这里只选择配置的 marker_id，
        # 用四角平均值得中心，用四条边平均长度作为视觉估高输入。
        result = DetectionResult()
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        try:
            corners, ids, _ = aruco.detectMarkers(gray, self.aruco_dict, parameters=self.detector_parameters)
        except TypeError:
            corners, ids, _ = aruco.detectMarkers(gray, self.aruco_dict)
        result.ids = ids
        if ids is None:
            return result
        ids_flat = ids.flatten().tolist()
        if int(self.args.marker_id) not in ids_flat:
            return result
        idx = ids_flat.index(int(self.args.marker_id))
        marker_corners = corners[idx][0]
        result.marker_corners = marker_corners
        # 图像坐标原点在左上：u 向右增大，v 向下增大。
        result.marker_center = np.mean(marker_corners, axis=0)
        side_lengths = []
        for i in range(4):
            p0 = marker_corners[i]
            p1 = marker_corners[(i + 1) % 4]
            side_lengths.append(float(np.linalg.norm(p0 - p1)))
        result.pixel_width = float(np.mean(side_lengths))
        result.detected = True
        return result

    def clip(self, v, lim):
        return max(min(float(v), float(lim)), -float(lim))

    def state_name(self):
        return ['SEARCH', 'ALIGN', 'DESCEND', 'LAND'][self.state_machine]

    def _handle_vision_loss_transition(self):
        # 丢码时可选先刹车/发零杆量。这里只发一次，避免每帧阻塞控制循环。
        if self.args.brake_on_vision_loss and not self._vision_lost_brake_sent:
            self.mqtt.send_brake()
            time.sleep(float(self.args.brake_hold_time))
            self._vision_lost_brake_sent = True

    def should_enter_land(self, du, dv, camera_h, raw_radar_h):
        # 正常进入 LAND 需要“足够低且基本对准”；更低的 force 阈值会忽略
        # 水平误差直接 LAND，目的是避免贴地持续横移，但风险必须现场评估。
        aligned_for_land = (abs(du) <= float(self.args.land_center_tolerance) and
                            abs(dv) <= float(self.args.land_center_tolerance))
        if self.marker_detected and self.pixel_width >= float(self.args.land_pixel_threshold) and aligned_for_land:
            return True
        src = self.selected_height_source()
        if src == 'vision':
            if camera_h is not None and camera_h <= float(self.args.land_camera_trigger_height) and aligned_for_land:
                return True
            if camera_h is not None and camera_h <= float(self.args.force_land_camera_height):
                return True
            return False
        if raw_radar_h is not None and raw_radar_h <= float(self.args.land_radar_trigger_height) and aligned_for_land:
            return True
        if raw_radar_h is not None and raw_radar_h <= float(self.args.force_land_radar_height):
            return True
        return False

    def low_alt_direct_vertical_active(self, camera_h, raw_radar_h):
        src = self.selected_height_source()
        if src == 'vision':
            return camera_h is not None and camera_h <= float(self.args.direct_vertical_camera_height)
        return raw_radar_h is not None and raw_radar_h <= float(self.args.direct_vertical_radar_height)

    def should_force_final_land(self, uav_h):
        return uav_h is not None and uav_h <= float(self.args.final_direct_land_height)

    def update(self, frame_bgr):
        # 每帧控制主函数：先更新视觉与高度，再按当前状态生成动作。
        # 返回值只描述意图，真正发送由 maybe_send_command() 统一门控。
        #
        # ---------------------------------------------------------------------
        # 状态机阅读手册
        # ---------------------------------------------------------------------
        # 状态机的价值是把“什么时候可以横移、什么时候可以下降、什么时候交给飞控”
        # 写成离散规则。若只用一条连续公式同时控制 xyz，很难保证低空时不横冲。
        #
        # SEARCH
        #   进入：程序启动，或者 ALIGN 中目标丢失。
        #   输出：默认 hold/中立摇杆，不主动盘旋寻找。
        #   退出：startup_guard_ok 且本帧检测到指定 marker，最近检测未超时。
        #   物理意义：没有可靠目标时不根据旧位置盲飞。
        #   风险：search_use_hold 的协议语义若与现场固件不同，可能发生模式变化。
        #
        # ALIGN.measure
        #   进入：首次发现目标、一次 actuation 结束，或到达分段下降目标高度。
        #   输出：水平零速度，尽量悬停；持续收集 du/dv/height。
        #   退出：采样时间和最少样本数同时满足。
        #   物理意义：先观察噪声和漂移，再决定一次动作，不被单帧角点抖动驱动。
        #   风险：采样太久会被风持续吹走；太短则均值不稳定。
        #
        # ALIGN.actuate
        #   进入：平均误差超出当前阶段死区，成功生成 actuation plan。
        #   输出：固定水平速度，持续到 _actuate_until；垂直速度为 0。
        #   退出：持续时间到期，然后回 measure。
        #   物理意义：给超过死区的有效杆量足够作用时间。
        #   风险：执行期间新视觉只被读取但不闭环修改命令，阵风或误测会导致过冲。
        #
        # DESCEND
        #   进入：本高度阶段已对准，但还没到最终阶段。
        #   输出：vx=vy=0，vz 为负；低空目标段可用更快下降速度。
        #   退出：机体高度达到 2 m 或 0.7 m 阶段目标，再回 ALIGN。
        #   物理意义：将长下降拆成几段，每段重新水平校准。
        #   风险：下降途中完全不做水平视觉纠偏，强风会一直漂到下一阶段才修正。
        #
        # LAND
        #   进入：最终阶段已对准，或者某些极低高度 force 条件满足。
        #   输出：只发送一次飞控 land 服务，后续等待接地确认。
        #   退出：接地确认或 finalize timeout 后，执行零命令、disarm 和状态恢复。
        #   物理意义：最终触地交给飞控内部降落器，而非 Python 连续下压油门。
        #   风险：force 条件可绕过水平对准；timeout 后落锁要求高度数据绝对可靠。
        #
        # ---------------------------------------------------------------------
        # detected 与 detection_timeout 不相同
        # ---------------------------------------------------------------------
        # marker_detected 只表示当前帧；detection_timeout 表示距最后成功检测是否仍在
        # loss_timeout 内。当前 ALIGN 分支要求二者都成立，所以当前帧丢码即退 SEARCH，
        # 并不会在 timeout 窗口内继续按旧误差横移。timeout 更多是防止陈旧检测状态。
        #
        # ---------------------------------------------------------------------
        # 为什么 update 不直接发 MQTT
        # ---------------------------------------------------------------------
        # update 负责“决策”，返回 cmd/action；maybe_send_command 负责“执行许可”。
        # 这种拆分让状态机可以每帧更新，但命令仍受以下门控：
        #
        # - control_rate：业务层最大发送频率。
        # - min_velocity_send_interval：最终不可绕过的时间间隔。
        # - send_every_n_frames：帧数间隔；变化足够大时可提前，但仍受时间间隔限制。
        # - velocity_resend_epsilon：小于阈值的浮点变化视为同一命令。
        # - autonomous mode：RTL/LAND 等模式中禁止脚本抢控制。
        # - recent motion reject：飞控刚拒绝命令后短暂停发，避免刷屏。
        # - OSD readiness：模式、joystick/PVA 状态必须真实就绪。
        # - near-center pause：可选的中心附近短暂停顿，目前默认关闭。
        #
        # 假设 control_rate=20 Hz 表示理论最短 0.05 s，但 min interval=0.12 s，真实
        # 上限仍只有约 8.3 Hz。调高 control_rate 并不会越过 0.12 s 的最终限制。
        #
        # ---------------------------------------------------------------------
        # 接地确认不是一个瞬时比较
        # ---------------------------------------------------------------------
        # touchdown_confirmed 要求高度低于阈值，同时 |vertical_speed| 小于阈值，并
        # 连续保持 touchdown_confirm_time。持续判定可过滤单帧雷达跳变或速度过零。
        # 若 vertical_speed 是 None，代码把速度条件视为满足，安全性退化为只看高度。
        #
        # should_finalize_land 还有 land_finalize_timeout 兜底。即使始终没有满足接地
        # 判定，超时也会进入 shutdown_after_land 并 disarm。这防止程序永久挂住，
        # 但若飞机仍在空中会非常危险；该时间不能未经机型和场地测试直接沿用。
        now = time.time()
        self.frame_index += 1
        det = self.detect(frame_bgr)
        self.last_detection = det

        if det.detected:
            self.marker_detected = True
            self.marker_center = det.marker_center
            self.pixel_width = det.pixel_width
            self.last_detection_time = now
            self.last_h_est = self.estimate_height_from_marker(self.pixel_width)
            self._vision_lost_brake_sent = False
        else:
            self.marker_detected = False
            self._last_du = None
            self._last_dv = None
            self._last_raw_du = None
            self._last_raw_dv = None

        # marker_detected 是“本帧看见”；detection_timeout 是“最近一段时间看见过”。
        detection_timeout = (now - self.last_detection_time) < float(self.args.loss_timeout)
        current_h = self.get_current_height()
        raw_radar_h = self.raw_radar_height()
        uav_h = self.selected_uav_height()
        stage_tol = self.get_stage_center_tolerance(uav_h)
        self._last_stage_name = self.get_stage_name(uav_h)

        cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)
        action = 'hold'

        if self.state_machine == self.SEARCH:
            # SEARCH 不主动搜索飞行，只等待稳定看到指定码，并用启动保护防误触发。
            self.reset_alignment_cycle()
            self._descend_target_uav_h = None
            if self.startup_guard_ok() and self.marker_detected and detection_timeout:
                self.state_machine = self.ALIGN
                self.align_start_time = now
                self.target_hold_height = current_h
                self.reset_alignment_cycle()

        elif self.state_machine == self.ALIGN:
            # ALIGN 交替执行两相：actuate 期间保持定时命令；结束后回 measure 悬停采样。
            if self._align_phase == 'actuate' and now < self._actuate_until:
                return {
                    'cmd': self._actuate_cmd,
                    'action': 'velocity',
                    'current_h': current_h,
                    'raw_radar_h': raw_radar_h,
                    'uav_h': uav_h,
                    'stage_tol': stage_tol,
                    'stage_name': self._last_stage_name,
                }
            if self._align_phase == 'actuate' and now >= self._actuate_until:
                self.reset_measure_phase()
                self.align_start_time = now

            if not self.marker_detected or not detection_timeout:
                # ALIGN 丢码立即退回 SEARCH，不用最后一次位置继续盲目横移。
                self._handle_vision_loss_transition()
                self.state_machine = self.SEARCH
                self.reset_alignment_cycle()
            else:
                h_cam = current_h if current_h is not None else max(self.last_h_est or 1.0, 0.1)
                u_target, v_target = self.compute_target_pixel(h_cam)
                # du/dv 是码中心相对期望像素的误差；可再旋转补偿相机安装偏航角。
                du = float(self.marker_center[0] - u_target)
                dv = float(self.marker_center[1] - v_target)
                if abs(float(self.args.image_yaw_comp_deg)) > 1e-6:
                    yaw_rad = np.deg2rad(float(self.args.image_yaw_comp_deg))
                    cos_y = np.cos(yaw_rad)
                    sin_y = np.sin(yaw_rad)
                    du_rot = cos_y * du - sin_y * dv
                    dv_rot = sin_y * du + cos_y * dv
                    du, dv = du_rot, dv_rot
                self._last_raw_du = du
                self._last_raw_dv = dv
                self._last_du = du
                self._last_dv = dv
                self.collect_measure_sample(du, dv, h_cam, uav_h)
                if self.align_start_time is None:
                    self.align_start_time = now
                # 同时满足采样时长和最少样本数，才相信这轮平均测量。
                measure_ready = (now - self.align_start_time) >= float(self.args.hover_measure_time)
                if measure_ready and len(self._measure_samples) >= int(self.args.hover_measure_min_samples):
                    measure = self.summarize_measure()
                    self.update_axis_response_from_measure(measure)
                    self._last_measure_result = measure
                    if measure is None:
                        self.align_start_time = now
                        self._measure_samples = []
                    else:
                        bx = float(measure['body_x_m'])
                        by = float(measure['body_y_m'])
                        tolx = float(measure['tol_x_m'])
                        toly = float(measure['tol_y_m'])
                        aligned = (abs(bx) <= tolx and abs(by) <= toly)
                        self._last_stage_name = measure['stage_name']
                        if aligned:
                            # 对准后不继续打杆：最终高度直接 LAND，否则下降到下一阶段。
                            if self.should_force_final_land(measure['uav_h']):
                                self.state_machine = self.LAND
                            else:
                                target = self.get_stage_target_height(measure['uav_h'])
                                if target is None:
                                    self.state_machine = self.LAND
                                else:
                                    self.begin_descend_to_target(target)
                        else:
                            # 未对准时生成一次定时纠偏计划，再回到悬停测量验证效果。
                            plan = self.build_timed_actuation_plan(measure)
                            if plan is not None:
                                self.begin_actuation(plan, now)
                                cmd = self._actuate_cmd
                                action = 'velocity'
                            else:
                                self.align_start_time = now
                                self._measure_samples = []

        elif self.state_machine == self.DESCEND:
            # DESCEND 阶段水平命令固定为 0，仅下降到阶段目标；到达后重新 ALIGN。
            # 这意味着下降途中不会实时纠偏，风大时会在下一阶段才消除漂移。
            target = self._descend_target_uav_h
            if target is None:
                target = self.get_stage_target_height(uav_h)
                self._descend_target_uav_h = target
            if uav_h is not None and target is not None and uav_h <= float(target) + float(self.args.timed_descent_target_margin):
                self.state_machine = self.ALIGN
                self.align_start_time = now
                self.target_hold_height = current_h
                self.reset_alignment_cycle()
            else:
                vz_des = -float(self.args.descent_speed)
                if target is not None and target <= float(self.args.final_direct_land_height) and self.args.low_alt_fast_descent_speed > 0.0:
                    vz_des = -float(self.args.low_alt_fast_descent_speed)
                cmd = ControlCommand(0.0, 0.0, vz_des, 0.0)
                action = 'velocity'

        if self.state_machine == self.LAND:
            # LAND 只产生一次“调用飞控降落服务”的动作，不再直接控制速度。
            action = 'land'
            cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)

        self._last_action = action
        return {
            'cmd': cmd,
            'action': action,
            'current_h': current_h,
            'raw_radar_h': raw_radar_h,
            'uav_h': uav_h,
            'stage_tol': stage_tol,
            'stage_name': self._last_stage_name,
        }

    def _cmd_changed_enough(self, cmd):
        # 只有变化超过 epsilon 才视为新命令，过滤浮点抖动和无意义 MQTT 刷新。
        prev = self._last_sent_velocity_cmd
        return (abs(cmd.vx - prev.vx) >= float(self.args.velocity_resend_epsilon) or
                abs(cmd.vy - prev.vy) >= float(self.args.velocity_resend_epsilon) or
                abs(cmd.vz - prev.vz) >= float(self.args.vertical_resend_epsilon) or
                abs(cmd.yaw_rate - prev.yaw_rate) >= float(self.args.velocity_resend_epsilon))

    def _maybe_send_idle_zero(self, now, reason='idle'):
        # 空闲时仍以 10 Hz 左右发送中立摇杆，明确告诉飞控“不运动”。
        if not self.mqtt.uses_joystick_control(self.args):
            return False
        if self.mqtt.is_autonomous_mode():
            return False
        interval = 0.10
        if (now - self._last_idle_zero_ts) < interval:
            return False
        sent = self.mqtt.send_zero_velocity(self.args, repeat=1, interval=0.0, quiet=True)
        if sent:
            self._last_idle_zero_ts = now
            self._last_sent_velocity_cmd = ControlCommand(0.0, 0.0, 0.0, 0.0)
            if self.args.debug_send_gate:
                print('[SEND_GATE] neutral joystick only, reason={}'.format(reason))
        return sent

    def maybe_send_command(self, cmd, action):
        # 最终命令安全门：按顺序检查 LAND 单次发送、控制频率、自主模式、
        # 最近拒绝、OSD 就绪、近中心暂停、帧间隔和命令变化。
        now = time.time()
        if action == 'land':
            if not self._land_cmd_sent:
                self.mqtt.send_land(self.args)
                self._land_cmd_sent = True
                self._land_start_time = now
            return True
        if action == 'hold' or action == 'none':
            self._maybe_send_idle_zero(now, reason=action)
            self.last_cmd_time = now
            return False
        if (now - self.last_cmd_time) < (1.0 / max(float(self.args.control_rate), 1.0)):
            return False

        if self.mqtt.is_autonomous_mode():
            # 发现飞控进入 RTL/LAND 等自主模式后停止发运动命令，避免争夺控制权。
            self.mqtt.maybe_warn_auto_mode_block()
            self.last_cmd_time = now
            return False

        if self.mqtt.has_recent_motion_reject(self.args.motion_reject_holdoff):
            if self.args.debug_send_gate:
                print('[SEND_GATE] blocked by recent motion reject; runtime does not reacquire mode/joystick automatically')
            self._maybe_send_idle_zero(now, reason='motion_reject')
            self.last_cmd_time = now
            return False

        if not self.mqtt.is_manual_control_ready():
            # 未就绪时默认只发零杆量，而不是运行中反复强制切模式。
            self.mqtt.maybe_warn_not_ready()
            if self.args.not_ready_action in ('hold', 'brake_hold') and not self.mqtt.is_autonomous_mode():
                if self.mqtt.uses_joystick_control(self.args):
                    self._maybe_send_idle_zero(now, reason='not_ready')
                elif self.args.not_ready_action == 'brake_hold':
                    self.mqtt.send_brake()
            self.last_cmd_time = now
            return False

        if self.state_machine != self.SEARCH or (self.state_machine == self.SEARCH and not self.args.search_use_hold):
            if now < self._near_center_pause_until:
                self._maybe_send_idle_zero(now, reason='near_center_pause')
                if self.args.debug_send_gate:
                    print('[SEND_GATE] blocked by near-center pause: remain={:.3f}s'.format(self._near_center_pause_until - now))
                return False

            frame_gap = int(self.args.send_every_n_frames)
            # control_rate 是外层节流；min_velocity_send_interval 是不可绕过的最终上限。
            time_gap_ok = (now - self._last_velocity_logic_send_ts) >= float(self.args.min_velocity_send_interval)
            frame_gap_ok = (self.frame_index - self._last_velocity_logic_frame) >= max(1, frame_gap)
            changed_enough = self._cmd_changed_enough(cmd)
            if not time_gap_ok:
                if self.args.debug_send_gate:
                    print('[SEND_GATE] blocked by min interval: dt={:.3f} < {:.3f}'.format(now - self._last_velocity_logic_send_ts, float(self.args.min_velocity_send_interval)))
                return False
            if not (frame_gap_ok or changed_enough):
                if self.args.debug_send_gate:
                    print('[SEND_GATE] blocked by frame gap/change: frame_gap={} need={} changed_enough={}'.format(self.frame_index - self._last_velocity_logic_frame, max(1, frame_gap), changed_enough))
                return False
            sent = self.mqtt.send_velocity(cmd, self.args)
            self.last_cmd_time = now
            if sent:
                self._last_sent_velocity_cmd = ControlCommand(cmd.vx, cmd.vy, cmd.vz, cmd.yaw_rate)
                self._last_velocity_logic_send_ts = now
                self._last_velocity_logic_frame = self.frame_index
                near_thr = float(self.args.near_center_pause_threshold)
                if self.state_machine == self.ALIGN and near_thr > 0.0 and self._last_du is not None and self._last_dv is not None and (abs(cmd.vx) > 1e-6 or abs(cmd.vy) > 1e-6):
                    if str(self.args.near_center_pause_mode).lower() == 'or':
                        near_hit = (abs(self._last_du) <= near_thr or abs(self._last_dv) <= near_thr)
                    else:
                        near_hit = (abs(self._last_du) <= near_thr and abs(self._last_dv) <= near_thr)
                    if near_hit:
                        self._near_center_pause_until = now + float(self.args.near_center_pause_time)
            return sent
        self.last_cmd_time = now
        return False

    def touchdown_confirmed(self):
        # 接地不能只看高度瞬时值：还要求垂直速度足够小，并连续保持确认时长。
        # 若 OSD 没有垂直速度，代码会放宽为只检查高度。
        now = time.time()
        raw_radar_h = self.raw_radar_height()
        camera_h = self.get_current_height()
        low_enough = False
        src = self.selected_height_source()
        if src == 'vision':
            if camera_h is not None and camera_h <= float(self.args.touchdown_camera_height):
                low_enough = True
        else:
            if raw_radar_h is not None and raw_radar_h <= float(self.args.touchdown_radar_height):
                low_enough = True
        vs = self.mqtt.vertical_speed
        vs_ok = True if vs is None else (abs(float(vs)) <= float(self.args.touchdown_vertical_speed))
        if low_enough and vs_ok:
            if self._touchdown_start_ts is None:
                self._touchdown_start_ts = now
            return (now - self._touchdown_start_ts) >= float(self.args.touchdown_confirm_time)
        self._touchdown_start_ts = None
        return False

    def should_finalize_land(self, now):
        # 正常路径在确认接地后收尾；兜底路径在 LAND 超时后也收尾并 disarm。
        # 超时落锁是现场策略，不是通用安全保证。
        if self._land_start_time is None:
            return False
        if self.touchdown_confirmed():
            return True
        return (now - self._land_start_time) >= float(self.args.land_finalize_timeout)

    def draw_overlay(self, frame_bgr, update_info, source_lag=None):
        # 预览叠加层只用于观察，不参与控制计算。它显示状态、误差、高度和命令。
        out = frame_bgr.copy()
        h = update_info['current_h']
        raw_radar_h = update_info.get('raw_radar_h')
        uav_h = update_info.get('uav_h')
        stage_name = update_info.get('stage_name', self._last_stage_name)
        stage_tol = update_info.get('stage_tol')
        u_target, v_target = self.compute_target_pixel(h if h is not None else 0.0)
        u_target_i = int(round(u_target))
        v_target_i = int(round(v_target))
        cv2.circle(out, (u_target_i, v_target_i), 8, (255, 0, 0), 2)
        cv2.line(out, (0, int(round(v_target))), (out.shape[1]-1, int(round(v_target))), (0, 255, 0), 1)
        cv2.line(out, (int(round(self.args.camera_cx)), 0), (int(round(self.args.camera_cx)), out.shape[0]-1), (120, 120, 120), 1)
        cv2.line(out, (0, int(round(self.args.camera_cy))), (out.shape[1]-1, int(round(self.args.camera_cy))), (120, 120, 120), 1)
        if self.last_detection.detected and self.last_detection.marker_corners is not None:
            pts = self.last_detection.marker_corners.astype(np.int32)
            cv2.polylines(out, [pts], True, (0, 255, 0), 2)
            mc = (int(round(self.last_detection.marker_center[0])), int(round(self.last_detection.marker_center[1])))
            cv2.circle(out, mc, 7, (0, 255, 0), -1)
            cv2.line(out, (u_target_i, v_target_i), mc, (0, 255, 0), 2)
        txt = [
            'state={}'.format(self.state_name()),
            'marker_detected={}'.format(self.last_detection.detected),
            'pixel_width={:.1f}'.format(self.pixel_width),
            'camera_h={:.2f}m'.format(h) if h is not None else 'camera_h=None',
            'radar_h={:.2f}m'.format(raw_radar_h) if raw_radar_h is not None else 'radar_h=None',
            'height_src={}'.format(self.args.height_judge_source),
            'control_method={}'.format(self.args.control_method),
            'uav_h={:.2f}m'.format(uav_h) if uav_h is not None else 'uav_h=None',
            'stage={}'.format(stage_name),
            'stage_tol={:.1f}'.format(stage_tol) if stage_tol is not None else 'stage_tol=None',
        ]
        if self.last_detection.detected:
            du = self.last_detection.marker_center[0] - u_target
            dv = self.last_detection.marker_center[1] - v_target
            txt.append('du={:.1f} dv={:.1f}'.format(du, dv))
            if self._last_du is not None and self._last_dv is not None:
                txt.append('du_f={:.1f} dv_f={:.1f}'.format(self._last_du, self._last_dv))
        txt.append('control_rate={}'.format(self.args.control_rate))
        txt.append('frame={} source={} mode={}'.format(self.frame_index, self.args.input, self.args.input_mode))
        txt.append('raw_fly_mode={} norm_mode={} js={} pva={}'.format(
            self.mqtt.fly_mode, self.mqtt.normalize_fly_mode(self.mqtt.fly_mode), self.mqtt.joystick_state, self.mqtt.pva_state))
        txt.append('invX={} invY={} swapXY={} yawComp={:.1f} offDisable<{:.2f}m'.format(
            self.args.invert_x, self.args.invert_y, self.args.swap_xy,
            float(self.args.image_yaw_comp_deg), float(self.args.offset_comp_disable_below)))
        txt.append('axis_mode={} minEffMode={} minEffXY={}/{} minEffZ={}/{}'.format(
            str(getattr(self.args, 'axis_mode', 'single')).lower(),
            str(getattr(self.args, 'joystick_min_effective_mode', 'hold')).lower(),
            int(getattr(self.args, 'joystick_xy_min_effective_value', 0)),
            int(getattr(self.args, 'joystick_xy_force_value', 0)),
            int(getattr(self.args, 'joystick_z_min_effective_value', 0)),
            int(getattr(self.args, 'joystick_z_force_value', 0))))
        if source_lag is not None:
            txt.append('tail_lag_ms={:.1f}'.format(1000.0 * source_lag))
        y = 35
        for s in txt:
            cv2.putText(out, s, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            y += 34
        return out


class OpenCVVideoSource(object):
    # 简单视频源：OpenCV 直接读取摄像头编号、普通视频文件或 RTSP 地址。
    # 每次 read() 同步解码一帧，适合离线视频和常规视频流。
    def __init__(self, args):
        self.args = args
        self.cap = None
        self.is_camera = False
        self.last_frame_ts = None

    def open(self):
        # 只有短纯数字字符串才解释为摄像头索引，例如 "0"；其余按路径/URL 处理。
        src = self.args.input
        if src.isdigit() and len(src) <= 2:
            src_obj = int(src)
            self.is_camera = True
        else:
            src_obj = src
        self.cap = cv2.VideoCapture(src_obj)
        if not self.cap.isOpened():
            raise RuntimeError('无法打开输入源: {}'.format(src))
        return self.cap

    def read(self, timeout=None):
        # 普通文件可选循环播放；时间戳记录“本进程拿到帧”的时刻，而非相机曝光时刻。
        ret, frame = self.cap.read()
        if not ret:
            if self.args.loop_video and (not self.is_camera):
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            if not ret:
                return False, None, None
        self.last_frame_ts = time.time()
        return True, frame, self.last_frame_ts

    def release(self):
        if self.cap is not None:
            self.cap.release()


class TailH264Source(object):
    # 低延迟增长文件输入。另一个进程持续向 received_video.h264 追加码流，
    # 本类像 tail -f 一样读取新增字节并交给 FFmpeg 解码，只保留最新 BGR 帧。
    #
    # 三个后台线程：writer 把 H264 字节写入 FFmpeg stdin；reader 从 stdout
    # 组装固定大小 BGR 帧；stderr 收集解码错误。主线程通过 Condition 取最新帧。
    #
    # =========================================================================
    # 第三章：为什么视频输入会影响控制稳定性
    # =========================================================================
    # 控制器需要的是“当前飞机看到什么”，不是完整播放每一帧。若摄像头 30 FPS，
    # 算法只能处理 10 FPS，却把剩余帧排队，延迟会持续增长：一分钟后处理的可能是
    # 几秒前画面。即使检测精确，用旧误差控制当前飞机也会形成严重振荡。
    # 因此 TailH264Source 只保存 latest_frame，新帧覆盖旧帧。丢帧降低时间分辨率，
    # 但能保持反馈“新鲜”；对实时控制，低延迟通常比逐帧完整更重要。
    #
    # OpenCVVideoSource 与 TailH264Source：
    # - OpenCV 路径简单，适合普通文件、摄像头和 RTSP；底层缓冲多少取决于后端。
    # - tail 路径适合另一个进程持续追加的裸 H264 文件，可显式控制读取与解码缓存。
    #
    # 裸 H264 不是一张张独立图片。SPS 描述序列参数，PPS 描述图像参数，IDR 是可
    # 独立开始解码的关键帧；普通 P/B 帧可能依赖之前帧。若从文件末尾随便一个字节
    # 开始，FFmpeg 可能在下一个 SPS/PPS/IDR 前都无法输出画面。
    #
    # tail_start_mode=warm 会从末尾往前回看 tail_warm_bytes，使 FFmpeg 更可能先读到
    # 必要参数和关键帧。但这些历史字节可能属于上一次飞行，所以 _live_data_seen 在
    # 读指针越过启动时 initial_size 前阻止主线程使用画面。启动快与避免旧帧控制之间
    # 就是这里的取舍。
    #
    # 数据流和线程：
    #
    #   growing .h264 file
    #       | writer thread: read bytes, handle rotation/truncation
    #       v
    #   FFmpeg stdin -> decoder -> FFmpeg stdout (raw BGR bytes)
    #                               |
    #                               | reader thread: _read_exact(frame_bytes)
    #                               v
    #                         latest_frame + Condition
    #
    # stderr thread 必须持续读取错误输出。若子进程 stderr 管道写满而无人消费，FFmpeg
    # 可能阻塞，继而停止 stdout，表现为视频莫名卡死。
    #
    # 为什么 _read_exact？管道的 read(n) 只保证“最多 n 字节”，不保证一次凑满。
    # BGR24 每像素 3 字节，因此一帧严格需要 width*height*3。少一个字节就 reshape，
    # 下一帧边界会整体错位，画面数据不可用。
    #
    # 文件轮转：录像进程可能删除旧文件并创建同名新文件。Unix 可用 inode 判断；
    # Windows 的 st_ino 行为依文件系统而异。文件大小变小则视为截断。两种情况都要
    # 关闭旧句柄、重置 live_data_seen 并重新打开。
    #
    # FFmpeg 低延迟参数：
    # - nobuffer/low_delay 尽量减少内部缓存；
    # - analyzeduration=0 和小 probesize 缩短格式探测；
    # - avioflags=direct 尽量减少 I/O 缓冲；
    # - stdin flush 可更快把小块数据交给 FFmpeg，但增加系统调用和 CPU 开销。
    #
    # 参数并非越小越好。probesize 太小可能拿不到足够参数，低码率或损坏码流更易
    # 启动失败；轮询间隔太小会空转消耗 CPU；read_chunk 太小增加调用次数，太大则
    # 可能等待更多数据。应同时观测 source_lag、CPU、解码错误和检测帧率。
    #
    # 时间戳局限：latest_frame_ts 是“本机解码完成时间”，不是相机曝光时间。网络、
    # 写文件和编码阶段的延迟没有被计入，所以 overlay 显示的 lag 是下界。高可靠
    # 系统应让采集端携带源时间戳，并做时钟同步。
    #
    # release 设置 stop_event、唤醒等待者、terminate FFmpeg，超时后才 kill。守护线程
    # 随进程退出，但显式收尾能减少管道未关闭、FFmpeg 残留和文件句柄泄漏。
    def __init__(self, args):
        self.args = args
        self.proc = None
        self.stop_event = threading.Event()
        self.frame_bytes = int(args.image_width) * int(args.image_height) * 3
        self.latest_frame = None
        self.latest_frame_ts = None
        self.latest_seq = 0
        self._cond = threading.Condition()
        self._reader_thread = None
        self._writer_thread = None
        self._stderr_thread = None
        self._tail_offset = 0
        self._initial_size = 0
        self._live_data_seen = False
        self._last_file_size = 0

    def _build_ffmpeg_cmd(self):
        # nobuffer/low_delay/小 probesize 用启动稳定性换取较低延迟。
        # 输出 bgr24 rawvideo，所以每帧字节数严格为 width*height*3。
        return [
            self.args.ffmpeg_bin,
            '-hide_banner',
            '-loglevel', 'error',
            '-fflags', 'nobuffer',
            '-flags', 'low_delay',
            '-analyzeduration', '0',
            '-probesize', str(int(self.args.ffmpeg_probesize)),
            '-avioflags', 'direct',
            '-f', 'h264',
            '-i', 'pipe:0',
            '-pix_fmt', 'bgr24',
            '-f', 'rawvideo',
            '-vsync', '0',
            'pipe:1',
        ]

    def open(self):
        # 先等 H264 文件出现，再启动 FFmpeg 和三个守护线程。
        path = self.args.input
        start_wait = time.time()
        while not os.path.exists(path):
            if time.time() - start_wait > float(self.args.tail_open_timeout):
                raise RuntimeError('等待输入文件超时: {}'.format(path))
            time.sleep(float(self.args.tail_poll_interval))

        cmd = self._build_ffmpeg_cmd()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self._reader_thread = threading.Thread(target=self._reader_loop, name='ffmpeg-reader')
        self._reader_thread.daemon = True
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, name='ffmpeg-stderr')
        self._stderr_thread.daemon = True
        self._stderr_thread.start()
        self._writer_thread = threading.Thread(target=self._writer_loop, name='h264-tail-writer')
        self._writer_thread.daemon = True
        self._writer_thread.start()
        return self

    def _stderr_loop(self):
        try:
            while not self.stop_event.is_set() and self.proc is not None and self.proc.stderr is not None:
                line = self.proc.stderr.readline()
                if not line:
                    break
                try:
                    txt = line.decode('utf-8', errors='ignore').strip()
                except Exception:
                    txt = repr(line)
                if txt:
                    print('[FFMPEG] {}'.format(txt))
        except Exception:
            pass

    def _reader_loop(self):
        # 管道 read() 不保证一次返回完整帧，因此必须用 _read_exact 累积够 frame_bytes。
        try:
            while not self.stop_event.is_set() and self.proc is not None and self.proc.stdout is not None:
                chunk = self._read_exact(self.proc.stdout, self.frame_bytes)
                if chunk is None:
                    break
                frame = np.frombuffer(chunk, dtype=np.uint8)
                if frame.size != self.frame_bytes:
                    continue
                frame = frame.reshape((int(self.args.image_height), int(self.args.image_width), 3))
                ts = time.time()
                with self._cond:
                    self.latest_frame = frame.copy()
                    self.latest_frame_ts = ts
                    self.latest_seq += 1
                    self._cond.notify_all()
        except Exception as e:
            print('[TAIL_H264] reader error: {}'.format(e))

    def _read_exact(self, fd, n):
        buf = bytearray()
        while len(buf) < n and not self.stop_event.is_set():
            chunk = fd.read(n - len(buf))
            if not chunk:
                time.sleep(0.002)
                if self.proc is not None and self.proc.poll() is not None:
                    return None
                continue
            buf.extend(chunk)
        if len(buf) != n:
            return None
        return bytes(buf)

    def _calc_start_offset(self, size_now):
        # start 从头解码；end 只等新数据；warm 回看一段历史以找到 SPS/PPS/IDR，
        # 让 FFmpeg 更快获得解码参数，同时后续用 live_data_seen 拒绝旧画面控制。
        mode = self.args.tail_start_mode
        if mode == 'start':
            return 0
        if mode == 'end':
            return size_now
        warm = int(self.args.tail_warm_bytes)
        if warm <= 0:
            return size_now
        return max(0, size_now - warm)

    def _writer_loop(self):
        # 持续检测文件轮转和截断。录像进程重建文件后必须关闭旧句柄并重新打开。
        path = self.args.input
        fp = None
        inode = None
        try:
            while not self.stop_event.is_set():
                if fp is None:
                    while not os.path.exists(path) and not self.stop_event.is_set():
                        time.sleep(float(self.args.tail_poll_interval))
                    if self.stop_event.is_set():
                        break
                    fp = open(path, 'rb', buffering=0)
                    st = os.fstat(fp.fileno())
                    inode = getattr(st, 'st_ino', None)
                    self._initial_size = int(st.st_size)
                    self._last_file_size = int(st.st_size)
                    self._tail_offset = self._calc_start_offset(st.st_size)
                    fp.seek(self._tail_offset, os.SEEK_SET)
                    print('[TAIL_H264] open {} start_offset={} initial_size={}'.format(path, self._tail_offset, self._initial_size))
                try:
                    st = os.stat(path)
                except OSError:
                    st = None
                if st is not None:
                    cur_inode = getattr(st, 'st_ino', None)
                    if inode is not None and cur_inode is not None and cur_inode != inode:
                        print('[TAIL_H264] file rotated, reopen')
                        try:
                            fp.close()
                        except Exception:
                            pass
                        fp = None
                        inode = None
                        self._live_data_seen = False
                        continue
                    if st.st_size < self._tail_offset:
                        print('[TAIL_H264] file truncated, reopen from start')
                        try:
                            fp.close()
                        except Exception:
                            pass
                        fp = None
                        inode = None
                        self._live_data_seen = False
                        continue
                    self._last_file_size = int(st.st_size)
                data = fp.read(int(self.args.tail_read_chunk))
                if data:
                    prev_offset = self._tail_offset
                    self._tail_offset += len(data)
                    # 读指针越过脚本启动时的文件末尾，才说明已经到达本次运行的新数据。
                    if prev_offset < self._initial_size and self._tail_offset > self._initial_size:
                        self._live_data_seen = True
                        print('[TAIL_H264] live bytes reached after warm history.')
                    elif prev_offset >= self._initial_size:
                        self._live_data_seen = True
                    try:
                        self.proc.stdin.write(data)
                        if self.args.ffmpeg_stdin_flush:
                            self.proc.stdin.flush()
                    except Exception as e:
                        print('[TAIL_H264] write to ffmpeg failed: {}'.format(e))
                        break
                else:
                    time.sleep(float(self.args.tail_poll_interval))
        except Exception as e:
            print('[TAIL_H264] writer error: {}'.format(e))
        finally:
            if fp is not None:
                try:
                    fp.close()
                except Exception:
                    pass
            try:
                if self.proc is not None and self.proc.stdin:
                    self.proc.stdin.close()
            except Exception:
                pass

    def read(self, timeout=None):
        # 等待序号变化，返回最新帧而不是排队处理全部旧帧；控制系统宁可丢帧，
        # 也不应带着越来越大的视频延迟控制当前飞机。
        deadline = None if timeout is None else (time.time() + float(timeout))
        with self._cond:
            start_seq = self.latest_seq
            while not self.stop_event.is_set():
                if self.args.tail_require_live_data and (not self._live_data_seen):
                    if deadline is not None:
                        remain = deadline - time.time()
                        if remain <= 0:
                            return False, None, None
                        self._cond.wait(min(remain, 0.05))
                    else:
                        self._cond.wait(0.05)
                    continue
                if self.latest_frame is not None and self.latest_seq != start_seq:
                    return True, self.latest_frame.copy(), self.latest_frame_ts
                if self.latest_frame is not None and start_seq == 0:
                    return True, self.latest_frame.copy(), self.latest_frame_ts
                if deadline is not None:
                    remain = deadline - time.time()
                    if remain <= 0:
                        return False, None, None
                    self._cond.wait(min(remain, 0.05))
                else:
                    self._cond.wait(0.05)
        return False, None, None

    def release(self):
        # 通知线程退出，先温和 terminate FFmpeg，超时才 kill。
        self.stop_event.set()
        try:
            with self._cond:
                self._cond.notify_all()
        except Exception:
            pass
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


def build_parser():
    # 参数很多是因为该脚本带有现场调参历史。阅读时按下面的分组理解，
    # 不要把每个参数都当成独立算法。
    #
    # =========================================================================
    # 第四章：参数调优手册
    # =========================================================================
    #
    # 调参第一原则：一次只改一个物理问题相关的小组，保留录像、OSD 和实际位移。
    # 若同时改轴符号、增益、死区和高度阈值，即使结果变好也无法知道原因。
    #
    # A. 图像尺寸与相机内参
    #
    # image_width/height 必须与送入检测器的实际 resize 后尺寸一致。camera_cx/cy
    # 通常接近宽高一半，但应来自标定。fx/fy 控制像素到角度/距离的比例：
    # fx 填得过大，会估出更高高度，但同一像素误差换算出的水平距离也可能变化；
    # 不要用“调 fx”弥补 marker_size 或安装偏移错误。
    #
    # camera_offset_x/y 描述相机与期望机体落点的水平机械偏移。高空时换成较小像素
    # 补偿，低空像素补偿会变大，因此 offset_comp_disable_below 在低空关闭它，避免
    # 因高度噪声让目标像素剧烈移动。若机械偏移是真实且标定可靠，直接关闭也会留下
    # 固定落点偏差；这是稳定性与精度的取舍。
    #
    # swap_xy、invert_x/y、image_yaw_comp_deg 决定控制方向，是最高风险参数。方向
    # 错误时不要先降低增益继续飞，应停机确认坐标链。yaw 补偿角单位是度，符号要用
    # 人工移动标志和输出日志验证。
    #
    # B. Marker 参数
    #
    # marker_size 单位米，必须是编码黑白方形区域对应的真实边长，而非整个降落板。
    # 填大 10%，视觉高度也大约高估 10%。marker_id 防止追踪场景中其他码；字典配置
    # 必须和打印标志一致。min_marker_perimeter_rate 调大可过滤小噪声，也会让远距离
    # 小目标更早消失；调小提高远距召回，但误检和计算量可能增加。
    #
    # C. 高度机械偏移与来源
    #
    # radar_ground_offset 和 camera_ground_offset 是传感器到机体参考落地点的机械
    # 高度。它们影响“传感器高度”转“机体离地高度”。误差在高空不明显，接近地面
    # 却会直接改变 LAND、touchdown 和 startup guard 条件。
    #
    # height_judge_source=vision 依赖 ArUco 尺寸，受倾斜和模糊影响；radar 通常更适合
    # 近地高度，但可能受地面材质、盲区和安装角影响。选择来源不等于自动融合，代码
    # 没有 EKF，也没有基于测量方差动态加权。
    #
    # D. 悬停采样
    #
    # hover_measure_time 增大：均值更稳、控制更慢、持续风漂移更大。
    # hover_measure_min_samples 增大：要求更多有效帧；视频帧率下降或偶发丢码时可能
    # 长期无法决策。二者必须结合实际有效检测 FPS，例如 2 s 内要求 18 个样本只需
    # 9 FPS，但若有效检测只有 5 FPS 就永远不够。
    #
    # E. 杆量和动作时间
    #
    # timed_stage_min_joystick 必须略高于飞控真实起效门槛。太低导致计划执行却不动；
    # 太高导致最小一步过大。high/mid/final 应随高度降低而收紧，低空不能沿用高空
    # 猛烈杆量。
    #
    # timed_wind_bias 是无方向估计的“额外力度”，不是基于风向的前馈。它在所有修正
    # 方向上增加绝对杆量；太大会造成无风时过冲。真正风补偿应估计扰动向量，而非
    # 只提高最小杆量。
    #
    # timed_joystick_distance_gain 决定误差每增加 1 m 附加多少杆量。增大它会让大误差
    # 更快修正，但 joy 最终仍被 joystick_max 截断。若许多计划都顶到上限，再增大
    # gain 没有效果，只会缩小未饱和区。
    #
    # min/max actuation time 与最小杆量共同决定“最小位移步长”。即使 residual 很小，
    # 也至少以有效杆量运动 min_time。低空振荡时应检查这一最小步长是否已经大于允许
    # 误差，而不是只调像素容差。
    #
    # F. 响应自适应
    #
    # response_gain_init 是对飞控实际响应/理论速度的初始猜测。填小会算出更长时间，
    # 可能首轮过冲；填大则首轮移动不足。update_alpha 大表示相信最近一轮，适应快但
    # 易被误检污染；小表示变化平滑但适应风和载荷变化慢。gain_min/max 防止发散。
    #
    # G. 容差与阶段高度
    #
    # high/mid/final center tolerance 单位 px，不是厘米。相同 px 在高空代表更大米级
    # 距离。增大容差会更快进入下降但落点更偏；减小会反复 ALIGN，甚至因噪声永远
    # 无法下降。final 容差应结合相机高度换算成实际允许落点误差后确定。
    #
    # stage_high_alt_height 和 final_direct_land_height 决定何时切换参数组。阈值附近
    # 高度噪声可能使阶段来回变化，代码没有滞回区；因此高度源抖动要先解决。
    #
    # descent_speed 是常规段下降速度，low_alt_fast_descent_speed 名称虽叫 fast，
    # 是否安全取决于飞控和起落架。下降更快减少风漂移时间，却缩短视觉与人工反应
    # 时间，并可能导致地效或高度测量延迟引起硬着陆。
    #
    # direct_vertical_* 低于阈值后停止水平调整，目的是避免贴地横移翻覆；设得过高会
    # 带着较大偏差直降。force_land_* 更激进：低于阈值可无视对准直接 LAND。
    # 这两组阈值必须和传感器机械 offset、盲区一起标定。
    #
    # H. MQTT 和飞控限制
    #
    # manual_hor/cli/land_spd_max 同时参与飞控限制和速度到杆量比例。增大上限时，同样
    # m/s 请求换算出的杆量反而更小；若落入死区，又会被强制提升。它不是简单的
    # “最大速度越大飞得越快”，而会改变整条换算链。
    #
    # joystick_max_value 最终还受 hard_limit 限制。默认 300 远小于协议可能允许的
    # 1000，是现场保守上限。xy/z trigger、force 和 bypass 必须满足合理关系：force
    # 应高于真实起效门槛，bypass 决定何时保留原始大杆量。
    #
    # joystick_min_effective_mode=hold 连续、响应确定但最小动作较大；pulse 平均作用
    # 更细，却依赖命令频率、网络抖动和飞控对短脉冲的响应。周期若比实际发送间隔还
    # 短，程序可能总采到相同相位，理论占空比不成立。
    #
    # I. 命令调度
    #
    # control_rate、min_velocity_send_interval、send_every_n_frames 和 keepalive 是四层
    # 约束。真实发送频率由最严格者决定。调试“为何没发命令”应打开 debug_send_gate，
    # 不要盲目同时减小所有间隔。
    #
    # resend_epsilon 太小会把噪声当新命令频繁发送；太大则真实小修正不更新。near
    # center pause 默认关闭，开启后可能造成“动一下、停一下又被风吹走”的节拍振荡。
    #
    # J. 接地和落锁
    #
    # touchdown height 必须对应所选高度源的物理参考点。vertical_speed 阈值太大，
    # 尚在下降也可能被视为稳定；confirm_time 太短易受瞬时值影响，太长会延迟落锁。
    # land_finalize_timeout 到期无条件进入收尾，是全文件风险最高的参数之一。
    #
    # no_disarm 是 store_true、默认 False，可显式禁用自动落锁；但 mqtt_enable、
    # subscribe_osd/reply、wait_reply、setup_before_run、require_osd_ready、
    # force_ready_on_start、restore_mode_on_interrupt 和 tail_require_live_data 使用
    # store_true 且 default=True，当前 CLI 没有 --no-* 对应项，命令行无法关闭。
    p = argparse.ArgumentParser(description='Aruco precision landing -> MQTT virtual joystick output with landing cleanup / height offset handling')

    # ---- 视频输入与处理频率 -------------------------------------------------
    p.add_argument('--input', default='received_video.h264', help='输入源: 文件路径 / rtsp地址 / 摄像头编号字符串，如 0')
    p.add_argument('--input-mode', default='tail_h264', choices=['auto', 'opencv', 'tail_h264'], help='默认 tail_h264；若输入不是 h264 可改为 auto/opencv')
    p.add_argument('--loop-video', action='store_true', help='文件读到末尾后循环，仅 OpenCV 模式有效')
    p.add_argument('--preview', action='store_true', help='显示预览窗口')
    p.add_argument('--target-fps', type=float, default=30.0, help='OpenCV 模式下的视频处理目标帧率；tail_h264 模式下默认不节流')
    p.add_argument('--control-rate', type=float, default=20.0, help='控制发送频率')

    # ---- 相机内参、安装方向和控制轴映射 -------------------------------------
    # fx/fy/cx/cy 应来自相机标定；随意填写会让像素转距离和估高都产生比例误差。
    p.add_argument('--image-width', type=int, default=1280)
    p.add_argument('--image-height', type=int, default=720)
    p.add_argument('--camera-fx', type=float, default=550.0)
    p.add_argument('--camera-fy', type=float, default=550.0)
    p.add_argument('--camera-cx', type=float, default=640.0)
    p.add_argument('--camera-cy', type=float, default=360.0)
    p.add_argument('--camera-offset-x', type=float, default=0.0)
    p.add_argument('--camera-offset-y', type=float, default=0.0)
    p.add_argument('--offset-comp-disable-below', type=float, default=1.2, help='低于该相机高度时禁用 camera_offset 补偿，避免低空补偿过大')
    p.add_argument('--swap-xy', action='store_true', help='交换前后/左右控制轴')
    p.add_argument('--invert-x', action='store_true', help='反转前后控制方向')
    p.add_argument('--invert-y', action='store_true', help='反转左右控制方向')
    p.add_argument('--image-yaw-comp-deg', type=float, default=0.0, help='图像坐标到机体坐标的平面旋转补偿角，单位度')
    p.add_argument('--xy-min-effective-speed', type=float, default=0.22, help='水平最小有效速度，小于该值时虚拟摇杆可能不吃感量')
    p.add_argument('--xy-pulse-on', type=float, default=0.12, help='兼容旧参数：固定脉冲开启时长，自动脉冲未启用时作为回退')
    p.add_argument('--xy-pulse-off', type=float, default=0.10, help='兼容旧参数：固定脉冲关闭时长，自动脉冲未启用时作为回退')
    p.add_argument('--xy-pulse-period', type=float, default=0.22, help='自动脉冲总周期，单位秒')
    p.add_argument('--xy-pulse-on-min', type=float, default=0.04, help='自动脉冲最小开启时长，单位秒')
    p.add_argument('--xy-pulse-on-max', type=float, default=0.18, help='自动脉冲最大开启时长，单位秒')

    # ---- ArUco 目标定义 -----------------------------------------------------
    p.add_argument('--marker-size', type=float, default=0.20)
    p.add_argument('--marker-id', type=int, default=0)
    p.add_argument('--aruco-dict-name', default='DICT_4X4_50')
    p.add_argument('--min-marker-perimeter-rate', type=float, default=0.03)

    # Mechanical geometry.
    # ---- 传感器机械高度 -----------------------------------------------------
    p.add_argument('--radar-ground-offset', type=float, default=0.18, help='对地雷达离地机械高度，单位 m')
    p.add_argument('--camera-ground-offset', type=float, default=0.425, help='相机离地机械高度，单位 m')

    # ---- 水平测量-执行控制器 ------------------------------------------------
    p.add_argument('--vel-gain', type=float, default=1.2)
    p.add_argument('--axis-mode', default='single', choices=['single', 'multi'], help='水平修正方式：single=单轴优先，每帧只修正一个主轴；multi=多轴同时修正，前后/左右同帧一起输出')
    p.add_argument('--hover-measure-time', type=float, default=2.0, help='悬停采样时长，单位秒；在该时间内只检测不修正，使用平均偏差做一次时序修正')
    p.add_argument('--hover-measure-min-samples', type=int, default=18, help='单次悬停采样的最少有效样本数')
    p.add_argument('--timed-actuation-min-time', type=float, default=0.18, help='单次时序修正的最短保持时间，单位秒')
    p.add_argument('--timed-actuation-max-time-high', type=float, default=1.40, help='高空阶段单次时序修正的最大保持时间，单位秒')
    p.add_argument('--timed-actuation-max-time-mid', type=float, default=1.10, help='中空阶段单次时序修正的最大保持时间，单位秒')
    p.add_argument('--timed-actuation-max-time-final', type=float, default=0.80, help='最终阶段单次时序修正的最大保持时间，单位秒')
    p.add_argument('--timed-stage-min-joystick-high', type=int, default=170, help='高空阶段单次水平修正的最小有效摇杆，需高于飞控起效门槛 150')
    p.add_argument('--timed-stage-min-joystick-mid', type=int, default=165, help='中空阶段单次水平修正的最小有效摇杆')
    p.add_argument('--timed-stage-min-joystick-final', type=int, default=155, help='最终阶段单次水平修正的最小有效摇杆')
    p.add_argument('--timed-joystick-distance-gain', type=float, default=90.0, help='按估计横向距离附加的摇杆增益，单位 joystick/m')
    p.add_argument('--timed-wind-bias-joystick-high', type=int, default=18, help='高空阶段附加风补偿摇杆')
    p.add_argument('--timed-wind-bias-joystick-mid', type=int, default=12, help='中空阶段附加风补偿摇杆')
    p.add_argument('--timed-wind-bias-joystick-final', type=int, default=8, help='最终阶段附加风补偿摇杆')
    p.add_argument('--timed-axis-response-gain-init', type=float, default=0.90, help='飞控实际响应速度与理论速度的初始比例，越小表示同样摇杆需要保持更久')
    p.add_argument('--timed-axis-response-gain-min', type=float, default=0.35, help='响应比例下限')
    p.add_argument('--timed-axis-response-gain-max', type=float, default=1.80, help='响应比例上限')
    p.add_argument('--timed-axis-response-update-alpha', type=float, default=0.35, help='每次修正后根据实测效果更新响应比例的权重')
    p.add_argument('--timed-distance-deadband-scale', type=float, default=1.0, help='以当前阶段中心容差折算出的米级死区缩放；1 表示严格对齐到当前阶段容差')
    p.add_argument('--timed-descent-target-margin', type=float, default=0.03, help='垂直下降到阶段目标高度时的切换余量，单位 m')
    # ---- 分段下降、容差和高度策略 -------------------------------------------
    p.add_argument('--xy-vel-limit', type=float, default=0.45)
    p.add_argument('--alt-vel-limit', type=float, default=0.15)
    p.add_argument('--center-tolerance', type=float, default=50.0)
    p.add_argument('--land-center-tolerance', type=float, default=75.0, help='满足该中心阈值后允许进入 LAND；放宽可减少低空来回飘')
    p.add_argument('--align-stable-time', type=float, default=0.06, help='连续对准多久后允许转入下降；减小可更快开始下降')
    p.add_argument('--descent-speed', type=float, default=0.25)
    p.add_argument('--descent-check-interval', type=float, default=0.5)
    p.add_argument('--drift-tolerance', type=float, default=60.0)
    p.add_argument('--land-pixel-threshold', type=float, default=430.0)
    p.add_argument('--loss-timeout', type=float, default=1.0)
    p.add_argument('--hold-height-gain', type=float, default=0.20)
    p.add_argument('--hold-height-tolerance', type=float, default=0.04)
    p.add_argument('--max-align-climb-speed', type=float, default=0.02, help='ALIGN 中允许的最大上升速度，默认几乎禁止上升')
    p.add_argument('--search-use-hold', action='store_true')
    p.add_argument('--height-judge-source', default='vision', choices=['radar', 'vision'], help='整体高度判断来源: radar=对地雷达, vision=视觉估高(ArUco)')

    p.add_argument('--low-alt-fast-descent-speed', type=float, default=0.40, help='当高度低于阈值时的下降速度 (m/s)，设0禁用')
    p.add_argument('--low-alt-threshold', type=float, default=0.90, help='视觉高度模式下，低于该相机高度启动快速下降')
    p.add_argument('--low-alt-radar-threshold', type=float, default=0.655, help='雷达高度模式下，低于该雷达高度启动快速下降')
    p.add_argument('--direct-vertical-radar-height', type=float, default=0.60, help='雷达高度模式下，低于该雷达高度后不再做水平调整，直接垂直下降')
    p.add_argument('--direct-vertical-camera-height', type=float, default=0.845, help='视觉高度模式下，低于该相机高度后不再做水平调整，直接垂直下降')
    p.add_argument('--stage-high-alt-height', type=float, default=2.0, help='分阶段降落：高空阶段与中空阶段的分界，无人机离地高度，单位 m')
    p.add_argument('--stage-final-align-height', type=float, default=0.70, help='兼容保留参数；当前时序分段算法使用 final_direct_land_height 作为最终阶段分界，默认 0.70 m')
    p.add_argument('--high-alt-center-tolerance', type=float, default=110.0, help='高空阶段中心阈值，无人机离地高度 > stage-high-alt-height；时序平均法下可适当放宽，抗风更强')
    p.add_argument('--mid-alt-center-tolerance', type=float, default=70.0, help='中空阶段中心阈值，0.70~2.0 m；时序平均法下可适当放宽')
    p.add_argument('--final-alt-center-tolerance', type=float, default=22.0, help='最终阶段中心阈值，无人机离地高度 <= 0.70 m；满足后直接 LAND')
    p.add_argument('--stage-descend-realign-tolerance', type=float, default=999.0, help='兼容保留参数；当前时序分段算法下降阶段默认不做水平重对准')
    p.add_argument('--final-direct-land-height', type=float, default=0.70, help='无人机离地高度低于该值时，若已满足最终阶段对准则立即 LAND；若未对准则继续回 ALIGN，而不是无条件直落')
    p.add_argument('--vel-gain-high-scale', type=float, default=0.75, help='高空阶段水平修正增益缩放，减小可降低大范围来回晃动')
    p.add_argument('--vel-gain-mid-scale', type=float, default=0.90, help='中空阶段水平修正增益缩放')
    p.add_argument('--vel-gain-final-scale', type=float, default=1.00, help='低空最终阶段水平修正增益缩放')
    p.add_argument('--error-lpf-alpha-high', type=float, default=0.25, help='高空阶段像素误差低通滤波新值权重，越小越稳')
    p.add_argument('--error-lpf-alpha-mid', type=float, default=0.35, help='中空阶段像素误差低通滤波新值权重')
    p.add_argument('--error-lpf-alpha-final', type=float, default=0.60, help='低空阶段像素误差低通滤波新值权重，越大越跟手')
    p.add_argument('--xy-cmd-lpf-alpha-high', type=float, default=0.30, help='高空阶段水平速度命令低通滤波新值权重，减小可抗风防抖')
    p.add_argument('--xy-cmd-lpf-alpha-mid', type=float, default=0.45, help='中空阶段水平速度命令低通滤波新值权重')
    p.add_argument('--xy-cmd-lpf-alpha-final', type=float, default=0.75, help='低空阶段水平速度命令低通滤波新值权重')

    # ---- MQTT 连接、控制权初始化和飞控限制 ---------------------------------
    # 注意 mqtt-enable 使用 store_true 且默认 True，当前命令行定义没有对应关闭开关。
    p.add_argument('--mqtt-enable', action='store_true', default=True)
    p.add_argument('--mqtt-host', default='47.96.5.200')
    p.add_argument('--mqtt-port', type=int, default=1883)
    p.add_argument('--mqtt-username', default='')
    p.add_argument('--mqtt-password', default='')
    p.add_argument('--mqtt-client-id', default='')
    p.add_argument('--mqtt-keepalive', type=int, default=60)
    p.add_argument('--mqtt-qos', type=int, default=0, choices=[0, 1])
    p.add_argument('--mqtt-subscribe-osd', action='store_true', default=True)
    p.add_argument('--mqtt-subscribe-reply', action='store_true', default=True)
    p.add_argument('--mqtt-wait-reply', action='store_true', default=True, help='对 setup/land 等命令等待 services_reply')
    p.add_argument('--mqtt-reply-timeout', type=float, default=1.0)
    p.add_argument('--product-id', default='A02')
    p.add_argument('--setup-before-run', action='store_true', default=True)
    p.add_argument('--setup-cmd-interval', type=float, default=0.10)
    p.add_argument('--fly-mode', default='Posctl')
    p.add_argument('--manual-hor-spd-max', type=float, default=2.0)
    p.add_argument('--manual-cli-spd-max', type=float, default=1.0)
    p.add_argument('--manual-land-spd-max', type=float, default=1.0)
    p.add_argument('--yaw-spd-max', type=float, default=20.0)
    p.add_argument('--tilt-angle', type=float, default=30.0)
    p.add_argument('--land-speed', type=float, default=2.5)
    p.add_argument('--land-ground-speed', type=float, default=0.4)
    p.add_argument('--precision-land-error', type=float, default=0.35)
    # ---- 控制协议和虚拟摇杆死区补偿 -----------------------------------------
    p.add_argument('--control-method', default='joystick', choices=['joystick', 'velocity', 'target'], help='下发方式: joystick=setJoystickValue，兼容保留 velocity/target')
    p.add_argument('--joystick-max-value', type=int, default=300, help='虚拟摇杆单轴最大杆量请求值；本脚本默认收紧到 300')
    p.add_argument('--joystick-hard-limit', type=int, default=300, help='虚拟摇杆硬上限，最终任何轴都不会超过该值')
    p.add_argument('--joystick-xy-min-effective-value', type=int, default=150, help='若 |x|/|y| 小于该杆量则触发水平轴最小有效杆量补偿；0 表示关闭，当前现场建议约 150')
    p.add_argument('--joystick-xy-force-value', type=int, default=170, help='触发水平轴补偿后发送到该固定杆量；建议略高于生效门槛，例如 170')
    p.add_argument('--joystick-xy-bypass-value', type=int, default=0, help='若 |x|/|y| 大于等于该值则直接发送原始杆量，不再走最小有效杆量脉冲；0 时等同于 joystick-xy-min-effective-value')
    p.add_argument('--joystick-xy-pulse-period', type=float, default=0.40, help='水平摇杆最小有效杆量脉冲总周期，单位秒')
    p.add_argument('--joystick-xy-pulse-on-min', type=float, default=0.10, help='水平摇杆最小有效杆量脉冲最短开启时间，单位秒')
    p.add_argument('--joystick-xy-pulse-on-max', type=float, default=0.22, help='水平摇杆最小有效杆量脉冲最长开启时间，单位秒')
    p.add_argument('--joystick-min-effective-mode', default='hold', choices=['hold', 'pulse'], help='最小有效杆量补偿方式：hold=持续保持固定有效杆量，不主动插0；pulse=按周期插0脉冲')
    p.add_argument('--joystick-min-hold-time', type=float, default=0.35, help='hold 模式下，小杆量触发后最少保持该时长，避免刚发有效杆量就被0覆盖')
    p.add_argument('--joystick-z-min-effective-value', type=int, default=150, help='若 |z| 小于该杆量则触发垂直轴最小有效杆量补偿；0 表示关闭')
    p.add_argument('--joystick-z-force-value', type=int, default=170, help='垂直轴触发补偿后强制发送到该固定杆量；建议略高于生效门槛')
    p.add_argument('--joystick-z-bypass-value', type=int, default=0, help='若 |z| 大于等于该值则直接发送原始杆量，不再走垂直轴最小有效杆量补偿；0 时等同于 joystick-z-min-effective-value')
    p.add_argument('--joystick-z-pulse-period', type=float, default=0.40, help='垂直轴脉冲总周期；仅 pulse 模式使用，0 时回退到水平轴脉冲周期')
    p.add_argument('--joystick-z-pulse-on-min', type=float, default=0.10, help='垂直轴脉冲最短开启时间；仅 pulse 模式使用')
    p.add_argument('--joystick-z-pulse-on-max', type=float, default=0.22, help='垂直轴脉冲最长开启时间；仅 pulse 模式使用')
    p.add_argument('--joystick-pitch-sign', type=float, default=-1.0, help='协议换算用：机体系前进速度 -> 摇杆 x 的符号，默认 -1 因文档定义 x=-1000 为前进')
    p.add_argument('--joystick-roll-sign', type=float, default=1.0, help='协议换算用：机体系右移速度 -> 摇杆 y 的符号，默认 +1')
    p.add_argument('--joystick-throttle-sign', type=float, default=1.0, help='协议换算用：机体系上升速度 -> 摇杆 z 的符号，默认 +1，下降自然为负')
    p.add_argument('--joystick-yaw-sign', type=float, default=1.0, help='协议换算用：右转角速度 -> 摇杆 yaw 的符号，默认 +1')
    # ---- 运行时安全门和命令调度 ---------------------------------------------
    p.add_argument('--require-osd-ready', action='store_true', default=True, help='只有 OSD 显示模式/控制状态真正就绪后才下发运动控制；joystick 模式检查飞行模式+摇杆状态')
    p.add_argument('--not-ready-action', default='hold', choices=['hold', 'brake_hold', 'none'], help='joystick 模式下 hold/brake_hold 都只发零杆量，不改飞行模式；非 joystick 模式下 brake_hold 仍可走刹车/hold')
    p.add_argument('--brake-on-vision-loss', action='store_true', help='在 ALIGN/DESCEND 丢码时先发零杆量；joystick 模式下不再切到 hold，保持当前飞行模式不变')
    p.add_argument('--brake-hold-time', type=float, default=0.10)
    p.add_argument('--command-keepalive', type=float, default=0.25, help='相同速度命令的保活重发周期')
    p.add_argument('--send-every-n-frames', type=int, default=1, help='最少隔多少帧才发送一次；1 表示每帧都允许发，显著变化也可提前发')
    p.add_argument('--min-velocity-send-interval', type=float, default=0.12, help='两次控制之间的最小时间间隔，秒；该值一定生效，是最终频率上限，默认已收紧到 0.12')
    p.add_argument('--velocity-resend-epsilon', type=float, default=0.02, help='水平速度变化超过该阈值时允许在帧数限制上提前重发，但仍受最小发送间隔限制')
    p.add_argument('--vertical-resend-epsilon', type=float, default=0.015, help='垂直速度变化超过该阈值时允许在帧数限制上提前重发，但仍受最小发送间隔限制')
    p.add_argument('--near-center-pause-threshold', type=float, default=0.0, help='接近中心时发送一次水平修正后短暂停顿；默认 0=关闭，避免低空停一下又飘')
    p.add_argument('--near-center-pause-time', type=float, default=0.0, help='接近中心时发送一次水平修正后的停顿时间；默认 0=关闭')
    p.add_argument('--near-center-pause-mode', default='and', choices=['and', 'or'], help='近中心停顿判定方式：and=|du|和|dv|都小，or=任一轴小')
    p.add_argument('--debug-send-gate', action='store_true', help='打印发送频率门控原因，排查到底是时间限制还是帧限制在挡')
    p.add_argument('--cmd-round-digits', type=int, default=3)

    p.add_argument('--force-ready-on-start', action='store_true', default=True, help='仅在启动阶段强制等待 flyMode/joystick 就绪；运行中不再自动重新设置飞行模式或虚拟摇杆')
    p.add_argument('--force-ready-timeout', type=float, default=10.0, help='等待就绪的超时时间')
    p.add_argument('--ready-retry-interval', type=float, default=0.45)
    p.add_argument('--recover-cooldown', type=float, default=0.8)
    p.add_argument('--motion-reject-holdoff', type=float, default=0.8)
    p.add_argument('--init-release-pause', type=float, default=0.25)

    # ---- 接地确认、落锁和中断恢复 -------------------------------------------
    p.add_argument('--disarm-delay', type=float, default=1.5, help='进入 LAND 状态后至少等待多久才允许完成落锁收尾')
    p.add_argument('--disarm-repeat', type=int, default=3)
    p.add_argument('--disarm-repeat-interval', type=float, default=0.30)
    p.add_argument('--post-land-release-delay', type=float, default=0.20)
    p.add_argument('--no-disarm', action='store_true', help='禁用自动落锁')
    p.add_argument('--restore-mode-on-interrupt', action='store_true', default=True, help='Ctrl+C 中断时，发送零杆量并释放控制后恢复到启动前模式；若未知则恢复到指定飞行模式')
    p.add_argument('--interrupt-restore-fly-mode', default='Posctl', help='Ctrl+C 中断时恢复的飞行模式，常用 Hold 或 Posctl')
    p.add_argument('--interrupt-zero-repeat', type=int, default=5, help='Ctrl+C 中断时发送零速度指令的次数')
    p.add_argument('--interrupt-zero-interval', type=float, default=0.06, help='Ctrl+C 中断时连续发送零速度指令的时间间隔')
    p.add_argument('--land-radar-trigger-height', type=float, default=0.28, help='雷达到地高度低于该值并且已对准时，进入 LAND')
    p.add_argument('--land-camera-trigger-height', type=float, default=0.525, help='相机到地高度低于该值并且已对准时，进入 LAND')
    p.add_argument('--force-land-radar-height', type=float, default=0.24, help='雷达高度模式下，雷达到地高度低于该值时，直接强制 LAND')
    p.add_argument('--force-land-camera-height', type=float, default=0.485, help='视觉高度模式下，相机到地高度低于该值时，直接强制 LAND')
    p.add_argument('--touchdown-radar-height', type=float, default=0.22, help='用于判断接地完成的雷达高度阈值')
    p.add_argument('--touchdown-camera-height', type=float, default=0.465, help='用于判断接地完成的相机高度阈值')
    p.add_argument('--touchdown-vertical-speed', type=float, default=0.12, help='接地确认时允许的最大垂直速度绝对值')
    p.add_argument('--touchdown-confirm-time', type=float, default=0.40, help='连续满足接地条件多久才算真正接地')
    p.add_argument('--land-finalize-timeout', type=float, default=8.0, help='LAND 后的最大等待时间，超时也会执行落锁收尾')
    p.add_argument('--startup-guard-time', type=float, default=1.2, help='脚本启动后的保护时间，避免刚启动立刻进入降落流程')
    p.add_argument('--min-startup-radar-height', type=float, default=0.45, help='雷达高度模式下，二次起飞后雷达到地高度低于该值时不允许进入定位降落')
    p.add_argument('--min-startup-camera-height', type=float, default=0.695, help='视觉高度模式下，二次起飞后相机到地高度低于该值时不允许进入定位降落')

    # ---- H264 增长文件与 FFmpeg 低延迟选项 ----------------------------------
    p.add_argument('--ffmpeg-bin', default='ffmpeg', help='tail_h264 模式使用的 ffmpeg 可执行文件')
    p.add_argument('--ffmpeg-probesize', type=int, default=32, help='尽量小，减少启动缓冲')
    p.add_argument('--ffmpeg-stdin-flush', action='store_true', help='每次写入 ffmpeg 后 flush，延迟更低但 CPU 更高')
    p.add_argument('--tail-open-timeout', type=float, default=10.0)
    p.add_argument('--tail-poll-interval', type=float, default=0.005, help='尾读轮询间隔，越小延迟越低')
    p.add_argument('--tail-read-chunk', type=int, default=65536)
    p.add_argument('--tail-start-mode', default='warm', choices=['start', 'end', 'warm'], help='start: 从头; end: 从当前末尾; warm: 从末尾往前回看一段')
    p.add_argument('--tail-warm-bytes', type=int, default=2097152, help='warm 模式回看字节数，帮助快速拿到 SPS/PPS/IDR')
    p.add_argument('--tail-read-timeout', type=float, default=1.0, help='等待新帧的超时时间')
    p.add_argument('--tail-require-live-data', action='store_true', default=True, help='只在检测到启动后新追加的 H264 数据后才使用帧，避免读到上次落地旧帧')
    return p


def build_source(args):
    # =========================================================================
    # 第五章：关键函数调用索引与现有局限
    # =========================================================================
    #
    # 如果你准备逐函数阅读，可按下面调用链，而不是从第 1 行机械读到最后：
    #
    # run_with_interrupt_cleanup
    #   -> build_parser：把命令行转换成 args 配置对象。
    #   -> MqttAdapter.connect：建立网络线程和订阅。
    #   -> capture_startup_state：记录原飞行模式/控制器状态。
    #   -> initialize_for_run：清理残留状态并申请本次控制权。
    #   -> build_source/open：选择视频输入并启动解码。
    #   -> ArucoLandingController：保存视觉、状态机和自适应控制状态。
    #   -> 循环 source.read -> controller.update -> maybe_send_command。
    #   -> LAND 后 should_finalize_land -> shutdown_after_land。
    #
    # MqttAdapter 方法按职责：
    # _on_connect/_on_message/_on_disconnect 是网络线程回调；make_msg、publish_method、
    # wait_reply 是请求响应基础设施；capture/restore/release/initialize 管理控制权；
    # _velocity_payload/_joystick_payload 负责单位和协议转换；_apply_* 处理死区；
    # send_velocity/send_land/send_disarm 是真正产生飞行副作用的出口。
    #
    # ArucoLandingController 方法按职责：
    # raw_radar_height/vision_height/selected_* 统一高度参考；get_stage_* 选择阶段参数；
    # filter_detection_error/smooth_xy_command 是旧连续路径的滤波器；transform_xy_pair
    # 处理轴映射；collect/summarize_measure 形成稳定测量；estimate_body_error_m 做几何
    # 换算；build_timed_actuation_plan 产生动作；update_axis_response_from_measure 更新
    # 简单模型；detect 读视觉；update 执行状态机；maybe_send_command 执行安全门控；
    # touchdown_confirmed/should_finalize_land 决定何时允许落锁收尾。
    #
    # -------------------------------------------------------------------------
    # 现有局限 1：不是完整位姿估计
    # -------------------------------------------------------------------------
    # detect 只使用中心和平均边长，没有相机畸变校正，也没有 solvePnP 得到旋转和平移。
    # 无人机 roll/pitch、地面坡度、标志倾斜都会让高度和水平误差近似出现系统偏差。
    # 更完整方案应使用标定内参/畸变、PnP，并把相机外参和 IMU 姿态变换到机体系。
    #
    # 现有局限 2：没有状态估计器
    # -------------------------------------------------------------------------
    # 代码用均值和一阶低通抑制噪声，没有 EKF/UKF 去联合估计位置、速度、IMU 偏置
    # 与测量延迟。视觉短时丢失时也没有预测目标运动，而是退回 SEARCH。这种保守行为
    # 比盲飞安全，但抗遮挡和连续性有限。
    #
    # 现有局限 3：DESCEND 期间不开水平视觉闭环
    # -------------------------------------------------------------------------
    # 分段下降只发 vz，直到到达目标高度才重新 ALIGN。它简化了控制耦合，却允许风
    # 在整个下降段积累偏差。若改成边降边修，需要重新评估姿态耦合、地面接近风险、
    # 视频延迟和水平速度限制，不能只在现有分支里加 vx/vy。
    #
    # 现有局限 4：force-land 绕过对准
    # -------------------------------------------------------------------------
    # should_enter_land 在极低高度可仅凭高度返回 True，不检查 du/dv。这避免近地反复
    # 横移，却可能偏离降落板。阈值安全性依赖起落架尺寸、标志位置和高度源准确度。
    #
    # 现有局限 5：超时后仍 disarm
    # -------------------------------------------------------------------------
    # LAND 后若接地条件长期不成立，land_finalize_timeout 仍触发 shutdown_after_land。
    # 这是防止软件永远挂起的现场策略，但“软件超时”并不能证明“飞机已在地面”。
    # 生产系统应结合着陆检测、推力/加速度、电机状态和飞控明确 landed 状态。
    #
    # 现有局限 6：测量样本时间清理无效
    # -------------------------------------------------------------------------
    # collect_measure_sample 追加的字典没有 ts 字段，但后面只有在首样本含 ts 时才按
    # cutoff 清理，因此该分支实际不会运行。当前每轮 phase 会重置样本，通常不会无限
    # 累积，但代码意图和实现不一致。学习版只指出，不修复，以保持 AST 等价。
    #
    # 现有局限 7：部分 CLI 布尔参数无法关闭
    # -------------------------------------------------------------------------
    # argparse 的 action='store_true', default=True 意味着“不传”和“传了”都是 True。
    # 没有 store_false 或 BooleanOptionalAction 时，mqtt_enable、setup_before_run 等参数
    # 不能从 CLI 关闭。这是配置接口问题，不代表代码内永远不能赋 False。
    #
    # 现有局限 8：两个主循环重复
    # -------------------------------------------------------------------------
    # main 和 run_with_interrupt_cleanup 大量重复，__main__ 只调用后者。未来修改控制
    # 循环若只改一个，会产生行为分叉。理想结构是单一 run(args) 加外层异常包装；
    # 本学习版不重构，以保证现场代码逐语句一致。
    #
    # 现有局限 9：遥测没有显式新鲜度
    # -------------------------------------------------------------------------
    # last_osd 被保存，但 relative_alt、vertical_speed 等没有各自时间戳。MQTT 断流后
    # 可能继续使用最后值；connected 状态也不等于每项遥测新鲜。高可靠控制应检查
    # age，并在超时后停止运动或交给飞控 failsafe。
    #
    # 现有局限 10：接地速度缺失时放宽
    # -------------------------------------------------------------------------
    # touchdown_confirmed 中 vertical_speed=None 会令 vs_ok=True。这样兼容缺少字段的
    # 固件，却失去一项接地证据。若高度传感器也有近地盲区，误判风险进一步增大。
    #
    # 现有局限 11：response gain 不是动力学模型
    # -------------------------------------------------------------------------
    # 每轴只有一个标量，无法表示速度建立/制动惯性、不同方向响应、风向、载荷变化、
    # 电量变化或 x/y 耦合。它能修正平均比例，不等价于系统辨识或 MPC 模型。
    #
    # 现有局限 12：参数是现场默认值，不是普适常数
    # -------------------------------------------------------------------------
    # 相机焦距、机械 offset、死区、速度限制、接地高度都与硬件和固件相关。复制脚本
    # 到另一机型而不重新标定，语法仍正确，但物理意义已经错误。
    #
    # -------------------------------------------------------------------------
    # 推荐验证阶梯
    # -------------------------------------------------------------------------
    # 第 1 层：纯静态。AST 等价、语法编译、逐轴符号纸面推导。
    # 第 2 层：离线录像。只运行 detect/update 的无 MQTT 版本，检查状态和命令日志。
    # 第 3 层：软件在环。模拟 OSD、延迟、丢码、风扰和 MQTT 拒绝。
    # 第 4 层：拆桨台架。验证 topic、模式、杆量正负、零命令和中断恢复。
    # 第 5 层：系留低风险悬停。只开水平对准，不允许 LAND/disarm。
    # 第 6 层：分段下降，人工随时接管，逐步开放最终 LAND。
    #
    # 每层都应有明确通过标准，例如最大延迟、最大稳态误差、丢码后停止时间和接管
    # 成功率。一次“飞成功”不能证明算法稳定，必须覆盖错误方向、旧帧、网络断开、
    # 高度跳变和误检等失败场景。
    #
    # -------------------------------------------------------------------------
    # 阅读完成自测
    # -------------------------------------------------------------------------
    # 你应能回答：
    # 1. du=80 px、高度 2 m 时怎样换成米级误差？
    # 2. 为什么请求 0.4 m/s 最终可能发送 170 杆量？
    # 3. timed actuation 为什么用 residual 而不是完整 body distance？
    # 4. ALIGN 的 measure/actuate 为什么不等价于 PID？
    # 5. control_rate=20 为什么真实发送可能只有 8.3 Hz？
    # 6. DESCEND 丢码为什么不会立即在该分支处理水平误差？
    # 7. 哪些路径可以在未对准时进入 LAND？
    # 8. 为什么 MQTT publish 成功不代表动作成功？
    # 9. warm history 为什么既帮助启动又带来旧帧风险？
    # 10. 为什么 LAND timeout 后 disarm 是需要重点审查的安全策略？
    #
    # 若这些问题能结合具体函数和参数回答，才算理解了程序的控制逻辑，而不只是看懂
    # Python 语法。
    # auto 根据扩展名选择；明确 tail_h264 时使用增长文件管道，否则交给 OpenCV。
    mode = args.input_mode
    if mode == 'auto':
        if str(args.input).lower().endswith('.h264'):
            mode = 'tail_h264'
        else:
            mode = 'opencv'
    args.input_mode = mode
    if mode == 'tail_h264':
        return TailH264Source(args)
    return OpenCVVideoSource(args)


def main():
    # =========================================================================
    # 第六章：主循环中的时间与副作用
    # =========================================================================
    # 主循环每次迭代并不代表固定控制周期。耗时包括视频等待、解码、ArUco 检测、
    # MQTT 发布和可选预览。OpenCV 模式用 target_fps 补 sleep；tail 模式由新帧到达
    # 驱动，不额外节流。真正命令周期还会被 maybe_send_command 的门控重新限制。
    #
    # frame_ts 与 tick 的区别：tick 是本轮开始时间，用于 OpenCV 节流；frame_ts 是
    # 视频源交付帧的时间，用于估算 source lag。它们都不是无人机状态采样的原始时间。
    #
    # frame resize 会改变像素几何。如果输入宽高比例与目标 1280x720 不同，直接 resize
    # 造成非等比拉伸，ArUco 边长和 fx/fy 的物理对应关系被破坏。正确做法是确保采集
    # 分辨率、标定分辨率和处理分辨率一致，或同步缩放内参并保持宽高比。
    #
    # controller.update 不产生网络副作用，所以理论上可以在离线录像上单独测试。
    # maybe_send_command 才可能发布运动/land；shutdown_after_land 还会 disarm。
    # 做离线回放时，仅设置 mqtt_enable=False 仍需检查 argparse 默认和控制路径，最好
    # 使用隔离 broker 或显式 mock MqttAdapter，不能依赖“网络应该连不上”。
    #
    # preview 的 imshow/waitKey 会引入 GUI 调度延迟。人工观察方便，但正式性能测试应
    # 同时测量开启/关闭 preview 的处理帧率。按 q/Esc 会先 release_control 再退出，
    # 这比直接关闭终端窗口更可控。
    #
    # LAND 后分两种行为：no_disarm=False 时等待接地/超时并收尾；no_disarm=True 时
    # 进入 LAND 后很快退出脚本，不自动落锁。后者便于把最终电机管理交给飞控或人工，
    # 但退出后飞控将怎样继续 LAND 取决于其自身状态机。
    #
    # finally 负责释放视频和 MQTT，即使循环中抛异常也执行；但异常处理中的
    # restore_after_interrupt 更重要，因为 close 网络连接本身不会主动发送零杆量。
    # 清理函数也可能失败，所以代码用多层 try/except 尽量继续剩余收尾步骤。
    #
    # main 与 run_with_interrupt_cleanup 重复，实际入口是后者。阅读调试时应在后者
    # 设置断点；如果只修改 main，直接运行脚本不会执行你的修改。
    #
    # 调试建议记录每轮：frame_ts、state、phase、du/dv、height source、body error、
    # plan joy/duration、最终 payload、OSD mode/state 和 reply result。只看“飞机偏了”
    # 无法区分视觉误差、坐标符号、发送门控、飞控拒绝还是执行器死区。
    #
    # 控制程序的正确性包含三层：算法算出的命令合理；命令按预期送达飞控；飞控和
    # 机体对命令产生预期响应。任何一层都可能失败，日志也应按这三层组织。
    # 早期保留的主循环，逻辑与下方版本相近，但 __main__ 实际不调用它。
    args = build_parser().parse_args()
    args.camera_radar_height_offset = float(args.camera_ground_offset) - float(args.radar_ground_offset)
    print('[CFG] radar_ground_offset={:.3f}m camera_ground_offset={:.3f}m camera_radar_height_offset={:.3f}m height_judge_source={}'.format(
        args.radar_ground_offset, args.camera_ground_offset, args.camera_radar_height_offset, args.height_judge_source))

    mqtt_adapter = MqttAdapter(args)
    mqtt_adapter.connect()
    mqtt_adapter.capture_startup_state(timeout=1.0)

    try:
        if args.force_ready_on_start or args.setup_before_run:
            ok = mqtt_adapter.initialize_for_run(args)
            if not ok:
                print('[ERROR] Cannot initialize clean control state. Exiting.')
                mqtt_adapter.close()
                sys.exit(1)

        source = build_source(args)
        source.open()
        controller = ArucoLandingController(args, mqtt_adapter)
        target_frame_period = 1.0 / max(float(args.target_fps), 1.0)

        # 单线程业务循环：取最新帧 -> 更新控制状态 -> 经过门控发送 -> 判断落地。
        while True:
            tick = time.time()
            ok, frame, frame_ts = source.read(timeout=float(args.tail_read_timeout) if args.input_mode == 'tail_h264' else None)
            if not ok or frame is None:
                if args.input_mode == 'tail_h264':
                    continue
                print('输入结束')
                break

            if frame.shape[1] != int(args.image_width) or frame.shape[0] != int(args.image_height):
                frame = cv2.resize(frame, (int(args.image_width), int(args.image_height)))

            info = controller.update(frame)
            controller.maybe_send_command(info['cmd'], info['action'])

            if controller.state_machine == controller.LAND and not args.no_disarm:
                enough_time = (controller._land_start_time is not None and (time.time() - controller._land_start_time) >= float(args.disarm_delay))
                if enough_time and controller.should_finalize_land(time.time()):
                    mqtt_adapter.shutdown_after_land(args)
                    break

            if args.preview:
                lag = None
                if frame_ts is not None:
                    lag = max(0.0, time.time() - frame_ts)
                overlay = controller.draw_overlay(frame, info, source_lag=lag)
                cv2.imshow('aruco_landing_mqtt', overlay)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    mqtt_adapter.release_control(args, reason='preview quit')
                    break

            if args.input_mode != 'tail_h264':
                elapsed = time.time() - tick
                sleep_t = target_frame_period - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)

            if controller.state_machine == controller.LAND and args.no_disarm:
                print('已进入 LAND 状态，脚本结束。')
                time.sleep(0.2)
                break
    finally:
        try:
            source.release()
        except Exception:
            pass
        try:
            mqtt_adapter.close()
        except Exception:
            pass
        if args.preview:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass


def run_with_interrupt_cleanup():
    # 实际程序入口。与 main() 的关键区别是显式捕获 Ctrl+C 和异常，
    # 尝试发零命令、释放控制权并恢复启动前模式。
    args = None
    mqtt_adapter = None
    source = None
    try:
        args = build_parser().parse_args()
        args.camera_radar_height_offset = float(args.camera_ground_offset) - float(args.radar_ground_offset)
        print('[CFG] radar_ground_offset={:.3f}m camera_ground_offset={:.3f}m camera_radar_height_offset={:.3f}m height_judge_source={}'.format(
            args.radar_ground_offset, args.camera_ground_offset, args.camera_radar_height_offset, args.height_judge_source))

        # 初始化顺序：MQTT -> 保存现场状态 -> 申请控制权 -> 视频源 -> 控制器。
        mqtt_adapter = MqttAdapter(args)
        mqtt_adapter.connect()
        mqtt_adapter.capture_startup_state(timeout=1.0)

        if args.force_ready_on_start or args.setup_before_run:
            ok = mqtt_adapter.initialize_for_run(args)
            if not ok:
                print('[ERROR] Cannot initialize clean control state. Exiting.')
                raise SystemExit(1)

        source = build_source(args)
        source.open()
        controller = ArucoLandingController(args, mqtt_adapter)
        target_frame_period = 1.0 / max(float(args.target_fps), 1.0)

        while True:
            tick = time.time()
            ok, frame, frame_ts = source.read(timeout=float(args.tail_read_timeout) if args.input_mode == 'tail_h264' else None)
            if not ok or frame is None:
                if args.input_mode == 'tail_h264':
                    continue
                print('输入结束')
                break

            if frame.shape[1] != int(args.image_width) or frame.shape[0] != int(args.image_height):
                frame = cv2.resize(frame, (int(args.image_width), int(args.image_height)))

            # update 只计算动作；maybe_send_command 再执行频率、模式和就绪门控。
            info = controller.update(frame)
            controller.maybe_send_command(info['cmd'], info['action'])

            if controller.state_machine == controller.LAND and not args.no_disarm:
                enough_time = (controller._land_start_time is not None and (time.time() - controller._land_start_time) >= float(args.disarm_delay))
                if enough_time and controller.should_finalize_land(time.time()):
                    mqtt_adapter.shutdown_after_land(args)
                    break

            if args.preview:
                lag = None
                if frame_ts is not None:
                    lag = max(0.0, time.time() - frame_ts)
                overlay = controller.draw_overlay(frame, info, source_lag=lag)
                cv2.imshow('aruco_landing_mqtt', overlay)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    mqtt_adapter.release_control(args, reason='preview quit')
                    break

            if args.input_mode != 'tail_h264':
                elapsed = time.time() - tick
                sleep_t = target_frame_period - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)

            if controller.state_machine == controller.LAND and args.no_disarm:
                print('已进入 LAND 状态，脚本结束。')
                time.sleep(0.2)
                break

    except KeyboardInterrupt:
        # 人工中断不能只关闭进程，否则最后一条非零杆量可能短时残留。
        print('用户中断，开始执行安全收尾...')
        if mqtt_adapter is not None and args is not None:
            try:
                mqtt_adapter.restore_after_interrupt(args)
            except Exception as e:
                print('[MQTT_WARN] interrupt cleanup failed: {}'.format(e))
    except Exception as e:
        print('运行失败: {}'.format(e))
        if mqtt_adapter is not None and args is not None:
            try:
                mqtt_adapter.restore_after_interrupt(args, reason='exception cleanup')
            except Exception as cleanup_e:
                print('[MQTT_WARN] exception cleanup failed: {}'.format(cleanup_e))
        sys.exit(1)
    finally:
        try:
            if source is not None:
                source.release()
        except Exception:
            pass
        try:
            if mqtt_adapter is not None:
                mqtt_adapter.close()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


if __name__ == '__main__':
    # 文件被 import 时不启动；作为脚本运行时选择带完整中断清理的入口。
    run_with_interrupt_cleanup()
