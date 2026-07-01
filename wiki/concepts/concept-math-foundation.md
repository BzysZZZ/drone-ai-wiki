# 数学基础（Mathematics Foundation）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

AI 算法工程师需要掌握线性代数、微积分、概率统计、优化理论四大数学模块。这些是理解反向传播、贝叶斯推断、卷积运算、梯度优化的数学基石。

## 线性代数

### 必知概念速查

| 概念 | 数学描述 | AI 中的用途 |
|------|---------|------------|
| 矩阵乘法 | C = AB，O(n³) | 全连接层 / 注意力计算 |
| 转置 | Aᵀ_{ij} = A_{ji} | Gram矩阵、注意力 |
| 行列式 | det(A) | 体积变换，可逆性判断 |
| 矩阵秩 | rank(A) | 低秩近似，信息压缩 |
| 特征值分解 | Av = λv | PCA、谱归一化 |
| SVD | A = UΣVᵀ | 矩阵压缩、LoRA微调 |
| Moore-Penrose伪逆 | A⁺ = VΣ⁺Uᵀ | 最小二乘解 |
| Kronecker积 | A⊗B | 卷积分解 |

### SVD 实战（LoRA 低秩分解）

```python
import torch

def lora_decompose(W, rank=4):
    """
    LoRA 核心：将权重矩阵分解为低秩近似
    W ≈ W₀ + BA，其中 B ∈ R^{m×r}, A ∈ R^{r×n}
    """
    U, S, Vh = torch.linalg.svd(W, full_matrices=False)
    # 取前 r 个奇异值
    U_r = U[:, :rank]
    S_r = S[:rank]
    V_r = Vh[:rank, :]
    # 低秩近似
    B = U_r * S_r.sqrt()   # shape: (m, rank)
    A = (S_r.sqrt().unsqueeze(-1) * V_r)  # shape: (rank, n)
    return A, B

# 参数节省比例
# 原始: m*n, LoRA: m*r + r*n = r*(m+n)
# rank=4, m=4096, n=4096: 节省 99.8% 参数
```

### PCA 主成分分析

```python
def pca(X, n_components=2):
    """
    PCA 降维
    1. 中心化
    2. 协方差矩阵
    3. 特征值分解
    4. 取前 k 个主成分
    """
    X_centered = X - X.mean(axis=0)
    cov = X_centered.T @ X_centered / (len(X) - 1)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    # 按特征值降序排列
    idx = np.argsort(eigenvalues)[::-1]
    components = eigenvectors[:, idx[:n_components]]
    return X_centered @ components

# 解释方差比
explained_ratio = eigenvalues[idx[:n_components]] / eigenvalues.sum()
```

## 微积分与优化

### 链式法则（反向传播基础）

```
复合函数求导: ∂L/∂x = ∂L/∂y · ∂y/∂x

多层网络:
  L = f(g(h(x)))
  ∂L/∂x = ∂L/∂f · ∂f/∂g · ∂g/∂h · ∂h/∂x

矩阵形式（注意维度）:
  y = Wx + b，L = loss(y)
  ∂L/∂W = (∂L/∂y)ᵀ @ x   # 外积
  ∂L/∂x = Wᵀ @ ∂L/∂y     # 转置乘
  ∂L/∂b = ∂L/∂y           # 直接求和
```

### 梯度下降变种

| 方法 | 更新规则 | 特点 |
|------|---------|------|
| SGD | θ -= lr * g | 简单，需调lr |
| Momentum | v = βv + g; θ -= lr*v | 加速收敛 |
| RMSProp | v = βv + (1-β)g²; θ -= lr*g/√v | 自适应lr |
| Adam | m=β₁m+(1-β₁)g; v=β₂v+(1-β₂)g²; θ -= lr*m̂/√v̂ | 工业标配 |
| AdamW | Adam + 权重衰减（不衰减bias/bn） | Transformer首选 |
| LAMB | 大批量分布式训练 | BERT预训练 |
| Lion | 只用符号梯度 | 节省内存 |

```python
# Adam 从零实现
class Adam:
    def __init__(self, params, lr=1e-3, betas=(0.9, 0.999), eps=1e-8, wd=0.0):
        self.lr, self.betas, self.eps, self.wd = lr, betas, eps, wd
        self.state = {p: {'m': torch.zeros_like(p), 
                          'v': torch.zeros_like(p), 't': 0} 
                     for p in params}
    
    def step(self):
        for p, s in self.state.items():
            if p.grad is None: continue
            g = p.grad + self.wd * p.data  # 权重衰减
            s['t'] += 1
            s['m'] = self.betas[0] * s['m'] + (1 - self.betas[0]) * g
            s['v'] = self.betas[1] * s['v'] + (1 - self.betas[1]) * g**2
            # 偏差修正
            m_hat = s['m'] / (1 - self.betas[0]**s['t'])
            v_hat = s['v'] / (1 - self.betas[1]**s['t'])
            p.data -= self.lr * m_hat / (v_hat.sqrt() + self.eps)
```

### 动力系统视角：消失/爆炸梯度的深层机制

> 📄 **核心论文**: Pascanu et al., "On the Difficulty of Training Recurrent Neural Networks," ICML 2013. [[../raw/pascanu13.pdf]]

Pascanu 等人的另一大理论贡献是从**动力系统**（Dynamical Systems）角度理解梯度传播。将 RNN 视为离散动力系统：

$$x_t = F(x_{t-1}, u_t, \theta)$$

**关键概念**：

| 概念 | 定义 | 与训练的关系 |
|------|------|-------------|
| **吸引子（Attractor）** | 系统状态收敛的稳定点集 | 长程记忆的基础——信息存储在吸引子中 |
| **分岔边界（Bifurcation Boundary）** | 参数空间中将不同吸引子分开的超曲面 | 训练过程中**跨过分岔边界 = 梯度爆炸** |
| **谱半径（Spectral Radius）** | 线性化 Jacobian 的最大特征值 | λ₁ 决定梯度是爆炸还是消失 |
| **Lyapunov 指数** | 相邻轨迹发散/收敛速率 | 正值 = 混沌（梯度爆炸），负值 = 稳定（梯度消失） |

```python
import torch
import numpy as np

# ========== 动力系统模拟：RNN 的梯度行为 ==========
def simulate_rnn_dynamics(W_rec, T=100, init_noise=0.01):
    """
    模拟 RNN 动力系统，计算梯度的 Lyapunov 指数
    论文 2.3 节的理论对应实现
    """
    d = W_rec.shape[0]
    x = torch.randn(d) * init_noise
    
    # 记录状态和 Jacobian 范数
    states = [x.clone()]
    jacobian_norms = []
    lyapunov_sum = 0
    
    for t in range(T):
        # 前向传播（论文 eq.2: x_t = W_rec σ(x_{t-1}) + ...）
        pre_act = W_rec @ torch.tanh(x)
        
        # Jacobian: J = W_rec^T diag(tanh'(x))
        tanh_deriv = 1 - torch.tanh(x) ** 2
        # 近似最大奇异值（幂迭代法）
        v = torch.randn(d)
        for _ in range(5):
            v = W_rec.T @ (tanh_deriv * (W_rec @ v))
            v = v / v.norm()
        λ1_approx = torch.norm(W_rec.T @ (tanh_deriv * (W_rec @ v))) / torch.norm(v)
        
        jacobian_norms.append(λ1_approx.item())
        lyapunov_sum += np.log(max(λ1_approx.item(), 1e-10))
        
        # 状态更新
        x = torch.tanh(pre_act)
        states.append(x.clone())
    
    lyapunov_exp = lyapunov_sum / T
    
    return {
        'λ₁_max': max(jacobian_norms),
        'λ₁_mean': np.mean(jacobian_norms),
        'lyapunov_exp': lyapunov_exp,
        'is_exploding': max(jacobian_norms) > 1.5,
        'is_vanishing': np.mean(jacobian_norms) < 0.1,
    }

# 示例
W_exploding = torch.randn(100, 100) * 2   # 大权重 → 谱半径大
W_vanishing = torch.randn(100, 100) * 0.3 # 小权重 → 谱半径小
W_normal     = torch.randn(100, 100) * 1.0

print("大权重网络:", simulate_rnn_dynamics(W_exploding))
print("小权重网络:", simulate_rnn_dynamics(W_vanishing))
print("正常权重网络:", simulate_rnn_dynamics(W_normal))
```

### 论文的核心洞察：为什么梯度裁剪有效？

Pascanu 的假说（论文 2.3 节）：

```
传统观点: 高曲率峡谷 → 梯度震荡
Pascanu观点: 悬崖地貌 → 梯度爆炸是一种相变

               高曲率区域（悬崖）
                   ╱
      正常区域  ╱  梯度方向指向悬崖
    ──────────╱
              ╲
               ╲  悬崖另一侧（损失极低）
```

当参数接近分岔边界时，损失面的曲率突然急剧增大（如同悬崖边缘）。梯度裁剪等价于在悬崖边限制步长，防止一步跳到另一个吸引子盆地中。这解释了为何**裁剪只改善训练，不损害最终精度**——它不让模型"跳错盆地"。

> 📌 **数学本质**：梯度裁剪本质上是在损失面上施加了一个**信赖域约束**（Trust Region），类似于 TRPO（Schulman 2015）中的约束优化思想，但实现极简。

## 概率与统计

### 关键概率分布

| 分布 | 公式 | AI 应用 |
|------|------|---------|
| 高斯 N(μ,σ²) | exp(-(x-μ)²/2σ²) | 噪声建模，VAE |
| 伯努利 Ber(p) | p^x(1-p)^(1-x) | 二分类 |
| 多项式 Cat(π) | Ππᵢ^xᵢ | 多分类softmax |
| 狄利克雷 Dir(α) | ΠΓ(α_i)/Γ(Σα_i)·Πxᵢ^(αᵢ-1) | 主题模型 |
| 拉普拉斯 Lap(μ,b) | exp(-|x-μ|/b) | L1正则，稀疏性 |

### 最大似然估计（MLE）

```
目标: max_θ log P(data|θ) = Σ log p(xᵢ|θ)

等价于最小化负对数似然 NLL = -Σ log p(xᵢ|θ)

分类: CE Loss = -Σ y_i log ŷ_i = NLL（分类分布的MLE）
回归: MSE Loss = Σ(y-ŷ)² = NLL（高斯分布的MLE）
```

### 信息论

```
熵: H(p) = -Σ p(x) log p(x)              # 不确定性度量
交叉熵: H(p,q) = -Σ p(x) log q(x)       # 分类损失基础
KL散度: KL(p||q) = Σ p(x) log(p(x)/q(x)) # 分布距离，VAE/KD
互信息: I(X;Y) = H(X) - H(X|Y)           # 特征相关性
```

## 论文引用

- [1] **Deep Learning Book** — Goodfellow et al., "Deep Learning," MIT Press 2016. [圣经，必读]
- [2] **Matrix Cookbook** — Petersen & Pedersen, "The Matrix Cookbook," DTU 2012. [矩阵公式速查手册]
- [3] **Adam** — Kingma & Ba, "Adam: A Method for Stochastic Optimization," ICLR 2015.
- [4] **AdamW** — Loshchilov & Hutter, "Decoupled Weight Decay Regularization," ICLR 2019.
- [5] **Lion** — Chen et al., "Symbolic Discovery of Optimization Algorithms," NeurIPS 2023.
- [6] **LoRA** — Hu et al., "LoRA: Low-Rank Adaptation of Large Language Models," ICLR 2022.
- [7] **LAMB** — You et al., "Large Batch Optimization for Deep Learning: Training BERT in 76 Minutes," ICLR 2020.
- [8] **SGD分析** — Bottou, "Stochastic Gradient Descent Tricks," Neural Networks 2012.
- [9] **概率图模型** — Koller & Friedman, "Probabilistic Graphical Models," MIT Press 2009.
- [10] **信息论** — Cover & Thomas, "Elements of Information Theory," Wiley 2006.
- [11] **最优化** — Nocedal & Wright, "Numerical Optimization," Springer 2006.
- [12] **线性代数** — Strang, "Introduction to Linear Algebra," Wellesley 2016. [最佳教材]
- [13] **梯度动力学** — Pascanu, Mikolov & Bengio, "On the Difficulty of Training Recurrent Neural Networks," ICML 2013. [动力系统视角分析消失/爆炸梯度、悬崖地貌假说、Lyapunov指数，来源 [[../raw/pascanu13.pdf]]]

## 关联

- 相关概念: [[concept-deep-learning-basics]], [[concept-loss-functions]], [[concept-training-methods]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——SVD/PCA/Adam代码、链式法则、概率分布速查、信息论、12篇论文引用
- 2026-06-29: Ingest [[../raw/pascanu13.pdf]]——新增动力系统小节（吸引子/分岔边界/谱半径/Lyapunov指数模拟代码、悬崖地貌假说、信赖域类比）
