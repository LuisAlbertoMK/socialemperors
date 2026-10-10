# Jugar en Ruffle desktop (óptimo medido)

Binarios (fuera del repo, no se commitean): `D:\ruffle-desktop\`
(`ruffle.exe` nightly 2026-10-09 + `PresentMon.exe` 2.6).

## Jugar (3 pasos)

1. Server: `python server.py` desde `D:\socialemperors`.
2. Tu `USERID`: view-source de `/ruffle.html`, buscar `fb_sig_user`.
3. Lanzar:
   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\play_desktop.ps1 `
     -RuffleExe "D:\ruffle-desktop\ruffle.exe" -UserId "<tu id>" -Fullscreen
   ```

## Re-medir (mismo protocolo de la bitácora)

Con el juego corriendo (admin, acepta el UAC):

```powershell
D:\ruffle-desktop\PresentMon.exe --process_name ruffle.exe `
  --output_file bench.csv --v1_metrics --timed 90 --terminate_after_timed `
  --stop_existing_session --no_console_stats
```

Analizar: `python tools/bench_presentmon.py bench.csv`.
Veredictos vigentes en `ODD-bitacora.md` y `RDD-desktop.md`.
