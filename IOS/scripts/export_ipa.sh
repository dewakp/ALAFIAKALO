#!/usr/bin/env bash
# Archive and export an iOS release, named by what is INSIDE the build.
#
#   IOS/scripts/export_ipa.sh [ExportOptions.plist]
#
# `xcodebuild -exportArchive` always writes `ALAFIA.ipa`, so every release used
# to be renamed by hand — and each one was renamed differently. That left IPAs
# in four directories under five name shapes, including one file whose name said
# build 5 while it held build 6. This script removes the hand step:
#
#   IOS/build/archives/ALAFIA-<marketing>-<build>.xcarchive
#   IOS/build/ipa/ALAFIA-<marketing>-<build>.ipa
#   IOS/build/ipa/ALAFIA-latest.ipa -> the export just made
#
# Re-exporting a build that already has an artefact does not overwrite it: the
# new one lands in `older/` with today's date, because two binaries claiming the
# same build number is exactly the confusion this is here to prevent.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # IOS/

PLIST="${1:-build/ipa/ExportOptions.plist}"
[ -f "$PLIST" ] || { echo "missing export options: $PLIST" >&2; exit 1; }

# Automatic signing needs an AUTHENTICATED Apple Developer account. Xcode's
# Accounts pane is one way; an App Store Connect API key is the other, and it is
# the only one that works unattended — no GUI, no 2FA prompt, nothing in a
# keychain to go stale.
#
#   ASC_KEY_PATH=~/Downloads/AuthKey_XXXXXXXXXX.p8 \
#   ASC_KEY_ID=XXXXXXXXXX ASC_ISSUER_ID=<uuid> IOS/scripts/export_ipa.sh ...
#
# Why this was added: on 2026-09-26/27 every archive died with
#   "Unable to log in with account 'wolex@mac.com'. The login details ... were
#    rejected."
# The account configured in Xcode was not the operator's Apple ID at all — one
# wrong address, and no amount of re-authenticating it could succeed. An API key
# sidesteps the account entirely, so a mistyped or stale Xcode account cannot
# block a release again.
#
# ⚠️ NEITHER `xcodebuild -help` NOR `man xcodebuild` documents these three flags.
# They are nonetheless accepted: passing -authenticationKeyPath with no value
# answers "option '-authenticationKeyPath' requires an argument", not "unknown
# option". Verified on Xcode 26.6 (17F113). Do not delete them because the help
# text does not mention them.
AUTH=()
if [ -n "${ASC_KEY_PATH:-}" ]; then
  [ -f "$ASC_KEY_PATH" ] || { echo "ASC_KEY_PATH is not a file: $ASC_KEY_PATH" >&2; exit 1; }
  : "${ASC_KEY_ID:?ASC_KEY_PATH is set, so ASC_KEY_ID must be too}"
  : "${ASC_ISSUER_ID:?ASC_KEY_PATH is set, so ASC_ISSUER_ID must be too}"
  # The ISSUER is a UUID and the KEY ID is a 10-character alphanumeric. They are
  # easy to swap, and swapping them fails with an opaque authentication error —
  # a Team ID was once passed as the issuer and cost an afternoon.
  case "$ASC_ISSUER_ID" in
    ????????-????-????-????-????????????) ;;
    *) echo "ASC_ISSUER_ID does not look like a UUID: $ASC_ISSUER_ID" >&2
       echo "  (the issuer is a UUID from App Store Connect > Integrations;" >&2
       echo "   a Team ID such as GG8GA4QA5P is NOT the issuer)" >&2
       exit 1 ;;
  esac
  AUTH=(-authenticationKeyPath "$ASC_KEY_PATH"
        -authenticationKeyID "$ASC_KEY_ID"
        -authenticationKeyIssuerID "$ASC_ISSUER_ID")
  echo "── signing via App Store Connect API key $ASC_KEY_ID (no Xcode account used)"
fi

SCHEME="ALAFIA"
PROJECT="ALAFIA.xcodeproj"
STAGE="build/.staging-archive.xcarchive"
LOGDIR="build/logs"
mkdir -p build/archives/older build/ipa/older "$LOGDIR"

echo "── archiving ($PLIST)"
printf '   manageAppVersionAndBuildNumber: '
plutil -extract manageAppVersionAndBuildNumber raw "$PLIST" 2>/dev/null || echo "(unset)"

# -allowProvisioningUpdates is REQUIRED, not a convenience. A provisioning
# profile embeds SPECIFIC certificates, so every profile generated before a
# certificate was issued is stale for it. Without this flag xcodebuild may only
# use profiles already cached on disk — it will not contact Apple — so
# `CODE_SIGN_STYLE = Automatic` cannot repair anything and the archive dies with
#   "Provisioning profile ... doesn't include signing certificate ..."
#
# That is exactly what happened on 2026-09-27: both signing certificates expired
# within hours of each other, new ones were issued, and two consecutive
# re-exports still failed — first on the missing development certificate, then
# on the team profile that predated its replacement. Neither wrote an artefact,
# and both reported success upstream.
rm -rf "$STAGE"
# ${AUTH[@]+"${AUTH[@]}"} — NOT "${AUTH[@]}". macOS ships bash 3.2, where an
# empty array expanded under `set -u` is an unbound variable and aborts the
# script. This form expands to nothing when AUTH is empty.
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$STAGE" archive \
  -allowProvisioningUpdates ${AUTH[@]+"${AUTH[@]}"} \
  > "$LOGDIR/archive.log" 2>&1 || { tail -20 "$LOGDIR/archive.log"; exit 1; }

# The archive is the authority on what was built — not the project file, and
# never the folder name.
INFO="$STAGE/Info.plist"
V=$(plutil -extract ApplicationProperties.CFBundleShortVersionString raw "$INFO")
B=$(plutil -extract ApplicationProperties.CFBundleVersion raw "$INFO")
NAME="ALAFIA-$V-$B"
STAMP=$(date +%Y%m%d)
echo "── built $V ($B)"

ARCHIVE="build/archives/$NAME.xcarchive"
# Same rule as the IPA below: the newest archive keeps the canonical name and
# the previous one steps aside, dated by its own mtime. A stale archive under
# the canonical name is the quieter half of the same trap — it is what a later
# re-export reads from, so it would silently re-emit the old binary.
if [ -e "$ARCHIVE" ]; then
  PREV_STAMP=$(date -r "$ARCHIVE" +%Y%m%d 2>/dev/null || echo "$STAMP")
  PREV_A="build/archives/older/$NAME-$PREV_STAMP.xcarchive"
  [ -e "$PREV_A" ] && PREV_A="build/archives/older/$NAME-$PREV_STAMP-$(date +%H%M%S).xcarchive"
  mv "$ARCHIVE" "$PREV_A"
  echo "   previous: $PREV_A  (stepped aside; not deleted)"
fi
mv "$STAGE" "$ARCHIVE"
echo "   archive: $ARCHIVE"

echo "── exporting"
rm -rf build/.staging-export
# Same flag, same reason: the STORE profile embeds certificates too, and is
# stale for a newly issued distribution certificate. Fixing only the archive
# step above just moves the failure here.
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$PLIST" \
  -exportPath build/.staging-export -allowProvisioningUpdates \
  ${AUTH[@]+"${AUTH[@]}"} \
  > "$LOGDIR/export.log" 2>&1 \
  || { tail -20 "$LOGDIR/export.log"; exit 1; }

SRC=$(ls build/.staging-export/*.ipa | head -1)
IPA="build/ipa/$NAME.ipa"
# The NEWEST export keeps the canonical name; the previous one steps aside.
#
# This used to be the other way round — a repeat export of an existing build
# number landed in older/ and left the EARLIER artefact under the canonical
# name. The intent was "never overwrite", but the effect was to hide the fresh
# binary and keep the stale one where anyone would reach for it.
#
# It bit on 2026-09-27: build/ipa/ALAFIA-1.5-11.ipa held a binary signed with a
# SUPERSEDED distribution certificate (serial 7818F922D4878CAFB53A6412E9B063B2)
# while the correctly signed rebuild sat in older/. Uploading by the documented
# name would have shipped the unusable one — "a filename that lies is worse than
# no filename", with the lie in the GOOD name.
#
# Nothing is deleted either way. The displaced file is dated by its OWN mtime,
# not today's, so its name says when that binary was built rather than when it
# was moved.
if [ -e "$IPA" ]; then
  PREV_STAMP=$(date -r "$IPA" +%Y%m%d 2>/dev/null || echo "$STAMP")
  PREV="build/ipa/older/$NAME-$PREV_STAMP.ipa"
  [ -e "$PREV" ] && PREV="build/ipa/older/$NAME-$PREV_STAMP-$(date +%H%M%S).ipa"
  mv "$IPA" "$PREV"
  echo "   previous: $PREV  (stepped aside; not deleted)"
fi
mv "$SRC" "$IPA"
cp -f build/.staging-export/*.plist build/.staging-export/Packaging.log build/ipa/ 2>/dev/null || true
rm -rf build/.staging-export
ln -sfn "$(basename "$IPA")" build/ipa/ALAFIA-latest.ipa
echo "   ipa:     $IPA"
echo "   latest:  build/ipa/ALAFIA-latest.ipa -> $(basename "$IPA")"

# Verify from the artefact, because that is the only thing that gets uploaded.
echo "── verifying the IPA itself"
TMP=$(mktemp -d)
unzip -o -q "$IPA" -d "$TMP" 'Payload/*/Info.plist' 'Payload/*/embedded.mobileprovision'
APPINFO=$(ls "$TMP"/Payload/*/Info.plist | head -1)
printf '   version: %s (%s)\n' \
  "$(plutil -extract CFBundleShortVersionString raw "$APPINFO")" \
  "$(plutil -extract CFBundleVersion raw "$APPINFO")"
PROV=$(ls "$TMP"/Payload/*/embedded.mobileprovision 2>/dev/null | head -1)
if [ -n "$PROV" ]; then
  security cms -D -i "$PROV" > "$TMP/prov.plist" 2>/dev/null || true
  printf '   profile: %s\n' "$(plutil -extract Name raw "$TMP/prov.plist" 2>/dev/null)"
  printf '   get-task-allow: %s\n' "$(plutil -extract Entitlements.get-task-allow raw "$TMP/prov.plist" 2>/dev/null || echo 'absent (store build)')"
fi
rm -rf "$TMP"
