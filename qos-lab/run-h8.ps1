# H8 - QoS: ejecuta el laboratorio dentro de un contenedor Ubuntu (Docker Desktop).
# Uso (desde la carpeta del proyecto):  powershell -ExecutionPolicy Bypass -File .\qos-lab\run-h8.ps1
$ErrorActionPreference = "Stop"
$lab = Join-Path $PSScriptRoot "."
$out = Join-Path $PSScriptRoot "..\evidencias\h8"
New-Item -ItemType Directory -Force -Path $out | Out-Null
docker run --rm --privileged `
  -v "${lab}:/lab" -v "${out}:/out" `
  -e DUR=30 -e RATE=10mbit ubuntu:22.04 bash -c `
  "export DEBIAN_FRONTEND=noninteractive; apt-get update && apt-get install -y --no-install-recommends iproute2 iperf3 ethtool tcpdump python3 iputils-ping dos2unix && dos2unix -q /lab/run.sh && bash /lab/run.sh"
Write-Host "Evidencias en $out"
