# H6 - Videoconferencia: Jitsi Meet (web, prosody, jicofo, jvb) en https://localhost:8444
# Uso (desde la raíz del proyecto):  powershell -ExecutionPolicy Bypass -File .\h6-jitsi.ps1
$ErrorActionPreference = "Stop"
$base = Join-Path $PSScriptRoot "jitsi"
New-Item -ItemType Directory -Force -Path $base | Out-Null
Set-Location $base

# 1) Descarga la última versión estable del despliegue oficial (si no existe)
if (-not (Test-Path "docker-jitsi-meet")) {
  $rel = Invoke-RestMethod https://api.github.com/repos/jitsi/docker-jitsi-meet/releases/latest -Headers @{ "User-Agent" = "nexo" }
  Invoke-WebRequest -UseBasicParsing $rel.zipball_url -OutFile jitsi.zip
  Expand-Archive jitsi.zip -DestinationPath tmp -Force
  Move-Item (Get-ChildItem tmp | Select-Object -First 1).FullName docker-jitsi-meet
  Remove-Item tmp, jitsi.zip -Recurse -Force
}
Set-Location docker-jitsi-meet

# 2) .env con contraseñas aleatorias y puertos que no chocan con el resto del proyecto
if (-not (Test-Path ".env")) {
  $env = Get-Content env.example | ForEach-Object {
    if ($_ -match '^(\w*(PASSWORD|SECRET))=\s*$') {
      $pw = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_})
      "$($Matches[1])=$pw"
    } else { $_ }
  }
  $env += "", "CONFIG=./jitsi-cfg", "HTTP_PORT=8000", "HTTPS_PORT=8444",
          "PUBLIC_URL=https://localhost:8444", "DOCKER_HOST_ADDRESS=127.0.0.1", "TZ=America/Lima"
  $env | Set-Content -Encoding ASCII .env
  foreach ($d in "web","transcripts","prosody/config","prosody/prosody-plugins-custom","jicofo","jvb") { New-Item -ItemType Directory -Force -Path "jitsi-cfg/$d" | Out-Null }
}

# 3) Servicios
docker compose up -d
Write-Host "`nJitsi Meet: https://localhost:8444  (acepta el aviso del certificado autofirmado)"
