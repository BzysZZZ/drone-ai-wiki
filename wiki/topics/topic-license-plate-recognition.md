# 车牌识别系统

> **类型**: topic
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: [[raw/project-license-plate-recognition.md]]

## 摘要
基于 YOLOv8 + LPRNet 的端到端车牌识别系统。YOLOv8 定位车牌区域，四点透视变换矫正倾斜，LPRNet（CTC Loss）识别字符。支持蓝牌/绿牌/黄牌/警牌等全类型中国车牌。TensorRT 部署后可实现 30+ FPS 实时推理。

---

## 🛠️ 环境配置

### 依赖安装

```bash
# 1. 创建 conda 环境
conda create -n lpr python=3.10 -y
conda activate lpr

# 2. 安装 PyTorch (CUDA 11.8 示例，根据你的 CUDA 版本调整)
pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu118

# 3. 安装核心依赖
pip install ultralytics opencv-python-headless numpy shapely supervision

# 4. 安装部署相关（按需）
pip install onnx onnxruntime-gpu onnx-simplifier  # ONNX
pip install tensorrt  # TensorRT (需要先装 NVIDIA TensorRT SDK)

# 5. 安装 CCPD 数据集解析工具
pip install scikit-learn albumentations tqdm
```

### 硬件要求

| 场景 | GPU | 显存 | 预计 FPS |
|------|-----|------|---------|
| 训练 | RTX 3090/4090 | 24GB | - |
| 训练(小) | RTX 3060 | 12GB | - |
| 推理(GPU) | RTX 2060+ | 6GB | 30+ |
| 推理(边缘) | Jetson Orin NX | 8GB | 15+ |
| 推理(边缘) | RK3588 | 4GB | 10+ |

---

## 💻 核心代码

### 1. CCPD → YOLO 格式转换

```python
"""
CCPD 数据集文件名自带标注信息：
025-95_113-154&383_386&473-386&473_177&454_154&383_363&402-0_0_22_27_27_33_16-37-15.jpg
格式：面积-水平倾角_垂直倾角-四个角点坐标-车牌号
"""
import os
import cv2
import shutil
from pathlib import Path

def parse_ccpd_filename(filename):
    """解析 CCPD 文件名获取标注信息"""
    basename = os.path.splitext(filename)[0]
    parts = basename.split('-')
    
    # 提取四个角点坐标
    coords_str = parts[2]
    coords = []
    for pair in coords_str.split('_'):
        x, y = pair.split('&')
        coords.append([int(x), int(y)])
    
    # 车牌号（第 4 部分）
    plate_number = parts[4] if len(parts) > 4 else ""
    
    return coords, plate_number

def convert_ccpd_to_yolo(ccpd_dir, output_dir, train_ratio=0.9):
    """将 CCPD 数据集转换为 YOLO 格式"""
    output_dir = Path(output_dir)
    (output_dir / 'images' / 'train').mkdir(parents=True, exist_ok=True)
    (output_dir / 'images' / 'val').mkdir(parents=True, exist_ok=True)
    (output_dir / 'labels' / 'train').mkdir(parents=True, exist_ok=True)
    (output_dir / 'labels' / 'val').mkdir(parents=True, exist_ok=True)
    
    images = sorted(Path(ccpd_dir).glob('*.jpg'))
    train_count = int(len(images) * train_ratio)
    
    for idx, img_path in enumerate(images):
        # 读取图片获取尺寸
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        
        # 解析标注
        coords, plate_number = parse_ccpd_filename(img_path.name)
        
        # 角点坐标转 YOLO bbox (cx, cy, bw, bh 归一化)
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        
        cx = ((x_min + x_max) / 2) / w
        cy = ((y_min + y_max) / 2) / h
        bw = (x_max - x_min) / w
        bh = (y_max - y_min) / h
        
        # 判断 train/val
        split = 'train' if idx < train_count else 'val'
        
        # 复制图片
        shutil.copy(img_path, output_dir / 'images' / split / img_path.name)
        
        # 写 YOLO 标注
        label_path = output_dir / 'labels' / split / f"{img_path.stem}.txt"
        with open(label_path, 'w') as f:
            f.write(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
    
    print(f"转换完成: train={train_count}, val={len(images)-train_count}")

# 使用
# convert_ccpd_to_yolo('/data/CCPD2020/', '/data/CCPD_YOLO/')
```

### 2. LPRNet 模型定义 + CTC 识别

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class LPRNet(nn.Module):
    """Lightweight License Plate Recognition Network
    
    输入: (B, 3, 24, 94) — 矫正后的车牌图片
    输出: (B, T, 68) — CTC 每个时间步的字符概率
    字符集: 31省简称 + 24字母 + 10数字 + 3特殊 = 68 类
    """
    def __init__(self, num_classes=68, dropout=0.3):
        super().__init__()
        
        # Backbone (small CNN)
        self.backbone = nn.Sequential(
            # Block 1: 24×94 → 12×47
            nn.Conv2d(3, 64, 3, stride=1, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d(2, 2),
            
            # Block 2: 12×47 → 6×23
            nn.Conv2d(64, 128, 3, stride=1, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d(2, 2),
            
            # Block 3: 6×23 → 3×11
            nn.Conv2d(128, 256, 3, stride=1, padding=1), nn.BatchNorm2d(256), nn.ReLU(),
            nn.MaxPool2d((2, 1), (2, 1)),  # 只在高度维度下采样
            
            # Block 4: 3×11
            nn.Conv2d(256, 256, 3, stride=1, padding=1), nn.BatchNorm2d(256), nn.ReLU(),
            nn.Dropout(dropout),
        )
        
        # 分类头
        self.fc = nn.Linear(256 * 3, num_classes)  # 输出 68 类
    
    def forward(self, x):
        # x: (B, 3, 24, 94)
        features = self.backbone(x)  # (B, 256, 3, 11)
        
        # 保留宽度维度作为时间步
        B, C, H, W = features.shape
        features = features.permute(0, 3, 1, 2)  # (B, 11, 256, 3)
        features = features.reshape(B, W, C * H)  # (B, 11, 768)
        
        # 全连接 + LogSoftmax
        logits = self.fc(features)  # (B, 11, 68)
        return F.log_softmax(logits, dim=2)


class CTCLabelConverter:
    """CTC 解码器：将模型输出转为字符串"""
    
    # 字符集（索引 0 留空给 CTC blank）
    CHARS = ['-'] + \
            ['京','津','冀','晋','蒙','辽','吉','黑','沪','苏','浙',
             '皖','闽','赣','鲁','豫','鄂','湘','粤','桂','琼','渝',
             '川','贵','云','藏','陕','甘','青','宁','新'] + \
            ['A','B','C','D','E','F','G','H','J','K','L','M',
             'N','P','Q','R','S','T','U','V','W','X','Y','Z'] + \
            ['0','1','2','3','4','5','6','7','8','9'] + \
            ['港','澳','学']
    
    def __init__(self):
        self.char2idx = {c: i for i, c in enumerate(self.CHARS)}
        self.idx2char = {i: c for i, c in enumerate(self.CHARS)}
    
    def encode(self, text):
        """字符串 → 索引序列"""
        return [self.char2idx.get(c, 0) for c in text]
    
    def decode(self, indices, remove_blank=True):
        """CTC greedy decode: 索引序列 → 字符串"""
        result = []
        prev = -1
        for idx in indices:
            if idx == 0:  # blank
                if remove_blank:
                    prev = 0
                continue
            if idx != prev:
                result.append(self.idx2char.get(idx, ''))
            prev = idx
        return ''.join(result)
    
    def batch_decode(self, logits):
        """批量 CTC 解码"""
        # logits: (B, T, C) — 概率
        _, indices = logits.max(dim=2)  # (B, T)
        results = []
        for i in range(indices.size(0)):
            results.append(self.decode(indices[i].tolist()))
        return results
```

### 3. 透视变换矫正（核心算法）

```python
import cv2
import numpy as np

def correct_plate_perspective(img, bbox):
    """
    四点透视变换矫正倾斜车牌
    
    Args:
        img: 原始图片 (H, W, 3)
        bbox: 四点坐标 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
              顺序: 左上 → 右上 → 右下 → 左下
    
    Returns:
        plate: 矫正后的车牌图片 (24, 94, 3)
    """
    # 源点（根据左上角最小距离排序）
    bbox = np.array(bbox, dtype=np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)
    
    s = bbox.sum(axis=1)
    rect[0] = bbox[np.argmin(s)]   # 左上: x+y 最小
    rect[2] = bbox[np.argmax(s)]   # 右下: x+y 最大
    
    diff = np.diff(bbox, axis=1)
    rect[1] = bbox[np.argmin(diff)]  # 右上: y-x 最小
    rect[3] = bbox[np.argmax(diff)]  # 左下: y-x 最大
    
    # 目标尺寸（标准车牌 94×24）
    width, height = 94, 24
    dst = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1]
    ], dtype=np.float32)
    
    # 透视变换
    M = cv2.getPerspectiveTransform(rect, dst)
    plate = cv2.warpPerspective(img, M, (width, height))
    
    return plate
```

### 4. 完整推理管线

```python
import cv2
import torch
import numpy as np
from ultralytics import YOLO

class LicensePlateRecognizer:
    """端到端车牌识别管线"""
    
    def __init__(self, detector_path, recognizer_path):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.detector = YOLO(detector_path)  # YOLOv8 权重
        self.recognizer = LPRNet(num_classes=68).to(self.device)
        self.recognizer.load_state_dict(torch.load(recognizer_path, map_location=self.device))
        self.recognizer.eval()
        self.converter = CTCLabelConverter()
    
    def preprocess_plate(self, plate_img):
        """预处理车牌图片"""
        # 调整到标准尺寸
        plate = cv2.resize(plate_img, (94, 24))
        # 归一化
        plate = plate.astype(np.float32) / 255.0
        plate = (plate - 0.5) / 0.5  # [-1, 1]
        # CHW 格式
        plate = torch.from_numpy(plate).permute(2, 0, 1).unsqueeze(0)
        return plate.to(self.device)
    
    def __call__(self, img):
        """
        输入: 图片 (BGR)
        输出: [(plate_text, confidence, bbox), ...]
        """
        # 1. 检测车牌区域
        results = self.detector(img, conf=0.25, iou=0.45, verbose=False)[0]
        
        plates = []
        if len(results.boxes) == 0:
            return plates
        
        # 2. 逐个识别
        for box in results.boxes:
            # 获取四点坐标（如果有 keypoints）
            if results.keypoints is not None and len(results.keypoints) > 0:
                # 使用关键点做透视矫正
                kpts = results.keypoints.xy[0].cpu().numpy()
                plate_img = correct_plate_perspective(img, kpts[:4])
            else:
                # 直接用 bbox 裁剪
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = img[y1:y2, x1:x2]
                plate_img = cv2.resize(plate_img, (94, 24))
            
            # 3. LPRNet 识别
            plate_tensor = self.preprocess_plate(plate_img)
            with torch.no_grad():
                logits = self.recognizer(plate_tensor)  # (1, T, 68)
            
            # 4. CTC 解码
            plate_text = self.converter.batch_decode(logits)[0]
            confidence = float(torch.exp(logits).max(dim=2)[0].mean())
            
            plates.append({
                'text': plate_text,
                'confidence': confidence,
                'bbox': box.xyxy[0].cpu().numpy().tolist()
            })
        
        return plates


# ========== 使用示例 ==========
if __name__ == '__main__':
    recognizer = LicensePlateRecognizer(
        detector_path='runs/detect/train/weights/best.pt',
        recognizer_path='lprnet_best.pth'
    )
    
    # 图片推理
    img = cv2.imread('test.jpg')
    results = recognizer(img)
    for r in results:
        print(f"车牌: {r['text']}, 置信度: {r['confidence']:.3f}")
    
    # 视频流推理
    cap = cv2.VideoCapture('test.mp4')
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        results = recognizer(frame)
        for r in results:
            x1, y1, x2, y2 = map(int, r['bbox'])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, r['text'], (x1, y1-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow('LPR', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
```

### 5. 训练命令

```bash
# === YOLOv8 车牌检测训练 ===
# 数据集配置 ccpd.yaml:
#   path: /data/CCPD_YOLO/
#   train: images/train
#   val: images/val
#   names: {0: plate}
#   nc: 1

yolo detect train \
    model=yolov8n.pt \
    data=ccpd.yaml \
    epochs=100 \
    imgsz=640 \
    batch=32 \
    lr0=0.01 \
    lrf=0.01 \
    momentum=0.937 \
    weight_decay=0.0005 \
    warmup_epochs=3 \
    cos_lr=True \
    device=0

# === LPRNet 识别训练 ===
python train_lprnet.py \
    --train_data /data/CCPD_YOLO/crops/train \
    --val_data /data/CCPD_YOLO/crops/val \
    --epochs 100 \
    --batch_size 128 \
    --lr 1e-3 \
    --num_classes 68
```

## 关联
- 相关概念: [[concepts/concept-object-detection]]
- 关联项目: [[topics/topic-illegal-parking-system]]（违停系统集成车牌识别）
- 数据集: [[entities/dataset-visdrone]]

## 引用来源
- [1] [[raw/project-license-plate-recognition.md]] — 完整技术资料

## 核心论文引用

- [1] **LPRNet** — Zherzdev & Gruzdev, "LPRNet: License Plate Recognition via Deep Neural Networks," arXiv 2018. [车牌识别核心架构]
- [2] **YOLOv8** — Jocher et al., "Ultralytics YOLOv8," GitHub 2023.
- [3] **CCPD** — Xu et al., "Towards End-to-End License Plate Detection and Recognition: A Large Dataset and Baseline," ECCV 2018. [中国车牌数据集标准]
- [4] **HyperLPR** — 开源项目，"HyperLPR: High Performance Chinese License Plate Recognition Framework," GitHub 2019.
- [5] **CTC** — Graves et al., "Connectionist Temporal Classification: Labelling Unsegmented Sequence Data with Recurrent Neural Networks," ICML 2006. [LPRNet解码基础]
- [6] **CRNN** — Shi et al., "An End-to-End Trainable Neural Network for Image-based Sequence Recognition," TPAMI 2017. [OCR经典方案]
- [7] **Spatial Transformer** — Jaderberg et al., "Spatial Transformer Networks," NeurIPS 2015. [透视矫正理论基础]
- [8] **TPS-STN** — Shi et al., "ASTER: An Attentional Scene Text Recognizer," TPAMI 2019. [薄板样条变换]
- [9] **TensorRT** — NVIDIA, "TensorRT Documentation," 2024. [部署加速]
- [10] **四点透视变换** — Hartley & Zisserman, "Multiple View Geometry in Computer Vision," Cambridge 2004.
- [11] **Scene Text Recognition** — Chen et al., "Text Recognition in the Wild: A Survey," ACM CSUR 2021.
- [12] **TPH-YOLOv5** — Zhu et al., "TPH-YOLOv5: Improved YOLOv5 Based on Transformer Prediction Head for Object Detection on Drone-Captured Scenarios," ICCV-W 2021.

## 变更记录
- 2026-06-27: 初始创建
- 2026-06-27: 增强版，新增环境配置、完整代码(LPRNet/CTC/透视矫正/推理管线)、训练命令
- 2026-06-29: 补充12篇核心论文引用
