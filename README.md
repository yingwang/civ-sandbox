# Civ-Sandbox：开放式人工历史模拟器

`civ-sandbox` 不再模拟一组预先命名的文明游戏动作，也不再沿固定时代和科技树推进。它运行一个更小但完整的闭环：自主 Agent 提出开放计划与开放事件，compiler 把提案约束为通用物理操作，`WorldEngine` 再根据当前世界状态决定能否执行、需要多久、产生什么结果，以及触发哪些副作用。

第一版场景从具协作学习能力的智慧碳基生命开始。底层没有 `Earth`、`human`、`wheat`、`iron` 等专用实体，也没有农业、青铜、铁器、工业、信息时代等顺序。

## 最小架构

```text
Agent / LLM
  │  任意中文目标、假说、制度与事件因果
  ▼
OpenPlan / OpenEvent
  │  语法检查、数值边界、守恒声明、稳定 ID
  ▼
PlanCompiler / EventCompiler
  │  通用 primitive 或因果状态增量
  ▼
WorldEngine
  │  资源、质量、空间、人口、能力依赖、工期、风险检查
  ▼
World state + 动态 knowledge graph + 中文编年记录
```

`OpenPlan` 没有动作类型枚举。计划可以叫“修建多孔缓流层叠体”“建立随机抽签的照料组织”或任何尚未出现过的名称，并可组合任意数量的步骤。`OpenEvent` 同样没有灾害或事件类型枚举，它只要求给出因果说明、持续时间、地点变化和模拟边界上的资源输入输出。

引擎内部仍有一组很小的 `PrimitiveKind`：`acquire`、`transform`、`construct`、`relocate`、`research`、`communicate`、`organize`。这些词不是历史行动菜单，而是类似物理指令集的通用操作。新的历史行动由它们的参数、对象和组合产生，不需要为“修坝”“信用制度”或“驯化某种生命”新增 enum。

## 因果与物理边界

`PlanCompiler` 从规模推导劳动量和工期，并拒绝非有限数值、过大效果和直接违反产出上限的转换。`WorldEngine` 才有权修改状态，它会再次检查实际库存、地点连通性、人口协作能力、材料质量、知识能力和前置知识。

事件可以改变任意已有环境属性，但资源变化必须满足全局质量收支。来自模型边界外的输入和流向边界外的输出必须显式记录。事件会按持续时间逐纪施加，不会瞬间改写最终状态。

研究成功后才会创建 `KnowledgeNode`。每个节点保存前置节点、观察证据、获得的能力和 failure modes，因此知识图谱由历史中的实际提案动态长出。知识风险会在相应能力被使用时重新参与结算，而不是只在“发明”一刻出现。

每种生命可以用 `metabolic_needs` 声明自己的通用资源 tag 与单位需求，因此底层不需要假定人类饮食。环境资源不会在后台凭空恢复，任何来自模拟边界外的补充都必须由带 `external_inputs` 的开放事件记账。项目可能失败，环境可能恶化，迁移可能受阻，组织也可能制造新的紧张。当人口足够多而凝聚度长期过低时，社会可能带着按人口比例分配的资源和继承知识分裂为新社会。引擎没有胜利条件，也不会保护任何社会免于停滞、分裂、崩溃或灭绝。

## 运行

使用确定性离线 planner：

```bash
python3 main.py 12 --seed 42
```

显式调用本机已登录的 LLM CLI：

```bash
python3 main.py 12 --seed 42 --planner cli
```

`heuristic` 模式的提案和世界结算共用本地 `random.Random(seed)`，相同 seed 会得到完全相同的状态与中文记录。`cli` 模式中的模型提案本身不保证确定性，但每一纪的 `EpochRecord` 都保留原始 `OpenPlan` 与 `OpenEvent`；把这些提案作为 replay 输入时，compiler 和 WorldEngine 的结算仍然是确定性的。第一版尚未提供把 replay tape 写入文件的 CLI。

## 第一版边界

当前物理层使用带单位质量的标量资源账本。它能检查取得、输运、转换和事件边界流的质量收支，但还没有元素组成、反应热力学、连续空间或流体方程。因此“符合物理规律”在这一版意味着提案不能超出已建模资源、空间、人口、工期、能力依赖和标量守恒约束，并不意味着它已经能证明任意新材料在真实化学上成立。

当前迁移 primitive 只支持社会整体迁移。社会分裂由低凝聚度的因果结算产生，而不是把部分迁移伪装成分裂。外部 LLM 提案会保留在内存中的 `EpochRecord`，但 replay tape 的文件导入导出仍是后续工作。

比较多个 seed：

```bash
python3 compare_seeds.py --seeds 0,1,2,3,4,5,6,7 --epochs 24
```

该命令列出各 seed 形成的知识、结构、组织、迁移终态、事件与副作用，并检查是否存在所有 seed 共有的知识序列或固定现实时代词。

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

## 文件

```text
models.py             开放计划、开放事件、世界状态与知识图谱
plan_compiler.py      开放计划到通用 primitives 的确定性编译
event_compiler.py     无类别事件的因果与数值检查
world_engine.py       唯一能修改世界状态的确定性执行器
llm_backend.py        LLM 接口与可重放的离线提案器
engine.py             创世、逐纪调度、中文编年记录与快照
compare_seeds.py      多 seed 分叉检查
tests/                守恒、因果、风险、重放与分叉测试
legacy/               重构前的固定时代与固定动作实验
```
