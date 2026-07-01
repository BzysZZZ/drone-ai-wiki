# 变更日志



## 2026-06-30 — 云端同步划线笔记功能

> **操作**: Feature — 将静态知识库升级为支持右侧划线笔记、个人登录和云端同步的学习系统
> **影响页面/模块**: 6 项（Flask API + SQLite + 前端资产 + 构建器注入 + 站点资源复制 + 部署配置）

### 新增
- ✅ `server/app.py` — Flask + SQLite 笔记 API，支持登录、状态检查、页面笔记列表、创建、更新、删除。
- ✅ `server/test_app.py` — 后端 API 单元测试，覆盖未登录拦截、登录成功/失败、笔记 CRUD。
- ✅ `assets/annotations.css` — 可折叠右侧笔记栏、浮动划线工具条、高亮颜色、移动端抽屉样式。
- ✅ `assets/annotations.js` — 选中文本、保存高亮、恢复高亮、编辑笔记、切换颜色、删除笔记、登录交互。

### 更新
- 🔧 [[../build_site.py]] — 每个静态 HTML 页面注入云端笔记栏，并复制 `assets/` 到 `site/assets/`。

### 部署提示
- 静态页面继续由 Nginx 发布。
- `/api/` 需要反向代理到 `127.0.0.1:5000` 的 Flask 服务。
- 服务器上配置 `ANNOTATION_PASSWORD`、`FLASK_SECRET_KEY` 和 `ANNOTATION_DB`。

---
## 2026-06-30 — MQTT 与 ROS2 零基础工程教程

> **操作**: Expand — 将精准降落代码依赖的 MQTT 与 ROS2 工程基础补成从 0 到开发经验的完整教程
> **影响页面**: 6 项（2 新增 + 4 处索引/关联/构建更新）

### 新增
- ✅ [[concepts/concept-mqtt-engineering]] — MQTT 工程开发教程：Broker、Client、Topic、QoS、Retain、Will、Mosquitto、Paho Python、安全部署、无人机遥测与控制主题设计。
- ✅ [[entities/product-ros2]] — ROS2 工程开发教程：Node、Topic、Service、Action、Parameter、Launch、TF2、rosbag、rclpy、多节点无人机系统设计。

### 更新
- 📑 [[index.md]] — 总页面数 37→39，概念页 19→20，实体页 5→6，新增 MQTT/ROS2 快速入口与技术方向索引。
- 📑 [[topics/topic-precision-localization-code]] — 增加 MQTT/ROS2 学习入口，说明 `MqttAdapter` 和 ROS2 多节点拆分的学习路径。
- 📑 [[topics/topic-precision-localization]] — 增加零基础学习依赖说明。
- 🔧 [[../build_site.py]] — 增加 MQTT/ROS2 新页面中文标题映射。

### 解析重点
- MQTT 从本机 Mosquitto 实验推进到无人机遥测、命令回复、控制权、安全和故障排查。
- ROS2 从节点图和工作空间推进到发布订阅、Service、Action、Parameter、Launch、TF2、rosbag 和精准降落节点拆分。

---
## 2026-06-30 — 精准降落实际代码摄入与教科书级解析

> **操作**: Ingest — 摄入桌面 `code.txt` 中的现场版精准降落脚本
> **影响页面**: 5 项（1 raw 新增 + 1 topic 新增 + 3 处索引/构建更新）

### 新增
- ✅ [raw/precision-landing-mqtt-code.txt](raw/precision-landing-mqtt-code.txt) — 现场版 ArUco + MQTT 虚拟摇杆精准降落脚本，覆盖视频输入、视觉检测、状态机、控制下发和安全收尾。
- ✅ [[topics/topic-precision-localization-code]] — 代码级解析页：解释 `MqttAdapter`、`ArucoLandingController`、H.264 tail 输入、像素几何估高、定时修正控制律、低空 LAND 逻辑和参数调试顺序。

### 更新
- 📑 [[topics/topic-precision-localization]] — 增加实际代码解析入口，保留原页作为精准定位/精准降落总览。
- 📑 [[index.md]] — 总页面数 36→37，主题页 10→11，raw 资料 5→6，新增代码解析入口。
- 🔧 [[../build_site.py]] — 新增代码解析页中文标题映射，并在构建时复制 raw 下的非 Markdown 附件，保证 `.txt` 和 `.pdf` 可随站点部署。

### 解析重点
- 把实际脚本拆解为输入层、感知层、估计层、决策层、执行层。
- 将 `SEARCH → ALIGN → DESCEND → LAND` 状态机整理为可复用控制流程。
- 解释为什么现场脚本使用“悬停测量 → 定时拨杆 → 再测量”，而不是简单连续 PID。
- 总结虚拟摇杆死区、方向标定、高度源选择、触地确认和异常恢复的调试方法。

---

## 2026-06-29 — 基本功书单与经典论文体系补充

> **操作**: 扩展基本功知识体系 — 新增 5 个页面并更新索引/路线页
> **影响页面**: 7 页（5 新增 + 2 更新）

### 新增页面
- ✅ [[topics/topic-foundational-reading-list]] — 基本功书单与经典论文路线：数学、经典机器学习、视觉几何、状态估计、规划控制、强化学习总路线
- ✅ [[concepts/concept-classical-ml-foundations]] — 经典机器学习基本功：线性模型、EM、SVM、树模型、Boosting、Random Forest
- ✅ [[concepts/concept-vision-geometry-foundations]] — 视觉几何基本功：相机模型、标定、PnP、极几何、RANSAC、SIFT、光流
- ✅ [[concepts/concept-state-estimation-foundations]] — 状态估计基本功：Bayes Filter、Kalman、EKF/UKF、粒子滤波、因子图、ESKF
- ✅ [[concepts/concept-planning-control-foundations]] — 规划与控制基本功：A*、PRM/RRT/RRT*、Minimum Snap、PID/LQR/MPC、四旋翼控制

### 更新内容
- 📑 [[index.md]] — 总页面数 31→36，概念页 15→19，主题页 9→10，AI 基本功索引扩展到 12 个概念页 + 1 个书单专题
- 📑 [[topics/topic-ai-fundamentals-roadmap]] — 新增“基本功扩展书单”入口，串联新基础页
- 🔧 [[../build_site.py]] — 补充新页面中文标题映射，侧边栏显示中文标题

### 设计原则
- 书单页做路线和总览，不重复展开已有深度学习/CV/SLAM 页面内容
- 四个 concept 页各自聚焦一类底层能力：传统 ML、视觉几何、状态估计、规划控制
- 每页保留现有知识库格式：摘要、知识地图、表格、代码/公式、关联、引用来源、变更记录

---

## 2026-06-29 — Lint 健康巡检 + 索引修复
> **操作**: Lint — 全库健康检查 + 修复计数
> **影响页面**: 2 页修复

### 巡检结果
- ✅ **孤立页面**: 0 — 所有 29 个内容页均被 ≥2 个其他页面引用
- ✅ **零引用页面**: 0 — 最低 6 篇（数据集页），核心概念/主题页 12-18 篇
- ✅ **矛盾标注**: 0 — 无跨页面结论矛盾
- ⚠️ **待创建页面**: 13 个建议（见 index.md 待创建列表），其中 4 个已被现有页面明确提及（ros2/ardupilot/hkust-mars-lab/planning-stack）

### 修复内容
- 🔧 [[index.md]] — 总页面数 30→31，概念页 14→15（修正 AI 基本功 8 页未计入的错误）
- 🔧 [[log.md]] — 移除过时的初始化警告（"[AI综合整理]"），状态更新为已完成论文 Ingest

### 交叉引用密度
| 引用次数 | 页面 |
|---------|------|
| 13 | [[concepts/concept-object-detection]] |
| 11 | [[topics/topic-crack-detection]] |
| 10 | [[concepts/concept-deep-learning-basics]], [[entities/product-px4-autopilot]] |
| 9 | [[concepts/concept-drone-control]], [[concepts/concept-multi-sensor-fusion]], [[concepts/concept-path-planning]] |
| 8 | [[concepts/concept-slam]], [[topics/topic-license-plate-recognition]], [[topics/topic-precision-localization]] |
| 2-7 | 其余 17 个页面 |

---

## 2026-06-29 — Ingest Pascanu et al. 2013（梯度裁剪奠基论文）

> **操作**: Ingest — 摄入 [[../raw/pascanu13.pdf]]
> **影响页面**: 3 页核心概念更新

### 新增
- 📥 [[../raw/pascanu13.pdf]] — Pascanu, Mikolov & Bengio, "On the Difficulty of Training Recurrent Neural Networks," ICML 2013.

### 内容注入
- 📝 [[concepts/concept-training-methods]] — 新增「梯度裁剪理论」完整小节：Jacobian 连乘分析、悬崖地貌假说、Algorithm 1 手动实现、阈值启发式、消逝梯度正则化、实验验证表
- 📝 [[concepts/concept-deep-learning-basics]] — 新增「消失与爆炸梯度」小节：Jacobian 谱分析、50层 Sigmoid/ReLU 模拟代码、谱半径检查代码、8种解决方案对比表
- 📝 [[concepts/concept-math-foundation]] — 新增「动力系统视角」小节：吸引子/分岔边界/谱半径/Lyapunov 指数模拟代码、悬崖地貌假说几何解释、信赖域类比

### 交叉引用
- 🔗 [[concepts/concept-training-methods]] ↔ [[concepts/concept-deep-learning-basics]] ↔ [[concepts/concept-math-foundation]]（同一论文的三个理论视角）
- 🔗 [[../raw/pascanu13.pdf]] → [[concepts/concept-training-methods]], [[concepts/concept-deep-learning-basics]], [[concepts/concept-math-foundation]]

### 索引更新
- 📑 [[index.md]] — raw 资料从 4 份增至 5 份，更新最后更新日期

---

## 2026-06-27 — 论文引用全面补充（最终收尾）

> **操作**: 扩写补强 — 补齐4个论文引用为0/1的页面，知识库完整度收尾
> **影响页面**: 4 页（全量扩写）

### 扩写详情
- 📝 [[topics/topic-perception-stack]] — 从1篇扩至18篇引用；补充 MOT 完整对比表、SAHI代码、深度估计对比表、3DGS航拍流程、感知-规划坐标变换代码、Jetson 性能基准表
- 📝 [[topics/roadmap-drone-ai-engineer]] — 从1篇扩至17篇引用；补充 ROS2 Publisher C++ 模板、各阶段里程碑细化、必读论文清单（按主题分类）、顶会录取率表
- 📝 [[entities/product-px4-autopilot]] — 从1篇扩至15篇引用；补充完整 ROS2 Offboard Python 代码（200行）、uORB C++ 示例、EKF2 多传感器融合配置、关键参数速查表、Gazebo 一键启动命令
- 📝 [[topics/topic-ai-fundamentals-roadmap]] — 从0篇扩至15篇引用；补充 ResNet Bottleneck + BN 前向/反向代码、10道面试题精选含标准答案、15篇必读论文表、部署流水线完整命令

### 交叉引用补充
- 🔗 [[topics/topic-perception-stack]] ↔ [[topics/topic-crack-detection]]（感知技术应用）
- 🔗 [[entities/product-px4-autopilot]] ↔ [[topics/topic-sim-to-real]]（仿真集成）
- 🔗 [[topics/topic-ai-fundamentals-roadmap]] ↔ [[topics/roadmap-drone-ai-engineer]]（路线图汇总）

---

## 2026-06-27 — 基本功知识体系 + 项目深度增强
> **操作**: 大幅增强 — AI 算法工程师基本功 8 个新页面 + 4 项目环境配置/完整代码
> **影响页面**: 15 页（8 新增 + 4 增强 + 3 更新）

### 新增页面（基本功）
- ✨ [[concepts/concept-math-foundation]] — 数学基础（线代/概率论/最优化 + 必会推导）
- ✨ [[concepts/concept-deep-learning-basics]] — DL理论（BN/LN/Dropout/激活/初始化/正则化+代码）
- ✨ [[concepts/concept-loss-functions]] — 损失函数大全（CE/Focal/IoU/Dice/InfoNCE 完整实现）
- ✨ [[concepts/concept-cv-classic-backbones]] — 骨干网络谱系（ResNet→ViT→SwinT→ConvNeXt）
- ✨ [[concepts/concept-training-methods]] — 训练方法论（增强/AMP/EMA/过拟合诊断/DDP模板）
- ✨ [[concepts/concept-model-evaluation]] — 评估体系（mAP/mIoU/MAE/FPS 全指标+代码）
- ✨ [[concepts/concept-hyperparameter-tuning]] — 调优实战（Optuna/Bayesian/LR Range Test）
- ✨ [[concepts/concept-ai-interview-qa]] — 算法面试题库（20道高频题+STAR框架）
- ✨ [[topics/topic-ai-fundamentals-roadmap]] — AI基本功6阶段路线图

### 增强页面（项目）
- 📝 [[topics/topic-license-plate-recognition]] — 新增环境配置、CCPD转换代码、LPRNet定义、CTC解码、完整推理管线、训练命令
- 📝 [[topics/topic-illegal-parking-system]] — 新增环境配置、200+行推理管线、ROI管理器、违停引擎、证据生成器、架构图、参数调优
- 📝 [[topics/topic-crack-detection]] — 新增环境配置、SAHI手工+库双方案、裂缝量化(骨架/宽度/等级)、GSD坐标映射、完整Pipeline
- 📝 [[topics/topic-precision-localization]] — 新增硬件/软件环境、ArUco检测节点、PID控制节点、螺旋搜索、PX4参数、Gazebo仿真、架构图

### 技术改进
- 🔧 [[../build_site.py]] — 添加完整中文标题映射表（TITLE_MAP），侧边栏全部中文显示
- 📝 [[index.md]] — 索引更新至 30 页，新增 AI 基本功分类

---

## 2026-06-27 — 四项目资料大幅升级 + 侧边栏修复

> **操作**: 补充升级 — 四个简历项目的 raw/ 资料和 topic 页大幅扩充
> **触发**: 用户要求补充资料并修复网站侧边栏
> **影响页面**: 8 页（4 raw + 4 topic 全部重写）+ build_site.py 修复

### 资料升级内容
- 📝 更新: [[raw/project-license-plate-recognition.md]] — 新增完整 Python 代码（CCPD转换/YOLOv8训练/LPRNet架构/CTC解码/透视矫正/格式校验）、训练指南、TensorRT/RKNN部署方案
- 📝 更新: [[raw/project-illegal-parking.md]] — 新增完整推理管线代码（ROI多边形判定/ByteTrack跟踪/违停引擎/证据生成/Supervision集成）、多区域管理方案
- 📝 更新: [[raw/project-crack-detection.md]] — 新增 SAHI 手工切片+库调用双方案、USSC-YOLO论文方案、裂缝量化(骨架提取/宽度计算/GB/T分级)、GSD坐标映射、数据增强策略
- 📝 更新: [[raw/project-precision-localization.md]] — 新增 ROS2 完整控制节点代码、solvePnP位姿估计、PX4三阶段参数、螺旋搜索、Gazebo仿真启动步骤、传感器融合策略表
- 📝 更新: [[topics/topic-license-plate-recognition]]、[[topics/topic-illegal-parking-system]]、[[topics/topic-crack-detection]]、[[topics/topic-precision-localization]] — Wiki 同步更新

### 网站修复
- 🔧 修复: `build_site.py` 侧边栏链接路径 — 子目录页面统一加 `../` 前缀
- 🔧 修复: Wiki 正文 `[[link]]` 同步修正相对路径

### 数据来源
- PX4 官方 Precision Landing 文档、GitHub 开源项目 (Illegal-Parking-Detection, precision_landing)、USSC-YOLO 论文 (Sensors 2024)、CCPD 数据集转换教程

---

## 2026-06-27 — 项目资料 Ingest（4个简历项目）

> **操作**: Ingest — 灌入4个项目技术资料，编译为 Wiki 页面
> **触发**: 用户提供简历项目列表（车牌识别/违停取证/裂缝检测/精准定位）
> **影响页面**: 8 页（4 raw + 4 wiki）

### 新增原始资料（raw/）

- ✨ 新增: [[raw/project-license-plate-recognition.md]] — 车牌识别技术调研
- ✨ 新增: [[raw/project-illegal-parking.md]] — 车辆违停取证技术调研
- ✨ 新增: [[raw/project-crack-detection.md]] — 无人机裂缝检测技术调研
- ✨ 新增: [[raw/project-precision-localization.md]] — 无人机精准定位技术调研

### 新增 Wiki 页面

- ✨ 新增: [[topics/topic-license-plate-recognition]] — YOLOv8+LPRNet 完整 Pipeline
- ✨ 新增: [[topics/topic-illegal-parking-system]] — ByteTrack+多边形ROI违停取证
- ✨ 新增: [[topics/topic-crack-detection]] — SAHI+YOLOv8/SegFormer 裂缝检测
- ✨ 新增: [[topics/topic-precision-localization]] — ArUco视觉精准降落+RTK

### 交叉引用建立

- 🔗 [[topics/topic-illegal-parking-system]] ↔ [[topics/topic-license-plate-recognition]]（违停系统集成车牌识别）
- 🔗 [[topics/topic-crack-detection]] ↔ [[topics/topic-precision-localization]]（精准定位保障裂缝巡检）
- 🔗 [[topics/topic-license-plate-recognition]] ↔ [[concepts/concept-object-detection]]
- 🔗 [[topics/topic-precision-localization]] ↔ [[entities/product-px4-autopilot]]

### 同步更新

- 📝 更新: [[wiki/index.md]] — 新增 8 页，总页面数 14→22
- 📝 更新: [[wiki/log.md]] — 追加本次 Ingest 记录

---

## 2026-06-27 — 知识库初始化

> **操作**: Init — 从零创建无人机 AI 算法工程师知识库
> **触发**: 用户请求，知识库初始化
> **影响页面**: 14 页（新增）

#### 概念页（Concepts）
- ✨ 新增: [[concepts/concept-object-detection]] — 目标检测综述，含YOLO系列、小目标检测、嵌入式部署
- ✨ 新增: [[concepts/concept-slam]] — SLAM系统分类，特征/直接/半直接法，主流开源对比
- ✨ 新增: [[concepts/concept-path-planning]] — 路径规划全览，全局/局部规划，轨迹优化
- ✨ 新增: [[concepts/concept-drone-control]] — 无人机飞控，PID/MPC/RL控制，PX4架构
- ✨ 新增: [[concepts/concept-multi-sensor-fusion]] — 多传感器融合，VIO/LiDAR-IMU，标定工具
- ✨ 新增: [[concepts/concept-reinforcement-learning]] — RL在无人机应用，Sim-to-Real，安全约束
- ✨ 新增: [[concepts/method-model-deployment]] — 嵌入式部署，TensorRT/RKNN，模型压缩

#### 实体页（Entities）
- ✨ 新增: [[entities/dataset-visdrone]] — VisDrone 无人机目标检测基准数据集
- ✨ 新增: [[entities/dataset-dota]] — DOTA 遥感旋转目标检测基准数据集
- ✨ 新增: [[entities/org-eth-asl]] — ETH Zurich ASL，顶尖自主系统实验室
- ✨ 新增: [[entities/org-zhejiang-u-fast-lab]] — 浙大高飞实验室，EGO-Planner 出处
- ✨ 新增: [[entities/product-px4-autopilot]] — PX4 开源飞控固件

#### 主题页（Topics）
- ✨ 新增: [[topics/roadmap-drone-ai-engineer]] — 无人机AI工程师完整学习路线图（6阶段）
- ✨ 新增: [[topics/topic-perception-stack]] — 感知系统全栈综述
- ✨ 新增: [[topics/topic-slam-systems-comparison]] — SLAM系统横向对比与选型指南
- ✨ 新增: [[topics/topic-sim-to-real]] — 仿真到真机工作流

### 交叉引用建立

- 🔗 [[concepts/concept-object-detection]] ↔ [[entities/dataset-visdrone]]
- 🔗 [[concepts/concept-object-detection]] ↔ [[entities/dataset-dota]]
- 🔗 [[concepts/concept-slam]] ↔ [[concepts/concept-multi-sensor-fusion]]
- 🔗 [[concepts/concept-path-planning]] ↔ [[concepts/concept-drone-control]]
- 🔗 [[concepts/concept-reinforcement-learning]] ↔ [[topics/topic-sim-to-real]]
- 🔗 [[concepts/method-model-deployment]] ↔ [[entities/product-px4-autopilot]]
- 🔗 [[entities/org-eth-asl]] ↔ [[concepts/concept-slam]]
- 🔗 [[entities/org-zhejiang-u-fast-lab]] ↔ [[concepts/concept-path-planning]]
- 🔗 [[topics/roadmap-drone-ai-engineer]] — 汇聚所有核心页面

### 待完善项（Lint 预警）

- ⚠️ 13 个建议创建但尚无独立页面的概念（见 index.md 待创建列表）
- ✅ 所有页面已通过多轮 Ingest 获得论文/文档引用（最低 6 篇，核心页面 15-18 篇）

---

*变更日志由 LLM Wiki Expert 自动维护。*





