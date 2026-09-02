"""LLM-first open plan, event and chronicle generation with an offline fallback."""

import json
import random
import shutil
import subprocess
from typing import Dict, List, Optional, Sequence

from models import (
    KnowledgeGraph,
    Location,
    OpenEvent,
    OpenPlan,
    PlanStep,
    ResourceSpec,
    Society,
    Structure,
    public_dict,
)


class LLMBackend:
    """Propose meanings and causal hypotheses, without mutating world state."""

    AGY_MODEL = "gemini-3.7-flash-high"

    TAG_NAMES = {
        "nutrition": "可代谢性",
        "organic": "含碳结构",
        "structural": "承载特性",
        "mineral": "矿物结构",
        "moldable": "可塑性",
        "fluid": "流动性",
        "hydration": "溶剂亲和性",
        "energy": "能量释放",
        "processed": "加工稳定性",
        "transport": "运输用途",
        "portable": "便于携带",
    }
    EFFECT_NAMES = {
        "acquire_efficiency": "资源取得效率",
        "transport_capacity": "空间输运能力",
        "hazard_resistance": "扰动承受能力",
        "research_efficiency": "重复试验效率",
        "carrying_capacity": "局部承载能力",
    }
    PROPERTY_NAMES = {
        "habitability": "栖息适宜度",
        "carrying_capacity": "环境承载量",
        "crowding_pressure": "拥挤压力",
        "fluid_activity": "流体活跃度",
        "thermal_variance": "热状态波动",
        "elevation": "相对势位",
    }

    def __init__(self, mode: str = "cli"):
        if mode not in {"heuristic", "cli"}:
            raise ValueError("mode must be 'heuristic' or 'cli'")
        self.mode = mode
        self.cli_tool = self._detect_cli_tool() if mode == "cli" else None
        self.cli_model = self.AGY_MODEL if self.cli_tool == "agy" else None
        self.stats = {
            "llm_plan": 0,
            "heuristic_plan": 0,
            "llm_event": 0,
            "heuristic_event": 0,
            "llm_chronicle": 0,
            "fallback_chronicle": 0,
        }

    @staticmethod
    def _detect_cli_tool() -> Optional[str]:
        for tool in ("agy", "codex", "claude"):
            if shutil.which(tool):
                return tool
        return None

    def propose_plan(
        self,
        actor: Society,
        location: Location,
        resource_specs: Dict[str, ResourceSpec],
        societies: Dict[str, Society],
        knowledge_graph: KnowledgeGraph,
        structures: Dict[str, Structure],
        epoch: int,
        recent_history: Sequence[str],
        rng: random.Random,
        scenario_context: str,
        calendar_label: str,
        span_years: int,
    ) -> OpenPlan:
        if self.mode == "cli" and self.cli_tool:
            prompt = self._plan_prompt(
                actor,
                location,
                resource_specs,
                societies,
                knowledge_graph,
                structures,
                epoch,
                recent_history,
                scenario_context,
                calendar_label,
                span_years,
            )
            parsed = self._parse_plan(self._query_cli(prompt), actor.id)
            if parsed:
                self.stats["llm_plan"] += 1
                return parsed
        self.stats["heuristic_plan"] += 1
        return self._heuristic_plan(
            actor,
            location,
            resource_specs,
            societies,
            knowledge_graph,
            epoch,
            rng,
        )

    def propose_event(
        self,
        locations: Dict[str, Location],
        resource_specs: Dict[str, ResourceSpec],
        epoch: int,
        recent_history: Sequence[str],
        rng: random.Random,
        scenario_context: str,
        calendar_label: str,
        span_years: int,
    ) -> Optional[OpenEvent]:
        if rng.random() > 0.72:
            return None
        if self.mode == "cli" and self.cli_tool:
            prompt = self._event_prompt(
                locations,
                resource_specs,
                epoch,
                recent_history,
                scenario_context,
                calendar_label,
                span_years,
            )
            parsed = self._parse_event(self._query_cli(prompt))
            if parsed:
                self.stats["llm_event"] += 1
                return parsed
        self.stats["heuristic_event"] += 1
        return self._heuristic_event(locations, resource_specs, rng)

    def chronicle(
        self,
        epoch: int,
        events: List[OpenEvent],
        plans: List[OpenPlan],
        resolution_lines: List[str],
        societies: Dict[str, Society],
        scenario_context: str,
        calendar_label: str,
        span_years: int,
    ) -> str:
        if self.mode == "cli" and self.cli_tool:
            prompt = self._chronicle_prompt(
                epoch,
                events,
                plans,
                resolution_lines,
                societies,
                scenario_context,
                calendar_label,
                span_years,
            )
            text = self._query_cli(prompt)
            if text:
                self.stats["llm_chronicle"] += 1
                return self._clean_prose(text)
        self.stats["fallback_chronicle"] += 1
        return self._fallback_chronicle(
            epoch, events, plans, resolution_lines, societies, calendar_label
        )

    @staticmethod
    def _fallback_chronicle(
        epoch: int,
        events: List[OpenEvent],
        plans: List[OpenPlan],
        resolution_lines: List[str],
        societies: Dict[str, Society],
        calendar_label: str,
    ) -> str:
        lines = [f"【{calendar_label}】"]
        for event in events:
            lines.append(f"本纪，{event.name}。{event.description}")
        intentions = []
        for plan in plans:
            actor = societies.get(plan.actor_id)
            actor_name = actor.name if actor else plan.actor_id
            intentions.append(
                f"{actor_name}提出《{plan.title}》，意在{plan.objective}"
            )
        if intentions:
            lines.append("与此同时，" + "；".join(intentions) + "。")
        if resolution_lines:
            lines.append("其后，" + "".join(resolution_lines))
        alive = [item.name for item in societies.values() if item.is_alive]
        if alive:
            lines.append(
                f"纪末，{'、'.join(alive)}仍在延续。此后的道路尚未写定。"
            )
        else:
            lines.append("纪末已不存在可持续延续的社会，历史在此终止。")
        return "\n\n".join(lines)

    def _heuristic_plan(
        self,
        actor: Society,
        location: Location,
        specs: Dict[str, ResourceSpec],
        societies: Dict[str, Society],
        graph: KnowledgeGraph,
        epoch: int,
        rng: random.Random,
    ) -> OpenPlan:
        need_pressure = []
        for need_tag, rate in actor.metabolic_needs.items():
            matching = self._resources_with_tag(specs, need_tag)
            stored = sum(actor.inventory.get(item, 0.0) for item in matching)
            epochs_available = stored / max(0.001, actor.population * rate)
            need_pressure.append((epochs_available, need_tag, rate, matching, stored))
        if need_pressure:
            epochs_available, need_tag, rate, matching, stored = min(need_pressure)
            available = [item for item in matching if location.stocks.get(item, 0.0) >= 8]
        else:
            epochs_available, need_tag, rate, matching, stored, available = (10.0, "", 0.0, [], 0.0, [])
        if epochs_available < 3.0:
            if available:
                resource_id = max(available, key=lambda item: location.stocks[item])
                target = actor.population * rate * 5.0
                amount = min(30.0, max(8.0, target - stored), location.stocks[resource_id])
                need_name = self.TAG_NAMES.get(need_tag, need_tag)
                return OpenPlan(
                    actor.id,
                    f"集中取得{specs[resource_id].name}",
                    f"补足近期{need_name}缺口，并观察局部存量变化",
                    [PlanStep("acquire", {"resources": {resource_id: amount}}, "短缺已经威胁种群延续")],
                    ["当前采集规模低于可观测局部存量"],
                )

        candidates = ["organize"]
        if any(amount > 5 for amount in location.stocks.values()):
            candidates.append("research")
        if any(amount >= 8 for amount in location.stocks.values()):
            candidates.append("acquire")
        if actor.knowledge:
            candidates.extend(["construct", "transform", "communicate"])
        better_routes = [
            route
            for route in location.routes
            if self._location_score(route.destination_id, societies, actor, location) > 0
        ]
        if better_routes:
            candidates.append("relocate")

        preference = rng.choice(candidates)
        if preference == "research":
            plan = self._research_plan(actor, location, specs, graph, rng)
            if plan:
                return plan
        if preference == "organize":
            return self._organization_plan(actor, epoch, rng)
        if preference == "construct":
            plan = self._construction_plan(actor, specs, graph, epoch, rng)
            if plan:
                return plan
        if preference == "transform":
            plan = self._transformation_plan(actor, specs, graph, rng)
            if plan:
                return plan
        if preference == "communicate":
            plan = self._communication_plan(actor, societies, location, rng)
            if plan:
                return plan
        if preference == "relocate" and better_routes:
            destination = rng.choice(better_routes).destination_id
            return OpenPlan(
                actor.id,
                "全体移居至相邻空置栖息地",
                "离开当前压力较高的栖息地，重新组合可利用资源",
                [PlanStep("relocate", {"destination_id": destination, "population": actor.population, "cargo": {}}, "相邻地点呈现更高的可居住潜力")],
            )
        plan = self._acquisition_plan(actor, location, specs, rng)
        return plan or self._organization_plan(actor, epoch, rng)

    def _research_plan(
        self,
        actor: Society,
        location: Location,
        specs: Dict[str, ResourceSpec],
        graph: KnowledgeGraph,
        rng: random.Random,
    ) -> Optional[OpenPlan]:
        observable = [resource_id for resource_id, amount in location.stocks.items() if amount > 5 and resource_id in specs]
        if not observable:
            return None
        resource_id = rng.choice(observable)
        spec = specs[resource_id]
        method = rng.choice(["反复试用", "分组比较", "长期观察", "冷热试验", "多人记录"])
        dominant_tag = sorted(spec.tags)[rng.randrange(len(spec.tags))]
        dominant_label = self.TAG_NAMES.get(dominant_tag, dominant_tag)
        capability = f"操控:{dominant_tag}:{resource_id}"
        prerequisite = []
        if actor.knowledge and rng.random() < 0.45:
            prerequisite = [rng.choice(sorted(actor.knowledge))]
        risk_effect = rng.choice(["population_loss", "resource_loss", "environment_damage", "organization_strain"])
        risk = {
            "name": f"{spec.name}{method}失稳",
            "probability": round(rng.uniform(0.08, 0.28), 3),
            "effect": risk_effect,
            "magnitude": round(rng.uniform(1.0, 4.0), 2),
        }
        if risk_effect == "resource_loss":
            risk["resource_id"] = resource_id
        materials = {resource_id: 3.0} if actor.inventory.get(resource_id, 0.0) >= 3 else {}
        title = f"用{method}研究{spec.name}的{dominant_label}"
        return OpenPlan(
            actor.id,
            title,
            f"弄清{spec.name}在实际使用中的规律",
            [
                PlanStep(
                    "research",
                    {
                        "effort": 12,
                        "materials": materials,
                        "knowledge": {
                            "name": title,
                            "description": f"比较{spec.name}在{method}中的变化，并整理成可以重复使用的办法",
                            "prerequisites": prerequisite,
                            "observations": [f"记录{resource_id}处理前后的质量", f"重复{method}并比较响应方差"],
                            "capabilities": [capability],
                            "risks": [risk],
                        },
                    },
                    "环境中该对象足够丰富，可以进行有损试验",
                )
            ],
        )

    def _construction_plan(
        self,
        actor: Society,
        specs: Dict[str, ResourceSpec],
        graph: KnowledgeGraph,
        epoch: int,
        rng: random.Random,
    ) -> Optional[OpenPlan]:
        usable = [item for item, amount in actor.inventory.items() if amount >= 10 and item in specs]
        if not usable:
            return None
        resource_id = rng.choice(usable)
        capabilities = graph.available_capabilities(actor.knowledge)
        matching = [item for item in capabilities if item.endswith(f":{resource_id}")]
        if not matching:
            return None
        effect = rng.choice(["acquire_efficiency", "transport_capacity", "hazard_resistance", "research_efficiency", "carrying_capacity"])
        effect_name = self.EFFECT_NAMES[effect]
        form = rng.choice(["网格", "层叠体", "导流阵列", "悬挂架", "缓冲围护"])
        name = f"{specs[resource_id].name}{form}"
        return OpenPlan(
            actor.id,
            f"建造{name}",
            f"通过局部结构改变{effect_name}，并承担材料失效风险",
            [
                PlanStep(
                    "construct",
                    {
                        "structure_id": f"structure-{actor.id}-{epoch}",
                        "name": name,
                        "materials": {resource_id: 10.0},
                        "effects": {effect: round(rng.uniform(0.12, 0.35), 3)},
                        "required_capabilities": [rng.choice(matching)],
                        "risks": [{"name": f"{name}局部坍解", "probability": 0.12, "effect": "population_loss", "magnitude": 2.0}],
                    },
                    "已有知识允许尝试塑造该材料",
                )
            ],
        )

    def _transformation_plan(
        self,
        actor: Society,
        specs: Dict[str, ResourceSpec],
        graph: KnowledgeGraph,
        rng: random.Random,
    ) -> Optional[OpenPlan]:
        capabilities = graph.available_capabilities(actor.knowledge)
        options = [
            resource_id
            for resource_id, amount in actor.inventory.items()
            if amount >= 10 and resource_id in specs and any(item.endswith(f":{resource_id}") for item in capabilities)
        ]
        if not options:
            return None
        resource_id = rng.choice(options)
        required = rng.choice([item for item in capabilities if item.endswith(f":{resource_id}")])
        knowledge_id = next(item for item in sorted(actor.knowledge) if required in graph.nodes[item].capabilities)
        output_id = f"derived-{resource_id}-{knowledge_id[-5:]}"
        output_name = f"重组{specs[resource_id].name}"
        return OpenPlan(
            actor.id,
            f"制备{output_name}",
            "检验新知识能否稳定地产生不同材料，而不是直接获得抽象科技加成",
            [
                PlanStep(
                    "transform",
                    {
                        "inputs": {resource_id: 10.0},
                        "outputs": {output_id: 8.5},
                        "output_specs": {output_id: {"name": output_name, "tags": sorted(specs[resource_id].tags | {"processed"}), "mass_per_unit": specs[resource_id].mass_per_unit}},
                        "required_capabilities": [required],
                    },
                    "先前研究提供了可重复的操作条件",
                )
            ],
        )

    @staticmethod
    def _organization_plan(actor: Society, epoch: int, rng: random.Random) -> OpenPlan:
        human_history = "人类国家" in actor.species_profile
        if human_history:
            purpose = rng.choice(["粮仓管理", "灾民救济", "道路维护", "官吏监察", "边境运输"])
            rule = rng.choice(["轮值办理", "公开账目", "分区负责", "按户配给", "两级复核"])
        else:
            purpose = rng.choice(["轮换照料", "争议调停", "观测归档", "资源配给", "远行互助"])
            rule = rng.choice(["定期轮替", "公开记账", "随机抽签", "按需领取", "双重见证"])
        effect = rng.choice(["coordination", "knowledge_retention", "distribution"])
        name = f"{purpose}署" if human_history else f"{purpose}{rule}会"
        return OpenPlan(
            actor.id,
            f"建立{name}",
            f"以可修改的规则处理{purpose}问题",
            [
                PlanStep(
                    "organize",
                    {
                        "organization_id": f"organization-{actor.id}-{epoch}",
                        "name": name,
                        "purpose": purpose,
                        "members": min(actor.population, rng.randint(12, 28)),
                        "rules": [rule, "每三年复议一次规则" if human_history else "每三纪复议一次规则"],
                        "effects": {effect: round(rng.uniform(0.1, 0.3), 3)},
                        "materials": {},
                        "risks": [{"name": f"{purpose}权责固化", "probability": 0.16, "effect": "organization_strain", "magnitude": 0.08}],
                    },
                    "单个家庭已无法稳定处理该问题",
                )
            ],
        )

    def _communication_plan(
        self,
        actor: Society,
        societies: Dict[str, Society],
        location: Location,
        rng: random.Random,
    ) -> Optional[OpenPlan]:
        reachable = {route.destination_id for route in location.routes}
        targets = [
            item
            for item in societies.values()
            if item.id != actor.id and item.is_alive and item.location_id in reachable and actor.knowledge - item.knowledge
        ]
        if not targets:
            return None
        target = rng.choice(targets)
        knowledge_id = rng.choice(sorted(actor.knowledge - target.knowledge))
        return OpenPlan(
            actor.id,
            f"向{target.name}解释一项可复现实验",
            "让知识沿社会关系传播，并观察接收方是否产生不同用途",
            [PlanStep("communicate", {"target_society_id": target.id, "knowledge_ids": [knowledge_id]}, "双方之间存在直接可达路径")],
        )

    @staticmethod
    def _acquisition_plan(
        actor: Society,
        location: Location,
        specs: Dict[str, ResourceSpec],
        rng: random.Random,
    ) -> Optional[OpenPlan]:
        options = [item for item, amount in location.stocks.items() if amount >= 8]
        if not options:
            return None
        resource_id = rng.choice(options)
        amount = min(location.stocks[resource_id], rng.uniform(8, 20))
        human_history = "人类国家" in actor.species_profile
        return OpenPlan(
            actor.id,
            f"调集{specs[resource_id].name}" if human_history else f"试采{specs[resource_id].name}",
            "补充官府仓储，同时给地方保留余量" if human_history else "扩大可操作材料范围，同时保留局部存量余量",
            [PlanStep("acquire", {"resources": {resource_id: round(amount, 2)}})],
        )

    def _heuristic_event(
        self,
        locations: Dict[str, Location],
        specs: Dict[str, ResourceSpec],
        rng: random.Random,
    ) -> OpenEvent:
        if "grain" in specs and "water" in specs:
            location = rng.choice(list(locations.values()))
            water_stock = location.stocks.get("water", 0.0)
            water_capacity = location.capacities.get("water", water_stock)
            if rng.random() < 0.5 and water_capacity - water_stock >= 2.0:
                amount = round(min(water_capacity - water_stock, rng.uniform(3.0, 8.0)), 3)
                return OpenEvent(
                    f"{location.name}出现持续降雨",
                    "连日降雨补充了河渠和井泉，也增加了低地积水的风险。",
                    ["暖湿气流持续进入当地", "降水多于地表蒸发和排水"],
                    rng.randint(1, 2),
                    {location.id: {"water": amount}},
                    {},
                    {"water": amount},
                    {},
                )
            amount = round(min(water_stock * 0.06, rng.uniform(3.0, 7.0)), 3)
            return OpenEvent(
                f"{location.name}遭遇少雨天气",
                "降雨减少，河渠和井泉的水量随蒸发而下降。",
                ["干燥气流持续影响当地", "蒸发量超过降水补充"],
                rng.randint(1, 2),
                {location.id: {"water": -amount}},
                {},
                {},
                {"water": amount},
            )
        bounded_resources = [
            resource_id
            for resource_id in specs
            if any(resource_id in location.capacities for location in locations.values())
        ]
        fill_ratios = {
            resource_id: sum(location.stocks.get(resource_id, 0.0) for location in locations.values())
            / max(1.0, sum(location.capacities.get(resource_id, 0.0) for location in locations.values()))
            for resource_id in bounded_resources
        }
        scarce_resource = min(fill_ratios, key=fill_ratios.get)
        if fill_ratios[scarce_resource] < 0.45 and rng.random() < 0.88:
            candidate_locations = [
                item for item in locations.values() if scarce_resource in item.capacities
            ]
            location = max(
                candidate_locations,
                key=lambda item: item.capacities[scarce_resource]
                - item.stocks.get(scarce_resource, 0.0),
            )
            gap = location.capacities[scarce_resource] - location.stocks.get(scarce_resource, 0.0)
            amount = round(min(gap, rng.uniform(20.0, 45.0)), 3)
            spec = specs[scarce_resource]
            return OpenEvent(
                f"边界外循环向{location.name}补入{spec.name}",
                "持续观测到的低存量梯度使模型边界外物质进入当前空间。",
                [f"全域相对存量降至 {fill_ratios[scarce_resource]:.2f}", "边界两侧存在浓度差"],
                rng.randint(1, 3),
                {location.id: {scarce_resource: amount}},
                {},
                {scarce_resource: amount},
                {},
            )
        location = rng.choice(list(locations.values()))
        resource_id = rng.choice(sorted(location.stocks))
        spec = specs[resource_id]
        mode = rng.choice(["redistribute", "inflow", "outflow", "property"])
        if mode == "redistribute" and location.routes:
            route = rng.choice(location.routes)
            destination = locations[route.destination_id]
            amount = round(min(location.stocks[resource_id] * 0.08, 10.0), 3)
            return OpenEvent(
                f"{spec.name}沿{location.name}与{destination.name}之间重新分布",
                "局部势差使一种既有物质跨越相邻空间，没有创造或消灭质量。",
                [f"两地距离为 {route.distance:.1f}", "连续介质沿局部势差移动"],
                rng.randint(1, 3),
                {location.id: {resource_id: -amount}, destination.id: {resource_id: amount}},
                {},
            )
        if mode == "inflow":
            capacity = location.capacities[resource_id]
            amount = round(min(max(0.0, capacity - location.stocks[resource_id]), 8.0), 3)
            if amount > 0:
                return OpenEvent(
                    f"外部循环向{location.name}输入{spec.name}",
                    "模拟边界外储层经局部循环进入当前空间。",
                    ["开放世界边界存在可计量输入", f"输入量为 {amount:.1f}"],
                    rng.randint(1, 3),
                    {location.id: {resource_id: amount}},
                    {},
                    {resource_id: amount},
                    {},
                )
        if mode == "outflow" and location.stocks[resource_id] > 4:
            amount = round(min(location.stocks[resource_id] * 0.06, 7.0), 3)
            return OpenEvent(
                f"{location.name}的{spec.name}逸出模拟边界",
                "局部输运把物质带到当前模型尚未展开的空间。",
                ["边界并非封闭", f"逸出量为 {amount:.1f}"],
                rng.randint(1, 3),
                {location.id: {resource_id: -amount}},
                {},
                {},
                {resource_id: amount},
            )
        property_name = rng.choice(sorted(location.properties))
        property_label = self.PROPERTY_NAMES.get(property_name, property_name)
        current = location.properties[property_name]
        delta = round(rng.uniform(-0.08, 0.08) * max(abs(current), 0.2), 4)
        if property_name == "habitability":
            delta = max(-current, min(1.0 - current, delta))
        return OpenEvent(
            f"{location.name}的{property_label}缓慢漂移",
            "多项未建模微观过程叠加为可测量的宏观变化。",
            ["连续观测出现同方向偏移", "变化幅度处于局部物理上限内"],
            rng.randint(1, 4),
            {},
            {location.id: {property_name: delta}},
        )

    @staticmethod
    def _resources_with_tag(specs: Dict[str, ResourceSpec], tag: str) -> List[str]:
        return sorted(key for key, spec in specs.items() if tag in spec.tags)

    @staticmethod
    def _location_score(
        destination_id: str,
        societies: Dict[str, Society],
        actor: Society,
        current: Location,
    ) -> float:
        occupied = sum(item.population for item in societies.values() if item.is_alive and item.location_id == destination_id)
        return current.properties.get("crowding_pressure", 0.0) - occupied * 0.01

    def _query_cli(self, prompt: str) -> Optional[str]:
        if not self.cli_tool:
            return None
        commands = {
            "claude": ["claude", "-p", prompt],
            "codex": ["codex", "exec", prompt],
            "agy": [
                "agy",
                "--model",
                self.AGY_MODEL,
                "--disable-slash-commands",
                "-p",
                prompt,
            ],
        }
        try:
            result = subprocess.run(
                commands[self.cli_tool], capture_output=True, text=True, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    @staticmethod
    def _parse_plan(raw: Optional[str], actor_id: str) -> Optional[OpenPlan]:
        if not raw:
            return None
        try:
            payload = LLMBackend._parse_json_object(raw)
            return OpenPlan(
                actor_id,
                payload["title"],
                payload["objective"],
                [PlanStep(item["operation"], item["parameters"], item.get("rationale", "")) for item in payload["steps"]],
                payload.get("assumptions", []),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _parse_event(raw: Optional[str]) -> Optional[OpenEvent]:
        if not raw:
            return None
        try:
            return OpenEvent(**LLMBackend._parse_json_object(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _parse_json_object(raw: str) -> Dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            payload = json.loads(text[start : end + 1])
        if not isinstance(payload, dict):
            raise TypeError("LLM output must be a JSON object")
        return payload

    @staticmethod
    def _clean_prose(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()[1:-1]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _plan_prompt(
        actor: Society,
        location: Location,
        resource_specs: Dict[str, ResourceSpec],
        societies: Dict[str, Society],
        graph: KnowledgeGraph,
        structures: Dict[str, Structure],
        epoch: int,
        recent_history: Sequence[str],
        scenario_context: str,
        calendar_label: str,
        span_years: int,
    ) -> str:
        state = {
            "epoch": epoch,
            "calendar": calendar_label,
            "span_years": span_years,
            "scenario": scenario_context,
            "actor": public_dict(actor),
            "location": public_dict(location),
            "resources": {key: public_dict(value) for key, value in resource_specs.items()},
            "known_nodes": {key: public_dict(value) for key, value in graph.nodes.items()},
            "other_societies": [public_dict(value) for value in societies.values()],
            "structures": [public_dict(value) for value in structures.values()],
            "recent_history": list(recent_history),
        }
        return (
            "你是开放式人工历史模拟中一个独立的社会 Agent，只代表 actor，不代表其他社会。"
            "背景资料只规定开局，不规定未来；不得因为熟悉真实历史而照抄或强行纠正为真实结果。"
            "把 actor.traits 视为长期性格，把其地点、库存、知识和组织视为自身处境。"
            "你的选择应延续自身经历与立场，不要为了与其他社会显得不同而随机表演，也不要替其他社会统筹。"
            f"本轮覆盖{calendar_label}，共{span_years}年。提出这段时期最重要的一项长期计划，"
            "不要把跨度较长误解为计划可以无视物资、工期或知识前置条件。"
            "根据状态提出一个中文计划。标题、目标与理由须使用这个时代的人能够理解的常用词，"
            "在人类历史场景中写粮食、水利、道路、城防、官署、百姓、使者等，不写抽象科幻术语。"
            "不要套用现实科技树，也不要宣称结果已经成功。步骤使用物理 DSL："
            "acquire, transform, construct, relocate, research, communicate, organize。"
            "它们不是历史行动菜单。可以创造任意目标，但必须组合为一至六个可执行步骤。"
            "只输出 JSON，字段为 title, objective, assumptions, steps；每个 step 含 operation, parameters, rationale。"
            "parameters 必须严格服从以下结构之一："
            "acquire={resources:{resource_id:正数}}；"
            "transform={inputs:{resource_id:正数},outputs:{resource_id:正数},required_capabilities:[字符串],risks:[风险]}；"
            "construct={structure_id:字符串,name:字符串,materials:{resource_id:正数},effects:{允许效果:0至2},required_capabilities:[字符串],risks:[风险]}，"
            "允许效果仅为 acquire_efficiency, transport_capacity, hazard_resistance, research_efficiency, carrying_capacity；"
            "relocate={destination_id:字符串,population:正数,cargo:{resource_id:正数}}；"
            "research={effort:正数,materials:{resource_id:正数},knowledge:{name:字符串,description:字符串,prerequisites:[知识id],observations:[可检验观察],capabilities:[字符串],risks:[风险]}}；"
            "communicate={target_society_id:字符串,knowledge_ids:[知识id]}；"
            "organize={organization_id:字符串,name:字符串,purpose:字符串,members:正数,rules:[字符串],effects:{允许效果:0至2},materials:{resource_id:正数},risks:[风险]}，"
            "组织效果仅为 coordination, knowledge_retention, distribution, conflict_pressure。"
            "风险结构为 {name,probability,effect,magnitude,resource_id?}，probability 在0至0.75之间，"
            "effect 仅为 population_loss, resource_loss, environment_damage, organization_strain。"
            "只能引用世界状态中存在的资源、地点、社会、知识和能力标识；新知识名称、假说和组织可以自由提出。世界状态：\n"
            + json.dumps(state, ensure_ascii=False, sort_keys=True)
        )

    @staticmethod
    def _chronicle_prompt(
        epoch: int,
        events: List[OpenEvent],
        plans: List[OpenPlan],
        resolution_lines: List[str],
        societies: Dict[str, Society],
        scenario_context: str,
        calendar_label: str,
        span_years: int,
    ) -> str:
        facts = {
            "epoch": epoch,
            "calendar": calendar_label,
            "span_years": span_years,
            "scenario": scenario_context,
            "events": [public_dict(item) for item in events],
            "plans": [public_dict(item) for item in plans],
            "resolutions": resolution_lines,
            "end_state": [public_dict(item) for item in societies.values()],
        }
        return (
            "你是一位面向普通读者写作的中国史家。请把以下已经裁定的事实写成通俗历史正文。"
            f"第一行必须用【{calendar_label}：简短纪名】作标题，其后写三至五段连贯叙事。"
            + (
                f"这一期横跨{span_years}年，正文应使用“这一时期”“此后数十年”等时间说法，"
                "不得把整段误写成一年。"
                if span_years > 1
                else "这一期是一年，可以按年度纪事书写。"
            )
            + "先交代环境变化，再叙述各社会为何行动、行动如何受阻或完成，最后写本纪留下的局势。"
            "文风接近清楚的中学历史课本与通俗历史读物。每句话只说一两件事，少用长句，"
            "难词能换成常用词就换，不卖弄文言，不堆砌地理、水文或制度术语。"
            "在人类中国场景中，只写国家、朝廷、官员、军队、百姓、粮食、河流、道路、城邑等自然说法。"
            "不得出现 Agent、LLM、DSL、primitive、WorldEngine、resource id、知识节点、规模单位、"
            "种群、代谢、栖息适宜度、基质、溶剂、势差或模型边界等模拟术语。"
            "不用项目符号，不逐字段抄写，不写成运行日志，也不要逐国机械报账。"
            "不得添加输入中没有的人物、因果、成果、伤亡、技术或事件；提案不得写成已经实现，"
            "只有 resolutions 中确认完成的事情才能作为结果。不要评价这是游戏或模拟器。只输出正文。事实：\n"
            + json.dumps(facts, ensure_ascii=False, sort_keys=True)
        )

    @staticmethod
    def _event_prompt(
        locations: Dict[str, Location],
        resource_specs: Dict[str, ResourceSpec],
        epoch: int,
        recent_history: Sequence[str],
        scenario_context: str,
        calendar_label: str,
        span_years: int,
    ) -> str:
        state = {
            "epoch": epoch,
            "calendar": calendar_label,
            "span_years": span_years,
            "scenario": scenario_context,
            "locations": {key: public_dict(value) for key, value in locations.items()},
            "resources": {key: public_dict(value) for key, value in resource_specs.items()},
            "recent_history": list(recent_history),
        }
        return (
            "你是独立于各社会的环境过程 Agent。你不服务任何社会目标，只根据地点属性、物质存量与既往变化，"
            "提出一个有物理原因且没有预设类别的中文世界事件。只输出 JSON。字段必须为 name, description, "
            "causes, duration, location_resource_deltas, location_property_deltas, external_inputs, "
            "external_outputs。资源变化必须满足质量守恒，跨模拟边界的物质必须显式记入 input 或 output。"
            "不要从灾害清单选择，也不要为了贴合真实历史而强行制造已知事件。"
            + (
                "本轮跨越多年，事件应代表这一时期最重要且可由状态支持的环境过程，duration 必须为 1。"
                if span_years > 1
                else "本轮为一年，duration 可以按实际过程填写。"
            )
            + "在人类历史场景中，name、description 与 causes 必须使用旱情、降雨、河水、山洪、寒潮、"
            "粮食歉收等普通读者能懂的说法，不写抽象物理术语；内部字段仍使用给定 id。世界状态：\n"
            + json.dumps(state, ensure_ascii=False, sort_keys=True)
        )
