"""GoalSpec: v2 YAML-loaded goal definition (Ralph 型、subprocess ベース)。

Ralph 原則:
- 各 iteration で agent CLI を subprocess として起動
- Context は agent CLI 側で持たない (毎回 fresh)
- 状態はファイルシステム (workspace) と gate stdout で伝える

拡張 (P14, 2026-09-06):
- gate.delegate_to: 委譲呼び出し (Layer B、方式 B)
- post_evaluation: Ralph pass 後の判定 (Layer C、方式 C)
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
class DelegationCall:
    """1 件の委譲呼び出し (Layer B、方式 B の要素)。

    Ralph loop の gate.script が pass した後、または並行して、別スキル
    (fact-checker / doc-review / verify-content 等) を subprocess で呼び、
    その結果を集約して gate 判定に反映する。

    例:
        DelegationCall(
            name="fact-checker",
            cmd="claude",
            args=["-p", "--dangerously-skip-permissions"],
            prompt="Run /fact-checker on {file}. Output PASS or FAIL.",
            fail_pattern=r'^FAIL',
            timeout_sec=180.0,
        )
    """

    name: str
    """委譲の識別名 (log に出す)"""

    cmd: str
    """呼び出すコマンド (claude / codex / agy 等)"""

    args: list[str] = field(default_factory=list)
    """コマンドに渡す固定引数"""

    prompt: str = ""
    """subprocess に渡す prompt。`{file}` は current file の絶対 path に、
    `{base}` は BASE file の絶対 path に render 時に置換される"""

    fail_pattern: str = r"^FAIL"
    """subprocess の stdout に対する regex。match したら fail 判定"""

    timeout_sec: float = 300.0
    """subprocess の timeout"""

    stdin_prompt: bool = True
    """True なら prompt を stdin 経由、False なら args 末尾に append"""

    retries: int = 0
    """P20: LLM 非決定性回避。失敗時に n 回まで再試行 (any-pass 短絡)。
    - 0 (default): 単発実行、現行動作
    - N: 最大 N+1 回試行、いずれか PASS で終了
    - 再試行条件: passed=False かつ error is None (launch エラーは再試行しない)"""


@dataclass(frozen=True)
class GateConfig:
    """Gate script の呼び出し仕様。

    契約:
    - 呼び出し: `<script> <current_file>`
    - 環境変数: `BASE=<baseline_file>` (driver が自動で埋める)
    - Exit code: 0 = passed, non-zero = failed
    - stdout: 次 iteration の feedback として agent に渡される

    拡張:
    - delegate_to: syntactic gate pass 後に実行する委譲呼び出しの list
    - aggregate: 委譲結果の集約ルール (all_pass = 全部 pass で pass)
    """

    script: Path
    env: dict[str, str] = field(default_factory=dict)
    timeout_sec: float = 60.0

    delegate_to: list[DelegationCall] = field(default_factory=list)
    """Layer B の委譲呼び出し (方式 B)。syntactic gate pass 後に実行"""

    aggregate: str = "all_pass"
    """委譲結果の集約ルール。all_pass = 全部 pass で pass、any_pass = 1 つでも pass なら pass"""


@dataclass(frozen=True)
class PostEvaluationConfig:
    """Ralph loop の pass 後に呼ぶ最終評価 (Layer C、方式 C = LLM-as-judge)。

    Ralph loop が status=pass で終わった後、別 model で全体を judge する。
    Goodhart 型 hack の post-hoc 検出が主用途。

    Judge は Ralph loop の外側で 1 回だけ呼ばれる (cost 効率良)。
    """

    cmd: str
    """Judge の CLI (agent と異 provider 推奨、Goodhart 対策)"""

    args: list[str] = field(default_factory=list)
    """CLI 引数"""

    prompt: str = ""
    """Judge への prompt。`{file}` は最終 file の絶対 path に置換"""

    fail_pattern: str = r"^FAIL"
    """stdout の regex。match したら judge fail"""

    timeout_sec: float = 600.0
    """Judge 呼び出しの timeout"""

    stdin_prompt: bool = True
    """True なら prompt を stdin 経由"""

    model: str | None = None
    """モデル名 (agent と異なる provider が望ましい)"""

    run_always: bool = False
    """P19: True なら status=pass に加えて status=max_iterations でも judge を
    走らせる (Layer B の非決定的 FAIL で Layer C まで到達しないケースへの対策)。
    judge PASS on max_iter → 新 status=judge_passed で Ralph loop を rescue。
    judge FAIL on max_iter → status=max_iterations のまま (judge が失敗確認)。
    Default False で従来挙動。"""


@dataclass(frozen=True)
class GoalSpec:
    """Ralph loop の宣言的定義 (v2 + P14 拡張)。"""

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

    post_evaluation: PostEvaluationConfig | None = None
    """Ralph pass 後の judge 呼び出し (Layer C)。None なら post_evaluation なし"""

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

        # gate section (with optional delegate_to)
        gate_raw = data["gate"]
        if not isinstance(gate_raw, dict) or "script" not in gate_raw:
            raise ValueError(f"gate must be a mapping with a 'script' field in {yaml_path}")

        delegate_to_raw = gate_raw.get("delegate_to", [])
        delegate_to = []
        for i, d in enumerate(delegate_to_raw):
            if not isinstance(d, dict):
                raise ValueError(
                    f"gate.delegate_to[{i}] must be a mapping in {yaml_path}"
                )
            if "cmd" not in d:
                raise ValueError(
                    f"gate.delegate_to[{i}].cmd is required in {yaml_path}"
                )
            delegate_to.append(DelegationCall(
                name=str(d.get("name", f"delegation-{i}")),
                cmd=str(d["cmd"]),
                args=list(d.get("args", [])),
                prompt=str(d.get("prompt", "")),
                fail_pattern=str(d.get("fail_pattern", r"^FAIL")),
                timeout_sec=float(d.get("timeout_sec", 300.0)),
                stdin_prompt=bool(d.get("stdin_prompt", True)),
                retries=int(d.get("retries", 0)),
            ))

        gate = GateConfig(
            script=_resolve_path(gate_raw["script"], base_dir),
            env=dict(gate_raw.get("env", {})),
            timeout_sec=float(gate_raw.get("timeout_sec", 60.0)),
            delegate_to=delegate_to,
            aggregate=str(gate_raw.get("aggregate", "all_pass")),
        )

        # post_evaluation section (optional)
        post_eval_raw = data.get("post_evaluation")
        post_evaluation: PostEvaluationConfig | None = None
        if post_eval_raw is not None:
            if not isinstance(post_eval_raw, dict):
                raise ValueError(
                    f"post_evaluation must be a mapping in {yaml_path}"
                )
            if "cmd" not in post_eval_raw:
                raise ValueError(
                    f"post_evaluation.cmd is required in {yaml_path}"
                )
            post_evaluation = PostEvaluationConfig(
                cmd=str(post_eval_raw["cmd"]),
                args=list(post_eval_raw.get("args", [])),
                prompt=str(post_eval_raw.get("prompt", "")),
                fail_pattern=str(post_eval_raw.get("fail_pattern", r"^FAIL")),
                timeout_sec=float(post_eval_raw.get("timeout_sec", 600.0)),
                stdin_prompt=bool(post_eval_raw.get("stdin_prompt", True)),
                model=post_eval_raw.get("model"),
                run_always=bool(post_eval_raw.get("run_always", False)),
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
            post_evaluation=post_evaluation,
        )


def _resolve_path(raw: Any, base_dir: Path) -> Path:
    """Expand ~ and resolve relative paths against `base_dir`."""
    p = Path(os.path.expandvars(str(raw))).expanduser()
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p
