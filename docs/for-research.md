# 研究ログ

**予測 → 実測** の研究記録。P4 (2026-08-15、v1) 〜 P26 (2026-09-07、v2) の
実験 trail、Ralph landscape 調査、progress marker。

---

## 読み方

**目的別**:

- **Ralph pattern の landscape を知りたい**
  → [ralph-loop-landscape (2026-09-06)](research/2026-09-06-ralph-loop-landscape.md)
- **Anthropic 公式知見 + MAST failure taxonomy**
  → [agent-loop-overview (2026-08-05)](research/2026-08-05-agent-loop-overview.md)
- **現在の progress marker + 残課題**
  → [BACKLOG](01-BACKLOG.md)
- **総括**
  → [CONCLUSIONS](CONCLUSIONS.md)

---

## Experiments 一覧 (時系列)

**Predict-first 精神** に従い、各実験は plan (予測) → results (実測) の
2 doc 構成。**外れた予測も残す** (learning source)。

### v1 (agent-loop-lab、openai-agents SDK)

- **P4 (2026-08-15)**: gpt-4.1-mini via SDK、S-99 空エントリ捏造を実測
  - [Plan](experiments/2026-08-15-p4-plan.md) / [Results](experiments/2026-08-15-p4-results.md)

### v2 (ralph-lab、subprocess ベース)

- **P7 (2026-09-06)**: aider vs opencode 比較
  - [Report](experiments/2026-09-06-p7-aider-vs-opencode.md)
- **P9 (2026-09-06)**: pytest gate、code-fix 実測
  - [Report](experiments/2026-09-06-p9-code-fix-pytest.md)
- **P10 (2026-09-06)**: haiku-4.5 / sonnet-4.5 で code-fix 再測
  - [Plan](experiments/2026-09-06-p10-plan.md) / [Results](experiments/2026-09-06-p10-results.md)
- **P11 (2026-09-06)**: 実運用文書 (脚注参照) の初 fix — 削除型 Goodhart 観察
  - [Plan](experiments/2026-09-06-p11-real-doc-plan.md) / [Results](experiments/2026-09-06-p11-real-doc-results.md)
- **P12 (2026-09-06)**: 単調性 check 追加 — 空定義追加型 Goodhart への移動を実測
  - [Plan](experiments/2026-09-06-p12-plan.md) / [Results](experiments/2026-09-06-p12-results.md)
- **P13 (2026-09-06)**: 内容 non-empty check + 8 度目 Goodhart 実測
  - [Plan](experiments/2026-09-06-p13-plan.md) / [Results](experiments/2026-09-06-p13-results.md) /
    **[CORRECTION](experiments/2026-09-06-p13-CORRECTION.md)** (誤読の訂正)
  - P13-4 (対策後、実測): [Plan](experiments/2026-09-06-p13b-plan.md)
- **P15 (2026-09-06)**: 委譲機構 (Layer B/C) 実 API 検証
  - [Plan](experiments/2026-09-06-p15-plan.md) / [Results](experiments/2026-09-06-p15-results.md)
- **P16 (2026-09-06)**: 異 provider judge (gpt-4o) 実測
  - [Plan](experiments/2026-09-06-p16-plan.md) / [Results](experiments/2026-09-06-p16-results.md)
- **P18 (2026-09-06)**: fact-checker prompt 改訂 — URL なし dummy 捕捉
  - [Plan](experiments/2026-09-06-p18-plan.md) / [Results](experiments/2026-09-06-p18-results.md)
- **P22 (2026-09-06)**: retries=2 統合実測 — 非決定性 vs 決定的 FAIL
  - [Results](experiments/2026-09-06-p22-results.md)
- **P24 (2026-09-07)**: Layer B 非決定性の直接サンプリング (n=6)
  - [Plan](experiments/2026-09-07-p24-plan.md) / [Results](experiments/2026-09-07-p24-results.md)

**Goodhart 4 種の観察 (8 回)** は [BACKLOG "6 度観察された..." 節](01-BACKLOG.md) 参照。

---

## Framework 側の実装記録 (P で番号無し)

BACKLOG に [x] 印で完了記録:

- **P13-1**: Check 3 (内容 non-empty) 実装
- **P13-3**: Layer 0 (BASE hash verify + tarfile snapshot restore)
- **P14**: 委譲 3 方式 (A/B/C) 実装
- **P17**: JSONL log の stdout_head / stderr_head
- **P19**: `post_evaluation.run_always` + status=judge_passed
- **P20**: `retries: N` + attempts tracking
- **P26**: `retry_aggregate` (any_pass / all_pass / majority)

他 5 件は BACKLOG 参照。

---

## Research (landscape / overview)

**背景 / 先行研究**:

- [ralph-loop-landscape (2026-09-06)](research/2026-09-06-ralph-loop-landscape.md) — 6 実装比較
  + 5 論文レビュー + § 7 未解決論点 (ralph-lab を作る動機)
- [agent-loop-overview (2026-08-05)](research/2026-08-05-agent-loop-overview.md) — Anthropic 公式
  + MAST failure taxonomy
- [Plan doc (旧)](research/plan.md) — 一部履歴保存

---

## Progress marker

- [BACKLOG](01-BACKLOG.md) — 未着手 / 進行中 / 完了印
- [CONCLUSIONS](CONCLUSIONS.md) — 2026-09-07 時点の総括

---

## Predict-first 精神

**実験を書く時のルール**:

1. **予測を実行前に書く** — 「シナリオ n=1〜5 + 予測外」の形式
2. **実測後、予測 vs 実測を対比** — 外れも残す (P13-CORRECTION が代表例)
3. **Cost / 時間 / model / seed を明記** — 再現可能に
4. **学びを教訓節に** — なぜ予測が外れたか

参考: [loop-goal HANDOVER §2.4](https://github.com/dobachi/claude-skills-marketplace) の
「予測を書く」原則。
