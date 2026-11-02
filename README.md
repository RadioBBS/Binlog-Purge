# Binlog-Purge

```
Binlog-Purge – Löscht MariaDB-Binlogs per PURGE BINARY LOGS, nachdem das aktive Log rotiert wurde.

Projekt:     Binlog-Purge
Modul:       README.md
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
Das Programm soll die Binlogs löschen, das geht nur, wenn die DB läuft, daduch steht
diese aber auf den Binlogs. Siehe Zweck:

Historie
--------
Version 1.0.0 – 2026-09-03 – Erstausgabe: FLUSH, PURGE BEFORE NOW, Fallback PURGE TO
Version 1.1.0 – 2026-09-03 – slave_connections_needed_for_purge=0 vor PURGE
Version 1.1.1 – 2026-11-02 – Startausgabe und Python 3.11 nach Styleguide 2.1.0.

Aufruf / Nutzung
----------------
  python binlog_purge.py --help
  python binlog_purge.py --version
  python binlog_purge.py --dry-run
  python binlog_purge.py --yes
  python binlog_purge.py --host 127.0.0.1 --port 3307 --user root --yes
  python binlog_purge.py --yes --reset-master
```

## Zweck

Löscht MariaDB-Binlogs per PURGE BINARY LOGS, nachdem das aktive Log rotiert wurde.

`PURGE BINARY LOGS BEFORE NOW()` allein scheitert oft, weil `mysql-bin.000001` (oder das aktuelle Log) noch geschrieben wird. Das Programm macht deshalb zuerst `FLUSH BINARY LOGS` (neue Datei, alte Datei zu), dann `PURGE BINARY LOGS BEFORE NOW()`. Meldet der Server „is in use“, folgt `PURGE BINARY LOGS TO '<aktuelles Log>'` mit Wiederholung. Option `--reset-master` beginnt die Binlogs neu, wenn PURGE weiter blockiert (nur ohne Replikation).

## Voraussetzungen

- Python >= 3.11
- Laufender MariaDB-/MySQL-Server mit Binlogs (DigiKam: Internal Server, Port 3307, DigiKam muss offen sein)
- Client `mariadb` oder `mysql`

## Installation

Aufruf mit `python binlog_purge.py` – kein `chmod +x` noetig. Zeilenenden der Python-Dateien duerfen CRLF sein.

Windows: Client kommt mit MariaDB 12.3, extra Systempaket unnoetig, sofern der Server installiert ist.

Linux:

```bash
sudo apt-get install mariadb-client
```

Python-Pakete (Stdlib only, No-Op):

```bash
python -m pip install -r requirements.txt
```

Empfohlen:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Aufruf

```bash
python binlog_purge.py --help
python binlog_purge.py --version
python binlog_purge.py --dry-run
python binlog_purge.py --yes
python binlog_purge.py --host 127.0.0.1 --port 3307 --user root --yes
python binlog_purge.py --yes --reset-master
```

`--help` und `--version` brauchen keinen MariaDB-Client. Der Fachlauf schon; fehlt der Client: Exit 1 und dieser Installationshinweis.

`PURGE BINARY LOGS` allein reicht unter MariaDB 11.4+/12 nicht: der Default `slave_connections_needed_for_purge=1` blockiert das Loeschen ohne Replikat, der Server meldet trotzdem Erfolg. Das Programm setzt die Variable auf 0 und prueft danach die Restmenge.

Standard: Host `127.0.0.1`, Port `3307`, Benutzer `root`, leeres Passwort (DigiKam-Internal-Server mit `skip_grant_tables`). Alles per Parameter ueberschreibbar.

Client-Pfad, je Terminal (unverändert einfügen):

PowerShell:

```powershell
python binlog_purge.py --client "$env:ProgramFiles\MariaDB 12.3\bin\mariadb.exe" --yes
```

CMD:

```bat
python binlog_purge.py --client "%PROGRAMFILES%\MariaDB 12.3\bin\mariadb.exe" --yes
```

## Risiken

- Destruktiv: Binlogs sind danach weg. Ohne Replikate ist das gewollt. Bestaetigung oder `--yes`.
- `RESET MASTER` loescht alle Binlogs und startet die Nummerierung neu. Nicht nutzen, wenn Replikate den Stand brauchen.
- DigiKam waehrend des Purge nicht scannen lassen. 655 GB Loeschen kann Minuten dauern.
- Keine Passwoerter in dieses Repo schreiben.

## Test

```bash
python -m unittest tests.test_binlog_purge
```

SPDX-License-Identifier: MIT
