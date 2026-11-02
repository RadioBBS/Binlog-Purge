"""
Binlog-Purge – Unit-Tests ohne laufende MariaDB.

Projekt:     Binlog-Purge
Modul:       tests/test_binlog_purge.py
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
Prueft Versionsabgleich, Lognamen, PURGE-TO-Ziele und CLI ohne Server.

Historie
--------
Version 1.0.0 – 2026-09-03 – Parser, SQL-Helfer, --help/--version
Version 1.1.0 – 2026-09-03 – No-Op-Erkennung Alt-Logs
Version 1.1.1 – 2026-11-02 – Startausgabe und Python 3.11 nach Styleguide 2.1.0.

Aufruf / Nutzung
----------------
  python -m unittest tests.test_binlog_purge
"""

from __future__ import annotations

import io
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import binlog_purge
import project_meta

ROOT = Path(__file__).resolve().parents[1]


def _feld(text: str, schluessel: str) -> str:
    """Liest version oder description aus YAML/TOML.

    Parameter: text – Dateiinhalt; schluessel – Feldname
    Rueckgabe: Wert ohne Anfuehrungszeichen
    Fehlerfaelle: ValueError wenn der Schluessel fehlt
    Beispiel: _feld('version = "1.0.0"', "version")
    """
    muster = rf'^{schluessel}\s*[:=]\s*"?([^"\n]+)"?\s*$'
    treffer = re.search(muster, text, flags=re.MULTILINE)
    if treffer is None:
        raise ValueError(f"Schluessel fehlt: {schluessel}")
    return treffer.group(1).strip()


class TestMetadaten(unittest.TestCase):
    """Kopf, YAML und TOML."""

    def test_autor(self) -> None:
        """Pflicht-Autor."""
        self.assertEqual(project_meta.__author__, "(FFHB) / RadioBBS")

    def test_version(self) -> None:
        """Gleiche Version in YAML, TOML und Meta."""
        yaml_text = (ROOT / "PROJECT.yaml").read_text(encoding="utf-8")
        toml_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(_feld(yaml_text, "version"), project_meta.__version__)
        self.assertEqual(_feld(toml_text, "version"), project_meta.__version__)

    def test_zweck(self) -> None:
        """Ein-Satz-Zweck identisch."""
        yaml_text = (ROOT / "PROJECT.yaml").read_text(encoding="utf-8")
        toml_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(_feld(yaml_text, "description"), project_meta.BESCHREIBUNG)
        self.assertEqual(_feld(toml_text, "description"), project_meta.BESCHREIBUNG)


class TestSqlHelfer(unittest.TestCase):
    """Lognamen und PURGE-Ziele."""

    def test_in_use_name(self) -> None:
        """MariaDB-Meldung zur gesperrten Datei."""
        text = "ERROR 1376 (HY000): The log with filename 'mysql-bin.000001' is in use"
        self.assertEqual(binlog_purge.parse_in_use_name(text), "mysql-bin.000001")

    def test_sicherer_logname(self) -> None:
        """Nur harmlose Namen."""
        self.assertEqual(binlog_purge.sicherer_logname("mysql-bin.000002"), "mysql-bin.000002")
        with self.assertRaises(ValueError):
            binlog_purge.sicherer_logname("mysql-bin.000001'; DROP TABLE t;--")

    def test_sql_purge_to(self) -> None:
        """PURGE TO mit Quoting."""
        self.assertEqual(
            binlog_purge.sql_purge_to("mysql-bin.000010"),
            "PURGE BINARY LOGS TO 'mysql-bin.000010'",
        )

    def test_batch_ziele(self) -> None:
        """Chargen enden vor bzw. mit dem aktiven Log."""
        logs = [f"mysql-bin.{i:06d}" for i in range(1, 6)]
        ziele = binlog_purge.batch_ziele(logs, "mysql-bin.000005", 2)
        self.assertNotIn("mysql-bin.000005", logs[:4])
        self.assertEqual(ziele[-1], "mysql-bin.000005")
        self.assertTrue(all(z in logs for z in ziele))

    def test_zu_viele_altlogs(self) -> None:
        """No-Op erkennen: Alt-Logs neben dem aktiven File."""
        logs = [("mysql-bin.000001", 10), ("mysql-bin.000002", 5)]
        self.assertTrue(binlog_purge.zu_viele_altlogs(logs, "mysql-bin.000002"))
        self.assertFalse(binlog_purge.zu_viele_altlogs(logs[-1:], "mysql-bin.000002"))

    def test_parse_tsv(self) -> None:
        """SHOW BINARY LOGS im Batch-Format."""
        text = "Log_name\tFile_size\nmysql-bin.000001\t1024\nmysql-bin.000002\t2048\n"
        rows = binlog_purge.parse_tsv(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Log_name"], "mysql-bin.000001")


class TestCli(unittest.TestCase):
    """Hilfe ohne Fachlauf."""

    def test_help(self) -> None:
        """--help Exit 0, Zweck, ohne Client."""
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            code = binlog_purge.main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn(project_meta.BESCHREIBUNG, puffer.getvalue())
        self.assertIn("PURGE BINARY LOGS TO", puffer.getvalue())
        self.assertIn("slave_connections_needed_for_purge=0", puffer.getvalue())
        self.assertIn("$env:ProgramFiles", puffer.getvalue())
        self.assertIn("%PROGRAMFILES%", puffer.getvalue())

    def test_version(self) -> None:
        """--version Exit 0."""
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            code = binlog_purge.main(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(project_meta.__version__, puffer.getvalue())

    def test_unbekannte_option(self) -> None:
        """Unbekannt: FEHLER und Exit 2."""
        puffer = io.StringIO()
        with redirect_stderr(puffer):
            with self.assertRaises(SystemExit) as ctx:
                binlog_purge.main(["--unsinn"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("FEHLER:", puffer.getvalue())

    def test_port_ungueltig(self) -> None:
        """Port ausserhalb 1-65535: Exit 2."""
        puffer = io.StringIO()
        with redirect_stderr(puffer):
            code = binlog_purge.main(["--port", "0"])
        self.assertEqual(code, 2)
        self.assertIn("FEHLER:", puffer.getvalue())


if __name__ == "__main__":
    unittest.main()
