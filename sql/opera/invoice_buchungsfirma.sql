-- invoice_buchungsfirma.sql — welche Firma haengt an der Buchung?
-- Bindvariablen: :bill_no, :resort
--
-- Beantwortet die Frage, die bei der Sichtpruefung zaehlt: Der Beleg traegt
-- einen Firmennamen — gehoert die Rechnung deshalb der Firma, oder hat der
-- Gast selbst bezahlt?
--
-- Belegt an einer Live-DB: Von den Rechnungen mit Firmenname und
-- Privatprofil als Zahler hatte AUSNAHMSLOS jede eine COMPANY_ID an der Reservierung,
-- und das verknuepfte Profil ist in allen Faellen vom Typ COMPANY. COMPANY_NAME
-- auf dem Beleg stammt also aus der Firmenverknuepfung der RESERVIERUNG, nicht
-- aus dem Profil des Rechnungsempfaengers.
--
-- ACHTUNG PERFORMANCE: NAME_RESERVATION ist eine View ueber rund 1 Mio. Zeilen.
-- Diese Abfrage laeuft deshalb NUR auf der Detailseite fuer eine einzelne
-- Rechnung — niemals in der Liste oder in einer Schleife.

SELECT r.resv_name_id,
       r.company_id,
       f.company_name                       AS firmenname_beleg,
       COALESCE(c.company, c.legal_company, TRIM(TRIM(c."LAST") || CASE WHEN c."FIRST" IS NOT NULL THEN ', ' || c."FIRST" END))                               AS firma_profil,
       c.name_type                           AS firma_typ,
       r.travel_agent_id,
       COALESCE(t.company, t.legal_company, TRIM(TRIM(t."LAST") || CASE WHEN t."FIRST" IS NOT NULL THEN ', ' || t."FIRST" END))                               AS reisebuero,
       r.group_id,
       COALESCE(g.company, g.legal_company, TRIM(TRIM(g."LAST") || CASE WHEN g."FIRST" IS NOT NULL THEN ', ' || g."FIRST" END))                               AS gruppe,
       -- Zahler zum Vergleich
       NVL(f.payee_name_id, f.name_id)      AS zahler_name_id,
       z.name_type                          AS zahler_typ,
       -- Zahlungsart: ein Debitorenkonto bekommt keine Privatperson
       NVL(f.clpay, 0)                      AS city_ledger,
       NVL(f.ccpay, 0)                      AS karte,
       NVL(f.cashpay, 0)                    AS bar,
       f.account_code
  FROM @SCHEMA@.folio$_tax f
  LEFT JOIN @SCHEMA@.name_reservation r ON r.resv_name_id = f.resv_name_id
  LEFT JOIN @SCHEMA@.name c ON c.name_id = r.company_id
  LEFT JOIN @SCHEMA@.name t ON t.name_id = r.travel_agent_id
  LEFT JOIN @SCHEMA@.name g ON g.name_id = r.group_id
  LEFT JOIN @SCHEMA@.name z ON z.name_id = NVL(f.payee_name_id, f.name_id)
 WHERE f.bill_no = :bill_no
   AND f.resort  = :resort
