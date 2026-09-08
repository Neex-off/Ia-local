# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE
# Installation automatique sous Windows 10 / 11.
#   .\install.ps1            installation complète (modèle standard)
#   .\install.ps1 -All       + modèles léger, recherche et puissant
#   .\install.ps1 -NoVoice   sans reconnaissance ni synthèse vocale (mode texte seulement)
param([switch]$All, [switch]$NoVoice)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Say "1/6 Python 3.11"
$py = $null
foreach ($c in @("py -3.11", "py -3.12", "python3.11", "python")) {
  try {
    $v = & cmd /c "$c -c `"import sys;print((3,10)<=sys.version_info[:2]<=(3,12))`"" 2>$null
    if ("$v".Trim() -eq "True") { $py = $c; break }
  } catch {}
}
if (-not $py) {
  Say "Python 3.11 absent : installation via winget"
  winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements
  $py = "py -3.11"
}
Write-Host "Python : $(& cmd /c "$py --version")"

Say "2/6 Environnement virtuel"
if (-not (Test-Path .venv)) { & cmd /c "$py -m venv .venv" }
$venv = ".\.venv\Scripts\python.exe"
& $venv -m pip install --upgrade pip wheel | Out-Null

Say "3/6 Dépendances de base"
& $venv -m pip install -r requirements.txt

if (-not $NoVoice) {
  Say "4/6 PyTorch et dépendances vocales (plusieurs Go, patience)"
  $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
  if ($nvidia) { & $venv -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128 }
  else { & $venv -m pip install torch torchaudio }
  & $venv -m pip install --no-deps chatterbox-tts
  & $venv -m pip install -r requirements-voice.txt
  if ($nvidia) { & $venv -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 }
} else { Say "4/6 Mode texte : dépendances vocales ignorées (-NoVoice)" }

Say "5/6 Ollama et modèle"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue; Start-Sleep 3
ollama pull gemma4:12b
if ($All) { ollama pull gemma4:e4b-it-qat; ollama pull granite4.1:8b; ollama pull gemma4:26b-a4b-it-qat }

Say "6/6 Terminé"
New-Item -ItemType Directory -Force workspace | Out-Null
Write-Host @"

Installation terminée.
  Interface Jarvis (fond)   : jarvis.bat          puis dis « Bonjour Jarvis »
  Interface Jarvis (console): jarvis-console.bat
  Mode texte                : lancer.bat
  Arrêter                   : jarvis-arreter.bat
Les modèles de voix (Whisper, Chatterbox, ~4 Go) se téléchargent au premier lancement.
"@
