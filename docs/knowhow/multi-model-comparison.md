# --models で多モデル比較するノウハウ

**対象**: `ralph run <spec> --models m1,m2,m3` の設計と運用。

---

## §A. workspace 分離設計

### 実装 (cli.py::_run_all)

```python
if len(models) == 1:
    ws_root = workspace_root          # 単発なら subdir なし
else:
    safe_name = model.replace("/", "_").replace(":", "_")
    ws_root = workspace_root / f"{idx:02d}-{safe_name}"
```

- **単発**: `workspace_root/BASE.md`, `workspace_root/current.md`
- **複数**: `workspace_root/00-openrouter_openai_gpt-4.1-mini/BASE.md` ...

### 分離の理由

各 model の workspace を独立させるのは:

1. **workspace 内 state file 汚染防止** (aider の chat history 等)
2. **iteration の並列可能性を将来維持** (今は直列だが、workspace が独立して
   いれば並列化しても問題ない)
3. **model ごとに diff を独立比較** (BASE と current が各 model 独立)

### model 名の safe_name

`/` と `:` を `_` に置換 (path として使えないため):

- `openrouter/openai/gpt-4.1-mini` → `openrouter_openai_gpt-4.1-mini`

---

## §B. 直列実行 (並列にしない)

`_run_all` は `for` loop で直列。並列化しない理由:

1. **API rate limit 保護**: 同じ provider (OpenRouter 等) の rate limit を
   超えやすい
2. **gate.sh のローカル IO** が並列化の恩恵少 (通常数百 ms)
3. **workspace 混同事故防止** (cwd の混同や env の競合を回避)

将来的に並列化するなら `asyncio.gather` + workspace 独立 + API rate
throttle が必要。

---

## §C. 実測データフォーマット

`--models` 実行時の JSON 出力:

```json
{
  "spec_name": "doc-verify-loop-goal-aider",
  "models_count": 3,
  "runs": [
    {
      "spec_name": "doc-verify-loop-goal-aider",
      "model": "openrouter/openai/gpt-4.1-mini",
      "status": "pass",
      "iterations": 2,
      "workspace_root": "/tmp/.../00-openrouter_openai_gpt-4.1-mini",
      "total_duration_ms": 10458,
      "iteration_summaries": [...]
    },
    ...
  ]
}
```

`jq` で集計しやすい:

```bash
# 各 model の pass 状況
jq -r '.runs[] | "\(.model)\t\(.status)\t\(.iterations)\t\(.total_duration_ms)ms"' output.json

# 総 token / duration 集計は JSONL log (log_path) の方が詳細
```

---

## §D. 実測 (2026-09-06 P6-4 session)

同一 goal (`doc-verify-loop-goal-aider.yaml`, loop-goal の broken_ref.md を
修正) を 3 model で比較:

| Model | Status | Iter | Total | Notes |
|---|---|---|---|---|
| openrouter/openai/gpt-4.1-mini | pass | 2 | 10.5s | clean fix |
| openrouter/anthropic/claude-3.5-haiku | max_iterations | 5 | 19.7s | edit ゼロ (aider SEARCH/REPLACE 失敗) |
| openrouter/anthropic/claude-3.7-sonnet | max_iterations | 5 | 17.1s | 同上 |

**発見** (詳細は [aider-integration.md §E](aider-integration.md#e-anthropic-model--aider--openrouter-の-searchreplace-生成失敗)):

aider の SEARCH/REPLACE format と Anthropic model 経由 OpenRouter の相性が
悪い。同じ agent CLI + 同じ prompt でも model 差が明確に出る。

**このデータの意味**: 「どの agent CLI と どの model の組み合わせが Ralph
loop で機能するか」の実測台として `--models` は有効。逆に「単一 model で
どの agent CLI が最適か」を測るには agent CLI 側も切り替えた比較が要る
(P6-3 の multi-agent CLI の続き、まだ未実施)。

---

## §E. コスト目安

3-model horse race 1 回のコスト (2026-09-06 実測):

- broken_ref.md サイズ ~2kB
- 総 iteration: 2 + 5 + 5 = 12 iter
- 各 iter で aider が prompt 送信 (数 kB) + response (数百 tokens)
- 総費用: ~$0.03-0.05 (OpenRouter 経由)

**注意**: 5 iter で pass しない model は無駄コストを消費するので、
max_iterations を先に決める。

---

## §F. 落とし穴 — sequential 実行での state 汚染

**Ralph 原則**「各 iteration で fresh context」は **各 model の workspace
が独立していれば守られる**が、以下は例外:

- `spec.log_path` (JSONL) は共通の 1 ファイル → 各 model の record が
  混じって書かれる (model 名で区別可、問題なし)
- `.env` の env vars は親プロセス全体で共通 → OpenRouter の API key 等は
  全 model で同じ (意図通り)
- **cwd 独立の workspace subdir** → aider 等の state file は分離済 (問題なし)

一方、**agent CLI が親環境変数を読み書きするタイプ** (`HOME` 配下の
config file を書き換える) は分離できない。この場合は subprocess の env
を明示的に絞る (`env: {HOME: /tmp/isolated}`) 必要がある (未実装)。
