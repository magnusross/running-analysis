#!/usr/bin/env bash
set -euo pipefail

NOTEBOOK="course_speed_factors.ipynb"
VENV_ACTIVATE="$(dirname "$0")/.venv/bin/activate"

# Activate the project venv
# shellcheck disable=SC1090
source "$VENV_ACTIVATE"

echo "Exporting $NOTEBOOK to PDF..."
jupyter nbconvert --to pdf --no-input "$NOTEBOOK"

PDF="${NOTEBOOK%.ipynb}.pdf"
echo "Done: $PDF"

# Open the PDF if on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    open "$PDF"
fi
