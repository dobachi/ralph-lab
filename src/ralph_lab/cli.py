"""ralph CLI.

Subcommands:
    run    — spec YAML を実行 (multi-model 対応)
    init   — 対話 or フラグで spec YAML を生成
    check  — spec YAML を validation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from ralph_lab.core.check import check_spec, format_issues, has_errors
from ralph_lab.core.init import InitOptions, generate_spec
from ralph_lab.core.loop import RalphResult, run_ralph_loop
from ralph_lab.core.spec import GoalSpec

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# ↑ src/ralph_lab/cli.py → project root


def _result_summary(result: RalphResult, *, model: str | None = None) -> dict:
    summary = {
        "spec_name": result.spec_name,
        "status": result.status,
        "iterations": result.iterations,
        "workspace_root": str(result.workspace_root),
        "total_duration_ms": result.total_duration_ms,
        "iteration_summaries": [
            {
                "iteration": r.iteration,
                "agent": {
                    "cmd": r.agent.cmd[0] if r.agent.cmd else "",
                    "exit_code": r.agent.exit_code,
                    "duration_ms": r.agent.duration_ms,
                    "stdout_size": len(r.agent.stdout),
                    "stderr_size": len(r.agent.stderr),
                    "timed_out": r.agent.timed_out,
                },
                "gate": {
                    "exit_code": r.gate.exit_code,
                    "passed": r.gate.passed,
                    "duration_ms": r.gate.duration_ms,
                    "timed_out": r.gate.timed_out,
                },
                "prompt_size": r.prompt_size,
                "feedback_used_size": len(r.feedback_used) if r.feedback_used else 0,
            }
            for r in result.records
        ],
    }
    if model is not None:
        summary["model"] = model
    return summary


def _resolve_models(args: argparse.Namespace, spec: GoalSpec) -> list[str | None]:
    """--models > --model > spec.agent.model の優先順で解決。

    Returns:
        model 名の list。1 要素なら単発、複数なら multi-model 実行。
        spec に model が無く CLI からも指定なしの場合は [None] (agent CLI の default 使用)。
    """
    if getattr(args, "models", None):
        return [m.strip() for m in args.models.split(",") if m.strip()]
    if getattr(args, "model", None):
        return [args.model]
    return [spec.agent.model]  # None も許容


async def _run_one(
    spec: GoalSpec,
    model: str | None,
    *,
    workspace_root: Path | None,
    keep_workspace: bool,
) -> dict:
    """1 model 分の run + summary 変換。1 model 失敗しても raise しない。"""
    # spec.agent (frozen dataclass) を model 上書きで複製
    agent_updated = replace(spec.agent, model=model)
    spec_updated = replace(spec, agent=agent_updated)
    try:
        result = await run_ralph_loop(
            spec_updated,
            workspace_root=workspace_root,
            keep_workspace=keep_workspace,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "spec_name": spec.name,
            "model": model,
            "status": "init_error",
            "error": f"{type(exc).__name__}: {exc}",
            "iterations": 0,
            "iteration_summaries": [],
        }
    return _result_summary(result, model=model)


async def _run_all(
    spec: GoalSpec,
    models: list[str | None],
    *,
    workspace_root: Path | None,
    keep_workspace: bool,
) -> list[dict]:
    """複数 model を直列に実行 (並列にしない: local IO + API rate 保護)。"""
    summaries: list[dict] = []
    for idx, model in enumerate(models):
        ws_root = None
        if workspace_root is not None:
            if len(models) == 1:
                ws_root = workspace_root
            else:
                safe_name = (model or "default").replace("/", "_").replace(":", "_")
                ws_root = workspace_root / f"{idx:02d}-{safe_name}"
            ws_root.mkdir(parents=True, exist_ok=True)
        summary = await _run_one(
            spec, model,
            workspace_root=ws_root,
            keep_workspace=keep_workspace,
        )
        summaries.append(summary)
    return summaries


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        spec = GoalSpec.from_yaml(args.spec)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: failed to load spec: {exc}", file=sys.stderr)
        return 4

    models = _resolve_models(args, spec)

    try:
        summaries = asyncio.run(
            _run_all(
                spec, models,
                workspace_root=args.workspace_root,
                keep_workspace=args.keep_workspace,
            )
        )
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if len(summaries) == 1:
        payload: object = summaries[0]
    else:
        payload = {
            "spec_name": spec.name,
            "models_count": len(summaries),
            "runs": summaries,
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))

    if all(s["status"] == "pass" for s in summaries):
        return 0
    if any(s["status"] == "timeout" for s in summaries):
        return 2
    return 1


def _cmd_init(args: argparse.Namespace) -> int:
    """`ralph init` — spec 生成。生成後に自動 check (--no-check で無効)。"""
    opts = InitOptions(
        name=args.name,
        input_document=args.input,
        template=args.template,
        model=args.model,
        gate_script=args.gate,
        max_iterations=args.max_iterations,
        log_path=args.log_path,
        description=args.description or "Ralph loop goal spec.",
        output=args.output,
        force=args.force,
    )
    try:
        out_path = generate_spec(opts, _PROJECT_ROOT)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    print(f"wrote: {out_path}")

    # 生成直後に自動 check
    if not args.no_check:
        try:
            spec = GoalSpec.from_yaml(out_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"WARNING: generated spec failed to load: {exc}", file=sys.stderr)
            return 0
        issues = check_spec(spec)
        print()
        print(format_issues(issues))
        if has_errors(issues):
            print("\nFix the errors above before running the spec.", file=sys.stderr)
            return 0  # 生成自体は成功
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """`ralph check` — spec validation。"""
    try:
        spec = GoalSpec.from_yaml(args.spec)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: failed to load spec: {exc}", file=sys.stderr)
        return 4

    issues = check_spec(spec)
    print(format_issues(issues))
    return 1 if has_errors(issues) else 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ralph",
        description=(
            "Gate-neutral Ralph loop driver. Wrap agent CLIs in a subprocess "
            "loop until a user-supplied gate exits 0."
        ),
    )
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")

    # ---- run ----
    run_p = sub.add_parser("run", help="Run a Ralph loop from a spec YAML.")
    run_p.add_argument("spec", help="Path to spec YAML.")
    mg = run_p.add_mutually_exclusive_group()
    mg.add_argument("--model", help="Override spec.agent.model (single run).")
    mg.add_argument("--models",
                    help="Comma-separated list. Runs the goal once per model, "
                         "each in its own workspace subdirectory.")
    run_p.add_argument("--workspace-root", type=Path, default=None,
                       help="Workspace directory (default: tempfile.mkdtemp). "
                            "In --models mode, each model gets NN-<model_slug>/ subdir.")
    keep = run_p.add_mutually_exclusive_group()
    keep.add_argument("--keep-workspace", dest="keep_workspace",
                      action="store_true", default=True,
                      help="Keep workspace after run (default).")
    keep.add_argument("--no-keep-workspace", dest="keep_workspace",
                      action="store_false",
                      help="Delete workspace after run.")
    run_p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    run_p.set_defaults(func=_cmd_run)

    # ---- init ----
    init_p = sub.add_parser("init", help="Generate a new spec YAML from a template.")
    init_p.add_argument("--name", help="Spec name (kebab-case). Prompted if omitted.")
    init_p.add_argument("--input", help="Input document path. Prompted if omitted.")
    init_p.add_argument("--template", default="claude",
                        help="Template name under goals/templates/ "
                             "(claude / aider / opencode). Default: claude.")
    init_p.add_argument("--model", help="Model. Empty for CLI default.")
    init_p.add_argument("--gate", help="Gate script path. Default: auto-discover loop-goal.")
    init_p.add_argument("--max-iterations", type=int, default=5,
                        help="max_iterations (default: 5).")
    init_p.add_argument("--log-path", default="logs/ralph-runs.jsonl",
                        help="JSONL log path (default: logs/ralph-runs.jsonl).")
    init_p.add_argument("--description", help="Free-text description.")
    init_p.add_argument("--output", type=Path, default=None,
                        help="Output path (default: goals/<name>.yaml).")
    init_p.add_argument("--force", action="store_true", help="Overwrite if output exists.")
    init_p.add_argument("--no-check", action="store_true",
                        help="Skip validation after generation.")
    init_p.set_defaults(func=_cmd_init)

    # ---- check ----
    check_p = sub.add_parser("check", help="Validate a spec YAML.")
    check_p.add_argument("spec", help="Path to spec YAML to validate.")
    check_p.set_defaults(func=_cmd_check)

    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
