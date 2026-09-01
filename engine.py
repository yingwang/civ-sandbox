"""Compatibility entry point for the authoritative world engine.

The implementation lives in ``world_engine.py`` so policy, state models and world
mechanics remain separated. Existing imports of ``engine.WorldEngine`` continue to
work unchanged.
"""

from world_engine import WorldEngine

SimulationEngine = WorldEngine

__all__ = ["WorldEngine", "SimulationEngine"]
