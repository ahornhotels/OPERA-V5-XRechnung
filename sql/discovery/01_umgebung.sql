-- 01_umgebung.sql — Grundinventur der OPERA-Datenbank (nur lesend)

PROMPT == Datenbank-Version ==
SELECT banner FROM v$version;

PROMPT == Schemas mit Objektzahl (Top 30) ==
SELECT owner, COUNT(*) objekte
  FROM all_objects
 WHERE owner NOT IN ('SYS','SYSTEM','XDB','MDSYS','CTXSYS','OLAPSYS','WMSYS',
                     'ORDSYS','EXFSYS','DBSNMP','OUTLN','APPQOSSYS','AUDSYS',
                     'GSMADMIN_INTERNAL','ORDDATA','LBACSYS','DVSYS','OJVMSYS')
 GROUP BY owner
 ORDER BY 2 DESC
 FETCH FIRST 30 ROWS ONLY;

PROMPT == Sprach-/Zahlformat-Einstellungen (wichtig fuer TO_CHAR der Betraege) ==
SELECT parameter, value FROM nls_database_parameters
 WHERE parameter IN ('NLS_CHARACTERSET','NLS_NUMERIC_CHARACTERS','NLS_DATE_FORMAT','NLS_LANGUAGE','NLS_TERRITORY');

PROMPT == Rechte des aktuellen Benutzers ==
SELECT * FROM session_privs ORDER BY 1;

PROMPT == Properties / Resorts (falls Tabelle vorhanden) ==
SELECT owner, table_name FROM all_tables
 WHERE table_name IN ('PROPERTY','RESORT','RESORTS','PROPERTIES')
 ORDER BY 1,2;
