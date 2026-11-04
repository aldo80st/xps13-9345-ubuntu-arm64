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

1. Registra `MsmStats { gfx_ns, client_fingerprint, client_count }`, preservando la semántica de
   **tiempo GPU por cliente**, no porcentaje de utilización global.
2. Asocia los FDs DRM al identificador correcto mediante la cadena real
   `/dev/dri/renderD128` → `/sys/class/drm/renderD128/device/drm/card1`.
   Si la identidad no puede resolverse, **no inventa `card0`**.
3. Deduplica por `(DRM node, drm-client-id)`; agrega los contadores de
   varios clientes distintos asociados a un proceso y evita contar varias
   FDs del mismo cliente.
4. Rechaza unidades y contadores malformados, mapeos ambiguos y períodos
   de muestreo inválidos. Un contador que disminuye o un conjunto de clientes
   diferente (huella+conteo) no se interpreta como `0 %` de actividad:
   la muestra es desconocida. La huella es una combinación determinista de
   identificadores de cliente y puede colisionar excepcionalmente; no se
   interpreta como una identidad criptográfica.
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

- Suite Resources: **91 pruebas PASS**, incluyendo regresión para distinguir
  muestras GPU desconocidas de ceros reales.
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
  verificado en log. La aceptación de la columna GPU se automatiza con
  `scripts/verify_resources_ui.py`, descrito a continuación.

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

### Validación de identidad estable, segunda iteración

Para no confundir la aparición de procesos nuevos con trabajo GPU, el
verificador compara la clave interna `(pid, starttime, card)` entre dos
muestras RON y únicamente suma incrementos positivos de identidades
estables. **No imprime esas claves**; sólo publica número de grupos,
incremento acumulado en nanosegundos y estado de actividad. El agregado de
todos los procesos se conserva como dato de diagnóstico, no como prueba de
actividad ni porcentaje de ocupación global.

Prueba ejecutada el 3 de noviembre de 2026 en el XPS, con `vkcube`
(Adreno X1-85) y 1.6 s entre muestras: `DRM_CARDS=1`,
`STABLE_PROCESS_GROUPS=17`, `STABLE_PROCESS_ACTIVITY_NS=102762755`,
`ENGINE_ACTIVITY_OBSERVED=YES`, retorno `0`. La suite Python ahora
contiene **4 pruebas PASS**, incluyendo cambios de inicio de proceso,
contador reseteado y un cliente nuevo que no cuenta como actividad previa.

**Iteración adicional, validada:** el modelo Rust ahora conserva también una
huella XOR de identificadores mezclados con SplitMix64 y un conteo de clientes
por proceso. La UI invalida la comparación si cambia esa pareja; el
verificador externo también exige igualdad de la huella y el conteo, junto
con `(pid, starttime, card)`. Esto elimina falsos incrementos cuando se
abre/cierra un cliente DRM en las pruebas realizadas.

Un cliente DRM puede ser compartido entre procesos y la huella compacta
(64 bits + conteo) no equivale a conservar el conjunto exacto; una colisión
es teóricamente posible. No afirmar identificación individual perfecta ni
porcentaje global. Los identificadores originales de clientes no se muestran
en reportes del comprobador.

Validación adicional del 3 de noviembre en el XPS: durante una nueva prueba
Vulkan, los registros pasaron de **21 a 22**; se compararon **21 grupos
estables**, con `STABLE_PROCESS_ACTIVITY_NS=45444202` y `EXIT=0`. El
constructor completo con huella de clientes volvió a pasar **90 + 21 tests**
y la instalación aislada.

Un contraste exploratorio de tiempo de barrido con 3 muestras en el
mismo equipo dio mediana **0.114 s** para el auxiliar Ubuntu y **0.116 s**
para el parcheado. El valor es orientativo y **no** prueba una equivalencia
estadística de rendimiento.

## Aceptación funcional de la interfaz — completada

Se corrigió otra conversión errónea de `None` a `0.0 %` / `0 B` en las
**filas y el diálogo de procesos**. La capa `Process` conserva getters
compatibles, pero añade getters opcionales de GPU, encoder/decoder y
memoria de video para que la interfaz muestre **N/A cuando no hay un
contador medido**, sin modificar los valores de otras métricas. La tabla
usa el centinela `-1` sólo en propiedades de presentación. Un contador
válido con valor cero sigue mostrando `0.0 %`.

Se incorporó una aceptación de pantalla mediante GNOME AT-SPI, sin
capturas privilegiadas ni nombres, PIDs o comandos de procesos:

~~~bash
# Con Resources (Qualcomm test) abierto en la pestaña Procesos:
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  python3 scripts/verify_resources_ui.py --require-positive
~~~

**Resultado real XPS, 3 nov 2026, durante `vkcube` en Adreno X1-85:**
`RENDERED_GPU_CELLS=23`, `GPU_NA_CELLS=14`,
`GPU_VALID_ZERO_CELLS=6`, `GPU_POSITIVE_CELLS=3`,
`RENDERED_GPU_SEMANTICS=VERIFIED`, código de salida **0**. También
pasaron **7 pruebas Python** (4 del verificador DRM y 3 del comprobador
visual), ejecutadas por el workflow existente de validación de scripts.

La comprobación inspecciona las celdas GPU renderizadas y distingue
actividad positiva, cero válido y falta de métricas. No identifica
una fila específica como `vkcube`, ya que GTK virtualiza las filas
visibles; la fuente de actividad por cliente DRM se comprobó por separado
con el verificador de hardware y Vulkan.

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
