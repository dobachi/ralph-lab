"""Ralph outer loop driver.

For each iteration:
  1. Render PROMPT (spec.prompt with $CURRENT / $BASE / $ITER /
     $PREV_GATE_OUTPUT substituted)
  2. Run agent CLI as subprocess (fresh context every time — Ralph principle)
  3. Run gate script as subprocess (Layer A syntactic)
  4. Run delegations if syntactic gate passed (Layer B, 方式 B)
  5. If overall gate passed: return. Else: gate stdout → PREV_GATE_OUTPUT.
  6. After pass, run post_evaluation if configured (Layer C = LLM-as-judge, 方式 C)
  7. Loop bound by max_iterations and overall_timeout_sec.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from ralph_lab.core.agent_cli import AgentResult, run_agent
from ralph_lab.core.delegation import (
    DelegationResult,
    PostEvaluationResult,
    aggregate_delegations,
    run_all_delegations,
    run_post_evaluation,
)
from ralph_lab.core.gate import GateResult, format_gate_feedback, run_gate
from ralph_lab.core.spec import AgentSpec, GoalSpec
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

    delegations: list[DelegationResult] = field(default_factory=list)
    """Layer B の委譲呼び出し結果 (syntactic gate pass 後のみ実行)"""

    overall_gate_passed: bool = False
    """syntactic gate + delegations の総合判定"""


@dataclass
class RalphResult:
    spec_name: str
    status: str
    """pass | max_iterations | timeout | init_error | judge_failed"""

    iterations: int
    workspace_root: Path
    records: list[IterationRecord] = field(default_factory=list)
    total_duration_ms: int = 0
    post_evaluation: PostEvaluationResult | None = None
    """Ralph loop pass 後の judge 結果 (spec に post_evaluation あり時のみ)"""

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def _substitute_path_placeholders(
    text: str,
    workspace: Workspace,
    iteration: int,
    max_iterations: int,
) -> str:
    """Path 系 placeholder のみを置換する。args に埋めても安全なもの。"""
    return (
        text
        .replace("$CURRENT", str(workspace.current))
        .replace("$BASE", str(workspace.base))
        .replace("$ITER", str(iteration + 1))
        .replace("$MAX_ITER", str(max_iterations))
    )


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
    text = _substitute_path_placeholders(template, workspace, iteration, max_iterations)
    return text.replace(
        "$PREV_GATE_OUTPUT",
        previous_feedback or "(first iteration; no prior gate output)",
    )


def _render_agent_args(
    args: list[str],
    workspace: Workspace,
    iteration: int,
    max_iterations: int,
) -> list[str]:
    """spec.agent.args の path 系 placeholder ($CURRENT, $BASE, $ITER, $MAX_ITER)
    を置換する。$PREV_GATE_OUTPUT は含めない (長すぎて argv に不適)。
    """
    return [
        _substitute_path_placeholders(a, workspace, iteration, max_iterations)
        for a in args
    ]


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
        "delegations": [
            {
                "name": d.name,
                "exit_code": d.exit_code,
                "passed": d.passed,
                "duration_ms": d.duration_ms,
                "timed_out": d.timed_out,
                "stdout_size": len(d.stdout),
                "stderr_size": len(d.stderr),
                "error": d.error,
            }
            for d in record.delegations
        ],
        "overall_gate_passed": record.overall_gate_passed,
        "prompt_size": record.prompt_size,
        "feedback_used_size": len(record.feedback_used) if record.feedback_used else 0,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _log_post_evaluation(
    log_path: Path,
    spec: GoalSpec,
    result: PostEvaluationResult,
) -> None:
    """post_evaluation 結果を JSONL に追記。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "spec_name": spec.name,
        "event": "post_evaluation",
        "exit_code": result.exit_code,
        "passed": result.passed,
        "duration_ms": result.duration_ms,
        "timed_out": result.timed_out,
        "stdout_size": len(result.stdout),
        "stderr_size": len(result.stderr),
        "error": result.error,
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
        RalphResult (status + iterations + records + workspace_root
        + post_evaluation)
    """
    start = time.monotonic()
    workspace = Workspace.prepare(spec.input_document, root=workspace_root)
    records: list[IterationRecord] = []
    feedback: str | None = None
    status = "max_iterations"

    async def _loop() -> None:
        nonlocal feedback, status
        for i in range(spec.max_iterations):
            # 1. Render PROMPT + agent.args (both may contain placeholders)
            prompt = _render_prompt(
                spec.prompt, workspace, i, spec.max_iterations, feedback,
            )
            rendered_args = _render_agent_args(
                spec.agent.args, workspace, i, spec.max_iterations,
            )
            rendered_agent = replace(spec.agent, args=rendered_args)

            # 2. Run agent CLI (fresh subprocess)
            agent_result = await run_agent(
                rendered_agent,
                prompt,
                workdir=workspace.root,
                timeout_sec=spec.agent_timeout_sec,
            )

            # 3. Run syntactic gate
            gate_result = await run_gate(spec.gate, workspace)

            # 4. Run delegations (Layer B) if syntactic gate passed
            delegations: list[DelegationResult] = []
            delegation_summary = ""
            if gate_result.passed and spec.gate.delegate_to:
                delegations = await run_all_delegations(
                    spec.gate.delegate_to,
                    workspace.current,
                    workspace.base,
                    workspace.root,
                )
                agg_passed, delegation_summary = aggregate_delegations(
                    delegations, spec.gate.aggregate,
                )
                overall_passed = agg_passed
            else:
                overall_passed = gate_result.passed

            # 5. Log
            record = IterationRecord(
                iteration=i,
                agent=agent_result,
                gate=gate_result,
                feedback_used=feedback,
                prompt_size=len(prompt),
                delegations=delegations,
                overall_gate_passed=overall_passed,
            )
            records.append(record)
            _log_iteration(spec.log_path, spec, record)

            # 6. Verdict
            if overall_passed:
                status = "pass"
                return
            # 次 iter の feedback: syntactic gate stdout + 委譲 summary
            feedback = format_gate_feedback(gate_result)
            if delegation_summary:
                feedback = (
                    feedback + "\n\n--- Delegation results ---\n" + delegation_summary
                )

    try:
        await asyncio.wait_for(_loop(), timeout=spec.overall_timeout_sec)
    except asyncio.TimeoutError:
        status = "timeout"

    # 7. Post-evaluation (Layer C = LLM-as-judge) if configured and Ralph passed
    post_eval_result: PostEvaluationResult | None = None
    if status == "pass" and spec.post_evaluation is not None:
        post_eval_result = await run_post_evaluation(
            spec.post_evaluation,
            workspace.current,
            workspace.base,
            workspace.root,
        )
        _log_post_evaluation(spec.log_path, spec, post_eval_result)
        if not post_eval_result.passed:
            status = "judge_failed"

    total_duration_ms = int((time.monotonic() - start) * 1000)
    result = RalphResult(
        spec_name=spec.name,
        status=status,
        iterations=len(records),
        workspace_root=workspace.root,
        records=records,
        total_duration_ms=total_duration_ms,
        post_evaluation=post_eval_result,
    )
    if not keep_workspace:
        workspace.cleanup()
    return result
