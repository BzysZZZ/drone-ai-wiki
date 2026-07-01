# 模型评估体系（Model Evaluation）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

科学评估模型是工程闭环的关键。掌握检测（mAP/AR）、分割（mIoU/Dice）、分类（Acc/F1/AUC）、定位（ATE/RPE）等多场景指标体系，能让你在与客户、团队沟通时说清楚模型的真实能力。

## 目标检测指标

### mAP 完整计算流程

```python
def compute_map(predictions, ground_truths, iou_threshold=0.5, num_classes=80):
    """
    AP = 11点插值法 或 全点积分（COCO标准）
    mAP = 所有类别 AP 的平均值
    """
    ap_per_class = []
    
    for cls in range(num_classes):
        # 1. 收集该类所有预测结果，按置信度降序排列
        cls_preds = [(score, pred_box, gt_matched) 
                     for score, pred_box, cls_id in predictions 
                     if cls_id == cls]
        cls_preds.sort(key=lambda x: -x[0])
        
        # 2. 计算累积 TP/FP
        TPs = np.zeros(len(cls_preds))
        FPs = np.zeros(len(cls_preds))
        n_gt = sum(1 for gt in ground_truths if gt['class'] == cls)
        
        for i, (score, pred_box, _) in enumerate(cls_preds):
            best_iou, best_gt = 0, None
            for gt in ground_truths:
                if gt['class'] != cls or gt.get('matched'): continue
                iou = compute_iou(pred_box, gt['box'])
                if iou > best_iou:
                    best_iou, best_gt = iou, gt
            
            if best_iou >= iou_threshold and best_gt:
                TPs[i] = 1
                best_gt['matched'] = True
            else:
                FPs[i] = 1
        
        # 3. 累积 → Precision-Recall 曲线
        cum_TP = np.cumsum(TPs)
        cum_FP = np.cumsum(FPs)
        recall = cum_TP / (n_gt + 1e-9)
        precision = cum_TP / (cum_TP + cum_FP + 1e-9)
        
        # 4. 计算 AP（11点插值）
        ap = 0
        for thr in np.linspace(0, 1, 11):
            p_at_r = precision[recall >= thr].max() if (recall >= thr).any() else 0
            ap += p_at_r / 11
        ap_per_class.append(ap)
    
    return np.mean(ap_per_class)  # mAP
```

### COCO 指标速查

| 指标 | 含义 | IoU阈值 | 尺度 |
|------|------|---------|------|
| AP | COCO标准AP | 0.5:0.05:0.95均值 | all |
| AP50 | 宽松AP | 0.5 | all |
| AP75 | 严格AP | 0.75 | all |
| APs | 小目标AP | COCO标准 | <32²px |
| APm | 中目标AP | COCO标准 | 32²~96²px |
| APl | 大目标AP | COCO标准 | >96²px |
| AR1 | 每图1个目标召回率 | COCO标准 | all |
| AR100 | 每图100个目标召回率 | COCO标准 | all |

### 混淆矩阵

```python
def compute_confusion_matrix(preds, labels, num_classes):
    """
    行: 真实类别
    列: 预测类别
    对角线: 正确预测数量
    """
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for pred, label in zip(preds, labels):
        cm[label][pred] += 1
    return cm

# 从混淆矩阵推导指标
def metrics_from_cm(cm):
    TP = np.diag(cm)
    FP = cm.sum(0) - TP
    FN = cm.sum(1) - TP
    TN = cm.sum() - (TP + FP + FN)
    
    precision = TP / (TP + FP + 1e-9)
    recall    = TP / (TP + FN + 1e-9)
    f1        = 2 * precision * recall / (precision + recall + 1e-9)
    return precision, recall, f1
```

## 分割指标

```python
def compute_iou_dice(pred_mask, target_mask, eps=1e-6):
    """
    IoU（Jaccard Index）= |A∩B| / |A∪B|
    Dice = 2|A∩B| / (|A| + |B|)
    关系: IoU = Dice / (2 - Dice)
    """
    pred_flat = pred_mask.flatten().bool()
    target_flat = target_mask.flatten().bool()
    
    intersection = (pred_flat & target_flat).sum().float()
    union        = (pred_flat | target_flat).sum().float()
    
    iou  = (intersection + eps) / (union + eps)
    dice = (2 * intersection + eps) / (pred_flat.sum() + target_flat.sum() + eps)
    
    return iou.item(), dice.item()

# mIoU = 所有类别 IoU 的平均值
def miou(pred, target, num_classes):
    ious = []
    for cls in range(num_classes):
        pred_cls = pred == cls
        target_cls = target == cls
        if target_cls.sum() == 0: continue  # 跳过不存在的类
        iou, _ = compute_iou_dice(pred_cls, target_cls)
        ious.append(iou)
    return np.mean(ious)
```

## SLAM/定位指标

```python
def ate_rpe(pred_poses, gt_poses):
    """
    ATE（绝对轨迹误差）: 全局对齐后的 RMSE
    RPE（相对轨迹误差）: 局部段的相对误差，反映漂移速率
    """
    # ATE（使用 Horn 方法对齐）
    pred_aligned = align_trajectories(pred_poses, gt_poses)
    ate = np.sqrt(np.mean(np.sum((pred_aligned - gt_poses)**2, axis=1)))
    
    # RPE（delta = 1 step）
    delta = 1
    rpe_trans = []
    for i in range(len(gt_poses) - delta):
        T_gt = relative_pose(gt_poses[i], gt_poses[i+delta])
        T_pred = relative_pose(pred_poses[i], pred_poses[i+delta])
        error = np.linalg.inv(T_gt) @ T_pred
        trans_error = np.linalg.norm(error[:3, 3])
        rpe_trans.append(trans_error)
    
    return ate, np.sqrt(np.mean(np.array(rpe_trans)**2))
```

## 推理性能指标

```python
def measure_inference_performance(model, input_tensor, n_runs=1000, warm_up=100):
    """
    测量推理延迟和吞吐量
    注意: 必须 warm up，避免 GPU 冷启动误差
    """
    model.eval()
    device = next(model.parameters()).device
    
    # Warmup
    with torch.no_grad():
        for _ in range(warm_up):
            _ = model(input_tensor)
    
    # 正式计时（同步 GPU）
    torch.cuda.synchronize()
    start = time.perf_counter()
    
    with torch.no_grad():
        for _ in range(n_runs):
            _ = model(input_tensor)
            torch.cuda.synchronize()
    
    elapsed = time.perf_counter() - start
    latency_ms = elapsed / n_runs * 1000
    fps = n_runs / elapsed
    
    print(f"Latency: {latency_ms:.2f} ms | FPS: {fps:.1f}")
    return latency_ms, fps
```

## 指标选择建议

| 任务 | 主指标 | 辅助指标 | 工程指标 |
|------|--------|---------|---------|
| 通用检测 | mAP@0.5:0.95 | AP50, AP75 | FPS, Params |
| 小目标检测 | AP_s | mAP@0.5 | SAHI加速比 |
| 实例分割 | mask AP | box AP | FPS |
| 语义分割 | mIoU | Pixel Acc, Dice | FPS |
| 精准定位 | CEP50(cm) | ATE(m), RPE | 更新频率 |
| 分类 | Top-1 Acc | Top-5, F1, AUC | 推理时间 |
| 识别（OCR） | Char Acc | Seq Acc | TPS(字/秒) |

## 论文引用

- [1] **COCO指标** — Lin et al., "Microsoft COCO: Common Objects in Context," ECCV 2014. [业界标准]
- [2] **VOC mAP** — Everingham et al., "The PASCAL VOC Challenge 2010–2012 Results," IJCV 2015.
- [3] **ATE/RPE** — Sturm et al., "A Benchmark for the Evaluation of RGB-D SLAM Systems," IROS 2012. [SLAM评估标准]
- [4] **Semantic Segmentation** — Long et al., "Fully Convolutional Networks for Semantic Segmentation," CVPR 2015.
- [5] **Precision-Recall** — Davis & Goadrich, "The Relationship Between Precision-Recall and ROC Curves," ICML 2006.
- [6] **F1 Score综述** — Lipton et al., "Thresholding Classifiers to Maximize F1 Score," ECML 2014.
- [7] **Confusion Matrix** — Powers, "Evaluation: From Precision, Recall and F-Measure to ROC, Informedness, Markedness & Correlation," JMLR 2011.
- [8] **SLAM Benchmark** — Geiger et al., "Are We Ready for Autonomous Driving? The KITTI Vision Benchmark Suite," CVPR 2012.

## 关联

- 相关概念: [[concept-loss-functions]], [[concept-object-detection]], [[concept-hyperparameter-tuning]]
- 参见: [[topics/topic-license-plate-recognition]], [[topics/topic-crack-detection]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——mAP完整计算代码、COCO指标速查表、混淆矩阵、分割指标代码、SLAM指标代码、推理性能测量、8篇论文引用
