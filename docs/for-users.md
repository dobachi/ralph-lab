# ユーザー向け

ralph-lab を **使う** 人向けのドキュメント。動かすまでの手順から、
spec.yaml の全 field 詳細、トラブルシュートまで。

---

## 推奨読み順

1. **[Getting Started](getting-started.md)** — 5 分で 1 pass する経路
2. **[Architecture](architecture.md)** — 概念と 4 層防御を図で把握
3. **[Usage Manual](usage-manual.md)** — spec.yaml の全 field + cookbook

---

## Quick links

**目的別の入り口**:

- **文書検証をしたい (脚注書式、citation 完全性)**
  → [`goals/examples/real-doc-refs.yaml`](https://github.com/dobachi/ralph-lab/blob/main/goals/examples/real-doc-refs.yaml) を参考、[Usage Manual](usage-manual.md) の Layer A 節
- **コードを自動修正したい (pytest fail の fix)**
  → [`goals/examples/code-fix-pytest.yaml`](https://github.com/dobachi/ralph-lab/blob/main/goals/examples/code-fix-pytest.yaml)
- **Goodhart 対策を全部有効にした「本気の spec」がほしい**
  → [`goals/examples/doc-verify-unified.yaml`](https://github.com/dobachi/ralph-lab/blob/main/goals/examples/doc-verify-unified.yaml) (P14-P26 の全拡張を統合)
- **複数 model を比較したい**
  → [Multi-model 比較](knowhow/multi-model-comparison.md)

---

## Agent CLI ごとの入門

- **claude CLI**: [Getting Started](getting-started.md) の 経路 A
- **opencode + OpenRouter**: [Getting Started](getting-started.md) の 経路 B + [agent-cli-opencode](knowhow/agent-cli-opencode.md)
- **aider + OpenRouter**: [Getting Started](getting-started.md) の 経路 C + [aider-integration](knowhow/aider-integration.md)

---

## Troubleshooting

問題別の対処は [Usage Manual](usage-manual.md) の Troubleshooting 節参照。
より深い診断は [開発者向け](for-developers.md) 側の Knowhow を参照。

---

## Feedback

- Bug / feature: [GitHub Issues](https://github.com/dobachi/ralph-lab/issues)
