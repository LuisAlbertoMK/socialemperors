# Jugar en Ruffle desktop (óptimo medido)

Doble-click en `tools\JUGAR.bat` y listo: el server se levanta solo si está
caído y usa tu save más reciente. Binarios (fuera del repo, no se commitean):
`D:\ruffle-desktop\` (`ruffle.exe` nightly 2026-10-09 + `PresentMon.exe` 2.6).

Notas: requiere PowerShell 7 (`pwsh`, ya viene con el .bat); el `USERID` se
puede forzar con `-UserId` si jugás con otro save.

## Re-medir (mismo protocolo de la bitácora)

Con el juego corriendo (admin, acepta el UAC):

```powershell
D:\ruffle-desktop\PresentMon.exe --process_name ruffle.exe `
  --output_file bench.csv --v1_metrics --timed 90 --terminate_after_timed `
  --stop_existing_session --no_console_stats
```

Analizar: `python tools/bench_presentmon.py bench.csv`.
Veredictos vigentes en `ODD-bitacora.md` y `RDD-desktop.md`.
