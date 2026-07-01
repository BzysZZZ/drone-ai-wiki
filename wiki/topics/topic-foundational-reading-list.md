# 基本功书单与经典论文路线

> **类型**: topic
> **创建时间**: 2026-06-29
> **最后更新**: 2026-06-29
> **来源**: AI综合，优先官方书页/课程页/论文页
> **标签**: #基本功 #论文 #书单 #数学 #机器学习 #机器人

## 摘要

本页用于把无人机 AI 算法工程师需要长期反复阅读的“底层书”和“奠基论文”集中管理。现有知识库已经覆盖深度学习、检测、SLAM、规划、控制等工程主题，本页补齐更底层的数学、经典机器学习、视觉几何、状态估计、规划控制与强化学习阅读路线。

> 使用原则：不要把论文当收藏夹。每篇经典论文都要能回答三个问题：它解决了什么基本问题、核心假设是什么、今天的工程系统哪里还在用它。

---

## 总阅读顺序

| 阶段 | 目标 | 必读材料 | 对应页面 |
|------|------|----------|----------|
| 1 | 数学与概率底座 | Mathematics for Machine Learning、Convex Optimization、Information Theory | [[concepts/concept-math-foundation]] |
| 2 | 经典机器学习 | ESL、PRML、SVM、EM、Boosting、Random Forest | [[concepts/concept-classical-ml-foundations]] |
| 3 | 深度学习训练 | Deep Learning、Efficient BackProp、Xavier/Kaiming、BN、Dropout、Pascanu | [[concepts/concept-deep-learning-basics]], [[concepts/concept-training-methods]] |
| 4 | 视觉几何 | Szeliski、Multiple View Geometry、RANSAC、SIFT、标定、光流 | [[concepts/concept-vision-geometry-foundations]] |
| 5 | 状态估计与 SLAM | Probabilistic Robotics、Barfoot、Kalman、粒子滤波、因子图 | [[concepts/concept-state-estimation-foundations]] |
| 6 | 规划与控制 | Planning Algorithms、Feedback Systems、Modern Robotics、A*/RRT*/Minimum Snap | [[concepts/concept-planning-control-foundations]] |
| 7 | 强化学习 | Sutton & Barto、TD/Q-learning/Policy Gradient/DQN/PPO | [[concepts/concept-reinforcement-learning]] |

---

## 必读书籍清单

### 数学、优化、统计

| 书 | 作者 | 读法 | 为什么必读 |
|----|------|------|------------|
| Mathematics for Machine Learning | Deisenroth, Faisal, Ong | 线代、向量微积分、概率、优化按需读 | 用 ML 语境重讲数学，适合补短板 |
| Convex Optimization | Boyd, Vandenberghe | 重点读凸集、凸函数、对偶、KKT | 轨迹优化、模型训练、约束控制都绕不开 |
| The Elements of Statistical Learning | Hastie, Tibshirani, Friedman | 重点读线性模型、正则化、树模型、Boosting、SVM | 从统计学习视角理解模型复杂度与泛化 |
| Probabilistic Machine Learning | Kevin Murphy | 重点读概率图模型、贝叶斯推断、EM、状态空间模型 | 统一理解估计、感知、不确定性 |
| Information Theory, Inference, and Learning Algorithms | David MacKay | 信息论、编码、推断章节 | 交叉熵、KL、互信息、MDL 的底层直觉 |

### 机器学习与深度学习

| 书 | 作者 | 读法 | 为什么必读 |
|----|------|------|------------|
| Machine Learning | Tom Mitchell | 作为传统 ML 目录书 | 决策树、贝叶斯、学习理论、RL 的经典入口 |
| Pattern Recognition and Machine Learning | Christopher Bishop | 重点读概率模型、EM、核方法、图模型 | 比 ESL 更概率化，适合理解生成模型 |
| Deep Learning | Goodfellow, Bengio, Courville | 重点读优化、正则化、CNN/RNN、表示学习 | 深度学习总教材 |
| Dive into Deep Learning | Zhang et al. | 跟代码复现 | 把理论与 PyTorch/JAX/MXNet 实现连起来 |

### 机器人、视觉、规划控制

| 书 | 作者 | 读法 | 为什么必读 |
|----|------|------|------------|
| Computer Vision: Algorithms and Applications | Richard Szeliski | 视觉几何、特征、运动、重建章节 | CV 工程师的视觉总教材 |
| Multiple View Geometry | Hartley, Zisserman | 相机模型、极几何、PnP、三角化、BA | SLAM/VIO/三维重建的根教材 |
| Probabilistic Robotics | Thrun, Burgard, Fox | Bayes filter、MCL、SLAM | 移动机器人概率基础 |
| State Estimation for Robotics | Timothy Barfoot | 李群、最小二乘、Kalman、批量估计 | 现代 VIO/SLAM 的数学底座 |
| Planning Algorithms | Steven LaValle | 搜索、采样规划、反馈规划 | 路径规划和运动规划总教材 |
| Feedback Systems | Åström, Murray | 反馈、稳定性、PID/LQR/MPC 基础 | 控制系统的工程直觉 |
| Modern Robotics | Lynch, Park | 刚体运动、李群、Jacobian、动力学 | 位姿、轨迹、控制实现的统一语言 |
| Underactuated Robotics | Russ Tedrake | Quadrotor、LQR、轨迹优化、非线性控制 | 无人机欠驱动系统理解入口 |

---

## 经典论文阅读矩阵

| 方向 | 论文 | 读完应掌握 |
|------|------|------------|
| 经典 ML | Perceptron, Backprop, EM, SVM, AdaBoost, Random Forest | 从线性分类到集成学习的基本路线 |
| 深度训练 | Efficient BackProp, Xavier, Kaiming, BN, Dropout, Adam, Pascanu | 初始化、归一化、正则化、优化稳定性 |
| 视觉几何 | Canny, Lucas-Kanade, Horn-Schunck, Harris, RANSAC, SIFT, HOG, Zhang Calibration | 从局部特征到相机标定与鲁棒估计 |
| 状态估计 | Kalman Filter, Particle Filter, FastSLAM, Factor Graphs, SLAM Survey, VIO Survey | 从滤波到平滑、从在线估计到因子图优化 |
| 规划控制 | A*, PRM, RRT, RRT*, D* Lite, Minimum Snap, Geometric Quadrotor Control | 从离散搜索到连续轨迹、从几何控制到飞行 |
| 强化学习 | TD Learning, Q-learning, REINFORCE, Policy Gradient Theorem, DQN, TRPO, PPO | Bellman 方程、价值函数、策略梯度和稳定训练 |

---

## 30 天补基本功计划

| 周 | 主题 | 每天输出 |
|----|------|----------|
| 第 1 周 | 数学与经典 ML | 手推 1 个公式 + 总结 1 篇经典论文 |
| 第 2 周 | 深度学习训练 | 复现 1 个小实验：初始化/BN/Dropout/Adam/梯度裁剪 |
| 第 3 周 | 视觉几何与状态估计 | 手写 RANSAC/PnP 或 Kalman/EKF 的最小 demo |
| 第 4 周 | 规划控制与 RL | 写 A*/RRT* demo，读 Minimum Snap 或 PPO |

### 每篇论文的标准卡片

```markdown
## 论文卡片
- 问题：这篇论文解决什么基本问题？
- 输入/输出：算法吃什么、产出什么？
- 核心假设：哪些条件不满足时会失效？
- 关键公式：最重要的 1-3 个公式。
- 工程位置：今天在哪些系统里还能看到它？
- 复现任务：用 50-100 行代码复现最小版本。
```

---

## 关联

- 相关路线: [[topics/topic-ai-fundamentals-roadmap]], [[topics/roadmap-drone-ai-engineer]]
- 相关概念: [[concepts/concept-math-foundation]], [[concepts/concept-classical-ml-foundations]], [[concepts/concept-vision-geometry-foundations]], [[concepts/concept-state-estimation-foundations]], [[concepts/concept-planning-control-foundations]]
- 深度学习: [[concepts/concept-deep-learning-basics]], [[concepts/concept-training-methods]], [[concepts/concept-reinforcement-learning]]

## 引用来源

- [1] Deisenroth, M. P., Faisal, A. A., & Ong, C. S. **Mathematics for Machine Learning**. Cambridge University Press, 2020. https://mml-book.github.io/
- [2] Boyd, S., & Vandenberghe, L. **Convex Optimization**. Cambridge University Press, 2004. https://web.stanford.edu/~boyd/cvxbook/
- [3] Hastie, T., Tibshirani, R., & Friedman, J. **The Elements of Statistical Learning**. Springer, 2009. https://hastie.su.domains/ElemStatLearn/
- [4] Murphy, K. P. **Probabilistic Machine Learning**. MIT Press. https://probml.github.io/pml-book/
- [5] Szeliski, R. **Computer Vision: Algorithms and Applications**. Springer, 2022. https://szeliski.org/Book/
- [6] LaValle, S. M. **Planning Algorithms**. Cambridge University Press, 2006. https://lavalle.pl/planning/
- [7] Sutton, R. S., & Barto, A. G. **Reinforcement Learning: An Introduction**. MIT Press, 2018. http://incompleteideas.net/book/the-book-2nd.html

## 变更记录

- 2026-06-29: 初始创建，补充基本功书单、经典论文矩阵和 30 天阅读计划。
