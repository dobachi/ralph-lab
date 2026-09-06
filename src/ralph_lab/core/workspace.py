"""Workspace: BASE (read-only) + current の管理。v1 (agent-loop-lab) から移植。

Ralph 原則との整合:
- BASE は chmod 444 で書き込み範囲外 (loop-goal SKILL.md §5) — ただし
  file owner は chmod +w で解除可能なので **enforcement ではなく convention**。
  真の整合性は `verify_and_restore_base()` の hash verify で担保する (P13-3)。
- current は agent CLI subprocess から編集される (subprocess の cwd で操作)
- driver は BASE と current のパスだけ知り、中身には触らない
"""

from __future__ import annotations

import hashlib
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Workspace:
    """1 iteration ごとに使い回される workspace ディレクトリ。

    frozen=False 化: base_tampered_count を iter 経由で更新するため。
    整合性の根幹は base_sha256 + _base_bytes (immutable snapshot)。
    """

    root: Path
    """テンポラリディレクトリのルート (agent CLI subprocess の cwd)"""

    base: Path
    """編集前の baseline (chmod 444、ただし verify_and_restore_base() が
    hash 一致を担保する真の整合性 layer)"""

    current: Path
    """agent が編集するファイル"""

    base_sha256: str = ""
    """prepare 時に計算した BASE の SHA-256 (verify に使用)"""

    _base_bytes: bytes = b""
    """prepare 時に読んだ BASE の bytes (tamper 時の復元に使用)。
    先頭 `_` は 'internal, don't serialize' の目印。"""

    base_tampered_count: int = 0
    """agent 実行後に BASE tamper を検出した累積回数 (JSONL 用)"""

    @classmethod
    def prepare(
        cls,
        input_document: Path | str,
        root: Path | str | None = None,
    ) -> "Workspace":
        """`input_document` を BASE と current にコピーして workspace を作る。

        Args:
            input_document: コピー元ファイル
            root: 指定なしなら tempfile.mkdtemp で自動作成
        """
        src = Path(input_document).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"input_document not found: {src}")

        if root is None:
            root_path = Path(tempfile.mkdtemp(prefix="ralph-lab-"))
        else:
            root_path = Path(root).expanduser().resolve()
            root_path.mkdir(parents=True, exist_ok=True)

        suffix = src.suffix or ""
        base = root_path / f"BASE{suffix}"
        current = root_path / f"current{suffix}"

        shutil.copy2(src, base)
        shutil.copy2(src, current)

        base.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        base_bytes = base.read_bytes()
        base_sha256 = hashlib.sha256(base_bytes).hexdigest()

        return cls(
            root=root_path,
            base=base,
            current=current,
            base_sha256=base_sha256,
            _base_bytes=base_bytes,
        )

    def verify_and_restore_base(self) -> tuple[bool, str]:
        """BASE.md が prepare 時から変わっていないかを確認、変わっていれば復元。

        Returns:
            (verified, message):
              - verified=True: hash 一致、変更なし。message は空文字
              - verified=False: hash 不一致 = tamper 検出。restoration を実施した後、
                message にサマリを返す

        P13-2 (2026-09-06) で観察: chmod 444 は file owner による chmod +w で
        解除可能。agent が BASE を書き換えて gate の monotonicity check を空振り
        させる Goodhart 型攻撃を実測した。この関数は hash verify で検出し、
        BASE を prepare 時 snapshot から復元する。
        """
        try:
            current_bytes = self.base.read_bytes()
        except FileNotFoundError:
            # BASE 自体が消された場合も tamper 扱いで復元
            current_bytes = b""

        current_hash = hashlib.sha256(current_bytes).hexdigest()
        if current_hash == self.base_sha256:
            return True, ""

        # Tamper 検出 — 復元
        try:
            self.base.chmod(stat.S_IWUSR | stat.S_IRUSR)
        except FileNotFoundError:
            pass
        self.base.write_bytes(self._base_bytes)
        self.base.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        self.base_tampered_count += 1

        return False, (
            f"BASE tamper detected (attempt #{self.base_tampered_count}): "
            f"expected sha256={self.base_sha256[:16]}..., "
            f"got={current_hash[:16]}... "
            f"({len(current_bytes)} bytes vs {len(self._base_bytes)} bytes original). "
            f"BASE has been restored from prepare-time snapshot."
        )

    def cleanup(self) -> None:
        """workspace 全体を削除。root 配下だけ触る。"""
        try:
            self.base.chmod(stat.S_IWUSR | stat.S_IRUSR)
        except FileNotFoundError:
            pass
        shutil.rmtree(self.root, ignore_errors=True)
