# Research Plan: エージェントループ実装アーキテクチャの俯瞰

**Depth**: Standard (5 sub-questions, verify all verifiable claims, refute load-bearing)
**Date**: 2026-08-05
**Language**: 日本語
**Decision this feeds**: 子プロジェクト `agent-loop-lab` の設計インプット

## Sub-questions

| # | Sub-question | Retriever budget |
|---|---|---|
| Q1 | 主要な agent loop アーキテクチャ (ReAct, Plan-and-Execute, Reflexion, LangGraph state graph, CodeAct/OpenAgents 型) の動作原理・使い所・限界 | 5 searches |
| Q2 | Anthropic 公式知見 ("Building effective agents" 2024/12, "How we built our multi-agent research system" 2025 系) から得られる、agent 設計の原則と本番運用トラブル | 5 searches |
| Q3 | Agent loop の本番運用における実務知見: token cost 構造 / prompt caching / 停止条件 / hallucination / 無限ループ / context bloat | 5 searches |
| Q4 | 既存 OSS/SaaS agent framework の比較 — LangGraph, AutoGen (Microsoft), CrewAI, OpenAI Agents SDK, Claude Agent SDK, smolagents (HuggingFace) の制御モデル・状態管理・成熟度 | 6 searches |
| Q5 | 単一エージェントと multi-agent orchestration の使い分け基準 (Anthropic 知見、失敗パターン論文) | 4 searches |

## Independence check

- Q1 (アーキ動作原理) は Q4 (OSS 実装比較) と別。前者は概念モデル、後者は実装スタック。
- Q2 (Anthropic 一次資料) は Q3 (本番運用トピック横断) と別。前者は特定ソース、後者は cross-source アグリ。
- Q5 (single vs multi) は Q1/Q2 の後段テーマだが、独立に検索可能。

## Retriever contract (共通)

1 sub-question のみ担当し、以下のみを返す:

- Span tuples: `[(verbatim quoted span, canonical URL, accessed date YYYY-MM-DD, tier T1-T4, source name)]`
- Tier 判定 (T1=標準/公式仕様/一次論文/ソースコード, T2=vendor blog/公式ブログ, T3=署名済み技術記事, T4=aggregator/undated)
- 検索スニペットだけで引用しない (ページを開いて verbatim を取る)
- ⚠️ prose summary / conclusion / パラフレーズを返してはならない

## Post-retrieval steps

1. Source Register 統合、tier ラベル
2. Claim Ledger 作成、C-/I- ID 付与、kind=verifiable/interpretive/speculative
3. Blind verifier を verifiable claim ごとに fan-out (並列)
4. Load-bearing / numeric な claim には Refuter
5. Draft (日本語、C- ID 参照、verbatim quote は source 言語)
6. Grounding gate walk-through
7. span check (可能なら `scripts/check_spans.py`)
8. Coverage block
9. `agent-loop-lab/docs/research/2026-08-05-agent-loop-overview.md` として最終配置
