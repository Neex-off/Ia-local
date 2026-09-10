# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Briques vocales 100 % locales : micro -> texte (faster-whisper) et texte -> voix (Chatterbox).

Tout tourne sur le GPU, aucun appel réseau une fois les modèles téléchargés.
"""
from __future__ import annotations

import queue
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
    AUDIO_ERROR = ""
except (ImportError, OSError) as _exc:  # PortAudio absent (Linux : libportaudio2, macOS : brew portaudio)
    sd = None  # type: ignore[assignment]
    AUDIO_ERROR = (f"Micro et haut-parleurs indisponibles : {_exc}. Installe PortAudio "
                   "(Ubuntu/Debian : sudo apt install libportaudio2 ; Fedora : sudo dnf install portaudio ; "
                   "macOS : brew install portaudio) puis relance Jarvis. En attendant, écris dans la page.")

import config

SAMPLE_RATE = 16000  # ce qu'attend Whisper


# ---------------------------------------------------------------------------
# Micro : attend de la parole puis enregistre jusqu'à un silence
# ---------------------------------------------------------------------------

def listen(
    silence_seconds: float = config.SILENCE_SECONDS,
    max_seconds: float = config.MAX_RECORD_SECONDS,
    threshold: float = config.SILENCE_THRESHOLD,
    wait_seconds: float | None = None,
    level_cb=None,
    stop_event: threading.Event | None = None,
) -> np.ndarray:
    """Attend que quelqu'un parle, enregistre, et s'arrête après `silence_seconds` de silence.

    wait_seconds : durée max d'attente avant la première parole (None = infini).
    level_cb     : appelé avec (niveau_rms, parole_en_cours) toutes les 50 ms, pour une interface.
    stop_event   : si posé, on abandonne l'écoute et on renvoie un tableau vide.
    Renvoie un tableau vide si rien n'a été dit.
    """
    if sd is None:  # pas d'audio : on attend simplement (le texte tapé dans la page reste possible)
        deadline = time.time() + (wait_seconds if wait_seconds is not None else 3600)
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(0.2)
        return np.zeros(0, dtype="float32")
    chunks: list[np.ndarray] = []
    q: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata, frames, t, status):  # noqa: ARG001
        q.put(indata[:, 0].copy())

    block = int(SAMPLE_RATE * 0.05)  # blocs de 50 ms
    started = time.time()
    speech_start = None
    last_voice = None
    pre_roll: list[np.ndarray] = []  # garde 300 ms avant le premier mot pour ne pas le couper

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=block, callback=callback):
        while True:
            try:
                data = q.get(timeout=0.5)
            except queue.Empty:
                if stop_event is not None and stop_event.is_set():
                    return np.zeros(0, dtype="float32")
                continue
            if stop_event is not None and stop_event.is_set():
                return np.zeros(0, dtype="float32")
            now = time.time()
            rms = float(np.sqrt(np.mean(data ** 2)))
            if level_cb is not None:
                level_cb(rms, speech_start is not None)

            if speech_start is None:
                pre_roll.append(data)
                pre_roll = pre_roll[-6:]
                if rms > threshold:
                    speech_start = now
                    last_voice = now
                    chunks.extend(pre_roll)
                elif wait_seconds is not None and now - started > wait_seconds:
                    return np.zeros(0, dtype="float32")
                continue

            chunks.append(data)
            if rms > threshold:
                last_voice = now
            if now - last_voice > silence_seconds:
                break
            if now - speech_start > max_seconds:
                break

    audio = np.concatenate(chunks)
    # Moins de 300 ms de son : un bruit, pas une phrase
    if audio.size < SAMPLE_RATE * 0.3:
        return np.zeros(0, dtype="float32")
    return audio


# ---------------------------------------------------------------------------
# Reconnaissance vocale
# ---------------------------------------------------------------------------

class Transcriber:
    def __init__(self, model_name: str = config.WHISPER_MODEL):
        self.model_name = model_name
        self.model = None
        self.device = "cpu"
        self._lock = threading.Lock()
        self.to_gpu()

    def to_gpu(self) -> None:
        """Modèle complet sur la carte graphique (mode actif)."""
        from faster_whisper import WhisperModel

        with self._lock:
            if self.device == "cuda" and self.model is not None:
                return
            try:
                self.model = WhisperModel(self.model_name, device="cuda", compute_type=config.WHISPER_COMPUTE)
                self.device = "cuda"
            except Exception as exc:  # noqa: BLE001
                print(f"[whisper] GPU indisponible ({exc}), bascule sur CPU.", file=sys.stderr)
                self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                self.device = "cpu"

    def to_standby(self) -> None:
        """Petit modèle sur processeur, juste pour entendre le mot d'activation : libère la carte."""
        from faster_whisper import WhisperModel

        with self._lock:
            if self.device == "cpu-standby":
                return
            self.model = None
            import gc
            gc.collect()
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
            self.model = WhisperModel(config.WHISPER_STANDBY_MODEL, device="cpu", compute_type="int8",
                                      cpu_threads=4)
            self.device = "cpu-standby"

    def warmup(self) -> None:
        """Premier appel à blanc : initialise CUDA/cuDNN pour que la vraie première phrase soit rapide."""
        self.transcribe(np.zeros(SAMPLE_RATE, dtype="float32") + 1e-4)

    # Phrases que Whisper « invente » sur du silence ou du bruit (génériques de sous-titres).
    _HALLUCINATIONS = (
        "sous-titrage", "sous titrage", "sous-titres", "amara.org", "merci d'avoir regarde",
        "abonnez-vous", "st' 501", "st 501", "merci de votre attention",
    )

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        with self._lock:
            return self._transcribe(audio)

    def _transcribe(self, audio: np.ndarray) -> str:
        segments, _info = self.model.transcribe(
            audio, language=config.LANGUAGE, beam_size=3, vad_filter=True,
            condition_on_previous_text=False, no_speech_threshold=0.5,
            initial_prompt="Bonjour Jarvis. " + ", ".join(config.VOCAB_HINTS) + ".",  # aide Whisper sur les noms propres
        )
        kept = [seg.text.strip() for seg in segments if seg.no_speech_prob < 0.7]
        text = " ".join(kept).strip()
        return "" if is_hallucination(text) else text


def is_hallucination(text: str) -> bool:
    """Vrai si le texte ressemble à une invention de Whisper sur du bruit (générique de sous-titres…)."""
    low = " ".join(_normalize(text).split())
    return any(" ".join(_normalize(h).split()) in low for h in Transcriber._HALLUCINATIONS)


# ---------------------------------------------------------------------------
# Mot d'activation
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text)


_WAKE_VARIANTS = ("jarvis", "djarvis", "jarvice", "jarvys", "jarvi", "charvis", "jervis")
_SLEEP_PHRASES = ("merci jarvis", "au revoir jarvis", "bonne nuit jarvis", "stop jarvis", "a plus jarvis")


_WAKE_RE = re.compile(
    r"(?:\b(?:bonjour|salut|hey|h[ée]|eh|ok|dis|hello|coucou)\b[\s,]*)?"
    r"\b(?:" + "|".join(_WAKE_VARIANTS) + r")\b[\s,.!?;:]*",
    re.IGNORECASE,
)


def strip_wake_word(text: str) -> tuple[bool, str]:
    """Renvoie (mot d'activation entendu ?, texte restant, accents et ponctuation conservés)."""
    m = _WAKE_RE.search(text)
    if m is None:
        return False, text.strip()
    rest = (text[:m.start()] + " " + text[m.end():]).strip(" ,;")
    return True, rest.strip()


def is_sleep_phrase(text: str) -> bool:
    norm = _normalize(text)
    return any(p in norm for p in _SLEEP_PHRASES)


_STOP_PHRASES = ("stop", "tais toi", "chut", "arrete", "silence", "ca suffit", "ok merci", "c est bon")


def is_stop_phrase(text: str) -> bool:
    """Vrai si l'utilisateur veut juste faire taire Jarvis (sans nouvelle demande)."""
    norm = " ".join(_normalize(text).split())
    norm = re.sub(r"\b(jarvis|djarvis|jarvice)\b", "", norm).strip()
    # Court et sans autre demande (« stop », « chut jarvis », « ça suffit ») ; « stop, ouvre Spotify » n'est pas un simple stop.
    return len(norm) <= 12 and any(p in norm for p in _STOP_PHRASES)


# ---------------------------------------------------------------------------
# Synthèse vocale
# ---------------------------------------------------------------------------

_MD_PATTERNS = [
    (re.compile(r"```.*?```", re.S), " "),          # blocs de code
    (re.compile(r"`([^`]*)`"), r"\1"),              # code inline
    (re.compile(r"\\sqrt\{([^}]*)\}"), r"racine de \1"),
    (re.compile(r"\$\$?([^$]*)\$\$?"), r"\1"),      # LaTeX
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # liens
    (re.compile(r"(?<=\d)\s*[*×]\s*(?=\d)"), " fois "),   # 17*23 -> 17 fois 23
    (re.compile(r"(?<=\d)\s*/\s*(?=\d)"), " divisé par "),
    (re.compile(r"[*_#>]+"), ""),                   # gras, italique, titres, citations
    (re.compile(r"^\s*[-•]\s+", re.M), ""),         # puces
    (re.compile(r"(?:^|(?<=[.!?…:]\s))\s*\d{1,2}[.)]\s+(?=[A-Za-zÀ-ÿ])", re.M), ""),  # numéros de liste « 1. », « 2) »
    (re.compile(r"\s+"), " "),
]


def clean_for_speech(text: str) -> str:
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text)
    # Les miettes (« 4. », « Ok. », un numéro de liste) font planter Chatterbox et sautaient en silence :
    # on les recolle à la phrase suivante (ou précédente).
    merged: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if merged and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", merged[-1])) < 6:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    if len(merged) > 1 and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", merged[-1])) < 6:
        last = merged.pop()
        merged[-1] = merged[-1] + " " + last
    out: list[str] = []
    for p in merged:
        if not re.search(r"[A-Za-zÀ-ÿ]{2}", p):
            continue  # que des chiffres ou de la ponctuation : rien à dire
        # Chatterbox préfère des phrases courtes : on coupe les très longues aux virgules
        while len(p) > 220:
            cut = p.rfind(",", 0, 220)
            if cut < 60:
                cut = 220
            out.append(p[:cut + 1].strip())
            p = p[cut + 1:].strip()
        if p:
            out.append(p)
    return out


class Speaker:
    def __init__(self, voice_ref: Path | None = config.VOICE_REF):
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            device = "mps"  # Mac Apple Silicon
        else:
            device = "cpu"
        self.model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        self.sr = self.model.sr
        self.voice_ref = str(voice_ref) if voice_ref and Path(voice_ref).is_file() else None
        self.device = device
        self._lock = threading.Lock()

    def _move(self, device: str) -> None:
        """Déplace les réseaux de Chatterbox entre carte graphique et processeur."""
        import torch

        with self._lock:
            if self.device == device:
                return
            for name in ("t3", "s3gen", "ve", "conds"):
                part = getattr(self.model, name, None)
                if part is None:
                    continue
                if hasattr(part, "to"):
                    setattr(self.model, name, part.to(device))
            self.model.device = device
            self.device = device
            if device == "cpu":
                torch.cuda.empty_cache()

    def to_standby(self) -> None:
        """Libère la carte graphique (veille). La synthèse reste possible sur processeur, plus lente."""
        try:
            self._move("cpu")
        except Exception as exc:  # noqa: BLE001
            print(f"[tts] impossible de passer sur CPU : {exc}", file=sys.stderr)

    def to_gpu(self) -> None:
        try:
            import torch
            if torch.cuda.is_available():
                self._move("cuda")
            elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                self._move("mps")
        except Exception as exc:  # noqa: BLE001
            print(f"[tts] impossible de revenir sur GPU : {exc}", file=sys.stderr)

    def synthesize(self, sentence: str) -> np.ndarray:
        kwargs = {"language_id": config.LANGUAGE}
        if self.voice_ref:
            kwargs["audio_prompt_path"] = self.voice_ref
        with self._lock:
            wav = self.model.generate(sentence, exaggeration=config.TTS_EXAGGERATION,
                                      cfg_weight=config.TTS_CFG, temperature=config.TTS_TEMPERATURE, **kwargs)
        return wav.squeeze().cpu().numpy().astype("float32")

    def warmup(self) -> None:
        self.synthesize("Bonjour.")

    def say(self, text: str, level_cb=None, stop_event: threading.Event | None = None,
            pause_event: threading.Event | None = None) -> None:
        """Parle le texte : chaque phrase est générée pendant que la précédente est lue.

        level_cb    : appelé avec le niveau sonore (rms) toutes les ~50 ms pendant la lecture.
        stop_event  : si posé, la lecture s'interrompt.
        pause_event : tant qu'il est posé, la lecture attend (bruit entendu : on vérifie si c'est une vraie parole).
        """
        sentences = split_sentences(clean_for_speech(text))
        if not sentences:
            return
        q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=3)
        cancelled = threading.Event()

        def producer():
            for s in sentences:
                if cancelled.is_set():
                    break
                try:
                    q.put(self.synthesize(s))
                except Exception as exc:  # noqa: BLE001
                    print(f"[tts] erreur sur « {s[:40]}… » : {exc}, nouvel essai", file=sys.stderr)
                    try:
                        q.put(self.synthesize(s.rstrip(".!?…") + ", voilà."))  # reformulé : Chatterbox cale sur les bouts trop courts
                    except Exception as exc2:  # noqa: BLE001
                        print(f"[tts] phrase sautée « {s[:40]}… » : {exc2}", file=sys.stderr)
            q.put(None)

        threading.Thread(target=producer, daemon=True).start()
        try:
            while True:
                wav = q.get()
                if wav is None:
                    break
                if stop_event is not None and stop_event.is_set():
                    break
                self._play(wav, level_cb, stop_event, pause_event)
        finally:
            cancelled.set()
            if level_cb is not None:
                level_cb(0.0)

    def _play(self, wav: np.ndarray, level_cb, stop_event, pause_event: threading.Event | None = None) -> None:
        if sd is None:
            return  # pas de sortie audio : la réponse reste visible dans la page
        block = int(self.sr * 0.05)
        pos = 0
        with sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32", blocksize=block) as out:
            while pos < len(wav):
                if stop_event is not None and stop_event.is_set():
                    break
                if pause_event is not None and pause_event.is_set():
                    if level_cb is not None:
                        level_cb(0.0)
                    time.sleep(0.05)
                    continue  # en pause : on reprend exactement là où on en était
                chunk = wav[pos:pos + block]
                if len(chunk) < block:
                    chunk = np.pad(chunk, (0, block - len(chunk)))
                if level_cb is not None:
                    level_cb(float(np.sqrt(np.mean(chunk ** 2))))
                out.write(chunk.reshape(-1, 1))
                pos += block

    def stop(self) -> None:
        if sd is not None:
            sd.stop()
