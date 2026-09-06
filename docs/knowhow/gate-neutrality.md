# Gate 中立性 (Level C) の実装意味

**対象**: ralph-lab は `spec.gate.script` に任意の bash script を受ける。
loop-goal は example の 1 つ。他の gate も同格。

---

## §A. Level C の定義

**gate 中立** とは:

1. ralph-lab は gate の中身を知らない
2. 契約は 3 点のみ:
   - **呼び出し**: `<script> <current_file>` (positional 1 引数)
   - **環境変数**: `BASE=<baseline_file>` (driver が自動で埋める)
   - **返り値**: exit 0 = pass, 非 0 = fail
3. stdout は次 iteration の agent への feedback として渡される

これを守れば **どんな検証器も gate にできる**:

- 文書検証: loop-goal
- コード: `pytest`, `cargo test`, `npm test`
- lint: `eslint`, `ruff`, `mypy`
- 静的検査: `grep -q "not-allowed"` (該当文字列がないことを確認)
- カスタム: 独自 bash script

---

## §B. 対比 - v1 (agent-loop-lab) との違い

v1 は loop-goal に密結合していた:

```yaml
# v1 (agent-loop-lab)
gate:
  script: ~/.claude/plugins/cache/dobachi-skills/loop-goal/0.3.0/skills/loop-goal/gate.sh
```

- init コマンドが loop-goal の gate.sh を自動探索
- example spec がすべて loop-goal 前提
- loop-goal が install されていないと動かない

v2 (ralph-lab) はこれを外した理由:

1. Ralph 系他ツールと同じ設計 (syuya2036, Ralph Orchestrator, PraisonAI
   は全て gate 中立)
2. 文書検証以外の用途 (code test, lint) に自然に載る
3. loop-goal に依存しないので **ralph-lab 単体で動作可能**
4. loop-goal は「相性の良い example gate」の 1 つ

---

## §C. Gate example のバリエーション

### loop-goal (文書検証)

```yaml
gate:
  script: ~/.claude/plugins/cache/dobachi-skills/loop-goal/0.3.0/skills/loop-goal/gate.sh
```

- 適合: Markdown 文書、`[S-XX]` 参照 + 出典表がある形式
- 契約: 11 detectors の AND (refs_integrity, declared_counts,
  citation_presence, forbidden_phrases, no_regression)
- fixture: broken_ref.md 等が 5 種類

### pytest (Python コード)

```yaml
gate:
  script: /project/scripts/pytest-gate.sh
```

中身の例:
```bash
#!/bin/bash
# pytest-gate.sh: pytest が通るまで
CURRENT=$1
# CURRENT が編集された Python file の path
# BASE は編集前 (現状未使用でも env で来る)
cd "$(dirname $CURRENT)"
pytest -x  # 1 個でも fail したら exit 1
```

### grep-based (単純な状態検査)

```yaml
gate:
  script: /path/to/grep-gate.sh
```

```bash
#!/bin/bash
# grep-gate.sh: 特定文字列が消えたら pass
CURRENT=$1
if grep -q "TODO" "$CURRENT"; then
    echo "still has TODO markers"
    exit 1
fi
echo "no TODO markers"
exit 0
```

### 複合 gate

```bash
#!/bin/bash
# 複数の検査を AND で束ねる
lint-check.sh "$1" && \
type-check.sh "$1" && \
test-run.sh "$1"
```

---

## §D. Gate 側の設計原則 (loop-goal から借りた教訓)

**Ralph 派生の gate 設計は loop-goal の設計原則を借りるとよい**
(agent-loop-lab v1 で長期実測済み):

### 1. 単一検出器をゲートにしない

複数の検出器を AND で束ねる。**1 個だけを gate にすると、通った瞬間に
別の問題が発生する** (loop-goal 実測: `citation_presence` を満たした
瞬間に `declared_counts` が壊れた)。

### 2. `no_regression` に相当する下限

「消して満たせる gate」は agent が最短経路で削除に走る (Goodhart 問題)。
編集前後で減っていないことを検査する何かを必ず混ぜる。

### 3. 前提が無ければ「測定できない」で NG

gate が対象 file に噛んでいないとき (書式が違う等) は fail-open せず
NG を返す。**gate が空回りしていることを agent と人に伝える**。

### 4. 「保証しないこと」を stdout に含める

gate は完璧ではない。何を検査していないかを明示する。agent が「gate は
緑だが実は問題がある」を認識できる。

### 5. 検出器は編集して使う小さいスクリプト

30-120 行の 1 目的 script。標準ライブラリのみ。定数はファイル冒頭に
ベタ書き。「編集して使う」を成立させるための制約。

---

## §E. Ralph loop での gate 選択の判断軸

**タスク領域から gate を選ぶ**:

| タスク | Gate 候補 |
|---|---|
| 文書検証 (引用整合、削除禁止) | loop-goal |
| Python コード修正 | pytest, ruff, mypy |
| Rust コード修正 | cargo test, cargo clippy |
| JavaScript/TS 修正 | vitest/jest, eslint, tsc |
| lint 汎用 | eslint, ruff, shellcheck |
| 状態検査のみ | grep-based custom script |
| ビルド成功まで | make, cargo build, npm run build |
| E2E テスト | Playwright, Cypress |

**gate の複雑さで CLI の agent との相性が変わる**:

- 単純な gate (grep, exit code のみ) → 弱い model + 短い prompt でも OK
- 複雑な gate (loop-goal の 5 detector) → 強い model + 詳細 prompt が必要

**Ralph 原則**: gate は決定的、agent は fresh context。gate を強くすることで
agent の劣化を検出可能にする。逆に gate が弱いと agent の失敗を見逃す。

---

## §F. 落とし穴

### 1. gate.sh の permission

`chmod +x gate.sh` 必須。ralph-lab は subprocess で起動するので
executable bit がないと `PermissionError` になる。

### 2. `BASE` 環境変数の意味

driver が自動で `BASE=<baseline file の path>` を注入するが、**gate 側は
BASE を無視してもよい**。使わない gate (pytest 等) は無視して current だけ
検査すれば OK。

### 3. gate の stdout サイズ

feedback として agent に渡されるので、あまりに大きい stdout (>10kB) は
prompt を圧迫する。gate 側で `head -c 5000` 等で truncate する対応が
必要な場合がある。ralph-lab の `format_gate_feedback()` は 6000 chars で
truncate する default 実装。

### 4. gate の実行時間

`spec.gate.timeout_sec` の default は 60 秒。E2E テスト等で長い gate は
明示的に伸ばす:

```yaml
gate:
  script: ./e2e-gate.sh
  timeout_sec: 300
```

### 5. gate が false pass する場合

**loop-goal §7.11 の教訓**: gate 緑は「追跡可能性の形式が整った」だけで
「文書が正しい」を意味しない。ralph-lab では対応策なし (gate 側の設計問題)。
gate の「保証しないこと」を読んで人が判断する。
