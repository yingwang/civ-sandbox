"""Chinese CLI for the open-ended artificial-history simulator.

Defaults to the Unbounded LLM Mode (彻底释放大模型可能性，无硬编码枚举约束),
with optional classic primitive-based simulation.
"""

import argparse
from pathlib import Path
import sys

from engine import SimulationEngine
from unbounded_llm_history import UnboundedLLMHistoryEngine


def print_classic_state(engine: SimulationEngine) -> None:
    print("\n【纪末状态】")
    for society in engine.societies.values():
        status = "存续" if society.is_alive else "灭绝"
        print(
            f"{society.name}：{status}，人口规模 {society.population}，"
            f"地点 {engine.locations[society.location_id].name}，"
            f"知识 {len(society.knowledge)}，组织 {len(society.organizations)}"
        )
    if engine.knowledge_graph.nodes:
        print("动态知识图谱：")
        for node in engine.knowledge_graph.nodes.values():
            dependencies = (
                "、".join(
                    engine.knowledge_graph.nodes[item].name
                    for item in node.prerequisites
                    if item in engine.knowledge_graph.nodes
                )
                if node.prerequisites
                else "无前置节点"
            )
            risks = "、".join(item.name for item in node.risks) if node.risks else "尚无已知风险"
            print(f"  {node.name}，依赖：{dependencies}，风险：{risks}")


def run_unbounded_mode(epochs: int, seed: int, output_path: Path) -> None:
    print("=" * 70)
    print("【Civ-Sandbox 开放式文明模拟器 · 无约束大模型模式 (Default)】")
    print("模式特色：彻底解除写死枚举动作与规则约束，完全由 LLM 驱动历史宏大演变")
    print("涵盖维度：兼并决战、朝代更替、政制鼎革、科技范式跃迁（从冶铁到蒸汽算力与AI）与思想流变")
    print(f"推演纪数：{epochs} 纪 (公元前230年 至 公元2026年)，随机种子：{seed}")
    print("=" * 70)

    engine = UnboundedLLMHistoryEngine(seed=seed)
    engine.run(epochs=epochs, output_path=output_path, live_print=True)


def run_classic_mode(args) -> None:
    engine = SimulationEngine(
        seed=args.seed, planner_mode=args.planner, scenario=args.scenario
    )
    locations, societies = engine.genesis()
    print(
        f"【开局】{engine.scenario.title}，seed={args.seed}，"
        f"生成 {len(locations)} 个地点与 {len(societies)} 个社会。"
    )
    print(engine.scenario.context)
    if engine.backend.cli_tool:
        model = f" / {engine.backend.cli_model}" if engine.backend.cli_model else ""
        print(
            f"本机 LLM（{engine.backend.cli_tool}{model}）分别扮演各社会 Agent、环境 Agent 与史家 Agent；"
            "WorldEngine 只裁定约束与后果。"
        )
    elif args.planner == "cli":
        print("未检测到可用的本机 LLM CLI，本次将逐项回退到确定性离线规划器。")
    else:
        print("本次显式使用确定性离线规划器。")

    for _ in range(args.epochs):
        if not any(item.is_alive for item in engine.societies.values()):
            break
        record = engine.step()
        print("\n" + record.chronicle_text)
        print_classic_state(engine)

    stats = engine.backend.stats
    print(
        "\n【生成说明】"
        f"社会 Agent 的 LLM 计划 {stats['llm_plan']} 项，离线回退计划 {stats['heuristic_plan']} 项；"
        f"环境 Agent 的 LLM 事件 {stats['llm_event']} 项，离线回退事件 {stats['heuristic_event']} 项；"
        f"史家 Agent 的 LLM 纪事 {stats['llm_chronicle']} 纪，模板回退纪事 {stats['fallback_chronicle']} 纪。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Civ-Sandbox：开放式人工历史与大模型文明演化模拟器"
    )
    parser.add_argument(
        "epochs",
        nargs="?",
        type=int,
        default=None,
        help="推演纪数 (无约束大模型模式默认全景 23 纪，覆盖前230至2026年)",
    )
    parser.add_argument(
        "--mode",
        choices=("unbounded", "classic"),
        default="unbounded",
        help="推演模式：默认 unbounded (真正释放大模型所有可能性的宏大演变)，classic 为离线规则/通用物理基元模式",
    )
    parser.add_argument("--seed", type=int, default=42, help="确定性随机种子")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".artifacts/china-unbounded-history-2026.md"),
        help="输出通史文档路径",
    )
    parser.add_argument(
        "--scenario",
        choices=("warring-states", "open-origin"),
        default="warring-states",
        help="经典模式下的开局场景 (warring-states / open-origin)",
    )
    parser.add_argument(
        "--planner",
        choices=("cli", "heuristic"),
        default="cli",
        help="经典模式下的规划器来源 (cli / heuristic)",
    )
    args = parser.parse_args()

    # If user explicitly specifies heuristic planner without specifying mode, default to classic mode
    if args.planner == "heuristic" and "--mode" not in sys.argv:
        args.mode = "classic"

    epochs = args.epochs if args.epochs is not None else (23 if args.mode == "unbounded" else 8)

    if args.mode == "unbounded":
        run_unbounded_mode(epochs=epochs, seed=args.seed, output_path=args.output)
    else:
        args.epochs = epochs
        run_classic_mode(args)


if __name__ == "__main__":
    main()
