"""Compile open-ended plans into deterministic world primitives."""

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Set, Tuple

from models import (
    CompiledPlan,
    KnowledgeProposal,
    OpenPlan,
    PlanStep,
    Primitive,
    PrimitiveKind,
    RiskSpec,
)


class PlanCompileError(ValueError):
    pass


class PlanCompiler:
    """
    This compiler knows no historical actions or technologies. It only validates
    a small physical DSL and derives labor and time from the requested scale.
    """

    MAX_STEPS = 6

    def compile(self, plan: OpenPlan, epoch: int) -> CompiledPlan:
        if not plan.actor_id or not plan.title or not plan.objective:
            raise PlanCompileError("计划必须包含 actor_id、title 和 objective")
        if not plan.steps or len(plan.steps) > self.MAX_STEPS:
            raise PlanCompileError(f"计划必须包含 1 至 {self.MAX_STEPS} 个步骤")

        primitives = [self._compile_step(step) for step in plan.steps]
        canonical = json.dumps(
            {
                "epoch": epoch,
                "actor": plan.actor_id,
                "title": plan.title,
                "objective": plan.objective,
                "steps": [
                    {"operation": step.operation, "parameters": step.parameters}
                    for step in plan.steps
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=self._json_default,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return CompiledPlan(f"plan-{epoch}-{plan.actor_id}-{digest}", plan, primitives)

    def _compile_step(self, step: PlanStep) -> Primitive:
        try:
            kind = PrimitiveKind(step.operation.lower())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in PrimitiveKind)
            raise PlanCompileError(
                f"不支持 primitive '{step.operation}'；可用底层操作为 {allowed}"
            ) from exc

        params = dict(step.parameters)
        validators = {
            PrimitiveKind.ACQUIRE: self._compile_acquire,
            PrimitiveKind.TRANSFORM: self._compile_transform,
            PrimitiveKind.CONSTRUCT: self._compile_construct,
            PrimitiveKind.RELOCATE: self._compile_relocate,
            PrimitiveKind.RESEARCH: self._compile_research,
            PrimitiveKind.COMMUNICATE: self._compile_communicate,
            PrimitiveKind.ORGANIZE: self._compile_organize,
        }
        labor, duration, risks = validators[kind](params)
        return Primitive(kind, params, labor, duration, risks)

    def _compile_acquire(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        quantities = self._quantities(params, "resources")
        scale = sum(quantities.values())
        return max(1, math.ceil(scale / 8)), max(1, math.ceil(scale / 30)), []

    def _compile_transform(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        inputs = self._quantities(params, "inputs")
        outputs = self._quantities(params, "outputs")
        input_mass = sum(inputs.values())
        params["required_capabilities"] = self._strings(
            params.get("required_capabilities", []), "required_capabilities"
        )
        risks = self._risks(params.pop("risks", []))
        return max(1, math.ceil(input_mass / 6)), max(1, math.ceil(input_mass / 24)), risks

    def _compile_construct(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        materials = self._quantities(params, "materials")
        for field in ("name", "structure_id"):
            self._required_string(params, field)
        effects = params.get("effects", {})
        self._bounded_effects(
            effects,
            {
                "acquire_efficiency",
                "transport_capacity",
                "hazard_resistance",
                "research_efficiency",
                "carrying_capacity",
            },
        )
        params["effects"] = effects
        params["required_capabilities"] = self._strings(
            params.get("required_capabilities", []), "required_capabilities"
        )
        risks = self._risks(params.pop("risks", []))
        scale = sum(materials.values())
        complexity = 1 + len(effects)
        return max(2, math.ceil(scale / 5)), max(1, math.ceil(scale * complexity / 25)), risks

    def _compile_relocate(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        self._required_string(params, "destination_id")
        population = self._positive_number(params, "population")
        cargo = self._quantities(params, "cargo", required=False)
        scale = population + sum(cargo.values()) / 4
        return max(1, math.ceil(scale / 6)), max(1, math.ceil(scale / 20)), []

    def _compile_research(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        effort = self._positive_number(params, "effort")
        raw = params.get("knowledge")
        if not isinstance(raw, dict):
            raise PlanCompileError("research 必须包含知识提案")
        for field in ("name", "description"):
            self._required_string(raw, field)
        proposal = KnowledgeProposal(
            name=raw["name"],
            description=raw["description"],
            prerequisites=self._strings(raw.get("prerequisites", []), "prerequisites"),
            observations=self._strings(raw.get("observations", []), "observations"),
            capabilities=self._strings(raw.get("capabilities", []), "capabilities"),
            risks=self._risks(raw.get("risks", [])),
        )
        if not proposal.observations:
            raise PlanCompileError("research 至少需要一项可检验观察")
        params["knowledge"] = proposal
        params["materials"] = self._quantities(params, "materials", required=False)
        return max(1, math.ceil(effort / 4)), max(1, math.ceil(effort / 12)), []

    def _compile_communicate(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        self._required_string(params, "target_society_id")
        params["knowledge_ids"] = self._strings(
            params.get("knowledge_ids", []), "knowledge_ids"
        )
        if not params["knowledge_ids"]:
            raise PlanCompileError("communicate 必须包含 knowledge_ids")
        return max(1, len(params["knowledge_ids"])), 1, []

    def _compile_organize(
        self, params: Dict[str, Any]
    ) -> Tuple[int, int, List[RiskSpec]]:
        for field in ("name", "organization_id", "purpose"):
            self._required_string(params, field)
        members = self._positive_number(params, "members")
        params["rules"] = self._strings(params.get("rules", []), "rules")
        if not params["rules"]:
            raise PlanCompileError("organization 必须包含明确规则")
        effects = params.get("effects", {})
        self._bounded_effects(
            effects,
            {"coordination", "knowledge_retention", "distribution", "conflict_pressure"},
        )
        params["effects"] = effects
        params["materials"] = self._quantities(params, "materials", required=False)
        risks = self._risks(params.pop("risks", []))
        return max(1, math.ceil(members / 12)), max(1, math.ceil(members / 30)), risks

    def _quantities(
        self, params: Dict[str, Any], field: str, required: bool = True
    ) -> Dict[str, float]:
        value = params.get(field, {})
        if not isinstance(value, dict) or (required and not value):
            raise PlanCompileError(f"{field} 必须是非空数量映射")
        normalized: Dict[str, float] = {}
        for resource_id, quantity in value.items():
            if not isinstance(resource_id, str) or not resource_id:
                raise PlanCompileError(f"{field} 包含无效资源标识")
            normalized[resource_id] = self._number(quantity, f"{field}.{resource_id}")
        params[field] = normalized
        return normalized

    def _positive_number(self, params: Dict[str, Any], field: str) -> float:
        value = self._number(params.get(field), field)
        params[field] = value
        return value

    @staticmethod
    def _number(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PlanCompileError(f"{field} 必须是数值")
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise PlanCompileError(f"{field} 必须是有限正数")
        return value

    @staticmethod
    def _required_string(params: Dict[str, Any], field: str) -> None:
        if not isinstance(params.get(field), str) or not params[field].strip():
            raise PlanCompileError(f"{field} 必须是非空字符串")

    @staticmethod
    def _strings(value: Any, field: str) -> List[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise PlanCompileError(f"{field} 必须是非空字符串列表")
        return list(value)

    def _risks(self, raw_risks: Iterable[Any]) -> List[RiskSpec]:
        if not isinstance(raw_risks, list):
            raise PlanCompileError("risks 必须是列表")
        risks: List[RiskSpec] = []
        allowed_effects = {
            "population_loss",
            "resource_loss",
            "environment_damage",
            "organization_strain",
        }
        for raw in raw_risks:
            if not isinstance(raw, dict):
                raise PlanCompileError("每项 risk 必须是对象")
            self._required_string(raw, "name")
            self._required_string(raw, "effect")
            if raw["effect"] not in allowed_effects:
                raise PlanCompileError(f"不支持的风险效果：{raw['effect']}")
            probability = self._number(raw.get("probability"), "risk.probability")
            if probability > 0.75:
                raise PlanCompileError("风险概率不能超过 0.75")
            magnitude = self._number(raw.get("magnitude"), "risk.magnitude")
            resource_id = raw.get("resource_id")
            if resource_id is not None and not isinstance(resource_id, str):
                raise PlanCompileError("risk.resource_id 必须是字符串")
            risks.append(
                RiskSpec(raw["name"], probability, raw["effect"], magnitude, resource_id)
            )
        return risks

    def _bounded_effects(self, effects: Any, allowed: Set[str]) -> None:
        if not isinstance(effects, dict):
            raise PlanCompileError("effects 必须是对象")
        unknown = set(effects) - allowed
        if unknown:
            raise PlanCompileError(f"不支持的效果：{sorted(unknown)}")
        for name, value in effects.items():
            numeric = self._number(value, f"effects.{name}")
            if numeric > 2.0:
                raise PlanCompileError(f"effects.{name} 超过安全边界")
            effects[name] = numeric

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (KnowledgeProposal, RiskSpec)):
            return value.__dict__
        raise TypeError(f"cannot serialize {type(value)}")
