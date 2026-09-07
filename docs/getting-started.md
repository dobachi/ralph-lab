# Getting Started

**対象**: 初めて ralph-lab を触る人。5-10 分で 1 回 pass する経路まで案内。

**前提**:

- Python 3.10+
- git, curl
- OpenRouter API key (aider/opencode 経由の agent CLI で必要)
  - OR Anthropic 認証済 claude CLI

---

## 1. Install (2 分)

```bash
# clone + install
git clone git@github.com:dobachi/ralph-lab.git
cd ralph-lab

# uv (recommended) or pip
uv sync

# .env に OpenRouter key
cp .env.example .env
# vi .env  # OPENROUTER_API_KEY=... を書く

# 動作確認
uv run ralph --help
```

---

## 2. Agent CLI を 1 つ選ぶ (3 分)

3 通りの経路から 1 つ:

### 経路 A: claude CLI (敷居 ★☆☆)

前提: `claude` (Claude Code CLI) install 済、`~/.claude/` に認証済

```bash
# 動作確認
which claude
claude --version

# ralph-lab の template で spec 生成
uv run ralph init \
    --template claude \
    --name my-first \
    --input experiments/real-doc-refs/buggy.md \
    --output goals/my-first.yaml

# spec 検証
uv run ralph check goals/my-first.yaml

# 実行 (無料枠 or Max plan で cost ≈ $0)
uv run ralph run goals/my-first.yaml
```

### 経路 B: opencode + OpenRouter (敷居 ★★☆)

前提: Node.js/npm、`OPENROUTER_API_KEY` in `.env`

```bash
# Install
npm install -g opencode-ai

# spec 生成 + 実行
uv run ralph init --template opencode --name my-first \
    --input experiments/real-doc-refs/buggy.md \
    --output goals/my-first.yaml
uv run ralph run goals/my-first.yaml
```

**Cost 目安**: haiku-4.5 で 1 iter $0.01-0.02、5 iter で $0.05-0.10。

### 経路 C: aider + OpenRouter (敷居 ★★☆)

前提: `pipx` or `uv tool install`、`OPENROUTER_API_KEY`

```bash
uv tool install aider-chat

uv run ralph init --template aider --name my-first \
    --input experiments/real-doc-refs/buggy.md \
    --output goals/my-first.yaml
uv run ralph run goals/my-first.yaml
```

**注意**: aider + Anthropic model で SEARCH/REPLACE format 失敗の実測あり
(2026-09-06)。**model は OpenAI 系推奨**。詳細は
[knowhow/aider-integration.md](knowhow/aider-integration.md) §E。

---

## 3. 結果を見る (1 分)

`ralph run` の出力例:

```json
{
  "spec_name": "my-first",
  "status": "pass",       ← or judge_failed / max_iterations / judge_passed
  "iterations": 2,
  "workspace_root": "/tmp/ralph-lab-XXX",
  "total_duration_ms": 31730,
  "iteration_summaries": [...]
}
```

**Status の意味**:

| status | 意味 |
|---|---|
| `pass` | Ralph loop pass、判定 (Layer B/C あれば) も PASS |
| `judge_failed` | Ralph pass だが Layer C judge が FAIL |
| `max_iterations` | 5 iter で pass できず |
| `judge_passed` | max_iter だが Layer C が rescue 判定 (`run_always: true` 時のみ) |
| `timeout` | overall_timeout_sec を超過 |

**JSONL log**:

```bash
# 各 iter の詳細 (stdout_head 込み)
cat logs/my-first-runs.jsonl | python3 -m json.tool
```

**Workspace 中身**:

```bash
# 実行後の状態を確認 (keep_workspace=True の場合)
ls /tmp/ralph-lab-XXX/
# → BASE.md (chmod 444), current.md (agent 編集)

diff /tmp/ralph-lab-XXX/BASE.md /tmp/ralph-lab-XXX/current.md
```

---

## 4. Sample を追ってみる

もう少し複雑な例:

### Sample 1: 実文書の脚注参照修正 (`goals/examples/real-doc-refs.yaml`)

- 入力: buggy.md (壊れた `[^99]` ref)
- Gate: 3 check (対応関係 / 単調性 / 内容 non-empty)
- Agent は 5 iter 以内に fix を試みる

```bash
uv run ralph run goals/examples/real-doc-refs.yaml --pretty
```

### Sample 2: pytest の自動修正 (`goals/examples/code-fix-pytest.yaml`)

- 入力: 壊れた `calc.py` + tests/
- Gate: `pytest` の exit code

```bash
uv run ralph run goals/examples/code-fix-pytest.yaml --pretty
```

### Sample 3: 全機能統合 (`goals/examples/doc-verify-unified.yaml`)

- Layer A gate + Layer B (fact-checker + doc-review、retries=2 + retry_aggregate) + Layer C (OpenAI gpt-4o judge)
- **実運用テンプレとして参照可能**

```bash
uv run ralph run goals/examples/doc-verify-unified.yaml --pretty
```

Cost 目安 $0.30-0.60/run。

---

## 5. Multi-model 比較

同じ goal を複数 model で比較:

```bash
uv run ralph run goals/my-first.yaml \
    --models "openrouter/openai/gpt-4o-mini,openrouter/anthropic/claude-haiku-4.5"
```

model ごとに workspace が別々に作られ、結果を比較可能。詳細は
[knowhow/multi-model-comparison.md](knowhow/multi-model-comparison.md)。

---

## 6. 次に何を読む

- **概念を深く**: [architecture.md](architecture.md) — 4 層防御、Ralph pattern
- **spec 書き方**: [usage-manual.md](usage-manual.md) — 全 field の詳細
- **prompt 設計**: [knowhow/prompt-patterns.md](knowhow/prompt-patterns.md)
- **Gate 設計**: [knowhow/gate-design-patterns.md](knowhow/gate-design-patterns.md)
- **実験ログ**: [experiments/](experiments/) — P4-P26 の予測 vs 実測

## Troubleshooting

**「cmd not found」**: agent CLI が PATH にない。
`which claude` / `which aider` / `which opencode` で確認。

**「OPENROUTER_API_KEY not set」**: `.env` を load していない。
`set -a && source .env && set +a` で load してから `ralph run`。

**Status = max_iterations で pass しない**: Layer B/C 委譲を検討。
[knowhow/prompt-patterns.md](knowhow/prompt-patterns.md) の Pattern 2 (agent
prompt) で削除禁止・捏造禁止・clean fix hint を明示すると改善する場合あり。

**gate script が chmod +x されていない**: `chmod +x path/to/gate.sh`。
`ralph check` が warning を出す。

**Log が空**: `spec.log_path` の親 dir が存在しない or 権限なし。
`ralph check` で warning、mkdir で対応。
