"""Workspace: BASE (read-only) + current の管理。v1 (agent-loop-lab) から移植。

Ralph 原則との整合:
- BASE は chmod 444 で書き込み範囲外 (loop-goal SKILL.md §5)
- current は agent CLI subprocess から編集される (subprocess の cwd で操作)
- driver は BASE と current のパスだけ知り、中身には触らない
"""

from __future__ import annotations

import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """1 iteration ごとに使い回される workspace ディレクトリ。"""

    root: Path
    """テンポラリディレクトリのルート (agent CLI subprocess の cwd)"""

    base: Path
    """編集前の baseline (read-only, chmod 444)"""

    current: Path
    """agent が編集するファイル"""

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

        return cls(root=root_path, base=base, current=current)

    def cleanup(self) -> None:
        """workspace 全体を削除。root 配下だけ触る。"""
        try:
            self.base.chmod(stat.S_IWUSR | stat.S_IRUSR)
        except FileNotFoundError:
            pass
        shutil.rmtree(self.root, ignore_errors=True)
