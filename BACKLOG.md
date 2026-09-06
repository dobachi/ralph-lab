# BACKLOG

未着手 or 中期の課題。会話が終わっても持ち越したい項目を積んでおく置き場。

書き方: 1 行 1 項目。着手予定・優先度は書かない。**やる時に判断する**。
完了したら line ごと削除 or `[x]` で checked にして数日残す。

---

## 実装 / bug

- [ ] opencode CLI との aider 比較 (使い勝手 A/B) — P7 で実施予定
- [ ] `--edit-format udiff` / `whole` で aider + Anthropic model の SEARCH/REPLACE 失敗が解消するか調査 (docs/knowhow/aider-integration.md §E)
- [ ] `ralph init` サブコマンドの v1 移植 (agent-loop-lab の core/init.py 相当)
- [ ] `ralph check` サブコマンドの v1 移植 (agent-loop-lab の core/check.py 相当)
- [ ] Windows 対応 (`/dev/stdin` 依存の解消、`--message-file` 系の platform 抽象化)
- [ ] cost 計算機能 (OpenRouter `/generation` endpoint or agent CLI の cost 出力を parse)
- [ ] `--parallel` 実装 (multi-model の並列実行、API rate throttle 込み)
- [ ] silent failure 検出 (v1 agent-loop-lab で発見: subprocess が exit 0 で戻るが何もしていない状態) の v2 での再現確認と対策

## 実験 / 検証

- [ ] 実運用文書での動作確認 (daily-curation-reports の記事、熊本地震レポート等)
- [ ] agent CLI の網羅比較 — claude / codex / opencode / aider の 4 種で同じ goal
- [ ] v1 P4 の再現 (「S-99 捏造で pass」現象が v2 でも起きるか)
- [ ] gate の複合化 — loop-goal + custom grep で複数 detector を AND
- [ ] コード領域の gate 検証 (pytest / cargo / eslint) を実 project で回す

## ドキュメント / ノウハウ

- [ ] docs/knowhow/agent-cli-<cli>.md を CLI ごとに追加 (opencode, codex, claude CLI)
- [ ] docs/knowhow/prompt-patterns.md — Ralph 系で通りやすい prompt 型の抽出
- [ ] README に「Quickstart 3 通り」を明示 (claude 直、aider + OpenRouter、opencode + OpenRouter)

## 検討 (実装前に判断する)

- [ ] gate.sh を pypi package 化してユーザーが `ralph-gate-loop-goal` みたいに参照できるようにするか
- [ ] agent-loop-lab v1 で採用した Pydantic 出力型を v2 で復活させるか (subprocess 応答を型で拘束したい場合。ただし多くの agent CLI は自由 stdout)
- [ ] `.env` の妥当性 check — spec load 時に OPENROUTER_API_KEY 未設定を警告するか
- [ ] Rate limit / retry の spec レベル制御 (v1 の SDK 内包 retry cap は削除された)
- [ ] 実装を pypi 公開するか (現状は git clone + uv sync 前提。他人が使うなら公開)
- [ ] claude-skills-marketplace への skill 化 (`/ralph` skill を作って Claude Code / Codex から自然文で呼び出せるようにするか)
