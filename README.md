# ralph-lab

Gate-neutral **Ralph loop** driver in Python. Wraps agent CLIs
(claude / aider / opencode) in a subprocess loop, runs them until a
**user-supplied gate script** exits 0, and records everything as JSONL.

**Successor to [agent-loop-lab](https://github.com/dobachi/agent-loop-lab)**
(archived). Full rewrite; see [Prior art](#prior-art).

## Design principles

- **Ralph faithful.** Each iteration starts with a fresh subprocess.
  No shared context across iterations — context accumulation degrades
  quality past 100k-150k tokens (Ralph pattern, 2025).
- **Gate-neutral.** Any bash script that returns exit 0 / non-zero works.
  `loop-goal`, `pytest`, `cargo test`, `eslint`, `grep -q "…"` — all first
  class.
- **Multi-agent CLI.** Switch between `claude`, `aider`, `opencode` etc.
  without changing framework code — only the spec YAML.
- **Multi-model.** Run the same goal across N models to compare
  (`--models m1,m2,m3`), each in its own workspace.
- **Observability.** Every iteration recorded as one JSONL line
  (exit code, duration, gate result, stdout/stderr sizes).

## Status

**Alpha.** ~P14 complete (2026-09-06):

- [x] Core loop (subprocess ベース, gate 中立)
- [x] Multi-model 比較 (`ralph run --models m1,m2,m3`)
- [x] `ralph init` / `ralph check` サブコマンド
- [x] 3 templates: claude / aider / opencode
- [x] Observability (JSONL log)
- [x] Docs (knowhow / experiments / research)
- [x] **委譲機構 (P14)**: `gate.delegate_to[]` (方式 B) + `post_evaluation` (方式 C)
- [ ] `--parallel` for multi-model (直列のみ)
- [ ] Cost tracking (OpenRouter `/generation` endpoint)
- [ ] Windows 対応 (`/dev/stdin` 依存の解消)

## Prerequisites

Python 3.10+、[uv](https://docs.astral.sh/uv/) (推奨) or pip、
そして **少なくとも 1 つの agent CLI** (下記 Quickstart で選ぶ)。

## Quickstart

まずは基本セットアップ:

```bash
git clone git@github.com:dobachi/ralph-lab.git
cd ralph-lab
uv sync

cp .env.example .env
# .env に OPENROUTER_API_KEY を書く (aider / opencode 経路で必要)
```

3 通りの agent CLI から 1 つ選んでください。**動かすまで最短 5 分**:

### 経路 A: claude CLI 直 (敷居 ★☆☆)

前提: `claude` (Claude Code CLI) が install 済、`~/.claude` に認証済 (Anthropic Max / 従量課金)

```bash
# spec を生成 (対話)
uv run ralph init --template claude --name my-doc \
    --input ~/.claude/plugins/cache/dobachi-skills/loop-goal/0.3.0/skills/loop-goal/detectors/fixtures/broken_ref.md \
    --output goals/my-doc.yaml

# 検証
uv run ralph check goals/my-doc.yaml

# 実行
uv run ralph run goals/my-doc.yaml
```

**Model**: default は claude CLI の default (通常 haiku)。`agent.model:
claude-sonnet-4-5` 等で切替可。

### 経路 B: aider + OpenRouter (敷居 ★★☆)

前提: OpenRouter API key、`aider` CLI

```bash
# aider install (Python only)
uv tool install aider-chat

# spec 生成
uv run ralph init --template aider --name my-doc-aider \
    --input .../broken_ref.md \
    --output goals/my-doc-aider.yaml

# 実行
uv run ralph run goals/my-doc-aider.yaml
```

**Model 切替**:
```bash
uv run ralph run goals/my-doc-aider.yaml --model openrouter/openai/gpt-4o-mini
uv run ralph run goals/my-doc-aider.yaml --models "openrouter/openai/gpt-4.1-mini,openrouter/openai/gpt-4o-mini"
```

**注意**: aider は Anthropic model 経由 OpenRouter で SEARCH/REPLACE format
生成失敗の実測あり (2026-09-06)。**model は OpenAI 系推奨**。詳細は
[docs/knowhow/aider-integration.md §E](docs/knowhow/aider-integration.md)。

### 経路 C: opencode + OpenRouter (敷居 ★★☆)

前提: OpenRouter API key、Node.js/npm

```bash
# opencode install (Node.js)
npm install -g opencode-ai

# spec 生成
uv run ralph init --template opencode --name my-doc-opencode \
    --input .../broken_ref.md \
    --output goals/my-doc-opencode.yaml

# 実行
uv run ralph run goals/my-doc-opencode.yaml
```

**opencode 固有ノウハウ**: `-f` (file attach) と長い prompt が衝突する
ため `stdin_prompt: true` 必須。template で対応済み。詳細は
[docs/knowhow/agent-cli-opencode.md](docs/knowhow/agent-cli-opencode.md)。

## Delegation: 苦手な judge を別スキルに委譲する (P14)

Ralph-lab の gate は syntactic 判定に強く、semantic 判定は苦手。
既存の他スキル (fact-checker / doc-review / verify-content 等) や
別 model の LLM-as-judge に **subprocess で委譲**できる。3 方式:

**方式 A: `gate.sh` 内で subprocess** — core 変更ゼロ。
[experiments/delegating-gate/](experiments/delegating-gate/) 参照。

**方式 B: `spec.yaml` の `gate.delegate_to[]`** — Layer B。
Syntactic gate pass 後に走る委譲群を宣言的に書ける:

```yaml
gate:
  script: experiments/real-doc-refs/gate.sh
  delegate_to:
    - name: fact-checker
      cmd: claude
      args: [-p, --dangerously-skip-permissions]
      prompt: |
        Invoke the fact-checker skill on {file}.
        Output PASS or FAIL: <reason>.
      fail_pattern: '^FAIL'
      stdin_prompt: true
      timeout_sec: 180
  aggregate: all_pass  # or any_pass
```

**方式 C: `spec.yaml` の `post_evaluation`** — Layer C (LLM-as-judge)。
Ralph pass 後 **1 回だけ** 走る post-hoc 判定:

```yaml
post_evaluation:
  cmd: claude
  args: [-p, --dangerously-skip-permissions]
  prompt: |
    Detect Goodhart-type hacks in {file}. Output PASS or FAIL: <reason>.
  fail_pattern: '^FAIL'
  stdin_prompt: true
```

- 完全例: [goals/examples/doc-verify-delegating.yaml](goals/examples/doc-verify-delegating.yaml)
- 設計解説: [docs/knowhow/gate-delegation-patterns.md](docs/knowhow/gate-delegation-patterns.md)
- **警告**: judge は agent と異 provider を推奨 (Goodhart 相関エラー対策)

## What ralph-lab does NOT do

- **No custom LLM SDK.** `openai-agents-python`, `anthropic-sdk` 等は
  agent CLI に任せる。ralph-lab は subprocess を起動するだけ
- **No built-in gate.** 任意の bash script を持ち込む。`loop-goal` は
  example の 1 つ
- **No multi-agent coordination.** 1 spec = 1 agent CLI。複数 agent の
  orchestration は外側で組む

## CLI 一覧

```bash
ralph run <spec.yaml>                   # 実行
ralph run <spec.yaml> --model M         # model 上書き
ralph run <spec.yaml> --models m1,m2    # 多 model 比較
ralph init [--template claude|aider|opencode]   # spec 生成 (対話 or フラグ)
ralph check <spec.yaml>                 # spec の validation
```

## Docs

- [docs/README.md](docs/README.md) — docs 全体の目次
- [docs/knowhow/](docs/knowhow/) — 実装で得た再現性あるノウハウ
- [docs/experiments/](docs/experiments/) — 予測 → 実測の記録
- [docs/research/](docs/research/) — Ralph landscape 調査

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

## Related projects

- [DevCurationViaAI](https://github.com/dobachi/DevCurationViaAI) — parent project (information curation system)
- [claude-skills-marketplace](https://github.com/dobachi/claude-skills-marketplace) — personal marketplace, home of loop-goal
- [agent-loop-lab](https://github.com/dobachi/agent-loop-lab) — v1 (archived), see for design history

## License

MIT.
