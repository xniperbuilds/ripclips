# =====================================================================
# RipClips - one-command setup for Windows (PowerShell)
#   Run:  powershell -ExecutionPolicy Bypass -File setup.ps1
# =====================================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

Write-Host "== RipClips setup ==" -ForegroundColor Cyan

# --- Python ---
if (-not (Have "python")) {
    Write-Host "Python not found. Install Python 3.9+ from https://python.org and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "[ok] python: $((python --version) 2>&1)"

# --- virtual environment ---
if (-not (Test-Path "$root\.venv")) {
    Write-Host "Creating virtual environment (.venv) ..."
    python -m venv .venv
}
$py = "$root\.venv\Scripts\python.exe"

# --- python deps ---
Write-Host "Installing Python dependencies ..."
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r "$root\requirements.txt"

# --- ffmpeg ---
if (Have "ffmpeg") {
    Write-Host "[ok] ffmpeg found on PATH"
} else {
    Write-Host "ffmpeg not found - attempting install via winget ..." -ForegroundColor Yellow
    if (Have "winget") {
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        Write-Host "If ffmpeg is still not detected, open a NEW terminal so PATH refreshes." -ForegroundColor Yellow
    } else {
        Write-Host "winget not available. Install ffmpeg manually: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Activate the venv with:  .\.venv\Scripts\Activate.ps1"
Write-Host "Then hand a YouTube URL to your AI agent (Claude Code / Codex) - it reads AGENTS.md and runs the pipeline."
