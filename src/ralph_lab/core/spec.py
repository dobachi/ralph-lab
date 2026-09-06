"""GoalSpec: v2 YAML-loaded goal definition (Ralph 型、subprocess ベース)。

Ralph 原則:
- 各 iteration で agent CLI を subprocess として起動
- Context は agent CLI 側で持たない (毎回 fresh)
- 状態はファイルシステム (workspace) と gate stdout で伝える
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AgentSpec:
    """Agent CLI の起動仕様。

    例:
        AgentSpec(cmd="claude", args=["-p", "--dangerously-skip-permissions"])
        AgentSpec(cmd="codex", args=["exec", "--full-auto"])
    """

    cmd: str
    """Agent CLI コマンド名 (PATH から解決)"""

    args: list[str] = field(default_factory=list)
    """agent CLI に渡す固定引数"""

    stdin_prompt: bool = True
    """True なら prompt を stdin から流す。False なら args 末尾に prompt を足す"""

    model: str | None = None
    """モデル名。指定時は --model で渡す (agent CLI ごとに flag 名は違うが標準化しない)"""

    env: dict[str, str] = field(default_factory=dict)
    """agent CLI 起動時の追加環境変数"""


@dataclass(frozen=True)
class GateConfig:
    """Gate script の呼び出し仕様。

    契約:
    - 呼び出し: `<script> <current_file>`
    - 環境変数: `BASE=<baseline_file>` (driver が自動で埋める)
    - Exit code: 0 = passed, non-zero = failed
    - stdout: 次 iteration の feedback として agent に渡される
    """

    script: Path
    env: dict[str, str] = field(default_factory=dict)
    timeout_sec: float = 60.0


@dataclass(frozen=True)
class GoalSpec:
    """Ralph loop の宣言的定義 (v2)。"""

    name: str
    description: str
    input_document: Path
    agent: AgentSpec
    prompt: str
    """PROMPT.md 相当。Ralph 原則で毎回丸ごと agent に渡す。$CURRENT, $BASE,
    $ITER, $PREV_GATE_OUTPUT は driver が render 時に置換する"""

    gate: GateConfig
    max_iterations: int = 5
    overall_timeout_sec: float = 900.0
    agent_timeout_sec: float = 600.0
    """1 iteration の agent subprocess timeout"""

    log_path: Path = Path("logs/ralph-runs.jsonl")

    @classmethod
    def from_yaml(cls, path: Path | str) -> "GoalSpec":
        yaml_path = Path(path).expanduser().resolve()
        with yaml_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        base_dir = yaml_path.parent
        required = ("name", "description", "input_document", "agent", "prompt", "gate")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"GoalSpec missing required fields: {missing} in {yaml_path}")

        # agent section
        agent_raw = data["agent"]
        if isinstance(agent_raw, str):
            # shortcut: agent: claude → AgentSpec(cmd="claude", args=[])
            agent = AgentSpec(cmd=agent_raw)
        elif isinstance(agent_raw, dict):
            agent = AgentSpec(
                cmd=str(agent_raw["cmd"]),
                args=list(agent_raw.get("args", [])),
                stdin_prompt=bool(agent_raw.get("stdin_prompt", True)),
                model=agent_raw.get("model"),
                env=dict(agent_raw.get("env", {})),
            )
        else:
            raise ValueError(f"agent must be a string or mapping, got {type(agent_raw)}")

        # gate section
        gate_raw = data["gate"]
        if not isinstance(gate_raw, dict) or "script" not in gate_raw:
            raise ValueError(f"gate must be a mapping with a 'script' field in {yaml_path}")
        gate = GateConfig(
            script=_resolve_path(gate_raw["script"], base_dir),
            env=dict(gate_raw.get("env", {})),
            timeout_sec=float(gate_raw.get("timeout_sec", 60.0)),
        )

        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            input_document=_resolve_path(data["input_document"], base_dir),
            agent=agent,
            prompt=str(data["prompt"]),
            gate=gate,
            max_iterations=int(data.get("max_iterations", 5)),
            overall_timeout_sec=float(data.get("overall_timeout_sec", 900.0)),
            agent_timeout_sec=float(data.get("agent_timeout_sec", 600.0)),
            log_path=_resolve_path(str(data.get("log_path", "logs/ralph-runs.jsonl")), base_dir),
        )


def _resolve_path(raw: Any, base_dir: Path) -> Path:
    """Expand ~ and resolve relative paths against `base_dir`."""
    p = Path(os.path.expandvars(str(raw))).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p
