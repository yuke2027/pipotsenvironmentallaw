import hashlib
import os
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from app.v2.common import fail


class FileStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            fail("文件路径无效")
        return path

    def put(self, content: bytes, category: str, suffix: str = "") -> tuple[str, str]:
        hashed = hashlib.sha256(content).hexdigest()
        key = f"{category}/{hashed[:2]}/{hashed}{suffix}"
        target = self.path(key)
        self._write(target, hashed, (content,))
        return key, hashed

    @staticmethod
    def _digest(path: Path) -> str | None:
        try:
            with path.open("rb") as source:
                digest = hashlib.sha256()
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
                return digest.hexdigest()
        except FileNotFoundError:
            return None

    def _write(self, target: Path, expected: str, blocks: Iterable[bytes]) -> None:
        # A content-addressed filename alone does not prove that a previous write survived.
        if self._digest(target) == expected:
            self._sync_directories(target.parent)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{uuid4().hex}.tmp")
        try:
            digest = hashlib.sha256()
            with temporary.open("xb") as stream:
                for block in blocks:
                    stream.write(block)
                    digest.update(block)
                stream.flush()
                os.fsync(stream.fileno())
            if digest.hexdigest() != expected:
                raise ValueError("Source file changed during storage")
            os.replace(temporary, target)
            # Persist the directory entry before the caller commits its database reference.
            self._sync_directories(target.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _sync_directories(self, parent: Path) -> None:
        if os.name == "nt":
            return
        while parent.is_relative_to(self.root):
            directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            if parent == self.root:
                break
            parent = parent.parent

    def verify(self, key: str, expected: str) -> Path:
        path = self.path(key)
        if self._digest(path) != expected:
            fail("文件缺失或完整性校验失败")
        return path

    def put_file(self, source: Path, category: str, suffix: str = "") -> tuple[str, str]:
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
        hashed = digest.hexdigest()
        key = f"{category}/{hashed[:2]}/{hashed}{suffix}"
        target = self.path(key)
        with source.open("rb") as stream:
            self._write(target, hashed, iter(lambda: stream.read(1024 * 1024), b""))
        return key, hashed
