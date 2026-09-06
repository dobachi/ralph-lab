# aider を Ralph loop で使うときのノウハウ

**対象**: aider CLI を ralph-lab の agent として組み込む場合。他の agent CLI
(claude / codex / opencode) にも部分的に共通する項目あり (§ ラベル参照)。

**動作確認バージョン**: aider 0.86.2 (2026-09-06)

---

## §A. `.aider.chat.history.md` 蓄積 (最重要、必須対策)

### 症状

`ralph run --models m1,m2,m3` で 3-model horse race を回すと、**3 モデルとも
5 iter で edit ゼロ**になった。単発 `--model m1` では 3 iter で clean fix
できていたのに、`--models` (subdir に分離される) にすると全 model が
"already fixed" と誤認識して no-op を返す。

### 直接の原因

aider は default で `.aider.chat.history.md` を cwd に作り、次回起動時に
それを読み込む (`--restore-chat-history`)。ralph-lab の workspace/cwd は
iteration 間で使い回されるので、iteration が進むと history が蓄積し、
aider が「既に修正した」と誤判断する。

**Ralph 原則**「毎回 fresh context」に真っ向から反する。

### 再現手順

```bash
# subdir を作り、workspace 相当のファイルを置く (BASE と current が同一)
mkdir -p /tmp/aider-history-repro
cp /some/broken.md /tmp/aider-history-repro/current.md
cd /tmp/aider-history-repro

# 1 回目: 正常に edit する
echo "Fix [S-99] → [S-06] on line 32" | aider --yes-always --no-git \
    --message-file /dev/stdin current.md --model openrouter/openai/gpt-4.1-mini

# .aider.chat.history.md が作られている
ls -la .aider.chat.history.md   # ~27kB

# 2 回目: 同じ指示を出しても history に引きずられて no-op になる (再現条件依存)
echo "Fix [S-99] → [S-06] on line 32" | aider --yes-always --no-git \
    --message-file /dev/stdin current.md --model openrouter/openai/gpt-4.1-mini
# → "Are you sure you need this SEARCH/REPLACE block?"
#    "The REPLACE lines are already in current.md!"
```

### 修正

spec.agent.args に **2 つの flag** を必ず加える:

```yaml
agent:
  cmd: aider
  args:
    - "--no-restore-chat-history"    # 前回の history を読み込まない
    - "--chat-history-file"
    - "/dev/null"                    # history を書き込まない
    - "--yes-always"
    - "--no-auto-commits"
    - "--no-git"
    - "--message-file"
    - "/dev/stdin"
    - "$CURRENT"
```

`--no-restore-chat-history` **単独では不十分**。history file 自体が作られる
と、外部プロセス (別 model の subprocess) が読み込む可能性があるので、
`/dev/null` に書き飛ばす。

### なぜ「単発 --model」では動いていたか

単発 --model は 3 iter で pass するので、history 蓄積が 27kB に達する前に
loop が終わる。iter が伸びると同じ問題が起きる。3-model horse race で顕在化
したのは iter 5 まで agent が繰り返し起動されたため。

### 一般化 (§H: agent CLI 共通)

**agent CLI が cwd に "state file" を作るタイプ**は Ralph 原則と相性が悪い。
Ralph loop で使うときは:

1. state file 出力先を `/dev/null` に向ける flag があれば使う
2. なければ ralph-lab 側で iteration 前に cwd を rm/mkdir で作り直す
   (ただし BASE/current は保持する必要あるので実装は要検討)

該当例:
- **aider**: `.aider.chat.history.md`, `.aider.input.history`,
  `.aider.model.metadata.json`
- **codex**: 要検証 (`~/.codex/` に history がある可能性)
- **claude**: `~/.claude/` に session 情報を保持するが cwd には作らない
  (claude 2.1.152 時点、要検証)

---

## §B. `--no-git` は必須

### 症状 & 原因

aider は default で cwd から親を辿って `.git` を探し、見つかると
「commit してよいか」プロンプトを出す。`--yes-always` があっても
`.git` に対して意図しない操作をする可能性。

### 修正

`--no-git` を必ず付ける。ralph-lab の workspace は git 管理外なので必須。

---

## §C. `--yes-always` と `--no-auto-commits` の役割分担

- `--yes-always`: 全確認プロンプト自動承認 (aider が「編集していい?」等を
  聞かない)
- `--no-auto-commits`: aider が自動 git commit しない (`--no-git` があれば
  実質重複だが安全のため両方指定)

---

## §D. `--message-file /dev/stdin` の platform 依存

Linux / macOS 前提。Windows では `/dev/stdin` が存在しないので別方法が必要
(未検証。tempfile 経由 or `--message "..."` 引数直渡し等)。

---

## §E. Anthropic model + aider + OpenRouter の SEARCH/REPLACE 生成失敗

### 症状 (2026-09-06 実測)

同一 spec (`doc-verify-loop-goal-aider.yaml`) で 3-model horse race:

| Model | Status | 5 iter total | Edit |
|---|---|---|---|
| openrouter/openai/gpt-4.1-mini | pass 2 iter | 10.3s | clean fix |
| openrouter/anthropic/claude-3.5-haiku | max_iterations | 19.2s | **edit ゼロ** |
| openrouter/anthropic/claude-3.7-sonnet | max_iterations | 17.1s | **edit ゼロ** |

API は叩いた (agent_duration_ms が 3-4s / iter で妥当)。しかし SEARCH/REPLACE
block が生成できず gate 通過できず。

### 疑い

以下のいずれか (要調査):

1. aider の diff format prompt に対する Anthropic model の response format が
   OpenAI と異なり、aider の parser が拾えていない
2. OpenRouter 経由の Anthropic API の response formatting に何か差がある
3. aider の SEARCH/REPLACE 生成は OpenAI model 系との相性で調整されており
   Anthropic model 系は fine-tuning されていない

### 暫定的な対処 (P10-C 2026-09-06 で **`--edit-format udiff` を検証済み** ✅)

**`--edit-format udiff` は Anthropic model で有効**と確定 (P10-C 実測):

- SEARCH/REPLACE (haiku-4.5): edit 0 件、5 iter 全失敗
- **udiff (haiku-4.5): pass 2 iter, 14 秒**

spec の args に追加:

```yaml
agent:
  args:
    - "--edit-format"
    - "udiff"        # ★ SEARCH/REPLACE の代わりに
    - "--yes-always"
    - ...
```

`goals/examples/doc-verify-loop-goal-aider-udiff.yaml` を参照。

**ただし別の落とし穴**: udiff で pass しても、**「逆向き捏造」型の Goodhart
が起きる**ことを実測 (P10-C の diff: 本文の [S-99] を残したまま、出典表の
S-06 を S-99 に書き換えて refs_integrity を通す)。詳細は
[../experiments/2026-09-06-p10-results.md](../experiments/2026-09-06-p10-results.md)
Finding 3。

**Anthropic model を aider で使うなら**:
- `--edit-format udiff` を default に
- prompt で「本文を直す、出典表を書き換えない」等の対称性拘束を明示
- あるいは opencode に切り替え (§F 追記参照)

### 実務上のガイド

- **aider を Ralph agent として使う場合、model は OpenAI 系推奨** (2026-09
  現在)
- Anthropic model を使いたいなら claude CLI 直接 (spec.agent.cmd: claude)
  の方が安定

---

## §F. subprocess の cwd = workspace.root

ralph-lab は agent CLI を `cwd=workspace.root` で起動する
(`agent_cli.py::run_agent` の実装)。理由:

- agent CLI が cwd の相対 path で file を扱う場合が多い
- BASE と current は workspace 内にあり cwd 相対で参照できる
- 他のプロジェクトの file を誤って触るリスクを下げる

**副作用**: agent CLI が cwd に state file を作る場合、workspace に貯まる
(§A の問題の元)。

---

## §G. stdin_prompt=true と PIPE 動作

ralph-lab の `agent_cli.py::run_agent` は:

```python
proc = await asyncio.create_subprocess_exec(
    *argv,
    stdin=asyncio.subprocess.PIPE if spec.stdin_prompt else None,
    stdout=..., stderr=...,
    cwd=str(workdir),
    env=env,
)
stdin_input = prompt.encode("utf-8") if spec.stdin_prompt else None
stdout_b, stderr_b = await asyncio.wait_for(
    proc.communicate(input=stdin_input),
    timeout=timeout_sec,
)
```

`spec.stdin_prompt: true` なら prompt を stdin から流す。aider は
`--message-file /dev/stdin` と組み合わせて機能する。**stderr に
"Warning: Input is not a terminal (fd=0)"** が出るが正常動作
(41 bytes、無視して良い)。

---

## §I. 命令の書き方 — 実測ベースの推奨

`spec.prompt` に何を書くと edit が通りやすいか (実測):

**通りやすい prompt** (openai/gpt-4.1-mini + aider):
- `Replace [S-99] with [S-06] on line 32 and 40.` (具体的指示)
- `Fix the failing detectors listed in the previous gate output.` (指示 +
  feedback 参照)

**通りにくい prompt**:
- `Improve the document.` (抽象的)
- `Make the gate pass.` (goal だけ、how がない)

Ralph 原則の「gate は決定的検証、agent は fresh context で作業」を活かすには
prompt で **具体的な状態変更を指示** する。gate 出力の feedback は
`$PREV_GATE_OUTPUT` で受け取れるので、これを prompt 内で明示的に参照する
と model が拾いやすい:

```yaml
prompt: |
  ...
  Previous gate output (findings to fix):
  $PREV_GATE_OUTPUT

  Emit SEARCH/REPLACE blocks that address ONLY the failing detectors listed
  above. Do not rewrite the file broadly.
```

---

## 参照

- ralph-lab 実装: `src/ralph_lab/core/agent_cli.py`, `core/loop.py`
- example: `goals/examples/doc-verify-loop-goal-aider.yaml`
- 実測ログ: `goals/examples/logs/ralph-runs.jsonl` (session ごとにクリア)
