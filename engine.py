"""Simulation orchestration for open-ended artificial history."""

import json
import random
from dataclasses import asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple

from event_compiler import EventCompileError, EventCompiler
from llm_backend import LLMBackend
from models import (
    EpochRecord,
    KnowledgeGraph,
    Location,
    OpenEvent,
    OpenPlan,
    Resolution,
    ResourceSpec,
    Route,
    Society,
)
from plan_compiler import PlanCompileError, PlanCompiler
from world_engine import WorldEngine

class SimulationEngine:
    """Own the seed, ask for proposals, compile them, and delegate all mutation."""

    def __init__(
        self,
        seed: Optional[int] = None,
        planner_mode: str = "heuristic",
        backend: Optional[LLMBackend] = None,
    ):
        self.seed = 0 if seed is None else seed
        self.rng = random.Random(self.seed)
        self.backend = backend or LLMBackend(planner_mode)
        self.plan_compiler = PlanCompiler()
        self.event_compiler = EventCompiler()
        self.epoch = 0
        self.history: List[EpochRecord] = []
        self.resource_specs: Dict[str, ResourceSpec] = {}
        self.locations: Dict[str, Location] = {}
        self.societies: Dict[str, Society] = {}
        self.knowledge_graph = KnowledgeGraph()
        self.world: Optional[WorldEngine] = None

    def genesis(
        self,
    ) -> Tuple[Dict[str, Location], Dict[str, Society]]:
        """Create one generic carbon-based starting scenario, not a universal era."""
        self.resource_specs = {
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
        self.locations = {}
        for index, name in enumerate(location_names):
            location_id = f"location-{index + 1}"
            capacities = {
                resource_id: round(self.rng.uniform(70, 180), 3)
                for resource_id in self.resource_specs
            }
            stocks = {
                resource_id: round(capacity * self.rng.uniform(0.42, 0.9), 3)
                for resource_id, capacity in capacities.items()
            }
            self.locations[location_id] = Location(
                location_id,
                name,
                {
                    "habitability": round(self.rng.uniform(0.55, 0.92), 3),
                    "carrying_capacity": round(self.rng.uniform(95, 155), 2),
                    "crowding_pressure": round(self.rng.uniform(0.1, 0.5), 3),
                    "fluid_activity": round(self.rng.uniform(0.2, 0.9), 3),
                    "thermal_variance": round(self.rng.uniform(0.08, 0.55), 3),
                    "elevation": round(self.rng.uniform(0.0, 1.0), 3),
                },
                stocks,
                capacities,
            )
        location_ids = sorted(self.locations)
        for index, location_id in enumerate(location_ids):
            destinations = {
                location_ids[(index - 1) % len(location_ids)],
                location_ids[(index + 1) % len(location_ids)],
            }
            self.locations[location_id].routes = [
                Route(destination, round(self.rng.uniform(1.0, 4.5), 2))
                for destination in sorted(destinations)
            ]

        society_names = ["折光群体", "织痕共同体", "静潮群落"]
        self.societies = {}
        for index, name in enumerate(society_names):
            society_id = f"society-{index + 1}"
            self.societies[society_id] = Society(
                society_id,
                name,
                "具协作学习能力的智慧碳基生命，个体尺度与代谢方式未绑定现实物种",
                self.rng.randint(64, 88),
                location_ids[index],
                {
                    "nutrient_matrix": round(self.rng.uniform(28, 46), 3),
                    "fibrous_matter": round(self.rng.uniform(10, 22), 3),
                    "granular_mineral": round(self.rng.uniform(10, 22), 3),
                    "plastic_sediment": round(self.rng.uniform(5, 16), 3),
                    "circulating_solvent": round(self.rng.uniform(16, 28), 3),
                    "chemical_store": round(self.rng.uniform(4, 12), 3),
                },
                {
                    "cohesion": round(self.rng.uniform(0.35, 0.82), 3),
                    "novelty_seeking": round(self.rng.uniform(0.2, 0.9), 3),
                    "risk_tolerance": round(self.rng.uniform(0.1, 0.75), 3),
                },
                metabolic_needs={"nutrition": 0.11, "hydration": 0.04},
            )
        self.knowledge_graph = KnowledgeGraph()
        self.world = WorldEngine(
            self.rng,
            self.resource_specs,
            self.locations,
            self.societies,
            self.knowledge_graph,
        )
        return self.locations, self.societies

    def step(self) -> EpochRecord:
        if not self.world:
            raise RuntimeError("call genesis() before step()")
        self.epoch += 1
        recent = [line for record in self.history[-3:] for line in record.chronicle_text.splitlines()]
        events: List[OpenEvent] = []
        plans: List[OpenPlan] = []
        resolutions: List[Resolution] = []

        event = self.backend.propose_event(
            self.locations, self.resource_specs, self.epoch, recent, self.rng
        )
        if event:
            events.append(event)
            try:
                compiled_event = self.event_compiler.compile(event, self.epoch)
                resolutions.append(self.world.submit_event(compiled_event))
            except EventCompileError as exc:
                resolutions.append(
                    Resolution("event-uncompiled", "world", "rejected", f"事件提案无效：{exc}", "event")
                )

        busy = {
            project.plan.source.actor_id
            for project in self.world.projects.values()
            if project.status in {"queued", "active"}
        }
        for actor in sorted(self.societies.values(), key=lambda item: item.id):
            if not actor.is_alive or actor.id in busy:
                continue
            plan = self.backend.propose_plan(
                actor,
                self.locations[actor.location_id],
                self.resource_specs,
                self.societies,
                self.knowledge_graph,
                self.world.structures,
                self.epoch,
                recent,
                self.rng,
            )
            plans.append(plan)
            try:
                compiled = self.plan_compiler.compile(plan, self.epoch)
                resolutions.append(self.world.submit(compiled))
            except PlanCompileError as exc:
                resolutions.append(
                    Resolution("plan-uncompiled", actor.id, "rejected", f"计划提案无效：{exc}")
                )

        resolutions.extend(self.world.advance(self.epoch))
        readable = [self._resolution_line(item) for item in resolutions]
        record = EpochRecord(
            self.epoch,
            events,
            plans,
            resolutions,
            self.backend.chronicle(
                self.epoch, events, plans, readable, self.societies
            ),
        )
        self.history.append(record)
        return record

    def run(self, epochs: int) -> List[EpochRecord]:
        if not self.world:
            self.genesis()
        for _ in range(epochs):
            if not any(item.is_alive for item in self.societies.values()):
                break
            self.step()
        return self.history

    def state_snapshot(self) -> Dict:
        if not self.world:
            raise RuntimeError("call genesis() before taking a snapshot")
        state = {
            "seed": self.seed,
            "epoch": self.epoch,
            "resource_specs": self.resource_specs,
            "locations": self.locations,
            "societies": self.societies,
            "knowledge_graph": self.knowledge_graph,
            "structures": self.world.structures,
            "projects": self.world.projects,
            "events": self.world.events,
            "history": self.history,
        }
        return json.loads(json.dumps(state, default=self._json_default, ensure_ascii=False, sort_keys=True))

    def path_signature(self) -> Tuple:
        if not self.world:
            raise RuntimeError("call genesis() before reading a path signature")
        knowledge = tuple(sorted(node.name for node in self.knowledge_graph.nodes.values()))
        structures = tuple(sorted(item.name for item in self.world.structures.values()))
        organizations = tuple(
            sorted(org.name for actor in self.societies.values() for org in actor.organizations.values())
        )
        locations = tuple(sorted((item.id, item.location_id, item.is_alive) for item in self.societies.values()))
        return knowledge, structures, organizations, locations

    def _resolution_line(self, resolution: Resolution) -> str:
        if resolution.actor_id == "world":
            subject = "世界"
        else:
            actor = self.societies.get(resolution.actor_id)
            subject = actor.name if actor else resolution.actor_id
        line = f"{subject}：{resolution.summary}。"
        if resolution.side_effects:
            line += "副作用：" + "；".join(resolution.side_effects) + "。"
        return line

    @classmethod
    def _json_default(cls, value):
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, Enum):
            return value.value
        try:
            return asdict(value)
        except TypeError as exc:
            raise TypeError(f"cannot serialize {type(value)}") from exc
