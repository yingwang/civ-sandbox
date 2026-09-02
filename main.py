"""Chinese CLI for the open-ended artificial-history simulator.

Defaults to the ledger mode with open-ended knowledge proposals and deterministic
settlement, with options for open-world narrative, real-history narrative and the
classic primitive-based simulation.
"""

import argparse
from pathlib import Path
import sys

from engine import SimulationEngine
from open_law_engine import OpenLawHistoryEngine
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


def run_open_world_mode(epochs: int, seed: int, output_path: Path) -> None:
    print("=" * 75)
    print("【Civ-Sandbox 开放式文明模拟器 · 开放世界客观规律分叉模式 (Default)】")
    print("法则核心：绝不照抄既定历史剧本，严格服从地理运力、马尔萨斯承载力、宏观经济与科技阶梯")
    print("演变空间：七雄争霸、海上商业帝国、南方水运联邦、游牧铁骑、早期工业萌芽与现代文明")
    print(f"推演纪数：{epochs} 纪 (公元前230年 至 公元2026年)，随机种子：{seed}")
    print("=" * 75)

    engine = OpenLawHistoryEngine(seed=seed)
    engine.run(epochs=epochs, output_path=output_path, live_print=True)


def run_real_history_mode(epochs: int, seed: int, output_path: Path) -> None:
    print("=" * 75)
    print("【Civ-Sandbox 开放式文明模拟器 · 真实历史编年全景模式】")
    print("模式特色：大模型沿真实朝代更替与关键科技节点，生成两千年全景通史")
    print(f"推演纪数：{epochs} 纪 (公元前230年 至 公元2026年)，随机种子：{seed}")
    print("=" * 75)

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
        help="推演纪数 (账本模式默认跑全部 23 纪，覆盖前230至2026年)",
    )
    parser.add_argument(
        "--mode",
        choices=("ledger", "open-world", "real-history", "classic"),
        default="ledger",
        help="推演模式：默认 ledger (开放知识提案 + 规则与随机数结算)，open-world (单次调用的开放提示词模式)，real-history (真实历史全景)，classic (离线规则沙盘)",
    )
    parser.add_argument("--seed", type=int, default=42, help="确定性随机种子")
    parser.add_argument("--no-llm", action="store_true", help="账本模式下不调用模型，只用离线启发式提案与模板纪事（用于测试与校准）")
    parser.add_argument("--resume", action="store_true", help="账本模式下从输出文件旁的 .checkpoint.json 续跑（模型额度用尽中断后使用）")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出通史文档路径 (默认自动分配)",
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

    if args.planner == "heuristic" and "--mode" not in sys.argv:
        args.mode = "classic"

    if args.mode == "ledger":
        from open_ledger_engine import OpenKnowledgeLedgerEngine
        out_path = args.output or Path(".artifacts/china-ledger-history-2026.md")
        print("=" * 75)
        print("【Civ-Sandbox · 开放知识账本模式】研究由模型从问题、假说、实验与机制自由提出；规则与骰子只结算可行性、宏观后果、战争与政权存亡。")
        print(f"推演纪数：{args.epochs or '全部'}，随机种子：{args.seed}，速率见 ledger_config.json")
        print("=" * 75)
        engine = OpenKnowledgeLedgerEngine(seed=args.seed, llm_enabled=not args.no_llm)
        engine.run(epochs=args.epochs, output_path=out_path, resume=args.resume)
        if getattr(engine, "paused", False):
            sys.exit(2)
        return
    if args.mode == "open-world":
        epochs = args.epochs if args.epochs is not None else 16
        out_path = args.output or Path(".artifacts/china-open-world-history-2026.md")
        run_open_world_mode(epochs=epochs, seed=args.seed, output_path=out_path)
    elif args.mode == "real-history":
        epochs = args.epochs if args.epochs is not None else 23
        out_path = args.output or Path(".artifacts/china-unbounded-history-2026.md")
        run_real_history_mode(epochs=epochs, seed=args.seed, output_path=out_path)
    else:
        args.epochs = args.epochs if args.epochs is not None else 8
        run_classic_mode(args)


if __name__ == "__main__":
    main()
