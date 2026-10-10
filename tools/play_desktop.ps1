#Requires -Version 5.1
<#
.SYNOPSIS
  Launch Ruffle desktop (nightly) against the local SocialEmperors server.

.USAGE
  1. Start the server:  python server.py   (from D:\socialemperors)
  2. Get your USERID:    view-source of /ruffle.html in the browser, search fb_sig_user
  3. Play (optimal flags from docs/benchmarks/RDD-desktop.md):
     powershell -ExecutionPolicy Bypass -File tools\play_desktop.ps1 `
       -RuffleExe "D:\ruffle-desktop\ruffle.exe" -UserId "<tu id>" -Fullscreen

  Optional experiment flags (one at a time): -Graphics dx12|gl|vulkan
  -Quality low -FrameRate 24. See docs/benchmarks/ODD-bitacora.md for verdicts.
#>
param(
    [Parameter(Mandatory = $true, HelpMessage = "Ruta a ruffle.exe del nightly desktop")]
    [string]$RuffleExe,
    [Parameter(Mandatory = $true, HelpMessage = "Tu USERID (sale en view-source de ruffle.html como fb_sig_user)")]
    [string]$UserId,
    [string]$ServerIp = "127.0.0.1",
    [int]$Width = 760,
    [int]$Height = 600,
    [switch]$Fullscreen,
    [string]$Graphics = "",
    [string]$Quality = "",
    [double]$FrameRate = 0
)

$base = "http://${ServerIp}:5050"
$flash = "$base/default01.static.socialpointgames.com/static/socialempires/flash"
$movie = "$flash/SELoader.swf?swftoload=$flash/SocialEmpires0926bsec.swf"
$serverTime = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$friendsPic = "$base/img/profile/x.jpg"

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
    '-PfriendsInfo[{"first_name":"AcidCaos","uid":"100000","pic_square":"' + $friendsPic + '"}]' `
    "-PserverTime=$serverTime" `
    "-PforceSyncError=1" `
    "-PforceAttackReload=0" `
    "-PforceQuestReload=0"
