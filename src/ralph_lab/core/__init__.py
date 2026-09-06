"""ralph-lab core: spec, agent_cli, workspace, gate, loop, init, check."""

from ralph_lab.core.agent_cli import AgentResult, run_agent
from ralph_lab.core.check import SpecIssue, check_spec, format_issues, has_errors
from ralph_lab.core.gate import GateResult, format_gate_feedback, run_gate
from ralph_lab.core.init import (
    InitOptions,
    discover_loop_goal_gate,
    generate_spec,
    list_templates,
)
from ralph_lab.core.loop import (
    IterationRecord,
    RalphResult,
    run_ralph_loop,
)
from ralph_lab.core.spec import AgentSpec, GateConfig, GoalSpec
from ralph_lab.core.workspace import Workspace

__all__ = [
    "AgentResult",
    "AgentSpec",
    "GateConfig",
    "GateResult",
    "GoalSpec",
    "InitOptions",
    "IterationRecord",
    "RalphResult",
    "SpecIssue",
    "Workspace",
    "check_spec",
    "discover_loop_goal_gate",
    "format_gate_feedback",
    "format_issues",
    "generate_spec",
    "has_errors",
    "list_templates",
    "run_agent",
    "run_gate",
    "run_ralph_loop",
]
