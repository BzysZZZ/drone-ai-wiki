# YOLOv3 / YOLOv4 单页复现实验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增可持续扩展的“实验 · 复现”板块，并交付两份复制到 IDE、安装公开依赖后即可独立运行的 YOLOv3 与 YOLOv4 完整教学代码。

**Architecture:** 每种网络由一个自包含 Python 文件实现数据读取、模型、损失、训练、评估和推理，不导入仓库内其他源码。Wiki 每种网络只使用一个高密度页面，构建器通过受限代码包含指令把完整源码嵌入页面，源码文件是唯一事实来源。

**Tech Stack:** Python 3.10+、PyTorch、NumPy、Pillow、Python `unittest`、Python-Markdown、现有静态站点生成器。

---

## 文件结构

**新增：**

- `experiments/yolo_classics/README.md`：独立运行说明、数据目录约定和命令索引。
- `experiments/yolo_classics/requirements.txt`：两份单文件实现共有的公开依赖。
- `experiments/yolo_classics/yolov3_reproduction.py`：YOLOv3 自包含复现。
- `experiments/yolo_classics/yolov4_reproduction.py`：YOLOv4 自包含复现。
- `experiments/yolo_classics/tests/test_yolov3.py`：YOLOv3 数学、形状、梯度和 CLI 测试。
- `experiments/yolo_classics/tests/test_yolov4.py`：YOLOv4 数学、形状、增强、梯度和 CLI 测试。
- `experiments/yolo_classics/tests/test_isolated_scripts.py`：复制到临时目录后的独立运行测试。
- `tests/test_build_site.py`：源码包含安全性、实验导航和页面生成测试。
- `wiki/experiments/index.md`：实验复现目录。
- `wiki/experiments/experiment-yolov3-reproduction.md`：YOLOv3 单页教程。
- `wiki/experiments/experiment-yolov4-reproduction.md`：YOLOv4 单页教程。

**修改：**

- `build_site.py`：增加实验导航分组和受限源码包含功能。
- `wiki/index.md`：在首页登记实验复现入口。

## Task 1: 为源码包含功能建立安全测试

**Files:**
- Create: `tests/test_build_site.py`
- Modify: `build_site.py`

- [ ] **Step 1: 写源码包含的失败测试**

```python
import tempfile
import unittest
from pathlib import Path

import build_site


class CodeIncludeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.allowed = self.root / "experiments" / "yolo_classics"
        self.allowed.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_expands_python_file_inside_allowed_directory(self):
        source = self.allowed / "demo.py"
        source.write_text("print('<ready>')\n", encoding="utf-8")
        raw = '<!-- include-code: experiments/yolo_classics/demo.py -->'
        result = build_site.expand_code_includes(raw, self.root)
        self.assertEqual(result, "```python\nprint('<ready>')\n```")

    def test_rejects_parent_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "非法代码包含路径"):
            build_site.expand_code_includes(
                '<!-- include-code: experiments/yolo_classics/../../secret.py -->',
                self.root,
            )

    def test_reports_missing_source(self):
        with self.assertRaisesRegex(FileNotFoundError, "代码包含文件不存在"):
            build_site.expand_code_includes(
                '<!-- include-code: experiments/yolo_classics/missing.py -->',
                self.root,
            )
```

- [ ] **Step 2: 运行测试并确认因函数不存在而失败**

Run: `python -m unittest tests.test_build_site.CodeIncludeTest -v`

Expected: `ERROR`，包含 `AttributeError: module 'build_site' has no attribute 'expand_code_includes'`。

- [ ] **Step 3: 在构建器中实现受限包含**

在 `build_site.py` 常量区增加：

```python
EXPERIMENTS_DIR = BASE_DIR / "experiments" / "yolo_classics"
CODE_INCLUDE_RE = re.compile(r"<!--\s*include-code:\s*([^>]+?)\s*-->")
```

在 `build_page` 前增加完整函数：

```python
def expand_code_includes(raw: str, base_dir: Path = BASE_DIR) -> str:
    """把实验源码包含标记替换为 fenced Python 代码，并阻止目录穿越。"""
    allowed_root = (base_dir / "experiments" / "yolo_classics").resolve()

    def replace_include(match: re.Match) -> str:
        relative = Path(match.group(1).strip())
        if relative.is_absolute():
            raise ValueError(f"非法代码包含路径: {relative}")
        source = (base_dir / relative).resolve()
        try:
            source.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(f"非法代码包含路径: {relative}") from exc
        if not source.is_file():
            raise FileNotFoundError(f"代码包含文件不存在: {relative}")
        code = source.read_text(encoding="utf-8").rstrip("\n")
        return f"```python\n{code}\n```"

    return CODE_INCLUDE_RE.sub(replace_include, raw)
```

在 `build_page` 读取 Markdown 后、转换 Wiki 链接前调用：

```python
raw = expand_code_includes(raw)
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python -m unittest tests.test_build_site.CodeIncludeTest -v`

Expected: `Ran 3 tests`，`OK`。

- [ ] **Step 5: 提交**

```bash
git add build_site.py tests/test_build_site.py
git commit -m "功能：支持安全嵌入实验源码"
```

## Task 2: 增加可扩展的实验导航

**Files:**
- Modify: `tests/test_build_site.py`
- Modify: `build_site.py`
- Create: `wiki/experiments/index.md`
- Modify: `wiki/index.md`

- [ ] **Step 1: 写实验分组与页面收集测试**

向 `tests/test_build_site.py` 增加：

```python
class ExperimentNavigationTest(unittest.TestCase):
    def test_experiment_pages_have_dedicated_group(self):
        self.assertEqual(
            build_site.get_nav_group("experiments/experiment-yolov3-reproduction.md"),
            "实验 · 复现",
        )

    def test_collected_experiment_index_has_nested_url(self):
        pages = build_site.collect_pages()
        page = pages["experiments/index.md"]
        self.assertEqual(page["url"], "experiments/index.html")
        self.assertEqual(page["group"], "实验 · 复现")
```

- [ ] **Step 2: 运行测试并确认分组失败**

Run: `python -m unittest tests.test_build_site.ExperimentNavigationTest -v`

Expected: `FAIL`，实际分组为“其他”或实验首页尚不存在。

- [ ] **Step 3: 实现实验分组与总览入口**

在 `get_nav_group` 的 `topics/` 分支之后增加：

```python
elif rel.startswith("experiments/"):
    return "实验 · 复现"
```

把 `build_page` 的 `ordered_groups` 改为包含实验分组：

```python
ordered_groups = [
    "index",
    "概念 · 理论",
    "实体 · 工具",
    "专题 · 项目",
    "实验 · 复现",
    "工具 · 私有",
    "原始资料",
    "系统文件",
]
```

创建 `wiki/experiments/index.md`，包含板块用途、复制即跑规范和 YOLOv3/YOLOv4 链接；在 `wiki/index.md` 快速导航中增加 `[[experiments/index]]`。

- [ ] **Step 4: 运行导航测试和整站构建**

Run: `python -m unittest tests.test_build_site.ExperimentNavigationTest -v`

Expected: `Ran 2 tests`，`OK`。

Run: `python build_site.py`

Expected: 输出包含 `[OK] experiments/index.html`，最终显示 `[DONE] Site built`。

- [ ] **Step 5: 提交**

```bash
git add build_site.py tests/test_build_site.py wiki/index.md wiki/experiments/index.md
git commit -m "功能：新增实验复现导航板块"
```

## Task 3: 建立 YOLOv3 数学工具与测试契约

**Files:**
- Create: `experiments/yolo_classics/requirements.txt`
- Create: `experiments/yolo_classics/yolov3_reproduction.py`
- Create: `experiments/yolo_classics/tests/__init__.py`
- Create: `experiments/yolo_classics/tests/test_yolov3.py`

- [ ] **Step 1: 写边框转换、IoU 与 NMS 的失败测试**

```python
import unittest
import torch

from experiments.yolo_classics import yolov3_reproduction as y3


class YoloV3GeometryTest(unittest.TestCase):
    def test_xywh_xyxy_round_trip(self):
        boxes = torch.tensor([[10.0, 20.0, 4.0, 8.0]])
        restored = y3.xyxy_to_xywh(y3.xywh_to_xyxy(boxes))
        torch.testing.assert_close(restored, boxes)

    def test_box_iou_known_overlap(self):
        first = torch.tensor([[0.0, 0.0, 2.0, 2.0]])
        second = torch.tensor([[1.0, 1.0, 3.0, 3.0]])
        torch.testing.assert_close(y3.box_iou(first, second), torch.tensor([[1.0 / 7.0]]))

    def test_nms_suppresses_same_class_overlap(self):
        predictions = torch.tensor([
            [0.0, 0.0, 10.0, 10.0, 0.90, 0.0],
            [1.0, 1.0, 9.0, 9.0, 0.80, 0.0],
            [20.0, 20.0, 30.0, 30.0, 0.70, 0.0],
        ])
        kept = y3.class_aware_nms(predictions, iou_threshold=0.5)
        self.assertEqual(kept.shape, (2, 6))
        torch.testing.assert_close(kept[:, 4], torch.tensor([0.90, 0.70]))
```

- [ ] **Step 2: 运行测试并确认导入失败**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3.YoloV3GeometryTest -v`

Expected: `ImportError`，因为 YOLOv3 文件尚未实现。

- [ ] **Step 3: 创建依赖文件和 YOLOv3 数学工具**

`requirements.txt` 固定公开依赖的兼容下限：

```text
torch>=2.2
numpy>=1.26
Pillow>=10.0
```

在 `yolov3_reproduction.py` 中实现并逐个注释：`xywh_to_xyxy`、`xyxy_to_xywh`、`box_iou`、`class_aware_nms`。NMS 不依赖 `torchvision`，按置信度降序逐类抑制，以保持单文件公开依赖最少。

- [ ] **Step 4: 运行数学测试**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3.YoloV3GeometryTest -v`

Expected: `Ran 3 tests`，`OK`。

- [ ] **Step 5: 提交**

```bash
git add experiments/yolo_classics/requirements.txt experiments/yolo_classics/yolov3_reproduction.py experiments/yolo_classics/tests
git commit -m "功能：实现YOLOv3边框与NMS工具"
```

## Task 4: 实现 YOLOv3 网络、解码与标签分配

**Files:**
- Modify: `experiments/yolo_classics/yolov3_reproduction.py`
- Modify: `experiments/yolo_classics/tests/test_yolov3.py`

- [ ] **Step 1: 写三尺度网络和标签分配失败测试**

```python
class YoloV3ModelTest(unittest.TestCase):
    def test_model_returns_three_detection_scales(self):
        model = y3.YOLOv3(num_classes=3)
        outputs = model(torch.randn(1, 3, 128, 128))
        expected_channels = 3 * (5 + 3)
        self.assertEqual([tuple(x.shape) for x in outputs], [
            (1, expected_channels, 4, 4),
            (1, expected_channels, 8, 8),
            (1, expected_channels, 16, 16),
        ])

    def test_target_assignment_marks_exactly_one_best_anchor(self):
        targets = torch.tensor([[0.0, 1.0, 0.5, 0.5, 0.20, 0.20]])
        assigned = y3.build_targets(
            targets=targets,
            image_size=128,
            grid_sizes=(4, 8, 16),
            anchors=y3.DEFAULT_ANCHORS,
            num_classes=3,
        )
        positives = sum(int(scale[..., 4].sum().item()) for scale in assigned)
        self.assertEqual(positives, 1)
```

- [ ] **Step 2: 运行测试并确认缺少模型类**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3.YoloV3ModelTest -v`

Expected: `ERROR`，包含 `AttributeError` 或 `NameError`。

- [ ] **Step 3: 实现 Darknet-53、FPN 和检测头**

在同一个源码文件中定义：

```python
DEFAULT_ANCHORS = (
    ((116, 90), (156, 198), (373, 326)),
    ((30, 61), (62, 45), (59, 119)),
    ((10, 13), (16, 30), (33, 23)),
)
```

实现 `ConvBNLeaky`、`ResidualBlock`、`Darknet53`、`DetectionBlock`、`YOLOv3`。`Darknet53.forward` 返回 stride 8/16/32 三个特征；`YOLOv3.forward` 返回从粗到细的三个原始预测张量。所有类都有中文 docstring，前向传播处注明每个特征图形状。

- [ ] **Step 4: 实现预测重排、解码和目标分配**

实现以下稳定接口：

```python
def reshape_predictions(raw: torch.Tensor, num_classes: int) -> torch.Tensor:
    """把 [B, A*(5+C), H, W] 变为 [B, A, H, W, 5+C]。"""


def decode_scale(raw, anchors, image_size, num_classes):
    """应用 sigmoid、网格偏移和锚框缩放，返回像素坐标 xywh。"""


def build_targets(targets, image_size, grid_sizes, anchors, num_classes):
    """按宽高 IoU 选择全局最佳锚框，生成三个尺度的监督张量。"""
```

`targets` 固定为 `[N, 6] = [batch_index, class_id, cx, cy, width, height]`，坐标归一化到 `[0, 1]`。非法类别或非正边框立即抛出中文 `ValueError`。

- [ ] **Step 5: 运行模型测试**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3.YoloV3ModelTest -v`

Expected: `Ran 2 tests`，`OK`。

- [ ] **Step 6: 提交**

```bash
git add experiments/yolo_classics/yolov3_reproduction.py experiments/yolo_classics/tests/test_yolov3.py
git commit -m "功能：实现YOLOv3网络与标签分配"
```

## Task 5: 实现 YOLOv3 损失与有限梯度

**Files:**
- Modify: `experiments/yolo_classics/yolov3_reproduction.py`
- Modify: `experiments/yolo_classics/tests/test_yolov3.py`

- [ ] **Step 1: 写损失和反向传播测试**

```python
class YoloV3LossTest(unittest.TestCase):
    def test_loss_is_finite_and_backpropagates(self):
        torch.manual_seed(7)
        model = y3.YOLOv3(num_classes=2)
        images = torch.randn(1, 3, 128, 128)
        targets = torch.tensor([[0.0, 1.0, 0.5, 0.5, 0.25, 0.20]])
        result = y3.compute_yolov3_loss(
            model(images), targets, image_size=128,
            anchors=y3.DEFAULT_ANCHORS, num_classes=2,
        )
        self.assertEqual(set(result), {"total", "box", "objectness", "classification"})
        self.assertTrue(torch.isfinite(result["total"]))
        result["total"].backward()
        gradients = [p.grad for p in model.parameters() if p.grad is not None]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(g).all() for g in gradients))
```

- [ ] **Step 2: 运行并确认缺少损失函数**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3.YoloV3LossTest -v`

Expected: `ERROR`，包含 `compute_yolov3_loss` 不存在。

- [ ] **Step 3: 实现 YOLOv3 分项损失**

实现 `compute_yolov3_loss`：正样本的中心偏移使用 BCE、宽高使用与锚框比值对数后的 MSE，目标性和类别使用 `binary_cross_entropy_with_logits`；目标性对全部有效位置计算，类别只对正样本计算。返回包含四个标量张量的字典，并在每个尺度验证通道数为 `3 * (5 + num_classes)`。

- [ ] **Step 4: 运行损失测试**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3.YoloV3LossTest -v`

Expected: `Ran 1 test`，`OK`。

- [ ] **Step 5: 提交**

```bash
git add experiments/yolo_classics/yolov3_reproduction.py experiments/yolo_classics/tests/test_yolov3.py
git commit -m "功能：实现YOLOv3训练损失"
```

## Task 6: 完成 YOLOv3 数据、训练、评估、推理与默认运行

**Files:**
- Modify: `experiments/yolo_classics/yolov3_reproduction.py`
- Modify: `experiments/yolo_classics/tests/test_yolov3.py`

- [ ] **Step 1: 写数据格式和默认 CLI 测试**

测试使用 `TemporaryDirectory` 创建一张 64×64 图片、一份 VOC XML 和一份 YOLO 文本标注；分别断言 `VOCDataset`、`YoloTextDataset` 返回 `[3, image_size, image_size]` 图像和 `[N, 5]` 标签。再通过 `subprocess.run([sys.executable, script], ...)` 断言无参数执行返回码为 0，stdout 包含 `YOLOv3 inspect 完成` 和三个尺度。

- [ ] **Step 2: 运行并确认数据类或 CLI 缺失**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3 -v`

Expected: 新增测试 `ERROR` 或 `FAIL`，现有数学与模型测试保持通过。

- [ ] **Step 3: 实现自包含数据管线**

在单文件中实现 `letterbox`、`random_hsv`、`random_horizontal_flip`、`VOCDataset`、`YoloTextDataset`、`detection_collate`。统一返回 RGB float 张量和归一化 `class,cx,cy,w,h`；解析时验证文件存在、类别范围与边框有效性，并在错误中带上标注路径和行号/节点。

- [ ] **Step 4: 实现训练、评估和推理函数**

实现：

```python
def train(args) -> None:
    """构建数据、SGD、warmup+cosine 调度器，记录分项损失并保存 last/best。"""


@torch.no_grad()
def evaluate(model, loader, device, args) -> dict[str, float]:
    """按 VOC IoU=0.5 计算每类 AP 与 mAP。"""


@torch.no_grad()
def detect(model, image, device, args):
    """完成 letterbox、三尺度解码、阈值过滤、逐类 NMS 和坐标还原。"""


def inspect_model(args) -> None:
    """使用合成输入执行前向、损失和反向传播，不读取数据或访问网络。"""


def run_smoke_pipeline(output_dir: Path, device: str = "cpu") -> Path:
    """在合成检测数据上训练一步、保存、重载并推理，返回检查点路径。"""
```

`build_parser` 使用子命令 `train/eval/detect/inspect/smoke`；`main(argv=None)` 在没有参数时自动使用 `inspect`。CPU 下默认 inspect 输入为 128，避免测试占用过大。`smoke --output-dir PATH` 必须在 PATH 内生成检查点和一张带检测结果的图片。

- [ ] **Step 5: 运行 YOLOv3 全部测试和语法检查**

Run: `python -m py_compile experiments/yolo_classics/yolov3_reproduction.py`

Expected: 无输出，退出码 0。

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov3 -v`

Expected: 所有 YOLOv3 测试 `OK`。

- [ ] **Step 6: 提交**

```bash
git add experiments/yolo_classics/yolov3_reproduction.py experiments/yolo_classics/tests/test_yolov3.py
git commit -m "功能：完成YOLOv3单文件训练闭环"
```

## Task 7: 建立 YOLOv4 专属数学与结构测试

**Files:**
- Create: `experiments/yolo_classics/yolov4_reproduction.py`
- Create: `experiments/yolo_classics/tests/test_yolov4.py`

- [ ] **Step 1: 写 CIoU、Mosaic 和三尺度结构测试**

```python
import unittest
import numpy as np
import torch

from experiments.yolo_classics import yolov4_reproduction as y4


class YoloV4CoreTest(unittest.TestCase):
    def test_ciou_is_one_for_identical_boxes(self):
        boxes = torch.tensor([[0.0, 0.0, 2.0, 2.0]])
        torch.testing.assert_close(y4.complete_iou(boxes, boxes), torch.ones(1))

    def test_mosaic_returns_fixed_image_and_valid_boxes(self):
        images = [np.full((32, 32, 3), fill_value=i * 30, dtype=np.uint8) for i in range(4)]
        labels = [np.array([[0, 0.5, 0.5, 0.5, 0.5]], dtype=np.float32) for _ in range(4)]
        image, merged = y4.mosaic_augment(images, labels, output_size=64, center=(32, 32))
        self.assertEqual(image.shape, (64, 64, 3))
        self.assertEqual(merged.shape[1], 5)
        self.assertTrue(np.logical_and(merged[:, 1:] >= 0, merged[:, 1:] <= 1).all())

    def test_model_returns_three_scales(self):
        model = y4.YOLOv4(num_classes=3)
        outputs = model(torch.randn(1, 3, 128, 128))
        channels = 3 * (5 + 3)
        self.assertEqual([tuple(x.shape) for x in outputs], [
            (1, channels, 4, 4),
            (1, channels, 8, 8),
            (1, channels, 16, 16),
        ])
```

- [ ] **Step 2: 运行并确认 YOLOv4 导入失败**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov4.YoloV4CoreTest -v`

Expected: `ImportError`。

- [ ] **Step 3: 实现 YOLOv4 数学工具与增强函数**

创建自包含脚本并独立实现 `xywh_to_xyxy`、`xyxy_to_xywh`、`box_iou`、`complete_iou`、`class_aware_nms`。不能从 YOLOv3 文件导入。实现 `mosaic_augment(images, labels, output_size, center=None)`，完成四图放置、边框平移/缩放/裁剪和无效框过滤；固定 `center` 时结果可测试。

- [ ] **Step 4: 实现 CSPDarknet-53、SPP、PAN 和检测头**

在单文件中定义 `Mish`、`ConvBNAct`、`CSPStage`、`CSPDarknet53`、`SpatialPyramidPooling`、`PANet`、`YOLOv4`。主干返回 stride 8/16/32 特征，SPP 使用 5/9/13 最大池化，PAN 完成双向融合，输出顺序与 YOLOv3 一致。

- [ ] **Step 5: 运行核心测试**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov4.YoloV4CoreTest -v`

Expected: `Ran 3 tests`，`OK`。

- [ ] **Step 6: 提交**

```bash
git add experiments/yolo_classics/yolov4_reproduction.py experiments/yolo_classics/tests/test_yolov4.py
git commit -m "功能：实现YOLOv4核心网络与增强"
```

## Task 8: 完成 YOLOv4 标签、CIoU 损失和训练闭环

**Files:**
- Modify: `experiments/yolo_classics/yolov4_reproduction.py`
- Modify: `experiments/yolo_classics/tests/test_yolov4.py`

- [ ] **Step 1: 写 CIoU 损失有限梯度和默认 CLI 测试**

```python
class YoloV4TrainingTest(unittest.TestCase):
    def test_loss_is_finite_and_backpropagates(self):
        torch.manual_seed(11)
        model = y4.YOLOv4(num_classes=2)
        images = torch.randn(1, 3, 128, 128)
        targets = torch.tensor([[0.0, 1.0, 0.5, 0.5, 0.20, 0.30]])
        result = y4.compute_yolov4_loss(
            model(images), targets, image_size=128,
            anchors=y4.DEFAULT_ANCHORS, num_classes=2, label_smoothing=0.01,
        )
        self.assertTrue(torch.isfinite(result["total"]))
        result["total"].backward()
        self.assertTrue(all(
            torch.isfinite(p.grad).all()
            for p in model.parameters() if p.grad is not None
        ))
```

另加无参数子进程测试，断言 stdout 包含 `YOLOv4 inspect 完成`。

- [ ] **Step 2: 运行并确认损失和 CLI 测试失败**

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov4 -v`

Expected: 新增测试 `ERROR` 或 `FAIL`。

- [ ] **Step 3: 实现标签分配与 YOLOv4 损失**

独立实现 `reshape_predictions`、`decode_scale`、`build_targets`、`compute_yolov4_loss`。边框项使用 `1 - CIoU`，目标性与类别使用 logits BCE，类别正标签应用可配置标签平滑；返回 `total/box/objectness/classification` 四项。

- [ ] **Step 4: 实现数据、训练、评估、推理与 CLI**

独立实现 VOC/YOLO 数据集、Mosaic 开关、随机仿射、HSV、翻转、SGD、warmup+cosine、检查点、VOC AP/mAP、三尺度解码与 NMS。公开函数和命令行名称与 YOLOv3 保持一致，但不得导入 YOLOv3 文件。无参数默认执行合成数据 inspect；`smoke` 子命令在指定目录完成一步训练、保存、重载和推理。

- [ ] **Step 5: 运行 YOLOv4 全测试**

Run: `python -m py_compile experiments/yolo_classics/yolov4_reproduction.py`

Expected: 退出码 0。

Run: `python -m unittest experiments.yolo_classics.tests.test_yolov4 -v`

Expected: 所有 YOLOv4 测试 `OK`。

- [ ] **Step 6: 提交**

```bash
git add experiments/yolo_classics/yolov4_reproduction.py experiments/yolo_classics/tests/test_yolov4.py
git commit -m "功能：完成YOLOv4单文件训练闭环"
```

## Task 9: 验证两个源码文件复制即跑

**Files:**
- Create: `experiments/yolo_classics/tests/test_isolated_scripts.py`
- Create: `experiments/yolo_classics/README.md`

- [ ] **Step 1: 写临时目录隔离执行测试**

```python
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = ROOT / "experiments" / "yolo_classics"


class IsolatedScriptTest(unittest.TestCase):
    def assert_runs_after_copy(self, filename, marker):
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / filename
            shutil.copy2(SOURCE_DIR / filename, copied)
            result = subprocess.run(
                [sys.executable, str(copied)],
                cwd=tmp,
                text=True,
                capture_output=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(marker, result.stdout)

    def test_yolov3_copy_runs_without_repository_imports(self):
        self.assert_runs_after_copy("yolov3_reproduction.py", "YOLOv3 inspect 完成")

    def test_yolov4_copy_runs_without_repository_imports(self):
        self.assert_runs_after_copy("yolov4_reproduction.py", "YOLOv4 inspect 完成")

    def assert_smoke_pipeline_creates_reloadable_artifacts(self, filename):
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / filename
            output = Path(tmp) / "artifacts"
            shutil.copy2(SOURCE_DIR / filename, copied)
            result = subprocess.run(
                [sys.executable, str(copied), "smoke", "--output-dir", str(output)],
                cwd=tmp,
                text=True,
                capture_output=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "smoke_checkpoint.pt").is_file())
            self.assertTrue((output / "smoke_detection.jpg").is_file())

    def test_both_scripts_complete_training_reload_and_inference(self):
        for filename in ("yolov3_reproduction.py", "yolov4_reproduction.py"):
            with self.subTest(filename=filename):
                self.assert_smoke_pipeline_creates_reloadable_artifacts(filename)
```

- [ ] **Step 2: 运行隔离测试**

Run: `python -m unittest experiments.yolo_classics.tests.test_isolated_scripts -v`

Expected: `Ran 3 tests`，`OK`。如失败，删除所有仓库内导入，并把必要实现移入对应单文件；smoke 失败时保留 stderr，用它定位训练、检查点或推理解码问题。

- [ ] **Step 3: 编写运行说明**

`README.md` 给出 Python 版本、`pip install -r requirements.txt`、直接运行、四个子命令、VOC 与 YOLO 文本目录示例。明确说明单文件不下载权重，默认 inspect 不要求数据集。

- [ ] **Step 4: 提交**

```bash
git add experiments/yolo_classics/README.md experiments/yolo_classics/tests/test_isolated_scripts.py
git commit -m "测试：验证YOLO复现代码复制即跑"
```

## Task 10: 创建两个高密度单页实验

**Files:**
- Create: `wiki/experiments/experiment-yolov3-reproduction.md`
- Create: `wiki/experiments/experiment-yolov4-reproduction.md`
- Modify: `wiki/experiments/index.md`
- Modify: `tests/test_build_site.py`

- [ ] **Step 1: 写页面完整源码和导航测试**

```python
class ExperimentPageBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_site.build_site()

    def test_yolov3_page_contains_full_source(self):
        html = (build_site.SITE_DIR / "experiments" / "experiment-yolov3-reproduction.html").read_text(encoding="utf-8")
        self.assertIn("class YOLOv3", html)
        self.assertIn("def compute_yolov3_loss", html)
        self.assertNotIn("include-code:", html)

    def test_yolov4_page_contains_full_source(self):
        html = (build_site.SITE_DIR / "experiments" / "experiment-yolov4-reproduction.html").read_text(encoding="utf-8")
        self.assertIn("class YOLOv4", html)
        self.assertIn("def compute_yolov4_loss", html)
        self.assertNotIn("include-code:", html)

    def test_sidebar_contains_experiment_group(self):
        html = (build_site.SITE_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("实验 · 复现", html)
        self.assertIn("YOLOv3 完整复现", html)
        self.assertIn("YOLOv4 完整复现", html)
```

- [ ] **Step 2: 运行并确认页面尚不存在**

Run: `python -m unittest tests.test_build_site.ExperimentPageBuildTest -v`

Expected: `ERROR`，缺少两个实验 HTML 页面。

- [ ] **Step 3: 编写 YOLOv3 单页**

页面只使用一级网络标题和紧凑二级章节：结构速览、数学与张量、完整代码、关键实现解读、运行命令、输出与排错。完整代码位置使用：

```markdown
<!-- include-code: experiments/yolo_classics/yolov3_reproduction.py -->
```

解释必须覆盖 Darknet-53、FPN、三尺度张量、锚框匹配、损失四项、解码与 NMS，不重复基础 Python 教程。

- [ ] **Step 4: 编写 YOLOv4 单页**

结构与 YOLOv3 一致，完整代码位置使用：

```markdown
<!-- include-code: experiments/yolo_classics/yolov4_reproduction.py -->
```

解释必须覆盖 CSP、Mish、SPP、PAN、Mosaic、CIoU，以及与 YOLOv3 公平对比时必须保持一致的变量。

- [ ] **Step 5: 运行页面测试和构建**

Run: `python -m unittest tests.test_build_site.ExperimentPageBuildTest -v`

Expected: `Ran 3 tests`，`OK`。

Run: `python build_site.py`

Expected: 两个实验页面均显示 `[OK]`，构建完成。

- [ ] **Step 6: 提交**

```bash
git add wiki/experiments tests/test_build_site.py
git commit -m "文档：发布YOLOv3和YOLOv4单页复现实验"
```

## Task 11: 完整回归与页面可用性验收

**Files:**
- Modify only if verification exposes defects in files already listed above.

- [ ] **Step 1: 运行所有 Python 单元测试**

Run: `python -m unittest discover -s experiments/yolo_classics/tests -v`

Expected: YOLOv3、YOLOv4 和隔离执行测试全部 `OK`。

Run: `python -m unittest tests.test_build_site server.test_app -v`

Expected: 构建器与现有服务测试全部 `OK`。

- [ ] **Step 2: 运行两个独立脚本默认命令**

Run: `python experiments/yolo_classics/yolov3_reproduction.py`

Expected: 输出三个尺度、有限总损失和 `YOLOv3 inspect 完成`。

Run: `python experiments/yolo_classics/yolov4_reproduction.py`

Expected: 输出三个尺度、有限总损失和 `YOLOv4 inspect 完成`。

- [ ] **Step 3: 构建站点并检查生成内容**

Run: `python build_site.py`

Expected: 退出码 0，生成 `site/experiments/index.html`、YOLOv3 页面和 YOLOv4 页面。

Run: `rg -n "class YOLOv3|class YOLOv4|实验 · 复现" site/experiments site/index.html`

Expected: 三类文本均在生成站点中出现。

- [ ] **Step 4: 启动本地服务并做桌面/移动视觉检查**

Run: `python server/app.py`

Expected: 本地服务启动并打印访问地址。使用 Playwright 打开两个实验页面，在 1440×900 和 390×844 视口截图；检查侧栏、标题、正文无重叠，长代码块在自身区域横向滚动，页面宽度不被代码撑破。

- [ ] **Step 5: 修复验证发现的问题并重跑受影响测试**

只修改本计划列出的文件。每个修复先增加能够复现问题的断言，再修改实现，随后重跑 Task 11 Step 1–4。

- [ ] **Step 6: 最终提交**

```bash
git add build_site.py tests wiki experiments/yolo_classics
git commit -m "完成：交付YOLO经典网络复现实验板块"
```
