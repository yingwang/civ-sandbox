"""Chinese CLI for the open-ended artificial-history simulator."""

import argparse

from engine import SimulationEngine


def print_state(engine: SimulationEngine) -> None:
    print("\n【纪末状态】")
    for society in engine.societies.values():
        status = "存续" if society.is_alive else "灭绝"
        print(
            f"{society.name}：{status}，种群 {society.population}，"
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
        "--planner",
        choices=("heuristic", "cli"),
        default="heuristic",
        help="计划与事件提案来源；heuristic 可完全按 seed 重放",
    )
    args = parser.parse_args()

    engine = SimulationEngine(seed=args.seed, planner_mode=args.planner)
    locations, societies = engine.genesis()
    print(f"【创世】seed={args.seed}，生成 {len(locations)} 个地点与 {len(societies)} 个社会。")
    print("开局是智慧碳基生命场景，但资源、知识、制度和发展方向均未绑定现实历史。")

    for _ in range(args.epochs):
        if not any(item.is_alive for item in engine.societies.values()):
            break
        record = engine.step()
        print("\n" + record.chronicle_text)
        print_state(engine)


if __name__ == "__main__":
    main()
