$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composePath = Join-Path $repositoryRoot "docker\compose.yml"
$compose = Get-Content -LiteralPath $composePath -Raw

if ($compose -match '(?m)^  redis:' -or $compose -match '\bREDIS_URL\b') {
    throw "Redis ne doit plus être démarré ni configuré par le Compose principal."
}

function Get-ServiceBlock([string]$name) {
    $escaped = [regex]::Escape($name)
    $match = [regex]::Match(
        $compose,
        "(?ms)^  $escaped`:\r?\n.*?(?=^  [a-zA-Z0-9_-]+`:\r?\n|\z)"
    )
    if (-not $match.Success) {
        throw "Le service Compose '$name' est introuvable."
    }
    return $match.Value
}

$privateNetwork = [regex]::Match($compose, "(?ms)^networks`:\r?\n.*\bprivate`:\r?\n.*?internal`:\s*true")
if (-not $privateNetwork.Success) {
    throw "Le réseau privé Compose doit rester marqué internal: true."
}

foreach ($serviceName in @("postgres")) {
    $service = Get-ServiceBlock $serviceName
    if ($service -match "(?m)^\s+ports`:\s*$") {
        throw "Le service $serviceName ne doit pas publier de port vers l'hôte."
    }
}

$migrate = Get-ServiceBlock "migrate"
if ($migrate -notmatch '(?m)^\s+command:\s+\["alembic",\s+"upgrade",\s+"head"\]') {
    throw "Le service migrate doit être le seul service Compose à appliquer les migrations."
}
foreach ($serviceName in @("api", "capture-worker", "reminder-worker", "memory-worker")) {
    $service = Get-ServiceBlock $serviceName
    if ($service -notmatch '(?m)^\s+target:\s+runtime\s*$') {
        throw "Le service $serviceName doit utiliser l'image runtime sans dépendances de test."
    }
    if ($service -match "alembic upgrade head") {
        throw "Le service $serviceName ne doit pas exécuter les migrations lui-même."
    }
    if ($service -notmatch "service_completed_successfully") {
        throw "Le service $serviceName doit attendre la réussite du service migrate."
    }
}

$memoryWorker = Get-ServiceBlock "memory-worker"
if ($memoryWorker -notmatch '(?m)^\s+profiles:\s+\[memory\]') {
    throw "Le worker mémoire doit rester facultatif via le profil memory."
}
if ($memoryWorker -match '(?m)^\s+ports:\s*$') {
    throw "Le worker mémoire ne doit publier aucun port vers l'hôte."
}
if ($memoryWorker -notmatch '(?m)^\s+- egress\s*$' -or
    $memoryWorker -notmatch '(?m)^\s+- private\s*$') {
    throw "Le worker mémoire doit joindre la base privée et son runtime d'embedding."
}
foreach ($variableName in @("DATABASE_URL", "MEMORY_EMBEDDINGS_ENABLED", "MEMORY_VECTOR_ENABLED", "MEMORY_EMBEDDING_BASE_URL", "MEMORY_EMBEDDING_MODEL")) {
    if ($memoryWorker -notmatch ("(?m)^\s+" + [regex]::Escape($variableName) + ":")) {
        throw "La variable $variableName doit être transmise au worker mémoire."
    }
}

$api = Get-ServiceBlock "api"
if ($api -match "(?m)^\s+ports`:\s*$") {
    throw "L'API doit rester derrière le reverse proxy et utiliser expose uniquement."
}

foreach ($variableName in @("STT_API_URL", "STT_API_KEY", "STT_MODEL", "WEB_PUSH_PUBLIC_KEY", "WEB_PUSH_PRIVATE_KEY", "WEB_PUSH_SUBJECT", "WEBAUTHN_ORIGIN")) {
    if ($api -notmatch ("(?m)^\s+" + [regex]::Escape($variableName) + ":")) {
        throw "La variable $variableName doit être transmise au service API pour le contrat STT privé."
    }
}
$reminderWorker = Get-ServiceBlock "reminder-worker"
foreach ($variableName in @("WEB_PUSH_PUBLIC_KEY", "WEB_PUSH_PRIVATE_KEY", "WEB_PUSH_SUBJECT")) {
    if ($reminderWorker -notmatch ("(?m)^\s+" + [regex]::Escape($variableName) + ":")) {
        throw "La variable $variableName doit être transmise au worker de rappels."
    }
}
foreach ($variableName in @("MEMORY_EMBEDDINGS_ENABLED", "MEMORY_VECTOR_ENABLED", "MEMORY_EMBEDDING_BASE_URL", "MEMORY_EMBEDDING_MODEL", "ASSISTANT_PROMPT_MAX_BYTES")) {
    if ($api -notmatch ("(?m)^\s+" + [regex]::Escape($variableName) + ":")) {
        throw "La variable $variableName doit être transmise à l'API."
    }
}

# The Supabase override must not silently start a second, unused PostgreSQL.
$previousMigrationUrl = [Environment]::GetEnvironmentVariable("MIGRATION_DATABASE_URL", "Process")
$migrationCheckUrl = "postgresql+psycopg://migration-check:example@invalid.example:5432/cocoon_ci"
$env:MIGRATION_DATABASE_URL = $migrationCheckUrl
$composeArguments = @(
    "compose", "--env-file", (Join-Path $repositoryRoot ".env.example"),
    "-f", $composePath,
    "-f", (Join-Path $repositoryRoot "docker\compose.supabase.yml")
)
try {
    $remoteServices = @(& docker @composeArguments config --services)
    if ($LASTEXITCODE -ne 0) { throw "La surcharge Supabase Compose est invalide." }
    if ($remoteServices -contains "postgres") {
        throw "La surcharge Supabase ne doit pas démarrer PostgreSQL local."
    }
    if ($remoteServices -contains "redis") {
        throw "La surcharge Supabase ne doit pas démarrer l'ancien service Redis."
    }
    $remoteMemoryServices = @(& docker @composeArguments --profile memory config --services)
    if ($LASTEXITCODE -ne 0) { throw "Le profil mémoire Supabase Compose est invalide." }
    if ($remoteMemoryServices -notcontains "memory-worker") {
        throw "Le profil memory doit démarrer le worker mémoire."
    }
    $remoteConfig = (& docker @composeArguments --profile memory config --format json | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw "Le rendu Supabase Compose est invalide." }
    if ($remoteConfig.services.migrate.environment.DATABASE_URL -ne $migrationCheckUrl) {
        throw "Le migrateur Supabase doit utiliser MIGRATION_DATABASE_URL."
    }
    foreach ($serviceName in @("api", "capture-worker", "reminder-worker", "memory-worker")) {
        $service = $remoteConfig.services.PSObject.Properties[$serviceName].Value
        if ($null -eq $service -or $service.environment.DATABASE_URL -eq $migrationCheckUrl) {
            throw "Le service $serviceName ne doit pas recevoir l'URL de migration."
        }
    }
}
finally {
    [Environment]::SetEnvironmentVariable("MIGRATION_DATABASE_URL", $previousMigrationUrl, "Process")
}

Write-Host "Sécurité Compose validée : PostgreSQL privé, worker mémoire opt-in et réseau interne."
