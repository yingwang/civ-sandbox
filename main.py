import sys
import time
from engine import SimulationEngine


def print_banner():
    print("=" * 60)
    print("       📜 大模型自主推演·蛮荒文明演化沙盒 (Civ-Sandbox) 📜       ")
    print("=" * 60)


def print_tribe_status(engine: SimulationEngine):
    print("\n【当前各部族概况】")
    print(f"{'部族':<10}{'首领':<12}{'人口':<8}{'粮草':<8}{'矿石':<8}{'科技发明'}")
    print("-" * 60)
    for t in engine.tribes:
        if t.is_alive:
            tech_str = "、".join(t.techs) if t.techs else "暂无"
            print(f"{t.name:<10}{t.leader_title + ' ' + t.leader_name:<12}{t.population:<8}{t.food:<8}{t.ore:<8}{tech_str}")
        else:
            print(f"{t.name:<10}{'（已覆灭）':<12}{'0':<8}{'0':<8}{'0':<8}{'宗庙倾覆'}")
    print("-" * 60)


def main():
    print_banner()
    engine = SimulationEngine()
    regions, tribes = engine.genesis()

    print("\n【混沌初开·山河创生】")
    for r in regions:
        print(f"· 地域【{r.name}】（{r.terrain.value}）- 沃度: {r.fertility}/10, 矿藏: {r.mineral_richness}/10")

    print("\n【三方始祖部落定居】")
    for t in tribes:
        print(f"· 【{t.name}】奉【{t.totem}】为图腾，首领【{t.leader_name}】，性格：{t.ethos}")

    epochs_to_run = 5
    if len(sys.argv) > 1:
        try:
            epochs_to_run = int(sys.argv[1])
        except ValueError:
            pass

    print(f"\n即将自主演化推演 {epochs_to_run} 个纪元……\n")

    for _ in range(epochs_to_run):
        record = engine.step()
        print("*" * 60)
        print(f"       >>> 纪元推演：第 {record.epoch_num} 载 <<<       ")
        print("*" * 60)
        
        print("\n【各族领袖决断诏令】")
        for d in record.actions:
            print(f"· {d.edict}")
            print(f"  └─ 密谋内由：{d.rationale}")

        print("\n【天道仲裁与变故】")
        for res in record.resolutions:
            print(f"· {res}")

        print_tribe_status(engine)
        print("\n" + record.chronicle_text + "\n")
        time.sleep(0.5)

    print("=" * 60)
    print("推演完成。诸族兴衰已录入青史。")
    print("=" * 60)


if __name__ == "__main__":
    main()
