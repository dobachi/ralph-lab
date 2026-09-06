# Ralph loop 調査メモ (2026-09-06 受領)

**出所**: ユーザーが別 AI アシスタントに調査させて agent-loop-lab の positioning
見直し材料として渡してくれたもの。作成日 2026-09-06。

**agent-loop-lab との関係**:
- 本 repo は「outer loop framework を自作する」路線で P0-P5 進めた
- この調査は「先行実装 (Ralph loop 系) が既に多数ある」ことを示す
- **§7 の未解決論点** (検証関数の設計、ドリフト制御、コスト設計) が
  agent-loop-lab がまさに loop-goal と組み合わせて実装しつつある領域
- 特に §7.1 の「grounded-research / longform-discipline / verify-content /
  fact-checker が検証関数の役割を果たす」観察は、我々の loop-goal 統合方針と
  同じ結論

**注意** (受領者宛):
- 一次ソースまで裏取り済ではない。§8 の再確認リストに従って引用時は verify する
- Claude Code のスラッシュコマンドはバージョンで挙動が変わる (§6)
- ツール選定そのものは本題ではない。§7 の未解決論点が本題に近い

---

## 0. このメモの前提と引き継ぎ先への指示

### 調査の背景

依頼者は「最初に目的（ゴール）を与えると、自分で改善しながら進めていく汎用フレームワーク」を構想している。想定要件は以下:

- コード開発と、文章執筆・リサーチの**両方**に使える汎用設計
- 人間の介在をできるだけ減らす（自動化志向）
- コスト意識あり。SDK 利用も `claude -p` 経由のプログラム利用も課金対象という認識を持っている

この構想の参考として Ralph loop とその周辺を調査した。以下はその結果。

### 引き継ぎ先が注意すべきこと

1. **バージョン依存の情報が多い。** 特に Claude Code のスラッシュコマンドはバージョンで挙動が変わる。断定する前に公式ドキュメントで再確認すること（§6 参照）。
2. **本文中の「未確認」タグに注意。** 一次情報で裏が取れていない項目には印を付けてある。依頼者の用途では正確性が重要なので、そのまま事実として引用しないこと。
3. **依頼者の関心はツール選定そのものではない。** §7 の未解決論点が本題に近い。

---

## 1. Ralph loop とは

Geoffrey Huntley が 2025年7月の記事で名付けた技術。最も純粋な形では **Bash のループ**である。

```bash
while :; do
  cat PROMPT.md | your-agent-cli
done
```

同じプロンプトファイルを毎回読み込ませてコーディングエージェントを無限ループで回す。会話履歴ではなく**ファイルシステムを記憶として使う**。各イテレーションは新しいコンテキストウィンドウで始まり、状態はコードベース・TODOファイル・git履歴に残る。

### 設計思想の核

- **毎回コンテキストを捨てるのが狙い**（副作用ではない）。LLM はコンテキストが埋まるほど劣化し、モデルにもよるが 10万〜15万トークン付近から品質が目に見えて落ちる。
- 仕様書をルックアップテーブル兼フレーミングとして毎回与え直す。
- **外部の検証器**（コンパイラ・リンタ・テスト）が合格を宣言するまで回る。エージェントが自分の仕事を自分で承認して通せない点が、Reflexion 系の自己批評と決定的に違う。

### 名前の由来

シンプソンズのラルフ・ウィガム（頭をドア枠にぶつけながら「僕、役に立ってる!」と言うキャラ）に由来。愚直で粘り強いループが意外に効く、という含意。同時に "ralph" は嘔吐のスラングでもあり、自律コード生成がここまで安くなった現実に吐き気を覚えた、という第二の由来もあるとされる。

### 実運用上のポイント

- プライマリのコンテキストには極力割り当てず、サブエージェントを起こしてテスト結果の要約などの重い作業をやらせる。プライマリはスケジューラに徹する。
- `AGENT.md` がループの心臓部。ビルドと実行の手順を指示する。
- 向くタスク: 明確な「完了の定義」をテストや完了タグとしてエンコードできるバッチ作業、大規模リファクタ、バックログ処理。
- 向かないタスク: 曖昧な人間の判断に依存するもの、外部承認が必要なもの。

---

## 2. ループ設計の系譜

| 年 | 手法 | 追加したもの |
|---|---|---|
| 2022 | ReAct | 推論と行動を交互に回す形 |
| 2023 | Reflexion | 失敗後に自然言語で反省文を書いて記憶に残す層 |
| 2023 | Self-Refine | 単一モデルを生成者・批評者・改訂者として回す（学習なしで品質向上） |
| 2025 | Ralph | bash の while まで削ぎ落とし、メモリを会話からディスク上のファイルへ |
| 2026 | エージェントハーネス | 独立した評価器・毎回新規のコンテキスト・厳格な予算でループを包む |

**この並びで変わらないのは真ん中のモデル呼び出し。変わるのはその周り**——何を記憶し、何が「十分」を判定し、失敗時に何が起きるか。ここがそのまま設計の勘所になる。

### パターンの使い分け

- **ReAct** — ツールやAPIとリアルタイムにやりとりする動的タスク
- **Reflexion** — 反復改善
- **Plan-and-Execute** — 先に全体戦略を立ててから各ステップを実行する長い多段ワークフロー
- **Tree of Thoughts** — 複数解を並列探索する複雑問題

実運用では ReAct + Reflexion、Plan-and-Execute + ToT のように組み合わせるのが普通。

### 歴史的先行例とその失敗

AutoGPT / BabyAGI / GPT-Engineer / AgentGPT（2023）。サブゴール分解と自己批評をLLMに担わせた初期のPoC群。BabyAGI はタスク生成・優先順位付け・実行の3チェーン構成。

定番の失敗モード（**Ralph が外部検証と予算を重視する理由がここにある**）:

- 目標の客観的検証がないため無限ループに陥る（AutoGPT の 2023年の事例が典型）
- goal drift（目標のすり替わり）
- トークンコスト爆発

### マルチエージェント側

MetaGPT、ChatDev、ALMAS など、PM・アーキテクト・コーダー・テスターと役割を割り当ててソフトウェアチームを模す枠組み。同系統の論文が Ralph 系ループに欠けるものとして挙げているのは:

1. 人間とAIのチケットを同一に扱うチケット管理層
2. 品質劣化時にループを止めるドリフト制御の一時停止ゲート
3. 網羅性を担保する三層の戦略モデル

**これは依頼者の「文章・リサーチに広げるときの検証関数」の議論とほぼ同じ問題意識。引き継ぎ先はここを深掘りする価値がある。**

### 語彙の整理

- **loop engineering** — 個々のループの設計
- **harness engineering** — そのループを複数セッションにわたり信頼できるものにする制約・ツール・フィードバック基盤の構築

汎用設計を狙うなら後者の語彙で文献を追うと当たりが良い。

---

## 3. ベンダー公式の実装

### 3.1 Claude Code のスラッシュコマンド

公式ドキュメントに、毎ターン止まる従来の挙動を4つの自律モードに分けるコマンドが束ねられた。

| コマンド | モード | 備考 |
|---|---|---|
| `/goal` | 条件駆動 | 判定に高速な評価モデル（既定 Haiku）が毎ターン走る |
| `/loop` | 間隔駆動 | v2.1.72以降、1分〜1時間 |
| `/batch` | 並列 | 5〜30本のPR、git worktree 必須 |
| `/background` | 分離セッション | v2.1.139以降、`claude agents` ビューで進捗確認 |

**`/goal` の使い方の勘所** — 成功条件をエージェントが実際に検査できる**状態**として書く。

- 悪い例: 「非推奨APIの呼び出しを消してみて」（努力の記述）
- 良い例: 「`/src` に `fetch()` の呼び出しが残っていない」（状態の記述、grepで確認可能）

検証可能な条件のカテゴリ: コマンドの終了コード（最も信頼できる）、ファイルの有無や中身、コード構造、APIレスポンス。

条件判定の評価トークンはメインの消費に比べれば無視できる、と公式は書いている。一方 `/batch` は同時に5〜30本立ち上がるためトークン消費は当然その分増える。

**`/loop` の例**

```
/goal All integration tests pass and no linting errors
/loop every 10m
/loop until: tests pass
```

### 3.2 ralph-wiggum プラグイン（Anthropic 公式）

Claude Code のセッション**内部**で Ralph を再現する。Stop フックで終了を横取りして、同じプロンプトを再注入する仕組み。

```
/plugin marketplace add anthropics/claude-code
/plugin install ralph-wiggum@claude-plugins-official

/ralph-loop "Fix all ESLint errors in src/. Output <promise>LINT_CLEAN</promise> when npm run lint passes." \
  --max-iterations 10 \
  --completion-promise "LINT_CLEAN"
```

`/cancel-ralph` で中断。必ず git 管理下で走らせること（各イテレーションが履歴に残り、壊れたら戻せる）。

**重要な批判（Matt Pocock）** — 本来の Ralph は bash がエージェントを制御するのに対し、このプラグインは逆にエージェントがループを制御するため、コンテキスト腐敗を招く。プラグインはセッション内ループなので「毎回まっさらなコンテキスト」という Ralph の核心が厳密には保たれない。忠実さを取るなら外側の bash ループのほうが良い。

### 3.3 Agent Teams（Claude Code、実験的）

共有タスクリストとエージェント間メッセージングを持つ複数の独立セッションを、チームリーダーが調整する仕組み。単一セッション内で動いて親にだけ報告する subagents と違い、各メンバーが自分のコンテキストウィンドウを持ち、どのメンバーとも直接やりとりできる。

有効化: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

### 3.4 他社

- **OpenAI Codex `/goal`** — Ralph パターンをそのまま製品化。14時間連続でデバイスドライバのプロジェクトを走らせた事例あり。実践者からは、`/goal` の後に手書きしたプロンプトはたいてい不十分で、プロジェクトの文脈を持つ別のAIに `/goal` 用プロンプトを生成させる**メタプロンプティング**のほうが良いという指摘。長時間実行は高額なので事前に支出上限を設定すること。
- **Cursor `/orchestrate`** — 再帰的にエージェントを生成する形。（未確認: 詳細未調査）
- **Gas Town**（Steve Yegge） — 複数エージェントを並列開発向けに束ねる「エージェントの Kubernetes」。タスクを極小粒度に定義する MEOW が核。ただし「Ralph ループに手順を足しただけ」「個人開発者なら Ralph ループで十分」という批判があり、重いセッションは時間あたり $100〜200 と言われる。

---

## 4. ベンダー非依存のツール

いずれも「エージェントCLIをフラグで差し替えられるループドライバ」という形をしている。

### Open Ralph Wiggum（Th0rgal）

MIT、Bun + TypeScript。`--agent` で Claude Code / Codex / Copilot CLI / Cursor Agent / Qwen Code / OpenCode を切り替え。既定は OpenCode。

```
ralph "Build a REST API" --agent claude-code --max-iterations 10
ralph "Refactor the auth module" --agent copilot --max-iterations 10
```

### syuya2036/ralph-loop

bash 一枚。エージェントのCLIコマンドを第1引数、最大反復回数を第2引数（既定10）。`prd.json` にユーザーストーリーを書くと、エージェントが1件選んで実装→テスト→コミット→進捗更新を繰り返す。

```
./ralph-loop/ralph.sh "claude --dangerously-skip-permissions" 20
./ralph-loop/ralph.sh "codex exec --full-auto" 20
./ralph-loop/ralph.sh "gemini --yolo" 20
```

各CLIの「確認をスキップするフラグ」が違うだけでループ本体は共通。Ollama / Qwen などローカルモデルも想定している。**設計が読める最小実装なので、自作の下敷きにするならこれが最適。**

### PageAI-Pro/ralph-loop

claude / codex / copilot / cursor / gemini / opencode 対応。`--` の後ろでエージェント固有オプションを渡せる。

```
./ralph.sh --agent codex -- --model gpt-5.3-codex
./ralph.sh --agent gemini -- --model pro
```

特徴は**サンドボックス統合**。エージェント名がサンドボックス名の一部になるため、切り替えるとそのエージェント専用の環境が作られる。README が明言するとおり、ループが成立するにはAIが自分の実装を検証できる手段が必要で、最低限 E2E とユニットのテストフレームワーク（例: Playwright + Vitest）が前提。

### madhavajay/ralph

Rust、`cargo install ralph`。Codex / Claude / Pi / Gemini を統一インターフェースで包む。

```
ralph -H claude "implement the feature"
ralph -n 5 TASK.md
ralph -n inf TASK.md
ralph install codex   # エージェント自体のインストールも面倒を見る
```

### Ralph Orchestrator + ralph-adapters

Claude / Gemini / Codex / Pi / Roo / Amp / 任意のカスタムコマンドのアダプタを提供。設定で `agent: auto` にすると PATH から利用可能なバックエンドを自動検出。Claude については PTY 実行モードがあり、色やスピナーといったターミナルUIを保ったままループを回せる。

`ralph plan` で requirements / design / implementation-plan を作り `ralph run` で実装する preset 付き CLI。

### randomcodespace の ralph-loop skill

標準ライブラリのみの Python、ネットワーク不要、他スキルへの依存なし。specs / tickets / gotchas / plan という構造化されたファイル状態のワークスペースに対して任意のコーディングCLI（Claude Code, Codex, OpenCode, Gemini, Aider, Amp, Copilot…）を回す。**停止条件とLLM呼び出し最小化がデフォルト**。依存の少なさとこの既定は、コスト懸念があるなら相性が良い。

### frankbria/ralph-claude-code

まだ Claude 寄りだが、任意のヘッドレスCLI（Codex, Gemini, OpenCode, Droid, Kilocode, Copilot）が駆動できるようマルチプロバイダ抽象化を整備中。実装として面白いのは**終了判定の二重条件**で、完了指標と明示的な `EXIT_SIGNAL` の両方が揃わないと抜けない。レート制限や5時間APIリミットの検出・自動待機も入っている。

### その他

- **PraisonAI** — Ralph を概念として実装。毎回クリーンなコンテキスト、ファイルとGit履歴による状態永続化、明示マーカーによる完了宣言、そして**反復して進捗しないサイクルを検出する doom loop detection** を原則に据える。`praisonai loop "..." -n 5` のように反復上限を渡す。
- **autoresearch**（uditgoenka） — Karpathy の autoresearch に着想。goal-metric-loop パターンで、自動テストと Git ベースのロールバックにより、コード・コンテンツ・測定可能なドメインを反復改善する。**「コンテンツ」を明示的に対象に含めている点が依頼者の用途に近い。要調査。**
- **LangChain / LangGraph** — AutoGPT のような完成品を直接デプロイするより、ReAct や Plan-and-Execute のパターンを自前の LangGraph 実装に組み込むのが実務の主流とされる。

### 選定軸

| 要件 | 推奨 |
|---|---|
| 最小で読める・自作の下敷き | syuya2036（bash）、randomcodespace（Python標準ライブラリのみ） |
| サンドボックス分離が要る | PageAI-Pro |
| 設定ファイルと自動検出、長期運用 | Ralph Orchestrator |
| バイナリ配布で手軽に | madhavajay/ralph |
| ローカルモデル併用 | syuya2036 |

---

## 5. 仕様駆動（入力側を固める）系

Kiro、TaskMaster、BMAD、GSD、Spec Kit など。「仕様が曖昧ならループを何回回しても無駄（garbage in, garbage out）」という前提で、PRD / 仕様の質を担保する方向。**Spec Kit が構造を、Ralph が永続性を与える**という組み合わせ方がよく語られる。

Anthropic 推奨の計画フォーマット: 各タスクを pass/fail で判定できる形にする。カテゴリ・説明・手順・`passes` フィールドを持つ JSON。

---

## 6. 始め方（推奨順序）

1. `CLAUDE.md` / `AGENT.md` に、ビルド手順・実行方法・プロジェクトの規約を書く。エージェントは実行間で何も覚えていないので、書いていない規約は毎回推測される（cold start 問題）。
2. PRD / 計画を先に作る。練り切れていないアイデアで Ralph を回すのは時間と金の無駄。各タスクを pass/fail 判定可能な形に構造化する。
3. 小さく `/goal` から。**イテレーション上限**と**連続失敗回数の上限**（`max_consecutive_failures`）を必ず設定。
4. 慣れてから `/loop` の定期実行、`/batch` の並列化へ。
5. 最初のサイクルは必ず監視する。放置する前にコスト管理を設定する。

### 一次情報の確認先

- Claude Code 公式: https://docs.claude.com/en/docs/claude-code/overview
- Claude Code ドキュメントマップ: https://docs.anthropic.com/en/docs/claude-code/claude_code_docs_map.md
- ralph-wiggum プラグイン: https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum
- 公式プラグインディレクトリ: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/ralph-loop
- syuya2036/ralph-loop: https://github.com/syuya2036/ralph-loop
- Th0rgal/open-ralph-wiggum: https://github.com/Th0rgal/open-ralph-wiggum
- PageAI-Pro/ralph-loop: https://github.com/PageAI-Pro/ralph-loop
- frankbria/ralph-claude-code: https://github.com/frankbria/ralph-claude-code
- madhavajay/ralph: https://docs.rs/ralph

---

## 7. 未解決論点（引き継ぎ先への主要な宿題）

依頼者の構想（コードと文章・リサーチの両方に使える自己改善フレームワーク）に照らすと、既存の Ralph 系ツールには次のギャップがある。

### 7.1 検証関数の設計【最重要】

Ralph はコード側の完成度は高いが、**完了判定をテストに依存している**のが最大の制約。文章・リサーチ用途に広げるには、テストに相当する決定的な検証関数が要る。候補:

- ファクトチェックの合格
- 査読ルーブリックのスコア閾値
- drift scan のような決定的スキャン（用語の一貫性、主旨のすり替わり検出）
- Source Ledger のような、全主張と出典の対応の網羅性チェック

`/goal` の「grep で確認できる状態として書く」という規律がそのまま効く。「良い記事にする」ではなく「すべての主張に Source Ledger の行が対応している」「drift_scan がゼロを返す」と書けば、コードと同じループに載る。

**依頼者は既に grounded-research、longform-discipline、verify-content、fact-checker といったスキルを保有しており、これらがまさに検証関数の役割を果たす形になっている。`/goal` の完了条件をそれらの出力に紐づけるのが最も手っ取り早い接続点。**

### 7.2 ドリフト制御

品質劣化時にループを止めるゲート。PraisonAI の doom loop detection、frankbria の二重条件終了判定が参考実装。長文タスクでは goal drift が特に起きやすい。

### 7.3 コスト設計

依頼者はSDK・`claude -p` いずれも課金対象と認識している。反復回数がそのままコストなので:

- イテレーション上限と停止条件を**先に**決める
- LLM呼び出し最小化を既定とする実装（randomcodespace）を参考にする
- ローカルモデルで回して仕上げだけ商用APIに投げる段階構成も検討可能

### 7.4 未調査の項目

- Cursor `/orchestrate` の詳細
- autoresearch（uditgoenka）の goal-metric-loop パターン——コンテンツ領域を明示的に対象にしており、依頼者の用途に最も近い可能性がある
- MetaGPT / ChatDev 系が挙げる「三層の戦略モデル」の具体的内容
- ローカルモデルでの実用性（品質がループ回数を増やしてコストを相殺しない範囲に収まるか）

---

## 8. 情報の確度について

本メモは web 検索ベースであり、一次ソースまで当たっていない記述を含む。特に以下は再確認が必要:

- Claude Code のコマンドとバージョン番号（急速に変化する）
- 各OSSツールの現在の対応エージェント一覧（更新が速い）
- Gas Town のコスト水準（伝聞）
- Codex `/goal` の14時間事例（二次情報）

数値やバージョンをそのまま引用せず、公式ドキュメント・リポジトリで裏を取ること。
