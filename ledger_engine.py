"""Ledger engine: the mechanics decide what happens, the model only proposes and narrates.

The open-world prompt mode asked a language model to "simulate" two thousand years, and
the model did what a model does: it wrote the history it already knew, renamed and moved
forward a millennium. This engine takes the decision away from it. A seeded random number
generator and a small set of explicit rules (all rates in ledger_config.json) settle
climate, plague, harvests, wars, the survival of every polity and whether a piece of
knowledge can grow. The model is asked two things per era: what each region's polities
intend to do, and how to write the settled ledger as a chronicle. It never decides an
outcome, and it cannot introduce a technology whose prerequisites are not on the books.

Every macro-region (Yellow River, Yangtze, the steppe, Central Asia, India, West Asia and
the Mediterranean, Africa, the Americas) runs under the same rules and the same state
format, so no region is the protagonist by construction.
"""

from __future__ import annotations

import concurrent.futures
import json
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

CONFIG_PATH = Path(__file__).with_name("ledger_config.json")

EFFECT_BONUS_KEY = {
    "capacity": "capacity_bonus",
    "military": "military_bonus",
    "trade": "trade_bonus",
    "literacy": "literacy_bonus",
    "research": "research_bonus",
    "health": "health_bonus",
    "navigation": "navigation",
}

NAME_SYLLABLES = "沩澶洎沔漭湲汭浍溱涢淇澧沣渭泾灞浐涑沁潞澹漪泠汾漳滹溵洮洹淦浯"
NAME_SUFFIXES = ["国", "邦", "联盟", "王廷", "城邦同盟", "教团", "都护", "侯国"]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class Node:
    id: str
    name: str
    kind: str
    prereqs: List[str]
    origin: str
    era: int
    bonuses: Dict[str, float] = field(default_factory=dict)


@dataclass
class Polity:
    id: str
    name: str
    region: str
    population: float
    share: float
    fiscal: float
    cohesion: float
    military: float
    legitimacy: float
    institutions: List[str]
    age: int = 0
    founded_era: int = 0
    alive: bool = True
    lineage: List[str] = field(default_factory=list)
    at_war: bool = False
    needs_name: bool = False


class QuotaExhausted(RuntimeError):
    """The model provider refused for lack of quota; the run should pause, not degrade."""


class LLMClient:
    """One call to the locally authenticated agy (or claude / codex) in print mode.

    A transient failure is retried once. A quota refusal is different: every further call
    would fail the same way, so the client marks itself exhausted and raises, and the engine
    stops at the era boundary with a checkpoint instead of filling the rest of history with
    template text.
    """

    def __init__(self, cfg: Dict[str, Any], enabled: bool = True):
        self.tool = cfg.get("tool", "agy") if enabled else None
        self.model = cfg.get("model", "gemini-3.7-flash-high")
        self.timeout = int(cfg.get("timeout_seconds", 180))
        self.max_parallel = int(cfg.get("max_parallel_calls", 4))
        if self.tool and not shutil.which(self.tool):
            self.tool = None
        self.calls = 0
        self.failures = 0
        self.exhausted = False
        self.last_error = ""

    def ask(self, prompt: str) -> str:
        if not self.tool:
            return ""
        if self.exhausted:
            raise QuotaExhausted(self.last_error)
        text = self._ask_once(prompt)
        if not text and not self.exhausted:
            time.sleep(8)
            text = self._ask_once(prompt)
        return text

    def _ask_once(self, prompt: str) -> str:
        if self.tool == "agy":
            cmd = ["agy", "--model", self.model, "--disable-slash-commands",
                   "--output-format", "json", "-p", prompt]
        elif self.tool == "claude":
            cmd = ["claude", "-p", prompt, "--output-format", "json"]
        else:
            cmd = ["codex", "exec", prompt]
        self.calls += 1
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        except Exception:
            self.failures += 1
            return ""
        if not res.stdout.strip():
            self.failures += 1
            return ""
        if res.returncode != 0:
            self.failures += 1
            try:
                payload = json.loads(res.stdout.strip())
                error = str(payload.get("error") or "")
                if error and "quota" in error.lower():
                    self.exhausted = True
                    self.last_error = error
                    raise QuotaExhausted(error)
            except json.JSONDecodeError:
                pass
            return ""
        text = res.stdout.strip()
        if self.tool in ("agy", "claude"):
            try:
                payload = json.loads(text)
                error = str(payload.get("error") or "")
                if error and "quota" in error.lower():
                    self.exhausted = True
                    self.last_error = error
                    self.failures += 1
                    raise QuotaExhausted(error)
                text = str(payload.get("response") or payload.get("result") or "")
            except json.JSONDecodeError:
                pass
        return text.strip()

    def ask_many(self, prompts: Sequence[str]) -> List[str]:
        if not self.tool or not prompts:
            return ["" for _ in prompts]
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
            return list(pool.map(self.ask, prompts))


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Find the first JSON object in a model reply, fenced or bare."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    if start != -1:
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:index + 1])
                    break
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None


class LedgerEngine:
    def __init__(
        self,
        seed: int = 2026,
        config_path: Path = CONFIG_PATH,
        llm_enabled: bool = True,
        live_print: bool = True,
    ):
        self.cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.seed = seed
        self.rng = random.Random(seed)
        self.live_print = live_print
        self.llm = LLMClient(self.cfg.get("llm", {}), enabled=llm_enabled)
        self.rates = self.cfg["rates"]
        self.forbidden = list(self.cfg.get("forbidden_names", []))
        self.eras: List[Tuple[str, int, int]] = [tuple(e) for e in self.cfg["eras"]]
        self.regions: Dict[str, Dict[str, Any]] = {}
        self.nodes: Dict[str, Node] = {}
        self.polities: List[Polity] = []
        self.ledger: List[Dict[str, Any]] = []
        self.chronicle: List[str] = []
        self.stats = {"llm_proposals": 0, "heuristic_proposals": 0, "llm_chronicles": 0,
                      "template_chronicles": 0, "nodes_created": 0, "nodes_lost": 0,
                      "polities_born": 0, "polities_ended": 0}
        self._polity_counter = 0
        self._node_counter = 0
        self._genesis()

    # ------------------------------------------------------------------ setup
    def _genesis(self) -> None:
        for rid, rcfg in self.cfg["regions"].items():
            self.regions[rid] = {
                "id": rid,
                "name": rcfg["name"],
                "cfg": rcfg,
                "knowledge": set(),
                "urban": 0.04,
                "literacy": 0.03,
                "climate": 0.0,
                "plague": False,
                "links": set(),
                "contacts": set(rcfg.get("neighbors", [])),
                "famine": False,
            }
        for nid, ncfg in self.cfg["seed_nodes"].items():
            bonuses = {k: v for k, v in ncfg.items() if k.endswith("_bonus")}
            self.nodes[nid] = Node(nid, ncfg["name"], ncfg["kind"], list(ncfg.get("prereqs", [])),
                                   "seed", 0, bonuses)
        for rid, ids in self.cfg["initial_knowledge"].items():
            self.regions[rid]["knowledge"].update(ids)
        for pcfg in self.cfg["initial_polities"]:
            self._polity_counter += 1
            self.polities.append(Polity(
                id=f"p{self._polity_counter}", name=pcfg["name"], region=pcfg["region"],
                population=float(pcfg["population"]), share=float(pcfg["share"]),
                fiscal=pcfg["fiscal"], cohesion=pcfg["cohesion"], military=pcfg["military"],
                legitimacy=pcfg["legitimacy"], institutions=list(pcfg.get("institutions", [])),
            ))

    # --------------------------------------------------------------- helpers
    def living(self, region: Optional[str] = None) -> List[Polity]:
        return [p for p in self.polities if p.alive and (region is None or p.region == region)]

    def region_bonus(self, rid: str, key: str) -> float:
        return sum(self.nodes[n].bonuses.get(key, 0.0) for n in sorted(self.regions[rid]["knowledge"]) if n in self.nodes)

    def region_capacity(self, rid: str) -> float:
        region = self.regions[rid]
        base = float(region["cfg"]["base_capacity"])
        bonus = self.region_bonus(rid, "capacity_bonus")
        swing = self.rates["climate_capacity_swing"] * region["climate"]
        return max(1.0, base * (1.0 + bonus) * (1.0 + swing))

    def region_population(self, rid: str) -> float:
        return sum(p.population for p in self.living(rid))

    def is_forbidden(self, name: str) -> bool:
        return any(bad in name for bad in self.forbidden)

    def invent_name(self, rid: str) -> str:
        for _ in range(20):
            core = "".join(self.rng.choice(NAME_SYLLABLES) for _ in range(2))
            name = core + self.rng.choice(NAME_SUFFIXES)
            if not any(p.name == name for p in self.polities):
                return name
        return f"{self.regions[rid]['name']}新政权{self._polity_counter}"

    def new_polity(self, rid: str, era: int, population: float, share: float,
                   parent: Optional[Polity], reason: str) -> Polity:
        self._polity_counter += 1
        pol = Polity(
            id=f"p{self._polity_counter}", name=f"@新政权{self._polity_counter}", region=rid,
            population=max(0.05, population), share=clamp(share, 0.02, 1.0),
            fiscal=0.45, cohesion=0.6, military=0.45, legitimacy=0.5,
            institutions=list(parent.institutions[-2:]) if parent else [],
            founded_era=era, lineage=(parent.lineage + [parent.name]) if parent else [],
            needs_name=True,
        )
        self.polities.append(pol)
        self.stats["polities_born"] += 1
        self.log(era, "polity_born", rid, f"{reason}，{self.regions[rid]['name']}出现新政权 {pol.id}",
                 polity=pol.id, parent=parent.name if parent else None)
        return pol

    def log(self, era: int, kind: str, region: Optional[str], text: str, **extra: Any) -> None:
        entry = {"era": era, "type": kind, "region": region, "text": text}
        entry.update(extra)
        self.ledger.append(entry)

    # ------------------------------------------------------------ era steps
    def exogenous(self, era: int) -> None:
        rates = self.rates
        for rid, region in self.regions.items():
            sens = float(region["cfg"]["climate_sensitivity"])
            region["climate"] = clamp(self.rng.gauss(0.0, 0.6) * sens, -1.0, 1.0)
            if abs(region["climate"]) > 0.6:
                mood = "持续偏冷干旱" if region["climate"] < 0 else "持续温暖湿润"
                self.log(era, "climate", rid, f"{region['name']}本纪气候{mood}", value=round(region["climate"], 2))
            p_plague = rates["epidemic_base"] + rates["epidemic_per_urban"] * region["urban"] \
                + rates["epidemic_per_link"] * len(region["links"])
            region["plague"] = self.rng.random() < p_plague
            if region["plague"]:
                self.log(era, "plague", rid, f"{region['name']}爆发大疫")
        # plague spreads along links
        for rid, region in list(self.regions.items()):
            if region["plague"]:
                for other in sorted(region["links"]):
                    if not self.regions[other]["plague"] and self.rng.random() < rates["epidemic_spread"]:
                        self.regions[other]["plague"] = True
                        self.log(era, "plague", other, f"疫病沿商路传入{self.regions[other]['name']}", source=rid)

    def observable_state(self, rid: str) -> Dict[str, Any]:
        region = self.regions[rid]
        pols = []
        for p in self.living(rid):
            pols.append({
                "name": p.name, "population_millions": round(p.population, 2), "territory_share": round(p.share, 2),
                "fiscal": round(p.fiscal, 2), "cohesion": round(p.cohesion, 2), "military": round(p.military, 2),
                "legitimacy": round(p.legitimacy, 2), "institutions": p.institutions[-6:], "age_eras": p.age,
            })
        neighbours = []
        for other in sorted(region["contacts"] | region["links"]):
            o = self.regions[other]
            neighbours.append({
                "region": o["name"],
                "polities": [{"name": p.name, "military": round(p.military, 2), "population_millions": round(p.population, 1)} for p in self.living(other)],
                "trade_link": other in region["links"],
            })
        return {
            "region": region["name"],
            "climate": "偏冷干旱" if region["climate"] < -0.3 else ("温暖湿润" if region["climate"] > 0.3 else "平常"),
            "plague": region["plague"],
            "carrying_capacity_millions": round(self.region_capacity(rid), 1),
            "population_millions": round(self.region_population(rid), 1),
            "urbanization": round(region["urban"], 2),
            "literacy": round(region["literacy"], 2),
            "knowledge": [self.nodes[n].name for n in sorted(region["knowledge"]) if n in self.nodes],
            "polities": pols,
            "neighbours": neighbours,
        }

    def proposal_schema_text(self) -> str:
        """The JSON shape one region's council must answer with (the research menu variant)."""
        return (
            '{"polities": {"<政权名>": {'
            '"research": [{"name": "<新知识的描述性名称>", "kind": "observation|principle|technique", '
            '"from": ["<所依赖的已有知识名>", "..."], "effect": "capacity|military|trade|literacy|research|health|navigation"}], '
            '"reform": {"name": "<制度名>", "target": "fiscal|cohesion|legitimacy|military"} 或 null, '
            '"war": {"target": "<邻近政权名>", "aim": "<目的>"} 或 null, '
            '"build": "irrigation|roads|ports|walls|none"}}}'
        )

    def proposal_rules_text(self) -> str:
        return (
            "规则：研究只能从 knowledge 列表里已有的知识长出来，from 必须写已有的名字，写不出依赖就不要提；"
            "每个政权最多三项研究；知识名要按它解决的问题和用的材料来描述，不得使用真实历史上出现过的技术名、人名、地名与朝代名；"
            "战争目标只能是本区域或相邻区域里存在的政权；不必让每个政权都开战或都研究，穷弱的政权可以只求生存。"
        )

    def proposal_prompt(self, rid: str, era_label: str) -> str:
        state = self.observable_state(rid)
        return (
            f"你是【{state['region']}】各政权的决策议事会，时间是{era_label}。下面是本纪开始时你们能观察到的状态：\n"
            f"{json.dumps(state, ensure_ascii=False, indent=1)}\n\n"
            "为每个政权写出本纪的意图。只输出一个 JSON 对象，不要任何解释：\n"
            f"{self.proposal_schema_text()}\n\n{self.proposal_rules_text()}"
        )

    def world_proposal_prompt(self, rids: Sequence[str], era_label: str) -> str:
        """One prompt for every region at once.

        A run used to make one model call per region per era, ten per era with the
        chronicle, 230 for the whole history; twice in one day the provider's quota ran
        out at era 13. Each region's council still sees only its own observable state and
        answers for itself, but all nine answers come back in one reply, so an era costs
        two calls and the whole history fits comfortably inside one quota window.
        """
        states = {rid: self.observable_state(rid) for rid in rids}
        return (
            f"时间是{era_label}。下面是本纪开始时各区域议事会各自能观察到的状态，键是区域代号：\n"
            f"{json.dumps(states, ensure_ascii=False, indent=1)}\n\n"
            "你要依次扮演每一个区域各政权的决策议事会，只根据该区域自己的状态与邻区情报替它们写本纪意图；"
            "各区域互不知道对方议事会的决定。只输出一个 JSON 对象，不要任何解释，形状是 "
            '{"regions": {"<区域代号>": ' + self.proposal_schema_text() + "}}。\n"
            "每个区域的键必须与上面的区域代号完全一致。\n\n" + self.proposal_rules_text()
        )

    def _parse_world_reply(self, rids: Sequence[str], reply: str) -> Dict[str, Dict[str, Any]]:
        parsed = extract_json(reply)
        regions = parsed.get("regions") if isinstance(parsed, dict) else None
        if not isinstance(regions, dict):
            return {}
        by_name = {self.regions[rid]["name"]: rid for rid in rids}
        out: Dict[str, Dict[str, Any]] = {}
        for key, value in regions.items():
            rid = key if key in self.regions else by_name.get(str(key))
            if rid in rids and isinstance(value, dict) and isinstance(value.get("polities"), dict):
                out[rid] = value
        return out

    def heuristic_proposal(self, rid: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {"polities": {}}
        known = [self.nodes[n] for n in sorted(self.regions[rid]["knowledge"]) if n in self.nodes]
        for p in self.living(rid):
            research = []
            if known and self.rng.random() < 0.7:
                base = self.rng.choice(known)
                effect = self.rng.choice(["capacity", "military", "trade", "literacy", "research", "health"])
                research.append({"name": f"{base.name}的改良用法（{self.regions[rid]['name']}）", "kind": "technique",
                                 "from": [base.name], "effect": effect})
            war = None
            others = [q for q in self.living() if q.id != p.id and (q.region == rid or q.region in self.regions[rid]["contacts"])]
            if others and p.military > 0.55 and self.rng.random() < 0.3:
                war = {"target": self.rng.choice(others).name, "aim": "兼并"}
            reform = None
            weakest = min(("fiscal", "cohesion", "legitimacy", "military"), key=lambda k: getattr(p, k))
            if self.rng.random() < 0.5:
                reform = {"name": f"整饬{weakest}", "target": weakest}
            out["polities"][p.name] = {"research": research, "reform": reform, "war": war,
                                       "build": self.rng.choice(["irrigation", "roads", "ports", "walls", "none"])}
        return out

    def collect_proposals(self, era: int, era_label: str) -> Dict[str, Dict[str, Any]]:
        rids = [rid for rid in self.regions if self.living(rid)]
        proposals: Dict[str, Dict[str, Any]] = {}
        if self.cfg.get("llm", {}).get("batch_regions", True):
            answered = self._parse_world_reply(rids, self.llm.ask(self.world_proposal_prompt(rids, era_label))) if self.llm.tool else {}
            for rid in rids:
                if rid in answered:
                    proposals[rid] = answered[rid]
                    self.stats["llm_proposals"] += 1
                else:
                    proposals[rid] = self.heuristic_proposal(rid)
                    self.stats["heuristic_proposals"] += 1
            return proposals
        prompts = [self.proposal_prompt(rid, era_label) for rid in rids]
        replies = self.llm.ask_many(prompts)
        for rid, reply in zip(rids, replies):
            parsed = extract_json(reply)
            if parsed and isinstance(parsed.get("polities"), dict):
                proposals[rid] = parsed
                self.stats["llm_proposals"] += 1
            else:
                proposals[rid] = self.heuristic_proposal(rid)
                self.stats["heuristic_proposals"] += 1
        return proposals

    # A one-character overlap used to count as a match, which made "the prerequisite must
    # be on the books" and "the war target must exist" nearly meaningless.
    MIN_PARTIAL_MATCH = 3

    def find_node_by_name(self, rid: str, name: str) -> Optional[Node]:
        name = name.strip()
        if not name:
            return None
        known = [self.nodes[nid] for nid in sorted(self.regions[rid]["knowledge"]) if nid in self.nodes]
        for node in known:
            if node.name == name:
                return node
        partial = [
            node for node in known
            if min(len(name), len(node.name)) >= self.MIN_PARTIAL_MATCH
            and (name in node.name or node.name in name)
        ]
        if len(partial) == 1:
            return partial[0]
        return None

    def find_polity(self, name: str) -> Optional[Polity]:
        name = (name or "").strip()
        if not name:
            return None
        for p in self.living():
            if p.name == name:
                return p
        partial = [
            p for p in self.living()
            if min(len(name), len(p.name)) >= self.MIN_PARTIAL_MATCH - 1
            and (name in p.name or p.name in name)
        ]
        if len(partial) == 1:
            return partial[0]
        return None

    def resolve(self, era: int, proposals: Dict[str, Dict[str, Any]]) -> None:
        rates = self.rates
        for p in self.living():
            p.at_war = False
        # 1. reforms, builds, research, wars declared
        wars: List[Tuple[Polity, Polity, str]] = []
        for rid, proposal in proposals.items():
            for pname, intent in proposal.get("polities", {}).items():
                p = self.find_polity(pname)
                if p is None or p.region != rid or not isinstance(intent, dict):
                    continue
                reform = intent.get("reform")
                if isinstance(reform, dict) and reform.get("target") in ("fiscal", "cohesion", "legitimacy", "military"):
                    target = reform["target"]
                    setattr(p, target, clamp(getattr(p, target) + 0.08))
                    p.fiscal = clamp(p.fiscal - 0.03)
                    label = str(reform.get("name") or f"整饬{target}")[:20]
                    if not self.is_forbidden(label):
                        p.institutions = (p.institutions + [label])[-6:]
                    self.log(era, "reform", rid, f"{p.name}推行「{label}」", polity=p.id, target=target)
                build = intent.get("build")
                if build in ("irrigation", "roads", "ports", "walls") and p.fiscal > 0.3:
                    p.fiscal = clamp(p.fiscal - 0.04)
                    region = self.regions[rid]
                    if build == "irrigation":
                        region["cfg"]["base_capacity"] = float(region["cfg"]["base_capacity"]) * 1.02
                    elif build == "ports" and region["cfg"].get("coast"):
                        region["urban"] = clamp(region["urban"] + 0.02)
                    elif build == "roads":
                        region["urban"] = clamp(region["urban"] + 0.01)
                    elif build == "walls":
                        p.military = clamp(p.military + 0.03)
                    self.log(era, "build", rid, f"{p.name}大兴{build}", polity=p.id, build=build)
                for item in (intent.get("research") or [])[:3]:
                    if isinstance(item, dict):
                        self.attempt_research(era, rid, p, item)
                war = intent.get("war")
                if isinstance(war, dict) and war.get("target"):
                    target = self.find_polity(str(war["target"]))
                    if target and target.id != p.id and (target.region == rid or target.region in self.regions[rid]["contacts"] | self.regions[rid]["links"]):
                        wars.append((p, target, str(war.get("aim") or "兼并")[:30]))
        for attacker, defender, aim in wars:
            self.resolve_war(era, attacker, defender, aim)
        # 2. harvest, plague, growth
        for rid, region in self.regions.items():
            capacity = self.region_capacity(rid)
            pols = self.living(rid)
            total_share = sum(p.share for p in pols) or 1.0
            region["famine"] = False
            for p in pols:
                cap = capacity * (p.share / total_share)
                if p.population > cap * 1.05:
                    loss = (p.population - cap) * 0.5
                    p.population -= loss
                    region["famine"] = True
                    p.cohesion = clamp(p.cohesion - 0.08)
                    self.log(era, "famine", rid, f"{p.name}粮不足食，饥荒减口约{loss:.1f}百万", polity=p.id)
                if region["plague"]:
                    lo, hi = rates["epidemic_mortality"]
                    mortality = lo + (hi - lo) * clamp(region["urban"] * 3)
                    dead = p.population * mortality
                    p.population -= dead
                    p.fiscal = clamp(p.fiscal - 0.06)
                    self.log(era, "plague_toll", rid, f"{p.name}疫死约{dead:.1f}百万", polity=p.id)
                growth = rates["pop_growth_base"] * (1.0 - p.population / max(cap, 0.1))
                health = self.region_bonus(rid, "health_bonus")
                p.population = max(0.02, p.population * (1.0 + growth + health * 0.3))
        # 3. recovery, ageing, stress, lifecycle
        for p in list(self.living()):
            region = self.regions[p.region]
            if not p.at_war:
                p.fiscal = clamp(p.fiscal + rates["fiscal_recovery"] * (1 - p.fiscal))
                p.cohesion = clamp(p.cohesion + rates["cohesion_recovery"] * (1 - p.cohesion))
            p.legitimacy = clamp(p.legitimacy - rates["legitimacy_decay"] * (0.5 + p.age / 8))
            p.age += 1
            stress = (rates["stress_fiscal_weight"] * (1 - p.fiscal) + rates["stress_cohesion_weight"] * (1 - p.cohesion)
                      + rates["stress_legitimacy_weight"] * (1 - p.legitimacy) + rates["sclerosis_per_era"] * p.age)
            if region["famine"]:
                stress += rates["stress_famine"]
            if region["plague"]:
                stress += rates["stress_plague"]
            if getattr(p, "_defeated", False):
                stress += rates["stress_defeat"]
                p._defeated = False  # type: ignore[attr-defined]
            if stress > rates["collapse_threshold"]:
                prob = clamp((stress - rates["collapse_threshold"]) * rates["collapse_probability_scale"], 0.0, 0.9)
                if self.rng.random() < prob:
                    self.collapse(era, p, stress)
        # 3b. consolidation: statelets too small to hold a court are absorbed by the strongest neighbour
        for rid in self.regions:
            pols = self.living(rid)
            if len(pols) < 2:
                continue
            strongest = max(pols, key=lambda q: q.military * (0.5 + q.share))
            for q in pols:
                if q.id != strongest.id and q.share < rates["absorb_share_below"] and self.rng.random() < rates["absorb_probability"]:
                    self.log(era, "absorbed", rid, f"{q.name}地狭民贫，为{strongest.name}所并", polity=q.id, conqueror=strongest.id)
                    self.end_polity(era, q, f"为{strongest.name}所并", conqueror=strongest)
        # 4. urbanisation and literacy from the books
        for rid, region in self.regions.items():
            pop = self.region_population(rid)
            cap = self.region_capacity(rid)
            surplus = clamp((cap - pop) / max(cap, 0.1))
            trade_nodes = self.region_bonus(rid, "trade_bonus")
            region["urban"] = clamp(0.03 + 0.02 * len(region["links"]) + 0.5 * trade_nodes + 0.06 * surplus
                                    + 0.02 * sum(1 for p in self.living(rid) if p.fiscal > 0.6))
            region["literacy"] = clamp(0.02 + self.region_bonus(rid, "literacy_bonus")
                                       + 0.005 * sum(len(p.institutions) for p in self.living(rid)))
        # 5. trade links, contact, diffusion
        self.trade_and_diffusion(era)

    def attempt_research(self, era: int, rid: str, p: Polity, item: Dict[str, Any]) -> None:
        rates = self.rates
        region = self.regions[rid]
        name = str(item.get("name") or "").strip()[:30]
        if not name or self.is_forbidden(name):
            return
        if any(n.name == name for n in self.nodes.values()):
            return
        deps = [d for d in (item.get("from") or []) if isinstance(d, str)]
        resolved = [self.find_node_by_name(rid, d) for d in deps]
        if not deps or any(r is None for r in resolved):
            self.log(era, "research_rejected", rid, f"{p.name}想要「{name}」，但所需前置知识不在本区域账上",
                     polity=p.id, missing=[d for d, r in zip(deps, resolved) if r is None])
            return
        prob = rates["research_base"] * (0.5 + rates["research_urban_weight"] * region["urban"]
                                          + rates["research_literacy_weight"] * region["literacy"]
                                          + rates["research_fiscal_weight"] * p.fiscal
                                          + self.region_bonus(rid, "research_bonus"))
        if p.at_war:
            prob *= rates["research_war_penalty"]
        if self.rng.random() >= prob:
            self.log(era, "research_failed", rid, f"{p.name}探索「{name}」未得要领", polity=p.id)
            return
        self._node_counter += 1
        kind = item.get("kind") if item.get("kind") in ("observation", "principle", "technique") else "technique"
        effect = item.get("effect") if item.get("effect") in EFFECT_BONUS_KEY else "research"
        bonuses: Dict[str, float] = {}
        if kind == "technique" and effect != "navigation":
            size = rates["capacity_per_node_default"] if effect == "capacity" else rates["other_bonus_per_node"]
            bonuses[EFFECT_BONUS_KEY[effect]] = size
        elif effect == "navigation":
            bonuses["navigation"] = 1.0
            bonuses["trade_bonus"] = rates["capacity_per_node_default"]
        elif kind == "principle":
            bonuses["research_bonus"] = rates["capacity_per_node_default"] / 2
        node = Node(f"n{self._node_counter}", name, kind, [r.id for r in resolved if r], rid, era, bonuses)
        self.nodes[node.id] = node
        region["knowledge"].add(node.id)
        self.stats["nodes_created"] += 1
        self.log(era, "research", rid, f"{p.name}得「{name}」（{kind}，源自{'、'.join(r.name for r in resolved if r)}）",
                 polity=p.id, node=node.id, effect=effect)

    def resolve_war(self, era: int, attacker: Polity, defender: Polity, aim: str) -> None:
        rates = self.rates
        if not (attacker.alive and defender.alive):
            return
        attacker.at_war = defender.at_war = True
        prob = rates["war_base_probability"] + (attacker.military - defender.military)
        if attacker.region != defender.region:
            prob -= rates["war_logistics_penalty"]
        prob -= rates["war_defender_bonus"] * float(self.regions[defender.region]["cfg"]["terrain_defense"])
        prob = clamp(prob, 0.05, 0.9)
        lo, hi = rates["war_population_loss"]
        loss_a = attacker.population * self.rng.uniform(lo, hi)
        loss_d = defender.population * self.rng.uniform(lo, hi)
        attacker.population -= loss_a
        defender.population -= loss_d
        attacker.fiscal = clamp(attacker.fiscal - 0.1)
        defender.fiscal = clamp(defender.fiscal - 0.06)
        if self.rng.random() < prob:
            gain = defender.share * rates["conquest_share_gain"]
            if attacker.region == defender.region:
                attacker.share = clamp(attacker.share + gain, 0.02, 1.0)
            defender.share = clamp(defender.share - gain, 0.0, 1.0)
            moved = defender.population * rates["conquest_share_gain"]
            defender.population -= moved
            attacker.population += moved
            attacker.legitimacy = clamp(attacker.legitimacy + 0.05)
            defender.cohesion = clamp(defender.cohesion - 0.15)
            defender._defeated = True  # type: ignore[attr-defined]
            self.log(era, "war", attacker.region, f"{attacker.name}为{aim}攻{defender.name}，获胜，夺其半壁",
                     attacker=attacker.id, defender=defender.id, outcome="attacker_won")
            if defender.share < 0.05 or defender.population < 0.1:
                self.end_polity(era, defender, f"被{attacker.name}吞并", conqueror=attacker)
        else:
            attacker.military = clamp(attacker.military - 0.1)
            attacker.cohesion = clamp(attacker.cohesion - 0.1)
            attacker._defeated = True  # type: ignore[attr-defined]
            defender.military = clamp(defender.military + 0.03)
            self.log(era, "war", attacker.region, f"{attacker.name}为{aim}攻{defender.name}，师老无功而返",
                     attacker=attacker.id, defender=defender.id, outcome="defender_held")

    def end_polity(self, era: int, p: Polity, reason: str, conqueror: Optional[Polity] = None) -> None:
        p.alive = False
        self.stats["polities_ended"] += 1
        if conqueror is not None and conqueror.region == p.region:
            conqueror.share = clamp(conqueror.share + p.share, 0.02, 1.0)
            conqueror.population += p.population
        self.log(era, "polity_end", p.region, f"{p.name}亡，{reason}", polity=p.id, conqueror=conqueror.id if conqueror else None)

    def collapse(self, era: int, p: Polity, stress: float) -> None:
        rates = self.rates
        region = self.regions[p.region]
        rivals = [q for q in self.living(p.region) if q.id != p.id and q.military > p.military + 0.1]
        roll = self.rng.random()
        if rivals and roll < 0.35:
            winner = max(rivals, key=lambda q: q.military)
            self.log(era, "collapse", p.region, f"{p.name}财政与人心俱溃（压力{stress:.2f}），被{winner.name}趁势兼并", polity=p.id)
            self.end_polity(era, p, "崩溃后被兼并", conqueror=winner)
        elif roll < 0.8:
            pieces = self.rng.randint(2, 3) if p.share > 0.5 else 2
            self.log(era, "collapse", p.region, f"{p.name}解体为{pieces}个政权（压力{stress:.2f}）", polity=p.id, pieces=pieces)
            shares = [self.rng.random() + 0.3 for _ in range(pieces)]
            total = sum(shares)
            for s in shares:
                self.new_polity(p.region, era, p.population * s / total, p.share * s / total, p, f"{p.name}解体")
            self.end_polity(era, p, "解体")
        else:
            self.log(era, "collapse", p.region, f"{p.name}旧统绝嗣，为新的教团或军事集团所取代（压力{stress:.2f}）", polity=p.id)
            heir = self.new_polity(p.region, era, p.population, p.share, p, f"{p.name}旧统被取代")
            heir.military = clamp(p.military + 0.05)
            self.end_polity(era, p, "被新集团取代")
        # knowledge can be lost when the state that kept the books goes down
        if region["knowledge"] and self.rng.random() < rates["knowledge_loss_on_collapse"] * p.share:
            candidates = [n for n in sorted(region["knowledge"]) if self.nodes[n].origin != "seed"]
            if candidates:
                lost = self.rng.choice(candidates)
                region["knowledge"].discard(lost)
                self.stats["nodes_lost"] += 1
                self.log(era, "knowledge_lost", p.region, f"「{self.nodes[lost].name}」随{p.name}的簿册一同散佚", node=lost)

    def trade_and_diffusion(self, era: int) -> None:
        rates = self.rates
        for rid, region in self.regions.items():
            trade = self.region_bonus(rid, "trade_bonus")
            for other in sorted(region["contacts"]):
                if other not in region["links"] and self.rng.random() < rates["trade_link_probability"] * (0.5 + trade * 3):
                    region["links"].add(other)
                    self.regions[other]["links"].add(rid)
                    self.log(era, "trade_link", rid, f"{region['name']}与{self.regions[other]['name']}之间形成稳定商路", other=other)
            # deep-sea contact with regions not adjacent
            if self.region_bonus(rid, "navigation") > 0 and region["cfg"].get("coast"):
                for other, ocfg in self.regions.items():
                    if other == rid or other in region["contacts"] or not ocfg["cfg"].get("coast"):
                        continue
                    if self.rng.random() < rates["ocean_contact_probability"] * 3:
                        region["contacts"].add(other)
                        ocfg["contacts"].add(rid)
                        region["links"].add(other)
                        ocfg["links"].add(rid)
                        self.log(era, "contact", rid, f"{region['name']}的远洋船队抵达{ocfg['name']}，两地首次接触，病原与技术开始双向交换", other=other)
                        # Setting the plague flag here did nothing: the toll is taken in
                        # the harvest step, which has already run, and the next era's
                        # exogenous roll overwrote the flag. Settle the exchange now.
                        for side in (rid, other):
                            if self.rng.random() < 0.6:
                                self.contact_epidemic(era, side)
        # diffusion along links, only where prerequisites already exist
        for rid, region in self.regions.items():
            for other in sorted(region["links"]):
                target = self.regions[other]
                for nid in sorted(region["knowledge"] - target["knowledge"]):
                    node = self.nodes.get(nid)
                    if node is None or not all(pr in target["knowledge"] for pr in node.prereqs):
                        continue
                    prob = rates["diffusion_base"] * (1 + rates["diffusion_trade_weight"] * self.region_bonus(other, "trade_bonus") * 5)
                    if self.rng.random() < prob:
                        target["knowledge"].add(nid)
                        self.log(era, "diffusion", other, f"「{node.name}」自{region['name']}传入{target['name']}", node=nid, source=rid)

    def contact_epidemic(self, era: int, rid: str) -> None:
        """A pathogen carried by first ocean contact: a virgin-soil epidemic, settled at once."""
        lo, hi = self.rates["epidemic_mortality"]
        region = self.regions[rid]
        mortality = min(hi * 1.5, hi + (hi - lo) * 0.5)  # no acquired resistance at all
        for p in self.living(rid):
            dead = p.population * mortality
            p.population = max(0.02, p.population - dead)
            p.fiscal = clamp(p.fiscal - 0.05)
            p.cohesion = clamp(p.cohesion - 0.05)
            self.log(era, "plague_toll", rid, f"远洋接触带来的疫病在{p.name}蔓延，疫死约{dead:.1f}百万", polity=p.id, source="contact")
        region["plague"] = True

    # ------------------------------------------------------------ narration
    def era_summary(self, era: int) -> Dict[str, Any]:
        world_pop = sum(p.population for p in self.living()) or 1.0
        regions = []
        for rid, region in self.regions.items():
            pols = self.living(rid)
            regions.append({
                "region": region["name"],
                "population_millions": round(self.region_population(rid), 1),
                "population_share_of_world": round(self.region_population(rid) / world_pop, 2),
                "polities": [{"name": p.name, "population_millions": round(p.population, 1), "share": round(p.share, 2),
                              "military": round(p.military, 2), "fiscal": round(p.fiscal, 2), "institutions": p.institutions[-4:]} for p in pols],
                "knowledge": [self.nodes[n].name for n in sorted(region["knowledge"]) if n in self.nodes],
                "urbanization": round(region["urban"], 2), "literacy": round(region["literacy"], 2),
                "trade_links": [self.regions[o]["name"] for o in sorted(region["links"])],
            })
        return {"world_population_millions": round(world_pop, 1), "regions": regions}

    def chronicle_prompt(self, era: int, era_label: str, events: List[Dict[str, Any]], placeholders: List[Polity]) -> str:
        summary = self.era_summary(era)
        names_needed = {p.id: f"{self.regions[p.region]['name']}，脱胎于{p.lineage[-1] if p.lineage else '旧部'}" for p in placeholders}
        return (
            f"你是这部开放世界通史的史官。这是第 {era} 纪（{era_label}）已经结算完毕的账本：\n"
            f"【事件】\n{json.dumps([{k: v for k, v in e.items() if k in ('type', 'region', 'text')} for e in events], ensure_ascii=False)}\n"
            f"【纪末状态】\n{json.dumps(summary, ensure_ascii=False)}\n"
            f"【需要命名的新政权】\n{json.dumps(names_needed, ensure_ascii=False)}\n\n"
            "请输出两部分。第一部分是一个 ```json 块：{\"title\": \"<本纪标题，八到十四字>\", \"names\": {\"<新政权占位id>\": \"<你起的名字>\"}}。"
            "名字要合乎该地区的语言与传统，不得是真实历史上存在过的国名朝代名。\n"
            "第二部分是 800 到 1100 字的纪事正文，用典雅克制的史书体，按各区域人口比例分配篇幅，不以任何一处为主角；"
            "只能写账本里有的事：可以补人物群像、因果与风物，但不得新增账本之外的战争、技术、政权或人口数字；"
            "账本里被拒绝的研究要写成未竟的探索，不能写成已经成功；不得出现真实历史的朝代、人物与专名。不要小标题。"
        )

    def template_chronicle(self, era: int, era_label: str, events: List[Dict[str, Any]]) -> Tuple[str, str]:
        lines = [e["text"] for e in events if e["type"] in ("war", "collapse", "polity_end", "research", "plague", "famine", "contact", "climate")]
        body = "。".join(lines[:18]) + ("。" if lines else "本纪天下无大事，列国各自休养。")
        return f"{era_label}纪事", body

    def narrate(self, era: int, era_label: str, events: List[Dict[str, Any]]) -> str:
        placeholders = [p for p in self.living() if p.needs_name]
        reply = self.llm.ask(self.chronicle_prompt(era, era_label, events, placeholders))
        title, body = "", ""
        if reply:
            meta = extract_json(reply)
            if meta:
                title = str(meta.get("title") or "").strip()
                names = meta.get("names") if isinstance(meta.get("names"), dict) else {}
                for p in placeholders:
                    proposed = str(names.get(p.id) or "").strip()
                    if proposed and not self.is_forbidden(proposed) and not any(q.name == proposed for q in self.polities if q.id != p.id):
                        self.rename(p, proposed)
            body = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", reply, flags=re.DOTALL).strip()
            body = re.sub(r"\A\s*#+\s*.*\n", "", body).strip()
        for p in placeholders:
            if p.needs_name:
                self.rename(p, self.invent_name(p.region))
        if body and len(body) > 200:
            self.stats["llm_chronicles"] += 1
        else:
            title, body = self.template_chronicle(era, era_label, events)
            self.stats["template_chronicles"] += 1
        if not title or self.is_forbidden(title):
            title = f"{era_label}纪事"
        return f"## 【{era_label}：{title}】\n\n{body}\n"

    def rename(self, p: Polity, name: str) -> None:
        old = p.name
        p.name = name
        p.needs_name = False
        # The placeholder appears in ledger text either as the polity id ("p12") or as
        # its provisional name ("@新政权12"). A plain replace of "p1" also rewrote the
        # "p1" inside "p12" and "p120"; match on boundaries instead.
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(p.id)}(?![0-9])|{re.escape(old)}(?![0-9])")
        for entry in self.ledger:
            text = entry.get("text")
            if text and (p.id in text or old in text):
                entry["text"] = pattern.sub(name, text)
        for q in self.polities:
            q.lineage = [name if item == old else item for item in q.lineage]

    def conclusion(self) -> str:
        summary = self.era_summary(len(self.eras))
        tree = self.knowledge_tree_text()
        prompt = (
            "你是这部开放世界通史的史官。推演已至终局，下面是最后的天下状态与全部知识谱系：\n"
            f"{json.dumps(summary, ensure_ascii=False)}\n{tree}\n\n"
            "请写 400 到 600 字的《史官论赞》：指出决定走向的几处关键分岔（气候、疫病、战争、知识、制度各举其要），"
            "评价终局相对开局的得失，不与真实历史比较，不预言未来，不歌颂不哀叹。只输出正文。"
        )
        text = self.llm.ask(prompt)
        if not text or len(text) < 100:
            text = ("两千二百余年，起于列国相持，止于本志所录之终局。其间账本所记的每一次饥荒、疫病、战败与解体，"
                    "都不是为了成全某个结局而写下的；知识只在有余粮、有商路、有识字者的地方缓慢生长，也随簿册散佚。"
                    "终局如何，读者自可于前文各纪中检视因果。")
        return "\n## 【史官论赞】\n\n" + text.strip() + "\n"

    def knowledge_tree_text(self) -> str:
        lines = ["## 附录一 知识谱系（按出现顺序）", ""]
        for node in sorted(self.nodes.values(), key=lambda n: (n.era, n.id)):
            if node.origin == "seed":
                continue
            deps = "、".join(self.nodes[d].name for d in node.prereqs if d in self.nodes) or "无"
            where = self.regions[node.origin]["name"] if node.origin in self.regions else node.origin
            lines.append(f"- 第{node.era}纪 {where}：{node.name}（{node.kind}），依赖：{deps}")
        return "\n".join(lines) + "\n"

    def lineage_text(self) -> str:
        lines = ["## 附录二 政权谱系", ""]
        for p in self.polities:
            state = "存续" if p.alive else "已亡"
            origin = f"，出自{'←'.join(reversed(p.lineage))}" if p.lineage else ""
            lines.append(f"- {p.name}（{self.regions[p.region]['name']}，第{p.founded_era}纪起，{state}{origin}）")
        return "\n".join(lines) + "\n"

    # ---------------------------------------------------------- checkpoints
    @staticmethod
    def checkpoint_path(output_path: Path) -> Path:
        return output_path.with_suffix(".checkpoint.json")

    def save_checkpoint(self, path: Path, eras_done: int) -> None:
        """Everything needed to continue the same run bit-for-bit after a pause."""
        version, internal, gauss_next = self.rng.getstate()
        payload = {
            "seed": self.seed,
            "engine": type(self).__name__,
            "eras_done": eras_done,
            "rng": {"version": version, "internal": list(internal), "gauss_next": gauss_next},
            "regions": {
                rid: {
                    "cfg": region["cfg"], "knowledge": sorted(region["knowledge"]), "urban": region["urban"],
                    "literacy": region["literacy"], "climate": region["climate"], "plague": region["plague"],
                    "links": sorted(region["links"]), "contacts": sorted(region["contacts"]), "famine": region["famine"],
                }
                for rid, region in self.regions.items()
            },
            "nodes": {k: asdict(v) for k, v in self.nodes.items()},
            "polities": [asdict(p) for p in self.polities],
            "ledger": self.ledger,
            "chronicle": self.chronicle,
            "stats": self.stats,
            "counters": {"polity": self._polity_counter, "node": self._node_counter},
            "llm": {"calls": self.llm.calls, "failures": self.llm.failures},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def load_checkpoint(self, path: Path) -> int:
        """Restore a saved run into this engine; returns how many eras were already done."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload["seed"] != self.seed:
            raise ValueError(f"checkpoint seed {payload['seed']} differs from engine seed {self.seed}")
        written_by = payload.get("engine")
        if written_by and written_by != type(self).__name__:
            # Two engines, two rule sets: continuing one run under the other would splice
            # histories that were never the same simulation.
            raise ValueError(
                f"checkpoint was written by {written_by}, not {type(self).__name__}; "
                "start a fresh run (or move the checkpoint aside) instead of resuming"
            )
        rng = payload["rng"]
        self.rng.setstate((rng["version"], tuple(rng["internal"]), rng["gauss_next"]))
        for rid, saved in payload["regions"].items():
            region = self.regions[rid]
            region["cfg"] = saved["cfg"]
            region["knowledge"] = set(saved["knowledge"])
            region["links"] = set(saved["links"])
            region["contacts"] = set(saved["contacts"])
            for key in ("urban", "literacy", "climate", "plague", "famine"):
                region[key] = saved[key]
        self.nodes = {k: Node(**v) for k, v in payload["nodes"].items()}
        self.polities = [Polity(**p) for p in payload["polities"]]
        self.ledger = payload["ledger"]
        self.chronicle = payload["chronicle"]
        self.stats = payload["stats"]
        self._polity_counter = payload["counters"]["polity"]
        self._node_counter = payload["counters"]["node"]
        self.llm.calls = payload["llm"]["calls"]
        self.llm.failures = payload["llm"]["failures"]
        return int(payload["eras_done"])

    # ---------------------------------------------------------------- run
    def run(self, epochs: Optional[int] = None, output_path: Optional[Path] = None, resume: bool = False) -> str:
        eras = self.eras[:epochs] if epochs else self.eras
        out = Path(output_path) if output_path else Path(".artifacts/china-ledger-history-2026.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = self.checkpoint_path(out)
        eras_done = 0
        if resume and checkpoint.is_file():
            eras_done = self.load_checkpoint(checkpoint)
            if self.live_print:
                print(f"从检查点续跑：前 {eras_done} 纪已完成", flush=True)
        else:
            self.chronicle = [
                "# 《账本通史》：由规则与骰子结算、由史官记述的开放世界（前230年至2026年）",
                "",
                f"种子 {self.seed}。每一纪先由随机数结算气候与疫病，再由各区域议事会提出意图，由引擎依 `ledger_config.json` 中的速率结算"
                "收成、战争、政权存亡与知识生长，最后由史官据账本记述。史官不得增删事实，模型从不决定结局。",
                "",
            ]
        self.paused = False
        for era, (label, start, end) in enumerate(eras, 1):
            if era <= eras_done:
                continue
            t0 = time.time()
            try:
                self.exogenous(era)
                proposals = self.collect_proposals(era, label)
                before = len(self.ledger)
                self.resolve(era, proposals)
                events = [e for e in self.ledger if e["era"] == era]
                section = self.narrate(era, label, events)
            except QuotaExhausted as exc:
                # Roll back to the last completed era so the retry replays this era whole.
                if checkpoint.is_file():
                    self.load_checkpoint(checkpoint)
                self.paused = True
                if self.live_print:
                    print(f"第 {era} 纪中断：模型额度用尽（{exc}）。已保存到第 {era - 1} 纪的检查点，额度恢复后加 --resume 续跑。", flush=True)
                break
            self.chronicle.append(section)
            out.write_text("\n".join(self.chronicle), encoding="utf-8")
            self.save_checkpoint(checkpoint, era)
            if self.live_print:
                alive = len(self.living())
                print(f"【第 {era}/{len(eras)} 纪】{label} 事件 {len(events)} 条，政权 {alive} 个，"
                      f"世界人口 {sum(p.population for p in self.living()):.0f} 百万，用时 {time.time() - t0:.0f} 秒", flush=True)
        if self.paused:
            return "\n".join(self.chronicle)
        if not epochs or epochs >= len(self.eras):
            try:
                self.chronicle.append(self.conclusion())
            except QuotaExhausted:
                self.paused = True
                if self.live_print:
                    print("史官论赞未生成：模型额度用尽，额度恢复后加 --resume 补写。", flush=True)
                return "\n".join(self.chronicle)
        self.chronicle.append(self.knowledge_tree_text())
        self.chronicle.append(self.lineage_text())
        doc = "\n".join(self.chronicle)
        out.write_text(doc, encoding="utf-8")
        out.with_suffix(".ledger.json").write_text(
            json.dumps({"seed": self.seed, "stats": self.stats, "ledger": self.ledger,
                        "polities": [asdict(p) for p in self.polities],
                        "nodes": {k: asdict(v) for k, v in self.nodes.items()}}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        if self.live_print:
            print(f"完成：{out}（{len(doc)} 字）；{self.stats}；模型调用 {self.llm.calls} 次，失败 {self.llm.failures} 次", flush=True)
        return doc


if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else None
    LedgerEngine(seed=2026).run(epochs=count)
