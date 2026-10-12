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
-- BELEGT HEISST: IN IRGENDEINER KARTEI. NAME.UDFCnn ist EINE Spalte fuer
-- alle Profiltypen. Bis zum 12.10.2026 zaehlte die Abfrage nur Firmen-,
-- Reisebuero-, Gruppen- und Quellkarteien — und zeigte zehn Felder als "frei",
-- die an Gastkarteien (name_type 'D') produktiv beschrieben werden, eines mit
-- 183.579 Werten (gemessen an der Live-DB). Wer so ein Feld fuer die Firmenkartei
-- einrichtet, teilt sich die Spalte mit dem, was dort schon schreibt. Deshalb
-- zwei Zahlen: belegt (Firmenkarteien, zur Orientierung) und belegt_gesamt
-- (alle Profile) — nur die zweite entscheidet, ob ein Feld frei ist.
-- Laufzeit ueber alle 1,1 Mio. Profile: 8,8 s (gemessen am 12.10.2026) — auf Knopfdruck vertretbar.
--
-- ALLE 40 FELDER: NAME fuehrt UDFC01..UDFC40, und so viele nimmt die
-- Anwendung auch an (opera.UDF_SPALTEN). Bis zum 12.10.2026 endete die Liste
-- bei UDFC20 — UDFC39 ("C/O Ref.", an der Firmenkartei in Gebrauch) fehlte
-- stillschweigend, genau auf der Seite, auf der man ein freies Feld waehlt.
-- Gezaehlt wird TRIM(), damit ein Feld nur aus Leerzeichen nicht als belegt
-- gilt.
--
-- ACHTUNG, LAUFZEIT: Die Zaehlung geht ueber alle Firmenkarteien (rund 114.000
-- in diesem Haus) und laeuft ohne Index. Sie gehoert auf Knopfdruck in die
-- Einrichtung, nicht in den Seitenaufbau.
--
-- ACC_MAIN ist das Formular der Firmen-/Debitorenkartei, PROFILE das der
-- Individualkartei. Verwechselt man beides, landet das Kennzeichen an der
-- Gastkartei — dort, wo es fuer Firmenrechnungen nichts nuetzt.

--
-- SPALTENNAME MIT ZUSATZ: Liegt ein Feld auf einem zweiten Reiter der Maske,
-- traegt DBCOLUMNNAME einen Zusatz — gemessen am 12.10.2026: UDFC05 auf dem
-- "More"-Reiter heisst 'UDFC05_TAB2', der Wert liegt trotzdem in NAME.UDFC05.
-- Vorher wurde der volle Name verglichen; das eingerichtete Feld erschien
-- dann als "nicht eingerichtet, frei — geeignet". Deshalb zaehlt nur der
-- Stamm UDFCnn. Die unsichtbaren Hilfsitems (*_IB) haben keine Beschriftung
-- und kein DISPLAYED_YN = 'Y'; MAX() laesst sie hinter dem sichtbaren Item.
WITH beschriftung AS (
    SELECT REGEXP_SUBSTR(UPPER(TRIM(df.dbcolumnname)), '^UDFC[0-9]{2}') AS spalte,
           MAX(df.form_name)            AS formular,
           MAX(df.block_name)           AS block,
           MAX(df.prompt)               AS beschriftung,
           MAX(NVL(df.displayed_yn, 'N')) AS sichtbar
      FROM @SCHEMA@.dynamic_fields df
     WHERE REGEXP_SUBSTR(UPPER(TRIM(df.dbcolumnname)), '^UDFC[0-9]{2}') IS NOT NULL
       AND df.form_name = 'ACC_MAIN'
     GROUP BY REGEXP_SUBSTR(UPPER(TRIM(df.dbcolumnname)), '^UDFC[0-9]{2}')
),
belegung AS (
    SELECT COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc01) END) AS f01, COUNT(TRIM(n.udfc01)) AS g01,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc02) END) AS f02, COUNT(TRIM(n.udfc02)) AS g02,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc03) END) AS f03, COUNT(TRIM(n.udfc03)) AS g03,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc04) END) AS f04, COUNT(TRIM(n.udfc04)) AS g04,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc05) END) AS f05, COUNT(TRIM(n.udfc05)) AS g05,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc06) END) AS f06, COUNT(TRIM(n.udfc06)) AS g06,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc07) END) AS f07, COUNT(TRIM(n.udfc07)) AS g07,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc08) END) AS f08, COUNT(TRIM(n.udfc08)) AS g08,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc09) END) AS f09, COUNT(TRIM(n.udfc09)) AS g09,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc10) END) AS f10, COUNT(TRIM(n.udfc10)) AS g10,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc11) END) AS f11, COUNT(TRIM(n.udfc11)) AS g11,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc12) END) AS f12, COUNT(TRIM(n.udfc12)) AS g12,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc13) END) AS f13, COUNT(TRIM(n.udfc13)) AS g13,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc14) END) AS f14, COUNT(TRIM(n.udfc14)) AS g14,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc15) END) AS f15, COUNT(TRIM(n.udfc15)) AS g15,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc16) END) AS f16, COUNT(TRIM(n.udfc16)) AS g16,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc17) END) AS f17, COUNT(TRIM(n.udfc17)) AS g17,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc18) END) AS f18, COUNT(TRIM(n.udfc18)) AS g18,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc19) END) AS f19, COUNT(TRIM(n.udfc19)) AS g19,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc20) END) AS f20, COUNT(TRIM(n.udfc20)) AS g20,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc21) END) AS f21, COUNT(TRIM(n.udfc21)) AS g21,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc22) END) AS f22, COUNT(TRIM(n.udfc22)) AS g22,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc23) END) AS f23, COUNT(TRIM(n.udfc23)) AS g23,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc24) END) AS f24, COUNT(TRIM(n.udfc24)) AS g24,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc25) END) AS f25, COUNT(TRIM(n.udfc25)) AS g25,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc26) END) AS f26, COUNT(TRIM(n.udfc26)) AS g26,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc27) END) AS f27, COUNT(TRIM(n.udfc27)) AS g27,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc28) END) AS f28, COUNT(TRIM(n.udfc28)) AS g28,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc29) END) AS f29, COUNT(TRIM(n.udfc29)) AS g29,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc30) END) AS f30, COUNT(TRIM(n.udfc30)) AS g30,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc31) END) AS f31, COUNT(TRIM(n.udfc31)) AS g31,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc32) END) AS f32, COUNT(TRIM(n.udfc32)) AS g32,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc33) END) AS f33, COUNT(TRIM(n.udfc33)) AS g33,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc34) END) AS f34, COUNT(TRIM(n.udfc34)) AS g34,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc35) END) AS f35, COUNT(TRIM(n.udfc35)) AS g35,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc36) END) AS f36, COUNT(TRIM(n.udfc36)) AS g36,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc37) END) AS f37, COUNT(TRIM(n.udfc37)) AS g37,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc38) END) AS f38, COUNT(TRIM(n.udfc38)) AS g38,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc39) END) AS f39, COUNT(TRIM(n.udfc39)) AS g39,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN TRIM(n.udfc40) END) AS f40, COUNT(TRIM(n.udfc40)) AS g40,
           COUNT(CASE WHEN n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') THEN 1 END) AS karteien,
           COUNT(*) AS profile_gesamt
      FROM @SCHEMA@.name n
)
SELECT s.spalte,
       b.beschriftung,
       b.formular,
       b.block,
       NVL(b.sichtbar, 'N')                              AS sichtbar,
       CASE s.spalte
         WHEN 'UDFC01' THEN g.f01
         WHEN 'UDFC02' THEN g.f02
         WHEN 'UDFC03' THEN g.f03
         WHEN 'UDFC04' THEN g.f04
         WHEN 'UDFC05' THEN g.f05
         WHEN 'UDFC06' THEN g.f06
         WHEN 'UDFC07' THEN g.f07
         WHEN 'UDFC08' THEN g.f08
         WHEN 'UDFC09' THEN g.f09
         WHEN 'UDFC10' THEN g.f10
         WHEN 'UDFC11' THEN g.f11
         WHEN 'UDFC12' THEN g.f12
         WHEN 'UDFC13' THEN g.f13
         WHEN 'UDFC14' THEN g.f14
         WHEN 'UDFC15' THEN g.f15
         WHEN 'UDFC16' THEN g.f16
         WHEN 'UDFC17' THEN g.f17
         WHEN 'UDFC18' THEN g.f18
         WHEN 'UDFC19' THEN g.f19
         WHEN 'UDFC20' THEN g.f20
         WHEN 'UDFC21' THEN g.f21
         WHEN 'UDFC22' THEN g.f22
         WHEN 'UDFC23' THEN g.f23
         WHEN 'UDFC24' THEN g.f24
         WHEN 'UDFC25' THEN g.f25
         WHEN 'UDFC26' THEN g.f26
         WHEN 'UDFC27' THEN g.f27
         WHEN 'UDFC28' THEN g.f28
         WHEN 'UDFC29' THEN g.f29
         WHEN 'UDFC30' THEN g.f30
         WHEN 'UDFC31' THEN g.f31
         WHEN 'UDFC32' THEN g.f32
         WHEN 'UDFC33' THEN g.f33
         WHEN 'UDFC34' THEN g.f34
         WHEN 'UDFC35' THEN g.f35
         WHEN 'UDFC36' THEN g.f36
         WHEN 'UDFC37' THEN g.f37
         WHEN 'UDFC38' THEN g.f38
         WHEN 'UDFC39' THEN g.f39
         WHEN 'UDFC40' THEN g.f40
       END AS belegt,
       CASE s.spalte
         WHEN 'UDFC01' THEN g.g01
         WHEN 'UDFC02' THEN g.g02
         WHEN 'UDFC03' THEN g.g03
         WHEN 'UDFC04' THEN g.g04
         WHEN 'UDFC05' THEN g.g05
         WHEN 'UDFC06' THEN g.g06
         WHEN 'UDFC07' THEN g.g07
         WHEN 'UDFC08' THEN g.g08
         WHEN 'UDFC09' THEN g.g09
         WHEN 'UDFC10' THEN g.g10
         WHEN 'UDFC11' THEN g.g11
         WHEN 'UDFC12' THEN g.g12
         WHEN 'UDFC13' THEN g.g13
         WHEN 'UDFC14' THEN g.g14
         WHEN 'UDFC15' THEN g.g15
         WHEN 'UDFC16' THEN g.g16
         WHEN 'UDFC17' THEN g.g17
         WHEN 'UDFC18' THEN g.g18
         WHEN 'UDFC19' THEN g.g19
         WHEN 'UDFC20' THEN g.g20
         WHEN 'UDFC21' THEN g.g21
         WHEN 'UDFC22' THEN g.g22
         WHEN 'UDFC23' THEN g.g23
         WHEN 'UDFC24' THEN g.g24
         WHEN 'UDFC25' THEN g.g25
         WHEN 'UDFC26' THEN g.g26
         WHEN 'UDFC27' THEN g.g27
         WHEN 'UDFC28' THEN g.g28
         WHEN 'UDFC29' THEN g.g29
         WHEN 'UDFC30' THEN g.g30
         WHEN 'UDFC31' THEN g.g31
         WHEN 'UDFC32' THEN g.g32
         WHEN 'UDFC33' THEN g.g33
         WHEN 'UDFC34' THEN g.g34
         WHEN 'UDFC35' THEN g.g35
         WHEN 'UDFC36' THEN g.g36
         WHEN 'UDFC37' THEN g.g37
         WHEN 'UDFC38' THEN g.g38
         WHEN 'UDFC39' THEN g.g39
         WHEN 'UDFC40' THEN g.g40
       END AS belegt_gesamt,
       g.karteien,
       g.profile_gesamt
  FROM (SELECT 'UDFC' || LPAD(LEVEL, 2, '0') AS spalte
          FROM dual CONNECT BY LEVEL <= 40) s
  LEFT JOIN beschriftung b ON b.spalte = s.spalte
  CROSS JOIN belegung g
 ORDER BY s.spalte
