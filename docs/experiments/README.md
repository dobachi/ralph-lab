# docs/experiments/

**予測をコードや文書ではなく先に**書き出し、その通りかを実測して突き合わせる
記録場所。外れた予測は残す (loop-goal HANDOVER 精神)。

## 現行

- **2026-08-15-p4-plan.md** — v1 (agent-loop-lab) 時代の P4 実験計画
- **2026-08-15-p4-results.md** — v1 P4 実験の結果、予測 3/8 外し
  - 主要な発見: gpt-4.1-mini が「ソース S-99 を捏造して pass」した現象
    (loop-goal §7.11 「gate 緑 = 追跡可能性の形式しか意味しない」の実測)
  - claude-haiku-4.5 のみが唯一 clean fix (2-line targeted edit)
  - **これらの実験は v1 (openai-agents SDK 経由) で得た知見**。v2
    (ralph-lab, subprocess ベース) では未再現。移植価値のある実験。

## 予定 (v2 で再現したい)

- v2 で P4 相当を再現: 同一 goal を複数 model で走らせ、diff の質を評価
  - 特に「ソース捏造」が v2 の agent CLI (aider / opencode / claude 直) でも
    起きるか。gate 側 (loop-goal) は同じなので、agent 側の差だけで観察可能
- Anthropic model + aider + OpenRouter の SEARCH/REPLACE 失敗の原因調査
  (docs/knowhow/aider-integration.md §E 参照)

## 書き方

**実行前** の doc (計画): 予測、条件、成功条件を書く。
**実行後** の doc (結果): 実測、予測との差、外れた予測を保存する。
「外れた予測を後付けで正当化しない」 (loop-goal 精神)。
