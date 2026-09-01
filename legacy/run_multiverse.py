from multiverse_engine import MultiverseSimEngine


def main():
    engine = MultiverseSimEngine(seed=101)
    engine.create_multiverse_starting_factions()
    
    print("=" * 65)
    print("    🌌 多维文明演化沙盒·多元分支与复杂系统推演 (Multiverse) 🌌    ")
    print("=" * 65)
    
    epochs = [
        "第一阶段：蛮荒奠基与信仰分野",
        "第二阶段：封建扩张与制度分流",
        "第三阶段：工业巨变与生态危机",
        "第四阶段：信息网络与算力觉醒",
        "第五阶段：终极跃迁与文明终局"
    ]
    
    for i, era_title in enumerate(epochs, 1):
        record = engine.simulate_epoch(i)
        print(f"\n【{era_title}】")
        for ev in record["events"]:
            print(f"  · {ev}")

    print("\n" + "=" * 65)
    print("【最终文明多维档案】")
    for civ in engine.civilizations:
        print(f"· 【{civ.name}】")
        print(f"  - 核心政体：{civ.regime}")
        print(f"  - 主流思潮：{civ.ideology}")
        print(f"  - 科技分野：{civ.tech_branch}")
        print(f"  - 经济形态：{civ.economy_model}")
        print(f"  - 生态健康：{civ.ecology_health}/100 | 飞升进度：{civ.ascension_progress}%")
    print("=" * 65)


if __name__ == "__main__":
    main()
