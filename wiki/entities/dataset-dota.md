# DOTA 数据集（遥感目标检测）

> **类型**: entity（数据集）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

DOTA（A Large-Scale Dataset for Object Detection in Aerial Images）是遥感和无人机视角目标检测最重要的基准数据集，特色是支持**旋转框（OBB）检测**，覆盖飞机、轮船、储罐、车辆等 18 类目标。

## 版本历史

| 版本 | 图像数 | 实例数 | 类别 | 特点 |
|------|--------|--------|------|------|
| DOTA-v1.0 | 2,806 | 188,282 | 15 | 原始版本 |
| DOTA-v1.5 | 2,806 | 403,318 | 16 | 增加非常小目标 |
| DOTA-v2.0 | 11,268 | 1,793,658 | 18 | 大幅扩充 |

**18 类目标**: Plane, Ship, Storage-tank, Baseball-diamond, Tennis-court, Basketball-court, Ground-track-field, Harbor, Bridge, Large-vehicle, Small-vehicle, Helicopter, Roundabout, Soccer-ball-field, Swimming-pool, Container-crane, Airport, Helipad

## 旋转框检测原理

```python
"""
DOTA 使用旋转框（OBB）标注: (cx, cy, w, h, θ)
θ: 旋转角度（相对于水平方向）

旋转框转换为多边形:
"""
import cv2
import numpy as np

def obb_to_polygon(cx, cy, w, h, theta_deg):
    """旋转框 → 4点多边形"""
    box = ((cx, cy), (w, h), theta_deg)
    pts = cv2.boxPoints(box)  # 返回4个角点
    return pts.astype(int)

def polygon_iou(poly1, poly2):
    """多边形 IoU（旋转框IoU）"""
    from shapely.geometry import Polygon
    p1 = Polygon(poly1)
    p2 = Polygon(poly2)
    if not p1.is_valid or not p2.is_valid:
        return 0.0
    intersection = p1.intersection(p2).area
    union = p1.union(p2).area
    return intersection / (union + 1e-9)

# 旋转框 NMS
def rotated_nms(boxes_obb, scores, iou_threshold=0.3):
    """旋转框非极大值抑制"""
    order = scores.argsort()[::-1]
    keep = []
    while len(order) > 0:
        i = order[0]
        keep.append(i)
        if len(order) == 1: break
        iou = np.array([polygon_iou(
            obb_to_polygon(*boxes_obb[i]),
            obb_to_polygon(*boxes_obb[j])
        ) for j in order[1:]])
        order = order[1:][iou < iou_threshold]
    return keep
```

## 数据切片策略

DOTA 图像通常为 4000×4000px，需要切片：

```python
def slice_dota_image(image, labels, slice_size=1024, overlap=0.25):
    """
    将大图切成小块，标注相应裁剪
    overlap: 重叠比例，防止边界目标丢失
    """
    H, W = image.shape[:2]
    stride = int(slice_size * (1 - overlap))
    slices = []
    
    for y in range(0, H - slice_size + stride, stride):
        for x in range(0, W - slice_size + stride, stride):
            y2 = min(y + slice_size, H)
            x2 = min(x + slice_size, W)
            y1, x1 = max(0, y2 - slice_size), max(0, x2 - slice_size)
            
            img_slice = image[y1:y2, x1:x2]
            # 筛选在切片内的标注
            slice_labels = filter_labels_in_region(labels, x1, y1, x2, y2)
            slices.append((img_slice, slice_labels, (x1, y1)))
    
    return slices
```

## SOTA 方法

| 方法 | mAP OBB | 年份 | 关键创新 |
|------|---------|------|---------|
| LSKNet | 81.85 | 2023 | 大核选择卷积 |
| OrientedRCNN | 80.87 | 2021 | 旋转RPN |
| RoI-Transformer | 76.98 | 2019 | 旋转特征对齐 |
| S²ANet | 79.42 | 2021 | 对齐卷积 |
| Oriented RepPoints | 78.19 | 2022 | 无锚旋转框 |

## 论文引用

- [1] **DOTA-v1** — Xia et al., "DOTA: A Large-Scale Dataset for Object Detection in Aerial Images," CVPR 2018.
- [2] **DOTA-v2** — Ding et al., "Object Detection in Aerial Images: A Large-Scale Benchmark and Challenges," TPAMI 2021.
- [3] **OrientedRCNN** — Xie et al., "Oriented R-CNN for Object Detection," ICCV 2021.
- [4] **RoI-Transformer** — Ding et al., "Learning RoI Transformer for Oriented Object Detection in Aerial Images," CVPR 2019.
- [5] **S²ANet** — Han et al., "Align Deep Features for Oriented Object Detection," IEEE TGRS 2021.
- [6] **LSKNet** — Li et al., "Large Selective Kernel Network for Remote Sensing Object Detection," ICCV 2023.
- [7] **MMRotate** — Zhou et al., "MMRotate: A Rotated Object Detection Benchmark Using PyTorch," ACMMM 2022.

## 关联

- 相关概念: [[concept-object-detection]]
- 相关实体: [[entities/dataset-visdrone]]
- 参见: [[topics/topic-perception-stack]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 扩写——版本历史、旋转框代码、SOTA对比、7篇论文引用
