import random
from typing import List, Dict, Tuple, Optional


class CivilizationTimelineEngine:
    ERAS = [
        {
            "name": "石器蛮荒纪 (约公元前 8000 载)",
            "techs": ["钻木取火", "打制石斧", "兽骨缝缀", "岩画图腾", "陶土烧制"],
            "events": [
                "部落逐水草而居，以石斧击退荒原剑齿恶兽",
                "首领在洞窟岩壁刻下日月图腾，始有原始巫祝",
                "族人学会以陶罐存水煮粟，婴儿夭折之数大减"
            ]
        },
        {
            "name": "青铜城邦纪 (约公元前 2000 载)",
            "techs": ["泥范铸铜", "车马战阵", "井田沟洫", "甲骨契刻", "夯土筑城"],
            "events": [
                "青铜巨鼎铸成，上铭山川神魔，四方城邦震慑纳贡",
                "开凿沟洫引河水灌溉千顷良田，秋收禾谷堆积如山",
                "各邦于中原会盟，划野分疆，立万仞夯土城垣"
            ]
        },
        {
            "name": "铁器帝国纪 (约公元前 300 载至公元 500 载)",
            "techs": ["高炉炼铁", "诸子百家", "成文律法", "丝路驼铃", "万里长垣"],
            "events": [
                "铁犁牛耕普及四海，百家争鸣，法度明晰",
                "商队载丝绸瓷器穿越万里大漠，连接极西异邦",
                "修筑万里关隘抵御朔方游牧骑兵，帝国版图大定"
            ]
        },
        {
            "name": "航海与火器纪 (约公元 1400 载至 1700 载)",
            "techs": ["活字雕版", "罗盘指极", "火铳重炮", "巨舰远洋", "水运仪象"],
            "events": [
                "千艘巨舰扬帆远航，渡过惊涛骇浪绘制全球海图",
                "雕版印刷使万卷经书流入寻常巷陌，文脉大昌",
                "城头列装红夷大炮，旧式骑兵战阵自此退出争锋舞台"
            ]
        },
        {
            "name": "蒸汽与电气工业纪 (约公元 1800 载至 1950 载)",
            "techs": ["蒸汽机车", "钢铁高炉", "电灯电报", "内燃机动", "无线电波"],
            "events": [
                "钢铁轨道如经络般铺满平原，火车汽笛声惊破群山",
                "电线交织连通重洋，瞬息之间万里传书",
                "烟囱林立，机器昼夜轰鸣，人类彻底告别手工劳作"
            ]
        },
        {
            "name": "信息与硅基计算纪 (约公元 1960 载至 2010 载)",
            "techs": ["晶体管微雕", "登月飞船", "万维网络", "移动终端", "卫星天网"],
            "events": [
                "火箭冲破九霄，人类足迹首次印刻在银月荒原之上",
                "光纤与芯片将整颗星球编织成一张无所不达的数字网络",
                "掌中方寸荧幕连接大千世界，知识与信息瞬息可得"
            ]
        },
        {
            "name": "大模型与人工智能纪元 (2020 至 2026 载)",
            "techs": ["大语言模型", "多模态视频生成", "具身智能机器人", "神经拟真沙盒", "量子算力矩阵"],
            "events": [
                "大模型突破语言与视觉边界，代码与艺术可在指尖自动涌现",
                "多模态视频模型能够自主演绎历史光影与现实梦境",
                "智能体沙盒中，千万虚拟文明在数秒内生灭轮回……"
            ]
        }
    ]

    def __init__(self):
        self.factions = [
            {"name": "炎夏华夏系", "culture": "农耕文治·天人合一", "score": 100, "status": "繁盛"},
            {"name": "欧罗巴城邦系", "culture": "逻辑法理·工商业航海", "score": 100, "status": "繁盛"},
            {"name": "美洲新陆系", "culture": "拓荒技术·资本金融", "score": 80, "status": "繁盛"},
            {"name": "东瀛扶桑系", "culture": "匠人精致·极简美学", "score": 70, "status": "繁盛"}
        ]

    def run_grand_epic(self) -> List[Dict]:
        chronicles = []
        for era in self.ERAS:
            era_record = {
                "era_name": era["name"],
                "key_techs": era["techs"],
                "major_events": era["events"],
                "factions_state": []
            }
            for f in self.factions:
                f["score"] += random.randint(150, 300)
                era_record["factions_state"].append((f["name"], f["score"], f["status"]))
            chronicles.append(era_record)
        return chronicles


if __name__ == "__main__":
    engine = CivilizationTimelineEngine()
    history = engine.run_grand_epic()
    print("=== 《人类文明演化通史：从石器时代到 2026》 ===")
    for h in history:
        print(f"\n【{h['era_name']}】")
        print("· 关键科技突破：" + "、".join(h["key_techs"]))
        print("· 历史标志事件：")
        for ev in h["major_events"]:
            print(f"  - {ev}")
