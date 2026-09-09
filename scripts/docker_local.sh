#!/usr/bin/env sh
# Bu makinede kurulan bağımsız Colima profili; kullanıcının Docker context'i değişmez.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_docker_config="$task_root/.local/docker-client"
mkdir -p "$task_docker_config"
if [ ! -f "$task_docker_config/config.json" ]; then
  printf '%s\n' '{"auths": {}}' > "$task_docker_config/config.json"
fi
export DOCKER_CONFIG="$task_docker_config"
export DOCKER_HOST="unix://$HOME/.colima/tenantfiles/docker.sock"
exec docker "$@"
