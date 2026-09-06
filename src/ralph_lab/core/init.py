"""Spec 生成 (ralph init) の実装。

対話 or フラグで template placeholder を埋めて goals/<name>.yaml を書き出す。
LLM は使わない — 機械的置換のみ。

v1 (agent-loop-lab/core/init.py) からの主な変更:
- template は agent CLI 毎に 3 種 (claude.yaml / aider.yaml / opencode.yaml)
- `--template <cli>` で選択 (default: claude、最も敷居低い)
- placeholder MAX_OUTER_ITERATIONS → MAX_ITERATIONS (v2 spec に合わせる)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_LOOP_GOAL_CACHE_ROOT = (
    Path.home() / ".claude" / "plugins" / "cache" / "dobachi-skills" / "loop-goal"
)

# Template ごとの default model
_DEFAULT_MODELS = {
    "claude": "",  # empty = CLI default (通常 haiku)
    "aider": "openrouter/openai/gpt-4.1-mini",
    "opencode": "openrouter/openai/gpt-4.1-mini",
}


@dataclass
class InitOptions:
    """Spec 生成に必要な値。None は対話で聞く。"""

    name: str | None = None
    input_document: str | None = None
    template: str = "claude"
    model: str | None = None  # None なら template の default を使う
    gate_script: str | None = None  # None なら loop-goal を自動探索
    max_iterations: int = 5
    log_path: str = "logs/ralph-runs.jsonl"
    description: str = "Ralph loop goal spec."
    output: Path | None = None  # None なら goals/<name>.yaml
    force: bool = False  # 上書き許可


def discover_loop_goal_gate() -> Path | None:
    """~/.claude/plugins/cache/dobachi-skills/loop-goal/*/skills/loop-goal/gate.sh
    を探す。複数バージョンあれば最新 (辞書順で最後) を返す。無ければ None。
    """
    if not _LOOP_GOAL_CACHE_ROOT.is_dir():
        return None
    versions = sorted(_LOOP_GOAL_CACHE_ROOT.iterdir(), key=lambda p: p.name)
    for v in reversed(versions):
        candidate = v / "skills" / "loop-goal" / "gate.sh"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def list_templates(project_root: Path) -> list[str]:
    """goals/templates/ にある template 名の list (stem)。"""
    templates_dir = project_root / "goals" / "templates"
    if not templates_dir.is_dir():
        return []
    return sorted(p.stem for p in templates_dir.glob("*.yaml"))


def _prompt(msg: str, default: str | None = None, *, required: bool = True) -> str:
    """簡易 stdin prompt。default があれば Enter で採用。"""
    if default is not None:
        display = f"{msg} [{default}]: "
    else:
        display = f"{msg}: "
    while True:
        try:
            answer = input(display).strip()
        except EOFError:
            answer = ""
        if not answer and default is not None:
            return default
        if answer:
            return answer
        if not required:
            return ""
        print("  (required)", file=sys.stderr)


def _load_template(template_name: str, project_root: Path) -> str:
    """goals/templates/<name>.yaml を読み込む。"""
    path = project_root / "goals" / "templates" / f"{template_name}.yaml"
    if not path.is_file():
        available = list_templates(project_root)
        raise FileNotFoundError(
            f"template not found: {path}. Available: {available}"
        )
    return path.read_text(encoding="utf-8")


def _substitute(template_text: str, values: dict[str, str]) -> str:
    """${KEY} を values[KEY] で置換。単純置換 (nested / escape はサポートしない)。"""
    result = template_text
    for key, value in values.items():
        result = result.replace(f"${{{key}}}", value)
    return result


def _resolve_defaults(opts: InitOptions) -> None:
    """未指定の gate_script / model を default で埋める。"""
    if opts.gate_script is None:
        found = discover_loop_goal_gate()
        if found:
            opts.gate_script = str(found)
        else:
            print(
                "WARNING: loop-goal not found in ~/.claude/plugins/cache. "
                "Falling back to a placeholder; edit `gate.script` in the "
                "output file to point to a real gate script.",
                file=sys.stderr,
            )
            opts.gate_script = "/path/to/gate.sh"
    if opts.model is None:
        opts.model = _DEFAULT_MODELS.get(opts.template, "")


def _fill_interactively(opts: InitOptions, project_root: Path) -> InitOptions:
    """未指定 field を対話で埋める。"""
    if opts.name is None:
        opts.name = _prompt("Spec name (kebab-case, e.g. my-goal)")
    if opts.input_document is None:
        opts.input_document = _prompt(
            "Input document path (absolute or relative to CWD)"
        )
    # optional な項目は default 有り prompt
    available = list_templates(project_root)
    opts.template = _prompt(
        f"Template (choices: {', '.join(available)})",
        default=opts.template,
    )
    template_default_model = _DEFAULT_MODELS.get(opts.template, "")
    opts.model = _prompt(
        "Model (empty = CLI default)",
        default=opts.model if opts.model is not None else template_default_model,
        required=False,
    )
    opts.gate_script = _prompt(
        "Gate script path",
        default=opts.gate_script or "/path/to/gate.sh",
    )
    opts.max_iterations = int(
        _prompt("max_iterations", default=str(opts.max_iterations))
    )
    return opts


def generate_spec(opts: InitOptions, project_root: Path) -> Path:
    """`opts` に従って spec YAML を生成し、書き出したパスを返す。

    未指定 field があれば対話で埋める (TTY 無しなら error)。
    """
    _resolve_defaults(opts)

    # 必須 field の対話補完
    if opts.name is None or opts.input_document is None:
        if not sys.stdin.isatty():
            missing = [
                k for k in ("name", "input_document") if getattr(opts, k) is None
            ]
            raise ValueError(
                f"Interactive fill requires a TTY. Provide flags for: {missing}"
            )
        opts = _fill_interactively(opts, project_root)

    # 出力パス決定
    output = opts.output or (project_root / "goals" / f"{opts.name}.yaml")
    if output.exists() and not opts.force:
        raise FileExistsError(
            f"{output} already exists. Use --force to overwrite."
        )

    # input_document を絶対パス化
    input_abs = Path(opts.input_document).expanduser()
    if not input_abs.is_absolute():
        input_abs = Path.cwd() / input_abs
    input_abs = input_abs.resolve()

    template_text = _load_template(opts.template, project_root)
    values = {
        "NAME": opts.name or "",
        "DESCRIPTION": opts.description,
        "INPUT_DOCUMENT": str(input_abs),
        "MODEL": opts.model or "",
        "GATE_SCRIPT": opts.gate_script or "",
        "MAX_ITERATIONS": str(opts.max_iterations),
        "LOG_PATH": opts.log_path,
    }
    rendered = _substitute(template_text, values)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return output
