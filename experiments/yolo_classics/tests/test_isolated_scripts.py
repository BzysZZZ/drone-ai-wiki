import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = ROOT / "experiments" / "yolo_classics"


class IsolatedScriptTest(unittest.TestCase):
    def copy_script(self, temporary_directory: str, filename: str) -> Path:
        """只复制被测网络文件，不复制包、配置或工具模块。"""
        copied = Path(temporary_directory) / filename
        shutil.copy2(SOURCE_DIR / filename, copied)
        return copied

    def assert_runs_after_copy(self, filename: str, marker: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = self.copy_script(tmp, filename)
            result = subprocess.run(
                [sys.executable, str(copied)],
                cwd=tmp,
                text=True,
                capture_output=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(marker, result.stdout)

    def assert_smoke_pipeline_creates_artifacts(self, filename: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = self.copy_script(tmp, filename)
            output = Path(tmp) / "artifacts"
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

    def test_yolov3_copy_runs_without_repository_imports(self):
        self.assert_runs_after_copy("yolov3_reproduction.py", "YOLOv3 inspect 完成")

    def test_yolov4_copy_runs_without_repository_imports(self):
        self.assert_runs_after_copy("yolov4_reproduction.py", "YOLOv4 inspect 完成")

    def test_both_scripts_complete_training_reload_and_inference(self):
        for filename in ("yolov3_reproduction.py", "yolov4_reproduction.py"):
            with self.subTest(filename=filename):
                self.assert_smoke_pipeline_creates_artifacts(filename)
