#!/usr/bin/env python3
"""
Binlog-Purge – Löscht MariaDB-Binlogs per PURGE BINARY LOGS, nachdem das aktive Log rotiert wurde.

Projekt:     Binlog-Purge
Modul:       binlog_purge.py
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
Version 1.0.0 – 2026-09-03 – FLUSH BINARY LOGS, PURGE BEFORE NOW, Fallback PURGE TO
Version 1.1.0 – 2026-09-03 – SET GLOBAL slave_connections_needed_for_purge=0 vor PURGE
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

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from project_meta import (
    BESCHREIBUNG,
    DEFAULT_HOST,
    DEFAULT_LOGFILE,
    DEFAULT_PORT,
    DEFAULT_USER,
    END_PROMPT,
    PROJECT_NAME,
    README_CLIENT_DEB,
    README_CLIENT_WIN,
    __date__,
    __version__,
    check_runtime,
)

LOGNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
IN_USE_RE = re.compile(
    r"filename ['\"]?(?P<name>[A-Za-z0-9._-]+)['\"]? is in use",
    re.IGNORECASE,
)
SSL_FLAGS = (("--ssl=off",), ("--skip-ssl",), ("--ssl-mode=DISABLED",), ())
SQL_PURGE_NOW = "PURGE BINARY LOGS BEFORE NOW()"
SQL_FLUSH = "FLUSH BINARY LOGS"
SQL_PURGE_REPLIKATE_AUS = "SET GLOBAL slave_connections_needed_for_purge=0"
CLIENT_TIMEOUT_S = 3600
RETRY_PAUSE_S = 2.0
MAX_VERSUCHE = 8


@dataclass
class Laufzeit:
    """Verbindung und Ablaufsteuerung."""

    host: str
    port: int
    user: str
    password: str
    client: Path
    ssl_flags: tuple[str, ...]
    dry_run: bool
    yes: bool
    reset_master: bool
    log_an: bool
    logfile: Path
    batch: int


class AufrufParser(argparse.ArgumentParser):
    """ArgumentParser mit FEHLER: und Exit 2."""

    def error(self, message: str) -> None:
        """Bricht bei falschen Optionen mit Exit 2 ab.

        Parameter: message – argparse-Text
        Rueckgabe: None (kein Return)
        Fehlerfaelle: SystemExit(2)
        Beispiel: intern
        """
        print(f"FEHLER: {message} (siehe --help)", file=sys.stderr)
        raise SystemExit(2)


def zeige_hilfe() -> int:
    """Schreibt Zweck, Version und Parameter.

    Parameter: keine
    Rueckgabe: 0
    Fehlerfaelle: keine
    Beispiel: zeige_hilfe()
    """
    print(f"{PROJECT_NAME} {__version__} ({__date__})")
    print(BESCHREIBUNG)
    print()
    print("Ablauf: SET GLOBAL slave_connections_needed_for_purge=0,")
    print("FLUSH BINARY LOGS, PURGE BINARY LOGS TO <aktuelles Log>.")
    print("Ohne den SET-Schritt liefert MariaDB 11.4+/12 Exit 0 und loescht nichts.")
    print()
    print("Verwendung:")
    print("  python binlog_purge.py --help")
    print("  python binlog_purge.py --version")
    print("  python binlog_purge.py --dry-run")
    print("  python binlog_purge.py --yes")
    print("  python binlog_purge.py --host 127.0.0.1 --port 3307 --user root --yes")
    print("  python binlog_purge.py --yes --reset-master")
    print()
    print("Parameter:")
    print("  --help / -h")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: Diese Hilfe, ohne MariaDB-Client.")
    print("    Beispiel: python binlog_purge.py --help")
    print("  --version")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: Version, Datum und Ein-Satz-Zweck.")
    print("    Beispiel: python binlog_purge.py --version")
    print("  --host HOST")
    print(f"    Typ: str  Standard: {DEFAULT_HOST}")
    print("    Beschreibung: TCP-Host des Servers (Internal Server: Loopback).")
    print("    Beispiel: --host 127.0.0.1")
    print("  --port PORT")
    print(f"    Typ: int  Standard: {DEFAULT_PORT}")
    print("    Beschreibung: TCP-Port. DigiKam-Internal-Server: 3307.")
    print("    Beispiel: --port 3307")
    print("  --user NAME")
    print(f"    Typ: str  Standard: {DEFAULT_USER}")
    print("    Beschreibung: Datenbankbenutzer. Bei skip_grant_tables reicht root.")
    print("    Beispiel: --user root")
    print("  --password TEXT")
    print("    Typ: str  Standard: leer")
    print("    Beschreibung: Passwort; leer lassen wenn Grants aus sind.")
    print("    Beispiel: --password")
    print("  --client PFAD")
    print("    Typ: Pfad  Standard: MariaDB 12.3\\bin\\mariadb.exe oder PATH")
    print("    Beschreibung: mariadb- bzw. mysql-Client.")
    print(r'    Beispiel CMD: --client "%PROGRAMFILES%\MariaDB 12.3\bin\mariadb.exe"')
    print(r'    Beispiel PowerShell: --client "$env:ProgramFiles\MariaDB 12.3\bin\mariadb.exe"')
    print("  --dry-run")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: Nur SQL und Dateiliste zeigen, nichts loeschen.")
    print("    Beispiel: python binlog_purge.py --dry-run")
    print("  --yes")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: Loeschen ohne Rueckfrage (destruktiv).")
    print("    Beispiel: python binlog_purge.py --yes")
    print("  --reset-master")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: Wenn PURGE an 'in use' scheitert: alle Binlogs neu beginnen.")
    print("    Beispiel: python binlog_purge.py --yes --reset-master")
    print("  --batch N")
    print("    Typ: int  Standard: 50")
    print("    Beschreibung: Bei 'in use' so viele Dateien pro PURGE TO.")
    print("    Beispiel: --batch 20")
    print("  --log")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: UTF-8-Log ohne BOM schreiben.")
    print("    Beispiel: python binlog_purge.py --log --yes")
    print("  --logfile PFAD")
    print(f"    Typ: Pfad  Standard: {DEFAULT_LOGFILE}")
    print("    Beschreibung: Logdatei (ASCII-Dateiname).")
    print("    Beispiel: --logfile binlog_purge.log")
    print("  --Ende / -E")
    print("    Typ: Schalter  Standard: aus")
    print("    Beschreibung: Am Ende auf Taste oder Enter warten.")
    print("    Beispiel: python binlog_purge.py --yes --Ende")
    print()
    print("Beispiele:")
    print("  python binlog_purge.py --help")
    print("  python binlog_purge.py --version")
    print("  python binlog_purge.py --dry-run")
    print("  python binlog_purge.py --yes")
    print("  python binlog_purge.py --host 127.0.0.1 --port 3307 --user root --yes")
    print("  python binlog_purge.py --yes --reset-master")
    return 0


def zeige_version() -> int:
    """Schreibt Version, Datum und Zweck.

    Parameter: keine
    Rueckgabe: 0
    Fehlerfaelle: keine
    Beispiel: zeige_version()
    """
    print(f"{PROJECT_NAME} {__version__} ({__date__})")
    print(BESCHREIBUNG)
    return 0


def sicherer_logname(name: str) -> str:
    """Laesst nur harmlose Binlog-Dateinamen zu.

    Parameter: name – Dateiname aus SHOW BINARY LOGS
    Rueckgabe: derselbe Name
    Fehlerfaelle: ValueError bei Sonderzeichen
    Beispiel: sicherer_logname("mysql-bin.000002")
    """
    if not LOGNAME_RE.fullmatch(name):
        raise ValueError(name)
    return name


def parse_in_use_name(stderr: str) -> str | None:
    """Liest den gesperrten Lognamen aus der MariaDB-Meldung.

    Parameter: stderr – Client-Fehlertext
    Rueckgabe: Dateiname oder None
    Fehlerfaelle: keine
    Beispiel: parse_in_use_name("... filename 'mysql-bin.000001' is in use")
    """
    treffer = IN_USE_RE.search(stderr or "")
    if treffer is None:
        return None
    return treffer.group("name")


def sql_purge_to(logname: str) -> str:
    """Baut PURGE BINARY LOGS TO fuer ein geprueftes Log.

    Parameter: logname – aktuelles oder Ziel-Log
    Rueckgabe: SQL-Text
    Fehlerfaelle: ValueError bei unsicherem Namen
    Beispiel: sql_purge_to("mysql-bin.000010")
    """
    sicher = sicherer_logname(logname)
    return f"PURGE BINARY LOGS TO '{sicher}'"


def default_client_kandidaten() -> list[Path]:
    """Sucht den Client unter PROGRAMFILES und im PATH.

    Parameter: keine
    Rueckgabe: vorhandene Dateipfade
    Fehlerfaelle: keine
    Beispiel: default_client_kandidaten()
    """
    gefunden: list[Path] = []
    pf = os.environ.get("PROGRAMFILES")
    if pf:
        basis = Path(pf) / "MariaDB 12.3" / "bin"
        gefunden.extend([basis / "mariadb.exe", basis / "mysql.exe"])
    for name in ("mariadb", "mysql", "mariadb.exe", "mysql.exe"):
        which = shutil.which(name)
        if which:
            gefunden.append(Path(which))
    return [p for p in gefunden if p.is_file()]


def finde_client(explicit: Path | None) -> Path | None:
    """Waehlt den MariaDB-Client.

    Parameter: explicit – --client oder None
    Rueckgabe: Pfad oder None
    Fehlerfaelle: keine
    Beispiel: finde_client(None)
    """
    if explicit is not None:
        return explicit if explicit.is_file() else None
    kandidaten = default_client_kandidaten()
    return kandidaten[0] if kandidaten else None


def parse_tsv(text: str) -> list[dict[str, str]]:
    """Parst --batch-Tabellen (erste Zeile = Kopf).

    Parameter: text – stdout des Clients
    Rueckgabe: Zeilen als dict
    Fehlerfaelle: keine
    Beispiel: parse_tsv("Log_name\\tFile_size\\nmysql-bin.000001\\t10")
    """
    zeilen = [z for z in text.splitlines() if z.strip()]
    if not zeilen:
        return []
    koepfe = zeilen[0].split("\t")
    result: list[dict[str, str]] = []
    for zeile in zeilen[1:]:
        teile = zeile.split("\t")
        rec = {koepfe[i]: teile[i] if i < len(teile) else "" for i in range(len(koepfe))}
        result.append(rec)
    return result


def client_env(password: str) -> dict[str, str]:
    """Setzt MYSQL_PWD nur wenn ein Passwort da ist.

    Parameter: password – Klartext oder leer
    Rueckgabe: Umgebung
    Fehlerfaelle: keine
    Beispiel: client_env("")
    """
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    return env


def schreibe_log(cfg: Laufzeit, text: str) -> None:
    """Haengt eine UTF-8-Zeile ohne BOM an das Log.

    Parameter: cfg – Laufzeit; text – Meldung
    Rueckgabe: None
    Fehlerfaelle: OSError wird nach stderr geschrieben, Lauf geht weiter
    Beispiel: schreibe_log(cfg, "FLUSH ok")
    """
    if not cfg.log_an:
        return
    stempel = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    zeile = f"{stempel} {text}\n"
    try:
        with cfg.logfile.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(zeile)
    except OSError as exc:
        print(f"FEHLER: Log nicht schreibbar: {exc}", file=sys.stderr)


def fuehre_sql(cfg: Laufzeit, sql: str, timeout: int = 60) -> tuple[int, str, str]:
    """Startet eine SQL-Anweisung ueber den Client.

    Parameter: cfg, sql, timeout – Sekunden
    Rueckgabe: (rc, stdout, stderr)
    Fehlerfaelle: Timeout und OSError als rc 1
    Beispiel: fuehre_sql(cfg, "SELECT 1")
    """
    cmd = [
        str(cfg.client),
        "-h",
        cfg.host,
        "-P",
        str(cfg.port),
        "-u",
        cfg.user,
        "--protocol=TCP",
        "--batch",
        "--raw",
        "--connect-timeout=30",
        *cfg.ssl_flags,
        "-e",
        sql,
    ]
    try:
        fertig = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=client_env(cfg.password),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "", f"Timeout nach {timeout}s"
    except OSError as exc:
        return 1, "", str(exc)
    return fertig.returncode, fertig.stdout or "", fertig.stderr or ""


def probe_ssl(cfg: Laufzeit) -> tuple[str, ...]:
    """Findet ein SSL-Flag, mit dem SELECT 1 klappt.

    Parameter: cfg – noch ohne ssl_flags
    Rueckgabe: Extra-Argumente (kann leer sein)
    Fehlerfaelle: keine (leeres Tupel als Fallback)
    Beispiel: probe_ssl(cfg)
    """
    for flags in SSL_FLAGS:
        test = Laufzeit(**{**cfg.__dict__, "ssl_flags": flags})
        rc, _out, err = fuehre_sql(test, "SELECT 1", timeout=20)
        if rc == 0:
            return flags
        low = err.lower()
        if "unknown option" in low or "invalid option" in low:
            continue
    return ()


def liste_binlogs(cfg: Laufzeit) -> list[tuple[str, int]]:
    """Liest SHOW BINARY LOGS.

    Parameter: cfg
    Rueckgabe: (Name, Groesse) in Index-Reihenfolge
    Fehlerfaelle: RuntimeError bei Clientfehler
    Beispiel: liste_binlogs(cfg)
    """
    rc, out, err = fuehre_sql(cfg, "SHOW BINARY LOGS")
    if rc != 0:
        raise RuntimeError(err.strip() or "SHOW BINARY LOGS fehlgeschlagen")
    logs: list[tuple[str, int]] = []
    for rec in parse_tsv(out):
        name = rec.get("Log_name") or rec.get("Log_Name") or ""
        groesse = rec.get("File_size") or rec.get("File_Size") or "0"
        if not name:
            continue
        try:
            logs.append((sicherer_logname(name), int(groesse)))
        except ValueError:
            continue
    return logs


def aktuelles_log(cfg: Laufzeit, logs: list[tuple[str, int]]) -> str:
    """Ermittelt das aktive Binlog (STATUS, sonst letzte Indexzeile).

    Parameter: cfg, logs – bereits gelesene Liste
    Rueckgabe: Dateiname
    Fehlerfaelle: RuntimeError wenn nichts da ist
    Beispiel: aktuelles_log(cfg, logs)
    """
    for sql in ("SHOW BINARY LOG STATUS", "SHOW MASTER STATUS"):
        rc, out, _err = fuehre_sql(cfg, sql)
        if rc != 0 or not out.strip():
            continue
        recs = parse_tsv(out)
        if recs:
            datei = recs[0].get("File") or recs[0].get("Log_name") or ""
            if datei:
                return sicherer_logname(datei)
    if not logs:
        raise RuntimeError("Keine Binlogs vorhanden.")
    return logs[-1][0]


def batch_ziele(logs: list[str], aktuell: str, batch: int) -> list[str]:
    """Liefert PURGE-TO-Ziele vor dem aktiven Log.

    Parameter: logs – Namen in Index-Reihenfolge; aktuell; batch
    Rueckgabe: Zielnamen, zuletzt immer aktuell
    Fehlerfaelle: keine
    Beispiel: batch_ziele(["mysql-bin.000001", "mysql-bin.000002"], "mysql-bin.000002", 50)
    """
    vor = [n for n in logs if n != aktuell]
    if not vor:
        return []
    ziele: list[str] = []
    schritt = max(1, batch)
    for index in range(schritt - 1, len(vor), schritt):
        ziele.append(vor[index])
    if vor[-1] not in ziele:
        ziele.append(vor[-1])
    if aktuell not in ziele:
        ziele.append(aktuell)
    return ziele


def verbindungs_hinweis(err: str) -> str:
    """Erklaert typische Connect-Fehler.

    Parameter: err – stderr
    Rueckgabe: naechster Schritt
    Fehlerfaelle: keine
    Beispiel: verbindungs_hinweis("Can't connect")
    """
    low = err.lower()
    if "can't connect" in low or "cannot connect" in low or "connect" in low:
        return (
            "Naechster Schritt: DigiKam oeffnen, damit der Internal Server "
            "auf Port 3307 laeuft, dann erneut aufrufen."
        )
    return "Naechster Schritt: Host, Port und --client pruefen (siehe --help)."


def bestaetigen(cfg: Laufzeit, anzahl: int, bytes_zahl: int) -> bool:
    """Fragt vor dem Loeschen, ausser --yes.

    Parameter: cfg, anzahl, bytes_zahl
    Rueckgabe: True wenn geloescht werden darf
    Fehlerfaelle: keine
    Beispiel: bestaetigen(cfg, 10, 1000)
    """
    if cfg.yes:
        return True
    gb = bytes_zahl / (1024**3)
    print(
        f"Es werden bis zu {anzahl} Binlogs (ca. {gb:.1f} GB) geloescht. "
        "Das ist unwiderruflich."
    )
    print('Bitte "j" bestaetigen oder --yes verwenden.')
    try:
        antwort = input("Loeschen? [j/N] ").strip().lower()
    except EOFError:
        return False
    return antwort in {"j", "ja", "y", "yes"}


def warte_auf_ende() -> None:
    """Wartet auf Taste oder Enter.

    Parameter: keine
    Rueckgabe: None
    Fehlerfaelle: EOF zaehlt als Enter
    Beispiel: warte_auf_ende()
    """
    print(END_PROMPT)
    try:
        input()
    except EOFError:
        return


def baue_parser() -> AufrufParser:
    """Erzeugt den CLI-Parser ohne automatische Hilfe.

    Parameter: keine
    Rueckgabe: Parser
    Fehlerfaelle: keine
    Beispiel: baue_parser()
    """
    parser = AufrufParser(add_help=False)
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default="")
    parser.add_argument("--client", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--reset-master", action="store_true")
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--logfile", type=Path, default=Path(DEFAULT_LOGFILE))
    parser.add_argument("--Ende", "-E", action="store_true")
    return parser


def pruefe_werte(ns: argparse.Namespace) -> str | None:
    """Prueft Port und Batch.

    Parameter: ns – geparste Argumente
    Rueckgabe: Fehlertext oder None
    Fehlerfaelle: keine
    Beispiel: pruefe_werte(ns)
    """
    if ns.port < 1 or ns.port > 65535:
        return "Port muss zwischen 1 und 65535 liegen."
    if ns.batch < 1:
        return "--batch muss >= 1 sein."
    return None


def zu_viele_altlogs(logs: list[tuple[str, int]], aktuell: str) -> bool:
    """Prueft, ob nach dem Purge noch Alt-Logs stehen.

    Parameter: logs – SHOW BINARY LOGS; aktuell – aktives Log
    Rueckgabe: True wenn mindestens ein Log neben dem aktiven bleibt
    Fehlerfaelle: keine
    Beispiel: zu_viele_altlogs([("mysql-bin.000001", 1)], "mysql-bin.000002")
    """
    return any(name != aktuell for name, _groesse in logs)


def aktiviere_standalone_purge(cfg: Laufzeit) -> None:
    """Hebt die Replikat-Sperre fuer PURGE auf (MariaDB 11.4+ / 12).

    Parameter: cfg
    Rueckgabe: None
    Fehlerfaelle: unbekannte Variable wird ignoriert (aeltere Server)
    Beispiel: aktiviere_standalone_purge(cfg)
    """
    print(SQL_PURGE_REPLIKATE_AUS)
    schreibe_log(cfg, SQL_PURGE_REPLIKATE_AUS)
    rc, _out, err = fuehre_sql(cfg, SQL_PURGE_REPLIKATE_AUS, timeout=30)
    if rc != 0:
        text = err.lower()
        if "unknown" in text or "does not exist" in text:
            return
        print(f"Hinweis: {err.strip()}")
        return
    print("Standalone: PURGE ohne Replikat-Verbindung erlaubt.")


def drucke_rest(logs: list[tuple[str, int]]) -> None:
    """Gibt eine kurze Restliste aus, nicht hunderte Zeilen.

    Parameter: logs
    Rueckgabe: None
    Fehlerfaelle: keine
    Beispiel: drucke_rest([("mysql-bin.000010", 10)])
    """
    print(f"Verbleibende Binlogs: {len(logs)}")
    if len(logs) <= 6:
        for name, groesse in logs:
            print(f"  {name}\t{groesse}")
        return
    for name, groesse in logs[:2]:
        print(f"  {name}\t{groesse}")
    print("  ...")
    for name, groesse in logs[-2:]:
        print(f"  {name}\t{groesse}")


def purge_einmal(cfg: Laufzeit, sql: str) -> tuple[int, str]:
    """Fuehrt ein PURGE/FLUSH aus und protokolliert.

    Parameter: cfg, sql
    Rueckgabe: (rc, stderr)
    Fehlerfaelle: Clientfehler als rc != 0
    Beispiel: purge_einmal(cfg, SQL_FLUSH)
    """
    print(sql)
    schreibe_log(cfg, f"SQL {sql}")
    rc, _out, err = fuehre_sql(cfg, sql, timeout=CLIENT_TIMEOUT_S)
    if rc != 0:
        schreibe_log(cfg, f"FEHLER {err.strip()}")
    return rc, err


def purge_mit_fallback(cfg: Laufzeit, aktuell: str, logs: list[str]) -> tuple[int, str]:
    """PURGE TO aktuelles Log, sonst BEFORE NOW, bei 'in use' Chargen.

    Parameter: cfg, aktuell – aktives Log, logs – alle Namen
    Rueckgabe: letzter (rc, stderr)
    Fehlerfaelle: Datei-in-Verwendung wird abgefangen
    Beispiel: purge_mit_fallback(cfg, "mysql-bin.000010", names)
    """
    rc, err = purge_einmal(cfg, sql_purge_to(aktuell))
    if rc == 0:
        return rc, err
    print("Hinweis: PURGE TO blockiert – versuche BEFORE NOW().")
    rc, err = purge_einmal(cfg, SQL_PURGE_NOW)
    if rc == 0:
        return rc, err
    if parse_in_use_name(err) is None and "in use" not in err.lower():
        return rc, err
    print("Hinweis: Datei in Verwendung – Fallback PURGE TO in Chargen.")
    schreibe_log(cfg, f"Fallback nach in-use: {err.strip()}")
    for _versuch in range(MAX_VERSUCHE):
        rc, err = purge_einmal(cfg, sql_purge_to(aktuell))
        if rc == 0:
            return rc, err
        time.sleep(RETRY_PAUSE_S)
    letzter = (rc, err)
    for ziel in batch_ziele(logs, aktuell, cfg.batch):
        for _versuch in range(MAX_VERSUCHE):
            letzter = purge_einmal(cfg, sql_purge_to(ziel))
            if letzter[0] == 0:
                break
            if parse_in_use_name(letzter[1]) is None:
                return letzter
            time.sleep(RETRY_PAUSE_S)
        else:
            return letzter
    return letzter


def fachlauf(cfg: Laufzeit) -> int:
    """Rotiert das aktive Log und purged den Altbestand.

    Parameter: cfg
    Rueckgabe: Exit-Code 0 oder 1
    Fehlerfaelle: Server weg, PURGE schlaegt fehl
    Beispiel: fachlauf(cfg)
    """
    rc, _out, err = fuehre_sql(cfg, "SELECT 1", timeout=20)
    if rc != 0:
        print(f"FEHLER: Keine Verbindung zu {cfg.host}:{cfg.port}. {err.strip()}", file=sys.stderr)
        print(verbindungs_hinweis(err), file=sys.stderr)
        return 1
    try:
        logs = liste_binlogs(cfg)
        aktuell = aktuelles_log(cfg, logs)
    except (RuntimeError, ValueError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        print("Naechster Schritt: SHOW BINARY LOGS in HeidiSQL pruefen.", file=sys.stderr)
        return 1
    namen = [n for n, _s in logs]
    bytes_zahl = sum(s for n, s in logs if n != aktuell)
    print(f"Binlogs: {len(logs)} Dateien, aktiv: {aktuell}")
    if cfg.dry_run:
        print(SQL_PURGE_REPLIKATE_AUS)
        print(SQL_FLUSH)
        print(sql_purge_to(aktuell))
        print(SQL_PURGE_NOW)
        if cfg.reset_master:
            print("RESET MASTER")
        return 0
    if not bestaetigen(cfg, max(0, len(logs) - 1), bytes_zahl):
        print("FEHLER: Loeschen nicht bestaetigt. --yes verwenden.", file=sys.stderr)
        return 2
    aktiviere_standalone_purge(cfg)
    rc, err = purge_einmal(cfg, SQL_FLUSH)
    if rc != 0:
        print(f"FEHLER: FLUSH BINARY LOGS: {err.strip()}", file=sys.stderr)
        print("Naechster Schritt: Serverlauf und SUPER/BINLOG ADMIN pruefen.", file=sys.stderr)
        return 1
    time.sleep(1.0)
    try:
        logs = liste_binlogs(cfg)
        aktuell = aktuelles_log(cfg, logs)
    except (RuntimeError, ValueError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1
    namen = [n for n, _s in logs]
    rc, err = purge_mit_fallback(cfg, aktuell, namen)
    if rc == 0:
        rest_check = liste_binlogs(cfg)
        aktuell_check = aktuelles_log(cfg, rest_check)
        if zu_viele_altlogs(rest_check, aktuell_check):
            print("PURGE lieferte Erfolg, Alt-Logs bleiben (MariaDB-Sperre).")
            aktiviere_standalone_purge(cfg)
            rc, err = purge_einmal(cfg, sql_purge_to(aktuell_check))
            rest_check = liste_binlogs(cfg)
            aktuell_check = aktuelles_log(cfg, rest_check)
            if zu_viele_altlogs(rest_check, aktuell_check):
                rc = 1
                err = "Alt-Logs nach PURGE noch vorhanden."
    if rc != 0 and cfg.reset_master:
        print("PURGE weiter blockiert – RESET MASTER (kein Replikat noetig).")
        rc, err = purge_einmal(cfg, "RESET MASTER")
    if rc != 0:
        print(f"FEHLER: PURGE: {err.strip()}", file=sys.stderr)
        print(
            "Naechster Schritt: python binlog_purge.py --yes --reset-master "
            "(keine Replikation). Dauerhaft in my.ini: "
            "slave_connections_needed_for_purge=0",
            file=sys.stderr,
        )
        return 1
    rest = liste_binlogs(cfg)
    print("Fertig.")
    drucke_rest(rest)
    print("Dauerhaft in db_data\\my.ini unter [mysqld]:")
    print("slave_connections_needed_for_purge=0")
    schreibe_log(cfg, f"Rest {len(rest)}")
    return 0


def _ausgabe_ist_terminal() -> bool:
    """Meldet, ob stdout ein Terminal ist.

    Parameter: keine
    Rueckgabe: True bei einem Terminal
    Fehlerfaelle: fehlende isatty-Methode gilt als kein Terminal
    Beispiel: _ausgabe_ist_terminal()
    """
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def schreibe_startausgabe() -> None:
    """Gibt Kurzname, Zweck und Version vor dem Fachlauf aus.

    Parameter: keine
    Rueckgabe: None
    Fehlerfaelle: keine
    Beispiel: schreibe_startausgabe()
    """
    if sys.platform == "win32":
        os.system("")
    innen = f"  {PROJECT_NAME}  "
    linie = "═" * len(innen)
    farbe = "\033[34m" if _ausgabe_ist_terminal() else ""
    aus = "\033[0m" if farbe else ""
    print(f"{farbe}╔{linie}╗{aus}")
    print(f"{farbe}║{innen}║{aus}")
    print(f"{farbe}╚{linie}╝{aus}")
    print(BESCHREIBUNG)
    print()
    print(f"Version {__version__}  |  {__date__}")
    print()


def pruefe_plattform() -> bool:
    """Prüft Windows und Linux vor dem Fachlauf.

    Parameter: keine
    Rueckgabe: True, wenn das System erlaubt ist
    Fehlerfaelle: eine Zeile auf stderr und False
    Beispiel: pruefe_plattform()
    """
    system = platform.system()
    if system in {"Windows", "Linux"}:
        return True
    print(
        "FEHLER: Dieses Programm läuft unter Windows 11 und Linux "
        f"(erkannt: {system}).",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI-Einstieg.

    Parameter: argv – ohne Programmname, sonst sys.argv[1:]
    Rueckgabe: 0 Erfolg, 1 Laufzeit, 2 Aufruf
    Fehlerfaelle: Optionen, fehlender Client, Server
    Beispiel: main(["--help"])
    """
    if argv is None:
        argv = sys.argv[1:]
    ns = baue_parser().parse_args(argv)
    if ns.help:
        code = zeige_hilfe()
    elif ns.version:
        code = zeige_version()
    else:
        fehler = pruefe_werte(ns)
        if fehler:
            print(f"FEHLER: {fehler} (siehe --help)", file=sys.stderr)
            code = 2
        else:
            schreibe_startausgabe()
            if not pruefe_plattform():
                code = 1
            else:
                check_runtime()
                client = finde_client(ns.client)
                if client is None:
                    print("FEHLER: MariaDB-Client nicht gefunden.", file=sys.stderr)
                    print(f"Naechster Schritt: {README_CLIENT_WIN}", file=sys.stderr)
                    print(f"Linux: {README_CLIENT_DEB}", file=sys.stderr)
                    code = 1
                else:
                    cfg = Laufzeit(
                        host=ns.host,
                        port=ns.port,
                        user=ns.user,
                        password=ns.password,
                        client=client,
                        ssl_flags=(),
                        dry_run=ns.dry_run,
                        yes=ns.yes,
                        reset_master=ns.reset_master,
                        log_an=ns.log,
                        logfile=ns.logfile,
                        batch=ns.batch,
                    )
                    cfg.ssl_flags = probe_ssl(cfg)
                    code = fachlauf(cfg)
    if ns.Ende:
        warte_auf_ende()
    return code


if __name__ == "__main__":
    sys.exit(main())
