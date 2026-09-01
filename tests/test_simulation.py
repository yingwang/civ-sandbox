import unittest

from engine import WorldEngine
from models import ActionType, AgentIntent, DiplomaticStatus


class SimulationTests(unittest.TestCase):
    def test_same_seed_replays_heuristic_run(self):
        a = WorldEngine(seed=7, llm_mode="off")
        b = WorldEngine(seed=7, llm_mode="off")
        a.genesis()
        b.genesis()
        for _ in range(5):
            a.step()
            b.step()
        snap_a = [(c.name, c.population, c.food, c.ore, c.wealth, tuple(c.techs)) for c in a.civilizations]
        snap_b = [(c.name, c.population, c.food, c.ore, c.wealth, tuple(c.techs)) for c in b.civilizations]
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

    def test_treaty_persists_in_world_state(self):
        engine = WorldEngine(seed=2, llm_mode="off")
        engine.genesis()
        a, b = engine.civilizations[:2]
        engine.step([AgentIntent(a.id, ActionType.TREATY, target_civilization_id=b.id)])
        self.assertEqual(a.relationships[b.id], DiplomaticStatus.ALLIED.value)
        self.assertEqual(b.relationships[a.id], DiplomaticStatus.ALLIED.value)


if __name__ == "__main__":
    unittest.main()
