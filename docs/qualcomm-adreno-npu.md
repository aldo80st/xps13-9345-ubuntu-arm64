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
  `cargo test --locked --all-targets`: **89 pruebas PASS, 0 FAIL**.
- Build reproducible desde el script del repositorio: **PASS**; conserva
  `/usr/bin/resources` sin cambios.
- Smoke GUI combinado: **PASS** durante 11 segundos, 6 sensores Qualcomm CPU,
  GPU `Qualcomm Adreno X1-85`, `clock_speed: Some(300000000.0)`,
  temperaturas `Some(77.6)`, `Some(77.2)` y `Some(76.8)`.
  El proceso terminó por el límite previsto de la prueba, no por un panic.
- La lectura interna y el arranque están verificados; la confirmación
  visual humana de los subtítulos renderizados es un gate aparte.

Para revertir la versión aislada:

~~~bash
rm -rf ~/.local/opt/resources-qualcomm-51
rm -f ~/.local/share/applications/org.gnome.Resources.QualcommTest.desktop
~~~

## Referencias

- [Linux Qualcomm QDA RFC](https://www.spinics.net/lists/kernel/msg6060193.html)
- [Linux accel/qda v2, 2026](https://lkml.indiana.edu/hypermail/linux/kernel/2608.2/00896.html)
- [GNOME Resources](https://gitlab.gnome.org/GNOME/Incubator/resources)
