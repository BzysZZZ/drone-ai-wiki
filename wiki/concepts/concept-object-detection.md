# 目标检测（Object Detection）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

目标检测是计算机视觉最核心的任务之一，旨在图像/视频中定位并分类所有目标。分为两阶段（Two-Stage）和单阶段（One-Stage）两大流派，现代工业界主流为以 YOLO 系列为代表的单阶段检测器。无人机场景面临小目标、密集目标、高速运动等特殊挑战。

## 发展脉络

### 两阶段检测器（Two-Stage）

| 算法 | 年份 | 核心贡献 | 速度（FPS） |
|------|------|---------|------------|
| R-CNN | 2014 | 区域建议 + CNN 特征 | ~0.05 |
| Fast R-CNN | 2015 | RoI Pooling，端到端 | ~0.5 |
| Faster R-CNN | 2015 | RPN 区域建议网络，全端到端 | ~7 |
| Mask R-CNN | 2017 | 实例分割扩展 | ~5 |
| Cascade R-CNN | 2018 | 级联 IoU 阈值提升精度 | ~7 |

### 单阶段检测器（One-Stage）

| 算法 | 年份 | 核心贡献 |
|------|------|---------|
| YOLO v1 | 2016 | 网格预测，实时检测 |
| SSD | 2016 | 多尺度特征图锚框 |
| RetinaNet | 2017 | Focal Loss 解决类别不平衡 |
| YOLO v3 | 2018 | FPN 多尺度，Darknet-53 |
| YOLO v4 | 2020 | CSPNet + Mosaic 增强 |
| YOLO v5 | 2020 | PyTorch 生态，工程化友好 |
| YOLO v7 | 2022 | E-ELAN 高效架构 |
| YOLO v8 | 2023 | Anchor-Free，C2f 模块 |
| YOLO v9 | 2024 | GELAN + PGI 可编程梯度信息 |
| YOLO v10 | 2024 | NMS-Free，双重分配 |
| YOLO v11 | 2024 | C3k2 模块，更高效 |

### Transformer 检测器

| 算法 | 年份 | 核心贡献 |
|------|------|---------|
| DETR | 2020 | 端到端无需 NMS，Set Loss |
| Deformable DETR | 2020 | 可变形注意力加速收敛 |
| DAB-DETR | 2022 | 动态锚框查询 |
| DN-DETR | 2022 | 降噪训练 |
| DINO | 2022 | 对比降噪，SOTA 精度 |
| RT-DETR | 2023 | 实时 Transformer 检测 |

## 核心概念深解

### Anchor 机制 vs Anchor-Free

**Anchor-Based（YOLOv5 为例）**
```
预先定义不同尺寸锚框 → 预测(dx, dy, dw, dh)偏移 → 解码为绝对坐标
优点：对不同比例目标鲁棒
缺点：需要聚类确定锚框尺寸，超参依赖数据分布
```

**Anchor-Free（YOLOv8 为例）**
```
直接预测目标中心点 + (l, t, r, b) 四边距离
优点：无需先验，泛化性更好
缺点：对密集遮挡略逊于 Anchor 方案
```

### 非极大值抑制（NMS）及其变种

```python
# 标准 NMS
def nms(boxes, scores, iou_threshold=0.45):
    indices = cv2.dnn.NMSBoxes(boxes, scores, 0.25, iou_threshold)
    return indices

# Soft-NMS（减小遮挡漏检）
# 不删除重叠框，而是按 IoU 衰减其置信度
score_i = score_i * exp(-iou^2 / sigma)
```

### 特征金字塔（FPN / PANet / BiFPN）

```
FPN：自顶向下融合高层语义 → 多尺度特征
PANet：在 FPN 基础上增加自底向上路径 → 低层定位信息上传
BiFPN（EfficientDet）：双向跨尺度连接 + 加权融合
AFPN（YOLO11）：渐进式不等尺度特征聚合
```

### IoU 系列损失函数

| 损失 | 公式 | 特点 |
|------|------|------|
| IoU Loss | 1 - IoU | 基础，不反映未重叠情况 |
| GIoU | IoU - (C-U)/C | 解决不重叠梯度消失 |
| DIoU | IoU - ρ²/c² | 加入中心点距离 |
| CIoU | DIoU - αv | 加入宽高比 |
| EIoU | CIoU改 | 独立宽高误差项 |
| SIoU | 方向+距离+形状 | YOLO社区广泛使用 |
| WIoU | 动态权重聚焦低质量样本 | 2023 SOTA |

### 小目标检测专项技术（无人机场景核心）

1. **SAHI（Sliced Inference）**：将大图切成 640×640 小块分别推理，再合并 NMS
2. **超分辨率预处理**：ESRGAN 先放大再检测
3. **多尺度训练**：随机缩放 0.5-1.5 倍
4. **动态标签分配**：TOOD / TaskAligned / VFL 让小目标获得更多正样本
5. **注意力机制**：CBAM / SE / ECA 增强关键区域响应

## 关键指标

| 指标 | 含义 | 计算方式 |
|------|------|---------|
| mAP@0.5 | IoU=0.5 时各类平均精度均值 | ΣAP / num_classes |
| mAP@0.5:0.95 | COCO 标准，IoU 0.5~0.95 均值 | COCO 标准 |
| AP_s | 小目标（<32²px）精度 | COCO 子集 |
| FPS | 推理速度 | 1000ms/latency_ms |
| Params(M) | 参数量 | 模型大小指标 |
| GFLOPs | 计算量 | 硬件适配指标 |

## 论文引用

- [1] **RCNN** — Girshick et al., "Rich Feature Hierarchies for Accurate Object Detection," CVPR 2014. [经典两阶段检测开山之作]
- [2] **Fast R-CNN** — Girshick, "Fast R-CNN," ICCV 2015. [RoI Pooling，端到端训练]
- [3] **Faster R-CNN** — Ren et al., "Faster R-CNN: Towards Real-Time Object Detection with Region Proposal Networks," NIPS 2015. [RPN网络，必读]
- [4] **YOLO v1** — Redmon et al., "You Only Look Once: Unified, Real-Time Object Detection," CVPR 2016. [单阶段检测开山之作]
- [5] **RetinaNet** — Lin et al., "Focal Loss for Dense Object Detection," ICCV 2017. [Focal Loss解决类别不均衡]
- [6] **FPN** — Lin et al., "Feature Pyramid Networks for Object Detection," CVPR 2017. [多尺度特征融合基础架构]
- [7] **YOLO v4** — Bochkovskiy et al., "YOLOv4: Optimal Speed and Accuracy of Object Detection," arXiv 2020. [大量 Tricks 系统验证]
- [8] **DETR** — Carion et al., "End-to-End Object Detection with Transformers," ECCV 2020. [Transformer检测端到端]
- [9] **Deformable DETR** — Zhu et al., "Deformable DETR," ICLR 2021. [解决DETR收敛慢问题]
- [10] **DINO** — Zhang et al., "DINO: DETR with Improved DeNoising Anchor Boxes," ICLR 2022. [Transformer检测SOTA]
- [11] **RT-DETR** — Zhao et al., "DETRs Beat YOLOs on Real-time Object Detection," CVPR 2024. [首个实时Transformer检测器]
- [12] **YOLOv9** — Wang et al., "YOLOv9: Learning What You Want to Learn Using Programmable Gradient Information," arXiv 2024.
- [13] **YOLOv10** — Wang et al., "YOLOv10: Real-Time End-to-End Object Detection," NeurIPS 2024.
- [14] **SAHI** — Akyon et al., "Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection," ICIP 2022. [无人机小目标必用]
- [15] **VisDrone Challenge** — Zhu et al., "Vision Meets Drones: Past, Present and Future," arXiv 2020. [无人机目标检测benchmark]
- [16] **WIoU** — Tong et al., "Wise-IoU: Bounding Box Regression Loss with Dynamic Focusing Mechanism," arXiv 2023.
- [17] **TOOD** — Feng et al., "TOOD: Task-aligned One-stage Object Detection," ICCV 2021. [动态标签分配]
- [18] **CBAM** — Woo et al., "CBAM: Convolutional Block Attention Module," ECCV 2018. [通道+空间注意力]

## 关联

- 相关概念: [[concept-multi-sensor-fusion]], [[concept-deep-learning-basics]], [[concept-model-evaluation]]
- 相关实体: [[entities/dataset-visdrone]], [[entities/dataset-dota]]
- 参见项目: [[topics/topic-license-plate-recognition]], [[topics/topic-crack-detection]], [[topics/topic-illegal-parking-system]]

## 变更记录

- 2026-06-27: 初始创建，基础版本
- 2026-06-29: 大幅扩写——增加发展脉络表格、Anchor对比、NMS变种、FPN系列、小目标技术、18篇论文引用
