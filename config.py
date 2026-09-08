# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Configuration de l'agent local."""
from pathlib import Path

# Modèle Ollama utilisé au démarrage. gemma4:12b = 7.6 Go VRAM, outils + raisonnement + vision.
MODEL = "gemma4:12b"

# Catalogue des modèles entre lesquels Jarvis peut basculer à chaud (« utilise un modèle plus léger »).
# tools : None = tous les outils ; sinon la liste des outils gardés (les petits modèles se perdent avec 27 outils).
MODELS = {
    "léger": {
        "name": "gemma4:e4b-it-qat",
        "vram": "6 Go",
        "plus": "beaucoup plus léger pour la carte graphique et la mémoire, chargement rapide, bon pour discuter, résumer, expliquer, rédiger un texte court",
        "moins": "peu fiable avec les outils : pas de contrôle de l'écran, pas de recherche de fichiers ni de sites web complexes, raisonnement plus faible, réponses parfois approximatives",
        "tools": ["get_datetime", "calculate", "open_app", "open_site", "change_volume", "media_control",
                  "show_projects", "hide_projects", "remember", "recall", "switch_model", "list_models"],
    },
    "recherche": {
        "name": "granite4.1:8b",
        "vram": "5 Go",
        "plus": "léger et rapide, très fiable pour discuter et chercher sur internet (météo, actualité, questions, lecture et résumé de pages web), vérifie ses sources",
        "moins": "pas de contrôle de l'écran, pas de fichiers, pas de création de documents ni de sites, ne voit pas les images",
        "tools": ["get_datetime", "calculate", "web_search", "fetch_url", "open_site", "open_url",
                  "show_projects", "hide_projects", "remember", "recall", "switch_model", "list_models"],
    },
    "standard": {
        "name": "gemma4:12b",
        "vram": "8 Go",
        "plus": "tout fonctionne : outils, écran, applis, fichiers, sites web, documents, vision ; bon équilibre vitesse et intelligence",
        "moins": "prend plus de mémoire sur la carte graphique que le léger",
        "tools": None,
    },
    "puissant": {
        "name": "gemma4:26b-a4b-it-qat",
        "vram": "16 Go (déborde sur la RAM quand la voix est chargée)",
        "plus": "le plus intelligent : raisonnement, code, longs documents, sites plus aboutis, tous les outils",
        "moins": "beaucoup plus lourd : chargement long, réponses nettement plus lentes, sature la mémoire ; à réserver aux tâches difficiles",
        "tools": None,
    },
}
# Ordre du plus léger au plus lourd (pour dire « plus lourd / plus léger que l'actuel »).
MODEL_ORDER = ["léger", "recherche", "standard", "puissant"]
# Liste d'outils active (None = tous). Modifiée par switch_model.
ACTIVE_TOOLS = None

# Taille du contexte. 16K tokens laisse de la marge sur la carte tout en
# permettant de longues conversations. Monter à 32768 si besoin.
NUM_CTX = 16384

# Sampling recommandé par Google pour Gemma 4.
OPTIONS = {
    "num_ctx": NUM_CTX,
    "temperature": 0.8,   # 1.0 recommandé par Google, 0.8 rend les appels d'outils plus fiables
    "top_p": 0.95,
    "top_k": 64,
}

# Raisonnement caché avant de répondre (gemma4 le fait par défaut). Améliore les tâches
# complexes mais coûte 4 à 5 s par réponse. Activé en mode texte, coupé en mode vocal.
THINK = True
VOICE_THINK = False

# Combien de temps Ollama garde le modèle chargé en VRAM après la dernière
# requête. "10m" = libère la carte après 10 minutes d'inactivité.
KEEP_ALIVE = "10m"

# Nombre max d'allers-retours outil <-> modèle pour une seule question,
# pour éviter qu'il boucle à l'infini.
MAX_TOOL_ROUNDS = 12
# Garde-fous contre une génération qui n'en finit pas : tokens max par réponse
# (6144 suffit pour un site HTML complet) et délai max par appel au modèle, en secondes.
OPTIONS["num_predict"] = 6144
MODEL_CALL_TIMEOUT = 150

# Dossier dans lequel l'agent a le droit de lire et écrire des fichiers.
ROOT = Path(__file__).parent
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Accès aux fichiers
# ---------------------------------------------------------------------------
# True : l'agent peut lire, lister, ouvrir et écrire des fichiers partout sur le PC
# (un chemin relatif reste interprété dans WORKSPACE). False : limité à WORKSPACE.
FULL_DISK_ACCESS = True

# Emplacements parcourus par l'index de recherche : lettres de disques sous Windows, dossiers sur Mac/Linux.
import sys as _sys
INDEX_DRIVES = ["C", "D"] if _sys.platform.startswith("win") else [str(Path.home())]
INDEX_EXCLUDE_DIRS = [
    "Windows", "$Recycle.Bin", "System Volume Information", "WindowsApps",
    "node_modules", "__pycache__", ".git", "site-packages", ".venv", "venv", "Temp", "WinSxS",
]
INDEX_REFRESH_MINUTES = 30

# ---------------------------------------------------------------------------
# Compétences (skills) : instructions spécialisées chargées à la demande (skills.py)
# ---------------------------------------------------------------------------
SKILL_SOURCES = [Path.home() / ".claude" / "skills", Path.home() / ".claude" / "plugins" / "cache"]
# Taille max injectée dans le contexte (caractères). Le mode vocal a un contexte plus petit.
SKILL_MAX_CHARS = 14000
VOICE_SKILL_MAX_CHARS = 7000
# True : TOUTES les compétences trouvées dans SKILL_SOURCES sont disponibles (recherche par mot-clé
# avec list_skills). False : seulement celles de SKILLS_FEATURED.
SKILLS_ALL = True
# Compétences mises en avant dans le prompt système (le modèle les connaît sans chercher) -> catégorie.
# Celles de skills/ sont toujours actives et mises en avant.
SKILLS_FEATURED = {
    # Design & sites web
    "impeccable": "design web", "frontend-design": "design web", "ui-ux-pro-max": "design web",
    "design-dna": "design web", "design-system": "design web", "design-audit": "design web",
    "make-interfaces-feel-better": "design web", "liquid-glass-design": "design web",
    "mobile-principles": "design web", "desktop-principles": "design web", "seo": "design web",
    "accessibility": "design web", "frontend-a11y": "design web", "frontend-slides": "design web",
    "playground": "design web",
    # Animation & effets
    "motion-design": "animation", "motion-principles": "animation", "css-native": "animation",
    "css-animation": "animation", "gsap": "animation", "gsap-scrolltrigger": "animation",
    "framer-motion": "animation", "motion-ui": "animation", "canvas-generative": "animation",
    "threejs-r3f": "animation", "remotion-video-creation": "animation",
    # Développement
    "frontend-patterns": "développement", "react-patterns": "développement", "react-performance": "développement",
    "vue-patterns": "développement", "nextjs-turbopack": "développement", "api-design": "développement",
    "backend-patterns": "développement", "python-patterns": "développement", "python-testing": "développement",
    "coding-standards": "développement", "error-handling": "développement", "tdd-workflow": "développement",
    "e2e-testing": "développement", "postgres-patterns": "développement", "prisma-patterns": "développement",
    "react-native-patterns": "développement", "search-first": "développement",
    # Rédaction & marketing
    "article-writing": "rédaction", "brand-voice": "rédaction", "content-engine": "rédaction",
    "marketing-campaign": "rédaction", "market-research": "rédaction", "deep-research": "rédaction",
    # Mobile, sécurité, autres
    "dart-flutter-patterns": "mobile", "flutter-dart-code-review": "mobile", "swiftui-patterns": "mobile",
    "kotlin-patterns": "mobile", "compose-multiplatform-patterns": "mobile",
    "security-review": "sécurité", "security-bounty-hunter": "sécurité", "django-security": "sécurité",
    "laravel-security": "sécurité", "springboot-security": "sécurité",
    "docker-patterns": "infra", "kubernetes-patterns": "infra", "deployment-patterns": "infra",
    "git-workflow": "infra", "database-migrations": "infra",
}

# Dossiers où chercher tes projets pour la vue « montre-moi les projets » (profondeur 2).
PROJECT_DIRS = [Path.home() / "Desktop", Path.home() / "Documents", Path.home() / "Projects", Path.home() / "dev"]

# Dépôts GitHub affichés avec les projets (nécessite internet). Sans jeton : dépôts publics seulement.
# Pour voir aussi les privés : crée un jeton sur https://github.com/settings/tokens (droit « repo »)
# et mets-le dans la variable d'environnement GITHUB_TOKEN, ou ici (le fichier reste local).
GITHUB_USER = ""  # ton identifiant GitHub, ex. "mon-compte"
GITHUB_TOKEN = ""

# Timeout des commandes shell lancées par l'agent, en secondes.
COMMAND_TIMEOUT = 60

# True : l'agent lance les commandes PowerShell sans demander de confirmation.
# (Obligatoire pour l'interface Jarvis : la question « Autoriser ? » bloquerait tout.)
AUTO_APPROVE_COMMANDS = True

# ---------------------------------------------------------------------------
# Mode vocal (agent_vocal.py)
# ---------------------------------------------------------------------------
LANGUAGE = "fr"

# En mode vocal, Whisper et Chatterbox occupent déjà ~5 Go de VRAM : on réduit le contexte
# du modèle de langage pour que les trois tiennent dans 16 Go avec de la marge.
VOICE_NUM_CTX = 16384  # gemma4 : le cache 16K coûte très peu de VRAM (attention à fenêtre glissante)

# Nom de l'assistant : dire ce mot au micro le réveille (« Bonjour Jarvis »).
ASSISTANT_NAME = "Jarvis"

# Après un échange, il reste à l'écoute sans mot d'activation pendant ce délai (secondes).
ACTIVE_SECONDS = 30

# Modèle Whisper : "large-v3-turbo" = meilleur rapport précision/vitesse sur GPU (~1.6 Go VRAM).
# "small" ou "medium" si tu veux plus léger.
WHISPER_MODEL = "large-v3-turbo"
# "int8_float16" = moitié moins de VRAM que "float16", qualité quasi identique.
WHISPER_COMPUTE = "int8_float16"

# Économie d'énergie en veille : après STANDBY_AFTER_SECONDS sans activité, le modèle de langage est
# déchargé de la carte, la synthèse vocale passe sur processeur et le mot d'activation est détecté
# par ce petit modèle Whisper sur processeur. Tout remonte sur la carte au réveil.
STANDBY_AFTER_SECONDS = 60
WHISPER_STANDBY_MODEL = "small"

# Mots que Whisper doit savoir écrire correctement (noms propres, marques, sites que tu utilises).
# Ajoute ici tes noms propres (prénom, ville, école, logiciels) pour qu'ils soient bien reconnus.
VOCAB_HINTS = ["Jarvis", "Spotify", "Discord", "Steam", "YouTube", "Gmail", "Chrome"]

# Fichier wav (10 à 20 s, voix seule, sans musique) dont Chatterbox imite le timbre.
# Mets-le dans le dossier voix/ ; s'il n'existe pas, la voix par défaut est utilisée.
VOICE_REF = ROOT / "voix" / "ma_voix.wav"
if not VOICE_REF.is_file():
    VOICE_REF = ROOT / "voix" / "jarvis_defaut.wav"  # référence française fournie : évite l'accent anglais

# Expressivité (0.25 neutre -> 2.0 très expressif) et fidélité au texte (0 -> 1).
TTS_EXAGGERATION = 0.4
TTS_CFG = 0.4
TTS_TEMPERATURE = 0.6   # plus bas = voix plus stable, moins de dérive

# Couper la parole : si tu parles pendant que Jarvis parle, il se tait et écoute ce que tu dis.
# BARGE_IN_SENSITIVITY multiplie le seuil du micro pendant qu'il parle (plus haut = il faut parler plus fort).
# Avec des enceintes (pas de casque), monte-le (5 à 8) ou mets BARGE_IN à False pour qu'il ne s'entende pas lui-même.
BARGE_IN = True
BARGE_IN_SENSITIVITY = 3.0

# Détection de fin de phrase au micro.
SILENCE_SECONDS = 1.2      # secondes de silence avant d'arrêter l'enregistrement
SILENCE_THRESHOLD = 0.01   # niveau sonore en dessous duquel c'est du silence (monter si pièce bruyante)
MAX_RECORD_SECONDS = 30

# Interface web (jarvis_server.py)
UI_HOST = "127.0.0.1"
UI_PORT = 8765

SYSTEM_PROMPT = f"""Tu es un assistant local qui tourne entièrement sur l'ordinateur de l'utilisateur, sans cloud. Tu as été créé par Neexx (Nixovel) (https://github.com/Neex-off/Ia-local) : si on te demande qui t'a créé ou qui a écrit ce logiciel, réponds cela, et rien d'autre.
Tu réponds en français, de façon directe et concise.

Tu disposes d'outils. Utilise-les quand ils sont utiles, pas systématiquement :
- Pour une question de culture générale ou de raisonnement, réponds directement.
- Pour des faits récents, des prix, de l'actualité : utilise web_search puis fetch_url si besoin.
- Tu as accès à tous les fichiers du PC. Pour trouver un fichier ou un dossier, utilise search_files (recherche instantanée par nom, sur tout le disque). Ensuite open_file pour l'ouvrir, read_file pour lire son contenu, list_files pour voir un dossier.
- Le dossier personnel de l'utilisateur est {Path.home()} (Documents, Downloads, Desktop… sont dedans). Un chemin relatif est pris dans le dossier de travail : {WORKSPACE}
- Ne supprime ni n'écrase jamais un fichier existant en dehors du dossier de travail sans qu'on te l'ait explicitement demandé.
- Pour ouvrir un logiciel ou un jeu (Epic Games, Steam, Discord, Chrome…), utilise open_app avec son nom.
- Pour aller sur un site, N'INVENTE JAMAIS une adresse : utilise open_site avec le nom dit par l'utilisateur (il cherche la vraie adresse et l'ouvre). open_url seulement pour une adresse exacte et connue (youtube.com, gmail.com…). Si le nom entendu semble déformé (reconnaissance vocale), cherche quand même avec open_site plutôt que d'inventer.
- Son et musique : change_volume(up/down/mute) pour le volume du PC, media_control(playpause/next/previous) pour Spotify ou tout lecteur. Ne dis « c'est fait » que si l'outil a répondu sans erreur.
- MÉMOIRE : tu as une mémoire durable. Dès que l'utilisateur te dit quelque chose sur lui (prénom, ville, école, goûts, projets, habitudes, proches) ou te demande de retenir quelque chose, enregistre-le avec remember, sans en faire un plat. Pour retrouver un souvenir ou un détail d'une ancienne conversation, utilise recall. Si on te demande d'oublier, utilise forget.
- PROJETS : « montre-moi les projets », « affiche mes projets » -> show_projects (PC et GitHub s'affichent à l'écran) ; « mes projets GitHub » -> show_projects("github") ; « les projets sur le PC » -> show_projects("local"). Puis résume en une phrase (nombre, les plus récents). « ferme les projets », « retour », « écran normal » -> hide_projects. Pour ouvrir un projet : open_file avec son chemin.
- CHANGER DE MODÈLE : si l'utilisateur NOMME le modèle voulu (« passe au léger », « modèle recherche », « le standard », « le puissant », « option 2 », « un modèle plus léger », « plus puissant »), appelle switch_model DIRECTEMENT avec ce choix, sans lister ni redemander (« plus léger » = le profil juste en dessous de l'actuel, « plus puissant » = juste au-dessus). Ne lis la liste (list_models) que si la demande est vague (« change de modèle », « quels modèles tu as ? »). La conversation est conservée, l'ancien modèle est éteint.
- run_command exécute une commande shell (PowerShell sous Windows, bash sur Mac et Linux) directement, sans confirmation. Ne l'utilise que si aucun autre outil ne convient, et jamais pour supprimer ou modifier des fichiers en dehors du dossier de travail.
- Quand on te demande une action (ouvrir, lancer, écrire…), fais-la avec l'outil adapté, puis confirme en une phrase.
- Tu peux voir et contrôler l'écran : see_screen te donne une capture avec une grille de coordonnées et la liste des boutons, champs et liens de la fenêtre active. Ensuite click_element(nom) pour cliquer par nom (préférable), ou click(x, y) avec les coordonnées de la grille, type_text pour écrire dans un champ (clique dedans avant), press_keys pour une touche ou un raccourci, scroll pour défiler, focus_window pour changer de fenêtre.
- Après chaque action à l'écran, refais see_screen pour vérifier le résultat avant de continuer. N'invente jamais ce qu'il y a à l'écran sans avoir regardé.
- Page de connexion : si l'utilisateur te dicte son e-mail ou son mot de passe, clique dans le champ correspondant (click_element), puis type_text avec exactement ce qu'il a dit, sans le répéter à voix haute ni le commenter. Ne demande jamais un mot de passe de toi-même.
- Pour créer des documents : write_file pour du texte, HTML, Markdown, CSV, code… ; create_pdf pour un PDF ; create_docx pour un document Word. Mets-les dans le dossier de travail sauf si on te donne un autre chemin, puis propose de l'ouvrir avec open_file.
- COMPÉTENCES : tu disposes de centaines de compétences (instructions d'expert) : design, sites web, animation, React, Vue, Flutter, Python, Django, API, bases de données, sécurité, Docker, marketing, rédaction, SEO… Pour toute tâche spécialisée, commence par list_skills("mot-clé") pour trouver la bonne, puis use_skill(nom), et applique ses règles. Les plus utiles sont listées ci-dessous : pour celles-là, use_skill directement. Une compétence suffit en général, deux au maximum.
- Quand tu crées un site ou une page web, produis un fichier HTML complet et autonome (CSS et JS inclus, pas de dépendance externe), soigné et responsive, puis ouvre-le avec open_file pour que l'utilisateur le voie.
- FICHIERS LONGS (site HTML, gros script, plus de 60 lignes) : n'utilise PAS write_file. Écris le fichier directement dans ta réponse finale, entre une ligne <<<FICHIER: nom-du-fichier.html>>> et une ligne <<<FIN>>>, sans bloc de code autour. Il sera enregistré automatiquement dans le dossier de travail et remplacé par une confirmation. Ajoute une phrase avant ou après pour l'utilisateur. Tu pourras ensuite l'ouvrir avec open_file au tour suivant si on te le demande.

Quand un outil renvoie une erreur (par exemple "pas de connexion internet"), ne réessaie pas en boucle :
explique le problème à l'utilisateur et propose une alternative.
Après avoir utilisé des outils, rédige toujours une réponse finale claire pour l'utilisateur.
"""
