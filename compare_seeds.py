"""Run several deterministic histories and summarize whether their paths diverge."""

import argparse
from collections import Counter

from engine import SimulationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="比较多个 seed 的人工历史路径")
    parser.add_argument("--seeds", default="0,1,2,3,4,5,6,7")
    parser.add_argument("--epochs", type=int, default=24)
    parser.add_argument(
        "--scenario",
        choices=("warring-states", "open-origin"),
        default="warring-states",
    )
    args = parser.parse_args()
    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]

    signatures = set()
    knowledge_sets = []
    fixed_history_terms = ("农业时代", "青铜时代", "铁器时代", "工业时代", "信息时代")
    historical_matches = []

    for seed in seeds:
        engine = SimulationEngine(
            seed=seed, planner_mode="heuristic", scenario=args.scenario
        )
        engine.run(args.epochs)
        signatures.add(engine.path_signature())
        knowledge = {
            node.name
            for node in engine.knowledge_graph.nodes.values()
            if node.discovered_epoch > 0
        }
        knowledge_sets.append(knowledge)
        structures = [item.name for item in engine.world.structures.values()]
        organizations = [
            item.name
            for society in engine.societies.values()
            for item in society.organizations.values()
        ]
        locations = Counter(
            engine.locations[society.location_id].name
            for society in engine.societies.values()
            if society.is_alive
        )
        extinct = [society.name for society in engine.societies.values() if not society.is_alive]
        event_count = sum(len(record.events) for record in engine.history)
        side_effect_count = sum(
            len(resolution.side_effects)
            for record in engine.history
            for resolution in record.resolutions
        )
        for name in knowledge:
            if any(term in name for term in fixed_history_terms):
                historical_matches.append((seed, name))
        print(f"\nseed {seed}：")
        print(f"  新知识：{'；'.join(sorted(knowledge)) or '无成功知识节点'}")
        print(f"  结构：{'；'.join(structures) or '无'}")
        print(f"  组织：{'；'.join(organizations) or '无'}")
        print(f"  存续分布：{dict(locations)}；灭绝：{'、'.join(extinct) or '无'}")
        print(f"  开放事件 {event_count} 个；已触发副作用 {side_effect_count} 个")

    common_knowledge = set.intersection(*knowledge_sets) if knowledge_sets else set()
    print("\n【分叉检查】")
    print(f"共运行 {len(seeds)} 个 seed，得到 {len(signatures)} 个不同终态签名。")
    print(f"所有 seed 共同产生的新知识：{'；'.join(sorted(common_knowledge)) or '无'}。")
    print(f"固定现实时代词命中：{historical_matches or '无'}。")
    if len(signatures) == len(seeds) and not common_knowledge and not historical_matches:
        print("检查通过：当前样本没有收敛到共同科技序列，也没有复刻固定现实时代路径。")
    else:
        print("检查需关注：部分 seed 出现相同终态、共同知识序列或现实时代词。")


if __name__ == "__main__":
    main()
