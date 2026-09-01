from __future__ import annotations

import random
from typing import List, Optional, Tuple

from agents import CivilizationAgent, HistorianAgent
from llm_backend import LLMBackend
from models import (
    ActionType,
    AgentIntent,
    Civilization,
    CivilizationView,
    DiplomaticStatus,
    EpochRecord,
    Region,
    TerrainType,
    WorldEvent,
    WorldState,
)


class WorldEngine:
    """Authoritative civilization simulator.

    Agents propose intentions. This engine alone mutates the WorldState. Given the
    same seed, initial state and sequence of intents, transitions are reproducible.
    """

    TECH_TREE = {
        "水车引灌": {"farm_mult": 1.25},
        "铁犁牛耕": {"farm_mult": 1.35},
        "冶铜铸兵": {"attack": 30},
        "重甲战车": {"attack": 35},
        "夯土城垣": {"defense": 45},
        "观星历法": {"disaster_resistance": 0.5},
        "草药医理": {"growth_mult": 1.2},
        "造舟浮海": {"trade_mult": 1.3},
        "成文法典": {"stability": 1},
    }

    DISASTERS = [
        ("大旱", 0.16),
        ("洪水", 0.14),
        ("极寒", 0.12),
        ("蝗灾", 0.15),
        ("丰年", -0.10),
    ]

    def __init__(self, seed: int = 0, llm_mode: str = "off"):
        self.seed = seed
        self.rng = random.Random(seed)
        self.backend = LLMBackend(mode=llm_mode)
        self.agent = CivilizationAgent(self.backend, self.rng)
        self.historian = HistorianAgent(self.backend)
        self.state = WorldState(seed=seed)

    @property
    def epoch(self) -> int:
        return self.state.epoch

    @property
    def regions(self) -> List[Region]:
        return self.state.regions

    @property
    def civilizations(self) -> List[Civilization]:
        return self.state.civilizations

    @property
    def tribes(self) -> List[Civilization]:
        return self.state.civilizations

    @property
    def history(self) -> List[EpochRecord]:
        return self.state.history

    def genesis(self) -> Tuple[List[Region], List[Civilization]]:
        regions = [
            Region("reg_1", "中原沃野", TerrainType.PLAINS, 9, 4, neighbors=["reg_2", "reg_4"]),
            Region("reg_2", "九江大泽", TerrainType.RIVERLAND, 8, 3, neighbors=["reg_1", "reg_4", "reg_5"]),
            Region("reg_3", "昆仑荒原", TerrainType.HIGHLAND, 3, 10, neighbors=["reg_4", "reg_6"]),
            Region("reg_4", "云梦林莽", TerrainType.FOREST, 6, 7, neighbors=["reg_1", "reg_2", "reg_3"]),
            Region("reg_5", "东溟之滨", TerrainType.COASTAL, 5, 5, neighbors=["reg_2"]),
            Region("reg_6", "西荒流沙", TerrainType.DESERT, 2, 8, neighbors=["reg_3"]),
        ]
        civs = [
            Civilization(
                id="civ_1", name="炎黎氏", leader_title="大祭司", leader_name="黎炎", totem="赤焰火鸟",
                ethos="崇火勇猛，以战养战", population=112, food=330, ore=90, wealth=100,
                home_region_id="reg_1", goals=["确保粮食安全", "控制富饶土地"],
            ),
            Civilization(
                id="civ_2", name="渚泽氏", leader_title="族长", leader_name="云汐", totem="玄龟双鲤",
                ethos="依水织网，善通商贾", population=104, food=320, ore=75, wealth=130,
                home_region_id="reg_2", goals=["扩大商路", "维持和平环境"],
            ),
            Civilization(
                id="civ_3", name="磐石氏", leader_title="首领", leader_name="重石", totem="苍角青兕",
                ethos="耐苦耐劳，工于采石筑城", population=98, food=285, ore=160, wealth=90,
                home_region_id="reg_3", goals=["积累技术", "保障资源自主"],
            ),
        ]
        for civ in civs:
            for other in civs:
                if other.id != civ.id:
                    civ.relationships[other.id] = DiplomaticStatus.NEUTRAL.value
        for civ in civs:
            next(r for r in regions if r.id == civ.home_region_id).controlled_by = civ.id
        self.state = WorldState(epoch=0, regions=regions, civilizations=civs, history=[], seed=self.seed)
        return self.regions, self.civilizations

    def observe(self, civ: Civilization) -> CivilizationView:
        region_map = self.state.region_map()
        recent = [event.text for record in self.history[-3:] for event in record.events]
        return CivilizationView(
            epoch=self.epoch + 1,
            self_state=civ,
            home_region=region_map[civ.home_region_id],
            known_regions=list(self.regions),
            known_civilizations=list(self.civilizations),
            recent_events=recent[-12:],
        )

    def step(self, intents: Optional[List[AgentIntent]] = None) -> EpochRecord:
        if not self.regions:
            self.genesis()
        self.state.epoch += 1
        epoch = self.state.epoch
        events: List[WorldEvent] = []

        disaster = self._apply_environment(epoch, events)
        if intents is None:
            intents = [self.agent.decide(self.observe(c)) for c in self.civilizations if c.is_alive]

        for intent in sorted(intents, key=lambda x: (-x.priority, x.civilization_id)):
            self._resolve(intent, events)

        self._settle_population(events)
        self._write_memories(events)
        resolutions = [e.text for e in events]
        survivors = [c.name for c in self.civilizations if c.is_alive]
        chronicle = self.historian.chronicle(epoch, resolutions, survivors)
        record = EpochRecord(epoch, disaster, intents, resolutions, chronicle, events)
        self.history.append(record)
        return record

    def _apply_environment(self, epoch: int, events: List[WorldEvent]) -> Optional[str]:
        if self.rng.random() > 0.55:
            return None
        title, severity = self.rng.choice(self.DISASTERS)
        for civ in self.civilizations:
            if not civ.is_alive:
                continue
            region = self.state.region_map()[civ.home_region_id]
            resistance = self.TECH_TREE.get("观星历法", {}).get("disaster_resistance", 1.0) if "观星历法" in civ.techs else 1.0
            terrain_factor = 1.0
            if title == "洪水" and region.terrain == TerrainType.RIVERLAND:
                terrain_factor = 1.35
            elif title == "大旱" and region.terrain == TerrainType.DESERT:
                terrain_factor = 1.45
            elif title == "丰年" and region.fertility >= 8:
                terrain_factor = 1.25
            delta = int(civ.food * severity * resistance * terrain_factor)
            civ.food = max(0, civ.food - delta)
        if severity >= 0:
            text = f"【天变】{title}波及诸邦，损失程度因地形与减灾技术而异。"
        else:
            text = f"【天时】{title}降临，高沃度地区受益尤多。"
        events.append(WorldEvent(epoch, "environment", text, data={"event": title, "severity": severity}))
        return title

    def _resolve(self, intent: AgentIntent, events: List[WorldEvent]) -> None:
        civs = self.state.civilization_map()
        actor = civs.get(intent.civilization_id)
        if actor is None or not actor.is_alive:
            return
        action = intent.action_type
        if action == ActionType.CULTIVATE:
            self._cultivate(actor, events)
        elif action == ActionType.INVENT:
            self._invent(actor, events)
        elif action == ActionType.TRADE:
            self._trade(actor, civs.get(intent.target_civilization_id or ""), events)
        elif action == ActionType.TREATY:
            self._treaty(actor, civs.get(intent.target_civilization_id or ""), events)
        elif action == ActionType.RAID:
            self._raid(actor, civs.get(intent.target_civilization_id or ""), events)
        elif action == ActionType.EXPAND:
            self._expand(actor, intent.target_region_id, events)
        elif action == ActionType.WORSHIP:
            self._worship(actor, events)

    def _cultivate(self, civ: Civilization, events: List[WorldEvent]) -> None:
        region = self.state.region_map()[civ.home_region_id]
        tech_mult = 1.0
        for tech in civ.techs:
            tech_mult *= float(self.TECH_TREE.get(tech, {}).get("farm_mult", 1.0))
        gain = int((civ.population * 1.8 + region.fertility * 18) * tech_mult)
        civ.food += gain
        events.append(WorldEvent(self.epoch, "agriculture", f"【农桑】{civ.name}依{region.name}地力耕作，增粮 {gain}。", [civ.id], {"food": gain}))

    def _invent(self, civ: Civilization, events: List[WorldEvent]) -> None:
        available = [t for t in self.TECH_TREE if t not in civ.techs]
        if not available or civ.ore < 25:
            civ.wealth += 15
            events.append(WorldEvent(self.epoch, "craft", f"【百工】{civ.name}无力开辟新技，转而改良旧器，财富 +15。", [civ.id]))
            return
        region = self.state.region_map()[civ.home_region_id]
        idx = (self.epoch + region.mineral_richness + len(civ.techs)) % len(available)
        tech = available[idx]
        civ.techs.append(tech)
        civ.ore -= 25
        events.append(WorldEvent(self.epoch, "technology", f"【技术】{civ.name}创制【{tech}】。", [civ.id], {"tech": tech}))

    def _trade(self, actor: Civilization, target: Optional[Civilization], events: List[WorldEvent]) -> None:
        if target is None or not target.is_alive or target.id == actor.id:
            return
        if actor.relationships.get(target.id) == DiplomaticStatus.WAR.value:
            events.append(WorldEvent(self.epoch, "trade_failed", f"【互市未成】{actor.name}与{target.name}仍在交战，商路不通。", [actor.id, target.id]))
            return
        coastal_bonus = 1.0
        if self.state.region_map()[actor.home_region_id].terrain == TerrainType.COASTAL or "造舟浮海" in actor.techs:
            coastal_bonus *= 1.3
        gain = int(35 * coastal_bonus)
        actor.wealth += gain
        target.wealth += 25
        actor.food += 15
        target.food += 15
        self._improve_relation(actor, target)
        events.append(WorldEvent(self.epoch, "trade", f"【互市】{actor.name}与{target.name}通商，{actor.name}财富 +{gain}。", [actor.id, target.id]))

    def _treaty(self, actor: Civilization, target: Optional[Civilization], events: List[WorldEvent]) -> None:
        if target is None or not target.is_alive or target.id == actor.id:
            return
        current = actor.relationships.get(target.id, DiplomaticStatus.NEUTRAL.value)
        new_status = DiplomaticStatus.FRIENDLY.value if current in {DiplomaticStatus.HOSTILE.value, DiplomaticStatus.WAR.value} else DiplomaticStatus.ALLIED.value
        actor.relationships[target.id] = new_status
        target.relationships[actor.id] = new_status
        events.append(WorldEvent(self.epoch, "diplomacy", f"【盟约】{actor.name}与{target.name}关系转为【{new_status}】。", [actor.id, target.id]))

    def _raid(self, actor: Civilization, target: Optional[Civilization], events: List[WorldEvent]) -> None:
        if target is None or not target.is_alive or target.id == actor.id:
            return
        if actor.relationships.get(target.id) == DiplomaticStatus.ALLIED.value:
            actor.relationships[target.id] = DiplomaticStatus.HOSTILE.value
            target.relationships[actor.id] = DiplomaticStatus.HOSTILE.value
            events.append(WorldEvent(self.epoch, "betrayal", f"【背盟】{actor.name}毁盟攻{target.name}，两邦转为敌对。", [actor.id, target.id]))
        else:
            actor.relationships[target.id] = DiplomaticStatus.WAR.value
            target.relationships[actor.id] = DiplomaticStatus.WAR.value

        attack = actor.population + sum(int(self.TECH_TREE.get(t, {}).get("attack", 0)) for t in actor.techs)
        defense = target.population + sum(int(self.TECH_TREE.get(t, {}).get("defense", 0)) for t in target.techs)
        attack += self.rng.randint(0, 25)
        defense += self.rng.randint(0, 25)
        if attack > defense:
            loot = min(target.food, 90)
            target.food -= loot
            actor.food += loot
            loss_a = self.rng.randint(4, 10)
            loss_t = self.rng.randint(12, 24)
            actor.population = max(10, actor.population - loss_a)
            target.population = max(0, target.population - loss_t)
            events.append(WorldEvent(self.epoch, "war", f"【战争】{actor.name}击败{target.name}，夺粮 {loot}；双方人口损失 {loss_a}/{loss_t}。", [actor.id, target.id]))
        else:
            loss_a = self.rng.randint(10, 20)
            actor.population = max(10, actor.population - loss_a)
            events.append(WorldEvent(self.epoch, "war", f"【战争】{actor.name}攻{target.name}不克，人口损失 {loss_a}。", [actor.id, target.id]))
        if target.population <= 12:
            target.is_alive = False
            for region in self.regions:
                if region.controlled_by == target.id:
                    region.controlled_by = actor.id
            events.append(WorldEvent(self.epoch, "collapse", f"【覆亡】{target.name}失去组织能力，其控制地转入{actor.name}势力范围。", [target.id, actor.id], {"salience": 3}))

    def _expand(self, actor: Civilization, requested_region_id: Optional[str], events: List[WorldEvent]) -> None:
        region_map = self.state.region_map()
        home = region_map[actor.home_region_id]
        candidates = [region_map[rid] for rid in home.neighbors if region_map[rid].controlled_by is None]
        if requested_region_id:
            requested = region_map.get(requested_region_id)
            if requested in candidates:
                candidates = [requested]
        if not candidates:
            actor.population += 5
            events.append(WorldEvent(self.epoch, "settlement", f"【拓土】{actor.name}近境已无无主地，只在旧疆增筑聚落。", [actor.id]))
            return
        if actor.food < actor.population * 3:
            region = max(candidates, key=lambda r: (r.fertility, r.mineral_richness, r.id))
        else:
            region = max(candidates, key=lambda r: (r.mineral_richness, r.fertility, r.id))
        region.controlled_by = actor.id
        actor.ore += region.mineral_richness * 4
        actor.food += region.fertility * 8
        events.append(WorldEvent(self.epoch, "expansion", f"【拓境】{actor.name}控制{region.name}，开始利用当地地力与矿藏。", [actor.id], {"region": region.id}))

    def _worship(self, actor: Civilization, events: List[WorldEvent]) -> None:
        cost = min(actor.food, 20)
        actor.food -= cost
        actor.wealth += 8
        events.append(WorldEvent(self.epoch, "culture", f"【祭仪】{actor.name}祭奉{actor.totem}，消耗粮 {cost}，共同体凝聚增强。", [actor.id]))

    def _settle_population(self, events: List[WorldEvent]) -> None:
        for civ in self.civilizations:
            if not civ.is_alive:
                continue
            consumption = civ.population * 2
            if civ.food >= consumption:
                civ.food -= consumption
                growth_mult = 1.2 if "草药医理" in civ.techs else 1.0
                growth = max(1, int(civ.population * 0.035 * growth_mult))
                civ.population += growth
            else:
                deficit = consumption - civ.food
                deaths = min(max(0, civ.population - 10), max(1, deficit // 3))
                civ.food = 0
                civ.population -= deaths
                events.append(WorldEvent(self.epoch, "famine", f"【饥馑】{civ.name}粮食不足，人口减少 {deaths}。", [civ.id], {"salience": 2}))

    def _write_memories(self, events: List[WorldEvent]) -> None:
        civ_map = self.state.civilization_map()
        for event in events:
            salience = int(event.data.get("salience", 1))
            if event.kind in {"war", "collapse", "betrayal", "diplomacy"}:
                salience = max(salience, 2)
            for civ_id in event.actors:
                civ = civ_map.get(civ_id)
                if civ:
                    civ.remember(self.epoch, event.text, salience=salience)

    def _improve_relation(self, a: Civilization, b: Civilization) -> None:
        current = a.relationships.get(b.id, DiplomaticStatus.NEUTRAL.value)
        if current == DiplomaticStatus.HOSTILE.value:
            status = DiplomaticStatus.NEUTRAL.value
        elif current == DiplomaticStatus.NEUTRAL.value:
            status = DiplomaticStatus.FRIENDLY.value
        else:
            status = current
        a.relationships[b.id] = status
        b.relationships[a.id] = status


SimulationEngine = WorldEngine
