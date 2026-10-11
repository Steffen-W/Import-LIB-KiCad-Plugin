"""Atomic file replacement shared by ConfigHandler and KiCad_Settings.

Guards against truncating/corrupting the destination file if the process is
interrupted mid-write (crash, force-quit, unhandled exception): the new
content is written to a temp file first and only becomes visible as `path`
via a single `os.replace()`, so `path` always contains either the old or the
fully-written new content, never a partial write.

The temp file and (on POSIX) its directory entry are fsync'd before/after
the rename as a best-effort durability improvement, but this does not
guarantee survival of a true power-loss/OS-crash event (that would also
require the underlying storage and filesystem to honor fsync semantics,
which e.g. some network filesystems or misconfigured drives don't) — treat
it as "safe against process-level interruption", not as a full ACID
guarantee.

Also preserves the destination file's existing permission bits (or falls
back to the umask-respecting default for a brand-new file) instead of
silently narrowing them to mkstemp()'s restrictive 0600.
"""

from __future__ import annotations

import os
import stat
import tempfile
from contextlib import suppress
from typing import Callable


def _dirfsync(directory: str) -> None:
    # Directory fsync is a POSIX-only durability step (ensures the rename
    # itself survives a crash, not just the file content); Windows has no
    # equivalent and os.open() with O_DIRECTORY isn't available there.
    if os.name != "posix":
        return
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def atomic_write(path: str, write_fn: Callable[[str], object]) -> None:
    """Atomically replace `path` with content produced by `write_fn(tmp_path)`.

    `write_fn` receives a temporary path in the same directory as `path` and
    must (over)write it completely. On success, the temp file is fsync'd and
    renamed onto `path` via `os.replace()`; the destination's existing
    permission bits are preserved (or umask-default for a new file) instead
    of inheriting mkstemp()'s restrictive 0600. On any failure the temp file
    is removed and the original `path` is left untouched.
    """
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=os.path.basename(path))
    os.close(fd)
    try:
        write_fn(tmp_path)

        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except FileNotFoundError:
            # New file: mkstemp() always creates it 0600 regardless of umask.
            # Use the umask-respecting default (like a plain open(path, "w")
            # would) instead of leaving it locked down to the owner only.
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp_path, mode)

        # Ensure the temp file's content is on disk before the rename that
        # makes it visible as `path` — otherwise a crash right after the
        # rename could leave `path` pointing at not-yet-flushed data.
        fd_sync = os.open(tmp_path, os.O_RDONLY)
        try:
            os.fsync(fd_sync)
        except OSError:
            pass
        finally:
            os.close(fd_sync)

        os.replace(tmp_path, path)
        _dirfsync(directory)
    except BaseException:
        with suppress(OSError):
            os.remove(tmp_path)
        raise


def atomic_write_text(path: str, content: str, encoding: str = "utf-8") -> None:
    """Write text to `path` atomically and durably. See `atomic_write`."""

    def _write(tmp_path: str) -> None:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

    atomic_write(path, _write)
