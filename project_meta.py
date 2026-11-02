"""
Binlog-Purge – Gemeinsame Projekt-Metadaten.

Projekt:     Binlog-Purge
Modul:       project_meta.py
Version:     1.1.1
Stand:       2026-11-02
Abhaengig:   Python >= 3.11; MariaDB-Client mariadb oder mysql
Bezug:       requirements.txt
Lizenz:      MIT
Upstream:    –
Erstellt mit: Cursor Grok 4.6
Autor:       (FFHB) / RadioBBS

Beschreibung
------------
Löscht MariaDB-Binlogs per PURGE BINARY LOGS, nachdem das aktive Log rotiert wurde.

Historie
--------
Version 1.0.0 – 2026-09-03 – Erstausgabe: FLUSH, PURGE BEFORE NOW, Fallback PURGE TO
Version 1.1.0 – 2026-09-03 – MariaDB 12: slave_connections_needed_for_purge=0 vor PURGE
Version 1.1.1 – 2026-11-02 – Startausgabe und Python 3.11 nach Styleguide 2.1.0.

Aufruf / Nutzung
----------------
  python binlog_purge.py --help
  python binlog_purge.py --version
  python binlog_purge.py --dry-run
  python binlog_purge.py --yes
  python binlog_purge.py --host 127.0.0.1 --port 3307 --user root --yes
  python binlog_purge.py --yes --reset-master
"""

from __future__ import annotations

import re
import sys

PROJECT_NAME = "Binlog-Purge"
BESCHREIBUNG = (
    "Löscht MariaDB-Binlogs per PURGE BINARY LOGS, nachdem das aktive Log rotiert wurde."
)
PROJECT_DESCRIPTION = BESCHREIBUNG
PYTHON_REQUIRES = ">=3.11"
REQUIRES_WINDOWS = False
STYLEGUIDE_VERSION = "2.1.0"
SOFTWARE_STANDARD_VERSION = "1.6.0"

__version__ = "1.1.1"
__date__ = "2026-11-02"
__license__ = "MIT"
__created_with__ = "Cursor Grok 4.6"
__upstream__ = "–"
__author__ = "(FFHB) / RadioBBS"
__requires__ = "Python >= 3.11; MariaDB-Client mariadb oder mysql"
__requirements_ref__ = "requirements.txt"

END_PROMPT = 'Programmende: "Hit any Key or Enter"'
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3307
DEFAULT_USER = "root"
DEFAULT_LOGFILE = "binlog_purge.log"
README_CLIENT_WIN = (
    r'CMD: "%PROGRAMFILES%\MariaDB 12.3\bin\mariadb.exe". '
    r'PowerShell: & "$env:ProgramFiles\MariaDB 12.3\bin\mariadb.exe"'
)
README_CLIENT_DEB = "sudo apt-get install mariadb-client"


def min_python_tuple() -> tuple[int, int]:
    """Liest die Mindest-Python-Version aus PYTHON_REQUIRES.

    Parameter: keine
    Rueckgabe: (major, minor)
    Fehlerfaelle: ValueError bei ungueltigem PYTHON_REQUIRES
    Beispiel: min_python_tuple() == (3, 11)
    """
    treffer = re.search(r"(\d+)\.(\d+)", PYTHON_REQUIRES)
    if treffer is None:
        raise ValueError(f"Ungueltiges PYTHON_REQUIRES: {PYTHON_REQUIRES!r}")
    return int(treffer.group(1)), int(treffer.group(2))


def check_runtime() -> None:
    """Prueft die Python-Version nach --help/--version.

    Parameter: keine
    Rueckgabe: None
    Fehlerfaelle: SystemExit(2) bei zu altem Python
    Beispiel: check_runtime()
    """
    braucht = min_python_tuple()
    if sys.version_info[:2] < braucht:
        print(
            "FEHLER: Python >= "
            f"{braucht[0]}.{braucht[1]} noetig "
            f"(gefunden: {sys.version_info.major}.{sys.version_info.minor}).",
            file=sys.stderr,
        )
        raise SystemExit(2)
