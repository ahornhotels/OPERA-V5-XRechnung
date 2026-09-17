-- profil_udf.sql — ein benutzerdefiniertes Feld der Kartei lesen
-- Bindvariable: :name_id
-- Der SPALTENNAME wird in app/opera.py eingesetzt, nicht gebunden — Oracle
-- laesst Spaltennamen nicht als Bindvariable zu. Erlaubt sind ausschliesslich
-- UDFC01..UDFC40; alles andere lehnt die Anwendung ab, bevor die Abfrage
-- entsteht. Deshalb ist diese Datei eine Vorlage mit @SPALTE@ und keine
-- fertige Abfrage.
--
-- Warum ueberhaupt: Die Leitweg-ID gehoert an die FIRMENkartei. OPERA bietet
-- Mitgliedschaften aber nur an der Individualkartei an — von 130.846
-- Mitgliedschaften liegt keine einzige auf einer Firmenkartei.
-- Ein benutzerdefiniertes Feld auf ACC_MAIN ist der einzige Traeger, der an
-- der richtigen Kartei sichtbar UND lang genug ist (VARCHAR2(200); eine
-- Leitweg-ID darf 46 Zeichen haben).

SELECT TRIM(n.@SPALTE@) AS wert
  FROM @SCHEMA@.name n
 WHERE n.name_id = :name_id
