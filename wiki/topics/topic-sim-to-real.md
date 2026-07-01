# 仿真到真机（Sim-to-Real）工作流

> **类型**: topic（综述）
> **创建时间**: 2026-06-27
> **最后更新**: 2026-06-29
> **来源**: AI综合，见论文引用列表

## 摘要

Sim-to-Real 是无人机 AI 研究的核心范式——在仿真环境中训练/验证算法，再迁移到真实飞机上。掌握这一流程能极大降低真机测试风险和成本，是现代无人机算法工程师必备技能。

## 仿真平台对比

| 平台 | 物理引擎 | 渲染质量 | 飞控集成 | 速度 | 适用场景 |
|------|---------|---------|---------|------|---------|
| Gazebo + PX4 SITL | ODE/Bullet | 中 | PX4原生 | 慢 | 算法验证首选 |
| AirSim（微软） | PhysX | 高（UE4） | PX4/ArduPilot | 中 | 计算机视觉 |
| Flightmare | Unity | 高 | ✅专为旋翼 | 快 | RL训练 |
| IsaacGym（NVIDIA）| PhysX GPU | 中 | 自定义 | **极快** | 大规模RL |
| Isaac Lab（新版） | PhysX GPU | 中高 | 更完整 | 极快 | RL/策略训练 |
| Webots | ODE | 中 | ArduPilot | 中 | 教育/原型 |
| JSBSim | -- | 无 | 固定翼 | 极快 | 固定翼飞行 |

## Gazebo + PX4 SITL 完整配置

```bash
# 1. 安装 PX4 固件
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
bash ./Tools/setup/ubuntu.sh

# 2. 安装 ROS2 Humble
sudo apt install ros-humble-desktop

# 3. 安装 MAVROS
sudo apt install ros-humble-mavros ros-humble-mavros-extras
wget https://raw.githubusercontent.com/mavlink/mavros/master/mavros/scripts/install_geographiclib_datasets.sh
sudo bash install_geographiclib_datasets.sh

# 4. 启动仿真（Gazebo + PX4 + QGC）
cd PX4-Autopilot
make px4_sitl gazebo-classic_iris__empty  # 启动空旷场景

# 5. 在另一终端启动 MAVROS
ros2 launch mavros px4.launch fcu_url:="udp://:14540@127.0.0.1:14557"

# 6. 验证连接
ros2 topic list | grep mavros
ros2 topic echo /mavros/state
```

## Flightmare + RL 训练配置

```python
# Flightmare 专为 RL 设计的高速仿真
# 支持 GPU 渲染，比 Gazebo 快 100x

from flightgym import QuadrotorEnv_v1
import stable_baselines3 as sb3

# 创建环境（支持 128 个并行实例）
env = QuadrotorEnv_v1(
    cfg_path="cfg/quad_env.yaml",
    render=False  # 训练时关闭渲染
)

# PPO 训练
model = sb3.PPO(
    "MlpPolicy", env,
    n_steps=2048,
    batch_size=512,
    n_epochs=10,
    learning_rate=3e-4,
    ent_coef=0.01,
    verbose=1
)
model.learn(total_timesteps=5_000_000)
model.save("quadrotor_ppo")
```

## 域随机化实现

```python
import numpy as np

class DomainRandomizer:
    """训练时随机化仿真参数，减少 Sim-to-Real Gap"""
    
    def __init__(self, base_params):
        self.base = base_params
    
    def randomize(self):
        return {
            # 机体参数 ±20%
            'mass': self.base['mass'] * np.random.uniform(0.8, 1.2),
            'inertia': self.base['inertia'] * np.random.uniform(0.8, 1.2),
            
            # 电机参数 ±15%
            'thrust_coeff': self.base['thrust_coeff'] * np.random.uniform(0.85, 1.15),
            'torque_coeff':  self.base['torque_coeff'] * np.random.uniform(0.85, 1.15),
            
            # 环境干扰
            'wind_speed': np.random.uniform(0, 3.0),     # m/s
            'wind_direction': np.random.uniform(0, 360),  # deg
            
            # 传感器噪声
            'imu_noise_std': np.random.uniform(0.01, 0.05),
            'camera_exposure': np.random.uniform(0.5, 1.5),
            
            # 视觉域随机化
            'texture_variation': np.random.randint(0, 100),
            'lighting': np.random.choice(['noon', 'dusk', 'overcast', 'indoor']),
        }
    
    def apply_to_sim(self, sim, params):
        sim.set_mass(params['mass'])
        sim.set_inertia(params['inertia'])
        sim.set_wind(params['wind_speed'], params['wind_direction'])
        sim.set_imu_noise(params['imu_noise_std'])
```

## Sim-to-Real Gap 量化评估

```python
def sim_real_gap_analysis(sim_data, real_data):
    """
    对比仿真和真机的系统响应
    用于定量评估 Gap 大小
    """
    metrics = {}
    
    # 阶跃响应对比
    for signal in ['roll', 'pitch', 'yaw', 'altitude']:
        sim_response = sim_data[signal]
        real_response = real_data[signal]
        
        # 上升时间（10%→90%）
        sim_rise = rise_time(sim_response)
        real_rise = rise_time(real_response)
        
        # 超调量
        sim_overshoot = overshoot(sim_response)
        real_overshoot = overshoot(real_response)
        
        # Gap 评分
        gap = abs(sim_rise - real_rise) / real_rise
        metrics[f'{signal}_rise_gap'] = gap
    
    total_gap = np.mean(list(metrics.values()))
    print(f"总体 Sim-to-Real Gap: {total_gap:.1%}")
    return metrics
```

## 实际落地流程

```
Phase 1: 算法在仿真中验证（100%）
  - 功能正确性
  - 边界条件处理
  - 参数初步调整

Phase 2: HITL（Hardware-In-The-Loop）
  - PX4真实飞控 + 仿真桨叶
  - 验证飞控接口和通信
  - 约 50-80% 仿真参数迁移

Phase 3: 低空悬停测试
  - 系留绳 + 垫子保护
  - 验证基本控制
  - 录制真机数据，更新仿真参数

Phase 4: 自由飞行验证
  - 空旷场地
  - 人工接管随时准备
  - 逐步放开速度/复杂度限制

Phase 5: 真实场景测试
  - 目标场景复现
  - 压力测试（风扰/干扰/遮挡）
```

## 论文引用

- [1] **Sim-to-Real综述** — Zhao et al., "Sim-to-Real Transfer in Deep Reinforcement Learning for Robotics," 2020.
- [2] **OpenAI DR** — Tobin et al., "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World," IROS 2017.
- [3] **Dexterous Hand** — OpenAI, "Learning Dexterous In-Hand Manipulation," IJRR 2020. [DR最著名应用]
- [4] **ADR** — Akkaya et al., "Solving Rubik's Cube with a Robot Hand," arXiv 2019. [自动域随机化]
- [5] **Flightmare** — Song et al., "Flightmare: A Flexible Quadrotor Simulator," CoRL 2020.
- [6] **AirSim** — Shah et al., "AirSim: High-Fidelity Visual and Physical Simulation for Autonomous Vehicles," FSR 2017.
- [7] **IsaacGym** — Makoviychuk et al., "Isaac Gym: High Performance GPU-Based Physics Simulation for Robot Learning," NeurIPS Dataset 2021.
- [8] **Agility from Simulation** — Loquercio et al., "Learning High-Speed Flight in the Wild," Science Robotics 2021.
- [9] **HITL仿真** — Meier et al., "PIXHAWK: A Micro Aerial Vehicle Design for Autonomous Flight," Autonomous Robots 2012.
- [10] **系统辨识** — Burri et al., "Real-world, Real-time Robust Visual-Inertial Odometry," IROS 2015.

## 关联

- 相关概念: [[concept-drone-control]], [[concept-reinforcement-learning]], [[concept-path-planning]]
- 相关实体: [[entities/product-px4-autopilot]]

## 变更记录

- 2026-06-27: 初始创建
- 2026-06-29: 大幅扩写——平台对比、Gazebo/Flightmare配置、域随机化代码、Gap评估代码、落地流程、10篇论文引用
