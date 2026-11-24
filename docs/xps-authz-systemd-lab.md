# XPS AUTHZ v1.1 — fixtures systemd de laboratorio (M4)

**NO INSTALAR NI ACTIVAR.** Los seis archivos de `tests/fixtures/xps-authz-units/` son material de revisión estática. Todos los servicios declaran únicamente `ExecStart=/usr/bin/true`. Cada unidad tiene una condición que impide su arranque cuando existe `/usr/bin/true`; los fixtures carecen de sección `[Install]`. La comprobación se realiza sin privilegios, en el worktree, sobre la base `c6f8af36043fd10d5aa24a91707f4481b53a687e`.

Referencias del repositorio: [contrato r2](../.ai-architect/architecture-contract.yaml), [plan y gates](../.ai-architect/implementation-plan.md), [broker](xps-authz-broker-interface.md), [IPC](xps-authz-ipc.md), [inspección nativa](xps-authz-native-readonly.md) y [migración de identidades](xps-authz-migration.md).

## Límites declarados

| Unidad (`xps-authz-lab-*`) | Contrato representado |
|---|---|
| `broker.socket` | AF_UNIX/SOCK_STREAM por ruta de filesystem `/run/xps-authz-lab.sock`, bajo el padre del sistema `/run`. Socket `root:xps-agent` 0660, un listener para el broker fijo. El gate nativo debe comprobar que el agente carece de escritura en el padre. El broker futuro debe verificar UID y GID exactos mediante `SO_PEERCRED`; la pertenencia al grupo del socket por sí sola no acredita la identidad. |
| `broker.service` | Identidad root candidata para estado protegido, con bounding set y capacidades ambientales vacíos. Debe recibir el descriptor de socket y solicitar únicamente unidades fijas mediante el supervisor pendiente. |
| `audit.service` | Lectura prevista de módulos con filesystem protegido contra escritura, bounding set vacío y `SystemCallFilter=~@module`. Se omite `ProtectKernelModules` para conservar las rutas de módulos. Queda pendiente definir y comprobar la visibilidad de procesos exigida por el inspector nativo, incluida la decisión sobre `CAP_SYS_PTRACE` y el testigo protegido por boot. |
| `thermal.service` | `DynamicUser=yes`, 25 % de un núcleo, `RuntimeMaxSec=10s`, `TimeoutStopSec=1s`, `KillMode=control-group` y SIGKILL habilitado. El presupuesto configurado de ejecución y parada suma 11 s. El límite efectivo de 12 s, la carga de un trabajador y la parada en hasta 2 s ante revocación o caducidad requieren prueba. |
| `iris-r0.service`, `recovery.service` | Únicos bounding sets con `CAP_SYS_MODULE`, capacidad prevista para la operación oficial. Unidades fijas, sin disparadores de recuperación ni llamadas a módulos. El supervisor deberá preservar la recuperación independiente de la conexión y del proceso principal. |

Los cinco servicios declaran `NoNewPrivileges=yes`, sin capacidades ambientales, red privada y familias de socket limitadas a AF_UNIX. El socket modela una cuenta de servicio futura. Esta revisión no provisiona cuentas ni políticas de autorización.

## Verificación local

Desde la raíz del worktree, con UID no privilegiado:

```sh
python3 -B -m unittest discover -s tests -p test_xps_authz_unit_contract.py -v
systemd-analyze --man=no --generators=no --recursive-errors=yes verify tests/fixtures/xps-authz-units/*.socket tests/fixtures/xps-authz-units/*.service
```

`unittest` comprueba el inventario y las directivas del fixture. `verify` comprueba carga, sintaxis y dependencias de las unidades en la versión local de systemd. El resultado es estático. El sandbox efectivo, los permisos del socket creado por systemd, las credenciales de peer y los límites de cgroup requieren evidencia de ejecución aparte.

## Integración y gates nativos pendientes

- **Supervisor de trabajadores.** Falta conectar la admisión al lanzamiento fijo, correlacionar la terminación por ID de operación, propagar fallos y supervisar térmica y recuperación aun si cae el broker. La recuperación debe quedar acotada y nunca repetir la descarga.
- **Persistencia de recibos e informes.** Faltan el canal protegido de resultados, la persistencia de informes y recibos de admisión, rechazo, resultado y recuperación, y su correlación con el marcador durable. Probar escritura atómica y fsync de archivo y directorio, o durabilidad equivalente, con disco lleno y caídas. Un fallo de evidencia bloquea nuevas acciones y conserva la restauración comprometida.
- **G-ID y G-AUDIT.** Validar identidades y permisos reales, descriptor del socket, credenciales exactas y negativas desde ambas rutas MCP y su rollback. Comprobar lectura de los archivos requeridos, capacidades efectivas y filtro de syscalls. Las pruebas negativas de carga y descarga se reservan al laboratorio autorizado.
- **G-LEASE y G-LEDGER.** Demostrar consumo previo al efecto, serialización con expiración y revocación, exclusión y denegación ante reinicio, cambio de boot, duplicación y fallo de persistencia. Reconciliar desconexiones mediante estado y recibos.
- **G-THERM.** Validar cgroup y watchdog independientes de la vida del broker, sensores y alimentación según r2, muestreo objetivo de 250 ms, aborto y parada ante revocación o caducidad. Comprobar que no quedan procesos y medir los plazos en host responsivo.
- **G-R0.** Probar marcador previo al efecto y recuperación oficial ante caída, desconexión y timeout. Conservar bloqueo hasta verificar módulo, dispositivos y smoke CPU/Iris de 120 cuadros. Un boot distinto exige reconciliación local sin carga automática.

Aceptación nativa M4 y pruebas de instalación **NOT_RUN**. Q-002 sigue abierto. M5 y M6 dependen de sus gates y de autorización local separada.
