#!/usr/bin/env bash
# Validate production prerequisites without printing the values in the secret file.
set -euo pipefail

env_file="${1:-deploy/.env.production}"
compose_file="docker-compose.production.yml"

fail() {
  printf 'Preflight failed: %s\n' "$1" >&2
  exit 1
}

[[ -f "$env_file" ]] || fail "Missing $env_file. Copy deploy/.env.production.example first."
[[ -f "$compose_file" ]] || fail "Run this script from the repository root."
command -v docker >/dev/null || fail "Docker Engine and Docker Compose v2 are required."

if grep -Eq '(^|=)(replace-with|.*example\.com)' "$env_file"; then
  fail "Replace all template placeholders and example domains in $env_file."
fi

permissions=$(stat -c '%a' "$env_file" 2>/dev/null || true)
if [[ -n "$permissions" && "$permissions" != "600" ]]; then
  fail "$env_file must be owner-readable only. Run: chmod 600 $env_file"
fi

app_domain=$(awk -F= '$1 == "APP_DOMAIN" { print $2; exit }' "$env_file")
s3_domain=$(awk -F= '$1 == "S3_PUBLIC_DOMAIN" { print $2; exit }' "$env_file")
[[ -n "$app_domain" && -n "$s3_domain" ]] || fail "APP_DOMAIN and S3_PUBLIC_DOMAIN are required."

for domain in "$app_domain" "$s3_domain"; do
  getent ahosts "$domain" >/dev/null || fail "DNS does not resolve for $domain."
done

docker compose --env-file "$env_file" -f "$compose_file" config --quiet
printf 'Preflight passed. DNS resolves and the Compose configuration is valid.\n'
