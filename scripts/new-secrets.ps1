# Completa los secretos tecnicos locales que falten. Conserva los existentes.
$ErrorActionPreference = "Stop"
function New-Secret([string]$prefix) {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $value = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "A").Replace("/", "B")
    return "${prefix}_${value}"
}
$required = [ordered]@{
    KC_VOIP_CLIENT_SECRET = (New-Secret "NexoVoipOIDC")
    VOIP_SESSION_SECRET = (New-Secret "NexoVoipSession")
    VOIP_AMI_SECRET = (New-Secret "NexoVoipAMI")
    JICOFO_AUTH_PASSWORD = (New-Secret "NexoJicofo")
    JICOFO_COMPONENT_SECRET = (New-Secret "NexoJicofoComponent")
    JVB_AUTH_PASSWORD = (New-Secret "NexoJVB")
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
    Write-Host "Se agregaron $added secretos tecnicos a .env. No lo compartas ni lo subas a Git."
} else {
    Write-Host "El archivo .env ya contiene todos los secretos tecnicos; no se modifica."
}
