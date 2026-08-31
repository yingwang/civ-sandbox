import random
from typing import List, Dict, Tuple, Optional
from models import Region, TerrainType, Tribe, ActionType, TribeDecision, EpochRecord
from llm_backend import LLMBackend


class SimulationEngine:
    TECH_POOL = [
        "冶铜熔铸", "水车引渠", "观星历法", "重甲步战", "夯土筑城",
        "井田之法", "草药医理", "陶范铸造", "造船泛舟", "成文法典"
    ]
    
    DISASTERS = [
        "大旱三月，赤地千里",
        "连绵淫雨，江水决堤泛滥",
        "天降流火陨星，坠于荒原",
        "极寒霜冻，百草冻毙",
        "四野蝗灾，禾稼皆尽",
        "春和景明，山川郁秀（祥瑞）"
    ]

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.backend = LLMBackend()
        self.epoch = 0
        self.regions: List[Region] = []
        self.tribes: List[Tribe] = []
        self.history: List[EpochRecord] = []

    def genesis(self) -> Tuple[List[Region], List[Tribe]]:
        """创世：随机生成地理格局与初始部族"""
        terrains = [
            (TerrainType.PLAINS, "中原沃野", 8, 4),
            (TerrainType.RIVERLAND, "九江大泽", 7, 3),
            (TerrainType.HIGHLAND, "昆仑荒原", 3, 9),
            (TerrainType.FOREST, "云梦林莽", 6, 6),
            (TerrainType.COASTAL, "东溟之滨", 5, 5),
            (TerrainType.DESERT, "西荒流沙", 2, 7),
        ]
        
        self.regions = []
        for i, (t_type, r_name, fert, ore) in enumerate(terrains):
            r = Region(
                id=f"reg_{i+1}",
                name=r_name,
                terrain=t_type,
                fertility=fert,
                mineral_richness=ore
            )
            self.regions.append(r)

        tribe_archetypes = [
            ("炎黎氏", "大祭司", "黎炎", "赤焰火鸟", "崇火勇猛，以战养战", self.regions[0]),
            ("渚泽氏", "族长", "云汐", "玄龟双鲤", "依水织网，善通商贾", self.regions[1]),
            ("磐石氏", "首领", "重石", "苍角青兕", "耐苦耐劳，工于采石筑城", self.regions[2]),
        ]

        self.tribes = []
        for i, (name, title, leader, totem, ethos, region) in enumerate(tribe_archetypes):
            region.controlled_by = f"tribe_{i+1}"
            tribe = Tribe(
                id=f"tribe_{i+1}",
                name=name,
                leader_title=title,
                leader_name=leader,
                totem=totem,
                ethos=ethos,
                population=100 + random.randint(-10, 20),
                food=300,
                ore=100,
                wealth=100,
                techs=[],
                home_region_id=region.id
            )
            self.tribes.append(tribe)

        return self.regions, self.tribes

    def step(self) -> EpochRecord:
        """推演一纪"""
        self.epoch += 1
        resolutions: List[str] = []

        # 1. 天象与自然演变
        disaster = random.choice(self.DISASTERS) if random.random() < 0.6 else None
        if disaster and "祥瑞" not in disaster:
            for t in self.tribes:
                if t.is_alive:
                    loss = int(t.food * 0.15)
                    t.food = max(0, t.food - loss)
            resolutions.append(f"【天变】{disaster}，各部族存粮皆受损耗。")
        elif disaster:
            resolutions.append(f"【天象】{disaster}，万物竞发生长。")

        # 2. 各部落生成决策
        decisions: List[TribeDecision] = []
        for tribe in self.tribes:
            if not tribe.is_alive:
                continue
            decision = self.backend.generate_tribe_decision(
                tribe, self.regions, self.tribes, self.epoch, [r for h in self.history[-3:] for r in h.resolutions]
            )
            decisions.append(decision)

        # 3. 仲裁各族决策
        tribe_map = {t.id: t for t in self.tribes}
        for d in decisions:
            actor = tribe_map[d.tribe_id]
            if not actor.is_alive:
                continue

            if d.action_type == ActionType.CULTIVATE:
                gain = actor.population * 3 + random.randint(50, 150)
                actor.food += gain
                resolutions.append(f"【农桑】{actor.name}深耕厚积，本纪获粮 {gain} 石。")

            elif d.action_type == ActionType.INVENT:
                available_techs = [tech for tech in self.TECH_POOL if tech not in actor.techs]
                if available_techs:
                    new_tech = random.choice(available_techs)
                    actor.techs.append(new_tech)
                    actor.ore = max(0, actor.ore - 30)
                    resolutions.append(f"【百工】{actor.name}巧匠夜以继日，首创【{new_tech}】之法！")
                else:
                    actor.wealth += 50
                    resolutions.append(f"【百工】{actor.name}技艺圆熟，族人治器大备，富庶日增。")

            elif d.action_type == ActionType.TRADE and d.target_tribe_id:
                target = tribe_map.get(d.target_tribe_id)
                if target and target.is_alive:
                    actor.wealth += 40
                    target.wealth += 40
                    actor.food += 30
                    target.food += 30
                    resolutions.append(f"【通商】{actor.name}遣使赴 {target.name} 互市，两族欢悦，民享其利。")

            elif d.action_type == ActionType.RAID and d.target_tribe_id:
                target = tribe_map.get(d.target_tribe_id)
                if target and target.is_alive:
                    # 战争判定：人口 + 科技加成
                    actor_power = actor.population + len(actor.techs) * 20 + random.randint(0, 30)
                    target_power = target.population + len(target.techs) * 20 + random.randint(0, 30)
                    
                    if actor_power > target_power:
                        loot = min(target.food, 100)
                        target.food -= loot
                        actor.food += loot
                        casualty_actor = random.randint(5, 12)
                        casualty_target = random.randint(15, 30)
                        actor.population = max(10, actor.population - casualty_actor)
                        target.population = max(0, target.population - casualty_target)
                        
                        resolutions.append(
                            f"【征伐】{actor.name}起兵突袭 {target.name}，斩获粮秣 {loot} 石！{target.name}大溃，伤亡 {casualty_target} 人。"
                        )
                        if target.population <= 15:
                            target.is_alive = False
                            resolutions.append(f"【覆灭】{target.name}社稷倾覆，族民流散，部族自此绝嗣。")
                    else:
                        casualty_actor = random.randint(15, 25)
                        actor.population = max(10, actor.population - casualty_actor)
                        resolutions.append(
                            f"【战败】{actor.name}出兵攻 {target.name} 不克，折损勇士 {casualty_actor} 人，仓皇引退。"
                        )

            elif d.action_type == ActionType.WORSHIP:
                actor.food = max(0, actor.food - 30)
                actor.wealth += 20
                if random.random() < 0.4:
                    actor.population += random.randint(10, 20)
                    resolutions.append(f"【祭天】{actor.name}筑坛祭【{actor.totem}】，远近流民慕其盛德，纷纷归附！")
                else:
                    resolutions.append(f"【祭天】{actor.name}焚香献牲，族人感召神谕，人心大定。")

            elif d.action_type == ActionType.EXPAND:
                actor.population += random.randint(15, 25)
                actor.ore += 20
                resolutions.append(f"【拓土】{actor.name}开辟新野，分立新邑，添丁增邑。")

        # 4. 人口与粮食日常消耗结算
        for t in self.tribes:
            if t.is_alive:
                consumption = t.population * 2
                if t.food >= consumption:
                    t.food -= consumption
                    growth = max(1, int(t.population * 0.08))
                    t.population += growth
                else:
                    famine_death = min(t.population - 10, int((consumption - t.food) / 2))
                    t.population = max(10, t.population - famine_death)
                    t.food = 0
                    resolutions.append(f"【饥馑】{t.name}仓廪见底，发生小饥，折损人口 {famine_death} 人。")

        # 5. 生成史官编年实录
        chronicle_text = self.backend.generate_chronicle(
            self.epoch, disaster, decisions, resolutions, self.tribes
        )

        record = EpochRecord(
            epoch_num=self.epoch,
            disaster_event=disaster,
            actions=decisions,
            resolutions=resolutions,
            chronicle_text=chronicle_text
        )
        self.history.append(record)
        return record
