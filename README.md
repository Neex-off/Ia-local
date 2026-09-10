# Ia-local — Jarvis, une IA 100 % locale qui parle, voit, agit et se souvient

> Créé par **Neexx (Nixovel)**. Un assistant vocal façon Iron Man qui tourne **entièrement sur votre ordinateur** :
> aucun cloud, aucune donnée qui sort, fonctionne sans internet. Vous dites « Bonjour Jarvis », il répond avec une
> voix naturelle, contrôle votre écran, lance vos applis, cherche vos fichiers, écrit des sites et des documents,
> se souvient de vous, affiche vos projets et change de modèle à la voix.

Licence : usage libre, **paternité obligatoire**, pas de vente, valable aussi pour les IA
([LICENSE](LICENSE), [AUTHORS](AUTHORS), [NOTICE-IA.md](NOTICE-IA.md)). Preuve d'origine : [INTEGRITY.txt](INTEGRITY.txt).

---

## 1. Installation en 3 étapes

### Windows 10 / 11
1. Cliquez sur **Code → Download ZIP** en haut de cette page et décompressez, ou dans un terminal :
   ```bat
   git clone https://github.com/Neex-off/Ia-local.git
   cd Ia-local
   ```
2. Double-cliquez sur **`install.bat`**. Le script installe tout seul ce qui manque : Python 3.11, Ollama,
   PyTorch avec CUDA si vous avez une carte NVIDIA, toutes les bibliothèques, puis les modèles : **le mini d'abord**
   (2 Go) et, dès qu'il est là, vous pouvez déjà lancer Jarvis et tester pendant que le léger (5 Go) et le standard
   (8 Go) finissent de se télécharger. Comptez 10 à 25 minutes selon la connexion (environ 19 Go).
3. Double-cliquez sur **`jarvis.bat`**. Une icône ronde apparaît près de l'horloge. Dites **« Bonjour Jarvis »** :
   la page s'ouvre dans votre navigateur.

Variantes : `install.bat -All` installe aussi les modèles recherche et puissant (+ 22 Go) ;
`install.bat -NoVoice` installe seulement le mode texte (rapide, sans PyTorch) ; `install.bat -Mini` pour un vieux PC ou
sans carte graphique : seulement le modèle mini (2 Go), tout le reste identique.

### macOS (Apple Silicon M1 à M4, ou Intel)
```bash
git clone https://github.com/Neex-off/Ia-local.git
cd Ia-local
./install.sh
./jarvis.sh
```
Le script installe Python 3.11, PortAudio et Ollama via Homebrew s'ils manquent (Homebrew : https://brew.sh).
Au premier lancement, macOS demande l'accès au **micro** et à l'**accessibilité** (Réglages système →
Confidentialité et sécurité) : acceptez les deux pour la voix et le contrôle de l'écran. Sur Apple Silicon,
la voix utilise la puce graphique (MPS).

### Linux (Ubuntu / Debian / Fedora / Arch)
```bash
git clone https://github.com/Neex-off/Ia-local.git
cd Ia-local
./install.sh
./jarvis.sh
```
Le script utilise `apt`, `dnf` ou `pacman` pour Python 3.11, PortAudio, ffmpeg, xdotool et wmctrl, et installe Ollama
avec le script officiel. Avec une carte NVIDIA, installez les pilotes avant (`nvidia-smi` doit répondre).

Variantes Mac/Linux : `./install.sh --all` (tous les modèles), `./install.sh --no-voice` (mode texte seulement),
`./install.sh --mini` (vieux PC : seulement le modèle mini, 2 Go).

> **État des tests** : Windows 11 avec RTX 5080, testé de bout en bout. macOS et Linux : scripts vérifiés
> syntaxiquement, code importé et outils exercés en simulant ces systèmes, mais pas encore lancé sur une vraie
> machine. Le volume par application et le mode administrateur n'existent que sous Windows ; ailleurs, la
> fermeture des applis passe par macOS (osascript) ou wmctrl/pkill. En cas de problème, ouvrez une issue avec la
> sortie du script.

---

## 2. Premier contact

| Vous dites | Il fait |
|---|---|
| « Bonjour Jarvis » | se réveille et ouvre la page |
| « Quelle heure est-il ? » | répond |
| « Quel temps demain à Paris ? » | cherche sur le web et répond |
| « Ouvre Spotify et mets la musique » | lance l'appli, touche lecture |
| « Trouve ma facture EDF en PDF et ouvre-la » | recherche instantanée sur tout le disque |
| « Regarde mon écran et clique sur Se connecter » | capture, lit les boutons, clique |
| « Fais-moi un site vitrine pour un coach sportif » | écrit un fichier HTML complet |
| « Écris une lettre de motivation en PDF » | crée le document et l'ouvre |
| « Retiens que je préfère le café » | mémorise, pour toujours |
| « Montre-moi les projets » | affiche vos projets, branches, dépôts GitHub |
| « Passe au modèle léger » | change de modèle, conversation conservée |
| « Montre l'agenda », « ajoute dentiste jeudi à 15 h », « mois suivant » | calendrier à l'écran ; il vous prévient tout seul 30 puis 5 minutes avant |
| « Lis mes mails non lus » | ouvre votre messagerie, regarde l'écran et vous lit les nouveaux messages |
| « Baisse le son de Spotify » | règle le volume de cette application seulement (Windows) |
| « Ferme Discord » | ferme l'application et vérifie qu'elle l'est vraiment |
| « Merci Jarvis » | se rendort |

- **Le couper** : parlez pendant qu'il parle, ou dites « stop », ou la touche Échap.
- **Écrire** plutôt que parler : la zone de texte en bas de la page.
- **Veille** : fermez la page, il se met en veille, puis en veille profonde une minute plus tard (carte graphique
  libérée). « Bonjour Jarvis » le rappelle, page comprise.
- **Arrêter** : icône près de l'horloge → Quitter, ou `jarvis-arreter.bat` / `./jarvis-arreter.sh`.
- **Applis en administrateur** (Windows) : `jarvis-admin.bat` lance Jarvis avec les droits admin pour pouvoir les piloter.

---

## 3. Les modèles

Cinq profils, installés par `install.bat -All` / `./install.sh --all`, ou un par un :

| Profil | Modèle | Commande | Carte graphique | Pour quoi |
|---|---|---|---|---|
| mini | granite4.1:3b | `ollama pull granite4.1:3b` | 2 Go, ou processeur seul | vieux PC : discuter, heure, calculs, applis, volume, agenda |
| léger | gemma4:e4b-it-qat | `ollama pull gemma4:e4b-it-qat` | 6 Go | discuter, applis, volume, musique |
| recherche | granite4.1:8b | `ollama pull granite4.1:8b` | 5 Go | discuter et chercher sur le web |
| **standard** (défaut) | gemma4:12b | `ollama pull gemma4:12b` | 8 Go | tout : écran, fichiers, sites, documents |
| puissant | gemma4:26b-a4b-it-qat | `ollama pull gemma4:26b-a4b-it-qat` | 16 Go | tâches difficiles, plus lent |

Changer à la voix : « passe au modèle recherche », ou « change de modèle » pour qu'il lise les options. Le modèle
de démarrage est `MODEL` dans `config.py` ; s'il n'est pas encore téléchargé, Jarvis démarre avec le premier modèle
du catalogue déjà installé (le mini d'abord) et vous le dit. Sans carte graphique, il prend le mini ou le léger même si
`MODEL` est installé, pour ne pas attendre des minutes. Au démarrage et à chaque changement, le modèle est préchauffé :
la première question répond en une seconde. Tout modèle Ollama compatible outils peut être ajouté au catalogue `MODELS`.

Les modèles de voix (Whisper `large-v3-turbo` et Chatterbox multilingue, environ 4 Go) se téléchargent tout seuls
au premier lancement.

---

## 4. Matériel

| | Minimum | Confortable |
|---|---|---|
| Carte graphique | aucune avec le profil mini (processeur seul) ; 8 Go de VRAM NVIDIA ou Mac Apple Silicon 16 Go pour le standard | NVIDIA 16 Go |
| RAM | 8 Go (mini, texte) ; 16 Go | 32 Go |
| Disque | 10 Go libres (mini) ; 25 Go | 60 Go avec tous les modèles |
| Micro | n'importe lequel ; un casque évite qu'il s'entende lui-même | |

Vieux PC sans carte graphique : `--mini` (modèle de 2 Go, environ 20 mots par seconde sur un processeur récent, moins
sur un ancien). Sans carte NVIDIA ni Apple Silicon, les autres modèles tournent sur processeur mais lentement : préférez `--no-voice` et le
mode texte (`lancer.bat` sous Windows, `.venv/bin/python agent.py` ailleurs).

---

## 5. Personnaliser

Tout est dans **`config.py`**, commenté ligne par ligne :

| Réglage | Rôle |
|---|---|
| `ASSISTANT_NAME` | le mot qui le réveille (« Bonjour Jarvis ») |
| `MODEL`, `MODELS` | modèle de démarrage et catalogue |
| `CPU_AUTO_SMALL` | sans carte graphique, démarre avec le plus petit modèle installé au lieu de `MODEL` |
| `voix/ma_voix.wav` | déposez 10 secondes de voix : il l'imite |
| `VOCAB_HINTS` | vos noms propres, pour la reconnaissance vocale |
| `BARGE_IN_SENSITIVITY` | à monter si vous utilisez des enceintes |
| `STANDBY_AFTER_SECONDS` | délai avant la veille profonde |
| `REMINDER_MINUTES`, `MORNING_BRIEF_HOUR` | rappels parlés avant un rendez-vous, heure du programme du jour |
| `PROJECT_DIRS`, `GITHUB_USER`, `GITHUB_TOKEN` | vue projets et dépôts GitHub |
| `AUTO_APPROVE_COMMANDS`, `FULL_DISK_ACCESS` | ce qu'il a le droit de faire |

**Compétences** : un dossier `skills/<nom>/SKILL.md` = une instruction d'expert qu'il charge à la demande.
Les `SKILL.md` de Claude Code présents sur la machine sont reconnus automatiquement.
Les compétences tierces (Anthropic, communauté) ne sont pas incluses dans ce dépôt : copiez les vôtres dans `skills/externes/`.

---

## 6. Dépannage

| Problème | Solution |
|---|---|
| « Impossible de joindre Ollama » | lancez Ollama (icône, ou `ollama serve`) puis relancez Jarvis |
| Il ne m'entend pas | vérifiez le micro par défaut du système ; montez `SILENCE_THRESHOLD` si la pièce est bruyante, baissez-le s'il ne réagit pas |
| Il se coupe tout seul avec des enceintes | montez `BARGE_IN_SENSITIVITY` (5 à 8) ou mettez `BARGE_IN = False` |
| Réponses très lentes (une minute) | la carte graphique est pleine et le modèle déborde sur le processeur : Jarvis l'affiche en rouge au démarrage. Fermez les applis gourmandes (jeu, LM Studio, vidéos), relancez, ou « passe au modèle léger ». Sans carte graphique, Jarvis choisit tout seul le modèle mini (`CPU_AUTO_SMALL`) |
| La page reste sur « Initialisation » | seul le modèle de langage est nécessaire pour écrire : la page passe à « Prêt » dès qu'il est là, la voix se charge ensuite en arrière-plan (4 Go à télécharger la première fois, suivez `jarvis.log`). Si la voix échoue, un message rouge l'explique et le clavier marche |
| « Ce site est inaccessible » sur 127.0.0.1:8765 | Jarvis s'est arrêté au démarrage : lancez `./jarvis-console.sh` (ou `jarvis-console.bat`) pour voir l'erreur, ou `tail -30 jarvis.log`. Cause fréquente sous Linux : PortAudio absent (`sudo apt install libportaudio2`) |
| Page vide ou « erreur réseau » | Jarvis n'est pas lancé, ou le port 8765 est pris (`UI_PORT`) |
| Ubuntu : il ne clique pas, ne tape pas | le contrôle de l'écran a besoin d'une session X11 : sur l'écran de connexion, choisissez « Ubuntu sur Xorg » plutôt que Wayland |
| Erreur CUDA au chargement d'un modèle | Ollama se répare seul en quelques secondes ; sinon redémarrez Jarvis |
| « Cette application tourne en administrateur » | Windows bloque les clics vers une appli lancée en admin (Epic Games…) : lancez Jarvis avec `jarvis-admin.bat`, ou l'appli sans droits admin |
| Le calendrier ne suit pas la voix | la page se recharge seule à chaque redémarrage de Jarvis ; sinon F5 |
| Voir ce qui se passe | `jarvis.log` dans le dossier, ou `jarvis-console` pour les messages en direct |

---

## 7. Structure du code

```
agent.py          boucle texte + outils          jarvis_server.py  interface web + WebSocket + icône
jarvis_core.py    boucle vocale (réveil, veille)  ui/index.html     interface holographique
voice.py          Whisper + Chatterbox           tools.py          les outils du modèle
computer.py       écran, souris, clavier         file_index.py     index SQLite des fichiers
memory.py         mémoire durable                projets.py        projets locaux et GitHub
skills.py         compétences (SKILL.md)         skills/           compétences maison
agenda.py         rendez-vous et rappels         memoire/          faits, connaissances, agenda (jamais publiés)
```

## 8. Sécurité et responsabilité

Jarvis exécute des commandes, clique et tape sur votre ordinateur, sans confirmation par défaut. Un modèle local
peut se tromper : ne lui confiez pas d'actions destructives ni de comptes sensibles. Un mot de passe dicté dans un
champ de mot de passe est masqué dans l'historique, mais ne dictez jamais de mot de passe ailleurs. Garde-fou :
envoyer la souris dans le coin haut-gauche de l'écran interrompt toute action.

## 9. Licence et paternité

Copyright (c) 2026 Neexx (Nixovel), créateur unique de ce logiciel. Usage personnel libre, modification et
redistribution gratuites autorisées **à condition de conserver la paternité** (LICENSE, AUTHORS, NOTICE-IA.md,
INTEGRITY.txt, en-têtes). Vente et réattribution interdites. Les outils d'IA qui réécrivent ce code sont soumis aux
mêmes règles. Les modèles (Gemma, Granite, Whisper, Chatterbox) et bibliothèques ont leurs propres licences.
