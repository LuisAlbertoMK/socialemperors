# Upstream performance issue — ruffle-rs/ruffle#24884

Title: AVM2 30fps game: ~12% of ticks exceed 50ms on CPU, GPU innocent (ETW data)

## Environment

- Ruffle desktop nightly-2026-10-09, Windows x86_64, AMD RX Vega 10 (iGPU)
- Backend: vulkan (default pick); content: 30fps AVM2 game, 760x600

## Method

PresentMon 2.6 capture (`--v1_metrics`) of real gameplay, ~90-350s per config.
Same scene across runs. Harness: per-frame `msBetweenPresents` + `msGPUActive`
split. (Raw CSVs available on request; game assets are not redistributable,
so no public repro SWF — happy to run requested experiments locally.)

## Findings

- Median frame ~= game tick (~32-36ms). Tail: p95 51-137ms depending on config.
- Hitch probability per tick is CONSTANT (~12%): capping frame-rate to 24fps
  lowers fps but not hitches (2.82/24 ~= 3.61/30 per-tick rate).
- Worst hitches (327-573ms gaps) show only 13-146ms of GPU work: the app stops
  presenting because emulation blocks on CPU (single thread).
- Median GPU share of a typical frame: 34-58% on this iGPU — the GPU does real
  work, but the tail is all CPU stalls.
- Config sweep: fullscreen (flip presentation) halves the tail; dx12 loses to
  vulkan here; canvas/webgl tested on web build; process priority changes nothing.

## Question for maintainers

Is a per-tick profile (AVM2 execution vs display-list vs other) of interest?
We can capture targeted traces if you point at the subsystem to instrument.
