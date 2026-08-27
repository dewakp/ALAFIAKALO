#!/usr/bin/env python3
"""Verify in App Store Connect what App Review said was missing (guideline 2.1(b)).

Apple rejected 1.0 (2) with "In-app purchase products ... such as Membership,
could not be found in the submitted binary". The binary is fine — it asks
StoreKit for `alafia_plus_monthly` and `alafia_plus_annual`, and the backend
verifies those same two ids. What could NOT be checked from the repo is the ASC
side: whether products with those exact ids exist, what state they are in, and
whether they are attached to the version under review.

This asks App Store Connect directly instead of guessing.

Usage:
    export ASC_API_ISSUER_ID=<uuid from Users and Access -> Integrations>
    python3 IOS/scripts/asc_check.py

Key id and .p8 are discovered from ~/.appstoreconnect/private_keys/.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

import jwt

BUNDLE_ID = os.environ.get("ASC_BUNDLE_ID", "com.alafia.app")
EXPECTED = ["alafia_plus_monthly", "alafia_plus_annual"]
BASE = "https://api.appstoreconnect.apple.com/v1"


def _key() -> tuple[str, str]:
    paths = glob.glob(os.path.expanduser("~/.appstoreconnect/private_keys/AuthKey_*.p8"))
    if not paths:
        sys.exit("No AuthKey_*.p8 in ~/.appstoreconnect/private_keys/")
    path = paths[0]
    key_id = os.path.basename(path)[len("AuthKey_"):-len(".p8")]
    return key_id, open(path).read()


def _token() -> str:
    issuer = os.environ.get("ASC_API_ISSUER_ID", "").strip()
    if not issuer:
        sys.exit(
            "Set ASC_API_ISSUER_ID first.\n"
            "  App Store Connect -> Users and Access -> Integrations -> "
            "App Store Connect API. The Issuer ID is the UUID at the top.\n"
            "  export ASC_API_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
    key_id, private_key = _key()
    now = int(time.time())
    return jwt.encode(
        # Apple rejects a token whose lifetime exceeds 20 minutes.
        {"iss": issuer, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"},
        private_key, algorithm="ES256", headers={"kid": key_id, "typ": "JWT"},
    )


def api(path: str, token: str):
    req = urllib.request.Request(
        path if path.startswith("http") else f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        # 401 here is almost always a wrong issuer id or an expired/revoked key,
        # not a missing product — say which, or this reads as "no products".
        sys.exit(f"App Store Connect returned {e.code}: {body}")


def main() -> None:
    token = _token()

    apps = api(f"/apps?filter[bundleId]={BUNDLE_ID}", token)["data"]
    if not apps:
        sys.exit(f"No app with bundle id {BUNDLE_ID} on this account.")
    app = apps[0]
    app_id = app["id"]
    print(f"App: {app['attributes']['name']}  ({BUNDLE_ID})  id={app_id}\n")

    # ── In-app purchases ──
    iaps = api(f"/apps/{app_id}/inAppPurchasesV2?limit=200", token)["data"]
    found = {}
    print("In-app purchases on the account:")
    for iap in iaps:
        a = iap["attributes"]
        pid, state = a.get("productId"), a.get("state")
        found[pid] = state
        print(f"  {pid:<28} {a.get('name','?'):<24} {state}")
    if not iaps:
        print("  (none)")

    print("\nWhat the binary asks StoreKit for:")
    ok = True
    for pid in EXPECTED:
        state = found.get(pid)
        if state is None:
            ok = False
            print(f"  {pid:<28} MISSING  <- Product.products() returns nothing for this")
        elif state in ("APPROVED", "READY_TO_SUBMIT", "WAITING_FOR_REVIEW", "IN_REVIEW"):
            print(f"  {pid:<28} {state}")
        else:
            ok = False
            print(f"  {pid:<28} {state}  <- not purchasable in review")

    # ── Versions and what is attached ──
    print("\nApp Store versions:")
    versions = api(f"/apps/{app_id}/appStoreVersions?limit=5", token)["data"]
    for v in versions:
        a = v["attributes"]
        print(f"  {a.get('versionString'):<10} {a.get('appStoreState')}  platform={a.get('platform')}")

    print("\nBuilds (newest first):")
    builds = api(f"/builds?filter[app]={app_id}&limit=5&sort=-uploadedDate", token)["data"]
    for b in builds:
        a = b["attributes"]
        print(f"  {a.get('version'):<6} uploaded={str(a.get('uploadedDate'))[:19]}  "
              f"expired={a.get('expired')}  processing={a.get('processingState')}")

    print("\n" + ("All expected products are present and purchasable."
                  if ok else
                  "ACTION NEEDED: the products above are why review could not find them."))


if __name__ == "__main__":
    main()
