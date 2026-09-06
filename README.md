# ralph-lab

Gate-neutral **Ralph loop** driver in Python. Wraps agent CLIs
(claude / codex / gemini / opencode) in a subprocess loop, runs them until a
**user-supplied gate script** exits 0, and records everything as JSONL.

**Successor to [agent-loop-lab](https://github.com/dobachi/agent-loop-lab)**
(archived). Full rewrite; see [Prior art](#prior-art) for the history.

## Design principles

- **Ralph faithful.** Each iteration starts with a fresh subprocess.
  No shared context across iterations — context accumulation degrades
  quality past 100k-150k tokens (Ralph pattern, 2025).
- **Gate-neutral.** Any bash script that returns exit 0 / non-zero works.
  `loop-goal`, `pytest`, `cargo test`, `eslint`, `grep -q "…"` — all first
  class. `ralph-lab` doesn't care what the gate does; it just reads
  stdout as feedback and exit code as verdict.
- **Multi-agent CLI.** Switch between `claude`, `codex`, `gemini`,
  `opencode` without changing the loop.
- **Multi-model.** Run the same goal across N models to compare
  (`--models m1,m2,m3`), each in its own workspace, results in one JSONL
  for easy diffing.
- **Observability.** Every iteration records subprocess exit, duration,
  gate result, and stdout/stderr sizes. Iteration-level metric only
  (turn/tool-call metric is inside the agent CLI subprocess and not
  exposed).

## What ralph-lab does NOT do

- **No custom LLM SDK.** `openai-agents-python`, `anthropic-sdk`, etc.
  belong to the agent CLI, not to ralph-lab. If you want to change
  which SDK is used, use a different agent CLI or add flags via
  `agent_flags` in the spec.
- **No built-in gate.** Bring your own. `goals/examples/` shows several
  patterns.
- **No multi-agent coordination.** One agent CLI per run. For multi-agent
  workflows, orchestrate ralph-lab runs from outside.

## Prior art

Based on:

- Geoffrey Huntley's [Ralph loop pattern](https://ghuntley.com/ralph/) (2025)
- [syuya2036/ralph-loop](https://github.com/syuya2036/ralph-loop) (bash reference)
- [randomcodespace/ralph-loop](https://github.com/randomcodespace) (Python stdlib-only skill reference)
- [loop-goal](https://github.com/dobachi/claude-skills-marketplace) (dobachi/claude-skills-marketplace) — document verification skill,
  used as one of the example gates
- [agent-loop-lab](https://github.com/dobachi/agent-loop-lab) — predecessor (archived).
  Used openai-agents SDK, was tightly coupled to loop-goal. ralph-lab
  is a rewrite that drops the SDK and makes the gate optional.

## Status

**Pre-alpha.** Under active development (P6-1..P6-6).

- [x] P6-0: repo skeleton
- [ ] P6-1: minimal Ralph loop (subprocess with `claude -p`, 1 iteration)
- [ ] P6-2: gate.sh integration + workspace management (BASE/current)
- [ ] P6-3: multi-agent CLI (`--agent claude|codex|gemini`)
- [ ] P6-4: multi-model comparison (`--models m1,m2`)
- [ ] P6-5: observability (JSONL)
- [ ] P6-6: migrate v1 (agent-loop-lab) docs, archive v1

## Quick start (planned, not yet functional)

```bash
git clone git@github.com:dobachi/ralph-lab.git
cd ralph-lab
uv sync

# Bring your own gate script (any bash script returning exit 0/1)
cp .env.example .env

# Generate a spec (interactive)
uv run ralph init

# Or use a shipped example
uv run ralph run goals/examples/doc-verify-loop-goal.yaml
uv run ralph run goals/examples/code-tests-pytest.yaml
```

## Related projects

- [DevCurationViaAI](https://github.com/dobachi/DevCurationViaAI) — parent project (information curation system)
- [claude-skills-marketplace](https://github.com/dobachi/claude-skills-marketplace) — personal marketplace, home of loop-goal
- [agent-loop-lab](https://github.com/dobachi/agent-loop-lab) — v1 (archived), see for the design history

## License

MIT.
