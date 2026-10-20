# Investigación profunda: código fuente de Adobe Flash Player, alternativas abiertas y estrategia de modernización

**Objetivo del documento:** dar instrucciones a un agente de investigación técnica para localizar, verificar y analizar el código fuente relacionado con Adobe Flash Player, evaluar alternativas abiertas y proponer una modernización con Rust, Go, WebAssembly u otras tecnologías sin asumir de antemano que una reescritura sea la mejor solución.

**Fecha de preparación:** 2026-10-08  
**Idioma de entrega:** español  
**Regla principal:** distinguir siempre entre código original de Adobe, código abierto derivado/donado, implementaciones compatibles, herramientas de análisis y simples especificaciones de formato.

---

## 1. Objetivos y preguntas que deben resolverse

El agente debe responder con evidencia verificable:

1. ¿Adobe publicó alguna vez el código fuente completo del reproductor nativo Flash Player? ¿Existe una copia pública legítima, una liberación parcial, un archivo histórico o una filtración cuyo origen pueda verificarse?
2. ¿Qué código fuente auténtico de Adobe relacionado con Flash sí está publicado, en particular AVMPlus/Tamarin y herramientas del SDK?
3. ¿Qué repositorios abiertos implementan SWF, ActionScript 1/2/3, reproducción multimedia, renderizado, APIs de Flash o compatibilidad con contenido antiguo?
4. ¿Qué proyectos están activos, mantenidos, archivados o abandonados? Verificar fechas y actividad actual; no deducir estado solo por la descripción del README.
5. ¿Cuáles son las licencias y obligaciones de redistribución, modificación, uso comercial y distribución como servicio?
6. ¿Qué subsistemas merecen optimización y cuáles conviene conservar, reemplazar o aislar?
7. ¿Tiene sentido Rust para el núcleo, Go para tooling o es mejor mantener partes en C/C++? ¿Qué evidencia comparativa existe?
8. ¿Qué tecnologías actuales son mejores si la meta es migrar las aplicaciones Flash, en lugar de mantener un reproductor?
9. ¿Qué prototipo mínimo y benchmark permitirían decidir objetivamente?
10. ¿Qué riesgos legales, de seguridad, compatibilidad, rendimiento y mantenimiento deben quedar documentados?

No considerar terminada la investigación por haber encontrado un solo repositorio o una lista de resultados de buscador.

---

## 2. Reglas de rigor y verificación

### 2.1 Etiquetar cada hallazgo

Cada afirmación importante debe recibir una categoría:

- **Verificado:** confirmado en el repositorio/documentación primaria.
- **Corroborado:** confirmado por dos fuentes independientes, preferentemente primarias.
- **Indicio:** resultado de búsqueda, espejo o afirmación sin procedencia suficiente.
- **No localizado:** no se encontró tras describir búsquedas reproducibles.
- **Desconocido:** la evidencia disponible no permite concluir.
- **No compatible con el objetivo:** recurso relacionado, pero no contiene el componente buscado.

No afirmar “no existe en Internet” basándose solo en una búsqueda web. Usar la formulación: “No se localizó en las fuentes y consultas enumeradas; esto no demuestra inexistencia”.

### 2.2 Verificación doble obligatoria

Para cada repositorio prioritario:

1. Abrir el repositorio original, no solo el snippet del buscador.
2. Revisar README, LICENSE, historial de commits, etiquetas/releases, ramas, issues y fecha de actividad.
3. Identificar lenguajes y directorios que realmente implementan el componente.
4. Comprobar si es implementación completa, parcial, biblioteca, parser, VM, reproductor o documentación.
5. Buscar documentación primaria externa que describa su origen.
6. Contrastar licencia en el archivo LICENSE y en la documentación oficial.
7. Registrar fecha de consulta y URLs exactas.
8. Cuando una afirmación sea importante (p. ej. “Adobe donó AVM2”), confirmar en al menos dos fuentes fiables, incluyendo una fuente primaria cuando sea posible.

No dar por verificado el estado actual de un repositorio con datos antiguos. No inventar estrellas, descargas, compatibilidad, benchmark ni actividad reciente.

### 2.3 Seguridad y procedencia

- No ejecutar binarios Flash antiguos o SWF no confiables en el sistema principal.
- Analizar contenido sospechoso en un entorno aislado, sin credenciales ni acceso innecesario a la red.
- No descargar, redistribuir ni usar supuestas filtraciones propietarias sin evaluar procedencia, licencias y legalidad.
- No recomendar eludir licencias, controles de acceso o medidas técnicas.
- Priorizar repositorios públicos oficiales y código con licencia explícita.
- Tratar archivos SWF/FLV como entradas potencialmente maliciosas; revisar fuzzing, validación de límites y fallos de memoria.
- No enviar archivos privados o confidenciales a servicios de análisis externos sin autorización.

---

## 3. Repositorios prioritarios: abrir y examinar directamente

### 3.1 Ruffle — primera opción para una base Rust

- Repositorio: https://github.com/ruffle-rs/ruffle
- Web/documentación: https://ruffle.rs/
- Objetivo de análisis: emulación de Flash, compatibilidad SWF, ActionScript, renderizado y WebAssembly.

Investigar:

- Directorios del parser/formato SWF, core, AVM1, AVM2, renderizado, audio/vídeo, interfaces web y escritorio.
- Qué partes están escritas en Rust y cuáles dependen de bibliotecas externas.
- Cobertura de ActionScript 1/2 y ActionScript 3; diferencias funcionales y casos no implementados.
- Estrategia de memoria, representación de objetos, recolección de basura, asignaciones y manejo de eventos.
- Mecanismos de profiling, logging, pruebas de regresión y corpus de compatibilidad.
- Backends gráficos y ruta de cada fotograma: ejecución AVM → display list → renderizador.
- Estado actual de los módulos multimedia y límites conocidos.
- Licencia real de cada componente y de las dependencias.
- Issues abiertos relevantes para rendimiento, compatibilidad, consumo de RAM y seguridad.
- CI, pruebas, fuzzing, releases y actividad reciente.

Preguntas concretas:
- ¿Qué benchmarks y herramientas de perfilado incluye actualmente?
- ¿Qué costes dominan en contenido real: ejecución AVM, layout, filtros, bitmap, audio/vídeo o llamadas al host?
- ¿Qué interfaces internas permitirían optimizar un subsistema sin alterar el comportamiento?
- ¿Cómo comparar una compilación nativa con WebAssembly?
- ¿Qué limitaciones de compatibilidad son funcionales y cuáles son de rendimiento?

No asumir que todo Ruffle es un reemplazo perfecto de Flash Player; medir cada aplicación representativa.

### 3.2 AVMPlus / Tamarin — fuente histórica de la VM de ActionScript 3

- Repositorio: https://github.com/adobe-flash/avmplus

Investigar:

- README, LICENSE, historia, etiquetas y último estado verificable.
- Procedencia del código y relación con Adobe, Mozilla y el proyecto Tamarin.
- Archivos de interpretación/ejecución de bytecode, JIT, verificación, objetos, strings, garbage collector y runtime.
- Diferencia entre AVM2/ActionScript 3 y AVM1/ActionScript 1–2.
- Qué componentes son reutilizables y qué dependencias o toolchains antiguos impiden una compilación moderna.
- Pruebas, benchmarks y documentación de arquitectura.
- Si el código compila hoy en toolchains actuales; si no, registrar errores exactos y parches necesarios.
- Licencia por archivo y licencia global. Confirmar MPL-2.0 directamente en el repositorio, no solo en páginas de terceros.

Límite esencial: AVMPlus/Tamarin es material de la máquina virtual, no prueba de que esté disponible todo Flash Player nativo. No presentarlo como fuente completa del reproductor.

### 3.3 Lightspark — implementación nativa C/C++

- Repositorio: https://github.com/lightspark/lightspark

Investigar:

- Arquitectura general y compatibilidad actual.
- ActionScript, renderizado, multimedia, threading y uso de GPU.
- Uso de LLVM/JIT: si existe, cómo se configura, qué bytecode acelera y qué limitaciones tiene.
- Dependencias y dificultad de compilación en Linux/Windows.
- Issues, releases, CI, pruebas y estado de mantenimiento actual.
- Licencias de componentes GPL/LGPL y obligaciones para distribución.
- Benchmarks publicados y posibilidad de reproducirlos.

No concluir que JIT = más rápido en todos los casos. Medir arranque, contenido breve, cargas intensivas de CPU, animación, renderizado y memoria.

### 3.4 Parser Rust de SWF

- Repositorio candidato: https://github.com/open-flash/swf-parser

Verificar que la URL siga correspondiendo al proyecto previsto. Si fue movido, renombrado, archivado o eliminado, buscar el origen oficial y documentar la redirección. Examinar:

- Qué versión del formato SWF maneja.
- Parsing incremental frente a carga completa.
- Validación de longitudes, desbordamientos, límites y datos truncados.
- Cero-copy, asignaciones, representación de etiquetas y errores.
- Pruebas, fuzzing y corpus.
- Licencia AGPL-3.0 indicada en el repositorio, confirmada directamente.
- Compatibilidad con el parser de Ruffle y coste de sustituirlo.

No asumir que una biblioteca con “SWF” en el nombre ejecuta ActionScript o reproduce el archivo.

### 3.5 swf-go — tooling en Go

- Repositorio candidato: https://github.com/WeebDataHoarder/swf-go

Verificar URL, estado y licencia actual. Identificar con precisión si implementa parsing, extracción de datos, decodificación o algo adicional.

Evaluar para:
- Inventario de grandes colecciones SWF.
- Lectura de cabeceras, tags y metadatos.
- Clasificación por versión, ActionScript y recursos.
- Generación de informes JSON/CSV.
- Pipeline de pruebas masivas y comparación de resultados.

No presentarlo como reproductor completo sin evidencia de AVM, renderizador y APIs compatibles.

### 3.6 Apache Flex SDK — herramientas de desarrollo

- Repositorio: https://github.com/apache/flex-sdk

Investigar compilador, bibliotecas, MXML, ActionScript, cadena de construcción y licencias. Separar claramente el SDK/compilador del runtime Flash Player. Revisar estado del proyecto y toolchains que aún funcionan.

### 3.7 OpenFL

- Sitio: https://openfl.org/
- Repositorio: https://github.com/openfl/openfl
- Proyecto relacionado: https://github.com/openfl/swf

Investigar si es más conveniente migrar el código fuente de aplicaciones a Haxe/OpenFL que reimplementar el reproductor. Verificar:
- Objetivos de salida disponibles hoy: HTML5, nativo y otros.
- Compatibilidad real con el código fuente original.
- Qué assets SWF se pueden importar y cuáles deben convertirse.
- Estado y nivel de madurez de los módulos relacionados con SWF.
- Licencias, dependencias, mantenimiento y esfuerzo de migración.

### 3.8 Proyectos históricos para contexto, no como primera base

- Mozilla Shumway: https://github.com/mozilla/shumway
- GNU Gnash: https://www.gnu.org/software/gnash/

Verificar su estado directamente. Shumway es histórico/archivado; Gnash es legado. Usarlos para ideas, documentación, pruebas o algoritmos si aportan algo concreto, no asumir que son buenas bases de producción modernas.

---

## 4. Búsqueda específica del código original de Adobe

Esta sección debe ser una investigación separada. No mezclar el hallazgo de AVMPlus con la existencia del código completo del reproductor.

### 4.1 Fuentes y archivos que revisar

- GitHub y repositorios oficiales de Adobe.
- Historial de proyectos y organizaciones `adobe-flash`, `adobe`, `mozilla` y repositorios de la comunidad con referencias primarias.
- Archivo web: https://web.archive.org/
- Internet Archive: https://archive.org/
- Documentación de Adobe archivada y especificaciones SWF/FLV/AMF.
- Catálogos de software histórico y archivos de código con procedencia documentada.
- Artículos técnicos, anuncios de donación de código y publicaciones originales de Adobe/Mozilla.
- Mirrors de repositorios antiguos: comprobar commit hash, autoría, tags y coincidencia con el upstream.
- Repositorios de código de investigación académica y archivos de conferencias que documenten componentes de Flash.

### 4.2 Consultas de búsqueda sugeridas

Ejecutar las consultas en inglés y español, y registrar cuáles se usaron y los resultados relevantes:

- `"Adobe Flash Player" source code released`
- `"Flash Player" source code repository Adobe`
- `Adobe Flash Player leaked source code provenance`
- `Adobe Flash Player source code archive`
- `site:github.com adobe flash player source`
- `site:github.com/adobe-flash avmplus`
- `Adobe AVM2 source code donation Mozilla Tamarin`
- `Adobe Flash Player open source announcement`
- `Flash Player native runtime source code`
- `Flash Player source code leak legal status`
- `código fuente original Adobe Flash Player repositorio`
- `Adobe Flash Player código fuente filtrado procedencia`
- `Flash Player source tarball archived`
- `Adobe Flash Player debugger source code`

Usar búsquedas por dominio y búsquedas de frase exacta. Repetir con nombres de versiones, componentes y términos históricos encontrados en las fuentes.

### 4.3 Qué se acepta como evidencia

Evidencia fuerte:
- Anuncio oficial de Adobe o Mozilla.
- Repositorio de upstream con historia verificable.
- Documentación legal o licencia dentro del repositorio.
- Commit/tag autenticable y referencias cruzadas con el proyecto original.

Evidencia débil:
- Un archivo ZIP sin autor ni hash conocido.
- Un vídeo que afirma que “se filtró todo”.
- Un repositorio que usa el nombre Adobe sin historial verificable.
- Copias en foros, sitios de descarga o repositorios con archivos binarios sin fuentes.
- Comentarios que confunden el código de un SDK con el runtime.

Si aparece una presunta filtración:
1. No descargar ni ejecutar de inmediato.
2. Buscar confirmación independiente y procedencia.
3. Identificar si incluye fuentes, símbolos, binarios o solo archivos parciales.
4. Evaluar términos de uso y riesgos jurídicos antes de recomendar su utilización.
5. Informar el hallazgo como indicio hasta tener confirmación sólida.

### 4.4 Conclusión que debe producir el agente

Redactar una conclusión limitada a la evidencia:
- Qué fuentes oficiales fueron consultadas.
- Qué partes del runtime se verificaron como publicadas.
- Si se encontró o no una liberación completa.
- Qué componentes están disponibles de forma legítima.
- Qué incertidumbres quedan abiertas.

Nunca escribir “el código no existe en ningún lugar” si solo se revisaron repositorios públicos.

---

## 5. Especificaciones y documentación técnica que deben localizarse

Buscar documentación primaria, copias archivadas y versiones exactas. Registrar qué documentos están disponibles, su fecha y la parte del formato que cubren.

### 5.1 Formatos y protocolos

- SWF File Format Specification.
- ActionScript 1/2 y AVM1.
- ActionScript 3 y AVM2 bytecode.
- FLV (Flash Video).
- F4V/ISO Base Media File Format cuando corresponda.
- RTMP y protocolos relacionados, solo si el producto necesita esas funciones.
- AMF0/AMF3 para serialización de datos.
- Formatos de audio, vídeo, fuentes, bitmaps, filtros, blend modes y texto que aparecen en los SWF objetivo.

Recurso de referencia inicial:
- Library of Congress, SWF: https://www.loc.gov/preservation/digital/formats/fdd/fdd000629.shtml

No asumir que una especificación pública documenta todos los comportamientos internos del runtime. Registrar comportamientos históricos que solo puedan deducirse por pruebas.

### 5.2 APIs de Flash

Inventariar, según las aplicaciones objetivo:
- Display list, MovieClip, Sprite, Stage y eventos.
- Loader y carga externa.
- NetConnection, NetStream, URLLoader y acceso a red.
- Audio, vídeo y sincronización.
- Filtros, transformaciones, máscaras, blend modes y caché de bitmap.
- Texto, fuentes y medición.
- XML, sockets, SharedObject y almacenamiento.
- APIs de navegador, ExternalInterface y comunicación host.
- Seguridad, sandbox, dominios y políticas cross-domain.
- APIs AIR si se trata de aplicaciones AIR, separándolas del reproductor de navegador.

Crear una matriz por API: especificación/documentación, soporte en Ruffle, soporte en Lightspark, uso real en el corpus de aplicaciones, criticidad y estrategia de migración.

---

## 6. Evaluación de alternativas modernas

El agente debe decidir primero cuál es el objetivo del proyecto. No son el mismo problema:

### A. Ejecutar archivos SWF antiguos con la mayor compatibilidad posible
Comparar Ruffle y Lightspark. Medir compatibilidad por aplicación, APIs, vídeo, audio, filtros y diferencias de comportamiento.

### B. Optimizar un reproductor compatible
Partir de Ruffle como candidato principal en Rust, construir benchmarks reproducibles y optimizar únicamente los puntos calientes confirmados.

### C. Migrar aplicaciones Flash cuyo código fuente está disponible
Evaluar HTML5/Canvas/WebGL/WebGPU, TypeScript, frameworks modernos, Haxe/OpenFL y conversión de assets. Comparar coste total, mantenibilidad y fidelidad, no solo FPS.

### D. Analizar colecciones SWF a escala
Usar Rust o Go para parsing, inventario, extracción de assets y reportes. Mantener la ejecución de contenido separada y aislada.

### E. Construir un runtime propio
Solo considerarlo si los requisitos no se satisfacen con proyectos existentes. Estimar por separado parser, AVM1, AVM2, APIs, renderizador, audio/vídeo, seguridad, compatibilidad, herramientas y mantenimiento.

Tecnologías a estudiar según el caso:
- Rust y WebAssembly.
- wgpu/WebGPU, Vulkan, Direct3D, Metal u OpenGL, según las plataformas.
- LLVM/JIT solo si los requisitos y las licencias lo justifican.
- HTML5, Canvas, WebGL/WebGPU y TypeScript para migración.
- Haxe/OpenFL para reaprovechar parte de la lógica de aplicaciones.
- FFmpeg u otras bibliotecas multimedia, revisando licencias, codecs y soporte real.
- Go para CLI, pipelines, análisis y servicios auxiliares.
- C/C++ cuando un componente existente y probado tenga más valor que reescribirlo.

No recomendar automáticamente WebGPU o JIT: validar soporte de plataformas, consumo, latencia, complejidad y seguridad.

---

## 7. Plan de benchmark y profiling

No declarar una optimización exitosa sin un protocolo reproducible.

### 7.1 Crear un corpus representativo

Usar únicamente archivos que se tenga derecho a analizar. Clasificar, como mínimo:
- SWF pequeños, medianos y grandes.
- ActionScript 1/2 y ActionScript 3.
- Animación simple, scripts intensivos, muchas instancias, listas de display grandes.
- Filtros, máscaras, transparencias, bitmaps y escalado.
- Audio, vídeo y sincronización.
- Fuentes y texto.
- Cargas externas y eventos.
- Aplicaciones que ya fallen en el runtime actual.

Registrar hash SHA-256, tamaño, versión SWF, clasificación, procedencia/licencia y caso de prueba. No incluir archivos confidenciales en repositorios públicos.

### 7.2 Métricas

Medir:
- Tiempo de inicio y de carga.
- Tiempo de CPU total y por subsistema.
- Tiempo de cada fotograma y percentiles p50/p95/p99.
- FPS, estabilidad temporal y frames perdidos.
- RAM máxima y memoria sostenida.
- Asignaciones por segundo, pausas del GC y fragmentación cuando las herramientas lo permitan.
- Uso de GPU, tiempo de render y transferencias CPU/GPU.
- Consumo energético si la plataforma permite medirlo.
- Exactitud visual, audio, eventos y resultados funcionales.
- Compatibilidad por test y tasa de fallos/crashes.

Ejecutar con versiones y configuración fijadas, varias repeticiones y máquinas documentadas. Separar compilación/debug de release, arranque frío de ejecución estable y CPU de GPU. Conservar logs sin datos personales.

### 7.3 Herramientas candidatas

Confirmar soporte actual antes de elegir:
- `cargo bench`, Criterion.rs y `cargo flamegraph` para Rust.
- `perf` y herramientas de perfiles del sistema en Linux.
- Instruments en macOS y Windows Performance Recorder/Analyzer en Windows.
- Tracy u otra herramienta de tracing si se integra correctamente.
- Sanitizers, fuzzers y pruebas de regresión.
- Métricas internas de Ruffle y trazas de Lightspark.

No introducir herramientas solo porque sean conocidas; comprobar que funcionan con el sistema y el proyecto seleccionados.

### 7.4 Criterios de aceptación

Antes de modificar código, fijar objetivos, por ejemplo:
- No empeorar compatibilidad en el corpus prioritario.
- Mejorar una métrica objetivo definida de antemano.
- Mantener límites de RAM y latencia.
- No introducir vulnerabilidades conocidas ni saltarse validaciones.
- Pasar tests funcionales y de regresión.
- Documentar la diferencia estadística y el coste de mantenimiento.

El agente debe proponer umbrales después de establecer la línea base; no inventar un porcentaje de mejora antes de medir.

---

## 8. Guía de revisión del código para optimización

Revisar estas áreas en orden, buscando evidencia en perfiles:

1. **Parser SWF:** límites, lecturas, copias, asignaciones, validación y posibilidad de procesamiento incremental.
2. **Representación de datos:** estructuras, locality/cache, referencias, clonaciones y coste de strings/bitmaps.
3. **AVM1/AVM2:** dispatch de opcodes, llamadas a funciones, conversión de tipos, resolución de propiedades, eventos y bytecode.
4. **Memoria:** GC, ciclos de referencias, asignaciones pequeñas, objetos temporales y lifetime.
5. **Display list/layout:** invalidaciones, cálculos repetidos, transformaciones y traversal.
6. **Renderizador:** batching, draw calls, texturas, filtros, máscaras, blending y sincronizaciones CPU/GPU.
7. **Audio/vídeo:** decodificación, buffering, sincronización y copias entre procesos o dispositivos.
8. **Concurrencia:** bloqueos, colas, contención y tareas que podrían ejecutarse en paralelo sin romper semántica.
9. **Interoperabilidad:** FFI, límites Rust/C++, WebAssembly y coste de cruces de interfaz.
10. **Cargas y red:** caching, parseo de respuestas, políticas de seguridad y cancelación.

Por cada optimización, entregar:
- Problema observado y evidencia del profiler.
- Archivos y funciones involucradas.
- Hipótesis causal.
- Cambio mínimo propuesto.
- Riesgos semánticos/compatibilidad.
- Test que reproduce el problema.
- Benchmark antes/después.
- Resultado de pruebas y limitaciones.

Evitar refactors masivos antes de tener pruebas y línea base.

---

## 9. Licencias: verificación obligatoria

Comprobar directamente el archivo LICENSE, avisos por archivo, dependencias y licencias de recursos. La licencia del repositorio no siempre cubre todos los componentes.

Puntos de partida a verificar, no asumir sin revisión actual:
- Ruffle: se publica bajo MIT y/o Apache-2.0 según componentes; confirmar la política vigente y dependencias.
- AVMPlus/Tamarin: comprobar MPL-2.0 y los avisos concretos.
- Lightspark: comprobar GPL/LGPL y qué componentes quedan bajo cada una.
- `open-flash/swf-parser`: verificar la licencia AGPL-3.0 directamente.
- Apache Flex SDK: comprobar licencia Apache y avisos de terceros.
- OpenFL: verificar licencias actuales y dependencias.
- swf-go: comprobar licencia del repositorio y de dependencias.

Para cada uno, responder:
1. ¿Puede modificarse?
2. ¿Puede usarse comercialmente?
3. ¿Qué debe publicarse al distribuir binarios o servicios?
4. ¿Hay obligaciones de atribución o entrega de código?
5. ¿Se permite enlazarlo con un producto propietario?
6. ¿Qué licencias de dependencias o codecs pueden cambiar la respuesta?

No emitir asesoría legal definitiva. Si el uso comercial o la distribución es importante, recomendar revisión legal basada en el árbol de dependencias real.

---

## 10. Búsquedas de GitHub y código

Además de buscar en la web, ejecutar búsquedas directas en GitHub y otras fuentes públicas. Guardar consultas y resultados para que otra persona pueda repetirlos.

Consultas sugeridas para GitHub:
- `flash player language:C++`
- `AVM2 language:C++`
- `ActionScript virtual machine`
- `SWF parser language:Rust`
- `SWF parser language:Go`
- `Flash emulator language:Rust`
- `Flash emulator language:C++`
- `FLV demuxer Rust`
- `AMF0 AMF3 parser`
- `Tamarin AVMPlus`
- `ActionScript bytecode interpreter`
- `Flash JIT LLVM`
- `SWF fuzzing`
- `SWF file format parser`
- `Flash Player source code`

Buscar también por directorios, símbolos y nombres de componentes que aparezcan en Ruffle/AVMPlus/Lightspark. No confiar solo en el nombre del repositorio: inspeccionar código y licencia.

Para cada candidato, anotar:
- URL canónica y redirects.
- Autor/organización.
- Fecha de última actividad verificada.
- Releases y última versión.
- Lenguajes.
- Función exacta.
- Compatibilidad demostrada.
- Tests y CI.
- Licencia.
- Riesgos y motivo de incluir/excluir.

---

## 11. Entregables obligatorios del agente

El agente debe crear una carpeta de investigación con estos archivos:

### `README.md`
Resumen ejecutivo, conclusión, decisión recomendada y límites de la investigación.

### `repositorios.md`
Tabla comparativa de Ruffle, AVMPlus/Tamarin, Lightspark, parser Rust, swf-go, Apache Flex, OpenFL, Shumway y Gnash. Incluir URLs, función, lenguaje, licencia verificada, estado actual, pruebas, compatibilidad y adecuación al objetivo.

### `codigo-original-adobe.md`
Investigación específica sobre si el código completo del reproductor fue publicado. Separar fuentes oficiales, código donado, SDK, binarios, espejos y supuestas filtraciones. Incluir consultas, fuentes, fechas y nivel de certeza.

### `formatos-y-arquitectura.md`
Especificaciones SWF/FLV/AMF, AVM1/AVM2, APIs necesarias y mapa de subsistemas del runtime.

### `licencias.md`
Licencias y dependencias, obligaciones de modificación/redistribución, riesgos y preguntas para asesoría jurídica.

### `plan-migracion.md`
Opciones Rust, Go, C++, WebAssembly, HTML5 y OpenFL. Separar “ejecutar SWF” de “migrar aplicaciones”.

### `benchmark-plan.md`
Corpus, entorno, comandos, métricas, pruebas, criterios de aceptación y plantilla para resultados antes/después.

### `fuentes.md`
Registro de cada fuente: URL, título, tipo (primaria/secundaria), fecha de publicación si se conoce, fecha de consulta, afirmación que sustenta y nivel de confianza.

### `unknowns.md`
Preguntas abiertas, enlaces inaccesibles, repositorios que cambiaron, licencias no concluyentes y próximos pasos.

Si el agente puede ejecutar comandos, incluir scripts de inventario reproducibles, pero no descargar ni ejecutar SWF desconocidos fuera de un entorno aislado.

---

## 12. Método de trabajo recomendado

### Fase 1 — Descubrimiento
1. Verificar repositorios prioritarios.
2. Buscar el código original de Adobe por separado.
3. Localizar especificaciones y anuncios históricos.
4. Construir un mapa de componentes.
5. Registrar fuentes y huecos de información.

### Fase 2 — Validación
1. Verificar dos veces las afirmaciones críticas.
2. Confirmar licencias.
3. Comprobar compilación y pruebas de los candidatos más importantes.
4. Evaluar actividad, compatibilidad y seguridad.
5. Separar hechos de hipótesis.

### Fase 3 — Prototipo
1. Elegir un corpus representativo.
2. Crear línea base con Ruffle y, si resulta viable, Lightspark.
3. Perfilar sin modificar el comportamiento.
4. Identificar los dos o tres cuellos de botella principales.
5. Crear una prueba mínima para cada uno.

### Fase 4 — Decisión
Comparar al menos estas opciones:
- Adoptar y contribuir a Ruffle.
- Integrar componentes abiertos de forma selectiva.
- Mantener componentes C/C++ existentes.
- Crear tooling Rust/Go alrededor de un runtime.
- Migrar aplicaciones a HTML5/OpenFL.
- Construir un runtime propio únicamente si los demás no satisfacen los requisitos.

La recomendación final debe incluir coste estimado en rangos, riesgos, compatibilidad esperada, mantenimiento y evidencia. Si no hay suficiente información para una estimación, declararlo en vez de inventarla.

---

## 13. Prompt operativo para el agente

Copia este bloque como instrucción principal:

> Actúa como investigador sénior de ingeniería inversa legal, runtimes, compiladores, Rust, Go, C/C++, WebAssembly y preservación de software.
>
> Investiga de forma profunda y reproducible la disponibilidad del código fuente de Adobe Flash Player y las alternativas abiertas para analizar, optimizar o migrar su funcionalidad. No asumas que el código completo de Adobe fue publicado. Distingue el reproductor nativo completo de AVMPlus/Tamarin, SDKs, especificaciones, parsers SWF y reimplementaciones como Ruffle y Lightspark.
>
> Empieza por los repositorios canónicos indicados en este documento y amplía la búsqueda usando GitHub, archivos históricos, documentación primaria, anuncios de Adobe/Mozilla, especificaciones y literatura técnica. Verifica las URLs actuales, redirects, actividad, releases, historial, estructura del código, tests, dependencias y licencias. Para cada afirmación importante busca dos confirmaciones fiables, priorizando fuentes primarias. Registra consultas, fecha de consulta, URL y qué afirmación respalda cada fuente.
>
> No declares que algo no existe en toda Internet. Indica qué fuentes y búsquedas revisaste y formula la conclusión con el grado de certeza correcto. No presentes una supuesta filtración como auténtica sin procedencia demostrable. No descargues ni ejecutes binarios o SWF no confiables sin aislamiento y autorización.
>
> Compara Ruffle, AVMPlus/Tamarin, Lightspark, parsers SWF en Rust/Go, Apache Flex, OpenFL y proyectos históricos. Explica qué parte del sistema implementa cada uno, qué no implementa, estado de mantenimiento y compatibilidad actual. Verifica licencias directamente y registra obligaciones de dependencias.
>
> Evalúa Rust como candidato para el núcleo, Go para herramientas de inventario/análisis y C/C++ para componentes existentes; no elijas un lenguaje por moda. Propón alternativas HTML5/WebGL/WebGPU/WebAssembly/OpenFL cuando migrar las aplicaciones sea más razonable que mantener un runtime.
>
> No afirmes que una reescritura o un JIT será más rápido sin benchmark. Diseña una línea base, corpus legal de pruebas, métricas de CPU/RAM/latencia/renderizado/compatibilidad y criterios de aceptación. Recomienda optimizar primero los cuellos de botella que los perfiles demuestren.
>
> Entrega los archivos `README.md`, `repositorios.md`, `codigo-original-adobe.md`, `formatos-y-arquitectura.md`, `licencias.md`, `plan-migracion.md`, `benchmark-plan.md`, `fuentes.md` y `unknowns.md`. El resumen ejecutivo debe ser conciso; los anexos deben permitir que otro ingeniero repita la investigación. Señala claramente hechos verificados, indicios, incertidumbres y decisiones recomendadas.
>
> No modifiques ningún repositorio ni hagas commits sin aprobación explícita. Primero entrega investigación y plan; espera autorización antes de implementar.

---

## 14. Resumen ejecutivo inicial para el agente

La mejor hipótesis de trabajo es que no existe una publicación oficial ampliamente verificable del código fuente completo de Adobe Flash Player, mientras que sí existen fuentes públicas de componentes relacionados y reimplementaciones abiertas. AVMPlus/Tamarin permite estudiar una VM de ActionScript 3; Ruffle es la primera base que conviene evaluar para un runtime moderno en Rust; Lightspark sirve de contraste nativo C/C++; Go parece más apropiado para análisis y automatización que para reemplazar por sí solo el reproductor. Estas conclusiones deben volver a verificarse durante la investigación y actualizarse con evidencia fechada.

**Prioridad de investigación:** Ruffle → AVMPlus/Tamarin → Lightspark → procedencia del código original de Adobe → especificaciones y APIs → herramientas Rust/Go → benchmark → decisión de migración.

**Decisión que no debe tomarse aún:** reescribir todo Flash Player. Primero establecer el objetivo de compatibilidad, verificar licencias y medir una línea base.
