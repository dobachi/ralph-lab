# experiments/delegating-gate/

**方式 A の実装例**: gate.sh 内で他スキルを subprocess として呼び出し、
Layer A (syntactic) + Layer B (委譲) の 2 段構えを実現する。

## 目的

Ralph-lab が苦手な semantic 判定 (Check 4-5) を、既存の別スキル
(fact-checker / doc-review) に **subprocess 経由で委譲**する PoC。

詳細な設計は [../../docs/knowhow/gate-delegation-patterns.md](../../docs/knowhow/gate-delegation-patterns.md)
参照。

## Gate の構造

```
gate.sh <current_file>
  ├── Layer A (syntactic, Python embedded)
  │    ├── Check 1: 対応関係 (refs vs defs)
  │    ├── Check 2: 単調性 (BASE との比較)
  │    └── Check 3: 内容 non-empty
  │    └── Layer A fail → fail-fast (Layer B スキップ)
  │
  └── Layer B (委譲、claude subprocess)
       ├── fact-checker → URL 実在性 / 引用の妥当性
       └── doc-review   → 論理妥当性 (critical only)
```

各委譲は `timeout 300` (5 分) で切る。時間内に返らなければスキップ (fail に
しない、gate の完全崩壊を避ける)。

## 前提

1. **claude CLI** が PATH にあり、認証済み (`~/.claude`)
2. **fact-checker** / **doc-review** スキルが Claude Code で利用可能
   (claude-skills-marketplace 経由 or 手元 install)
3. `real-doc-refs` の書式 (脚注 `[^N]` + `[^N]: URL` 定義) の Markdown 文書

**claude が無い場合**: gate.sh は自動的に Layer B をスキップし、Layer A の
みで判定する (`OK (Layer A のみ)` を出力)。

## 使い方

### 単体テスト

```bash
# baseline 自身との比較 (問題なしなら OK)
BASE=/path/to/baseline.md ./gate.sh /path/to/baseline.md

# buggy 版 (未定義 [^99] 有り)
BASE=/path/to/baseline.md ./gate.sh /path/to/buggy.md
```

### ralph-lab spec からの呼び出し

`goals/examples/doc-verify-delegating.yaml`:
```yaml
gate:
  script: ../../experiments/delegating-gate/gate.sh
  env: {}
  timeout_sec: 900  # 委譲込みで長め
```

## Cost / 時間の実測目安

Layer A のみ: <1s、cost ゼロ
Layer B 委譲: fact-checker + doc-review で 30-120s、cost $0.05-0.20/iter

Ralph loop で 5 iter 回すと、Layer B は最大 5 × $0.20 = **$1** 程度かかる
可能性。**Layer A の fail-fast** で無駄呼び出しを避けているが、成功パスは
全 iter で委譲が走る。

## Trade-offs

**方式 A の利点**:
- ralph-lab core 変更ゼロ
- gate.sh 単体で完結 (spec.yaml も従来のまま)
- fresh subprocess で Ralph 原則忠実

**方式 A の欠点**:
- 委譲の記述が gate.sh に集中 (拡張性低い)
- 集約ロジックは自作
- JSONL log に委譲別の詳細が残らない (Layer B は 1 stdout 塊で扱う)

**方式 B/C を検討する動機**:
- 複数 spec で同じ委譲を使い回すなら 方式 B (spec.yaml `delegate_to`)
- Ralph pass 後の最終 judge なら 方式 C (`post_evaluation`)

## 関連

- [../real-doc-refs/](../real-doc-refs/) — Layer A のみの実装 (元の gate.sh)
- [../../docs/knowhow/gate-delegation-patterns.md](../../docs/knowhow/gate-delegation-patterns.md)
  — 3 方式の設計解説
- [../../docs/knowhow/gate-design-patterns.md](../../docs/knowhow/gate-design-patterns.md)
  — Goodhart 4 手法 × gate 5 check、多層防御 3 層
