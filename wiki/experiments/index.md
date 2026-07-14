# 实验 · 复现

这里收录经典网络的完整教学复现。每种网络对应一个高密度页面和一份自包含 Python 源码：把源码完整复制到 IDE，安装页面列出的公开依赖后即可运行，不依赖知识库中的其他 Python 模块。

## 目标检测

- [[experiments/experiment-yolov3-reproduction]]：Darknet-53、FPN、三尺度检测头、训练、评估与推理。
- [[experiments/experiment-yolov4-reproduction]]：CSPDarknet-53、SPP、PAN、Mosaic、CIoU、训练、评估与推理。

## 复现约定

- 页面展示完整源码，不使用省略号或伪代码替代实现。
- 无参数运行源码时执行合成数据检查，不要求预先下载数据或权重。
- 真实训练支持 VOC XML 和通用 YOLO 文本标注。
- 每份源码都通过复制到临时目录后的独立运行测试。
