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
    Society,
)
from plan_compiler import PlanCompileError, PlanCompiler
from scenarios import ScenarioState, build_scenario
from world_engine import WorldEngine

class SimulationEngine:
    """Own the seed, ask for proposals, compile them, and delegate all mutation."""

    def __init__(
        self,
        seed: Optional[int] = None,
        planner_mode: str = "cli",
        backend: Optional[LLMBackend] = None,
        scenario: str = "warring-states",
    ):
        self.seed = 0 if seed is None else seed
        self.rng = random.Random(self.seed)
        self.backend = backend or LLMBackend(planner_mode)
        self.scenario_name = scenario
        self.scenario: Optional[ScenarioState] = None
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
        """Load scenario data without changing the domain-neutral world engine."""
        self.scenario = build_scenario(self.scenario_name, self.rng)
        self.resource_specs = self.scenario.resource_specs
        self.locations = self.scenario.locations
        self.societies = self.scenario.societies
        self.knowledge_graph = self.scenario.knowledge_graph
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
            self.locations,
            self.resource_specs,
            self.epoch,
            recent,
            self.rng,
            self._scenario_context(),
            self.calendar_label(),
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
                self._scenario_context(),
                self.calendar_label(),
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
                self.epoch,
                events,
                plans,
                readable,
                self.societies,
                self._scenario_context(),
                self.calendar_label(),
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

    def calendar_label(self) -> str:
        if not self.scenario:
            return f"第{self.epoch}纪"
        return self.scenario.calendar_label(self.epoch)

    def _scenario_context(self) -> str:
        return self.scenario.context if self.scenario else ""

    def state_snapshot(self) -> Dict:
        if not self.world:
            raise RuntimeError("call genesis() before taking a snapshot")
        state = {
            "seed": self.seed,
            "scenario": self.scenario_name,
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
