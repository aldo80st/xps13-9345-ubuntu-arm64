#!/usr/bin/env python3
"""Read-only, offline research snapshot validator. Never authorizes a candidate."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT = Path(__file__).resolve().parents[1] / 'docs/hibernate-upstream-reuse-manifest.json'
IDS = {'pdc_restore', 'clock_restore', 'pcie_freeze', 'pcie_shutdown',
       'smp2p_restore', 'remoteproc_lifecycle', 'uart_restore', 'bluetooth_ibs',
       'pinctrl_restore', 'dell_ec', 'ubuntu_concept'}
GATES = {'pdc_restore': 'unresolved', 'clock_restore': 'unresolved',
         'ppa_hibernation': 'disabled', 'pcie_reconciliation': 'unresolved',
         'remoteproc_lifecycle': 'unresolved', 'dell_validation': 'unverified'}
FIELDS = {'id', 'title', 'publication', 'accepted', 'mainline', 'ubuntu_inclusion',
          'commit', 'decision', 'dell_restore', 'sources', 'access', 'notes'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def validate(data):
    errors = []
    if not isinstance(data, dict) or set(data) != {
            'schema_version', 'evidence_date', 'scope', 'components', 'ppa', 'gates'}:
        return ['invalid manifest fields']
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        errors.append('unsupported schema_version')
    if data['evidence_date'] != '2026-11-07' or data['scope'] != 'offline_review_only':
        errors.append('unsupported snapshot date or scope')
    if data['gates'] != GATES:
        errors.append('locked research gates changed; new review required')
    ppa = data['ppa']
    expected_ppa = {'package': 'linux-qcom-x1e', 'version': '7.3.0-31',
                    'machine': 'Dell XPS 13 9345', 'hibernation': 'disabled',
                    'config_line': '# CONFIG_HIBERNATION is not set',
                    'provenance': 'user_reported_xps_verified'}
    if not isinstance(ppa, dict) or set(ppa) != set(expected_ppa) | {'notes'}:
        errors.append('invalid PPA evidence fields')
    elif any(ppa[k] != v for k, v in expected_ppa.items()) or not isinstance(ppa['notes'], str) or not ppa['notes'].strip():
        errors.append('PPA snapshot changed or lacks provenance')
    components = data['components']
    if not isinstance(components, list):
        return errors + ['components must be a list']
    seen = []
    for item in components:
        if not isinstance(item, dict) or set(item) != FIELDS:
            errors.append('invalid component fields')
            continue
        ident = item['id']
        if not isinstance(ident, str) or ident not in IDS:
            errors.append('unexpected component ID')
            continue
        seen.append(ident)
        allowed_publication = 'unknown' if ident == 'remoteproc_lifecycle' else (
            'not_applicable' if ident == 'ubuntu_concept' else 'proposed')
        expected_accepted = 'accepted' if ident == 'pinctrl_restore' else 'unknown'
        # This version records a fixed review, not a user-editable admission path.
        if (item['publication'] != allowed_publication or item['accepted'] != expected_accepted
                or item['mainline'] != 'unknown' or item['ubuntu_inclusion'] != 'unknown'
                or item['dell_restore'] != 'unknown' or item['commit'] is not None):
            errors.append(ident + ': unsupported status/commit claim')
        decision = ('reuse_packaging' if ident == 'ubuntu_concept' else
                    'reuse_after_review' if ident in {'dell_ec', 'pinctrl_restore'} else 'defer')
        if item['decision'] != decision:
            errors.append(ident + ': unsupported reuse decision')
        if item['access'] not in ('live_primary', 'indexed_primary', 'carried_local'):
            errors.append(ident + ': invalid access classification')
        for field in ('title', 'notes'):
            if not isinstance(item[field], str) or not item[field].strip():
                errors.append(ident + ': missing ' + field)
        sources = item['sources']
        if not isinstance(sources, list) or not sources:
            errors.append(ident + ': missing sources')
        else:
            for source in sources:
                try:
                    url = urlsplit(source) if isinstance(source, str) else None
                    valid = (url and url.scheme == 'https' and url.hostname
                             and not url.username and not url.password
                             and not any(c.isspace() for c in source))
                except ValueError:
                    valid = False
                if not valid:
                    errors.append(ident + ': invalid HTTPS source')
    if len(seen) != len(IDS) or set(seen) != IDS:
        errors.append('missing or duplicate component IDs')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT)
    parser.add_argument('--json', action='store_true', help='emit machine-readable report')
    args = parser.parse_args()
    try:
        with args.manifest.open(encoding='utf-8') as stream:
            data = json.load(stream, object_pairs_hook=unique_object)
        errors = validate(data)
    except (OSError, ValueError, RecursionError) as exc:
        errors = ['manifest unreadable or invalid: ' + type(exc).__name__]
    result = {'verdict': 'NO_GO', 'admitted': False, 'errors': errors,
              'blockers': list(GATES) + ['review_lock']}
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print('NO_GO: offline review only')
        for entry in result['blockers'] + errors:
            print('- ' + entry)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
