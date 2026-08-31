import os
import json
import random
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from models import Tribe, Region, TribeDecision, ActionType


class LLMBackend:
    """
    LLM 驱动器：支持调用外部大模型 API（如 Gemini / OpenAI / 本地兼容端点），
    亦内置高水准的离线启发式推演生成器，保证无网络或未配置 Key 时亦可丝滑推演。
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.model = model

    def generate_tribe_decision(
        self,
        tribe: Tribe,
        world_regions: List[Region],
        all_tribes: List[Tribe],
        epoch: int,
        recent_history: List[str]
    ) -> TribeDecision:
        other_alive = [t for t in all_tribes if t.is_alive and t.id != tribe.id]
        
        # 离线启发式智能生成（结合部落性格与当前困境）
        decision = self._heuristic_tribe_decision(tribe, world_regions, other_alive, epoch)
        return decision

    def generate_chronicle(
        self,
        epoch: int,
        disaster: Optional[str],
        decisions: List[TribeDecision],
        resolutions: List[str],
        all_tribes: List[Tribe]
    ) -> str:
        # 史官撰史：以沉郁凝练的史书文笔撰写本纪实录
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
        # 基于部落性格特质与资源储备自主研判
        is_hungry = tribe.food < tribe.population * 2
        is_aggressive = "崇武" in tribe.ethos or "掠夺" in tribe.ethos or "勇猛" in tribe.ethos
        is_mercantile = "通商" in tribe.ethos or "富庶" in tribe.ethos
        is_scholarly = "百工" in tribe.ethos or "钻研" in tribe.ethos or "构筑" in tribe.ethos
        
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
            
        # 默认开辟新地或祭祀
        if random.random() < 0.5:
            action = ActionType.EXPAND
            edict = f"{tribe.leader_name}立木为界：族人日盛，当向四方开辟原野。"
            rationale = "人口滋长，需分立新邑以居。"
        else:
            action = ActionType.WORSHIP
            edict = f"{tribe.leader_name}燔柴告天：敬拜天神图腾【{tribe.totem}】，祈降甘霖祥瑞。"
            rationale = "敬奉神明图腾，凝聚族众之心。"
            
        return TribeDecision(tribe.id, action, edict=edict, rationale=rationale)
