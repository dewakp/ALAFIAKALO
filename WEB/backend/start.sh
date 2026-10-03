#!/usr/bin/env bash
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

# Start the ALAFIA backend from any working directory.
# Usage: ./start.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../.venv/bin/activate"
exec python "$SCRIPT_DIR/_launch.py" "$@"
