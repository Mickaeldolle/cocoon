[CmdletBinding()]
param(
    [string]$Repository = ''
)

$ErrorActionPreference = 'Continue'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Repository)) {
    $Repository = Join-Path $scriptRoot '..'
}
$repoPath = (Resolve-Path -LiteralPath $Repository).Path
$repoForGit = $repoPath.Replace('\', '/')

function Write-Check {
    param(
        [string]$Name,
        [ValidateSet('PASS', 'WARN', 'INFO')][string]$Status,
        [string]$Detail
    )

    Write-Output ('[{0}] {1}: {2}' -f $Status, $Name, $Detail)
}

Write-Output "Cocoon reproducibility audit (read-only)"
Write-Output "Repository: $repoPath"
Write-Output ""

Push-Location $repoPath
try {
    $gitStatus = & git -c "safe.directory=$repoForGit" status --short --branch 2>&1
    if ($LASTEXITCODE -eq 0) {
        $branch = ($gitStatus | Select-Object -First 1).ToString()
        Write-Check 'Git repository' 'PASS' $branch
    } else {
        Write-Check 'Git repository' 'WARN' 'status indisponible ; aucune configuration globale n’a été modifiée'
    }

    $trackedSensitive = @(
        & git -c "safe.directory=$repoForGit" ls-files -- '*.env' '.env.*' '*.pem' '*.key' '*credentials*' '*secrets*' 2>$null
    )
    if ($trackedSensitive.Count -eq 0) {
        Write-Check 'Tracked secrets' 'PASS' 'aucun fichier sensible connu n’est suivi'
    } else {
        Write-Check 'Tracked secrets' 'WARN' ("{0} chemin(s) sensible(s) suivi(s), noms volontairement masqués" -f $trackedSensitive.Count)
    }

    $envCandidates = @(
        (Join-Path $repoPath '.env'),
        (Join-Path $repoPath '.env.example'),
        (Join-Path $repoPath 'apps/api/.env'),
        (Join-Path $repoPath 'apps/api/.env.example'),
        (Join-Path $repoPath 'apps/mobile/.env'),
        (Join-Path $repoPath 'apps/mobile/.env.example')
    )
    $envFiles = @($envCandidates | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Item -LiteralPath $_ })
    $exampleFiles = @($envFiles | Where-Object { $_.Name -like '*.example' })
    $localEnvFiles = @($envFiles | Where-Object { $_.Name -notlike '*.example' })
    Write-Check 'Environment files' 'INFO' ("{0} example(s), {1} local file(s) détecté(s) ; valeurs non affichées" -f $exampleFiles.Count, $localEnvFiles.Count)

    $ignoredEnv = & git -c "safe.directory=$repoForGit" check-ignore -q '.env' 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Check 'Ignored environment files' 'PASS' '.env local est ignoré par Git'
    } else {
        Write-Check 'Ignored environment files' 'WARN' 'au moins un .env attendu n’est pas confirmé ignoré'
    }

    $lockfileCandidates = @(
        (Join-Path $repoPath 'uv.lock'),
        (Join-Path $repoPath 'apps/api/uv.lock'),
        (Join-Path $repoPath 'package-lock.json'),
        (Join-Path $repoPath 'apps/mobile/package-lock.json'),
        (Join-Path $repoPath 'pnpm-lock.yaml'),
        (Join-Path $repoPath 'apps/mobile/pnpm-lock.yaml'),
        (Join-Path $repoPath 'yarn.lock')
    )
    $lockfiles = @($lockfileCandidates | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Item -LiteralPath $_ })
    if ($lockfiles.Count -gt 0) {
        Write-Check 'Dependency lockfiles' 'PASS' (($lockfiles | ForEach-Object { $_.FullName.Substring($repoPath.Length + 1) }) -join ', ')
    } else {
        Write-Check 'Dependency lockfiles' 'WARN' 'aucun lockfile détecté'
    }

    $versionCommands = @(
        @{ Name = 'Python'; Command = { & (Join-Path $repoPath 'apps/api/.venv/Scripts/python.exe') --version } },
        @{ Name = 'Node'; Command = { & node --version } },
        @{ Name = 'npm'; Command = { & npm --version } },
        @{ Name = 'uv'; Command = { & uv --version } }
    )
    foreach ($version in $versionCommands) {
        try {
            $output = (& $version.Command 2>&1 | Select-Object -First 1).ToString()
            if ($output -and $output -notmatch 'not recognized|cannot find|CommandNotFoundException') {
                Write-Check $version.Name 'INFO' $output
            } else {
                Write-Check $version.Name 'WARN' 'outil ou environnement non disponible'
            }
        } catch {
            Write-Check $version.Name 'WARN' 'outil ou environnement non disponible'
        }
    }

    $apiManifest = Get-Content -Raw -LiteralPath (Join-Path $repoPath 'apps/api/pyproject.toml')
    foreach ($dependencyName in @('fastapi', 'SQLAlchemy', 'alembic')) {
        $escapedName = [regex]::Escape($dependencyName)
        $pattern = '(?im)^\s*"?' + $escapedName + '"?\s*([<>=!~].*)?$'
        $match = [regex]::Match($apiManifest, $pattern)
        if ($match.Success) {
            $spec = ($match.Groups[1].Value).Trim()
            if (-not $spec) { $spec = 'déclaré' }
            Write-Check $dependencyName 'INFO' $spec
        } else {
            Write-Check $dependencyName 'WARN' 'non trouvé dans pyproject.toml'
        }
    }

    $mobilePackage = Get-Content -Raw -LiteralPath (Join-Path $repoPath 'apps/mobile/package.json') | ConvertFrom-Json
    $expoVersion = [string]$mobilePackage.dependencies.expo
    if ($expoVersion) {
        Write-Check 'Expo' 'INFO' $expoVersion
    } else {
        Write-Check 'Expo' 'WARN' 'non trouvé dans package.json'
    }

    $migrationFiles = @(Get-ChildItem -LiteralPath (Join-Path $repoPath 'apps/api/migrations/versions') -File -Filter '*.py' -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($migrationFiles.Count -gt 0) {
        Write-Check 'Alembic migrations' 'INFO' ("{0} fichier(s), de {1} à {2}" -f $migrationFiles.Count, $migrationFiles[0].BaseName, $migrationFiles[-1].BaseName)
    } else {
        Write-Check 'Alembic migrations' 'WARN' 'répertoire de migrations vide ou absent'
    }

    Push-Location (Join-Path $repoPath 'apps/api')
    try {
        $heads = & .\.venv\Scripts\alembic.exe heads 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check 'Alembic heads' 'PASS' (($heads -join ' ') -replace '\s+', ' ')
        } else {
            Write-Check 'Alembic heads' 'WARN' 'impossible à calculer dans l’environnement courant'
        }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
