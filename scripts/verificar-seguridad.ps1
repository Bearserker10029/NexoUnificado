# Nexo Unificado - verificacion de endurecimiento (solo lectura, contra TU propio laboratorio)
# Uso (PowerShell, dentro del repositorio):
#   powershell -ExecutionPolicy Bypass -File .\scripts\verificar-seguridad.ps1
# No imprime ni guarda secretos: solo lee NEXO_HOST de .env. Salida: evidencias\seguridad\verificacion-FECHA.txt
$ErrorActionPreference = 'Continue'
$envFile = Join-Path (Get-Location) '.env'
$hostLine = Select-String -Path $envFile -Pattern '^NEXO_HOST=' | Select-Object -First 1
$h = ($hostLine.Line -split '=',2)[1].Trim()
$dir = Join-Path (Get-Location) 'evidencias\seguridad'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$out = Join-Path $dir ("verificacion-" + (Get-Date -Format 'yyyyMMdd-HHmm') + ".txt")
function Log($t){ $t | Tee-Object -FilePath $out -Append }
Log "== Verificacion de seguridad Nexo Unificado =="
Log ("Fecha: " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "   Host: $h")

Log "`n--- 1. Encabezados HTTPS (portal) ---"
$hdr = curl.exe -sk -I "https://${h}:8443/docs/" 2>&1
$hdr | Select-String -Pattern '^(HTTP|Strict-Transport|X-Content|X-Frame|Referrer|Content-Security|Permissions|Server|Location)' | ForEach-Object { Log $_.Line.Trim() }

Log "`n--- 2. Redireccion HTTP 8081 -> HTTPS 8443 ---"
curl.exe -s -I --max-time 8 "http://${h}:8081/" 2>&1 | Select-String -Pattern '^(HTTP|Location|Server)' | ForEach-Object { Log $_.Line.Trim() }

Log "`n--- 3. Versiones de TLS aceptadas por el proxy ---"
$protos = [ordered]@{ 'TLS 1.0'=192; 'TLS 1.1'=768; 'TLS 1.2'=3072; 'TLS 1.3'=12288 }
foreach($k in $protos.Keys){
  try{
    $c = New-Object Net.Sockets.TcpClient; $c.Connect($h,8443)
    $ssl = New-Object Net.Security.SslStream($c.GetStream(),$false,({$true}))
    $ssl.AuthenticateAsClient($h,$null,[Security.Authentication.SslProtocols]$protos[$k],$false)
    Log "$k : ACEPTADO (cifrado negociado: $($ssl.CipherAlgorithm) $($ssl.CipherStrength) bits)"
    $c.Close()
  } catch { Log "$k : RECHAZADO" }
}
Log "(Si TLS 1.3 aparece rechazado, puede ser limite de esta version de .NET; confirmalo con: curl.exe -skv --tlsv1.3 https://${h}:8443/ )"

Log "`n--- 4. Puertos TCP (esperado: solo 8443 y 8081 abiertos) ---"
$ports = 8443,8081,5060,5061,5038,3306,8080,8008,8448,9090,9093,3000,8088,8089,9100,9115,10000,8444
foreach($p in $ports){
  $c = New-Object Net.Sockets.TcpClient
  $iar = $c.BeginConnect($h,$p,$null,$null)
  $ok = $iar.AsyncWaitHandle.WaitOne(1200)
  if($ok -and $c.Connected){ Log "TCP $p : ABIERTO" } else { Log "TCP $p : cerrado/filtrado" }
  $c.Close()
}

Log "`n--- 5. Limite de peticiones (150 peticiones en paralelo a /voip/) ---"
$codes = curl.exe -sk --parallel --parallel-max 60 -o NUL -w "%{http_code}`n" "https://${h}:8443/voip/?n=[1-150]" 2>&1
$codes | Where-Object { $_ -match '^\d{3}$' } | Group-Object | ForEach-Object { Log ("HTTP " + $_.Name + " : " + $_.Count + " respuestas") }

Log "`n--- 6. Acceso sin sesion a rutas protegidas ---"
foreach($r in '/docs/','/_matrix/client/v3/account/whoami','/grafana/','/keycloak/admin/','/voip-sso/'){
  $code = curl.exe -sk -o NUL -w "%{http_code}" --max-time 8 "https://${h}:8443$r"
  $loc  = (curl.exe -sk -I --max-time 8 "https://${h}:8443$r" | Select-String '^Location' | Select-Object -First 1)
  Log ("$r -> HTTP $code " + $(if($loc){ ($loc.Line -replace '\?.*','') } else { '' }))
}

Log "`n--- 7. Contenedores y puertos publicados al anfitrion ---"
docker ps --format "{{.Names}}`t{{.Ports}}" | Where-Object { $_ -match '0\.0\.0\.0|:::' } | ForEach-Object { Log $_ }

Log "`nListo. Archivo: $out"
