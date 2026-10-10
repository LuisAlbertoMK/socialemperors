# RDD — Fluidez Ruffle: investigación y decisión (2026-10-09)

## Research (fuentes verificadas)

- Ruffle = núcleo en Rust + pegamento TS/JS (wasm-bindgen), MIT/Apache-2.0,
  `github.com/ruffle-rs/ruffle` (coincide con `assets/ruffle/README.md`).
- CLI desktop (`desktop/src/cli.rs`): acepta URL como película, `-P clave=valor`
  repetible (flashvars), `--graphics {default,vulkan,metal,dx12,gl}`
  (`render/wgpu/src/clap.rs`), `--quality`, `--frame-rate` ("set and lock"),
  `--fullscreen`, `--dummy-external-interface`.
- PresentMon 2.6 (`GameTechDev/PresentMon`): requiere elevación para ETW
  (muere en silencio sin admin; usar `--restart_as_admin`).
- Frau web previa (traces Chrome, misma escena): nightly 0.8.0 = 0.7.1
  (p95 idéntico 16.73 ms, ~3.5 janks/s); `frameRate: 24` ignorado en 0.7.1 web;
  renderer canvas 3.7x peor que WebGL. Todo refutado con datos.

## Decisiones

1. Quedarse en **0.7.1 + WebGL + no-pause** para la web (estable, óptimo medido).
2. Para máxima fluidez: **Ruffle desktop nightly a fullscreen** (p95 51 ms,
   1.33 janks/s — 2.7x mejor cola que la web y que el desktop en ventana).
3. No capar framerate (E4: no reduce hitches, solo baja fps).
4. No usar dx12 en esta iGPU (E2: pierde vs vulkan).
5. E5 demostró que fullscreen + quality low no apila; E6 que OpenGL está roto
   en esta máquina; E7 que la prioridad del proceso no mueve la aguja.
   Ventana de optimización por software: CERRADA con evidencia.

## Por qué no hay 10x por software

El hitch por tick (~12 %) es costo propio del juego bajo emulación y aparece
igual en todos los builds/flags. El 10x real solo lo da el Flash original
(EOL) o CPU con mucho más single-thread (la emulación usa 1 núcleo).

## Método de eval (escuela Karpathy)

- Un experimento por variable, baseline pineado antes de optimizar
  (`tools/bench_presentmon.py` reproduce todas las métricas de esta bitácora).
- Overfit a un ejemplo: disecar el peor hitch individual antes que promediar
  (acá absolvió a la GPU en todos los casos).
- La descomposición CPU-vs-GPU decide el próximo paso: con la cola dominada
  por stalls de emulación, el backend gráfico ya no mueve la aguja; solo
  cuentan menos trabajo por tick o más single-thread.
