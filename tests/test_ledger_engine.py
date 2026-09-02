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
                if self.calls > 3:
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
            # an era is one batched proposal call plus one chronicle call: era 1 fits in the 3-call budget, era 2 trips it
            self.assertEqual(checkpoint["eras_done"], 1)
            self.assertEqual(doc.count("\n## 【"), 1)
            self.assertEqual(max(e["era"] for e in engine.ledger), 1)

    def test_extract_json_reads_fenced_and_bare_objects(self):
        self.assertEqual(extract_json('前言 ```json {"a": 1} ``` 后记')["a"], 1)
        self.assertEqual(extract_json('{"title": "x", "names": {"p3": "y"}}')["names"]["p3"], "y")
        self.assertIsNone(extract_json("no json here"))


if __name__ == "__main__":
    unittest.main()



class LedgerReviewFixesTests(unittest.TestCase):
    def setUp(self):
        from ledger_engine import LedgerEngine
        self.engine = LedgerEngine(seed=3, llm_enabled=False, live_print=False)

    def test_world_reply_is_split_per_region_by_id_or_name(self):
        rids = ["huabei", "jianghuai"]
        reply = '{"regions": {"huabei": {"polities": {"a": {}}}, "长江流域": {"polities": {"b": {}}}, "nowhere": {"polities": {}}}}'
        parsed = self.engine._parse_world_reply(rids, reply)
        self.assertEqual(set(parsed), {"huabei", "jianghuai"})
        prompt = self.engine.world_proposal_prompt(rids, "第一纪")
        self.assertIn('"regions"', prompt)
        self.assertIn("huabei", prompt)

    def test_contact_epidemic_takes_its_toll_immediately(self):
        before = sum(p.population for p in self.engine.living("huabei"))
        self.engine.contact_epidemic(1, "huabei")
        after = sum(p.population for p in self.engine.living("huabei"))
        self.assertLess(after, before)
        self.assertEqual(self.engine.ledger[-1]["type"], "plague_toll")

    def test_rename_does_not_touch_ids_that_share_a_prefix(self):
        from ledger_engine import Polity
        self.engine._polity_counter = 11
        p1 = self.engine.polities[0]
        p1.needs_name = True
        p1.name = "@新政权1"
        self.engine.log(1, "note", "huabei", "p1 与 p12 同纪并起，@新政权1 未定")
        self.engine.rename(p1, "沣渭国")
        self.assertEqual(self.engine.ledger[-1]["text"], "沣渭国 与 p12 同纪并起，沣渭国 未定")

    def test_short_overlaps_no_longer_match(self):
        self.assertIsNone(self.engine.find_node_by_name("huabei", "水"))
        self.assertIsNone(self.engine.find_polity("国"))
        first = self.engine.living("huabei")[0]
        self.assertIs(self.engine.find_polity(first.name), first)

    def test_checkpoint_refuses_another_engine(self):
        import tempfile, pathlib
        from open_ledger_engine import OpenKnowledgeLedgerEngine
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "x.checkpoint.json"
            self.engine.save_checkpoint(path, 2)
            other = OpenKnowledgeLedgerEngine(seed=3, llm_enabled=False, live_print=False)
            with self.assertRaises(ValueError):
                other.load_checkpoint(path)
            self.assertEqual(self.engine.load_checkpoint(path), 2)
