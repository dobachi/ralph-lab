# Ralph-lab 結論 (2026-09-07 時点)

**対象読者**: このプロジェクトを継承する未来の自分、または再現・拡張したい第三者。

**scope**: Ralph loop パターンを subprocess ベースで実装した ralph-lab の、
2026-08-15 (v1 agent-loop-lab から出発) 〜 2026-09-07 (v2 P26 完了) の総括。

---

## 1. 現状で実現できていること

### 1.1 コア機能

Ralph loop の subprocess-based driver として、以下が動く:

**「任意の agent CLI × 任意の gate script」で Ralph loop を回せる**:
- Agent CLI: `claude`, `aider`, `opencode` の 3 種を実測、他も spec.yaml で追加可能
- Gate script: bash / python / 任意言語で書ける、exit 0/1 が契約の全て
- 実測 domain: 文書検証 (脚注参照書式) + コード修正 (pytest)、いずれも 5+ iter で動作

**モデル切替**:
- `--model` フラグで実行時上書き
- `--models m1,m2,m3` で複数 model を同一 goal で比較 (直列)
- OpenRouter 経由で任意 provider (Anthropic / OpenAI / xAI / ...)

**Observability**:
- 各 iteration が JSONL 1 行として記録される
- P17 で `stdout_head` / `stderr_head` (先頭 200 char) を追加 → 判定理由が
  post-hoc に log から追える
- silent failure 検出 (`current_unchanged`) で agent が空回りしているか可視化

### 1.2 4 層防御 (Layer 0 / A / B / C)

Ralph loop の Goodhart 対策として **4 層防御**を設計・実装:

| Layer | 目的 | 実装 |
|---|---|---|
| **0. Framework integrity** | BASE の tamper 検出 | `Workspace.verify_and_restore_base()` (sha256 verify + tarfile snapshot restore) |
| **A. Syntactic gate** | 対応関係 / 単調性 / 内容 non-empty | `experiments/real-doc-refs/gate.sh` の 3 check (P11/P12/P13-1) |
| **B. Delegation** | 特定 skill による狭い semantic 判定 | `gate.delegate_to[]` (P14 方式 B、fact-checker / doc-review 等の subprocess 委譲) |
| **C. LLM-as-judge** | 総合的な Goodhart 検出 | `post_evaluation` (P14 方式 C、`run_always: true` で max_iter でも判定) |

Layer 別に**「独立した判定基準」**を持たせ、多層で重ねる設計。1 層で全部
塞ぐのは不可能、多層で 95% を目指す。

### 1.3 非決定性への対策 (P17-P26)

Layer B/C の LLM subprocess は本質的に非決定的。以下を framework 側で扱える:

- `retries: N` (P20): 追加試行回数
- `retry_aggregate: str` (P26): 集約 mode
  - `any_pass`: FAIL-happy skill 向け (稀な PASS を尊重)
  - `all_pass`: PASS-happy skill 向け (稀な FAIL を尊重、**P24 実測で重要と判明**)
  - `majority`: 中庸、cost 最大
- `post_evaluation.run_always` (P19): max_iter でも judge が判定 → `judge_passed`
  (rescue) or `max_iterations` (judge 確認) の 2 分岐

### 1.4 Prompt engineering 4 パターン (P23)

`docs/knowhow/prompt-patterns.md` で 4 種の prompt の書き分けを体系化:

1. **Delegation prompt**: 判定基準を狭く、具体的に (enumeration + 反例 + 条件付き適用回避)
2. **Agent prompt**: 削除禁止 + 捏造禁止 + clean fix hint + 「わからなければ stop 許可」
3. **Gate feedback**: 「何が失敗か」ではなく「どう直すか」を明示
4. **Post_evaluation**: Goodhart 4 種を enumerate + 具体例

`goals/examples/doc-verify-unified.yaml` で全パターンを組み合わせた
reference implementation を提供。

### 1.5 Workspace 拡張 (P9 / P13 finding 対応)

- **dir 対応** (P9): input_document が file でも dir でも OK。code 領域で
  tests/, src/ 等の周辺 file を持ち込める。tarfile snapshot で hash verify も dir 対応
- **baseline_document 分離** (P13 finding): BASE (correct) と current (buggy) を
  別 file/dir から source 可能。「buggy から correct に近づける」workflow を明示

### 1.6 実測で確立した知見

Goodhart 4 種の分類 (実測ベース):
1. **捏造** (fabrication): 6 度観察 (P4/P7/P12/P15/P16/P18)、最頻
2. **削除** (deletion): 2 度 (P7/P11)、agent が壊れた要素を消す
3. **迂回** (evasion): 1 度 (P9、code fix で `return 5` hack)
4. **逆向き置換** (inverted substitution): 1 度 (P10-C、定義側書き換え)

Goodhart 対策の実測エビデンス:
- **単調性 check** で削除型を確実に塞ぐ (P12 実測)
- **内容 non-empty check** で空捏造型を塞ぐ (P13-1 実測)
- **狭い prompt** (P18) で URL なし descriptive dummy を塞ぐ
- **LLM-as-judge** で content-shaped dummy を捕える (P15 Anthropic / P16 OpenAI)
- **異 provider judge は必須ではない**: Anthropic ↔ Anthropic でも実測で検出
  (相関エラー懸念は理論的、実測 n=1 では発現せず)

### 1.7 Cost 実測

各実験の cost (n≈1、opencode + haiku-4.5 + 委譲 + judge):
- Layer A のみ: ~$0.02-0.05 / run
- Layer A+B: ~$0.20-0.30 / run
- Layer A+B+C: ~$0.30-0.60 / run
- Full unified spec (推定): ~$0.30-0.60 / run

Judge cost は Anthropic (claude) と OpenAI (gpt-4o) でほぼ同等 ($0.04-0.05)。

---

## 2. 残った課題

### 2.1 Framework 未実装 (優先度中)

| 課題 | 状態 | 理由 |
|---|---|---|
| **Windows 対応** | 未着手 | `/dev/stdin` 依存、`--message-file` 系の平台抽象化。test 環境なしで開発困難 |
| **cost tracking** | 未着手 | OpenRouter `/generation` endpoint や agent CLI の cost 出力を parse。実装工数 vs 現時点の必要性で優先度低 |
| **`--parallel` 実装** | 未着手 | multi-model の並列実行。API rate throttle が難易度、直列で当面足りている |
| **Pydantic 出力型** | 未着手 (検討) | v1 agent-loop-lab で採用、多くの agent CLI は自由 stdout で拘束できず、v2 で復活は限定的 |

### 2.2 未検証の仮説 (優先度中)

| 課題 | 理由 |
|---|---|
| **Layer B 非決定性の 50/50 fixture** | P22/P24 で **決定的 FAIL** (fact-checker) と **PASS-happy** (doc-review) を実測、真の 50/50 fixture は未見。retries の理論的挙動 (any_pass/all_pass/majority) は unit test で確認済だが、実 LLM subprocess での効果は 50/50 分布下では未実測 |
| **P25: agent prompt Pattern 2 の実測** | P23 で理論を書き、Pattern 2 を unified spec に反映済だが、「これで削除 over-reaction が改善するか」は未実測 (haiku-4.5 の adaptive さの限界も見えているので、model 上位化 or model 別実測が要る) |
| **agent CLI 4 種の網羅比較** | claude / codex / opencode / aider の比較。codex を local に持たず、実測できず |
| **上位 model (sonnet-4.5) での adaptive さ** | P18/P22 で haiku-4.5 は feedback 追随限界、model 上位化で改善するかは仮説段階 |
| **gate 複合化** | loop-goal + custom grep で複数 detector を AND、実測なし |

### 2.3 実運用の未検証 (優先度低〜中)

| 課題 | 理由 |
|---|---|
| **daily-curation-reports 実文書での実運用** | 実運用 workflow (システム連携、schedule実行) 未検証 |
| **opencode chat history の長期実験** | 現在 iter ごとに fresh subprocess を仮定、長期運用で chat history が累積する pathology を実測せず |
| **cargo test / eslint / grep-based gate** | pytest は P9 で実測、他言語 gate の example は未整備 |

### 2.4 外部依存 (優先度検討)

| 課題 | 理由 |
|---|---|
| **loop-goal 開発者との対称性 detector 相談** | Ralph-lab から loop-goal (別 skill) への feedback、外部プロジェクト |
| **pypi 公開** | 現状 git clone + uv sync 前提、他人が使うなら公開検討 |
| **claude-skills-marketplace の skill 化** | `/ralph` skill を作って自然文で呼べるようにする、UX 大幅改善だが実装工数大 |

---

## 3. なぜ課題が残っているか

### 3.1 実測に依存する仮説は「多数の run」が必要

Ralph loop は本質的に stochastic (LLM 非決定性 + gate との相互作用)。
1 実験 = 1 run では有意な結論が出ない場合が多く、**n=5-10 の分布測定**が
本来必要。しかし cost ($0.30/run × 10 = $3) と時間の両面で、**「必要性が
明確な仮説」だけ n を増やす** 運用にしている。

**残っている「未実測仮説」の多く**は「重要だが、単発 run で見える範囲を
超える」もの。今後実施する場合、**「予測を書いてから、n=5 で分布を測る」**
を守る (loop-goal HANDOVER 精神)。

### 3.2 Framework の追加拡張は「実測なしの過剰設計」を避けたい

Windows 対応、`--parallel`、cost tracking などは、**今の実測 domain で
必要になっていない**。ラッパー実装として複雑化させると、Ralph 原則
(subprocess ベース、gate 中立、単純) から離れるリスクがある。

**判断基準**: 実測実験で 3 回以上「不足を実感した」機能を実装する。
Windows は 0 回、`--parallel` は 0 回、cost tracking は 2 回程度 (実装
検討中)。

### 3.3 外部依存の管理コスト

- codex CLI は local に無く、実測できない
- pypi 公開・skill 化は「他人が使う」ことを想定した packaging で、
  現時点で他人 user なしのため優先度低
- loop-goal との連携は外部プロジェクトへの feedback、コミュニケーション
  コスト大

### 3.4 発見された「予測外」の観察が優先度を書き換えた

- P13-2 で「framework tamper」と誤読 → P13-3 の実装 (Layer 0) は「防御は
  したが実測で起動事例なし」の状態
- P22 で agent の削除 over-reaction を新観察 → P25 (prompt Pattern 2 実測)
  が新規発生
- P24 で「retries の方向問題」を発見 → P26 (retry_aggregate) が新規実装

**次に何をやるかは、直前の実測が書き換える**。長期 roadmap は当てにならない。
BACKLOG は「積み場」であり、優先順は都度判断。

---

## 4. 総括

**Ralph-lab v2 (2026-09-07) の到達点**:

1. **Ralph loop 実装として一通り動く**: 任意 agent CLI × 任意 gate、
   マルチモデル比較、JSONL 観測性、4 層防御、prompt patterns。
2. **Goodhart 4 種を実測**: 捏造 / 削除 / 迂回 / 逆向き置換、8 回観察を
   蓄積。「Goodhart は塞いだ穴の隣に移動する」を実測で確認。
3. **framework 側の対策を段階的に実装**: 単調性 check → 内容 non-empty →
   Layer B 委譲 → Layer C judge → retries → retry_aggregate → dir 対応 →
   baseline_document 分離 → silent failure 検出。
4. **prompt patterns を体系化**: 4 pattern (delegation / agent / gate feedback / post_eval) + skill pathology 分類。
5. **reference implementation**: `goals/examples/doc-verify-unified.yaml`
   で全拡張を組み合わせた 運用テンプレを提供。

**残った未解決**:
- **Layer B 非決定性の実測分布** (n=1-6 で片鱗、n=10-20 で真の分布)
- **上位 model + prompt Pattern 2 での agent adaptive さ**
- **framework 拡張** (Windows / parallel / cost tracking)
- **実運用の連続 workflow 検証** (daily-curation-reports 系)

**これから何をやるか (推奨)**:
- ralph-lab を「他 project の gate 検証」に投入する — real workflow への統合
- Anthropic + opencode で code-fix-pytest (P10-B の対照)
- 上位 model で unified spec を回して adaptive さ実測
- 「予測→実測→learnings」の loop-goal 精神を継続

---

## 5. 主要 artifacts (再現用 pointer)

### コード
- `src/ralph_lab/core/`: workspace / spec / loop / gate / agent_cli / delegation / check
- `scripts/judge-openrouter.py`: 汎用 OpenRouter judge wrapper (stdlib only)
- `experiments/real-doc-refs/gate.sh`: Layer A の 3 checks 実装

### Docs
- `docs/knowhow/gate-design-patterns.md`: Goodhart 4 手法 × Gate 5 check × 4 Layer
- `docs/knowhow/gate-delegation-patterns.md`: 委譲 3 方式 (A/B/C)
- `docs/knowhow/gate-neutrality.md`: gate 中立性 (Level C) の設計思想
- `docs/knowhow/prompt-patterns.md`: 4 種 prompt の書き分け + retry_aggregate
- `docs/knowhow/agent-cli-opencode.md`: opencode 特有の noise-guard

### Reference specs
- `goals/examples/doc-verify-unified.yaml`: 全拡張の統合例 ← 実運用テンプレ
- `goals/examples/doc-verify-delegating-p18.yaml`: 個別実験 (P18、fact-checker prompt 改訂)
- `goals/examples/real-doc-refs.yaml`: 最小構成

### 実験ログ (28 doc)
- `docs/experiments/`: P4 (2026-08-15) 〜 P26 (2026-09-07)
- 特に P13-CORRECTION.md, P16, P18, P22, P24 の "予測 vs 実測" の乖離が learning
