# Qualcomm Adreno: contadores de actividad DRM por cliente

**Equipo verificado:** Dell XPS 13 9345, Snapdragon X Elite, Adreno X1-85,
Ubuntu 26.10 ARM64 y kernel 7.3.0-10-generic.

## El defecto

Resources 51.0 descarta las estadísticas de `drm-driver: msm` en su biblioteca
`process-data`. Además, al no existir `drm-pdev`, el parser asignaba por
defecto `GpuIdentifier::Enumerator(0)`; en esta máquina **card0 es EVDI**
(DisplayLink) y la GPU Qualcomm aparece como `card1`/`renderD128`.

Otro defecto: el recolector descartaba todas las FDs posteriores que
apuntaran al mismo nodo `/dev/dri/renderD128`, aunque fueran **clientes DRM
distintos**. El kernel sí publica:

~~~text
drm-driver: msm
drm-client-id: [identificador por cliente]
drm-engine-gpu: [nanosegundos acumulados]
drm-cycles-gpu: [ciclos acumulados]
drm-maxfreq-gpu: [Hz]
drm-total-memory: [KiB de memoria compartida]
~~~

## Corrección implementada

Patch: [resources-51-msm-fdinfo.patch](../patches/resources-51-msm-fdinfo.patch).

1. Registra `MsmStats { gfx_ns }`, preservando la semántica de
   **tiempo GPU por cliente**, no porcentaje de utilización global.
2. Asocia los FDs DRM al identificador correcto mediante la cadena real
   `/dev/dri/renderD128` → `/sys/class/drm/renderD128/device/drm/card1`.
   Si la identidad no puede resolverse, **no inventa `card0`**.
3. Deduplica por `(DRM node, drm-client-id)`; agrega los contadores de
   varios clientes distintos asociados a un proceso y evita contar varias
   FDs del mismo cliente.
4. Rechaza unidades y contadores malformados, mapeos ambiguos y períodos
   de muestreo inválidos. Un contador que disminuye no se interpreta como
   `0 %` de actividad: la muestra es desconocida.
5. No inventa memoria de video **dedicada** ni codificación/decodificación.
6. Conserva **N/A** en el panel de utilización global de GPU: las estadísticas
   por cliente **no equivalen** a telemetría hardware global.

**Limitación de atribución:** DRM publica tiempos por *cliente*. Si un
cliente DRM se comparte entre varios procesos, el tiempo del cliente no
puede repartirse de forma exacta entre esos procesos mediante este
contador. La columna de procesos describe actividad del cliente asociado,
no una medición individual de ejecución GPU universal.

## Compilación integral y regresiones

La receta de [build-resources-arm64.sh](../scripts/build-resources-arm64.sh)
ahora aplica tres parches en orden sobre GNOME Resources tag `51.0`:

- Sensores/topología CPU Qualcomm.
- Identificación, temperatura y frecuencia de GPU Adreno.
- Lectura de clientes `msm`/`fdinfo` y atribución de GPU por tarjeta DRM.

Compila **todas** las herramientas, incluyendo `resources-processes`,
`resources-adjust` y `resources-kill`, con `LIBEXECDIR` apuntando al
directorio aislado:

~~~bash
cd ~/labs/xps13-9345-ubuntu-arm64
bash scripts/build-resources-arm64.sh
~/.local/opt/resources-qualcomm-51/run --open-tab-id processes
~~~

**Esto es indispensable:** compilar solo el ejecutable principal haría
que la interfaz continuara usando `/usr/libexec/resources/resources-processes`
del paquete Ubuntu, que no conoce `MsmStats`.

No sustituye binarios ni configuración bajo `/usr`; todo se instala bajo
`~/.local/opt/resources-qualcomm-51`.

Se ejecutan **dos** suites por separado:

~~~bash
cargo test --locked --all-targets
cargo test --locked --manifest-path lib/process_data/Cargo.toml --all-targets
~~~

`process-data` es un paquete Cargo independiente. La suite de la aplicación
**no incluye** sus tests y no debe considerarse suficiente sin el segundo comando.

## Validaciones en la máquina

- Suite Resources: **90 pruebas PASS**.
- Suite `process-data`: **21 pruebas PASS** (incluye los casos nuevos de
  DisplayLink/card1, clientes distintos/duplicados, malformed/ausente,
  reseteo y falta de mapeo).
- Constructor completo en contenedor Ubuntu 26.10 ARM64: **PASS** en modo
  CI (`CI_RESULT=0`, `CI_ISOLATION=PASS`) y en instalación aislada.
- Consulta del auxiliar compilado en el XPS: `MsmStats` **presente**
  y asociado a `Enumerator(1)`. El número de clientes es dinámico.
- Prueba Vulkan corta (`vkcube`, Adreno X1-85, ventana 160×160):
  dos muestras consecutivas con 12 registros y aumento agregado
  **5 731 476 ns** en contadores de actividad DRM. No es un benchmark
  de rendimiento ni un porcentaje global.
- Smoke de interfaz: Resources detecta Adreno y lanza el auxiliar
  **desde** `~/.local/opt/resources-qualcomm-51/resources-processes`,
  verificado en log. La inspección final de la columna GPU en una fila
  concreta requiere un test de aceptación visual o de accesibilidad
  adicional; no confundir con la validación del auxiliar.

## Smoke test de hardware (sin identificadores de procesos)

~~~bash
python3 scripts/verify_msm_fdinfo.py
~~

Comprueba la presencia de `MsmStats` desde el **auxiliar instalado**, la
asociación con un controlador `msm` real mediante sysfs y dos muestras
consecutivas. Nunca imprime nombres ni IDs de procesos. Cuando no hay carga
GPU, el contador puede quedar estable: eso **no es fallo**.

Opcionalmente, durante una carga gráfica conocida:

~~~bash
python3 scripts/verify_msm_fdinfo.py --expect-activity --interval 1.5
~~

En el XPS con `vkcube` se obtuvo `MSM_FDINFO=VERIFIED`, tarjeta `1`,
12 registros en cada muestra y aumento positivo de **8 927 611 ns**,
con salida `GLOBAL_GPU_UTILIZATION=NOT_INFERRED`. Tres pruebas del
verificador (parser, mapeo de controlador y auxiliar sintético) también
pasaron con `unittest` y se incorporaron al workflow de scripts.

Un contraste exploratorio de tiempo de barrido con 3 muestras en el
mismo equipo dio mediana **0.114 s** para el auxiliar Ubuntu y **0.116 s**
para el parcheado. El valor es orientativo y **no** prueba una equivalencia
estadística de rendimiento.

## NPU

Este parche **no modifica la NPU**: el CDSP figura `running`, pero no
existe un `accelN` operativo ni contadores verificables de inferencias
para presentar en GNOME Resources. Véase
[issue #13](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/13).

## Rollback

La versión de Ubuntu continúa intacta. La instalación de prueba se
desinstala retirando únicamente el directorio y el lanzador del usuario:

~~~bash
rm -rf ~/.local/opt/resources-qualcomm-51
rm -f ~/.local/share/applications/org.gnome.Resources.QualcommTest.desktop
~~~
