#!/usr/bin/env bash
# Ejecuta dos veces el mismo playbook y conserva ambas salidas.
set -euo pipefail
cd "$(dirname "$0")/.."
export ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-$PWD/ansible/ansible.cfg}"
PLAYBOOK="${ANSIBLE_PLAYBOOK:-ansible-playbook}"
mkdir -p evidencias/h12
"$PLAYBOOK" ansible/site.yml 2>&1 | tee evidencias/h12/01-primera-ejecucion.txt
"$PLAYBOOK" ansible/site.yml 2>&1 | tee evidencias/h12/02-segunda-ejecucion.txt
python3 - <<'PY'
import re
from pathlib import Path
out = Path('evidencias/h12')
runs = []
for name in ('01-primera-ejecucion.txt', '02-segunda-ejecucion.txt'):
    text = (out / name).read_text(encoding='utf-8')
    recaps = re.findall(r'^localhost\s*:\s*(ok=.*)$', text, re.M)
    if not recaps:
        raise SystemExit(f'No se encontro recap en {name}')
    runs.append(recaps[-1])
if not re.search(r'changed=0\s', runs[1]):
    raise SystemExit(f'La segunda corrida no fue idempotente: {runs[1]}')
(out / 'resumen.txt').write_text(
    'H12 - idempotencia comprobada\n'
    f'Primera ejecucion: {runs[0]}\n'
    f'Segunda ejecucion: {runs[1]}\n', encoding='utf-8')
print('Idempotencia comprobada: changed=0 en la segunda ejecucion.')
PY
