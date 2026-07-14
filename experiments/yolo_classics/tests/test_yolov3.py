import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch
from PIL import Image

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


class YoloV3ModelTest(unittest.TestCase):
    def test_model_returns_three_detection_scales(self):
        model = y3.YOLOv3(num_classes=3, width_mult=0.25, depth_mult=0.25)
        outputs = model(torch.randn(1, 3, 128, 128))
        expected_channels = 3 * (5 + 3)
        self.assertEqual([tuple(x.shape) for x in outputs], [
            (1, expected_channels, 4, 4),
            (1, expected_channels, 8, 8),
            (1, expected_channels, 16, 16),
        ])

    def test_target_assignment_marks_one_best_anchor(self):
        targets = torch.tensor([[0.0, 1.0, 0.5, 0.5, 0.20, 0.20]])
        assigned = y3.build_targets(
            targets, 128, (4, 8, 16), y3.DEFAULT_ANCHORS, 3
        )
        positives = sum(int(scale[..., 4].sum().item()) for scale in assigned)
        self.assertEqual(positives, 1)


class YoloV3LossTest(unittest.TestCase):
    def test_loss_is_finite_and_backpropagates(self):
        torch.manual_seed(7)
        model = y3.YOLOv3(num_classes=2, width_mult=0.25, depth_mult=0.25)
        images = torch.randn(1, 3, 128, 128)
        targets = torch.tensor([[0.0, 1.0, 0.5, 0.5, 0.25, 0.20]])
        result = y3.compute_yolov3_loss(
            model(images), targets, 128, y3.DEFAULT_ANCHORS, 2
        )
        self.assertEqual(set(result), {"total", "box", "objectness", "classification"})
        self.assertTrue(torch.isfinite(result["total"]))
        result["total"].backward()
        gradients = [p.grad for p in model.parameters() if p.grad is not None]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(g).all() for g in gradients))


class YoloV3DataAndMetricTest(unittest.TestCase):
    def test_yolo_text_dataset_reads_normalized_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images, labels = root / "images", root / "labels"
            images.mkdir()
            labels.mkdir()
            Image.new("RGB", (80, 40), "white").save(images / "sample.jpg")
            (labels / "sample.txt").write_text("0 0.5 0.5 0.25 0.5\n", encoding="utf-8")
            dataset = y3.YoloTextDataset(images, labels, ["object"], image_size=64)
            image, target, _ = dataset[0]
            self.assertEqual(tuple(image.shape), (3, 64, 64))
            self.assertEqual(tuple(target.shape), (1, 5))
            self.assertTrue(torch.logical_and(target[:, 1:] >= 0, target[:, 1:] <= 1).all())

    def test_voc_dataset_reads_xml_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images, labels = root / "images", root / "labels"
            images.mkdir()
            labels.mkdir()
            Image.new("RGB", (100, 50), "white").save(images / "sample.jpg")
            (labels / "sample.xml").write_text(
                "<annotation><object><name>object</name><bndbox>"
                "<xmin>10</xmin><ymin>5</ymin><xmax>50</xmax><ymax>25</ymax>"
                "</bndbox></object></annotation>",
                encoding="utf-8",
            )
            dataset = y3.VOCDataset(images, labels, ["object"], image_size=64)
            _, target, _ = dataset[0]
            self.assertEqual(tuple(target.shape), (1, 5))

    def test_perfect_detection_has_map_one(self):
        detections = [torch.tensor([[10.0, 10.0, 30.0, 30.0, 0.9, 0.0]])]
        ground_truths = [torch.tensor([[10.0, 10.0, 30.0, 30.0, 0.0]])]
        metrics = y3.evaluate_detections(detections, ground_truths, num_classes=1)
        self.assertAlmostEqual(metrics["map50"], 1.0, places=6)


class YoloV3CliTest(unittest.TestCase):
    def test_no_arguments_runs_offline_inspect(self):
        script = Path(y3.__file__)
        result = subprocess.run(
            [sys.executable, str(script)],
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("YOLOv3 inspect 完成", result.stdout)


if __name__ == "__main__":
    unittest.main()
