"""Simulation orchestration for open-ended artificial history."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
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
from timeline import advance_year
from world_engine import WorldEngine

class SimulationEngine:
    """Own the seed, ask for proposals, compile them, and delegate all mutation."""

    def __init__(
        self,
        seed: Optional[int] = None,
        planner_mode: str = "cli",
        backend: Optional[LLMBackend] = None,
        scenario: str = "warring-states",
        agent_workers: int = 1,
    ):
        self.seed = 0 if seed is None else seed
        self.rng = random.Random(self.seed)
        self.backend = backend or LLMBackend(planner_mode)
        self.agent_workers = max(1, int(agent_workers))
        self.scenario_name = scenario
        self.scenario: Optional[ScenarioState] = None
        self.current_year: Optional[int] = None
        self.active_calendar_label = ""
        self.active_span_years = 1
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
        self.current_year = self.scenario.start_year
        self.world = WorldEngine(
            self.rng,
            self.resource_specs,
            self.locations,
            self.societies,
            self.knowledge_graph,
        )
        return self.locations, self.societies

    def step(self, span_years: int = 1) -> EpochRecord:
        if not self.world:
            raise RuntimeError("call genesis() before step()")
        if not isinstance(span_years, int) or span_years < 1:
            raise ValueError("span_years must be a positive integer")
        self.epoch += 1
        self.active_span_years = span_years
        if self.scenario and self.current_year is not None:
            self.active_calendar_label = self.scenario.period_label(
                self.current_year, span_years
            )
        else:
            self.active_calendar_label = f"第{self.epoch}纪"
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
            span_years,
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
        actors = [
            actor
            for actor in sorted(self.societies.values(), key=lambda item: item.id)
            if actor.is_alive and actor.id not in busy
        ]
        proposed = self._propose_plans(actors, recent, span_years)
        for actor, plan in proposed:
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
        period_start_year = self.current_year
        period_end_year = (
            advance_year(self.current_year, span_years - 1)
            if self.current_year is not None
            else None
        )
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
                span_years,
            ),
            calendar_label=self.calendar_label(),
            span_years=span_years,
            period_start_year=period_start_year,
            period_end_year=period_end_year,
        )
        self.history.append(record)
        if self.current_year is not None:
            self.current_year = advance_year(self.current_year, span_years)
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
        if self.active_calendar_label:
            return self.active_calendar_label
        if not self.scenario:
            return f"第{self.epoch}纪"
        if self.current_year is not None:
            return self.scenario.period_label(self.current_year, 1)
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
            "current_year": self.current_year,
            "active_span_years": self.active_span_years,
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

    def _propose_plans(
        self, actors: List[Society], recent: List[str], span_years: int
    ) -> List[Tuple[Society, OpenPlan]]:
        if not actors:
            return []

        def propose(actor: Society) -> Tuple[Society, OpenPlan]:
            seed_text = f"{self.seed}|{self.epoch}|{actor.id}|plan"
            local_seed = int(
                hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16
            )
            plan = self.backend.propose_plan(
                actor,
                self.locations[actor.location_id],
                self.resource_specs,
                self.societies,
                self.knowledge_graph,
                self.world.structures,
                self.epoch,
                recent,
                random.Random(local_seed),
                self._scenario_context(),
                self.calendar_label(),
                span_years,
            )
            return actor, plan

        use_parallel = (
            self.agent_workers > 1
            and self.backend.mode == "cli"
            and len(actors) > 1
        )
        if not use_parallel:
            return [propose(actor) for actor in actors]
        with ThreadPoolExecutor(
            max_workers=min(self.agent_workers, len(actors)),
            thread_name_prefix="society-agent",
        ) as executor:
            results = list(executor.map(propose, actors))
        return sorted(results, key=lambda item: item[0].id)

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
