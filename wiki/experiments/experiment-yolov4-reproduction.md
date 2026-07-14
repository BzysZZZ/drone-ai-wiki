# YOLOv4 完整复现

> 单文件 PyTorch 教学实现：CSPDarknet-53、Mish、SPP、双向 PAN、Mosaic、CIoU、训练、VOC mAP 评估、NMS 和推理全部包含在本页源码中。

## 相对 YOLOv3 的关键变化

| 部分 | YOLOv3 | YOLOv4 |
|---|---|---|
| Backbone | Darknet-53 | CSPDarknet-53 |
| Activation | LeakyReLU | Mish |
| 高层上下文 | 普通卷积 | 5/9/13 SPP |
| 特征融合 | 单向 FPN | 自顶向下 + 自底向上 PAN |
| Box loss | 中心 BCE + 宽高 MSE | CIoU |
| 主要增强 | HSV、翻转 | Mosaic、HSV、翻转 |

CSP 将通道分为主分支和短路分支，只让主分支经过残差堆叠，再拼接融合。它减少重复梯度信息，同时保留稳定的跨层梯度路径。

SPP 对最高层特征并联执行 5×5、9×9、13×13 最大池化，stride 都为 1，因此空间尺寸不变，但同一位置获得不同范围的上下文。PAN 在 FPN 自顶向下之后再自底向上传递定位信息。

CIoU 同时考虑：

```text
CIoU = IoU - center_distance / enclosing_diagonal - alpha * aspect_ratio_penalty
```

即使两个框没有交集，中心距离仍能提供优化方向；宽高比惩罚帮助预测框形状接近真实框。

## 直接运行

```bash
pip install torch numpy Pillow
python yolov4_reproduction.py
```

无参数运行完全离线的 inspect。真实训练命令：

```bash
python yolov4_reproduction.py train \
  --dataset-format yolo \
  --images dataset/images \
  --labels dataset/labels \
  --classes dataset/classes.txt \
  --epochs 100 \
  --output-dir runs/yolov4

python yolov4_reproduction.py eval \
  --dataset-format yolo \
  --images dataset/images \
  --labels dataset/labels \
  --classes dataset/classes.txt \
  --checkpoint runs/yolov4/best.pt

python yolov4_reproduction.py detect \
  --checkpoint runs/yolov4/best.pt \
  --image demo.jpg \
  --output result.jpg

python yolov4_reproduction.py smoke --output-dir smoke-yolov4
```

## 完整代码

下面是完整、可复制运行的单文件源码，不依赖 YOLOv3 文件或知识库内部模块。

<!-- include-code: experiments/yolo_classics/yolov4_reproduction.py -->

## 关键代码解读

### 1. CSP 的张量流

`CSPStage.forward()` 先下采样，再产生 `short` 与 `main` 两条同通道分支。只有 `main` 经过残差堆叠；两条分支在通道维拼接后用 1×1 卷积融合。这里的拼接维度必须是 `dim=1`，因为 PyTorch NCHW 的第 1 维是通道。

### 2. SPP 为什么不改变分辨率

池化核分别为 5、9、13，padding 分别为 2、4、6，stride 为 1。因此池化前后 H/W 相同，可以直接在通道维与原特征拼接；拼接后通道扩大四倍，再由 `spp_post` 压回检测路径需要的通道数。

### 3. PAN 为什么有两次融合

第一次从大尺度语义特征上采样，帮助细网格识别目标；第二次从小尺度定位特征下采样，把边缘与位置线索重新送回粗网格。代码中的 `small_down` 和 `medium_down` 就是自底向上路径。

### 4. Mosaic 如何同步边框

`mosaic_augment()` 对每张源图记录目标画布区域和源图裁剪区域。边框先从归一化 xywh 转成源图像素 xyxy，再乘缩放、加平移、裁剪到画布边界，过滤宽高不足 2 像素的框，最后重新归一化。

### 5. CIoU 损失的坐标恢复

网络预测和监督张量都先恢复为当前尺度的真实像素 xywh，再转为 xyxy 计算 CIoU。若直接对 `tx/ty/tw/th` 计算 IoU，坐标含义不同，结果没有几何意义。

### 6. 标签平滑

正类别目标从 1 调低，负类别从 0 稍微抬高，降低模型对训练标签的过度确信。`label_smoothing` 只作用于正样本位置的分类项，不作用于边框和目标性。

## 公平对比 YOLOv3

对比两个版本时必须保持数据划分、输入尺寸、类别顺序、训练轮数、batch、评价阈值和随机种子一致。Mosaic 是 YOLOv4 的算法组成部分；若要单独衡量结构收益，应额外做关闭增强的消融实验，而不是把不同训练配置的结果直接归因于网络结构。

## 常见问题

- **PAN 拼接失败**：检查相邻特征是否先通过 stride=2 下采样或 nearest 上采样到相同 H/W。
- **Mosaic 框越界**：裁剪必须发生在画布像素坐标中，最后才能归一化。
- **CIoU 为 NaN**：宽高必须 clamp 为正，分母和包围框对角线必须加 epsilon。
- **训练前期 objectness 很高**：大量网格是负样本，需观察分项损失，不要只看 total。
- **复制后无法运行**：确认只需要 `torch`、`numpy`、`Pillow`，脚本不应导入任何仓库路径。

## 验证范围

测试覆盖相同框 CIoU=1、固定中心 Mosaic、三尺度形状、有限 CIoU 损失与梯度、无参数 CLI，以及复制到空目录后的训练、保存、重载和推理闭环。
