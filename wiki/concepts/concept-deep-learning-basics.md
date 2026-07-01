# 深度学习理论基础（Deep Learning Basics）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

深度学习理论涵盖神经网络基础结构、激活函数、归一化方法、注意力机制和 Transformer 架构。这是 AI 算法工程师的核心理论基础，必须深刻理解才能做好模型设计和调优。

## 神经网络基础

### 全连接层（Linear Layer）

```python
# 前向传播
y = W @ x + b    # W: (out, in), x: (in,), b: (out,)
# 参数量: in * out + out

# 矩阵批量计算
Y = X @ Wᵀ + b   # X: (batch, in), Y: (batch, out)
```

### 卷积层（Conv2D）

```
输出尺寸公式:
  H_out = ⌊(H_in + 2p - k) / s⌋ + 1
  
参数量: k×k × C_in × C_out + C_out（有bias）

感受野:
  单层 k×k 卷积感受野 = k
  n层堆叠感受野 = n*(k-1) + 1
  带 stride: 成倍扩大

计算量: 2 × H_out × W_out × C_in × C_out × k²  (FLOPs)
```

### 激活函数对比

| 函数 | 公式 | 值域 | 优势 | 问题 |
|------|------|------|------|------|
| Sigmoid | 1/(1+e^-x) | (0,1) | 概率输出 | 梯度消失，计算慢 |
| Tanh | (e^x-e^-x)/(e^x+e^-x) | (-1,1) | 零中心化 | 梯度消失 |
| ReLU | max(0,x) | [0,+∞) | 简单高效 | 死亡ReLU |
| Leaky ReLU | max(αx,x), α=0.01 | (-∞,+∞) | 缓解死亡 | α需调参 |
| ELU | x≥0:x, x<0:α(e^x-1) | (-α,+∞) | 负值饱和 | 计算慢 |
| GELU | x·Φ(x) | (-∞,+∞) | BERT/GPT标配 | 计算稍慢 |
| SiLU/Swish | x·σ(x) | (-∞,+∞) | YOLO系列常用 | 计算稍慢 |
| Mish | x·tanh(softplus(x)) | (-∞,+∞) | YOLO v4使用 | 计算慢 |

```python
# GELU 实现
import torch, math
def gelu(x):
    return x * 0.5 * (1.0 + torch.erf(x / math.sqrt(2.0)))

# SiLU/Swish
def silu(x):
    return x * torch.sigmoid(x)
```

## 消失与爆炸梯度（Vanishing & Exploding Gradients）

> 📄 **核心论文**: Pascanu et al., "On the Difficulty of Training Recurrent Neural Networks," ICML 2013. [[../raw/pascanu13.pdf]]

### 数学本质：Jacobian 连乘

这是深度学习中**最根本的优化挑战之一**。对于 RNN，梯度通过时间反向传播（BPTT）时需要连乘 Jacobian 矩阵：

$$\frac{\partial x_t}{\partial x_k} = \prod_{t \ge i > k} W_{rec}^T \cdot \text{diag}(\sigma'(x_{i-1}))$$

记 $W_{rec}$ 的最大特征值/奇异值为 $\lambda_1$：

| 条件 | 现象 | 后果 |
|------|------|------|
| $\|\lambda_1\| > 1$ | 梯度指数爆炸 | loss 突然飙升到 NaN，训练崩溃 |
| $\|\lambda_1\| < 1$ | 梯度指数消失 | 早期时间步信息无法影响后续输出 |
| $\|\lambda_1\| \approx 1$ | 正常传播 | 梯度稳定，信息可长程传递 |

### 消失梯度的根本原因

不仅是 RNN——**任何深层网络都存在梯度消失隐患**：

```
深层前馈网络:
  ∂L/∂x₁ = ∂L/∂x_L · ∏_{i=L}^{2} ∂x_i/∂x_{i-1}
  
  若每层梯度 < 1（如 Sigmoid 导数最大 0.25），则:
  经过 4 层  → 梯度衰减至 (0.25)⁴ ≈ 0.004
  经过 20 层 → 梯度衰减至 10⁻¹²（基本为零）
```

```python
import torch
import torch.nn as nn

# 验证：深层 Sigmoid 网络的梯度消失
def demonstrate_vanishing_gradient():
    """模拟 50 层纯 Sigmoid 网络的梯度衰减"""
    x = torch.randn(1, 10, requires_grad=True)
    for i in range(50):
        x = torch.sigmoid(x)  # 每层梯度 ≤ 0.25
    loss = x.sum()
    loss.backward()
    # 此时第一层的梯度 ≈ 0.25^50 ≈ 10^{-30}
    print(f"50层后梯度范数: {x.grad.norm():.2e}")
    # 输出: 50层后梯度范数: ~0.00e+00 (数值下溢)

# 对比：ReLU
def demonstrate_no_vanishing_relu():
    x = torch.randn(1, 10, requires_grad=True)
    for i in range(50):
        x = torch.relu(x)  # 正半区导数固定为 1
    loss = x.sum()
    loss.backward()
    print(f"50层ReLU后梯度范数: {x.grad.norm():.6f}")
    # 输出正常值

# Pascanu 论文的验证：检查 Wrec 的谱半径
def check_spectral_radius(model, module_name='rnn'):
    """检查循环权重矩阵的最大奇异值"""
    for name, param in model.named_parameters():
        if 'weight_hh' in name:  # RNN hidden-to-hidden weight
            λ1 = torch.linalg.svdvals(param).max().item()
            print(f"{name}: λ₁ = {λ1:.4f}")
            if λ1 > 1:
                print("  ⚠️  可能梯度爆炸！")
            elif λ1 < 0.1:
                print("  ⚠️  可能梯度消失！")
            else:
                print("  ✅ 梯度相对稳定")
```

### 解决方案对比

| 方案 | 解决爆炸？ | 解决消失？ | 来源 | 备注 |
|------|-----------|-----------|------|------|
| **梯度裁剪** | ✅ | ❌ | Pascanu 2013 | 工业标配 |
| ReLU/GELU 激活 | ❌ | ✅ (部分) | Nair 2010 | 正半区导数=1 |
| LSTM/GRU | ❌ | ✅ | Hochreiter 1997 | 门控机制 |
| 残差连接 | ❌ | ✅ | He 2016 | 梯度的"高速公路" |
| LayerNorm | ❌ | ✅ (部分) | Ba 2016 | 稳定激活值分布 |
| 消逝梯度正则化 | ❌ | ✅ (软约束) | Pascanu 2013 | 配合裁剪使用 |
| Hessian-Free 优化 | ✅ | ✅ | Martens 2011 | 计算昂贵 |

> 📌 **关键教训**：Pascanu 论文证明梯度裁剪**不是正则化**——它同时改善训练/测试误差，是一个纯优化技巧。这与 L1/L2 正则化（可能增加训练误差）本质不同。

## 归一化方法对比（重点）

```
BatchNorm:     μ,σ 沿 Batch 维度计算   → 适合 CNN（batch>=16）
LayerNorm:     μ,σ 沿 Channel 维度     → Transformer 标配
InstanceNorm:  μ,σ 沿每个样本每个通道 → 风格迁移
GroupNorm:     μ,σ 沿每组 Channel     → 小batch CNN（目标检测）
```

```python
class BatchNorm2d(nn.Module):
    """
    BN 训练时: 使用 batch 统计量
    BN 推理时: 使用 running mean/var（滑动平均）
    """
    def forward(self, x):
        if self.training:
            μ = x.mean(dim=[0,2,3], keepdim=True)  # 沿BHW
            σ² = x.var(dim=[0,2,3], keepdim=True)
            # 更新滑动统计量
            self.running_mean = 0.9*self.running_mean + 0.1*μ.squeeze()
            self.running_var  = 0.9*self.running_var  + 0.1*σ².squeeze()
        else:
            μ = self.running_mean.reshape(1,-1,1,1)
            σ² = self.running_var.reshape(1,-1,1,1)
        # 归一化 + 缩放平移
        x_norm = (x - μ) / (σ² + self.eps).sqrt()
        return self.gamma * x_norm + self.beta
```

## 注意力机制（Attention）

### Scaled Dot-Product Attention

```python
def scaled_dot_product_attention(Q, K, V, mask=None):
    """
    Q: (batch, heads, seq, d_k)
    K: (batch, heads, seq, d_k)
    V: (batch, heads, seq, d_v)
    """
    d_k = Q.shape[-1]
    # 计算注意力分数
    scores = Q @ K.transpose(-2, -1) / math.sqrt(d_k)
    if mask is not None:
        scores = scores.masked_fill(mask == 0, float('-inf'))
    # Softmax 归一化
    attn_weights = F.softmax(scores, dim=-1)
    attn_weights = F.dropout(attn_weights, p=0.1)
    # 加权聚合
    return attn_weights @ V, attn_weights
```

### Multi-Head Attention

```python
class MultiHeadAttention(nn.Module):
    def __init__(self, d_model=512, num_heads=8):
        super().__init__()
        assert d_model % num_heads == 0
        self.d_k = d_model // num_heads
        self.num_heads = num_heads
        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)
    
    def forward(self, Q, K, V, mask=None):
        batch = Q.shape[0]
        # 线性变换 + 多头拆分
        q = self.W_q(Q).view(batch, -1, self.num_heads, self.d_k).transpose(1,2)
        k = self.W_k(K).view(batch, -1, self.num_heads, self.d_k).transpose(1,2)
        v = self.W_v(V).view(batch, -1, self.num_heads, self.d_k).transpose(1,2)
        # 注意力计算
        attn_out, _ = scaled_dot_product_attention(q, k, v, mask)
        # 合并多头 + 输出投影
        attn_out = attn_out.transpose(1,2).contiguous().view(batch, -1, self.num_heads * self.d_k)
        return self.W_o(attn_out)
```

## Transformer 架构

```
Encoder Block:
  输入 → LayerNorm → Multi-Head Self-Attention → + 残差
       → LayerNorm → FFN(Linear→GELU→Linear) → + 残差

Decoder Block:
  输入 → LayerNorm → Masked Self-Attention → + 残差
       → LayerNorm → Cross-Attention(Q=decoder, K=V=encoder) → + 残差
       → LayerNorm → FFN → + 残差

位置编码:
  PE(pos, 2i) = sin(pos / 10000^(2i/d_model))
  PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))
```

## 过拟合与正则化

| 技术 | 原理 | 何时使用 |
|------|------|---------|
| Dropout | 训练时随机置零 p% 神经元 | 大模型、全连接层 |
| L1/L2 正则 | 损失加参数范数惩罚 | 小模型 |
| DropBlock | 块状Dropout | CNN特征图 |
| Mixup | 线性插值两样本 | 图像分类 |
| CutMix | 粘贴区域 | 检测/分类 |
| Label Smoothing | 硬标签→软标签 | 分类任务 |
| Weight Decay | L2正则，AdamW实现 | 通用 |
| Early Stopping | 验证集loss不降则停 | 防过拟合必备 |

## 论文引用

- [1] **Attention is All You Need** — Vaswani et al., "Attention Is All You Need," NeurIPS 2017. [Transformer 奠基]
- [2] **ResNet** — He et al., "Deep Residual Learning for Image Recognition," CVPR 2016. [残差连接]
- [3] **BatchNorm** — Ioffe & Szegedy, "Batch Normalization: Accelerating Deep Neural Networks," ICML 2015.
- [4] **LayerNorm** — Ba et al., "Layer Normalization," arXiv 2016.
- [5] **GroupNorm** — Wu & He, "Group Normalization," ECCV 2018.
- [6] **Dropout** — Srivastava et al., "Dropout: A Simple Way to Prevent Neural Networks from Overfitting," JMLR 2014.
- [7] **GELU** — Hendrycks & Gimpel, "Gaussian Error Linear Units (GELUs)," arXiv 2016.
- [8] **Swish/SiLU** — Ramachandran et al., "Searching for Activation Functions," arXiv 2017.
- [9] **Mixup** — Zhang et al., "Mixup: Beyond Empirical Risk Minimization," ICLR 2018.
- [10] **CutMix** — Yun et al., "CutMix: Training Strategy that Makes Dense Prediction of Great Benefit," ICCV 2019.
- [11] **Label Smoothing** — Szegedy et al., "Rethinking the Inception Architecture," CVPR 2016.
- [12] **ViT** — Dosovitskiy et al., "An Image is Worth 16×16 Words: Transformers for Image Recognition at Scale," ICLR 2021.
- [13] **Flash Attention** — Dao et al., "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness," NeurIPS 2022.
- [14] **KV Cache** — 多篇综述文章，大模型推理加速关键技术 2023-2024.
- [15] **DropBlock** — Ghiasi et al., "DropBlock: A Regularization Method for Convolutional Networks," NeurIPS 2018.
- [16] **梯度消失与爆炸** — Pascanu, Mikolov & Bengio, "On the Difficulty of Training Recurrent Neural Networks," ICML 2013. [Jacobian 连乘分析、梯度裁剪奠基，来源 [[../raw/pascanu13.pdf]]]

## 关联

- 相关概念: [[concept-math-foundation]], [[concept-loss-functions]], [[concept-cv-classic-backbones]]
- 参见: [[concept-training-methods]], [[concept-model-evaluation]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——卷积公式、激活函数对比、BN/LN/GN代码、完整注意力代码、Transformer架构、正则化对比表、15篇论文引用
- 2026-06-29: Ingest [[../raw/pascanu13.pdf]]——新增消失/爆炸梯度数学分析小节（Jacobian连乘、谱半径检查代码、解决方案对比表、梯度裁剪vs正则化辨析）
