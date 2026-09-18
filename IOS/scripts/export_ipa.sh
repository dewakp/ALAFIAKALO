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

SCHEME="ALAFIA"
PROJECT="ALAFIA.xcodeproj"
STAGE="build/.staging-archive.xcarchive"
LOGDIR="build/logs"
mkdir -p build/archives/older build/ipa/older "$LOGDIR"

echo "── archiving ($PLIST)"
printf '   manageAppVersionAndBuildNumber: '
plutil -extract manageAppVersionAndBuildNumber raw "$PLIST" 2>/dev/null || echo "(unset)"

rm -rf "$STAGE"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$STAGE" archive \
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
[ -e "$ARCHIVE" ] && ARCHIVE="build/archives/older/$NAME-$STAMP.xcarchive"
rm -rf "$ARCHIVE" && mv "$STAGE" "$ARCHIVE"
echo "   archive: $ARCHIVE"

echo "── exporting"
rm -rf build/.staging-export
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$PLIST" \
  -exportPath build/.staging-export > "$LOGDIR/export.log" 2>&1 \
  || { tail -20 "$LOGDIR/export.log"; exit 1; }

SRC=$(ls build/.staging-export/*.ipa | head -1)
IPA="build/ipa/$NAME.ipa"
[ -e "$IPA" ] && IPA="build/ipa/older/$NAME-$STAMP.ipa"
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
