from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from llm_backend import LLMBackend
from models import ActionType, AgentIntent, Civilization, CivilizationView, DiplomaticStatus, Region


class CivilizationAgent:
    """Decision policy for one civilization.

    LLM mode produces intentions only. The heuristic fallback uses utility scoring:
    needs, ethos, explicit goals, geography, diplomatic tension and seeded exploration
    all contribute. No single rule can permanently short-circuit the policy.
    """

    def __init__(self, backend: LLMBackend, rng: random.Random):
        self.backend = backend
        self.rng = rng

    def decide(self, view: CivilizationView) -> AgentIntent:
        if self.backend.enabled:
            intent = self._llm_decide(view)
            if intent is not None:
                return intent
        return self._heuristic_decide(view)

    def _llm_decide(self, view: CivilizationView) -> Optional[AgentIntent]:
        me = view.self_state
        others = [
            {
                "id": c.id,
                "name": c.name,
                "population": c.population,
                "relationship": me.relationships.get(c.id, DiplomaticStatus.NEUTRAL.value),
                "tension": round(me.tensions.get(c.id, 0.0), 1),
            }
            for c in view.known_civilizations
            if c.is_alive and c.id != me.id
        ]
        prompt = f"""
You are the ruler-policy agent for a civilization simulation. Choose ONE strategic intention.
You cannot change world state directly; a separate deterministic simulator will resolve the outcome.
Return JSON only with keys: action, target_civilization_id, target_region_id, rationale, edict.
Allowed action values: {[a.name for a in ActionType]}.

Epoch: {view.epoch}
Civilization: {me.name} ({me.id})
Ethos: {me.ethos}
Goals: {me.goals}
Population: {me.population}; food: {me.food}; ore: {me.ore}; wealth: {me.wealth}
Techs: {me.techs}
Home region: {view.home_region.name}, fertility={view.home_region.fertility}, minerals={view.home_region.mineral_richness}
Known civilizations: {others}
Recent events: {view.recent_events[-8:]}
Important memories: {[m.summary for m in me.memory[:6]]}
""".strip()
        data = self.backend.query_json(prompt)
        if not data:
            return None
        try:
            action = ActionType[str(data.get("action", "")).upper()]
        except KeyError:
            return None

        target_civ = data.get("target_civilization_id")
        target_region = data.get("target_region_id")
        valid_civ_ids = {c.id for c in view.known_civilizations if c.is_alive and c.id != me.id}
        valid_region_ids = {r.id for r in view.known_regions}
        if target_civ not in valid_civ_ids:
            target_civ = None
        if target_region not in valid_region_ids:
            target_region = None
        if action in {ActionType.RAID, ActionType.TRADE, ActionType.TREATY} and target_civ is None:
            return None
        return AgentIntent(
            civilization_id=me.id,
            action_type=action,
            target_civilization_id=target_civ,
            target_region_id=target_region,
            rationale=str(data.get("rationale", ""))[:500],
            edict=str(data.get("edict", ""))[:500],
        )

    def _heuristic_decide(self, view: CivilizationView) -> AgentIntent:
        me = view.self_state
        others = [c for c in view.known_civilizations if c.is_alive and c.id != me.id]
        region_map = {r.id: r for r in view.known_regions}
        owned = [r for r in view.known_regions if r.controlled_by == me.id]
        frontier = self._frontier_regions(owned, region_map)

        food_ratio = me.food / max(1, me.population * 2)
        scarcity = max(0.0, 1.45 - food_ratio)
        aggressive = self._contains(me.ethos, ("尚武", "勇猛", "征服", "以战", "崇火"))
        mercantile = self._contains(me.ethos, ("通商", "农商", "善贾", "贸易"))
        inventive = self._contains(me.ethos, ("百工", "采石", "格物", "钻研", "构筑", "筑城"))
        spiritual = self._contains(me.ethos, ("祭", "神", "图腾"))

        goal_food = self._goal(me, ("粮", "生存", "仓"))
        goal_land = self._goal(me, ("土地", "疆", "拓", "富饶"))
        goal_resources = self._goal(me, ("资源", "矿", "自主"))
        goal_trade = self._goal(me, ("商", "贸易", "财富"))
        goal_peace = self._goal(me, ("和平", "稳定", "盟"))
        goal_tech = self._goal(me, ("技术", "科技", "百工", "创新"))

        max_tension = max((me.tensions.get(c.id, 0.0) for c in others), default=0.0)
        hostile_count = sum(
            me.relationships.get(c.id) in {DiplomaticStatus.HOSTILE.value, DiplomaticStatus.WAR.value}
            for c in others
        )

        scores: Dict[ActionType, float] = {
            ActionType.CULTIVATE: 16 + scarcity * 48 + goal_food * 18,
            ActionType.INVENT: 14 + inventive * 24 + goal_tech * 30 + goal_resources * 8 + min(18, me.ore / 10),
            ActionType.EXPAND: 12 + goal_land * 24 + goal_resources * 8 + min(28, len(frontier) * 11) + (6 if food_ratio > 1.0 else -6),
            ActionType.TRADE: 11 + mercantile * 27 + goal_trade * 25 + (6 if me.wealth < 150 else 0),
            ActionType.TREATY: 6 + goal_peace * 30 + hostile_count * 16 + max_tension * 0.16 + me.war_exhaustion * 0.70,
            ActionType.RAID: 3 + aggressive * 28 + goal_land * 16 + max_tension * 0.48 + scarcity * 9 - me.war_exhaustion * 1.10,
            ActionType.WORSHIP: 7 + spiritual * 18,
        }

        if me.ore < 25:
            scores[ActionType.INVENT] -= 35
        if not frontier:
            scores[ActionType.EXPAND] -= 20
            if goal_land or aggressive:
                scores[ActionType.RAID] += 12
        if not others:
            scores[ActionType.TRADE] = scores[ActionType.TREATY] = scores[ActionType.RAID] = -100
        if aggressive and max_tension < 45:
            scores[ActionType.RAID] -= 25
        elif not aggressive and max_tension < 55:
            scores[ActionType.RAID] -= 45
        if food_ratio < 0.75:
            scores[ActionType.CULTIVATE] += 30

        # Seeded exploration prevents deterministic lock-in while preserving replayability.
        for action in scores:
            scores[action] += self.rng.uniform(0.0, 7.0)

        action = self._sample_action(scores, temperature=13.0)

        if action == ActionType.RAID:
            target = self._select_raid_target(me, others, region_map)
            if target is None:
                action = ActionType.CULTIVATE
            else:
                return self._intent(
                    me, action,
                    f"综合粮食、领土目标与外交紧张度后，战争收益最高；当前对{target.name}紧张度为{me.tensions.get(target.id, 0):.0f}。",
                    target.id,
                    metadata={"utility": round(scores[ActionType.RAID], 2)},
                )
        if action == ActionType.TRADE:
            target = self._select_trade_target(me, others)
            if target is not None:
                return self._intent(
                    me, action, "贸易符合本族经济取向，并可降低与邻邦的摩擦。",
                    target.id, metadata={"utility": round(scores[action], 2)},
                )
            action = ActionType.CULTIVATE
        if action == ActionType.TREATY:
            target = self._select_treaty_target(me, others)
            if target is not None:
                return self._intent(
                    me, action, "当前外部风险使外交缓和的边际收益上升。",
                    target.id, metadata={"utility": round(scores[action], 2)},
                )
            action = ActionType.CULTIVATE
        if action == ActionType.EXPAND:
            target_region = self._select_frontier(me, frontier)
            if target_region is not None:
                return self._intent(
                    me, action, f"扩张可获得{target_region.name}的地力与矿藏。",
                    target_region_id=target_region.id, metadata={"utility": round(scores[action], 2)},
                )
            action = ActionType.CULTIVATE

        rationale = {
            ActionType.CULTIVATE: "当前粮食安全的效用高于其他战略选择。",
            ActionType.INVENT: "文化取向、明确目标与矿石储备共同提高了技术投资收益。",
            ActionType.WORSHIP: "公共仪式有助于维持共同体凝聚与财富循环。",
        }.get(action, "综合当前状态选择效用最高的行动。")
        return self._intent(me, action, rationale, metadata={"utility": round(scores[action], 2)})

    def _sample_action(self, scores: Dict[ActionType, float], temperature: float) -> ActionType:
        maximum = max(scores.values())
        weighted = []
        total = 0.0
        for action, score in scores.items():
            weight = math.exp((score - maximum) / temperature)
            weighted.append((action, weight))
            total += weight
        roll = self.rng.random() * total
        upto = 0.0
        for action, weight in weighted:
            upto += weight
            if roll <= upto:
                return action
        return max(scores, key=scores.get)

    def _frontier_regions(self, owned: List[Region], region_map: Dict[str, Region]) -> List[Region]:
        ids = set()
        for region in owned:
            for rid in region.neighbors:
                candidate = region_map[rid]
                if candidate.controlled_by is None:
                    ids.add(rid)
        return [region_map[rid] for rid in sorted(ids)]

    def _select_frontier(self, me: Civilization, frontier: List[Region]) -> Optional[Region]:
        if not frontier:
            return None
        wants_food = self._goal(me, ("粮", "富饶", "土地"))
        wants_resources = self._goal(me, ("资源", "矿", "技术"))
        return max(
            frontier,
            key=lambda r: (
                r.fertility * (1.5 if wants_food else 1.0)
                + r.mineral_richness * (1.5 if wants_resources else 1.0),
                r.id,
            ),
        )

    def _select_raid_target(
        self, me: Civilization, others: List[Civilization], region_map: Dict[str, Region]
    ) -> Optional[Civilization]:
        candidates = [c for c in others if me.relationships.get(c.id) != DiplomaticStatus.ALLIED.value]
        if not candidates:
            candidates = others
        if not candidates:
            return None
        def score(c: Civilization) -> float:
            region = region_map[c.home_region_id]
            tension = me.tensions.get(c.id, 0.0)
            weakness = max(-20.0, min(20.0, (me.population - c.population) * 0.35))
            value = region.fertility * 2.2 + region.mineral_richness
            ally_penalty = 45 if me.relationships.get(c.id) == DiplomaticStatus.ALLIED.value else 0
            return tension + weakness + value - ally_penalty
        return max(candidates, key=lambda c: (score(c), c.id))

    def _select_trade_target(self, me: Civilization, others: List[Civilization]) -> Optional[Civilization]:
        candidates = [c for c in others if me.relationships.get(c.id) != DiplomaticStatus.WAR.value]
        if not candidates:
            return None
        return min(candidates, key=lambda c: (me.tensions.get(c.id, 0.0), -c.wealth, c.id))

    def _select_treaty_target(self, me: Civilization, others: List[Civilization]) -> Optional[Civilization]:
        if not others:
            return None
        return max(
            others,
            key=lambda c: (
                me.tensions.get(c.id, 0.0)
                + (30 if me.relationships.get(c.id) in {DiplomaticStatus.HOSTILE.value, DiplomaticStatus.WAR.value} else 0),
                c.id,
            ),
        )

    def _goal(self, me: Civilization, keywords: Tuple[str, ...]) -> int:
        text = " ".join(me.goals)
        return int(any(k in text for k in keywords))

    def _contains(self, text: str, keywords: Tuple[str, ...]) -> int:
        return int(any(k in text for k in keywords))

    def _intent(
        self,
        me: Civilization,
        action: ActionType,
        rationale: str,
        target_civ_id: Optional[str] = None,
        target_region_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AgentIntent:
        return AgentIntent(
            civilization_id=me.id,
            action_type=action,
            target_civilization_id=target_civ_id,
            target_region_id=target_region_id,
            edict=f"{me.leader_name}下令施行【{action.value}】。",
            rationale=rationale,
            metadata=metadata or {},
        )


class HistorianAgent:
    def __init__(self, backend: LLMBackend):
        self.backend = backend

    def chronicle(self, epoch: int, resolutions: List[str], survivors: List[str]) -> str:
        if self.backend.enabled:
            prompt = f"""
Write a concise Chinese classical-chronicle-style account of this simulation epoch.
Do not invent events, causes, casualties, technologies, or participants that are not present in the event list.
Epoch: {epoch}
Events: {resolutions}
Surviving civilizations: {survivors}
Use 2-4 short paragraphs.
""".strip()
            text = self.backend.query(prompt)
            if text:
                return text
        body = "\n".join(f"· {r}" for r in resolutions)
        return f"【文明纪 第 {epoch} 纪】\n{body}\n\n史官曰：存续诸邦：{'、'.join(survivors)}。兴亡所系，皆由地利、资源、制度与前事相因。"
