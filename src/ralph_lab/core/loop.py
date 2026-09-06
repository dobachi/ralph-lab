"""Ralph outer loop driver.

For each iteration:
  1. Render PROMPT (spec.prompt with $CURRENT / $BASE / $ITER /
     $PREV_GATE_OUTPUT substituted)
  2. Run agent CLI as subprocess (fresh context every time — Ralph principle)
  3. Run gate script as subprocess
  4. If gate passed: return. Else: gate stdout → PREV_GATE_OUTPUT for next iter.
  5. Loop bound by max_iterations and overall_timeout_sec.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ralph_lab.core.agent_cli import AgentResult, run_agent
from ralph_lab.core.gate import GateResult, format_gate_feedback, run_gate
from ralph_lab.core.spec import GoalSpec
from ralph_lab.core.workspace import Workspace


@dataclass
class IterationRecord:
    iteration: int
    agent: AgentResult
    gate: GateResult
    feedback_used: str | None
    """This iteration の agent に渡した feedback (前 iter の gate stdout)"""

    prompt_size: int
    """agent に渡した PROMPT の文字数"""


@dataclass
class RalphResult:
    spec_name: str
    status: str
    """pass | max_iterations | timeout | init_error"""

    iterations: int
    workspace_root: Path
    records: list[IterationRecord] = field(default_factory=list)
    total_duration_ms: int = 0

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def _render_prompt(
    template: str,
    workspace: Workspace,
    iteration: int,
    max_iterations: int,
    previous_feedback: str | None,
) -> str:
    """spec.prompt の placeholder を置換する。

    Placeholders:
      $CURRENT           workspace.current の絶対パス
      $BASE              workspace.base の絶対パス
      $ITER              現在 iteration (1-indexed)
      $MAX_ITER          最大 iteration
      $PREV_GATE_OUTPUT  前 iter の gate stdout (初回は空文字)
    """
    return (
        template
        .replace("$CURRENT", str(workspace.current))
        .replace("$BASE", str(workspace.base))
        .replace("$ITER", str(iteration + 1))
        .replace("$MAX_ITER", str(max_iterations))
        .replace("$PREV_GATE_OUTPUT", previous_feedback or "(first iteration; no prior gate output)")
    )


def _log_iteration(
    log_path: Path,
    spec: GoalSpec,
    record: IterationRecord,
) -> None:
    """1 iteration の record を JSONL に追記。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "spec_name": spec.name,
        "iteration": record.iteration,
        "agent": {
            "cmd": record.agent.cmd,
            "exit_code": record.agent.exit_code,
            "duration_ms": record.agent.duration_ms,
            "timed_out": record.agent.timed_out,
            "stdout_size": len(record.agent.stdout),
            "stderr_size": len(record.agent.stderr),
        },
        "gate": {
            "exit_code": record.gate.exit_code,
            "passed": record.gate.passed,
            "duration_ms": record.gate.duration_ms,
            "timed_out": record.gate.timed_out,
            "stdout_size": len(record.gate.stdout),
        },
        "prompt_size": record.prompt_size,
        "feedback_used_size": len(record.feedback_used) if record.feedback_used else 0,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


async def run_ralph_loop(
    spec: GoalSpec,
    *,
    workspace_root: Path | None = None,
    keep_workspace: bool = True,
) -> RalphResult:
    """Ralph loop の実行本体。

    Args:
        spec: YAML から load 済みの GoalSpec
        workspace_root: 指定なしなら tempfile.mkdtemp
        keep_workspace: False なら結果に関わらず workspace 削除

    Returns:
        RalphResult (status + iterations + records + workspace_root)
    """
    start = time.monotonic()
    workspace = Workspace.prepare(spec.input_document, root=workspace_root)
    records: list[IterationRecord] = []
    feedback: str | None = None
    status = "max_iterations"

    async def _loop() -> None:
        nonlocal feedback, status
        for i in range(spec.max_iterations):
            # 1. Render PROMPT
            prompt = _render_prompt(
                spec.prompt, workspace, i, spec.max_iterations, feedback,
            )

            # 2. Run agent CLI (fresh subprocess)
            agent_result = await run_agent(
                spec.agent,
                prompt,
                workdir=workspace.root,
                timeout_sec=spec.agent_timeout_sec,
            )

            # 3. Run gate
            gate_result = await run_gate(spec.gate, workspace)

            # 4. Log
            record = IterationRecord(
                iteration=i,
                agent=agent_result,
                gate=gate_result,
                feedback_used=feedback,
                prompt_size=len(prompt),
            )
            records.append(record)
            _log_iteration(spec.log_path, spec, record)

            # 5. Verdict
            if gate_result.passed:
                status = "pass"
                return
            feedback = format_gate_feedback(gate_result)

    try:
        await asyncio.wait_for(_loop(), timeout=spec.overall_timeout_sec)
    except asyncio.TimeoutError:
        status = "timeout"

    total_duration_ms = int((time.monotonic() - start) * 1000)
    result = RalphResult(
        spec_name=spec.name,
        status=status,
        iterations=len(records),
        workspace_root=workspace.root,
        records=records,
        total_duration_ms=total_duration_ms,
    )
    if not keep_workspace:
        workspace.cleanup()
    return result
