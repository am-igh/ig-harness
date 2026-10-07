#!/bin/sh
# Creates the search engine's settings on first use (kept in ~/IG-Harness-data/searxng, outside the repo, because it holds a random secret key).
set -e
DIR="$HOME/IG-Harness-data/searxng"
mkdir -p "$DIR"
if [ ! -f "$DIR/settings.yml" ]; then
  KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$DIR/settings.yml" <<YML
use_default_settings: true
general:
  instance_name: "IG Harness search"
  enable_metrics: false
search:
  safe_search: 0
  formats: [html, json]
server:
  secret_key: "$KEY"
  limiter: false
  image_proxy: false
  bind_address: "0.0.0.0"
  port: 8080
outgoing:
  request_timeout: 6.0
YML
  chmod 600 "$DIR/settings.yml"
  echo "Search engine settings created in $DIR."
fi
