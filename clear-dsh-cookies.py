#!/usr/bin/env python3
"""Clear accumulated dsh-auth-* cookies from the DSH Desktop cookie store.

Why this exists: every DSH Desktop launch asks the local Host for a fresh
random port, and the Host mints a 30-day persistent cookie named
`dsh-auth-<sha256("127.0.0.1:<port>")>`. Chromium keeps every one of them
(cookies ignore ports), so after roughly 70 launches the Cookie request header
exceeds the 16 KiB limit of the local Node Host, which answers HTTP 431 and the
welcome handshake fails ("desktop welcome: Web authentication failed").

Run this while DSH Desktop is fully closed, including the tray icon.
No account credentials live in this cookie; deleting it only forces a new
handshake on the next launch.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

PREFIX = "dsh-auth-"
HEADER_LIMIT = 16384   # node:http default maxHeaderSize of the Host
COOKIE_BYTES = 228     # serialized `dsh-auth-...=...; ` for one cookie
RESERVED = 600         # request line + Chromium's own request headers, approx.
KEEP_BACKUPS = 5
APP_EXE_NAME = "DeepSeek Harness.exe"
APP_DIR_NAME = "DeepSeek Harness"


def default_db_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("[error] APPDATA is not set; pass --db <path> explicitly.")
    return Path(appdata) / "@deepseek-ai" / "dsh-desktop" / "Network" / "Cookies"


def _registry_executable() -> Path | None:
    """Find the install path the Desktop uninstaller registered."""
    try:
        import winreg
    except ImportError:
        return None
    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, key in roots:
        try:
            root = winreg.OpenKey(hive, key)
        except OSError:
            continue
        with root:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(root, sub) as entry:
                        name = winreg.QueryValueEx(entry, "DisplayName")[0]
                        if not isinstance(name, str) or not name.startswith(APP_DIR_NAME):
                            continue
                        try:
                            location = winreg.QueryValueEx(entry, "InstallLocation")[0]
                        except OSError:
                            location = ""
                        if isinstance(location, str) and location:
                            candidate = Path(location) / APP_EXE_NAME
                            if candidate.is_file():
                                return candidate
                        try:
                            icon = winreg.QueryValueEx(entry, "DisplayIcon")[0]
                        except OSError:
                            icon = ""
                        if isinstance(icon, str) and icon:
                            candidate = Path(icon.split(",")[0].strip().strip('"'))
                            if candidate.is_file():
                                return candidate
                except OSError:
                    continue
    return None


def app_executable(explicit: str | None = None) -> Path | None:
    """Locate the Desktop executable: flag, env var, common paths, then the registry."""
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    from_env = os.environ.get("DSH_DESKTOP_EXE")
    if from_env:
        candidate = Path(from_env)
        if candidate.is_file():
            return candidate
    for base in (
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if not base:
            continue
        for candidate in (
            Path(base) / APP_DIR_NAME / APP_EXE_NAME,
            Path(base) / "Programs" / APP_DIR_NAME / APP_EXE_NAME,
        ):
            if candidate.is_file():
                return candidate
    return _registry_executable()



def store_is_locked(path: Path) -> bool:
    """Chromium opens the cookie file exclusively while DSH is running."""
    try:
        with path.open("rb"):
            return False
    except OSError:
        return True


def open_store(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=2.0)
    conn.execute("PRAGMA busy_timeout = 2000")
    tables = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'cookies'"
    ).fetchone()[0]
    if not tables:
        conn.close()
        raise RuntimeError("not a Chromium cookie database (no `cookies` table)")
    return conn


def count(conn: sqlite3.Connection, like: str) -> int:
    return conn.execute(
        "SELECT count(*) FROM cookies WHERE name LIKE ?", (like,)
    ).fetchone()[0]


def busy_hint() -> None:
    print()
    print("[stop] the cookie store is still in use - DSH Desktop is running.")
    print("       Quit it completely (tray icon -> Quit), then run this again.")
    print("       Nothing was changed.")


def prune_backups(path: Path) -> None:
    backups = sorted(path.parent.glob(path.name + ".bak-*"))
    for stale in backups[:-KEEP_BACKUPS]:
        try:
            stale.unlink()
        except OSError:
            pass


def clean(args: argparse.Namespace) -> int:
    path = args.db or default_db_path()
    print(f"cookie store : {path}")
    if not path.is_file():
        print("result       : no cookie store yet - nothing to clean.")
        return 0

    if not args.force and store_is_locked(path):
        busy_hint()
        return 2

    try:
        conn = open_store(path)
    except (sqlite3.Error, RuntimeError) as error:
        print(f"\n[stop] cannot open the cookie store: {error}")
        if not args.force:
            busy_hint()
            return 2
        raise

    try:
        mine = count(conn, PREFIX + "%")
        others = conn.execute("SELECT count(*) FROM cookies").fetchone()[0] - mine
        print(f"dsh-auth-*   : {mine} cookie(s), ~{mine * COOKIE_BYTES} of {HEADER_LIMIT} header bytes")
        print(f"other cookies: {others} (kept)")

        if mine == 0:
            print("result       : already clean.")
            return 0
        if args.dry_run:
            print("result       : dry run, nothing deleted.")
            return 0

        backup = path.with_name(f"{path.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, backup)
        conn.execute("DELETE FROM cookies WHERE name LIKE ?", (PREFIX + "%",))
        conn.commit()
        left = count(conn, PREFIX + "%")
        print(f"backup       : {backup.name}")
        print(f"deleted      : {mine} row(s), {left} dsh-auth-* left")
        spare = max(0, (HEADER_LIMIT - RESERVED) // COOKIE_BYTES - left)
        print(f"result       : clean - about {spare} launches before it can fill up again.")
        prune_backups(path)
    finally:
        conn.close()
    return 0


def launch_app(explicit: str | None = None) -> None:
    exe = app_executable(explicit)
    if exe is None:
        print("[warn] DSH Desktop executable not found; start it yourself.")
        print("       Pass --exe <path> or set DSH_DESKTOP_EXE if it is installed elsewhere.")
        return
    subprocess.Popen([str(exe)], close_fds=True)
    print(f"launched     : {exe}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete old dsh-auth-* cookies from the DSH Desktop store."
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help=r"cookie database path (default: %%APPDATA%%\@deepseek-ai\dsh-desktop\Network\Cookies)",
    )
    parser.add_argument("--dry-run", action="store_true", help="only report, change nothing")
    parser.add_argument("--launch", action="store_true", help="start DSH Desktop afterwards")
    parser.add_argument(
        "--exe", default=None,
        help="Desktop executable used by --launch (default: auto-detect)",
    )
    parser.add_argument("--force", action="store_true", help="skip the in-use check (unsafe)")
    args = parser.parse_args()

    code = clean(args)
    if args.launch:
        launch_app(args.exe)
    return code


if __name__ == "__main__":
    sys.exit(main())
