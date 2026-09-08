# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Index de tous les fichiers du PC pour une recherche instantanée.

- Parcourt les disques (config.INDEX_DRIVES) en arrière-plan et stocke chemin, nom, taille,
  date dans une base SQLite (index/files.db) avec une table FTS5 « trigram » sur le nom.
- La recherche est une sous-chaîne insensible à la casse et aux accents, en quelques millisecondes.
- Le premier index prend quelques minutes ; ensuite il est rafraîchi toutes les
  config.INDEX_REFRESH_MINUTES minutes sans bloquer l'agent.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

import config

DB_PATH = config.ROOT / "index" / "files.db"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class FileIndex:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.building = False
        self.progress = 0
        self.last_build: float = 0.0
        self.last_duration: float = 0.0
        self.count = 0
        self._thread: threading.Thread | None = None
        db = self._connect()
        try:
            self._ensure_schema(db)
            row = db.execute("SELECT value FROM meta WHERE key='last_build'").fetchone()
            self.last_build = float(row[0]) if row else 0.0
            self.count = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        finally:
            db.close()

    # ------------------------------------------------------------------ base
    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=OFF")
        return db

    @staticmethod
    def _ensure_schema(db: sqlite3.Connection) -> None:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY, path TEXT, name_lc TEXT, ext TEXT,
                size INTEGER, mtime REAL, is_dir INTEGER);
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                name_lc, content='files', content_rowid='id', tokenize='trigram');
        """)

    # ----------------------------------------------------------------- build
    def start_background(self) -> None:
        """Reconstruit l'index si nécessaire puis le rafraîchit périodiquement (thread daemon)."""
        if self._thread and self._thread.is_alive():
            return

        def loop():
            if time.time() - self.last_build > config.INDEX_REFRESH_MINUTES * 60 or self.count == 0:
                self.build()
            while True:
                time.sleep(config.INDEX_REFRESH_MINUTES * 60)
                self.build()

        self._thread = threading.Thread(target=loop, daemon=True, name="file-index")
        self._thread.start()

    def build(self) -> None:
        """Parcourt les disques et remplace l'index d'un bloc (les recherches restent possibles pendant ce temps)."""
        if self.building:
            return
        self.building = True
        self.progress = 0
        skip = {s.lower() for s in config.INDEX_EXCLUDE_DIRS}
        t0 = time.time()
        db = self._connect()
        try:
            db.executescript("""
                DROP TABLE IF EXISTS files_new;
                CREATE TABLE files_new (
                    id INTEGER PRIMARY KEY, path TEXT, name_lc TEXT, ext TEXT,
                    size INTEGER, mtime REAL, is_dir INTEGER);
            """)
            batch: list[tuple] = []

            def flush():
                db.executemany("INSERT INTO files_new(path,name_lc,ext,size,mtime,is_dir) VALUES (?,?,?,?,?,?)", batch)
                batch.clear()

            for drive in config.INDEX_DRIVES:
                root = f"{drive}:\\" if len(drive) == 1 else drive
                if not os.path.isdir(root):
                    continue
                stack = [root]
                while stack:
                    d = stack.pop()
                    try:
                        with os.scandir(d) as it:
                            for e in it:
                                try:
                                    is_dir = e.is_dir(follow_symlinks=False)
                                    if is_dir:
                                        if e.name.lower() in skip:
                                            continue
                                        stack.append(e.path)
                                        st = e.stat(follow_symlinks=False)
                                        batch.append((e.path, _norm(e.name), "", 0, st.st_mtime, 1))
                                    else:
                                        st = e.stat(follow_symlinks=False)
                                        ext = os.path.splitext(e.name)[1].lower().lstrip(".")
                                        batch.append((e.path, _norm(e.name), ext, st.st_size, st.st_mtime, 0))
                                    self.progress += 1
                                    if len(batch) >= 5000:
                                        flush()
                                except OSError:
                                    continue
                    except OSError:
                        continue
            flush()
            with self._lock:
                db.executescript("""
                    DROP TABLE IF EXISTS files_fts;
                    DROP TABLE IF EXISTS files;
                    ALTER TABLE files_new RENAME TO files;
                    CREATE VIRTUAL TABLE files_fts USING fts5(
                        name_lc, content='files', content_rowid='id', tokenize='trigram');
                    INSERT INTO files_fts(rowid, name_lc) SELECT id, name_lc FROM files;
                """)
                self.last_build = time.time()
                db.execute("INSERT OR REPLACE INTO meta VALUES ('last_build', ?)", (str(self.last_build),))
                db.commit()
                self.count = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            self.last_duration = time.time() - t0
        finally:
            db.close()
            self.building = False

    # ---------------------------------------------------------------- search
    def search(self, query: str, folder: str = "", ext: str = "", limit: int = 20, dirs_only: bool = False) -> list[dict]:
        q = _norm(query.strip())
        words = [w for w in re.split(r"\s+", q) if w]
        if not words:
            return []
        folder_lc = _norm(folder.strip().strip('"'))
        ext = ext.lower().lstrip(".")
        with self._lock:
            db = self._connect()
            try:
                if all(len(w) >= 3 for w in words):
                    fts_q = " AND ".join('"' + w.replace('"', '""') + '"' for w in words)
                    sql = ("SELECT f.path, f.name_lc, f.ext, f.size, f.mtime, f.is_dir FROM files_fts "
                           "JOIN files f ON f.id = files_fts.rowid WHERE files_fts MATCH ?")
                    params: list = [fts_q]
                else:  # mots trop courts pour les trigrammes : LIKE (plus lent mais correct)
                    sql = "SELECT path, name_lc, ext, size, mtime, is_dir FROM files WHERE " + " AND ".join("name_lc LIKE ?" for _ in words)
                    params = [f"%{w}%" for w in words]
                if ext:
                    sql += " AND ext = ?"
                    params.append(ext)
                if dirs_only:
                    sql += " AND is_dir = 1"
                sql += " LIMIT 4000"
                rows = db.execute(sql, params).fetchall()
            except sqlite3.OperationalError as exc:
                return [{"error": f"index indisponible ({exc})"}]
            finally:
                db.close()

        def score(r):
            path, name_lc, _ext, _size, mtime, _is_dir = r
            s = 0.0
            if name_lc == q:
                s += 100
            elif os.path.splitext(name_lc)[0] == q:
                s += 90
            elif name_lc.startswith(q):
                s += 50
            s -= path.count("\\") * 0.5          # les chemins courts d'abord
            s += min(mtime / 1e9, 2)              # léger bonus aux fichiers récents
            pl = path.lower()
            if any(k in pl for k in ("\\appdata\\", "\\programdata\\", "\\program files", "\\.next\\", "\\.cache\\", "\\cache\\", "\\windows kits\\")):
                s -= 40                           # fichiers techniques : en dernier
            if any(k in pl for k in ("\\desktop\\", "\\documents\\", "\\downloads\\", "\\pictures\\", "\\videos\\", "\\onedrive\\")) or pl.startswith("d:\\"):
                s += 15                           # dossiers personnels : en premier
            return s

        rows.sort(key=score, reverse=True)
        out = []
        for path, _name_lc, _e, size, mtime, is_dir in rows:
            if folder_lc and folder_lc not in _norm(path):
                continue
            out.append({"path": path, "size": size, "mtime": mtime, "is_dir": bool(is_dir)})
            if len(out) >= limit:
                break
        return out

    def status(self) -> str:
        if self.building:
            return f"index en cours de construction ({self.progress} éléments parcourus)"
        if self.count == 0:
            return "index vide"
        age = (time.time() - self.last_build) / 60
        return f"{self.count} fichiers et dossiers indexés, mis à jour il y a {age:.0f} min"


_instance: FileIndex | None = None


def get() -> FileIndex:
    global _instance
    if _instance is None:
        _instance = FileIndex()
    return _instance
