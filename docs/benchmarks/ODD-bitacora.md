# Bitácora ODD — Benchmarks Ruffle Desktop (2026-10-09)

Objetivo: cuantificar la fluidez del juego en Ruffle desktop nightly y probar
4 optimizaciones, una variable por vez, misma escena, mismo save.

Protocolo: Ruffle `nightly-2026-10-09` Windows x86_64 contra server local
(`play_desktop.ps1`, UserId del save del día). Captura con PresentMon 2.6
(`--v1_metrics`), segmentos por PID, descartando ~25 s de arranque.
Métricas: `avg_fps`, mediana y p95 de `msBetweenPresents`, janks `>50 ms`/s.

## Corridas

| # | Config | PID | Frames | avg_fps | med ms | p95 ms | jank/s | PresentMode |
|---|--------|-----|-------:|--------:|-------:|-------:|-------:|-------------|
| E0 | control: ventana, vulkan, high | 11016 | 1846 | 21.1 | 35.8 | 137.1 | 3.61 | Composed Copy |
| E1 | `--fullscreen` | 6108 | 9008 | 25.8 | 32.6 | 50.8 | 1.33 | Copy + Legacy Flip |
| E2 | `--graphics dx12` (ventana) | 14108 | 2899 | 22.7 | 32.3 | 121.0 | 2.68 | Indep Flip + Flip |
| E3 | `--quality low` (ventana) | 13516 | 4438 | 29.0 | 31.4 | 56.6 | 1.64 | Composed Copy |
| E4 | `--frame-rate 24` (ventana) | 13212 | 3590 | 21.5 | 39.4 | 115.0 | 2.82 | Composed Copy |
| E5 | `--fullscreen --quality low` | 9152 | 1830 | 24.4 | 33.1 | 54.5 | 1.37 | Copy + Legacy Flip |

Evidencia cruda: `presentmon-baseline-20261009.csv` (E0),
`presentmon-matrix-20261009.csv` (E1–E4, columna ProcessID).

## Lectura por corrida

- E1: mejor p95 (137 → 51 ms) y menor tasa de jank (3.61 → 1.33/s).
  El fullscreen consigue `Hardware: Legacy Flip` (flip real, menos latencia).
- E2: dx12 pierde contra vulkan en esta iGPU (Vega 10). Refutado.
- E3: sin MSAA ayuda a la integrada (p95 137 → 57 ms). Segundo puesto.
- E4: el lock aplica (mediana 39.4 ms ≈ 24 fps) pero NO baja los hitches:
  2.82/24 ≈ 12 % de ticks con hitch, idéntico al 3.61/30 del control.
  La probabilidad de hitch por tick es constante; capar fps no optimiza.
- E5: fullscreen + quality low NO apila (p95 54.5 vs 50.8, jank 1.37 vs 1.33/s,
  dentro de ruido). El flip ya satura la ganancia; conviene calidad default
  (misma perf, mejor imagen).
