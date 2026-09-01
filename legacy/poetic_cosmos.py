import random
from typing import List, Dict, Optional


class PoeticCosmosEngine:
    """
    【墨境玄黄·意象具象化宇宙演化沙盒】
    摆脱传统机械与科幻俗套，以东方诗性哲学、情绪通感与笔墨美学重构宇宙法则：
    在这里，物理常数是诗律与留白；星系靠执念与顿悟维系运转；战争是隐喻的兼并；文明消亡是被人彻底遗忘。
    """

    ENTITIES = [
        {
            "name": "落墨阁",
            "essence": "研墨成山，泼墨为海",
            "medium": "玄黑古墨与宣纸褶皱裂隙",
            "philosophy": "世间万物皆是一幅未干的泼墨卷轴，重山叠嶂不过是一笔浓淡枯湿",
            "artifact": "【焦墨定海砚】"
        },
        {
            "name": "抚琴氏",
            "essence": "五音定轨，宫商御星",
            "medium": "冰蚕丝弦与虚空共鸣腔",
            "philosophy": "星辰轨道皆由十二律吕拨动，一曲《广陵散》可令死星绽开万树白梅",
            "artifact": "【七弦断因果】"
        },
        {
            "name": "织梦国",
            "essence": "采撷人间未了之执念为砖石",
            "medium": "浮生残梦与晨曦雾霭",
            "philosophy": "现实本是虚妄，唯有众生在梦醒时分流下的那一滴清泪是永恒实体",
            "artifact": "【三更枕上城】"
        },
        {
            "name": "焚字族",
            "essence": "吞噬陈词滥调，淬炼一字诗眼",
            "medium": "劫灰余烬与惊堂长风",
            "philosophy": "天地间多一句废话便多一分浊气，唯有惊世孤句能化作撕裂长夜的极光",
            "artifact": "【一字断魂剑】"
        }
    ]

    COSMIC_SEASONS = [
        ("天地大留白·墨尽见素", "宇宙空间自发褪去繁复形迹，只留三分极简线条，凡臃肿之物皆化清虚"),
        ("九天落雨·洗尽铅华", "千万星河如宣纸浸水，文字与山川在晕染中重新交融互生"),
        ("绝句风暴·孤峰拔起", "苍穹之上骤现一句无名谶语，引动四方意象向诗眼坍缩聚形"),
        ("大音希声·万籁俱寂", "十二律吕同时归于一瞬静默，万物在呼吸停顿间完成一次返璞归真")
    ]

    AESTHETIC_MIRACLES = [
        "【借月为舟】：将九天清辉折叠为一叶扁舟，瞬息渡尽三千弱水",
        "【剪雪作锦】：裁下严冬初雪三万片，编织为抵御光阴侵蚀的无垢霓裳",
        "【点石化诗】：凡目光所及之处，顽石化为竹影，枯骨生出落梅",
        "【以悲为引】：将千万载离愁淬炼为冰魄冷焰，照亮整座沉眠的星海"
    ]

    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.cycle = 0

    def step(self) -> Dict:
        self.cycle += 1
        season_title, season_desc = random.choice(self.COSMIC_SEASONS)
        miracle = random.choice(self.AESTHETIC_MIRACLES)
        
        acts = []
        for e in self.ENTITIES:
            action_choice = random.choice([
                f"以【{e['artifact']}】为轴，于虚空中勾勒出一片崭新的水墨界域",
                f"吐纳万千清气，将周遭百里杂乱因果尽数炼化为纯净留白",
                f"与邻界展开了一场【隐喻论辩】，以一句诗意反客为主，化敌为友",
                f"垂眸静思三百年，令境内万座枯山在一夜春风中尽发奇葩"
            ])
            acts.append(f"· 【{e['name']}】（{e['essence']}）：{action_choice}")

        return {
            "cycle": self.cycle,
            "season": f"{season_title} —— {season_desc}",
            "miracle": miracle,
            "acts": acts
        }


if __name__ == "__main__":
    cosmos = PoeticCosmosEngine(seed=999)
    print("================================================================")
    print("      🌸 墨境玄黄·诗性通感与东方意象演化沙盒 (Poetic-Cosmos) 🌸      ")
    print("================================================================\n")
    
    for c in range(1, 4):
        res = cosmos.step()
        print(f"【意境更迭·第 {res['cycle']} 境界】")
        print(f"  天时大象：{res['season']}")
        print(f"  造物奇观：{res['miracle']}")
        print("  诸境生息：")
        for a in res["acts"]:
            print(f"    {a}")
        print("")
