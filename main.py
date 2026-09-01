from __future__ import annotations

import argparse

from engine import WorldEngine


def print_status(engine: WorldEngine) -> None:
    print("\n【当前文明概况】")
    print(f"{'文明':<10}{'人口':<8}{'粮食':<8}{'矿石':<8}{'财富':<8}科技")
    print("-" * 72)
    for c in engine.civilizations:
        techs = "、".join(c.techs) if c.techs else "暂无"
        life = "" if c.is_alive else "（覆亡）"
        print(f"{c.name + life:<10}{c.population:<8}{c.food:<8}{c.ore:<8}{c.wealth:<8}{techs}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Civ-Sandbox: agent intentions + deterministic world simulation")
    parser.add_argument("epochs", nargs="?", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42, help="replay seed")
    parser.add_argument("--llm", choices=["off", "auto", "claude", "agy", "codex"], default="off")
    args = parser.parse_args()

    engine = WorldEngine(seed=args.seed, llm_mode=args.llm)
    regions, civs = engine.genesis()

    print("=" * 72)
    print("Civ-Sandbox · LLM intentions, deterministic consequences")
    print(f"seed={args.seed} | llm={args.llm} | model_cli={engine.backend.cli_tool or 'heuristic'}")
    print("=" * 72)
    print("\n【世界创生】")
    for r in regions:
        print(f"· {r.name}: {r.terrain.value}, fertility={r.fertility}, minerals={r.mineral_richness}")
    print("\n【文明】")
    for c in civs:
        print(f"· {c.name} / {c.leader_name}: {c.ethos}; goals={c.goals}")

    for _ in range(args.epochs):
        record = engine.step()
        print(f"\n{'*' * 28} 第 {record.epoch_num} 纪 {'*' * 28}")
        print("【Agent Intentions】")
        for intent in record.actions:
            target = f" -> {intent.target_civilization_id}" if intent.target_civilization_id else ""
            print(f"· {intent.civilization_id}: {intent.action_type.name}{target} | {intent.rationale}")
        print("【World Resolution】")
        for line in record.resolutions:
            print(f"· {line}")
        print_status(engine)
        print("\n" + record.chronicle_text)


if __name__ == "__main__":
    main()
