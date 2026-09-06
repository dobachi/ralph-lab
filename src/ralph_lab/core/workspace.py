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
        baseline_document: Path | str | None = None,
    ) -> "Workspace":
        """input を workspace にコピー。file / dir 両対応 (P9 finding)。

        Args:
            input_document: agent が編集する初期状態。file なら 1 file、
              dir ならその dir 全体をコピー (P9 finding: code 領域で tests/ 等の
              周辺 file を持ち込むケース対応)
            root: 指定なしなら tempfile.mkdtemp で自動作成
            baseline_document: BASE (monotonicity 基準) の source。file/dir 両対応。
              None なら input_document を BASE にもコピー

        file 運用:
        - workspace root/BASE.<ext>, workspace root/current.<ext>
        - `$CURRENT` は current.<ext> の絶対 path

        dir 運用 (P9 対応):
        - workspace root/BASE/ (dir), workspace root/current/ (dir)
        - `$CURRENT` は current/ dir の絶対 path
        - hash verify は entire dir を tree-walk して集約 hash

        Backward-compat: file 運用は現行のまま (base_sha256 は file の sha256、
        _base_bytes は file の bytes)。dir 運用では tar 化した bytes を保存。
        """
        src = Path(input_document).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"input_document not found: {src}")

        base_src = (
            Path(baseline_document).expanduser().resolve()
            if baseline_document
            else src
        )
        if not base_src.exists():
            raise FileNotFoundError(f"baseline_document not found: {base_src}")

        if src.is_dir() != base_src.is_dir():
            raise ValueError(
                f"input_document and baseline_document must both be file or both dir. "
                f"input is {'dir' if src.is_dir() else 'file'}, "
                f"baseline is {'dir' if base_src.is_dir() else 'file'}."
            )

        if root is None:
            root_path = Path(tempfile.mkdtemp(prefix="ralph-lab-"))
        else:
            root_path = Path(root).expanduser().resolve()
            root_path.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            base = root_path / "BASE"
            current = root_path / "current"
            shutil.copytree(base_src, base)
            shutil.copytree(src, current)
            # BASE dir の全 file を chmod 444 (owner-bypass 可能なのは変わらず)
            for p in base.rglob("*"):
                if p.is_file():
                    p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            base_bytes = _dir_snapshot_bytes(base)
        else:
            suffix = src.suffix or ""
            base = root_path / f"BASE{suffix}"
            current = root_path / f"current{suffix}"
            shutil.copy2(base_src, base)
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
        """BASE (file or dir) が prepare 時から変わっていないかを確認、変わっていれば復元。

        Returns:
            (verified, message):
              - verified=True: hash 一致、変更なし。message は空文字
              - verified=False: hash 不一致 = tamper 検出。restoration を実施した後、
                message にサマリを返す

        P13-2 (2026-09-06) で観察: chmod 444 は file owner による chmod +w で
        解除可能。agent が BASE を書き換えて gate の monotonicity check を空振り
        させる Goodhart 型攻撃を実測した。この関数は hash verify で検出し、
        BASE を prepare 時 snapshot から復元する。

        dir 運用 (P9 対応): BASE が dir の場合、tree-walk で hash 集約。
        tamper 時は BASE dir 全体を削除 → 元 bytes から restore。
        """
        try:
            if self.base.is_dir():
                current_bytes = _dir_snapshot_bytes(self.base)
            else:
                current_bytes = self.base.read_bytes()
        except FileNotFoundError:
            current_bytes = b""

        current_hash = hashlib.sha256(current_bytes).hexdigest()
        if current_hash == self.base_sha256:
            return True, ""

        # Tamper 検出 — 復元
        if self.base.is_dir() or (not self.base.exists() and self._base_bytes.startswith(b"TAR:")):
            # Dir 運用の復元
            if self.base.exists():
                shutil.rmtree(self.base, ignore_errors=True)
            _restore_dir_from_snapshot(self.base, self._base_bytes)
            for p in self.base.rglob("*"):
                if p.is_file():
                    p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        else:
            # File 運用の復元
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
        """workspace 全体を削除。root 配下だけ触る。file/dir 両対応。"""
        if self.base.is_dir():
            for p in self.base.rglob("*"):
                if p.is_file():
                    try:
                        p.chmod(stat.S_IWUSR | stat.S_IRUSR)
                    except FileNotFoundError:
                        pass
        else:
            try:
                self.base.chmod(stat.S_IWUSR | stat.S_IRUSR)
            except FileNotFoundError:
                pass
        shutil.rmtree(self.root, ignore_errors=True)


def _dir_snapshot_bytes(dir_path: Path) -> bytes:
    """dir を deterministic snapshot bytes に変換 (hash 用)。

    実装は tar 化 (Python stdlib、順序固定、mode/mtime を除外)。
    prefix "TAR:" で file 運用の bytes と区別。
    """
    import io
    import tarfile

    buf = io.BytesIO()
    # deterministic mode: sorted names, no owner info, no mtime
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for p in sorted(dir_path.rglob("*")):
            if p.is_file():
                arcname = str(p.relative_to(dir_path))
                info = tf.gettarinfo(str(p), arcname=arcname)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                with p.open("rb") as f:
                    tf.addfile(info, f)
    return b"TAR:" + buf.getvalue()


def _restore_dir_from_snapshot(target: Path, snapshot: bytes) -> None:
    """`_dir_snapshot_bytes` で作った bytes から dir を復元。"""
    import io
    import tarfile

    if not snapshot.startswith(b"TAR:"):
        raise ValueError("snapshot is not a TAR: prefix bytes")
    buf = io.BytesIO(snapshot[len(b"TAR:"):])
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=buf, mode="r") as tf:
        tf.extractall(target)  # noqa: S202 — snapshot は自分で作った、trust
