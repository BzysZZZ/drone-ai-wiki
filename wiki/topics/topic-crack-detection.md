# 无人机道路裂缝检测

> **类型**: topic
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **来源**: [[raw/project-crack-detection.md]]

## 摘要
无人机航拍高分辨率图像 → SAHI 切片推理 (1024×1024 sliding window, 20% overlap) → YOLOv8/SegFormer 裂缝检测 → 裂缝量化（长度/宽度/严重等级/GB/T分级）。核心创新：SAHI 解决高分辨率航拍中小裂缝易丢失的难题，配合 USSC-YOLO 的 Swin Transformer 注意力增强细长裂缝检测。

---

## 🛠️ 环境配置

```bash
# 1. 创建环境
conda create -n crack-det python=3.10 -y
conda activate crack-det

# 2. PyTorch
pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu118

# 3. 核心依赖
pip install ultralytics opencv-python-headless numpy shapely supervision

# 4. SAHI 切片推理
pip install sahi

# 5. 图像处理 & 量化
pip install scikit-image scipy matplotlib opencv-contrib-python-headless

# 6. GIS 工具（可选）
pip install gdal rasterio
```

### RDD2022 数据集下载

```bash
# RDD2022: 全球道路病害数据集 (Japan, India, Czech, Norway, China, USA)
# 下载地址: https://doi.org/10.48550/arXiv.2207.08708
# 或用 Roboflow: https://universe.roboflow.com/
```

---

## 💻 核心代码

### 1. SAHI 切片推理（手工实现 + 库版本）

```python
import cv2
import numpy as np
import torch
from ultralytics import YOLO

class SlidingWindowInference:
    """手工实现 SAHI 切片推理（理解原理用）"""
    
    def __init__(self, model, window_size=1024, overlap_ratio=0.2, device='cuda'):
        self.model = model
        self.window_size = window_size
        self.overlap_ratio = overlap_ratio
        self.stride = int(window_size * (1 - overlap_ratio))
        self.device = torch.device(device) if torch.cuda.is_available() else torch.device('cpu')
    
    def __call__(self, image, conf_thresh=0.25, iou_thresh=0.45):
        h, w = image.shape[:2]
        all_boxes = []
        
        # 计算切片位置
        y_positions = list(range(0, h, self.stride))
        x_positions = list(range(0, w, self.stride))
        
        for y0 in y_positions:
            for x0 in x_positions:
                # 边界处理
                y0 = min(y0, h - self.window_size) if y0 + self.window_size > h else y0
                x0 = min(x0, w - self.window_size) if x0 + self.window_size > w else x0
                y1 = y0 + self.window_size
                x1 = x0 + self.window_size
                
                # 裁切片
                crop = image[y0:y1, x0:x1]
                
                # 推理
                results = self.model(crop, conf=conf_thresh, iou=iou_thresh, verbose=False)[0]
                
                # 坐标映射回原图
                for box in results.boxes:
                    bx1, by1, bx2, by2 = box.xyxy[0].cpu().numpy()
                    bx1 += x0; by1 += y0
                    bx2 += x0; by2 += y0
                    all_boxes.append({
                        'bbox': [bx1, by1, bx2, by2],
                        'conf': float(box.conf[0]),
                        'cls': int(box.cls[0]),
                    })
        
        # NMS 合并重叠检测
        all_boxes = self._slice_nms(all_boxes, iou_thresh)
        
        return all_boxes
    
    def _slice_nms(self, boxes, iou_thresh):
        """对切片推理结果做 NMS"""
        if not boxes:
            return boxes
        
        import torch
        
        bboxes = torch.tensor([b['bbox'] for b in boxes])
        scores = torch.tensor([b['conf'] for b in boxes])
        
        # IoU 计算
        x1 = bboxes[:, 0]; y1 = bboxes[:, 1]
        x2 = bboxes[:, 2]; y2 = bboxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        
        _, order = scores.sort(descending=True)
        keep = []
        
        while order.numel() > 0:
            if order.numel() == 1:
                keep.append(order.item())
                break
            i = order[0]
            keep.append(i.item())
            
            xx1 = torch.max(x1[i], x1[order[1:]])
            yy1 = torch.max(y1[i], y1[order[1:]])
            xx2 = torch.min(x2[i], x2[order[1:]])
            yy2 = torch.min(y2[i], y2[order[1:]])
            
            inter = (xx2 - xx1).clamp(0) * (yy2 - yy1).clamp(0)
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            
            remaining = (iou < iou_thresh).nonzero(as_tuple=True)[0]
            order = order[remaining + 1]
        
        return [boxes[k] for k in keep]


# ========== SAHI 库版本（推荐生产使用）==========
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

def sahi_inference(image_path, model_path, conf=0.3):
    """使用 SAHI 库进行切片推理"""
    detection_model = AutoDetectionModel.from_pretrained(
        model_type='yolov8',
        model_path=model_path,
        confidence_threshold=conf,
        device='cuda',
    )
    
    result = get_sliced_prediction(
        image=image_path,
        detection_model=detection_model,
        slice_height=1024,
        slice_width=1024,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
        postprocess_type='NMS',     # NMS 或 NMM
        postprocess_match_metric='IOS',  # IOS 比 IoU 更适合裂缝
        postprocess_match_threshold=0.5,
    )
    
    return result
```

### 2. 裂缝量化后处理

```python
import cv2
import numpy as np
from skimage import morphology, measure

class CrackQuantifier:
    """裂缝量化工具：骨架提取 → 长度/宽度/等级"""
    
    # JTG 5210-2018 公路技术状况评定标准
    SEVERITY_LEVELS = {
        '轻微': (0, 3),      # < 3mm
        '中等': (3, 10),     # 3-10mm
        '严重': (10, 20),    # 10-20mm
        '危险': (20, float('inf')),  # > 20mm
    }
    
    def __init__(self, gsd_mm_per_pixel=2.0):
        """
        Args:
            gsd_mm_per_pixel: 地面采样距离 (mm/pixel)
            GSD = (飞行高度 × 像元尺寸) / 焦距
        """
        self.gsd = gsd_mm_per_pixel
    
    def quantify(self, mask):
        """
        输入: 裂缝二值 mask (H, W) uint8
        输出: {length_mm, avg_width_mm, max_width_mm, severity, skeleton}
        """
        # 1. 骨架提取
        skeleton = morphology.skeletonize(mask > 0)
        
        # 2. 裂缝长度 (骨架像素数 × GSD)
        skeleton_pixels = np.sum(skeleton)
        length_mm = skeleton_pixels * self.gsd
        
        # 3. 裂缝宽度 (面积 / 骨架长度)
        crack_area_pixels = np.sum(mask > 0)
        # 膨胀 mask 获取宽度
        avg_width_mm = (crack_area_pixels / (skeleton_pixels + 1e-6)) * self.gsd
        
        # 4. 最大宽度（沿骨架法线方向）
        max_width_mm = self._estimate_max_width(mask, skeleton)
        
        # 5. 严重等级
        severity = self._classify_severity(max_width_mm)
        
        return {
            'length_mm': round(length_mm, 1),
            'length_m': round(length_mm / 1000, 2),
            'avg_width_mm': round(avg_width_mm, 1),
            'max_width_mm': round(max_width_mm, 1),
            'severity': severity,
            'area_mm2': round(crack_area_pixels * self.gsd * self.gsd, 1),
        }
    
    def _estimate_max_width(self, mask, skeleton):
        """估算裂缝最大宽度 — 距离变换法"""
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
        max_dist = dist[skeleton > 0].max()
        return max_dist * 2 * self.gsd  # ×2 因为是单边距离
    
    def _classify_severity(self, width_mm):
        for level, (lo, hi) in self.SEVERITY_LEVELS.items():
            if lo <= width_mm < hi:
                return level
        return '未知'
    
    def visualize(self, mask, results, save_path=None):
        """生成量化报告图"""
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        axes[0].imshow(mask, cmap='gray')
        axes[0].set_title('原始 Mask')
        
        skeleton = morphology.skeletonize(mask > 0)
        axes[1].imshow(skeleton, cmap='hot')
        axes[1].set_title(f'骨架 (长度: {results["length_m"]:.2f}m)')
        
        # 裂缝分级染色
        colored = np.zeros((*mask.shape, 3), dtype=np.uint8)
        colored[mask > 0] = {
            '轻微': (0, 255, 0),   # 绿
            '中等': (255, 255, 0),  # 黄
            '严重': (255, 165, 0),  # 橙
            '危险': (255, 0, 0),    # 红
        }.get(results['severity'], (128, 128, 128))
        axes[2].imshow(colored)
        axes[2].set_title(f'等级: {results["severity"]} ({results["max_width_mm"]:.1f}mm)')
        
        for ax in axes:
            ax.axis('off')
        
        plt.suptitle(f'裂缝量化报告 | GSD={self.gsd}mm/px', fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.show()
```

### 3. GSD 坐标映射

```python
import numpy as np

def pixel_to_gps(pixel_x, pixel_y, img_width, img_height,
                 drone_lat, drone_lon, drone_alt, drone_yaw,
                 cam_hfov=62.2, cam_focal_mm=4.5, sensor_width_mm=6.2):
    """
    像素坐标 → GPS 坐标（经纬度）
    
    Args:
        cam_hfov: 相机水平视场角（DJI Mavic 3 = 84°, Phantom 4 = 94°）
        cam_focal_mm: 焦距 (mm)
        sensor_width_mm: 传感器宽度 (mm)
    """
    # 1. 计算 GSD
    gsd_m_per_pixel = (drone_alt * sensor_width_mm) / (cam_focal_mm * img_width)
    
    # 2. 像素 → 局部坐标系 (NED)
    # 图像中心为原点
    dx = (pixel_x - img_width / 2) * gsd_m_per_pixel
    dy = (pixel_y - img_height / 2) * gsd_m_per_pixel
    
    # 3. 旋转变换 (yaw 角)
    yaw_rad = np.radians(drone_yaw)
    dn = dx * np.cos(yaw_rad) - dy * np.sin(yaw_rad)
    de = dx * np.sin(yaw_rad) + dy * np.cos(yaw_rad)
    
    # 4. NED → GPS
    # 纬度: 1° ≈ 111320m
    # 经度: 1° ≈ 111320m × cos(lat)
    meters_per_deg_lat = 111320
    meters_per_deg_lon = 111320 * np.cos(np.radians(drone_lat))
    
    target_lat = drone_lat + dn / meters_per_deg_lat
    target_lon = drone_lon + de / meters_per_deg_lon
    
    return target_lat, target_lon


# 使用示例
# gps_lat, gps_lon = pixel_to_gps(
#     pixel_x=2000, pixel_y=1500,
#     img_width=5472, img_height=3648,
#     drone_lat=30.2741, drone_lon=120.1551,
#     drone_alt=50, drone_yaw=90
# )
# print(f"裂缝GPS坐标: ({gps_lat:.6f}, {gps_lon:.6f})")
```

### 4. 完整无人机巡检 Pipeline

```python
class DroneCrackInspectionSystem:
    """无人机道路裂缝巡检全 Pipeline"""
    
    def __init__(self, model_path, gsd_mm_per_pixel=2.0):
        self.detector = YOLO(model_path)  # YOLOv8 裂缝检测模型
        self.slice_infer = SlidingWindowInference(
            self.detector, window_size=1024, overlap_ratio=0.2
        )
        self.quantifier = CrackQuantifier(gsd_mm_per_pixel=gsd_mm_per_pixel)
    
    def process_image(self, image_path):
        """处理单张航拍图片"""
        img = cv2.imread(image_path)
        h, w = img.shape[:2]
        print(f"处理图片: {image_path} ({w}×{h})")
        
        # 1. SAHI 切片推理
        print("  [1/4] SAHI 切片推理...")
        detections = self.slice_infer(img)
        print(f"  检测到 {len(detections)} 个裂缝候选")
        
        # 2. 生成裂缝 mask（可选：用 SegFormer 替代）
        mask = np.zeros((h, w), dtype=np.uint8)
        for det in detections:
            x1, y1, x2, y2 = map(int, det['bbox'])
            # YOLO bbox → 粗略 mask
            mask[y1:y2, x1:x2] = 255
        
        # 3. 裂缝量化
        print("  [2/4] 裂缝量化...")
        results = self.quantifier.quantify(mask)
        print(f"  长度: {results['length_m']}m, 最大宽度: {results['max_width_mm']:.1f}mm")
        print(f"  严重等级: {results['severity']}")
        
        # 4. 可视化
        print("  [3/4] 生成报告...")
        self.quantifier.visualize(mask, results, save_path='crack_report.png')
        
        # 5. GPS 坐标（如果有无人机数据）
        # gps = pixel_to_gps(...)
        
        return {
            'detections': detections,
            'quantification': results,
            'total_cracks': len(detections),
        }
    
    def batch_process(self, image_dir):
        """批量处理航拍图像"""
        from pathlib import Path
        
        image_exts = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
        images = [p for p in Path(image_dir).glob('*') if p.suffix.lower() in image_exts]
        images.sort()
        
        reports = []
        for img_path in images:
            report = self.process_image(str(img_path))
            reports.append(report)
        
        # 汇总统计
        total_cracks = sum(r['total_cracks'] for r in reports)
        severities = [r['quantification']['severity'] for r in reports if r['total_cracks'] > 0]
        
        print(f"\n=== 巡检汇总 ===")
        print(f"图片数: {len(images)}")
        print(f"总裂缝数: {total_cracks}")
        print(f"严重裂缝: {severities.count('严重') + severities.count('危险')}")
        
        return reports


# ========== 快速使用 ==========
if __name__ == '__main__':
    system = DroneCrackInspectionSystem(
        model_path='runs/detect/train/weights/best.pt',
        gsd_mm_per_pixel=2.5,  # 根据飞行高度调整
    )
    
    # 单张处理
    result = system.process_image('drone_image_001.jpg')
    
    # 或批量处理整个文件夹
    # reports = system.batch_process('./drone_images/')
```

### 5. 训练命令

```bash
# === YOLOv8 裂缝检测训练 ===
# 关键: 用高分辨率 (1024) 训练，保留裂缝细节
yolo detect train \
    model=yolov8m.pt \
    data=crack.yaml \
    epochs=200 \
    imgsz=1024 \
    batch=8 \
    lr0=0.001 \
    cos_lr=True \
    augment=True \
    device=0

# 数据增强（在 crack.yaml 中配置）
# hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4
# degrees: 30 (裂缝方向敏感，旋转角度不宜太大)
# translate: 0.1, scale: 0.3
# mosaic: 0.5, mixup: 0.0 (裂缝检测不建议 mixup)
```

## 关联
- 相关概念: [[concepts/concept-object-detection]]
- 关联项目: [[topics/topic-precision-localization]]（精准定位保障巡检航线）
- 参见: [[topics/topic-ai-fundamentals-roadmap]]

## 引用来源
- [1] [[raw/project-crack-detection.md]] — 完整技术资料

## 核心论文引用

- [1] **SAHI** — Akyon et al., "Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection," ICIP 2022. [无人机大图切片推理核心]
- [2] **DeepCrack** — Zou et al., "DeepCrack: Learning Hierarchical Convolutional Features for Crack Detection," TIP 2018. [裂缝检测深度学习开山]
- [3] **CrackFormer** — Liu et al., "CrackFormer: Transformer Network for Fine-Grained Crack Detection," ICCV 2021. [Transformer裂缝检测]
- [4] **SegNet** — Badrinarayanan et al., "SegNet: A Deep Convolutional Encoder-Decoder Architecture for Image Segmentation," TPAMI 2017.
- [5] **U-Net** — Ronneberger et al., "U-Net: Convolutional Networks for Biomedical Image Segmentation," MICCAI 2015. [分割网络经典]
- [6] **Crack500** — Zhang et al., "Road Crack Detection Using Deep Convolutional Neural Network," ICIP 2016. [裂缝检测基准数据集]
- [7] **CFD Dataset** — Shi et al., "Automatic Road Crack Detection Using Random Structured Forests," IEEE TITS 2016.
- [8] **SegFormer** — Xie et al., "SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers," NeurIPS 2021.
- [9] **UAV路面检测** — Fan et al., "Road Damage Detection Using UAV Images Based on Multi-Scale Attention," IEEE TITS 2022.
- [10] **YOLOv8-Seg** — Jocher et al., "Ultralytics YOLOv8 Instance Segmentation," GitHub 2023.
- [11] **骨架提取** — Lee et al., "Building Skeleton Models via 3-D Medial Surface Axis Thinning Algorithms," CVGIP 1994. [裂缝宽度测量基础]
- [12] **GB/T裂缝等级** — 中国行业标准 GB/T 28181，路面裂缝评定标准. [工程验收指标]
- [13] **Mask R-CNN** — He et al., "Mask R-CNN," ICCV 2017. [实例分割基础]
- [14] **Transformer分割** — Cheng et al., "Masked-attention Mask Transformer for Universal Image Segmentation," CVPR 2022.

## 变更记录
- 2026-06-27: 初始创建
- 2026-06-27: 增强版，新增环境配置、SAHI手工+库双方案、裂缝量化(骨架/宽度/等级/热力图)、GSD坐标映射、完整Pipeline代码
- 2026-06-29: 补充14篇核心论文引用
