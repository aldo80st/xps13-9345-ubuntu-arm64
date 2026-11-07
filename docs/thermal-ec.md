# Dell Embedded Controller and fan behavior

**Compatibilidad obligatoria con el futuro kernel de hibernación:** revisar [M3: matriz Dell EC v8 × SCMI × hibernación](hibernate-thermal-m3.md). El equipo se observó arrancado con `xps_ec_trial=20261107-stubble`, con el módulo `dell_xps_ec` activo. La fuente Ubuntu 7.3 original carece de ese controlador y DTS. Ya existe [copia integrada de fuentes Dell EC v8 en laboratorio](thermal-hibernation-integration.md), pero sus pruebas de recuperación y compatibilidad de kernel completo siguen pendientes. No reemplazar el módulo existente ni la configuración de arranque desde M3.

A [PATCH v8, published 2026-10-25](https://lkml.rescloud.iu.edu/2610.3/01866.html), introduces an EC driver for the Snapdragon X Elite Dell XPS 13 9345. The cover letter reports insufficient fan response under load, heavy throttling, and suspend/resume peripheral behavior.

**Status:** upstream proposal, not verified as merged into Ubuntu 26.10's `7.3.0-10-generic`. Do not cherry-pick into the daily-driver kernel without a tested secure-boot chain and rollback.

Collect the temperature, power-profile and CPU-load baseline before claiming thermal throttling. A 60 °C instantaneous reading is not proof of a thermal defect.

BIOS 2.15.0 was released 2026-10-21 and contains security updates. Dell cautions not to interrupt flashing; for a BitLocker-enabled Windows installation, suspend BitLocker before BIOS update. Never attempt firmware flashing from an unverified environment.

Source: [Dell BIOS 2.15.0 release](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=PK3V5).
