# BACKLOG

未着手 or 中期の課題。会話が終わっても持ち越したい項目を積んでおく置き場。

書き方: 1 行 1 項目。着手予定・優先度は書かない。**やる時に判断する**。
完了したら line ごと削除 or `[x]` で checked にして数日残す。

---

## 実装 / bug

- [x] opencode CLI との aider 比較 (使い勝手 A/B) — P7 (2026-09-06) 完了
- [ ] `--edit-format udiff` / `whole` で aider + Anthropic model の SEARCH/REPLACE 失敗が解消するか調査 (docs/knowhow/aider-integration.md §E)
- [ ] `ralph init` サブコマンドの v1 移植 (agent-loop-lab の core/init.py 相当) — **P8 で着手中**
- [ ] `ralph check` サブコマンドの v1 移植 (agent-loop-lab の core/check.py 相当) — **P8 で着手中**
- [ ] Windows 対応 (`/dev/stdin` 依存の解消、`--message-file` 系の platform 抽象化)
- [ ] cost 計算機能 (OpenRouter `/generation` endpoint or agent CLI の cost 出力を parse)
- [ ] `--parallel` 実装 (multi-model の並列実行、API rate throttle 込み)
- [ ] silent failure 検出 (v1 agent-loop-lab で発見: subprocess が exit 0 で戻るが何もしていない状態) の v2 での再現確認と対策

## 実験 / 検証

- [ ] 実運用文書での動作確認 (daily-curation-reports の記事、熊本地震レポート等)
- [ ] agent CLI の網羅比較 — claude / codex / opencode / aider の 4 種で同じ goal
- [x] v1 P4 の再現 (「S-99 捏造で pass」現象が v2 でも起きるか) — P7 (2026-09-06) で再現確認済、aider/opencode で追認
- [ ] gate の複合化 — loop-goal + custom grep で複数 detector を AND
- [ ] コード領域の gate 検証 (pytest / cargo / eslint) を実 project で回す
- [ ] Anthropic model + opencode の検証 (aider の Anthropic 失敗と対照、P7 で未実施)
- [ ] n=5 くらい回して非決定性の分布測定 (S-99 捏造 vs clean fix の出現率)
- [ ] opencode の chat history 相当が cwd に貯まるか長期実験

## ドキュメント / ノウハウ

- [ ] docs/knowhow/agent-cli-<cli>.md を CLI ごとに追加 (opencode, codex, claude CLI) — **P8 で opencode 分に着手**
- [ ] docs/knowhow/prompt-patterns.md — Ralph 系で通りやすい prompt 型の抽出
- [ ] README に「Quickstart 3 通り」を明示 (claude 直、aider + OpenRouter、opencode + OpenRouter) — **P8 で着手中**

## 検討 (実装前に判断する)

- [ ] gate.sh を pypi package 化してユーザーが `ralph-gate-loop-goal` みたいに参照できるようにするか
- [ ] agent-loop-lab v1 で採用した Pydantic 出力型を v2 で復活させるか (subprocess 応答を型で拘束したい場合。ただし多くの agent CLI は自由 stdout)
- [ ] `.env` の妥当性 check — spec load 時に OPENROUTER_API_KEY 未設定を警告するか
- [ ] Rate limit / retry の spec レベル制御 (v1 の SDK 内包 retry cap は削除された)
- [ ] 実装を pypi 公開するか (現状は git clone + uv sync 前提。他人が使うなら公開)
- [ ] claude-skills-marketplace への skill 化 (`/ralph` skill を作って Claude Code / Codex から自然文で呼び出せるようにするか)

---

## 次アクション案 (2026-09-06 検討)

P7 (aider vs opencode 比較) 完了時点で、次にやる価値のある方向を 4 分類:

### A. user が触れる状態にする (低コスト、価値高い) — **選択済 (P8 で実施中)**

前提: ralph-lab は動くが他人 (or 未来の自分) が使い始める摩擦が高い。

- `ralph init` / `ralph check` サブコマンド v1 移植 (~2-3 時間)
- README Quickstart 3 通り (claude / aider / opencode)
- docs/knowhow/agent-cli-opencode.md 追加

**選択理由**: 動く framework ができたので使い始めやすくするのが第一。
低コストで value が高い。他方向を先にやると「動くが使いにくい」状態が残る。

### B. framework の適用範囲を実証 (中コスト、価値高い)

前提: 現状 example は全て文章検証 (loop-goal)。「Ralph は code にも文章にも
使える」の実測が欠けている。

- pytest gate の mini example — わざと fail する Python test を含む small
  project、aider が test を通すまで実装を fix する
- cargo test / eslint / grep-based gate の example も

これで README の「gate は任意 bash script」が具体的に見える。

**次にやるならこれ**。P8 (A) 完了後の第一候補。

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
