$ErrorActionPreference = 'Stop'
$camera = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB\\VID_045E&PID_02AE' })
if ($camera.Count -eq 0) { throw 'No se detecta la cámara USB Kinect 360 (045E:02AE). Conecta alimentación y USB antes de continuar.' }
if ($camera.Count -gt 1) { throw 'Hay varias cámaras 045E:02AE. Comprueba cuál deseas enlazar antes de usar Zadig.' }
$device = $camera[0]
$service = (Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_Service).Data
Write-Host "Cámara: $($device.FriendlyName) [$($device.InstanceId)]"
Write-Host "Servicio actual: $service"
if ($service -eq 'libusbK') { Write-Host 'La cámara ya usa libusbK.'; return }

$toolDir = Join-Path $env:TEMP 'KinectHoard-Zadig'
New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
$download = Join-Path $toolDir 'zadig-2.9.exe'
$expected = '4ECAA95DF3DA3621486A043AEF8B3050B8BAFE7C901402871E816229EF82039B'
if (-not (Test-Path -LiteralPath $download) -or (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne $expected) {
    Invoke-WebRequest 'https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe' -OutFile $download
}
if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne $expected) {
    throw 'El ejecutable de Zadig no coincide con el SHA-256 esperado.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $download
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Akeo Consulting') {
    throw 'La firma de Zadig no es válida o no corresponde a Akeo Consulting.'
}
# Zadig otherwise hides devices with an existing Microsoft driver and defaults to WinUSB.
# Keep hubs/composite parents out of the list to reduce the chance of selecting one.
'[device]', 'list_all = true', 'include_hubs = false', '', '[driver]', 'default_driver = 2', 'extract_only = false' |
    Set-Content -LiteralPath (Join-Path $toolDir 'zadig.ini') -Encoding ascii
Write-Host 'En Zadig, selecciona SOLO Xbox NUI Camera (o Kinect for Windows Camera) con USB ID 045E:02AE y pulsa Replace Driver.'
Write-Host 'La lista de dispositivos y libusbK ya estarán preparados. Verifica el ID USB antes de instalar.'
Write-Host 'No cambies el motor 02B0, el audio 02BB ni ningún dispositivo Kinect One.'
$process = Start-Process -FilePath $download -Verb RunAs -WorkingDirectory $toolDir -PassThru
$process.WaitForExit()
$updated = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB\\VID_045E&PID_02AE' } | Select-Object -First 1
$newService = if ($updated) { (Get-PnpDeviceProperty -InstanceId $updated.InstanceId -KeyName DEVPKEY_Device_Service -ErrorAction SilentlyContinue).Data } else { $null }
if ($newService -ne 'libusbK') {
    throw "La cámara aún no usa libusbK (servicio: $newService). Comprueba la selección en Zadig y vuelve a ejecutar el script."
}
Write-Host 'Cámara 360 enlazada a libusbK. Ejecuta KinectHoard.App.exe --diagnose para verificar el backend.'
