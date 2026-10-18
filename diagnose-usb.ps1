param(
    [ValidateSet('Color', 'Depth', 'Infrared', 'LongExposureInfrared', 'BodyIndex', 'Skeleton', 'BackgroundRemoved', 'ColorDepth')]
    [string]$Stream = 'Depth',
    [ValidateRange(5, 600)]
    [int]$Seconds = 35
)

$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'KinectHoard.App\bin\Release\net48\KinectHoard.App.exe'
if (-not (Test-Path -LiteralPath $exe)) { $exe = Join-Path $PSScriptRoot 'KinectHoard.App.exe' }
if (-not (Test-Path -LiteralPath $exe)) { throw 'No se encontró KinectHoard.App.exe. Compila primero con .\build.ps1.' }
$log = Join-Path $PSScriptRoot 'diagnostico-estabilidad.txt'
$started = Get-Date
$process = Start-Process -FilePath $exe -ArgumentList ('--stress "' + $log + '" ' + $Seconds + ' ' + $Stream) -Wait -PassThru -WindowStyle Hidden
Get-Content -LiteralPath $log
$events = @(Get-WinEvent -FilterHashtable @{
    LogName = 'Microsoft-Windows-Kernel-PnP/Device Management'
    Id = 1010
    StartTime = $started
} -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'VID_045E&PID_02C4' })
"Eventos de retirada inesperada de Kinect One en Windows: $($events.Count)"
if ($events.Count) { $events | Select-Object TimeCreated, Message | Format-List }
$locks = @(Get-WinEvent -FilterHashtable @{
    LogName = 'System'
    Id = 225
    StartTime = $started
} -ErrorAction SilentlyContinue | Where-Object { $_.Message -match 'VID_045E&PID_02C4' })
"Eventos de aplicación que impidió reiniciar o expulsar Kinect One: $($locks.Count)"
if ($locks.Count) { $locks | Select-Object TimeCreated, Message | Format-List }
exit $process.ExitCode
