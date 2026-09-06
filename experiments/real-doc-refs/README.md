# experiments/real-doc-refs/

**実運用文書 (`[^N]` 脚注参照書式) の Ralph loop 用の custom gate と fixture 生成手順**。
P11 (2026-09-06) で使用。

## 目的

ralph-lab の **Level C gate 中立性の実運用検証**。loop-goal
(`[S-XX]` + 表形式) 前提の gate ではなく、`[^N]` 脚注参照形式に合わせた
custom gate を書けるかを実証する。

## ファイル

| ファイル | 内容 | commit |
|---|---|---|
| `gate.sh` | 脚注参照の対応関係 check (Python embedded、標準ライブラリのみ) | ✅ |
| `README.md` | この README | ✅ |
| `.gitignore` | 下記 `*.md` fixture を commit しないため | ✅ |
| `baseline.md` | daily-curation-reports の実文書 copy (元記事) | ❌ (private 元) |
| `buggy.md` | baseline から `[^1]` → `[^99]` に壊した版 | ❌ (private 元) |
| `current.md` | agent が編集する workspace 内 file | ❌ (workspace の一時) |

## Fixture 準備手順

daily-curation-reports (private) から実文書を copy し、わざと壊した版を作る:

```bash
# 例: 2026-09-01 の記事
SAMPLE=~/Sources/daily-curation-reports/reports/2026/09/01/01-cirpass2-dpp-reference-architecture-d41.md

# baseline (元記事) を copy
cp "$SAMPLE" ~/Sources/ralph-lab/experiments/real-doc-refs/baseline.md

# buggy 版を作る: [^1] を [^99] に置換、ただし定義行は元に戻す
sed 's/\[\^1\]/[^99]/g; s/\[\^99\]:/[^1]:/g' "$SAMPLE" \
    > ~/Sources/ralph-lab/experiments/real-doc-refs/buggy.md
```

## Gate の契約

- 呼び出し: `gate.sh <current_file>`
- 検査:
  - 本文中の `[^N]` 参照と `[^N]: URL` 定義の対応関係
  - 未定義参照 (本文にあるが定義がない) → NG (exit 1)
  - 未使用定義 (定義はあるが本文にない) → 現状 WARN (exit 0)
- Stdout: findings 詳細 + 「保証しないこと」

## Ralph run

```bash
# spec は project root からの相対 path
uv run ralph run goals/examples/real-doc-refs.yaml --pretty
```

## 実測 (P11、2026-09-06)

`opencode + openrouter/anthropic/claude-haiku-4.5`:
- **status: pass, iter 1, 12s**
- **ただし agent は `[^99]` を削除して pass** (Goodhart 6 度目、「削除で満たす」型)
- 詳細: [../../docs/experiments/2026-09-06-p11-real-doc-results.md](../../docs/experiments/2026-09-06-p11-real-doc-results.md)

## Gate の設計上の穴 (P11 で顕在化)

現状 `unused=WARN` は削除経路を開く。強化案:

1. **unused も NG に**: シンプル、削除を全禁止
2. **BASE からの単調性 check** (loop-goal `no_regression` 相当): 削除+捏造の両方を塞げる
3. **prompt 側の「削除禁止」明示**: gate ではなく指示レベル

BACKLOG で追跡。

## 関連

- ralph-lab の [docs/knowhow/gate-neutrality.md](../../docs/knowhow/gate-neutrality.md) — gate 中立性の設計思想
- ralph-lab の [docs/experiments/2026-09-06-p11-real-doc-plan.md](../../docs/experiments/2026-09-06-p11-real-doc-plan.md) — 実行前予測
- [experiments/code-fix-pytest/](../code-fix-pytest/) — pytest gate 版 (P9)
