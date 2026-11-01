#!/usr/bin/env python3
"""Bounded, read-only XPS sprint diagnostics. No raw command output is persisted."""
import os
from pathlib import Path
import re
import signal
import subprocess

FIRMWARE = Path('/lib/firmware/qcom/x1e80100/dell/xps13-9345')
OFFICIAL_SHA = '8e9d65ceeba183a2640d731e6c3fba6f27957529ab5f811ab78433306e3e7629'
COMMANDS = {
    'kernel': ('uname', '-r'),
    'architecture': ('uname', '-m'),
    'secure_boot': ('mokutil', '--sb-state'),
    'evdi_signature': ('modinfo', '-F', 'sig_hashalgo', 'evdi'),
    'evdi_vermagic': ('modinfo', '-F', 'vermagic', 'evdi'),
    'dock': ('lsusb', '-d', '17e9:6006'),
    'displaylink': ('systemctl', 'show', 'displaylink-driver.service',
                    '-p', 'ActiveState', '-p', 'Result', '-p', 'NRestarts'),
    'kernel_errors': ('journalctl', '-k', '-b', '-n', '100', '-o', 'cat', '--no-pager'),
    'pd': ('systemctl', 'is-active', 'pd-mapper.service'),
    'dc': ('systemctl', '--user', 'is-active', 'desktop-commander-remote.service'),
    'dc_count': ('pgrep', '-fc', '[d]esktop-commander/dist/index.js remote'),
    'pipewire': ('systemctl', '--user', 'is-active', 'pipewire.service'),
    'v4l2': ('v4l2-ctl', '--list-devices'),
    'gst_encoder': ('gst-inspect-1.0', 'x264enc'),
    'gst_parser': ('gst-inspect-1.0', 'h264parse'),
    'gst_stateful': ('gst-inspect-1.0', 'v4l2h264dec'),
    'gst_stateless': ('gst-inspect-1.0', 'v4l2slh264dec'),
}
for _kind, _decoder in [('stateful', 'v4l2h264dec'), ('stateless', 'v4l2slh264dec')]:
    COMMANDS['decode_' + _kind] = (
        'gst-launch-1.0', '-v', 'videotestsrc', 'num-buffers=3', '!',
        'video/x-raw,width=64,height=64,framerate=1/1', '!', 'x264enc',
        'tune=zerolatency', '!', 'h264parse', '!', _decoder, '!',
        'fakesink', 'sync=false')


def command(name):
    """Exact whitelist; kill only the process group this function creates."""
    if name not in COMMANDS:
        raise ValueError('command not allowlisted')
    argv = COMMANDS[name]
    # Ignore user PATH entries and plugin paths. Tools are distribution executables.
    executable = next((str(Path(p) / argv[0]) for p in ('/usr/bin', '/usr/sbin', '/bin')
                       if (Path(p) / argv[0]).is_file()), '/usr/bin/' + argv[0])
    env = {k: v for k, v in os.environ.items()
           if k in ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS')}
    cache = private_directory(Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[1] / '.local/sprint-cycles/tool-cache')
    env.update(PATH='/usr/bin:/usr/sbin:/bin', LC_ALL='C', GST_DEBUG='0',
               HOME=str(cache), XDG_CACHE_HOME=str(cache), XDG_CONFIG_HOME=str(cache),
               XDG_DATA_HOME=str(cache), GST_REGISTRY=str(cache / 'registry.bin'))
    try:
        process = subprocess.Popen((executable, *argv[1:]), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   env=env, start_new_session=True)
    except (FileNotFoundError, PermissionError):
        return {'status': 'unavailable', 'returncode': None, 'output': ''}
    try:
        output, _ = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return {'status': 'timeout', 'returncode': None, 'output': ''}
    return {'status': 'ok' if process.returncode == 0 else 'failed',
            'returncode': process.returncode,
            'output': output[:262144].decode('utf-8', errors='replace')}


def read_text(path):
    try:
        with Path(path).open() as stream:
            return stream.read(16384)
    except (OSError, UnicodeError):
        return None


def collect(allow_active_video_probe=False):
    """Return safe facts. Never exercise unstable IRIS without explicit opt-in."""
    import hashlib
    facts = {}
    results = {name: command(name) for name in COMMANDS if not name.startswith('decode_')}
    facts['commands'] = {name: result['status'] for name, result in results.items()}
    for name in ('kernel', 'architecture'):
        value = results[name]['output'].strip()
        facts[name] = value if results[name]['status'] == 'ok' and re.fullmatch(
            r'[a-zA-Z0-9.+_-]{1,80}', value) else None
    sb = results['secure_boot']
    facts['secure_boot'] = (True if sb['output'].strip() == 'SecureBoot enabled' else
                            False if sb['output'].strip() == 'SecureBoot disabled' else None)
    facts['evdi_signed'] = (bool(results['evdi_signature']['output'].strip())
                            if results['evdi_signature']['status'] == 'ok' else None)
    facts['evdi_matches_kernel'] = (results['evdi_vermagic']['output'].split()[:1]
                                    == [facts['kernel']]) if facts['kernel'] else None
    facts['dock_present'] = (bool(results['dock']['output'].strip())
                              if results['dock']['status'] == 'ok' else None)
    service = results['displaylink']
    facts['displaylink_active'] = ('ActiveState=active' in service['output']
                                   if service['status'] == 'ok' else None)
    journal = results['kernel_errors']
    facts['evdi_rejections_last_100'] = (sum('evdi' in line.lower() and
        any(word in line.lower() for word in ('lockdown', 'rejected', 'unsigned'))
        for line in journal['output'].splitlines()) if journal['status'] == 'ok' else None)
    for key, name in [('pd_active', 'pd'), ('dc_active', 'dc'), ('pipewire_active', 'pipewire')]:
        facts[key] = (True if results[name]['status'] == 'ok' and
                      results[name]['output'].strip() == 'active' else
                      False if results[name]['output'].strip() in ('inactive', 'failed') else None)
    count = results['dc_count']['output'].strip()
    facts['dc_processes'] = int(count) if count.isdigit() and len(count) < 5 else None
    facts['video_nodes'] = len(list(Path('/sys/class/video4linux').glob('video*')))
    facts['iris_v4l2'] = results['v4l2']['status'] == 'ok' and 'iris' in results['v4l2']['output'].lower()
    facts['iris_decode'] = 'not_available'
    if allow_active_video_probe and facts['video_nodes'] and facts['iris_v4l2'] and all(
            results[name]['status'] == 'ok' for name in ('gst_encoder', 'gst_parser')):
        for kind in ('stateful', 'stateless'):
            if results['gst_' + kind]['status'] != 'ok':
                continue
            result = command('decode_' + kind)
            facts['commands']['decode_' + kind] = result['status']
            output = result['output']
            facts['iris_decode'] = ('passed' if result['status'] == 'ok' and
                'Got EOS from element' in output and 'video/x-raw' in output else
                'permission' if any(s in output.lower() for s in ('permission denied', 'not permitted'))
                else 'failed')
            facts['iris_decoder'] = kind
            break
    facts['pd_maps'] = all((FIRMWARE / name).is_file() for name in ('adspr.jsn', 'cdspr.jsn'))
    facts['pd_overlay'] = Path('/lib/firmware/updates/qcom/x1e80100/dell/xps13-9345').exists()
    try:
        firmware = (FIRMWARE / 'qcvss8380.mbn').read_bytes()
        facts['iris_sha_official'] = hashlib.sha256(firmware).hexdigest() == OFFICIAL_SHA
    except OSError:
        facts['iris_sha_official'] = None
    facts['audio_cards'] = len([p for p in Path('/sys/class/sound').glob('card*') if p.name[4:].isdigit()])
    facts['audio_topologies'] = len(list(Path('/lib/firmware/qcom/x1e80100').glob('**/*.tplg*')))
    facts['ucm_present'] = Path('/usr/share/alsa/ucm2/Qualcomm/x1e80100').is_dir()
    temperatures = []
    for path in list(Path('/sys/class/thermal').glob('thermal_zone*/temp'))[:128]:
        text = read_text(path)
        if text and re.fullmatch(r'-?\d{1,7}\s*', text):
            value = int(text)
            if -50000 <= value <= 200000:
                temperatures.append(value)
    facts['ec_sensors'] = len(temperatures)
    facts['max_temperature_millic'] = max(temperatures, default=None)
    bios = read_text('/sys/class/dmi/id/bios_version')
    facts['bios_version'] = bios.strip() if bios and re.fullmatch(r'\d+(\.\d+){1,3}\s*', bios) else None
    return facts


# Historical gate decisions: no claim that proposed fixes are integrated today.
POLICY = {
    1: ('ADAPTAR', 'FIX COMMITTED', 'Ubuntu LP #2131181 / DisplayLink signed DKMS',
        'Revisar integración de kernel firmado y confianza MOK con autorización; probar ambas DisplayPort físicamente.',
        'Dos pantallas DisplayPort con video funcional observado; firma y Secure Boot conservados.'),
    2: ('ADAPTAR', 'PARCIAL', 'Dell KPF2C / V4L2 IRIS; guía Qualcomm de otro BSP',
        'Revisar caps V4L2 y disponibilidad de decoder hardware; elevar permisos solo con intervención humana.',
        'Tres frames H.264 sintéticos por decoder V4L2 hardware hasta EOS, sin render ni archivos personales.'),
    3: ('ESPERAR', 'WIP', 'Dell EC PATCH v8 / Ubuntu LP #2172131',
        'Esperar integración demostrada en kernel firmado; validación térmica funcional supervisada.',
        'Control EC y ventilación funcional demostrados; sensores solos no bastan.'),
    4: ('ESPERAR', 'PARCIAL', 'Dell tributo / AudioReach / UCM / Ubuntu LP #2172596',
        'Comparar topología/UCM y protección del amplificador antes de autorizar prueba acústica.',
        'Protección demostrada y prueba funcional segura L/R y micrófonos supervisada.'),
    5: ('ESPERAR', 'EXISTE', 'Dell BIOS PK3V5; referencia histórica 2.15.0',
        'Confirmar versión vigente Dell, alimentación y recuperación BitLocker; requiere autorización explícita.',
        'Validación humana por procedimiento Dell soportado; no se actualiza en este runner.'),
    6: ('DIRECTO', 'PARCIAL', 'docs/desktop-commander-systemd.md',
        'Validar conexión de relay y continuidad tras login/reinicio de forma supervisada; no reiniciar aquí.',
        'Servicio activo, una instancia y operación remota tras login comprobada.'),
    7: ('DIRECTO', 'EXISTE', 'docs/pd-mapper-overlay-regression.md',
        'Si hay regresión, investigar permisos/mapas y SHA; restauración global requiere intervención humana.',
        'Alcance: regresión de overlay recuperada; servicio activo, mapas base y firmware oficial, sin overlay.'),
    8: ('DESCARTAR', 'RECHAZADO', 'Ubuntu LP #2169496: reintento intencional según gate',
        'No modificar dracut; abrir investigación solo ante fallo gráfico funcional reproducible.',
        'No planificado; no se afirma prueba gráfica funcional.'),
}


def evaluate(facts):
    states = {1: 'BLOCKED_USER', 2: 'BLOCKED_UPSTREAM', 3: 'BLOCKED_UPSTREAM',
              4: 'BLOCKED_UPSTREAM', 5: 'BLOCKED_USER', 6: 'BLOCKED_USER',
              7: 'BLOCKED_USER', 8: 'NOT_PLANNED'}
    reasons = {
        1: 'Confianza MOK/kernel requiere intervención; relación con LP #2131181 es hipótesis. Dock enumerado no demuestra video.',
        2: 'Sin prueba de decode IRIS funcional; enumeración/firmware no demuestran aceleración. Integración usable no demostrada.',
        3: 'Sin solución integrada firmada demostrada ni validación funcional segura; no realizar estrés.',
        4: 'Protección de amplificador no demostrada; no realizar sonido. Integración segura no demostrada.',
        5: 'BIOS/BitLocker requieren intervención y autorización humana; versión disponible citada solo por gate histórico.',
        6: 'Estado de servicio/procesos no prueba relay ni continuidad posterior a login; falta prueba humana funcional.',
        7: 'No se cumplen todos los criterios de recuperación de la regresión; cambio global requiere intervención.',
        8: 'Comportamiento intencional según gate; no hay prueba nueva que justifique cambio.',
    }
    if facts.get('iris_decode') == 'passed':
        states[2] = 'VERIFIED'
        reasons[2] = 'Decode sintético hardware V4L2 completado hasta EOS; alcance limitado a este pipeline.'
    elif facts.get('iris_decode') == 'permission':
        states[2] = 'BLOCKED_USER'
        reasons[2] = 'El diagnóstico indica falta de permisos; elevar requiere intervención humana.'
    if (facts.get('pd_active') is True and facts.get('pd_maps') is True and
            facts.get('pd_overlay') is False and facts.get('iris_sha_official') is True):
        states[7] = 'VERIFIED'
        reasons[7] = 'Regresión de overlay: servicio activo y mapas base disponibles, overlay ausente y SHA oficial correcto. No prueba todo el subsistema.'
    issues = []
    for issue, policy in POLICY.items():
        decision, maturity, source, action, acceptance = policy
        issues.append({'issue': issue, 'state': states[issue], 'decision': decision,
                       'upstream_status': maturity, 'source': source,
                       'reason': reasons[issue], 'human_action': action,
                       'acceptance': acceptance, 'risk': 'Solo lectura; sin cambios globales.',
                       'rollback': 'No aplica: diagnóstico sin mutación del sistema.',
                       'alternatives': ['referencia upstream del gate', 'no intervenir'],
                       'applicability': 'Dell XPS 9345 X1E80100; integración actual no inferida del gate.',
                       'evidence': ['facts'], 'safe_actions': []})
    return issues


# Positive schema prevents newly added diagnostics from leaking into snapshots.
BOOL_FACTS = ('secure_boot', 'evdi_signed', 'evdi_matches_kernel', 'dock_present',
              'displaylink_active', 'pd_active', 'dc_active', 'pipewire_active',
              'iris_v4l2', 'pd_maps', 'pd_overlay', 'iris_sha_official', 'ucm_present')
INT_FACTS = ('evdi_rejections_last_100', 'dc_processes', 'video_nodes', 'audio_cards',
             'audio_topologies', 'ec_sensors', 'max_temperature_millic')
STATES = {'PENDING', 'DIAGNOSING', 'READY_SAFE_ACTION', 'VERIFIED', 'BLOCKED_USER',
          'BLOCKED_PHYSICAL', 'BLOCKED_UPSTREAM', 'WAITING_RELEASE', 'NOT_PLANNED',
          'INVESTIGATION_NEEDED'}
STAGES = ['BASELINE', 'DISCOVER', 'DECIDE', 'PLAN', 'EXECUTE', 'VERIFY', 'PERSIST', 'LOOP_GATE']


def safe_facts(facts):
    clean = {key: facts[key] for key in BOOL_FACTS if type(facts.get(key)) is bool}
    clean.update({key: facts[key] for key in INT_FACTS
                  if type(facts.get(key)) is int and -50000 <= facts[key] <= 200000})
    for key, pattern in [('kernel', r'\d+\.\d+\.\d+-\d+-generic'),
                         ('architecture', r'(aarch64|x86_64)'),
                         ('bios_version', r'\d+(\.\d+){1,3}')]:
        value = facts.get(key)
        if isinstance(value, str) and re.fullmatch(pattern, value):
            clean[key] = value
    for key, values in [('iris_decode', {'passed', 'failed', 'permission', 'not_available'}),
                        ('iris_decoder', {'stateful', 'stateless'})]:
        if facts.get(key) in values:
            clean[key] = facts[key]
    clean['commands'] = {key: value for key, value in facts.get('commands', {}).items()
                         if key in COMMANDS and value in {'ok', 'failed', 'unavailable', 'timeout'}}
    return clean


def private_directory(root, path):
    """Reject symlink components before any mutation, including inside the tree."""
    root, path = Path(root).absolute(), Path(path).absolute()
    if '..' in path.parts or not path.is_relative_to(root):
        raise ValueError('output must stay in this worktree')
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink output component rejected')
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        current.mkdir(mode=0o700, exist_ok=True)
        if not current.is_dir():
            raise ValueError('output component is not a directory')
    return path


def atomic_write(path, content):
    import tempfile
    if path.is_symlink():
        raise ValueError('symlink destination rejected')
    descriptor, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def public_report(data):
    # Do not render arbitrary facts, raw outputs, boot_id or exception messages.
    lines = ['# Sprint cycle — evidencia redactada', '',
             f"Iteración: {data['sequence']}. Fecha UTC: {data['checked_at']}.",
             f"Parada: `{data['stop_reason']}`.", '',
             'El gate es una referencia histórica; no se confirmó una nueva release en línea.', '',
             '| Issue | Estado | Decisión |', '| --- | --- | --- |']
    for item in data['issues']:
        lines.append(f"| #{item['issue']} | {item['state']} | {POLICY[item['issue']][0]} |")
    lines.extend(['', 'Los estados VERIFIED tienen alcance limitado al criterio indicado.'])
    for item in data['issues']:
        issue = item['issue']
        lines.extend(['', f"## #{issue}", '', f"Fuente: {POLICY[issue][2]}.",
                      f"Criterio: {POLICY[issue][4]}", f"Acción humana/upstream: {POLICY[issue][3]}"])
    return '\n'.join(lines) + '\n'


def run(root, output_dir, max_rounds=6, once=False, collector=collect):
    import datetime
    import fcntl
    import hashlib
    import json

    if type(max_rounds) is not int or not 1 <= max_rounds <= 6:
        raise ValueError('max_rounds must be between 1 and 6')
    root = Path(root).resolve()
    output_dir = Path(output_dir).absolute()
    if not output_dir.is_relative_to(root / '.local'):
        raise ValueError('private output must be under worktree .local')
    # Preflight every destination before writing even the first directory.
    for target in (output_dir / 'iterations', root / 'docs/sprint-cycles'):
        current = root
        if not target.is_relative_to(root) or '..' in target.parts:
            raise ValueError('output outside worktree')
        for part in target.relative_to(root).parts:
            current /= part
            if current.is_symlink():
                raise ValueError('symlink output component rejected')
    private_directory(root, output_dir / 'iterations')
    private_directory(root, root / 'docs/sprint-cycles')
    # Existing private directories must not have broad permissions either.
    for path in (output_dir, output_dir / 'iterations'):
        os.chmod(path, 0o700)
    lockpath = output_dir / '.lock'
    descriptor = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another sprint invocation holds the lock') from None
        history = sorted((output_dir / 'iterations').glob('*.json'))
        sequence, attempted = 0, set()
        for path in history:
            if path.is_symlink():
                raise ValueError('symlink checkpoint rejected')
            try:
                saved = json.loads(path.read_text())
                if (saved['schema'] != 1 or saved['sequence'] != sequence + 1 or
                        path.name != f'{sequence + 1:06d}.json' or
                        len(saved['issues']) != 8 or
                        {i['issue'] for i in saved['issues']} != set(range(1, 9)) or
                        any(i['state'] not in STATES for i in saved['issues'])):
                    raise ValueError('invalid checkpoint structure')
                sequence += 1
                attempted.update(saved['action_keys'])
            except (KeyError, TypeError, ValueError):
                raise ValueError('invalid checkpoint; preserve and inspect private evidence') from None
            # Recover a missing public summary after interruption, without replacing it.
            report = root / 'docs/sprint-cycles' / f'iteration-{sequence:06d}.md'
            if report.is_symlink():
                raise ValueError('symlink report rejected')
            if not report.exists():
                atomic_write(report, public_report(saved))
        hashes = {}
        for key, name in [('spec_sha256', 'docs/superpowers/specs/2026-11-01-sprint-cycle.md'),
                          ('gate_sha256', 'docs/sprint-2026-11-01-upstream-solutions-review.md')]:
            hashes[key] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        invocation_actions, previous, pending = set(), None, []
        for round_number in range(1, max_rounds + 1):
            checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for name, key in pending:
                # No general executor; only the two synthetic decode diagnostics.
                command(name)
                attempted.add(key)
                invocation_actions.add(name)
            facts = safe_facts(collector())
            issues = evaluate(facts)
            for item in issues:
                item['checked_at'] = checked_at
                item['evidence'] = [f'iteration:{sequence + 1}:facts']
            fingerprint = hashlib.sha256(json.dumps(
                {'facts': facts, 'states': [i['state'] for i in issues]}, sort_keys=True).encode()).hexdigest()
            pending = []
            for item in issues:
                for name in item['safe_actions']:
                    if name not in ('decode_stateful', 'decode_stateless'):
                        raise ValueError('unsafe pending action rejected')
                    key = name + ':' + fingerprint
                    if key not in attempted:
                        pending.append((name, key))
            if once:
                stop = 'once'
            elif all(i['state'] in {'VERIFIED', 'BLOCKED_USER', 'BLOCKED_PHYSICAL',
                      'BLOCKED_UPSTREAM', 'WAITING_RELEASE', 'NOT_PLANNED'} for i in issues):
                stop = 'external_actions_only'
            elif previous == fingerprint or not pending:
                stop = 'no_progress'
            elif round_number == max_rounds:
                stop = 'max_rounds'
            else:
                stop = 'continue_safe_work'
            sequence += 1
            data = dict(schema=1, sequence=sequence, checked_at=checked_at, stages=STAGES,
                        facts=facts, issues=issues, fingerprint=fingerprint, stop_reason=stop,
                        action_keys=sorted(attempted), pending_actions=[n for n, _ in pending],
                        upstream_refreshed=False, **hashes)
            boot = read_text('/proc/sys/kernel/random/boot_id')
            if boot and re.fullmatch(r'[a-f0-9-]{36}\s*', boot):
                data['boot_id'] = boot.strip()  # strictly private
            snapshot = output_dir / 'iterations' / f'{sequence:06d}.json'
            report = root / 'docs/sprint-cycles' / f'iteration-{sequence:06d}.md'
            if snapshot.exists() or report.exists():
                raise ValueError('iteration destination exists; refusing to overwrite')
            atomic_write(snapshot, json.dumps(data, indent=2, sort_keys=True) + '\n')
            atomic_write(report, public_report(data))
            if stop != 'continue_safe_work':
                return {'rounds': round_number, 'last_sequence': sequence,
                        'stop_reason': stop, 'states': {i['issue']: i['state'] for i in issues},
                        'actions_attempted': sorted(invocation_actions)}
            previous = fingerprint
    finally:
        os.close(descriptor)


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--run', action='store_true', help='repeat safe rounds to convergence')
    modes.add_argument('--once', action='store_true', help='perform exactly one full round')
    parser.add_argument('--max-rounds', type=int, choices=range(1, 7), default=6)
    parser.add_argument('--output-dir', type=Path, default=Path('.local/sprint-cycles'))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    destination = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    try:
        result = run(root, destination, args.max_rounds, args.once or not args.run)
    except (ValueError, OSError):
        print('Sprint stopped: invalid destination/checkpoint, lock conflict, or I/O failure; inspect private evidence locally.')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
