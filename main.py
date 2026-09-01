"""Chinese CLI for the open-ended artificial-history simulator."""

import argparse

from engine import SimulationEngine


def print_state(engine: SimulationEngine) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="开放式人工历史模拟器")
    parser.add_argument("epochs", nargs="?", type=int, default=8, help="推演纪数")
    parser.add_argument("--seed", type=int, default=42, help="确定性随机种子")
    parser.add_argument(
        "--scenario",
        choices=("warring-states", "open-origin"),
        default="warring-states",
        help="开局场景；默认从公元前230年的战国七雄开始",
    )
    parser.add_argument(
        "--planner",
        choices=("heuristic", "cli"),
        default="cli",
        help="计划、事件与纪事来源；默认 cli，heuristic 可完全按 seed 重放",
    )
    args = parser.parse_args()

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
        print_state(engine)

    stats = engine.backend.stats
    print(
        "\n【生成说明】"
        f"社会 Agent 的 LLM 计划 {stats['llm_plan']} 项，离线回退计划 {stats['heuristic_plan']} 项；"
        f"环境 Agent 的 LLM 事件 {stats['llm_event']} 项，离线回退事件 {stats['heuristic_event']} 项；"
        f"史家 Agent 的 LLM 纪事 {stats['llm_chronicle']} 纪，模板回退纪事 {stats['fallback_chronicle']} 纪。"
    )


if __name__ == "__main__":
    main()
