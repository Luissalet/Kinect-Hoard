$ErrorActionPreference = 'Stop'
$projects = @('KinectHoard.Core', 'KinectHoard.Driver.One', 'KinectHoard.Driver.ThreeSixty', 'KinectHoard.App')
foreach ($project in $projects) {
    dotnet build "$PSScriptRoot\$project\$project.csproj" --configuration Release
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$target = Join-Path $PSScriptRoot 'KinectHoard.App\bin\Release\net48'
Copy-Item (Join-Path $PSScriptRoot 'KinectHoard.Driver.One\bin\Release\net48\KinectHoard.Driver.One.dll') $target
Copy-Item (Join-Path $PSScriptRoot 'KinectHoard.Driver.ThreeSixty\bin\Release\net48\KinectHoard.Driver.ThreeSixty.dll') $target
Write-Host "Aplicación: $target\KinectHoard.App.exe"
