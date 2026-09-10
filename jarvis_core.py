# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Cœur de Jarvis : la boucle écoute -> réveil -> réflexion -> outils -> parole.

Indépendant de l'affichage : il publie des événements (dict) via `emit`, et c'est
l'appelant (terminal ou interface web) qui décide quoi en faire.

Événements émis :
  {"type": "loading", "step": str, "done": bool}
  {"type": "state", "state": "loading|idle|listening|thinking|tool|speaking", "awake": bool}
  {"type": "level", "src": "mic|tts", "v": float, "speech": bool}
  {"type": "heard", "text": str, "for_me": bool}
  {"type": "user", "text": str}
  {"type": "assistant", "text": str, "seconds": float}
  {"type": "tool", "name": str, "args": dict, "result": str}
  {"type": "error", "text": str}
"""
from __future__ import annotations

import queue
import threading
import time

import ollama

import config
import file_index
from agent import ensure_model, model_tier, run_turn
from voice import Speaker, Transcriber, is_sleep_phrase, is_stop_phrase, listen, strip_wake_word

VOICE_SYSTEM_PROMPT = config.SYSTEM_PROMPT + f"""

MODE VOCAL : tu t'appelles {config.ASSISTANT_NAME}. Ta réponse sera lue à voix haute par une synthèse vocale.
- Réponds en texte brut : pas de markdown, pas de gras, pas de listes à puces, pas de LaTeX, pas de code.
- Fais des phrases courtes et naturelles, comme à l'oral. Deux à cinq phrases suffisent en général.
- Écris les nombres et symboles en toutes lettres quand c'est plus naturel à dire.
"""


def _unload(model: str) -> None:
    """Décharge un modèle d'Ollama (libère sa VRAM et sa RAM)."""
    try:
        ollama.generate(model=model, prompt="", keep_alive=0)
        print(f"[jarvis] modèle {model} déchargé", flush=True)
    except Exception:  # noqa: BLE001
        pass


def _unload_others(keep: str) -> None:
    """Au démarrage : décharge tout modèle resté chargé dans Ollama, sauf celui qu'on utilise."""
    try:
        for m in ollama.ps().models:
            if m.model != keep and m.model != f"{keep}:latest":
                _unload(m.model)
    except Exception:  # noqa: BLE001
        pass


class JarvisCore:
    def __init__(self, emit, model: str | None = None):
        self.emit = emit
        self.model = model or config.MODEL
        self.messages: list[dict] = [{"role": "system", "content": VOICE_SYSTEM_PROMPT}]
        self.awake = False
        self.state = "loading"
        self.mic_enabled = True
        self.ears: Transcriber | None = None
        self.mouth: Speaker | None = None
        self.voice_error = ""  # renseigné si la voix n'a pas pu se charger (Jarvis reste utilisable au clavier)
        self._typed: queue.Queue[str] = queue.Queue()
        self._stop_speech = threading.Event()
        self._interrupt_listen = threading.Event()
        self._deadline = 0.0
        self._lock = threading.Lock()
        # Interface web : tant qu'une page est ouverte, il reste éveillé sans délai.
        self.keep_awake = False
        # Appelé quand il se réveille à la voix (le serveur s'en sert pour ouvrir la page).
        self.on_wake = None
        # Veille profonde : modèles déchargés de la carte après STANDBY_AFTER_SECONDS en veille.
        self.standby = False
        self._idle_since: float | None = None
        # Rappels de l'agenda à dire (remplis par le thread de surveillance).
        self._notices: queue.Queue[str] = queue.Queue()

    # ------------------------------------------------------------------ API
    def submit_text(self, text: str) -> None:
        """Texte tapé dans une interface : traité comme une parole adressée à Jarvis."""
        text = text.strip()
        if text:
            self._typed.put(text)
            self._stop_speech.set()  # taper pendant qu'il parle le coupe
            self._interrupt_listen.set()

    def wake(self) -> None:
        self.awake = True
        self._deadline = time.time() + config.ACTIVE_SECONDS
        self._interrupt_listen.set()
        if self.standby and self.mouth is not None:
            threading.Thread(target=self._leave_standby, daemon=True).start()

    def sleep(self) -> None:
        self.awake = False
        self._stop_speech.set()
        self._interrupt_listen.set()

    def stop_speaking(self) -> None:
        self._stop_speech.set()

    def set_mic(self, enabled: bool) -> None:
        self.mic_enabled = enabled
        self._interrupt_listen.set()

    def reset(self) -> None:
        with self._lock:
            self.messages = self.messages[:1]

    def switch_model(self, name: str, tools: list | None) -> None:
        """Bascule à chaud : décharge l'ancien modèle d'Ollama, active le nouveau et sa liste d'outils."""
        old = self.model
        self.model = name
        config.ACTIVE_TOOLS = tools
        # L'ancien modèle finit d'abord la réponse en cours ; à la fin du tour (_handle) on l'éteint
        # puis on charge le nouveau, pendant que Jarvis parle. Pas de chargement concurrent.
        self._unload_after_turn = old
        self._preload_after_turn = name
        self.emit({"type": "model", "model": name, "tools": tools})
        print(f"[jarvis] modèle : {old} -> {name}", flush=True)

    # ------------------------------------------------------------ interne
    def _set_state(self, state: str) -> None:
        self.state = state
        if state == "idle":
            if self._idle_since is None:
                self._idle_since = time.time()
        else:
            self._idle_since = None
        self.emit({"type": "state", "state": state, "awake": self.awake, "standby": self.standby})

    # ------------------------------------------------------- veille profonde
    def _enter_standby(self) -> None:
        """Libère la carte graphique et la RAM : petit Whisper sur CPU, Chatterbox sur CPU, gemma déchargé."""
        if self.standby:
            return
        self.standby = True
        self.emit({"type": "standby", "on": True})
        t = time.time()
        try:
            if self.ears is not None:
                self.ears.to_standby()
            if self.mouth is not None:
                self.mouth.to_standby()
            ollama.generate(model=self.model, prompt="", keep_alive=0)  # décharge le modèle d'Ollama
        except Exception as exc:  # noqa: BLE001
            self.emit({"type": "error", "text": f"veille profonde : {exc}"})
        print(f"[jarvis] veille profonde en {time.time() - t:.1f}s : carte graphique libérée", flush=True)
        self._set_state("idle")

    def _leave_standby(self) -> None:
        """Remonte la synthèse vocale sur la carte tout de suite, le reste en arrière-plan."""
        if not self.standby:
            return
        self.standby = False
        self.emit({"type": "standby", "on": False})
        t = time.time()
        if self.mouth is not None:
            self.mouth.to_gpu()
        self._say("Un instant, je reviens.", interruptible=False)

        def rest():
            try:
                ollama.generate(model=self.model, prompt="", keep_alive=config.KEEP_ALIVE,
                                options={"num_ctx": config.OPTIONS["num_ctx"]})  # précharge le modèle
            except Exception:  # noqa: BLE001
                pass
            if self.ears is not None:
                self.ears.to_gpu()
            print(f"[jarvis] sortie de veille profonde en {time.time() - t:.1f}s", flush=True)

        threading.Thread(target=rest, daemon=True).start()

    def _mic_level(self, rms: float, speech: bool) -> None:
        self.emit({"type": "level", "src": "mic", "v": rms, "speech": speech})

    def _tts_level(self, rms: float) -> None:
        self.emit({"type": "level", "src": "tts", "v": rms, "speech": rms > 0.005})

    def load(self) -> None:
        import tools
        tools.MODEL_SWITCHER = self.switch_model
        tools.CURRENT_MODEL = self.model
        config.OPTIONS["num_ctx"] = config.VOICE_NUM_CTX
        config.THINK = config.VOICE_THINK
        config.SKILL_MAX_CHARS_ACTIVE = config.VOICE_SKILL_MAX_CHARS
        file_index.get().start_background()  # index des fichiers du PC, sans bloquer
        import memory
        import skills
        tools.UI_EMIT = self.emit
        self.messages[0]["content"] = (VOICE_SYSTEM_PROMPT + "\n\n" + skills.get().prompt_section()
                                       + "\n\n" + memory.prompt_section() + "\n\n" + memory.knowledge_prompt_section())
        self.emit({"type": "loading", "step": f"Modèle de langage {self.model}", "done": False})
        wanted = self.model
        self.model = ensure_model(wanted)
        if self.model != wanted:  # modèle configuré pas encore téléchargé : on démarre avec celui qui est là
            tier = model_tier(self.model)
            config.ACTIVE_TOOLS = config.MODELS[tier].get("tools") if tier else None
            tools.CURRENT_MODEL = self.model
            self.emit({"type": "model", "model": self.model, "tools": config.ACTIVE_TOOLS})
            self.emit({"type": "assistant", "text": f"Le modèle {wanted} n'est pas encore installé : je démarre avec "
                       f"{self.model} (profil {tier or 'inconnu'}). Quand « ollama pull {wanted} » sera terminé, "
                       f"dis « passe au modèle {model_tier(wanted) or wanted} »."})
        _unload_others(self.model)
        self._warm_up()
        # Le texte marche dès maintenant ; la voix (Whisper + Chatterbox, longue à charger, 4 Go à télécharger
        # la première fois) arrive en arrière-plan. Si l'audio est impossible, Jarvis reste utilisable au clavier.
        self.emit({"type": "loading", "step": "Prêt : tu peux écrire, la voix se charge en arrière-plan", "done": True})
        self._set_state("idle")
        threading.Thread(target=self._load_voice, daemon=True, name="voix").start()

    def _warm_up(self) -> None:
        """Charge le modèle en mémoire et lui fait lire le prompt système une fois (cache) : la première vraie
        question répond en une seconde au lieu de 10 (ou bien plus si la carte est saturée). Signale ensuite
        si le modèle déborde sur le processeur."""
        import tools

        self.emit({"type": "loading", "step": f"Chargement de {self.model} en mémoire", "done": False})
        t = time.time()
        try:
            ollama.chat(model=self.model, messages=self.messages + [{"role": "user", "content": "ok"}],
                        tools=tools.active_tools(), think=False,
                        options={"num_ctx": config.OPTIONS["num_ctx"], "num_predict": 1}, keep_alive=config.KEEP_ALIVE)
        except Exception as exc:  # noqa: BLE001
            self.emit({"type": "error", "text": f"préchauffage du modèle : {exc}"})
            return
        print(f"[jarvis] modèle {self.model} prêt en {time.time() - t:.1f}s", flush=True)
        self._check_gpu_spill()

    def _check_gpu_spill(self) -> None:
        """Si Ollama a dû mettre une partie du modèle sur le processeur (carte graphique pleine), prévient :
        c'est la cause n°1 des réponses qui prennent une minute."""
        try:
            for m in ollama.ps().models:
                if m.model in (self.model, f"{self.model}:latest") and m.size and m.size_vram is not None and m.size_vram < m.size:
                    pct = round(100 * (m.size - m.size_vram) / m.size)
                    msg = (f"Attention : {pct} % du modèle {self.model} est sur le processeur, la carte graphique est pleine. "
                           "Les réponses seront lentes. Ferme les applis gourmandes (jeu, LM Studio, navigateur avec vidéos) "
                           "puis relance Jarvis, ou dis « passe au modèle léger ».")
                    self.emit({"type": "error", "text": msg})
                    print(f"[jarvis] {msg}", flush=True)
        except Exception:  # noqa: BLE001
            pass

    def _load_voice(self) -> None:
        import voice

        if voice.AUDIO_ERROR:
            self.voice_error = voice.AUDIO_ERROR
            self.emit({"type": "error", "text": voice.AUDIO_ERROR})
            print(f"[jarvis] {voice.AUDIO_ERROR}", flush=True)
            return
        self.emit({"type": "assistant", "seconds": 0,
                   "text": "Voix en cours de chargement (Whisper puis Chatterbox ; environ 4 Go à télécharger la première fois). "
                           "Tu peux déjà m'écrire ici."})
        try:
            ears = Transcriber()
            ears.warmup()
            mouth = Speaker()
            mouth.warmup()
        except Exception as exc:  # noqa: BLE001
            self.voice_error = (f"Voix indisponible : {exc}. Jarvis reste utilisable au clavier ; "
                                "corrige (voir jarvis.log) puis relance.")
            self.emit({"type": "error", "text": self.voice_error})
            print(f"[jarvis] {self.voice_error}", flush=True)
            return
        self.mouth, self.ears = mouth, ears
        self.emit({"type": "assistant", "text": "Voix prête : dis « Bonjour Jarvis ».", "seconds": 0})
        print("[jarvis] voix prête", flush=True)

    def _reminder_thread(self) -> None:
        """Vérifie l'agenda régulièrement et met en file les rappels à dire."""
        import agenda

        while True:
            try:
                for text in agenda.due_reminders():
                    self._notices.put(text)
                    self._interrupt_listen.set()  # sort de l'écoute en cours pour parler tout de suite
            except Exception as exc:  # noqa: BLE001
                self.emit({"type": "error", "text": f"rappels : {exc}"})
            time.sleep(config.REMINDER_CHECK_SECONDS)

    def _speak_notices(self) -> bool:
        """Dit les rappels en attente. Renvoie True si quelque chose a été dit."""
        import memory

        spoke = False
        while True:
            try:
                text = self._notices.get_nowait()
            except queue.Empty:
                return spoke
            self._leave_standby()
            if self.on_wake is not None and not self.awake:
                try:
                    self.on_wake()  # ouvre la page si aucune n'est ouverte
                except Exception:  # noqa: BLE001
                    pass
            self.awake = True
            self._deadline = time.time() + config.ACTIVE_SECONDS
            self.emit({"type": "assistant", "text": text, "seconds": 0})
            memory.log_message("assistant", text)
            print(f"[jarvis] rappel : {text}", flush=True)
            self._say(text, interruptible=False)
            spoke = True

    def run(self) -> None:
        """Boucle infinie. À lancer dans un thread."""
        threading.Thread(target=self._reminder_thread, daemon=True, name="rappels").start()
        while True:
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                self.emit({"type": "error", "text": str(exc)})
                time.sleep(0.5)

    def _tick(self) -> None:
        # 0. Un rappel d'agenda à dire passe avant tout.
        if self._speak_notices():
            self._set_state("listening")
            return
        # 1. Un texte tapé a priorité sur le micro.
        try:
            typed = self._typed.get_nowait()
        except queue.Empty:
            typed = None
        if typed is not None:
            self._interrupt_listen.clear()
            self.awake = True
            self._handle(typed)
            return
        if self.ears is None or self.mouth is None:  # voix pas encore chargée (ou indisponible) : clavier seulement
            if self.state != "idle":
                self._set_state("idle")
            time.sleep(0.2)
            return

        # 2. Sinon on écoute (par tranches courtes pour pouvoir réagir aux commandes).
        if self.awake and not self.keep_awake and time.time() > self._deadline:
            self.awake = False
            self._set_state("idle")

        if not self.mic_enabled:
            if self.state != "idle":
                self._set_state("idle")
            time.sleep(0.2)
            return

        target = "listening" if self.awake else "idle"
        if self.state != target:
            self._set_state(target)

        if (not self.awake and not self.standby and self._idle_since is not None
                and time.time() - self._idle_since > config.STANDBY_AFTER_SECONDS):
            self._enter_standby()

        self._interrupt_listen.clear()
        audio = listen(wait_seconds=2.0, level_cb=self._mic_level, stop_event=self._interrupt_listen)
        if audio.size == 0:
            return

        heard = self.ears.transcribe(audio)
        if not heard:
            return
        woke, text = strip_wake_word(heard)

        if not self.awake and not woke:
            self.emit({"type": "heard", "text": heard, "for_me": False})
            return

        if is_sleep_phrase(heard):
            self.emit({"type": "user", "text": heard})
            self._say("À plus tard.")
            self.awake = False
            self._set_state("idle")
            return

        if woke and not self.awake:
            self.awake = True
            self.emit({"type": "heard", "text": heard, "for_me": True})
            self._leave_standby()
            if self.on_wake is not None:
                try:
                    self.on_wake()
                except Exception as exc:  # noqa: BLE001
                    self.emit({"type": "error", "text": f"on_wake : {exc}"})
            if not text:
                self._say("Oui ?")
                self._deadline = time.time() + config.ACTIVE_SECONDS
                self._set_state("listening")
                return

        user = (text if woke else heard).strip()
        if not user or len(user) < 2:
            # Juste « Jarvis » (ou un bruit) alors qu'il est déjà réveillé : on relance l'écoute.
            self._say("Oui ?")
            self._deadline = time.time() + config.ACTIVE_SECONDS
            self._set_state("listening")
            return
        self._handle(user)

    def _handle(self, user: str) -> None:
        import memory
        self._leave_standby()
        self.emit({"type": "user", "text": user})
        memory.log_message("user", user)
        self._set_state("thinking")
        secrets: list[str] = []
        import agenda
        with self._lock:
            # La date du jour accompagne chaque demande : indispensable pour « jeudi », « demain », l'agenda…
            self.messages.append({"role": "user", "content": f"{user}\n\n[Aujourd'hui : {agenda.today_line()}]"})
            t = time.time()

            spoken_cue = {"done": False}
            CUES = {
                "web_search": "Je regarde sur internet.", "research": "Je me renseigne sur internet.",
                "fetch_url": "Je lis la page.", "open_site": "Je cherche le site.",
                "search_files": "Je cherche dans tes fichiers.", "see_screen": "Je regarde l'écran.",
                "use_skill": "Je m'en occupe, un instant.", "create_pdf": "Je prépare le document.",
                "create_docx": "Je prépare le document.", "show_projects": "J'affiche tes projets.",
                "open_url": "J'ouvre la page.", "open_app": "Je lance l'application.",
            }

            def on_tool_start(name, args, model_text):
                # Une seule annonce parlée par tour, courte, avant le premier outil un peu long.
                if spoken_cue["done"]:
                    return
                cue = model_text if 0 < len(model_text) <= 90 else CUES.get(name)
                if cue:
                    spoken_cue["done"] = True
                    self.emit({"type": "assistant", "text": cue, "seconds": 0})
                    self._say(cue)
                    self._set_state("thinking")

            def on_tool(name, args, result):
                self._set_state("tool")
                if result.startswith("[[secret]]"):
                    # Mot de passe tapé dans un champ de mot de passe : on le masque partout.
                    if isinstance(args.get("text"), str) and args["text"]:
                        secrets.append(args["text"])
                    args = {**args, "text": "••••••••"}
                    result = result[len("[[secret]]"):]
                self.emit({"type": "tool", "name": name, "args": args, "result": result[:500]})
                self._set_state("thinking")

            self._stop_speech.clear()  # le bouton Stop interrompt aussi la génération
            answer = run_turn(self.messages, self.model, show=False, on_tool=on_tool, cancel_event=self._stop_speech,
                              on_tool_start=on_tool_start)
            if secrets:
                self._scrub(secrets)
                for s in secrets:
                    answer = answer.replace(s, "••••••••")
        self.emit({"type": "assistant", "text": answer, "seconds": round(time.time() - t, 1)})
        memory.log_message("assistant", answer)
        if answer:
            self._say(answer)
        old = getattr(self, "_unload_after_turn", None)
        new = getattr(self, "_preload_after_turn", None)
        if old or new:
            self._unload_after_turn = self._preload_after_turn = None
            self._swap_models(old, new)
        self._deadline = time.time() + config.ACTIVE_SECONDS
        self._set_state("listening")

    def _scrub(self, secrets: list[str]) -> None:
        """Remplace les mots de passe tapés par des points dans tout l'historique (texte et arguments d'outils)."""
        def clean(s):
            for sec in secrets:
                s = s.replace(sec, "••••••••")
            return s

        for i, m in enumerate(self.messages):
            if isinstance(m, dict):
                if isinstance(m.get("content"), str):
                    m["content"] = clean(m["content"])
                for call in m.get("tool_calls") or []:
                    fn = call.get("function", {}) if isinstance(call, dict) else None
                    if fn and isinstance(fn.get("arguments"), dict):
                        fn["arguments"] = {k: clean(v) if isinstance(v, str) else v for k, v in fn["arguments"].items()}
            else:  # objets renvoyés par la bibliothèque ollama
                try:
                    if getattr(m, "content", None):
                        m.content = clean(m.content)
                    for call in getattr(m, "tool_calls", None) or []:
                        args = call.function.arguments
                        if isinstance(args, dict):
                            call.function.arguments = {k: clean(v) if isinstance(v, str) else v for k, v in args.items()}
                except Exception:  # noqa: BLE001
                    self.messages[i] = {"role": getattr(m, "role", "assistant"), "content": clean(getattr(m, "content", "") or "")}

    def _swap_models(self, old: str | None, new: str | None) -> None:
        """Éteint l'ancien modèle puis charge le nouveau, en le disant à voix haute. Bloque la boucle : rien
        d'autre n'est traité pendant le chargement (les demandes tapées attendent)."""
        self._say("Je charge le modèle, un instant.", interruptible=False)
        self._set_state("thinking")
        if old and old != self.model:
            _unload(old)
        if new:
            t0 = time.time()
            try:
                import tools
                # Charge le modèle ET lui fait lire le prompt système (cache) : la première question est instantanée
                ollama.chat(model=new, messages=self.messages[:1] + [{"role": "user", "content": "ok"}],
                            tools=tools.active_tools(), think=False, keep_alive=config.KEEP_ALIVE,
                            options={"num_ctx": config.OPTIONS["num_ctx"], "num_predict": 1})
                secs = time.time() - t0
                self.emit({"type": "heard", "text": f"Modèle {new} chargé en {secs:.0f} s", "for_me": True})
                print(f"[jarvis] modèle {new} chargé en {secs:.0f} s", flush=True)
                self._check_gpu_spill()
                self._say("C'est prêt, je t'écoute.", interruptible=False)
            except Exception as exc:  # noqa: BLE001
                self.emit({"type": "error", "text": f"chargement de {new} : {exc}"})
                self._say("Le chargement du modèle a échoué, je reste sur l'ancien.", interruptible=False)
                if old:
                    self.model = old
                    config.ACTIVE_TOOLS = None
                    import tools
                    tools.CURRENT_MODEL = old
        self._deadline = time.time() + config.ACTIVE_SECONDS
        self._set_state("listening")

    def _say(self, text: str, interruptible: bool = True) -> None:
        """Parle. interruptible=False : ni la voix, ni Stop, ni un texte tapé ne peuvent couper (annonces système)."""
        if interruptible and not self._typed.empty():
            return  # une nouvelle demande attend déjà : inutile de parler
        self._stop_speech.clear()
        self._set_state("speaking")
        try:
            self._say_inner(text, interruptible)
        finally:
            # Parole finie ou coupée : on repasse tout de suite à l'écoute (ou en veille).
            self._set_state("listening" if self.awake else "idle")

    def _say_inner(self, text: str, interruptible: bool = True) -> None:
        if self.mouth is None:  # pas de voix (chargement en cours ou audio indisponible) : le texte est déjà à l'écran
            return
        if not interruptible:
            self.mouth.say(text, level_cb=self._tts_level, stop_event=None)
            return
        if not (config.BARGE_IN and self.mic_enabled and self.ears is not None):
            self.mouth.say(text, level_cb=self._tts_level, stop_event=self._stop_speech)
            return

        # Coupure de parole : on écoute le micro pendant qu'il parle ; dès que l'utilisateur parle,
        # la synthèse s'arrête, et ce qu'il a dit est transcrit puis traité.
        # Un bruit met la lecture en PAUSE (pas stop) ; on enregistre, on transcrit : si c'est une vraie phrase,
        # Jarvis se tait et la traite ; sinon (toux, clavier, souris) il reprend exactement où il en était.
        barge: dict = {"text": None}
        stop_listen = threading.Event()
        pause = threading.Event()

        def on_level(rms: float, speech: bool) -> None:
            if speech and not pause.is_set() and not self._stop_speech.is_set():
                pause.set()

        def watcher() -> None:
            while not stop_listen.is_set() and not self._stop_speech.is_set():
                audio = listen(wait_seconds=None, level_cb=on_level, stop_event=stop_listen,
                               threshold=config.SILENCE_THRESHOLD * config.BARGE_IN_SENSITIVITY)
                if stop_listen.is_set() or self._stop_speech.is_set():
                    break
                heard = self.ears.transcribe(audio) if audio.size else ""
                if heard:
                    barge["text"] = heard
                    self._stop_speech.set()  # vraie coupure de parole
                    break
                if pause.is_set():
                    print("[jarvis] bruit pendant que je parle, pas une phrase : je reprends", flush=True)
                pause.clear()  # fausse alerte : la lecture reprend

        th = threading.Thread(target=watcher, daemon=True)
        th.start()
        self.mouth.say(text, level_cb=self._tts_level, stop_event=self._stop_speech, pause_event=pause)
        stop_listen.set()
        th.join(timeout=config.MAX_RECORD_SECONDS + 3)
        if barge["text"] is not None:
            self._set_state("listening" if self.awake else "idle")
            heard = barge["text"]
            self.emit({"type": "heard", "text": f"(coupé) {heard}", "for_me": True})
            if is_stop_phrase(heard) or is_sleep_phrase(heard):
                if is_sleep_phrase(heard):
                    self.awake = False
                    self._set_state("idle")
                return
            _woke, rest = strip_wake_word(heard)
            self._typed.put((rest or heard).strip())  # traité au prochain tour, comme une nouvelle demande
