$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$BotDirectory = Join-Path $Root "discord-bot"

if (-not (Test-Path (Join-Path $Root ".env"))) {
    throw "Missing .env in the repo root. Add DISCORD_TOKEN and SEARXNG_SECRET there."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install/start Docker Desktop, then retry."
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is unavailable. Check that Docker Desktop is running."
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama was not found. Install and start Ollama, then retry."
}

try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
} catch {
    throw "Ollama is not responding at http://127.0.0.1:11434. Start Ollama, then retry."
}

ollama show gemma4:12b *> $null
if ($LASTEXITCODE -ne 0) {
    throw "The gemma4:12b model is missing. Download it with: ollama pull gemma4:12b"
}

if (-not (Test-Path $VenvPython)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python was not found. Install Python 3, then retry."
    }

    python -m venv (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the Python virtual environment."
    }

    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the Python requirements."
    }
}

Push-Location $Root
try {
    docker compose up -d searxng
    if ($LASTEXITCODE -ne 0) {
        throw "Could not start SearXNG. Check Docker output and whether port 8088 is already in use."
    }
} finally {
    Pop-Location
}

Push-Location $BotDirectory
try {
    & $VenvPython "main.py"
    $BotExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $BotExitCode
