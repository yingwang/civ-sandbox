import unittest

from open_ledger_engine import OpenKnowledgeLedgerEngine


class OpenKnowledgeLedgerEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = OpenKnowledgeLedgerEngine(seed=1, llm_enabled=False, live_print=False)
        self.polity = self.engine.living("huabei")[0]

    def test_prompt_does_not_expose_a_research_effect_menu(self):
        prompt = self.engine.proposal_prompt("huabei", "公元前230年至公元前150年")
        self.assertIn('"hypothesis"', prompt)
        self.assertIn('"experiment"', prompt)
        self.assertIn('"mechanism"', prompt)
        self.assertIn('"expected_consequences"', prompt)
        self.assertNotIn('"effect": "capacity|military|trade|literacy|research|health|navigation"', prompt)
        self.assertIn("不要从任何预设科技树挑下一项", prompt)

    def test_direct_observation_can_be_discovered_without_a_named_prerequisite(self):
        before = len(self.engine.nodes)
        self.engine.rng.random = lambda: 0.0
        self.engine.attempt_research(
            1,
            "huabei",
            self.polity,
            {
                "name": "井水沉置后的层次差异记录法",
                "question": "同一井水静置后为什么出现不同层次",
                "from": [],
                "hypothesis": "静置时间会使不同颗粒自行分层",
                "experiment": "取等量井水放入多个相同陶器，分别静置不同时间并比较各层厚度",
                "mechanism": "较重颗粒更快沉降，因而形成可重复观察的层次",
                "expected_consequences": ["提高对浑水变化的可重复记录"],
            },
        )
        self.assertEqual(len(self.engine.nodes), before + 1)
        node = self.engine.nodes[f"n{self.engine._node_counter}"]
        self.assertEqual(node.prereqs, [])
        self.assertEqual(node.kind, "observation")

    def test_missing_claimed_capability_is_rejected(self):
        before = len(self.engine.nodes)
        self.engine.attempt_research(
            1,
            "huabei",
            self.polity,
            {
                "name": "不存在能力上的试验",
                "question": "能否做到某事",
                "from": ["账上不存在的能力"],
                "hypothesis": "也许可以",
                "experiment": "进行一个足够具体但依赖不存在能力的重复试验",
                "mechanism": "未知",
                "expected_consequences": [],
            },
        )
        self.assertEqual(len(self.engine.nodes), before)
        self.assertEqual(self.engine.ledger[-1]["type"], "research_rejected")

    def test_free_form_consequence_is_projected_after_success(self):
        self.engine.rng.random = lambda: 0.0
        self.engine.attempt_research(
            1,
            "huabei",
            self.polity,
            {
                "name": "分段引水与沉沙的反复试作法",
                "question": "怎样减少渠水携沙造成的耕地供水损失",
                "from": ["渠灌与蓄水"],
                "hypothesis": "让水流先经过多个缓流区会使泥沙分段沉降",
                "experiment": "在小渠上设置不同数量的缓流段，记录下游流量、泥沙和可灌溉面积",
                "mechanism": "降低局部流速使较重颗粒提前沉降，同时保留下游供水",
                "expected_consequences": ["减少灌溉堵塞并提高粮食产量和土地承载"],
            },
        )
        node = self.engine.nodes[f"n{self.engine._node_counter}"]
        self.assertGreater(node.bonuses.get("capacity_bonus", 0.0), 0.0)
        self.assertNotIn("effect", self.engine.ledger[-1])
        self.assertIn("macro_projection", self.engine.ledger[-1])


if __name__ == "__main__":
    unittest.main()
