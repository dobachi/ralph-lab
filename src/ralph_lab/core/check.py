"""Spec 検証 (ralph check) の実装。

load 後の GoalSpec に対して:
- input_document が存在する file か
- gate.script が存在し executable か
- agent.cmd が PATH で解決可能か
- prompt が非空か
- max_iterations / timeouts が正の値か

を検査し、issue の list を返す。CLI 側で表示 + exit code に翻訳。

v1 (agent-loop-lab/core/check.py) からの主な変更:
- instructions → prompt (v2 spec)
- tools list → agent.cmd の PATH 解決チェック
- max_inner_turns 削除、inner_timeout_sec 削除 (v2 では無い)
- agent_timeout_sec の妥当性チェックを追加
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from ralph_lab.core.spec import GoalSpec


@dataclass
class SpecIssue:
    severity: str  # "error" | "warning" | "info"
    field: str
    message: str


def check_spec(spec: GoalSpec) -> list[SpecIssue]:
    """spec を検証し、issue の list を返す。空 list なら「問題なし」。"""
    issues: list[SpecIssue] = []

    # input_document
    if not spec.input_document.is_file():
        issues.append(SpecIssue(
            "error", "input_document",
            f"file not found: {spec.input_document}",
        ))

    # gate.script
    if not spec.gate.script.is_file():
        issues.append(SpecIssue(
            "error", "gate.script",
            f"gate script not found: {spec.gate.script}",
        ))
    elif not os.access(spec.gate.script, os.X_OK):
        issues.append(SpecIssue(
            "error", "gate.script",
            f"gate script not executable (chmod +x): {spec.gate.script}",
        ))

    # agent.cmd — PATH で解決できるか
    if not spec.agent.cmd:
        issues.append(SpecIssue(
            "error", "agent.cmd",
            "empty agent.cmd — cannot launch subprocess.",
        ))
    elif shutil.which(spec.agent.cmd) is None:
        issues.append(SpecIssue(
            "error", "agent.cmd",
            f"agent CLI not found in PATH: {spec.agent.cmd!r}. "
            "Install the CLI or fix the cmd field.",
        ))

    # prompt
    if not spec.prompt.strip():
        issues.append(SpecIssue(
            "error", "prompt",
            "empty prompt — the agent will have no goal-specific guidance.",
        ))
    elif len(spec.prompt) < 100:
        issues.append(SpecIssue(
            "warning", "prompt",
            f"prompt is very short ({len(spec.prompt)} chars). "
            "Consider describing the workflow and rules.",
        ))

    # 数値パラメタ
    if spec.max_iterations < 1:
        issues.append(SpecIssue(
            "error", "max_iterations",
            f"must be >= 1 (got {spec.max_iterations})",
        ))
    if spec.agent_timeout_sec <= 0:
        issues.append(SpecIssue(
            "error", "agent_timeout_sec",
            f"must be > 0 (got {spec.agent_timeout_sec})",
        ))
    if spec.overall_timeout_sec <= 0:
        issues.append(SpecIssue(
            "error", "overall_timeout_sec",
            f"must be > 0 (got {spec.overall_timeout_sec})",
        ))
    if spec.gate.timeout_sec <= 0:
        issues.append(SpecIssue(
            "error", "gate.timeout_sec",
            f"must be > 0 (got {spec.gate.timeout_sec})",
        ))

    # 相対的な健全性
    if spec.overall_timeout_sec < spec.agent_timeout_sec:
        issues.append(SpecIssue(
            "warning", "overall_timeout_sec",
            f"overall_timeout_sec ({spec.overall_timeout_sec}) is less than "
            f"agent_timeout_sec ({spec.agent_timeout_sec}). "
            "Only 1 iteration will fit.",
        ))

    # log_path の親ディレクトリ
    log_parent = spec.log_path.parent
    if log_parent.exists() and not os.access(log_parent, os.W_OK):
        issues.append(SpecIssue(
            "warning", "log_path",
            f"log parent dir not writable: {log_parent}",
        ))

    # model prefix (OpenRouter 前提の情報レベル)
    if spec.agent.model and "/" not in spec.agent.model:
        issues.append(SpecIssue(
            "info", "agent.model",
            f"model {spec.agent.model!r} has no provider prefix. "
            "aider/opencode + OpenRouter usually expect '<provider>/<model>' form. "
            "claude CLI accepts short names.",
        ))

    # delegate_to (Layer B, 方式 B)
    for i, d in enumerate(spec.gate.delegate_to):
        if not d.cmd:
            issues.append(SpecIssue(
                "error", f"gate.delegate_to[{i}].cmd",
                f"empty cmd in delegation {d.name!r}",
            ))
        elif shutil.which(d.cmd) is None:
            issues.append(SpecIssue(
                "error", f"gate.delegate_to[{i}].cmd",
                f"delegation CLI not found in PATH: {d.cmd!r} (delegation: {d.name!r})",
            ))
        if not d.prompt.strip():
            issues.append(SpecIssue(
                "warning", f"gate.delegate_to[{i}].prompt",
                f"empty prompt in delegation {d.name!r}",
            ))
        if d.timeout_sec <= 0:
            issues.append(SpecIssue(
                "error", f"gate.delegate_to[{i}].timeout_sec",
                f"must be > 0 (got {d.timeout_sec})",
            ))
        if d.retries < 0:
            issues.append(SpecIssue(
                "error", f"gate.delegate_to[{i}].retries",
                f"must be >= 0 (got {d.retries})",
            ))
        if d.retries > 5:
            issues.append(SpecIssue(
                "warning", f"gate.delegate_to[{i}].retries",
                f"retries={d.retries} is high — cost multiplier is {d.retries + 1}x. "
                "Consider whether Layer C (post_evaluation) fits better.",
            ))
        if d.retry_aggregate not in ("any_pass", "all_pass", "majority"):
            issues.append(SpecIssue(
                "warning", f"gate.delegate_to[{i}].retry_aggregate",
                f"unknown retry_aggregate={d.retry_aggregate!r}. "
                "Known: any_pass, all_pass, majority. Unknown = falls back to single-shot.",
            ))
        if d.retries > 0 and d.retry_aggregate == "majority" and (d.retries + 1) % 2 == 0:
            issues.append(SpecIssue(
                "info", f"gate.delegate_to[{i}].retries",
                f"retries={d.retries} + retry_aggregate=majority: N+1={d.retries+1} is even, "
                "ties fall to FAIL. Consider odd N+1 (retries=2, 4 …) for clean majority.",
            ))
    if spec.gate.aggregate not in ("all_pass", "any_pass"):
        issues.append(SpecIssue(
            "warning", "gate.aggregate",
            f"unknown aggregate rule {spec.gate.aggregate!r} (known: all_pass, any_pass). "
            "unknown rule = fail-conservative.",
        ))

    # post_evaluation (Layer C, 方式 C)
    if spec.post_evaluation is not None:
        pe = spec.post_evaluation
        if not pe.cmd:
            issues.append(SpecIssue(
                "error", "post_evaluation.cmd", "empty cmd",
            ))
        elif shutil.which(pe.cmd) is None:
            issues.append(SpecIssue(
                "error", "post_evaluation.cmd",
                f"judge CLI not found in PATH: {pe.cmd!r}",
            ))
        if not pe.prompt.strip():
            issues.append(SpecIssue(
                "warning", "post_evaluation.prompt", "empty prompt",
            ))
        if pe.timeout_sec <= 0:
            issues.append(SpecIssue(
                "error", "post_evaluation.timeout_sec",
                f"must be > 0 (got {pe.timeout_sec})",
            ))
        # Info: judge model が agent と同じ provider か
        if pe.model and spec.agent.model and pe.model == spec.agent.model:
            issues.append(SpecIssue(
                "info", "post_evaluation.model",
                f"judge model {pe.model!r} matches agent model. "
                "Consider using a different provider (Goodhart 相関エラー対策)."
            ))

    return issues


def format_issues(issues: list[SpecIssue]) -> str:
    """人が読める形式の string に。空 list なら "OK" を返す。"""
    if not issues:
        return "OK: no issues found."
    lines = []
    by_sev: dict[str, list[SpecIssue]] = {"error": [], "warning": [], "info": []}
    for iss in issues:
        by_sev.setdefault(iss.severity, []).append(iss)
    for sev in ("error", "warning", "info"):
        rows = by_sev.get(sev, [])
        if not rows:
            continue
        lines.append(f"[{sev.upper()}] {len(rows)}")
        for r in rows:
            lines.append(f"  - {r.field}: {r.message}")
    return "\n".join(lines)


def has_errors(issues: list[SpecIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
