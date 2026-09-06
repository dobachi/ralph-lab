#!/bin/bash
# 方式 A: gate.sh 内 subprocess で他スキルに委譲する例
#
# 契約 (ralph-lab の spec.gate.script):
#   - 呼び出し: gate.sh <current_file>
#   - 環境変数: BASE=<baseline_file>
#   - Exit code: 0 = pass, 非 0 = fail
#   - Stdout: 次 iter の agent への feedback
#
# この gate は 3 層の check を組み合わせる:
#   Layer A (syntactic): 対応関係 + 単調性 + 内容 non-empty
#   Layer B (委譲): claude subprocess で fact-checker / doc-review を呼ぶ
#   注: Layer C (post_evaluation) は Ralph loop の外側なので gate では扱わない
#
# 前提:
#   - claude CLI が PATH にあり ~/.claude/ に認証済
#   - fact-checker / doc-review スキルが install 済 (or 相当の代替)
#
# 使い方:
#   BASE=/path/to/baseline.md ./gate.sh /path/to/current.md
#
# 注: 各 subprocess は独立に fresh context で起動される (Ralph 原則忠実)。
# 委譲 skill が model call を実行するので、iter 1 回で cost が数倍になる。

set -u

CURRENT="${1:?Missing target file argument}"
if [ ! -f "$CURRENT" ]; then
    echo "gate.sh: current file not found: $CURRENT" >&2
    exit 2
fi

BASE_FILE="${BASE:-}"

# ============================================================================
# Layer A: syntactic (自作 Python check)
# ============================================================================

python3 - "$CURRENT" "$BASE_FILE" <<'PY'
import re
import sys
from pathlib import Path

current_path = Path(sys.argv[1])
base_path_str = sys.argv[2] if len(sys.argv) > 2 else ""
base_path = Path(base_path_str) if base_path_str else None

def_pattern = re.compile(r'^\[\^(\d+)\]:\s*(.*)$', re.MULTILINE)
ref_pattern = re.compile(r'\[\^(\d+)\](?!:)')

def extract(text):
    defs = {m.group(1): m.group(2).strip() for m in def_pattern.finditer(text)}
    body_lines = [l for l in text.splitlines() if not def_pattern.match(l)]
    body = "\n".join(body_lines)
    refs = set(m.group(1) for m in ref_pattern.finditer(body))
    return refs, defs

current_text = current_path.read_text(encoding="utf-8")
curr_refs, curr_defs = extract(current_text)
curr_def_ids = set(curr_defs.keys())

# 対応関係
undefined = sorted(curr_refs - curr_def_ids, key=int)
unused = sorted(curr_def_ids - curr_refs, key=int)

# 単調性
missing_refs = None
missing_defs = None
if base_path and base_path.is_file():
    base_refs, base_defs = extract(base_path.read_text(encoding="utf-8"))
    base_def_ids = set(base_defs.keys())
    missing_refs = sorted(base_refs - curr_refs, key=int)
    missing_defs = sorted(base_def_ids - curr_def_ids, key=int)

# 内容 non-empty (Check 3)
empty_defs = sorted(
    (n for n, content in curr_defs.items() if len(content) < 20),
    key=int
)

print(f"=== Layer A syntactic check: {current_path.name} ===")
print(f"  refs = {sorted(curr_refs, key=int)}")
print(f"  defs = {sorted(curr_def_ids, key=int)}")

failed = False
if undefined:
    print(f"  ❌ 未定義参照 {undefined}: 本文の [^N] を baseline 側の既存参照に戻せ")
    failed = True
if missing_refs or missing_defs:
    m = (missing_refs or []) + (missing_defs or [])
    print(f"  ❌ 単調性違反 {m}: baseline から削除された")
    failed = True
if empty_defs:
    print(f"  ❌ 空/薄い定義 {empty_defs}: `[^N]:` の後に 20 文字以上の内容が要る")
    failed = True

# Layer A の結果を stdout に、exit code は 0/1 の segment で持つ
sys.exit(1 if failed else 0)
PY

LAYER_A_RC=$?

if [ $LAYER_A_RC -ne 0 ]; then
    echo ""
    echo "Layer A failed — Layer B の委譲は fail-fast でスキップします"
    echo ""
    echo "判定: NG"
    exit 1
fi

# ============================================================================
# Layer B: 委譲 (claude subprocess で fact-checker / doc-review を呼ぶ)
# ============================================================================
#
# 注: 実運用では ~/.claude に fact-checker / doc-review skill が install
# されている必要がある。ここでは prompt で明示的にスキル発火を指示する。

if ! command -v claude &>/dev/null; then
    echo ""
    echo "⚠️ claude CLI が PATH に無い — Layer B (委譲) をスキップ"
    echo "判定: OK (Layer A のみ)"
    exit 0
fi

echo ""
echo "=== Layer B delegation ==="

DELEGATE_FAIL=0

# --- fact-checker 委譲 ---
FACT_PROMPT=$(cat <<EOF
Please invoke the fact-checker skill on this document: $CURRENT

For each footnote reference [^N] pointing to a URL definition, verify that the
URL is reachable and that the referenced source actually contains the claim
being cited.

Output format:
- First line: exactly "PASS" or "FAIL"
- If FAIL, second and subsequent lines: brief reasons

Keep the output under 500 characters total. Do not add explanations.
EOF
)

echo "[fact-checker] invoking..."
FACT_OUTPUT=$(timeout 300 claude -p --dangerously-skip-permissions "$FACT_PROMPT" 2>&1 || echo "TIMEOUT")
if [ "$FACT_OUTPUT" = "TIMEOUT" ]; then
    echo "  ⚠️ fact-checker timed out (>5 min), skipping"
elif grep -qE '^FAIL' <<< "$FACT_OUTPUT"; then
    echo "  ❌ fact-checker: FAIL"
    echo "$FACT_OUTPUT" | head -5 | sed 's/^/    /'
    DELEGATE_FAIL=1
else
    echo "  ✅ fact-checker: PASS"
fi

# --- doc-review 委譲 ---
REVIEW_PROMPT=$(cat <<EOF
Please invoke the doc-review skill on this document: $CURRENT

Report only critical issues (buried conclusion, unsound argument, missing
evidence for a key claim). Do NOT report style / minor issues.

Output format:
- First line: exactly "PASS" or "FAIL"
- If FAIL, second and subsequent lines: list of critical issues, one per line

Keep the output under 500 characters total.
EOF
)

echo "[doc-review] invoking..."
REVIEW_OUTPUT=$(timeout 300 claude -p --dangerously-skip-permissions "$REVIEW_PROMPT" 2>&1 || echo "TIMEOUT")
if [ "$REVIEW_OUTPUT" = "TIMEOUT" ]; then
    echo "  ⚠️ doc-review timed out (>5 min), skipping"
elif grep -qE '^FAIL' <<< "$REVIEW_OUTPUT"; then
    echo "  ❌ doc-review: FAIL"
    echo "$REVIEW_OUTPUT" | head -5 | sed 's/^/    /'
    DELEGATE_FAIL=1
else
    echo "  ✅ doc-review: PASS"
fi

# ============================================================================
# 集約
# ============================================================================

echo ""
if [ $DELEGATE_FAIL -ne 0 ]; then
    echo "判定: NG (Layer A pass, Layer B fail)"
    exit 1
fi

echo "判定: OK (Layer A + Layer B all pass)"
exit 0
