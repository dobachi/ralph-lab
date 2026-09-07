# Usage Manual

**対象**: spec.yaml を自分で書きたい、任意 agent CLI / gate を組み込みたい人。
Getting Started の次に読む。

---

## 1. spec.yaml 完全ガイド

必須 / optional の field を一覧化 (2026-09-07 時点)。

### 必須 field

```yaml
name: my-project              # str, workspace 名等に使う
description: |                # 何をする spec か
  Multi-line description...
input_document: path/to/x.md  # file or dir (P9 で dir 対応)
agent:                        # AgentSpec
  cmd: opencode               # PATH 上の CLI
  args: [run, --auto]         # 固定引数
  model: openrouter/anthropic/claude-haiku-4.5  # optional
prompt: |                     # agent への PROMPT.md
  Target: $CURRENT ($BASE, $ITER, $PREV_GATE_OUTPUT も使える)
  ...
gate:                         # GateConfig
  script: path/to/gate.sh     # exit 0 = pass
```

### Optional field

```yaml
baseline_document: path/to/correct.md  # BASE と current が別 source (P13)
max_iterations: 5             # default 5
overall_timeout_sec: 900      # default 15 分
agent_timeout_sec: 600        # 1 iter の agent subprocess
log_path: logs/my-runs.jsonl  # default logs/ralph-runs.jsonl

gate:
  timeout_sec: 60             # gate 単体の timeout
  env:                        # gate に渡す追加環境変数
    CUSTOM_VAR: value
  delegate_to:                # Layer B (P14)
    - name: fact-checker
      cmd: claude
      args: [-p, --dangerously-skip-permissions]
      prompt: |
        Invoke fact-checker on {file}. Output PASS or FAIL: <reason>.
      fail_pattern: '^FAIL'
      timeout_sec: 180
      stdin_prompt: true
      retries: 2              # P20
      retry_aggregate: any_pass  # P26 - any_pass / all_pass / majority
  aggregate: all_pass         # delegations 集約: all_pass or any_pass

post_evaluation:              # Layer C (P14)
  cmd: judge-openrouter
  args: [--model, openai/gpt-4o]
  prompt: |
    An AI agent edited {file} ({file_content}).
    Detect Goodhart hacks. Output PASS or FAIL.
  fail_pattern: '^FAIL'
  timeout_sec: 180
  stdin_prompt: true
  run_always: true            # P19 - max_iter でも判定
```

### Placeholder 一覧

| Placeholder | 場所 | 展開 |
|---|---|---|
| `$CURRENT` | prompt, agent.args | workspace の current file/dir 絶対 path |
| `$BASE` | prompt, agent.args | workspace の BASE 絶対 path |
| `$ITER` | prompt, agent.args | 現在 iter (1-indexed) |
| `$MAX_ITER` | prompt, agent.args | 最大 iter |
| `$PREV_GATE_OUTPUT` | prompt のみ | 前 iter の gate stdout |
| `{file}` | delegate_to.prompt, post_evaluation.prompt | current 絶対 path |
| `{base}` | 同上 | BASE 絶対 path |
| `{file_content}` | 同上 (P16) | current の中身 inline |
| `{base_content}` | 同上 | BASE の中身 inline |

---

## 2. CLI 一覧

```bash
ralph run <spec.yaml>                       # 実行
ralph run <spec.yaml> --pretty              # JSON pretty print
ralph run <spec.yaml> --model M             # spec.agent.model 上書き
ralph run <spec.yaml> --models m1,m2,m3     # multi-model 直列
ralph run <spec.yaml> --workspace-root DIR  # workspace 位置固定

ralph init [--template claude|aider|opencode] \
    --name N --input path --output goals/N.yaml
    # spec を対話 or フラグで生成

ralph check <spec.yaml>                     # 静的検証
```

`ralph check` は以下を検査:

- File 存在: `input_document`, `baseline_document`, `gate.script`
- Executable: `gate.script` の `+x` bit
- PATH: `agent.cmd`, `delegate_to[N].cmd`, `post_evaluation.cmd`
- 数値: `max_iterations >= 1`, timeouts > 0
- Prompt: 非空、短すぎないか (warning)
- Env: `OPENROUTER_API_KEY` が必要な agent/judge を使うか
- Model 一致: judge model と agent model が同じ → info (Goodhart 相関)
- Retry: `retries` の範囲、`retry_aggregate` の値、majority + even N+1

---

## 3. Layer 別の書き方

### Layer A: syntactic gate.sh

Bash + Python embedded の混在が最も柔軟:

```bash
#!/bin/bash
set -u
CURRENT="${1:?}"
BASE="${BASE:-}"

python3 - "$CURRENT" "$BASE" <<'PY'
import re, sys
current = open(sys.argv[1]).read()
# ... check logic ...
if problem:
    print("❌ 問題を発見: ...")
    print("   → 修正方向: ...")  # Pattern 3: 修正 hint
    sys.exit(1)
print("OK")
sys.exit(0)
PY
```

**注意点**:

- `chmod +x gate.sh` を忘れずに (`ralph check` が warning)
- Exit 0 = pass, non-zero = fail が唯一の契約
- Stdout は次 iter の agent への feedback、可読性最優先
- BASE 環境変数は driver が自動 export

**参考実装**: [`experiments/real-doc-refs/gate.sh`](https://github.com/dobachi/ralph-lab/blob/main/experiments/real-doc-refs/gate.sh)

### Layer B: delegation

`gate.delegate_to[]` に skill 呼び出しを列挙:

```yaml
gate:
  script: ../../experiments/real-doc-refs/gate.sh
  delegate_to:
    - name: fact-checker             # log 識別用
      cmd: claude                    # CLI
      args: [-p, --dangerously-skip-permissions]
      prompt: |
        Invoke the fact-checker skill on {file}.
        Output PASS or FAIL: <reason>.
      fail_pattern: '^FAIL'           # regex
      timeout_sec: 180
      stdin_prompt: true              # prompt を stdin から流す
      retries: 2                      # 非決定性回避 (P20)
      retry_aggregate: any_pass       # any_pass / all_pass / majority (P26)
  aggregate: all_pass                # 委譲群の集約
```

**retry_aggregate の選び方** (P24 実測):

| Skill 種類 | 分布 | 選択 |
|---|---|---|
| FAIL-happy (fact-checker、明示 rule) | 決定的 FAIL 寄り | `any_pass` (稀な PASS 尊重) |
| PASS-happy (doc-review、broad prompt) | 稀に深い FAIL | **`all_pass`** (稀な FAIL 尊重) |
| 偏り未確認 | 分布不明 | `majority` (中庸、cost 最大) |

詳細: [knowhow/prompt-patterns.md](knowhow/prompt-patterns.md) の "Retry の方向"。

### Layer C: post_evaluation

Ralph pass 後 or max_iter 到達時 (run_always=true) に 1 回だけ走る judge:

```yaml
post_evaluation:
  cmd: judge-openrouter               # scripts/judge-openrouter.py (symlink)
  args: [--model, openai/gpt-4o, --max-tokens, "400"]
  prompt: |
    An AI agent edited a document to satisfy a syntactic gate:
    ----- BEGIN DOCUMENT -----
    {file_content}
    ----- END DOCUMENT -----

    Detect Goodhart hacks:
    1. Fabricated content
    2. Deleted substance
    3. Workarounds
    4. Inverted substitution

    Output PASS or FAIL: <reason>.
  fail_pattern: '^FAIL'
  timeout_sec: 180
  stdin_prompt: true
  run_always: true                    # max_iter でも実行 (P19)
```

**異 provider 推奨** (Goodhart 相関エラー対策): agent が Anthropic なら judge は
OpenAI、と使い分ける。`judge-openrouter` wrapper は任意 provider を指定可能。

---

## 4. Cookbook: よくある spec pattern

### Pattern 1: 単純な文書チェック (最小構成)

```yaml
name: simple-doc-check
description: markdown の syntax check
input_document: path/to/doc.md
agent:
  cmd: claude
  args: [-p, --dangerously-skip-permissions]
prompt: |
  Fix any markdown syntax errors in $CURRENT.
  Previous gate output: $PREV_GATE_OUTPUT
gate:
  script: my-gate.sh
```

### Pattern 2: baseline 分離 (buggy → correct)

```yaml
name: fix-from-baseline
description: buggy 版を correct 版に近づける
input_document: path/to/buggy.md
baseline_document: path/to/correct.md   # ← P13 で追加
agent:
  cmd: opencode
  # ...
gate:
  script: my-gate.sh  # BASE=correct を前提に diff check
```

### Pattern 3: 委譲 + judge の 3 層

```yaml
# goals/examples/doc-verify-unified.yaml 参照
name: full-verify
gate:
  script: syntactic-gate.sh
  delegate_to:
    - name: fact-checker
      cmd: claude
      # ...
      retries: 2
      retry_aggregate: any_pass
    - name: doc-review
      cmd: claude
      # ...
      retries: 2
      retry_aggregate: all_pass  # PASS-happy skill には all_pass
post_evaluation:
  cmd: judge-openrouter
  # ...
  run_always: true
```

### Pattern 4: コード修正 (dir workspace, P9)

```yaml
name: fix-code
input_document: path/to/project/    # dir を指定
agent:
  cmd: aider
  args: [--yes-always, --no-git, --edit-format, udiff]
  model: openrouter/openai/gpt-4o-mini
prompt: |
  Fix the failing tests in $CURRENT.
  Read $CURRENT/tests/ for expected behavior.
gate:
  script: pytest-gate.sh              # cd $CURRENT && pytest
```

---

## 5. Log 分析

各 iter は JSONL 1 行として記録される (P17 で `stdout_head` 追加):

```bash
cat logs/my-runs.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    r = json.loads(line)
    if 'event' in r and r['event'] == 'post_evaluation':
        print(f'judge: {r[\"passed\"]}, {r[\"stdout_head\"][:80]}')
    else:
        print(f'iter {r[\"iteration\"]}: '
              f'gate={r[\"gate\"][\"passed\"]}, '
              f'overall={r[\"overall_gate_passed\"]}')
        for d in r.get('delegations', []):
            print(f'  {d[\"name\"]}: {d[\"passed\"]}, '
                  f'attempts={d.get(\"attempts\", 1)}, '
                  f'stdout={d[\"stdout_head\"][:60]}')
"
```

### 記録されるフィールド

| フィールド | 意味 |
|---|---|
| `iteration` | 0-indexed |
| `agent.exit_code / duration_ms / stdout_head / stderr_head` | agent の結果 |
| `gate.exit_code / passed / stdout_head` | Layer A の結果 |
| `delegations[].name / passed / attempts / stdout_head` | Layer B 個別 |
| `overall_gate_passed` | Layer A + B の総合 |
| `base_tampered / base_tamper_message` | Layer 0 検出結果 |
| `current_unchanged` | silent failure signal (P20) |
| `event: post_evaluation` (別行) | Layer C 結果 |

---

## 6. Environment variables

| Var | 用途 |
|---|---|
| `OPENROUTER_API_KEY` | aider / opencode / judge-openrouter |
| `ANTHROPIC_API_KEY` | claude CLI (SDK 経由の場合) |
| `BASE` | gate.sh に自動 export される (driver が設定) |

`.env` file を repo root に置き、`set -a && source .env && set +a` で読み込むのが
定石。`python-dotenv` は driver 起動時に load される。

---

## 7. Troubleshooting

**問題別 対処**:

| 症状 | 原因 | 対処 |
|---|---|---|
| `agent CLI not found in PATH` | cmd が未インストール | `which <cmd>` で確認、install |
| `OPENROUTER_API_KEY not set` warning | .env 未読込 | `set -a && source .env && set +a` |
| max_iterations で pass せず | prompt 甘い or Layer B が非決定的 | prompt patterns 適用 or retries 追加 |
| judge always PASS だが実は fabrication | Layer C prompt が甘い | Goodhart 4 種 enumerate、`{file_content}` 使用 |
| `current_unchanged=True` 連続 | agent が空回り | prompt の tool 指示、`stdin_prompt` の on/off 確認 |
| BASE.md が modified の警告 | agent の削除 over-reaction | Layer 0 が自動復元、prompt に「BASE 触るな」明示 |

より深い場合は [experiments/](experiments/) の P4-P26 実測ログを検索。

---

## 8. 関連

- [architecture.md](architecture.md) — 図で概念理解
- [getting-started.md](getting-started.md) — 最短 5 分の walkthrough
- [knowhow/](knowhow/) — 実装で得た再現性のあるノウハウ
- [experiments/](experiments/) — 予測 → 実測の記録
