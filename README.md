# Civ-Sandbox: 大模型自主演化文明沙盒

一个由多智能体与大模型驱动的随机开局微型文明演化推演引擎。

## 核心理念

- **随机创世（Random Genesis）**：自动生成地形、矿产与气候。
- **始祖部落（Autonomous Tribes）**：各部族具备独特的图腾信仰、领袖性格与生存诉求。
- **自主演化（Emergent Dynamics）**：每纪自主决策农桑、拓土、征伐、通商、祭天与百工研发。
- **天道与史官（Arbiter & Chronicler）**：模拟天灾人祸与冲突仲裁，以古雅史书体裁实时编撰《文明编年史》。

## 快速运行

```bash
python3 main.py 5
```

## 架构

```
civ-sandbox/
├── models.py         # 核心数据结构（地域、部落、决策、纪元记录）
├── engine.py         # 模拟演化内核（创世、天灾、决策仲裁、资源结算）
├── llm_backend.py    # 大模型接口与启发式推演驱动器
├── main.py           # CLI 终端推演入口
└── README.md
```
