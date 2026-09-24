$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repositoryRoot "apps\api"
$mobileRoot = Join-Path $repositoryRoot "apps\mobile"

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "audit-reproducibility.ps1")
if ($LASTEXITCODE -ne 0) { throw "L'audit de reproductibilité a échoué." }

Push-Location $apiRoot
try {
    & ".\.venv\Scripts\python.exe" -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Les tests API ont échoué." }
    & ".\.venv\Scripts\ruff.exe" check app migrations tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff a échoué." }
    & ".\.venv\Scripts\python.exe" -m alembic heads
    if ($LASTEXITCODE -ne 0) { throw "La lecture de la tête Alembic a échoué." }
}
finally {
    Pop-Location
}

Push-Location $mobileRoot
try {
    node node_modules/typescript/bin/tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "Le typecheck mobile a échoué." }
}
finally {
    Pop-Location
}

Push-Location $repositoryRoot
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate-compose-security.ps1
    if ($LASTEXITCODE -ne 0) { throw "La sécurité Compose a échoué." }
    docker compose --env-file .env.example -f docker/compose.yml config --quiet
    if ($LASTEXITCODE -ne 0) { throw "La configuration Compose est invalide." }
}
finally {
    Pop-Location
}

Write-Host "Validation MVP terminée."
