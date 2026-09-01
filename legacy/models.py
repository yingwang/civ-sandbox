import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class TerrainType(str, Enum):
    PLAINS = "平原沃土"
    RIVERLAND = "大泽水系"
    HIGHLAND = "高山荒原"
    COASTAL = "沿海孤岛"
    FOREST = "密林山谷"
    DESERT = "大漠戈壁"


class ActionType(str, Enum):
    CULTIVATE = "开垦农桑"
    EXPAND = "迁徙筑城"
    TRADE = "互通有无"
    RAID = "起兵征伐"
    INVENT = "钻研百工"
    WORSHIP = "祭祀通神"
    TREATY = "结盟立约"


@dataclass
class Region:
    id: str
    name: str
    terrain: TerrainType
    fertility: int  # 1-10
    mineral_richness: int  # 1-10
    controlled_by: Optional[str] = None


@dataclass
class Tribe:
    id: str
    name: str
    leader_title: str
    leader_name: str
    totem: str
    ethos: str  # 文化基调与性格特征
    population: int
    food: int
    ore: int
    wealth: int
    techs: List[str] = field(default_factory=list)
    customs: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)  # tribe_id -> status (交好, 仇视, 称臣, 中立)
    is_alive: bool = True
    home_region_id: str = ""


@dataclass
class TribeDecision:
    tribe_id: str
    action_type: ActionType
    target_tribe_id: Optional[str] = None
    target_region_id: Optional[str] = None
    edict: str = ""  # 领袖诏令 / 部落决断宣言
    rationale: str = ""  # 内部动机


@dataclass
class EpochRecord:
    epoch_num: int
    disaster_event: Optional[str]
    actions: List[TribeDecision]
    resolutions: List[str]
    chronicle_text: str  # 史官撰写的纪元实录
