# YOLOv3 完整复现

> 单文件 PyTorch 教学实现：Darknet-53、FPN、锚框标签分配、三项损失、VOC/YOLO 数据读取、训练、mAP 评估、NMS 和单图推理全部包含在本页源码中。

## 结构速览

| 部分 | 实现 | 作用 |
|---|---|---|
| Backbone | Darknet-53，残差层数 1/2/8/8/4 | 提取 stride 8、16、32 特征 |
| Neck | 自顶向下 FPN | 把强语义逐级传给高分辨率特征 |
| Head | 3 个 anchor × `(5 + C)` 通道 | 每个尺度预测边框、目标性和类别 |
| Box encoding | `tx, ty, tw, th` | 中心相对网格，宽高相对 anchor |
| Postprocess | 置信度过滤 + class-aware NMS | 删除同类别重复框 |

输入为 `[B, 3, H, W]`。当 `H=W=416` 时，三个输出依次为：

```text
[B, 3*(5+C), 13, 13]
[B, 3*(5+C), 26, 26]
[B, 3*(5+C), 52, 52]
```

每个网格位置的原始预测为 `(tx, ty, tw, th, objectness, class logits...)`。解码公式是：

```text
bx = (sigmoid(tx) + grid_x) * stride
by = (sigmoid(ty) + grid_y) * stride
bw = exp(tw) * anchor_w
bh = exp(th) * anchor_h
```

标签分配会比较真实框宽高与全部 9 个 anchor 的 IoU，只把全局最佳 anchor 标为正样本。损失由中心偏移 BCE、宽高 MSE、目标性 BCE 和类别 BCE 组成。

## 直接运行

```bash
pip install torch numpy Pillow
python yolov3_reproduction.py
```

无参数运行使用 128×128 合成输入，执行前向、损失和反向传播。它不会联网，也不需要权重或数据集。默认完整模型仍使用 Darknet-53 的原始通道与深度；inspect 通过倍率缩小模型，只为快速验证代码环境。

常用命令：

```bash
# YOLO 文本标注训练
python yolov3_reproduction.py train \
  --dataset-format yolo \
  --images dataset/images \
  --labels dataset/labels \
  --classes dataset/classes.txt \
  --epochs 100 \
  --output-dir runs/yolov3

# VOC XML 评估
python yolov3_reproduction.py eval \
  --dataset-format voc \
  --images VOC/JPEGImages \
  --labels VOC/Annotations \
  --classes classes.txt \
  --checkpoint runs/yolov3/best.pt

# 单图推理
python yolov3_reproduction.py detect \
  --checkpoint runs/yolov3/best.pt \
  --image demo.jpg \
  --output result.jpg

# 不依赖数据集的训练、保存、重载、推理闭环
python yolov3_reproduction.py smoke --output-dir smoke-yolov3
```

## 完整代码

下面展示完整、可复制运行的源码，与仓库中的 Python 文件自动保持一致。

<!-- include-code: experiments/yolo_classics/yolov3_reproduction.py -->

## 关键代码解读

### 1. 为什么返回三个特征图

`Darknet53.forward()` 返回 stride 8、16、32 特征。stride 32 的单元感受野大，适合大目标；stride 8 保留更细的空间信息，更适合小目标。FPN 把 stride 32 的高层语义上采样后与低层特征拼接。

### 2. `reshape_predictions` 在做什么

卷积输出按通道存放所有 anchor 的结果。该函数将 `[B, A*(5+C), H, W]` 重排为 `[B, A, H, W, 5+C]`，使最后一维对应一个 anchor 的完整预测。`contiguous()` 保证后续 view 和索引使用连续内存。

### 3. 标签分配为什么只选一个 anchor

`build_targets()` 先把真实框宽高乘以输入尺寸，再与 9 个像素 anchor 比较宽高 IoU。全局最佳 anchor 决定尺度与 anchor 槽位。这样避免同一真实框在多个尺度被重复当作正样本。

### 4. 损失为何分开返回

`compute_yolov3_loss()` 返回 `box/objectness/classification/total`。训练时若 objectness 很快下降但 box 不下降，通常是坐标或 anchor 有误；若 classification 不下降，优先检查类别编号和类别文件顺序。

### 5. mAP 如何计算

`evaluate_detections()` 对每个类别按置信度排序预测，在每张图内用 IoU≥0.5 贪心匹配尚未匹配的真实框。累计 TP/FP 得到 PR 曲线，再通过 precision envelope 积分得到 AP，最后对有真实样本的类别求均值得到 mAP@0.5。

## 数据要求

YOLO 文本每行为：

```text
class_id center_x center_y width height
```

四个坐标必须归一化到 `[0,1]`，宽高必须大于 0。VOC 使用常规 `object/name/bndbox` XML。`classes.txt` 每行一个类别，行号就是类别编号。

## 常见问题

- **检测头通道错误**：通道必须为 `3*(5+类别数)`；类别文件变化后不能直接加载旧检测头。
- **损失出现 NaN/Inf**：检查宽高是否为 0、坐标是否重复归一化、学习率是否过大。
- **始终没有预测框**：先降低 `--confidence`，确认类别概率和 objectness 都参与最终分数。
- **显存不足**：减小 batch 或 image size；`width_mult` 主要用于学习和调试，不用于和论文精度直接比较。
- **断点不兼容**：恢复训练时类别顺序、宽度倍率和深度倍率必须与保存时一致。

## 验证范围

对应测试覆盖坐标往返、已知 IoU、逐类 NMS、三尺度形状、最佳 anchor、有限损失与梯度、VOC/YOLO 标注、完美预测 mAP=1、无参数 CLI，以及复制到空目录后的 smoke 闭环。
