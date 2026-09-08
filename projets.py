# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Inventaire des projets de l'utilisateur pour la vue « projets » de l'interface.

Parcourt config.PROJECT_DIRS (profondeur 2), reconnaît un projet à ses marqueurs (.git, package.json,
pubspec.yaml, requirements.txt, Cargo.toml…), lit la branche git courante, les autres branches
et le dépôt distant sans lancer git (fichiers .git/HEAD, refs/heads, packed-refs, config).
Deux projets sont « liés » s'ils partagent le même dépôt distant ou le même nom.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import config

MARKERS = {
    "pubspec.yaml": "Flutter", "package.json": "Node / Web", "requirements.txt": "Python", "pyproject.toml": "Python",
    "Cargo.toml": "Rust", "go.mod": "Go", "pom.xml": "Java", "build.gradle": "Android / Java",
    "CMakeLists.txt": "C / C++", "composer.json": "PHP", "Gemfile": "Ruby", "index.html": "Site web",
}
SKIP = {"node_modules", ".venv", "venv", "__pycache__", ".git", "build", "dist", ".next", ".dart_tool", "Library"}


def _git_info(root: Path) -> dict:
    git = root / ".git"
    info: dict = {"git": False, "branch": "", "branches": [], "remote": ""}
    if not git.is_dir():
        return info
    info["git"] = True
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        info["branch"] = head.split("refs/heads/", 1)[1] if "refs/heads/" in head else head[:8]
    except OSError:
        pass
    branches: set[str] = set()
    heads = git / "refs" / "heads"
    if heads.is_dir():
        for p in heads.rglob("*"):
            if p.is_file():
                branches.add(str(p.relative_to(heads)).replace("\\", "/"))
    packed = git / "packed-refs"
    if packed.is_file():
        try:
            for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
                if " refs/heads/" in line:
                    branches.add(line.split(" refs/heads/", 1)[1].strip())
        except OSError:
            pass
    info["branches"] = sorted(branches)
    cfg = git / "config"
    if cfg.is_file():
        try:
            m = re.search(r"\[remote \"origin\"\][^\[]*?url\s*=\s*(.+)", cfg.read_text(encoding="utf-8", errors="replace"))
            if m:
                info["remote"] = m.group(1).strip()
        except OSError:
            pass
    return info


def _kind(root: Path) -> str:
    kinds = [k for f, k in MARKERS.items() if (root / f).exists()]
    if "Flutter" in kinds:
        return "Flutter"
    if any((root / f).exists() for f in ("next.config.js", "next.config.ts", "next.config.mjs")):
        return "Next.js"
    return kinds[0] if kinds else "Dossier"


def _mtime(root: Path) -> float:
    latest = root.stat().st_mtime
    try:
        for p in list(root.iterdir())[:60]:
            if p.name in SKIP:
                continue
            latest = max(latest, p.stat().st_mtime)
    except OSError:
        pass
    return latest


def _is_project(p: Path) -> bool:
    if (p / "bin" / "flutter").exists() or (p / "bin" / "dart").exists():
        return False  # SDK Flutter/Dart, pas un projet
    return (p / ".git").is_dir() or any((p / f).exists() for f in MARKERS)


_github_cache: tuple[float, list[dict]] = (0.0, [])


def github_repos() -> list[dict]:
    """Dépôts GitHub de l'utilisateur (config.GITHUB_USER), privés inclus si un jeton est fourni. Cache 10 min."""
    global _github_cache
    import os
    import time

    import requests

    ts, cached = _github_cache
    if cached and time.time() - ts < 600:
        return cached
    user = (config.GITHUB_USER or "").strip()
    token = (os.environ.get("GITHUB_TOKEN") or config.GITHUB_TOKEN or "").strip()
    if not user and not token:
        return []
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "jarvis-local"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        url = "https://api.github.com/user/repos?per_page=100&affiliation=owner&sort=pushed"
    else:
        url = f"https://api.github.com/users/{user}/repos?per_page=100&sort=pushed"
    repos: list[dict] = []
    try:
        r = requests.get(url, headers=headers, timeout=8)
        r.raise_for_status()
        for it in r.json():
            pushed = it.get("pushed_at") or it.get("updated_at") or ""
            try:
                mt = datetime.fromisoformat(pushed.replace("Z", "+00:00")).timestamp()
            except ValueError:
                mt = 0.0
            repos.append({
                "name": it["name"], "path": it["html_url"], "kind": "GitHub" + (f" · {it['language']}" if it.get("language") else ""),
                "parent": "github.com/" + it["owner"]["login"] + (" · privé" if it.get("private") else ""),
                "git": True, "branch": it.get("default_branch") or "", "branches": [], "remote": it.get("clone_url", ""),
                "modified": datetime.fromtimestamp(mt).strftime("%d/%m/%Y") if mt else "?", "mtime": mt,
                "source": "github", "stars": it.get("stargazers_count", 0), "description": it.get("description") or "",
            })
        _github_cache = (time.time(), repos)
    except Exception:  # noqa: BLE001  (hors ligne, jeton invalide…)
        return cached
    return repos


def _same_remote(a: str, b: str) -> bool:
    def n(u: str) -> str:
        u = u.strip().lower().rstrip("/")
        u = re.sub(r"\.git$", "", u)
        u = re.sub(r"^git@github\.com:", "github.com/", u)
        u = re.sub(r"^https?://", "", u)
        return u
    return bool(a) and bool(b) and n(a) == n(b)


def scan(include_github: bool = True, include_local: bool = True) -> list[dict]:
    projects = _scan_local() if include_local else []
    if include_github:
        gh = github_repos()
        local_remotes = [p for p in projects if p.get("remote")]
        for g in gh:
            g = dict(g)
            g["links"] = [p["name"] for p in local_remotes if _same_remote(p["remote"], g["remote"])]
            for p in projects:
                if _same_remote(p.get("remote", ""), g["remote"]) and g["name"] not in p["links"]:
                    p["links"].append(g["name"] + " (GitHub)")
            projects.append(g)
    projects.sort(key=lambda x: -x["mtime"])
    return projects


def _scan_local() -> list[dict]:
    seen: set[str] = set()
    projects: list[dict] = []
    for base in config.PROJECT_DIRS:
        base = Path(base).expanduser()
        if not base.is_dir():
            continue
        candidates: list[Path] = []
        try:
            for p in base.iterdir():
                if p.is_dir() and p.name not in SKIP and not p.name.startswith("."):
                    candidates.append(p)
                    if not _is_project(p):  # un cran plus bas (ex. Desktop/github/<projet>)
                        try:
                            candidates += [q for q in p.iterdir() if q.is_dir() and q.name not in SKIP and not q.name.startswith(".")]
                        except OSError:
                            pass
        except OSError:
            continue
        for p in candidates:
            key = str(p.resolve()).lower()
            if key in seen or not _is_project(p):
                continue
            seen.add(key)
            g = _git_info(p)
            mt = _mtime(p)
            projects.append({
                "name": p.name, "path": str(p), "kind": _kind(p), "parent": p.parent.name,
                "git": g["git"], "branch": g["branch"], "branches": g["branches"][:12], "remote": g["remote"],
                "modified": datetime.fromtimestamp(mt).strftime("%d/%m/%Y"), "mtime": mt, "source": "local",
            })
    # liens : même dépôt distant ou même nom
    for i, a in enumerate(projects):
        a["links"] = []
        for j, b in enumerate(projects):
            if i == j:
                continue
            same_remote = bool(a["remote"]) and a["remote"].rstrip("/").lower() == b["remote"].rstrip("/").lower()
            same_name = a["name"].lower().replace("-", "_") == b["name"].lower().replace("-", "_")
            if same_remote or same_name:
                a["links"].append(b["name"])
    return projects


def summary(projects: list[dict]) -> str:
    if not projects:
        return "Aucun projet trouvé dans " + ", ".join(str(d) for d in config.PROJECT_DIRS)
    n_gh = sum(1 for p in projects if p.get("source") == "github")
    lines = [f"{len(projects)} projets ({len(projects) - n_gh} sur le PC, {n_gh} sur GitHub) :"]
    for p in projects:
        br = f", branche {p['branch']}" if p["branch"] else ""
        extra = f", {len(p['branches'])} branches" if len(p["branches"]) > 1 else ""
        links = f", lié à {', '.join(p['links'])}" if p["links"] else ""
        lines.append(f"- {p['name']} ({p['kind']}{br}{extra}{links}, modifié le {p['modified']}) — {p['path']}")
    return "\n".join(lines)
