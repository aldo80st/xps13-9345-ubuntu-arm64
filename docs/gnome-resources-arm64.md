# GNOME Resources 51.0 — Qualcomm/Oryon (ARM64)

## Estado

**Validado en Dell XPS 13 9345**, Snapdragon X Elite, Ubuntu 26.10,
Linux 7.3.0-10-generic, arquitectura aarch64. Esta corrección detecta sensores
de temperatura de CPU y la topología ARM64 sin inventar métricas no expuestas.

Origen: https://gitlab.gnome.org/GNOME/Incubator/resources
etiqueta **51.0**, commit **a44f9a1aecb68b2d893eecffd78112f80b0969c5**.
Parche: [resources-51-qualcomm-cpu-metrics.patch](../patches/resources-51-qualcomm-cpu-metrics.patch).

## Problemas y correcciones

| Métrica | Estado |
| --- | --- |
| Temperatura CPU | **Corregida**: usa sensores `cpussN_(top/btm)_thermal` disponibles en `hwmon`; fallback `thermal_zone`; máximo legible de clusters |
| Núcleos físicos | **Corregida**: interpreta `Core(s) per cluster` y `Cluster(s)` de `lscpu` |
| Frecuencias CPU | **Pendiente del kernel**: no hay políticas en `/sys/devices/system/cpu/cpufreq` |
| Sockets / virtualización | Conservar `N/A` cuando son inaplicables o no están disponibles |
| Propiedades `tailscale0` | `N/A` para propiedades Ethernet es esperado en una interfaz virtual TUN |

## Construir, probar e instalar versión separada

Requiere Docker, Git y GLib (Ubuntu GNOME). No usa `sudo`:

~~~bash
cd ~/labs/xps13-9345-ubuntu-arm64
bash scripts/build-resources-arm64.sh
~/.local/opt/resources-qualcomm-51/run
~~~

El script verifica el commit fuente 51.0, aplica el parche a copia temporal,
construye en Docker **Ubuntu 26.10 ARM64**, ejecuta `cargo fmt --all -- --check`,
`cargo test --locked --all-targets` y `cargo build --locked --bin resources`.
Compila además el archivo `resources.gresource` y el esquema GSettings
desde el **mismo origen exacto**. El contenedor usa el UID/GID local,
sin capacidades adicionales y con `no-new-privileges`.

Si ya tienes la etiqueta 51.0 en una copia Git local:

~~~bash
RESOURCES_SOURCE_REPO=~/labs/gnome-resources-arm64/vanilla-51 \
  bash scripts/build-resources-arm64.sh
~~~

El menú muestra **Resources (Qualcomm test)**, con ID independiente
`org.gnome.Resources.QualcommTest`. No reemplaza el Resources de Ubuntu,
sus recursos visuales ni sus preferencias. El original puede continuar abierto.

Para revertir:

~~~bash
rm -rf ~/.local/opt/resources-qualcomm-51
rm -f ~/.local/share/applications/org.gnome.Resources.QualcommTest.desktop
~~~

No toca kernel, firmware, Secure Boot ni paquetes del sistema.

## Evidencia (3 de noviembre de 2026)

- `git apply --check` sobre etiqueta 51.0: **PASS**.
- Formato Rust: **PASS**.
- `cargo test --locked --all-targets` en etiqueta 51.0:
  **86 pruebas aprobadas, 0 fallidas**.
- El commit posterior `b380a689` pasó **91 pruebas** como validación
  exploratoria, pero el parche publicable se fija a la etiqueta 51.0.
- Aplicación aislada iniciada con su `.gresource` y GSettings coincidentes:
  **arranque correcto sin panic**, detectó seis sensores Qualcomm.
- Lecturas reales: `temperature: Ok(86.3)`, `Ok(85.5)`, `Ok(84.8)`.
  Frecuencias siguen en `None` porque el kernel no las suministra.
- El instalador reproducible finalizó con código **0**; lanzador aislado y esquema generado correctamente.
- Smoke de la aplicación instalada: lecturas `Ok(84.0)`, `Ok(84.4)`, `Ok(81.1)`, proceso detenido intencionadamente tras 9 segundos.
- El ejecutable Ubuntu original **no se modificó**. Falta confirmación
  visual humana de la etiqueta de temperatura del ejecutable aislado.

**Importante:** `cargo test --locked --bin resources` ejecuta 0 pruebas.
La suite válida es `cargo test --locked --all-targets`.

Durante la primera prueba se mezcló un binario upstream con los recursos
visuales/GSettings del paquete Ubuntu y la interfaz se abortó. La construcción
actual genera el binario, los assets GTK y el esquema desde **una misma fuente**,
eliminando esa incompatibilidad. Una advertencia Vulkan no fatal permanece
como observación ajena a este parche.

El script actual en la rama de integración también aplica el parche
[GPU Adreno](../patches/resources-51-qualcomm-adreno-gpu.patch).
Ver [diagnóstico GPU/NPU](qualcomm-adreno-npu.md) para los límites de
utilización y CDSP.

## Frecuencia: investigación aparte

Se confirmó `CONFIG_CPU_FREQ=y` y la presencia del módulo firmado
`scmi-cpufreq.ko.zst`, pero ninguna política activa `cpufreq`.
El módulo no se cargó ni se dejó persistente. Seguimiento: [issue #12](https://github.com/aldo80st/xps13-9345-ubuntu-arm64/issues/12).
Probarlo requiere una autorización específica y comprobar efectos de energía
y suspensión.

## Publicación upstream

Presentar `src/devices/cpu.rs` y sus tests al repositorio GNOME en GitLab.
Conservar el cambio del XPS separado del producto Nexora. No publicar
registros brutos con datos de red, equipos ni identificadores personales.
