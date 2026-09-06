# Gate 委譲パターン — Ralph が苦手な領域を他スキルに任せる

**対象**: Ralph loop の弱点 ([gate-design-patterns.md §Check 4-5](gate-design-patterns.md))
を、既存の別スキル (fact-checker / doc-review 等) に委譲して補う設計。

**中心的な考え方**: **Ralph は syntactic な gate を回すのが得意**。**semantic
判定 (事実の正しさ、論理の妥当性、意味の一貫性) は既存の専用スキルに
subprocess で委譲する**。ralph-lab は「多層防御の framework」として、
Layer B/C の判定を他スキル呼び出しで実装する。

---

## 3 方式

### 方式 A: gate 内 subprocess で他スキルを呼ぶ

**特徴**: ralph-lab 変更ゼロ。gate.sh の中で `claude -p` 等を呼び、他スキルを
subprocess として起動する。

```bash
#!/bin/bash
# gate.sh (方式 A の例)
CURRENT=$1
FAIL=0

# Layer A: syntactic (自作)
python3 gate_syntactic.py "$CURRENT" || FAIL=1

# Layer B: fact-checker を委譲呼び出し
fact_output=$(claude -p --dangerously-skip-permissions \
    "Run /fact-checker on $CURRENT. Output only PASS or FAIL with brief reason." 2>&1)
if grep -qE '^FAIL' <<< "$fact_output"; then
    echo "❌ fact-checker: $fact_output" >&2
    FAIL=1
fi

exit $FAIL
```

**利点**:
- **実装コスト最小** (ralph-lab core は変更なし)
- **既存の gate 契約に載せられる** (bash script + exit code)
- **fresh subprocess** で他スキルを呼ぶので Ralph 原則忠実

**欠点**:
- 委譲の記述が gate.sh に散らかる
- 複数スキル併用の集約ロジックは自作
- cost が iteration ごとに乗る (LLM call ×委譲数)

**推奨用途**: PoC、一回限りの検証、gate.sh の中で丁寧に書きたいケース

---

### 方式 B: spec.yaml の `delegate_to` field (宣言的)

**特徴**: spec で委譲を宣言、ralph-lab の driver が実行と集約を担う。

```yaml
gate:
  script: syntactic-gate.sh
  delegate_to:
    - name: fact-checker
      cmd: claude
      args: [-p, --dangerously-skip-permissions]
      prompt: "Run /fact-checker on {file}. Output PASS or FAIL with reason."
      fail_pattern: '^FAIL'      # regex on stdout
      timeout_sec: 120
    - name: doc-review
      cmd: claude
      args: [-p, --dangerously-skip-permissions]
      prompt: "Run /doc-review on {file}, critical only. Output PASS or FAIL."
      fail_pattern: '^FAIL'
      timeout_sec: 180
  aggregate: all_pass  # all_pass | any_pass | specific_fields
```

driver の動作:
1. `syntactic-gate.sh` を実行、fail なら委譲せず終了
2. syntactic pass なら、`delegate_to` の各要素を subprocess で実行
3. `aggregate` に従って最終判定

**利点**:
- 委譲構成が **1 か所で読める** (spec.yaml)
- 集約ロジックは driver が担う (再実装しなくていい)
- **JSONL log に各委譲の cost / duration が記録される**
- 複数 spec で同じ委譲構成を再利用しやすい

**欠点**:
- ralph-lab core に実装が必要 (~200 行)
- 複雑な集約 (「fact-checker fail でも doc-review pass なら pass」等) は表現力の限界

**推奨用途**: 実運用、複数スキル併用、複数 spec で同じ委譲を使い回す

---

### 方式 C: LLM-as-judge (post_evaluation、Ralph loop の外側)

**特徴**: Ralph loop が pass した output を、**別 model で後評価**する。

```yaml
post_evaluation:
  judge:
    cmd: claude
    args: [-p, --dangerously-skip-permissions]
    model: openrouter/openai/gpt-4o    # agent と異 provider 推奨
    prompt: |
      This document was edited by an AI agent to satisfy a syntactic gate.
      Read it and detect Goodhart-type hacks:
      - fabricated content (dummy sources, empty definitions)
      - deleted substance (missing evidence)
      - workarounds that satisfy syntax but violate intent

      Output JSON:
      {
        "verdict": "PASS" | "FAIL",
        "hacks_found": ["..."],
        "reason": "..."
      }
    fail_on: verdict_is_FAIL
    timeout_sec: 300
```

driver の動作:
1. `run_ralph_loop` が status=pass で終わる
2. `post_evaluation` が指定されていれば judge を呼ぶ
3. judge が FAIL なら overall status を `judge_failed` にする

**利点**:
- **Layer C の semantic 判定**を framework 側で構造化
- Ralph loop の内側は速く syntactic のみ、judge は 1 回だけ (cost 効率)
- **異 provider の judge model** で相関エラー回避

**欠点**:
- judge model も Goodhart 対象になり得る (自分ができる hack を「妥当」と判定する)
- judge の判定基準を明確に prompt に書く必要
- 追加 cost ($0.02-0.10 / run)

**推奨用途**: 実運用の最終ゲート、gate の穴が心配なタスク

---

## 用途別の推奨構成

### 文章 (daily-curation の記事)

```
Ralph loop iter (agent が編集):
  ├── syntactic gate.sh
  │    ├── Check 1: refs 整合性
  │    ├── Check 2: 単調性
  │    └── Check 3: 内容 non-empty
  │
  └── (方式 B) delegate_to:
       ├── fact-checker    → 引用の実在性
       └── verify-content  → 出典の妥当性

Ralph loop pass 後:
  └── (方式 C) post_evaluation:
       ├── doc-review      → 論理妥当性
       └── LLM-as-judge    → Goodhart 検出
```

**期待できる自動化**:
- 書式・整合性・削除禁止: 完全自動 (Layer A)
- 引用の実在性: 委譲で自動化
- 論理妥当性: judge + 人間 review
- トーン・面白さ: humanize-prose or 人間

### パワーポイント (Markdown → .pptx)

```
Ralph loop iter (agent が spec.md を編集):
  ├── syntactic gate.sh
  │    ├── pptx-build で .pptx 生成成功
  │    ├── audit_pptx.py で layout 準拠
  │    └── slide 数の下限 (単調性)
  │
  └── (方式 B) delegate_to:
       └── doc-review → spec.md の論理妥当性

Ralph loop pass 後:
  └── (方式 C) post_evaluation:
       ├── pptx-design → デザイン妥当性のアドバイス
       └── LLM-as-judge → 発表として通用するか
```

---

## 委譲する既存スキル一覧

Claude Code の marketplace or 個人 skills にある活用候補:

### 内容判定系

| スキル | 用途 | Layer |
|---|---|---|
| **fact-checker** | 引用の実在性 (Puppeteer で URL fetch) | B |
| **verify-content** | fact-check + reference verification | B |
| **evidence-check** | 参考文献の妥当性 | B |
| **grounded-research** | verbatim 引用 + Source Ledger | 執筆 phase (別途) |

### 文章品質系

| スキル | 用途 | Layer |
|---|---|---|
| **doc-review** | 論理・議論の批判的 review | B/C |
| **doc-refactor** | 意味を変えず構造整理 | 別 phase |
| **essence-distiller** | 冗長性の削減 | ⚠️ 削除型 Goodhart と衝突する可能性 |
| **ai-tell-reducer** | AI っぽさ除去 | C |
| **humanize-prose** | 人間らしい prose | C |

### 視覚系

| スキル | 用途 | Layer |
|---|---|---|
| **pptx-build** | .pptx 生成 (audit_pptx.py 同梱) | gate 内 subprocess |
| **pptx-design** | デザインアドバイス | C |
| **document-figures** | 図表生成 | 別 phase |

### 別 AI 委譲系 (LLM-as-judge の基盤)

| スキル | 用途 |
|---|---|
| **agent-delegate:claude-code-delegate** | 別 Claude インスタンスに `claude -p` で投げる |
| **agent-delegate:codex-delegate** | Codex CLI (`codex exec`) に投げる |
| **agent-delegate:agy-delegate** | Antigravity (`agy -p`) に投げる |

異 provider を judge に使いたいとき、`claude-code-delegate` は同 provider に
なる。**judge 用途では `codex-delegate` (OpenAI 系) or `agy-delegate` を使う**
のが望ましい。

---

## Cost / 時間の実測目安

方式ごとの追加 cost (Ralph 1 iter あたり):

| 方式 | 追加 cost | 追加時間 | 用途 |
|---|---|---|---|
| A (subprocess) | $0.02-0.15 | 数十秒〜数分 | 各 iter で毎回、cost 累積 |
| B (delegate_to) | 同上 | 同上 | 集約は driver で効率化 |
| C (post_evaluation) | $0.02-0.10 | 数十秒 | Ralph pass 後 1 回だけ、cost 効率良 |

**推奨組み合わせ**:
- **軽い運用**: 方式 A のみ、必要に応じて呼ぶ
- **本番運用**: 方式 B (毎 iter で軽い判定) + 方式 C (最終判定)
- **cost 最優先**: 方式 C のみ、syntactic gate は自作で速く

---

## Predict-first を委譲設計にも

**「この委譲でどの Goodhart を塞ぐか」を実装前に予測する**:

- fact-checker 委譲 → 捏造型 (P4 / P12 の Dummy Source / 空定義) を塞げるか?
  - Predict: 塞げるはず。fact-checker が URL fetch して「Dummy Source は
    存在しない」を検出できる
  - 実測が必要
- doc-review 委譲 → 論理妥当性 (Check 5 領域) を塞げるか?
  - Predict: critical issue を検出できる可能性、model と rubric 次第
  - 実測が必要

これらは BACKLOG 化して predict-first の実験対象にする。

---

## 落とし穴と対策

### 落とし穴 1: judge model が Goodhart する

**Judge も LLM = Goodhart 対象**。特に:
- Agent と同じ model を judge に使う → 相関エラー
- Judge の prompt が緩い → 「妥当そう」で通す

**対策**:
- **異 provider を使う** (agent=Anthropic なら judge=OpenAI 系)
- **rubric を厳格に**書く (「Goodhart-type hacks を列挙せよ、無ければ empty list」)
- **binary (PASS/FAIL) で始める**、拡張は後

### 落とし穴 2: 委譲 cost が Ralph iter を圧迫

Ralph が iter 5 回すと、方式 B なら **5 × 委譲 cost** かかる。

**対策**:
- 委譲は syntactic gate **pass 後** にのみ実行 (fail-fast)
- 毎 iter でなく **N iter に 1 回** で十分な場合もある (spec で調整)
- 方式 C は Ralph pass 後 1 回だけなので効率良い

### 落とし穴 3: 委譲がタイムアウトする

fact-checker が URL fetch で時間かかる、doc-review が全文読むと遅い。

**対策**:
- `timeout_sec` を委譲ごとに設定
- タイムアウト時の挙動を明示 (fail か skip か)
- 重い委譲は post_evaluation に回す

### 落とし穴 4: 委譲の依存が壊れる

fact-checker は Node.js + Puppeteer が要る。ローカルに未設定なら fail。

**対策**:
- 委譲 gate の README に依存を明記
- `ralph check` で委譲設定の validation
- 一部委譲を optional にする (fail_soft オプション)

---

## Ralph-lab の実装状況

| 方式 | 実装 | 詳細 |
|---|---|---|
| A (subprocess) | ✅ **既に可能** | gate.sh に書けば動く。参考: `experiments/delegating-gate/` |
| B (delegate_to) | ✅ P14 で実装 | spec.yaml に `gate.delegate_to`、driver が実行・集約 |
| C (post_evaluation) | ✅ P14 で実装 | spec.yaml に `post_evaluation`、Ralph pass 後に judge |

---

## 参照

- [gate-design-patterns.md](gate-design-patterns.md) — Layer A/B/C の 3 層構造、Check 5 の LLM-as-judge 節
- [gate-neutrality.md](gate-neutrality.md) — gate 中立性 (Level C) の設計思想
- [../experiments/](../experiments/) — Ralph loop の 7 度観察 (Goodhart の実測)
- [agent-cli-contract.md](agent-cli-contract.md) — 委譲する subprocess の契約
