from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


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


class DiplomaticStatus(str, Enum):
    ALLIED = "同盟"
    FRIENDLY = "交好"
    NEUTRAL = "中立"
    HOSTILE = "敌对"
    WAR = "交战"


@dataclass
class Region:
    id: str
    name: str
    terrain: TerrainType
    fertility: int
    mineral_richness: int
    controlled_by: Optional[str] = None
    neighbors: List[str] = field(default_factory=list)


@dataclass
class MemoryEntry:
    epoch: int
    summary: str
    salience: int = 1


@dataclass
class Civilization:
    id: str
    name: str
    leader_title: str
    leader_name: str
    totem: str
    ethos: str
    population: int
    food: int
    ore: int
    wealth: int
    techs: List[str] = field(default_factory=list)
    customs: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    is_alive: bool = True
    home_region_id: str = ""
    goals: List[str] = field(default_factory=list)
    memory: List[MemoryEntry] = field(default_factory=list)

    def remember(self, epoch: int, summary: str, salience: int = 1, max_items: int = 12) -> None:
        self.memory.append(MemoryEntry(epoch=epoch, summary=summary, salience=salience))
        self.memory = sorted(self.memory, key=lambda m: (m.salience, m.epoch), reverse=True)[:max_items]


# Backward-compatible name used by the earlier experimental engines.
Tribe = Civilization


@dataclass
class CivilizationView:
    epoch: int
    self_state: Civilization
    home_region: Region
    known_regions: List[Region]
    known_civilizations: List[Civilization]
    recent_events: List[str]


@dataclass
class AgentIntent:
    civilization_id: str
    action_type: ActionType
    target_civilization_id: Optional[str] = None
    target_region_id: Optional[str] = None
    edict: str = ""
    rationale: str = ""
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def tribe_id(self) -> str:
        return self.civilization_id

    @property
    def target_tribe_id(self) -> Optional[str]:
        return self.target_civilization_id


TribeDecision = AgentIntent


@dataclass
class WorldEvent:
    epoch: int
    kind: str
    text: str
    actors: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpochRecord:
    epoch_num: int
    disaster_event: Optional[str]
    actions: List[AgentIntent]
    resolutions: List[str]
    chronicle_text: str
    events: List[WorldEvent] = field(default_factory=list)


@dataclass
class WorldState:
    epoch: int = 0
    regions: List[Region] = field(default_factory=list)
    civilizations: List[Civilization] = field(default_factory=list)
    history: List[EpochRecord] = field(default_factory=list)
    seed: int = 0

    @property
    def tribes(self) -> List[Civilization]:
        return self.civilizations

    def civilization_map(self) -> Dict[str, Civilization]:
        return {c.id: c for c in self.civilizations}

    def region_map(self) -> Dict[str, Region]:
        return {r.id: r for r in self.regions}
