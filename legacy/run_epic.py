import sys
from epic_engine import EpicSimulationEngine


def main():
    engine = EpicSimulationEngine(seed=42)
    engine.genesis()
    
    total_epochs = 12
    records = []
    
    for _ in range(total_epochs):
        data = engine.run_epoch()
        records.append(data)
        
    print(f"=== 《上古洪荒百载演化实录》【总计 {total_epochs} 纪】===\n")
    for r in records:
        print(f"【洪荒纪 第 {r['epoch']} 载】")
        for ev in r['events']:
            print(f"  · {ev}")
        print("  【各邦存续】: " + " | ".join([
            f"{name}({pop}人, 技艺:{len(techs)}门)" if alive else f"{name}(国灭)"
            for name, pop, food, ore, techs, alive in r['tribes']
        ]))
        print("")

if __name__ == "__main__":
    main()
