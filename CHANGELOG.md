# Binlog-Purge – Aenderungsprotokoll.

Projekt:     Binlog-Purge
Modul:       CHANGELOG.md
Version:     1.0.0
Stand:       2026-09-03
Abhaengig:   Python >= 3.10; MariaDB-Client mariadb oder mysql
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
Version 1.0.0 – 2026-09-03 – Erstausgabe

Aufruf / Nutzung
----------------
  python binlog_purge.py --help
  python binlog_purge.py --version
  python binlog_purge.py --dry-run
  python binlog_purge.py --yes
  python binlog_purge.py --host 127.0.0.1 --port 3307 --user root --yes
  python binlog_purge.py --yes --reset-master

## 1.0.0 – 2026-09-03

- FLUSH BINARY LOGS, danach PURGE BINARY LOGS BEFORE NOW().
- Bei „is in use“: PURGE TO das aktive Log, optional RESET MASTER.
