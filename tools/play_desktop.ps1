#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Ruffle desktop (nightly) against the local SocialEmperors server.

.USAGE
  Double-click tools\JUGAR.bat, or:
     powershell -ExecutionPolicy Bypass -File tools\play_desktop.ps1 -Fullscreen

  Server auto-starts if down; UserId auto-detects your latest save.
  Optimal flags from docs/benchmarks/RDD-desktop.md.
#>
param(
    [string]$RuffleExe = "D:\ruffle-desktop\ruffle.exe",
    [string]$UserId = "",
    [string]$ServerIp = "127.0.0.1",
    [int]$Width = 760,
    [int]$Height = 600,
    [switch]$Fullscreen,
    [string]$Graphics = "",
    [string]$Quality = "",
    [double]$FrameRate = 0
)

$base = "http://${ServerIp}:5050"

# 1. Server up? Start it if down.
$serverOk = $false
for ($i = 0; $i -lt 5 -and -not $serverOk; $i++) {
    try { $serverOk = (Invoke-WebRequest -Uri "$base/" -TimeoutSec 3).StatusCode -eq 200 } catch { Start-Sleep 1 }
}
if (-not $serverOk) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Start-Process python -ArgumentList "server.py" -WorkingDirectory $repoRoot
    for ($i = 0; $i -lt 30 -and -not $serverOk; $i++) {
        Start-Sleep 1
        try { $serverOk = (Invoke-WebRequest -Uri "$base/" -TimeoutSec 3).StatusCode -eq 200 } catch { }
    }
}
if (-not $serverOk) { throw "Server did not respond at $base/. Start it manually: python server.py" }

# 2. UserId defaults to the latest save.
if ([string]::IsNullOrWhiteSpace($UserId)) {
    $latest = Get-ChildItem (Join-Path (Split-Path -Parent $PSScriptRoot) "saves\*.save.json") |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $latest) { throw "No saves found. Pass -UserId explicitly." }
    $UserId = (Get-Content -Raw $latest.FullName | ConvertFrom-Json).playerInfo.pid
    Write-Host "Using latest save USERID: $UserId ($($latest.Name))"
}
$flash = "$base/default01.static.socialpointgames.com/static/socialempires/flash"
$movie = "$flash/SELoader.swf?swftoload=$flash/SocialEmpires0926bsec.swf"
$serverTime = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$friendsPic = "$base/img/profile/x.jpg"
$friendsInfo = '-PfriendsInfo[{"first_name":"AcidCaos","uid":"100000","pic_square":"' + $friendsPic + '"}]'

$extra = @()
if ($Fullscreen) { $extra += "--fullscreen" }
if ($Graphics -ne "") { $extra += "--graphics", $Graphics }
if ($Quality -ne "") { $extra += "--quality", $Quality }
if ($FrameRate -gt 0) { $extra += "--frame-rate", "$FrameRate" }

& $RuffleExe $movie --width $Width --height $Height @extra `
    "-Pspdebug=notnull" `
    "-PstaticUrl=$base/default01.static.socialpointgames.com/static/socialempires/" `
    "-PdynamicUrl=$base/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/" `
    "-Pskiphash12341=notnull" `
    "-Pfb_sig_user=$UserId" `
    "-Puser_key=123456789" `
    "-Planguage=en" `
    "-PaccessToken=AAABbZAm0wdMUBALsOrR0Ho68CLjaOT8SV3vftKg9mbo1zZColaW5FljRVaLxPGxXXnm1M98mTZCAttcQ4GHwvSyXfsyxYmvKMH8Hmn5iliSPnjvIsZA6" `
    "-Psex=m" `
    "-PlastLoggedIn=1349266517" `
    "-PdailyBonus=0" `
    $friendsInfo `
    "-PserverTime=$serverTime" `
    "-PforceSyncError=1" `
    "-PforceAttackReload=0" `
    "-PforceQuestReload=0"
