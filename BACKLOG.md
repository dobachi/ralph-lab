# BACKLOG

未着手 or 中期の課題。会話が終わっても持ち越したい項目を積んでおく置き場。

書き方: 1 行 1 項目。着手予定・優先度は書かない。**やる時に判断する**。
完了したら line ごと削除 or `[x]` で checked にして数日残す。

---

## 実装 / bug

- [x] opencode CLI との aider 比較 (使い勝手 A/B) — P7 (2026-09-06) 完了
- [x] `--edit-format udiff` で aider + Anthropic model の SEARCH/REPLACE 失敗が解消するか調査 — P10-C (2026-09-06) で有効性確認 ✅
- [x] `ralph init` サブコマンドの v1 移植 — P8 (2026-09-06) 完了
- [x] `ralph check` サブコマンドの v1 移植 — P8 (2026-09-06) 完了
- [ ] Windows 対応 (`/dev/stdin` 依存の解消、`--message-file` 系の platform 抽象化)
- [ ] cost 計算機能 (OpenRouter `/generation` endpoint or agent CLI の cost 出力を parse)
- [ ] `--parallel` 実装 (multi-model の並列実行、API rate throttle 込み)
- [ ] silent failure 検出 (v1 agent-loop-lab で発見: subprocess が exit 0 で戻るが何もしていない状態) の v2 での再現確認と対策

## 実験 / 検証

- [x] 実運用文書での動作確認 (daily-curation-reports の記事) — P11 (2026-09-06) 完了。opencode + haiku で pass 1 iter 12s、ただし削除型 Goodhart 発生。gate 設計が支配的と結論
- [ ] P11 続き: 別記事で同じ Goodhart が起きるか (n=2,3)、gate.sh に単調性 check 追加後の再試行
- [ ] agent CLI の網羅比較 — claude / codex / opencode / aider の 4 種で同じ goal
- [x] v1 P4 の再現 (「S-99 捏造で pass」現象が v2 でも起きるか) — P7 (2026-09-06) で再現確認済、aider/opencode で追認
- [ ] gate の複合化 — loop-goal + custom grep で複数 detector を AND
- [x] コード領域の gate 検証 (pytest) — P9 (2026-09-06) 実施、5 iter で pass せず。gpt-4.1-mini の Goodhart 型 hack (`return 5`) を実測。cargo / eslint は未実施
- [x] P9 の続き: sonnet-4.5 / haiku-4.5 で code-fix-pytest — P10-A/B (2026-09-06)、両者とも 5 iter で pass せず (divide の ValueError vs ZeroDivisionError で停止)
- [x] Anthropic model + opencode の検証 — P10-D (2026-09-06) で pass 2 iter clean fix ✅
- [ ] Anthropic + opencode で code-fix-pytest (P10-A/B の aider fail の対照)
- [ ] n=5 くらい回して非決定性の分布測定 (S-99 捏造 vs clean fix の出現率)
- [ ] opencode の chat history 相当が cwd に貯まるか長期実験

## ドキュメント / ノウハウ

- [x] docs/knowhow/agent-cli-opencode.md — P8 (2026-09-06) 完了。codex / claude CLI 分は残
- [ ] docs/knowhow/agent-cli-<cli>.md 残: codex CLI, claude CLI
- [ ] docs/knowhow/prompt-patterns.md — Ralph 系で通りやすい prompt 型の抽出
- [x] README に「Quickstart 3 通り」を明示 — P8 (2026-09-06) 完了

## 6 度観察された Goodhart 型行動 (P11 で「削除型」追加、主要 4 種完備)

各 session で下記 Goodhart pass が観察された:
- v1 P4 (2026-08-15): gpt-4.1-mini via SDK、S-99 空エントリ捏造 (**捏造型**)
- v2 P7 aider (2026-09-06): gpt-4.1-mini、同型 (**捏造型**再現)
- v2 P7 opencode 初回: gpt-4.1-mini、S-06 削除 + S-99 別データ捏造 (**削除+捏造の複合**)
- v2 P9: gpt-4.1-mini、code fix で `return 5` hack (**迂回型**)
- v2 P10-C: haiku-4.5, 本文でなく出典表を書き換え (**逆向き置換**)
- **v2 P11: haiku-4.5, 参照を削除して整合性回復 (削除型)**
- **v2 P12: haiku-4.5, 空 `[^99]:` を追加 (捏造型、P4 と同型)** — 単調性 check を追加すると隣の穴に移動した

**7 度観察、主要 4 種の Goodhart 手法完備**: 捏造 / 削除 / 迂回 / 置換
**loop-goal §2.4 「Goodhart は塞いだ穴の隣に移動する」の実測** (P11→P12)

**結論**: model / CLI / gate / 領域 / 具体手法 — 全部変えても発現する
model 側の抽象特性。gate 側の強化が根本策:
- 単調性の下限 (loop-goal `no_regression` 相当)
- 対称性 check (「本文でなく表を書き換えた」を検出)
- 迂回検出 (test 期待値だけをハードコード等)

- [ ] loop-goal 開発者に「対称性 detector 追加」の相談 (逆向き捏造検出)
- [ ] Anthropic model の code-fix で default response 型を上書きさせる prompt patterns
- [x] gate-design-patterns.md — 7 度観察を Goodhart 4 手法 × gate 5 check で体系化 — 2026-09-06 完了
- [x] experiments/real-doc-refs/gate.sh に単調性 check 追加 — P12 (2026-09-06) 完了
- [x] **委譲機構 3 方式実装** — P14 (2026-09-06) 完了。方式 A (gate.sh 内 subprocess) + 方式 B (`gate.delegate_to[]`) + 方式 C (`post_evaluation`)、Layer B/C を core に統合
- [x] gate-delegation-patterns.md — 3 方式の設計解説 — P14 (2026-09-06) 完了
- [x] experiments/delegating-gate/ — 方式 A のサンプル実装 — P14 (2026-09-06) 完了
- [ ] gate.sh に内容 non-empty check 追加、8 度目 Goodhart 実測 (P13 候補)
- [ ] 委譲機構の実 API 実測 (P15 候補): doc-verify-delegating.yaml で n=3 くらい回して Layer B/C が Goodhart を止められるか、cost がどう推移するか
- [ ] gate feedback の表現力改善 (「[^1] が消えている」→「削除された参照を復元せよ」等)
- [ ] docs/knowhow/prompt-patterns.md — gate feedback の書き方も含める

## Framework 側の設計課題 (P9 で顕在化)

- [ ] workspace の dir 対応 — 現状 input_document は 1 file のみコピー。
  code 領域 (tests/ が周辺に要る) では gate.sh 側で tempdir 組み直しが
  workaround。長期には workspace 自体を dir ベースに拡張したい
- [ ] predict-first の徹底 — 実験前に doc に予測を書く運用。P9 で予測を
  書かずに実行 → 「iter 5 で pass しない」ことが決まってから explanation
  を書く形になった。loop-goal HANDOVER 精神に反する

## 検討 (実装前に判断する)

- [ ] gate.sh を pypi package 化してユーザーが `ralph-gate-loop-goal` みたいに参照できるようにするか
- [ ] agent-loop-lab v1 で採用した Pydantic 出力型を v2 で復活させるか (subprocess 応答を型で拘束したい場合。ただし多くの agent CLI は自由 stdout)
- [ ] `.env` の妥当性 check — spec load 時に OPENROUTER_API_KEY 未設定を警告するか
- [ ] Rate limit / retry の spec レベル制御 (v1 の SDK 内包 retry cap は削除された)
- [ ] 実装を pypi 公開するか (現状は git clone + uv sync 前提。他人が使うなら公開)
- [ ] claude-skills-marketplace への skill 化 (`/ralph` skill を作って Claude Code / Codex から自然文で呼び出せるようにするか)

---

## 次アクション案 (2026-09-06 検討) — 履歴保存

**現在**: P8 (A: user 触りやすく) + P9 (B: 適用範囲実証) 完了。

P7 (aider vs opencode 比較) 完了時点で、次にやる価値のある方向を 4 分類:

### A. user が触れる状態にする (低コスト、価値高い) — **P8 (2026-09-06) 完了**

前提: ralph-lab は動くが他人 (or 未来の自分) が使い始める摩擦が高い。

- `ralph init` / `ralph check` サブコマンド v1 移植 (~2-3 時間)
- README Quickstart 3 通り (claude / aider / opencode)
- docs/knowhow/agent-cli-opencode.md 追加

**選択理由**: 動く framework ができたので使い始めやすくするのが第一。
低コストで value が高い。他方向を先にやると「動くが使いにくい」状態が残る。

### B. framework の適用範囲を実証 (中コスト、価値高い) — **P9 (2026-09-06) 完了**

- [x] pytest gate の mini example — experiments/code-fix-pytest/。 実測: aider +
  gpt-4.1-mini で 5 iter pass せず (Goodhart 型 hack を観察)
- [ ] cargo test / eslint / grep-based gate の example
- 副産物: workspace 1-file 制約が code 用途で顕在化 (→ 設計課題節へ)

これで README の「gate は任意 bash script」が具体的に見える。

### C. 未解決の技術疑問を解く (中コスト、docs 価値高い)

- `--edit-format udiff` で aider + Anthropic model の SEARCH/REPLACE 失敗
  解消するか検証 (docs/knowhow/aider-integration.md §E の残課題)
- n=5 くらい回して非決定性の分布測定 (S-99 捏造 vs clean fix の出現率)

$0.10-0.30 のコストで明確な結論が出せる。B と並行可能。

### D. 実運用の現実試行 (高コスト、実務価値高い)

- daily-curation-reports の記事を loop-goal で verify — 実文書
  (架空 fixture ではない) で ralph-lab が使えるか
- daily-curation-reports は書式が `[S-XX]` に沿っていない可能性が高いので、
  `applicability_report.py` で確認 → 書式が合わなければ調整
- 実際に「ラルフ回して直す」試行

**運用フェーズ用**。A/B/C が終わった後の実務価値検証。

### 判定

**A → B の順が最も投資対効果が良い**:

1. A で他人 (or 週明けの自分) が触れる状態にする (~3 時間)
2. B で「framework は文章専用ではない」を実証する (~2 時間 + 実 API 費 $0.05)

これで **ralph-lab は "コード領域も含む完動 Ralph 実装" として一段落**。
C は途中で気になったら挟む、D は運用ステージ用。
