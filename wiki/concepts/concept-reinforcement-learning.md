# 强化学习（Reinforcement Learning）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

强化学习（RL）通过智能体与环境交互，最大化累积奖励来学习策略，在无人机自主飞行、避障、竞速和操控任务中取得了突破性进展。深度强化学习（DRL）结合神经网络，使 RL 能处理高维连续观测空间。

## 核心要素

```
MDP（马尔可夫决策过程）:
  状态 S: 无人机位姿、速度、传感器读数
  动作 A: 电机推力/Roll/Pitch/Yaw
  奖励 R: 到达目标+（避障惩罚）+（能耗惩罚）
  转移 P: P(s'|s,a)，环境动力学
  折扣 γ: 0.99（重视长期奖励）

目标: max E[Σ γᵗ r_t]
```

## 主流算法对比

| 算法 | 策略类型 | 动作空间 | 样本效率 | 稳定性 | 无人机应用 |
|------|---------|---------|---------|--------|-----------|
| DQN | Off-policy | 离散 | 中 | 中 | 路点选择 |
| PPO | On-policy | 连续/离散 | 低 | 高 | 飞行控制(✅主流) |
| TRPO | On-policy | 连续 | 低 | 高 | 基线对比 |
| SAC | Off-policy | 连续 | 高 | 高 | 精细控制 |
| TD3 | Off-policy | 连续 | 高 | 中 | 竞速 |
| DDPG | Off-policy | 连续 | 高 | 低 | 较少 |
| A3C/A2C | On-policy | 连续 | 低 | 中 | 并行训练 |

## PPO 实现详解

```python
import torch
import torch.nn as nn

class ActorCritic(nn.Module):
    """无人机飞行控制 Actor-Critic 网络"""
    def __init__(self, obs_dim=18, act_dim=4):
        super().__init__()
        # 共享主干
        self.shared = nn.Sequential(
            nn.Linear(obs_dim, 256), nn.ELU(),
            nn.Linear(256, 256), nn.ELU(),
        )
        # Actor：输出动作均值（4个电机推力归一化）
        self.actor_mean = nn.Linear(256, act_dim)
        self.actor_logstd = nn.Parameter(torch.zeros(act_dim))
        # Critic：输出状态价值
        self.critic = nn.Linear(256, 1)
    
    def forward(self, obs):
        feat = self.shared(obs)
        mean = torch.tanh(self.actor_mean(feat))  # 归一化到 [-1,1]
        std = torch.exp(self.actor_logstd).expand_as(mean)
        return mean, std, self.critic(feat)

def ppo_update(policy, optimizer, rollout_buffer, clip_eps=0.2, epochs=10):
    """PPO 裁剪目标更新"""
    for _ in range(epochs):
        for batch in rollout_buffer.get_batches():
            obs, acts, old_log_probs, advantages, returns = batch
            mean, std, values = policy(obs)
            dist = torch.distributions.Normal(mean, std)
            log_probs = dist.log_prob(acts).sum(-1)
            
            # 重要性采样比率
            ratio = torch.exp(log_probs - old_log_probs)
            
            # PPO 裁剪损失
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1-clip_eps, 1+clip_eps) * advantages
            actor_loss = -torch.min(surr1, surr2).mean()
            
            # Critic 损失
            critic_loss = nn.MSELoss()(values.squeeze(), returns)
            
            # 熵正则（鼓励探索）
            entropy_loss = -dist.entropy().sum(-1).mean()
            
            loss = actor_loss + 0.5*critic_loss + 0.01*entropy_loss
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            optimizer.step()
```

## 奖励函数设计

```python
def compute_reward(state, action, next_state, target_pos, collision):
    """无人机导航任务奖励函数设计"""
    reward = 0.0
    
    # 1. 到达目标奖励（稀疏）
    dist_to_goal = np.linalg.norm(next_state['pos'] - target_pos)
    if dist_to_goal < 0.3:
        reward += 100.0  # 到达奖励
    
    # 2. 距离进展奖励（密集，加速学习）
    prev_dist = np.linalg.norm(state['pos'] - target_pos)
    reward += 2.0 * (prev_dist - dist_to_goal)  # 越近越好
    
    # 3. 碰撞惩罚
    if collision:
        reward -= 50.0
    
    # 4. 平滑飞行奖励（减少振荡）
    action_smoothness = -0.01 * np.sum(action**2)
    reward += action_smoothness
    
    # 5. 姿态惩罚（防止倒飞）
    if abs(state['roll']) > 0.5 or abs(state['pitch']) > 0.5:
        reward -= 2.0
    
    # 6. 时间惩罚（鼓励快速到达）
    reward -= 0.01
    
    return reward
```

## Sim-to-Real 迁移

无人机 RL 最大挑战是 Sim-to-Real Gap：

```yaml
主要差异:
  - 空气阻力/气动效应建模不准
  - 电机响应延迟（sim: 0 vs real: 5-10ms）
  - 传感器噪声差异
  - 机身振动

解决方案:
  1. 域随机化（Domain Randomization）:
     - 随机化质量、惯性、电机参数 ±20%
     - 随机化风扰 0~3m/s
     - 随机化传感器噪声
  
  2. Sim-to-Real 精调:
     - 先在仿真预训练
     - 少量真机数据微调
  
  3. 自适应控制:
     - 在线估计系统参数
     - Meta-RL（MAML）快速适应

仿真平台:
  IsaacGym: GPU并行，百万帧/秒
  Gazebo: 物理精确，速度慢
  Flightmare: 无人机专用，快速
```

## 分层强化学习

```
高层策略（Low Frequency, 10Hz）:
  输入: 任务描述、地图
  输出: 子目标（路径点）

低层策略（High Frequency, 100Hz）:
  输入: 当前状态、子目标
  输出: 电机控制

优势:
  - 高层可用规划算法
  - 低层专注控制精度
  - 各层独立训练
```

## 论文引用

- [1] **DQN** — Mnih et al., "Human-level Control through Deep Reinforcement Learning," Nature 2015. [DRL奠基]
- [2] **PPO** — Schulman et al., "Proximal Policy Optimization Algorithms," arXiv 2017. [最常用算法]
- [3] **SAC** — Haarnoja et al., "Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning," ICML 2018.
- [4] **TD3** — Fujimoto et al., "Addressing Function Approximation Error in Actor-Critic Methods," ICML 2018.
- [5] **Domain Randomization** — Tobin et al., "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World," IROS 2017.
- [6] **Champion Racing** — Kaufmann et al., "Champion-level Drone Racing Using Deep Reinforcement Learning," Nature 2023. [无人机RL最高成就]
- [7] **Learning to Fly** — Loquercio et al., "Learning High-Speed Flight in the Wild," Science Robotics 2021.
- [8] **Neural Fly** — O'Connell et al., "Neural-Fly Enables Rapid Learning for Agile Flight in Strong Winds," Science Robotics 2022.
- [9] **IsaacGym** — Makoviychuk et al., "Isaac Gym: High Performance GPU-Based Physics Simulation for Robot Learning," NeurIPS 2021.
- [10] **Flightmare** — Song et al., "Flightmare: A Flexible Quadrotor Simulator," CoRL 2020.
- [11] **MAML** — Finn et al., "Model-Agnostic Meta-Learning for Fast Adaptation of Deep Networks," ICML 2017. [Meta-RL基础]
- [12] **Hierarchical RL** — Nachum et al., "Data-Efficient Hierarchical Reinforcement Learning," NeurIPS 2018.
- [13] **Safe RL** — Garcia & Fernández, "A Comprehensive Survey on Safe Reinforcement Learning," JMLR 2015.
- [14] **RL避障** — Panerati et al., "Learning to Fly in Seconds," CoRL 2023.
- [15] **Gym-PyBullet-Drones** — Panerati et al., "Learning to Fly – a Gym Environment with PyBullet Physics for Reinforcement Learning of Multi-agent Quadcopter Control," IROS 2021.

## 关联

- 相关概念: [[concept-drone-control]], [[concept-path-planning]], [[concept-deep-learning-basics]]
- 参见: [[topics/topic-sim-to-real]], [[topics/topic-precision-localization]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——MDP框架、算法对比表、PPO完整代码、奖励函数、Sim-to-Real方案、分层RL、15篇论文引用
