# 无人机 AI 算法工程师知识库

[![License](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-green.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)

> 这是一个面向无人机 AI 算法工程师的系统化知识库，涵盖从基础理论到工程实践的完整知识体系。

## 📦 项目简介

本知识库旨在为无人机 AI 算法工程师提供全面、系统、可操作的知识支持。内容涵盖深度学习理论、计算机视觉、SLAM、路径规划、飞控系统、工程部署等核心技术领域，并提供丰富的项目实战指南和简历面试资源。

**核心特点：**

- **系统化知识体系**：从数学基础到前沿研究，循序渐进
- **工程导向**：注重实际代码实现和部署经验
- **简历友好**：每个项目包含核心关键词和量化成果句式
- **持续更新**：记录知识库的演进历程

## 📂 目录结构

```
drone-ai-wiki/
├── wiki/                      # 知识库主要内容
│   ├── concepts/              # 核心概念（20页）
│   │   ├── concept-deep-learning-basics.md
│   │   ├── concept-object-detection.md
│   │   ├── concept-slam.md
│   │   ├── concept-path-planning.md
│   │   ├── concept-drone-control.md
│   │   ├── concept-model-evaluation.md
│   │   ├── concept-training-methods.md
│   │   └── ...
│   ├── entities/              # 实体页（6页）
│   │   ├── dataset-dota.md
│   │   ├── dataset-visdrone.md
│   │   ├── product-px4-autopilot.md
│   │   ├── product-ros2.md
│   │   ├── org-eth-asl.md
│   │   └── org-zhejiang-u-fast-lab.md
│   ├── topics/                # 主题综述（11页）
│   │   ├── roadmap-drone-ai-engineer.md
│   │   ├── topic-ai-fundamentals-roadmap.md
│   │   ├── topic-perception-stack.md
│   │   ├── topic-precision-localization.md
│   │   ├── topic-crack-detection.md
│   │   ├── topic-license-plate-recognition.md
│   │   └── ...
│   ├── index.md               # 快速导航入口
│   └── log.md                 # 变更记录
├── raw/                       # 原始资料
│   ├── project-license-plate-recognition.md
│   ├── project-illegal-parking.md
│   ├── project-crack-detection.md
│   ├── project-precision-localization.md
│   └── pascanu13.pdf          # 经典论文
├── assets/                    # 静态资源
│   ├── annotations.css
│   ├── annotations.js
│   └── favicon.svg
├── server/                    # 后端服务（划线笔记功能）
│   ├── app.py
│   ├── requirements.txt
│   └── test_app.py
├── build_site.py              # 静态站点生成器
├── SCHEMA.md                  # 知识库规范文档
├── Jenkinsfile                # CI/CD 配置
└── README.md
```

## 🛠️ 技术栈

- **内容格式**：Markdown
- **站点生成**：Python + 自定义构建脚本
- **后端服务**：Python Flask（可选的划线笔记功能）
- **前端**：原生 HTML/CSS/JS

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://gitee.com/crawler111/drone-ai-wiki.git
cd drone-ai-wiki
```

### 2. 浏览知识库

直接打开 `wiki/index.md` 或 `overview.md` 开始浏览：

```bash
# 使用任意 Markdown 预览工具
# 例如 VS Code + Markdown Preview 插件
```

### 3.（可选）本地部署站点

```bash
# 安装依赖
pip install -r server/requirements.txt

# 启动后端服务（划线笔记功能）
cd server
cp .env.example .env  # 配置密码
python app.py

# 构建静态站点
cd ..
python build_site.py
```

## 📚 内容导航

### 核心概念（Concepts）

| 分类 | 内容 |
|------|------|
| AI 基础 | 深度学习理论、机器学习基本功、数学基础 |
| 计算机视觉 | 目标检测、语义分割、经典骨干网络 |
| 机器人 | SLAM、状态估计、路径规划、飞控与控制 |
| 工程实践 | 模型部署、超参数调优、训练方法论 |
| 通信协议 | MQTT、ROS2 |
| 强化学习 | 强化学习基础、PPO 实现、Sim-to-Real |

### 主题专题（Topics）

- **学习路线图**：无人机 AI 算法工程师成长路径
- **项目实战**：车牌识别、违停检测、裂缝检测、精准降落
- **感知系统**：目标检测、跟踪、分割、深度估计
- **仿真部署**：Gazebo + PX4 SITL、域随机化

### 实体资料（Entities）

- **数据集**：DOTA、VisDrone
- **开源项目**：PX4 Autopilot、ROS2
- **研究机构**：ETH ASL、浙江大学 FAST-Lab

## 📈 知识库健康度

- **概念页**：20 页
- **实体页**：6 页
- **主题页**：11 页
- **原始资料**：6 份
- **项目资料**：4 个完整简历项目

## 🤝 贡献指南

欢迎提交 Issue 或 Pull Request 来完善知识库：

1. 遵守 `SCHEMA.md` 中的命名规范和格式要求
2. 确保交叉引用正确
3. 更新 `wiki/index.md` 的索引
4. 在 `wiki/log.md` 中记录变更

## 📄 许可证

本知识库采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可证。

## 📞 联系方式

- 项目主页：https://gitee.com/crawler111/drone-ai-wiki
- 问题反馈：https://gitee.com/crawler111/drone-ai-wiki/issues