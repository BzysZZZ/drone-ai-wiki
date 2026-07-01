# 经典骨干网络谱系（CV Classic Backbones）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

骨干网络（Backbone）是视觉任务的特征提取器，其设计哲学从手工设计（VGG/ResNet）演化到自动搜索（NAS/EfficientNet）再到纯Transformer（ViT/Swin），深刻理解各代架构的核心创新是 CV 工程师必备能力。

## 发展脉络

```
2012 AlexNet → 2014 VGG/GoogLeNet → 2015 ResNet → 2017 DenseNet
    ↓ 轻量化方向
2017 MobileNetV1 → 2018 MobileNetV2 → 2019 EfficientNet → 2021 MobileNetV3
    ↓ NAS方向
2017 NASNet → 2019 EfficientNet-NAS
    ↓ Transformer方向
2020 ViT → 2021 Swin Transformer → 2022 ConvNeXt → 2024 ViT-22B
    ↓ 混合方向
2021 CoAtNet → 2022 MaxViT → 2023 InternImage
```

## 重要架构详解

### ResNet（残差网络）—— 最重要的基础架构

```python
class ResidualBlock(nn.Module):
    """
    核心创新：跳连接（Skip Connection）
    解决问题：深层网络退化（degradation problem）
    
    为什么有效？
    1. 梯度高速公路：梯度直接通过跳连接传回早期层
    2. 恒等映射：网络至少能学到恒等变换，不会"退化"
    3. 残差容易学：学 F(x)=0 比学 H(x)=x 容易
    """
    def __init__(self, channels, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, stride, 1, bias=False)
        self.bn1   = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, 1, 1, bias=False)
        self.bn2   = nn.BatchNorm2d(channels)
        self.relu  = nn.ReLU(inplace=True)
        # 下采样：保持残差维度一致
        self.shortcut = nn.Sequential(
            nn.Conv2d(channels, channels, 1, stride, bias=False),
            nn.BatchNorm2d(channels)
        ) if stride != 1 else nn.Identity()
    
    def forward(self, x):
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)   # 关键：加法跳连接
        return self.relu(out)
```

### Bottleneck（ResNet50/101/152 使用）

```python
class Bottleneck(nn.Module):
    """
    1×1 → 3×3 → 1×1 设计
    参数量: 256→64→64→256 vs 256→256 直接3×3
    节省参数约 4× ，计算量减少约 9×
    """
    expansion = 4
    def __init__(self, in_ch, out_ch, stride=1):
        super().__init__()
        mid_ch = out_ch // self.expansion
        self.conv1 = nn.Conv2d(in_ch, mid_ch, 1, bias=False)
        self.bn1   = nn.BatchNorm2d(mid_ch)
        self.conv2 = nn.Conv2d(mid_ch, mid_ch, 3, stride, 1, bias=False)
        self.bn2   = nn.BatchNorm2d(mid_ch)
        self.conv3 = nn.Conv2d(mid_ch, out_ch, 1, bias=False)
        self.bn3   = nn.BatchNorm2d(out_ch)
        self.relu  = nn.ReLU(inplace=True)
```

### MobileNet（深度可分离卷积）

```python
class DepthwiseSeparableConv(nn.Module):
    """
    深度可分离卷积 = Depthwise + Pointwise
    参数量对比（k=3, Cin=Cout=C）:
      标准卷积: k²×C×C = 9C²
      深度可分离: k²×C + C×C = 9C + C²
      节省比例: ≈ 1/9 (当C>>1时)
    """
    def __init__(self, in_ch, out_ch, stride=1):
        super().__init__()
        self.dw = nn.Conv2d(in_ch, in_ch, 3, stride, 1, groups=in_ch, bias=False)
        self.pw = nn.Conv2d(in_ch, out_ch, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(in_ch)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU6(inplace=True)
    
    def forward(self, x):
        x = self.relu(self.bn1(self.dw(x)))
        return self.relu(self.bn2(self.pw(x)))

# MobileNetV2 新增：倒残差（Inverted Residuals）+ Linear Bottleneck
# 1×1升维（×6） → 3×3 DW → 1×1降维，最后不用激活
```

### CSPNet（YOLO系列广泛使用）

```python
"""
Cross Stage Partial Network
将特征图分两路：
  主路: 经过卷积处理
  支路: 直接连接
在通道维度拼接 → 减少计算量 ~50%，保持精度
YOLO v4/5/7/8 均使用 CSP 变种
"""
class CSPBlock(nn.Module):
    def __init__(self, channels, n=1):
        super().__init__()
        half = channels // 2
        self.conv1 = Conv(channels, half, 1)   # 主路
        self.conv2 = Conv(channels, half, 1)   # 支路
        self.m = nn.Sequential(*[ResidualBlock(half) for _ in range(n)])
        self.conv3 = Conv(half * 2, channels, 1)
    
    def forward(self, x):
        return self.conv3(torch.cat([self.m(self.conv1(x)), self.conv2(x)], 1))
```

### Vision Transformer（ViT）核心

```python
class PatchEmbedding(nn.Module):
    """将图像切成 patch，映射为 token"""
    def __init__(self, img_size=224, patch_size=16, in_ch=3, embed_dim=768):
        super().__init__()
        self.num_patches = (img_size // patch_size) ** 2
        # 等价于步长为 patch_size 的大卷积
        self.proj = nn.Conv2d(in_ch, embed_dim, patch_size, patch_size)
    
    def forward(self, x):
        x = self.proj(x)           # (B, embed_dim, H/p, W/p)
        return x.flatten(2).T      # (B, num_patches, embed_dim)
```

## 骨干网络性能速查表

| 骨干 | Params | FLOPs | ImageNet Top-1 | 适用场景 |
|------|--------|-------|----------------|---------|
| ResNet-18 | 11.7M | 1.8G | 69.8% | 轻量嵌入式 |
| ResNet-50 | 25.6M | 4.1G | 76.1% | 通用基准 |
| ResNet-101 | 44.5M | 7.8G | 77.4% | 高精度 |
| MobileNetV2 | 3.4M | 300M | 72.0% | 移动端 |
| EfficientNet-B0 | 5.3M | 0.4G | 77.1% | 效率最优 |
| EfficientNet-B7 | 66M | 37G | 84.3% | 高精度 |
| ViT-B/16 | 86M | 17.6G | 81.8% | NLP迁移 |
| Swin-T | 28M | 4.5G | 81.3% | 下游任务友好 |
| ConvNeXt-T | 28M | 4.5G | 82.1% | CNN反击 |
| InternImage-T | 30M | 5G | 83.5% | DCN+Transformer |

## 论文引用

- [1] **AlexNet** — Krizhevsky et al., "ImageNet Classification with Deep Convolutional Neural Networks," NeurIPS 2012.
- [2] **VGG** — Simonyan & Zisserman, "Very Deep Convolutional Networks for Large-Scale Image Recognition," ICLR 2015.
- [3] **ResNet** — He et al., "Deep Residual Learning for Image Recognition," CVPR 2016. [必读，最重要]
- [4] **DenseNet** — Huang et al., "Densely Connected Convolutional Networks," CVPR 2017.
- [5] **MobileNetV1** — Howard et al., "MobileNets: Efficient CNNs for Mobile Vision Applications," arXiv 2017.
- [6] **MobileNetV2** — Sandler et al., "MobileNetV2: Inverted Residuals and Linear Bottlenecks," CVPR 2018.
- [7] **EfficientNet** — Tan & Le, "EfficientNet: Rethinking Model Scaling for CNNs," ICML 2019.
- [8] **ViT** — Dosovitskiy et al., "An Image is Worth 16×16 Words," ICLR 2021. [Transformer视觉]
- [9] **Swin Transformer** — Liu et al., "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows," ICCV 2021.
- [10] **ConvNeXt** — Liu et al., "A ConvNet for the 2020s," CVPR 2022. [CNN重新设计]
- [11] **CSPNet** — Wang et al., "CSPNet: A New Backbone That Can Enhance Learning Capability of CNN," CVPR-W 2020.
- [12] **InternImage** — Wang et al., "InternImage: Exploring Large-Scale Vision Foundation Models with Deformable Convolutions," CVPR 2023.
- [13] **GoogLeNet/Inception** — Szegedy et al., "Going Deeper with Convolutions," CVPR 2015.
- [14] **SENet** — Hu et al., "Squeeze-and-Excitation Networks," CVPR 2018. [通道注意力]
- [15] **RepVGG** — Ding et al., "RepVGG: Making VGG-style ConvNets Great Again," CVPR 2021.

## 关联

- 相关概念: [[concept-deep-learning-basics]], [[concept-object-detection]], [[concept-training-methods]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——ResNet/Bottleneck/MobileNet/CSP/ViT完整代码、发展脉络图、性能速查表、15篇论文引用
