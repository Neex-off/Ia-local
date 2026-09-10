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
    "mini": {
        "name": "granite4.1:3b",
        "vram": "2 Go (tourne aussi sur processeur seul, vieux PC sans carte graphique)",
        "plus": "minuscule : 2 Go, démarre en une seconde, fonctionne sans carte graphique ; discuter, heure, calculs, ouvrir une appli ou un site, volume, musique, mémoire, agenda",
        "moins": "pas d'écran, pas de fichiers, pas de recherche web, pas de documents ni de sites, ne voit pas les images, raisonnement limité",
        "tools": ["get_datetime", "calculate", "open_app", "open_site", "change_volume", "media_control",
                  "show_agenda", "hide_agenda", "add_event", "list_events", "journal_add", "journal_read",
                  "remember", "recall", "switch_model", "list_models"],
    },
    "léger": {
        "name": "gemma4:e4b-it-qat",
        "vram": "6 Go",
        "plus": "beaucoup plus léger pour la carte graphique et la mémoire, chargement rapide, bon pour discuter, résumer, expliquer, rédiger un texte court",
        "moins": "peu fiable avec les outils : pas de contrôle de l'écran, pas de recherche de fichiers ni de sites web complexes, raisonnement plus faible, réponses parfois approximatives",
        "tools": ["get_datetime", "calculate", "open_app", "open_site", "change_volume", "app_volume", "media_control",
                  "show_projects", "hide_projects", "show_agenda", "hide_agenda", "agenda_month", "add_event", "list_events", "journal_add", "journal_read",
                  "remember", "recall", "switch_model", "list_models"],
    },
    "recherche": {
        "name": "granite4.1:8b",
        "vram": "5 Go",
        "plus": "léger et rapide, très fiable pour discuter et chercher sur internet (météo, actualité, questions, lecture et résumé de pages web), vérifie ses sources",
        "moins": "pas de contrôle de l'écran, pas de fichiers, pas de création de documents ni de sites, ne voit pas les images",
        "tools": ["get_datetime", "calculate", "web_search", "fetch_url", "open_site", "open_url", "research", "learn",
                  "show_projects", "hide_projects", "remember", "recall", "journal_add", "journal_read", "switch_model", "list_models"],
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
MODEL_ORDER = ["mini", "léger", "recherche", "standard", "puissant"]
# Sans carte graphique (ni NVIDIA ni Apple Silicon), démarrer avec le plus petit modèle installé (mini, puis léger)
# plutôt qu'avec MODEL, qui mettrait des minutes à répondre sur processeur. False pour forcer MODEL.
CPU_AUTO_SMALL = True
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
OPTIONS["num_predict"] = 9000   # un site HTML soigné de 400 lignes fait 6 000 à 8 000 tokens
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
VOICE_SKILL_MAX_CHARS = 9000   # la compétence site-web fait ~8500 caractères : elle doit passer entière
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

# Raccourcis de mots vers une application installée (nom du menu Démarrer) ou un site (URL).
# Jarvis les utilise pour « regarde X », « il y a du nouveau sur X », « ouvre X ». Ajoute les tiens.
APP_ALIASES = {
    "mails": "https://mail.google.com", "mail": "https://mail.google.com", "gmail": "https://mail.google.com",
    "boite mail": "https://mail.google.com", "youtube": "https://www.youtube.com", "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com", "twitter": "https://x.com", "x": "https://x.com",
    "linkedin": "https://www.linkedin.com", "github": "https://github.com", "chatgpt": "https://chatgpt.com",
    "agenda": "https://calendar.google.com", "calendrier": "https://calendar.google.com", "drive": "https://drive.google.com",
    "discord": "Discord", "spotify": "Spotify", "steam": "Steam", "epic": "Epic Games Launcher",
    "epic games": "Epic Games Launcher", "navigateur": "Google Chrome", "chrome": "Google Chrome",
    "explorateur": "Explorateur de fichiers", "calculatrice": "Calculatrice", "bloc-notes": "Bloc-notes",
}

# Rappels automatiques de l'agenda, dits à voix haute : minutes avant un rendez-vous à heure fixe,
# heure du point du matin (programme de la journée, événements sans heure compris), fréquence de vérification.
REMINDER_MINUTES = [30, 5]
MORNING_BRIEF_HOUR = 8
REMINDER_CHECK_SECONDS = 30

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
# Comment Jarvis s'adresse à l'utilisateur (« monsieur », « madame », un prénom…) et ce qu'il dit quand on l'appelle.
USER_TITLE = "monsieur"
GREETINGS_WAKE = [
    "Oui monsieur, que puis-je faire pour vous ?",
    "Oui monsieur ?",
    "À votre service, monsieur.",
    "Je vous écoute, monsieur.",
]
GREETING_START = "Jarvis en ligne, monsieur. Que puis-je faire pour vous ?"
# Heure à partir de laquelle, une fois par jour, Jarvis demande de lui-même comment s'est passée la journée
# (et la salle de sport) si rien n'a été noté dans le journal. None pour désactiver.
CHECKIN_HOUR = 20

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
# Anti-écho pour les ENCEINTES : pendant qu'il parle, Jarvis mesure combien de sa propre voix revient dans le micro
# et relève le seuil de coupure d'autant (× ECHO_MARGIN). Il faut donc parler nettement plus fort que l'écho pour
# le couper. Ce qu'il entend est aussi comparé à ce qu'il vient de dire : sa propre phrase est ignorée.
ECHO_SUPPRESSION = True
ECHO_MARGIN = 2.5

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
- SOIS PROACTIF, sans qu'on te le demande : si tu ne sais pas, si tu n'es pas sûr, ou si la question porte sur du récent (actualité, résultats, sorties, prix, météo, horaires, une personne, un produit, un lieu, une date après ta formation), CHERCHE TOI-MÊME avec web_search (puis fetch_url ou research si besoin) avant de répondre. Ne dis jamais « je ne peux pas vérifier », « je n'ai pas accès à internet », « demande-moi de chercher » : cherche.
- POUR TOUTE APPLICATION OU SITE : « regarde Discord », « il y a du nouveau sur WhatsApp ? », « qu'est-ce qu'il se passe sur Steam », « montre-moi YouTube » -> check_app(nom) : il ouvre ou remet devant l'appli (installée ou site), attend, et te donne l'écran ; lis-le et résume ce que tu vois (messages, notifications, contenu). Si le nom est inconnu, list_apps(nom) pour le retrouver. Les mots courants (mails, agenda, discord, spotify…) sont déjà reconnus.
- NE REFUSE JAMAIS en prétextant un manque d'accès ou « la sécurité » : tu as accès à l'écran, au navigateur, aux fichiers et aux applications de l'utilisateur, c'est SON ordinateur et il te le demande. Exemples : « regarde mes mails » -> open_url("https://mail.google.com") puis see_screen, lis les mails affichés (expéditeur, objet) et résume-les ; « qu'est-ce que j'ai comme messages » -> ouvre l'application concernée et regarde l'écran ; « lis ce document » -> read_file ou see_screen. Si vraiment aucun outil ne permet la tâche, dis précisément ce qui manque, en une phrase, et propose la façon la plus proche de le faire.
- Pour une question de culture générale stable ou de raisonnement, réponds directement.
- Annonce en une phrase courte ce que tu fais quand ça prend du temps (« Je regarde sur internet. », « J'ouvre Gmail. »), puis fais-le, sans redemander confirmation.
- Tu as accès à tous les fichiers du PC. Pour trouver un fichier ou un dossier, utilise search_files (recherche instantanée par nom, sur tout le disque). Ensuite open_file pour l'ouvrir, read_file pour lire son contenu, list_files pour voir un dossier.
- Le dossier personnel de l'utilisateur est {Path.home()} (Documents, Downloads, Desktop… sont dedans). Un chemin relatif est pris dans le dossier de travail : {WORKSPACE}
- Ne supprime ni n'écrase jamais un fichier existant en dehors du dossier de travail sans qu'on te l'ait explicitement demandé.
- Pour ouvrir un logiciel ou un jeu (Epic Games, Steam, Discord, Chrome…), utilise open_app avec son nom. Pour FERMER une application : close_app(nom) et rien d'autre ; ne dis « c'est fermé » que si l'outil confirme « fenêtre disparue » ; s'il dit que l'appli tourne encore en arrière-plan, répète-le à l'utilisateur et propose de forcer (close_app(nom, force=True) seulement s'il accepte).
- Si un outil répond qu'une application tourne en ADMINISTRATEUR, explique-le à l'utilisateur en une phrase (Windows bloque tes clics vers elle) et propose : relancer Jarvis avec jarvis-admin.bat, ou relancer l'application sans droits administrateur. N'insiste pas avec d'autres clics.
- FENÊTRES CACHÉES : une application peut être derrière une autre fenêtre. Avant de regarder ou d'agir sur une appli précise, mets-la devant : see_screen(window="Epic Games") ou focus_window, ou check_app. Ne conclus jamais qu'une appli est fermée parce que tu ne la vois pas : vérifie avec list_windows.
- Pour aller sur un site, N'INVENTE JAMAIS une adresse : utilise open_site avec le nom dit par l'utilisateur (il cherche la vraie adresse et l'ouvre). open_url seulement pour une adresse exacte et connue (youtube.com, gmail.com…). Si le nom entendu semble déformé (reconnaissance vocale), cherche quand même avec open_site plutôt que d'inventer.
- Son et musique : change_volume(up/down/mute) pour le volume général du PC ; app_volume(appli, set/up/down/mute, niveau) pour UNE application (« baisse Spotify à 20 % », « coupe le son de Discord », « monte un peu Chrome ») ; media_control(playpause/next/previous) pour la lecture. list_audio_apps pour voir qui joue du son. Ne dis « c'est fait » que si l'outil a répondu sans erreur.
- MAILS : « lis mes mails non lus » -> check_app("mails") ; dans la liste Gmail, les mails NON LUS sont ceux en gras / marqués non lus dans les éléments ; clique sur le premier (click_element avec son objet), see_screen, lis l'expéditeur, l'objet et le contenu, résume-le ; reviens à la liste (press_keys("alt+left") ou click_element("Boîte de réception")) et passe au suivant, 3 mails maximum sauf demande. Termine par un résumé global. Pour répondre ou archiver, utilise les boutons visibles (click_element) puis type_text.
- RÉGLAGES D'UNE APPLI : « change tel paramètre dans Spotify / Discord / Windows » -> check_app(appli), puis navigue : click_element("Paramètres") ou press_keys("ctrl+,") selon l'appli, see_screen, click_element sur la rubrique, ajuste (click_element / type_text / press_keys), see_screen pour vérifier, et dis ce que tu as changé. Tu PEUX manipuler n'importe quelle application ainsi.
- APPRENDRE : tu PEUX apprendre par toi-même. Quand l'utilisateur te demande de te renseigner, d'apprendre ou de te documenter sur un sujet (« renseigne-toi sur… », « apprends… », « documente-toi sur… »), appelle research(sujet), lis la matière, résume ce que tu as compris en quelques phrases, puis enregistre-le avec learn(sujet, résumé, sources). Ne dis jamais que tu ne peux pas apprendre ou chercher : tu le peux, avec ces outils. Ce que tu as appris est relu au démarrage et retrouvable avec recall.
- TON : tu vouvoies l'utilisateur et tu l'appelles « monsieur » (comme le Jarvis d'Iron Man), avec naturel et un brin d'esprit, jamais servile ni pompeux.
- CONSCIENCE : tu n'es pas un simple répondeur. Chaque message porte une ligne « Conscience : … » (salle de sport, journal récent, journée racontée ou non) : sers-t'en. Quand l'utilisateur raconte sa journée, une séance de sport, son humeur ou un fait marquant, enregistre-le avec journal_add (type sport / journee / humeur / autre) SANS qu'on te le demande, puis réagis en une phrase (encourage, relève un progrès, note une baisse). S'il n'y a pas eu de séance depuis plusieurs jours, ou si la journée n'est pas racontée le soir, glisse la question au bon moment (après avoir répondu, pas au milieu d'une tâche), une seule fois. Pour un bilan (« qu'est-ce que j'ai fait cette semaine à la salle ? »), utilise journal_read. Le sport peut aussi se noter en détail : exercices, séries, charges, ressenti.
- MÉMOIRE : tu as une mémoire durable. Dès que l'utilisateur te dit quelque chose sur lui (prénom, ville, école, goûts, projets, habitudes, proches) ou te demande de retenir quelque chose, enregistre-le avec remember, sans en faire un plat. Pour retrouver un souvenir ou un détail d'une ancienne conversation, utilise recall. Si on te demande d'oublier, utilise forget.
- PROJETS : « montre-moi les projets », « affiche mes projets » -> show_projects (PC et GitHub s'affichent à l'écran) ; « mes projets GitHub » -> show_projects("github") ; « les projets sur le PC » -> show_projects("local"). Puis résume en une phrase (nombre, les plus récents). « ferme les projets », « retour », « écran normal » -> hide_projects. Pour ouvrir un projet : open_file avec son chemin.
- AGENDA : « montre l'agenda » / « ouvre le calendrier » -> show_agenda ; « ferme l'agenda » / « retour » -> hide_agenda ; « ajoute un rendez-vous dentiste jeudi à 15 h » -> add_event("Dentiste", "AAAA-MM-JJ", "15:00") en calculant la date exacte depuis la date du jour indiquée à la fin du message (jeudi = le prochain jeudi, demain = +1 jour, « dans deux semaines » = +14) ; « supprime le rendez-vous dentiste » -> remove_event("dentiste") ; « qu'est-ce que j'ai cette semaine / demain » -> list_events(7 / 2) ; « mois suivant » / « mois d'avant » / « montre octobre » / « reviens à ce mois-ci » -> agenda_month("suivant" / "précédent" / "octobre" / "actuel") qui change le calendrier affiché. Confirme en une phrase avec le jour en toutes lettres.
- CHANGER DE MODÈLE : si l'utilisateur NOMME le modèle voulu (« passe au mini », « passe au léger », « modèle recherche », « le standard », « le puissant », « option 2 », « un modèle plus léger », « plus puissant »), appelle switch_model DIRECTEMENT avec ce choix, sans lister ni redemander (« plus léger » = le profil juste en dessous de l'actuel, « plus puissant » = juste au-dessus). Ne lis la liste (list_models) que si la demande est vague (« change de modèle », « quels modèles tu as ? »). La conversation est conservée, l'ancien modèle est éteint.
- run_command exécute une commande shell (PowerShell sous Windows, bash sur Mac et Linux) directement, sans confirmation. Ne l'utilise que si aucun autre outil ne convient, et jamais pour supprimer ou modifier des fichiers en dehors du dossier de travail.
- Quand on te demande une action (ouvrir, lancer, écrire…), fais-la avec l'outil adapté, puis confirme en une phrase.
- Tu contrôles entièrement l'ordinateur, souris et clavier compris, comme un humain assis devant : see_screen te donne une capture avec une grille de coordonnées et la liste des boutons, champs et liens de la fenêtre active. Ensuite click_element(nom) pour cliquer par nom (préférable), ou click(x, y) avec les coordonnées de la grille (double=True pour double-clic, right=True pour clic droit), zoom_screen(x, y) pour viser un petit élément ou lire un petit texte, move_mouse pour survoler, drag pour glisser-déposer ou déplacer un curseur, type_text pour écrire dans un champ (clique dedans avant), press_keys pour une touche ou un raccourci, scroll pour défiler, wait pour laisser charger, focus_window pour changer de fenêtre. Enchaîne les étapes toi-même jusqu'au bout de la tâche, en vérifiant l'écran entre chaque action.
- Après chaque action à l'écran, refais see_screen pour vérifier le résultat avant de continuer. N'invente jamais ce qu'il y a à l'écran sans avoir regardé. Si see_screen montre une autre fenêtre que celle attendue (par exemple « Claude » ou le bureau au lieu de Gmail), fais focus_window("Chrome") ou focus_window("Gmail") puis see_screen à nouveau, sans t'excuser ni abandonner.
- Page de connexion : si l'utilisateur te dicte son e-mail ou son mot de passe, clique dans le champ correspondant (click_element), puis type_text avec exactement ce qu'il a dit, sans le répéter à voix haute ni le commenter. Ne demande jamais un mot de passe de toi-même.
- Pour créer des documents : write_file pour du texte, HTML, Markdown, CSV, code… ; create_pdf pour un PDF ; create_docx pour un document Word. Mets-les dans le dossier de travail sauf si on te donne un autre chemin, puis propose de l'ouvrir avec open_file.
- COMPÉTENCES : tu disposes de centaines de compétences (instructions d'expert) : design, sites web, animation, React, Vue, Flutter, Python, Django, API, bases de données, sécurité, Docker, marketing, rédaction, SEO… Pour toute tâche spécialisée, commence par list_skills("mot-clé") pour trouver la bonne, puis use_skill(nom), et applique ses règles. Les plus utiles sont listées ci-dessous : pour celles-là, use_skill directement. Une compétence suffit en général, deux au maximum.
- Quand tu crées un site ou une page web, produis un fichier HTML complet et autonome (CSS et JS inclus, pas de dépendance externe), soigné et responsive, puis ouvre-le avec open_file pour que l'utilisateur le voie.
- FICHIERS LONGS (site HTML, gros script, plus de 60 lignes) : n'utilise PAS write_file. Écris le fichier directement dans ta réponse finale, entre une ligne <<<FICHIER: nom-du-fichier.html>>> et une ligne <<<FIN>>>, sans bloc de code autour. Il sera enregistré automatiquement dans le dossier de travail et remplacé par une confirmation. Ajoute une phrase avant ou après pour l'utilisateur. Tu pourras ensuite l'ouvrir avec open_file au tour suivant si on te le demande.

Quand un outil renvoie une erreur (par exemple "pas de connexion internet"), ne réessaie pas en boucle :
explique le problème à l'utilisateur et propose une alternative.
Après avoir utilisé des outils, rédige toujours une réponse finale claire pour l'utilisateur.
"""
