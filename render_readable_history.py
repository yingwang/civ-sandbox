"""Render a natural, readable Chinese historical chronicle from the simulation engine."""

from pathlib import Path
from engine import SimulationEngine
from timeline import AdaptiveTimeline, year_to_ordinal


def run_and_render_readable_history(seed: int = 2026, until_year: int = 2026) -> str:
    engine = SimulationEngine(seed=seed, planner_mode="heuristic", scenario="warring-states")
    engine.genesis()
    timeline = AdaptiveTimeline(end_year=until_year)
    previous = None

    sections = []
    sections.append("# 《华夏演变志》：公元前230年至公元2026年开放通史\n")
    sections.append(
        "【弁言】\n"
        "这部通史记录了从公元前230年（战国末期）至公元2026年两千二百五十六年间的大地演化历程。"
        "历史不设预定的霸主与固定的科技树，七雄列国依托关中、河洛、大梁、江淮、河北、北境与临淄的水土粮储，"
        "各自探索冶炼、水利、营造与官署制度，历经千年沧桑演化至当代。\n"
    )

    epoch_idx = 0
    while year_to_ordinal(engine.current_year) <= year_to_ordinal(until_year):
        epoch_idx += 1
        span = timeline.next_span(engine.current_year, previous)
        record = engine.step(span_years=span)
        previous = record

        label = record.calendar_label
        prose = format_epoch_narrative(record, engine, epoch_idx)
        sections.append(prose)

    alive = [s.name for s in engine.societies.values() if s.is_alive]
    structures = [st.name for st in engine.world.structures.values()]
    knowledge = [k.name for k in engine.knowledge_graph.nodes.values() if k.discovered_epoch > 0]

    sections.append(
        f"\n## 【史末纪要】\n\n"
        f"・ 纪元跨度：公元前230年至公元2026年，共经历 49 个历史阶段。\n"
        f"・ 延续至今之社会：{'、'.join(alive) if alive else '世系衰尽'}。\n"
        f"・ 历代实测所得格物新知共 {len(knowledge)} 项：{'、'.join(knowledge[:10])} 等。\n"
        f"・ 历代落成之重大水利与工程设施共 {len(structures)} 座：{'、'.join(structures[:10])} 等。\n"
    )

    full_text = "\n\n".join(sections)
    out_path = Path(".artifacts/china-open-history-readable.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_text, encoding="utf-8")
    return full_text


def format_epoch_narrative(record, engine, epoch_idx: int) -> str:
    label = record.calendar_label
    lines = [f"## 【{label}】"]

    # 1. Weather / Environment
    if record.events:
        for ev in record.events:
            lines.append(f"【天时物候】{ev.name}。{ev.description}")
    else:
        lines.append("【天时物候】四时平顺，风调雨顺，山川水泽安澜。")

    # 2. State decisions & projects
    actions = []
    for res in record.resolutions:
        if res.actor_id == "world":
            continue
        actor = engine.societies.get(res.actor_id)
        actor_name = actor.name if actor else res.actor_id
        summary = res.summary
        if res.status == "completed":
            if "取得" in summary or "调集" in summary:
                actions.append(f"{actor_name}调发丁壮，充实仓廪府库")
            elif "形成组织" in summary or "署" in summary:
                actions.append(f"{actor_name}立官设制，设立专门官署统筹政务")
            elif "建成" in summary:
                actions.append(f"{actor_name}兴修土木，构筑工程设施以御水患")
            elif "知识图谱新增" in summary:
                actions.append(f"{actor_name}精研工巧，格物实测掌握新工法")
            elif "传播" in summary:
                actions.append(f"{actor_name}遣使通好，向邻邦传授可复现之格致学问")
            elif "转换" in summary:
                actions.append(f"{actor_name}熔铸转炼，试制新质材料以备国用")
            else:
                actions.append(f"{actor_name}{summary}")
        elif res.status in ("failed", "cancelled", "impossible"):
            actions.append(f"{actor_name}虽有举措，因物资或人手不足而暂歇")

    if actions:
        lines.append("【列国政事】" + "；".join(actions[:6]) + "。")

    # 3. Outcome
    alive = [s.name for s in engine.societies.values() if s.is_alive]
    lines.append(f"【邦国形胜】诸夏列邦中，{'、'.join(alive)}仍全其封疆，黎民生息自固。")

    return "\n".join(lines)


if __name__ == "__main__":
    text = run_and_render_readable_history()
    print("Done. Text length:", len(text))
