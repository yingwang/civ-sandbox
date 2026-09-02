"""Scenario data for the domain-neutral artificial-history engine."""

from dataclasses import dataclass
import random
from typing import Dict, Optional

from models import (
    KnowledgeGraph,
    KnowledgeNode,
    Location,
    Organization,
    ResourceSpec,
    RiskSpec,
    Route,
    Society,
)
from timeline import advance_year, format_period, format_year


@dataclass
class ScenarioState:
    """Initial state and narrative context, kept outside the world engine."""

    id: str
    title: str
    context: str
    resource_specs: Dict[str, ResourceSpec]
    locations: Dict[str, Location]
    societies: Dict[str, Society]
    knowledge_graph: KnowledgeGraph
    start_year_bce: Optional[int] = None

    @property
    def start_year(self) -> Optional[int]:
        return -self.start_year_bce if self.start_year_bce is not None else None

    def calendar_label(self, epoch: int) -> str:
        if self.start_year_bce is not None:
            year = advance_year(-self.start_year_bce, max(0, epoch - 1))
            return format_year(year)
        return f"第{epoch}纪"

    def period_label(self, start_year: int, span_years: int) -> str:
        end_year = advance_year(start_year, span_years - 1)
        return format_period(start_year, end_year)


def build_scenario(name: str, rng: random.Random) -> ScenarioState:
    if name == "warring-states":
        return _warring_states(rng)
    if name == "open-origin":
        return _open_origin(rng)
    raise ValueError(f"unknown scenario: {name}")


def _warring_states(rng: random.Random) -> ScenarioState:
    """China in 230 BCE, with history known but the future left unresolved."""

    specs = {
        "grain": ResourceSpec("grain", "粮食", {"nutrition", "organic"}),
        "water": ResourceSpec("water", "水", {"fluid", "hydration"}),
        "timber": ResourceSpec("timber", "木材", {"organic", "structural"}),
        "stone": ResourceSpec("stone", "石料", {"mineral", "structural"}),
        "iron": ResourceSpec("iron", "铁料", {"mineral", "structural"}),
        "bronze": ResourceSpec(
            "bronze", "青铜", {"mineral", "structural", "processed"}
        ),
        "horses": ResourceSpec("horses", "马匹", {"organic", "transport"}, 5.0),
        "textiles": ResourceSpec(
            "textiles", "布帛", {"organic", "processed", "portable"}
        ),
        "salt": ResourceSpec("salt", "盐", {"mineral", "nutrition"}),
    }

    place_data = {
        "guanzhong": ("秦国关中", 0.82, 190.0, 0.16, 0.55, 0.28, 0.70, 0.26, 0.20, 0.78),
        "han": ("韩国河洛", 0.70, 112.0, 0.37, 0.62, 0.30, 0.42, 0.34, 0.26, 0.86),
        "zhao": ("赵国河北", 0.68, 145.0, 0.28, 0.38, 0.46, 0.60, 0.22, 0.38, 0.72),
        "wei": ("魏国大梁", 0.73, 130.0, 0.35, 0.70, 0.35, 0.33, 0.52, 0.25, 0.88),
        "chu": ("楚国江淮", 0.84, 205.0, 0.18, 0.86, 0.20, 0.24, 0.44, 0.14, 0.62),
        "yan": ("燕国北境", 0.61, 118.0, 0.20, 0.34, 0.58, 0.76, 0.18, 0.42, 0.56),
        "qi": ("齐国临淄", 0.80, 172.0, 0.30, 0.66, 0.24, 0.25, 0.32, 0.22, 0.84),
    }
    locations: Dict[str, Location] = {}
    for place_id, values in place_data.items():
        (
            display_name,
            habitability,
            carrying_capacity,
            crowding,
            fluid_activity,
            thermal_variance,
            elevation,
            flood_exposure,
            drought_exposure,
            road_access,
        ) = values
        capacities = {
            "grain": carrying_capacity * 1.75,
            "water": carrying_capacity * 1.45,
            "timber": carrying_capacity * 0.82,
            "stone": carrying_capacity * 0.72,
            "iron": carrying_capacity * 0.34,
            "bronze": carrying_capacity * 0.18,
            "horses": carrying_capacity * 0.20,
            "textiles": carrying_capacity * 0.42,
            "salt": carrying_capacity * 0.24,
        }
        stocks = {
            resource_id: round(capacity * rng.uniform(0.46, 0.80), 3)
            for resource_id, capacity in capacities.items()
        }
        locations[place_id] = Location(
            place_id,
            display_name,
            {
                "habitability": habitability,
                "carrying_capacity": carrying_capacity,
                "crowding_pressure": crowding,
                "fluid_activity": fluid_activity,
                "thermal_variance": thermal_variance,
                "elevation": elevation,
                "flood_exposure": flood_exposure,
                "drought_exposure": drought_exposure,
                "road_access": road_access,
            },
            stocks,
            {key: round(value, 3) for key, value in capacities.items()},
        )

    links = {
        "guanzhong": {"han", "zhao", "chu"},
        "han": {"guanzhong", "zhao", "wei", "chu"},
        "zhao": {"guanzhong", "han", "wei", "yan", "qi"},
        "wei": {"han", "zhao", "chu", "qi"},
        "chu": {"guanzhong", "han", "wei", "qi"},
        "yan": {"zhao", "qi"},
        "qi": {"zhao", "wei", "chu", "yan"},
    }
    for source_id, destinations in links.items():
        locations[source_id].routes = [
            Route(destination_id, round(rng.uniform(1.2, 4.2), 2), 1.0)
            for destination_id in sorted(destinations)
        ]

    graph = KnowledgeGraph()
    initial_knowledge = [
        KnowledgeNode(
            "knowledge-farming",
            "农耕与水利经验",
            "根据土壤、节气和水源组织耕作，并维护沟渠。",
            "scenario",
            0,
            [],
            ["各国长期耕作与水利记录"],
            ["耕作:grain", "蓄水:water"],
            [RiskSpec("水利失修", 0.08, "environment_damage", 0.03)],
        ),
        KnowledgeNode(
            "knowledge-ironworking",
            "炼铁与铁器制作",
            "冶炼铁料并将其制成农具、工具与兵器。",
            "scenario",
            0,
            [],
            ["炉温、矿料与成品强度已有长期记录"],
            ["塑造:iron"],
            [RiskSpec("炉火与矿渣伤人", 0.10, "population_loss", 2.0)],
        ),
        KnowledgeNode(
            "knowledge-fortification",
            "夯土筑城",
            "用木、石与夯土修筑城墙、仓廪和道路。",
            "scenario",
            0,
            [],
            ["多地城防与土木工程记录"],
            ["建造:stone", "建造:timber"],
            [RiskSpec("大型土木劳役失序", 0.08, "organization_strain", 0.04)],
        ),
        KnowledgeNode(
            "knowledge-horse-logistics",
            "车马运输",
            "饲养马匹，并用道路和驿站输送人员与物资。",
            "scenario",
            0,
            [],
            ["长途运输的耗粮和速度已有记录"],
            ["运输:horses"],
            [RiskSpec("长途运输损耗", 0.10, "resource_loss", 2.0, "grain")],
        ),
        KnowledgeNode(
            "knowledge-records",
            "文字、律令与官府簿册",
            "用文字保存命令、户籍、赋税和工程记录。",
            "scenario",
            0,
            [],
            ["各国官府与民间已有成体系文书"],
            ["记录:administration"],
            [RiskSpec("簿册与权责僵化", 0.07, "organization_strain", 0.03)],
        ),
    ]
    for node in initial_knowledge:
        graph.add(node)

    state_data = {
        "qin": (
            "秦国",
            "guanzhong",
            138,
            0.78,
            0.68,
            0.73,
            "人类国家。商鞅变法后的法令、郡县与军功体系仍在运转，国力强盛，朝廷正权衡是否继续东进。",
            "秦国中枢官署",
        ),
        "han-state": (
            "韩国",
            "han",
            86,
            0.48,
            0.51,
            0.38,
            "人类国家。地处列强之间，疆土狭小，既担忧秦军，也试图借外交与工程保存国力。",
            "韩国王廷与地方官署",
        ),
        "zhao-state": (
            "赵国",
            "zhao",
            119,
            0.57,
            0.61,
            0.62,
            "人类国家。长平之战后实力受损，但北方骑战经验仍深，朝廷在守边、合纵与恢复民力之间取舍。",
            "赵国军政议事体系",
        ),
        "wei-state": (
            "魏国",
            "wei",
            104,
            0.52,
            0.63,
            0.46,
            "人类国家。大梁居中原水陆要冲，商业与工程传统深厚，却同时受数国牵制。",
            "魏国王廷与大梁官署",
        ),
        "chu-state": (
            "楚国",
            "chu",
            132,
            0.46,
            0.66,
            0.55,
            "人类国家。疆域广大、物产丰富，地方势力与王廷并存，能动员大量资源，却不易形成一致行动。",
            "楚国王廷与封君会议",
        ),
        "yan-state": (
            "燕国",
            "yan",
            92,
            0.55,
            0.57,
            0.52,
            "人类国家。北境辽阔而人口较少，重视边防、骑兵与通往中原的外交消息。",
            "燕国王廷与边郡体系",
        ),
        "qi-state": (
            "齐国",
            "qi",
            126,
            0.62,
            0.72,
            0.35,
            "人类国家。临淄富庶，盐铁与商贸发达，眼下倾向谨慎观望，但国内对是否介入西方战事意见不一。",
            "齐国王廷与临淄官署",
        ),
    }
    societies: Dict[str, Society] = {}
    for index, (society_id, values) in enumerate(state_data.items(), start=1):
        name, location_id, population, cohesion, novelty, risk, profile, org_name = values
        inventory = {
            "grain": round(rng.uniform(58, 88), 3),
            "water": round(rng.uniform(42, 68), 3),
            "timber": round(rng.uniform(18, 34), 3),
            "stone": round(rng.uniform(15, 32), 3),
            "iron": round(rng.uniform(10, 24), 3),
            "bronze": round(rng.uniform(6, 16), 3),
            "horses": round(rng.uniform(5, 14), 3),
            "textiles": round(rng.uniform(14, 28), 3),
            "salt": round(rng.uniform(7, 16), 3),
        }
        organization = Organization(
            id=f"organization-{society_id}-court",
            name=org_name,
            purpose="维持政令、赋税、粮仓与地方协作",
            members=min(population, 28),
            rules=["依官府文书分派事务", "重大决策由朝廷议定"],
            effects={"coordination": 0.18, "distribution": 0.12},
        )
        societies[society_id] = Society(
            society_id,
            name,
            profile,
            population,
            location_id,
            inventory,
            {
                "cohesion": cohesion,
                "novelty_seeking": novelty,
                "risk_tolerance": risk,
            },
            metabolic_needs={"nutrition": 0.075, "hydration": 0.028},
            knowledge={node.id for node in initial_knowledge},
            organizations={organization.id: organization},
        )

    context = (
        "这是公元前230年的中国，秦王政尚未统一六国。秦、韩、赵、魏、楚、燕、齐都是真实的人类国家，"
        "此前发生过的变法、战争与外交构成共同记忆，但公元前230年以后没有既定剧本。"
        "秦不保证获胜，六国也不保证灭亡；各国可结盟、改革、休养、扩张、分裂或走向未曾发生过的道路。"
        "每一纪代表一年。人口与资源数值是用于结算的规模单位，叙事中应写成百姓、粮仓、国力与物资，"
        "不要把抽象数值误写成精确人口统计。"
    )
    return ScenarioState(
        "warring-states",
        "战国末年开放历史",
        context,
        specs,
        locations,
        societies,
        graph,
        start_year_bce=230,
    )


def _open_origin(rng: random.Random) -> ScenarioState:
    """The original non-Earth carbon-life scenario, retained as an option."""

    specs = {
        "nutrient_matrix": ResourceSpec(
            "nutrient_matrix", "可代谢营养基质", {"nutrition", "organic"}
        ),
        "fibrous_matter": ResourceSpec(
            "fibrous_matter", "韧性纤维质", {"organic", "structural"}
        ),
        "granular_mineral": ResourceSpec(
            "granular_mineral", "颗粒矿质", {"mineral", "structural"}
        ),
        "plastic_sediment": ResourceSpec(
            "plastic_sediment", "可塑沉积质", {"mineral", "moldable"}
        ),
        "circulating_solvent": ResourceSpec(
            "circulating_solvent", "循环溶剂", {"fluid", "hydration"}
        ),
        "chemical_store": ResourceSpec(
            "chemical_store", "化学储能质", {"energy", "organic"}
        ),
    }
    location_names = ["低势汇流带", "多孔高台", "周期湿润谷", "风化边缘地"]
    locations: Dict[str, Location] = {}
    for index, display_name in enumerate(location_names):
        location_id = f"location-{index + 1}"
        capacities = {
            resource_id: round(rng.uniform(70, 180), 3) for resource_id in specs
        }
        stocks = {
            resource_id: round(capacity * rng.uniform(0.42, 0.9), 3)
            for resource_id, capacity in capacities.items()
        }
        locations[location_id] = Location(
            location_id,
            display_name,
            {
                "habitability": round(rng.uniform(0.55, 0.92), 3),
                "carrying_capacity": round(rng.uniform(95, 155), 2),
                "crowding_pressure": round(rng.uniform(0.1, 0.5), 3),
                "fluid_activity": round(rng.uniform(0.2, 0.9), 3),
                "thermal_variance": round(rng.uniform(0.08, 0.55), 3),
                "elevation": round(rng.uniform(0.0, 1.0), 3),
            },
            stocks,
            capacities,
        )
    location_ids = sorted(locations)
    for index, location_id in enumerate(location_ids):
        destinations = {
            location_ids[(index - 1) % len(location_ids)],
            location_ids[(index + 1) % len(location_ids)],
        }
        locations[location_id].routes = [
            Route(destination, round(rng.uniform(1.0, 4.5), 2))
            for destination in sorted(destinations)
        ]

    societies: Dict[str, Society] = {}
    for index, display_name in enumerate(["折光群体", "织痕共同体", "静潮群落"]):
        society_id = f"society-{index + 1}"
        societies[society_id] = Society(
            society_id,
            display_name,
            "具协作学习能力的智慧碳基生命，个体尺度与代谢方式未绑定现实物种",
            rng.randint(64, 88),
            location_ids[index],
            {
                "nutrient_matrix": round(rng.uniform(28, 46), 3),
                "fibrous_matter": round(rng.uniform(10, 22), 3),
                "granular_mineral": round(rng.uniform(10, 22), 3),
                "plastic_sediment": round(rng.uniform(5, 16), 3),
                "circulating_solvent": round(rng.uniform(16, 28), 3),
                "chemical_store": round(rng.uniform(4, 12), 3),
            },
            {
                "cohesion": round(rng.uniform(0.35, 0.82), 3),
                "novelty_seeking": round(rng.uniform(0.2, 0.9), 3),
                "risk_tolerance": round(rng.uniform(0.1, 0.75), 3),
            },
            metabolic_needs={"nutrition": 0.11, "hydration": 0.04},
        )
    return ScenarioState(
        "open-origin",
        "智慧碳基生命开放起源",
        "三个非地球智慧碳基社会刚刚形成。环境、知识、制度与发展方向均没有预设历史。",
        specs,
        locations,
        societies,
        KnowledgeGraph(),
    )
