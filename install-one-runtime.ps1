$ErrorActionPreference = 'Stop'
$kinectAssembly = 'C:\Windows\Microsoft.NET\assembly\GAC_64\Microsoft.Kinect\v4.0_2.0.0.0__31bf3856ad364e35\Microsoft.Kinect.dll'
if (Test-Path -LiteralPath $kinectAssembly) {
    Write-Host 'Kinect Runtime 2.x ya está instalado. No se modificarán los controladores.'
    exit 0
}

Write-Host 'Desconecta el USB de la Kinect One antes de instalar el runtime oficial de Microsoft.'
$answer = Read-Host 'Escribe SI cuando esté desconectada'
if ($answer -ne 'SI') { exit 1 }

$url = 'https://download.microsoft.com/download/e/6/8/e688a436-5937-41cb-af76-498e99e19191/KinectRuntime-v2.2_1905.zip'
$expectedHash = '79B91E83A0734CD050597C98A22BA2B94AC07BFE86C45AB2B98DDC83D52024DE'
$folder = Join-Path $env:TEMP 'KinectHoardRuntime-2.2.1905'
$zip = Join-Path $folder 'KinectRuntime-v2.2_1905.zip'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
Invoke-WebRequest -Uri $url -OutFile $zip
$actualHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) { throw "La descarga no coincide con el SHA256 esperado: $actualHash" }
$expanded = Join-Path $folder 'extracted'
Expand-Archive -LiteralPath $zip -DestinationPath $expanded -Force
$inf = Get-ChildItem -LiteralPath $expanded -Filter 'kinectsensor.inf' -File -Recurse | Where-Object { $_.FullName -match '\\x64\\' } | Select-Object -First 1
if ($null -eq $inf) { throw 'No se encontró kinectsensor.inf para x64 en el paquete oficial.' }
Write-Host 'Solicitando permisos de administrador para instalar kinectsensor.inf...'
$installer = Start-Process -FilePath 'pnputil.exe' -ArgumentList ('/add-driver "' + $inf.FullName + '" /install') -Verb RunAs -Wait -PassThru
if ($installer.ExitCode -ne 0) { throw "La instalación del runtime devolvió $($installer.ExitCode)." }
Write-Host 'Instalación solicitada. Reconecta alimentación y USB 3.0 de la Kinect One y ejecuta KinectHoard.App.exe.'
