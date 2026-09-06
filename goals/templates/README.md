# goals/templates/

`ralph init` が読む spec テンプレ集。**${...} placeholder** を init 時に
対話 or フラグで置換して `goals/<name>.yaml` を生成する。

## Placeholder 一覧

| Placeholder | 意味 | Default (init 時) |
|---|---|---|
| `${NAME}` | spec の name | (対話で聞く) |
| `${DESCRIPTION}` | spec の description | "Verify a document with loop-goal gate." |
| `${INPUT_DOCUMENT}` | 対象文書の絶対パス | (対話で聞く) |
| `${MODEL}` | agent CLI の model | template ごとに違う (下記) |
| `${GATE_SCRIPT}` | gate.sh の絶対パス | loop-goal の install 済 gate.sh を自動探索 |
| `${MAX_ITERATIONS}` | outer loop 上限 | `5` |
| `${LOG_PATH}` | JSONL log path | `logs/ralph-runs.jsonl` |

## Template 一覧

Ralph loop で動作確認済の agent CLI ごとに template を分けている
(agent の args / stdin_prompt が違うため)。

| Template | Agent CLI | Model 例 | 備考 |
|---|---|---|---|
| **claude.yaml** | `claude` (Claude Code CLI) | (CLI default) | 最も敷居低い。Anthropic auth 済み前提 |
| **aider.yaml** | `aider` | `openrouter/openai/gpt-4.1-mini` | `.aider.chat.history.md` 抑止 flag を含む |
| **opencode.yaml** | `opencode` | `openrouter/openai/gpt-4.1-mini` | `stdin_prompt: true` 必須 (docs/knowhow/agent-cli-opencode.md 参照) |

## 使い方

```bash
# 対話 (agent CLI と name / input を聞く)
uv run ralph init

# 非対話 (flags で完結)
uv run ralph init --template aider --name my-goal --input ./doc.md

# 生成後の validation
uv run ralph check goals/my-goal.yaml
```

## Template の追加

新規 CLI (codex 等) を組み込むときは:

1. `docs/knowhow/agent-cli-<name>.md` で subprocess 挙動と flag を検証
2. この dir に `<name>.yaml` を追加
3. README のこの表に 1 行追加
