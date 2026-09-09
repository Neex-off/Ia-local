# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Serveur de l'interface Jarvis : sert ui/index.html et relaie les événements du cœur en WebSocket.

Lancer :  jarvis.bat  (en fond, icône près de l'horloge, sans fenêtre)
          jarvis-console.bat  (avec la fenêtre noire, pour voir les messages)
Fonctionnement :
  - en veille il n'écoute que « Bonjour Jarvis » ;
  - au réveil il ouvre la page http://127.0.0.1:8765 si aucune n'est ouverte ;
  - tant qu'une page est ouverte il reste actif ; quand on la ferme il se rendort.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")  # pas de barres de progression Chatterbox dans le journal

import config

ROOT = Path(__file__).parent
UI_DIR = ROOT / "ui"
URL = f"http://{config.UI_HOST}:{config.UI_PORT}"
# Sans console (pythonw), un sous-processus console ouvrirait une fenêtre cmd : on l'interdit.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Lancé avec pythonw (sans console) : stdout/stderr n'existent pas, on écrit dans jarvis.log
if sys.stdout is None or sys.stderr is None:
    _log = open(ROOT / "jarvis.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log

import uvicorn  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from jarvis_core import JarvisCore  # noqa: E402

app = FastAPI()
clients: set[WebSocket] = set()
history: deque[dict] = deque(maxlen=80)   # derniers événements « importants » pour un nouvel onglet
events: asyncio.Queue[dict] | None = None
loop: asyncio.AbstractEventLoop | None = None
core: JarvisCore | None = None
BOOT_ID = str(int(time.time()))  # change à chaque démarrage : la page ouverte se recharge pour prendre le nouveau code


def emit(event: dict) -> None:
    """Appelé depuis les threads du cœur : pousse l'événement vers la boucle asyncio."""
    event.setdefault("t", time.time())
    if event["type"] in ("user", "assistant", "tool", "heard", "error", "loading", "view", "agenda_goto"):
        history.append(event)
        if event["type"] == "tool":
            print(f"{time.strftime('%H:%M:%S')} [outil] {event['name']}({json.dumps(event.get('args', {}), ensure_ascii=False)[:200]}) -> {str(event.get('result', ''))[:120]!r}", flush=True)
        elif event["type"] in ("user", "assistant", "error"):
            print(f"{time.strftime('%H:%M:%S')} [{event['type']}] {str(event.get('text', ''))[:300]}", flush=True)
    if loop is not None and events is not None:
        loop.call_soon_threadsafe(events.put_nowait, event)


def gpu_stats() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, creationflags=NO_WINDOW,
        ).stdout.strip().splitlines()[0]
        used, total, util, temp = [float(x) for x in out.split(",")]
        return {"type": "stats", "vram_used": used / 1024, "vram_total": total / 1024,
                "gpu_util": util, "gpu_temp": temp, "clients": len(clients),
                "awake": core.awake if core else False, "state": core.state if core else "loading"}
    except Exception:  # noqa: BLE001
        return None


def stats_thread() -> None:
    while True:
        s = gpu_stats()
        if s:
            emit(s)
        time.sleep(2)


async def broadcaster() -> None:
    while True:
        event = await events.get()
        data = json.dumps(event, ensure_ascii=False)
        dead = []
        for ws in list(clients):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)


@app.on_event("startup")
async def startup() -> None:
    global events, loop, core
    loop = asyncio.get_running_loop()
    events = asyncio.Queue()
    asyncio.create_task(broadcaster())
    model_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    core = JarvisCore(emit=emit, model=model_args[0] if model_args else None)
    core.on_wake = open_page_if_needed

    def boot():
        core.load()
        core.run()

    threading.Thread(target=boot, daemon=True).start()
    threading.Thread(target=stats_thread, daemon=True).start()


@app.get("/")
async def index():
    return FileResponse(UI_DIR / "index.html")


def open_page_if_needed() -> None:
    """Ouvre l'interface dans le navigateur s'il n'y a aucune page connectée."""
    if not clients:
        print(f"[jarvis] réveil : ouverture de {URL}", flush=True)
        webbrowser.open(URL)


async def sleep_if_no_client() -> None:
    """Quand la dernière page se ferme : petit délai (rechargement possible), puis retour en veille."""
    await asyncio.sleep(2.5)
    if not clients and core is not None:
        core.keep_awake = False
        if core.state != "loading":
            core.sleep()
        print("[jarvis] page fermée : retour en veille", flush=True)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    if core is not None:
        core.keep_awake = True
        if core.state != "loading" and not core.awake:
            core.wake()  # une page qui s'ouvre = on veut lui parler
    await ws.send_text(json.dumps({
        "type": "hello", "name": config.ASSISTANT_NAME, "model": core.model if core else config.MODEL, "boot": BOOT_ID,
        "state": core.state if core else "loading", "awake": core.awake if core else False,
        "mic": core.mic_enabled if core else True, "history": list(history),
    }, ensure_ascii=False))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if core is None or core.state == "loading":
                continue
            if kind == "text":
                core.submit_text(str(msg.get("text", "")))
            elif kind == "wake":
                core.wake()
            elif kind == "sleep":
                core.sleep()
            elif kind == "stop":
                core.stop_speaking()
            elif kind == "mic":
                core.set_mic(bool(msg.get("enabled", True)))
            elif kind == "reset":
                core.reset()
            elif kind == "open":  # clic sur un projet dans la vue projets (dossier local ou page GitHub)
                import tools
                target = str(msg.get("path", ""))
                if target.startswith(("http://", "https://")):
                    webbrowser.open(target)
                else:
                    tools.open_file(target)
            elif kind == "view":  # bouton Retour de la vue projets
                emit({"type": "view", "view": str(msg.get("view", "home"))})
                if msg.get("view") == "home":
                    import tools
                    tools._AGENDA_OPEN = False
                    tools._AGENDA_SHOWN.clear()
            elif kind == "agenda_month":  # boutons < > de l'agenda : le serveur suit le mois affiché
                import tools
                try:
                    tools._AGENDA_SHOWN[:] = [int(msg.get("year")), int(msg.get("month"))]
                    tools._AGENDA_OPEN = True
                except (TypeError, ValueError):
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
        if not clients:
            asyncio.create_task(sleep_if_no_client())


def open_browser_later() -> None:
    time.sleep(1.5)
    webbrowser.open(URL)


def start_tray() -> None:
    """Icône près de l'horloge : ouvrir l'interface, réveiller, quitter."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), outline=(79, 216, 255, 255), width=4)
    d.ellipse((20, 20, 44, 44), fill=(79, 216, 255, 255))

    def state_text(_item):
        if core is None:
            return "Démarrage…"
        return {"loading": "Chargement…", "idle": "En veille", "listening": "À l'écoute",
                "thinking": "Réflexion", "tool": "Outil", "speaking": "Parle"}.get(core.state, core.state)

    def quit_app(icon, _item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(state_text, None, enabled=False),
        pystray.MenuItem("Ouvrir l'interface", lambda: webbrowser.open(URL), default=True),
        pystray.MenuItem("Réveiller", lambda: core and core.wake()),
        pystray.MenuItem("Rendormir", lambda: core and core.sleep()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter Jarvis", quit_app),
    )
    icon = pystray.Icon("jarvis", img, "Jarvis", menu)
    icon.run_detached()


def lower_priority() -> None:
    """Priorité processeur « inférieure à la normale » : Jarvis ne ralentit pas les jeux et applis au premier plan."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            BELOW_NORMAL = 0x00004000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
        else:
            os.nice(5)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    lower_priority()
    print(f"[jarvis] démarrage {time.strftime('%d/%m/%Y %H:%M:%S')}", flush=True)
    try:
        start_tray()
    except Exception as exc:  # noqa: BLE001  (Linux sans zone de notification, Wayland…) : Jarvis marche sans icône
        print(f"[jarvis] pas d'icône près de l'horloge ({exc}) ; la page reste accessible sur {URL}", flush=True)
    import voice
    if voice.AUDIO_ERROR:
        print(f"[jarvis] {voice.AUDIO_ERROR}", flush=True)
        history.append({"type": "error", "text": voice.AUDIO_ERROR, "t": time.time()})
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser_later, daemon=True).start()
    uvicorn.run(app, host=config.UI_HOST, port=config.UI_PORT, log_level="warning")
