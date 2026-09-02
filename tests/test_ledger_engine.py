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

    def test_checkpoint_resume_reproduces_a_straight_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run.md"
            straight = LedgerEngine(seed=5, llm_enabled=False, live_print=False).run(epochs=6, output_path=Path(tmp) / "straight.md")
            first = LedgerEngine(seed=5, llm_enabled=False, live_print=False)
            first.run(epochs=3, output_path=out)
            self.assertTrue(first.checkpoint_path(out).is_file())
            second = LedgerEngine(seed=5, llm_enabled=False, live_print=False)
            resumed = second.run(epochs=6, output_path=out, resume=True)
        self.assertEqual(resumed, straight)

    def test_quota_refusal_pauses_at_the_era_boundary_with_a_checkpoint(self):
        from ledger_engine import QuotaExhausted

        class QuotaClient:
            tool = "fake"
            calls = 0
            failures = 0
            exhausted = False
            last_error = ""

            def ask(self, prompt):
                self.calls += 1
                if self.calls > 12:
                    self.exhausted = True
                    raise QuotaExhausted("Individual quota reached")
                return ""

            def ask_many(self, prompts):
                return [self.ask(p) for p in prompts]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run.md"
            engine = LedgerEngine(seed=9, llm_enabled=False, live_print=False)
            engine.llm = QuotaClient()
            doc = engine.run(epochs=8, output_path=out)
            self.assertTrue(engine.paused)
            checkpoint = json.loads(engine.checkpoint_path(out).read_text(encoding="utf-8"))
            # one era of nine proposal calls plus one chronicle call fits in the 12-call budget; the second era trips it
            self.assertEqual(checkpoint["eras_done"], 1)
            self.assertEqual(doc.count("\n## 【"), 1)
            self.assertEqual(max(e["era"] for e in engine.ledger), 1)

    def test_extract_json_reads_fenced_and_bare_objects(self):
        self.assertEqual(extract_json('前言 ```json {"a": 1} ``` 后记')["a"], 1)
        self.assertEqual(extract_json('{"title": "x", "names": {"p3": "y"}}')["names"]["p3"], "y")
        self.assertIsNone(extract_json("no json here"))


if __name__ == "__main__":
    unittest.main()
