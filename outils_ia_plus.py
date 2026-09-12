# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Compléments de la boîte « ia » : sous-agents qui travaillent en fond, correction d'un bug sur une branche, prototype
d'application depuis une idée, maquette Figma vers code, explication d'une base de code, fine-tuning LoRA,
amélioration de prompt, prompts vidéo, génération d'images (ComfyUI).

Importé par outils_ia.py.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TACHES = config.ROOT / "memoire" / "taches_fond.json"
PROMPTS = config.ROOT / "memoire" / "prompts.json"
_TACHES: dict[str, dict] = {}


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _prevenir(texte: str) -> None:
    try:
        import noyau

        if "dire" in noyau.hooks:
            noyau.hooks["dire"](texte)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Sous-agents
# --------------------------------------------------------------------------
_ROLES = {
    "généraliste": "Tu es un agent autonome qui accomplit une tâche de bout en bout avec les outils, sans poser de question.",
    "exécutant méthodique": "Tu exécutes la tâche étape par étape avec les outils, tu vérifies chaque résultat, tu continues jusqu'au bout sans poser de question.",
    "développeur": "Tu es un développeur senior : tu lis le code avec read_file / search_in_files, tu modifies avec write_file, tu lances les tests (run_tests), tu itères jusqu'à ce que ça passe.",
    "chercheur": "Tu es un chercheur : tu utilises web_search, fetch_url et research pour rassembler des faits sourcés, puis tu rends une synthèse structurée.",
    "rédacteur": "Tu es un rédacteur : tu produis un texte fini, structuré, sans remplissage, que tu écris dans un fichier avec write_file.",
}


def delegate_task(goal: str, role: str = "généraliste", toolbox: str = "", wait: bool = False, max_turns: int = 14) -> str:
    """Confie une tâche à un sous-agent spécialisé (développeur, chercheur, rédacteur…) qui travaille en fond avec les outils et te prévient à la fin.

    Args:
        goal: Le but complet et précis.
        role: "généraliste", "exécutant méthodique", "développeur", "chercheur" ou "rédacteur".
        toolbox: Boîte à outils à lui ouvrir (vide = aucune en plus des outils de base).
        wait: True pour attendre le résultat (jusqu'à 10 min).
        max_turns: Nombre max d'allers-retours avec le modèle.
    """
    import tools
    from agent import run_turn

    tid = "t-" + uuid.uuid4().hex[:6]
    systeme = (config.SYSTEM_PROMPT.split("- BOÎTES À OUTILS")[0] + "\n- " + _ROLES.get(role, _ROLES["généraliste"])
               + "\n- Quand la tâche est finie, réponds par un compte rendu court commençant par « TERMINÉ : ». Si tu es bloqué, commence par « BLOQUÉ : ».")
    messages = [{"role": "system", "content": systeme}]
    if toolbox:
        messages.append({"role": "user", "content": f"(Ouvre d'abord la boîte « {toolbox} » avec open_toolbox.)"})
    messages.append({"role": "user", "content": goal})
    info = {"id": tid, "but": goal, "role": role, "etat": "en cours", "resultat": "", "t": datetime.now().isoformat(timespec="minutes")}
    _TACHES[tid] = info
    base = _json(TACHES, [])
    if not isinstance(base, list):
        base = []
    base.append(info)
    _save(TACHES, base[-50:])

    def travail():
        modele = getattr(tools, "CURRENT_MODEL", None) or config.MODEL
        resultat = ""
        try:
            for _ in range(max_turns):
                rep = run_turn(messages, modele, show=False) or ""
                resultat = rep.strip()
                if resultat.upper().startswith(("TERMINÉ", "BLOQUÉ", "TERMINE", "BLOQUE")) or not resultat:
                    break
                messages.append({"role": "user", "content": "(Continue jusqu'au bout. Quand c'est fini, commence ta réponse par « TERMINÉ : ».)"})
            info["etat"] = "bloqué" if resultat.upper().startswith(("BLOQUÉ", "BLOQUE")) else "fini"
        except Exception as exc:  # noqa: BLE001
            resultat = f"erreur : {exc}"
            info["etat"] = "erreur"
        info["resultat"] = resultat[:3000]
        b = _json(TACHES, [])
        if isinstance(b, list):
            for x in b:
                if x.get("id") == tid:
                    x.update(info)
            _save(TACHES, b)
        _prevenir(f"Tâche {tid} {info['etat']} : {resultat[:160]}")

    th = threading.Thread(target=travail, daemon=True)
    th.start()
    if wait:
        th.join(600)
        return f"[{tid}] {info['etat']} : {info['resultat'] or 'toujours en cours'}"
    return f"Tâche {tid} confiée à un sous-agent « {role} » : je te préviens quand c'est fini (task_result(\"{tid}\") pour voir)."


def task_result(task_id: str = "") -> str:
    """Résultat d'une tâche confiée à un sous-agent (ou la liste des dernières tâches).

    Args:
        task_id: Identifiant renvoyé par delegate_task (vide = liste).
    """
    base = _json(TACHES, [])
    if not isinstance(base, list):
        base = []
    if not task_id:
        return "\n".join(f"- {t['id']} [{t['etat']}] {t['but'][:60]}" for t in base[-15:] if "id" in t) or "Aucune tâche."
    t = _TACHES.get(task_id) or next((x for x in base if x.get("id") == task_id), None)
    if not t:
        return f"Tâche inconnue : {task_id}."
    return f"[{t['id']}] {t['etat']} — {t['but'][:100]}\n{t.get('resultat') or '(en cours)'}"


def fix_bug_on_branch(repo: str, description: str, test_command: str = "", wait: bool = False) -> str:
    """Un sous-agent corrige un bug sur une branche séparée (fix/…), lance les tests et commit ; la branche reste à relire avant merge.

    Args:
        repo: Dossier du dépôt.
        description: Le bug (symptôme, où, comment le reproduire).
        test_command: Commande de test (ex. "pytest -q"), vide = run_tests.
        wait: Attendre la fin.
    """
    p = Path(repo).expanduser()
    if not (p / ".git").exists():
        return f"Pas un dépôt Git : {p}"
    slug = re.sub(r"\W+", "-", description.lower())[:40].strip("-")
    nom = f"fix/{slug}-{datetime.now():%m%d%H%M}"
    r = subprocess.run(["git", "checkout", "-b", nom], cwd=p, capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        return f"Impossible de créer la branche : {r.stderr[:200]}"
    test = f'run_command("{test_command}")' if test_command else "run_tests"
    but = (f"Dans le dépôt {p}, corrige ce bug : {description}. Méthode : search_in_files et read_file pour localiser, "
           f"write_file pour corriger, puis {test} dans le dépôt ; itère jusqu'à ce que les tests passent, puis git_commit avec un message clair. Ne touche à rien d'autre.")
    return f"Branche {nom} créée. " + delegate_task(but, role="développeur", toolbox="dev", wait=wait)


def prototype_app(idea: str, stack: str = "web", folder: str = "", wait: bool = False) -> str:
    """Prototype d'application depuis une idée : crée le squelette (web statique, python, ou expo) puis un sous-agent écrit une première version fonctionnelle.

    Args:
        idea: L'idée, en quelques phrases (quoi, pour qui, écrans principaux).
        stack: "web" (HTML/CSS/JS), "python" (script ou FastAPI), "expo" (React Native).
        folder: Dossier cible (vide = workspace/proto-<nom>).
        wait: Attendre la fin.
    """
    nom = re.sub(r"\W+", "-", idea.lower())[:30].strip("-") or "proto"
    d = Path(folder).expanduser() if folder else config.WORKSPACE / f"proto-{nom}"
    d.mkdir(parents=True, exist_ok=True)
    if stack == "web":
        (d / "index.html").write_text(f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>{nom}</title><link rel='stylesheet' href='style.css'></head><body><main id='app'></main><script src='app.js'></script></body></html>", encoding="utf-8")
        (d / "style.css").write_text(":root{font-family:system-ui;color-scheme:light dark}body{margin:0}main{max-width:960px;margin:0 auto;padding:24px}", encoding="utf-8")
        (d / "app.js").write_text("// point d'entrée\n", encoding="utf-8")
        lancer = f'open_file("{d / "index.html"}")'
    elif stack == "expo":
        r = subprocess.run(["npx", "-y", "create-expo-app@latest", str(d), "--template", "blank"], capture_output=True, text=True, timeout=900, shell=True)
        lancer = "expo_start"
        if r.returncode != 0:
            return f"create-expo-app a échoué : {(r.stderr or r.stdout)[-300:]}"
    else:
        (d / "main.py").write_text('"""Prototype."""\n\n\ndef main() -> None:\n    print("prototype")\n\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
        (d / "requirements.txt").write_text("", encoding="utf-8")
        lancer = f'run_command("python {d / "main.py"}")'
    but = (f"Dans le dossier {d} (stack {stack}), construis un prototype fonctionnel de : {idea}. Écris les fichiers avec write_file, "
           f"garde ça simple et propre, puis vérifie que ça se lance ({lancer}). Termine par TERMINÉ : et la liste des fichiers.")
    return f"Squelette {stack} créé dans {d}. " + delegate_task(but, role="développeur", toolbox="dev", wait=wait)


def figma_to_code(file_key: str, node_id: str = "", write_json: bool = True) -> str:
    """Lit une maquette Figma (API, FIGMA_TOKEN) et en extrait la structure (cadres, textes, couleurs, tailles, polices) pour que tu écrives le HTML/CSS.

    Args:
        file_key: La clé du fichier (dans l'URL figma.com/file/<clé>/…).
        node_id: Id du cadre à convertir (vide = première page).
        write_json: Écrire la structure simplifiée dans workspace/figma-<clé>.json.
    """
    token = getattr(config, "FIGMA_TOKEN", "")
    if not token:
        return "Il manque FIGMA_TOKEN dans config.py (Figma > Settings > Personal access tokens)."
    import requests

    h = {"X-Figma-Token": token}
    try:
        if node_id:
            data = requests.get(f"https://api.figma.com/v1/files/{file_key}/nodes", params={"ids": node_id}, headers=h, timeout=60).json()
            racine = list(data["nodes"].values())[0]["document"]
        else:
            data = requests.get(f"https://api.figma.com/v1/files/{file_key}", params={"depth": 4}, headers=h, timeout=60).json()
            racine = data["document"]["children"][0]
    except Exception as exc:  # noqa: BLE001
        return f"Figma injoignable ou clé invalide : {exc}"

    def couleur(fills):
        for f in fills or []:
            if f.get("type") == "SOLID" and f.get("visible", True):
                c = f["color"]
                return "#%02x%02x%02x" % (int(c["r"] * 255), int(c["g"] * 255), int(c["b"] * 255))
        return None

    def simplifier(n, prof=0):
        if prof > 6:
            return None
        bb = n.get("absoluteBoundingBox") or {}
        s = {"type": n.get("type"), "nom": n.get("name"), "x": bb.get("x"), "y": bb.get("y"), "w": bb.get("width"), "h": bb.get("height")}
        if n.get("type") == "TEXT":
            st = n.get("style", {})
            s.update({"texte": n.get("characters"), "police": st.get("fontFamily"), "taille": st.get("fontSize"),
                      "poids": st.get("fontWeight"), "couleur": couleur(n.get("fills"))})
        else:
            fond = couleur(n.get("fills"))
            if fond:
                s["fond"] = fond
            if n.get("cornerRadius"):
                s["rayon"] = n["cornerRadius"]
            if n.get("layoutMode"):
                s.update({"layout": n["layoutMode"], "gap": n.get("itemSpacing"),
                          "padding": [n.get("paddingTop"), n.get("paddingRight"), n.get("paddingBottom"), n.get("paddingLeft")]})
        enfants = [e for e in (simplifier(c, prof + 1) for c in n.get("children", [])[:40]) if e]
        if enfants:
            s["enfants"] = enfants
        return s

    arbre = simplifier(racine)
    texte = json.dumps(arbre, ensure_ascii=False, indent=1)
    if write_json:
        out = config.WORKSPACE / f"figma-{file_key[:8]}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(texte, encoding="utf-8")
    return (f"Structure de « {racine.get('name')} » ({len(texte)} caractères) :\n{texte[:5000]}\n\n"
            "Écris le HTML/CSS correspondant (flex selon layout, couleurs, polices, tailles), avec write_file.")


def explain_codebase(path: str, depth: int = 2) -> str:
    """Explique une base de code inconnue : arborescence, langages, points d'entrée, scripts, README, plus gros fichiers.

    Args:
        path: Dossier du projet.
        depth: Profondeur de l'arborescence.
    """
    p = Path(path).expanduser()
    if not p.is_dir():
        return f"Dossier introuvable : {p}"
    ignore = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target"}
    exts: dict[str, int] = {}
    gros = []
    lignes: list[str] = []

    def arbre(d: Path, prof: int, prefixe: str = ""):
        if prof > depth:
            return
        try:
            entrees = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:  # noqa: BLE001
            return
        for e in entrees[:40]:
            if e.name in ignore or e.name.startswith("."):
                continue
            lignes.append(f"{prefixe}{e.name}{'/' if e.is_dir() else ''}")
            if e.is_dir():
                arbre(e, prof + 1, prefixe + "  ")

    arbre(p, 1)
    for f in p.rglob("*"):
        if any(x in f.parts for x in ignore) or not f.is_file():
            continue
        exts[f.suffix] = exts.get(f.suffix, 0) + 1
        try:
            gros.append((f.stat().st_size, str(f.relative_to(p))))
        except Exception:  # noqa: BLE001
            pass
    gros.sort(reverse=True)
    entrees = [n for n in ("main.py", "app.py", "manage.py", "server.py", "index.js", "index.ts", "src/main.ts", "src/index.ts",
                           "src/App.tsx", "app/page.tsx", "cmd/main.go", "Program.cs") if (p / n).exists()]
    scripts = ""
    if (p / "package.json").exists():
        try:
            pk = json.loads((p / "package.json").read_text(encoding="utf-8"))
            scripts = ", ".join(f"{k}: {v}" for k, v in list(pk.get("scripts", {}).items())[:8])
            entrees.append(f"package.json main={pk.get('main', '')}")
        except Exception:  # noqa: BLE001
            pass
    readme = ""
    for n in ("README.md", "readme.md", "README.rst", "README.txt"):
        if (p / n).exists():
            readme = (p / n).read_text(encoding="utf-8", errors="replace")[:1200]
            break
    top_ext = sorted(exts.items(), key=lambda x: -x[1])[:8]
    return ("## Arborescence\n" + "\n".join(lignes[:120]) + "\n\n## Langages (fichiers) : " + ", ".join(f"{e or 'sans ext'} {n}" for e, n in top_ext)
            + "\n## Points d'entrée : " + (", ".join(entrees) or "non évidents") + (f"\n## Scripts : {scripts}" if scripts else "")
            + "\n## Plus gros fichiers : " + ", ".join(f"{n} ({s//1024} Ko)" for s, n in gros[:6])
            + (f"\n\n## README\n{readme}" if readme else "")
            + "\n\nExplique à l'utilisateur : ce que fait le projet, comment il est organisé, par où commencer pour le modifier.")


# --------------------------------------------------------------------------
# Modèles et prompts
# --------------------------------------------------------------------------
_SCRIPT_LORA = '''"""Fine-tuning LoRA généré par Jarvis."""
import json, torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, DataCollatorForLanguageModeling

BASE = {base!r}
DATA = {data!r}
OUT = {out!r}
tok = AutoTokenizer.from_pretrained(BASE)
tok.pad_token = tok.pad_token or tok.eos_token
model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="auto")
model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
rows = []
for l in open(DATA, encoding="utf-8"):
    try:
        d = json.loads(l)
    except Exception:
        continue
    if "prompt" in d:
        rows.append(tok.apply_chat_template([{{"role": "user", "content": d["prompt"]}}, {{"role": "assistant", "content": d["response"]}}], tokenize=False))
ds = Dataset.from_dict({{"text": rows}}).map(lambda x: tok(x["text"], truncation=True, max_length=1024), batched=True, remove_columns=["text"])
Trainer(model=model, args=TrainingArguments(OUT, num_train_epochs={epochs}, per_device_train_batch_size=2, gradient_accumulation_steps=4, learning_rate=2e-4, logging_steps=5, save_strategy="epoch", bf16=True, report_to=[]),
        train_dataset=ds, data_collator=DataCollatorForLanguageModeling(tok, mlm=False)).train()
model.save_pretrained(OUT)
tok.save_pretrained(OUT)
print("TERMINE", OUT)
'''


def finetune_lora(dataset_path: str, base_model: str = "", output_name: str = "jarvis-perso", epochs: int = 2, mode: str = "auto") -> str:
    """Fine-tuning sur tes données : LoRA (transformers + peft, GPU) si peft est installé, sinon un « profil » Ollama (Modelfile avec exemples) immédiat.

    Args:
        dataset_path: Fichier JSONL avec des lignes {"prompt": "...", "response": "..."} (ou {"messages": [...]}).
        base_model: Modèle de base HuggingFace (LoRA) ou Ollama (profil). Vide = choix automatique.
        output_name: Nom du modèle produit.
        epochs: Nombre d'époques (LoRA).
        mode: "auto", "lora" ou "ollama".
    """
    p = Path(dataset_path).expanduser()
    if not p.exists():
        return f"Introuvable : {p}"
    exemples = []
    for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        if "prompt" in d and "response" in d:
            exemples.append((d["prompt"], d["response"]))
        elif "messages" in d:
            us = [m["content"] for m in d["messages"] if m.get("role") == "user"]
            ass = [m["content"] for m in d["messages"] if m.get("role") == "assistant"]
            if us and ass:
                exemples.append((us[-1], ass[-1]))
    if not exemples:
        return "Aucun exemple lisible : une ligne JSON par exemple, avec prompt et response."
    try:
        import peft  # noqa: F401
        import transformers  # noqa: F401

        peft_ok = True
    except Exception:  # noqa: BLE001
        peft_ok = False
    if mode == "lora" or (mode == "auto" and peft_ok):
        if not peft_ok:
            return "LoRA demande les paquets peft, transformers, datasets, accelerate (pip install peft datasets accelerate)."
        base = base_model or "Qwen/Qwen2.5-1.5B-Instruct"
        script = config.WORKSPACE / "finetune_lora.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_SCRIPT_LORA.format(base=base, data=str(p), out=str(config.WORKSPACE / output_name), epochs=int(epochs)), encoding="utf-8")
        log = config.WORKSPACE / f"{output_name}-train.log"
        subprocess.Popen([str(config.ROOT / ".venv" / "Scripts" / "python.exe"), str(script)], stdout=log.open("w"), stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        return (f"Entraînement LoRA lancé sur {base} avec {len(exemples)} exemples ({epochs} époques), journal : {log}. "
                f"À la fin, l'adaptateur sera dans {config.WORKSPACE / output_name} (conversion GGUF pour Ollama : llama.cpp convert_lora_to_gguf).")
    base = base_model or getattr(config, "MODEL", "gemma4:12b")
    mf = config.WORKSPACE / f"Modelfile-{output_name}"
    mf.parent.mkdir(parents=True, exist_ok=True)
    systeme = "Tu réponds dans le style et avec les connaissances des exemples suivants.\n" + "\n".join(f"Q : {q[:300]}\nR : {r[:400]}" for q, r in exemples[:25])
    mf.write_text(f'FROM {base}\nSYSTEM """{systeme}"""\n', encoding="utf-8")
    r = subprocess.run(["ollama", "create", output_name, "-f", str(mf)], capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
    if r.returncode != 0:
        return f"ollama create a échoué : {(r.stderr or r.stdout)[-300:]}"
    return (f"Profil « {output_name} » créé dans Ollama à partir de {base} avec {min(len(exemples), 25)} exemples en contexte (pas un vrai entraînement : "
            f"pour un LoRA, installe peft/datasets/accelerate). switch_model(\"{output_name}\") pour l'essayer.")


def improve_prompt(prompt: str, goal: str = "", save_as: str = "") -> str:
    """Améliore un prompt : diagnostic (rôle, contexte, format, exemples, contraintes, critères) puis tu produis la version réécrite ; peut l'enregistrer.

    Args:
        prompt: Le prompt actuel.
        goal: Ce que le prompt doit obtenir.
        save_as: Nom sous lequel enregistrer (vide = ne pas enregistrer).
    """
    manques = []
    bas = prompt.lower()
    if not re.search(r"\b(tu es|you are|agis en|en tant que)\b", bas):
        manques.append("rôle explicite")
    if len(prompt) < 200:
        manques.append("contexte (qui, pour quoi, contraintes)")
    if not re.search(r"(format|json|markdown|liste|tableau|en \d+ (mots|lignes|points))", bas):
        manques.append("format de sortie attendu")
    if "exemple" not in bas and "example" not in bas:
        manques.append("un exemple de bonne réponse")
    if not re.search(r"(ne pas|n'|jamais|évite|interdit|sans )", bas):
        manques.append("ce qu'il ne faut pas faire")
    if not re.search(r"(critère|vérifie|avant de répondre|étape)", bas):
        manques.append("critères de qualité ou étapes")
    if save_as:
        base = _json(PROMPTS, {})
        base[save_as] = {"prompt": prompt, "but": goal, "t": datetime.now().isoformat(timespec="minutes")}
        _save(PROMPTS, base)
    return (f"Prompt actuel ({len(prompt)} caractères)" + (f", but : {goal}" if goal else "") + ".\nIl manque : " + (", ".join(manques) or "rien de structurel")
            + ".\nRéécris-le avec : rôle, contexte, tâche précise, format de sortie, un exemple, interdits, critères de réussite ; garde le sens, retire le flou. "
            "Donne la version améliorée entre guillemets, puis en une ligne ce qui a changé." + (f" (enregistré sous « {save_as} »)" if save_as else ""))


def video_prompt(scene: str, style: str = "cinématographique", duration: int = 5, platform: str = "kling") -> str:
    """Prépare un prompt vidéo pour Kling, Runway, Sora, Pika ou Veo : structure sujet / action / caméra / lumière / style / négatifs, adaptée à la plateforme.

    Args:
        scene: La scène voulue (sujet, action, décor).
        style: Style visuel.
        duration: Durée en secondes.
        platform: "kling", "runway", "sora", "pika" ou "veo".
    """
    conseils = {"kling": "phrase unique, sujet d'abord, mouvement de caméra explicite, éviter les textes à l'écran",
                "runway": "décrire la caméra en premier (dolly, pan, static), puis le sujet, puis l'ambiance ; court",
                "sora": "phrase riche et naturelle, détails physiques cohérents, une seule action principale",
                "pika": "très court, mots-clés séparés par des virgules, préciser -camera et -motion",
                "veo": "description naturelle avec lumière et lentille (35mm, 85mm), un mouvement de caméra"}
    return (f"Plateforme {platform} ({conseils.get(platform, conseils['kling'])}), {duration} s, style {style}.\n"
            f"Scène : {scene}\n\nÉcris le prompt final en anglais avec cette structure : [sujet + détails] [action unique] [mouvement de caméra] "
            "[lumière et heure] [style, lentille, grain] ; puis une ligne Negative: (flou, déformations, texte, watermark). "
            "Propose 2 variantes : une fidèle, une plus audacieuse.")


def generate_image(prompt: str, width: int = 1024, height: int = 1024, steps: int = 25, negative: str = "blurry, low quality, watermark, text") -> str:
    """Génère une image en local avec ComfyUI (doit tourner sur COMFYUI_URL) : envoie un workflow texte-vers-image et récupère l'image.

    Args:
        prompt: Description de l'image (anglais recommandé).
        width: Largeur.
        height: Hauteur.
        steps: Nombre d'étapes.
        negative: Ce qu'on ne veut pas.
    """
    import requests

    url = getattr(config, "COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
    try:
        info = requests.get(f"{url}/object_info/CheckpointLoaderSimple", timeout=5).json()
        ckpts = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except Exception:  # noqa: BLE001
        return (f"ComfyUI ne répond pas sur {url}. Lance-le (ou installe-le : github.com/comfyanonymous/ComfyUI, avec un modèle dans models/checkpoints), "
                "puis réessaie.")
    if not ckpts:
        return "ComfyUI n'a aucun modèle dans models/checkpoints."
    ckpt = next((c for c in ckpts if "xl" in c.lower() or "flux" in c.lower()), ckpts[0])
    wf = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
          "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
          "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
          "4": {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
          "5": {"class_type": "KSampler", "inputs": {"seed": int(time.time()) % 2**31, "steps": int(steps), "cfg": 6.0, "sampler_name": "euler",
                                                   "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0],
                                                   "negative": ["3", 0], "latent_image": ["4", 0]}},
          "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
          "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "jarvis", "images": ["6", 0]}}}
    try:
        pid = requests.post(f"{url}/prompt", json={"prompt": wf}, timeout=30).json()["prompt_id"]
    except Exception as exc:  # noqa: BLE001
        return f"ComfyUI a refusé le workflow : {exc}"
    fin = time.time() + 600
    while time.time() < fin:
        time.sleep(2)
        try:
            h = requests.get(f"{url}/history/{pid}", timeout=10).json()
        except Exception:  # noqa: BLE001
            continue
        if pid in h:
            imgs = [i for o in h[pid]["outputs"].values() for i in o.get("images", [])]
            if not imgs:
                return "ComfyUI a fini sans image (voir sa console)."
            i = imgs[0]
            data = requests.get(f"{url}/view", params={"filename": i["filename"], "subfolder": i.get("subfolder", ""), "type": i.get("type", "output")}, timeout=60).content
            out = config.WORKSPACE / f"image-{datetime.now():%Y%m%d-%H%M%S}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            return f"[[image:{out}]]\nImage générée avec {ckpt} : {out}"
    return "ComfyUI n'a pas fini en 10 minutes."


TOOLS = [delegate_task, task_result, fix_bug_on_branch, prototype_app, figma_to_code, explain_codebase, finetune_lora,
         improve_prompt, video_prompt, generate_image]
