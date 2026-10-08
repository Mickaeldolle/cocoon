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

foreach ($serviceName in @("postgres", "redis")) {
    $service = Get-ServiceBlock $serviceName
    if ($service -match "(?m)^\s+ports`:\s*$") {
        throw "Le service $serviceName ne doit pas publier de port vers l'hôte."
    }
}

$migrate = Get-ServiceBlock "migrate"
if ($migrate -notmatch '(?m)^\s+command:\s+\["alembic",\s+"upgrade",\s+"head"\]') {
    throw "Le service migrate doit être le seul service Compose à appliquer les migrations."
}
foreach ($serviceName in @("api", "capture-worker", "reminder-worker")) {
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

if ($migrate -notmatch '(?m)^\s+target:\s+runtime\s*$') {
    throw "Le service migrate doit utiliser l'image runtime sans dépendances de test."
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

foreach ($variableName in @("STT_API_URL", "STT_API_KEY", "STT_MODEL")) {
    if ($api -notmatch ("(?m)^\s+" + [regex]::Escape($variableName) + ":")) {
        throw "La variable $variableName doit être transmise au service API pour le contrat STT privé."
    }
}

Write-Host "Sécurité Compose validée : PostgreSQL/Redis privés et réseau interne."
