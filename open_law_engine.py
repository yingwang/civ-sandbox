"""Open-World Physics & Economics-Driven Civilization Simulation Engine (230 BCE to 2026 CE).

Completely unlocks the timeline from real-world historical scripts:
- No predetermined unification, dynasties, or fixed outcomes.
- Strictly governed by fundamental laws of Physics, Geography, Logistics, and Macroeconomics.
- Dynamic state progression with emergent wars, diplomacy, tech paradigms, and institutions.
"""

import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple


class OpenLawHistoryEngine:
    AGY_MODEL = "gemini-3.7-flash-high"

    DEFAULT_TIMELINE: List[Tuple[str, str, int, int]] = [
        ("公元前230年至公元前180年", "大兼并时代：七雄地缘决战与初次秩序定型", 230, 180),
        ("公元前179年至公元前100年", "霸权确立与制度探索：大一统或多极均势", 179, 100),
        ("公元前99年至公元前1年", "经贸扩张与边疆碰撞：丝路或海路初期开拓", 99, 1),
        ("公元1年至公元150年", "第一繁盛纪：农业改良、人口峰值与早期工巧突破", 1, 150),
        ("公元151年至公元300年", "动荡与重组：气候波动、流民迁徙与制度危机", 151, 300),
        ("公元301年至公元500年", "南北交融与思想裂变：新势力崛起与冶金水利大跨越", 301, 500),
        ("公元501年至公元700年", "大动脉重构：运河、海港与大交通网络成型", 501, 700),
        ("公元701年至公元900年", "繁荣极峰与商业革命：货币金融、印刷与海外市舶", 701, 900),
        ("公元901年至公元1100年", "科技大爆炸：火药兵工、精密天文与近世市民社会", 901, 1100),
        ("公元1101年至公元1300年", "动力与机械演进：水力工场、远洋探险与大陆争霸", 1101, 1300),
        ("公元1301年至公元1500年", "全球大航海与白银时代：海洋帝国的崛起与内陆竞逐", 1301, 1500),
        ("公元1501年至公元1700年", "科学革命与早期工业萌芽：焦炭冶铁、机械织造与格致学", 1501, 1700),
        ("公元1701年至公元1850年", "工业革命浪潮：蒸汽动力、铁路网络与现代国家机器", 1701, 1850),
        ("公元1851年至公元1950年", "电气化与全球总体格局：钢铁巨舰、内燃机与制度决战", 1851, 1950),
        ("公元1951年至公元2000年", "信息时代与工业巅峰：原子能、航天巡天与全球产业链", 1951, 2000),
        ("公元2001年至公元2026年", "智能文明纪元：高速立体交通、算力枢纽与AI奇点爆发", 2001, 2026),
    ]

    def __init__(self, seed: int = 2026):
        self.seed = seed
        self.rng = random.Random(seed)
        self.cli_tool = self._detect_cli()

    def _detect_cli(self) -> Optional[str]:
        for tool in ("agy", "claude", "codex"):
            if shutil.which(tool):
                return tool
        return None

    def _query_llm(self, prompt: str) -> str:
        if not self.cli_tool:
            return ""
        cmd = {
            "agy": ["agy", "--model", self.AGY_MODEL, "--disable-slash-commands", "-p", prompt],
            "claude": ["claude", "-p", prompt],
            "codex": ["codex", "exec", prompt],
        }.get(self.cli_tool)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return ""

    def run(
        self,
        epochs: Optional[int] = None,
        output_path: Optional[Path] = None,
        live_print: bool = True,
    ) -> str:
        all_chronicles = []
        all_chronicles.append("# 《华夏开放宇宙演变志》：基于物理与经济学客观规律的架空通史 (前230年至2026年)\n")
        all_chronicles.append(
            "【演化法则弁言】\n"
            "这是一部完全打破既定历史剧本的开放世界推演史。自公元前230年战国七雄开局，"
            "历史不再受秦始皇、汉唐宋明等真实人物与事件的约束。每一次兼并、变法、王朝兴衰与科技跃迁，"
            "均严格遵循地理后勤、马尔萨斯承载力、拉弗赋税曲线、因果格致技术树与博弈论等底层物理与宏观经济学规律自由涌现。\n"
        )

        state = {
            "epoch_index": 0,
            "calendar_range": "公元前230年",
            "active_powers": {
                "秦国": {"territory": "关中平原、巴蜀、汉中", "capital": "咸阳", "advantage": "都江堰与郑国渠粮仓、法家高动员力", "weakness": "严苛律法易引反弹"},
                "齐国": {"territory": "齐鲁大地、胶东半岛", "capital": "临淄", "advantage": "鱼盐之利、东方海运、稷下学宫百家争鸣、工商业金融富庶", "weakness": "军备偏弛"},
                "楚国": {"territory": "江汉平原、江淮流域、洞庭云梦", "capital": "郢都/寿春", "advantage": "纵深辽阔、水网纵横、资源丰富、道家巫风", "weakness": "封君贵族掣肘分权"},
                "赵国": {"territory": "河北平原、太行山以东、雁门代地", "capital": "邯郸", "advantage": "胡服骑射、名将如云、铁骑精锐", "weakness": "腹背受敌、产粮薄弱"},
                "魏国": {"territory": "中原核心、大梁、河东", "capital": "大梁", "advantage": "李悝变法遗存、重装魏武卒、人口稠密", "weakness": "四战之地、无险可守"},
                "燕国": {"territory": "幽燕之地、辽东辽西", "capital": "蓟城", "advantage": "地处偏僻、抗击东胡", "weakness": "地狭民贫、内讧频繁"},
                "韩国": {"territory": "中原咽喉、宜阳、新郑", "capital": "新郑", "advantage": "天下劲弩皆出于韩、天下铁兵之首", "weakness": "疆土最小、强邻环伺"},
            },
            "dominant_institutions": "战国分封与封君封邑制，兼有法家郡县试点",
            "tech_stack": ["青铜冶铸", "块炼渗碳铁器", "战国强弩", "都江堰引水灌溉", "竹简漆书", "早期骑兵阵"],
            "economy_and_logistics": {
                "economic_centers": ["临淄（商贸金融）", "咸阳-成都（农业粮仓）", "大梁（中原集散）", "寿春（水运集聚）"],
                "total_population": "约2500万人",
                "trade_routes": "中原河道商路、齐国沿海航线、楚国江汉漕运",
            },
            "major_unresolved_tensions": [
                "关中秦国军功爵制对关东的兼并压力",
                "齐国海洋商贸资本与中原大陆农耕势力的竞争",
                "三晋（赵魏韩）合纵连横的脆弱均势",
                "北疆游牧部族（匈奴、东胡）南侵压力",
            ],
        }

        selected_epochs = self.DEFAULT_TIMELINE[:epochs] if epochs else self.DEFAULT_TIMELINE
        total_epochs = len(selected_epochs)

        out_file = Path(output_path) if output_path else Path(".artifacts/china-open-world-history-2026.md")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        existing_text = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
        existing_epochs = {}
        if existing_text:
            for idx, (era_label, era_theme, start_yr, end_yr) in enumerate(self.DEFAULT_TIMELINE, 1):
                marker_start = f"<!-- EPOCH_{idx}_START -->"
                # Check comment marker or year range pattern
                if marker_start in existing_text:
                    existing_epochs[idx] = True
                elif (f"{start_yr}" in existing_text and f"{end_yr}" in existing_text) or (f"纪元{idx}" in existing_text) or (idx == 1 and "前230" in existing_text) or (idx == 2 and "前179" in existing_text) or (idx == 3 and "前99" in existing_text):
                    existing_epochs[idx] = True

        llm_count = 0
        fallback_count = 0

        for idx, (era_label, era_theme, start_yr, end_yr) in enumerate(selected_epochs, 1):
            if idx in existing_epochs:
                # If we don't have comment markers, parse by era
                chronicle_content = ""
                marker_start = f"<!-- EPOCH_{idx}_START -->"
                marker_end = f"<!-- EPOCH_{idx}_END -->"
                if marker_start in existing_text and marker_end in existing_text:
                    chronicle_content = existing_text.split(marker_start)[1].split(marker_end)[0].strip()
                    all_chronicles.append(f"\n<!-- EPOCH_{idx}_START -->\n{chronicle_content}\n<!-- EPOCH_{idx}_END -->\n")
                else:
                    # Find section in raw text
                    sections = existing_text.split("## ")
                    for s in sections:
                        if (f"{start_yr}" in s and f"{end_yr}" in s) or f"纪元{idx}" in s or (idx == 1 and "前230" in s) or (idx == 2 and "前179" in s) or (idx == 3 and "前99" in s):
                            chronicle_content = s.strip()
                            all_chronicles.append(f"\n<!-- EPOCH_{idx}_START -->\n## {chronicle_content}\n<!-- EPOCH_{idx}_END -->\n")
                            break

                self._update_state_heuristic(state, idx)
                llm_count += 1
                if live_print:
                    print(f"【推演纪元 {idx}/{total_epochs}】{era_label} (已从检查点恢复)", flush=True)
                continue

            if live_print:
                print(f"\n【开放世界推演 · 第 {idx}/{total_epochs} 纪】{era_label} ({start_yr}—{end_yr})", flush=True)

            prompt = self._build_open_world_prompt(idx, era_label, era_theme, start_yr, end_yr, state)
            raw_response = self._query_llm(prompt)

            chronicle, new_state = self._parse_llm_response(raw_response, idx, era_label, era_theme, state)
            if raw_response:
                llm_count += 1
            else:
                fallback_count += 1

            if live_print:
                print(f"{chronicle}\n", flush=True)

            all_chronicles.append(f"\n<!-- EPOCH_{idx}_START -->\n## {chronicle}\n<!-- EPOCH_{idx}_END -->\n")
            state = new_state
            out_file.write_text("\n".join(all_chronicles), encoding="utf-8")

        # Conclusion
        if not epochs or epochs >= len(self.DEFAULT_TIMELINE):
            conclusion = (
                "\n## 【太史公·开放宇宙演变论赞】\n\n"
                "夫两千二百五十六载之风雷激荡，起自公元前230年之诸侯争雄，终至公元2026年之星辰大海。\n"
                "历史何尝有定论？山川不改其险，日月不移其辉，而人事代谢、机变万千！"
                "只要遵从物理之尺度、地缘之纵深、经济之脉络与格致之递进，华夏山河无论由齐、楚、秦、赵谁掌中枢，"
                "皆能在大江大海与算力星河间，走出一条璀璨壮丽的文明宏途！\n"
            )
            all_chronicles.append(conclusion)
            out_file.write_text("\n".join(all_chronicles), encoding="utf-8")

        full_doc = "\n".join(all_chronicles)
        if live_print:
            print("━" * 70)
            print(f"【推演完成】共推演 {total_epochs} 纪开放世界史，大模型生成 {llm_count} 纪，规则回退 {fallback_count} 纪。")
            print(f"全景开放历史已保存至: {out_file} (总字数: {len(full_doc)})")
            print("━" * 70)

        return full_doc

    def _build_open_world_prompt(
        self,
        epoch_idx: int,
        era_label: str,
        era_theme: str,
        start_yr: int,
        end_yr: int,
        state: Dict,
    ) -> str:
        return (
            "你是一个掌管宏大历史沙盘演化与大历史哲学的推演核心。现在进行【华夏两千年开放世界分叉推演】。\n"
            f"当前纪元阶段：【{era_label}】（跨度约 {abs(end_yr - start_yr)} 年）\n"
            f"上一纪元结束时真实天下状态：\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
            "【推演绝对原则——严禁照抄真实历史剧本】：\n"
            "1. 绝不照搬现实中秦始皇必然一统、汉唐宋明必然出现的定式！秦可能统一，但也可能因暴政或六国合纵被齐楚瓜分；齐国可能发展海上帝国与商业民主；楚国可能建立南方水运联邦；赵国可能打造游牧铁骑大帝国。\n"
            "2. 每一个新政权名称、年号、制度、新皇帝与思想学派，都必须由你在本时空的因果逻辑下自行命名与推演。\n\n"
            "【四大底层客观规律（物理与宏观经济学基本法）】：\n"
            "1. 【地理、运力与后勤法则】：水运成本只有陆运的十分之一；山川要塞（崤函、长江、太行）具备非线性防御倍率；征伐扩张受限于粮草运输半径与军队消耗。\n"
            "2. 【马尔萨斯承载力与农业经济】：人口增长受粮食亩产与水利灌溉严格制约；重税与战争会引发饥荒与人口暴跌；和平休养会促使人口按自然繁殖曲线指数增长。\n"
            "3. 【商业、金融与资本演化】：商贸集聚会催生货币信用（如纸币飞钱、汇兑）、股份契约、手工工场与远洋贸易驱动力。\n"
            "4. 【格致科技因果阶梯】：技术严禁凭空跃迁，必须遵循因果链（采矿冶炼 -> 高炉百炼钢/铸铁 -> 机械水力 -> 焦炭煤矿 -> 蒸汽动力/火车轮船 -> 电气化 -> 内燃机 -> 计算与信息 -> 算力与智能）。\n\n"
            "【输出格式要求】：\n"
            "请直接输出两部分内容：\n"
            "第一部分：典雅磅礴的大历史纪要（600-900字），标题自拟（格式为《【{era_label}：自拟壮丽主题】》），下分四个维度：\n"
            "  一、天象地理与地缘变局（气候冷暖、生态水文、边患冲击、地理版图转移）\n"
            "  二、政权兴亡与兼并决战（战役胜负、外交纵横、制度变革、政权生灭）\n"
            "  三、经济流变与格致科技（生产力跃迁、新农具/新材料/新机器发明、贸易网络与货币）\n"
            "  四、天下大势与文明图景（期末存续政权、人口总数、思想流变与城市文化）\n\n"
            "第二部分：在正文最后附上一个 JSON 代码块（```json ... ```），更新下一纪的状态，字段包含：\n"
            "  active_powers (当前存续主要政权及特征), dominant_institutions, tech_stack (新增技术), economy_and_logistics (人口与商业重心), major_unresolved_tensions。"
        )

    def _parse_llm_response(
        self,
        raw: str,
        idx: int,
        era_label: str,
        era_theme: str,
        old_state: Dict,
    ) -> Tuple[str, Dict]:
        if not raw:
            fallback = self._generate_open_narrative_fallback(idx, era_label, era_theme, old_state)
            self._update_state_heuristic(old_state, idx)
            return fallback, old_state

        # Split text and json block
        text = raw.strip()
        new_state = dict(old_state)
        new_state["epoch_index"] = idx
        new_state["calendar_range"] = era_label

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                parsed_json = json.loads(json_match.group(1))
                new_state.update(parsed_json)
                # Remove json block from readable chronicle text
                text = text[:json_match.start()].strip()
            except Exception:
                pass
        else:
            self._update_state_heuristic(new_state, idx)

        return text, new_state

    def _update_state_heuristic(self, state: Dict, idx: int):
        state["epoch_index"] = idx
        if idx == 1:
            state["active_powers"] = {
                "大齐联合王国": {"territory": "齐鲁、淮北、吴越沿海", "capital": "临淄", "traits": "海洋商贸、工商业发达"},
                "西秦帝国": {"territory": "关中、巴蜀、河东", "capital": "咸阳", "traits": "农耕军功、法家集权"},
                "大楚联邦": {"territory": "荆襄、江淮、岭南", "capital": "寿春", "traits": "水运网络、贵族自治"},
            }
            state["tech_stack"].extend(["早期高炉炒钢", "沿海海运福船", "木牛轮轴运具"])
        elif idx == 4:
            state["tech_stack"].extend(["植物纤维造纸术", "水排鼓风冶铁", "龙骨水车", "市舶商税制"])
        elif idx == 8:
            state["tech_stack"].extend(["活字印刷术", "指南罗盘深海航行", "原始管形火器", "主权信用纸币"])
        elif idx == 12:
            state["tech_stack"].extend(["蒸汽机原理试验", "焦炭高炉冶铁", "水力大纺车", "机械钟表"])
        elif idx == 14:
            state["tech_stack"].extend(["蒸汽火车与铁道网", "铁甲轮船", "电报网络", "近代工矿企业"])
        elif idx == 16:
            state["tech_stack"].extend(["高速立体交通网", "全球算力网络", "量子计算与AI大模型前沿"])

    def _generate_open_narrative_fallback(self, idx: int, era_label: str, era_theme: str, state: Dict) -> str:
        return (
            f"【{era_label}：{era_theme}】\n\n"
            "天地玄黄，宇宙洪荒。在严格的地理水运与宏观经济规律主导下，天下列国依凭自身地缘禀赋展开了波澜壮阔的开放竞争。\n"
            "山川关隘锁闭要津，江海舟楫通达四海。工巧格致随着商业繁荣而代代跃迁，人口在农桑精耕中稳步繁衍，"
            "展现出完全不同于既定历史的崭新华夏文明图景。"
        )


if __name__ == "__main__":
    engine = OpenLawHistoryEngine(seed=2026)
    res = engine.run(epochs=None)
    print("Open Law History Result Total Length:", len(res))
