#!/usr/bin/env sh
# Download CGMacros v1.0.0 (PhysioNet, open access, CC BY-NC-SA 4.0), check its SHA-256 and extract the CSVs only.
# Data stay in data/external (gitignored); they are not redistributed with this repository.
set -eu
DEST="$(dirname "$0")/../data/external"
mkdir -p "$DEST"
cd "$DEST"
BASE="https://physionet-open.s3.amazonaws.com/cgmacros/1.0.0"
curl -fsSL --retry 5 -C - -o cgmacros.zip "$BASE/CGMacros_dateshifted365.zip"
curl -fsSL -o SHA256SUMS.txt "$BASE/SHA256SUMS.txt"
EXPECTED=$(grep "CGMacros_dateshifted365.zip" SHA256SUMS.txt | cut -d' ' -f1)
ACTUAL=$(shasum -a 256 cgmacros.zip | cut -d' ' -f1)
[ "$EXPECTED" = "$ACTUAL" ] || { echo "checksum mismatch"; exit 1; }
mkdir -p cgmacros
unzip -q -o cgmacros.zip "*.csv" -d cgmacros
echo "CGMacros ready in data/external/cgmacros"
