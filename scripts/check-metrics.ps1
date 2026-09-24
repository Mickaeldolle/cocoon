[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [Parameter(Mandatory = $true)]
    [ValidatePattern('.{32,}')]
    [string]$MetricsToken,
    [int]$MaxInFlight = 32,
    [int]$Max5xx = 0
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd('/')

function Get-MetricValue {
    param(
        [string]$Text,
        [string]$MetricName,
        [string]$LabelPattern = ''
    )

    $escapedName = [regex]::Escape($MetricName)
    $pattern = "(?m)^$escapedName(?:\{$LabelPattern\})?\s+([0-9]+(?:\.[0-9]+)?)\s*$"
    $match = [regex]::Match($Text, $pattern)
    if (-not $match.Success) {
        throw "La métrique requise est absente : $MetricName"
    }
    return [double]$match.Groups[1].Value
}

$readiness = Invoke-WebRequest -Uri "$base/health/ready" -Method Get
if ($readiness.StatusCode -ne 200) {
    throw "La readiness API a répondu HTTP $($readiness.StatusCode)."
}

$metrics = Invoke-WebRequest -Uri "$base/internal/metrics" -Method Get -Headers @{
    'X-Metrics-Token' = $MetricsToken
}
if ($metrics.StatusCode -ne 200) {
    throw "La sonde métriques a répondu HTTP $($metrics.StatusCode)."
}

$body = [string]$metrics.Content
$inFlight = Get-MetricValue -Text $body -MetricName 'cocoon_http_requests_in_flight'
$serverErrors = 0.0
$errorMatches = [regex]::Matches(
    $body,
    '(?m)^cocoon_http_requests_total\{[^}]*status_class="5xx"[^}]*\}\s+([0-9]+(?:\.[0-9]+)?)\s*$'
)
foreach ($match in $errorMatches) {
    $serverErrors += [double]$match.Groups[1].Value
}

if ($inFlight -gt $MaxInFlight) {
    throw "Trop de requêtes en cours : $inFlight (seuil $MaxInFlight)."
}
if ($serverErrors -gt $Max5xx) {
    throw "Le compteur HTTP 5xx est à $serverErrors (seuil $Max5xx)."
}

Write-Output ("OK readiness=ready in_flight={0} http_5xx={1}" -f $inFlight, $serverErrors)
