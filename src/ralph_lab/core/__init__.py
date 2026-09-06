"""ralph-lab core: spec, agent_cli, workspace, gate, loop, init, check, delegation."""

from ralph_lab.core.agent_cli import AgentResult, run_agent
from ralph_lab.core.check import SpecIssue, check_spec, format_issues, has_errors
from ralph_lab.core.delegation import (
    DelegationResult,
    PostEvaluationResult,
    aggregate_delegations,
    run_all_delegations,
    run_delegation,
    run_post_evaluation,
)
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
from ralph_lab.core.spec import (
    AgentSpec,
    DelegationCall,
    GateConfig,
    GoalSpec,
    PostEvaluationConfig,
)
from ralph_lab.core.workspace import Workspace

__all__ = [
    "AgentResult",
    "AgentSpec",
    "DelegationCall",
    "DelegationResult",
    "GateConfig",
    "GateResult",
    "GoalSpec",
    "InitOptions",
    "IterationRecord",
    "PostEvaluationConfig",
    "PostEvaluationResult",
    "RalphResult",
    "SpecIssue",
    "Workspace",
    "aggregate_delegations",
    "check_spec",
    "discover_loop_goal_gate",
    "format_gate_feedback",
    "format_issues",
    "generate_spec",
    "has_errors",
    "list_templates",
    "run_agent",
    "run_all_delegations",
    "run_delegation",
    "run_gate",
    "run_post_evaluation",
    "run_ralph_loop",
]
