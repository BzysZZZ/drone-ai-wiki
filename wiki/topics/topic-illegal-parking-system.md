# 车辆违停取证系统

> **类型**: topic
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: [[raw/project-illegal-parking.md]]

## 摘要
基于 YOLOv8 车辆检测 + ByteTrack 多目标跟踪的智能违停取证系统。支持自定义多边形 ROI、车辆停留时长统计、双重确认防误报、自动证据链生成（全景+车牌特写+JSON日志）。可联动车牌识别实现「违停→取证→追责」全闭环。

---

## 🛠️ 环境配置

```bash
# 1. 创建环境
conda create -n parking python=3.10 -y
conda activate parking

# 2. PyTorch
pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu118

# 3. 核心依赖
pip install ultralytics opencv-python-headless numpy shapely supervision

# 4. 可选：Web 管理后台
pip install fastapi uvicorn sqlite3 jinja2 python-multipart

# 5. 可选：车牌识别联动
# 需要先完成车牌识别项目的环境配置
```

---

## 💻 核心代码：完整推理管线

```python
import cv2
import json
import time
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from shapely.geometry import Point, Polygon

import torch
import supervision as sv
from ultralytics import YOLO


# ============================================================
# 配置类
# ============================================================
class Config:
    # ROI 区域 (消防通道示例 — 四边形顶点)
    ROI_POLYGON = [(100, 200), (800, 200), (900, 500), (50, 500)]
    
    # 违停判定阈值
    TIME_THRESHOLD = 60        # 停留超过 60 秒判定违停
    STATIONARY_FRAMES = 30     # 连续静止 30 帧确认
    MIN_IOU_STATIC = 0.6       # 静止判定 IoU 阈值
    CONSECUTIVE_ALERT = 5      # 连续告警次数防抖
    
    # 模型
    MODEL_PATH = 'yolov8n.pt'
    CONF_THRESHOLD = 0.4
    IOU_THRESHOLD = 0.45
    
    # 证据存储
    EVIDENCE_DIR = Path('./evidence')
    VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck
    
    # 视频源
    VIDEO_SOURCE = 0  # 0 = 摄像头, 或 RTSP 地址


# ============================================================
# ROI 区域管理器
# ============================================================
class ROIManager:
    def __init__(self, polygons):
        """polygons: {name: [(x1,y1), ...]}"""
        self.regions = {}
        for name, points in polygons.items():
            self.regions[name] = Polygon(points)
    
    def is_inside(self, point, region_name=None):
        """判断点是否在 ROI 内"""
        point = Point(point)
        if region_name:
            return self.regions[region_name].contains(point)
        return any(r.contains(point) for r in self.regions.values())
    
    def draw_roi(self, frame):
        """绘制 ROI 区域"""
        for name, poly in self.regions.items():
            pts = np.array(poly.exterior.coords, dtype=np.int32)
            cv2.polylines(frame, [pts], True, (0, 0, 255), 2)
            cv2.putText(frame, name, (pts[0][0], pts[0][1]-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        return frame


# ============================================================
# 违停判定引擎
# ============================================================
class ViolationEngine:
    def __init__(self, config: Config, roi_manager: ROIManager):
        self.cfg = config
        self.roi = roi_manager
        
        # 跟踪状态: track_id → {enter_time, last_bbox, stationary_count, alert_count, alerted, evidence_saved}
        self.tracks = defaultdict(lambda: {
            'enter_time': None,       # 进入 ROI 的时间
            'last_bbox': None,        # 上一个 bbox
            'stationary_count': 0,    # 连续静止帧数
            'alert_count': 0,         # 连续告警帧数
            'alerted': False,         # 是否已触发违停
            'evidence_saved': False,  # 是否已保存证据
            'plate_crop': None,       # 裁剪的车牌区域
        })
        
    def update(self, track_id, bbox, frame, timestamp):
        """
        每次检测更新单辆车状态
        Returns: (is_violation, event_type)
            event_type: 'enter_roi' | 'stationary' | 'violation' | None
        """
        state = self.tracks[track_id]
        center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        
        # === 1. 空间判定：是否在 ROI 内 ===
        in_roi = self.roi.is_inside(center)
        
        if not in_roi:
            # 离开 ROI，重置状态
            state['enter_time'] = None
            state['stationary_count'] = 0
            state['alert_count'] = 0
            return False, None
        
        # === 2. 进入 ROI 记录时间 ===
        if state['enter_time'] is None:
            state['enter_time'] = timestamp
            state['last_bbox'] = bbox
            return False, 'enter_roi'
        
        # === 3. 静止判定（IoU 计算） ===
        if state['last_bbox'] is not None:
            iou = self._compute_iou(bbox, state['last_bbox'])
            if iou > self.cfg.MIN_IOU_STATIC:
                state['stationary_count'] += 1
            else:
                state['stationary_count'] = max(0, state['stationary_count'] - 1)
        
        state['last_bbox'] = bbox
        
        # === 4. 时间判定 ===
        elapsed = timestamp - state['enter_time']
        
        is_stationary = state['stationary_count'] >= self.cfg.STATIONARY_FRAMES
        is_timeout = elapsed >= self.cfg.TIME_THRESHOLD
        
        # === 5. 联防机制 ===
        if is_stationary and is_timeout and not state['alerted']:
            state['alert_count'] += 1
            if state['alert_count'] >= self.cfg.CONSECUTIVE_ALERT:
                state['alerted'] = True
                return True, 'violation'
            return False, 'stationary'
        
        if not is_stationary:
            state['alert_count'] = max(0, state['alert_count'] - 1)
        
        return False, None
    
    def _compute_iou(self, bbox1, bbox2):
        """计算两个 bbox 的 IoU"""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        return inter / (area1 + area2 - inter + 1e-6)
    
    def reset(self, track_id):
        """手动重置某车状态"""
        self.tracks[track_id] = defaultdict(lambda: {
            'enter_time': None, 'last_bbox': None,
            'stationary_count': 0, 'alert_count': 0,
            'alerted': False, 'evidence_saved': False,
            'plate_crop': None,
        })


# ============================================================
# 证据生成器
# ============================================================
class EvidenceGenerator:
    def __init__(self, config: Config):
        self.cfg = config
        self.cfg.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        self.record = []  # 违停记录
    
    def save(self, frame, bbox, track_id, elapsed_time, violation_time=None):
        """保存违停证据"""
        if violation_time is None:
            violation_time = datetime.now()
        
        case_id = violation_time.strftime('%Y%m%d_%H%M%S') + f'_{track_id}'
        case_dir = self.cfg.EVIDENCE_DIR / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        
        x1, y1, x2, y2 = map(int, bbox)
        
        # 1. 全景图（带 bbox + 时间叠加）
        panorama = frame.copy()
        cv2.rectangle(panorama, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(panorama, f'ID:{track_id} TIME:{elapsed_time:.0f}s',
                   (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(panorama, violation_time.strftime('%Y-%m-%d %H:%M:%S'),
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.imwrite(str(case_dir / 'panorama.jpg'), panorama)
        
        # 2. 车牌区域裁剪
        plate_crop = frame[y1:y2, x1:x2]
        cv2.imwrite(str(case_dir / 'plate_crop.jpg'), plate_crop)
        
        # 3. JSON 元数据
        metadata = {
            'case_id': case_id,
            'track_id': track_id,
            'violation_time': violation_time.isoformat(),
            'elapsed_seconds': elapsed_time,
            'bbox': [x1, y1, x2, y2],
            'roi': str(self.cfg.ROI_POLYGON),
        }
        with open(case_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        self.record.append(metadata)
        
        return case_id


# ============================================================
# 主程序
# ============================================================
def main():
    cfg = Config()
    
    # 初始化组件
    roi_manager = ROIManager({'fire_lane': cfg.ROI_POLYGON})
    violation_engine = ViolationEngine(cfg, roi_manager)
    evidence_gen = EvidenceGenerator(cfg)
    
    # 加载模型
    model = YOLO(cfg.MODEL_PATH)
    byte_tracker = sv.ByteTrack(
        track_activation_threshold=0.25,
        lost_track_buffer=30,
        minimum_matching_threshold=0.8,
        frame_rate=30,
    )
    box_annotator = sv.BoxAnnotator(thickness=2)
    
    # 打开视频流
    cap = cv2.VideoCapture(cfg.VIDEO_SOURCE)
    start_time = time.time()
    frame_count = 0
    
    print(f"[INFO] 违停取证系统启动, ROI={cfg.ROI_POLYGON}")
    print(f"[INFO] 阈值: TIME={cfg.TIME_THRESHOLD}s, STATIONARY={cfg.STATIONARY_FRAMES}frames")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        timestamp = time.time() - start_time
        
        # 1. 目标检测
        results = model(frame, conf=cfg.CONF_THRESHOLD, iou=cfg.IOU_THRESHOLD, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)
        
        # 过滤仅保留车辆类
        vehicle_mask = np.isin(detections.class_id, cfg.VEHICLE_CLASSES)
        detections = detections[vehicle_mask]
        
        # 2. 目标跟踪
        detections = byte_tracker.update_with_detections(detections)
        
        # 3. 绘制 ROI
        frame = roi_manager.draw_roi(frame)
        
        # 4. 违停判定
        violation_events = []
        for i, track_id in enumerate(detections.tracker_id):
            if track_id is None:
                continue
            bbox = detections.xyxy[i]
            is_violation, event = violation_engine.update(
                int(track_id), bbox, frame, timestamp
            )
            if is_violation:
                violation_events.append((int(track_id), bbox, timestamp))
        
        # 5. 证据保存
        for track_id, bbox, ts in violation_events:
            state = violation_engine.tracks[track_id]
            if not state['evidence_saved']:
                elapsed = ts - state['enter_time']
                case_id = evidence_gen.save(frame, bbox, track_id, elapsed)
                print(f"[证据] 违停案件: {case_id}")
                state['evidence_saved'] = True
        
        # 6. 可视化
        annotated_frame = box_annotator.annotate(frame, detections)
        
        # 7. 叠加状态信息
        cv2.putText(annotated_frame, f'Frame: {frame_count}',
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(annotated_frame, f'Active tracks: {len(detections)}',
                   (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(annotated_frame, f'Violations today: {len(evidence_gen.record)}',
                   (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
        
        cv2.imshow('Illegal Parking Detection', annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print(f"[INFO] 系统关闭, 今日违停: {len(evidence_gen.record)} 件")


if __name__ == '__main__':
    main()
```

---

## 系统架构图

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────┐
│  RTSP 视频流 │ → │  YOLOv8 检测  │ → │  ByteTrack 跟踪   │
│  (4-8 路)    │    │  车辆 bbox    │    │  track_id + 轨迹  │
└─────────────┘    └──────────────┘    └────────┬─────────┘
                                                │
                              ┌─────────────────┘
                              ▼
                    ┌──────────────────┐
                    │   ROI 多边形判定   │
                    │  射线法 + 停留时长  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  进入/离开   │  │  静止判定   │  │  超时判定   │
    │  记录时间戳  │  │  IoU > 0.6 │  │  > 60s     │
    └────────────┘  └────────────┘  └────────────┘
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                    ┌──────────────────┐
                    │  联防机制 (5帧)   │
                    │  触发 → 证据生成   │
                    └────────┬─────────┘
                             ▼
    ┌────────────────────────────────────────────┐
    │             证据链生成                       │
    │  • 全景图 (bbox + 时间戳叠加)                │
    │  • 车牌裁剪图                               │
    │  • JSON 元数据 (时长/位置/时间)              │
    └────────────────────────────────────────────┘
```

## 联动车牌识别

```python
# 在 violation 触发时调用
from license_plate import LicensePlateRecognizer  # 来自车牌识别项目

lpr = LicensePlateRecognizer('detector.pt', 'lprnet.pth')

# 在 EvidenceGenerator.save() 中加入
plate_crop = frame[y1:y2, x1:x2]
plate_results = lpr(plate_crop)
if plate_results:
    metadata['plate_number'] = plate_results[0]['text']
    metadata['plate_confidence'] = plate_results[0]['confidence']
```

## 关键参数调优

| 参数 | 建议值 | 调整策略 |
|------|--------|---------|
| TIME_THRESHOLD | 60-120s | 路边停车取 60s，消防通道取 30s |
| STATIONARY_FRAMES | 20-30 | 帧率越高设越大，避免等红灯误报 |
| MIN_IOU_STATIC | 0.6-0.8 | 摄像头抖动时适当降低 |
| CONSECUTIVE_ALERT | 3-5 | 防短暂遮挡导致的误报恢复 |
| YOLO conf | 0.35-0.5 | 允许一定漏检，通过跟踪补偿 |

## 关联
- 相关概念: [[concepts/concept-object-detection]]
- 关联项目: [[topics/topic-license-plate-recognition]]
- 参见: [[concepts/method-model-deployment]]

## 引用来源
- [1] [[raw/project-illegal-parking.md]] — 完整技术资料

## 核心论文引用

- [1] **ByteTrack** — Zhang et al., "ByteTrack: Multi-Object Tracking by Associating Every Detection Box," ECCV 2022. [违停跟踪核心算法]
- [2] **DeepSORT** — Wojke et al., "Simple Online and Realtime Tracking with a Deep Association Metric," ICIP 2017.
- [3] **StrongSORT** — Du et al., "StrongSORT: Make DeepSORT Great Again," IEEE TCSVT 2023.
- [4] **SORT** — Bewley et al., "Simple Online and Realtime Tracking," ICIP 2016.
- [5] **Hungarian Algorithm** — Kuhn, "The Hungarian Method for the Assignment Problem," Naval Research Logistics 1955. [MOT数据关联基础]
- [6] **YOLOv8** — Jocher et al., "Ultralytics YOLOv8," GitHub 2023.
- [7] **Supervision** — Skalski et al., "Supervision: Computer Vision Utilities Library," GitHub 2023. [多边形ROI工具]
- [8] **Kalman Filter** — Kalman, "A New Approach to Linear Filtering and Prediction Problems," JBE 1960. [跟踪状态预测]
- [9] **Illegal Parking Detection** — Hua et al., "A Vehicle Detection and Tracking Method Based on Deep Learning," IEEE Sensors 2021.
- [10] **Re-ID** — Zheng et al., "Person Re-Identification: Past, Present and Future," arXiv 2016. [跨摄像头关联基础]
- [11] **CCPD** — Xu et al., "Towards End-to-End License Plate Detection and Recognition," ECCV 2018.
- [12] **Multi-Camera MOT** — Wen et al., "UA-DETRAC: A New Benchmark and Protocol for Multi-Object Detection and Tracking," CVIU 2020.

## 变更记录
- 2026-06-27: 初始创建
- 2026-06-27: 增强版，新增环境配置、完整推理管线代码(200+行)、架构图、车牌联动接口、参数调优指南
- 2026-06-29: 补充12篇核心论文引用
