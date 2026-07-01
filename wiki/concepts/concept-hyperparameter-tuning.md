# 超参数调优（Hyperparameter Tuning）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

超参数调优是将模型从"能跑"推向"跑好"的关键工程环节。掌握学习率诊断、Optuna自动搜索、正则化策略、Batch Size选择等技巧，能系统性地提升模型精度和训练稳定性。

## 关键超参数速查

### 最常调的参数

| 超参数 | 推荐默认值 | 影响 | 调整方向 |
|--------|----------|------|---------|
| Learning Rate | 1e-3 (Adam) | 最大 | 先LR Range Test |
| Batch Size | 16~64 | 大 | 越大越稳定，但收益递减 |
| Epochs | 按数据量 | 中 | 早停+验证集监控 |
| Weight Decay | 1e-4 ~ 1e-2 | 中 | 过拟合时增大 |
| Dropout | 0.1~0.5 | 中 | 过拟合时增大 |
| Warmup Steps | 5% total | 中 | Transformer必须 |
| Momentum | 0.937 (SGD) | 中 | YOLO标配值 |
| Label Smoothing | 0.1 | 小 | 分类任务小加 |

## 学习率诊断

### Learning Rate Range Test（LR Finder）

```python
from torch.optim.lr_scheduler import ExponentialLR

def lr_range_test(model, dataloader, optimizer, start_lr=1e-7, end_lr=1.0, num_steps=100):
    """
    1. LR 从极小值指数增大
    2. 记录每步 loss
    3. loss 开始发散前的 LR 的 1/10 作为最优 LR
    """
    lrs, losses = [], []
    factor = (end_lr / start_lr) ** (1 / num_steps)
    
    for param_group in optimizer.param_groups:
        param_group['lr'] = start_lr
    
    scheduler = ExponentialLR(optimizer, gamma=factor)
    
    for step, batch in enumerate(dataloader):
        if step >= num_steps: break
        
        optimizer.zero_grad()
        loss = compute_loss(model, batch)
        loss.backward()
        optimizer.step()
        scheduler.step()
        
        lrs.append(optimizer.param_groups[0]['lr'])
        losses.append(loss.item())
    
    # 选最优 LR（梯度最大处）
    smooth_losses = np.convolve(losses, np.ones(5)/5, mode='valid')
    steepest_idx = np.gradient(smooth_losses).argmin()
    best_lr = lrs[steepest_idx] / 10  # 取发散前的 1/10
    
    return best_lr, lrs, smooth_losses
```

### 常见训练曲线诊断

```
Loss 曲线异常 → 原因分析：

① Train Loss↓  Val Loss↑（过拟合）
   → 增大Dropout/Weight Decay，减小模型，增多数据

② Train Loss↓  Val Loss ↓→ 平台（欠拟合）
   → 增大模型，降低正则，增加epochs

③ Loss 震荡剧烈
   → 降低 LR，增大 Batch Size，检查数据标注

④ Loss 开始就不降
   → LR太小/太大，检查梯度（是否为0），检查数据pipeline

⑤ Loss NaN
   → LR太大，梯度爆炸（加梯度裁剪），检查数据中是否有异常值
```

## Optuna 自动调优

```python
import optuna

def objective(trial):
    """Optuna 贝叶斯优化搜索超参数"""
    # 定义搜索空间
    lr = trial.suggest_float('lr', 1e-5, 1e-2, log=True)
    weight_decay = trial.suggest_float('wd', 1e-5, 1e-1, log=True)
    dropout = trial.suggest_float('dropout', 0.1, 0.5)
    batch_size = trial.suggest_categorical('batch_size', [8, 16, 32, 64])
    optimizer_name = trial.suggest_categorical('optimizer', ['Adam', 'AdamW', 'SGD'])
    
    # 构建模型
    model = build_model(dropout=dropout).to(device)
    optimizer = getattr(torch.optim, optimizer_name)(
        model.parameters(), lr=lr, weight_decay=weight_decay
    )
    
    # 训练 N 个 epoch
    val_map = train_and_evaluate(model, optimizer, batch_size, n_epochs=10)
    return val_map  # 最大化 mAP

# 运行搜索
study = optuna.create_study(
    direction='maximize',
    sampler=optuna.samplers.TPESampler(),      # 贝叶斯优化
    pruner=optuna.pruners.MedianPruner(n_startup_trials=5)  # 早停差组合
)
study.optimize(objective, n_trials=50, n_jobs=4)

print("Best params:", study.best_params)
print("Best mAP:", study.best_value)

# 可视化
optuna.visualization.plot_optimization_history(study)
optuna.visualization.plot_param_importances(study)
```

## Batch Size 策略

```
线性缩放法则（Goyal et al. 2017）:
  batch 翻倍 → LR 翻倍
  batch: 32 → LR: 1e-3
  batch: 256 → LR: 8e-3

Batch Size 与精度关系:
  太小（<8）: 梯度噪声大，BN统计不准，训练不稳定
  适中（16~64）: 最佳平衡点
  太大（>1024）: 泛化性能下降（sharp minima），需要更多trick

解决大 Batch 泛化问题:
  - LARS / LAMB 优化器
  - 更长 Warmup
  - Mixup/正则化加强
```

## 正则化策略决策树

```
模型过拟合？
├── Yes:
│   ├── 数据不足？→ 数据增强 + 预训练迁移
│   ├── 模型太大？→ 剪枝 + 减少层数
│   ├── 训练过长？→ 早停（EarlyStopping）
│   └── 正则不足？→ 增大 Weight Decay + Dropout
└── No (欠拟合):
    ├── 模型太小？→ 增加参数量
    ├── 训练不足？→ 增加 Epochs
    ├── LR 太小？→ 增大 LR，配合 Warmup
    └── 特征不够？→ 增加输入分辨率，多尺度
```

## 迁移学习策略

```python
# 分层学习率（骨干 LR << 头部 LR）
def get_layerwise_lr(model, backbone_lr=1e-4, head_lr=1e-3):
    backbone_params = [p for n, p in model.named_parameters() 
                       if 'backbone' in n]
    head_params = [p for n, p in model.named_parameters() 
                   if 'backbone' not in n]
    return [
        {'params': backbone_params, 'lr': backbone_lr},
        {'params': head_params,     'lr': head_lr},
    ]

optimizer = AdamW(get_layerwise_lr(model), weight_decay=1e-4)

# 渐进解冻（Progressive Unfreezing）
# 第1阶段: 冻结骨干，只训练头部（5 epoch）
# 第2阶段: 解冻最后几层骨干（10 epoch）
# 第3阶段: 全部解冻，小 LR 微调（20 epoch）
```

## 论文引用

- [1] **Hyperparameter Optimization** — Bergstra & Bengio, "Random Search for Hyper-Parameter Optimization," JMLR 2012.
- [2] **贝叶斯优化** — Snoek et al., "Practical Bayesian Optimization of Machine Learning Algorithms," NeurIPS 2012.
- [3] **LR Range Test** — Smith, "Cyclical Learning Rates for Training Neural Networks," WACV 2017.
- [4] **线性缩放** — Goyal et al., "Accurate, Large Minibatch SGD: Training ImageNet in 1 Hour," arXiv 2017.
- [5] **Sharp/Flat Minima** — Keskar et al., "On Large-Batch Training for Deep Learning," ICLR 2017.
- [6] **Optuna** — Akiba et al., "Optuna: A Next-generation Hyperparameter Optimization Framework," KDD 2019.
- [7] **迁移学习** — Pan & Yang, "A Survey on Transfer Learning," IEEE TKDE 2010.
- [8] **渐进解冻** — Howard & Ruder, "Universal Language Model Fine-tuning for Text Classification," ACL 2018. [ULMFiT]
- [9] **Early Stopping** — Prechelt, "Early Stopping — But When?" Neural Networks 1998.
- [10] **LARS** — You et al., "Large Batch Training of Convolutional Networks," arXiv 2017.
- [11] **Warmup分析** — Ma & Yarats, "Quasi-Hyperbolic Momentum and Adam for Deep Learning," ICLR 2019.

## 关联

- 相关概念: [[concept-math-foundation]], [[concept-training-methods]], [[concept-model-evaluation]]
- 参见: [[concept-ai-interview-qa]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——LR Range Test代码、训练曲线诊断、Optuna完整代码、Batch Size分析、正则化决策树、分层LR代码、11篇论文引用
