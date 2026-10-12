<#
.SYNOPSIS
    Starts the pcbpick backend and frontend for local development, with the
    Ollama-backed LLM fallback enabled (PCBPICK_USE_LLM=1). Ollama and its Open WebUI
    management UI run in the `ollama`/`open-webui` Docker Compose services (see
    docker-compose.yml) so no local `ollama` install is needed. Each service opens in
    its own PowerShell window so you can watch its logs; close a window to stop that
    service.
#>

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$ollamaModel = if ($env:PCBPICK_OLLAMA_MODEL) { $env:PCBPICK_OLLAMA_MODEL } else { "llama3.2:3b" }
$ollamaBaseUrl = if ($env:PCBPICK_OLLAMA_BASE_URL) { $env:PCBPICK_OLLAMA_BASE_URL } else { "http://localhost:11434" }

function Test-OllamaReachable {
    try {
        Invoke-WebRequest -Uri "$ollamaBaseUrl/api/tags" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warning "docker was not found on PATH; skipping Ollama container startup. LLM-assisted stages will degrade gracefully."
} else {
    Write-Host "Starting Ollama + Open WebUI containers (docker compose up -d ollama open-webui)..."
    Push-Location $repoRoot
    try {
        docker compose up -d ollama open-webui
    } finally {
        Pop-Location
    }

    Write-Host "Waiting for Ollama to become reachable at $ollamaBaseUrl..."
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-OllamaReachable) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
    }

    if (Test-OllamaReachable) {
        $haveModel = (docker exec pcbpick-ollama ollama list 2>$null) -match [regex]::Escape($ollamaModel)
        if (-not $haveModel) {
            Write-Host "Pulling model '$ollamaModel' into the Ollama container (first run only, may take a while)..."
            docker exec pcbpick-ollama ollama pull $ollamaModel
        }
    } else {
        Write-Warning "Ollama did not become reachable within 30s; continuing without it -- LLM-assisted stages will degrade gracefully."
    }
}

Write-Host "Starting pcbpick backend (uvicorn, PCBPICK_USE_LLM=1)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$repoRoot'; `$env:PCBPICK_USE_LLM = '1'; uv run uvicorn pcbpick.api.app:app --reload"
)

Write-Host "Starting pcbpick frontend (vite dev server)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$repoRoot\web'; npm run dev"
)

Write-Host ""
Write-Host "Backend:    http://localhost:8000  (health check at /health)"
Write-Host "Frontend:   http://localhost:5173"
Write-Host "Ollama UI:  http://localhost:3000  (Open WebUI, if docker was found)"
