"""Agent CLI 起動: subprocess で claude/codex/gemini などを呼ぶ。

Ralph 原則忠実な実装 — 毎回 fresh subprocess を立ち上げ、prompt を stdin
(or args) から流し込む。agent CLI 側の context は iteration ごとに捨てられる。

ralph-lab はどの agent CLI を使うか、どんな model を使うかを知らない。
spec.agent に書かれた cmd/args/env をそのまま subprocess に渡すだけ。
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path

from ralph_lab.core.spec import AgentSpec


@dataclass(frozen=True)
class AgentResult:
    """Agent CLI subprocess 1 回の実行結果。"""

    cmd: list[str]
    """実際に起動された argv (デバッグ用)"""

    exit_code: int
    """0 = 成功と見なす (ただし agent CLI ごとに意味は違う)。-1 = 実行失敗"""

    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


async def run_agent(
    spec: AgentSpec,
    prompt: str,
    *,
    workdir: Path,
    timeout_sec: float,
) -> AgentResult:
    """`spec.cmd` を subprocess として起動し `prompt` を渡す。

    Never raises: エラーは AgentResult に格納する (outer loop が
    1 iteration の失敗で全体を落とさないため)。

    Args:
        spec: どの CLI をどう起動するか
        prompt: agent に渡す prompt (PROMPT.md 全体)
        workdir: subprocess の cwd。通常は workspace.root
        timeout_sec: subprocess の hard timeout
    """
    start = time.monotonic()

    # argv 組み立て
    argv = [spec.cmd] + list(spec.args)
    if spec.model is not None:
        # 標準化: --model を末尾に足す。agent CLI ごとに flag 名が違う場合は
        # spec.args に手で --model を書いてもらう (spec.model は省略)
        argv.extend(["--model", spec.model])

    if not spec.stdin_prompt:
        argv.append(prompt)

    # env 組み立て
    env = {**os.environ, **spec.env}

    # 起動
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if spec.stdin_prompt else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
            env=env,
        )
    except (FileNotFoundError, PermissionError) as exc:
        return AgentResult(
            cmd=argv,
            exit_code=-1,
            stdout="",
            stderr=f"failed to launch agent: {type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=False,
        )

    timed_out = False
    try:
        stdin_input = prompt.encode("utf-8") if spec.stdin_prompt else None
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=stdin_input),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_b, stderr_b = await proc.communicate()

    duration_ms = int((time.monotonic() - start) * 1000)
    exit_code = -1 if timed_out else (proc.returncode if proc.returncode is not None else -1)

    return AgentResult(
        cmd=argv,
        exit_code=exit_code,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
        duration_ms=duration_ms,
        timed_out=timed_out,
    )
