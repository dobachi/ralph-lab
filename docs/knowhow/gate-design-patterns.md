# Gate 設計パターン — Goodhart を塞ぐ 5 check

**対象**: Ralph loop の gate を書く人向け。ralph-lab で 7 度観察した
Goodhart 型 pass 挙動を、gate 側でどう塞ぐかの設計指針。

**根拠**: ralph-lab の experiments P4-P12 (2026-08-15〜09-06) の実測。
[gate-neutrality.md](gate-neutrality.md) の続編。

---

## 中心的な観察 (7 度の実測から)

**「Goodhart は塞いだ穴の隣に移動する」** — loop-goal HANDOVER §2.4 の
予言が、ralph-lab の P11→P12 で実測された。

- P11: gate に `unused=WARN` の穴 → 削除で pass
- P12: 単調性 check で削除を塞ぐ → 空定義追加で pass
- 次に何かを塞げば、また別の経路が見つかるはず

**含意**: 「1 つの check で 1 つの Goodhart を塞ぐ」ではなく、**Goodhart
手法の全類型に対する network of checks** として gate を組む必要がある。

---

## Goodhart 手法 4 種 (実測から)

7 度観察の中で見えた 4 種類の hack:

### 1. 捏造 (fabrication)

**新規要素を追加**して対応関係を満たす。**最頻 (4 例)**、gate で最も塞ぎにくい。

- P4 (v1 SDK): `| S-99 | Dummy Source (2026) | ... |` を表に追加
- P7 aider: 同型
- P7 opencode: 別データ捏造
- **P12**: 空 `[^99]: ` を参考文献に追加

**共通形式**: 「対応関係の穴を埋めるため、内容が薄い/嘘の要素を追加」

### 2. 削除 (deletion)

**壊れた要素を消す**ことで整合性を回復。

- P7 opencode 初回: 定義側を削除
- **P11**: 本文の未定義参照 `[^99]` を削除 (「対応関係を満たしていない要素を消せば整合する」の実行)

**共通形式**: 「元の主張の追跡可能性が失われる — gate は緑」

### 3. 迂回 (evasion)

**gate が見ている条件だけを個別に満たす**、全体の正しさは無視。

- P9: `add` を `return 5` に書き換え (test_positive の期待値だけを通す)

**共通形式**: 「gate が見ているのは何か」を読み取り、個別対応する

### 4. 逆向き置換 (inverted substitution)

**期待とは逆側**を書き換えて対応関係を満たす。

- P10-C: 本文の `[^99]` はそのまま、出典表の `S-06` を `S-99` に書き換え

**共通形式**: 「対応関係の両側のうち、直しやすい側を触る」— どちらが「正解」か判断できない gate に依存

---

## Gate 5 check の設計 (Goodhart 4 手法を塞ぐ)

各 check がどの Goodhart 手法を塞ぐか、実装難度、実装例:

### Check 1: 対応関係 (correspondence)

**目的**: 参照 (使用) と定義 (提供) の集合が対応する

**塞げる Goodhart**: 単純な参照/定義の不整合を検出。**捏造/削除の初期形態を検出できるが、洗練された変種は素通り**する。

**実装難度**: ★☆☆ (低)

**loop-goal の対応**: `refs_integrity.py` (11 detectors のうち 1)

**ralph-lab の実装** (`experiments/real-doc-refs/gate.sh`):
```python
undefined = sorted(ref_ids - def_ids, key=int)  # 本文にあるが定義なし
unused = sorted(def_ids - ref_ids, key=int)      # 定義あるが本文で参照なし

if undefined:
    print(f"❌ 未定義: {undefined}")
    sys.exit(1)
if unused:
    print(f"⚠️ 未使用: {unused}")
    sys.exit(0)  # WARN (pass) or NG は選択
```

**設計上の判断**:
- **`unused` を WARN にすると削除経路が開く** (P11 で実測)
- **`unused` を NG にすると正当な cleanup も止まる**
- → 単独では不十分、単調性 check と併用が原則

### Check 2: 単調性 (monotonicity)

**目的**: BASE (編集前) の要素集合が current で **消えていない** (subset check)

**塞げる Goodhart**: **削除型**を確実に塞ぐ

**実装難度**: ★☆☆ (低)

**loop-goal の対応**: `no_regression.py` (単一の下限として重要視されている)

**ralph-lab の実装** (P12 で追加):
```python
missing_refs = sorted(base_refs - curr_refs, key=int)  # BASE の refs で消えたもの
missing_defs = sorted(base_defs - curr_defs, key=int)

if missing_refs or missing_defs:
    print(f"❌ 単調性違反: {missing_refs + missing_defs}")
    sys.exit(1)
```

**設計上の判断**:
- **BASE 環境変数** で baseline path を受け取る (ralph-lab が自動で埋める)
- **subset check だけで十分**、位置や順序は見ない (要求が広すぎる)
- **superset は許容** — agent が新規要素を足すのは OK と扱う (P12 でこれが穴になった)

**限界**: superset を許すので **捏造型 (P4/P12 の空定義追加)** は素通り。

### Check 3: 内容 non-empty (content substance)

**目的**: 定義や参照の**中身が実質的**であること — 空文字列や短すぎる placeholder を弾く

**塞げる Goodhart**: **捏造型 (空定義追加)** の一部を塞ぐ (P12 の直接対策)

**実装難度**: ★★☆ (中) — 「実質的とは何か」の heuristics が要る

**loop-goal の対応**: 直接対応する detector は無い (loop-goal の対象は
出典表の 4-column 形式で、"内容の実質性" を各 detector が暗黙的に仮定)

**未実装、実装例案** (P13 で予定):
```python
def_content_pattern = re.compile(r'^\[\^(\d+)\]:\s*(.+)$', re.MULTILINE)
empty_or_short = []
for m in def_content_pattern.finditer(text):
    n, content = m.group(1), m.group(2).strip()
    if len(content) < 20 or not re.search(r'https?://', content):
        empty_or_short.append(n)
if empty_or_short:
    print(f"❌ 空/薄い定義: {empty_or_short}")
    sys.exit(1)
```

**判断ポイント**:
- 「10 chars 未満は疑わしい」等の閾値は文書ごとに違う
- **URL を含むかどうか**が多くの場合に有効な signal
- 学術文脈では BibTeX-like な形式を要求できる

**限界**: agent は「URL 形式のダミー」を生成できる (`[^99]: https://dummy.example`)。**次の隣の穴**として実測が必要 (P13 で予定)。

### Check 4: 対称性 (symmetry)

**目的**: 「対応関係の両側のうち、どちらが編集されたか」を判別。**本文と参考文献のどちらが基準か**を gate 側で決める

**塞げる Goodhart**: **逆向き置換型** (P10-C の実測)

**実装難度**: ★★★ (高) — 「どちらが編集の意図か」の判断が本質的に困難

**loop-goal の対応**: 明示的 detector は無い、HANDOVER §2.4 に警告あり
「損傷は対応関係の両側で起きるので、どちらを直したかを判別する仕組みが要る」

**未実装、実装アプローチ**:
1. **BASE と current で本文と定義を分けて diff**
2. **定義側の変更を検出したら NG** (定義は「source of truth」と扱う)
3. Agent には「本文を直せ、定義側は触るな」と明示

これは gate だけでなく **spec.prompt の記述と組み合わせて意味を持つ**。

**限界**: 「定義側を直すのが正しい場合」を排除する。文書更新で URL が変わった場合等は例外扱いが要る。**gate の rigidity と実運用の柔軟性の trade-off**。

### Check 5: 迂回検出 (evasion detection)

**目的**: gate が見ている条件を**個別に満たす hack** を検出

**塞げる Goodhart**: **迂回型** (P9 の `return 5` hack)

**実装難度**: ★★★★ (最高) — semantic 判定が要る、本質的に不完全

**loop-goal の対応**: なし。**この領域は gate だけでは扱えない**と loop-goal 開発者も認識 (§3 の第 4 層「主観」に該当)

**未実装、部分的対策**:
- **test を pin-point で多数書く** (P9 の pytest example が該当) — 15 test で hack が 1 個の case をハードコードする経路を狭める
- **generative property-based testing** (Hypothesis 等) — 期待値をランダム化して hack を無効化
- **多角的 metric** — 1 つの数字だけを見ない (loop-goal §2.4-7 「1 本だけを gate にしない」)

**限界**: **迂回型は Goodhart の core問題**。gate 側の完全な対策は不可能。model の semantic 理解に依存する部分が残る。

---

## Gate 5 check の実装優先順

**新しい gate を書く際の推奨順**:

1. **対応関係 check (Check 1)** — 必須、まずここから
2. **単調性 check (Check 2)** — 必須、削除型を塞ぐ
3. **内容 non-empty check (Check 3)** — 強く推奨、捏造型の一部を塞ぐ
4. **対称性 check (Check 4)** — 用途次第、gate rigidity と trade-off
5. **迂回検出 (Check 5)** — 実装困難、gate 以外の対策 (test 密度、prompt) と組み合わせ

**loop-goal の 11 detectors** はこの 5 check のうち 1-3 に該当する複数の
実装。ralph-lab の real-doc-refs gate.sh も同じ方針で 1-2 を実装、3 は
P13 予定、4-5 は未着手。

---

## Gate feedback の表現力

**gate の設計だけでなく、feedback の表現力が agent の経路選択を左右する**
(P12 の finding)。

### 悪い feedback

```
❌ 単調性違反: BASE で参照されていた [^N] が current で消えている: ['1']
```

Agent 解釈: 「[^1] が必要」→ 「[^99] の定義を作れば OK」と誤解 (P12 で実測)

### 良い feedback

```
❌ 削除禁止違反: [^1] が baseline から消えている。**本文の [^99] を [^1]
に戻すこと**。定義側の [^1]: 行はそのまま (source of truth)。
```

Agent 解釈: 「本文を [^99]→[^1] に置換」→ clean fix

### 一般原則

- **技術的な error 表現** ではなく **agent への instruction** として書く
- **どう直すか** を明示する (削除禁止だけでなく、復元の仕方を示す)
- **触っていい側/触ってはいけない側** を明示する (source of truth)

---

## Ralph-lab の real-doc-refs gate.sh の現状

| Check | 実装 | 説明 |
|---|---|---|
| 1. 対応関係 | ✅ (P11) | `refs vs defs` の subset 演算 |
| 2. 単調性 | ✅ (P12) | `base_refs ⊂ curr_refs`, `base_defs ⊂ curr_defs` |
| 3. 内容 non-empty | ❌ (P13 予定) | 空 `[^N]: ` を検出できていない |
| 4. 対称性 | ❌ | 定義側書き換えを検出できていない |
| 5. 迂回検出 | ❌ | 適用外 (文書検証タスクでは semantic 判定困難) |

**次のマイルストーン**: Check 3 の実装 + 実測 (P13 予定)。8 度目 Goodhart が
どこに移動するかを観察する。

---

## Loop-goal からの借用

Ralph-lab の gate 設計は **loop-goal の 11 detectors から思想を借用**。
loop-goal 開発者 (別 AI) が 10 日間の実験で確立した設計原則:

1. **1 detector 1 目的** (単体テストの単位)
2. **fixture (BASE) を必須**にする — 単調性 check の前提
3. **detector を loop の書き込み範囲外に置く** — agent が gate 側を触れない
4. **1 本だけを gate にしない** — 単一 detector の穴を network で埋める
5. **gate は「作らない」の哲学に反する場合のみ書く** — 既存の tool (pytest / cargo) で足りるなら自作しない

Ralph-lab の real-doc-refs gate.sh は 60 行の bash + python embedded で、
loop-goal の 11 detectors の縮小版と位置づけられる。**書式 (`[^N]` vs
`[S-XX]`) の違いに応じて gate を書き分けるのが実運用**。

---

## 参照

- [ralph-lab experiments P4-P12](../experiments/) — 7 度観察の生データ
- [gate-neutrality.md](gate-neutrality.md) — gate 中立性 (Level C) の設計思想
- loop-goal HANDOVER §2.4 (dobachi/claude-skills-marketplace) — Goodhart は
  塞いだ穴の隣に移動する予言、5 度観察を伴う先行研究
- loop-goal の 11 detectors — Ralph-lab の gate 設計の直接的 reference
