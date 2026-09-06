"""Ralph outer loop driver.

For each iteration:
  1. Render PROMPT (spec.prompt with $CURRENT / $BASE / $ITER /
     $PREV_GATE_OUTPUT substituted)
  2. Run agent CLI as subprocess (fresh context every time — Ralph principle)
  3. **Verify BASE integrity** (P13-3, Layer 0): agent が BASE.md を書き換えていたら
     復元し、iter を強制 NG にする (framework tamper 対策)
  4. Run gate script as subprocess (Layer A syntactic)
  5. Run delegations if syntactic gate passed (Layer B, 方式 B)
  6. If overall gate passed AND no tamper: return. Else: gate stdout → PREV_GATE_OUTPUT.
  7. After pass, run post_evaluation if configured (Layer C = LLM-as-judge, 方式 C)
  8. Loop bound by max_iterations and overall_timeout_sec.
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

    base_tampered: bool = False
    """P13-3: agent が BASE.md を書き換えていた場合 True。
    tamper 時は overall_gate_passed=False に強制、feedback にも tamper 通知を含める。"""

    base_tamper_message: str = ""
    """tamper 検出時のサマリ (workspace.verify_and_restore_base() の返す文字列)"""

    current_unchanged: bool = False
    """silent failure detection: agent は exit 0 で戻ったが current.md が
    前 iter から変わっていない場合 True。JSONL log に記録され、複数 iter で
    連続すると agent の異常 (context/tool 誤設定、prompt 誤解等) の signal に。"""


@dataclass
class RalphResult:
    spec_name: str
    status: str
    """pass | max_iterations | timeout | init_error | judge_failed | judge_passed

    - pass: Ralph loop pass、post_eval (あれば) も pass
    - judge_failed: Ralph loop pass だが post_eval が FAIL 判定
    - max_iterations: Ralph loop 5 iter で終わらず、post_eval (もし run_always
      で走ったなら) も FAIL 判定 or 未実行
    - judge_passed: (P19) Ralph loop 5 iter だが post_eval が「実は OK」と rescue
      判定 = Layer B/C 非決定性への対策で judge を最終権威に
    - timeout / init_error: unrecoverable
    """

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


# P17: subprocess の stdout/stderr を先頭 N char だけ log に残す。
# 判定理由 (PASS/FAIL の 1 行) を post-hoc 分析するのに使う。
# 全体を残すと log が肥大化するので head のみ。
_LOG_HEAD_CHARS = 200


def _head(text: str, n: int = _LOG_HEAD_CHARS) -> str:
    """text の先頭 n char を返す。改行込み、UTF-8 safe。"""
    if not text:
        return ""
    if len(text) <= n:
        return text
    return text[:n] + "...[TRUNCATED]"


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
            "stdout_head": _head(record.agent.stdout),
            "stderr_head": _head(record.agent.stderr),
        },
        "gate": {
            "exit_code": record.gate.exit_code,
            "passed": record.gate.passed,
            "duration_ms": record.gate.duration_ms,
            "timed_out": record.gate.timed_out,
            "stdout_size": len(record.gate.stdout),
            "stdout_head": _head(record.gate.stdout),
            "stderr_head": _head(record.gate.stderr),
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
                "stdout_head": _head(d.stdout),
                "stderr_head": _head(d.stderr),
                "attempts": d.attempts,
            }
            for d in record.delegations
        ],
        "overall_gate_passed": record.overall_gate_passed,
        "base_tampered": record.base_tampered,
        "base_tamper_message": record.base_tamper_message,
        "current_unchanged": record.current_unchanged,
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
        "stdout_head": _head(result.stdout),
        "stderr_head": _head(result.stderr),
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
    workspace = Workspace.prepare(
        spec.input_document,
        root=workspace_root,
        baseline_document=spec.baseline_document,
    )
    records: list[IterationRecord] = []
    feedback: str | None = None
    status = "max_iterations"
    prev_current_hash: str | None = None  # silent failure detection

    async def _loop() -> None:
        nonlocal feedback, status, prev_current_hash
        import hashlib as _hashlib
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

            # 3a. Silent failure detection: current.md unchanged despite agent exit 0
            try:
                curr_hash = _hashlib.sha256(workspace.current.read_bytes()).hexdigest()
            except FileNotFoundError:
                curr_hash = ""
            current_unchanged = (
                prev_current_hash is not None
                and curr_hash == prev_current_hash
                and agent_result.exit_code == 0
            )
            prev_current_hash = curr_hash

            # 3b. Verify BASE integrity (P13-3, Layer 0 = framework tamper 対策)
            base_ok, tamper_msg = workspace.verify_and_restore_base()

            # 4. Run syntactic gate (BASE は復元済なので通常通り)
            gate_result = await run_gate(spec.gate, workspace)

            # 5. Run delegations (Layer B) if syntactic gate passed AND no tamper
            delegations: list[DelegationResult] = []
            delegation_summary = ""
            if gate_result.passed and base_ok and spec.gate.delegate_to:
                delegations = await run_all_delegations(
                    spec.gate.delegate_to,
                    workspace.current,
                    workspace.base,
                    workspace.root,
                )
                agg_passed, delegation_summary = aggregate_delegations(
                    delegations, spec.gate.aggregate,
                )
                overall_passed = agg_passed and base_ok
            else:
                overall_passed = gate_result.passed and base_ok

            # 6. Log
            record = IterationRecord(
                iteration=i,
                agent=agent_result,
                gate=gate_result,
                feedback_used=feedback,
                prompt_size=len(prompt),
                delegations=delegations,
                overall_gate_passed=overall_passed,
                base_tampered=not base_ok,
                base_tamper_message=tamper_msg,
                current_unchanged=current_unchanged,
            )
            records.append(record)
            _log_iteration(spec.log_path, spec, record)

            # 7. Verdict
            if overall_passed:
                status = "pass"
                return
            # 次 iter の feedback: syntactic gate stdout + 委譲 summary + tamper 通知
            feedback = format_gate_feedback(gate_result)
            if delegation_summary:
                feedback = (
                    feedback + "\n\n--- Delegation results ---\n" + delegation_summary
                )
            if not base_ok:
                feedback = (
                    "❌ FRAMEWORK VIOLATION: " + tamper_msg + "\n"
                    "BASE.md は編集禁止 (source of truth)。次の iter では BASE.md を\n"
                    "触らず、current.md のみ編集すること。BASE を書き換えても、\n"
                    "framework が自動復元するので無駄な操作になる。\n\n"
                    + feedback
                )

    try:
        await asyncio.wait_for(_loop(), timeout=spec.overall_timeout_sec)
    except asyncio.TimeoutError:
        status = "timeout"

    # 7. Post-evaluation (Layer C = LLM-as-judge)
    # 通常: status=pass のときのみ実行
    # run_always=True (P19): status=max_iterations でも実行 = Layer B/C の
    # 非決定的 FAIL で Ralph loop まで到達しないケースへの対策
    post_eval_result: PostEvaluationResult | None = None
    should_run_judge = spec.post_evaluation is not None and (
        status == "pass"
        or (status == "max_iterations" and spec.post_evaluation.run_always)
    )
    if should_run_judge:
        post_eval_result = await run_post_evaluation(
            spec.post_evaluation,
            workspace.current,
            workspace.base,
            workspace.root,
        )
        _log_post_evaluation(spec.log_path, spec, post_eval_result)
        # Status 遷移:
        #   pass       + judge_pass → pass (変わらず)
        #   pass       + judge_fail → judge_failed (既存挙動)
        #   max_iter   + judge_pass → judge_passed (P19、rescue)
        #   max_iter   + judge_fail → max_iterations (変わらず、judge が確認)
        if status == "pass" and not post_eval_result.passed:
            status = "judge_failed"
        elif status == "max_iterations" and post_eval_result.passed:
            status = "judge_passed"

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
