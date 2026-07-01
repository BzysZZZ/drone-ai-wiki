# 项目资料：车牌识别系统（完整版）

> **来源类型**: 技术调研 + 工程实践整理 + 论文复现
> **采集日期**: 2026-06-27
> **项目背景**: 用于简历包装的车牌识别项目技术资料，覆盖从数据到部署的完整链路

---

## 项目概述

车牌识别（License Plate Recognition, LPR）是智能交通系统的核心子系统。完整系统分两阶段：**车牌检测（YOLOv8）** → **字符识别（LPRNet/CRNN）**，辅以透视矫正和视频流去噪。

---

## 完整 Pipeline（含代码骨架）

```
输入视频帧
    ↓
YOLOv8 车牌检测 (返回 bbox)
    ↓
四点透视变换矫正 (getPerspectiveTransform)
    ↓
字符识别 (LPRNet, 94×24 输入, CTC Loss)
    ↓
后处理: 省份规则校验 + 格式正则匹配
    ↓
输出: 车牌号 + 置信度 + 时间戳
```

### 关键代码骨架

**1. CCPD 数据集 → YOLO 格式转换**
```python
import os, cv2

def parse_ccpd_filename(filename):
    """
    CCPD 文件名编码所有标注信息，无需额外标签文件
    格式: 025-95_113-154&383_386&473-386&473_177&454_154&383_363&402...
    解析出: bbox四点坐标 (x1,y1,x2,y2,x3,y3,x4,y4)
    """
    parts = filename.split('-')
    # 第3段是 bbox 坐标
    coords = list(map(int, parts[2].split('_')[0].split('&')))
    # 计算最小包围矩形 → YOLO 格式 (cx, cy, w, h) 归一化
    xs = coords[0::2]
    ys = coords[1::2]
    xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
    img = cv2.imread(filename)
    h, w = img.shape[:2]
    cx = ((xmin + xmax) / 2) / w
    cy = ((ymin + ymax) / 2) / h
    bw = (xmax - xmin) / w
    bh = (ymax - ymin) / h
    return f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"
```

**2. YOLOv8 训练命令**
```bash
# 安装
pip install ultralytics

# 训练
yolo detect train data=ccpd.yaml model=yolov8n.pt epochs=100 imgsz=640 batch=16 \
    name=plate_detection device=0

# 验证
yolo detect val model=runs/detect/plate_detection/weights/best.pt data=ccpd.yaml

# TensorRT 导出 (Jetson/NVIDIA GPU)
yolo export model=best.pt format=engine device=0 half=True
```

**3. LPRNet 网络核心（简化）**
```python
import torch, torch.nn as nn

class small_basic_block(nn.Module):
    """LPRNet 基础卷积块: 1×1 降维 + 3×1 特征提取"""
    def __init__(self, ch_in, ch_out):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(ch_in, ch_out//4, 1),
            nn.ReLU(),
            nn.Conv2d(ch_out//4, ch_out//4, (3,1), padding=(1,0)),
            nn.ReLU(),
            nn.Conv2d(ch_out//4, ch_out//4, (1,3), padding=(0,1)),
            nn.ReLU(),
            nn.Conv2d(ch_out//4, ch_out, 1),
        )
    def forward(self, x):
        return self.block(x)

class LPRNet(nn.Module):
    """输入 94×24×3, 输出 (batch, 68, 18) → CTC 解码到 68 类字符"""
    def __init__(self, class_num=68, dropout_rate=0.5):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Conv2d(3, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool3d((1,3,3), stride=(1,1,1)),  # 仅在空间维度池化
            small_basic_block(64, 128),
            nn.MaxPool3d((1,3,3), stride=(2,1,2)),
            small_basic_block(128, 256),
            small_basic_block(256, 256),
            nn.MaxPool3d((1,3,3), stride=(4,1,2)),
            nn.Dropout(dropout_rate),
            nn.Conv2d(256, 256, (4,1), padding=0),
            nn.Dropout(dropout_rate),
        )
        self.container = nn.Sequential(
            nn.Conv2d(256, class_num, (1,13), padding=(0,6))
        )

    def forward(self, x):
        x = self.backbone(x)
        x = self.container(x)  # → (batch, 68, 1, 18)
        x = x.squeeze(2).permute(2, 0, 1)  # → (18, batch, 68)
        log_probs = nn.functional.log_softmax(x, dim=2)
        return log_probs  # CTC Loss 需要 log_probs
```

**4. 透视变换矫正**
```python
import cv2, numpy as np

def correct_perspective(plate_img, bbox_points):
    """四点透视变换 → 矫正倾斜车牌"""
    pts_src = np.float32(bbox_points)  # 四点坐标
    w, h = 94, 24  # LPRNet 标准输入尺寸
    pts_dst = np.float32([[0,0], [w-1,0], [w-1,h-1], [0,h-1]])
    M = cv2.getPerspectiveTransform(pts_src, pts_dst)
    corrected = cv2.warpPerspective(plate_img, M, (w, h))
    return corrected

def decode_ctc(log_probs, idx_to_char, blank=0):
    """CTC greedy decode → 车牌号字符串"""
    _, max_indices = torch.max(log_probs, dim=2)
    raw = []
    prev = blank
    for t in range(max_indices.size(0)):
        idx = max_indices[t, 0].item()
        if idx != prev and idx != blank:
            raw.append(idx_to_char[idx])
        prev = idx
    return ''.join(raw)

def validate_plate(plate_str):
    """中国车牌格式校验"""
    import re
    # 标准7位蓝牌/黄牌: 京A12345
    # 新能源8位绿牌: 京AD12345
    pattern = r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤川青藏琼宁][A-HJ-NP-Z][A-HJ-NP-Z0-9]{4,6}$'
    return bool(re.match(pattern, plate_str))
```

---

## 训练指南

### 第1步：环境
```bash
conda create -n lpr python=3.10
conda activate lpr
pip install ultralytics torch torchvision opencv-python numpy tqdm
```

### 第2步：数据准备
1. 下载 CCPD2019（约 35 万张）或 CCPD2020（新能源绿牌）
2. 运行转换脚本 → 生成 YOLO 格式 labels
3. 按 8:1:1 划分 train/val/test
4. 创建 `ccpd.yaml`:
```yaml
path: ./CCPD
train: images/train
val: images/val
test: images/test
names: {0: plate}
```

### 第3步：训练 YOLOv8 检测器
```bash
# 从预训练权重开始，冻结 backbone 前10层
yolo detect train model=yolov8n.pt data=ccpd.yaml epochs=100 imgsz=640 \
    batch=32 lr0=0.01 freeze=10
```

### 第4步：训练 LPRNet 识别
```python
# 损失函数
ctc_loss = nn.CTCLoss(blank=0, zero_infinity=True)
# 字符集: 0=blank, 1-31=省份, 32-57=字母, 58-67=数字
# 训练循环
for imgs, targets, lengths in dataloader:
    log_probs = model(imgs)  # (T, N, C)
    input_lengths = torch.full((N,), T, dtype=torch.long)
    loss = ctc_loss(log_probs, targets, input_lengths, target_lengths)
    loss.backward()
```

### 第5步：端到端评估
```bash
# 在 CCPD test 子集上评估
python eval.py --detector best.pt --recognizer lprnet.pth --dataset ccpd/test
# 指标: 检测 mAP + 字符准确率 + 端到端识别率
```

---

## 部署方案

| 平台 | 方案 | 推理速度 |
|------|------|---------|
| NVIDIA GPU | TensorRT FP16 | ~5ms |
| Jetson Orin NX | TensorRT INT8 | ~10ms |
| 瑞芯微 RK3588 | RKNN 量化 | ~15ms |
| CPU (i7) | ONNX Runtime | ~30ms |
| 海思 Hi3559A | NNIE 专用加速 | ~20ms |

---

## 数据集

| 数据集 | 样本量 | 类型 | 来源 |
|--------|--------|------|------|
| CCPD2019 | ~35万 | 蓝牌 | [GitHub](https://github.com/detectRecog/CCPD) |
| CCPD2020 | ~10万 | 绿牌(新能源) | 同上 |
| CLPD | 1200视频帧 | 连续帧 | 学术论文 |
| OpenALPR Benchmark | 多国 | 北美/欧洲 | [openalpr.com](https://www.openalpr.com) |

---

## 性能 Benchmark

| 指标 | 优秀 | 良好 | 达标 |
|------|------|------|------|
| 检测 mAP@0.5 | >98% | >95% | >90% |
| 字符准确率 | >98% | >95% | >92% |
| 端到端识别率 | >97% | >93% | >88% |
| 推理 FPS (GPU) | >100 | >60 | >30 |
| 推理 FPS (Edge) | >30 | >20 | >15 |

---

## 系统难点与解决方案

| 难点 | 方案 |
|------|------|
| 夜间/雨天画质差 | CLAHE 自适应直方图均衡化 + Zero-DCE 暗光增强预处理 |
| 小车牌检测漏 (远距) | 双阶段：先检测车辆 ROI → 再检测车牌 |
| 新能源8位绿牌 | CCPD2020 微调，扩展字符集 68→78 类 |
| 视频流单帧误识 | ByteTrack 跟踪 + 滑动窗口投票取众数 |
| 遮挡导致字符缺失 | 后处理正则校验 + 省份编码规则约束 |
| 多类型车牌混杂 | 多分类头设计（蓝/绿/黄/白/警/军/港澳） |

---

## 简历包装核心关键词

- YOLOv8 目标检测 + LPRNet 字符识别 (CTC Loss)
- CCPD 35万数据集训练，包含旋转/遮挡/模糊/夜间场景
- 四点透视变换矫正倾斜车牌
- ByteTrack 多帧跟踪去噪，单帧误识率降低 60%+
- TensorRT/RKNN 嵌入式部署，Jetson Orin NX 实时推理 30+ FPS
- 支持蓝牌/绿牌/黄牌/警牌/军牌/港澳牌等全类型
- 端到端识别准确率 【填写实际值】
