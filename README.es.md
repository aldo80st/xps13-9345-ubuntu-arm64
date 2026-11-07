# XPS 13 9345 — Bitácora pública de estabilidad Ubuntu ARM64

Repositorio comunitario de problemas, diagnósticos, soluciones reproducibles y procedimientos de reversión para **Dell XPS 13 9345 (Snapdragon X Elite)**.

## Estado inicial observado — 2026-11-01
- Ubuntu 26.10, kernel `7.3.0-10-generic`, Secure Boot activado.
- EVDI 1.15 firmado con un certificado MOK inscrito, pero rechazado por el kernel.
- `systemd-modules-load.service` falla al cargar EVDI.
- DisplayLink D6000: servicio inactivo, historial de reinicios fallidos.
- Falta el archivo `qcom/x1e80100/dell/xps13-9345/qcvss8380.mbn` solicitado por IRIS; **ya fue extraído del controlador oficial Dell y verificado contra el archivo comunitario**, pendiente instalación y pruebas tras reinicio.
- Audio, Wi-Fi y cámara aparecen enumerados; esto **no** demuestra funcionamiento completo.

## Guías
- [DisplayLink + Secure Boot](docs/secure-boot-evdi.md)
- [Firmware de video IRIS](docs/qcom-iris.md)
- [Ventiladores / EC](docs/thermal-ec.md)
- [Audio y SoundWire](docs/audio.md)
- [Diagnóstico seguro](scripts/diagnose-readonly.sh)
- [Hibernación ARM64: diagnóstico y plan seguro](docs/hibernation-arm64.md)
- [Hibernación: auditoría M1 de kernel y parches](docs/hibernate-kernel-m1.md)
- [Hibernación: auditoría automatizada de configuración](docs/hibernate-config-audit.md)
- [M2: Toolchain ARM64 reproducible y validación de Kconfig](docs/hibernate-m2-toolchain.md)
- [M3: Matriz de compatibilidad hibernación, Dell EC y SCMI](docs/hibernate-thermal-m3.md)
- [Reproducción del controlador térmico Dell EC v8 en laboratorio](docs/thermal-hibernation-integration.md)
- [Epic XPS-HIB-01: milestones, agentes y seguimiento](docs/hibernate-epic-tracking.md)
- [Hibernación: revisión independiente de parches (Paseo)](docs/hibernate-patch-review-20261107.md)

## Política de pruebas
Cada solución deberá documentar versiones, síntomas, causa, referencias upstream, método, evidencia posterior y cómo deshacerla. Ninguna prueba puede desactivar Secure Boot, copiar certificados privados a GitHub ni realizar cambios irreversibles sin decisión explícita.

**No alojamos firmware propietario de Dell o Qualcomm.** Se documenta procedencia y verificación de integridad; cada persona debe obtenerlo de fuentes autorizadas.

## Ejecutar diagnóstico de solo lectura
```bash
bash scripts/diagnose-readonly.sh
```
El resultado se muestra por pantalla: no se guarda ni se publica automáticamente.
