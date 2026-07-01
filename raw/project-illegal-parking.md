# 项目资料：车辆违停取证系统（完整版）

> **来源类型**: 技术调研 + 工程实践整理
> **采集日期**: 2026-06-27
> **项目背景**: 结合车牌识别的智能交通管理项目，覆盖检测/跟踪/判违/取证全链路

---

## 项目概述

传统违停管理依赖人工巡逻，效率低、取证难。本系统结合 **YOLOv8 车辆检测 + ByteTrack 多目标跟踪 + 自定义 ROI 多边形区域 + 时间阈值违规判定**，实现全自动违停检测与证据链生成。

---

## 系统架构

```
┌─────────────┐
│  视频流输入   │ (RTSP/摄像头/USB)
└──────┬──────┘
       ▼
┌─────────────┐
│  YOLOv8      │ 车辆检测（car/truck/bus 三类）
│  车辆检测     │ 输出: bbox + class + confidence
└──────┬──────┘
       ▼
┌─────────────┐
│  ByteTrack   │ 多目标跟踪，分配唯一 track_id
│  目标跟踪     │ 保持跨帧身份一致
└──────┬──────┘
       ▼
┌─────────────┐
│  ROI 判定    │ 检测车辆中心点是否在违停多边形内
│  区域过滤     │ 判断停留时长是否超过阈值
└──────┬──────┘
       ▼
┌─────────────────────┐
│  违停判定引擎         │
│  - 停留时间 > T_illegal │
│  - 车辆静止（IoU 变化小）│
│  - 双重确认（连续N帧）   │
└──────┬──────────────┘
       ▼
┌─────────────────────┐
│  证据生成             │
│  - 全景图 + 车牌特写   │
│  - 时间戳 + 位置叠加   │
│  - JSON 事件日志       │
└─────────────────────┘
```

---

## 核心代码实现

### 1. ROI 区域配置

```python
import numpy as np

# 方式一：配置文件（推荐）
no_parking_zones = [
    {
        "id": "zone_A",
        "polygon": [(100, 200), (400, 200), (400, 400), (100, 400)],
        "max_duration": 120,  # 秒
        "description": "消防通道"
    },
    {
        "id": "zone_B",
        "polygon": [(500, 100), (700, 100), (700, 350), (500, 350)],
        "max_duration": 60,
        "description": "公交专用道"
    }
]

# 方式二：交互式 ROI 绘制工具（cv2.polylines + 鼠标回调）
# 使用 Supervision 库的 PolygonZone
from supervision import PolygonZone

zone = PolygonZone(
    polygon=np.array([[100,200],[400,200],[400,400],[100,400]]),
    triggering_anchors=[0, 1, 2, 3]  # 四个角点触发
)
```

### 2. 完整推理管线

```python
import cv2
import supervision as sv
from ultralytics import YOLO
from collections import defaultdict
import time

# ── 初始化 ──
model = YOLO("yolov8n.pt")  # 或用自定义训练的 best.pt
tracker = sv.ByteTrack(frame_rate=30)
box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()

# 状态维护
vehicle_states = defaultdict(lambda: {
    "enter_time": None,     # 进入时间戳
    "last_position": None,  # 上次位置
    "stationary_frames": 0, # 连续静止帧数
    "violation_start": None,# 违规开始时间
    "violated": False,      # 是否已违规
    "photos": []            # 证据图片
})

# 参数
TIME_THRESHOLD = 60        # 违停判定时长 (秒)
STATIONARY_THRESH = 30     # 视为"停车"的连续静止帧数
MIN_IOU_FOR_STATIC = 0.6   # 判断静止的 IoU 阈值
CONSECUTIVE_ALERT = 5      # 连续确认帧数

# ── 主循环 ──
cap = cv2.VideoCapture("rtsp://camera_stream")

while True:
    ret, frame = cap.read()
    if not ret: break

    # 1. 车辆检测
    results = model(frame, classes=[2,5,7], conf=0.4)[0]  # car, bus, truck
    detections = sv.Detections.from_ultralytics(results)

    # 2. 目标跟踪
    detections = tracker.update_with_detections(detections)

    # 3. 遍历每个跟踪目标
    current_ids = set()
    for i, (tracker_id, bbox) in enumerate(zip(
        detections.tracker_id, detections.xyxy
    )):
        tid = int(tracker_id)
        current_ids.add(tid)
        state = vehicle_states[tid]

        # 计算车辆中心点
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        current_pos = (cx, cy)

        # 检查是否在违停区域内
        in_zone = is_point_in_polygon(current_pos, no_parking_zones[0]["polygon"])

        if in_zone:
            if state["enter_time"] is None:
                state["enter_time"] = time.time()

            # 判断是否静止
            if state["last_position"] is not None:
                iou = compute_iou(bbox, state["last_bbox"])
                if iou > MIN_IOU_FOR_STATIC:
                    state["stationary_frames"] += 1
                else:
                    state["stationary_frames"] = 0

            # 违停判定
            elapsed = time.time() - state["enter_time"]
            is_static = state["stationary_frames"] >= STATIONARY_THRESH

            if is_static and elapsed > TIME_THRESHOLD and not state["violated"]:
                # 连续确认
                state["violation_count"] = state.get("violation_count", 0) + 1
                if state["violation_count"] >= CONSECUTIVE_ALERT:
                    state["violated"] = True
                    state["violation_start"] = time.time()
                    # 生成证据
                    evidence = generate_evidence(frame, tid, bbox, elapsed)
                    save_evidence(evidence)
        else:
            # 离开区域 → 重置
            if state["enter_time"] is not None:
                state["enter_time"] = None
                state["stationary_frames"] = 0

        state["last_position"] = current_pos
        state["last_bbox"] = bbox

    # 清理丢失的目标
    for tid in list(vehicle_states.keys()):
        if tid not in current_ids:
            state = vehicle_states[tid]
            if state["violated"] and time.time() - state.get("last_seen", 0) > 30:
                del vehicle_states[tid]

    # 可视化
    annotated = box_annotator.annotate(frame, detections)
    annotated = draw_roi_zones(annotated, no_parking_zones)
    cv2.imshow("Illegal Parking Detection", annotated)
    if cv2.waitKey(1) & 0xFF == ord('q'): break
```

### 3. 几何工具函数

```python
def is_point_in_polygon(point, polygon):
    """射线法判断点是否在多边形内"""
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def compute_iou(box1, box2):
    """两个 bbox 的 IoU"""
    x1 = max(box1[0], box2[0]); y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2]); y2 = min(box1[3], box2[3])
    inter = max(0, x2-x1) * max(0, y2-y1)
    area1 = (box1[2]-box1[0]) * (box1[3]-box1[1])
    area2 = (box2[2]-box2[0]) * (box2[3]-box2[1])
    return inter / (area1 + area2 - inter + 1e-6)
```

### 4. 证据生成

```python
import json
from datetime import datetime

def generate_evidence(frame, track_id, bbox, duration):
    """生成违停证据包"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 裁剪全景 + 车牌特写
    x1, y1, x2, y2 = map(int, bbox)
    full_view = frame.copy()
    plate_crop = frame[y1:y2, x1:x2]

    # 叠加信息
    overlay = f"ID:{track_id}  Duration:{duration:.0f}s  {timestamp}"
    cv2.putText(full_view, overlay, (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)
    cv2.rectangle(full_view, (x1,y1), (x2,y2), (0,0,255), 3)

    return {
        "track_id": track_id,
        "timestamp": timestamp,
        "duration_seconds": duration,
        "full_view": full_view,
        "plate_crop": plate_crop,
        "bbox": [x1, y1, x2, y2]
    }

def save_evidence(evidence, output_dir="evidence/"):
    """保存证据到磁盘"""
    ts = evidence["timestamp"]
    cv2.imwrite(f"{output_dir}{ts}_full.jpg", evidence["full_view"])
    cv2.imwrite(f"{output_dir}{ts}_plate.jpg", evidence["plate_crop"])
    meta = {k:v for k,v in evidence.items() if k not in ["full_view","plate_crop"]}
    with open(f"{output_dir}{ts}_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
```

---

## 系统配置参数

| 参数 | 建议值 | 说明 |
|------|--------|------|
| TIME_THRESHOLD | 60-120s | 超时即判定违停 |
| STATIONARY_THRESH | 30 帧 | 连续静止帧数 |
| MIN_IOU_FOR_STATIC | 0.6 | 静止判定 IoU 阈值 |
| CONSECUTIVE_ALERT | 5 帧 | 连续确认帧数（防误报） |
| YOLOv8 conf | 0.4 | 检测置信度阈值 |
| ByteTrack lost_buffer | 30 帧 | 目标丢失容忍 |

---

## 扩展功能（简历加分项）

### 1. 车牌联动识别
违停确认后，自动调用车牌识别模块：
```python
if violation_confirmed:
    plate_number = lpr_pipeline(plate_crop)
    evidence["plate_number"] = plate_number
```

### 2. 多 ROI 混合管理
- 使用 SQLite 存储 ROI 区域配置（支持动态增删）
- 支持「禁止停车」「限时停车」「公交车专用道」等不同策略

### 3. 管理后台
- FastAPI + SQLite 后端
- 前端展示违停记录（时间线、车辆照片、车牌）
- 支持人工审核确认/撤销

### 4. 边缘计算部署
- Jetson Orin NX / Xavier NX
- 多路视频流同时处理 (4-8 路)
- TensorRT 加速推理

---

## 性能指标

| 指标 | 目标值 |
|------|--------|
| 车辆检测 mAP@0.5 | > 95% |
| 跟踪 ID Switch | < 3% |
| 违停检测 Precision | > 90% |
| 违停检测 Recall | > 85% |
| 单路视频处理 | > 25 FPS |
| 多路处理 (Jetson) | 4路 × 15 FPS |

---

## 简历包装核心关键词

- YOLOv8 车辆检测 + ByteTrack 多目标跟踪
- 多边形 ROI 区域管理 + 自定义违停策略配置
- 车辆停留时长统计（静止判定 + 时间阈值双确认）
- 自动证据链生成：全景图 + 车牌特写 + 时间戳 JSON
- FastAPI 管理后台 + SQLite 记录存储
- TensorRT 优化部署，Jetson 边缘端多路视频实时分析
- 联动车牌识别，实现「违停→取证→追责」全闭环
