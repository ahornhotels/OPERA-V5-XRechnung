-- udf_uebersicht.sql — welche benutzerdefinierten Felder der Kartei sind frei?
-- Bindvariablen: keine
--
-- Fuer die Einrichtung: Sie beantwortet zwei Fragen auf einmal.
--   1. Ist das Feld an der FIRMENkartei ueberhaupt sichtbar? (DYNAMIC_FIELDS)
--   2. Steht dort schon etwas drin? (NAME)
--
-- Beides zaehlt. Ein freies Feld, das auf keinem Formular steht, kann niemand
-- pflegen; ein sichtbares Feld, in dem schon Werte stehen, waere Diebstahl an
-- einer bestehenden Verwendung.
--
-- ACHTUNG, LAUFZEIT: Die Zaehlung geht ueber alle Firmenkarteien (rund 114.000
-- in diesem Haus) und laeuft ohne Index. Sie gehoert auf Knopfdruck in die
-- Einrichtung, nicht in den Seitenaufbau.
--
-- ACC_MAIN ist das Formular der Firmen-/Debitorenkartei, PROFILE das der
-- Individualkartei. Verwechselt man beides, landet das Kennzeichen an der
-- Gastkartei — dort, wo es fuer Firmenrechnungen nichts nuetzt.

WITH beschriftung AS (
    SELECT UPPER(TRIM(df.dbcolumnname)) AS spalte,
           MAX(df.form_name)            AS formular,
           MAX(df.block_name)           AS block,
           MAX(df.prompt)               AS beschriftung,
           MAX(NVL(df.displayed_yn, 'N')) AS sichtbar
      FROM @SCHEMA@.dynamic_fields df
     WHERE UPPER(TRIM(df.dbcolumnname)) LIKE 'UDFC%'
       AND df.form_name = 'ACC_MAIN'
     GROUP BY UPPER(TRIM(df.dbcolumnname))
),
belegung AS (
    SELECT COUNT(n.udfc01) AS udfc01, COUNT(n.udfc02) AS udfc02,
           COUNT(n.udfc03) AS udfc03, COUNT(n.udfc04) AS udfc04,
           COUNT(n.udfc05) AS udfc05, COUNT(n.udfc06) AS udfc06,
           COUNT(n.udfc07) AS udfc07, COUNT(n.udfc08) AS udfc08,
           COUNT(n.udfc09) AS udfc09, COUNT(n.udfc10) AS udfc10,
           COUNT(n.udfc11) AS udfc11, COUNT(n.udfc12) AS udfc12,
           COUNT(n.udfc13) AS udfc13, COUNT(n.udfc14) AS udfc14,
           COUNT(n.udfc15) AS udfc15, COUNT(n.udfc16) AS udfc16,
           COUNT(n.udfc17) AS udfc17, COUNT(n.udfc18) AS udfc18,
           COUNT(n.udfc19) AS udfc19, COUNT(n.udfc20) AS udfc20,
           COUNT(*)        AS karteien
      FROM @SCHEMA@.name n
     WHERE n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S')
)
SELECT s.spalte,
       b.beschriftung,
       b.formular,
       b.block,
       NVL(b.sichtbar, 'N')                              AS sichtbar,
       CASE s.spalte
         WHEN 'UDFC01' THEN g.udfc01 WHEN 'UDFC02' THEN g.udfc02
         WHEN 'UDFC03' THEN g.udfc03 WHEN 'UDFC04' THEN g.udfc04
         WHEN 'UDFC05' THEN g.udfc05 WHEN 'UDFC06' THEN g.udfc06
         WHEN 'UDFC07' THEN g.udfc07 WHEN 'UDFC08' THEN g.udfc08
         WHEN 'UDFC09' THEN g.udfc09 WHEN 'UDFC10' THEN g.udfc10
         WHEN 'UDFC11' THEN g.udfc11 WHEN 'UDFC12' THEN g.udfc12
         WHEN 'UDFC13' THEN g.udfc13 WHEN 'UDFC14' THEN g.udfc14
         WHEN 'UDFC15' THEN g.udfc15 WHEN 'UDFC16' THEN g.udfc16
         WHEN 'UDFC17' THEN g.udfc17 WHEN 'UDFC18' THEN g.udfc18
         WHEN 'UDFC19' THEN g.udfc19 WHEN 'UDFC20' THEN g.udfc20
       END                                               AS belegt,
       g.karteien
  FROM (SELECT 'UDFC' || LPAD(LEVEL, 2, '0') AS spalte
          FROM dual CONNECT BY LEVEL <= 20) s
  LEFT JOIN beschriftung b ON b.spalte = s.spalte
  CROSS JOIN belegung g
 ORDER BY s.spalte
