"""Domain-neutral state and plan models for the artificial-history simulator."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class PrimitiveKind(str, Enum):
    """Small, domain-neutral operations understood by the world engine."""

    ACQUIRE = "acquire"
    TRANSFORM = "transform"
    CONSTRUCT = "construct"
    RELOCATE = "relocate"
    RESEARCH = "research"
    COMMUNICATE = "communicate"
    ORGANIZE = "organize"


@dataclass
class ResourceSpec:
    id: str
    name: str
    tags: Set[str]
    mass_per_unit: float = 1.0


@dataclass
class Route:
    destination_id: str
    distance: float
    carrying_cost: float = 1.0


@dataclass
class Location:
    id: str
    name: str
    properties: Dict[str, float]
    stocks: Dict[str, float]
    capacities: Dict[str, float]
    routes: List[Route] = field(default_factory=list)


@dataclass
class Structure:
    id: str
    name: str
    owner_id: str
    location_id: str
    effects: Dict[str, float]
    durability: float = 1.0


@dataclass
class Organization:
    id: str
    name: str
    purpose: str
    members: int
    rules: List[str]
    effects: Dict[str, float]


@dataclass
class RiskSpec:
    name: str
    probability: float
    effect: str
    magnitude: float
    resource_id: Optional[str] = None


@dataclass
class KnowledgeProposal:
    name: str
    description: str
    prerequisites: List[str]
    observations: List[str]
    capabilities: List[str]
    risks: List[RiskSpec]


@dataclass
class KnowledgeNode:
    id: str
    name: str
    description: str
    discovered_by: str
    discovered_epoch: int
    prerequisites: List[str]
    observations: List[str]
    capabilities: List[str]
    risks: List[RiskSpec]


@dataclass
class KnowledgeGraph:
    nodes: Dict[str, KnowledgeNode] = field(default_factory=dict)

    def add(self, node: KnowledgeNode) -> None:
        missing = [item for item in node.prerequisites if item not in self.nodes]
        if missing:
            raise ValueError(f"knowledge prerequisites are missing: {missing}")
        self.nodes[node.id] = node

    def available_capabilities(self, knowledge_ids: Set[str]) -> Set[str]:
        capabilities: Set[str] = set()
        for knowledge_id in knowledge_ids:
            node = self.nodes.get(knowledge_id)
            if node:
                capabilities.update(node.capabilities)
        return capabilities


@dataclass
class Society:
    id: str
    name: str
    species_profile: str
    population: int
    location_id: str
    inventory: Dict[str, float]
    traits: Dict[str, float]
    metabolic_needs: Dict[str, float] = field(default_factory=dict)
    knowledge: Set[str] = field(default_factory=set)
    organizations: Dict[str, Organization] = field(default_factory=dict)
    is_alive: bool = True


@dataclass
class PlanStep:
    """A planner-facing declaration using universal operations and open payloads."""

    operation: str
    parameters: Dict[str, Any]
    rationale: str = ""


@dataclass
class OpenPlan:
    actor_id: str
    title: str
    objective: str
    steps: List[PlanStep]
    assumptions: List[str] = field(default_factory=list)


@dataclass
class OpenEvent:
    """An untyped event proposal expressed as causal state changes."""

    name: str
    description: str
    causes: List[str]
    duration: int
    location_resource_deltas: Dict[str, Dict[str, float]]
    location_property_deltas: Dict[str, Dict[str, float]]
    external_inputs: Dict[str, float] = field(default_factory=dict)
    external_outputs: Dict[str, float] = field(default_factory=dict)


@dataclass
class CompiledEvent:
    id: str
    source: OpenEvent


@dataclass
class EventProcess:
    event: CompiledEvent
    remaining_ticks: int


@dataclass
class Primitive:
    kind: PrimitiveKind
    parameters: Dict[str, Any]
    labor: int
    duration: int
    risks: List[RiskSpec] = field(default_factory=list)


@dataclass
class CompiledPlan:
    id: str
    source: OpenPlan
    primitives: List[Primitive]


@dataclass
class Project:
    id: str
    plan: CompiledPlan
    primitive_index: int = 0
    remaining_ticks: int = 0
    started: bool = False
    status: str = "queued"
    failure_reason: Optional[str] = None


@dataclass
class Resolution:
    plan_id: str
    actor_id: str
    status: str
    summary: str
    primitive: Optional[str] = None
    side_effects: List[str] = field(default_factory=list)


@dataclass
class EpochRecord:
    epoch_num: int
    events: List[OpenEvent]
    plans: List[OpenPlan]
    resolutions: List[Resolution]
    chronicle_text: str
    calendar_label: str = ""
    span_years: int = 1
    period_start_year: Optional[int] = None
    period_end_year: Optional[int] = None

    @property
    def actions(self) -> List[OpenPlan]:
        """Compatibility spelling for callers that displayed the old action list."""
        return self.plans


def public_dict(value: Any) -> Dict[str, Any]:
    """Return a JSON-friendly dataclass dictionary with stable set ordering."""

    raw = asdict(value)

    def normalize(item: Any) -> Any:
        if isinstance(item, set):
            return sorted(item)
        if isinstance(item, dict):
            return {key: normalize(item[key]) for key in sorted(item)}
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, Enum):
            return item.value
        return item

    return normalize(raw)
