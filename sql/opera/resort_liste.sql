-- resort_liste.sql — Welche Hotelcodes gibt es in dieser OPERA-Datenbank?
-- Bindvariablen: keine
--
-- Fuer den Verbindungstest der Konfigurationsseite: Steht der eingetragene
-- Hotelcode (property.resort) nicht darunter, nennt die Meldung die
-- vorhandenen. In einer Multiproperty-Datenbank liegen mehrere Haeuser, dazu
-- oft eine Reservierungszentrale und Demo-Mandanten. Je Hotelcode laeuft eine
-- eigene Installation der Anwendung.
SELECT r.resort,
       r.name
  FROM @SCHEMA@.resort r
 ORDER BY r.resort
