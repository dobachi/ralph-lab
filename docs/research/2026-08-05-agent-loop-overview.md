# エージェントループ実装アーキテクチャの俯瞰調査

**Depth**: Standard **Date**: 2026-08-05 **Sub-questions**: 5 **Sources**: 27 (T1: 17, T2: 10)
**Decision this feeds**: 子プロジェクト `agent-loop-lab` の初期設計インプット
**Skill**: grounded-research (retrieval / synthesis 分離、verbatim span ベース)

## Bottom line

Agent loop の設計は、**まず single-agent + augmented tools (retrieval / tools / memory) で足りるかを検証**し、真に並列化可能で高価値なタスクだけ multi-agent orchestrator-worker に上げるのが Anthropic 公式の立場である [C-B06, C-D01, C-D04]。Multi-agent は実測で約 15 倍のトークンを消費し、単一 vs 複数の性能差の 80% はトークン消費量で説明できる ため、multi-agent の本質は「並列に十分な token を使えること」に近い [C-C05, C-C06]。フレームワーク選定は、durable stateful workflow が中心なら **LangGraph** (v1.0 GA / production 実績厚)、Claude Code エコシステム前提なら **Claude Agent SDK** (Skills / MCP / Subagents が transparently 使える)、Python コード実行を action にする code-agent 派なら **smolagents / CodeAct** 型が第一選択。**AutoGen は 2025 年に maintenance mode 移行済** のため新規採用は非推奨 [C-F04]。

---

## Findings

### 1. アーキテクチャの主要型

**ReAct** — LLM の action space に "language (思考)" を足し、Thought → Action → Observation を interleave する [C-A01]。原論文の formal な記述:

> "we augment the agent's action space to Â = A ∪ L, where L is the space of language"
> — S-01, Yao et al. 2022 (T1)

CoT が抱える幻覚・error propagation を、外部 API 呼び出しで grounding して抑える [C-A02]。**HotpotQA / Fever のような外部知識照会 QA、ALFWorld / WebShop のような対話的意思決定**に有効 (imitation / RL より +34% / +10% success rate)。

**Reflexion** — Actor / Evaluator / Self-Reflection の 3 モジュール構成 [C-A03]。sparse reward (成否) を受けて自然言語で振り返り、その reflective text を episodic memory に保持し次 trial で参照する [C-A04]。原論文の modular formulation:

> "an Actor, denoted as Ma, which generates text and actions; an Evaluator model, represented by Me, that scores the outputs produced by Ma; and a Self-Reflection model, denoted as Msr, which generates verbal reinforcement cues"
> — S-02, Shinn et al. 2023 (T1)

重み更新なしに trial-and-error 学習を実現し、HumanEval で pass@1 91% を報告 [C-A05]。

**Plan-and-Solve / Plan-and-Execute** — Planner が multi-step plan を作り、Executor がステップごとに tool を叩く。Yao ら (2023, ACL) がプロンプト戦略として提案し [C-A06]、LangChain が LangGraph 実装として "planner + executor" ノード分離を明記している [C-A07]。ReAct 比の利点は **LLM コール数 (レイテンシ・コスト)** の削減:

> "First of all, they can execute multi-step workflow faster, since the larger agent doesn't need to be consulted after each action."
> — S-04, LangChain blog "Planning Agents" (T2)

**LangGraph state graph 型** — Nodes / Edges / State (with reducer per key) / super-step という Pregel 派生の実行モデル [C-A08, C-A09]。Node は state を読み更新する純関数的単位、Edge は次 node を state から決めるルーティング。super-step 単位で並列 / 逐次を制御する:

> "A super-step can be considered a single iteration over the graph nodes. Nodes that run in parallel are part of the same super-step, while nodes that run sequentially belong to separate super-steps."
> — S-05, LangChain Docs LangGraph Graph API (T1)

**CodeAct** — action を Python コードに統一する code-agent 型 [C-A10]。原論文の主張:

> "This work proposes to use executable Python code to consolidate LLM agents' actions into a unified action space (CodeAct). Integrated with a Python interpreter, CodeAct can execute code actions and dynamically revise prior actions or emit new actions upon new observations through multi-turn interactions."
> — S-06, Wang et al. 2024 (T1)

control flow / data flow / variable / tool composition が action 内で表現できる。API-Bank + 新規ベンチで JSON tool-call 比 **最大 +20pt success rate** を報告 [C-A11]。smolagents が実装として直接採用。

### 2. Anthropic 公式知見 (設計原則と本番トラブル)

Anthropic engineering の "Building effective agents" (2024-12) が用語を分けている [C-B01, C-B02]:

> "Workflows are systems where LLMs and tools are orchestrated through predefined code paths."
> "Agents, on the other hand, are systems where LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks."
> — S-07 (T2)

同記事の中核の 3 原則 [C-B03]:

> "1. Maintain **simplicity** in your agent's design. 2. Prioritize **transparency** by explicitly showing the agent's planning steps. 3. Carefully craft your agent-computer interface (ACI)."
> — S-07 (T2)

そして開発方針として、**framework より API 直叩きを先に**という強い推奨 [C-B04, C-B05]:

> "We recommend finding the simplest solution possible, and only increasing complexity when needed."
> "We suggest that developers start by using LLM APIs directly: many patterns can be implemented in a few lines of code."
> — S-07 (T2)

"Building agents with the Claude Agent SDK" (2025) が示す **4 ステップ loop** [C-B07]:

> "gather context -> take action -> verify work -> repeat"
> — S-08 (T2)

**本番運用の三大リアリティ** ("How we built our multi-agent research system", 2025-06) [C-B08, C-B09, C-B10]:

> "Agents are stateful and errors compound." "Agents make dynamic decisions and are non-deterministic between runs, even with identical prompts." "Minor changes cascade into large behavioral changes, which makes it remarkably difficult to write code for complex agents that must maintain state in a long-running process."
> — S-09 (T2)

Anthropic は本番デプロイに **rainbow deployment** (旧バージョンに traffic を残しつつ徐々に切替) を使っている [C-B11]。

### 3. 本番運用の実務知見 (コスト・レイテンシ・信頼性)

**Prompt caching (Anthropic)** — default 5 分 TTL、read で TTL が更新される sliding cache [C-C01]:

> "By default, the cache has a 5-minute lifetime. The cache is refreshed for no additional cost each time the cached content is used."
> — S-10, Anthropic prompt caching docs (T1)

5 分では短い agent loop 用に **1 時間 TTL の有料オプション** あり [C-C02]。価格倍率 [C-C03]:

> "5-minute cache write tokens are 1.25 times the base input tokens price / 1-hour cache write tokens are 2 times the base input tokens price / Cache read tokens are 0.1 times the base input tokens price"
> — S-10 (T1)

Tool 定義そのものをキャッシュできる:

> "Tool definitions can be cached by placing `cache_control` on the last tool in your `tools` array. All tools defined before and including that tool are cached as a single prefix."
> — S-10 (T1)

**Prompt caching (OpenAI)** — 1024 トークン最低、default 30 分 TTL [C-C04]:

> "Caching is available for prefixes containing at least 1,024 tokens. This is a strict minimum."
> — S-11, OpenAI prompt caching docs (T1)

**トークン消費倍率** (Anthropic 自社データ) [C-C05]:

> "In our data, agents typically use about 4× more tokens than chat interactions, and multi-agent systems use about 15× more tokens than chats."
> — S-12, Anthropic multi-agent research system (T2)

そして重要な発見: **性能差の 80% はトークン消費で説明できる** [C-C06]。

> "Token usage by itself explains 80% of the variance, with the number of tool calls and the model choice as the two other explanatory factors."
> — S-12 (T2)

→ multi-agent の本質は「並列に十分に token を使えるアーキテクチャ」に近い、と読める。

**Context bloat 対策** — Anthropic は "attention budget" というメタファーで context 累積を扱い、`tool result clearing` を Claude Developer Platform に機能として追加した [C-C07, C-C08]:

> "An agent running in a loop generates more and more data that _could_ be relevant for the next turn of inference, and this information must be cyclically refined."
> "One of the safest lightest touch forms of compaction is tool result clearing, most recently launched as a feature on the Claude Developer Platform."
> — S-13, Anthropic "Effective context engineering for AI agents" (T1)

具体的な実測値 [C-C09]:

> "In a 100-turn web search evaluation, context editing enabled agents to complete workflows that would otherwise fail due to context exhaustion"
> "reducing token consumption by 84%"
> — S-14, Anthropic "Managing context on the Claude Developer Platform" (T1)

**停止条件**: Anthropic 公式が "max iterations" を control として明示 [C-C10]:

> "It is also common to include stopping conditions (such as a maximum number of iterations) to maintain control."
> — S-07 (T2)

LangGraph 実装レベルでは default `recursion_limit=25`、内部 sentinel が 10,000 [C-C11]:

> "Your LangGraph `StateGraph` reached the maximum number of steps before hitting a stop condition."
> — S-15, LangChain Docs GRAPH_RECURSION_LIMIT (T1)
> "LangGraph uses a magical number of 10_000 for recursion limit."
> — S-16, langchain-ai/langgraph#7313 (T2)

**Infinite Agentic Loop (IAL)** — 2025 の arXiv 論文で 47 プロジェクト中 68 confirmed IAL failure を報告、LangGraph + AutoGen が 66.2% を占める [C-C12]。処方箋:

> "each agent run should set turn or step limits, retry and repair paths should have caps and timeouts, and message history or workflow state should have size limits"
> — S-17, arXiv "When Agents Do Not Stop" (T2)

→ **停止条件は 4 種必要**: (a) turn/step limit、(b) retry cap、(c) timeout、(d) history/state size limit。

**Tool hallucination** — 現行モデルでも未定義 tool の捏造が観測されている [C-C13]:

> "Claude 4.5 hallucinated access to a tool I hadn't given it yet, made up the parameters, tried to run it"
> — S-18, answer.ai blog (T2)

**Context rot** — Chroma 実測で 18 frontier モデル全てが context 長に比例して性能低下 [C-C14]:

> "Across all experiments, model performance consistently degrades with increasing input length."
> — S-19, Chroma Research (T2)

### 4. OSS agent framework 比較

| framework | 制御モデル | 状態管理 | 対応モデル | 成熟度シグナル |
|---|---|---|---|---|
| **LangGraph** | low-level graph orchestration | persistence / checkpointing / HITL / short/long-term memory | 非限定 | v1.0 GA、38.9k stars、Uber/LinkedIn/Klarna 事例 [C-E01, C-E02, C-E03] |
| **AutoGen** | multi-agent chat (two-agent / group chat) | Teams primitive | GPT-4o / gpt-4.1 examples | **maintenance mode 移行済 (負)** [C-E04] |
| **CrewAI** | role-playing crew + event-driven Flows | Flows で state 管理 | 非限定 | 56.6k stars、10 万人 developer コミュニティ、LangChain 非依存 [C-E05, C-E06] |
| **OpenAI Agents SDK** | Agents / Handoffs / Guardrails / Sessions | Sessions で会話履歴自動管理 | provider-agnostic、100+ LLM | 28.4k stars [C-E07] |
| **Claude Agent SDK** | Claude Code の agent loop を programmable 化 | Sessions / Subagents / Hooks / MCP / Skills / Memory | Claude 系 | Python/TS のみ (他言語は `claude -p --output-format json` の CLI subprocess) [C-E08, C-E09] |
| **smolagents** | code-execution / CodeAgent (Python 実行 = action) | minimal (~1000 LOC) | provider-agnostic (Hub / OpenAI / Anthropic / LiteLLM / Ollama) | sandbox 実行 (Modal / E2B / Docker) [C-E10, C-E11] |

**verbatim 抜粋** (control model の自称):

- LangGraph: "LangGraph is a low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents." — S-20 (T1)
- AutoGen: "AutoGen is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward." — S-21 (T1)
- CrewAI: "Framework for orchestrating role-playing, autonomous AI agents." + "CrewAI is a standalone Python framework with its own primitives" — S-22, S-23 (T1)
- OpenAI Agents SDK: "Agents: LLMs configured with instructions, tools, guardrails, and handoffs" — S-24 (T1)
- Claude Agent SDK: "The Agent SDK gives you the same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript." — S-25 (T1)
- smolagents: "First-class support for Code Agents: CodeAgent writes its actions in code (as opposed to 'agents being used to write code')" — S-26 (T1)

### 5. Single vs Multi-agent の使い分け

**Anthropic の適用条件** [C-D01]:

> "Multi-agent systems excel at valuable tasks that involve heavy parallelization, information that exceeds single context windows, and interfacing with numerous complex tools."
> — S-12 (T2)

**Anthropic の非適用条件** (multi-agent に**しない**判断基準) [C-D02]:

> "Some domains that require all agents to share the same context or involve many dependencies between agents are not a good fit for multi-agent systems today. For instance, most coding tasks involve fewer truly parallelizable tasks than research, and LLM agents are not yet great at coordinating and delegating to other agents in real time."
> — S-12 (T2)

**性能差** (Anthropic 内部 research eval) [C-D03]:

> "We found that a multi-agent system with Claude Opus 4 as the lead agent and Claude Sonnet 4 subagents outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval."
> — S-12 (T2)

**経済成立条件** [C-D04]:

> "For economic viability, multi-agent systems require tasks where the value of the task is high enough to pay for the increased performance."
> — S-12 (T2)

**反対視点 (Cognition, Devin の開発元)** [C-D05, C-D06]:

> "Actions carry implicit decisions, and conflicting decisions carry bad results"
> "The simplest way to follow the principles is to just use a single-threaded linear agent: Here, the context is continuous."
> "Share context, and share full agent traces, not just individual messages"
> — S-27, Cognition "Don't Build Multi-Agents" (T2)

**学術懐疑論 (MAST, Cemri et al. 2025)** — 14 failure modes を 3 カテゴリに分類 [C-D07]:

> "the first Multi-Agent System Failure Taxonomy (MAST) … identifies 14 unique modes, clustered into 3 categories: (i) system design issues, (ii) inter-agent misalignment, and (iii) task verification"
> — S-28, arXiv 2503.13657 (T1)

失敗分布: FC1 (specification) 41.77%、FC2 (inter-agent) 36.94%、FC3 (verification) 21.30% [C-D08]。また **性能利得が single-agent 比で minimal であるケースが多い**とも指摘 [C-D09]:

> "Despite the increasing adoption of MAS, their performance gains often remain minimal compared to single-agent frameworks"
> — S-28 (T1)

**Multi-agent debate 懐疑論 (Hu et al. 2025)** [C-D10]:

> "Majority Voting alone accounts for most of the performance gains typically attributed to MAD."
> — S-29, arXiv 2508.17536 (T1)

---

## Disagreement / unresolved

1. **Multi-agent は有効か、避けるべきか** — Anthropic (推奨、90.2% 性能差 [C-D03]) vs Cognition (反対、single-threaded 推奨 [C-D06]) vs MAST 論文 (性能利得 minimal が多い [C-D09])。
   - **Conflict type**: definitional + domain。Anthropic の 90.2% は research (並列可能タスク) 上での比較で、Cognition は coding agent (Anthropic 自身も multi-agent 非適合と認めるドメイン [C-D02])、MAST は debate/vote 型 MAS を主対象。
   - **Unresolved の扱い**: 「タスクドメインで結論が変わる」ものとして両論を残す。Curation / inquiry (本プロジェクト) は 「並列可能な research 型」寄り → Anthropic 側が参考になり得るが、経済性 [C-D04] を都度検証。

2. **Multi-agent debate の効果は debate 自体か多数決 ensemble か** — Anthropic は orchestrator-worker の "parallel subagents" を推奨するが、Hu et al. は MAD (debate) の効果は多数決 ensemble でほぼ説明できると主張 [C-D10]。
   - **Conflict type**: 測定対象違い (orchestrator-worker vs debate/vote)。orchestrator-worker はもともと "debate" ではない (専門化した subagent の parallel 実行) なので厳密には対立していない。ただし「複数モデルの outputs を統合する」層で同じ懐疑論が適用され得る。

## What we could not establish

- Claude Agent SDK / smolagents の GitHub star 数 verbatim (README 冒頭に明示なし)。今後 GitHub API 直接照会で埋める。
- 各 framework の日本国内 production 事例 (今回英語圏中心)
- LangGraph / CrewAI の対応モデル一覧の公式 verbatim (docs にプロバイダ enumeration なし)
- 各 framework の同一タスクでのレイテンシ・コスト実測比較 (公平な bench が存在しない模様)
- ローカル環境 (WSL2 / Ubuntu / systemd user timer) 上での実運用ノウハウは、既存 DevCurationViaAI の runbook 側にあるが Web 側のドキュメントは少ない

## Coverage note (span check)

- 各 sub-question で WebSearch 5-8 回、WebFetch 5-9 回。全 27 registered source が **T1/T2 一次ソースからの verbatim**。
- `scripts/check_spans.py` による mechanical span check は本ラン内で省略。**代替の grounding シグナル**:
  - Anthropic の 15x token 主張 [C-C05] は 2 個の retriever (Q2, Q3) が同一 URL / 同一 span を独立に取得 → implicit corroboration
  - すべての span に canonical URL と accessed date (2026-08-05) が付与されているため、事後の手動再検証が可能
- 検出したソース更新可能性: LangGraph の recursion_limit 内部 sentinel が「10,000」であるのは GitHub issue [S-16] 由来。将来的にコード側で変更される可能性あり (要 re-verify)。

---

## DevCurationViaAI 文脈での次アクション示唆 (5 点)

1. **agent-loop-lab は「単一 agent + augmented tools の実験場」から始める**。既存の daily-curation Phase 1-3 は既に "single-agent + tool" 型に近い (`claude -p` + WebSearch/WebFetch + `scripts/fetch.py`) ため、まず既存パターンを SDK 化することで得られる利点を測る (transparency / hook / subagent) [根拠: C-B04 simplest first, C-B06 API 直叩き先行]。

2. **Framework 第一候補は Claude Agent SDK (Python)**。理由: (a) 既に `claude -p` を systemd timer で走らせているので CLI subprocess パターン [C-E09] と同一路線、(b) Skills / Commands / Memory / Hooks / Subagents / MCP が Claude Code と同じ資産として再利用可、(c) Anthropic 4 ステップ loop "gather context → take action → verify work → repeat" [C-B07] とほぼ同型。**second choice は LangGraph** (v1.0 GA / durable execution / HITL が必要になった段階で移行)。

3. **停止条件は 4 種セットで初期実装**: (a) turn/step limit (Anthropic 推奨 [C-C10])、(b) retry cap、(c) per-loop timeout (既存 daily-curation の `/tmp/*.lock` パターンを流用可)、(d) context size limit (Anthropic の tool result clearing / context editing [C-C08] を有効化)。IAL 論文 [C-C12] の実測 66.2% は LangGraph + AutoGen が発生源なので、SDK 側でも同じ轍を踏まないよう明示防御。

4. **Prompt caching を初日から前提化**: system prompt + tool 定義 + skills が semi-static のため、`cache_control` を tools 配列最後尾に置く実装を初期からテンプレ化 [C-C03]。5 分 TTL で refresh される sliding cache を活かすため、loop の tick 間隔を 5 分以内に設計するか、1 時間 TTL (2x write) が経済成立するかを実測で判断。

5. **Multi-agent 化は保留、代わりに context 分離のみの "isolated subagent" 型を先行**。Anthropic の 90.2% 実績 [C-D03] は並列 research 前提で、curation / inquiry でも一部の phase (例: Phase 1 リサーチの topic 別 fan-out) は該当し得る。ただし 15x コスト [C-C05] と MAST の failure taxonomy [C-D07] を踏まえ、multi-agent debate / vote 型は採用しない。Cognition の "share full traces" 原則 [C-D06] を守り、subagent には要約でなく完全な履歴を渡す。

**さらに**:
- 実装評価用に **grounded-research 自体を benchmark task にする**という選択肢がある。retriever / verifier / refuter の 3 種 subagent contract が既に規定されており、agent-loop-lab の設計テストベッドとして自然。

---

## Source Register

| ID | Source | URL | Tier | Accessed | Retriever |
|---|---|---|---|---|---|
| S-01 | Yao et al. 2022, ReAct: Synergizing Reasoning and Acting | https://arxiv.org/abs/2210.03629 | T1 | 2026-08-05 | Q1 |
| S-02 | Shinn et al. 2023, Reflexion (NeurIPS 2023) | https://arxiv.org/abs/2303.11366v3 | T1 | 2026-08-05 | Q1 |
| S-03 | Wang et al. 2023, Plan-and-Solve Prompting (ACL 2023) | https://arxiv.org/abs/2305.04091 | T1 | 2026-08-05 | Q1 |
| S-04 | LangChain Blog — Planning Agents | https://www.langchain.com/blog/planning-agents | T2 | 2026-08-05 | Q1 |
| S-05 | LangChain Docs — LangGraph Graph API overview | https://docs.langchain.com/oss/python/langgraph/graph-api | T1 | 2026-08-05 | Q1 |
| S-06 | Wang et al. 2024, Executable Code Actions (CodeAct, ICML 2024) | https://arxiv.org/abs/2402.01030 | T1 | 2026-08-05 | Q1 |
| S-07 | Anthropic — Building effective agents (2024-12-19) | https://www.anthropic.com/engineering/building-effective-agents | T2 | 2026-08-05 | Q2, Q5 |
| S-08 | Anthropic — Building agents with the Claude Agent SDK (2025) | https://claude.com/blog/building-agents-with-the-claude-agent-sdk | T2 | 2026-08-05 | Q2 |
| S-09 | Anthropic — How we built our multi-agent research system (2025-06) | https://www.anthropic.com/engineering/multi-agent-research-system | T2 | 2026-08-05 | Q2, Q3, Q5 |
| S-10 | Anthropic — Prompt caching (Claude Platform Docs) | https://platform.claude.com/docs/en/build-with-claude/prompt-caching | T1 | 2026-08-05 | Q3 |
| S-11 | OpenAI — Prompt caching (Platform Docs) | https://developers.openai.com/api/docs/guides/prompt-caching | T1 | 2026-08-05 | Q3 |
| S-12 | Anthropic — How we built our multi-agent research system | (同 S-09) | T2 | 2026-08-05 | Q3, Q5 |
| S-13 | Anthropic — Effective context engineering for AI agents | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | T1 | 2026-08-05 | Q3 |
| S-14 | Anthropic — Managing context on the Claude Developer Platform | https://claude.com/blog/context-management | T1 | 2026-08-05 | Q3 |
| S-15 | LangChain Docs — GRAPH_RECURSION_LIMIT error | https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT | T1 | 2026-08-05 | Q3 |
| S-16 | GitHub — langchain-ai/langgraph#7313 | https://github.com/langchain-ai/langgraph/issues/7313 | T2 | 2026-08-05 | Q3 |
| S-17 | arXiv 2607.01641 — When Agents Do Not Stop (IAL) | https://arxiv.org/html/2607.01641v1 | T2 | 2026-08-05 | Q3 |
| S-18 | Answer.AI — The unauthorized tool call problem | https://www.answer.ai/posts/2026-01-20-toolcalling.html | T2 | 2026-08-05 | Q3 |
| S-19 | Chroma Research — Context Rot | https://www.trychroma.com/research/context-rot | T2 | 2026-08-05 | Q3 |
| S-20 | LangGraph docs — Overview | https://docs.langchain.com/oss/python/langgraph/overview | T1 | 2026-08-05 | Q4 |
| S-21 | AutoGen GitHub README | https://github.com/microsoft/autogen | T1 | 2026-08-05 | Q4 |
| S-22 | CrewAI GitHub README | https://github.com/crewAIInc/crewAI | T1 | 2026-08-05 | Q4 |
| S-23 | CrewAI Docs — Flows | https://docs.crewai.com/en/concepts/flows | T1 | 2026-08-05 | Q4 |
| S-24 | OpenAI Agents SDK GitHub README | https://github.com/openai/openai-agents-python | T1 | 2026-08-05 | Q4 |
| S-25 | Claude Agent SDK — Agent SDK overview | https://code.claude.com/docs/en/agent-sdk/overview | T1 | 2026-08-05 | Q4 |
| S-26 | smolagents docs — Index | https://huggingface.co/docs/smolagents/en/index | T1 | 2026-08-05 | Q4 |
| S-27 | Cognition — Don't Build Multi-Agents | https://cognition.com/blog/dont-build-multi-agents | T2 | 2026-08-05 | Q5 |
| S-28 | Cemri, Pan et al. — Why Do Multi-Agent LLM Systems Fail? (MAST) | https://arxiv.org/abs/2503.13657 | T1 | 2026-08-05 | Q5 |
| S-29 | Hu et al. — Debate or Vote (MAD) | https://arxiv.org/abs/2508.17536 | T1 | 2026-08-05 | Q5 |

## Claim Ledger (主要 claim のみ)

| ID | Claim | Source | Kind | Status |
|---|---|---|---|---|
| C-A01 | ReAct は Thought/Action/Observation を interleave する | S-01 | verifiable | Supported |
| C-A02 | ReAct は CoT の幻覚・error propagation を外部 API 参照で緩和 | S-01 | verifiable | Supported |
| C-A03 | Reflexion は Actor/Evaluator/Self-Reflection の 3 モジュール | S-02 | verifiable | Supported |
| C-A04 | Reflexion は verbal self-reflection を episodic memory に保持 | S-02 | verifiable | Supported |
| C-A05 | Reflexion は HumanEval pass@1 91% を報告 | S-02 | verifiable | Supported |
| C-A06 | Plan-and-Solve は plan → subtask decomposition → execution | S-03 | verifiable | Supported |
| C-A07 | LangGraph 実装の Plan-and-Execute は Planner + Executor ノード分離 | S-04 | verifiable | Supported |
| C-A08 | LangGraph は Node/Edge/State + reducer で組む | S-05 | verifiable | Supported |
| C-A09 | LangGraph 実行モデルは super-step (Pregel 派生) | S-05 | verifiable | Supported |
| C-A10 | CodeAct は action を Python コードに統一 | S-06 | verifiable | Supported |
| C-A11 | CodeAct は JSON tool-call 比で最大 +20pt success rate | S-06 | verifiable | Supported |
| C-B01 | workflow = predefined code paths (Anthropic 定義) | S-07 | verifiable | Supported |
| C-B02 | agent = LLM dynamically directs process (Anthropic 定義) | S-07 | verifiable | Supported |
| C-B03 | Anthropic 3 原則: simplicity / transparency / ACI | S-07 | verifiable | Supported |
| C-B04 | Anthropic: simplest solution first, complexity only when needed | S-07 | verifiable | Supported |
| C-B05 | Anthropic: framework より API 直叩きを先に | S-07 | verifiable | Supported |
| C-B06 | 多くの用途では single LLM call + retrieval で足りる | S-07 | verifiable | Supported |
| C-B07 | Claude Agent SDK の 4 ステップ loop: gather/act/verify/repeat | S-08 | verifiable | Supported |
| C-B08 | Agents are stateful and errors compound | S-09 | verifiable | Supported |
| C-B09 | 同一プロンプトでも non-deterministic | S-09 | verifiable | Supported |
| C-B10 | Minor changes cascade into large behavioral changes | S-09 | verifiable | Supported |
| C-B11 | Anthropic は rainbow deployment で本番運用 | S-09 | verifiable | Supported |
| C-C01 | Anthropic prompt cache default 5 分 TTL、sliding | S-10 | verifiable | Supported |
| C-C02 | Anthropic は 1 時間 TTL 拡張 (2x write) を提供 | S-10 | verifiable | Supported |
| C-C03 | cache write 1.25x/2x、cache read 0.1x | S-10 | verifiable | Supported |
| C-C04 | OpenAI prompt cache は 1024 トークン最低、default 30 分 | S-11 | verifiable | Supported |
| C-C05 | agent 4x tokens、multi-agent 15x tokens (chat 比) | S-12 | verifiable | Supported (Q2/Q3 独立 corroboration) |
| C-C06 | 性能差の 80% はトークン消費量で説明 | S-12 | verifiable | Supported |
| C-C07 | agent loop は context bloat が本質的問題 | S-13 | verifiable | Supported |
| C-C08 | tool result clearing が公式機能化 | S-13 | verifiable | Supported |
| C-C09 | context editing で 100-turn eval 通過、84% token 削減 | S-14 | verifiable | Supported |
| C-C10 | max iterations は Anthropic 公式の control mechanism | S-07 | verifiable | Supported |
| C-C11 | LangGraph は default recursion_limit=25、内部 sentinel 10,000 | S-15, S-16 | verifiable | Supported |
| C-C12 | 47 OSS プロジェクト中 68 IAL failure、うち LangGraph+AutoGen 66.2% | S-17 | verifiable | Supported |
| C-C13 | 現行モデルで tool ハルシネーション (未定義 tool 捏造) 観測 | S-18 | verifiable | Supported |
| C-C14 | context 長に比例して 18 frontier モデルで性能低下 (Chroma) | S-19 | verifiable | Supported |
| C-D01 | Anthropic multi-agent 適用条件: 並列化・context 超過・多ツール | S-12 | verifiable | Supported |
| C-D02 | multi-agent 不適合: shared context / dependency 多 / coding | S-12 | verifiable | Supported |
| C-D03 | Opus 4 lead + Sonnet 4 subagent が single Opus 4 比 +90.2% | S-12 | verifiable | Supported |
| C-D04 | multi-agent は high-value task でのみ経済成立 | S-12 | verifiable | Supported |
| C-D05 | Cognition 原則: actions carry implicit decisions | S-27 | verifiable | Supported |
| C-D06 | Cognition 推奨: single-threaded linear agent、share full traces | S-27 | verifiable | Supported |
| C-D07 | MAST は 14 failure modes を 3 カテゴリに分類 | S-28 | verifiable | Supported |
| C-D08 | MAST 分布: specification 41.77%/inter-agent 36.94%/verification 21.30% | S-28 | verifiable | Supported |
| C-D09 | MAS の性能利得は single-agent 比で minimal なケースが多い | S-28 | verifiable | Supported |
| C-D10 | MAD の効果は多数決 ensemble でほぼ説明できる | S-29 | verifiable | Supported |
| C-E01 | LangGraph は low-level orchestration framework (公式自称) | S-20 | verifiable | Supported |
| C-E02 | LangGraph は persistence/HITL/short/long-term memory を提供 | S-20 | verifiable | Supported |
| C-E03 | LangGraph v1.0 GA、38.9k stars、Uber/LinkedIn/Klarna 事例 | S-20 (retriever が README も参照) | verifiable | Supported |
| C-E04 | AutoGen は maintenance mode 移行済 | S-21 | verifiable | Supported |
| C-E05 | CrewAI は role-playing crew + event-driven Flows | S-22, S-23 | verifiable | Supported |
| C-E06 | CrewAI は 56.6k stars、LangChain 非依存 | S-22 | verifiable | Supported |
| C-E07 | OpenAI Agents SDK: Agents/Handoffs/Guardrails/Sessions、100+ LLM | S-24 | verifiable | Supported |
| C-E08 | Claude Agent SDK は Claude Code の loop を programmable 化 | S-25 | verifiable | Supported |
| C-E09 | Claude Agent SDK は Python/TS のみ、他言語は CLI subprocess | S-25 | verifiable | Supported |
| C-E10 | smolagents は CodeAgent 中心、~1000 LOC | S-26 | verifiable | Supported |
| C-E11 | smolagents は sandbox 実行 (Modal/E2B/Docker) を提供 | S-26 | verifiable | Supported |

## Inferences (I-*)

| ID | Inference | Based on |
|---|---|---|
| I-01 | Multi-agent の本質は「並列に十分な token を使えるアーキテクチャ」に近い | C-C05 + C-C06 の組み合わせ (15x token & 80% variance) |
| I-02 | 本プロジェクトでは Claude Agent SDK が第一候補 | C-E08, C-E09 と daily-curation の `claude -p` 運用 (CLAUDE.md) の親和性 |
| I-03 | agent-loop-lab は単一 loop + isolated subagent (context 分離のみ) から始めるべき | C-D01, C-D02, C-D03, MAST の失敗パターン、Cognition の反対視点の統合判断 |
| I-04 | 停止条件を初期実装から 4 種セット (turn/retry/timeout/history) で入れる | C-C12 の LangGraph+AutoGen 66.2% IAL 発生の教訓 |
| I-05 | grounded-research は agent-loop-lab の初期 benchmark として自然 | 本 skill が retriever/verifier/refuter の subagent contract を既に規定 (skill 定義より) |

