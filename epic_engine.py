import random
from typing import List, Dict, Tuple, Optional
from models import Region, TerrainType, Tribe, ActionType, TribeDecision, EpochRecord


class EpicSimulationEngine:
    TECH_TREE = [
        ("冶铜铸兵", "兵刃锋锐，战力倍增"),
        ("水车引灌", "开渠引水，农桑大熟"),
        ("观星历法", "顺天应时，减免天灾"),
        ("重甲战车", "横扫原野，坚不可摧"),
        ("夯土城垣", "筑万仞高墙，固若金汤"),
        ("井田礼制", "定尊卑之序，民心安定"),
        ("造舟浮海", "泛舟江海，拓土远疆"),
        ("成文法典", "明刑弼教，奸邪绝迹"),
        ("青铜鼎彝", "铸九鼎以镇国运"),
        ("铁犁牛耕", "百工大备，天下富足")
    ]

    DISASTERS = [
        ("赤日炎炎，大旱三载", "赤地千里，草木焦枯，江河断流"),
        ("暴雨如注，江河滔天", "山洪暴发，泽国万里，田舍淹没"),
        ("荧惑守心，天降流火", "陨星坠于荒野，震动山川"),
        ("极寒霜冻，朔风凛冽", "大雪覆地三尺，人畜冻毙"),
        ("群蝗蔽日，食尽嘉禾", "四野无青草，饥殍遍野"),
        ("紫气东来，地涌甘泉", "风调雨顺，祥瑞纷呈")
    ]

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.epoch = 0
        self.regions: List[Region] = []
        self.tribes: List[Tribe] = []
        self.history: List[EpochRecord] = []
        self.wars_count = 0
        self.alliances: List[Tuple[str, str]] = []

    def genesis(self):
        terrains = [
            (TerrainType.PLAINS, "中原沃野", 9, 5),
            (TerrainType.RIVERLAND, "云梦九泽", 8, 4),
            (TerrainType.HIGHLAND, "昆仑西极", 4, 10),
            (TerrainType.FOREST, "苍梧密林", 6, 7),
            (TerrainType.COASTAL, "东溟归墟", 5, 6),
        ]
        self.regions = [
            Region(f"reg_{i+1}", name, t_type, f, o)
            for i, (t_type, name, f, o) in enumerate(terrains)
        ]

        archetypes = [
            ("炎黎部", "九黎苗裔", "赤羽天凤", "尚武悍勇，以战立威", "黎九霄", self.regions[0]),
            ("渚泽邦", "水德之民", "玄龟双蛟", "精于农商，柔韧善贾", "云梦舒", self.regions[1]),
            ("昆仑氏", "古之方士", "苍角白兕", "工于采石，筑城通神", "公输衡", self.regions[2]),
            ("东溟族", "海岱遗民", "吞海巨鲸", "泛海采珠，孤悬海外", "越沧溟", self.regions[4]),
        ]

        self.tribes = []
        for i, (name, lineage, totem, ethos, leader, region) in enumerate(archetypes):
            region.controlled_by = f"tribe_{i+1}"
            t = Tribe(
                id=f"tribe_{i+1}",
                name=name,
                leader_title="宗主" if i % 2 == 0 else "君长",
                leader_name=leader,
                totem=totem,
                ethos=ethos,
                population=120 + random.randint(0, 30),
                food=400,
                ore=150,
                wealth=150,
                home_region_id=region.id
            )
            self.tribes.append(t)

    def run_epoch(self) -> Dict:
        self.epoch += 1
        events = []
        
        # 1. 阶段：天象变迁
        dis_title, dis_desc = random.choice(self.DISASTERS)
        is_auspicious = "祥瑞" in dis_desc
        if not is_auspicious:
            for t in self.tribes:
                if t.is_alive:
                    # 科技减灾
                    reduction = 0.5 if "观星历法" in t.techs else 1.0
                    loss = int(t.food * 0.12 * reduction)
                    t.food = max(0, t.food - loss)
            events.append(f"【天兆】{dis_title}：{dis_desc}。各邦仓廪受损。")
        else:
            events.append(f"【天兆】{dis_title}：{dis_desc}。四海承平，万物繁育。")

        # 2. 阶段：各邦决策与行动
        alive_tribes = [t for t in self.tribes if t.is_alive]
        
        for t in alive_tribes:
            # 演化阶段晋升
            if t.population > 250 and not t.name.endswith("国"):
                old_name = t.name
                t.name = t.name.replace("部", "国").replace("邦", "国").replace("氏", "国").replace("族", "国")
                events.append(f"【晋封】{old_name}族众逾二百五十，建宗立庙，正式称【{t.name}】！")

            # 动机研判
            choices = ["FARM", "INVENT", "EXPAND", "WORSHIP"]
            other_alive = [o for o in alive_tribes if o.id != t.id]
            
            if "尚武" in t.ethos and other_alive and random.random() < 0.5:
                choices.append("RAID")
            if "农商" in t.ethos and other_alive:
                choices.extend(["TRADE", "TREATY"])
            if t.food < t.population * 2:
                choices = ["FARM", "FARM"]

            chosen_action = random.choice(choices)

            if chosen_action == "FARM":
                mult = 4 if "水车引灌" in t.techs or "铁犁牛耕" in t.techs else 3
                gain = t.population * mult + random.randint(60, 160)
                t.food += gain
                events.append(f"【农桑】{t.name}君臣勤勉开荒，本纪大稔，获嘉禾 {gain} 石。")

            elif chosen_action == "INVENT":
                unlearned = [(tech, desc) for tech, desc in self.TECH_TREE if tech not in t.techs]
                if unlearned:
                    tech_name, tech_desc = random.choice(unlearned)
                    t.techs.append(tech_name)
                    t.ore = max(0, t.ore - 40)
                    events.append(f"【格物】{t.name}能工巧匠参透天工，铸就【{tech_name}】（{tech_desc}）！")
                else:
                    t.wealth += 80
                    events.append(f"【大备】{t.name}诸法圆融，百工大备，四方求学者络绎不绝。")

            elif chosen_action == "TRADE" and other_alive:
                target = random.choice(other_alive)
                t.wealth += 50
                target.wealth += 50
                t.food += 40
                target.food += 40
                events.append(f"【互市】{t.name}与 {target.name} 开辟商道，舟车辐辏，两邦同享富庶。")

            elif chosen_action == "TREATY" and other_alive:
                target = random.choice(other_alive)
                events.append(f"【修好】{t.name}与 {target.name} 歃血为盟，登坛盟誓，结为兄弟之邦。")

            elif chosen_action == "WORSHIP":
                t.food = max(0, t.food - 40)
                t.wealth += 30
                if random.random() < 0.45:
                    new_pop = random.randint(20, 35)
                    t.population += new_pop
                    events.append(f"【神道】{t.name}祭祀图腾【{t.totem}】，降下神谕，荒野流民 {new_pop} 人扶老携幼来归！")
                else:
                    events.append(f"【祭天】{t.name}筑高台燔柴告天，宗族和睦，民风纯朴。")

            elif chosen_action == "EXPAND":
                t.population += random.randint(20, 35)
                t.ore += 30
                events.append(f"【拓境】{t.name}分兵拓荒，于险要处筑立别邑，疆域大阔。")

            elif chosen_action == "RAID" and other_alive:
                target = random.choice(other_alive)
                # 战争结算
                has_bronze = 30 if "冶铜铸兵" in t.techs else 0
                has_armor = 30 if "重甲战车" in t.techs else 0
                has_wall = 40 if "夯土城垣" in target.techs else 0

                att_score = t.population + has_bronze + has_armor + random.randint(0, 40)
                def_score = target.population + has_wall + random.randint(0, 40)

                if att_score > def_score:
                    loot_food = min(target.food, 150)
                    loot_ore = min(target.ore, 50)
                    target.food -= loot_food
                    target.ore -= loot_ore
                    t.food += loot_food
                    t.ore += loot_ore
                    cas_att = random.randint(8, 15)
                    cas_def = random.randint(25, 45)
                    t.population = max(10, t.population - cas_att)
                    target.population = max(0, target.population - cas_def)
                    events.append(f"【干戈】{t.name}举兵伐 {target.name}，破其关隘，斩获粮 {loot_food} 石、矿 {loot_ore} 钧！{target.name}折损 {cas_def} 人。")
                    if target.population <= 20:
                        target.is_alive = False
                        events.append(f"【国灭】{target.name}社稷覆灭，宗庙沦为丘墟，名号自此绝于青史！")
                else:
                    cas = random.randint(20, 35)
                    t.population = max(10, t.population - cas)
                    events.append(f"【折戟】{t.name}夜袭 {target.name} 城垣不克，死伤 {cas} 勇士，败退本疆。")

        # 3. 阶段：人口日常粮饷结算
        for t in alive_tribes:
            if not t.is_alive:
                continue
            consume = t.population * 2
            if t.food >= consume:
                t.food -= consume
                t.population += max(2, int(t.population * 0.07))
            else:
                starved = min(t.population - 10, int((consume - t.food) / 2))
                t.population = max(10, t.population - starved)
                t.food = 0
                events.append(f"【岁歉】{t.name}公粮断绝，人相食草根，饥毙 {starved} 人。")

        return {
            "epoch": self.epoch,
            "disaster": dis_title,
            "events": events,
            "tribes": [(t.name, t.population, t.food, t.ore, list(t.techs), t.is_alive) for t in self.tribes]
        }
