# 无人机感知系统全栈（Perception Stack）

> **类型**: topic
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: 知识库初始化（AI综合整理）
> **标签**: #感知 #深度学习 #多传感器融合

## 摘要

无人机感知系统全栈涵盖从原始传感器数据到高层语义理解的完整处理链路，包括目标检测、语义分割、深度估计、目标跟踪和场景重建五大子任务，是自主飞行的信息基础。每个子任务都有对应的 SOTA 方法和工程实践路径。

## 详情

### 感知系统架构

```
传感器层
├── RGB 相机（主摄，MIPI/USB/GigE）
├── 双目/深度相机（RealSense/ZED）
├── LiDAR（Velodyne/Livox/Ouster）
└── 红外/热成像（特殊任务）
    ↓
预处理层
├── 去畸变（cv2.undistort，径向畸变 k1/k2/k3）
├── 白平衡 / ISP
├── 时间戳同步（硬件触发 / 软件对齐）
└── 传感器标定（Kalibr，相机-IMU-LiDAR）
    ↓
感知算法层
├── 目标检测（YOLOv8 / RT-DETR / DINO）
├── 目标跟踪（ByteTrack / BoT-SORT）
├── 语义/实例分割（SAM / Mask2Former / SegFormer）
├── 深度估计（DepthAnything v2 / Metric3D v2）
├── 3D 目标检测（BEVFusion / BEV感知）
└── 场景重建（NeRF / 3DGS / MVS）
    ↓
融合输出层
├── 目标列表（位置/类别/速度/置信度）
├── 语义/实例地图
└── 深度图 / 点云 / 稠密地图
```

### 核心任务详解

#### 1. 目标检测 → [[concepts/concept-object-detection]]

无人机场景核心挑战：

| 挑战 | 原因 | 解决方案 |
|------|------|---------|
| 小目标检测 | 飞行高度导致目标像素面积极小 | SAHI 切片推理 + P2 检测头 |
| 旋转目标 | 航拍视角物体有任意方向 | OBB（旋转框）检测，YOLOv8-OBB |
| 实时性 | 嵌入式板卡算力有限 | TensorRT INT8 量化 + 剪枝 |
| 密集目标 | 人群/车辆密集堆叠 | NMS 替代方案（Soft-NMS / NMS-Free） |

**SAHI 切片推理流程**：

```python
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

model = AutoDetectionModel.from_pretrained(
    model_type='yolov8',
    model_path='yolov8n.pt',
    confidence_threshold=0.25,
    device='cuda:0',
)

result = get_sliced_prediction(
    "aerial_image.jpg",
    model,
    slice_height=640,
    slice_width=640,
    overlap_height_ratio=0.2,
    overlap_width_ratio=0.2,
)
result.export_visuals(export_dir="output/")
```

#### 2. 多目标跟踪（MOT）

| 算法 | 论文 | 特点 | HOTA(↑) |
|------|------|------|---------|
| SORT | Bewley et al. 2016 | 经典卡尔曼+匈牙利，极简 | ~60 |
| DeepSORT | Wojke et al. 2017 | 引入 ReID 外观特征 | ~63 |
| ByteTrack | Zhang et al. 2022 | 利用低置信度框防丢失 | ~77 |
| StrongSORT | Du et al. 2022 | EMA外观+NSA卡尔曼 | ~79 |
| BoT-SORT | Aharon et al. 2022 | 相机运动补偿+外观融合 | ~80 |
| OC-SORT | Cao et al. 2022 | 处理遮挡和非线性运动 | ~76 |

评估指标：**HOTA**（检测×关联调和均值，最综合），MOTA，IDF1

**ByteTrack 核心逻辑**：

```python
# 低置信度框也参与二次匹配，减少 ID Switch
high_det = detections[scores > 0.5]
low_det  = detections[(scores > 0.1) & (scores <= 0.5)]

# 第一轮：高置信度框匹配激活轨迹
matches1, unmatched_tracks, unmatched_dets = associate(tracks, high_det)

# 第二轮：低置信度框匹配上轮未匹配轨迹（防丢失）
matches2, lost_tracks, _ = associate(unmatched_tracks, low_det)
```

#### 3. 语义/实例分割

```
FCN（2015）→ U-Net（2015）→ DeepLabV3+（2018）
    → Mask RCNN（2017）→ SegFormer（2021）
    → SAM（2023）→ SAM2（2024）→ Mask2Former（2022）
```

| 模型 | 类型 | 参数量 | 实时性（A100） | 无人机推荐场景 |
|------|------|--------|--------------|--------------|
| SegFormer-B0 | 语义分割 | 3.7M | 60+ FPS | 边缘轻量化 |
| SegFormer-B5 | 语义分割 | 82M | ~15 FPS | 高精度地物 |
| SAM-B | 实例分割 | 94M | 交互式 | 标注辅助 |
| Mask2Former | 全景分割 | 44M | 15 FPS | 综合场景 |

**SegFormer 无人机裂缝分割**（参见 [[topics/topic-crack-detection]]）：

```python
from transformers import SegformerForSemanticSegmentation
model = SegformerForSemanticSegmentation.from_pretrained(
    "nvidia/mit-b2",
    num_labels=2,   # 裂缝 / 背景
    ignore_mismatched_sizes=True,
)
```

#### 4. 深度估计

| 类型 | 代表模型 | 绝对尺度 | 泛化性 | 推荐场景 |
|------|----------|---------|-------|---------|
| 单目相对深度 | MiDaS v3, DPT | ❌ | 强 | 定性避障 |
| 单目度量深度 | Metric3D v2, UniDepth | ✅ | 强 | 定量测量 |
| 双目深度 | RAFT-Stereo, IGEV | ✅ | 弱（需标定） | 近距离精准 |
| 自监督单目 | Monodepth2, SC-SfMLearner | ❌ | 中 | 无标注训练 |

**DepthAnything v2 推理**：

```python
from transformers import pipeline
depth_estimator = pipeline("depth-estimation",
                           model="depth-anything/Depth-Anything-V2-Small-hf")
result = depth_estimator("aerial.jpg")
depth_map = result["depth"]  # PIL Image
```

#### 5. 场景重建

| 方法 | 原理 | 训练时间 | 渲染速度 | 几何精度 |
|------|------|---------|---------|---------|
| NeRF（原始） | 隐式神经场 | 数小时 | 慢（秒级/帧） | 高 |
| Instant-NGP | Hash编码NeRF | 分钟级 | 中 | 高 |
| 3DGS | 3D高斯点渲染 | 30min | 实时 100+FPS | 中 |
| SuGaR | 3DGS+Mesh提取 | 1h | 实时 | 高（带网格） |
| 2DGS | 2D高斯平面 | 30min | 实时 | 高（薄表面） |

**无人机航拍重建推荐流程**：

```bash
# 1. COLMAP 位姿估计
colmap automatic_reconstructor \
    --workspace_path ./colmap_ws \
    --image_path ./images

# 2. 转换为 3DGS 输入格式
python convert.py -s ./colmap_ws --skip_matching

# 3. 训练 3DGS
python train.py -s ./colmap_ws -m ./output --iterations 30000
```

### 感知-规划接口

感知输出需转换为规划可用格式：

```python
import numpy as np
import cv2

def pixel_to_world(u, v, depth, K, T_cam_world):
    """像素坐标 → 世界坐标"""
    # 相机内参反投影
    fx, fy, cx, cy = K[0,0], K[1,1], K[0,2], K[1,2]
    x_cam = (u - cx) * depth / fx
    y_cam = (v - cy) * depth / fy
    z_cam = depth
    
    p_cam = np.array([x_cam, y_cam, z_cam, 1.0])
    
    # 坐标变换：相机 → 世界
    p_world = T_cam_world @ p_cam
    return p_world[:3]

# 使用示例
bbox_center_u, bbox_center_v = 320, 240
depth_value = depth_map[bbox_center_v, bbox_center_u]
world_pos = pixel_to_world(bbox_center_u, bbox_center_v,
                           depth_value, camera_K, T_cam_to_world)
```

### 主流开源感知工具链

| 工具 | 功能 | GitHub Stars | 推荐度 |
|------|------|-------------|-------|
| Ultralytics YOLOv8/v11 | 检测/分割/跟踪/OBB 一体化 | 35k+ | ⭐⭐⭐⭐⭐ |
| MMDetection 3.x | 检测算法研究框架 | 28k+ | ⭐⭐⭐⭐ |
| SAHI | 大图切片推理，小目标利器 | 3k+ | ⭐⭐⭐⭐⭐ |
| supervision（Roboflow） | 后处理/可视化/标注工具 | 23k+ | ⭐⭐⭐⭐ |
| DepthAnything v2 | 单目深度估计 | 7k+ | ⭐⭐⭐⭐⭐ |
| gaussian-splatting | 官方 3DGS 实现 | 12k+ | ⭐⭐⭐⭐ |
| SAM2 | 视频/图像分割 | 11k+ | ⭐⭐⭐⭐ |

### 无人机感知系统性能基准（Jetson Orin NX 16G）

| 任务 | 模型 | 精度指标 | 推理速度 | 功耗 |
|------|------|---------|---------|------|
| 目标检测 | YOLOv8n (TRT FP16) | mAP50 37.3 | 80 FPS | ~8W |
| 目标检测 | YOLOv8m (TRT FP16) | mAP50 50.2 | 35 FPS | ~12W |
| 语义分割 | SegFormer-B0 (TRT) | mIoU 42.2 | 45 FPS | ~9W |
| 深度估计 | DPT-Hybrid (TRT) | — | 18 FPS | ~15W |
| 目标跟踪 | ByteTrack (CPU) | — | 250Hz | ~2W |

## 关联
- 相关概念: [[concepts/concept-object-detection]], [[concepts/concept-multi-sensor-fusion]], [[concepts/method-model-deployment]]
- 相关数据集: [[entities/dataset-visdrone]], [[entities/dataset-dota]]
- 相关主题: [[topics/roadmap-drone-ai-engineer]], [[topics/topic-crack-detection]], [[topics/topic-illegal-parking-system]]

## 引用来源

### 目标检测
- [1] Redmon, J., & Farhadi, A. (2018). **YOLOv3: An Incremental Improvement**. arXiv:1804.02767. — YOLO 系列奠基
- [2] Bochkovskiy, A., Wang, C. Y., & Liao, H. Y. M. (2020). **YOLOv4: Optimal Speed and Accuracy of Object Detection**. arXiv:2004.10934. — Mosaic增强、CIoU Loss
- [3] Akyon, F. C., et al. (2022). **Slicing Aided Hyper Inference and Fine-Tuning for Small Object Detection**. ICIP 2022. — SAHI 小目标切片推理
- [4] Zhu, X., et al. (2021). **Deformable DETR: Deformable Transformers for End-to-End Object Detection**. ICLR 2021. — 可变形注意力高效检测

### 目标跟踪
- [5] Bewley, A., et al. (2016). **Simple Online and Realtime Tracking**. ICIP 2016. — SORT 开篇之作
- [6] Wojke, N., et al. (2017). **Simple Online and Realtime Tracking with a Deep Association Metric**. ICASSP 2017. — DeepSORT，引入外观特征
- [7] Zhang, Y., et al. (2022). **ByteTrack: Multi-Object Tracking by Associating Every Detection Box**. ECCV 2022. — ByteTrack，低置信度框二次匹配
- [8] Cao, J., et al. (2023). **Observation-Centric SORT: Rethinking SORT for Robust Multi-Object Tracking**. CVPR 2023. — OC-SORT，处理非线性运动

### 语义分割
- [9] Xie, E., et al. (2021). **SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers**. NeurIPS 2021. — 高效分割 Transformer
- [10] Cheng, B., et al. (2022). **Masked-Attention Mask Transformer for Universal Image Segmentation**. CVPR 2022. — Mask2Former，统一分割框架
- [11] Kirillov, A., et al. (2023). **Segment Anything**. ICCV 2023. — SAM，通用分割大模型

### 深度估计
- [12] Ranftl, R., et al. (2021). **Vision Transformers for Dense Prediction**. ICCV 2021. — DPT，Transformer 深度估计
- [13] Yang, L., et al. (2024). **Depth Anything V2**. NeurIPS 2024. — 最强单目深度估计基础模型
- [14] Yin, W., et al. (2023). **Metric3D: Towards Zero-shot Metric 3D Prediction from A Single Image**. ICCV 2023. — 零样本度量深度

### 场景重建
- [15] Mildenhall, B., et al. (2020). **NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis**. ECCV 2020. — NeRF 开山之作
- [16] Müller, T., et al. (2022). **Instant Neural Graphics Primitives with a Multiresolution Hash Encoding**. SIGGRAPH 2022. — Instant-NGP，分钟级训练
- [17] Kerbl, B., et al. (2023). **3D Gaussian Splatting for Real-Time Radiance Field Rendering**. SIGGRAPH 2023. — 3DGS，实时重建标志性工作
- [18] Guédon, A., & Lepetit, V. (2024). **SuGaR: Surface-Aligned Gaussian Splatting for Efficient 3D Mesh Reconstruction and High-Quality Mesh Rendering**. CVPR 2024. — 3DGS提取高质量网格

## 变更记录
- 2026-06-27: 初始创建，知识库初始化
- 2026-06-27: 大规模扩写，补充18篇论文引用、完整代码示例、性能基准表
