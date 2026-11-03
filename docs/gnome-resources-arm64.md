# GNOME Resources 51: CPU Qualcomm/Oryon en ARM64

**Referencia:** Dell XPS 13 9345, Snapdragon X Elite, Ubuntu 26.10, kernel 7.3.0-10-generic, Resources 51.0.

## Defectos confirmados

| Métrica | Observación | Solución |
| --- | --- | --- |
| Temperatura CPU | El kernel publica sensores cpussN_(top/btm)_thermal; Resources no los reconoce | Detectar sensores Qualcomm y mostrar máximo legible de clusters |
| Núcleos físicos | lscpu informa Core(s) per cluster: 12, Cluster(s): 1 y Socket(s): - | Interpretar clusters como alternativa a sockets |
| Frecuencias | Directorio cpu/cpufreq vacío y módulo SCMI CPUFreq sin cargar | Validación independiente del módulo de kernel |
| Sockets/virtualización | Datos no expuestos o inaplicables | Mantener N/A sin inventar información |

## Corrección publicable

Parche: **patches/resources-51-qualcomm-cpu-metrics.patch**

Origen: https://gitlab.gnome.org/GNOME/Incubator/resources, tag 51.0, commit af35f9c3738418c074b63f9c44b748c5defebb02.

El parche altera solo src/devices/cpu.rs. Conserva compatibilidad Intel/AMD/POWER, añade fallback a thermal_zone si falta hwmon y pruebas de regresión. No modifica firmware ni kernel.

### Reproducción

~~~bash
git clone https://gitlab.gnome.org/GNOME/Incubator/resources.git
cd resources
git checkout 51.0
git apply --check /ruta/xps13-9345-ubuntu-arm64/patches/resources-51-qualcomm-cpu-metrics.patch
git apply /ruta/xps13-9345-ubuntu-arm64/patches/resources-51-qualcomm-cpu-metrics.patch
cargo fmt --all -- --check
cargo test --locked --bin resources
~~~

Requiere Rust 1.93+, GTK 4 de desarrollo y libadwaita >=1.8. Probar preferentemente en un contenedor Ubuntu 26.10 ARM64. El parche **no sustituye automáticamente el Resources instalado desde apt**: hay que construir e instalar el ejecutable corregido o recibir la actualización de GNOME/Ubuntu.

### Diagnóstico seguro

~~~bash
bash scripts/diagnose-resources-arm64.sh
~~~

No modifica la máquina y no requiere privilegios. Revisar su salida antes de publicarla.

## Frecuencia: problema aparte del kernel

En el equipo se verificó CONFIG_CPU_FREQ=y, existencia de scmi-cpufreq.ko.zst y ausencia de policies cpufreq. Resources no puede inferir una frecuencia que el kernel no publica. Fedora documenta que algunos equipos Snapdragon necesitan cargar el módulo expresamente debido a la ausencia de autoload:

https://fedoraproject.org/wiki/Snapdragon_WoA_Laptop_Install_%28Fedora_Beta%29

Prueba manual, opcional, durante una ventana donde se pueda recuperar el equipo:

~~~bash
sudo modprobe scmi-cpufreq
ls /sys/devices/system/cpu/cpufreq/
LC_ALL=C lscpu | grep -i MHz
~~~

**Aceptación:** aparecen policyN, frecuencias legibles y no hay errores nuevos en journalctl -k. Si falla, no persistir ni modificar DTB o firmware. Solo si resulta estable, puede hacerse permanente:

~~~bash
printf 'scmi-cpufreq\n' | sudo tee /etc/modules-load.d/90-scmi-cpufreq.conf
~~~

Reversión de persistencia: borrar el archivo y reiniciar. **No se ejecutaron operaciones privilegiadas como parte de este parche.**

## Contribución

La revisión upstream debe enviarse a GNOME GitLab. El repositorio GitHub nokyan/resources está archivado. Distinguir validación de código, aceptación upstream y actualización efectiva del binario instalado.
