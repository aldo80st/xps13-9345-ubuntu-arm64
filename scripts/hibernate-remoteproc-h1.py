#!/usr/bin/env python3
"""Offline H1 lifecycle admission gate: this revision never admits a candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

REQUIREMENTS = (
    'exact_ubuntu_base_and_ordered_patch_hashes',
    'dell_remoteproc_dt_firmware_inventory',
    'freeze_poweroff_restore_lifecycle_and_ordering',
    'balanced_refs_subdevices_and_failure_unwind',
    'smp2p_restore_and_pas_state_reconciliation',
    'dell_powercycle_thaw_test_resume_and_regressions',
)
DEFAULT = Path(__file__).resolve().parents[1] / 'docs/hibernate-remoteproc-h1.json'
SOURCE_FILES = {
    'drivers/soc/qcom/smp2p.c': (
        'qcom_smp2p_probe', 'qcom_smp2p_alloc_outbound_item',
        'qcom_smp2p_start_in', 'qcom_smp2p_check_ssr'),
    'drivers/remoteproc/qcom_q6v5_pas.c': ('qcom_pas_probe', 'qcom_pas_stop'),
    'drivers/remoteproc/remoteproc_core.c': (
        'rproc_start', 'rproc_boot', '__rproc_shutdown', 'rproc_stop'),
}
MAX_SOURCE_BYTES = 4 * 1024 * 1024
PM_HOOKS = ('prepare', 'complete', 'suspend', 'suspend_late', 'suspend_noirq',
            'resume_noirq', 'resume_early', 'resume',
            'freeze', 'freeze_late', 'freeze_noirq',
            'thaw_noirq', 'thaw_early', 'thaw',
            'poweroff', 'poweroff_late', 'poweroff_noirq',
            'restore_noirq', 'restore_early', 'restore',
            'runtime_suspend', 'runtime_resume', 'runtime_idle')


def read_source(root, relative):
    """Open fixed paths through directory fds; never follow source symlinks."""
    parts = Path(relative).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        source_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=fd)
        with os.fdopen(source_fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES:
                raise ValueError('source must be a bounded regular file')
            raw = stream.read(MAX_SOURCE_BYTES + 1)
            if len(raw) > MAX_SOURCE_BYTES:
                raise ValueError('source exceeds size limit')
            return raw
    finally:
        os.close(fd)


def c_text(raw):
    """Mask comments/literals after line splicing. Not a C parser."""
    text = raw.decode('utf-8')
    # C line splicing happens before comment recognition.
    text = re.sub(r'\\\r?\n', '', text)
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                       re.S)
    clean = token.sub(lambda m: re.sub(r'[^\n]', ' ', m.group()), text)
    if '/*' in clean or '"' in clean or "'" in clean or '\x00' in clean:
        raise ValueError('unrecognized C text')
    # Do not mistake macro definitions for actual definitions or assignments.
    return re.sub(r'^\s*#[^\n]*', '', clean, flags=re.M), bool(
        re.search(r'^\s*#\s*(?:if|ifdef|ifndef|elif|else)\b', clean, re.M))


def braced(text, opening):
    depth = 0
    for pos in range(opening, len(text)):
        if text[pos] == '{':
            depth += 1
        elif text[pos] == '}':
            depth -= 1
            if depth == 0:
                return text[opening + 1:pos]
    raise ValueError('unbalanced source braces')


def definitions(text, name):
    pattern = (r'^\s*(?:static\s+)?(?:inline\s+)?(?:int|void|bool)\s+'
               + re.escape(name) + r'\s*\(([^;{}]*)\)\s*\{')
    return [(m.group(1), braced(text, m.end() - 1))
            for m in re.finditer(pattern, text, re.M)]


def initializer(text, kind, name):
    matches = list(re.finditer(r'\bstruct\s+' + kind + r'\s+' + name
                               + r'\s*=\s*\{', text))
    return braced(text, matches[0].end() - 1) if len(matches) == 1 else None


def members(body):
    """Recognize explicit designated fields; reject macro/positional forms."""
    fields = {}
    start = depth = 0
    for pos, char in enumerate(body + ','):
        if char in '({[':
            depth += 1
        elif char in ')}]':
            depth -= 1
        elif char == ',' and depth == 0:
            part = body[start:pos].strip()
            start = pos + 1
            if not part:
                continue
            match = re.fullmatch(r'\.(\w+)\s*=\s*(.*)', part, re.S)
            if not match or match[1] in fields:
                return None
            fields[match[1]] = match[2].strip()
    return fields if depth == 0 else None


def driver_pm(text, name):
    body = initializer(text, 'platform_driver', name)
    fields = members(body) if body is not None else None
    driver = fields.get('driver', '') if fields is not None else ''
    if not driver.startswith('{') or not driver.endswith('}'):
        return 'unknown', None
    fields = members(driver[1:-1])
    if fields is None:
        return 'unknown', None
    return ('present', fields['pm']) if 'pm' in fields else ('absent', None)


def pm_hooks(text, status, binding):
    if status == 'absent':
        return {hook: 'not_registered' for hook in PM_HOOKS}
    match = re.fullmatch(r'&\s*([A-Za-z_]\w*)', binding or '')
    body = initializer(text, 'dev_pm_ops', match[1]) if match else None
    fields = members(body) if body is not None else None
    return {hook: fields.get(hook, 'absent') if fields is not None else 'unknown'
            for hook in PM_HOOKS}


def restore_shape(text):
    found = definitions(text, 'qcom_smp2p_restore_noirq')
    if not found:
        return 'missing'
    if len(found) != 1 or not re.fullmatch(r'\s*struct\s+device\s*\*\s*dev\s*', found[0][0]):
        return 'unrecognized'
    if not re.search(r'^\s*static\s+int\s+qcom_smp2p_restore_noirq\s*\(', text, re.M):
        return 'unrecognized'
    status, binding = driver_pm(text, 'qcom_smp2p_driver')
    ops = initializer(text, 'dev_pm_ops', 'qcom_smp2p_pm_ops')
    fields = members(ops) if ops is not None else None
    if (status != 'present' or binding != '&qcom_smp2p_pm_ops' or fields is None
            or fields.get('restore_noirq') != 'pm_sleep_ptr(qcom_smp2p_restore_noirq)'):
        return 'unrecognized'
    # Ordered lexical anchors from the Oct 9 proposal, NOT semantic validation.
    body = re.sub(r'\s+', '', found[0][1])
    anchors = (
        'smp2p=dev_get_drvdata(dev);', 'smp2p->in=NULL;',
        'smp2p->valid_entries=0;', 'smp2p->negotiation_done=false;',
        'smp2p->ssr_ack_enabled=false;', 'smp2p->ssr_ack=false;',
        'list_for_each_entry(entry,&smp2p->inbound,node){',
        'entry->value=NULL;', 'entry->last_value=0;', '}',
        'ret=qcom_smp2p_alloc_outbound_item(smp2p);', 'if(ret<0)returnret;',
        'list_for_each_entry_reverse(entry,&smp2p->outbound,node)',
        'qcom_smp2p_claim_outbound_entry(smp2p,entry);',
        'qcom_smp2p_start_in(smp2p);', 'qcom_smp2p_kick(smp2p);', 'return0;',
    )
    cursor = 0
    for anchor in anchors:
        pos = body.find(anchor, cursor)
        if pos < 0:
            return 'unrecognized'
        cursor = pos + len(anchor)
    if len(definitions(text, 'qcom_smp2p_claim_outbound_entry')) != 1:
        return 'unrecognized'
    return 'expected_shape'


def inspect_source(root):
    report = {'schema_version': 1, 'scope': 'file_local_lexical_only',
              'files': {}, 'smp2p_restore': 'unknown', 'pas_driver_pm': 'unknown',
              'pas_pm_hooks': {hook: 'unknown' for hook in PM_HOOKS},
              'reason_codes': []}
    reasons = report['reason_codes']
    for relative, expected in SOURCE_FILES.items():
        record = {'sha256': None, 'missing_definitions': [], 'definitions': {},
                  'status': 'unknown'}
        report['files'][relative] = record
        try:
            raw = read_source(root, relative)
            record['sha256'] = hashlib.sha256(raw).hexdigest()
            text, conditional = c_text(raw)
            if conditional:
                reasons.append('PREPROCESSOR_NOT_EVALUATED')
            for name in expected:
                found = definitions(text, name)
                record['definitions'][name] = [re.sub(r'\s+', ' ', params).strip()
                                                for params, _ in found]
                if len(found) != 1:
                    record['missing_definitions'].append(name)
            if record['missing_definitions']:
                reasons.append('EXPECTED_API_MISSING')
            if relative.endswith('/smp2p.c'):
                report['smp2p_restore'] = restore_shape(text)
                reasons.append({'missing': 'SMP2P_RESTORE_MISSING',
                                'unrecognized': 'SMP2P_RESTORE_UNRECOGNIZED',
                                'expected_shape': 'SMP2P_RESTORE_SHAPE_OBSERVED'}[
                                    report['smp2p_restore']])
            elif relative.endswith('/qcom_q6v5_pas.c'):
                status, binding = driver_pm(text, 'qcom_pas_driver')
                report['pas_driver_pm'] = status
                report['pas_pm_hooks'] = pm_hooks(text, status, binding)
                record['pm_binding'] = binding
                reasons.append('PAS_DRIVER_PM_' + status.upper())
            record['status'] = 'observed'
        except (OSError, ValueError, RecursionError):
            reasons.append('SOURCE_INPUT_UNREADABLE')
    reasons.extend(('PAS_LIFECYCLE_UNRECONCILED',
                    'C7_REMOTEPROC_SMP2P_EQUIVALENCE_UNPROVEN',
                    'SOURCE_PROVENANCE_UNVERIFIED', 'DELL_RUNTIME_UNVERIFIED'))
    report['reason_codes'] = sorted(set(reasons))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=DEFAULT)
    parser.add_argument('--source-tree', type=Path,
                        help='read three fixed source paths; never admits or executes tree content')
    args = parser.parse_args()
    errors = []
    try:
        data = json.loads(args.contract.read_text(encoding='utf-8'))
        expected = {'schema_version': 1, 'verdict': 'NO_GO', 'dell_verified': False,
                    'requirements': {key: 'UNKNOWN' for key in REQUIREMENTS}}
        # Exact shape prevents ignored evidence, dropped requirements and invented approval.
        if not isinstance(data, dict) or data != expected:
            errors.append('contract must retain the complete locked UNKNOWN lifecycle record')
        elif type(data['schema_version']) is not int or data['dell_verified'] is not False:
            errors.append('contract field types are invalid')
    except (OSError, ValueError, RecursionError):
        errors.append('contract cannot be read as a JSON lifecycle record')
    result = {'verdict': 'NO_GO', 'admitted': False, 'errors': errors,
              'blockers': list(REQUIREMENTS)}
    if args.source_tree is not None:
        result['source_report'] = inspect_source(args.source_tree)
    print(json.dumps(result))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
