"""Validate open event proposals without assigning them to event categories."""

import hashlib
import json
import math
from typing import Dict

from models import CompiledEvent, OpenEvent


class EventCompileError(ValueError):
    pass


class EventCompiler:
    MAX_DURATION = 20

    def compile(self, event: OpenEvent, epoch: int) -> CompiledEvent:
        if not event.name.strip() or not event.description.strip():
            raise EventCompileError("事件必须包含名称和描述")
        if not event.causes or any(not cause.strip() for cause in event.causes):
            raise EventCompileError("事件必须包含明确因果说明")
        if not isinstance(event.duration, int) or not 1 <= event.duration <= self.MAX_DURATION:
            raise EventCompileError(f"事件持续时间必须在 1 至 {self.MAX_DURATION} 纪之间")
        if not event.location_resource_deltas and not event.location_property_deltas:
            raise EventCompileError("事件至少要提出一项状态变化")

        self._validate_nested(event.location_resource_deltas, "location_resource_deltas")
        self._validate_nested(event.location_property_deltas, "location_property_deltas")
        self._validate_flat(event.external_inputs, "external_inputs", nonnegative=True)
        self._validate_flat(event.external_outputs, "external_outputs", nonnegative=True)

        canonical = json.dumps(
            {
                "epoch": epoch,
                "name": event.name,
                "description": event.description,
                "causes": event.causes,
                "duration": event.duration,
                "resource_deltas": event.location_resource_deltas,
                "property_deltas": event.location_property_deltas,
                "external_inputs": event.external_inputs,
                "external_outputs": event.external_outputs,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return CompiledEvent(f"event-{epoch}-{digest}", event)

    def _validate_nested(self, values: Dict, label: str) -> None:
        if not isinstance(values, dict):
            raise EventCompileError(f"{label} 必须是对象")
        for location_id, deltas in values.items():
            if not isinstance(location_id, str) or not location_id:
                raise EventCompileError(f"{label} 包含无效地点")
            self._validate_flat(deltas, f"{label}.{location_id}", nonnegative=False)

    @staticmethod
    def _validate_flat(values: Dict, label: str, nonnegative: bool) -> None:
        if not isinstance(values, dict):
            raise EventCompileError(f"{label} 必须是对象")
        for key, value in values.items():
            if not isinstance(key, str) or not key:
                raise EventCompileError(f"{label} 包含无效键")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EventCompileError(f"{label}.{key} 必须是数值")
            if not math.isfinite(float(value)):
                raise EventCompileError(f"{label}.{key} 必须是有限数值")
            if nonnegative and value < 0:
                raise EventCompileError(f"{label}.{key} 不能为负数")
