"""ralph CLI: `ralph run <spec.yaml>` の最小実装。

`init` / `check` サブコマンドは P6 で後追い予定。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from ralph_lab.core.loop import RalphResult, run_ralph_loop
from ralph_lab.core.spec import GoalSpec


def _result_summary(result: RalphResult) -> dict:
    return {
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


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        spec = GoalSpec.from_yaml(args.spec)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: failed to load spec: {exc}", file=sys.stderr)
        return 4

    try:
        result = asyncio.run(
            run_ralph_loop(
                spec,
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

    print(json.dumps(_result_summary(result), ensure_ascii=False, indent=2 if args.pretty else None))
    if result.passed:
        return 0
    if result.status == "timeout":
        return 2
    return 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ralph",
        description="Gate-neutral Ralph loop driver. Wrap agent CLIs in a subprocess loop until a user-supplied gate exits 0.",
    )
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")

    run_p = sub.add_parser("run", help="Run a Ralph loop from a spec YAML.")
    run_p.add_argument("spec", help="Path to spec YAML.")
    run_p.add_argument("--workspace-root", type=Path, default=None,
                       help="Workspace directory (default: tempfile.mkdtemp).")
    keep = run_p.add_mutually_exclusive_group()
    keep.add_argument("--keep-workspace", dest="keep_workspace",
                      action="store_true", default=True,
                      help="Keep workspace after run (default).")
    keep.add_argument("--no-keep-workspace", dest="keep_workspace",
                      action="store_false",
                      help="Delete workspace after run.")
    run_p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    run_p.set_defaults(func=_cmd_run)

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
