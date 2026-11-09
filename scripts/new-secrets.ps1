# Completa los secretos locales que falten. Conserva los valores existentes.
$ErrorActionPreference = "Stop"
function New-Secret([string]$prefix) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 24
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $value = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "A").Replace("/", "B")
    return "${prefix}_${value}"
}
$required = [ordered]@{
    GRAFANA_USER = "admin"
    GRAFANA_PASSWORD = (New-Secret "NexoGrafana")
    SIP_PASSWORD_100 = (New-Secret "NexoSip100")
    SIP_PASSWORD_101 = (New-Secret "NexoSip101")
    WEBRTC_PASSWORD_100 = (New-Secret "NexoWeb100")
    WEBRTC_PASSWORD_101 = (New-Secret "NexoWeb101")
}
$path = Join-Path (Get-Location) ".env"
$lines = [System.Collections.Generic.List[string]]::new()
if (Test-Path $path) {
    [System.IO.File]::ReadAllLines($path) | ForEach-Object { $lines.Add($_) }
}
$added = 0
foreach ($entry in $required.GetEnumerator()) {
    if (-not ($lines | Where-Object { $_ -match "^$([regex]::Escape($entry.Key))=" })) {
        $lines.Add("$($entry.Key)=$($entry.Value)")
        $added++
    }
}
if ($added -gt 0) {
    [System.IO.File]::WriteAllLines($path, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Se agregaron $added valores a .env. No lo compartas ni lo subas a Git."
} else {
    Write-Host "El archivo .env ya contiene todos los valores; no se modifica."
}
