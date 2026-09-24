param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot "docker\compose.yml"
$envFile = Join-Path $repositoryRoot ".env"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Le fichier .env est requis ; ne sauvegardez jamais avec .env.example."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker est requis pour sauvegarder PostgreSQL."
}
if (-not (Get-Command age -ErrorAction SilentlyContinue)) {
    throw "age est requis pour chiffrer la sauvegarde ; aucune sauvegarde en clair ne sera produite."
}

if (-not $OutputPath) {
    $backupDirectory = Join-Path $repositoryRoot "backups"
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    $OutputPath = Join-Path $backupDirectory ("cocoon-{0}.dump.age" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
if (Test-Path -LiteralPath $resolvedOutput) {
    throw "Le fichier de destination existe déjà : $resolvedOutput"
}

$temporaryDump = Join-Path ([IO.Path]::GetTempPath()) ("cocoon-{0}.dump" -f [guid]::NewGuid())
try {
    & docker compose --env-file $envFile -f $composeFile exec -T postgres sh -c 'pg_dump --format=custom --no-owner --no-acl --dbname="$POSTGRES_DB"' > $temporaryDump
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump a échoué ; la sauvegarde chiffrée n’a pas été créée."
    }
    & age -p -o $resolvedOutput $temporaryDump
    if ($LASTEXITCODE -ne 0) {
        throw "Le chiffrement age a échoué."
    }
    Write-Host "Sauvegarde PostgreSQL chiffrée créée : $resolvedOutput"
}
finally {
    if (Test-Path -LiteralPath $temporaryDump) {
        Remove-Item -LiteralPath $temporaryDump -Force
    }
}
