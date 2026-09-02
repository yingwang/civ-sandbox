"""Open-knowledge variant of the ledger engine.

The base ledger engine remains responsible for deterministic settlement. This subclass
removes the research menu from the LLM-facing interface: agents describe a problem,
hypothesis, experiment, mechanism and free-form expected consequences. The engine then
checks grounding against the current books and projects successful knowledge onto the
small set of macro state variables that the ledger can actually simulate.

The finite macro state is therefore an accounting boundary, not a technology catalogue.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from ledger_engine import EFFECT_BONUS_KEY, LedgerEngine, Node, Polity, clamp


class OpenKnowledgeLedgerEngine(LedgerEngine):
    """Ledger engine with an open-ended research proposal space."""

    _EFFECT_HINTS: Dict[str, Tuple[str, ...]] = {
        "capacity": (
            "粮", "农", "耕", "灌", "水利", "土壤", "肥", "收成", "储粮", "食物", "产量", "承载",
            "crop", "harvest", "irrig", "soil", "food", "yield", "storage",
        ),
        "military": (
            "兵", "军", "武器", "甲", "弩", "弓", "矛", "刀", "防御", "攻城", "骑战", "战术",
            "military", "weapon", "armor", "defen", "siege", "combat",
        ),
        "trade": (
            "商", "贸易", "市场", "运输", "道路", "驿", "港", "货", "物流", "交易", "车",
            "trade", "market", "transport", "road", "port", "cargo", "caravan",
        ),
        "literacy": (
            "文字", "记录", "文书", "账", "档案", "抄写", "复制", "符号", "信息", "索引",
            "writing", "record", "archive", "copy", "document", "index", "information",
        ),
        "research": (
            "测量", "度量", "实验", "观察", "比较", "标准", "计算", "校准", "误差", "分类",
            "measure", "experiment", "observ", "standard", "calibr", "error", "classif",
        ),
        "health": (
            "疫", "病", "医", "伤", "卫生", "消毒", "隔离", "药", "感染", "饮水",
            "health", "disease", "medical", "sanit", "disinfect", "quarantine", "infection",
        ),
        "navigation": (
            "航", "远洋", "海路", "海船", "船队", "方位", "星象", "风向", "洋流", "测深",
            "navigation", "ocean", "seafaring", "bearing", "current", "depth sounding",
        ),
    }

    def observable_state(self, rid: str) -> Dict[str, Any]:
        state = super().observable_state(rid)
        cfg = self.regions[rid]["cfg"]
        state["geography"] = {
            "coast": bool(cfg.get("coast")),
            "steppe_border": bool(cfg.get("steppe_border")),
            "terrain_defense": round(float(cfg.get("terrain_defense", 1.0)), 2),
        }
        return state

    def proposal_prompt(self, rid: str, era_label: str) -> str:
        state = self.observable_state(rid)
        return (
            f"你是【{state['region']}】各政权的决策议事会，时间是{era_label}。下面是本纪开始时真正可观察的状态：\n"
            f"{json.dumps(state, ensure_ascii=False, indent=1)}\n\n"
            "为每个政权提出本纪意图。只输出一个 JSON 对象，不要解释：\n"
            '{"polities": {"<政权名>": {'
            '"research": [{'
            '"name": "<给这种新知识起一个描述性名字>", '
            '"question": "<当前具体要解决或理解的问题>", '
            '"from": ["<真正用到的已有 knowledge 名称>", "..."], '
            '"hypothesis": "<为什么这种办法可能成立>", '
            '"experiment": "<以当时条件可实际执行、可失败的观察或试验>", '
            '"mechanism": "<若成功，因果机制是什么>", '
            '"expected_consequences": ["<自由语言描述可能产生的直接后果>", "..."]}], '
            '"reform": {"name": "<制度名>", "target": "fiscal|cohesion|legitimacy|military"} 或 null, '
            '"war": {"target": "<邻近政权名>", "aim": "<目的>"} 或 null, '
            '"build": "irrigation|roads|ports|walls|none"}}}\n\n'
            "研究规则：不要从任何预设科技树挑下一项，也不要因为年代和地区去补全你知道的真实历史。"
            "真实历史只可作为物理与社会常识，不能作为候选答案表。先看当前状态里的压力、机会、地理和已有知识，再从第一性原理提出办法。"
            "可以出现现实历史从未采用的材料组合、组织办法、信息体系或技术路线；不同地区面对同一问题可以得到完全不同的解。"
            "from 只列真正不可缺少的已有知识；如果只是一次不依赖既有理论的直接观察，可以为空数组，但必须给出具体 experiment。"
            "不得凭空跨越必要能力：若一个方案需要某种加工、测量、航行或组织能力而账上没有，应把相应已有知识写入 from，否则不要提出。"
            "name 不要直接使用教科书里的著名技术专名来替代机制描述；每个政权最多三项研究。"
            "expected_consequences 用自由语言，不要填写 capacity、military、trade 等引擎字段，宏观效果由引擎结算。"
            "战争目标只能是本区域或已接触区域中存在的政权；穷弱政权可以只求生存。"
        )

    def heuristic_proposal(self, rid: str) -> Dict[str, Any]:
        proposal = super().heuristic_proposal(rid)
        known = [self.nodes[n] for n in sorted(self.regions[rid]["knowledge"]) if n in self.nodes]
        for intent in proposal.get("polities", {}).values():
            if not isinstance(intent, dict):
                continue
            converted: List[Dict[str, Any]] = []
            for old in intent.get("research") or []:
                if not isinstance(old, dict):
                    continue
                deps = [d for d in old.get("from", []) if isinstance(d, str)]
                base = deps[0] if deps else (self.rng.choice(known).name if known else "周遭现象")
                method = self.rng.choice(("分组比较", "反复试作", "长期记录", "改变一个条件后对照", "小规模有损试验"))
                converted.append({
                    "name": f"围绕{base}的{method}法（{self.regions[rid]['name']}）",
                    "question": f"{base}在什么条件下会出现稳定而可重复的差异",
                    "from": deps,
                    "hypothesis": f"改变操作条件可能使{base}表现出此前未被系统利用的性质",
                    "experiment": f"采用{method}，逐次只改变一个可观察条件并记录结果",
                    "mechanism": "若差异可重复，就把有效条件整理成可传授的操作规则",
                    "expected_consequences": ["减少反复试错成本", "提高相关操作的一致性"],
                })
            intent["research"] = converted
        return proposal

    @staticmethod
    def _research_text(item: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("name", "question", "hypothesis", "experiment", "mechanism"):
            value = item.get(key)
            if isinstance(value, str):
                parts.append(value)
        consequences = item.get("expected_consequences") or []
        if isinstance(consequences, list):
            parts.extend(str(value) for value in consequences if isinstance(value, (str, int, float)))
        return " ".join(parts).lower()

    def _infer_bonuses(self, item: Dict[str, Any], resolved: List[Node], kind: str) -> Dict[str, float]:
        """Project free-form causal claims onto the ledger's finite macro state.

        This mapping does not decide what can be invented. It only translates a successful,
        already-created knowledge claim into the coarse variables the ledger knows how to
        account for. Unrecognized mechanisms still survive as knowledge and receive only a
        small generic research bonus rather than being rejected.
        """
        text = self._research_text(item) + " " + " ".join(node.name.lower() for node in resolved)
        scores: Dict[str, int] = {}
        for effect, hints in self._EFFECT_HINTS.items():
            score = sum(1 for hint in hints if hint.lower() in text)
            if score:
                scores[effect] = score

        ranked = sorted(scores, key=lambda key: (-scores[key], key))[:2]
        bonuses: Dict[str, float] = {}
        if not ranked:
            bonuses["research_bonus"] = self.rates["other_bonus_per_node"] * 0.35
            return bonuses

        divisor = max(1.0, float(len(ranked)))
        for effect in ranked:
            if effect == "navigation":
                maritime_grounding = any(
                    token in (text + " " + " ".join(n.name for n in resolved)).lower()
                    for token in ("船", "舟", "航", "海", "boat", "ship")
                )
                if maritime_grounding and scores[effect] >= 2:
                    bonuses["navigation"] = 1.0
                    bonuses["trade_bonus"] = max(
                        bonuses.get("trade_bonus", 0.0),
                        self.rates["other_bonus_per_node"] * 0.5 / divisor,
                    )
                continue
            key = EFFECT_BONUS_KEY[effect]
            base = self.rates["capacity_per_node_default"] if effect == "capacity" else self.rates["other_bonus_per_node"]
            bonuses[key] = max(bonuses.get(key, 0.0), base * 0.7 / divisor)

        if kind in ("observation", "principle"):
            bonuses["research_bonus"] = bonuses.get("research_bonus", 0.0) + self.rates["other_bonus_per_node"] * 0.2
        if not bonuses:
            bonuses["research_bonus"] = self.rates["other_bonus_per_node"] * 0.35
        return bonuses

    def attempt_research(self, era: int, rid: str, p: Polity, item: Dict[str, Any]) -> None:
        rates = self.rates
        region = self.regions[rid]
        name = str(item.get("name") or "").strip()[:48]
        if not name or self.is_forbidden(name) or any(n.name == name for n in self.nodes.values()):
            return

        deps = [d.strip() for d in (item.get("from") or []) if isinstance(d, str) and d.strip()]
        resolved = [self.find_node_by_name(rid, dep) for dep in deps]
        if any(node is None for node in resolved):
            self.log(
                era,
                "research_rejected",
                rid,
                f"{p.name}想要探索「{name}」，但方案调用了账上不存在的前置能力",
                polity=p.id,
                missing=[d for d, node in zip(deps, resolved) if node is None],
            )
            return

        question = str(item.get("question") or "").strip()
        hypothesis = str(item.get("hypothesis") or "").strip()
        experiment = str(item.get("experiment") or "").strip()
        mechanism = str(item.get("mechanism") or "").strip()
        if len(question) < 4 or len(experiment) < 8:
            self.log(
                era,
                "research_rejected",
                rid,
                f"{p.name}提出「{name}」，但没有给出足够具体、可失败的观察或试验",
                polity=p.id,
                reason="ungrounded_experiment",
            )
            return

        resolved_nodes = [node for node in resolved if node is not None]
        prob = rates["research_base"] * (
            0.5
            + rates["research_urban_weight"] * region["urban"]
            + rates["research_literacy_weight"] * region["literacy"]
            + rates["research_fiscal_weight"] * p.fiscal
            + self.region_bonus(rid, "research_bonus")
        )
        # Direct empirical discoveries are allowed, but harder than extensions of established knowledge.
        grounding = 0.68 if not resolved_nodes else min(1.08, 0.82 + 0.08 * len(resolved_nodes))
        if hypothesis:
            grounding += 0.04
        if mechanism:
            grounding += 0.04
        prob *= min(1.1, grounding)
        if p.at_war:
            prob *= rates["research_war_penalty"]
        prob = clamp(prob, 0.01, 0.95)

        if self.rng.random() >= prob:
            self.log(
                era,
                "research_failed",
                rid,
                f"{p.name}围绕「{name}」反复试验，未得到可重复的结果",
                polity=p.id,
                question=question,
                experiment=experiment[:160],
            )
            return

        if not resolved_nodes:
            kind = "observation"
        elif mechanism and (item.get("expected_consequences") or []):
            kind = "technique"
        else:
            kind = "principle"

        self._node_counter += 1
        bonuses = self._infer_bonuses(item, resolved_nodes, kind)
        node = Node(
            f"n{self._node_counter}",
            name,
            kind,
            [node.id for node in resolved_nodes],
            rid,
            era,
            bonuses,
        )
        self.nodes[node.id] = node
        region["knowledge"].add(node.id)
        self.stats["nodes_created"] += 1
        consequences = [
            str(value)[:120]
            for value in (item.get("expected_consequences") or [])
            if isinstance(value, str)
        ][:4]
        self.log(
            era,
            "research",
            rid,
            f"{p.name}由试验得「{name}」；其机制被记录为：{mechanism[:120] or '尚只知其现象，不明其所以然'}",
            polity=p.id,
            node=node.id,
            kind=kind,
            prerequisites=[node.name for node in resolved_nodes],
            question=question[:160],
            hypothesis=hypothesis[:160],
            experiment=experiment[:200],
            mechanism=mechanism[:200],
            expected_consequences=consequences,
            macro_projection=bonuses,
        )
