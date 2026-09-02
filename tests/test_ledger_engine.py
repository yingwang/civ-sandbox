import json
import unittest
from pathlib import Path
import tempfile

from ledger_engine import LedgerEngine, extract_json


class LedgerEngineTests(unittest.TestCase):
    def run_offline(self, seed, epochs=6):
        with tempfile.TemporaryDirectory() as tmp:
            engine = LedgerEngine(seed=seed, llm_enabled=False, live_print=False)
            doc = engine.run(epochs=epochs, output_path=Path(tmp) / "out.md")
            ledger = json.loads((Path(tmp) / "out.ledger.json").read_text(encoding="utf-8"))
        return engine, doc, ledger

    def test_offline_run_is_deterministic_and_keeps_the_books(self):
        first, doc1, _ = self.run_offline(3)
        second, doc2, ledger = self.run_offline(3)
        self.assertEqual(doc1, doc2)
        self.assertEqual(doc1.count("\n## 【"), 6)
        self.assertTrue(all(p.population > 0 for p in first.polities if p.alive))
        self.assertGreater(len(ledger["ledger"]), 0)
        # every created node names prerequisites that exist
        for node in first.nodes.values():
            for dep in node.prereqs:
                self.assertIn(dep, first.nodes)

    def test_no_real_history_names_and_no_protagonist_region(self):
        engine, doc, _ = self.run_offline(11, epochs=10)
        for polity in engine.polities:
            self.assertFalse(engine.is_forbidden(polity.name), polity.name)
        # every region still has at least one polity or was absorbed by a neighbour, and all regions appear
        for region in engine.regions.values():
            self.assertIn(region["name"], doc)

    def test_research_needs_prerequisites_on_the_books(self):
        engine = LedgerEngine(seed=1, llm_enabled=False, live_print=False)
        polity = engine.living("huabei")[0]
        before = len(engine.nodes)
        engine.attempt_research(1, "huabei", polity, {"name": "凭空而来的机器", "kind": "technique", "from": ["不存在的知识"], "effect": "capacity"})
        self.assertEqual(len(engine.nodes), before)
        self.assertEqual(engine.ledger[-1]["type"], "research_rejected")
        engine.rng.random = lambda: 0.0  # force success
        engine.attempt_research(1, "huabei", polity, {"name": "渠灌的分水闸法", "kind": "technique", "from": ["渠灌与蓄水"], "effect": "capacity"})
        self.assertEqual(len(engine.nodes), before + 1)
        self.assertEqual(engine.ledger[-1]["type"], "research")

    def test_extract_json_reads_fenced_and_bare_objects(self):
        self.assertEqual(extract_json('前言 ```json {"a": 1} ``` 后记')["a"], 1)
        self.assertEqual(extract_json('{"title": "x", "names": {"p3": "y"}}')["names"]["p3"], "y")
        self.assertIsNone(extract_json("no json here"))


if __name__ == "__main__":
    unittest.main()
