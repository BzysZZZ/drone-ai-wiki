#!/usr/bin/env python3
"""YOLOv4 单文件教学复现：复制本文件、安装依赖后即可独立运行。

无参数运行会使用合成数据完成前向、损失和反向传播，不下载权重，也不要求数据集。
真实训练支持 VOC XML 与通用 YOLO 文本标注。代码优先表达算法结构，适合学习和实验，
没有加入分布式训练、混合精度或部署优化。
"""

from __future__ import annotations

import argparse
import math
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw
import torch
from torch import Tensor, nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


DEFAULT_ANCHORS = (
    ((116, 90), (156, 198), (373, 326)),
    ((30, 61), (62, 45), (59, 119)),
    ((10, 13), (16, 30), (33, 23)),
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def xywh_to_xyxy(boxes: Tensor) -> Tensor:
    """把中心点格式 ``cx,cy,w,h`` 转为左上右下格式。"""
    result = boxes.clone()
    result[..., 0] = boxes[..., 0] - boxes[..., 2] / 2
    result[..., 1] = boxes[..., 1] - boxes[..., 3] / 2
    result[..., 2] = boxes[..., 0] + boxes[..., 2] / 2
    result[..., 3] = boxes[..., 1] + boxes[..., 3] / 2
    return result


def xyxy_to_xywh(boxes: Tensor) -> Tensor:
    """把左上右下格式 ``x1,y1,x2,y2`` 转为中心点格式。"""
    result = boxes.clone()
    result[..., 0] = (boxes[..., 0] + boxes[..., 2]) / 2
    result[..., 1] = (boxes[..., 1] + boxes[..., 3]) / 2
    result[..., 2] = boxes[..., 2] - boxes[..., 0]
    result[..., 3] = boxes[..., 3] - boxes[..., 1]
    return result


def box_iou(first: Tensor, second: Tensor, eps: float = 1e-7) -> Tensor:
    """计算两组 ``xyxy`` 框的两两 IoU，返回形状 ``[N,M]``。"""
    top_left = torch.maximum(first[:, None, :2], second[None, :, :2])
    bottom_right = torch.minimum(first[:, None, 2:], second[None, :, 2:])
    intersection = (bottom_right - top_left).clamp(min=0).prod(dim=-1)
    first_area = (first[:, 2:] - first[:, :2]).clamp(min=0).prod(dim=-1)
    second_area = (second[:, 2:] - second[:, :2]).clamp(min=0).prod(dim=-1)
    union = first_area[:, None] + second_area[None, :] - intersection
    return intersection / (union + eps)


def complete_iou(first: Tensor, second: Tensor, eps: float = 1e-7) -> Tensor:
    """逐元素计算 CIoU，综合重叠、中心距离和宽高比差异。"""
    intersection_top_left = torch.maximum(first[..., :2], second[..., :2])
    intersection_bottom_right = torch.minimum(first[..., 2:], second[..., 2:])
    intersection = (intersection_bottom_right - intersection_top_left).clamp(min=0).prod(dim=-1)
    first_wh = (first[..., 2:] - first[..., :2]).clamp(min=eps)
    second_wh = (second[..., 2:] - second[..., :2]).clamp(min=eps)
    union = first_wh.prod(dim=-1) + second_wh.prod(dim=-1) - intersection
    iou = intersection / (union + eps)
    first_center = (first[..., :2] + first[..., 2:]) / 2
    second_center = (second[..., :2] + second[..., 2:]) / 2
    center_distance = ((first_center - second_center) ** 2).sum(dim=-1)
    enclosing_top_left = torch.minimum(first[..., :2], second[..., :2])
    enclosing_bottom_right = torch.maximum(first[..., 2:], second[..., 2:])
    diagonal = ((enclosing_bottom_right - enclosing_top_left) ** 2).sum(dim=-1) + eps
    aspect = (4 / math.pi**2) * (
        torch.atan(first_wh[..., 0] / first_wh[..., 1])
        - torch.atan(second_wh[..., 0] / second_wh[..., 1])
    ) ** 2
    with torch.no_grad():
        alpha = aspect / (1 - iou + aspect + eps)
    return iou - center_distance / diagonal - alpha * aspect


def class_aware_nms(predictions: Tensor, iou_threshold: float = 0.5) -> Tensor:
    """逐类别执行 NMS；输入每行为 ``x1,y1,x2,y2,score,class``。"""
    if predictions.numel() == 0:
        return predictions.reshape(0, 6)
    kept: list[Tensor] = []
    for class_id in predictions[:, 5].unique():
        candidates = predictions[predictions[:, 5] == class_id]
        candidates = candidates[candidates[:, 4].argsort(descending=True)]
        while len(candidates):
            best = candidates[0]
            kept.append(best)
            if len(candidates) == 1:
                break
            overlaps = box_iou(best[:4].unsqueeze(0), candidates[1:, :4])[0]
            candidates = candidates[1:][overlaps <= iou_threshold]
    return torch.stack(kept)[torch.stack(kept)[:, 4].argsort(descending=True)]


def width_height_iou(wh: Tensor, anchors: Tensor, eps: float = 1e-7) -> Tensor:
    """仅比较宽高的 IoU，用于选择与真实框比例最接近的锚框。"""
    intersection = torch.minimum(wh[:, None], anchors[None]).prod(dim=-1)
    union = wh.prod(dim=-1, keepdim=True) + anchors.prod(dim=-1)[None] - intersection
    return intersection / (union + eps)


def _channels(value: int, multiplier: float) -> int:
    """按宽度倍率缩放通道数，并保证至少为 8。"""
    return max(8, int(value * multiplier))


class ConvBNAct(nn.Module):
    """YOLOv4 卷积积木：Conv2d + BatchNorm + Mish。"""

    def __init__(self, in_channels: int, out_channels: int, kernel: int, stride: int = 1):
        super().__init__()
        padding = (kernel - 1) // 2
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel, stride, padding, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.Mish(inplace=True),
        )

    def forward(self, x: Tensor) -> Tensor:
        """保持或按 stride 下采样空间尺寸。"""
        return self.block(x)


class ResidualBlock(nn.Module):
    """Darknet-53 残差块：先用 1x1 压缩，再用 3x3 恢复通道。"""

    def __init__(self, channels: int):
        super().__init__()
        hidden = channels // 2
        self.body = nn.Sequential(
            ConvBNAct(channels, hidden, 1),
            ConvBNAct(hidden, channels, 3),
        )

    def forward(self, x: Tensor) -> Tensor:
        """残差相加让梯度可以直接跨过两层卷积。"""
        return x + self.body(x)


class CSPStage(nn.Module):
    """CSP 阶段：只让一半通道经过残差堆叠，再与旁路融合。"""

    def __init__(self, in_channels: int, out_channels: int, blocks: int):
        super().__init__()
        hidden = out_channels // 2
        self.downsample = ConvBNAct(in_channels, out_channels, 3, stride=2)
        self.short_route = ConvBNAct(out_channels, hidden, 1)
        self.main_route = ConvBNAct(out_channels, hidden, 1)
        self.residuals = nn.Sequential(*(ResidualBlock(hidden) for _ in range(blocks)))
        self.main_post = ConvBNAct(hidden, hidden, 1)
        self.fuse = ConvBNAct(hidden * 2, out_channels, 1)

    def forward(self, x: Tensor) -> Tensor:
        """下采样后分流；拼接使梯度路径更短且减少重复计算。"""
        x = self.downsample(x)
        short = self.short_route(x)
        main = self.main_post(self.residuals(self.main_route(x)))
        return self.fuse(torch.cat((main, short), dim=1))


class CSPDarknet53(nn.Module):
    """CSPDarknet-53 主干，返回 stride 8、16、32 的三个特征图。"""

    def __init__(self, width_mult: float = 1.0, depth_mult: float = 1.0):
        super().__init__()
        c = [_channels(v, width_mult) for v in (32, 64, 128, 256, 512, 1024)]
        depths = [max(1, round(v * depth_mult)) for v in (1, 2, 8, 8, 4)]
        self.out_channels = (c[3], c[4], c[5])
        self.stem = ConvBNAct(3, c[0], 3)
        self.stage1 = CSPStage(c[0], c[1], depths[0])
        self.stage2 = CSPStage(c[1], c[2], depths[1])
        self.stage3 = CSPStage(c[2], c[3], depths[2])
        self.stage4 = CSPStage(c[3], c[4], depths[3])
        self.stage5 = CSPStage(c[4], c[5], depths[4])

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        """输入 ``[B,3,H,W]``，输出 H/8、H/16、H/32 三层特征。"""
        x = self.stage2(self.stage1(self.stem(x)))
        small = self.stage3(x)
        medium = self.stage4(small)
        large = self.stage5(medium)
        return small, medium, large


class DetectionBlock(nn.Module):
    """PAN 检测块；route 继续参与跨尺度融合，tip 用于预测。"""

    def __init__(self, in_channels: int, route_channels: int):
        super().__init__()
        self.layers = nn.Sequential(
            ConvBNAct(in_channels, route_channels, 1),
            ConvBNAct(route_channels, route_channels * 2, 3),
            ConvBNAct(route_channels * 2, route_channels, 1),
            ConvBNAct(route_channels, route_channels * 2, 3),
            ConvBNAct(route_channels * 2, route_channels, 1),
        )
        self.tip = ConvBNAct(route_channels, route_channels * 2, 3)

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor]:
        """返回较窄的 route 和用于输出预测的 tip。"""
        route = self.layers(x)
        return route, self.tip(route)


class SpatialPyramidPooling(nn.Module):
    """并联 5/9/13 最大池化，在不降采样的情况下扩大感受野。"""

    def __init__(self):
        super().__init__()
        self.pools = nn.ModuleList(nn.MaxPool2d(size, 1, size // 2) for size in (5, 9, 13))

    def forward(self, x: Tensor) -> Tensor:
        """拼接原特征和三种池化特征，通道数扩大四倍。"""
        return torch.cat((x, *(pool(x) for pool in self.pools)), dim=1)


class YOLOv4(nn.Module):
    """完整 YOLOv4：CSPDarknet-53 + SPP + 双向 PAN + 三尺度检测头。"""

    def __init__(
        self,
        num_classes: int,
        width_mult: float = 1.0,
        depth_mult: float = 1.0,
    ):
        super().__init__()
        if num_classes <= 0:
            raise ValueError("num_classes 必须大于 0")
        self.num_classes = num_classes
        output_channels = 3 * (5 + num_classes)
        self.backbone = CSPDarknet53(width_mult, depth_mult)
        c3, c4, c5 = self.backbone.out_channels

        self.spp_pre = ConvBNAct(c5, c5 // 2, 1)
        self.spp = SpatialPyramidPooling()
        self.spp_post = ConvBNAct(c5 * 2, c5, 1)
        self.large_block = DetectionBlock(c5, c5 // 2)
        self.large_reduce = ConvBNAct(c5 // 2, c4 // 2, 1)

        self.medium_block = DetectionBlock(c4 + c4 // 2, c4 // 2)
        self.medium_reduce = ConvBNAct(c4 // 2, c3 // 2, 1)

        self.small_block = DetectionBlock(c3 + c3 // 2, c3 // 2)
        self.small_output = nn.Conv2d(c3, output_channels, 1)
        self.small_down = ConvBNAct(c3 // 2, c4 // 2, 3, stride=2)
        self.medium_pan = DetectionBlock(c4, c4 // 2)
        self.medium_output = nn.Conv2d(c4, output_channels, 1)
        self.medium_down = ConvBNAct(c4 // 2, c5 // 2, 3, stride=2)
        self.large_pan = DetectionBlock(c5, c5 // 2)
        self.large_output = nn.Conv2d(c5, output_channels, 1)

    def forward(self, x: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        """按粗到细顺序返回 stride 32、16、8 的原始预测。"""
        c3, c4, c5 = self.backbone(x)
        c5 = self.spp_post(self.spp(self.spp_pre(c5)))
        large_route, _ = self.large_block(c5)

        up_medium = F.interpolate(self.large_reduce(large_route), size=c4.shape[-2:], mode="nearest")
        medium_route, _ = self.medium_block(torch.cat((up_medium, c4), dim=1))

        up_small = F.interpolate(self.medium_reduce(medium_route), size=c3.shape[-2:], mode="nearest")
        small_route, small_tip = self.small_block(torch.cat((up_small, c3), dim=1))
        small = self.small_output(small_tip)

        medium_route, medium_tip = self.medium_pan(torch.cat((self.small_down(small_route), medium_route), dim=1))
        medium = self.medium_output(medium_tip)
        large_route, large_tip = self.large_pan(torch.cat((self.medium_down(medium_route), large_route), dim=1))
        large = self.large_output(large_tip)
        return large, medium, small


def reshape_predictions(raw: Tensor, num_classes: int) -> Tensor:
    """把 ``[B,A*(5+C),H,W]`` 改为 ``[B,A,H,W,5+C]``。"""
    batch, channels, height, width = raw.shape
    expected = 3 * (5 + num_classes)
    if channels != expected:
        raise ValueError(f"检测头通道数应为 {expected}，实际为 {channels}")
    return raw.view(batch, 3, 5 + num_classes, height, width).permute(0, 1, 3, 4, 2).contiguous()


def decode_scale(raw: Tensor, anchors: Sequence[Sequence[float]], image_size: int, num_classes: int) -> Tensor:
    """把单尺度网络输出解码为像素坐标 ``xywh``、置信度和类别概率。"""
    prediction = reshape_predictions(raw, num_classes)
    batch, anchor_count, height, width, _ = prediction.shape
    device, dtype = prediction.device, prediction.dtype
    grid_y, grid_x = torch.meshgrid(
        torch.arange(height, device=device, dtype=dtype),
        torch.arange(width, device=device, dtype=dtype),
        indexing="ij",
    )
    grid = torch.stack((grid_x, grid_y), dim=-1).view(1, 1, height, width, 2)
    anchor_tensor = torch.tensor(anchors, device=device, dtype=dtype).view(1, anchor_count, 1, 1, 2)
    stride = torch.tensor((image_size / width, image_size / height), device=device, dtype=dtype)
    xy = (prediction[..., :2].sigmoid() + grid) * stride
    wh = prediction[..., 2:4].clamp(max=10).exp() * anchor_tensor
    objectness = prediction[..., 4:5].sigmoid()
    classes = prediction[..., 5:].sigmoid()
    return torch.cat((xy, wh, objectness, classes), dim=-1).view(batch, -1, 5 + num_classes)


def build_targets(
    targets: Tensor,
    image_size: int,
    grid_sizes: Sequence[int],
    anchors: Sequence[Sequence[Sequence[float]]],
    num_classes: int,
    batch_size: int | None = None,
) -> list[Tensor]:
    """为每个真实框选择九个锚框中的全局最佳项，并编码监督张量。"""
    if targets.ndim != 2 or targets.shape[1] != 6:
        raise ValueError("targets 必须是 [N,6]：batch,class,cx,cy,w,h")
    inferred_batch = int(targets[:, 0].max().item()) + 1 if len(targets) else 1
    batch_size = batch_size or inferred_batch
    result = [targets.new_zeros((batch_size, 3, g, g, 5 + num_classes)) for g in grid_sizes]
    if not len(targets):
        return result

    if (targets[:, 1] < 0).any() or (targets[:, 1] >= num_classes).any():
        raise ValueError("标签类别编号超出 num_classes 范围")
    if (targets[:, 2:4] < 0).any() or (targets[:, 2:4] > 1).any() or (targets[:, 4:6] <= 0).any():
        raise ValueError("标签坐标必须归一化，且宽高必须为正数")

    flat_anchors = targets.new_tensor(anchors).view(-1, 2)
    best_indices = width_height_iou(targets[:, 4:6] * image_size, flat_anchors).argmax(dim=1)
    for target, flat_anchor_index in zip(targets, best_indices):
        batch_index, class_id = int(target[0]), int(target[1])
        scale_index = int(flat_anchor_index) // 3
        anchor_index = int(flat_anchor_index) % 3
        grid_size = grid_sizes[scale_index]
        gx, gy = target[2] * grid_size, target[3] * grid_size
        cell_x = min(grid_size - 1, int(gx))
        cell_y = min(grid_size - 1, int(gy))
        anchor_wh = flat_anchors[int(flat_anchor_index)] / image_size
        encoded = result[scale_index][batch_index, anchor_index, cell_y, cell_x]
        encoded[0] = gx - cell_x
        encoded[1] = gy - cell_y
        encoded[2:4] = torch.log(target[4:6] / anchor_wh.clamp(min=1e-7))
        encoded[4] = 1
        encoded[5 + class_id] = 1
    return result


def compute_yolov4_loss(
    raw_outputs: Sequence[Tensor],
    targets: Tensor,
    image_size: int,
    anchors: Sequence[Sequence[Sequence[float]]],
    num_classes: int,
    label_smoothing: float = 0.01,
) -> dict[str, Tensor]:
    """计算 CIoU 边框损失、目标性 BCE 和带平滑的分类 BCE。"""
    grid_sizes = tuple(output.shape[-1] for output in raw_outputs)
    encoded_targets = build_targets(
        targets, image_size, grid_sizes, anchors, num_classes, raw_outputs[0].shape[0]
    )
    zero = raw_outputs[0].sum() * 0
    box_loss, object_loss, class_loss = zero, zero, zero
    for raw, target, scale_anchors in zip(raw_outputs, encoded_targets, anchors):
        prediction = reshape_predictions(raw, num_classes)
        target = target.to(prediction.device)
        positive = target[..., 4].bool()
        object_loss = object_loss + F.binary_cross_entropy_with_logits(
            prediction[..., 4], target[..., 4]
        )
        if positive.any():
            grid_size = prediction.shape[2]
            dtype, device = prediction.dtype, prediction.device
            grid_y, grid_x = torch.meshgrid(
                torch.arange(grid_size, device=device, dtype=dtype),
                torch.arange(grid_size, device=device, dtype=dtype), indexing="ij"
            )
            grid = torch.stack((grid_x, grid_y), dim=-1).view(1, 1, grid_size, grid_size, 2)
            anchor_tensor = torch.tensor(scale_anchors, device=device, dtype=dtype).view(1, 3, 1, 1, 2)
            stride = image_size / grid_size
            predicted_xy = (prediction[..., :2].sigmoid() + grid) * stride
            predicted_wh = prediction[..., 2:4].clamp(max=10).exp() * anchor_tensor
            target_xy = (target[..., :2] + grid) * stride
            target_wh = target[..., 2:4].exp() * anchor_tensor
            predicted_boxes = xywh_to_xyxy(torch.cat((predicted_xy, predicted_wh), dim=-1)[positive])
            target_boxes = xywh_to_xyxy(torch.cat((target_xy, target_wh), dim=-1)[positive])
            box_loss = box_loss + (1.0 - complete_iou(predicted_boxes, target_boxes)).mean()
            smooth_positive = 1.0 - label_smoothing
            smooth_negative = label_smoothing / max(num_classes, 1)
            class_targets = target[..., 5:][positive] * (smooth_positive - smooth_negative) + smooth_negative
            class_loss = class_loss + F.binary_cross_entropy_with_logits(
                prediction[..., 5:][positive], class_targets
            )
    total = box_loss + object_loss + class_loss
    return {"total": total, "box": box_loss, "objectness": object_loss, "classification": class_loss}


def letterbox(image: Image.Image, labels: np.ndarray, size: int) -> tuple[Tensor, Tensor]:
    """等比例缩放并灰色填充，同时把归一化标签映射到新画布。"""
    image = image.convert("RGB")
    width, height = image.size
    scale = min(size / width, size / height)
    resized_w, resized_h = max(1, round(width * scale)), max(1, round(height * scale))
    resized = image.resize((resized_w, resized_h), Image.Resampling.BILINEAR)
    offset_x, offset_y = (size - resized_w) // 2, (size - resized_h) // 2
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(resized, (offset_x, offset_y))
    output = labels.copy()
    if len(output):
        output[:, 1] = (labels[:, 1] * width * scale + offset_x) / size
        output[:, 2] = (labels[:, 2] * height * scale + offset_y) / size
        output[:, 3] = labels[:, 3] * width * scale / size
        output[:, 4] = labels[:, 4] * height * scale / size
    array = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(array).permute(2, 0, 1).contiguous()
    return tensor, torch.from_numpy(output.astype(np.float32))


def random_hsv(image: Image.Image, probability: float = 0.5) -> Image.Image:
    """以一定概率扰动亮度和饱和度，增强光照变化鲁棒性。"""
    if random.random() >= probability:
        return image
    hsv = np.asarray(image.convert("HSV"), dtype=np.float32).copy()
    hsv[..., 1] *= random.uniform(0.7, 1.3)
    hsv[..., 2] *= random.uniform(0.7, 1.3)
    return Image.fromarray(np.clip(hsv, 0, 255).astype(np.uint8), mode="HSV").convert("RGB")


def random_horizontal_flip(image: Image.Image, labels: np.ndarray, probability: float = 0.5):
    """随机水平翻转；中心点横坐标同步变为 ``1-cx``。"""
    if random.random() >= probability:
        return image, labels
    output = labels.copy()
    if len(output):
        output[:, 1] = 1.0 - output[:, 1]
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT), output


def mosaic_augment(
    images: Sequence[np.ndarray],
    labels: Sequence[np.ndarray],
    output_size: int,
    center: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """把四张图放到同一画布，并同步平移、裁剪和归一化边框。"""
    if len(images) != 4 or len(labels) != 4:
        raise ValueError("Mosaic 必须恰好接收四张图片及其标注")
    center_x, center_y = center or (
        random.randint(output_size // 3, output_size * 2 // 3),
        random.randint(output_size // 3, output_size * 2 // 3),
    )
    canvas = np.full((output_size, output_size, 3), 114, dtype=np.uint8)
    merged_labels: list[np.ndarray] = []
    for index, (source, source_labels) in enumerate(zip(images, labels)):
        source_image = Image.fromarray(source.astype(np.uint8)).convert("RGB")
        width, height = source_image.size
        scale = min(output_size / width, output_size / height)
        resized_w, resized_h = max(1, round(width * scale)), max(1, round(height * scale))
        resized = np.asarray(source_image.resize((resized_w, resized_h), Image.Resampling.BILINEAR))
        if index == 0:  # 左上：取源图右下部分
            x1, y1, x2, y2 = max(0, center_x - resized_w), max(0, center_y - resized_h), center_x, center_y
            sx1, sy1 = resized_w - (x2 - x1), resized_h - (y2 - y1)
        elif index == 1:  # 右上：取源图左下部分
            x1, y1, x2, y2 = center_x, max(0, center_y - resized_h), min(output_size, center_x + resized_w), center_y
            sx1, sy1 = 0, resized_h - (y2 - y1)
        elif index == 2:  # 左下：取源图右上部分
            x1, y1, x2, y2 = max(0, center_x - resized_w), center_y, center_x, min(output_size, center_y + resized_h)
            sx1, sy1 = resized_w - (x2 - x1), 0
        else:  # 右下：取源图左上部分
            x1, y1, x2, y2 = center_x, center_y, min(output_size, center_x + resized_w), min(output_size, center_y + resized_h)
            sx1, sy1 = 0, 0
        canvas[y1:y2, x1:x2] = resized[sy1:sy1 + (y2 - y1), sx1:sx1 + (x2 - x1)]
        if not len(source_labels):
            continue
        converted = source_labels.copy()
        source_xyxy = xywh_to_xyxy(torch.from_numpy(converted[:, 1:5])).numpy()
        source_xyxy[:, [0, 2]] *= resized_w
        source_xyxy[:, [1, 3]] *= resized_h
        source_xyxy[:, [0, 2]] += x1 - sx1
        source_xyxy[:, [1, 3]] += y1 - sy1
        source_xyxy = np.clip(source_xyxy, 0, output_size)
        valid = (source_xyxy[:, 2] - source_xyxy[:, 0] > 2) & (source_xyxy[:, 3] - source_xyxy[:, 1] > 2)
        if valid.any():
            normalized = xyxy_to_xywh(torch.from_numpy(source_xyxy[valid])).numpy() / output_size
            merged_labels.append(np.concatenate((converted[valid, :1], normalized), axis=1))
    merged = np.concatenate(merged_labels, axis=0).astype(np.float32) if merged_labels else np.zeros((0, 5), dtype=np.float32)
    return canvas, merged


class DetectionDataset(Dataset):
    """VOC 与 YOLO 文本数据集共用的图像预处理基类。"""

    def __init__(self, image_dir: str | Path, class_names: Sequence[str], image_size: int, augment: bool):
        self.image_dir = Path(image_dir)
        if not self.image_dir.is_dir():
            raise FileNotFoundError(f"图片目录不存在: {self.image_dir}")
        self.class_names = list(class_names)
        self.class_to_id = {name: index for index, name in enumerate(class_names)}
        self.image_size = image_size
        self.augment = augment
        self.images = sorted(path for path in self.image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
        if not self.images:
            raise ValueError(f"图片目录中没有支持的图片: {self.image_dir}")

    def __len__(self) -> int:
        """返回图像数量。"""
        return len(self.images)

    def read_labels(self, image_path: Path, image_size: tuple[int, int]) -> np.ndarray:
        """子类负责把标注统一成 ``class,cx,cy,w,h``。"""
        raise NotImplementedError

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, str]:
        """读取图像；训练时可组合四图 Mosaic，再做颜色和翻转增强。"""
        image_path = self.images[index]
        if self.augment and len(self.images) >= 4 and random.random() < 0.5:
            indices = [index] + random.choices(range(len(self.images)), k=3)
            mosaic_images, mosaic_labels = [], []
            for selected_index in indices:
                selected_path = self.images[selected_index]
                selected_image = Image.open(selected_path).convert("RGB")
                mosaic_images.append(np.asarray(selected_image))
                mosaic_labels.append(self.read_labels(selected_path, selected_image.size))
            array, labels = mosaic_augment(mosaic_images, mosaic_labels, self.image_size)
            image = Image.fromarray(array)
        else:
            image = Image.open(image_path).convert("RGB")
            labels = self.read_labels(image_path, image.size)
        if self.augment:
            image = random_hsv(image)
            image, labels = random_horizontal_flip(image, labels)
        image_tensor, label_tensor = letterbox(image, labels, self.image_size)
        return image_tensor, label_tensor, str(image_path)


class YoloTextDataset(DetectionDataset):
    """读取每行 ``class cx cy width height`` 的 YOLO 文本标注。"""

    def __init__(self, image_dir, label_dir, class_names, image_size=416, augment=False):
        super().__init__(image_dir, class_names, image_size, augment)
        self.label_dir = Path(label_dir)
        if not self.label_dir.is_dir():
            raise FileNotFoundError(f"YOLO 标注目录不存在: {self.label_dir}")

    def read_labels(self, image_path: Path, image_size: tuple[int, int]) -> np.ndarray:
        """解析与图片同名的 txt，并验证类别和归一化坐标。"""
        label_path = self.label_dir / f"{image_path.stem}.txt"
        if not label_path.is_file():
            raise FileNotFoundError(f"YOLO 标注文件不存在: {label_path}")
        rows = []
        for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"{label_path}:{line_number} 应包含 5 列")
            values = [float(value) for value in parts]
            class_id = int(values[0])
            if class_id != values[0] or not 0 <= class_id < len(self.class_names):
                raise ValueError(f"{label_path}:{line_number} 类别编号无效")
            if any(value < 0 or value > 1 for value in values[1:]) or values[3] <= 0 or values[4] <= 0:
                raise ValueError(f"{label_path}:{line_number} 坐标必须归一化且宽高为正")
            rows.append(values)
        return np.asarray(rows, dtype=np.float32).reshape(-1, 5)


class VOCDataset(DetectionDataset):
    """读取 Pascal VOC XML 标注。"""

    def __init__(self, image_dir, annotation_dir, class_names, image_size=416, augment=False):
        super().__init__(image_dir, class_names, image_size, augment)
        self.annotation_dir = Path(annotation_dir)
        if not self.annotation_dir.is_dir():
            raise FileNotFoundError(f"VOC 标注目录不存在: {self.annotation_dir}")

    def read_labels(self, image_path: Path, image_size: tuple[int, int]) -> np.ndarray:
        """把 XML 中的像素 xyxy 转为归一化中心点格式。"""
        annotation_path = self.annotation_dir / f"{image_path.stem}.xml"
        if not annotation_path.is_file():
            raise FileNotFoundError(f"VOC 标注文件不存在: {annotation_path}")
        width, height = image_size
        rows = []
        try:
            root = ET.parse(annotation_path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"VOC XML 无法解析: {annotation_path}") from exc
        for object_node in root.findall("object"):
            name = object_node.findtext("name")
            if name not in self.class_to_id:
                raise ValueError(f"{annotation_path} 包含未知类别: {name}")
            box = object_node.find("bndbox")
            if box is None:
                raise ValueError(f"{annotation_path} 的 object 缺少 bndbox")
            x1, y1 = float(box.findtext("xmin", "0")), float(box.findtext("ymin", "0"))
            x2, y2 = float(box.findtext("xmax", "0")), float(box.findtext("ymax", "0"))
            if x2 <= x1 or y2 <= y1:
                raise ValueError(f"{annotation_path} 包含宽高非正的边框")
            rows.append([self.class_to_id[name], (x1 + x2) / 2 / width, (y1 + y2) / 2 / height, (x2 - x1) / width, (y2 - y1) / height])
        return np.asarray(rows, dtype=np.float32).reshape(-1, 5)


def detection_collate(batch: Sequence[tuple[Tensor, Tensor, str]]):
    """堆叠图像，并给每个标签添加 batch 索引。"""
    images, combined, paths = [], [], []
    for batch_index, (image, labels, path) in enumerate(batch):
        images.append(image)
        paths.append(path)
        if len(labels):
            batch_column = torch.full((len(labels), 1), batch_index, dtype=labels.dtype)
            combined.append(torch.cat((batch_column, labels), dim=1))
    targets = torch.cat(combined) if combined else torch.zeros((0, 6), dtype=torch.float32)
    return torch.stack(images), targets, paths


def decode_predictions(outputs, anchors, image_size, num_classes, confidence_threshold=0.25, iou_threshold=0.5):
    """合并三个尺度，计算类别分数并逐图片执行 NMS。"""
    decoded = torch.cat([decode_scale(raw, scale_anchors, image_size, num_classes) for raw, scale_anchors in zip(outputs, anchors)], dim=1)
    results = []
    for image_prediction in decoded:
        class_probability, class_id = image_prediction[:, 5:].max(dim=1)
        score = image_prediction[:, 4] * class_probability
        mask = score >= confidence_threshold
        if not mask.any():
            results.append(image_prediction.new_zeros((0, 6)))
            continue
        boxes = xywh_to_xyxy(image_prediction[mask, :4])
        candidates = torch.cat((boxes, score[mask, None], class_id[mask, None].float()), dim=1)
        results.append(class_aware_nms(candidates, iou_threshold))
    return results


def voc_ap(recall: np.ndarray, precision: np.ndarray) -> float:
    """按积分包络计算 VOC AP。"""
    recall = np.concatenate(([0.0], recall, [1.0]))
    precision = np.concatenate(([0.0], precision, [0.0]))
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    changes = np.where(recall[1:] != recall[:-1])[0]
    return float(np.sum((recall[changes + 1] - recall[changes]) * precision[changes + 1]))


def evaluate_detections(
    detections: Sequence[Tensor],
    ground_truths: Sequence[Tensor],
    num_classes: int,
    iou_threshold: float = 0.5,
) -> dict[str, float]:
    """逐类别、逐图片贪心匹配检测框，计算 VOC AP@0.5 与 mAP。"""
    if len(detections) != len(ground_truths):
        raise ValueError("detections 与 ground_truths 的图片数量必须一致")
    average_precisions = []
    metrics: dict[str, float] = {}
    for class_id in range(num_classes):
        class_ground_truths: dict[int, Tensor] = {}
        matched: dict[int, Tensor] = {}
        total_ground_truths = 0
        ranked_detections: list[tuple[float, int, Tensor]] = []
        for image_index, (image_detections, image_ground_truths) in enumerate(zip(detections, ground_truths)):
            gt = image_ground_truths[image_ground_truths[:, 4].long() == class_id, :4]
            class_ground_truths[image_index] = gt
            matched[image_index] = torch.zeros(len(gt), dtype=torch.bool)
            total_ground_truths += len(gt)
            selected = image_detections[image_detections[:, 5].long() == class_id]
            ranked_detections.extend((float(row[4]), image_index, row[:4]) for row in selected)
        if total_ground_truths == 0:
            continue
        ranked_detections.sort(key=lambda item: item[0], reverse=True)
        true_positive = np.zeros(len(ranked_detections), dtype=np.float32)
        false_positive = np.zeros(len(ranked_detections), dtype=np.float32)
        for detection_index, (_, image_index, box) in enumerate(ranked_detections):
            gt = class_ground_truths[image_index]
            if not len(gt):
                false_positive[detection_index] = 1
                continue
            overlaps = box_iou(box.unsqueeze(0), gt)[0]
            best_iou, best_index = overlaps.max(dim=0)
            if best_iou >= iou_threshold and not matched[image_index][best_index]:
                true_positive[detection_index] = 1
                matched[image_index][best_index] = True
            else:
                false_positive[detection_index] = 1
        cumulative_tp = np.cumsum(true_positive)
        cumulative_fp = np.cumsum(false_positive)
        recall = cumulative_tp / max(total_ground_truths, 1)
        precision = cumulative_tp / np.maximum(cumulative_tp + cumulative_fp, 1e-9)
        ap = voc_ap(recall, precision)
        metrics[f"ap50_class_{class_id}"] = ap
        average_precisions.append(ap)
    metrics["map50"] = float(np.mean(average_precisions)) if average_precisions else 0.0
    metrics["detections"] = float(sum(len(item) for item in detections))
    return metrics


def choose_device(name: str) -> torch.device:
    """解析 cpu/cuda/auto，并在 CUDA 不可用时给出明确错误。"""
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if name.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但当前 PyTorch 检测不到可用 GPU")
    return torch.device(name)


def save_checkpoint(path: Path, model: nn.Module, optimizer, epoch: int, class_names: Sequence[str], args) -> None:
    """保存模型、优化器、轮次和重建模型所需元数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict() if optimizer else None, "epoch": epoch, "class_names": list(class_names), "args": vars(args)}, path)


def load_model(checkpoint_path: str | Path, device: torch.device) -> tuple[YOLOv4, dict]:
    """从检查点恢复模型，并验证版本标识。"""
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    class_names = checkpoint.get("class_names")
    if not class_names:
        raise ValueError("检查点缺少 class_names，无法确定检测头通道数")
    saved_args = checkpoint.get("args", {})
    model = YOLOv4(len(class_names), saved_args.get("width_mult", 1.0), saved_args.get("depth_mult", 1.0)).to(device)
    model.load_state_dict(checkpoint["model"])
    return model, checkpoint


def make_dataset(args, training: bool):
    """根据 dataset_format 创建 VOC 或 YOLO 文本数据集。"""
    class_names = [line.strip() for line in Path(args.classes).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not class_names:
        raise ValueError("类别文件不能为空")
    common = (args.images, class_names, args.image_size, training)
    if args.dataset_format == "voc":
        return VOCDataset(args.images, args.labels, *common[1:]), class_names
    return YoloTextDataset(args.images, args.labels, *common[1:]), class_names


def train(args) -> None:
    """执行基础 SGD 训练，按轮验证并保存 last/best 检查点。"""
    device = choose_device(args.device)
    dataset, class_names = make_dataset(args, training=True)
    loader = DataLoader(dataset, args.batch_size, shuffle=True, num_workers=0, collate_fn=detection_collate)
    model = YOLOv4(len(class_names), args.width_mult, args.depth_mult).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=args.learning_rate, momentum=0.9, weight_decay=5e-4)
    start_epoch = 0
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model"])
        if checkpoint.get("optimizer"):
            optimizer.load_state_dict(checkpoint["optimizer"])
        start_epoch = int(checkpoint.get("epoch", -1)) + 1
    warmup_epochs = max(1, min(3, args.epochs // 10))
    for parameter_group in optimizer.param_groups:
        parameter_group.setdefault("initial_lr", args.learning_rate)

    def learning_rate_factor(epoch: int) -> float:
        if epoch < warmup_epochs:
            return (epoch + 1) / warmup_epochs
        progress = (epoch - warmup_epochs) / max(1, args.epochs - warmup_epochs)
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, learning_rate_factor, last_epoch=start_epoch - 1)
    output_dir = Path(args.output_dir)
    best_loss = math.inf
    for epoch in range(start_epoch, args.epochs):
        model.train()
        epoch_loss = 0.0
        for images, targets, _ in loader:
            images, targets = images.to(device), targets.to(device)
            losses = compute_yolov4_loss(model(images), targets, args.image_size, DEFAULT_ANCHORS, len(class_names))
            if not torch.isfinite(losses["total"]):
                raise FloatingPointError("训练损失出现 NaN/Inf，请检查标签和学习率")
            optimizer.zero_grad(set_to_none=True)
            losses["total"].backward()
            nn.utils.clip_grad_norm_(model.parameters(), 10.0)
            optimizer.step()
            epoch_loss += float(losses["total"].detach())
        scheduler.step()
        save_checkpoint(output_dir / "last.pt", model, optimizer, epoch, class_names, args)
        mean_loss = epoch_loss / max(len(loader), 1)
        if mean_loss < best_loss:
            best_loss = mean_loss
            save_checkpoint(output_dir / "best.pt", model, optimizer, epoch, class_names, args)
        print(f"epoch={epoch + 1}/{args.epochs} loss={mean_loss:.4f} lr={scheduler.get_last_lr()[0]:.6g}")


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, args) -> dict[str, float]:
    """解码预测、和每张图的真实框匹配，计算 VOC@0.5 mAP。"""
    model.eval()
    all_detections: list[Tensor] = []
    all_ground_truths: list[Tensor] = []
    for images, targets, _ in loader:
        outputs = model(images.to(device))
        detections = decode_predictions(outputs, DEFAULT_ANCHORS, args.image_size, model.num_classes, args.confidence, args.iou_threshold)
        all_detections.extend(item.cpu() for item in detections)
        for batch_index in range(len(images)):
            selected = targets[targets[:, 0].long() == batch_index]
            if len(selected):
                boxes = xywh_to_xyxy(selected[:, 2:6] * args.image_size)
                gt = torch.cat((boxes, selected[:, 1:2]), dim=1)
            else:
                gt = torch.zeros((0, 5))
            all_ground_truths.append(gt.cpu())
    return evaluate_detections(all_detections, all_ground_truths, model.num_classes, 0.5)


@torch.no_grad()
def detect(model: nn.Module, image: Image.Image, device: torch.device, args):
    """对单图执行 letterbox、推理、解码和 NMS，并返回绘制结果。"""
    original = image.convert("RGB")
    tensor, _ = letterbox(original, np.zeros((0, 5), dtype=np.float32), args.image_size)
    outputs = model(tensor.unsqueeze(0).to(device))
    boxes = decode_predictions(outputs, DEFAULT_ANCHORS, args.image_size, model.num_classes, args.confidence, args.iou_threshold)[0].cpu()
    canvas = original.resize((args.image_size, args.image_size))
    draw = ImageDraw.Draw(canvas)
    for x1, y1, x2, y2, score, class_id in boxes.tolist():
        draw.rectangle((x1, y1, x2, y2), outline="red", width=2)
        draw.text((x1, y1), f"{int(class_id)} {score:.2f}", fill="red")
    return canvas, boxes


def inspect_model(args) -> None:
    """离线执行小模型的前向、损失和反向传播。"""
    torch.manual_seed(args.seed)
    model = YOLOv4(args.num_classes, args.width_mult, args.depth_mult)
    model.eval()
    image = torch.randn(1, 3, args.image_size, args.image_size)
    targets = torch.tensor([[0.0, 0.0, 0.5, 0.5, 0.25, 0.20]])
    outputs = model(image)
    losses = compute_yolov4_loss(outputs, targets, args.image_size, DEFAULT_ANCHORS, args.num_classes)
    losses["total"].backward()
    print("三个检测尺度:", [tuple(output.shape) for output in outputs])
    print(f"总损失: {losses['total'].item():.6f}")
    print("YOLOv4 inspect 完成")


def run_smoke_pipeline(output_dir: Path, device_name: str = "cpu") -> Path:
    """训练一步、保存、重载并推理，用于验证完整工程闭环。"""
    device = choose_device(device_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(width_mult=0.25, depth_mult=0.25)
    class_names = ["object"]
    model = YOLOv4(1, 0.25, 0.25).to(device).eval()
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-3, momentum=0.9)
    image = torch.randn(1, 3, 128, 128, device=device)
    targets = torch.tensor([[0.0, 0.0, 0.5, 0.5, 0.25, 0.25]], device=device)
    loss = compute_yolov4_loss(model(image), targets, 128, DEFAULT_ANCHORS, 1)["total"]
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()
    checkpoint_path = output_dir / "smoke_checkpoint.pt"
    save_checkpoint(checkpoint_path, model, optimizer, 0, class_names, args)
    restored, _ = load_model(checkpoint_path, device)
    detect_args = argparse.Namespace(image_size=128, confidence=0.99, iou_threshold=0.5)
    rendered, _ = detect(restored.eval(), Image.new("RGB", (128, 128), "white"), device, detect_args)
    rendered.save(output_dir / "smoke_detection.jpg")
    print("YOLOv4 smoke 完成")
    return checkpoint_path


def add_data_arguments(parser: argparse.ArgumentParser) -> None:
    """向 train/eval 子命令添加一致的数据参数。"""
    parser.add_argument("--dataset-format", choices=("voc", "yolo"), default="yolo")
    parser.add_argument("--images", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--classes", required=True)
    parser.add_argument("--image-size", type=int, default=416)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--device", default="auto")


def build_parser() -> argparse.ArgumentParser:
    """创建 train/eval/detect/inspect/smoke 命令行解析器。"""
    parser = argparse.ArgumentParser(description="YOLOv4 单文件教学复现")
    subparsers = parser.add_subparsers(dest="command")
    inspect_parser = subparsers.add_parser("inspect", help="离线检查网络、损失和梯度")
    inspect_parser.add_argument("--image-size", type=int, default=128)
    inspect_parser.add_argument("--num-classes", type=int, default=3)
    inspect_parser.add_argument("--width-mult", type=float, default=0.25)
    inspect_parser.add_argument("--depth-mult", type=float, default=0.25)
    inspect_parser.add_argument("--seed", type=int, default=7)

    train_parser = subparsers.add_parser("train", help="训练模型")
    add_data_arguments(train_parser)
    train_parser.add_argument("--epochs", type=int, default=100)
    train_parser.add_argument("--learning-rate", type=float, default=1e-3)
    train_parser.add_argument("--output-dir", default="runs/yolov4")
    train_parser.add_argument("--width-mult", type=float, default=1.0)
    train_parser.add_argument("--depth-mult", type=float, default=1.0)
    train_parser.add_argument("--resume")

    eval_parser = subparsers.add_parser("eval", help="计算 VOC AP@0.5")
    add_data_arguments(eval_parser)
    eval_parser.add_argument("--checkpoint", required=True)
    eval_parser.add_argument("--confidence", type=float, default=0.001)
    eval_parser.add_argument("--iou-threshold", type=float, default=0.5)

    detect_parser = subparsers.add_parser("detect", help="单图推理")
    detect_parser.add_argument("--checkpoint", required=True)
    detect_parser.add_argument("--image", required=True)
    detect_parser.add_argument("--output", default="detection.jpg")
    detect_parser.add_argument("--image-size", type=int, default=416)
    detect_parser.add_argument("--confidence", type=float, default=0.25)
    detect_parser.add_argument("--iou-threshold", type=float, default=0.5)
    detect_parser.add_argument("--device", default="auto")

    smoke_parser = subparsers.add_parser("smoke", help="训练、保存、重载和推理闭环")
    smoke_parser.add_argument("--output-dir", type=Path, required=True)
    smoke_parser.add_argument("--device", default="cpu")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """命令行入口；无参数时默认执行完全离线的 inspect。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "inspect"
    if command == "inspect":
        if args.command is None:
            args = parser.parse_args(["inspect"])
        inspect_model(args)
    elif command == "train":
        train(args)
    elif command == "eval":
        device = choose_device(args.device)
        model, checkpoint = load_model(args.checkpoint, device)
        dataset, class_names = make_dataset(args, training=False)
        if class_names != checkpoint["class_names"]:
            raise ValueError("类别文件与检查点中的 class_names 不一致")
        loader = DataLoader(dataset, args.batch_size, shuffle=False, num_workers=0, collate_fn=detection_collate)
        metrics = evaluate(model, loader, device, args)
        print("mAP@0.5:", f"{metrics['map50']:.6f}")
    elif command == "detect":
        device = choose_device(args.device)
        model, _ = load_model(args.checkpoint, device)
        rendered, boxes = detect(model.eval(), Image.open(args.image), device, args)
        rendered.save(args.output)
        print(f"保留 {len(boxes)} 个检测框，结果写入 {args.output}")
    elif command == "smoke":
        run_smoke_pipeline(args.output_dir, args.device)
    else:
        parser.error(f"尚未实现的命令: {command}")


if __name__ == "__main__":
    main()
