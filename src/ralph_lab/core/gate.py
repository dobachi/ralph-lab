"""Gate script 呼び出し: 任意の bash script を subprocess で実行する。

Ralph 原則の中核 — 完了判定は agent 自身ではなく外部の決定的コマンドで行う。
Reflexion 系の自己批評との決定的な違い。

契約 (spec.GateConfig と対応):
- 呼び出し: `<script> <current_file>`
- 環境変数: `BASE=<baseline_file>` (driver が自動で埋める)
- Exit code: 0 = passed, non-zero = failed
- stdout: 次 iteration の feedback として agent に渡される
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from ralph_lab.core.spec import GateConfig
from ralph_lab.core.workspace import Workspace


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    """0 = pass, non-zero = fail, -1 = 実行失敗 (script なし等)"""

    passed: bool
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


async def run_gate(config: GateConfig, workspace: Workspace) -> GateResult:
    """`config.script <workspace.current>` を BASE=workspace.base で走らせる。

    Never raises: timeout / 実行不能でも GateResult を返す。
    """
    start = time.monotonic()
    env = {
        **os.environ,
        "BASE": str(workspace.base),
        **config.env,
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            str(config.script),
            str(workspace.current),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError) as exc:
        return GateResult(
            exit_code=-1,
            passed=False,
            stdout="",
            stderr=f"failed to launch gate: {type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=False,
        )

    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(),
            timeout=config.timeout_sec,
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_b, stderr_b = await proc.communicate()

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    duration_ms = int((time.monotonic() - start) * 1000)
    exit_code = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)

    return GateResult(
        exit_code=exit_code,
        passed=(exit_code == 0),
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


def format_gate_feedback(result: GateResult, max_chars: int = 6000) -> str:
    """gate の stdout を次 iteration の agent 向け feedback に整形。"""
    lines: list[str] = []
    lines.append(f"--- Gate result (exit code: {result.exit_code}) ---")
    if result.timed_out:
        lines.append("**TIMED OUT.** gate did not complete within its budget.")
    if result.stderr.strip():
        lines.append("--- stderr ---")
        lines.append(result.stderr.strip())
    lines.append("--- stdout ---")
    lines.append(result.stdout)
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars] + "\n[...TRUNCATED...]"
    return body
