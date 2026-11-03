# XPS 13 9345 — Bitácora pública de estabilidad Ubuntu ARM64

Repositorio comunitario de problemas, diagnósticos, soluciones reproducibles y procedimientos de reversión para **Dell XPS 13 9345 (Snapdragon X Elite)**.

## Estado inicial observado — 2026-11-01
- Ubuntu 26.10, kernel `7.3.0-10-generic`, Secure Boot activado.
- EVDI 1.15 firmado con un certificado MOK inscrito, pero rechazado por el kernel.
- `systemd-modules-load.service` falla al cargar EVDI.
- DisplayLink D6000: servicio inactivo, historial de reinicios fallidos.
- El firmware IRIS `qcvss8380.mbn` **ya fue extraído de Dell, verificado e instalado en la ruta correcta**. El dispositivo V4L2 aparece, pero la aceleración real aún no funciona en las pruebas: `not-negotiated`; no repetir sesiones de video a ciegas.
- Audio, Wi-Fi y cámara aparecen enumerados; esto **no** demuestra funcionamiento completo.

## Guías
- [DisplayLink + Secure Boot](docs/secure-boot-evdi.md)
- [Firmware de video IRIS](docs/qcom-iris.md)
- [Ventiladores / EC](docs/thermal-ec.md)
- [Audio y SoundWire](docs/audio.md)
- [Diagnóstico seguro](scripts/diagnose-readonly.sh)

## Ciclo de cierre del sprint con Superpowers

Implementamos un [controlador iterativo de diagnóstico seguro](docs/sprint-cycle-method.md), con estados, pruebas TDD, evidencias privadas y reportes anonimizados.

```bash
python3 -m unittest discover -v
python3 scripts/sprint_cycle.py --run --max-rounds 6
```

**No es un instalador automático de drivers**: se detiene cuando el trabajo restante exige autorización, prueba física o una corrección upstream. Consulte la [validación](docs/sprint-cycles/2026-11-01-validation.md) y la [comparación previa con upstream](docs/sprint-2026-11-01-upstream-solutions-review.md).

## Política de pruebas
Cada solución deberá documentar versiones, síntomas, causa, referencias upstream, método, evidencia posterior y cómo deshacerla. Ninguna prueba puede desactivar Secure Boot, copiar certificados privados a GitHub ni realizar cambios irreversibles sin decisión explícita.

**No alojamos firmware propietario de Dell o Qualcomm.** Se documenta procedencia y verificación de integridad; cada persona debe obtenerlo de fuentes autorizadas.

## Ejecutar diagnóstico de solo lectura
```bash
bash scripts/diagnose-readonly.sh
```
El resultado se muestra por pantalla: no se guarda ni se publica automáticamente.
