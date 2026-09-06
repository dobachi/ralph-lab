# docs/knowhow/

ralph-lab を実装・運用して得た**再現性のあるノウハウ**を残す場所。

**目的**: 同じ落とし穴を二度踏まないため、と、外部の似た実装 (Ralph 系他ツール)
を作る人が最初から回避できるようにするため。

**書き方**: 発見が **具体的な症状 / 直接の原因 / 再現手順 / 修正** の 4 点セット
で書ける状態になったら 1 file 追加する。予想や推測は書かない (別途 experiments/
に残す)。

## Index

- [aider-integration.md](aider-integration.md) — aider CLI を Ralph loop で
  使うときの注意事項。特に chat history 蓄積問題
- [agent-cli-opencode.md](agent-cli-opencode.md) — opencode CLI の pitfall
  (`-f` array と長い prompt の衝突、stdin_prompt: true が必須)
- [multi-model-comparison.md](multi-model-comparison.md) — `--models` で
  多モデル比較するときの workspace 設計と実測データ
- [agent-cli-contract.md](agent-cli-contract.md) — Ralph の agent CLI に
  求める挙動 (subprocess から呼べる、stdin/args で prompt を受ける、
  file 編集を自前でやる、fresh-context)。ralph-lab 側の spec 契約と対応
- [gate-neutrality.md](gate-neutrality.md) — Level C (gate 中立) の実装意味と
  loop-goal / pytest / cargo test 等の複数 gate 対応

## 関連

- [../experiments/](../experiments/) — 実験ノート (予測と実測、外れた予測)
- [../research/](../research/) — 周辺調査 (Ralph loop landscape 等)
