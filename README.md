# Civ-Sandbox

**A Civilization-like world simulator where agents make decisions, but deterministic mechanics decide what actually happens.**

Civ-Sandbox is an experimental civilization simulation. Each civilization has goals, ethos, relationships, diplomatic tension, war exhaustion and memory. An LLM (optional) acts as a **policy layer** that proposes structured intentions; it never edits the world directly. The `WorldEngine` resolves agriculture, technology, diplomacy, war, expansion, disasters, population and resources from the authoritative `WorldState`.

This separation is deliberate:

```text
WorldState
   │
   ├── CivilizationAgent A ─┐
   ├── CivilizationAgent B ─┼─> structured AgentIntent[]
   └── CivilizationAgent C ─┘
                              │
                              v
                         WorldEngine
                              │
                  ┌───────────┴───────────┐
                  v                       v
              new WorldState          WorldEvent[]
                  │                       │
                  └───────────┬───────────┘
                              v
                         HistorianAgent
```

## What is simulated

- Geography with fertility, mineral richness and adjacency.
- Civilizations with population, food, ore, wealth, ethos, goals and technology.
- Persistent diplomacy (`neutral`, `friendly`, `allied`, `hostile`, `war`).
- Directed diplomatic tension driven by borders, scarcity, expansionist goals and militarist ethos.
- War exhaustion that raises the utility of peace and suppresses endless consecutive raids.
- Expansion across the frontier of every controlled region, not just the original homeland.
- Technology with mechanical effects (farming, attack, defense, disaster resistance, growth, trade).
- Environment events whose impact depends on terrain and technology.
- Agent memory built from high-salience world events.
- Reproducible transitions using a local seeded RNG.

## Utility-scored policy

The offline heuristic is not a hard `if food_low: cultivate` policy. Every action receives a utility score from the current state:

- immediate needs such as food pressure,
- civilization ethos,
- explicit goals,
- available frontier and resources,
- diplomatic relationships and tension,
- war exhaustion,
- seeded exploration.

Actions are sampled from these utilities with a seeded softmax, so strong incentives matter without locking every run into the same path. This makes goals causal: a civilization whose goals emphasize technology is materially more likely to invest in invention, while an expansionist civilization under border pressure can become hostile even before the first raid.

## LLM policy, not LLM physics

`--llm auto` detects an already-authenticated local CLI (`claude`, `agy`, or `codex`). The model receives an observation and must return one constrained JSON intention such as:

```json
{
  "action": "TRADE",
  "target_civilization_id": "civ_2",
  "target_region_id": null,
  "rationale": "Food is stable; trade improves wealth and relations.",
  "edict": "Open the river market."
}
```

Invalid or unavailable model output falls back to the built-in state-aware utility policy. Model prose cannot mutate resources, population, territory, technology, or battle outcomes.

For reproducible experiments, use `--llm off`. LLM decisions themselves are not guaranteed deterministic even though the world resolver is.

## Run

```bash
python3 main.py 12 --seed 42 --llm off
```

Use a logged-in local model subscription:

```bash
python3 main.py 8 --seed 42 --llm auto
# or --llm claude / --llm codex / --llm agy
```

## Architecture

```text
models.py        authoritative data model: WorldState, Civilization, Region, AgentIntent, events
agents.py        civilization utility/LLM policy + historian
llm_backend.py   safe local CLI adapter and JSON extraction
world_engine.py  authoritative state transitions and mechanics
engine.py        compatibility import for WorldEngine / SimulationEngine
main.py          CLI runner
```

The older `epic_*`, `multiverse_*`, cosmic and poetic engines remain in the repository as experiments, but `main.py` uses the unified world-state architecture.

## Design principles

1. **Agents express intent; the simulator determines consequences.**
2. **State has causal meaning.** Terrain, resources, technology, goals and diplomacy affect outcomes.
3. **Peace and war can both emerge.** Structural tension can create conflict; trade, treaties and exhaustion can de-escalate it.
4. **History persists.** Diplomacy, territory and salient memories influence future decisions.
5. **Runs are explainable and replayable.** World events record why state changed.
6. **Narrative is downstream of simulation.** The historian may describe events but cannot invent mechanics.

## Next steps

- Partial observability / fog of war and false beliefs.
- Migration routes, logistics and distance-sensitive warfare.
- Explicit economy with production/consumption chains and prices.
- Institutions, factions and internal political stability.
- Logged intents + snapshots for exact counterfactual replay.
- Batch simulation and metrics for comparing policies across seeds.
