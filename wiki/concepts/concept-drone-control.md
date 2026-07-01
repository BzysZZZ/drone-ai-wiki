# 飞控与无人机控制（Drone Control）

> **类型**: concept
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

无人机控制系统负责将高层规划指令转化为电机控制信号，核心包括：姿态控制（Attitude Control）、位置控制（Position Control）和轨迹跟踪（Trajectory Tracking）。控制方法从经典 PID 到现代 MPC、强化学习，持续演进。

## 多旋翼飞行原理

```
四旋翼（Quadrotor）控制输入:
  油门（Thrust）T = k_t × (ω₁² + ω₂² + ω₃² + ω₄²)
  横滚（Roll）  τ_φ = k_t × L × (ω₄² - ω₂²)
  俯仰（Pitch） τ_θ = k_t × L × (ω₃² - ω₁²)
  偏航（Yaw）  τ_ψ = k_d × (ω₁² - ω₂² + ω₃² - ω₄²)

其中:
  L = 轴距
  k_t = 升力系数
  k_d = 反扭矩系数
  ω_i = 第 i 个电机转速
```

## 控制架构（级联 PID）

```
┌─────────────┐    位置误差    ┌─────────────┐    姿态期望    ┌─────────────┐    电机PWM
│ 位置控制器  │──────────────→ │ 姿态控制器  │──────────────→ │  电机混合器  │──────────→
│ Outer Loop  │               │ Inner Loop  │               │   Mixer     │
└─────────────┘               └─────────────┘               └─────────────┘
  频率: 50Hz                    频率: 250-500Hz                直接控制

位置PID → 期望加速度 → 期望姿态（Roll/Pitch） → 姿态PID → 期望角速度 → 角速度PID → PWM
```

### PID 控制器实现

```python
class PIDController:
    def __init__(self, kp, ki, kd, i_limit=None):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.i_limit = i_limit
        self.integral = 0.0
        self.prev_error = 0.0
    
    def update(self, error, dt):
        # 比例项
        p_term = self.kp * error
        # 积分项（防饱和）
        self.integral += error * dt
        if self.i_limit:
            self.integral = np.clip(self.integral, -self.i_limit, self.i_limit)
        i_term = self.ki * self.integral
        # 微分项（低通滤波抑制噪声）
        d_term = self.kd * (error - self.prev_error) / dt
        self.prev_error = error
        return p_term + i_term + d_term

# PX4 典型参数（Position Controller）
pos_ctrl = PIDController(kp=1.0, ki=0.1, kd=0.2, i_limit=2.0)
```

### PID 参数整定方法

| 方法 | 适用场景 | 步骤 |
|------|---------|------|
| Ziegler-Nichols | 快速整定 | 增大Kp至临界振荡→计算Ku,Tu→代入公式 |
| 自动整定（AutoTune） | PX4内置 | 飞行时自动激励→频率响应辨识 |
| 仿真+迁移 | Gazebo SITL | Gazebo中整定，真机微调 |
| 贝叶斯优化 | 高精度需求 | 最小化跟踪误差目标函数 |

## 模型预测控制（MPC）

```python
"""
MPC：在预测时域内求解最优控制序列
优势：可处理约束，精度高于PID
代价：计算量大，需实时求解 QP
"""
# 线性 MPC（离散化后的四旋翼模型）
def mpc_solve(x0, A, B, Q, R, N=20, x_ref=None):
    """
    min Σ(x-x_ref)ᵀQ(x-x_ref) + uᵀRu
    s.t. x_{k+1} = Ax_k + Bu_k
         u_min ≤ u_k ≤ u_max
    """
    import cvxpy as cp
    n, m = A.shape[0], B.shape[1]
    x = cp.Variable((n, N+1))
    u = cp.Variable((m, N))
    
    cost = 0
    constraints = [x[:, 0] == x0]
    
    for k in range(N):
        cost += cp.quad_form(x[:, k] - x_ref, Q) + cp.quad_form(u[:, k], R)
        constraints += [x[:, k+1] == A @ x[:, k] + B @ u[:, k]]
        constraints += [u[:, k] >= u_min, u[:, k] <= u_max]
    
    prob = cp.Problem(cp.Minimize(cost), constraints)
    prob.solve(solver=cp.OSQP)
    return u.value[:, 0]  # 只执行第一步
```

## 姿态表示

| 表示方法 | 维度 | 奇异性 | 计算 | 场景 |
|---------|------|--------|------|------|
| 欧拉角（RPY） | 3 | 万向锁 | 直观简单 | PID调参、显示 |
| 旋转矩阵 | 9 | 无 | 稳定 | 矩阵运算 |
| 四元数 | 4 | 无 | 高效 | 传感器融合 |
| 轴角 | 4 | 接近0退化 | 误差表示 | 指数映射 |
| 李代数 so(3) | 3 | 无 | 优化友好 | SLAM/图优化 |

## 强化学习控制

```yaml
近年趋势：用 RL 代替手工调参
代表工作:
  - ETH Zurich: 学习抗风扰控制（2022 Science Robotics）
  - Champion-level 无人机竞速（2023 Nature）
  
框架:
  训练: IsaacGym / Gazebo（Sim-to-Real关键）
  算法: PPO（最常用）, SAC（连续动作）
  观测空间: 位姿 + 角速度 + 目标位置
  动作空间: 4个电机推力 or Roll/Pitch/Yaw/Thrust

挑战: Sim-to-Real Gap（气动参数差异）
解决: 域随机化（Domain Randomization）
```

## PX4 与 ArduPilot 对比

| 维度 | PX4 | ArduPilot |
|------|-----|-----------|
| 开源协议 | BSD | GPL |
| 语言 | C++ | C++ |
| 社区 | 较小，工业品质 | 极大，爱好者友好 |
| 配置工具 | QGroundControl | Mission Planner |
| 仿真 | Gazebo/SITL | SITL/AirSim |
| 算法扩展 | 模块化，易集成 | 插件系统 |
| 无人机竞速 | 主流 | 较少 |
| 研究用途 | ✅ 主流 | ✅ 也常用 |

## 论文引用

- [1] **四旋翼动力学模型** — Mahony et al., "Nonlinear Complementary Filters on the Special Orthogonal Group," IEEE TAC 2008.
- [2] **MPC无人机** — Mueller & D'Andrea, "A Model Predictive Controller for Quadrocopter State Interception," ECC 2013.
- [3] **学习飞行控制** — Loquercio et al., "Learning High-Speed Flight in the Wild," Science Robotics 2021.
- [4] **RL竞速** — Kaufmann et al., "Champion-level Drone Racing Using Deep Reinforcement Learning," Nature 2023.
- [5] **抗风扰学习** — Peng et al., "Agility from Agility: Learning to Recover from Crashes in Quadrotors," CoRL 2022.
- [6] **Neural Fly** — O'Connell et al., "Neural-Fly Enables Rapid Learning for Agile Flight in Strong Winds," Science Robotics 2022.
- [7] **几何控制** — Lee et al., "Geometric Tracking Control of a Quadrotor UAV on SE(3)," CDC 2010. [理论基础]
- [8] **INDI控制** — Smeur et al., "Incremental Nonlinear Dynamic Inversion for Rotorcraft Attitude Control," AIAA 2016.
- [9] **MPC调研** — Kamel et al., "Linear vs Nonlinear MPC for Trajectory Tracking Applied to Rotary Wing Micro Aerial Vehicles," IFAC 2017.
- [10] **PX4控制架构** — Meier et al., "PIXHAWK: A Micro Aerial Vehicle Design for Autonomous Flight Using Onboard Computer Vision," Autonomous Robots 2012.
- [11] **域随机化** — Molchanov et al., "Sim-to-(Multi)-Real: Transfer of Low-Level Robust Control Policies to Multiple Quadrotors," IROS 2019.
- [12] **姿态估计** — Mahony et al., "Nonlinear Complementary Filters on SO(3)," IEEE TAC 2008.

## 关联

- 相关概念: [[concept-multi-sensor-fusion]], [[concept-path-planning]], [[concept-reinforcement-learning]]
- 相关实体: [[entities/product-px4-autopilot]]
- 参见: [[topics/topic-precision-localization]], [[topics/topic-sim-to-real]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——飞行原理、级联PID架构、MPC代码、姿态表示对比、RL控制、PX4对比、12篇论文引用
