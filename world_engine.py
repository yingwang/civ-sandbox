"""Deterministic resolution of compiled plans against physical world state."""

import hashlib
import math
import random
from typing import Dict, Iterable, List, Optional, Set, Tuple

from models import (
    CompiledEvent,
    CompiledPlan,
    EventProcess,
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeProposal,
    Location,
    Organization,
    Primitive,
    PrimitiveKind,
    Project,
    Resolution,
    ResourceSpec,
    RiskSpec,
    Society,
    Structure,
)


class FeasibilityError(ValueError):
    pass


class WorldEngine:
    """The only component allowed to mutate simulated world state."""

    PRIMITIVE_NAMES = {
        PrimitiveKind.ACQUIRE: "取得资源",
        PrimitiveKind.TRANSFORM: "转换资源",
        PrimitiveKind.CONSTRUCT: "建造结构",
        PrimitiveKind.RELOCATE: "迁移种群",
        PrimitiveKind.RESEARCH: "检验知识",
        PrimitiveKind.COMMUNICATE: "传播信息",
        PrimitiveKind.ORGANIZE: "组织协作",
    }

    def __init__(
        self,
        rng: random.Random,
        resource_specs: Dict[str, ResourceSpec],
        locations: Dict[str, Location],
        societies: Dict[str, Society],
        knowledge_graph: Optional[KnowledgeGraph] = None,
    ):
        self.rng = rng
        self.resource_specs = resource_specs
        self.locations = locations
        self.societies = societies
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()
        self.structures: Dict[str, Structure] = {}
        self.projects: Dict[str, Project] = {}
        self.events: Dict[str, EventProcess] = {}

    def submit_event(self, event: CompiledEvent) -> Resolution:
        try:
            self._validate_event(event)
        except FeasibilityError as exc:
            return Resolution(event.id, "world", "rejected", f"事件不成立：{exc}", "event")
        self.events[event.id] = EventProcess(event, event.source.duration)
        return Resolution(
            event.id,
            "world",
            "submitted",
            f"事件《{event.source.name}》开始，持续 {event.source.duration} 纪",
            "event",
        )

    def submit(self, plan: CompiledPlan) -> Resolution:
        actor = self.societies.get(plan.source.actor_id)
        if not actor or not actor.is_alive:
            return Resolution(plan.id, plan.source.actor_id, "rejected", "计划主体不存在或已灭绝")
        if any(
            project.plan.source.actor_id == actor.id
            and project.status in {"queued", "active"}
            for project in self.projects.values()
        ):
            return Resolution(plan.id, actor.id, "rejected", "已有计划占用主要协作能力")
        project = Project(plan.id, plan)
        self.projects[project.id] = project
        return Resolution(plan.id, actor.id, "submitted", f"已接受开放计划《{plan.source.title}》")

    def advance(self, epoch: int) -> List[Resolution]:
        resolutions: List[Resolution] = self._advance_events()
        for project_id in sorted(self.projects):
            project = self.projects[project_id]
            if project.status in {"completed", "failed", "cancelled"}:
                continue
            actor = self.societies[project.plan.source.actor_id]
            if not actor.is_alive:
                project.status = "cancelled"
                resolutions.append(
                    Resolution(project.id, actor.id, "cancelled", "主体灭绝，计划中止")
                )
                continue

            primitive = project.plan.primitives[project.primitive_index]
            primitive_name = self.PRIMITIVE_NAMES[primitive.kind]
            if not project.started:
                try:
                    self._start(actor, primitive)
                except FeasibilityError as exc:
                    project.status = "failed"
                    project.failure_reason = str(exc)
                    resolutions.append(
                        Resolution(
                            project.id,
                            actor.id,
                            "failed",
                            f"《{project.plan.source.title}》不可行：{exc}",
                            primitive.kind.value,
                        )
                    )
                    continue
                project.status = "active"
                project.started = True
                project.remaining_ticks = primitive.duration
                resolutions.append(
                    Resolution(
                        project.id,
                        actor.id,
                        "started",
                        f"开始{primitive_name}，预计需 {primitive.duration} 纪",
                        primitive.kind.value,
                    )
                )

            project.remaining_ticks -= 1
            if project.remaining_ticks > 0:
                resolutions.append(
                    Resolution(
                        project.id,
                        actor.id,
                        "progress",
                        f"{primitive_name}尚余 {project.remaining_ticks} 纪",
                        primitive.kind.value,
                    )
                )
                continue

            success, summary = self._complete(actor, primitive, epoch)
            side_effects = self._resolve_risks(actor, primitive)
            if not success:
                project.status = "failed"
                project.failure_reason = summary
                resolutions.append(
                    Resolution(
                        project.id,
                        actor.id,
                        "failed",
                        summary,
                        primitive.kind.value,
                        side_effects,
                    )
                )
                continue

            project.primitive_index += 1
            project.started = False
            if project.primitive_index >= len(project.plan.primitives):
                project.status = "completed"
                status = "completed"
                summary = f"《{project.plan.source.title}》完成。{summary}"
            else:
                status = "step_completed"
                summary = f"阶段完成。{summary}"
            resolutions.append(
                Resolution(
                    project.id,
                    actor.id,
                    status,
                    summary,
                    primitive.kind.value,
                    side_effects,
                )
            )

        resolutions.extend(self._environment_and_population())
        return resolutions

    def _validate_event(self, compiled: CompiledEvent) -> None:
        event = compiled.source
        location_ids = set(event.location_resource_deltas) | set(
            event.location_property_deltas
        )
        unknown_locations = location_ids - set(self.locations)
        if unknown_locations:
            raise FeasibilityError(f"事件指向未知地点 {sorted(unknown_locations)}")

        resources: Set[str] = set(event.external_inputs) | set(event.external_outputs)
        for deltas in event.location_resource_deltas.values():
            resources.update(deltas)
        unknown_resources = resources - set(self.resource_specs)
        if unknown_resources:
            raise FeasibilityError(f"事件涉及未知资源 {sorted(unknown_resources)}")

        internal_mass = sum(
            delta * self.resource_specs[resource_id].mass_per_unit
            for deltas in event.location_resource_deltas.values()
            for resource_id, delta in deltas.items()
        )
        input_mass = sum(
            amount * self.resource_specs[resource_id].mass_per_unit
            for resource_id, amount in event.external_inputs.items()
        )
        output_mass = sum(
            amount * self.resource_specs[resource_id].mass_per_unit
            for resource_id, amount in event.external_outputs.items()
        )
        if abs(internal_mass - (input_mass - output_mass)) > 1e-6:
            raise FeasibilityError("事件资源变化与外部输入输出不守恒")

        for location_id, deltas in event.location_resource_deltas.items():
            location = self.locations[location_id]
            for resource_id, delta in deltas.items():
                final = location.stocks.get(resource_id, 0.0) + delta
                capacity = location.capacities.get(resource_id, max(final, 0.0))
                if final < -1e-9:
                    raise FeasibilityError(f"{location_id} 的 {resource_id} 不足以支撑事件")
                if final > capacity + 1e-9:
                    raise FeasibilityError(f"{location_id} 的 {resource_id} 变化超过局部容量")

        for location_id, deltas in event.location_property_deltas.items():
            location = self.locations[location_id]
            for property_name, delta in deltas.items():
                current = location.properties.get(property_name, 0.0)
                if abs(delta) > max(1.0, abs(current)) * 0.5:
                    raise FeasibilityError(f"{property_name} 的单次变化超过物理上限")
                if property_name == "habitability" and not 0 <= current + delta <= 1:
                    raise FeasibilityError("栖息适宜度必须保持在 0 到 1 之间")

    def _advance_events(self) -> List[Resolution]:
        resolutions: List[Resolution] = []
        for event_id in sorted(self.events):
            process = self.events[event_id]
            if process.remaining_ticks <= 0:
                continue
            event = process.event.source
            divisor = event.duration
            resource_updates = []
            for location_id, deltas in event.location_resource_deltas.items():
                location = self.locations[location_id]
                for resource_id, total_delta in deltas.items():
                    updated = location.stocks.get(resource_id, 0.0) + total_delta / divisor
                    capacity = location.capacities.get(resource_id, updated)
                    if updated < -1e-9 or updated > capacity + 1e-9:
                        process.remaining_ticks = 0
                        resolutions.append(
                            Resolution(
                                event_id,
                                "world",
                                "failed",
                                f"事件《{event.name}》因后续状态超出局部资源边界而中止",
                                "event",
                            )
                        )
                        break
                    resource_updates.append((location, resource_id, updated))
                if process.remaining_ticks <= 0:
                    break
            if process.remaining_ticks <= 0:
                continue
            property_updates = []
            for location_id, deltas in event.location_property_deltas.items():
                location = self.locations[location_id]
                for property_name, total_delta in deltas.items():
                    updated = location.properties.get(property_name, 0.0) + total_delta / divisor
                    if property_name == "habitability" and not 0 <= updated <= 1:
                        process.remaining_ticks = 0
                        resolutions.append(
                            Resolution(
                                event_id,
                                "world",
                                "failed",
                                f"事件《{event.name}》因后续适宜度越界而中止",
                                "event",
                            )
                        )
                        break
                    property_updates.append((location, property_name, updated))
                if process.remaining_ticks <= 0:
                    break
            if process.remaining_ticks <= 0:
                continue
            for location, resource_id, updated in resource_updates:
                location.stocks[resource_id] = round(updated, 6)
            for location, property_name, updated in property_updates:
                location.properties[property_name] = round(updated, 6)
            process.remaining_ticks -= 1
            if process.remaining_ticks:
                summary = (
                    f"事件《{event.name}》继续作用，尚余 {process.remaining_ticks} 纪"
                )
                status = "progress"
            else:
                summary = f"事件《{event.name}》结束"
                status = "completed"
            resolutions.append(
                Resolution(event_id, "world", status, summary, "event")
            )
        return resolutions

    def _start(self, actor: Society, primitive: Primitive) -> None:
        required_labor = self._effective_labor(actor, primitive)
        if required_labor > self._labor_capacity(actor):
            raise FeasibilityError(
                f"需 {required_labor} 劳动单位，但当前最多可协调 {self._labor_capacity(actor)}"
            )
        params = primitive.parameters
        self._require_capabilities(actor, params.get("required_capabilities", []))

        if primitive.kind == PrimitiveKind.ACQUIRE:
            location = self.locations[actor.location_id]
            self._require_known_resources(params["resources"])
            self._take(location.stocks, params["resources"], "环境存量")
        elif primitive.kind == PrimitiveKind.TRANSFORM:
            self._require_known_resources(params["inputs"])
            output_specs = self._proposed_output_specs(params)
            self._check_mass_balance(params["inputs"], params["outputs"], output_specs)
            self._take(actor.inventory, params["inputs"], "库存")
        elif primitive.kind == PrimitiveKind.CONSTRUCT:
            if params["structure_id"] in self.structures:
                raise FeasibilityError("结构标识已经存在")
            self._require_known_resources(params["materials"])
            self._take(actor.inventory, params["materials"], "库存")
        elif primitive.kind == PrimitiveKind.RESEARCH:
            proposal: KnowledgeProposal = params["knowledge"]
            missing = [item for item in proposal.prerequisites if item not in actor.knowledge]
            if missing:
                raise FeasibilityError(f"尚未掌握知识依赖 {missing}")
            self._require_known_resources(params["materials"])
            self._take(actor.inventory, params["materials"], "库存")
        elif primitive.kind == PrimitiveKind.COMMUNICATE:
            target = self.societies.get(params["target_society_id"])
            if not target or not target.is_alive:
                raise FeasibilityError("信息接收方不存在或已灭绝")
            missing = set(params["knowledge_ids"]) - actor.knowledge
            if missing:
                raise FeasibilityError(f"无法传播尚未掌握的知识 {sorted(missing)}")
            if not self._route(actor.location_id, target.location_id):
                raise FeasibilityError("双方之间没有可达的信息路径")
        elif primitive.kind == PrimitiveKind.ORGANIZE:
            if params["organization_id"] in actor.organizations:
                raise FeasibilityError("组织标识已经存在")
            if params["members"] > actor.population:
                raise FeasibilityError("组织成员超过存活人口")
            self._require_known_resources(params["materials"])
            self._take(actor.inventory, params["materials"], "库存")
        elif primitive.kind == PrimitiveKind.RELOCATE:
            if int(params["population"]) != actor.population:
                raise FeasibilityError("最小版本只支持整个社会共同迁移")
            route = self._route(actor.location_id, params["destination_id"])
            if not route:
                raise FeasibilityError("目的地不相邻或不可达")
            destination = self.locations.get(params["destination_id"])
            if not destination or destination.properties.get("habitability", 0) <= 0:
                raise FeasibilityError("目的地无法维持当前生命形态")
            self._take(actor.inventory, params["cargo"], "库存")
            transport = self._structure_effect(actor, "transport_capacity")
            travel_need = (
                route.distance
                * actor.population
                * 0.01
                * route.carrying_cost
                / (1.0 + transport)
            )
            self._consume_by_tag(actor, "nutrition", travel_need, "迁移补给不足")

    def _complete(
        self, actor: Society, primitive: Primitive, epoch: int
    ) -> Tuple[bool, str]:
        params = primitive.parameters
        if primitive.kind == PrimitiveKind.ACQUIRE:
            gained = dict(params["resources"])
            self._give(actor.inventory, gained)
            return True, f"取得资源 {self._format_quantities(gained)}"
        if primitive.kind == PrimitiveKind.TRANSFORM:
            for resource_id, spec in self._proposed_output_specs(params).items():
                self.resource_specs.setdefault(resource_id, spec)
            self._give(actor.inventory, params["outputs"])
            return True, f"完成资源转换并产出 {self._format_quantities(params['outputs'])}"
        if primitive.kind == PrimitiveKind.CONSTRUCT:
            structure = Structure(
                id=params["structure_id"],
                name=params["name"],
                owner_id=actor.id,
                location_id=actor.location_id,
                effects=dict(params["effects"]),
            )
            self.structures[structure.id] = structure
            return True, f"建成《{structure.name}》"
        if primitive.kind == PrimitiveKind.RELOCATE:
            actor.location_id = params["destination_id"]
            self._give(actor.inventory, params["cargo"])
            return True, f"社会整体迁至 {self.locations[actor.location_id].name}"
        if primitive.kind == PrimitiveKind.RESEARCH:
            return self._complete_research(actor, params["knowledge"], epoch)
        if primitive.kind == PrimitiveKind.COMMUNICATE:
            target = self.societies[params["target_society_id"]]
            before = len(target.knowledge)
            target.knowledge.update(params["knowledge_ids"])
            return True, f"向 {target.name} 传播 {len(target.knowledge) - before} 个知识节点"
        if primitive.kind == PrimitiveKind.ORGANIZE:
            organization = Organization(
                id=params["organization_id"],
                name=params["name"],
                purpose=params["purpose"],
                members=int(params["members"]),
                rules=list(params["rules"]),
                effects=dict(params["effects"]),
            )
            actor.organizations[organization.id] = organization
            return True, f"形成组织《{organization.name}》"
        raise AssertionError(f"unhandled primitive: {primitive.kind}")

    def _complete_research(
        self, actor: Society, proposal: KnowledgeProposal, epoch: int
    ) -> Tuple[bool, str]:
        observation_score = min(0.28, len(set(proposal.observations)) * 0.07)
        support = min(0.2, self._structure_effect(actor, "research_efficiency") * 0.1)
        coordination = min(0.12, self._organization_effect(actor, "coordination") * 0.06)
        probability = min(0.9, 0.38 + observation_score + support + coordination)
        if self.rng.random() > probability:
            return False, f"研究未通过可重复检验，成功阈值为 {probability:.2f}"

        key = "|".join(
            [proposal.name, proposal.description] + sorted(proposal.prerequisites)
        )
        knowledge_id = "knowledge-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        if knowledge_id not in self.knowledge_graph.nodes:
            self.knowledge_graph.add(
                KnowledgeNode(
                    id=knowledge_id,
                    name=proposal.name,
                    description=proposal.description,
                    discovered_by=actor.id,
                    discovered_epoch=epoch,
                    prerequisites=list(proposal.prerequisites),
                    observations=list(proposal.observations),
                    capabilities=list(proposal.capabilities),
                    risks=list(proposal.risks),
                )
            )
        actor.knowledge.add(knowledge_id)
        return True, f"知识图谱新增《{proposal.name}》[{knowledge_id}]"

    def _resolve_risks(self, actor: Society, primitive: Primitive) -> List[str]:
        risks = list(primitive.risks)
        required = set(primitive.parameters.get("required_capabilities", []))
        for knowledge_id in sorted(actor.knowledge):
            node = self.knowledge_graph.nodes.get(knowledge_id)
            if node and required.intersection(node.capabilities):
                risks.extend(node.risks)

        side_effects: List[str] = []
        protection = min(0.7, self._structure_effect(actor, "hazard_resistance") * 0.5)
        for risk in risks:
            if self.rng.random() >= risk.probability * (1.0 - protection):
                continue
            if risk.effect == "population_loss":
                loss = min(actor.population, max(1, int(risk.magnitude)))
                actor.population -= loss
                side_effects.append(f"{risk.name} 导致 {loss} 个个体死亡")
            elif risk.effect == "resource_loss":
                resource_id = risk.resource_id or self._largest_inventory(actor)
                loss = min(actor.inventory.get(resource_id, 0.0), risk.magnitude)
                actor.inventory[resource_id] = actor.inventory.get(resource_id, 0.0) - loss
                side_effects.append(f"{risk.name} 损失 {loss:.1f} {resource_id}")
            elif risk.effect == "environment_damage":
                location = self.locations[actor.location_id]
                loss = min(location.properties.get("habitability", 0.0), risk.magnitude)
                location.properties["habitability"] -= loss
                side_effects.append(f"{risk.name} 使栖息适宜度下降 {loss:.2f}")
            elif risk.effect == "organization_strain":
                loss = min(actor.traits.get("cohesion", 0.0), risk.magnitude)
                actor.traits["cohesion"] = actor.traits.get("cohesion", 0.0) - loss
                side_effects.append(f"{risk.name} 使凝聚度下降 {loss:.2f}")
        if actor.population <= 1:
            actor.is_alive = False
            side_effects.append(f"{actor.name} 已无可持续繁衍的种群")
        return side_effects

    def _environment_and_population(self) -> List[Resolution]:
        resolutions: List[Resolution] = []
        fission_candidates: List[Society] = []
        for actor in sorted(self.societies.values(), key=lambda item: item.id):
            if not actor.is_alive:
                continue
            location = self.locations[actor.location_id]
            distribution = self._organization_effect(actor, "distribution")
            habitability = location.properties.get("habitability", 0.5)
            thermal_variance = location.properties.get("thermal_variance", 0.0)
            crowding = location.properties.get("crowding_pressure", 0.0)
            carrying_capacity = max(1.0, location.properties.get("carrying_capacity", 100.0))
            stress = (
                max(0.0, 0.65 - habitability) * 0.7
                + max(0.0, thermal_variance) * 0.14
                + max(0.0, crowding) * actor.population / carrying_capacity * 0.08
            )
            efficiency = 1.0 + distribution * 0.08
            satisfactions = []
            for need_tag, rate in sorted(actor.metabolic_needs.items()):
                need = actor.population * rate * (1.0 + stress) / efficiency
                consumed = self._consume_available_by_tag(actor, need_tag, need)
                satisfactions.append(consumed / need if need else 1.0)
            satisfaction = min(satisfactions) if satisfactions else 1.0
            viability = min(1.0, habitability / 0.25)
            if satisfaction + 1e-9 < 1.0 or viability + 1e-9 < 1.0:
                shortage = 1.0 - min(satisfaction, viability)
                deaths = max(1, int(actor.population * shortage * 0.18))
                actor.population = max(0, actor.population - deaths)
                resolutions.append(
                    Resolution(
                        "upkeep",
                        actor.id,
                        "side_effect",
                        f"环境或代谢约束不足，种群减少 {deaths}",
                    )
                )
            else:
                capacity = location.properties.get("carrying_capacity", 100.0)
                capacity += self._structure_effect(actor, "carrying_capacity") * 20
                growth_chance = 0.55 * max(0.0, min(1.0, habitability))
                if actor.population < capacity and self.rng.random() < growth_chance:
                    actor.population += max(1, int(actor.population * 0.025))
            if actor.population <= 1:
                actor.is_alive = False
                resolutions.append(
                    Resolution("upkeep", actor.id, "extinct", f"{actor.name} 的种群灭绝")
                )
            elif actor.population >= 30 and actor.traits.get("cohesion", 0.5) < 0.18:
                fission_candidates.append(actor)
        for actor in fission_candidates:
            resolution = self._maybe_fission(actor)
            if resolution:
                resolutions.append(resolution)
        return resolutions

    def _maybe_fission(self, actor: Society) -> Optional[Resolution]:
        conflict = self._organization_effect(actor, "conflict_pressure")
        cohesion = actor.traits.get("cohesion", 0.5)
        probability = min(0.45, 0.08 + max(0.0, 0.18 - cohesion) + conflict * 0.08)
        if self.rng.random() >= probability:
            return None
        branch_index = 1
        while f"{actor.id}-branch-{branch_index}" in self.societies:
            branch_index += 1
        child_id = f"{actor.id}-branch-{branch_index}"
        child_population = max(8, int(actor.population * 0.32))
        original_population = actor.population
        actor.population -= child_population
        share = child_population / original_population
        child_inventory: Dict[str, float] = {}
        for resource_id, amount in list(actor.inventory.items()):
            transferred = round(amount * share, 6)
            actor.inventory[resource_id] = round(amount - transferred, 6)
            child_inventory[resource_id] = transferred
        actor.traits["cohesion"] = min(1.0, cohesion + 0.14)
        child_traits = dict(actor.traits)
        child_traits["cohesion"] = max(0.28, cohesion + 0.1)
        child = Society(
            id=child_id,
            name=f"{actor.name}第{branch_index}分支",
            species_profile=actor.species_profile,
            population=child_population,
            location_id=actor.location_id,
            inventory=child_inventory,
            traits=child_traits,
            metabolic_needs=dict(actor.metabolic_needs),
            knowledge=set(actor.knowledge),
        )
        self.societies[child.id] = child
        return Resolution(
            "social-fission",
            actor.id,
            "fission",
            f"凝聚度长期过低，{child_population} 个个体形成独立社会《{child.name}》",
        )

    def _labor_capacity(self, actor: Society) -> int:
        coordination = self._organization_effect(actor, "coordination")
        cohesion = actor.traits.get("cohesion", 0.5)
        return max(1, int(actor.population * (0.18 + cohesion * 0.08 + coordination * 0.04)))

    def _effective_labor(self, actor: Society, primitive: Primitive) -> int:
        if primitive.kind == PrimitiveKind.ACQUIRE:
            effect = self._structure_effect(actor, "acquire_efficiency")
        elif primitive.kind == PrimitiveKind.RELOCATE:
            effect = self._structure_effect(actor, "transport_capacity")
        else:
            effect = 0.0
        return max(1, int(round(primitive.labor / (1.0 + effect))))

    def _require_capabilities(self, actor: Society, required: Iterable[str]) -> None:
        available = self.knowledge_graph.available_capabilities(actor.knowledge)
        missing = set(required) - available
        if missing:
            raise FeasibilityError(f"缺少可验证能力 {sorted(missing)}")

    def _require_known_resources(self, quantities: Dict[str, float]) -> None:
        unknown = set(quantities) - set(self.resource_specs)
        if unknown:
            raise FeasibilityError(f"未知资源 {sorted(unknown)}")

    def _proposed_output_specs(self, params: Dict) -> Dict[str, ResourceSpec]:
        specs = params.get("output_specs", {})
        proposed: Dict[str, ResourceSpec] = {}
        for resource_id in params["outputs"]:
            if resource_id in self.resource_specs:
                continue
            raw = specs.get(resource_id)
            if not isinstance(raw, dict) or not raw.get("name") or not raw.get("tags"):
                raise FeasibilityError(f"新材料 {resource_id} 缺少可检验的资源描述")
            tags = raw["tags"]
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise FeasibilityError(f"新材料 {resource_id} 的 tags 无效")
            try:
                mass_per_unit = float(raw.get("mass_per_unit", 1.0))
            except (TypeError, ValueError) as exc:
                raise FeasibilityError(
                    f"新材料 {resource_id} 的单位质量无效"
                ) from exc
            if not math.isfinite(mass_per_unit) or mass_per_unit <= 0:
                raise FeasibilityError(f"新材料 {resource_id} 的单位质量无效")
            proposed[resource_id] = ResourceSpec(
                resource_id, raw["name"], set(tags), mass_per_unit
            )
        return proposed

    def _check_mass_balance(
        self,
        inputs: Dict[str, float],
        outputs: Dict[str, float],
        proposed_specs: Dict[str, ResourceSpec],
    ) -> None:
        input_mass = sum(
            amount * self.resource_specs[resource_id].mass_per_unit
            for resource_id, amount in inputs.items()
        )
        output_mass = sum(
            amount
            * (self.resource_specs.get(resource_id) or proposed_specs[resource_id]).mass_per_unit
            for resource_id, amount in outputs.items()
        )
        if output_mass > input_mass * 0.95 + 1e-9:
            raise FeasibilityError("转换结果违反质量与损耗约束")

    @staticmethod
    def _take(stock: Dict[str, float], quantities: Dict[str, float], label: str) -> None:
        missing = {
            resource_id: amount - stock.get(resource_id, 0.0)
            for resource_id, amount in quantities.items()
            if stock.get(resource_id, 0.0) + 1e-9 < amount
        }
        if missing:
            raise FeasibilityError(f"{label}不足 {missing}")
        for resource_id, amount in quantities.items():
            stock[resource_id] = round(stock.get(resource_id, 0.0) - amount, 6)

    @staticmethod
    def _give(stock: Dict[str, float], quantities: Dict[str, float]) -> None:
        for resource_id, amount in quantities.items():
            stock[resource_id] = round(stock.get(resource_id, 0.0) + amount, 6)

    def _consume_by_tag(
        self, actor: Society, tag: str, amount: float, error: str
    ) -> None:
        consumed = self._consume_available_by_tag(actor, tag, amount)
        if consumed + 1e-9 < amount:
            raise FeasibilityError(error)

    def _consume_available_by_tag(self, actor: Society, tag: str, amount: float) -> float:
        remaining = amount
        for resource_id in sorted(actor.inventory):
            spec = self.resource_specs.get(resource_id)
            if not spec or tag not in spec.tags:
                continue
            taken = min(actor.inventory[resource_id], remaining)
            actor.inventory[resource_id] = round(actor.inventory[resource_id] - taken, 6)
            remaining -= taken
            if remaining <= 1e-9:
                break
        return amount - remaining

    def _route(self, source_id: str, destination_id: str):
        if source_id == destination_id:
            return None
        source = self.locations.get(source_id)
        if not source:
            return None
        return next(
            (route for route in source.routes if route.destination_id == destination_id),
            None,
        )

    def _structure_effect(self, actor: Society, effect: str) -> float:
        return sum(
            structure.effects.get(effect, 0.0) * structure.durability
            for structure in self.structures.values()
            if structure.owner_id == actor.id and structure.location_id == actor.location_id
        )

    @staticmethod
    def _organization_effect(actor: Society, effect: str) -> float:
        return sum(item.effects.get(effect, 0.0) for item in actor.organizations.values())

    @staticmethod
    def _largest_inventory(actor: Society) -> str:
        if not actor.inventory:
            return "unknown"
        return max(sorted(actor.inventory), key=lambda key: actor.inventory[key])

    def _format_quantities(self, quantities: Dict[str, float]) -> str:
        return "、".join(
            f"{self.resource_specs[resource_id].name}={amount:.1f}"
            for resource_id, amount in quantities.items()
        )
