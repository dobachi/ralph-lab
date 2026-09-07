# 開発者向け

ralph-lab を **拡張・改造・貢献する** 人向けのドキュメント。

---

## 推奨読み順

1. **[Architecture](architecture.md)** — 4 層防御の設計 (Users と共通)
2. **[Knowhow 目次](knowhow/README.md)** — 再現性のあるノウハウ集
3. **[CONCLUSIONS](CONCLUSIONS.md)** — 到達点と残課題 (2026-09-07 時点)
4. **[AI 協働 spec 提案](proposal-ai-collaborative-spec.md)** — 次期機能の設計提案

---

## Knowhow (再現性のあるノウハウ)

**症状 / 原因 / 修正の 4 点セット** に留意した technical writing。詳細は
[knowhow/README.md](knowhow/README.md)。

### 契約とインターフェース

- [agent-cli-contract](knowhow/agent-cli-contract.md) — spec.yaml が定義する契約
- [agent-cli-opencode](knowhow/agent-cli-opencode.md) — opencode 固有の
  noise-guard (chat history / -f 配列衝突)
- [aider-integration](knowhow/aider-integration.md) — aider の SEARCH/REPLACE
  失敗 / .aider.chat.history.md 蓄積 / udiff format

### Gate / Layer 設計

- [gate-neutrality](knowhow/gate-neutrality.md) — Level C (gate 中立性) の設計思想
- [gate-design-patterns](knowhow/gate-design-patterns.md) — Goodhart 4 手法 ×
  Gate 5 check × 4 Layer 防御
- [gate-delegation-patterns](knowhow/gate-delegation-patterns.md) — 委譲 3 方式
  (A: gate.sh 内、B: `delegate_to`、C: `post_evaluation`)

### Prompt engineering

- [prompt-patterns](knowhow/prompt-patterns.md) — 4 種 prompt の書き分け +
  retry_aggregate による pathology 制御

### Multi-model

- [multi-model-comparison](knowhow/multi-model-comparison.md) — `--models m1,m2,m3` の
  使い方と実測結果

---

## 設計判断の背景

- **[CONCLUSIONS](CONCLUSIONS.md)** (2026-09-07) — 実現できていること /
  残った課題 / なぜ残っているか
- **[AI 協働 spec 提案](proposal-ai-collaborative-spec.md)** — 「ルールベース生成後、
  AI と協業で spec を洗練させる」提案 (User's proposal + 対案 + 推奨案)

---

## Source Layout

```
ralph-lab/
├── src/ralph_lab/
│   ├── cli.py              # ralph CLI entry
│   └── core/
│       ├── spec.py         # GoalSpec + AgentSpec + DelegationCall + PostEvaluationConfig
│       ├── workspace.py    # Workspace.prepare/verify/cleanup (P9/P13 dir 対応)
│       ├── agent_cli.py    # run_agent (subprocess)
│       ├── gate.py         # run_gate + format_gate_feedback
│       ├── delegation.py   # run_delegation + retry_aggregate (P20/P26)
│       ├── loop.py         # run_ralph_loop の本体
│       ├── check.py        # ralph check の validation
│       └── init.py         # ralph init の template 展開
├── scripts/
│   └── judge-openrouter.py # stdlib のみ OpenRouter API wrapper
├── goals/examples/          # サンプル spec (unified spec が最終形)
├── experiments/             # test fixtures + gate.sh 実装例
├── docs/                    # このサイト
└── tests/                   # unit test
```

---

## Contributing

- Bug / feature: [GitHub Issues](https://github.com/dobachi/ralph-lab/issues)
- Pull request: main branch へ、CHANGELOG.md に記載
- 実験: [研究ログ](for-research.md) 参照、predict-first (実行前に予測 doc 書く) 遵守
