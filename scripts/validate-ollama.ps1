[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:11434",
    [string]$Model = "gemma4:e4b",
    [ValidateRange(1, 10)]
    [int]$Requests = 3
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd('/')
$tags = Invoke-RestMethod -Uri "$base/api/tags" -Method Get
$models = @($tags.models | ForEach-Object { [string]$_.name })
if ($models -notcontains $Model) {
    throw "Le modèle Ollama '$Model' est absent de $base."
}

$payload = @{
    model = $Model
    messages = @(@{ role = "user"; content = "Réponds uniquement OK." })
    stream = $false
} | ConvertTo-Json -Depth 5 -Compress

$measurements = foreach ($index in 1..$Requests) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $response = Invoke-RestMethod `
        -Uri "$base/v1/chat/completions" `
        -Method Post `
        -ContentType "application/json" `
        -Body $payload
    $watch.Stop()
    $content = [string]$response.choices[0].message.content
    if ($content.Trim() -ne "OK") {
        throw "Réponse Ollama inattendue à la requête $index."
    }
    [pscustomobject]@{
        request = $index
        elapsed_ms = [math]::Round($watch.Elapsed.TotalMilliseconds)
        mode = "llm"
        model = $Model
    }
}

$measurements | ConvertTo-Json -Compress
