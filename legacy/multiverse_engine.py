import random
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class CivilizationProfile:
    name: str
    regime: str          # 政体形态：神权祭司制 / 封建分封 / 君主专制 / 自由商邦 / 科技托拉斯 / 机械共识网
    ideology: str        # 核心思想：图腾崇拜 / 礼法宗族 / 科学理性 / 虚无末日 / 赛博飞升 / 生态天人合一
    tech_branch: str     # 科技分野：生物基因 / 机械工程 / 灵能信息 / 算力天网 / 航天重工
    economy_model: str   # 经济结构：原始互易 / 井田贡赋 / 重商重金 / 工业金融 / 算力配给制
    population: int = 100
    stability: int = 80  # 内部社会稳定度 0-100
    ecology_health: int = 90  # 生态健康度 0-100
    ascension_progress: int = 0  # 终极跃迁度
    is_alive: bool = True
    chronicles: List[str] = field(default_factory=list)


class MultiverseSimEngine:
    REGIMES = [
        "神权祭司议会", "诸侯封建邦联", "中央集权帝国", 
        "远洋自由商邦", "军工科技托拉斯", "智脑共识网络"
    ]
    IDEOLOGIES = [
        "天人感应·生态守护", "绝对理性·机械崇拜", "资本扩张·重商逐利",
        "神圣信仰·唯灵永生", "虚无主义·末日方舟", "集群意志·硅基升华"
    ]
    TECH_BRANCHES = [
        "生物血肉进化", "重型机械重工", "星际能源裂变", "高维量子信息", "仿生具身智能"
    ]
    CRISES = [
        ("全球气温骤降·极寒冰河期", "生态承载暴跌，农桑受损，迫使技术向地下与保温重工跃迁"),
        ("跨大陆恶性瘟疫大流行", "旧政体瓦解，医学生物技术与封闭隔离政策崛起"),
        ("能源枯竭危机与化石枯水", "引发地缘争夺战，倒逼新能源或聚变突破"),
        ("社会阶层极化与裂解狂潮", "引发内部大革命，催生新思潮与政体更迭"),
        ("智械意识觉醒与伦理大分歧", "人机关系成为文明存亡核心议题")
    ]

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.civilizations: List[CivilizationProfile] = []

    def create_multiverse_starting_factions(self):
        self.civilizations = [
            CivilizationProfile(
                name="苍溟联邦",
                regime="远洋自由商邦",
                ideology="资本扩张·重商逐利",
                tech_branch="重型机械重工",
                economy_model="远洋贸易与金融汇兑",
                population=120
            ),
            CivilizationProfile(
                name="赤天神圣帝国",
                regime="神权祭司议会",
                ideology="神圣信仰·唯灵永生",
                tech_branch="生物血肉进化",
                economy_model="神庙配给与贡赋制",
                population=140
            ),
            CivilizationProfile(
                name="极光智理国",
                regime="诸侯封建邦联",
                ideology="天人感应·生态守护",
                tech_branch="高维量子信息",
                economy_model="自给自足与平衡工坊",
                population=110
            )
        ]

    def simulate_epoch(self, epoch_num: int) -> Dict:
        events = []
        
        # 1. 危机事件判定
        crisis_title, crisis_effect = random.choice(self.CRISES)
        events.append(f"【时代大考】{crisis_title}：{crisis_effect}")

        # 2. 各文明多维演化
        for civ in self.civilizations:
            if not civ.is_alive:
                continue

            # 多维分支可能性与转变
            if random.random() < 0.35:
                old_regime = civ.regime
                civ.regime = random.choice(self.REGIMES)
                if old_regime != civ.regime:
                    events.append(f"【政治更迭】{civ.name}发生社会大重组，由【{old_regime}】转型为【{civ.regime}】！")

            if random.random() < 0.3:
                old_ideo = civ.ideology
                civ.ideology = random.choice(self.IDEOLOGIES)
                if old_ideo != civ.ideology:
                    events.append(f"【思潮演变】{civ.name}思想分野剧变，转向崇奉【{civ.ideology}】。")

            # 科技与生态互动
            civ.population += random.randint(15, 35)
            civ.ascension_progress += random.randint(8, 18)
            civ.ecology_health = max(10, civ.ecology_health - random.randint(2, 8))

            if civ.ecology_health < 40 and "生态" not in civ.ideology:
                events.append(f"【生态警报】{civ.name}工业过载导致环境承载力濒临红线，社会动荡加剧！")
                civ.stability = max(20, civ.stability - 15)

            events.append(
                f"【文明纵深】{civ.name}（政体: {civ.regime} | 思潮: {civ.ideology}）人口达 {civ.population} 万，飞升进度 {civ.ascension_progress}%。"
            )

        return {
            "epoch": epoch_num,
            "crisis": crisis_title,
            "events": events
        }
