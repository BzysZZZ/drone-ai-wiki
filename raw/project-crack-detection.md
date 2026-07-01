# 项目资料：无人机道路裂缝检测（完整版）

> **来源类型**: 技术调研 + 论文方案汇总 + 工程实践
> **采集日期**: 2026-06-27
> **项目背景**: 无人机航拍道路图像 → AI 自动检测裂缝病害，输出裂缝位置/长度/宽度/严重等级

---

## 项目概述

传统道路巡检依赖人工目视，效率低、主观性强。本系统利用 **无人机高空航拍 + SAHI 切片推理 + YOLOv8/USSC-YOLO 裂缝检测 + 后处理量化**，实现路面裂缝的自动化检测与评估。核心创新在于解决了超高分辨率航拍图中小裂缝（像素级）的检测难题。

---

## 完整 Pipeline

```
无人机航拍 (4K/8K 影像)
    ↓
图像预处理 (畸变校正、光照归一化)
    ↓
SAHI 切片 (1024×1024 滑窗, overlap=20%)
    ↓
YOLOv8/SegFormer 裂缝检测 (每切片推理)
    ↓
切片结果合并 (NMS + 坐标映射回原图)
    ↓
裂缝后处理 (连通域分析、骨架提取)
    ↓
量化输出:
  - 裂缝位置 (GPS 坐标)
  - 裂缝长度 & 平均宽度 (像素→物理)
  - 严重等级 (GB/T 规范分级)
  - 裂缝密度热力图
```

---

## 核心技术详解

### 1. SAHI 切片推理（核心创新）

**为什么需要 SAHI？**
- 无人机单张图像 4000×3000 像素以上，直接 resize 到 640×640 会让细小裂缝完全消失
- SAHI (Slicing Aided Hyper Inference) 将大图切分为可处理的小块，保留原始分辨率

```python
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

# 方案一：使用 SAHI 库（推荐）
model = AutoDetectionModel.from_pretrained(
    model_type='yolov8',
    model_path='best.pt',
    confidence_threshold=0.35,
    device='cuda:0'
)

result = get_sliced_prediction(
    image='drone_ortho_8k.jpg',
    detection_model=model,
    slice_height=1024,      # 切片尺寸
    slice_width=1024,
    overlap_height_ratio=0.2,  # 20% 重叠防止边界裂缝丢失
    overlap_width_ratio=0.2,
    postprocess_type='NMS',    # NMS 合并重叠检测
    postprocess_match_metric='IOS',  # Intersection over Slice
    postprocess_match_threshold=0.5
)

# 导出结果
result.export_visuals(export_dir='output/', file_name='crack_result')
```

**手工切片方案（用于自定义后处理）**：
```python
import cv2, numpy as np

def slice_image(img, slice_size=1024, overlap=0.2):
    """将大图切分为有重叠的小块"""
    h, w = img.shape[:2]
    stride = int(slice_size * (1 - overlap))
    slices = []
    for y in range(0, h - slice_size + 1, stride):
        for x in range(0, w - slice_size + 1, stride):
            patch = img[y:y+slice_size, x:x+slice_size]
            slices.append({"patch": patch, "offset": (x, y)})
    # 处理右边缘和下边缘（保证覆盖）
    if w % stride != 0:
        for y in range(0, h - slice_size + 1, stride):
            slices.append({"patch": img[y:y+slice_size, -slice_size:],
                          "offset": (w - slice_size, y)})
    if h % stride != 0:
        for x in range(0, w - slice_size + 1, stride):
            slices.append({"patch": img[-slice_size:, x:x+slice_size],
                          "offset": (x, h - slice_size)})
    return slices

def merge_predictions(predictions, original_shape):
    """将切片级预测映射回原图坐标"""
    merged = []
    for pred in predictions:
        ox, oy = pred["offset"]
        for box in pred["boxes"]:
            x1, y1, x2, y2 = box[:4]
            merged.append({
                "bbox": [x1+ox, y1+oy, x2+ox, y2+oy],
                "score": box[4],
                "class": box[5]
            })
    # 重叠区域 NMS
    merged = apply_nms(merged, iou_threshold=0.45)
    return merged
```

### 2. USSC-YOLO 论文方案（2024，MDPI Sensors）

论文提出针对无人机路面裂缝检测的三个改进：
- **U** 型特征融合：引入 U-Net 风格的上采样路径，融合浅层细节特征与深层语义特征
- **S** WIN Transformer 注意力：在 Neck 中嵌入 Swin Transformer 块，增强对细长裂缝的全局建模
- **S** patial Pyramid Pooling：改进 SPPF，多尺度感受野捕获不同宽度裂缝
- **C**oordinate Attention：坐标注意力机制，增强裂缝位置感知

> 论文：USSC-YOLO: Enhanced Multi-Scale Road Crack Object Detection Algorithm for UAV Image (Sensors 2024)

### 3. 语义分割方案（SegFormer）

当需要裂缝像素级轮廓时（评估宽度/面积），采用 SegFormer：
```python
from transformers import SegformerForSemanticSegmentation

model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/segformer-b0-finetuned-ade-512-512"
)
# 微调时修改分类头：背景 / 横向裂缝 / 纵向裂缝 / 网状裂缝
model.decode_head.classifier = nn.Conv2d(256, 4, kernel_size=1)
```

### 4. 裂缝后处理与量化

```python
from skimage import morphology, measure

def quantify_crack(mask, pixel_resolution=0.5):
    """
    输入: 裂缝二值 mask
    pixel_resolution: 每个像素代表的实际距离 (cm/pixel), 由无人机高度和相机参数确定
    """
    # 骨架提取 → 估算长度
    skeleton = morphology.skeletonize(mask)
    length_px = np.sum(skeleton)
    length_cm = length_px * pixel_resolution

    # 计算平均宽度
    # 宽度 = 裂缝面积 / 骨架长度
    area_px = np.sum(mask)
    width_px = area_px / (length_px + 1e-6)
    width_mm = width_px * pixel_resolution * 10

    # 严重等级评估（参考 JTG 5210-2018 公路技术状况评定标准）
    if width_mm < 3:
        grade = "轻微"
    elif width_mm < 10:
        grade = "中等"
    elif width_mm < 20:
        grade = "严重"
    else:
        grade = "危险"

    return {
        "length_cm": round(length_cm, 1),
        "width_mm": round(width_mm, 2),
        "grade": grade,
        "area_cm2": round(area_px * pixel_resolution**2, 2)
    }

def generate_heatmap(results, img_shape, grid_size=100):
    """裂缝密度热力图"""
    heatmap = np.zeros((img_shape[0]//grid_size, img_shape[1]//grid_size))
    for r in results:
        cx, cy = (r["bbox"][0]+r["bbox"][2])/2, (r["bbox"][1]+r["bbox"][3])/2
        gx, gy = int(cy//grid_size), int(cx//grid_size)
        if 0 <= gy < heatmap.shape[0] and 0 <= gx < heatmap.shape[1]:
            heatmap[gy, gx] += 1
    return heatmap
```

---

## 数据集

| 数据集 | 样本量 | 特点 | 来源 |
|--------|--------|------|------|
| Crack500 | 500 | 路面裂缝分割标注 | [GitHub](https://github.com/fyangneil/pavement-crack-detection) |
| CrackForest (CFD) | 118 | 含阴影、水渍等干扰 | 公开数据集 |
| DeepCrack | 537 | 像素级标注，包含多场景 | [GitHub](https://github.com/yhlleo/DeepCrack) |
| UAV-PDD2023 | 600+ | 无人机视角，5类路面病害 | 中国公路学会 |
| RDD2022 | 47,420 | 全球多国道路病害 | [GitHub](https://github.com/sekilab/RoadDamageDetector) |
| 自定义数据集 | 自建 | 本地路段航拍，实际场景最重要 | - |

---

## 训练指南

### YOLOv8 裂缝检测

```bash
# 1. 安装
pip install ultralytics sahi

# 2. 数据准备 (YOLO 格式)
# dataset/
# ├── images/train/*.jpg
# ├── images/val/*.jpg
# ├── labels/train/*.txt
# └── labels/val/*.txt
# 类别: 0=crack

# 3. 训练（针对小目标优化）
yolo detect train \
    model=yolov8n.pt \
    data=crack.yaml \
    epochs=200 \
    imgsz=1024 \        # 高分辨率保留裂缝细节
    batch=8 \
    lr0=0.001 \
    augment=hsv_h=0.015 hsv_s=0.7 hsv_v=0.4 \
    name=crack_detection

# 4. SAHI 推理评估
python eval_sahi.py --model best.pt --dataset test/ --slice 1024
```

### 数据增强（裂缝检测特化）

```yaml
# crack_augment.yaml
augment:
  - Rotate: {limit: 30}          # 裂缝方向多样
  - RandomBrightnessContrast: {brightness_limit: 0.2}
  - GaussNoise: {var_limit: 10}   # 模拟传感器噪声
  - MotionBlur: {blur_limit: 5}   # 模拟无人机抖动
  - CLAHE: {clip_limit: 2}         # 增强低光照对比度
  - CoarseDropout: {max_holes: 3}  # 模拟遮挡（树叶/阴影）
```

---

## 性能指标

| 指标 | 基准 | 优化后目标 |
|------|------|----------|
| 裂缝检测 mAP@0.5 | ~70% | > 85% |
| 裂缝检测 mAP@0.5:0.95 | ~40% | > 60% |
| 推理速度 (8K图+SAHI) | - | < 5s/张 |
| 长度误差 | < 15% | < 10% |
| 宽度误差 | < 20% | < 15% |
| 漏检率 (Recall) | < 80% | > 90% |

---

## 无人机平台集成

```
无人机 (DJI M300/M350 或自组)
    ↓ 航点任务 (Mission Planner / QGC)
    ↓ 定时拍照/正射影像采集
    ↓ 4G/5G 实时回传 or 落地后 SD 卡导出
    ↓
地面站/服务器
    ↓ SAHI + YOLOv8 裂缝检测
    ↓ 裂缝量化 + 热力图生成
    ↓
输出: 巡检报告 (PDF) + 裂缝 GIS 标注
```

### 坐标映射

```python
def pixel_to_gps(px, py, drone_gps, drone_alt, camera_params, heading):
    """
    图像像素坐标 → GPS 坐标
    需要: 无人机 GPS、飞行高度、相机内参、云台角度、航向角
    """
    # 相机投影矩阵
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
    # 图像坐标 → 相机坐标 → 世界坐标 → GPS
    # 使用 GSD (Ground Sample Distance) 近似
    gsd = (sensor_width * drone_alt) / (focal_length * image_width)
    # 像素偏移 → 米偏移
    dx = (px - cx) * gsd
    dy = (py - cy) * gsd
    # 航向旋转
    heading_rad = np.radians(heading)
    dn = dy * np.cos(heading_rad) - dx * np.sin(heading_rad)
    de = dy * np.sin(heading_rad) + dx * np.cos(heading_rad)
    # GPS 偏移 (1 deg lat ≈ 111320m, 1 deg lon ≈ 111320*cos(lat))
    lat_offset = dn / 111320.0
    lon_offset = de / (111320.0 * np.cos(np.radians(drone_gps[0])))
    return (drone_gps[0] + lat_offset, drone_gps[1] + lon_offset)
```

---

## 简历包装核心关键词

- 无人机高分辨率航拍图像 (4K/8K) 路面裂缝自动检测
- SAHI 切片推理：1024×1024 滑窗 + 20% 重叠 + NMS 合并
- YOLOv8 + USSC-YOLO (Swin Transformer 注意力 + 多尺度特征融合)
- SegFormer 语义分割实现裂缝像素级轮廓提取
- 骨架提取 + 连通域分析：量化裂缝长度（cm）/宽度（mm）/严重等级
- 裂缝密度热力图 + GPS 坐标映射 + GIS 系统集成
- GSD (Ground Sample Distance) 校准，像素→物理尺寸精确转换
- 数据增强：旋转/运动模糊/CLAHE/模拟遮挡，提升鲁棒性
