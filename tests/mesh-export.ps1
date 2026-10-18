$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Add-Type -Path (Join-Path $root 'KinectHoard.Core\bin\Release\net48\KinectHoard.Core.dll')
$folder = Join-Path $root '.cache\mesh-test'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$path = Join-Path $folder 'grid.ply'
$frame = [KinectHoard.Core.PointCloudFrame]::new()
$frame.Width = 2; $frame.Height = 2
$frame.Xyz = [float[]]@(0, 0, 1, 0.01, 0, 1, 0, -0.01, 1, 0.01, -0.01, 1)
$mesh = [KinectHoard.Core.FrameExporter]::SaveMeshPly($path, $frame, 0.06)
if ($mesh.Vertices -ne 4 -or $mesh.Faces -ne 2) { throw 'La cuadrícula plana debe producir dos triángulos.' }
$frame.Xyz[11] = 2
$mesh = [KinectHoard.Core.FrameExporter]::SaveMeshPly($path, $frame, 0.06)
if ($mesh.Vertices -ne 4 -or $mesh.Faces -ne 1) { throw 'La discontinuidad debe descartar el triángulo que la cruza.' }
$content = Get-Content -LiteralPath $path
if ('element face 1' -notin $content -or '3 0 2 1' -notin $content) { throw 'El PLY no contiene la cara esperada.' }
$frame.Rgb = [byte[]]@(255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255)
$mesh = [KinectHoard.Core.FrameExporter]::SaveMeshPly($path, $frame, 0.06)
$content = Get-Content -LiteralPath $path
if ('property uchar red' -notin $content -or 'property uchar green' -notin $content -or 'property uchar blue' -notin $content -or '0 0 1 255 0 0' -notin $content) {
    throw 'El PLY no conserva las propiedades RGB.'
}
Write-Host 'Malla verificada: dos caras planas y descarte por salto de profundidad.'
