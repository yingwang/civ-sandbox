import os
import sys
import json
import shutil
import subprocess
from typing import Dict, Any, List, Optional
from models import Tribe, Region, TribeDecision, ActionType


class LLMBackend:
    """
    零 API Key 设计：
    优先直接利用本机已登录的订阅命令行工具（Claude Code / Antigravity / Codex CLI），
    完全无需配置或购买任何 API Key，使用用户的现有订阅额度；
    亦可随时使用内置的高效离线启发式推演引擎。
    """

    def __init__(self, mode: str = "auto"):
        self.mode = mode
        self.cli_tool = self._detect_cli_tool()

    def _detect_cli_tool(self) -> Optional[str]:
        for tool in ["claude", "agy", "codex"]:
            if shutil.which(tool):
                return tool
        return None

    def query_subscription_cli(self, prompt: str) -> Optional[str]:
        """通过本地已登录的 CLI 订阅调用大模型"""
        if not self.cli_tool:
            return None

        try:
            if self.cli_tool == "claude":
                cmd = ["claude", "-p", prompt]
            elif self.cli_tool == "codex":
                cmd = ["codex", "exec", prompt]
            else:
                cmd = ["agy", "-p", prompt]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=25
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def generate_tribe_decision(
        self,
        tribe: Tribe,
        world_regions: List[Region],
        all_tribes: List[Tribe],
        epoch: int,
        recent_history: List[str]
    ) -> TribeDecision:
        other_alive = [t for t in all_tribes if t.is_alive and t.id != tribe.id]
        
        # 默认快速且精准的自主演化决策（零延迟、零额外扣费）
        return self._heuristic_tribe_decision(tribe, world_regions, other_alive, epoch)

    def generate_chronicle(
        self,
        epoch: int,
        disaster: Optional[str],
        decisions: List[TribeDecision],
        resolutions: List[str],
        all_tribes: List[Tribe]
    ) -> str:
        surviving = [t.name for t in all_tribes if t.is_alive]
        chronicle_lines = [
            f"【洪荒纪 第 {epoch} 载·史官纪事】",
            ""
        ]
        if disaster:
            chronicle_lines.append(f"时值天降异象：{disaster}，苍生惶恐。")
        
        for r in resolutions:
            chronicle_lines.append(f"· {r}")
            
        chronicle_lines.append("")
        chronicle_lines.append(f"太史公曰：天下大势，分合无常。本纪存续部族：{'、'.join(surviving)}。各族繁衍争存，天道昭昭，未有定数。")
        return "\n".join(chronicle_lines)

    def _heuristic_tribe_decision(
        self,
        tribe: Tribe,
        world_regions: List[Region],
        other_tribes: List[Tribe],
        epoch: int
    ) -> TribeDecision:
        import random
        is_hungry = tribe.food < tribe.population * 2
        is_aggressive = "崇武" in tribe.ethos or "掠夺" in tribe.ethos or "勇猛" in tribe.ethos or "尚武" in tribe.ethos
        is_mercantile = "通商" in tribe.ethos or "富庶" in tribe.ethos or "农商" in tribe.ethos
        is_scholarly = "百工" in tribe.ethos or "钻研" in tribe.ethos or "构筑" in tribe.ethos or "采石" in tribe.ethos
        
        if is_hungry:
            action = ActionType.CULTIVATE
            edict = f"{tribe.leader_name}颁令：春耕夏耘，族人当深耕厚积，以实仓廪。"
            rationale = "部族存粮告急，当务之急在充实口粮以养族民。"
            return TribeDecision(tribe.id, action, edict=edict, rationale=rationale)
            
        if is_aggressive and other_tribes and random.random() < 0.45:
            target = random.choice(other_tribes)
            action = ActionType.RAID
            edict = f"{tribe.leader_name}拔刃向天：{target.name}据膏腴之地，勇士当披坚执锐，拓我疆土！"
            rationale = f"觊觎 {target.name} 之沃土与积粮，欲起兵彰显天威。"
            return TribeDecision(tribe.id, action, target_tribe_id=target.id, edict=edict, rationale=rationale)
            
        if is_mercantile and other_tribes and random.random() < 0.5:
            target = random.choice(other_tribes)
            action = ActionType.TRADE
            edict = f"{tribe.leader_name}遣使：备牛羊玉帛，与 {target.name} 互通有无，休兵修好。"
            rationale = f"愿与 {target.name} 开辟互市商路，求万物之利。"
            return TribeDecision(tribe.id, action, target_tribe_id=target.id, edict=edict, rationale=rationale)
            
        if is_scholarly and random.random() < 0.6:
            action = ActionType.INVENT
            edict = f"{tribe.leader_name}聚能工巧匠：穷山川草木之变，作新器以利民生。"
            rationale = "欲钻研器用与技法，筑万世不拔之基。"
            return TribeDecision(tribe.id, action, edict=edict, rationale=rationale)
            
        if random.random() < 0.5:
            action = ActionType.EXPAND
            edict = f"{tribe.leader_name}立木为界：族人日盛，当向四方开辟原野。"
            rationale = "人口滋长，需分立新邑以居。"
        else:
            action = ActionType.WORSHIP
            edict = f"{tribe.leader_name}燔柴告天：敬拜天神图腾【{tribe.totem}】，祈降甘霖祥瑞。"
            rationale = "敬奉神明图腾，凝聚族众之心。"
            
        return TribeDecision(tribe.id, action, edict=edict, rationale=rationale)
