# Agent CLI に求める挙動 (Ralph loop での契約)

**対象**: ralph-lab の spec.agent に指定する CLI が満たすべき条件。
新しい agent CLI を組み込むときのチェックリスト。

---

## §A. 必須条件

以下 4 点をすべて満たす CLI は Ralph loop に組み込める:

1. **subprocess から起動できる** (`subprocess.exec` / `create_subprocess_exec`)
2. **prompt を stdin or args で受け取れる** (interactive TUI 専用は不可)
3. **file 編集を自前で行う** (LLM の応答を parse → ファイルへ apply)
4. **fresh context モードがある** (前回の session を復元しない設定)

### 1 と 2: subprocess から prompt を渡せる

ralph-lab の `agent_cli.py::run_agent` は:

- `spec.agent.cmd` で subprocess.exec
- `stdin_prompt: true` なら stdin から prompt を流す
- `stdin_prompt: false` なら prompt を argv 末尾に足す (未検証)

**NG 例**: 対話 TUI 前提で `--message` 引数が無い CLI、REPL のみの CLI。

### 3: file 編集を自前で行う

Ralph loop は「agent CLI が file を編集した結果を gate が検証する」形。
agent が **stdout に応答テキストを返すだけ** で file を書かない場合、
gate は編集された file を検査できず失敗する。

**該当する自前編集モード**:
- aider: SEARCH/REPLACE block を LLM に生成させ、aider が apply
- opencode: 内蔵 file edit tool
- claude (Claude Code CLI): 内蔵 Edit tool
- codex: 内蔵 patch tool

**NG 例**: 単に LLM API を叩いて stdout に response を返すだけの CLI。

### 4: fresh context

Ralph 原則の核。前 iteration の context を持ち込まないこと。

**確認方法**: CLI の `--help` で以下のような flag があるか探す:
- `--no-restore-*` (aider: `--no-restore-chat-history`)
- `--fresh` / `--new-session`
- 環境変数で history file を `/dev/null` にできる

**該当 flag がない CLI** は Ralph loop に不向き (別途 workspace 側で
state file を毎 iter 消す実装が要る、未対応)。

---

## §B. 現行の対応状況

| Agent CLI | subprocess | prompt stdin | prompt args | file 編集 | fresh flag | 動作確認 |
|---|---|---|---|---|---|---|
| aider 0.86+ | ✅ | ✅ (`--message-file /dev/stdin`) | ✅ (`--message "..."`) | ✅ | ✅ (`--no-restore-chat-history` + `--chat-history-file /dev/null`) | ✅ (openai model 系のみ検証済) |
| claude 2.1+ | ✅ | ✅ (`-p` + stdin) | ✅ (`-p "..."`) | ✅ | ⚠️ (session 分離要検証) | ✅ (loop-goal 例で動作) |
| codex | ✅ | 要検証 | ✅ (`exec "..."`) | ✅ | 要検証 | 未検証 |
| opencode | ✅ | 要検証 | ✅ (`run "..."`) | ✅ | 要検証 | 未検証 |

---

## §C. spec.agent の書き方

### 基本形

```yaml
agent:
  cmd: <CLI コマンド名>
  args:                # 固定引数のリスト
    - "--flag1"
    - "--flag2"
    - "value2"
  stdin_prompt: true   # true: stdin から prompt、false: args 末尾
  model: <モデル名>    # None なら agent CLI の default 使用
  env:                 # 追加環境変数 (親プロセスの env を継承した上に足す)
    KEY: value
```

### $CURRENT / $BASE の argv 埋め込み

`spec.agent.args` に `$CURRENT` / `$BASE` / `$ITER` / `$MAX_ITER` を書くと
driver が iteration 前に置換する:

```yaml
args:
  - "--target-file"
  - "$CURRENT"      # 例: /tmp/ralph-lab-xxx/current.md に置換
```

**注意**: `$PREV_GATE_OUTPUT` は argv に埋め込まない (改行を含む長文で
argv 長制限や shell parsing に引っかかる)。`spec.prompt` 側で使う。

### model prefix と provider

model 名は CLI ごとに解釈が違う:

- **aider**: `openrouter/openai/gpt-4.1-mini` (provider prefix でルーティング)
- **claude**: `haiku-4-5` / `sonnet-4-5` 等 (Anthropic model 名)
- **codex**: OpenAI model 名 (`gpt-4.1` 等)

ralph-lab は model 名を CLI に丸ごと渡すだけ。中身は CLI に任せる (Level C
の gate 中立性と同じ思想: driver は詳細を知らない)。

---

## §D. 新しい agent CLI を組み込むチェックリスト

1. `--help` を読み、`§A` の 4 条件を満たすか確認
2. 単発 (ralph-lab 抜き) で `echo "prompt" | <cmd> ... target.md` を叩いて
   実 file が編集されるか確認
3. `.<cmd>*` みたいな state file が cwd に作られていないか確認 (ある場合は
   fresh flag or /dev/null リダイレクト)
4. spec.agent を書いて `ralph run` で単発実行 (1 iteration で通るまで prompt
   を調整)
5. 3-model horse race で複数 iteration の挙動確認 (aider の chat history
   問題のような蓄積系不具合が出ないか)
6. `docs/knowhow/agent-cli-<name>.md` (or この doc に追記) にノウハウ残す

---

## §E. 落とし穴

### 1. stdin が閉じるタイミング

`asyncio.subprocess` で `PIPE` を渡して `communicate(input=b"...")` すると
prompt を write して stdin を close する。CLI 側が「stdin から追加入力を
待つ」動作をすると deadlock or timeout する。

**対策**: CLI に「stdin を 1 回読んだら EOF で終わる」flag があれば付ける
(`--message-file /dev/stdin` は該当)。

### 2. cwd が親プロセスと違うと config が見つからない

一部 CLI は `~/.config/<name>/config.json` を読むが、`XDG_CONFIG_HOME` を
env で継承しないと fallback する場合がある。

**対策**: spec.agent.env は空 (`env: {}`) を default にして、必要なら
明示的に追加。

### 3. TTY 判定で挙動が変わる

多くの CLI は `isatty()` で分岐し、非 TTY では簡素な出力になる。
これは通常 Ralph loop に好都合 (progress bar なし)。ただし逆に
「非 TTY だと prompt を待たない」誤動作を起こす CLI もある。

**兆候**: agent が数百 ms で即終了、stdout に "Warning: Input is not a
terminal" 等が出る。

**対策**: `--yes-always` や `--non-interactive` を付けて明示的に非対話
モードにする。
