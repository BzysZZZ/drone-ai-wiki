# 损失函数大全（Loss Functions）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

损失函数决定了模型的优化目标，直接影响训练结果。AI 算法工程师需要掌握分类、检测、分割、回归、对比学习等各场景的损失函数，并能根据任务特点设计组合损失。

## 分类损失

### 交叉熵（Cross Entropy）

```python
# 二分类（Sigmoid + BCE）
def binary_cross_entropy(y_pred, y_true):
    """y_pred: logits, y_true: 0/1"""
    return F.binary_cross_entropy_with_logits(y_pred, y_true.float())

# 多分类（Softmax + CE）
def cross_entropy(logits, labels):
    """等价于 NLLLoss(log_softmax(logits), labels)"""
    return F.cross_entropy(logits, labels)

# 手动实现
def ce_manual(logits, labels):
    log_probs = logits - logits.logsumexp(dim=-1, keepdim=True)
    return -log_probs[range(len(labels)), labels].mean()
```

### Focal Loss（解决类别不平衡）

```python
class FocalLoss(nn.Module):
    """
    FL = -α_t × (1-p_t)^γ × log(p_t)
    γ=2 时：easy sample 权重缩小 ~4×，hard sample 保持
    α=0.25 平衡正负样本比例
    """
    def __init__(self, alpha=0.25, gamma=2.0, reduction='mean'):
        super().__init__()
        self.alpha, self.gamma, self.reduction = alpha, gamma, reduction
    
    def forward(self, pred, target):
        bce = F.binary_cross_entropy_with_logits(pred, target, reduction='none')
        p = torch.sigmoid(pred)
        p_t = p * target + (1 - p) * (1 - target)
        alpha_t = self.alpha * target + (1 - self.alpha) * (1 - target)
        focal_weight = alpha_t * (1 - p_t) ** self.gamma
        loss = focal_weight * bce
        return loss.mean() if self.reduction == 'mean' else loss.sum()
```

### Label Smoothing CE

```python
def label_smoothing_loss(logits, targets, smoothing=0.1, n_classes=80):
    """
    硬标签 → 软标签: 1 → 1-ε, 0 → ε/(C-1)
    防止过于自信，提升泛化
    """
    confidence = 1.0 - smoothing
    smooth_val = smoothing / (n_classes - 1)
    
    log_probs = F.log_softmax(logits, dim=-1)
    # 构造软标签
    soft_targets = torch.full_like(log_probs, smooth_val)
    soft_targets.scatter_(1, targets.unsqueeze(1), confidence)
    
    return -(soft_targets * log_probs).sum(dim=-1).mean()
```

## 检测损失（目标检测专项）

### IoU 系列损失

```python
def ciou_loss(pred_boxes, target_boxes, eps=1e-9):
    """
    CIoU = IoU - ρ²(b,bᵍᵗ)/c² - αv
    其中:
      ρ²: 中心点距离²
      c²: 最小外接矩形对角线²
      v = 4/π² × (arctan(w_gt/h_gt) - arctan(w/h))²
      α = v / (1 - IoU + v)
    """
    # 预测框 (cx, cy, w, h) 转 (x1,y1,x2,y2)
    pb = box_cxcywh_to_xyxy(pred_boxes)
    tb = box_cxcywh_to_xyxy(target_boxes)
    
    # 交集
    inter_x1 = torch.max(pb[:, 0], tb[:, 0])
    inter_y1 = torch.max(pb[:, 1], tb[:, 1])
    inter_x2 = torch.min(pb[:, 2], tb[:, 2])
    inter_y2 = torch.min(pb[:, 3], tb[:, 3])
    inter_area = (inter_x2 - inter_x1).clamp(0) * (inter_y2 - inter_y1).clamp(0)
    
    pb_area = (pb[:, 2]-pb[:, 0]) * (pb[:, 3]-pb[:, 1])
    tb_area = (tb[:, 2]-tb[:, 0]) * (tb[:, 3]-tb[:, 1])
    union = pb_area + tb_area - inter_area + eps
    iou = inter_area / union
    
    # 最小外接矩形
    enclose_x1 = torch.min(pb[:, 0], tb[:, 0])
    enclose_y1 = torch.min(pb[:, 1], tb[:, 1])
    enclose_x2 = torch.max(pb[:, 2], tb[:, 2])
    enclose_y2 = torch.max(pb[:, 3], tb[:, 3])
    c2 = (enclose_x2-enclose_x1)**2 + (enclose_y2-enclose_y1)**2 + eps
    
    # 中心点距离
    pcx, pcy = (pb[:, 0]+pb[:, 2])/2, (pb[:, 1]+pb[:, 3])/2
    tcx, tcy = (tb[:, 0]+tb[:, 2])/2, (tb[:, 1]+tb[:, 3])/2
    rho2 = (pcx-tcx)**2 + (pcy-tcy)**2
    
    # 宽高比
    pw, ph = pb[:, 2]-pb[:, 0], pb[:, 3]-pb[:, 1]
    tw, th = tb[:, 2]-tb[:, 0], tb[:, 3]-tb[:, 1]
    v = (4 / math.pi**2) * (torch.atan(tw/th.clamp(eps)) - torch.atan(pw/ph.clamp(eps)))**2
    alpha = v / (1 - iou + v + eps)
    
    ciou = iou - rho2/c2 - alpha*v
    return (1 - ciou).mean()
```

## 分割损失

### Dice Loss

```python
def dice_loss(pred, target, smooth=1.0):
    """
    Dice = 2|A∩B| / (|A| + |B|)
    Dice Loss = 1 - Dice
    特别适合类别不平衡的分割（如裂缝检测）
    """
    pred = torch.sigmoid(pred).flatten(1)
    target = target.flatten(1)
    intersection = (pred * target).sum(1)
    dice = (2. * intersection + smooth) / (pred.sum(1) + target.sum(1) + smooth)
    return (1 - dice).mean()

# 组合损失（裂缝检测常用）
def bce_dice_loss(pred, target, bce_weight=0.5):
    bce = F.binary_cross_entropy_with_logits(pred, target)
    dice = dice_loss(pred, target)
    return bce_weight * bce + (1 - bce_weight) * dice
```

## 回归损失

| 损失 | 公式 | 特点 | 使用场景 |
|------|------|------|---------|
| MSE | (y-ŷ)² | 对离群值敏感 | 坐标回归 |
| MAE/L1 | |y-ŷ| | 对离群值鲁棒 | 深度估计 |
| Huber/Smooth L1 | <δ用L2，≥δ用L1 | 两者平衡 | RCNN框回归 |
| Log-Cosh | log(cosh(y-ŷ)) | 近似Huber，可导 | 通用回归 |

## 对比学习损失

### InfoNCE / NT-Xent（SimCLR）

```python
def nt_xent_loss(z1, z2, temperature=0.5):
    """
    同一图像的两个增强视图相互为正样本
    批内其他样本为负样本
    """
    z1 = F.normalize(z1, dim=1)
    z2 = F.normalize(z2, dim=1)
    
    N = z1.shape[0]
    z = torch.cat([z1, z2], dim=0)  # (2N, d)
    
    # 相似度矩阵
    sim = z @ z.T / temperature  # (2N, 2N)
    
    # 移除对角线自身相似度
    sim.fill_diagonal_(-float('inf'))
    
    # 正样本 index
    labels = torch.cat([torch.arange(N, 2*N), torch.arange(0, N)]).to(z.device)
    
    return F.cross_entropy(sim, labels)
```

## 损失权重调节

```python
# 不确定性加权多任务损失（Kendall et al. 2018）
class UncertaintyWeightedLoss(nn.Module):
    def __init__(self, n_tasks=3):
        super().__init__()
        # 可学习的不确定性参数（log σ²）
        self.log_vars = nn.Parameter(torch.zeros(n_tasks))
    
    def forward(self, losses):
        """
        Loss = Σᵢ exp(-log_var_i) * L_i + log_var_i
        等价于: L_i / (2σᵢ²) + log σᵢ
        """
        total = 0
        for i, loss in enumerate(losses):
            precision = torch.exp(-self.log_vars[i])
            total += precision * loss + self.log_vars[i]
        return total
```

## 论文引用

- [1] **Focal Loss** — Lin et al., "Focal Loss for Dense Object Detection," ICCV 2017. [目标检测必读]
- [2] **GIoU** — Rezatofighi et al., "Generalized Intersection over Union," CVPR 2019.
- [3] **DIoU/CIoU** — Zheng et al., "Distance-IoU Loss," AAAI 2020.
- [4] **WIoU** — Tong et al., "Wise-IoU: Bounding Box Regression Loss with Dynamic Focusing Mechanism," arXiv 2023.
- [5] **Dice Loss** — Milletari et al., "V-Net: Fully Convolutional Neural Networks for Volumetric Medical Image Segmentation," 3DV 2016.
- [6] **Label Smoothing** — Szegedy et al., "Rethinking the Inception Architecture," CVPR 2016.
- [7] **SimCLR** — Chen et al., "A Simple Framework for Contrastive Learning of Visual Representations," ICML 2020.
- [8] **InfoNCE** — van den Oord et al., "Representation Learning with Contrastive Predictive Coding," arXiv 2018.
- [9] **多任务不确定性** — Kendall et al., "Multi-Task Learning Using Uncertainty to Weigh Losses," CVPR 2018.
- [10] **Tversky Loss** — Salehi et al., "Tversky Loss Function for Image Segmentation," MICCAI 2017. [分割不平衡]
- [11] **VFL** — Zhang et al., "VarifocalNet: An IoU-aware Dense Object Detector," CVPR 2021.
- [12] **OKS Loss** — 关键点检测标准损失，COCO Pose 2016.

## 关联

- 相关概念: [[concept-math-foundation]], [[concept-model-evaluation]], [[concept-object-detection]]
- 参见项目: [[topics/topic-crack-detection]], [[topics/topic-license-plate-recognition]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——CE/FocalLoss/CIoU/Dice完整代码、对比学习损失、不确定性加权、12篇论文引用
