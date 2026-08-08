#!/usr/bin/env bash
# Print everything ALAFIA owns in Google Cloud, with console links.
#
#   scripts/gcp/inventory.sh
#
# Read-only. Answers "what exists, in which project, and where do I click to
# edit it" — including which project holds the DNS zone, which is not obvious
# because a domain's registrar and its DNS host are usually different places.

set -uo pipefail
GC="${GCLOUD:-$HOME/google-cloud-sdk/bin/gcloud}"
command -v "$GC" >/dev/null 2>&1 || GC=gcloud
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

PROJECT="${PROJECT_ID:-alafia-prod-6igma}"
REGION="${REGION:-us-east4}"

hdr() { printf '\n\033[1;36m── %s\033[0m\n' "$*"; }
row() { printf '  %-22s %s\n' "$1" "$2"; }

if ! "$GC" projects describe "$PROJECT" >/dev/null 2>&1; then
  printf '\033[1;31mNot authenticated (or no access to %s).\033[0m\n' "$PROJECT"
  printf 'Run:  %s auth login\n      %s auth application-default login\n' "$GC" "$GC"
  exit 1
fi

NUM=$("$GC" projects describe "$PROJECT" --format='value(projectNumber)' 2>/dev/null)

hdr "PROJECT"
row "id"            "$PROJECT"
row "number"        "$NUM"
row "default region" "$REGION"
row "console"       "https://console.cloud.google.com/home/dashboard?project=$PROJECT"

hdr "ALL PROJECTS THIS ACCOUNT CAN SEE"
"$GC" projects list --format='value(projectId,name)' 2>/dev/null | sed 's/^/  /'

hdr "CLOUD RUN SERVICES  (console: https://console.cloud.google.com/run?project=$PROJECT)"
"$GC" run services list --region "$REGION" --project "$PROJECT" \
  --format='table[no-heading](metadata.name, status.latestReadyRevisionName, status.url)' 2>/dev/null \
  | sed 's/^/  /'

hdr "CUSTOM DOMAIN MAPPINGS  (Cloud Run → domain)"
MAP=$("$GC" beta run domain-mappings list --region "$REGION" --project "$PROJECT" \
      --format='value(metadata.name,spec.routeName)' 2>/dev/null)
[ -n "$MAP" ] && echo "$MAP" | sed 's/^/  /' || echo "  (none in $REGION)"

hdr "DNS — WHERE THE RECORDS ACTUALLY LIVE"
FOUND=0
for p in $("$GC" projects list --format='value(projectId)' 2>/dev/null); do
  Z=$("$GC" dns managed-zones list --project="$p" \
      --format='value(name,dnsName,visibility)' 2>/dev/null)
  if [ -n "$Z" ]; then
    FOUND=1
    echo "  project: $p"
    echo "$Z" | sed 's/^/    zone: /'
    echo "    console: https://console.cloud.google.com/net-services/dns/zones?project=$p"
  fi
done
[ "$FOUND" -eq 0 ] && cat <<'EOS'
  No Cloud DNS zone in any project this account can see.
  That means DNS is hosted OUTSIDE Google Cloud. Check the nameservers to find
  the real host — registrar and DNS host are usually different companies:
      dig +short NS alafia.app
      dig +short NS alafia.com
  ns-cloud-*.googledomains.com  → Google Cloud DNS (find the owning project)
  dns*.registrar-servers.com    → Namecheap dashboard
  *.domaincontrol.com           → GoDaddy dashboard
EOS

hdr "LIVE NAMESERVERS (authoritative answer, independent of any console)"
for d in alafia.app alafia.com; do
  row "$d" "$(dig +short NS "$d" 2>/dev/null | tr '\n' ' ')"
done

hdr "CLOUD SQL  (console: https://console.cloud.google.com/sql/instances?project=$PROJECT)"
"$GC" sql instances list --project "$PROJECT" \
  --format='table[no-heading](name, databaseVersion, region, settings.tier, state)' 2>/dev/null \
  | sed 's/^/  /'

hdr "SECRETS  (names only — console: https://console.cloud.google.com/security/secret-manager?project=$PROJECT)"
"$GC" secrets list --project "$PROJECT" --format='value(name)' 2>/dev/null | sed 's/^/  /'

hdr "ARTIFACT REGISTRY  (container images)"
"$GC" artifacts repositories list --project "$PROJECT" \
  --format='table[no-heading](name, format, location)' 2>/dev/null | sed 's/^/  /'

hdr "DEPLOYED COMMIT (GIT_SHA baked into the backend)"
SHA=$("$GC" run services describe alafia-backend --region "$REGION" --project "$PROJECT" \
      --format='value(spec.template.spec.containers[0].env)' 2>/dev/null \
      | tr ';' '\n' | grep -i GIT_SHA | grep -oE '[0-9a-f]{40}' | head -1)
row "prod GIT_SHA" "${SHA:-<unset>}"
row "local HEAD"   "$(git -C "$(dirname "${BASH_SOURCE[0]}")/../.." rev-parse HEAD 2>/dev/null)"

printf '\n'
