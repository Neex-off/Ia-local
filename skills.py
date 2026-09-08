# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compétences (skills) : fichiers d'instructions spécialisées que le modèle charge à la demande.

Une compétence = un dossier contenant SKILL.md (en-tête YAML `name` / `description`, puis les
instructions) et éventuellement des fichiers de référence. Sources, par priorité :
  1. skills/ dans ce projet (compétences maison, toujours actives)
  2. ~/.claude/skills (compétences personnelles installées pour Claude Code)
  3. ~/.claude/plugins/cache (compétences des plugins)
Pour 2 et 3, seules les compétences listées dans config.SKILLS_ENABLED sont exposées.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import config

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


class Skill:
    def __init__(self, name: str, description: str, path: Path, category: str):
        self.name, self.description, self.path, self.category = name, description, path, category

    def content(self, max_chars: int) -> str:
        text = self.path.read_text(encoding="utf-8", errors="replace")
        text = _FM.sub("", text, count=1).strip()
        extra = sorted(p for p in self.path.parent.rglob("*") if p.is_file() and p.name != "SKILL.md"
                       and p.suffix.lower() in (".md", ".txt", ".json", ".html", ".css", ".js", ".py"))
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[… compétence tronquée à {max_chars} caractères ; fichier complet : {self.path}]"
        if extra:
            text += "\n\nFichiers de référence de cette compétence (lisibles avec read_file) :\n" + "\n".join(
                f"  - {p}" for p in extra[:25])
        return text


def _parse(path: Path) -> tuple[str, str]:
    head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    m = _FM.match(head)
    name = desc = ""
    if m:
        fm = m.group(1)
        n = re.search(r"^name:\s*(.+)$", fm, re.M)
        d = re.search(r"^description:\s*(.+)$", fm, re.M)
        name = n.group(1).strip().strip("\"'") if n else ""
        if d:
            desc = d.group(1).strip().strip("\"'")
            if desc in (">", ">-", "|", "|-"):  # description multi-ligne YAML
                after = fm[d.end():]
                desc = " ".join(line.strip() for line in after.splitlines() if line.startswith((" ", "\t")))[:400]
            desc = re.sub(r"\s+", " ", desc)[:300]
    return name or path.parent.name, desc


_CAT_KEYWORDS = [
    ("design web", r"design|ui|ux|front|css|html|landing|site|brand|seo|access|slides|typo|color|figma"),
    ("animation", r"motion|anim|gsap|three|canvas|shader|framer|remotion|video"),
    ("mobile", r"flutter|dart|swift|ios|android|kotlin|compose|react-native|expo"),
    ("sécurité", r"secur|cyber|bounty|hipaa|phi|compliance|vuln"),
    ("infra", r"docker|kubernetes|deploy|git|network|homelab|ssh|cisco|vlan|vpn|dns|migration|flox|pm2"),
    ("données & IA", r"postgres|sql|prisma|redis|clickhouse|rag|llm|pytorch|ml|mle|agent|prompt|eval|embedding"),
    ("rédaction & business", r"writ|article|market|content|copy|brand|research|investor|finance|billing|email|crosspost|social"),
    ("développement", r"pattern|test|tdd|api|backend|python|django|fastapi|react|vue|nuxt|next|node|java|spring|quarkus|rust|go\b|golang|php|laravel|perl|cpp|c\+\+|csharp|dotnet|fsharp|coding|refactor|error|hexagonal|architecture|build|review"),
]


def _auto_category(path: Path, root: Path) -> str:
    text = (path.parent.name + " " + str(path.relative_to(root))).lower()
    for cat, pattern in _CAT_KEYWORDS:
        if re.search(pattern, text):
            return cat
    return "autres"


class Registry:
    def __init__(self):
        self.skills: dict[str, Skill] = {}
        self.loaded_at = 0.0

    def load(self) -> None:
        found: dict[str, tuple[float, Skill]] = {}
        featured = config.SKILLS_FEATURED
        # 1. compétences maison : toutes, toujours mises en avant
        local = config.ROOT / "skills"
        for p in (sorted(local.rglob("SKILL.md")) if local.is_dir() else []):
            name, desc = _parse(p)
            found[name] = (float("inf"), Skill(name, desc, p, "maison"))
        # 2 et 3 : toutes (SKILLS_ALL) ou seulement les mises en avant ; version la plus récente
        for root in config.SKILL_SOURCES:
            root = Path(root).expanduser()
            if not root.is_dir():
                continue
            for p in root.rglob("SKILL.md"):
                try:
                    name, desc = _parse(p)
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if name not in featured and not config.SKILLS_ALL:
                    continue
                if name not in found or mtime > found[name][0]:
                    found[name] = (mtime, Skill(name, desc, p, featured.get(name) or _auto_category(p, root)))
        self.skills = {k: v[1] for k, v in sorted(found.items())}
        self.loaded_at = time.time()

    def search(self, query: str, limit: int = 25) -> list[Skill]:
        """Compétences dont le nom ou la description contient tous les mots de la requête (au moins un si aucun ne matche tout)."""
        words = [w for w in re.split(r"[\s,;/]+", query.lower()) if w]
        if not words:
            return list(self.skills.values())[:limit]

        def score(s: Skill) -> int:
            hay = (s.name + " " + s.description + " " + s.category).lower()
            hits = sum(1 for w in words if w in hay)
            if hits == 0:
                return 0
            bonus = 3 if any(w in s.name.lower() for w in words) else 0
            return hits * 2 + bonus + (1 if s.category == "maison" or s.name in config.SKILLS_FEATURED else 0)

        ranked = sorted((s for s in self.skills.values() if score(s) > 0), key=score, reverse=True)
        return ranked[:limit]

    def get(self, name: str) -> Skill | None:
        key = name.strip().lower().replace("_", "-").replace(" ", "-")
        if key in self.skills:
            return self.skills[key]
        for k, s in self.skills.items():  # correspondance approchée
            if key in k or k in key:
                return s
        return None

    def by_category(self) -> dict[str, list[Skill]]:
        out: dict[str, list[Skill]] = {}
        for s in self.skills.values():
            out.setdefault(s.category, []).append(s)
        order = ["maison", "design web", "animation", "développement", "rédaction"]
        return {c: out[c] for c in order if c in out} | {c: v for c, v in out.items() if c not in order}

    def prompt_section(self) -> str:
        """Section du prompt système : total + compétences mises en avant par catégorie (le reste via list_skills)."""
        if not self.skills:
            return ""
        featured = {n: s for n, s in self.skills.items() if s.category == "maison" or n in config.SKILLS_FEATURED}
        cats: dict[str, list[str]] = {}
        for n, s in featured.items():
            cats.setdefault(s.category, []).append(n)
        lines = [f"COMPÉTENCES : {len(self.skills)} disponibles. Cherche avec list_skills(\"mot-clé\") puis charge avec use_skill(nom) AVANT une tâche concernée. Les principales :"]
        order = ["maison", "design web", "animation", "développement", "mobile", "sécurité", "infra", "rédaction"]
        for cat in order + [c for c in cats if c not in order]:
            if cat in cats:
                lines.append(f"- {cat} : " + ", ".join(sorted(cats[cat])))
        return "\n".join(lines)


_registry: Registry | None = None


def get() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
        _registry.load()
    return _registry
