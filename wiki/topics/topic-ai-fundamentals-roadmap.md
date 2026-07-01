# AI 算法工程师基本功路线

> **类型**: topic
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-27
> **标签**: #基本功 #深度学习 #CV #面试 #工程

## 摘要
从初级到资深 AI 算法工程师（CV 方向）的完整基本功学习路线图，覆盖 6 个阶段：数学基础 → 深度学习理论 → CV 核心任务 → 工程部署 → 项目实战 → 面试突击。每阶段标注必学内容、检验标准和预计时间，并配套关键论文引用。

---

## 阶段一：数学基础（2-4 周）

| 模块 | 必学内容 | 检验标准 |
|------|---------|---------|
| 线性代数 | 矩阵运算、特征值/SVD、PCA 推导 | 能手推 PCA、SVD 几何意义 |
| 概率论 | 贝叶斯、MLE/MAP、常见分布、信息论 | 能手推 Softmax + CE 梯度 |
| 最优化 | 梯度下降族、凸优化、拉格朗日对偶 | 能解释为什么 Adam 有效 |
| 微积分 | 链式法则、梯度、Hessian、泰勒展开 | 能推导反向传播 |
| 旋转理论 | 旋转矩阵/四元数/欧拉角/李代数 | 理解 Gimbal Lock 问题 |

**必读**：Thrun et al. 《Probabilistic Robotics》第 2-3 章（贝叶斯滤波）

> 📖 参见: [[concepts/concept-math-foundation]]

---

## 阶段二：深度学习理论（3-4 周）

| 模块 | 必学内容 | 检验标准 |
|------|---------|---------|
| 前向/反向传播 | 计算图、链式法则、自动微分 | 能徒手写两层 MLP 的反向传播 |
| 激活函数 | ReLU/Sigmoid/GELU/SiLU 对比 | 能画出各函数及其导数曲线 |
| 损失函数 | CE/MSE/Focal/IoU 系列 | 能解释何时用哪个 |
| 归一化 | BN/LN/IN/GN 原理与区别 | 能写出 BN 的前向和反向代码 |
| 优化器 | SGD/Adam/AdamW 原理 | 能解释 bias correction 的作用 |
| 正则化 | Dropout/WeightDecay/LabelSmooth | 能解释贝叶斯先验对应关系 |
| 初始化 | Xavier/Kaiming | 理解方差保持原理 |
| Attention | Self-Attention / Multi-Head / Cross-Attention | 能写出完整 MHA 代码 |

**关键代码：BN 前向传播（面试必考）**

```python
def batch_norm_forward(x, gamma, beta, eps=1e-5):
    """x: (N, C, H, W)"""
    mu    = x.mean(axis=(0, 2, 3), keepdims=True)
    var   = x.var(axis=(0, 2, 3), keepdims=True)
    x_hat = (x - mu) / (var + eps) ** 0.5
    y     = gamma * x_hat + beta
    return y, x_hat, mu, var  # 缓存用于反向传播

def batch_norm_backward(dout, x_hat, mu, var, gamma, eps=1e-5):
    N, C, H, W = dout.shape
    M = N * H * W
    dgamma = (dout * x_hat).sum(axis=(0, 2, 3), keepdims=True)
    dbeta  = dout.sum(axis=(0, 2, 3), keepdims=True)
    dx_hat = dout * gamma
    dvar   = (-0.5 * dx_hat * x_hat / (var + eps)).sum(axis=(0,2,3), keepdims=True)
    dmu    = (-dx_hat / (var + eps)**0.5).sum(axis=(0,2,3), keepdims=True)
    dx = dx_hat / (var+eps)**0.5 + 2*dvar*x_hat*(var+eps)**0.5/M + dmu/M
    return dx, dgamma, dbeta
```

> 📖 参见: [[concepts/concept-deep-learning-basics]], [[concepts/concept-loss-functions]]

---

## 阶段三：CV 核心任务（6-8 周）

### 3.1 图像分类
```
必学: ResNet → MobileNet → EfficientNet → ViT → SwinT → ConvNeXt
实战: ImageNet 训练、迁移学习 (from_pretrained)、类别不平衡处理
检验: 能手写 ResNet50 的 Block 结构，知道各 Stage 通道数
```

**ResNet Bottleneck Block**：

```python
class Bottleneck(nn.Module):
    expansion = 4
    def __init__(self, in_planes, planes, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_planes, planes, 1, bias=False)
        self.bn1   = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, stride, 1, bias=False)
        self.bn2   = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes*4, 1, bias=False)
        self.bn3   = nn.BatchNorm2d(planes*4)
        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != planes*4:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, planes*4, 1, stride, bias=False),
                nn.BatchNorm2d(planes*4))
    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = F.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        out += self.shortcut(x)
        return F.relu(out)
```

### 3.2 目标检测
```
必学: Faster RCNN → YOLOv5/v8 → DETR → RT-DETR → DINO
实战: COCO 训练、Anchor-Free vs Anchor-Based、mAP 评估、NMS 调参
检验: 能画出 YOLOv8 的完整网络结构（CSPDarknet53 + C2f + PAN + Head）
```

### 3.3 语义分割
```
必学: FCN → U-Net → DeepLabV3+ → SegFormer → SAM → SAM2
实战: 自定义数据集标注、Dice Loss + CE 组合、mIoU 评估
重点: 注意力机制在分割中的应用（SegFormer 的 Mix-FFN）
```

### 3.4 目标跟踪
```
必学: SORT → DeepSORT → ByteTrack → BoT-SORT → StrongSORT
实战: MOT16/17 评估、ID Switch 优化、ReID 特征提取
检验: 能解释 HOTA 指标的含义，知道 ByteTrack 如何利用低置信度框
```

### 3.5 关键论文速读清单

| 论文 | 核心贡献 | 必要性 |
|------|---------|-------|
| ResNet（He 2016） | 残差连接，训练极深网络 | ★★★★★ |
| Attention Is All You Need（Vaswani 2017） | Transformer，视觉基础 | ★★★★★ |
| ViT（Dosovitskiy 2021） | 图像分块 Patch Embedding | ★★★★★ |
| Swin Transformer（Liu 2021） | 窗口注意力，视觉SOTA基础 | ★★★★★ |
| YOLOv8（Jocher 2023） | Anchor-Free YOLO，工业必备 | ★★★★★ |
| DETR（Carion 2020） | 端到端检测，匈牙利匹配 | ★★★★ |
| SegFormer（Xie 2021） | 轻量分割，无位置编码 | ★★★★ |
| ByteTrack（Zhang 2022） | 低置信度框跟踪 | ★★★★ |
| SAM（Kirillov 2023） | 通用分割大模型 | ★★★★ |

> 📖 参见: [[concepts/concept-cv-classic-backbones]], [[concepts/concept-object-detection]]

---

## 阶段四：工程部署（3-4 周）

| 模块 | 必学内容 |
|------|---------|
| **模型导出** | PyTorch → ONNX → TensorRT / OpenVINO / RKNN |
| **推理加速** | FP16/INT8 量化、算子融合、动态 batch |
| **边缘部署** | Jetson Orin (TensorRT)、RK3588 (RKNN) |
| **性能分析** | nvprof/nsys、trtexec、torch.profiler |
| **服务化** | Triton Inference Server、FastAPI + 异步队列 |
| **MLOps** | DVC 数据版本、MLflow 实验追踪、wandb 可视化 |

**完整部署流水线**：

```bash
# Step 1: PyTorch → ONNX（动态 batch）
python -c "
import torch
model = torch.load('best.pt').eval().cuda()
dummy = torch.zeros(1, 3, 640, 640).cuda()
torch.onnx.export(model, dummy, 'model.onnx',
    opset_version=17,
    input_names=['images'],
    output_names=['output'],
    dynamic_axes={'images': {0: 'batch'}, 'output': {0: 'batch'}})
"

# Step 2: ONNX 简化（常量折叠 + 死代码消除）
pip install onnxsim && onnxsim model.onnx model_sim.onnx

# Step 3: TensorRT 构建（FP16）
trtexec --onnx=model_sim.onnx \
        --saveEngine=model_fp16.engine \
        --fp16 --workspace=4096

# Step 4: 压测
trtexec --loadEngine=model_fp16.engine \
        --fp16 --warmUp=200 --duration=60
```

> 📖 参见: [[concepts/method-model-deployment]]

---

## 阶段五：项目实战（持续）

| 项目类型 | 推荐方向 | 技术栈 | 参考页 |
|---------|---------|--------|--------|
| 检测类 | 车牌识别 | LPRNet + CTC + TensorRT | [[topics/topic-license-plate-recognition]] |
| 跟踪类 | 违停取证 | YOLOv8 + ByteTrack + ROI | [[topics/topic-illegal-parking-system]] |
| 分割类 | 裂缝检测 | SAHI + SegFormer + 骨架 | [[topics/topic-crack-detection]] |
| 定位类 | 精准降落 | ArUco + PX4 + MAVROS | [[topics/topic-precision-localization]] |
| 重建类 | 三维建模 | COLMAP + 3DGS | [[topics/topic-perception-stack]] |

---

## 阶段六：面试突击（2-4 周）

### 高频知识体系

```
┌─ 数学基础 ────────────┐
│ • SVD/PCA 手推        │
│ • CE 梯度推导（含 BN） │
│ • 凸优化 KKT 条件     │
└──────────────────────┘
         ↓
┌─ 深度学习 ────────────┐
│ • ResNet/Attention 结构│
│ • Adam bias correction │
│ • Dropout train/eval  │
│ • BN 在 train/eval 差异│
└──────────────────────┘
         ↓
┌─ CV 专项 ─────────────┐
│ • YOLO 演进（v1→v11） │
│ • mAP 手算           │
│ • 小目标检测方案      │
│ • NMS → Soft-NMS → NMSFree│
└──────────────────────┘
         ↓
┌─ 工程能力 ────────────┐
│ • DataLoader pin_memory│
│ • AMP 混合精度原理    │
│ • TensorRT 量化方案  │
│ • OOM 排查步骤        │
└──────────────────────┘
         ↓
┌─ 项目深挖 ────────────┐
│ • STAR 法则           │
│ • 技术难点 + 解决方案 │
│ • 量化指标（mAP/FPS） │
│ • 踩坑经验（真实最加分）│
└──────────────────────┘
```

### 高频面试题精选（Top 10）

1. **BN 和 LN 有什么区别？训练和推理时 BN 有什么不同？**
   - BN 在 batch 维度归一化；LN 在特征维度归一化
   - 训练：实时计算均值方差；推理：使用 running mean/var（需 `model.eval()`）

2. **解释 Focal Loss 的原理，它解决了什么问题？**
   - 解决正负样本极度不平衡（背景远多于目标）
   - `FL = -α(1-p)^γ log(p)`，γ 降低易分样本权重，聚焦困难样本

3. **YOLO 从 v1 到 v8 的核心演进是什么？**
   - v1: 7×7 grid，回归框；v3: FPN多尺度；v5: CSP+Mosaic；v8: Anchor-Free+C2f+decoupled head

4. **Transformer 的计算复杂度是多少？如何优化？**
   - `O(n²d)`，n 为序列长度；优化：窗口注意力（Swin）、线性注意力、Flash Attention

5. **NMS 的时间复杂度？Soft-NMS 和 NMS 的区别？**
   - NMS: `O(n²)`；Soft-NMS 不直接删除，而是衰减重叠框的置信度，召回率更高

6. **混合精度训练（AMP）的原理？为什么 FP16 不会导致溢出？**
   - 前向 FP16，梯度 FP32 累积；loss scaling 防止 FP16 下溢出

7. **如何处理小目标检测？**
   - P2 检测头 + SAHI 切片 + 数据增强（Mosaic大图） + Anchor 尺寸调整

8. **mAP 的完整计算过程？**
   - 按置信度排序 → 计算 Precision/Recall 曲线 → 计算 AUC → 各类别平均

9. **DataLoader 的 num_workers 和 pin_memory 有什么作用？**
   - `num_workers>0`：多进程预加载；`pin_memory=True`：锁页内存，GPU 传输更快

10. **模型推理时出现 OOM 怎么处理？**
    - 减小 batch；`with torch.no_grad():`；释放 cache；FP16 推理；动态图换静态图

> 📖 参见: [[concepts/concept-ai-interview-qa]], [[concepts/concept-model-evaluation]]

### 每日刷题建议

| 时间 | 内容 | 目的 |
|------|------|------|
| 上午 1h | 手推公式（每天 1-2 个） | 数学深度 |
| 下午 1h | 刷面试题（理解原理而非背诵） | 面试准备 |
| 晚上 1h | 看论文 / 复现核心代码 | 前沿追踪 |

---

## 学习资源推荐

### 必读论文（Top 15）

| # | 论文 | 作者 | 年份 | 核心贡献 |
|---|------|------|------|---------|
| 1 | Deep Residual Learning | He et al. | 2016 | 残差网络 |
| 2 | Attention Is All You Need | Vaswani et al. | 2017 | Transformer |
| 3 | An Image is Worth 16×16 Words | Dosovitskiy et al. | 2021 | ViT |
| 4 | Swin Transformer | Liu et al. | 2021 | 窗口注意力 |
| 5 | Focal Loss (RetinaNet) | Lin et al. | 2017 | 类别不平衡 |
| 6 | Batch Normalization | Ioffe & Szegedy | 2015 | BN 归一化 |
| 7 | Adam | Kingma & Ba | 2014 | 自适应优化器 |
| 8 | DETR | Carion et al. | 2020 | 端到端检测 |
| 9 | ConvNeXt | Liu et al. | 2022 | CNN 的反击 |
| 10 | Segment Anything | Kirillov et al. | 2023 | 通用分割 |
| 11 | ByteTrack | Zhang et al. | 2022 | 多目标跟踪 |
| 12 | SegFormer | Xie et al. | 2021 | 高效分割 |
| 13 | Masked Autoencoders | He et al. | 2022 | MAE 自监督 |
| 14 | CLIP | Radford et al. | 2021 | 多模态对比学习 |
| 15 | Dropout | Srivastava et al. | 2014 | 正则化经典 |

### 基本功扩展书单

| 页面 | 重点 |
|------|------|
| [[topics/topic-foundational-reading-list]] | 数学、经典机器学习、视觉几何、状态估计、规划控制的书和论文总路线 |
| [[concepts/concept-classical-ml-foundations]] | EM/SVM/Boosting/Random Forest 等传统机器学习底座 |
| [[concepts/concept-vision-geometry-foundations]] | 相机模型、标定、PnP、极几何、RANSAC、SIFT |
| [[concepts/concept-state-estimation-foundations]] | Bayes Filter、Kalman、EKF、因子图、ESKF |
| [[concepts/concept-planning-control-foundations]] | A*/RRT*/Minimum Snap、PID/LQR/MPC、四旋翼控制 |

### 推荐课程

| 课程 | 平台 | 特点 |
|------|------|------|
| CS231n (Stanford) | YouTube | CV 入门首选，作业质量极高 |
| CS224n (Stanford) | YouTube | NLP + Transformer |
| 李宏毅 ML/DL | YouTube/B站 | 中文最友好，深入浅出 |
| DeepLearning.AI | Coursera | 动手实战，适合初学者 |
| Fast.ai | fast.ai | Top-Down 方法论 |

---

## 关联
- 相关概念: [[concepts/concept-math-foundation]], [[concepts/concept-classical-ml-foundations]], [[concepts/concept-deep-learning-basics]], [[concepts/concept-training-methods]], [[concepts/concept-hyperparameter-tuning]], [[concepts/concept-model-evaluation]], [[concepts/concept-ai-interview-qa]], [[concepts/concept-loss-functions]], [[concepts/concept-cv-classic-backbones]], [[concepts/concept-vision-geometry-foundations]], [[concepts/concept-state-estimation-foundations]], [[concepts/concept-planning-control-foundations]]
- 项目实战: [[topics/topic-license-plate-recognition]], [[topics/topic-illegal-parking-system]], [[topics/topic-crack-detection]], [[topics/topic-precision-localization]]
- 总路线: [[topics/roadmap-drone-ai-engineer]], [[topics/topic-foundational-reading-list]]

## 引用来源

### 深度学习基础
- [1] He, K., et al. (2016). **Deep Residual Learning for Image Recognition**. CVPR 2016. — 残差网络，深度学习里程碑
- [2] Ioffe, S., & Szegedy, C. (2015). **Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift**. ICML 2015. — BN，训练加速核心技术
- [3] Kingma, D. P., & Ba, J. (2014). **Adam: A Method for Stochastic Optimization**. ICLR 2015. — Adam 优化器
- [4] Srivastava, N., et al. (2014). **Dropout: A Simple Way to Prevent Neural Networks from Overfitting**. JMLR 2014. — Dropout 正则化
- [5] Glorot, X., & Bengio, Y. (2010). **Understanding the Difficulty of Training Deep Feedforward Neural Networks**. AISTATS 2010. — Xavier 初始化
- [6] He, K., et al. (2015). **Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification**. ICCV 2015. — Kaiming/He 初始化，PReLU

### 注意力与 Transformer
- [7] Vaswani, A., et al. (2017). **Attention Is All You Need**. NeurIPS 2017. — Transformer 原始论文
- [8] Dosovitskiy, A., et al. (2021). **An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale**. ICLR 2021. — ViT
- [9] Liu, Z., et al. (2021). **Swin Transformer: Hierarchical Vision Transformer using Shifted Windows**. ICCV 2021. — Swin Transformer，视觉 SOTA 基础

### 目标检测
- [10] Lin, T. Y., et al. (2017). **Focal Loss for Dense Object Detection**. ICCV 2017. — Focal Loss + RetinaNet
- [11] Carion, N., et al. (2020). **End-to-End Object Detection with Transformers**. ECCV 2020. — DETR，端到端检测
- [12] Zhang, H., et al. (2022). **DINO: DETR with Improved DeNoising Anchor Boxes for End-to-End Object Detection**. ICLR 2023. — DINO，检测 SOTA

### 分割与多模态
- [13] Kirillov, A., et al. (2023). **Segment Anything**. ICCV 2023. — SAM，通用分割
- [14] Radford, A., et al. (2021). **Learning Transferable Visual Models from Natural Language Supervision**. ICML 2021. — CLIP，多模态基础
- [15] He, K., et al. (2022). **Masked Autoencoders Are Scalable Vision Learners**. CVPR 2022. — MAE，自监督预训练

## 变更记录
- 2026-06-27: 初始创建，6 阶段完整路线图（无引用）
- 2026-06-27: 大规模扩写，补充15篇论文引用、ResNet/BN代码、面试题精选、论文速读表
- 2026-06-29: 补充基本功扩展书单入口，链接经典机器学习、视觉几何、状态估计、规划控制四个新基础页
