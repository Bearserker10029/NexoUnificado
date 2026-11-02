# Nexo Unificado · Recolecta la evidencia del hito H2 en un archivo de texto.
# Uso (PowerShell, dentro de la carpeta del proyecto):  .\evidencias.ps1
$salida = "evidencia_h2.txt"
$linea = "=" * 70
function Seccion($titulo) { Add-Content $salida "`n$linea`n$titulo`n$linea" }

Set-Content $salida "Nexo Unificado · Evidencia del hito H2"
Add-Content $salida ("Equipo : " + $env:COMPUTERNAME)
Add-Content $salida ("Usuario: " + $env:USERNAME)
Add-Content $salida ("Fecha  : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

Seccion "docker compose ps"
docker compose ps 2>&1 | Add-Content $salida

Seccion "Redirección HTTP -> HTTPS (curl -I http://localhost:8080)"
curl.exe -s -I http://localhost:8080 2>&1 | Add-Content $salida

Seccion "Cabeceras de seguridad HTTPS (curl -k -I https://localhost:8443)"
curl.exe -k -s -I https://localhost:8443 2>&1 | Add-Content $salida

Seccion "Versión de TLS negociada"
curl.exe -k -s -v -o NUL https://localhost:8443 2>&1 | Select-String "SSL connection|TLSv" | Add-Content $salida

Seccion "Redes del proyecto"
docker network ls --filter "name=nexo" 2>&1 | Add-Content $salida

Seccion "Disponibilidad medida por Prometheus (probe_success)"
docker compose exec -T prometheus wget -q -O - "http://127.0.0.1:9090/api/v1/query?query=probe_success" 2>&1 | Add-Content $salida

Write-Host "Listo. Evidencia guardada en $salida"
