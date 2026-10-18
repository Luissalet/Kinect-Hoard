$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$assembly = Join-Path $root 'KinectHoard.Core\bin\Release\net48\KinectHoard.Core.dll'
$exe = Join-Path $root 'KinectHoard.App\bin\Release\net48\KinectHoard.App.exe'
if (-not (Test-Path -LiteralPath $assembly) -or -not (Test-Path -LiteralPath $exe)) {
    throw 'Compila primero con build.ps1.'
}
Add-Type -Path $assembly
$folder = Join-Path $root '.cache\gesture-test'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$session = Join-Path $folder 'synthetic.khr'
$report = Join-Path $folder ("synthetic-" + [guid]::NewGuid().ToString('N') + '.json')

function New-Joint([string]$name, [float]$x, [float]$y, [float]$z) {
    $joint = [KinectHoard.Core.BodyJoint]::new()
    $joint.Name = $name; $joint.X = $x; $joint.Y = $y; $joint.Z = $z
    $joint.TrackingState = 2
    return $joint
}
function New-Frame([datetime]$time, [float]$leftX, [float]$rightY) {
    $body = [KinectHoard.Core.TrackedBody]::new()
    $body.TrackingId = 42
    $body.Joints = [KinectHoard.Core.BodyJoint[]]@(
        (New-Joint 'Head' 0 1.7 2),
        (New-Joint 'ShoulderLeft' -0.2 1.35 2),
        (New-Joint 'ShoulderRight' 0.2 1.35 2),
        (New-Joint 'HandLeft' $leftX 1.0 2),
        (New-Joint 'HandRight' 0.35 $rightY 2)
    )
    $frame = [KinectHoard.Core.CameraFrame]::new()
    $frame.Kind = [KinectHoard.Core.StreamKind]::Skeleton
    $frame.Width = 1; $frame.Height = 1; $frame.Bgra = [byte[]]@(0, 0, 0, 255)
    $frame.Bodies = [KinectHoard.Core.TrackedBody[]]@($body)
    $frame.TimestampUtc = $time
    return $frame
}

$writer = [KinectHoard.Core.SessionWriter]::new($session, [KinectHoard.Core.StreamKind]::Skeleton)
try {
    $base = [datetime]::UtcNow
    $writer.WriteFrame((New-Frame $base -0.35 1.0))
    $writer.WriteFrame((New-Frame $base.AddMilliseconds(200) -0.35 1.55))
    $writer.WriteFrame((New-Frame $base.AddMilliseconds(400) -0.35 1.0))
    $writer.WriteFrame((New-Frame $base.AddMilliseconds(800) 0.10 1.0))
} finally { $writer.Dispose() }

& $exe --gestures-session $session $report
for ($attempt = 0; $attempt -lt 50 -and -not (Test-Path -LiteralPath $report); $attempt++) { Start-Sleep -Milliseconds 100 }
if (-not (Test-Path -LiteralPath $report)) { throw 'Falló el análisis de la sesión sintética.' }
$data = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
$names = @($data.events | ForEach-Object { "$($_.gesture):$($_.state)" })
foreach ($expected in @('right_hand_raised:started', 'right_hand_raised:ended', 'left_hand_swipe_right:detected')) {
    if ($expected -notin $names) { throw "Falta el evento $expected. Eventos: $($names -join ', ')" }
}
if ($data.frames -ne 4 -or $data.tracked_frames -ne 4) { throw 'Recuento de fotogramas incorrecto.' }
Write-Host "Gestos verificados: $($names -join ', ')"
