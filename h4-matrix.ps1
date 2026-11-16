# H4 - Levanta Matrix Synapse + Element Web y crea 3 usuarios de prueba.
# Uso (desde la raíz del proyecto):  powershell -ExecutionPolicy Bypass -File .\h4-matrix.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "matrix")

# 1) Configuración inicial de Synapse (solo la primera vez)
$existe = docker volume ls -q --filter name=nexo-synapse-data
if (-not $existe) {
  docker volume create nexo-synapse-data | Out-Null
  docker run --rm -v nexo-synapse-data:/data -e SYNAPSE_SERVER_NAME=nexo.local -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
}

# 2) Servicios
docker compose up -d

# 3) Espera a que Synapse responda
for ($i=0; $i -lt 60; $i++) {
  try { if ((Invoke-WebRequest -UseBasicParsing http://localhost:8008/health).StatusCode -eq 200) { break } } catch { Start-Sleep 2 }
}

# 4) Usuarios de prueba (contraseñas aleatorias, quedan en matrix\usuarios.txt, ignorado por git)
$usuarios = "ana","beto","carla"
$lineas = @()
foreach ($u in $usuarios) {
  $pw = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 14 | ForEach-Object {[char]$_})
  docker exec nexo-synapse register_new_matrix_user -c /data/homeserver.yaml -u $u -p $pw --no-admin http://localhost:8008 2>&1 | Out-Null
  $lineas += "@${u}:nexo.local  /  $pw"
}
$lineas | Set-Content -Encoding UTF8 usuarios.txt
Write-Host "`nElement Web: http://localhost:8090"
Write-Host "Usuarios (también en matrix\usuarios.txt):"; $lineas
