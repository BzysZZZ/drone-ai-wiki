# 经典机器学习基本功

> **类型**: concept
> **创建时间**: 2026-06-29
> **最后更新**: 2026-06-29
> **来源**: AI综合，见引用来源
> **标签**: #基本功 #机器学习 #统计学习 #面试

## 摘要

经典机器学习是深度学习之前形成的建模基本功：线性模型、概率模型、核方法、集成学习、无监督学习与泛化理论。无人机 AI 工程中即使大量使用深度网络，也仍然需要这些基础来理解特征、分类边界、过拟合、数据不平衡、异常检测和模型评估。

---

## 知识地图

```
经典机器学习
├── 线性模型
│   ├── 线性回归 / Ridge / Lasso
│   └── Logistic Regression / Softmax
├── 概率模型
│   ├── Naive Bayes / GMM / EM
│   └── HMM / CRF / 图模型
├── 核方法
│   ├── SVM / Kernel Trick
│   └── SVR / One-Class SVM
├── 树与集成
│   ├── Decision Tree / Random Forest
│   └── AdaBoost / GBDT / XGBoost
├── 无监督学习
│   ├── K-Means / GMM
│   └── PCA / t-SNE / UMAP
└── 学习理论
    ├── Bias-Variance
    ├── VC Dimension
    └── Regularization
```

---

## 核心算法速查

| 算法 | 核心思想 | 工程用途 | 面试要点 |
|------|----------|----------|----------|
| Linear Regression | 最小化平方误差 | 标定曲线、误差拟合、趋势估计 | 正规方程、岭回归、过拟合 |
| Logistic Regression | 线性 logit + sigmoid | 二分类 baseline、可解释模型 | CE 损失、MLE、决策边界 |
| Naive Bayes | 条件独立假设 | 文本/离散特征快速 baseline | 先验、似然、平滑 |
| K-Means | 最小化类内平方距离 | 聚类、anchor 聚类、数据清洗 | 初始化敏感、局部最优 |
| GMM + EM | 隐变量概率模型 | 多峰分布、目标运动模式建模 | E-step/M-step 推导 |
| SVM | 最大间隔分类 | 小样本、高维特征分类 | 间隔、支持向量、核技巧 |
| Decision Tree | 贪心划分特征空间 | 规则提取、可解释模型 | Gini/Entropy、剪枝 |
| Random Forest | Bagging 多棵树投票 | 强 baseline、特征重要性 | 降低方差、OOB 评估 |
| AdaBoost | 错样本重加权 | 分类器集成 | 指数损失、弱学习器 |
| PCA | 最大方差低维投影 | 降维、去噪、可视化 | SVD、协方差特征分解 |

---

## 必读经典论文

| 论文 | 年份 | 核心贡献 | 为什么仍然重要 |
|------|------|----------|----------------|
| The Perceptron | 1958 | 感知机线性分类器 | 神经网络和线性分类的起点 |
| Learning representations by back-propagating errors | 1986 | 反向传播训练多层网络 | 现代深度学习训练基础 |
| Maximum likelihood from incomplete data via the EM algorithm | 1977 | EM 算法 | GMM、HMM、缺失数据、隐变量模型 |
| Support-Vector Networks | 1995 | SVM 与最大间隔 | 核方法和凸优化分类器代表 |
| A Decision-Theoretic Generalization of On-Line Learning and an Application to Boosting | 1997 | AdaBoost | 集成学习与加性模型基础 |
| Random Forests | 2001 | 随机森林 | 工业强 baseline 与特征重要性 |
| Stochastic Gradient Descent Tricks | 2012 | SGD 工程经验 | 深度学习优化经验的传统源头 |

---

## EM 算法最小推导

EM 用于最大化含隐变量 z 的似然：

```
目标: log p(x | theta) = log sum_z p(x, z | theta)

E-step:
  Q(theta, theta_old) = E_{z ~ p(z|x,theta_old)} [ log p(x,z|theta) ]

M-step:
  theta_new = argmax_theta Q(theta, theta_old)
```

直觉：如果隐变量 z 不知道，就先用旧参数估计“每个样本属于哪个隐状态”的软概率，再用这些软标签更新参数。K-Means 可以看作 GMM 在协方差相同且趋近 0 时的硬分配近似。

---

## SVM 与最大间隔

线性可分时，SVM 选择离两类样本都尽量远的分割超平面：

```
minimize    1/2 ||w||^2
subject to  y_i (w^T x_i + b) >= 1
```

软间隔版本：

```
minimize    1/2 ||w||^2 + C sum_i xi_i
subject to  y_i (w^T x_i + b) >= 1 - xi_i, xi_i >= 0
```

核技巧把内积 `x_i^T x_j` 替换为核函数 `K(x_i, x_j)`，相当于在不显式构造高维特征的情况下做非线性分类。

---

## 与无人机 AI 的关系

| 场景 | 为什么要懂经典 ML |
|------|-------------------|
| 小样本缺陷检测 | SVM/Random Forest 可能比小网络更稳定 |
| 传感器异常检测 | GMM、One-Class SVM、Isolation Forest 可作为轻量方案 |
| 目标跟踪 | Kalman + 匈牙利匹配常与传统距离度量结合 |
| 标定与误差建模 | 最小二乘、RANSAC、鲁棒估计是基础工具 |
| 数据集分析 | PCA/t-SNE/聚类能发现类别混淆和数据偏差 |
| 模型解释 | 树模型和线性模型是工程汇报中的可解释 baseline |

---

## 学习检验

1. 手推 Logistic Regression 的交叉熵梯度。
2. 写出 Ridge Regression 的闭式解。
3. 解释 EM 为什么每轮不会降低似然。
4. 说明 SVM 中 C 增大/减小对间隔和误分类的影响。
5. 比较 Bagging 和 Boosting：一个主要降方差，一个主要降偏差。
6. 用 `sklearn` 在同一数据集上比较 Logistic Regression、SVM、Random Forest 和 XGBoost。

---

## 关联

- 总书单: [[topics/topic-foundational-reading-list]]
- 数学基础: [[concepts/concept-math-foundation]]
- 模型评估: [[concepts/concept-model-evaluation]]
- 深度学习基础: [[concepts/concept-deep-learning-basics]]

## 引用来源

- [1] Rosenblatt, F. (1958). **The Perceptron: A Probabilistic Model for Information Storage and Organization in the Brain**. Psychological Review.
- [2] Rumelhart, D. E., Hinton, G. E., & Williams, R. J. (1986). **Learning representations by back-propagating errors**. Nature.
- [3] Dempster, A. P., Laird, N. M., & Rubin, D. B. (1977). **Maximum likelihood from incomplete data via the EM algorithm**. JRSS-B.
- [4] Cortes, C., & Vapnik, V. (1995). **Support-Vector Networks**. Machine Learning.
- [5] Freund, Y., & Schapire, R. E. (1997). **A Decision-Theoretic Generalization of On-Line Learning and an Application to Boosting**. JCSS.
- [6] Breiman, L. (2001). **Random Forests**. Machine Learning.
- [7] Hastie, T., Tibshirani, R., & Friedman, J. **The Elements of Statistical Learning**. https://hastie.su.domains/ElemStatLearn/
- [8] Mitchell, T. **Machine Learning**. https://www.cs.cmu.edu/~tom/mlbook.html

## 变更记录

- 2026-06-29: 初始创建，补充经典机器学习算法地图、必读论文和工程关联。
