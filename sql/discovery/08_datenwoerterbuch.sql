-- 08_datenwoerterbuch.sql — Datenwoerterbuch des OPERA-Schemas als Datei.
-- Nur lesend: ausschliesslich SELECT auf die Oracle-Katalogsichten (ALL_*).
-- Es wird KEIN Inhalt einer OPERA-Tabelle gelesen, nur deren Aufbau.
--
-- Wozu: Vor einer Installation in einem anderen Haus laesst sich damit
-- pruefen, ob dessen OPERA-Version alle Tabellen und Spalten hat, die die
-- Anwendung braucht — ohne Zugang zu dessen Datenbank. Die Datei geht an
-- den, der die Installation vorbereitet.
--
-- Aufruf (SQL*Plus, Benutzer mit Lesezugriff auf das OPERA-Schema):
--   DEFINE OPERA_OWNER = OPERA
--   @08_datenwoerterbuch.sql
-- Ergebnis: datenwoerterbuch_<schema>.csv im aktuellen Verzeichnis,
-- Trennzeichen Semikolon, eine Zeile je Spalte jeder Tabelle und View.
-- Dauer: einige Minuten (im bisherigen Haus 2,5 min fuer 217.000 Spalten);
-- Groesse: rund 13 MB.
--
-- Bewusst ohne SET MARKUP CSV (das kennt erst SQL*Plus 12.2): Die Zeile wird
-- selbst zusammengesetzt, Semikolons und Zeilenumbrueche in Kommentaren
-- werden ersetzt, damit jede Spalte genau eine Zeile bleibt. Kommentare sind
-- auf 1500 Zeichen gekuerzt: Eine Zeile ueber 4000 Zeichen bricht mit ORA-01489 ab.
-- Kommentare haengen an den Tabellen (..._E), nicht an den Views darueber.

-- LINESIZE 3300 und ARRAYSIZE 1000: gemessen 146 s statt 387 s, Datei
-- byte-gleich. Mit 4000 baut SQL*Plus je Zeile einen 4000-Zeichen-Puffer und
-- schneidet ihn wieder ab, mit der Standard-ARRAYSIZE 15 sind es rund 14.500
-- Rundreisen. 3300 reicht: zwei Kommentare zu je hoechstens 1500 Zeichen plus
-- unter 230 fuer den Rest; die laengste Zeile im bisherigen Haus hatte 602.
SET PAGESIZE 0 LINESIZE 3300 TRIMSPOOL ON FEEDBACK OFF HEADING OFF
SET ARRAYSIZE 1000
SET TERMOUT OFF VERIFY OFF ECHO OFF
SPOOL datenwoerterbuch_&&OPERA_OWNER..csv

SELECT 'objekt;objekttyp;spalte;position;datentyp;nullbar;pk_position;zeilen_statistik;kommentar_spalte;kommentar_objekt'
  FROM dual;

SELECT c.table_name
       || ';' || o.object_type
       || ';' || c.column_name
       || ';' || c.column_id
       || ';' || c.data_type
       || CASE WHEN c.data_type IN ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR')
               THEN '(' || c.char_length || ')'
               WHEN c.data_type = 'NUMBER' AND c.data_precision IS NOT NULL
               THEN '(' || c.data_precision || ',' || NVL(c.data_scale, 0) || ')' END
       || ';' || c.nullable
       || ';' || pk.position
       || ';' || t.num_rows
       || ';' || SUBSTR(REPLACE(REPLACE(REPLACE(cc.comments, ';', ','), CHR(10), ' '), CHR(13), ' '), 1, 1500)
       || ';' || SUBSTR(REPLACE(REPLACE(REPLACE(tc.comments, ';', ','), CHR(10), ' '), CHR(13), ' '), 1, 1500)
  FROM all_tab_columns c
  JOIN all_objects o
    ON o.owner = c.owner AND o.object_name = c.table_name
   AND o.object_type IN ('TABLE', 'VIEW')
  LEFT JOIN all_tables t
    ON t.owner = c.owner AND t.table_name = c.table_name
  LEFT JOIN all_col_comments cc
    ON cc.owner = c.owner AND cc.table_name = c.table_name AND cc.column_name = c.column_name
  LEFT JOIN all_tab_comments tc
    ON tc.owner = c.owner AND tc.table_name = c.table_name
  LEFT JOIN (SELECT k.owner, k.table_name, k.column_name, k.position
               FROM all_cons_columns k
               JOIN all_constraints p
                 ON p.owner = k.owner AND p.constraint_name = k.constraint_name
              WHERE p.constraint_type = 'P'
                AND k.owner = '&&OPERA_OWNER') pk
    ON pk.owner = c.owner AND pk.table_name = c.table_name AND pk.column_name = c.column_name
 WHERE c.owner = '&&OPERA_OWNER'
 ORDER BY c.table_name, c.column_id;

SPOOL OFF
SET TERMOUT ON FEEDBACK ON HEADING ON PAGESIZE 200
PROMPT Fertig: datenwoerterbuch_&&OPERA_OWNER..csv
