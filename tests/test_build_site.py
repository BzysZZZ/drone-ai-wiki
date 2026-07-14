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
