#!/bin/sh
set -eu
: "${NEXO_URL:?}" "${KC_SYNAPSE_CLIENT_SECRET:?}"
cat "$(python -c 'import certifi; print(certifi.where())')" /certs/server.crt > /data/nexo-ca-bundle.pem
# Solo se sustituyen variables conocidas: las llaves de Jinja de Synapse quedan intactas.
export NEXO_URL KC_SYNAPSE_CLIENT_SECRET
python - <<'PY'
import os
from pathlib import Path
text = Path('/template/homeserver.yaml').read_text(encoding='utf-8')
for key in ('NEXO_URL', 'KC_SYNAPSE_CLIENT_SECRET'):
    text = text.replace('${' + key + '}', os.environ[key])
Path('/data/homeserver.yaml').write_text(text, encoding='utf-8')
PY
# /start.py baja privilegios al UID/GID 991 antes de crear claves y SQLite.
chown -R 991:991 /data
exec /start.py
