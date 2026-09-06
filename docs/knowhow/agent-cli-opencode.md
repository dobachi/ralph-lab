# opencode を Ralph loop で使うときのノウハウ

**対象**: opencode CLI (SST 製、npm 経由) を ralph-lab の agent として組み
込む場合。aider との比較は [multi-model-comparison.md](multi-model-comparison.md)
および [../experiments/2026-09-06-p7-aider-vs-opencode.md](../experiments/2026-09-06-p7-aider-vs-opencode.md)
参照。

**動作確認バージョン**: opencode 1.18.29 (2026-09-06)

---

## §A. `-f` (file attach) と長い prompt の positional 衝突 (最重要)

### 症状

`opencode run [message..]` の message は positional array、`-f, --file` も
array。**message を positional で渡し、その後に -f を置くと、prompt を追加
file path と解釈してしまう** (2026-09-06 実測):

```
Error: File not found: Target file: /tmp/.../current.md
Baseline (DO NOT modify): /tmp/.../BASE.md
...
```

### 直接の原因

opencode の argparse は positional message と -f の array 型 option の
境界を絶対値では判定していない。長い改行入り prompt を渡すと -f の
続きとして解釈される。

### 修正

**message を stdin から渡す** — opencode は stdin に投入された文字列を
message として扱う (実測で確認)。

**spec.agent の書き方**:

```yaml
agent:
  cmd: opencode
  args:
    - "run"
    - "--auto"           # permission 自動承認 (Ralph loop 必須)
    - "-f"
    - "$CURRENT"         # driver が render 時に置換
  stdin_prompt: true     # message は stdin 経由 (positional 衝突回避)
  model: openrouter/openai/gpt-4.1-mini
```

`stdin_prompt: true` で ralph-lab の driver が prompt を stdin に流す。
opencode は positional message として認識、`-f` は別 option として file
attach。

---

## §B. `--auto` は必須

`--auto`: "auto-approve permissions that are not explicitly denied
(dangerous!)"

Ralph loop で人が介入しないので必須。非対話モードでは permission
プロンプトが出ないが、`--auto` を付けないと明示的に必要な permission
だけ block される可能性 (実測未確認、defensive に付ける)。

---

## §C. OpenRouter 設定は環境変数だけで済む

**設定ファイル不要**。`OPENROUTER_API_KEY` env var を親プロセスに設定
すれば opencode が自動認識する (2026-09-06 実測)。

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
opencode run "..." -m openrouter/openai/gpt-4.1-mini
```

`~/.local/share/opencode/auth.json` に credentials を保存する仕組みもあり、
`opencode providers login` で対話登録できるが、Ralph loop の非対話用途
では env var の方が簡潔。

---

## §D. Model prefix は aider と互換 (`openrouter/<provider>/<model>`)

opencode の `-m` / `--model` は `provider/model` 形式:

- `openrouter/openai/gpt-4.1-mini`
- `openrouter/anthropic/claude-3.7-sonnet`
- 他: `openai/gpt-4.1-mini` (OPENAI_API_KEY 経由の OpenAI 直)、
  `anthropic/claude-3.7-sonnet` (ANTHROPIC_API_KEY 経由の Anthropic 直)

aider と同じ命名なので、両 CLI で model を切り替えるときに mental cost 少。

---

## §E. Chat history — 未検証 (aider との違いの可能性)

aider は `.aider.chat.history.md` を cwd に作り、次回起動時に読み込む
(Ralph 原則違反、[aider-integration.md §A](aider-integration.md#a-aiderchathistorymd-蓄積-最重要-必須対策) 参照)。

**opencode は同種の cwd state file を作らないように見える** (2026-09-06
実測、`ls -la /tmp/ralph-p7-opencode/` に `.opencode*` は無かった)。ただし
これは 3 iter × short session の観察で、長期実験は未実施。

**BACKLOG**: opencode chat history 相当が cwd or `$HOME` 配下に貯まるか
長期実験する。

もし貯まる場合、以下 flag を検証:
- `-c, --continue` — 前 session を継続する (Ralph 原則違反、要無効化)
- `--fork` — session を fork する (要挙動確認)

現状の template `goals/templates/opencode.yaml` はこれらの flag なしで動く
(default が fresh session の可能性が高い)。

---

## §F. 出力フォーマット

opencode の `run` サブコマンドは default で装飾された stdout を吐く
(box-drawing 文字、tool 呼び出しの diff format 等)。

```
[0m
> build · openai/gpt-4.1-mini
[0m
[0m← [0mWrite test.md
Wrote file successfully.
```

Ralph loop 内では `stdout_size` を JSONL log に記録するだけなので影響なし。
`--format json` オプションで raw JSON events も取れる (未使用、将来的な
metric 抽出に使えるかもしれない)。

---

## §G. subprocess 契約チェックリスト (agent-cli-contract.md §D と対応)

| 項目 | opencode |
|---|---|
| subprocess から起動できる | ✅ |
| prompt を stdin で受け取れる | ✅ (stdin_prompt: true 必須) |
| prompt を args で受け取れる | ⚠️ 短い prompt なら可、長い prompt は `-f` と衝突 (§A) |
| file 編集を自前で行う | ✅ (内蔵 file edit tool) |
| fresh context モード | ⚠️ default が fresh session の可能性、長期実験未実施 (§E) |

---

## §H. Anthropic model + opencode の SEARCH/REPLACE 生成問題は?

**aider は Anthropic model で SEARCH/REPLACE format 失敗が実測されている**
(aider-integration.md §E)。**opencode は built-in file edit tool を使うので
LLM が特定 format を生成する必要がなく、Anthropic model でも動く可能性が
高い**。ただし未検証。

**BACKLOG**: Anthropic model + opencode + OpenRouter で
`goals/examples/doc-verify-loop-goal-opencode.yaml` の model を
`openrouter/anthropic/claude-3.5-haiku` に変えて実行、動作するか確認。

---

## §I. 実測 (2026-09-06 P7 session)

同一 goal (loop-goal broken_ref.md 修正)、同一 model (openai/gpt-4.1-mini
via OpenRouter):

| CLI | Status | Iter | Total | Fix の質 |
|---|---|---|---|---|
| aider | pass | 1 | 5.5s | ハーフ fix (S-99 空エントリを表に追加) |
| **opencode** | pass | 3 | 29.4s | **clean fix (Line 32, 40 両方置換)** |

opencode は 3 iter 要したが、fix の質は aider より正確。ただし n=1 で
model の非決定性含む。

初回実行では opencode + gpt-4.1-mini でも「S-99 を捏造して pass」
(v1 P4 の再現) が起きた。**agent CLI を変えても gpt-4.1-mini の
Goodhart 型行動は残る** — model 側の behavior で、ralph-lab の bug では
ない。

詳細は [../experiments/2026-09-06-p7-aider-vs-opencode.md](../experiments/2026-09-06-p7-aider-vs-opencode.md)。

---

## 参照

- opencode 公式: https://opencode.ai/
- opencode GitHub: https://github.com/sst/opencode
- ralph-lab template: `goals/templates/opencode.yaml`
- 実測 experiment: `docs/experiments/2026-09-06-p7-aider-vs-opencode.md`
