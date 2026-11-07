#!/usr/bin/env python3
"""Offline H1 lifecycle admission gate: this revision never admits a candidate."""
import argparse
import json
from pathlib import Path

REQUIREMENTS = (
    'exact_ubuntu_base_and_ordered_patch_hashes',
    'dell_remoteproc_dt_firmware_inventory',
    'freeze_poweroff_restore_lifecycle_and_ordering',
    'balanced_refs_subdevices_and_failure_unwind',
    'smp2p_restore_and_pas_state_reconciliation',
    'dell_powercycle_thaw_test_resume_and_regressions',
)
DEFAULT = Path(__file__).resolve().parents[1] / 'docs/hibernate-remoteproc-h1.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=DEFAULT)
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
    print(json.dumps({'verdict': 'NO_GO', 'admitted': False, 'errors': errors,
                      'blockers': list(REQUIREMENTS)}))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
