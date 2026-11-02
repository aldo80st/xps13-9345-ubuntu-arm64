#!/usr/bin/env bash
# Purely observational MOK/Kernel trusted keyring inventory on ARM64.
# It does NOT import keys, set EFI variables, load modules or touch boot configuration.
set -euo pipefail
if [ "$(id -u)" != "0" ]; then
  printf '%s\n' 'ERROR=ADMINISTRATOR_AUTHORIZATION_REQUIRED'
  exit 77
fi
if [ "$(uname -m)" != "aarch64" ]; then
  printf '%s\n' 'ERROR=NOT_ARM64'
  exit 2
fi
/usr/bin/python3 - <<'PY'
import json
import re
import struct
import subprocess
from pathlib import Path

def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 255, ''

def get_field(name):
    code, txt = run(['/usr/sbin/modinfo', '-F', name, 'evdi'])
    return txt if code == 0 else ''

signer = get_field('signer')
_, cert_subject = run(['/usr/bin/openssl', 'x509', '-inform', 'DER', '-in',
                       '/var/lib/shim-signed/mok/MOK.der', '-noout', '-subject', '-nameopt', 'RFC2253'])
cn_match = re.search(r'CN=([^,]+)', cert_subject)
cn = cn_match.group(1).replace('\\,', ',').strip() if cn_match else ''
try:
    text = Path('/proc/keys').read_text()
except OSError:
    text = ''
rows = text.splitlines()
asymmetric = [row for row in rows if 'asymmetric:' in row]
rings = ['.machine', '.platform', '.secondary_trusted_keys', '.builtin_trusted_keys']
keyctl = '/usr/bin/keyctl' if Path('/usr/bin/keyctl').is_file() else ''
# Never run a user-writable keyctl binary with elevated privileges.
_, module_key_id = run(['/usr/sbin/modinfo', '-F', 'sig_key', 'evdi'])
_, ski_extension = run(['/usr/bin/openssl', 'x509', '-inform', 'DER', '-in',
                       '/var/lib/shim-signed/mok/MOK.der', '-noout', '-ext',
                       'subjectKeyIdentifier'])
ski_line = ski_extension.splitlines()[-1] if ski_extension else ''
cert_ski = ''.join(re.findall(r'[a-fA-F0-9]{2}', ski_line))
module_key_id = ''.join(re.findall(r'[a-fA-F0-9]{2}', module_key_id))
# Parse only public certificate signatures from the read-only shim MOK EFI table.
mok_table = {'available': False, 'length_bytes': None, 'certificate_count': 0,
             'local_cert_present': False, 'module_key_id_matches_any_mok_ski': False}
try:
    table = Path('/sys/firmware/efi/mok-variables/MokListRT').read_bytes()
    enrolled = Path('/var/lib/shim-signed/mok/MOK.der').read_bytes()
    mok_table['available'] = True
    mok_table['length_bytes'] = len(table)
    mok_table['local_cert_present'] = enrolled in table
    offset = 0
    while offset + 28 <= len(table):
        _, block_size, header_size, entry_size = struct.unpack_from('<16sIII', table, offset)
        if block_size < 28 or block_size > len(table) - offset or entry_size < 16:
            break
        payload_size = block_size - 28 - header_size
        if payload_size < 0 or payload_size % entry_size:
            break
        start = offset + 28 + header_size
        for n in range(payload_size // entry_size):
            signature = table[start + n * entry_size + 16: start + (n + 1) * entry_size]
            mok_table['certificate_count'] += 1
            result = subprocess.run(
                ['/usr/bin/openssl', 'x509', '-inform', 'DER', '-noout',
                 '-ext', 'subjectKeyIdentifier'], input=signature,
                 capture_output=True, timeout=5)
            if result.returncode == 0 and module_key_id:
                last = result.stdout.decode('utf-8', 'replace').splitlines()[-1]
                signature_ski = ''.join(re.findall(r'[a-fA-F0-9]{2}', last))
                if signature_ski.lower() == module_key_id.lower():
                    mok_table['module_key_id_matches_any_mok_ski'] = True
        offset += block_size
except (OSError, ValueError, struct.error, subprocess.TimeoutExpired):
    pass
access = {}
for ring in rings:
    visible = any(re.search(r'keyring:\s+' + re.escape(ring) + r'(?:\s|$)', row) for row in rows)
    if keyctl:
        code, output = run([keyctl, 'show', '%:' + ring])
    else:
        code, output = (255, '')
    access[ring] = {'ring_visible_in_proc_keys': visible, 'keyctl_readable': code == 0,
                    'keyctl_exit': code}

def normalize(s):
    return re.sub('[^a-z0-9]', '', s.lower())
norm_signer, norm_cn = normalize(signer), normalize(cn)
result = {
    'schema': 1,
    'operation': 'read-only kernel trust inspection',
    'secureboot_kernel_flag': 'not_collected',
    'proc_keys_readable': bool(text),
    'proc_keys_total_rows': len(rows),
    'asymmetric_keys_visible_to_proc_reader': len(asymmetric),
    'key_visibility_is_conclusive': False,
    'module_signer_name_matches_mok_cert_cn': bool(norm_cn and norm_signer and norm_cn == norm_signer),
    'module_key_identifier_matches_mok_ski': bool(module_key_id and cert_ski and
                                                 module_key_id.lower() == cert_ski.lower()),
    'keyctl_available': bool(keyctl),
    'mok_table': mok_table,
    'module_signer_visible_as_asymmetric_key': bool(norm_signer and any(norm_signer in normalize(row) for row in asymmetric)),
    'keyrings': access,
    'efi_noruntime_present': 'efi=noruntime' in Path('/proc/cmdline').read_text().split(),
}
print(json.dumps(result, indent=2, sort_keys=True))
PY