"""Delegation & post-evaluation: 委譲呼び出しと LLM-as-judge の実装。

方式 B (spec.gate.delegate_to) と方式 C (spec.post_evaluation) の
subprocess 実行 + 結果集約を担う。

Ralph 原則忠実に、各委譲は fresh subprocess として起動される。cwd は
workspace のもの (agent と同じ)。
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path

from ralph_lab.core.spec import DelegationCall, PostEvaluationConfig


@dataclass(frozen=True)
class DelegationResult:
    """1 件の委譲呼び出しの結果。"""

    name: str
    """委譲の識別名 (DelegationCall.name)"""

    cmd: list[str]
    """実際の argv (debug 用)"""

    exit_code: int
    """0 = subprocess は正常終了 / -1 = 起動失敗 or timeout"""

    passed: bool
    """委譲の判定 (fail_pattern に match しなかった場合 True)"""

    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    error: str | None = None
    """subprocess 起動失敗等の error message"""


@dataclass(frozen=True)
class PostEvaluationResult:
    """post_evaluation の結果。"""

    cmd: list[str]
    exit_code: int
    passed: bool
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    error: str | None = None


def _render_prompt(template: str, current: Path, base: Path | None) -> str:
    """`{file}` `{base}` の placeholder を置換する。"""
    result = template.replace("{file}", str(current))
    if base is not None:
        result = result.replace("{base}", str(base))
    return result


async def run_delegation(
    call: DelegationCall,
    current: Path,
    base: Path | None,
    workdir: Path,
) -> DelegationResult:
    """1 件の委譲を subprocess で実行、判定結果を返す。

    Never raises: エラーは result.error に格納。gate 全体を壊さない。
    """
    start = time.monotonic()
    prompt = _render_prompt(call.prompt, current, base)

    argv = [call.cmd] + list(call.args)
    if not call.stdin_prompt and prompt:
        argv.append(prompt)

    env = {**os.environ}

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if call.stdin_prompt else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
            env=env,
        )
    except (FileNotFoundError, PermissionError) as exc:
        return DelegationResult(
            name=call.name,
            cmd=argv,
            exit_code=-1,
            passed=False,
            stdout="",
            stderr="",
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    timed_out = False
    try:
        stdin_input = prompt.encode("utf-8") if call.stdin_prompt else None
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin_input),
            timeout=call.timeout_sec,
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_b, stderr_b = await proc.communicate()

    duration_ms = int((time.monotonic() - start) * 1000)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    exit_code = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)

    # fail_pattern に match したら fail
    passed = True
    if exit_code == -1:
        passed = False  # 起動失敗 or timeout = fail
    elif call.fail_pattern:
        try:
            if re.search(call.fail_pattern, stdout, re.MULTILINE):
                passed = False
        except re.error:
            # fail_pattern が壊れている場合、conservative に fail
            passed = False

    return DelegationResult(
        name=call.name,
        cmd=argv,
        exit_code=exit_code,
        passed=passed,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


async def run_all_delegations(
    delegate_to: list[DelegationCall],
    current: Path,
    base: Path | None,
    workdir: Path,
) -> list[DelegationResult]:
    """全ての委譲を直列に実行 (rate limit / cost 予測性のため並列にしない)。"""
    results: list[DelegationResult] = []
    for call in delegate_to:
        result = await run_delegation(call, current, base, workdir)
        results.append(result)
    return results


def aggregate_delegations(
    results: list[DelegationResult],
    rule: str = "all_pass",
) -> tuple[bool, str]:
    """委譲結果を集約。(passed, summary_string) を返す。"""
    if not results:
        return True, "(no delegations)"

    passed_count = sum(1 for r in results if r.passed)
    total = len(results)

    if rule == "all_pass":
        overall = passed_count == total
    elif rule == "any_pass":
        overall = passed_count > 0
    else:
        # 未知の rule は fail-conservative
        overall = False

    detail_lines = []
    for r in results:
        mark = "✅" if r.passed else "❌"
        extra = f" (error: {r.error})" if r.error else ""
        if r.timed_out:
            extra = " (TIMEOUT)"
        detail_lines.append(f"  {mark} {r.name}: exit={r.exit_code}, {r.duration_ms}ms{extra}")

    summary = f"delegations {passed_count}/{total} passed (rule: {rule})\n" + "\n".join(detail_lines)
    return overall, summary


async def run_post_evaluation(
    config: PostEvaluationConfig,
    final_current: Path,
    base: Path | None,
    workdir: Path,
) -> PostEvaluationResult:
    """Ralph loop の pass 後の judge を実行。

    LLM-as-judge の semantic 評価。異 provider を推奨 (Goodhart 相関エラー
    対策)。
    """
    start = time.monotonic()
    prompt = _render_prompt(config.prompt, final_current, base)

    argv = [config.cmd] + list(config.args)
    if config.model:
        argv.extend(["--model", config.model])
    if not config.stdin_prompt and prompt:
        argv.append(prompt)

    env = {**os.environ}

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if config.stdin_prompt else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
            env=env,
        )
    except (FileNotFoundError, PermissionError) as exc:
        return PostEvaluationResult(
            cmd=argv,
            exit_code=-1,
            passed=False,
            stdout="",
            stderr="",
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    timed_out = False
    try:
        stdin_input = prompt.encode("utf-8") if config.stdin_prompt else None
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin_input),
            timeout=config.timeout_sec,
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_b, stderr_b = await proc.communicate()

    duration_ms = int((time.monotonic() - start) * 1000)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    exit_code = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)

    passed = True
    if exit_code == -1:
        passed = False
    elif config.fail_pattern:
        try:
            if re.search(config.fail_pattern, stdout, re.MULTILINE):
                passed = False
        except re.error:
            passed = False

    return PostEvaluationResult(
        cmd=argv,
        exit_code=exit_code,
        passed=passed,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )
