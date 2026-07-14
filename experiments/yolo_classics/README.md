# YOLOv3 / YOLOv4 单文件复现

这里的两个 Python 文件彼此独立，也不依赖知识库中的其他源码。可以把任意一个文件直接复制到 IDE 项目中运行。

## 环境

推荐 Python 3.10 或更高版本：

```bash
pip install -r requirements.txt
```

公开依赖只有 PyTorch、NumPy 和 Pillow。脚本不会自动访问网络或下载权重。

## 直接运行

```bash
python yolov3_reproduction.py
python yolov4_reproduction.py
```

无参数运行进入 `inspect`：使用 128×128 合成输入构建轻量验证模型，执行三尺度前向、损失计算和反向传播。默认完整模型仍使用论文对应的通道和残差深度。

## 数据目录

YOLO 文本格式：

```text
dataset/
├── images/
│   ├── 0001.jpg
│   └── 0002.jpg
├── labels/
│   ├── 0001.txt
│   └── 0002.txt
└── classes.txt
```

每行标签为 `class_id center_x center_y width height`，四个坐标归一化到 `[0, 1]`。VOC 格式把 `labels/` 中的同名文件替换为 Pascal VOC XML。

## 训练与推理

```bash
python yolov3_reproduction.py train --dataset-format yolo --images dataset/images --labels dataset/labels --classes dataset/classes.txt --epochs 100 --output-dir runs/yolov3
python yolov4_reproduction.py train --dataset-format voc --images VOC/JPEGImages --labels VOC/Annotations --classes classes.txt --epochs 100 --output-dir runs/yolov4

python yolov3_reproduction.py eval --dataset-format yolo --images dataset/images --labels dataset/labels --classes dataset/classes.txt --checkpoint runs/yolov3/best.pt
python yolov4_reproduction.py detect --checkpoint runs/yolov4/best.pt --image demo.jpg --output result.jpg
```

断点续训使用 `train --resume runs/yolov3/last.pt`。`smoke --output-dir smoke-output` 会用合成数据验证一次训练、保存、重载和推理闭环。
