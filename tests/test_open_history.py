import random
import unittest

from engine import SimulationEngine
from event_compiler import EventCompiler
from models import (
    KnowledgeGraph,
    KnowledgeNode,
    Location,
    OpenEvent,
    OpenPlan,
    PlanStep,
    ResourceSpec,
    RiskSpec,
    Society,
)
from plan_compiler import PlanCompiler
from world_engine import WorldEngine


class CompilerTests(unittest.TestCase):
    def test_open_semantic_plan_compiles_to_generic_primitives(self):
        plan = OpenPlan(
            "society-a",
            "用多孔层叠体缓释周期洪峰",
            "降低高流量时的栖息地冲刷，同时保留低流量交换",
            [
                PlanStep(
                    "construct",
                    {
                        "structure_id": "porous-barrier-a",
                        "name": "多孔缓流层叠体",
                        "materials": {"loose-mass": 12},
                        "effects": {"hazard_resistance": 0.25},
                        "required_capabilities": [],
                    },
                )
            ],
        )
        compiled = PlanCompiler().compile(plan, epoch=3)
        self.assertEqual(compiled.primitives[0].kind.value, "construct")
        self.assertEqual(compiled.source.title, "用多孔层叠体缓释周期洪峰")

class WorldConstraintTests(unittest.TestCase):
    def setUp(self):
        self.specs = {
            "raw": ResourceSpec("raw", "原始物质", {"structural"}),
            "derived": ResourceSpec("derived", "重组物质", {"processed"}),
        }
        self.location = Location(
            "place",
            "试验地点",
            {"habitability": 0.8, "carrying_capacity": 100},
            {"raw": 100, "derived": 0},
            {"raw": 120, "derived": 100},
        )
        self.actor = Society(
            "society-a",
            "试验共同体",
            "智慧碳基生命",
            50,
            "place",
            {"raw": 20, "derived": 0},
            {"cohesion": 0.7},
        )

    def test_missing_knowledge_capability_rejects_execution(self):
        world = WorldEngine(
            random.Random(1),
            self.specs,
            {"place": self.location},
            {"society-a": self.actor},
        )
        plan = OpenPlan(
            "society-a",
            "塑造未知材料",
            "验证因果依赖",
            [
                PlanStep(
                    "construct",
                    {
                        "structure_id": "x",
                        "name": "未知结构",
                        "materials": {"raw": 5},
                        "effects": {"hazard_resistance": 0.2},
                        "required_capabilities": ["尚未掌握的塑造法"],
                    },
                )
            ],
        )
        compiled = PlanCompiler().compile(plan, epoch=1)
        world.submit(compiled)
        resolutions = world.advance(epoch=1)
        self.assertTrue(any(item.status == "failed" and "缺少可验证能力" in item.summary for item in resolutions))
        self.assertEqual(self.actor.inventory["raw"], 20)

    def test_transform_cannot_create_mass(self):
        world = WorldEngine(
            random.Random(1),
            self.specs,
            {"place": self.location},
            {"society-a": self.actor},
        )
        plan = OpenPlan(
            "society-a",
            "无中生有",
            "应当被物理执行器拒绝",
            [
                PlanStep(
                    "transform",
                    {
                        "inputs": {"raw": 2},
                        "outputs": {"derived": 3},
                        "required_capabilities": [],
                    },
                )
            ],
        )
        world.submit(PlanCompiler().compile(plan, epoch=1))
        resolutions = world.advance(epoch=1)
        self.assertTrue(any(item.status == "failed" and "质量" in item.summary for item in resolutions))
        self.assertEqual(self.actor.inventory["raw"], 20)

    def test_open_event_must_balance_boundary_flows(self):
        world = WorldEngine(
            random.Random(1),
            self.specs,
            {"place": self.location},
            {"society-a": self.actor},
        )
        event = OpenEvent(
            "无法解释的物质涌现",
            "没有来源却增加物质",
            ["未知原因"],
            1,
            {"place": {"raw": 5}},
            {},
        )
        compiled = EventCompiler().compile(event, epoch=1)
        result = world.submit_event(compiled)
        self.assertEqual(result.status, "rejected")
        self.assertIn("不守恒", result.summary)

    def test_knowledge_risk_is_active_when_capability_is_used(self):
        graph = KnowledgeGraph()
        node = KnowledgeNode(
            "knowledge-risk",
            "高应力重排假说",
            "材料可以重排，但会飞散碎片",
            "society-a",
            1,
            [],
            ["重复加载出现同类断裂"],
            ["重排:raw"],
            [RiskSpec("碎片飞散", 0.75, "population_loss", 3)],
        )
        graph.add(node)
        self.actor.knowledge.add(node.id)
        world = WorldEngine(
            random.Random(1),
            self.specs,
            {"place": self.location},
            {"society-a": self.actor},
            graph,
        )
        plan = OpenPlan(
            "society-a",
            "按高应力假说重排物质",
            "取得不同结构",
            [
                PlanStep(
                    "transform",
                    {
                        "inputs": {"raw": 10},
                        "outputs": {"derived": 8},
                        "required_capabilities": ["重排:raw"],
                    },
                )
            ],
        )
        world.submit(PlanCompiler().compile(plan, epoch=2))
        resolutions = world.advance(epoch=2)
        completion = next(item for item in resolutions if item.status == "completed")
        self.assertIn("碎片飞散", completion.side_effects[0])
        self.assertLessEqual(self.actor.population, 47)


class SimulationTests(unittest.TestCase):
    def test_same_seed_replays_exactly(self):
        first = SimulationEngine(
            seed=73, planner_mode="heuristic", scenario="open-origin"
        )
        second = SimulationEngine(
            seed=73, planner_mode="heuristic", scenario="open-origin"
        )
        first.run(14)
        second.run(14)
        self.assertEqual(first.state_snapshot(), second.state_snapshot())

    def test_seeds_produce_different_nonhistorical_paths(self):
        signatures = set()
        knowledge_names = []
        for seed in range(8):
            engine = SimulationEngine(
                seed=seed, planner_mode="heuristic", scenario="open-origin"
            )
            engine.run(18)
            signatures.add(engine.path_signature())
            knowledge_names.extend(node.name for node in engine.knowledge_graph.nodes.values())
        self.assertGreaterEqual(len(signatures), 6)
        self.assertGreater(len(knowledge_names), 4)
        fixed_eras = ("农业时代", "青铜时代", "铁器时代", "工业时代", "信息时代")
        self.assertFalse(any(era in name for era in fixed_eras for name in knowledge_names))

    def test_long_horizon_allows_survival_and_extinction(self):
        outcomes = []
        society_counts = []
        for seed in (0, 2, 4, 10):
            engine = SimulationEngine(
                seed=seed, planner_mode="heuristic", scenario="open-origin"
            )
            engine.run(120)
            outcomes.append(sum(item.is_alive for item in engine.societies.values()))
            society_counts.append(len(engine.societies))
        self.assertTrue(any(alive == 0 for alive in outcomes))
        self.assertTrue(any(alive > 0 for alive in outcomes))
        self.assertTrue(any(count > 3 for count in society_counts))

    def test_default_scenario_is_open_warring_states_history(self):
        engine = SimulationEngine(seed=42, planner_mode="heuristic")
        engine.genesis()
        self.assertEqual(
            {item.name for item in engine.societies.values()},
            {"秦国", "韩国", "赵国", "魏国", "楚国", "燕国", "齐国"},
        )
        self.assertEqual(engine.calendar_label(), "公元前230年")
        engine.step()
        self.assertEqual(engine.calendar_label(), "公元前230年")
        self.assertIn("没有既定剧本", engine.scenario.context)
        self.assertTrue(
            all("人类国家" in item.species_profile for item in engine.societies.values())
        )

    def test_scenario_data_does_not_replace_generic_origin(self):
        engine = SimulationEngine(
            seed=42, planner_mode="heuristic", scenario="open-origin"
        )
        engine.genesis()
        self.assertEqual(len(engine.societies), 3)
        self.assertNotIn("grain", engine.resource_specs)
        self.assertIn("nutrient_matrix", engine.resource_specs)


if __name__ == "__main__":
    unittest.main()
