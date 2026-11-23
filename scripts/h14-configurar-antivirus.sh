#!/bin/sh
# H14: conecta Nextcloud (app files_antivirus) con el demonio ClamAV del compose.
# Uso, con el stack arriba:  sh scripts/h14-configurar-antivirus.sh
set -eu
NC=${NC_CONTAINER:-nexo-nextcloud}
occ() { docker exec -u www-data "$NC" php occ "$@"; }

occ app:install files_antivirus >/dev/null 2>&1 || occ app:enable files_antivirus
occ config:app:set files_antivirus av_mode --value=daemon
occ config:app:set files_antivirus av_host --value=clamav
occ config:app:set files_antivirus av_port --value=3310
occ config:app:set files_antivirus av_stream_max_length --value=26214400
# delete: el archivo infectado se elimina; "only_log" solo registra.
occ config:app:set files_antivirus av_infected_action --value=delete
occ config:app:get files_antivirus av_host
