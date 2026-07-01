# VisDrone 数据集

> **类型**: entity（数据集）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

VisDrone 是无人机视角目标检测/跟踪的最权威 Benchmark，由天津大学机器学习与数据挖掘实验室创建，涵盖 10 个子任务，是无人机 AI 算法工程师最重要的公开数据集。

## 数据集统计

| 子任务 | 训练集 | 验证集 | 测试集 | 标注类型 |
|--------|--------|--------|--------|---------|
| DET（图像检测） | 6,471 | 548 | 1,610 | bbox |
| VID（视频检测） | 56 clips | 7 clips | 16 clips | bbox+trackID |
| MOT（多目标跟踪） | 56 clips | 7 clips | 16 clips | bbox+trackID |
| SOT（单目标跟踪） | 56 clips | 7 clips | 16 clips | bbox |
| CROWD（人群计数） | 3,608 | 1,296 | 1,202 | 点标注 |

**目标类别（10类）**: pedestrian, people, bicycle, car, van, truck, tricycle, awning-tricycle, bus, motor

**主要挑战**:
- 平均目标尺寸 <50px（极小目标）
- 密集遮挡，堆叠目标
- 视角多样（高空/斜视/低空）
- 光照变化（黄昏/阴天/晴天）

## 数据集使用（YOLOv8 格式转换）

```python
"""
VisDrone 原始格式: bbox_left, bbox_top, bbox_width, bbox_height, score, category, truncation, occlusion
YOLO 格式: class_id cx cy w h（归一化）
"""
import os
import pandas as pd

def visdrone_to_yolo(anno_dir, img_dir, out_dir, img_size=(1920, 1080)):
    """批量转换 VisDrone 标注到 YOLO 格式"""
    os.makedirs(out_dir, exist_ok=True)
    H, W = img_size
    
    CATEGORY_MAP = {
        0: -1,  # ignored
        1: 0,   # pedestrian
        2: 1,   # people
        3: 2,   # bicycle
        4: 3,   # car
        5: 4,   # van
        6: 5,   # truck
        7: 6,   # tricycle
        8: 7,   # awning-tricycle
        9: 8,   # bus
        10: 9,  # motor
    }
    
    for txt_file in os.listdir(anno_dir):
        if not txt_file.endswith('.txt'): continue
        df = pd.read_csv(
            os.path.join(anno_dir, txt_file),
            header=None,
            names=['x','y','w','h','score','cat','trunc','occ']
        )
        # 过滤 ignored 和 occluded>2
        df = df[(df['cat'] != 0) & (df['occ'] <= 2)]
        
        yolo_lines = []
        for _, row in df.iterrows():
            cls = CATEGORY_MAP.get(row['cat'], -1)
            if cls < 0: continue
            cx = (row['x'] + row['w']/2) / W
            cy = (row['y'] + row['h']/2) / H
            nw = row['w'] / W
            nh = row['h'] / H
            yolo_lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
        
        out_path = os.path.join(out_dir, txt_file)
        with open(out_path, 'w') as f:
            f.write('\n'.join(yolo_lines))
    
    print(f"转换完成: {len(os.listdir(anno_dir))} 个文件")
```

## 下载地址

```bash
# 官网
https://github.com/VisDrone/VisDrone-Dataset

# 通过 Kaggle CLI
kaggle datasets download -d mhrezaei/visdrone-dataset

# 百度网盘（国内）
# 参考 github README
```

## SOTA 方法回顾

| 方法 | mAP@0.5 | 年份 | 关键技术 |
|------|---------|------|---------|
| YOLOv8+SAHI | ~52 | 2023 | 切片推理 |
| DINO-4scale | ~58 | 2022 | Transformer检测 |
| QueryDet | 57.3 | 2022 | 级联稀疏查询 |
| Stitcher | 55.6 | 2020 | 动态尺度拼接 |
| ClusDet | 43.8 | 2019 | 集群感知检测 |

## 论文引用

- [1] **VisDrone2019** — Zhu et al., "VisDrone-DET2019: The Vision Meets Drone Object Detection in Image Challenge Results," ICCV-W 2019.
- [2] **VisDrone综述** — Du et al., "Vision Meets Drones: Past, Present and Future," arXiv 2020.
- [3] **VisDrone2021** — Cao et al., "VisDrone-DET2021: The Vision Meets Drone Object Detection Challenge Results," ICCV-W 2021.
- [4] **QueryDet** — Yang et al., "QueryDet: Cascaded Sparse Query for Accelerating High-Resolution Small Object Detection," CVPR 2022.
- [5] **ClusDet** — Yang et al., "Clustered Object Detection in Aerial Images," ICCV 2019.
- [6] **Stitcher** — Chen et al., "Stitcher: Feedback-driven Data Provider for Object Detection," arXiv 2020.

## 关联

- 相关概念: [[concept-object-detection]]
- 相关实体: [[entities/dataset-dota]]
- 参见: [[topics/topic-perception-stack]], [[topics/topic-crack-detection]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 扩写——统计表格、YOLO格式转换代码、SOTA对比、下载地址、6篇论文引用
