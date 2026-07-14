# Drone AI Algorithm Engineer Knowledge Base

[![License](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-green.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.10&#43;-blue.svg)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)

> This is a systematic knowledge base designed for drone AI algorithm engineers, covering a comprehensive knowledge体系 from foundational theory to engineering practice.

## 📦 Project Overview

This knowledge base aims to provide drone AI algorithm engineers with comprehensive, systematic, and actionable knowledge support. It covers core technical domains including deep learning theory, computer vision, SLAM, path planning, flight control systems, and engineering deployment, along with rich project tutorials and resume/interview resources.

**Key Features:**

- **Systematic Knowledge Structure**: Progressive learning from mathematical foundations to cutting-edge research
- **Engineering-Oriented**: Emphasis on practical code implementation and deployment experience
- **Resume-Friendly**: Each project includes core keywords and quantified achievement statements
- **Continuously Updated**: Documents the evolution of the knowledge base

## 📂 Directory Structure

```
drone-ai-wiki/
├── wiki/                      # Main knowledge base content
│   ├── concepts/              # Core concepts (20 pages)
│   │   ├── concept-deep-learning-basics.md
│   │   ├── concept-object-detection.md
│   │   ├── concept-slam.md
│   │   ├── concept-path-planning.md
│   │   ├── concept-drone-control.md
│   │   ├── concept-model-evaluation.md
│   │   ├── concept-training-methods.md
│   │   └── ...
│   ├── entities/              # Entity pages (6 pages)
│   │   ├── dataset-dota.md
│   │   ├── dataset-visdrone.md
│   │   ├── product-px4-autopilot.md
│   │   ├── product-ros2.md
│   │   ├── org-eth-asl.md
│   │   └── org-zhejiang-u-fast-lab.md
│   ├── topics/                # Topic overviews (11 pages)
│   │   ├── roadmap-drone-ai-engineer.md
│   │   ├── topic-ai-fundamentals-roadmap.md
│   │   ├── topic-perception-stack.md
│   │   ├── topic-precision-localization.md
│   │   ├── topic-crack-detection.md
│   │   ├── topic-license-plate-recognition.md
│   │   └── ...
│   ├── index.md               # Quick navigation entry
│   └── log.md                 # Change log
├── raw/                       # Raw source materials
│   ├── project-license-plate-recognition.md
│   ├── project-illegal-parking.md
│   ├── project-crack-detection.md
│   ├── project-precision-localization.md
│   └── pascanu13.pdf          # Classic paper
├── assets/                    # Static resources
│   ├── annotations.css
│   ├── annotations.js
│   └── favicon.svg
├── server/                    # Backend service (highlight notes feature)
│   ├── app.py
│   ├── requirements.txt
│   └── test_app.py
├── build_site.py              # Static site generator
├── SCHEMA.md                  # Knowledge base specification
├── Jenkinsfile                # CI/CD configuration
└── README.md
```

## 🛠️ Technology Stack

- **Content Format**: Markdown
- **Site Generation**: Python + Custom build scripts
- **Backend Service**: Python Flask (optional highlight notes feature)
- **Frontend**: Native HTML/CSS/JS

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://gitee.com/crawler111/drone-ai-wiki.git
cd drone-ai-wiki
```

### 2. Browse the Knowledge Base

Open `wiki/index.md` or `overview.md` directly:

```bash
# Use any Markdown preview tool
# e.g., VS Code + Markdown Preview extension
```

### 3. (Optional) Deploy Locally

```bash
# Install dependencies
pip install -r server/requirements.txt

# Start backend service (highlight notes feature)
cd server
cp .env.example .env  # Set password
python app.py

# Build static site
cd ..
python build_site.py
```

## 📚 Content Navigation

### Core Concepts (Concepts)

| Category | Content |
|--------|---------|
| AI Fundamentals | Deep learning theory, machine learning basics, mathematical foundations |
| Computer Vision | Object detection, semantic segmentation, classic backbone networks |
| Robotics | SLAM, state estimation, path planning, flight control systems |
| Engineering Practice | Model deployment, hyperparameter tuning, training methodologies |
| Communication Protocols | MQTT, ROS2 |
| Reinforcement Learning | RL fundamentals, PPO implementation, Sim-to-Real |

### Topic Overviews (Topics)

- **Learning Roadmaps**: Career path for drone AI algorithm engineers
- **Project Tutorials**: License plate recognition, illegal parking detection, crack detection, precision landing
- **Perception Systems**: Object detection, tracking, segmentation, depth estimation
- **Simulation & Deployment**: Gazebo + PX4 SITL, domain randomization

### Entity Resources (Entities)

- **Datasets**: DOTA, VisDrone
- **Open Source Projects**: PX4 Autopilot, ROS2
- **Research Institutions**: ETH ASL, Zhejiang University FAST-Lab

## 📈 Knowledge Base Health Metrics

- **Concept Pages**: 20
- **Entity Pages**: 6
- **Topic Pages**: 11
- **Raw Materials**: 6 files
- **Project Resources**: 4 complete resume-ready projects

## 🤝 Contribution Guidelines

Contributions via Issues or Pull Requests are welcome:

1. Follow naming conventions and formatting rules in `SCHEMA.md`
2. Ensure all cross-references are accurate
3. Update the index in `wiki/index.md`
4. Log changes in `wiki/log.md`

## 📄 License

This knowledge base is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).

## 📞 Contact

- Project Homepage: https://gitee.com/crawler111/drone-ai-wiki
- Feedback & Issues: https://gitee.com/crawler111/drone-ai-wiki/issues