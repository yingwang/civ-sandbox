"""Run, checkpoint, resume, and render a China-only history through 2026."""

import argparse
import os
from pathlib import Path
import pickle
from typing import Dict, Iterable, List

from engine import SimulationEngine
from models import EpochRecord
from timeline import AdaptiveTimeline, format_year, year_to_ordinal


DEFAULT_OUTPUT = Path(".artifacts/china-open-history-2026.md")
DEFAULT_CHECKPOINT = Path(".artifacts/china-open-history-2026.checkpoint.pkl")


def save_checkpoint(path: Path, engine: SimulationEngine) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    with temporary.open("wb") as stream:
        pickle.dump(engine, stream, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temporary, path)


def load_checkpoint(path: Path) -> SimulationEngine:
    with path.open("rb") as stream:
        engine = pickle.load(stream)
    if not isinstance(engine, SimulationEngine):
        raise TypeError("checkpoint does not contain a SimulationEngine")
    return engine


def render_history(engine: SimulationEngine, output: Path) -> List[Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    total = _render_document(
        "中国开放历史：公元前230年至2026年",
        engine.history,
        engine,
        include_preface=True,
    )
    output.write_text(total, encoding="utf-8")

    groups: Dict[str, List[EpochRecord]] = {
        "第一卷-战国余世": [],
        "第二卷-古代千年": [],
        "第三卷-中古至近世": [],
        "第四卷-近现代": [],
    }
    for record in engine.history:
        start = record.period_start_year
        if start is None or start < 1:
            groups["第一卷-战国余世"].append(record)
        elif start <= 1000:
            groups["第二卷-古代千年"].append(record)
        elif start <= 1900:
            groups["第三卷-中古至近世"].append(record)
        else:
            groups["第四卷-近现代"].append(record)

    rendered = [output]
    for volume_name, records in groups.items():
        if not records:
            continue
        volume_path = output.with_name(f"{output.stem}-{volume_name}{output.suffix}")
        volume_title = f"中国开放历史 {volume_name}"
        volume_path.write_text(
            _render_document(volume_title, records, engine, include_preface=False),
            encoding="utf-8",
        )
        rendered.append(volume_path)
    return rendered


def _render_document(
    title: str,
    records: Iterable[EpochRecord],
    engine: SimulationEngine,
    include_preface: bool,
) -> str:
    selected = list(records)
    lines = [f"# {title}", ""]
    if include_preface:
        lines.extend(
            [
                "这是一部只在中国境内展开的开放历史。公元前230年以前的历史与现实相同；从这一年起，未来不再服从真实历史，也没有预定的统一者、科技树或胜利条件。",
                "",
                "国家与社会分别提出计划，环境独立变化，世界引擎再依照物资、空间、工期、知识与因果条件裁定结果。时间步长随历史密度变化，动荡时期写得较细，长期稳定时期则合并叙述。",
                "",
            ]
        )
    for record in selected:
        text = record.chronicle_text.strip()
        if text:
            lines.extend([text, ""])

    lines.extend(_ending(engine, selected))
    return "\n".join(lines).rstrip() + "\n"


def _ending(engine: SimulationEngine, records: List[EpochRecord]) -> List[str]:
    alive = [item.name for item in engine.societies.values() if item.is_alive]
    new_knowledge = [
        node.name
        for node in engine.knowledge_graph.nodes.values()
        if node.discovered_epoch > 0
    ]
    structures = [item.name for item in engine.world.structures.values()]
    stats = engine.backend.stats
    covered = ""
    if records:
        covered = f"{records[0].calendar_label}至{records[-1].calendar_label}"
    return [
        "## 卷末说明",
        "",
        f"本卷覆盖{covered}，共 {len(records)} 个历史阶段。",
        f"期末仍在延续的社会：{'、'.join(alive) if alive else '无'}。",
        f"历史中形成的新知识包括：{'、'.join(new_knowledge) if new_knowledge else '尚无'}。",
        f"留存的重要工程包括：{'、'.join(structures) if structures else '尚无'}。",
        "",
        f"社会计划使用 Agy LLM {stats['llm_plan']} 次，离线回退 {stats['heuristic_plan']} 次；"
        f"环境事件使用 Agy LLM {stats['llm_event']} 次，离线回退 {stats['heuristic_event']} 次；"
        f"史家正文使用 Agy LLM {stats['llm_chronicle']} 次，模板回退 {stats['fallback_chronicle']} 次。",
        "",
    ]


def run_to_year(
    engine: SimulationEngine,
    end_year: int,
    checkpoint: Path,
    output: Path,
) -> None:
    if not engine.world:
        engine.genesis()
    if engine.current_year is None:
        raise ValueError("selected scenario has no historical calendar")
    timeline = AdaptiveTimeline(end_year=end_year)
    previous = engine.history[-1] if engine.history else None

    while year_to_ordinal(engine.current_year) <= year_to_ordinal(end_year):
        span = timeline.next_span(engine.current_year, previous)
        record = engine.step(span_years=span)
        previous = record
        save_checkpoint(checkpoint, engine)
        render_history(engine, output)
        print(
            f"[进度] {record.calendar_label} 完成，"
            f"历史阶段 {len(engine.history)}，下一起点 "
            f"{format_year(engine.current_year)}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成中国长期开放历史")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--until-year", type=int, default=2026)
    parser.add_argument("--agent-workers", type=int, default=3)
    parser.add_argument(
        "--planner-mode",
        choices=["heuristic", "cli"],
        default="heuristic",
        help="规划器后端模式 (heuristic: 离线快速推演; cli: 订阅大模型推演)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()

    if (args.resume or args.render_only) and args.checkpoint.exists():
        engine = load_checkpoint(args.checkpoint)
        engine.agent_workers = max(1, args.agent_workers)
    elif args.render_only:
        raise FileNotFoundError(args.checkpoint)
    else:
        engine = SimulationEngine(
            seed=args.seed,
            planner_mode=args.planner_mode,
            scenario="warring-states",
            agent_workers=args.agent_workers,
        )

    if args.render_only:
        paths = render_history(engine, args.output)
        for path in paths:
            print(path)
        return

    run_to_year(engine, args.until_year, args.checkpoint, args.output)
    paths = render_history(engine, args.output)
    print("[完成] 已生成：")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
