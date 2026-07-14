# Wiki 索引

> **总页面数**: 39 | **最后更新**: 2026-06-30 | **知识库主题**: 无人机 AI 算法工程师 + AI 基本功

---

## 快速导航

- 🗺️ 学习路线图 → [[topics/roadmap-drone-ai-engineer]]
- 📚 AI基本功路线 → [[topics/topic-ai-fundamentals-roadmap]]
- 📖 基本功书单 → [[topics/topic-foundational-reading-list]]
- 🧪 网络复现实验 → [[experiments/index]]
- 🔌 MQTT 工程教程 → [[concepts/concept-mqtt-engineering]]
- 🤖 ROS2 工程教程 → [[entities/product-ros2]]
- 📖 Wiki 规则 → [[../SCHEMA.md]]
- 📝 变更日志 → [[log.md]]

---

## 按类型索引

### 🔷 概念页（Concepts）— 20 页

| 页面 | 描述 | 标签 |
|------|------|------|
| [[concepts/concept-object-detection]] | 目标检测原理、YOLO系列、无人机小目标挑战 | #感知 #深度学习 |
| [[concepts/concept-slam]] | SLAM系统分类、主流算法、选型指南 | #SLAM #多传感器融合 |
| [[concepts/concept-path-planning]] | 路径规划算法全览、EGO-Planner、轨迹优化 | #规划 |
| [[concepts/concept-drone-control]] | 飞控架构、PID/MPC、姿态估计 | #控制 |
| [[concepts/concept-multi-sensor-fusion]] | IMU/Camera/LiDAR 融合、VIO、标定 | #多传感器融合 #SLAM |
| [[concepts/concept-reinforcement-learning]] | RL在无人机的应用、Sim-to-Real、安全约束 | #强化学习 #控制 |
| [[concepts/method-model-deployment]] | TensorRT/RKNN推理加速、模型压缩、ROS2集成 | #部署 #工程 |
| [[concepts/concept-mqtt-engineering]] | MQTT协议、Mosquitto、Paho Python、无人机遥测与控制工程 | #MQTT #工程 |

#### AI 基本功（新增 12 页）

| 页面 | 描述 | 标签 |
|------|------|------|
| [[concepts/concept-math-foundation]] | 数学基础：线代/概率论/最优化，手推公式 | #数学 #面试 |
| [[concepts/concept-deep-learning-basics]] | DL核心：BN/LN/Dropout/激活/初始化/正则化 | #深度学习 #理论 |
| [[concepts/concept-loss-functions]] | 损失函数大全：CE/Focal/IoU/Dice/InfoNCE | #损失函数 |
| [[concepts/concept-cv-classic-backbones]] | 骨干网络谱系：ResNet→ViT→SwinT→ConvNeXt | #CV #骨干网络 |
| [[concepts/concept-training-methods]] | 训练方法论：数据增强/AMP/EMA/过拟合诊断/DDP | #训练 #工程 |
| [[concepts/concept-model-evaluation]] | 评估体系：mAP/mIoU/MAE/FPS 全指标 | #评估 #指标 |
| [[concepts/concept-hyperparameter-tuning]] | 超参数调优：Optuna/Bayesian/LR Range Test | #调优 #实验 |
| [[concepts/concept-ai-interview-qa]] | 算法面试题库：20道高频题 + 答题框架 | #面试 #求职 |
| [[concepts/concept-classical-ml-foundations]] | 经典机器学习：线性模型/EM/SVM/树模型/集成学习 | #机器学习 #统计学习 |
| [[concepts/concept-vision-geometry-foundations]] | 视觉几何：相机模型/标定/PnP/极几何/RANSAC/SIFT | #视觉几何 #SLAM |
| [[concepts/concept-state-estimation-foundations]] | 状态估计：Bayes Filter/Kalman/EKF/因子图/ESKF | #状态估计 #多传感器融合 |
| [[concepts/concept-planning-control-foundations]] | 规划控制：A*/RRT*/Minimum Snap/PID/LQR/MPC | #规划 #控制 |

### 🔶 实体页（Entities）— 6 页

#### 数据集

| 页面 | 描述 |
|------|------|
| [[entities/dataset-visdrone]] | 无人机视角目标检测最重要基准，天津大学发布 |
| [[entities/dataset-dota]] | 遥感旋转目标检测基准，武汉大学发布 |

#### 机构/组织

| 页面 | 描述 |
|------|------|
| [[entities/org-eth-asl]] | ETH Zurich ASL，SLAM/自主系统顶尖实验室 |
| [[entities/org-zhejiang-u-fast-lab]] | 浙大高飞实验室，EGO-Planner 发布机构 |

#### 产品/工具

| 页面 | 描述 |
|------|------|
| [[entities/product-px4-autopilot]] | 最广泛使用的开源飞控固件 |
| [[entities/product-ros2]] | 机器人节点系统工程框架，从零到无人机 ROS2 开发 |

### 🟢 主题页（Topics）— 11 页

| 页面 | 描述 | 类型 |
|------|------|------|
| [[topics/roadmap-drone-ai-engineer]] | 完整学习路线图，6阶段成长路径 | 路线图 |
| [[topics/topic-perception-stack]] | 感知系统全栈：检测/跟踪/分割/深度估计 | 综述 |
| [[topics/topic-slam-systems-comparison]] | 主流SLAM系统横向对比与选型指南 | 对比 |
| [[topics/topic-sim-to-real]] | 仿真到真机工作流、Sim-to-Real Gap解决方案 | 综述 |
| [[topics/topic-license-plate-recognition]] | 车牌识别：YOLOv8+LPRNet，CCPD数据集，TensorRT部署 | 项目 |
| [[topics/topic-illegal-parking-system]] | 车辆违停取证：ByteTrack跟踪+多边形ROI+停留时长统计 | 项目 |
| [[topics/topic-crack-detection]] | 无人机路面裂缝检测：SAHI+YOLOv8/SegFormer，7类裂缝 | 项目 |
| [[topics/topic-precision-localization]] | 无人机精准定位：ArUco视觉降落+RTK+EKF融合 | 项目 |
| [[topics/topic-precision-localization-code]] | 精准降落实际代码解析：ArUco检测、MQTT虚拟摇杆、分阶段状态机 | 代码解析 |
| [[topics/topic-ai-fundamentals-roadmap]] | **AI算法工程师基本功路线**：6阶段完整学习路径 | 路线图 |
| [[topics/topic-foundational-reading-list]] | **基本功书单与经典论文路线**：数学/ML/视觉/估计/规划控制书单 | 书单 |

### 📥 原始资料（Raw）— 6 份

| 文件 | 来源 |
|------|------|
| [[../raw/project-license-plate-recognition.md]] | 车牌识别技术调研 |
| [[../raw/project-illegal-parking.md]] | 违停取证技术调研 |
| [[../raw/project-crack-detection.md]] | 裂缝检测技术调研 |
| [[../raw/project-precision-localization.md]] | 精准定位技术调研 |
| [precision-landing-mqtt-code.txt](raw/precision-landing-mqtt-code.txt) | 现场版 ArUco + MQTT 虚拟摇杆精准降落脚本 |
| [[../raw/pascanu13.pdf]] | 梯度裁剪奠基论文（Pascanu et al., ICML 2013） |

---

## 按技术方向索引

### 项目专题
- [[topics/topic-license-plate-recognition]] — 车牌识别
- [[topics/topic-illegal-parking-system]] — 车辆违停取证
- [[topics/topic-crack-detection]] — 无人机道路裂缝检测
- [[topics/topic-precision-localization]] — 无人机精准定位
- [[topics/topic-precision-localization-code]] — 精准降落实际代码解析

### AI 基本功
- [[topics/topic-ai-fundamentals-roadmap]] — 6阶段学习路线
- [[topics/topic-foundational-reading-list]] — 基本功书单与经典论文路线
- [[concepts/concept-math-foundation]] — 数学基础
- [[concepts/concept-classical-ml-foundations]] — 经典机器学习
- [[concepts/concept-deep-learning-basics]] — DL理论
- [[concepts/concept-loss-functions]] — 损失函数
- [[concepts/concept-cv-classic-backbones]] — 骨干网络
- [[concepts/concept-training-methods]] — 训练方法
- [[concepts/concept-model-evaluation]] — 评估体系
- [[concepts/concept-hyperparameter-tuning]] — 调优实战
- [[concepts/concept-ai-interview-qa]] — 面试题库
- [[concepts/concept-vision-geometry-foundations]] — 视觉几何基本功
- [[concepts/concept-state-estimation-foundations]] — 状态估计基本功
- [[concepts/concept-planning-control-foundations]] — 规划与控制基本功

### 感知方向
- [[concepts/concept-object-detection]] — 目标检测
- [[concepts/concept-vision-geometry-foundations]] — 视觉几何基本功
- [[topics/topic-perception-stack]] — 感知全栈
- [[entities/dataset-visdrone]] — VisDrone 数据集
- [[entities/dataset-dota]] — DOTA 数据集

### SLAM & 定位
- [[concepts/concept-slam]] — SLAM 综述
- [[entities/product-ros2]] — ROS2 节点系统开发
- [[concepts/concept-state-estimation-foundations]] — 状态估计基本功
- [[concepts/concept-vision-geometry-foundations]] — 视觉几何基本功
- [[concepts/concept-multi-sensor-fusion]] — 多传感器融合
- [[topics/topic-slam-systems-comparison]] — SLAM 对比选型
- [[topics/topic-precision-localization-code]] — ArUco精准降落实战代码
- [[concepts/concept-mqtt-engineering]] — 精准降落 MQTT 控制链路

### 规划方向
- [[concepts/concept-path-planning]] — 路径规划
- [[concepts/concept-planning-control-foundations]] — 规划与控制基本功
- [[entities/org-zhejiang-u-fast-lab]] — EGO-Planner 出处

### 控制方向
- [[concepts/concept-drone-control]] — 飞控与控制
- [[entities/product-ros2]] — ROS2 控制节点组织
- [[concepts/concept-planning-control-foundations]] — 规划与控制基本功
- [[entities/product-px4-autopilot]] — PX4 飞控
- [[concepts/concept-reinforcement-learning]] — RL 控制

### 工程与部署
- [[concepts/method-model-deployment]] — 模型部署
- [[concepts/concept-mqtt-engineering]] — MQTT 遥测与控制工程
- [[entities/product-ros2]] — ROS2 节点系统开发
- [[topics/topic-sim-to-real]] — 仿真工作流

### 前沿研究
- [[concepts/concept-reinforcement-learning]] — RL 前沿
- [[entities/org-eth-asl]] — ETH ASL

---

## 待创建页面（建议）

> 以下概念已在现有页面中多次提及，建议后续创建独立页面：

- [ ] `concepts/concept-semantic-segmentation` — 语义分割
- [ ] `concepts/algo-yolo-series` — YOLO 系列完整谱系
- [ ] `entities/dataset-uavdt` — UAVDT 数据集
- [ ] `entities/hardware-lidar-sensors` — LiDAR 传感器选型
- [ ] `entities/hardware-flight-computers` — 机载计算平台（Jetson/RK3588）
- [ ] `entities/product-ardupilot` — ArduPilot 飞控
- [ ] `entities/org-hkust-mars-lab` — 港科大 MARS Lab（VINS-Mono 出处）
- [ ] `topics/topic-control-stack` — 控制系统全栈
- [ ] `topics/topic-planning-stack` — 规划系统全栈
- [ ] `topics/topic-deployment-workflow` — 部署工程流程
- [ ] `topics/topic-multi-uav-cooperation` — 多机协同

---

*本索引由 LLM Wiki Expert 自动维护，每次 Ingest 后更新。*




