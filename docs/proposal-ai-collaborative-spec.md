# 提案: AI 協働による spec 編集の仕組み

**提案日**: 2026-09-07
**status**: 検討中 (実装前判断)
**scope**: `ralph init` 現行 (ルールベース生成) を拡張、AI と協業して spec を洗練させる仕組み

---

## 1. ユーザー提案の要約

以下の要素を組み合わせた仕組み:

1. コマンドをグローバルインストール可能にする
2. プロジェクト生成用のサブコマンドを作る
3. プロジェクト生成時に spec 以外に **AI 用の md ファイル**が生成される
4. Claude / Codex 等が指示を読みながら、ユーザーと協業で spec を編集
5. AI が考慮すべきナレッジ:
   - **最低限コンテキストに含む**
   - 足りないナレッジは何らかの手段で **取得できるようにする**
6. **spec としてふさわしい内容**を記載できるようになる

---

## 2. ユーザー提案の評価

### 良い点

- **正しい階層化**: 「ルールベースで骨組み → AI で微調整」の 2 段構えは低摩擦
- **context 限界を意識**: 「最低限 + 取得」の 2 層設計で LLM の context window を尊重
- **AI CLI agnostic (implicit)**: 「Claude / Codex など」で 特定 CLI 依存を避けようとしている
- **spec としてふさわしい**: 単に fields を埋めるだけでなく、**設計判断が入った spec** を目指す姿勢

### 気になる点 (対処が必要)

| 気になる点 | 詳細 | 対処案 |
|---|---|---|
| **CLI 非依存の指示 file 形式** | claude / codex / opencode / aider で解釈可能な universal な形式は? | `AGENT.md` convention を採用 (industry emerging) |
| **ナレッジの drift** | ralph-lab 側 docs 更新後、既存 project 内の AI 指示が古くなる | Versioning + fetch URL の併用 |
| **「取得できるようにする」の実装** | WebFetch / skill / MCP / local reference のどれ? | 現実解は URL + MCP (将来) |
| **「spec としてふさわしい」の定義** | 誰がどう判定するか | Layer C 相当の judge を init 時にも走らせる? |
| **AI が編集ミスをする** | AI が spec に矛盾を作る可能性 | `ralph check` の validation を強化して自動チェック |
| **ユーザー側の学習コスト** | 「AI と協業で spec 編集」自体の使い方 | AGENT.md 内に「ユーザーへの説明」を含める |

---

## 3. 対案 / 追加案

ユーザー提案に加えて、以下を検討する価値がある:

### 対案 A: AGENT.md 単一ファイル convention (**推奨**)

Anthropic / OpenAI が推進する emerging convention。任意 AI CLI が読める:

```
project-root/
├── spec.yaml          # spec
├── AGENT.md            # AI 用 (claude / codex / opencode / cursor 全対応)
├── PROJECT.md          # 人間用 (何を作る project か)
└── .ralph/
    └── knowledge/       # snapshot 版 knowledge (次項)
```

**Pros**: 1 file、universal
**Cons**: CLI ごとの optim は個別 patch できず

### 対案 B: 対話型 `ralph init` (LLM を init 段階でも使う)

現行 (rule-based template) と AI 協業 (post-init) の**間にもう 1 段**:

```
$ ralph new my-project
? どんな gate を作りますか?
  [1] 文書検証 (脚注書式 / citation format)
  [2] コード修正 (pytest / eslint / cargo test)
  [3] custom (bash script を書く)
> 1
? 対象文書の場所は? _
```

問答式で spec を組み立て。従来の template 選択より柔軟。

**Pros**: 初学者に優しい
**Cons**: 実装コスト大 (LLM の invocation を init に組む)

### 対案 C: Skill 化 (`ralph` skill for Claude Code)

ralph-lab を Claude Code の skill として公開。ユーザーは Claude Code 内で:
```
/ralph new my-project
```
と打つと、Claude Code の中で spec + AGENT.md が生成 + 対話編集される。

**Pros**: セットアップ最小、Claude Code user なら natural
**Cons**: Claude Code 依存、非 Claude ユーザーは使えない

### 対案 D: Template gallery + AGENT.md セット

現行 template (claude/aider/opencode) を **use case 別 template**に拡張:

```
$ ralph new my-project --template doc-verify
$ ralph new my-project --template code-fix
$ ralph new my-project --template api-testing
```

各 template は **spec + AGENT.md + PROJECT.md + .ralph/knowledge/** をセットで含む。
AGENT.md はその template 用の知識に絞る (context 削減)。

**Pros**: 実装最小 (静的 template)、AI 使わない
**Cons**: 静的なので柔軟性低い

### 対案 E: 段階的 knowledge injection (Retrieval-augmented)

AGENT.md には minimum、詳細は on-demand で取得:

```markdown
# AGENT.md

## Quick reference (常時 context)
- spec 主要 field: name, input_document, agent, prompt, gate
- 4 layer 防御: 0/A/B/C
- ...

## Deep-dive on demand
When user asks about ... fetch:
- gate design details: https://100.64.0.1:8000/knowhow/gate-design-patterns.html
- prompt patterns: https://100.64.0.1:8000/knowhow/prompt-patterns.html
- experiments logs: https://100.64.0.1:8000/experiments/

When user is in Claude Code with WebFetch tool: fetch directly.
When not: `curl -sS <url>` to get the content.
```

**Pros**: context 効率 + fresh docs
**Cons**: URL 参照は Claude Code 等の WebFetch tool 依存

---

## 4. 推奨案 (合成)

**ユーザー提案 + 対案 A + 対案 D + 対案 E** の合成:

### 4.1 コマンド設計

```bash
# Global install
pipx install ralph-lab  # 将来 pypi 公開後
# or
uv tool install --from git+https://github.com/dobachi/ralph-lab ralph-lab

# Project 生成
ralph new my-project [--template doc-verify|code-fix|custom]
```

`ralph new` は既存 `ralph init` を包含・拡張する新サブコマンド。

### 4.2 生成される project 構造

```
my-project/
├── spec.yaml                 # spec の starter
├── AGENT.md                   # AI 用 universal 指示 (~250 行)
├── PROJECT.md                 # 人間用: この project は何か
├── .ralph/
│   ├── knowledge/             # snapshot 版 (init 時の docs 抜粋)
│   │   ├── spec-schema.md
│   │   ├── prompt-patterns-quick.md
│   │   └── skill-pathology.md
│   ├── template-version.txt   # 使った template のバージョン
│   └── init.log               # 何を生成したかの trace
└── logs/                      # ralph run の JSONL 出力先
```

### 4.3 AGENT.md の構成 (推奨骨子)

```markdown
# ralph-lab project — AI 協働 spec 編集ガイド

## 目的
このファイルは Claude / Codex / opencode / cursor 等の AI CLI が読み、
ユーザーと協業で `spec.yaml` を編集するための **指示 + minimum knowledge**。

## Quick reference (必読、~50 行)
- spec 主要 field: [list]
- 4 layer 防御の概念: [1 diagram]
- 実測された Goodhart 4 種: [list]
- 推奨 retry_aggregate: fact-checker→any_pass, doc-review→all_pass

## 現在の spec の要約
(生成時に spec.yaml を要約したもの、AI が追記可)

## ユーザーとの対話ルール
1. ユーザーの意図を確認 (何を検証したい? どの CLI を使う?)
2. spec 変更は `spec.yaml` に反映、変更理由を PROJECT.md に追記
3. `ralph check spec.yaml` を実行して validation
4. 疑問点は具体的に聞く (漠然とした「良い spec ですか?」は避ける)

## Knowledge に不足を感じたら
以下から取得:
- https://100.64.0.1:8000/knowhow/gate-design-patterns.html  (gate 設計)
- https://100.64.0.1:8000/knowhow/prompt-patterns.html       (prompt 設計)
- https://100.64.0.1:8000/experiments/                       (実測ログ)
- .ralph/knowledge/*.md                                     (offline 版)

## Anti-patterns (避けるべき pattern)
- prompt に「削除禁止 + 捏造禁止 + clean fix hint」がない → 削除 over-reaction
- Layer B の retry_aggregate 未指定 → 非決定性への対策不足
- Layer C の異 provider 未検討 → Goodhart 相関エラー可能性
```

### 4.4 Knowledge 取得の 3 層

1. **AGENT.md 内 (常時 context)**: ~250 行、必須 5-10 pattern
2. **`.ralph/knowledge/*.md` (offline snapshot)**: init 時の docs 抜粋、versioned
3. **URL fetch (online、latest)**: WebFetch tool ある時 or `curl` fallback

3 層それぞれ trade-off (詳細度 ↔ 鮮度 ↔ context 消費) がある。

### 4.5 「spec としてふさわしい」の判定機構

AI が編集した spec を **`ralph check`** で自動 validation。さらに:

- **Optional**: `ralph review <spec>` サブコマンド (新規) — Layer C 相当の
  LLM judge で「この spec は要件を満たしているか」を判定。任意で run。

---

## 5. 実装の段階

**Phase 1 (最小、~1 週)**:
- `ralph new` サブコマンド (`ralph init` を包含)
- AGENT.md / PROJECT.md / .ralph/knowledge/ の template 化
- Template は 3 種 (doc-verify / code-fix / custom)
- Knowledge snapshot は現行 docs から抽出、~5 file
- **AI 対話は「AGENT.md 読ませて Claude Code で会話」の手動運用** (Phase 1 は自動化なし)

**Phase 2 (中期、~2 週)**:
- URL fetch 対応 (AGENT.md 内で https://... を明示)
- `ralph new --template <use-case>` の use-case を拡張
- `ralph check` の validation を強化 (spec の semantic 検査)

**Phase 3 (将来、条件付き)**:
- 対話型 `ralph new` (対案 B)、LLM 起動を init に組む
- `ralph review` サブコマンド (Layer C 相当の spec judge)
- Claude Code の skill 化 (対案 C)

---

## 6. 決定していないこと (User feedback 求む)

1. **配布方式**: pypi 公開する? git install で良い?
2. **AGENT.md の言語**: 日本語 / 英語 / 併記?
3. **Knowledge snapshot の版管理**: template のバージョンと ralph-lab のバージョンをどう紐付けるか
4. **Phase 1 の template**: 3 種で十分? 追加候補は?
5. **`ralph review` は初期 scope に入れるか**: LLM cost がかかるので慎重に

---

## 7. 追加リスク

- **AGENT.md 遵守率**: AI が指示に従わない可能性 (指示を無視した spec 編集を行う)
  - 対策: `ralph check` で automatic validation、AGENT.md 冒頭で「必ず check を走らせろ」明示
- **Knowledge drift**: snapshot が古くなる、URL 先も変わる
  - 対策: template-version.txt で init 時の版を記録、`ralph new --check-updates`
- **User 依存**: AI と協業できない user が置き去りに
  - 対策: template で「AI なし」でも動く starter を提供、AGENT.md はオプション

---

## 8. 参考

- [Anthropic AGENTS convention](https://www.anthropic.com/news/claude-code-plugins) (2026)
- [claude-skills-marketplace の SKILL.md convention](https://github.com/dobachi/claude-skills-marketplace)
- [ralph-lab 現行 template](https://github.com/dobachi/ralph-lab/tree/main/src/ralph_lab/templates)
