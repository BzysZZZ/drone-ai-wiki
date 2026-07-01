# 无人机 AI 算法工程师知识库 — 概览

> **创建时间**: 2026-06-27
> **版本**: v1.0.0
> **知识库路径**: `drone-ai-wiki/`

---

## 📦 这个知识库是什么？

这是一个基于 **LLM Wiki 模式**（Andrej Karpathy）搭建的个人知识库，专为**无人机 AI 算法工程师**设计。它能随着你积累的资料不断"编译"成体系化知识，形成覆盖感知、SLAM、规划、控制、部署的完整知识图谱。

---

## 📂 目录结构

```
drone-ai-wiki/
├── SCHEMA.md              ← Wiki 规则与标签体系
├── raw/                   ← 📥 你的资料投放区（论文、文章、笔记）
└── wiki/
    ├── index.md           ← 📋 总目录索引
    ├── log.md             ← 📝 变更日志
    ├── concepts/          ← 算法/理论/方法（7 页）
    ├── entities/          ← 数据集/机构/产品（5 页）
    └── topics/            ← 综述/对比/路线图（4 页）
```

---

## 📚 已创建页面（共 16 页）

### 🗺️ 入口页（必看）
| 页面 | 一句话描述 |
|------|-----------|
| `wiki/index.md` | 所有页面的导航总目录 |
| `wiki/topics/roadmap-drone-ai-engineer.md` | 6阶段学习路线，从入门到前沿 |

### 🧠 核心概念（7 页）
| 页面 | 内容亮点 |
|------|---------|
| `concept-object-detection` | YOLO系列演进、小目标挑战、OBB旋转检测 |
| `concept-slam` | 全类型SLAM对比、选型建议、学习路线 |
| `concept-path-planning` | EGO-Planner原理、Minimum Snap轨迹、地图表示 |
| `concept-drone-control` | PX4架构、PID/MPC/RL控制、Offboard接口 |
| `concept-multi-sensor-fusion` | VIO/LiDAR-IMU融合、标定工具、松/紧耦合 |
| `concept-reinforcement-learning` | PPO/SAC在无人机应用、域随机化、安全约束RL |
| `method-model-deployment` | TensorRT/RKNN加速、Jetson选型、ROS2集成 |

### 🏢 实体（5 页）
| 页面 | 关键信息 |
|------|---------|
| `dataset-visdrone` | 无人机目标检测最重要基准，10类，天津大学 |
| `dataset-dota` | 遥感OBB检测基准，18类，武汉大学 |
| `org-eth-asl` | ORB-SLAM3/Kalibr/Agile Autonomy 出处 |
| `org-zhejiang-u-fast-lab` | EGO-Planner/Fast-Planner 出处，高飞团队 |
| `product-px4-autopilot` | PX4 架构、uORB、Offboard 接口说明 |

### 📊 主题综述（4 页）
| 页面 | 内容 |
|------|------|
| `topic-perception-stack` | 感知系统全链路架构图 |
| `topic-slam-systems-comparison` | SLAM 选型决策树 + 横向对比表 |
| `topic-sim-to-real` | 仿真平台对比 + Sim-to-Real Gap 解决方案 |
| `roadmap-drone-ai-engineer` | 完整技术路线图 |

---

## 🚀 如何使用这个知识库

### 1. 投放原始资料（Ingest）
把论文、文章、会议笔记放入 `raw/` 目录，然后告诉 AI：
```
请 Ingest raw/ 目录下的新文件
```
AI 会自动提取关键信息，创建/更新相关 Wiki 页面，并更新索引和变更日志。

### 2. 查询知识（Query）
直接提问：
```
EGO-Planner 和 Fast-Planner 有什么区别？
Jetson Orin NX 和 RK3588 哪个适合跑 YOLOv8？
VIO 在弱纹理场景下容易丢失追踪，如何解决？
```
AI 会基于 Wiki 内容综合回答，并引用来源页面。

### 3. 健康巡检（Lint）
定期运行：
```
检查知识库的健康状态
```
AI 会报告矛盾内容、过时信息、孤立页面和缺失引用。

### 4. 扩展知识库
参考 `wiki/index.md` 中的"待创建页面"列表，优先补充：
- `concept-state-estimation`（EKF/ESKF）
- `algo-yolo-series`（YOLO完整谱系）
- `hardware-flight-computers`（Jetson/RK3588选型）

---

## 📈 当前知识库健康度

| 指标 | 状态 | 说明 |
|------|------|------|
| 总页面数 | 16 | 含 SCHEMA.md、index.md、log.md |
| 核心概念覆盖 | ✅ 7/7 | 感知/SLAM/规划/控制/融合/RL/部署 |
| 交叉引用密度 | ⭐⭐⭐ | 平均每页 4-6 条引用链接 |
| 原始资料溯源 | ⚠️ 待补充 | 初始化内容为 AI 综合整理 |
| 孤立页面 | 0 | 所有页面均有引用 |
| 待创建引用页 | 13 | 见 index.md 待创建列表 |

---

## 🔮 推荐下一步行动

1. **添加原始资料**：将你收藏的无人机/机器视觉论文放入 `raw/`，执行 Ingest
2. **补充硬件页**：创建 `hardware-flight-computers.md`，对比 Jetson 系列与 RK3588
3. **补充 HKUST MARS Lab**：VINS-Mono 出处，与现有 SLAM 内容强关联
4. **添加项目实战笔记**：将你参与项目的经验记录在 `raw/notes-xxx.md`

---

*由 LLM Wiki Expert 生成 · 2026-06-27*
