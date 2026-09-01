from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, Optional


class LLMBackend:
    """Thin adapter around already-authenticated local model CLIs.

    The simulator never lets model text mutate world state directly. Model output is
    parsed into a constrained intent schema; the deterministic world engine remains
    the sole authority for state transitions.
    """

    SUPPORTED = ("claude", "agy", "codex")

    def __init__(self, mode: str = "off", timeout_seconds: int = 25):
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.cli_tool = self._select_cli_tool(mode)

    def _select_cli_tool(self, mode: str) -> Optional[str]:
        if mode == "off":
            return None
        if mode in self.SUPPORTED:
            return mode if shutil.which(mode) else None
        if mode == "auto":
            for tool in self.SUPPORTED:
                if shutil.which(tool):
                    return tool
            return None
        raise ValueError(f"Unsupported LLM mode: {mode}")

    @property
    def enabled(self) -> bool:
        return self.cli_tool is not None

    def query(self, prompt: str) -> Optional[str]:
        if not self.cli_tool:
            return None
        if self.cli_tool == "claude":
            cmd = ["claude", "-p", prompt]
        elif self.cli_tool == "codex":
            cmd = ["codex", "exec", prompt]
        else:
            cmd = ["agy", "-p", prompt]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip()

    def query_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        raw = self.query(prompt)
        if not raw:
            return None
        text = raw.strip()
        if "```" in text:
            chunks = text.split("```")
            candidates = [c.removeprefix("json").strip() for c in chunks if "{" in c and "}" in c]
        else:
            candidates = [text]
        for candidate in candidates:
            start, end = candidate.find("{"), candidate.rfind("}")
            if start < 0 or end <= start:
                continue
            try:
                value = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return None
