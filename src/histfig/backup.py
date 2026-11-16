"""Backups of the data folder: one .zip with everything needed to continue elsewhere.

A backup holds a consistent copy of the database (figures, documents' passages and
vectors, conversations, prompts), the uploaded files, the portraits and the settings,
with API keys left out. Restoring checks the whole backup before anything is changed,
then swaps it in; the data it replaces is kept in <data_dir>/previous until the next restore.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path, PurePosixPath

from histfig.config import Config, load_config, save_config
from histfig.db import SCHEMA_VERSION, Database

FOLDERS = ("uploads", "images")  # copied as they are
MAX_RESTORE_BYTES = 20 * 1024**3  # unpacked size; protects against zip bombs


class RestoreError(ValueError):
    pass


def make_backup(data_dir: Path, db: Database, cfg: Config) -> Path:
    """Write a backup to a new temporary folder; returns the .zip (delete its folder afterwards)."""
    work = Path(tempfile.mkdtemp(prefix="histfig-backup-"))
    snapshot = work / "histfig.db"
    with db.connect() as conn:  # SQLite's backup: consistent even while the app is working
        target = sqlite3.connect(snapshot)
        try:
            conn.backup(target)
        finally:
            target.close()
    keyless = replace(cfg, chat=replace(cfg.chat, api_key=""), embedding=replace(cfg.embedding, api_key=""))
    save_config(keyless, work)  # api_key_env (the name of a variable, not a secret) is kept
    archive = work / "histfig-backup.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snapshot, "histfig.db")
        z.write(work / "config.toml", "config.toml")
        for folder in FOLDERS:
            for path in sorted((data_dir / folder).rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(data_dir).as_posix())
    snapshot.unlink()
    return archive


def unpack(source, staging: Path) -> None:
    """Check a backup (a path or file object) and unpack it into staging, which must not exist.
    Raises RestoreError, saying why, if it isn't a usable HistFig backup."""
    try:
        z = zipfile.ZipFile(source)
    except zipfile.BadZipFile as e:
        raise RestoreError("This is not a HistFig backup (not a .zip file).") from e
    with z:
        members = []
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = PurePosixPath(info.filename).parts
            if info.filename.startswith("/") or "\\" in info.filename or ".." in parts:
                raise RestoreError(f"The backup contains an unsafe path: {info.filename}")
            if info.filename in ("histfig.db", "config.toml") or (len(parts) > 1 and parts[0] in FOLDERS):
                members.append(info)  # anything else is ignored
        if not any(m.filename == "histfig.db" for m in members):
            raise RestoreError("This is not a HistFig backup (it has no histfig.db).")
        if sum(m.file_size for m in members) > MAX_RESTORE_BYTES:
            raise RestoreError("The backup is too large to restore.")
        staging.mkdir(parents=True)
        for m in members:
            target = staging.joinpath(*PurePosixPath(m.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    _check_database(staging / "histfig.db")
    if (staging / "config.toml").exists():
        try:
            load_config(staging)
        except Exception as e:
            raise RestoreError(f"The settings in the backup can't be read ({e}).") from e


def _check_database(path: Path) -> None:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise RestoreError(f"The database in the backup can't be read ({e}).") from e
    if not ok:
        raise RestoreError("The database in the backup is damaged.")
    if version != SCHEMA_VERSION:
        raise RestoreError(f"The backup is from a different version of HistFig "
                           f"(database version {version}, expected {SCHEMA_VERSION}).")


def swap_in(data_dir: Path, db: Database, staging: Path) -> None:
    """Replace the database, uploads and portraits with the unpacked backup. The current
    ones go to <data_dir>/previous (replacing what an earlier restore left there).
    Other requests wait meanwhile (db.exclusive)."""
    with db.exclusive():
        _swap_files(data_dir, db, staging)


def _swap_files(data_dir: Path, db: Database, staging: Path) -> None:
    conn = db._open()  # fold the write-ahead log into the database file
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    previous = data_dir / "previous"
    shutil.rmtree(previous, ignore_errors=True)
    previous.mkdir()
    if (data_dir / "config.toml").exists():
        shutil.copy2(data_dir / "config.toml", previous / "config.toml")
    for name in ("histfig.db", "histfig.db-wal", "histfig.db-shm", *FOLDERS):
        if (data_dir / name).exists():
            os.replace(data_dir / name, previous / name)
    for name in ("histfig.db", *FOLDERS):
        if (staging / name).exists():
            os.replace(staging / name, data_dir / name)
    for folder in FOLDERS:
        (data_dir / folder).mkdir(exist_ok=True)


def restored_config(staging: Path, current: Config) -> Config:
    """The backup's settings, keeping this computer's API keys (backups have none) and
    server address. Without settings in the backup: the current ones."""
    saved = load_config(staging) if (staging / "config.toml").exists() else None
    if saved is None:
        return current

    def keys_from(mine, theirs):
        if theirs.api_key or theirs.api_key_env:
            return theirs
        return replace(theirs, api_key=mine.api_key, api_key_env=mine.api_key_env)

    return replace(saved, server=current.server,
                   chat=keys_from(current.chat, saved.chat),
                   embedding=keys_from(current.embedding, saved.embedding))
