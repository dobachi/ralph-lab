#!/bin/bash
# Custom gate for real-doc-refs example.
#
# 契約 (ralph-lab の spec.gate.script):
#   - 呼び出し: gate.sh <current_file>
#   - 環境変数: BASE=<baseline_file> (driver が自動で埋める)
#   - Exit code: 0 = pass, non-zero = fail
#   - Stdout: 次 iter の agent への feedback
#
# 検査内容:
#   [1] 対応関係 (current 内部):
#     - 本文中の [^N] 参照 と [^N]: 定義 の対応
#     - 未定義参照 (本文にあるが定義がない) → NG
#     - 未使用定義 (定義はあるが本文で参照されない) → WARN (pass)
#
#   [2] 単調性 (BASE との比較、P12 で追加):
#     - BASE 環境変数が指す baseline の refs 集合が current の refs 集合の
#       subset か。BASE で参照されていた [^N] が current で消えていたら NG
#     - defs 集合も同様の subset check
#     - **loop-goal §2.4-3 に対応**: 「削除で満たす」型 Goodhart を塞ぐ
#     - P11 (2026-09-06) で agent が [^99] を削除して pass した観察への
#       直接対策
#
# 実装は Python3 の embedded script。標準ライブラリのみ。

set -u

CURRENT="${1:?Missing target file argument}"
if [ ! -f "$CURRENT" ]; then
    echo "gate.sh: current file not found: $CURRENT" >&2
    exit 2
fi

# BASE は driver が spec.gate 実行時に自動で埋める。手動 sanity test 用に
# `BASE=path ./gate.sh path` で叩けるように、未設定なら空文字扱い。
BASE_FILE="${BASE:-}"

python3 - "$CURRENT" "$BASE_FILE" <<'PY'
import re
import sys
from pathlib import Path

def_pattern = re.compile(r'^\[\^(\d+)\]:\s', re.MULTILINE)
ref_pattern = re.compile(r'\[\^(\d+)\](?!:)')


def extract_refs_defs(text: str):
    """本文 refs と定義 defs の集合を返す。"""
    def_ids = set(m.group(1) for m in def_pattern.finditer(text))
    # 定義行を除いた本文からの参照
    lines_body = []
    for line in text.splitlines():
        if def_pattern.match(line):
            continue
        lines_body.append(line)
    body_text = "\n".join(lines_body)
    ref_ids = set(m.group(1) for m in ref_pattern.finditer(body_text))
    return ref_ids, def_ids


current_path = Path(sys.argv[1])
base_path_str = sys.argv[2] if len(sys.argv) > 2 else ""
base_path = Path(base_path_str) if base_path_str else None

current_text = current_path.read_text(encoding="utf-8")
curr_refs, curr_defs = extract_refs_defs(current_text)

# 対応関係
undefined = sorted(curr_refs - curr_defs, key=int)
unused = sorted(curr_defs - curr_refs, key=int)

# BASE 比較 (単調性 check)
base_refs = None
base_defs = None
missing_refs = None  # BASE にあり current にないもの
missing_defs = None
if base_path and base_path.is_file():
    base_text = base_path.read_text(encoding="utf-8")
    base_refs, base_defs = extract_refs_defs(base_text)
    missing_refs = sorted(base_refs - curr_refs, key=int)
    missing_defs = sorted(base_defs - curr_defs, key=int)

# 結果 report
report = [f"# Footnote reference integrity: {current_path.name}"]
report.append(f"  refs in body   : {sorted(curr_refs, key=int)}")
report.append(f"  defs in bibliography: {sorted(curr_defs, key=int)}")

if base_path and base_path.is_file():
    report.append(f"  BASE refs      : {sorted(base_refs, key=int)}")
    report.append(f"  BASE defs      : {sorted(base_defs, key=int)}")

# 対応関係の findings
if undefined:
    report.append(f"  ❌ 未定義 (本文にあるが `[^N]: ...` 定義がない): {undefined}")
if unused:
    report.append(f"  ⚠️  未使用 (`[^N]: ...` 定義はあるが本文で参照されない): {unused}")

# 単調性の findings
if missing_refs:
    report.append(
        f"  ❌ 単調性違反: BASE で参照されていた [^N] が current で消えている: "
        f"{missing_refs}"
    )
if missing_defs:
    report.append(
        f"  ❌ 単調性違反: BASE の [^N]: 定義が current で消えている: "
        f"{missing_defs}"
    )

# 保証しないこと (loop-goal 風)
report.append("")
report.append("保証しないこと:")
report.append("  - 参照先 URL が生きているかは見ない (fetch check なし)")
report.append("  - 定義の内容が主張を支えるかは見ない (対応関係のみ)")
report.append("  - 脚注が正しい位置に付いているかは見ない")
report.append("  - 単調性 check は refs/defs の集合だけを見る。位置や数の")
report.append("    保持は見ない (例: 同じ [^1] が 2 箇所 → 1 箇所は検出しない)")
report.append("  - BASE 未指定なら単調性 check は行わない")

print("\n".join(report))

# 判定
if undefined:
    print(f"\n判定: NG ({len(undefined)} 個の未定義脚注参照)")
    sys.exit(1)
if missing_refs or missing_defs:
    n = len(missing_refs or []) + len(missing_defs or [])
    print(f"\n判定: NG (単調性違反 {n} 件、削除された参照/定義がある)")
    sys.exit(1)
if unused:
    print(f"\n判定: WARN ({len(unused)} 個の未使用定義、gate は pass)")
    sys.exit(0)  # 未使用は許容
print("\n判定: OK")
sys.exit(0)
PY
