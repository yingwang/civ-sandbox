import unittest

from engine import WorldEngine
from models import ActionType, AgentIntent, DiplomaticStatus


class SimulationTests(unittest.TestCase):
    def test_same_seed_replays_heuristic_run(self):
        a = WorldEngine(seed=7, llm_mode="off")
        b = WorldEngine(seed=7, llm_mode="off")
        a.genesis()
        b.genesis()
        for _ in range(12):
            a.step()
            b.step()
        snap_a = [
            (c.name, c.population, c.food, c.ore, c.wealth, tuple(c.techs),
             tuple(sorted(c.relationships.items())), tuple(sorted(c.tensions.items())))
            for c in a.civilizations
        ]
        snap_b = [
            (c.name, c.population, c.food, c.ore, c.wealth, tuple(c.techs),
             tuple(sorted(c.relationships.items())), tuple(sorted(c.tensions.items())))
            for c in b.civilizations
        ]
        self.assertEqual(snap_a, snap_b)

    def test_fertility_changes_farming_yield(self):
        engine = WorldEngine(seed=1, llm_mode="off")
        engine.genesis()
        plains, highland = engine.civilizations[0], engine.civilizations[2]
        plains.population = highland.population = 100
        plains.food = highland.food = 1000
        engine.step([
            AgentIntent(plains.id, ActionType.CULTIVATE),
            AgentIntent(highland.id, ActionType.CULTIVATE),
        ])
        self.assertGreater(plains.food, highland.food)

    def test_treaty_persists_and_reduces_tension(self):
        engine = WorldEngine(seed=2, llm_mode="off")
        engine.genesis()
        a, b = engine.civilizations[:2]
        a.tensions[b.id] = b.tensions[a.id] = 80
        engine.step([AgentIntent(a.id, ActionType.TREATY, target_civilization_id=b.id)])
        self.assertIn(a.relationships[b.id], {DiplomaticStatus.FRIENDLY.value, DiplomaticStatus.ALLIED.value})
        self.assertEqual(a.relationships[b.id], b.relationships[a.id])
        self.assertLess(a.tensions[b.id], 80)

    def test_technology_goal_changes_policy(self):
        engine = WorldEngine(seed=3, llm_mode="off")
        engine.genesis()
        inventor = engine.civilizations[2]
        inventor.food = 1000
        intent = engine.agent.decide(engine.observe(inventor))
        self.assertEqual(intent.action_type, ActionType.INVENT)

    def test_tension_can_create_hostility_without_prior_raid(self):
        engine = WorldEngine(seed=4, llm_mode="off")
        engine.genesis()
        a, b = engine.civilizations[:2]
        a.tensions[b.id] = b.tensions[a.id] = 69
        engine.step([
            AgentIntent(a.id, ActionType.CULTIVATE),
            AgentIntent(b.id, ActionType.CULTIVATE),
        ])
        self.assertEqual(a.relationships[b.id], DiplomaticStatus.HOSTILE.value)
        self.assertEqual(b.relationships[a.id], DiplomaticStatus.HOSTILE.value)

    def test_heuristic_does_not_collapse_into_farming_only(self):
        engine = WorldEngine(seed=42, llm_mode="off")
        engine.genesis()
        actions = []
        for _ in range(30):
            record = engine.step()
            actions.extend(intent.action_type for intent in record.actions)
        self.assertGreaterEqual(len(set(actions)), 5)
        self.assertIn(ActionType.INVENT, actions)
        self.assertIn(ActionType.RAID, actions)

    def test_frontier_expansion_uses_all_controlled_regions(self):
        engine = WorldEngine(seed=5, llm_mode="off")
        engine.genesis()
        civ = engine.civilizations[0]
        # reg_3 is not adjacent to civ_1's home (reg_1), but becomes frontier
        # once civ_1 controls reg_4.
        engine.state.region_map()["reg_4"].controlled_by = civ.id
        engine.state.region_map()["reg_3"].controlled_by = None
        engine.step([AgentIntent(civ.id, ActionType.EXPAND, target_region_id="reg_3")])
        self.assertEqual(engine.state.region_map()["reg_3"].controlled_by, civ.id)


if __name__ == "__main__":
    unittest.main()
