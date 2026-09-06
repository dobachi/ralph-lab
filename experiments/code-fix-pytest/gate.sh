#!/bin/bash
# Gate: 編集された calc.py を実 project の src/tests layout と組み合わせて
# pytest を走らせる。all pass → exit 0、fail → 非 0。
#
# 契約 (ralph-lab の spec.gate.script):
#   - 呼び出し: gate.sh <current_file>
#   - Exit code: 0 = pass, non-zero = fail
#   - Stdout: 次 iter の agent への feedback (pytest failures を含む)
#
# 設計:
# - ralph-lab の workspace は input_document (1 file) しか含まないため、
#   tests/ が周辺に無い。gate.sh 側で tempdir に完全 layout を組む。
# - src/calc.py を編集済 CURRENT で上書き、tests/ をこの project 定位置から
#   コピー、そこで pytest 実行。副作用は tempdir 内に閉じる。

set -u

CURRENT="${1:?Missing target file argument}"
if [ ! -f "$CURRENT" ]; then
    echo "gate.sh: current file not found: $CURRENT" >&2
    exit 2
fi

# この gate.sh が置かれているディレクトリ = project layout の root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -d "$PROJECT_ROOT/tests" ] || [ ! -d "$PROJECT_ROOT/src" ]; then
    echo "gate.sh: expected tests/ and src/ under $PROJECT_ROOT" >&2
    exit 2
fi

# tempdir に layout を組む
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

mkdir -p "$TEMP/src" "$TEMP/tests"
cp "$CURRENT" "$TEMP/src/calc.py"
cp "$PROJECT_ROOT/tests/"*.py "$TEMP/tests/"

cd "$TEMP"
export PYTHONPATH="$TEMP/src"

python3 -m pytest tests/ --tb=short -q --no-header 2>&1
