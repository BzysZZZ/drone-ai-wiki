import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

from experiments.yolo_classics import yolov4_reproduction as y4


class YoloV4CoreTest(unittest.TestCase):
    def test_ciou_is_one_for_identical_boxes(self):
        boxes = torch.tensor([[0.0, 0.0, 2.0, 2.0]])
        torch.testing.assert_close(y4.complete_iou(boxes, boxes), torch.ones(1))

    def test_mosaic_returns_fixed_image_and_valid_boxes(self):
        images = [np.full((32, 32, 3), i * 30, dtype=np.uint8) for i in range(4)]
        labels = [np.array([[0, 0.5, 0.5, 0.5, 0.5]], dtype=np.float32) for _ in range(4)]
        image, merged = y4.mosaic_augment(images, labels, output_size=64, center=(32, 32))
        self.assertEqual(image.shape, (64, 64, 3))
        self.assertEqual(merged.shape[1], 5)
        self.assertTrue(np.logical_and(merged[:, 1:] >= 0, merged[:, 1:] <= 1).all())

    def test_model_returns_three_scales(self):
        model = y4.YOLOv4(num_classes=3, width_mult=0.25, depth_mult=0.25)
        outputs = model(torch.randn(1, 3, 128, 128))
        channels = 3 * (5 + 3)
        self.assertEqual([tuple(x.shape) for x in outputs], [
            (1, channels, 4, 4),
            (1, channels, 8, 8),
            (1, channels, 16, 16),
        ])


class YoloV4TrainingTest(unittest.TestCase):
    def test_loss_is_finite_and_backpropagates(self):
        torch.manual_seed(11)
        model = y4.YOLOv4(num_classes=2, width_mult=0.25, depth_mult=0.25)
        images = torch.randn(1, 3, 128, 128)
        targets = torch.tensor([[0.0, 1.0, 0.5, 0.5, 0.20, 0.30]])
        result = y4.compute_yolov4_loss(
            model(images), targets, 128, y4.DEFAULT_ANCHORS, 2, label_smoothing=0.01
        )
        self.assertTrue(torch.isfinite(result["total"]))
        result["total"].backward()
        gradients = [p.grad for p in model.parameters() if p.grad is not None]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(g).all() for g in gradients))


class YoloV4CliTest(unittest.TestCase):
    def test_no_arguments_runs_offline_inspect(self):
        result = subprocess.run(
            [sys.executable, str(Path(y4.__file__))],
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("YOLOv4 inspect 完成", result.stdout)


if __name__ == "__main__":
    unittest.main()
