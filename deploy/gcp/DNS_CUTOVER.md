# `alafia.app` → ALAFIA production (Cloud Run) — DNS cutover record

**Date:** 2026-07-28 · **Operator account:** `dew@6igma.com` · **GCP project:** `alafia-prod-6igma`

## What this did

Made the **LAFIAKALO Cloud Run stack** (Vite SPA `alafia-frontend` + FastAPI
`alafia-backend` + `alafia-identity`) authoritative at the **apex `alafia.app`**,
and added `www.alafia.app`. DNS was migrated from **GoDaddy** to **Google Cloud
DNS**. The pre-existing **Next.js site** (Firebase App Hosting) was **left
completely untouched** — only the apex A/AAAA were repointed away from it; it
remains reachable at its own App Hosting URL, and its email records were preserved.

## Final DNS (Cloud DNS zone `alafia-app`, DNSSEC = on)

| Name | Type | Value | Purpose |
|------|------|-------|---------|
| `alafia.app.` | A | `216.239.32.21`, `.34.21`, `.36.21`, `.38.21` | apex → Cloud Run (`alafia-frontend`) |
| `alafia.app.` | AAAA | `2001:4860:4802:{32,34,36,38}::15` | apex → Cloud Run (IPv6) |
| `www.alafia.app.` | CNAME | `ghs.googlehosted.com.` | www → Cloud Run (`alafia-frontend`) |
| `alafia.app.` | TXT | `v=spf1 include:_spf.firebasemail.com ~all` | email SPF (Next.js/Firebase) — preserved |
| `alafia.app.` | TXT | `firebase=alafia-9i0hh` | Firebase verify — preserved |
| `alafia.app.` | TXT | `google-site-verification=XKCL…RCHLk` | prior Search Console — preserved |
| `alafia.app.` | TXT | `google-site-verification=9-sq…WSc0` | Search Console owner for Cloud Run mapping |
| `alafia.app.` | TXT | `fah-claim=002-02-434c3f07-…` | Firebase App Hosting claim (Next.js) — preserved |
| `firebase1._domainkey` | CNAME | `mail-alafia-app.dkim1._domainkey.firebasemail.com.` | DKIM — preserved |
| `firebase2._domainkey` | CNAME | `mail-alafia-app.dkim2._domainkey.firebasemail.com.` | DKIM — preserved |

**Cloud DNS nameservers** (set at the GoDaddy registrar):
`ns-cloud-c1 / c2 / c3 / c4.googledomains.com`

**DNSSEC** `DS` at the registrar (`.app` registry): keytag **43422**, alg **13**
(ECDSAP256SHA256), digest type **2**,
`928616252A3C11029BB11282559579D84AF241E0A578D47B3ED2CC55BA35E220`.
(The old GoDaddy DS keytags 10216 / 5543 were removed.)

## Steps performed

1. **Cloud DNS zone** `alafia-app` created replicating the GoDaddy zone exactly →
   nameserver switch at GoDaddy was a zero-change cutover.
2. **DNSSEC re-signed:** moving to the (initially unsigned) Cloud DNS zone broke the
   chain (registry DS still fingerprinted GoDaddy keys → SERVFAIL on validating
   resolvers). Enabled DNSSEC on the zone (ECDSAP256SHA256) and replaced the DS at
   GoDaddy with keytag 43422. Now validates (`AD` flag).
3. **Domain verified** for `dew@6igma.com` via Search Console (TXT `9-sq…WSc0`).
   Subdomains (`www`) are covered by this apex domain-property verification.
4. **Cloud Run domain mappings** created: `alafia.app` and `www.alafia.app` →
   `alafia-frontend` (region `us-east4`). Apex A/AAAA flipped to Google anycast IPs;
   Google-managed TLS certs issued (Google Trust Services).
5. **Backend wired:** `alafia-backend` env `PUBLIC_WEB_URL=https://alafia.app`,
   `EHR_REDIRECT_URI=https://alafia.app/ehr/callback`,
   `CORS_ORIGINS=["https://alafia.app","https://www.alafia.app"]`.

## Managing DNS going forward

DNS is now in Cloud DNS (`gcloud dns ...`), **not** GoDaddy. GoDaddy only holds the
NS delegation + the DNSSEC `DS`.

```bash
export PATH="/Users/woleakpose/Developer/AgentBook/book_env/google-cloud-sdk/bin:$PATH"
gcloud config set project alafia-prod-6igma

# list records
gcloud dns record-sets list --zone=alafia-app

# add a subdomain that points at a Cloud Run service (e.g. api.alafia.app):
gcloud beta run domain-mappings create --service=<svc> --domain=api.alafia.app --region=us-east4
gcloud dns record-sets create api.alafia.app. --zone=alafia-app --type=CNAME --ttl=300 \
  --rrdatas="ghs.googlehosted.com."
```

**Never** re-delegate NS or touch the `DS` at GoDaddy without matching the Cloud DNS
zone's signing key — a DS/zone mismatch = SERVFAIL (the failure we hit in step 2).

## Rollback

To return the apex to the Next.js Firebase App Hosting site:
```bash
gcloud dns record-sets transaction start --zone=alafia-app
gcloud dns record-sets transaction remove --zone=alafia-app --name=alafia.app. --ttl=300 --type=A \
  216.239.32.21 216.239.34.21 216.239.36.21 216.239.38.21
gcloud dns record-sets transaction add --zone=alafia-app --name=alafia.app. --ttl=300 --type=A 35.219.200.6
# remove the AAAA set too, then execute
gcloud dns record-sets transaction execute --zone=alafia-app
```
(Low TTL = 300s, so rollback propagates in ~5 min.) Optionally delete the Cloud Run
domain mappings. The Next.js App Hosting backend was never modified.
