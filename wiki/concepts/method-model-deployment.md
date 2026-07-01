# 模型部署与推理加速（Model Deployment）

> **类型**: method
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

将训练好的深度学习模型部署到嵌入式设备（Jetson、RKNN、移动端）上高效运行，涉及模型压缩（量化/剪枝/蒸馏）、格式转换（ONNX/TRT/RKNN）、推理优化（TensorRT/NCNN/ONNX Runtime）等完整工程链路。

## 部署平台对比

| 平台 | 算力 | 功耗 | AI加速 | 场景 |
|------|------|------|--------|------|
| Jetson Orin NX 8G | 157 TOPS | 10-25W | DLA + GPU | 无人机首选 |
| Jetson Orin NX 16G | 157 TOPS | 10-25W | DLA + GPU | 高算力 |
| Jetson AGX Orin | 275 TOPS | 15-60W | DLA + GPU | 高端算法站 |
| Jetson Nano | 472 GFLOPS | 5-10W | GPU | 入门/教学 |
| RK3588 | 6 TOPS | 5-7W | NPU | 低成本方案 |
| RK3566 | 0.8 TOPS | 2-3W | NPU | 超低功耗 |
| Intel NUC | 无AI加速 | 15-45W | CPU/iGPU | 地面站 |
| PC with RTX | 100+ TOPS | 300W | GPU | 训练/原型 |

## 推理框架选型

| 框架 | 硬件支持 | 量化 | 性能 | 场景 |
|------|---------|------|------|------|
| TensorRT | NVIDIA GPU/Jetson | INT8/FP16 | 极高 | Jetson首选 |
| RKNN Toolkit2 | RK3588/3566/3562 | INT8 | NPU加速 | 瑞芯微平台 |
| NCNN | ARM CPU | INT8/FP16 | 高 | 移动端无GPU |
| ONNX Runtime | 多平台 | INT8 | 中高 | 跨平台通用 |
| OpenVINO | Intel CPU/iGPU/VPU | INT8 | 高 | Intel平台 |
| TFLite | ARM/Edge TPU | INT8 | 中 | 移动端/树莓派 |
| MNN | ARM/x86 | INT8/FP16 | 高 | 阿里，移动端 |

## 完整部署流程

### 第一步：模型训练（PyTorch/PaddlePaddle）

```bash
# YOLOv8 训练
yolo train model=yolov8n.pt \
  data=dataset.yaml \
  epochs=300 \
  imgsz=640 \
  batch=16 \
  device=0
```

### 第二步：导出 ONNX

```python
# PyTorch → ONNX
from ultralytics import YOLO
model = YOLO('runs/detect/train/weights/best.pt')
model.export(format='onnx', opset=12, simplify=True, imgsz=640)

# 验证 ONNX
import onnx
model_onnx = onnx.load('best.onnx')
onnx.checker.check_model(model_onnx)
print("ONNX OK, output shapes:", 
      [(o.name, list(o.type.tensor_type.shape.dim)) 
       for o in model_onnx.graph.output])
```

### 第三步A：TensorRT 转换（Jetson）

```python
import tensorrt as trt

def build_engine(onnx_path, engine_path, fp16=True, int8=False):
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    )
    parser = trt.OnnxParser(network, logger)
    
    with open(onnx_path, 'rb') as f:
        parser.parse(f.read())
    
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 30)  # 1GB
    
    if fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    if int8:
        config.set_flag(trt.BuilderFlag.INT8)
        # 需要提供 calibrator
    
    engine = builder.build_serialized_network(network, config)
    with open(engine_path, 'wb') as f:
        f.write(engine)
    print(f"Engine saved to {engine_path}")

build_engine('best.onnx', 'best.engine', fp16=True)
```

### 第三步B：RKNN 转换（RK3588）

```python
from rknn.api import RKNN

rknn = RKNN(verbose=True)

# 配置
rknn.config(
    mean_values=[[0, 0, 0]],
    std_values=[[255, 255, 255]],
    target_platform='rk3588',
    quantized_algorithm='normal',
    quantized_dtype='asymmetric_quantized-8',
)

# 加载 ONNX
rknn.load_onnx(model='best.onnx')

# 量化（需要校准集）
rknn.build(do_quantization=True, dataset='./dataset.txt')

# 导出
rknn.export_rknn('best.rknn')
rknn.release()
```

## 模型压缩技术

### 量化（Quantization）

```
训练后量化（PTQ）:
  FP32 → INT8 / FP16
  速度提升 2-4×，精度损失 <1% mAP
  方法: TensorRT calibrate / RKNN quantize
  
量化感知训练（QAT）:
  训练时模拟量化误差
  精度损失更小（0.1~0.5% mAP）
  代码: torch.quantization.prepare_qat()
  
INT8 量化效果（YOLOv8n 为例）:
  FP32: 6.2ms / 161 GFLOPS
  FP16: 3.8ms（Jetson）
  INT8: 2.1ms（Jetson + TRT）
```

### 知识蒸馏（Knowledge Distillation）

```python
"""
Teacher-Student 蒸馏：大模型（Teacher）指导小模型（Student）
损失 = α * Task Loss + (1-α) * KL(Student||Teacher)
"""
def distillation_loss(student_logits, teacher_logits, labels, 
                       T=4, alpha=0.7):
    # 软标签损失（温度缩放）
    soft_loss = nn.KLDivLoss(reduction='batchmean')(
        F.log_softmax(student_logits / T, dim=1),
        F.softmax(teacher_logits / T, dim=1)
    ) * (T ** 2)
    
    # 硬标签损失
    hard_loss = F.cross_entropy(student_logits, labels)
    
    return alpha * soft_loss + (1 - alpha) * hard_loss
```

### 剪枝（Pruning）

```python
import torch.nn.utils.prune as prune

# 非结构化剪枝（L1 范数）
prune.l1_unstructured(model.conv1, name='weight', amount=0.3)  # 剪30%

# 结构化剪枝（通道剪枝，更友好于硬件）
prune.ln_structured(model.conv1, name='weight', amount=0.3, n=2, dim=0)

# 移除剪枝掩码，使模型真正稀疏
prune.remove(model.conv1, 'weight')
```

## 实际性能参考（YOLOv8 系列，Jetson Orin NX 16G）

| 模型 | 参数量 | mAP(COCO) | FP32 FPS | FP16 FPS | INT8 FPS |
|------|--------|-----------|---------|---------|---------|
| YOLOv8n | 3.2M | 37.3 | 45 | 80 | 120 |
| YOLOv8s | 11.2M | 44.9 | 25 | 50 | 90 |
| YOLOv8m | 25.9M | 50.2 | 12 | 28 | 55 |
| YOLOv8l | 43.7M | 52.9 | 7 | 18 | 38 |
| YOLOv8x | 68.2M | 53.9 | 4 | 12 | 25 |

## 论文引用

- [1] **TensorRT** — NVIDIA TensorRT Documentation 2024. [官方部署框架]
- [2] **知识蒸馏** — Hinton et al., "Distilling the Knowledge in a Neural Network," NeurIPS Workshop 2014. [经典蒸馏]
- [3] **量化综述** — Gholami et al., "A Survey of Quantization Methods for Efficient Neural Network Inference," 2021.
- [4] **剪枝综述** — Cheng et al., "A Survey on Deep Neural Network Pruning: Taxonomy, Comparison, Analysis, and Recommendations," TPAMI 2024.
- [5] **ONNX** — ONNX Community, "ONNX: Open Neural Network Exchange," 2019.
- [6] **MobileNet** — Howard et al., "MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications," arXiv 2017.
- [7] **EfficientNet** — Tan & Le, "EfficientNet: Rethinking Model Scaling for CNNs," ICML 2019.
- [8] **NAS** — Zoph & Le, "Neural Architecture Search with Reinforcement Learning," ICLR 2017.
- [9] **Once-for-All** — Cai et al., "Once-for-All: Train One Network and Specialize it for Efficient Deployment," ICLR 2020.
- [10] **Slim** — Liu et al., "Learning Efficient Convolutional Networks through Network Slimming," ICCV 2017. [通道剪枝经典]
- [11] **QAT** — Jacob et al., "Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference," CVPR 2018.
- [12] **NCNN** — Tencent NCNN, "NCNN: A High-Performance Neural Network Inference Framework," GitHub 2019.

## 关联

- 相关概念: [[concept-object-detection]], [[concept-deep-learning-basics]], [[concept-training-methods]]
- 相关实体: [[entities/product-px4-autopilot]]
- 参见项目: [[topics/topic-license-plate-recognition]], [[topics/topic-crack-detection]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——平台对比、框架选型、完整TRT/RKNN代码、量化/蒸馏/剪枝代码、性能参考表、12篇论文引用
