# AI 算法工程师面试题库（AI Interview Q&A）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合整理，行业经验

## 摘要

汇集资深 AI 算法工程师面试高频题，覆盖数理基础、深度学习原理、计算机视觉、工程经验、项目实战五大类，每题附参考答案要点和答题策略。

## 数理基础类

### Q1: 解释反向传播的计算过程

```
核心考点：链式法则 + 计算图

答题要点:
1. 前向传播: 计算各节点激活值，存储中间结果
2. 计算损失: L = loss(ŷ, y)
3. 反向传播（从输出到输入）:
   - 输出层: ∂L/∂ŷ（直接对损失求导）
   - 中间层: ∂L/∂x = ∂L/∂y × ∂y/∂x（链式法则）
   - 参数: ∂L/∂W = ∂L/∂y × xᵀ

举例（单层线性+sigmoid+BCE）:
  y = sigmoid(Wx + b)
  L = -[t·log(y) + (1-t)·log(1-y)]
  ∂L/∂y = (-t/y + (1-t)/(1-y)) = (y-t)/[y(1-y)]
  ∂y/∂(Wx) = y(1-y)  （sigmoid导数）
  ∂L/∂(Wx) = y - t   （化简后优美结果）
  ∂L/∂W = (y-t) × xᵀ
  ∂L/∂b = y - t
```

### Q2: BatchNorm 的作用？训练和推理时有什么区别？

```
作用（3点）:
  ① 解决内部协变量偏移（Internal Covariate Shift）
  ② 允许更大 LR，加速训练
  ③ 轻微正则化效果（训练时引入随机性）

训练时:
  μ, σ 来自当前 batch → 引入噪声 → 有正则效果

推理时:
  μ, σ 使用训练时统计的 running_mean/var
  → 确定性，无随机性

陷阱:
  - 小 batch（<4）时 BN 统计不稳定，用 GN/LN
  - batch 中样本不独立（如连续帧视频）时 BN 有偏
  - 模型导出时必须设 eval()，否则用 batch 统计推理
```

### Q3: 梯度消失和梯度爆炸的原因及解决方案

```
梯度消失:
  原因: sigmoid/tanh 导数最大值 < 1，多层相乘趋近于0
  解决:
    ① 使用 ReLU 等激活函数（导数不饱和）
    ② 残差连接（ResNet），梯度直连
    ③ 梯度裁剪（当然主要针对爆炸）
    ④ 合适的权重初始化（Xavier/He）

梯度爆炸:
  原因: 参数>1的连乘，梯度指数增大
  解决:
    ① 梯度裁剪: clip_grad_norm_(params, max_norm=1.0)
    ② 权重初始化
    ③ 降低 LR
```

## 深度学习原理类

### Q4: Transformer 的 Attention 为什么要除以 sqrt(d_k)？

```
原因:
  Q @ Kᵀ 的结果方差为 d_k（每个维度贡献 1 的方差）
  整体 Var(QKᵀ) = d_k
  
  若不缩放: d_k 较大时，点积结果方差大
  → softmax 梯度趋近于0（因为 softmax 在大值区间几乎是阶跃函数）
  → 注意力集中在一处，其他位置梯度消失
  
  除以 sqrt(d_k) 后:
  Var(QKᵀ / sqrt(d_k)) = 1
  → softmax 输入方差稳定
  → 梯度正常流动
```

### Q5: YOLO 系列的演进核心改进点？

```
YOLOv1: 网格 S×S → 每格预测 B 个框 + C 个类别
YOLOv2: BN + 锚框 + 高分辨率训练
YOLOv3: FPN 多尺度 + Darknet53
YOLOv4: Mosaic增强 + CSPNet + CIoU + PAN + SA-net
YOLOv5: PyTorch + 自动锚框 + 更好工程化
YOLOv7: E-ELAN + 辅助检测头
YOLOv8: Anchor-Free + C2f + Decoupled Head
YOLOv9: PGI（可编程梯度信息）+ GELAN
YOLOv10: NMS-Free 双重标签分配
YOLOv11: C3k2 + A2C2f + PSA（位置敏感注意力）
```

### Q6: 解释 Focal Loss 的原理和参数含义

```
背景: 单阶段检测器负样本（背景）>>正样本（目标），简单样本主导损失

FL(pt) = -αt × (1-pt)^γ × log(pt)

参数含义:
  pt = sigmoid(x) 若标签=1，else 1-sigmoid(x)
  αt: 前景/背景权重（默认 0.25 前景，0.75 背景）
  γ:  聚焦因子（默认2）

直觉理解:
  简单负样本 (pt=0.9): (1-0.9)^2=0.01，权重降低100×
  难负样本 (pt=0.5): (1-0.5)^2=0.25，权重降低4×
  → 自动聚焦在难样本上
```

## 计算机视觉类

### Q7: 小目标检测难在哪里？你怎么解决的？

```
难点:
  ① 像素少（<32×32px），特征信息不足
  ② 高层特征图（大步长）已丢失小目标
  ③ 正负样本极度不平衡（背景多，目标少）
  ④ 模型感受野通常大于目标尺寸

解决方案（按效果排序）:
  ① SAHI 切片推理：大图切成小块分别检测再合并
  ② 多尺度训练（0.5x~1.5x 随机）
  ③ FPN 低层特征 P2 接小目标分支
  ④ Anchor 设计（更小的锚框，k-means聚类）
  ⑤ 高分辨率输入（1280 vs 640）
  ⑥ 数据增强：随机缩小目标（copy-paste）
```

### Q8: 如何处理训练数据不平衡？

```
多类别不平衡:
  ① 过采样少数类（SMOTE/复制）
  ② 欠采样多数类
  ③ Focal Loss / Class Balanced Loss
  ④ 数据增强扩充少数类
  ⑤ 分层采样（StratifiedSampler）

前景/背景不平衡（目标检测）:
  ① Focal Loss（One-Stage）
  ② Online Hard Example Mining OHEM（Two-Stage）
  ③ 负样本采样（pos:neg = 1:3）

量化评估: 查看每类 AP，重点关注 AP 低的类
```

## 工程经验类

### Q9: 模型精度调不上去，你怎么排查？

```
排查步骤（从易到难）:

Step 1: 数据排查
  - 可视化训练数据 + 标注（check 标注质量）
  - 统计类别分布（是否严重不平衡）
  - 检查数据预处理（归一化、Resize是否正确）

Step 2: 过拟合/欠拟合判断
  - 在训练集上 test：若训练集精度也低 → 欠拟合
  - 训练集精度高但验证集低 → 过拟合

Step 3: 损失函数分析
  - 各组件损失（cls/box/obj）是否均在下降
  - 是否有某类 loss 不收敛

Step 4: 超参数检查
  - LR 是否合适（LR Range Test）
  - Batch Size
  - 数据增强是否过强（导致信息损失）

Step 5: 模型检查
  - 模型容量是否足够（试大模型）
  - 预训练权重是否正确加载（check层名）
```

### Q10: 解释 Sim-to-Real 的主要挑战和解决方案

```
核心 Gap:
  视觉: 光照、纹理、背景分布不同
  动力学: 电机延迟、气动效应、IMU噪声差异
  接触: 摩擦、弹性系数

解决方案:
  ① 域随机化: 随机化仿真中的光照/纹理/物理参数
  ② 域适应(Domain Adaptation): GAN/对比学习对齐特征分布
  ③ 系统辨识: 精确测量真实系统参数
  ④ 残差学习: 仿真控制器 + 学习残差修正
  ⑤ 自适应控制: 在线估计系统参数（RKHS, Gaussian Process）
  ⑥ Meta-RL: MAML 快速适应新环境
```

## 项目深问类（STAR 框架）

### Q11: 描述一个你解决的最有挑战性的技术问题

```
STAR 答题框架:
  S（Situation）: 项目背景，问题出现的场景
  T（Task）: 你的具体任务和目标
  A（Action）: 你做了什么（重点！要具体）
  R（Result）: 量化结果（mAP提升多少？速度提升几倍？）

示例（裂缝检测）:
  S: 无人机拍摄的路面图像分辨率5472×3648，裂缝最细0.3mm
  T: 要在Jetson上实时检测所有裂缝，包括细微裂缝
  A: 
    ① 调研发现YOLOv8在小目标上漏检严重（原因：步长32导致细裂缝消失）
    ② 实现SAHI切片推理：将大图切成640×640小块+50%重叠，分别推理后合并NMS
    ③ 针对重叠区域设计加权NMS策略，解决边界框重复问题
    ④ INT8量化+TensorRT加速，Jetson单帧处理时间从3.2s降至0.8s
  R: 
    mAP@0.5从0.51提升至0.78，细裂缝召回率从32%提升至74%
    处理速度满足作业需求（<1s/帧，无人机飞行覆盖完整路段）
```

## 论文引用

- [1] **梯度分析** — Pascanu et al., "On the Difficulty of Training Recurrent Neural Networks," ICML 2013.
- [2] **权重初始化** — He et al., "Delving Deep into Rectifiers: Surpassing Human-Level Performance," ICCV 2015.
- [3] **Xavier初始化** — Glorot & Bengio, "Understanding the Difficulty of Training Deep FFNNs," AISTATS 2010.
- [4] **Attention缩放** — Vaswani et al., "Attention Is All You Need," NeurIPS 2017.
- [5] **Focal Loss** — Lin et al., "Focal Loss for Dense Object Detection," ICCV 2017.
- [6] **OHEM** — Shrivastava et al., "Training Region-based Object Detectors with Online Hard Example Mining," CVPR 2016.
- [7] **SMOTE** — Chawla et al., "SMOTE: Synthetic Minority Over-sampling Technique," JAIR 2002.
- [8] **Domain Randomization** — Tobin et al., "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World," IROS 2017.
- [9] **MAML** — Finn et al., "Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks," ICML 2017.
- [10] **BatchNorm分析** — Santurkar et al., "How Does Batch Normalization Help Optimization?" NeurIPS 2018. [BN真实原理]

## 关联

- 相关概念: [[concept-deep-learning-basics]], [[concept-loss-functions]], [[concept-hyperparameter-tuning]]
- 参见: [[topics/topic-ai-fundamentals-roadmap]], 四个项目页

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——11道高频题、完整答题框架、STAR模板、10篇论文引用
