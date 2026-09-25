#!/usr/bin/env bash
# Zum Starten der Proxmark3-GUI unter macOS/Linux einfach doppelklicken.
# (Unter macOS ggf. vorher: Rechtsklick -> Oeffnen.)
cd "$(dirname "$0")" || exit 1

# Python 3 finden.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3 wurde nicht gefunden. Bitte von python.org installieren."
  read -r -p "Mit Enter schliessen..."
  exit 1
fi

echo "Starte Proxmark3-GUI ..."
"$PY" start.py "$@"
