param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [Parameter(Mandatory = $true)]
    [ValidateSet("RESTORE COCOON")]
    [string]$ConfirmText
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot "docker\compose.yml"
$envFile = Join-Path $repositoryRoot ".env"
$resolvedInput = [IO.Path]::GetFullPath($InputPath)

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Le fichier .env est requis ; la restauration est refusée sans configuration explicite."
}
if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) {
    throw "La sauvegarde chiffrée est introuvable : $resolvedInput"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker est requis pour restaurer PostgreSQL."
}
if (-not (Get-Command age -ErrorAction SilentlyContinue)) {
    throw "age est requis pour déchiffrer la sauvegarde."
}

Write-Warning "Cette opération remplace les données PostgreSQL du service compose ciblé."
Write-Warning "Elle est volontairement destructive et ne doit jamais viser une base personnelle par erreur."
$temporaryDump = Join-Path ([IO.Path]::GetTempPath()) ("cocoon-restore-{0}.dump" -f [guid]::NewGuid())
$containerPath = "/tmp/" + [IO.Path]::GetFileName($temporaryDump)
$containerId = ""
try {
    & age -d -o $temporaryDump $resolvedInput
    if ($LASTEXITCODE -ne 0) {
        throw "Le déchiffrement age a échoué ; aucune donnée n’a été restaurée."
    }
    $containerId = (& docker compose --env-file $envFile -f $composeFile ps -q postgres).Trim()
    if (-not $containerId) {
        throw "Le conteneur PostgreSQL n’est pas démarré."
    }
    & docker cp $temporaryDump ("{0}:{1}" -f $containerId, $containerPath)
    if ($LASTEXITCODE -ne 0) {
        throw "La copie temporaire vers PostgreSQL a échoué."
    }
    & docker compose --env-file $envFile -f $composeFile exec -T postgres sh -c "pg_restore --clean --if-exists --exit-on-error --no-owner --no-acl --dbname=\"`$POSTGRES_DB\" '$containerPath'"
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore a échoué ; vérifiez la base cible et les migrations."
    }
    Write-Host "Restauration PostgreSQL terminée. Relancez les migrations et les sondes avant de remettre le service en ligne."
}
finally {
    if ($containerId) {
        & docker compose --env-file $envFile -f $composeFile exec -T postgres rm -f $containerPath 2>$null
    }
    if (Test-Path -LiteralPath $temporaryDump) {
        Remove-Item -LiteralPath $temporaryDump -Force
    }
}
