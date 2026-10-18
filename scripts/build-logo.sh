#!/usr/bin/env bash
#
# Write `eta_publish/assets/logo.svg`, the logo charts carry,
# from `eta_publish/assets/logo.src.svg`, the logo as drawn.
#
# Edit the source, in Inkscape or anything else, then run this:
# the output is generated, so an edit made to it is lost the next time this runs.

set -euo pipefail

cd "$(dirname "$0")/.."

src=eta_publish/assets/logo.src.svg
out=eta_publish/assets/logo.svg

cp "$src" "$out"
