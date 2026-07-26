"""Gemeinsame Vorbereitungen fuer alle Tests."""

from __future__ import annotations

import os

# Qt ohne Bildschirm betreiben. Muss VOR dem ersten Qt-Import gesetzt sein,
# sonst sucht Qt einen X-Server und bricht in der CI ab.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
