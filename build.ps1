$ErrorActionPreference = 'Stop'
$projects = @('KinectHoard.Core', 'KinectHoard.Driver.One')
$legacySdk = Test-Path -LiteralPath 'C:\Program Files\Microsoft SDKs\Kinect\v1.8\Assemblies\Microsoft.Kinect.dll'
if ($legacySdk) { $projects += 'KinectHoard.Driver.ThreeSixty' }
else { Write-Host 'SDK 1.8 no instalado; Kinect 360 utiliza su controlador nativo libfreenect.' }
$projects += @('KinectHoard.Driver.ThreeSixty.Native', 'KinectHoard.App')
foreach ($project in $projects) {
    dotnet build "$PSScriptRoot\$project\$project.csproj" --configuration Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$target = Join-Path $PSScriptRoot 'KinectHoard.App\bin\Release\net48'
Copy-Item (Join-Path $PSScriptRoot 'KinectHoard.Driver.One\bin\Release\net48\KinectHoard.Driver.One.dll') $target
if ($legacySdk) { Copy-Item (Join-Path $PSScriptRoot 'KinectHoard.Driver.ThreeSixty\bin\Release\net48\KinectHoard.Driver.ThreeSixty.dll') $target }
Copy-Item (Join-Path $PSScriptRoot 'KinectHoard.Driver.ThreeSixty.Native\bin\Release\net48\KinectHoard.Driver.ThreeSixty.Native.dll') $target
$nativeBinaries = Join-Path $PSScriptRoot 'native\win-x64'
foreach ($name in @('KinectHoard.Native360.dll', 'freenect.dll', 'libusb-1.0.dll')) {
    $binary = Join-Path $nativeBinaries $name
    if (Test-Path -LiteralPath $binary) { Copy-Item -LiteralPath $binary -Destination $target }
}
Write-Host "Aplicación: $target\KinectHoard.App.exe"
