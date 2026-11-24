# XPS AUTHZ v1.1 — M3-DIAGNOSTIC staging design (no privileged effects)

Estado: **candidato de laboratorio y staging**. Sin instalación en host, sin servicios systemd activos, sin creación de cuentas ni credenciales, sin ejecución en XPS y sin privilegios concedidos. No se declara aislamiento real del sistema.

## 1. Propósito y límites

`scripts/xps_authz_diagnostic.py` implementa únicamente el canal diagnóstico M3-DIAGNOSTIC para verificar transporte `AF_UNIX` + `SO_PEERCRED` y el contrato de identidad dedicada antes de cualquier broker o ejecutor:

- `status\n`: responde `STATUS` con contadores en cero (`lease_remaining_s=0`, `remaining={audit:0, iris-r0:0, thermal:0}`, `recovery_pending=false`, `operation_id=null`).
- `audit\n`, `iris-r0\n`, `thermal\n`: siempre responde `DENIED` (`reason="NO_LEASE"`), independientemente de cualquier archivo o variable de entorno.
- Sin `grant`, sin `revoke`, sin almacenamiento ni escritura de política, sin importación de `xps_authz_actions` ni `xps_authz_policy`, sin `sudoers`, sin listener propio en Python y sin ejecución como root.

## 2. Proveniencia e identidad

- **Ejecución aislada:** la unidad `deploy/xps-authz-diagnostic/xps-authz-diagnostic@.service` invoca `/usr/bin/python3 -I -B /usr/local/libexec/xps-authz-diagnostic/xps_authz_diagnostic.py`.
- **Importación fijada por ruta y SHA-256:** en modo `__main__`, `xps_authz_diagnostic.py` carga `xps_authz_ipc.py` exclusivamente desde `/usr/local/libexec/xps-authz-diagnostic/xps_authz_ipc.py`, verificando en todos los componentes del árbol ausencia de symlinks, propiedad `root:root` (`0:0`) y ausencia de permisos de escritura de grupo/otros (`0o022`), abriendo con `O_RDONLY | O_NOFOLLOW`, validando `fstat` y verificando el digest exacto SHA-256 `28ccde3cd89bdf44e84b434a3b71e0158a7478d5d29f3a10adfe947c9e9d0cf4` (base `696a205099ed9cf81853eb6b150b819a703b952f`) antes de compilar/ejecutar. Ninguna ruta bajo `/home` es válida.
- **Identidad esperada (`SO_PEERCRED`):** obtenida únicamente de NSS (`pwd.getpwnam('xps-agent')`, `grp`, `os.getgrouplist`) sin parámetros de cliente, CLI ni entorno. Rechaza UID/GID `0`, `1000`, el UID/GID de `amarquez` resuelto en NSS, directorios bajo `/home` o `/root`, grupo primario distinto de `xps-agent` y cualquier grupo suplementario o administrativo (`root`, `sudo`, `adm`, `docker`, `lxd`, `wheel`, etc.). Esta validación es solo inventario NSS/cuentas; **no** sustituye al gate `G-ID`.

## 3. Unidades systemd candidatas (`deploy/xps-authz-diagnostic/`)

- `xps-authz-diagnostic.socket`: `ListenStream=/run/xps-authz-diagnostic.sock`, `Accept=yes`, `SocketUser=root`, `SocketGroup=xps-agent`, `SocketMode=0660`, `MaxConnections=16`, `MaxConnectionsPerSource=8`, `RemoveOnStop=yes`.
- `xps-authz-diagnostic@.service`: recibe la conexión ya aceptada en `FD 0` (`StandardInput=socket`), salida a `journal`, `DynamicUser=yes`, `NoNewPrivileges=yes`, `CapabilityBoundingSet=` y `AmbientCapabilities=` vacíos, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateNetwork=yes`, `RestrictAddressFamilies=AF_UNIX`, `MemoryDenyWriteExecute=yes`, `RuntimeMaxSec=5s`, `TimeoutStopSec=2s`, `MemoryMax=64M`, `TasksMax=4`, `CPUQuota=25%`.

## 4. Procedimiento de staging autenticado por el propietario (referencia manual)

**No hay instalador root automatizado todavía.** El propietario autenticado localmente ejecutaría estos pasos solo después de completar `S3` (runtime root-owned fuera de home) y `S4` (cuenta `xps-agent` sin grupos suplementarios y credenciales nuevas por conector), sin habilitar rutas heredadas ni `xps-authz-broker`:

1. Verificar hash SHA-256 de `scripts/xps_authz_ipc.py` (`28ccde3cd89bdf44e84b434a3b71e0158a7478d5d29f3a10adfe947c9e9d0cf4`) y `scripts/xps_authz_diagnostic.py`.
2. Instalar en `/usr/local/libexec/xps-authz-diagnostic` con propiedad `root:root` (`0755` directorio, `0644` ambos scripts `.py`, sin symlinks ni rutas en `/home`).
3. Copiar `deploy/xps-authz-diagnostic/xps-authz-diagnostic.socket` y `deploy/xps-authz-diagnostic/xps-authz-diagnostic@.service` a `/etc/systemd/system/` (`root:root 0644`).
4. Validar unidades con `systemd-analyze --man=no --generators=no --recursive-errors=yes verify` antes de recargar systemd (`systemctl daemon-reload`) y activar únicamente `xps-authz-diagnostic.socket` (`systemctl start xps-authz-diagnostic.socket`).
5. Comprobar que `/run/xps-authz-diagnostic.sock` existe como `root:xps-agent 0660`, que `status\n` desde `xps-agent` devuelve todo en cero, que `audit\n`/`iris-r0\n`/`thermal\n` devuelven `DENIED`/`NO_LEASE` y que conexiones desde `amarquez` (UID 1000) o root fallan por permisos de socket y `SO_PEERCRED`.
6. **No rehabilitar rutas heredadas UID 1000:** el rollback consiste únicamente en detener/deshabilitar `xps-authz-diagnostic.socket`, manteniendo las rutas MCP heredadas retiradas y la consola local del propietario intacta.

## 5. Gates y estado pendiente

- **Migración real S0–S9, identidades reales (`xps-agent`), credenciales de conectores, instalación en XPS:** `NOT_RUN`.
- **Gate `G-ID` (aislamiento real de procesos, grupos en vivo, Docker/LXD, `/run/user/1000`, bus, loopback, sockets abstractos, corte `S7` y rollback `S8`):** `NOT_RUN`.
- **`HUMAN_REQUIRED`:** creación local de `xps-agent` (`S4`), runtime independiente (`S3`), staging autenticado de estas unidades/archivos y revocación de tokens heredados (`S7`).
