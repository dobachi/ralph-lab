# ralph-lab docs

## 構成

| ディレクトリ | 内容 |
|---|---|
| [knowhow/](knowhow/) | 実装で得た再現性のあるノウハウ (症状 / 原因 / 修正の 4 点セット) |
| [experiments/](experiments/) | 予測 → 実行 → 実測結果の記録 (外れた予測も残す) |
| [research/](research/) | 周辺調査 (Ralph loop landscape 等) |

## 読む順序

**初めて ralph-lab に触れるなら**:

1. リポジトリ root の [README.md](00-repo-README.md) — 全体像
2. [research/2026-09-06-ralph-loop-landscape.md](research/2026-09-06-ralph-loop-landscape.md)
   § 1-3 — Ralph loop とは何か
3. [knowhow/agent-cli-contract.md](knowhow/agent-cli-contract.md) — spec の
   契約を理解する
4. [knowhow/gate-neutrality.md](knowhow/gate-neutrality.md) — gate 中立性
   (Level C) の設計意図

**特定の CLI を組み込むなら**:

- aider: [knowhow/aider-integration.md](knowhow/aider-integration.md)
- claude CLI: `goals/examples/doc-verify-loop-goal.yaml` の例を参照

**Multi-model 比較するなら**:

- [knowhow/multi-model-comparison.md](knowhow/multi-model-comparison.md)
- 過去実測: [experiments/2026-08-15-p4-results.md](experiments/2026-08-15-p4-results.md)
  (v1 データ)

**設計判断の背景を知りたいなら**:

- [research/2026-08-05-agent-loop-overview.md](research/2026-08-05-agent-loop-overview.md)
  — Anthropic 公式知見と MAST failure taxonomy
- [research/2026-09-06-ralph-loop-landscape.md](research/2026-09-06-ralph-loop-landscape.md)
  § 7 未解決論点 — ralph-lab を作る動機
