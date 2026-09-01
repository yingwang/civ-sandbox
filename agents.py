from __future__ import annotations

import random
from typing import List, Optional

from llm_backend import LLMBackend
from models import ActionType, AgentIntent, Civilization, CivilizationView, DiplomaticStatus


class CivilizationAgent:
    """Decision policy for one civilization.

    LLM mode produces intentions only. If no model is available or its output is
    invalid, a state-aware heuristic policy is used as a deterministic fallback.
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
        food_pressure = me.food / max(1, me.population * 2)
        aggressive = any(x in me.ethos for x in ("尚武", "勇猛", "征服", "以战"))
        mercantile = any(x in me.ethos for x in ("通商", "农商", "善贾", "贸易"))
        inventive = any(x in me.ethos for x in ("百工", "采石", "格物", "钻研", "构筑"))

        if food_pressure < 1.15:
            return self._intent(me, ActionType.CULTIVATE, "粮储接近人口消耗线，优先扩大粮食供给。")

        hostile = [c for c in others if me.relationships.get(c.id) in {DiplomaticStatus.HOSTILE.value, DiplomaticStatus.WAR.value}]
        if aggressive and hostile and self.rng.random() < 0.65:
            target = min(hostile, key=lambda c: c.population)
            return self._intent(me, ActionType.RAID, "敌对关系已经形成，尝试以军事行动夺取资源。", target.id)

        if inventive and self.rng.random() < 0.55:
            return self._intent(me, ActionType.INVENT, "本族文化重视技艺，投资新技术具有长期收益。")

        if mercantile and others and self.rng.random() < 0.65:
            candidates = [c for c in others if me.relationships.get(c.id) != DiplomaticStatus.WAR.value]
            if candidates:
                target = self.rng.choice(candidates)
                return self._intent(me, ActionType.TRADE, "通过互市获得财富，并改善外交关系。", target.id)

        if others and self.rng.random() < 0.22:
            target = self.rng.choice(others)
            return self._intent(me, ActionType.TREATY, "外部风险上升，建立稳定关系可降低战争成本。", target.id)

        if self.rng.random() < 0.55:
            return self._intent(me, ActionType.EXPAND, "人口增长需要新的定居空间与资源来源。")
        return self._intent(me, ActionType.WORSHIP, "通过公共仪式强化共同体认同与社会凝聚。")

    def _intent(
        self,
        me: Civilization,
        action: ActionType,
        rationale: str,
        target_civ_id: Optional[str] = None,
    ) -> AgentIntent:
        return AgentIntent(
            civilization_id=me.id,
            action_type=action,
            target_civilization_id=target_civ_id,
            edict=f"{me.leader_name}下令施行【{action.value}】。",
            rationale=rationale,
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
