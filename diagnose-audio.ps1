$ErrorActionPreference = 'Stop'
$endpoints = @(Get-PnpDevice -PresentOnly -Class AudioEndpoint | Where-Object { $_.FriendlyName -match 'Xbox NUI Sensor' })
if (-not $endpoints.Count) { Write-Output 'Micrófono Kinect: no enumerado'; exit 2 }
foreach ($endpoint in $endpoints) {
    Write-Output "Micrófono Kinect: $($endpoint.FriendlyName) | $($endpoint.Status)"
    if ($endpoint.InstanceId -notmatch '\.(\{[0-9A-Fa-f-]{36}\})$') { continue }
    $id = $Matches[1]
    $path = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture\' + $id + '\FxProperties'
    $property = '{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5'
    $effects = Get-ItemProperty -LiteralPath $path -ErrorAction SilentlyContinue
    if ($null -eq $effects) { Write-Output 'Efectos de audio: propiedad no accesible'; continue }
    $value = $effects.PSObject.Properties[$property]
    if ($null -eq $value) { Write-Output 'Efectos de audio: valor explícito ausente; comprobar en Configuración de sonido'; continue }
    Write-Output "Efectos de audio: Disable_SysFx=$($value.Value) (1 = desactivados)"
}
