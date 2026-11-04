# Qualcomm Adreno / Hexagon: observabilidad real en Dell XPS ARM64

**Fecha:** 3 de noviembre de 2026. Equipo: Dell XPS 13 9345, Qualcomm X1E80100,
Ubuntu 26.10, kernel 7.3.0-10-generic, GNOME Resources upstream tag 51.0.

## GPU: causa y corrección

- Vulkan reconoce **Qualcomm Adreno X1-85** (Mesa Turnip 26.2.4).
- El controlador DRM de pantalla se expone como `msm_dpu`; el dispositivo
  real de GPU está asociado al controlador de plataforma `adreno`.
- Resources 51.0 trata `msm_dpu` como GPU genérica y sólo busca
  `gpu_busy_percent` o rutas `hwmon` relacionadas al DRM, que no existen.
- El GPU real sí tiene `/sys/class/devfreq/3d00000.gpu/cur_freq`,
  `max_freq` (1.25 GHz), `min_freq` (300 MHz) y sensores
  `gpuss_0_thermal` a `gpuss_7_thermal` en hwmon.

El parche [Qualcomm Adreno](../patches/resources-51-qualcomm-adreno-gpu.patch)
identifica **únicamente** controladores Qualcomm Adreno enlazados por el kernel
(no infiere a partir de `msm_dpu` solamente), muestra fabricante y modelo
conocido, lee frecuencia en Hz desde devfreq y máximo de los sensores
térmicos `gpuss` en °C, con fallback a `thermal_zone`. Los sensores
de la NPU, batería y CPU no se mezclan con los de GPU.

La **segunda iteración** corrige un error adicional de Resources 51:
`ui/window.rs` convertía `None` en porcentajes ficticios `0 %` de GPU y
video en equipos sin contadores compatibles. Para Adreno, ahora conserva
los valores desconocidos y desactiva el medidor de la barra lateral.
La gráfica de uso de GPU muestra `N/A`; la temperatura y frecuencia siguen
actualizándose. Una prueba de regresión cubre esta política.

No falsifica **utilización total**, memoria GPU dedicada, potencia ni
frecuencias no disponibles. La GPU utiliza memoria compartida; no se debe
inventar una VRAM dedicada a partir de la RAM general. Los contadores
`drm-engine-gpu` disponibles en `/proc/<pid>/fdinfo` describen actividad
por proceso, **no porcentaje global**: es otro trabajo de instrumentación.

## NPU: diagnóstico y límites

- `remoteproc1: cdsp running` confirma firmware de **DSP de cómputo**
  ejecutándose; no confirma cargas de inferencia ni activación de NPU.
- `/dev/fastrpc-cdsp` y `/dev/fastrpc-cdsp-secure` están presentes,
  sin interfaz de utilización/telemetría estandarizada para Resources.
- Los sensores térmicos `nsp0..3_thermal` están publicados, pero su lectura
  **no demuestra carga/TOPS de la NPU**.
- No existen `/dev/accel/accelN` ni `/sys/class/accel/accelN`.
  Resources 51.0 sólo descubre NPU mediante esa clase DRM,
  no mediante `remoteproc` ni `fastrpc`.
- Propuestas recientes de Linux `accel/qda` diseñan una interfaz aceleradora
  sobre Qualcomm DSP, pero no está disponible como dispositivo
  operativo en este equipo. No corresponde forzar su instalación.

La investigación para exponer carga y capacidades **verificables** de NPU
continúa en [issue #13](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/13).

## Diagnóstico read-only

~~~bash
bash scripts/diagnose-qcom-accelerators.sh
~~~

No requiere privilegios, no modifica equipos ni expone IP, MAC o credenciales.

## Construcción integrada CPU + Adreno

~~~bash
cd ~/labs/xps13-9345-ubuntu-arm64
bash scripts/build-resources-arm64.sh
~/.local/opt/resources-qualcomm-51/run
~~~

El constructor combina de forma secuencial el parche de CPU del PR #11 con
el parche de Adreno, ambos aplicados sobre la etiqueta exacta GNOME 51.0.
Compila Rust, `.gresource` y GSettings desde la misma etiqueta en un
contenedor ARM64. Nunca reemplaza `/usr/bin/resources`.

## Pruebas y aceptación

- GPU aislada sobre upstream 51.0: **86 tests PASS, 0 FAIL**.
- Prueba gráfica GPU: reconoció `Qualcomm Adreno X1-85`,
  `clock_speed: Some(300000000.0)` y `temperature: Some(79.2)` /
  `Some(79.6)`; sin fallos fatales. Por diseño `usage_fraction: None`.
- Ejecución del diagnóstico real: frecuencia 300–1250 MHz de límites,
  8 sensores GPU y 4 térmicos `nsp`, CDSP `running`, dispositivos FastRPC.
- **Integración combinada CPU + Adreno PASS** con la etiqueta upstream 51.0:
  `cargo test --locked --all-targets`: **90 pruebas PASS, 0 FAIL**.
  Se añadió una regresión para que `None` en Adreno no se traduzca en `0 %`.

- Build reproducible desde el script del repositorio: **PASS**; conserva
  `/usr/bin/resources` sin cambios.
- Smoke GUI combinado: **PASS** durante 11 segundos, 6 sensores Qualcomm CPU,
  GPU `Qualcomm Adreno X1-85`, `clock_speed: Some(300000000.0)`,
  temperaturas `Some(77.6)`, `Some(77.2)` y `Some(76.8)`.
  El proceso terminó por el límite previsto de la prueba, no por un panic.
- En el último smoke: `Qualcomm Adreno X1-85`, `clock_speed:
  Some(300000000.0)`, `temperature: Some(71.2)`,
  `usage_fraction: None`, `qualcomm_adreno: true` y registro
  `Adreno: suppressing unsupported utilization meter`.
- AT-SPI permitió **seleccionar la pestaña GPU y leer sus etiquetas reales**:
  fabricante `Qualcomm`, nombre `Qualcomm Adreno X1-85`, frecuencia
  `300.00 MHz`, temperatura `61 °C` en una muestra, uso total `N/A`,
  VRAM `N/A`, codificador y decodificador `N/A`. **La salida UI fue
  validada** contra el defecto de cero ficticio.
- GNOME rechazó ScreenshotWindow con `AccessDenied`; sigue pendiente
  únicamente una revisión visual de estilo/maquetación con captura
  autorizada, no los valores de las etiquetas. No se cambiaron permisos.

## Prevención de regresiones mediante CI ARM64

El workflow [resources-arm64.yml](../.github/workflows/resources-arm64.yml)
se ejecuta en un runner GitHub **ARM64 nativo** y reconstruye el contenedor
Ubuntu 26.10 antes de aplicar ambos parches a GNOME 51.0, ejecutar
`cargo fmt --all -- --check`, `cargo test --locked --all-targets` y compilar.
Con `RESOURCES_CI_ONLY=1` genera y valida los binarios y assets sin instalar
ninguna aplicación en el host efímero. El modo CI se probó localmente en
el XPS: **90 tests PASS, CI_RESULT=0**. El resultado del runner remoto es
un gate independiente. **GitHub Actions ARM64 PASS** en el PR #14:
90 pruebas sin fallos. En la iteración siguiente se eliminó la compilación
ARM64 duplicada por `push` + `pull_request` (los pushes directos a `main`
siguen ejecutando el workflow) y se actualizó checkout a v7 con
`persist-credentials: false`.

Para revertir la versión aislada:

~~~bash
rm -rf ~/.local/opt/resources-qualcomm-51
rm -f ~/.local/share/applications/org.gnome.Resources.QualcommTest.desktop
~~~

## Referencias

- [Linux Qualcomm QDA RFC](https://www.spinics.net/lists/kernel/msg6060193.html)
- [Linux accel/qda v2, 2026](https://lkml.indiana.edu/hypermail/linux/kernel/2608.2/00896.html)
- [Linux accel/qda v4, 1 nov 2026](https://go.mail-archive.com/dri-devel%40lists.freedesktop.org/msg649277.html), **serie en revisión, no instalada**
- [GNOME Resources](https://gitlab.gnome.org/GNOME/Incubator/resources)
