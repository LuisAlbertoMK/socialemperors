# Bitácora — Smoke Lightspark 0.9.0 vs Ruffle (2026-10-15)

Objetivo: determinar si Lightspark es candidato para pruebas de rendimiento
contra el baseline de Ruffle. Criterio de paso del smoke: llegar al mapa
(`MapLoaded`). Sin smoke no hay PresentMon.

## Protocolo

- Server local en `http://127.0.0.1:5050/` (misma rama, sin cambios).
- Save del día, `UserId` del `*.save.json` más reciente.
- Lightspark 0.9.0 win64, instalación aislada fuera del repo.
- Flashvars idénticos a `tools/play_desktop.ps1` (17 parámetros:
  `swftoload`, `spdebug`, `staticUrl`, `dynamicUrl`, `skiphash12341`,
  `fb_sig_user`, `user_key`, `language`, `accessToken`, `sex`,
  `lastLoggedIn`, `dailyBonus`, `friendsInfo`, `serverTime`,
  `forceSyncError`, `forceAttackReload`, `forceQuestReload`) vía
  `--parameters-file` (línea impar = nombre, línea par = valor) más
  `--url` para simular el origen.
- Ruffle de referencia: `0.8.0-nightly 2026-10-09` (`D:\ruffle-desktop`).

## Resultados

1. El instalador solo acepta instalación con elevación (UAC); no hay
   binario portable. Se instaló en ruta temporal, fuera del repo.
2. `SELoader.swf` carga y entra en loop (`INIT_FRAME / ADVANCE_FRAME /
   enterFrame`) durante 20 s sin cerrarse solo: el loader no crashea.
3. El loader nunca pide el juego real. Resuelve `swftoload` al string
   `"null"` y descarga `.../flash/SELoader.swf` -> `.../flash/null`
   (404), aunque `swftoload` está presente tanto en `--url`
   (`?swftoload=.../SocialEmpires0926bsec.swf`) como en el params-file.
   Conclusión: Lightspark no expone query/params a
   `loaderInfo.parameters` como `SELoader` espera.
4. Gaps adicionales en el log: `Unsupported tag type 255`, `No such Id
   on dictionary 6` / `Invalid bitmap ID 6`, `Security::allowDomain`,
   `Stage.align`, `DefineFontNameTag` / `DefineFontAlignZonesTag`,
   `TextField antiAliasType` sin implementar.

## Dictamen

Smoke REFUTADO. Lightspark 0.9.0 no llega al mapa con este juego; no
corresponde medición PresentMon. Ruffle queda como único runtime viable
(ver `RDD-desktop.md`). Flare no se midió: es Ruffle embebido de
2025-03-15 con overhead de Electron declarado en su propio README, por lo
que no puede superar al Ruffle oficial actual.
