-- invoice_header.sql — Rechnungskopf nach Datenvertrag (docs/02_DATENVERTRAG.md)
-- Bindvariable: :bill_no
--
-- Die Leitweg-ID (BT-10) kommt aus einer Mitgliedschaft vom Typ 'LEITWEG' am
-- Kundenprofil — siehe docs/09_UDF_LEITWEG_ID.md.
--
-- Nicht aus OPERA zu holen und daher in der App zu ergaenzen:
--   duedate                (Zahlungsziel aus Config; AR$_ACCOUNT.PAYMENT_DUE_DAYS ist leer)
--   suppliercompanyid      (USt-IdNr., BT-31 — RESORT.VAT_ID ist leer)
--   payeefinancialaccount* (IBAN/BIC, BG-17 — siehe supplier_bank_udf als Abgleich)
--   suppliercontactname    (BT-41, Pflicht nach BR-DE-5)

SELECT f.bill_no                                              AS id,
       TO_CHAR(f.bill_generation_date, 'YYYY-MM-DD')          AS issuedate,
       TO_CHAR(NULL)                                          AS duedate,
       '380'                                                  AS invoicetypecode,
       r.currency_code                                        AS documentcurrencycode,
       -- BT-10 in Stufen. BR-DE-15 macht das Feld zur Pflicht, aber nur
       -- Behoerden haben eine Leitweg-ID — fuer gewoehnliche Firmenkunden ist
       -- jeder vereinbarte Wert zulaessig. Deshalb der Reihe nach:
       --   1. Leitweg-ID (Behoerde)
       --   2. vereinbarte Referenz aus der E-Rechnungs-Kennzeichnung
       --   3. FOLIO_TEXT1 — im Haus als Feld "Buyer Reference1" in die
       --      Reservierungsmaske gelegt. Das ist die Entscheidung des
       --      Hauses vom 09.09.2026: "wenn Leitweg existiert dann das
       --      nutzen, sonst Buyer Reference 1, sonst bisherige ResNr."
       --   4. EXTERNAL_REFERENCE an der Reservierung
       --   5. CUSTOM_REFERENCE — NUR wenn die Konfiguration es erlaubt
       --   6. NICHTS MEHR aus der Datenbank. Hier stand CONFIRMATION_NO, die
       --      Reservierungsnummer — ausnahmslos gefuellt. Genau deshalb erreichte
       --      die Kette in app/opera.py nie die Vorlage des Hauses
       --      (property.buyerreference_vorlage): BT-10 war nie leer. Die
       --      Reservierungsnummer steht weiter als eigene Spalte da und ist der
       --      Rueckfall der Vorlage.
       --
       -- ZU FOLIO_TEXT1: technisch das Folio-Textfeld, VARCHAR2(2000). Das
       -- Feld nimmt ganze Absaetze an; was daraus in BT-10 geht, wird in
       -- app/opera.py gekuerzt und der Umstand vermerkt. Im Gesamtbestand
       -- waren 0 von 1.518.183 Zeilen gefuellt, als das Feld eingerichtet
       -- wurde — es traegt also keine Altlasten.
       -- Bleibt alles leer, setzt die Anwendung einen Ersatzwert (siehe
       -- app/opera.py) und vermerkt, dass es einer ist.
       --
       -- WARUM CUSTOM_REFERENCE ABGESCHALTET IST: Das Feld ist gut gefuellt
       -- (320 von 620 Firmenbelegen in 30 Tagen), aber es enthaelt ueberwiegend
       -- nicht die Nummer des Kunden. Ausgezaehlt: 242 von 320 Werten sind
       -- reine neun- bis zehnstellige Ziffernfolgen, also Buchungsnummern aus
       -- dem Channel Manager. Bei Firmenprofilen ohne Debitorenkonto sind es
       -- 80 %, mit Debitorenkonto 29 %.
       --
       -- Eine Portal-Buchungsnummer in BT-10 ist SCHLECHTER als ein
       -- Ersatzwert: Der Kundenname ist erkennbar ein Platzhalter, eine
       -- zehnstellige Zahl sieht nach einer echten Bestellnummer aus, und die
       -- Buchhaltung der Gegenseite sucht sie vergeblich. Der Wert wird
       -- deshalb weiterhin gelesen und in der Oberflaeche angezeigt, geht aber
       -- nur nach ausdruecklicher Freigabe in die Rechnung.
       --
       -- EXTERNAL_REFERENCE ist im ganzen Bestand leer und wird von niemandem
       -- benutzt. Genau deshalb taugt es: Traegt der Empfang dort die
       -- Bestellnummer des Firmenkunden ein, steht sie ohne Codeaenderung in
       -- BT-10.
       COALESCE(
         (SELECT MAX(m.membership_card_no)
            FROM @SCHEMA@.memberships m
           WHERE m.name_id         = NVL(f.payee_name_id, f.name_id)
             AND m.membership_type = :leitweg_typ
             AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
             AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)),
         (SELECT MAX(m.membership_card_no)
            FROM @SCHEMA@.memberships m
           WHERE m.name_id         = NVL(f.payee_name_id, f.name_id)
             AND m.membership_type = :erechnung_typ
             AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
             AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)),
         resv.folio_text1,
         resv.external_reference,
         CASE WHEN :kundenreferenz_nutzen = 'J' THEN resv.custom_reference END
       )                                                      AS buyerreference,
       resv.custom_reference                                  AS kundenreferenz,
       resv.external_reference                                AS externe_referenz,
       resv.folio_text1                                       AS buyer_reference1,
       resv.confirmation_no                                   AS reservierungsnummer,
       (SELECT MAX(m.membership_card_no)
          FROM @SCHEMA@.memberships m
         WHERE m.name_id         = NVL(f.payee_name_id, f.name_id)
           AND m.membership_type = :leitweg_typ
           AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
           AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)) AS leitweg_id_vorhanden,
       -- Wer war im Haus? Auf der Papierrechnung steht der Gast oben; in der
       -- XRechnung fehlte er, und damit konnte die Buchhaltung des Kunden die
       -- Rechnung keiner Reise und keinem Mitarbeiter zuordnen.
       --
       -- Der Gast haengt an der RESERVIERUNG, der Zahler am Folio — bei
       -- Firmenrechnungen fallen die beiden gerade auseinander. Deshalb ueber
       -- resv.name_id und NICHT ueber NVL(payee_name_id, name_id); das waere
       -- wieder der Zahler. Bei Gruppen haengt kein einzelner Gast an der
       -- Reservierung, dann bleibt das Feld leer (im Bestand 98 % gefuellt).
       -- BEWUSST OHNE RUECKFALL AUF g.company: Steht dort keine Person, ist es
       -- keine. In 60 von 2542 Belegen griff der Rueckfall, und er lieferte
       -- Gruppenkuerzel wie 'GRO020926' — die Rechnung behauptete dann, eine
       -- Person dieses Namens habe im Haus gewohnt. Lieber keine Gastzeile.
       (SELECT TRIM(TRIM(g."LAST") || CASE WHEN g."FIRST" IS NOT NULL
                                           THEN ', ' || g."FIRST" END)
          FROM @SCHEMA@.name g
         WHERE g.name_id = resv.name_id)                      AS gastname,
       f.room                                                 AS zimmer,
       -- Der AUFENTHALT, nicht der Abrechnungszeitraum des Folios.
       -- f.bill_start_date ist der Beginn der Abrechnung: Bei einer Anzahlung
       -- beginnt sie mit deren Buchung. Ueber 30 Tage wich sie bei 928 von
       -- 2542 Belegen vom Anreisedatum ab, im Aeussersten um 1440 Tage — eine
       -- Rechnung ueber "21.08.2022 bis 05.09.2026" prueft die Reisekostenstelle
       -- des Kunden zu Recht nach.
       --
       -- Das gilt auch fuer BT-73/74: Fuer eine Hotelrechnung ist der
       -- Leistungszeitraum der Aufenthalt, und nach § 14 UStG gehoert genau der
       -- auf die Rechnung. Der Folio-Zeitraum bleibt der Rueckfall, wenn keine
       -- Reservierung daranhaengt.
       TO_CHAR(NVL(resv.begin_date, f.bill_start_date), 'YYYY-MM-DD') AS startdate,
       TO_CHAR(NVL(resv.end_date,   f.business_date),   'YYYY-MM-DD') AS enddate,
       TO_CHAR(f.bill_start_date, 'YYYY-MM-DD')               AS folio_beginn,
       TO_CHAR(f.business_date,   'YYYY-MM-DD')               AS folio_ende,
       f.document_type,
       -- Der Belegstatus wird bei JEDEM Erzeugen neu gelesen, nicht nur beim
       -- Einlesen: Ein Beleg, der waehrend der Wartezeit in OPERA storniert
       -- wird (VOID), faellt aus der Einleseliste heraus und wurde sonst
       -- trotzdem versendet. Geprueft in xml_build.pruefsummen.
       f.status                                               AS beleg_status,
       f.invoice_no,
       f.account_code,
       -- Verkaeufer (BG-4): Hausdaten, wo moeglich aus dem eingefrorenen Beleg
       NVL(f.hotel_name, r.name)                              AS suppliername,
       NVL(r.legal_owner, NVL(f.hotel_name, r.name))          AS supplierregistrationname,
       r.street                                               AS supplierstreetname,
       NVL(f.resort_city,     r.city)                         AS suppliercityname,
       NVL(f.resort_zip_code, r.post_code)                    AS supplierpostalzone,
       r.country_code                                         AS supplieridentificationcode,
       TO_CHAR(NULL)                                          AS suppliercompanyid,
       r.telephone                                            AS suppliercontacttelephone,
       r.email                                                AS suppliercontactelectronicmail,
       (SELECT MAX(a.description)
          FROM @SCHEMA@.udf_attributes a
          JOIN @SCHEMA@.udf_types     u ON u.udf_type = a.udf_type
         WHERE u.table_name = 'RESORT'
           AND u.udf_type   = 'BANK_DETAILS')                 AS supplier_bank_udf,
       -- Erwerber (BG-7): ADDRESSEE_NAME_ID ist im Bestand nie gefuellt,
       -- massgeblich sind PAYEE_NAME_ID bzw. NAME_ID.
       NVL(f.payee_name_id, f.name_id)                        AS customer_name_id,
       -- BT-46: die Debitorennummer, unter der das Haus den Kunden fuehrt.
       -- ACCOUNT_NO ist die Nummer der Buchhaltung, ACCOUNT_CODE nur der
       -- interne Schluessel der Tabelle.
       ar.account_no                                          AS debitorennummer,
       NVL(ar.account_name, NVL(f.payee_name, f.company_name)) AS customername,
       NVL(n.legal_company, NVL(ar.account_name,
           NVL(f.payee_name, f.company_name)))                AS customerregistrationname,
       adr.address1                                           AS customerstreetname,
       adr.city                                               AS customercityname,
       NVL(adr.zip_code, f.payee_zip_code)                    AS customerpostalzone,
       adr.country                                            AS customeridentificationcode,
       f.folio_address                                        AS customeraddress_beleg,
       NVL(n.tax1_no, n.tax2_no)                              AS customercompanyid,
       -- BT-49 kommt NICHT mehr von hier. Diese Abfrage sah nur das Profil
       -- NVL(payee_name_id, name_id) und ignorierte die Rechnungsanschrift,
       -- das Debitorenkonto und das Kennzeichen 'inaktiv'. Damit zog sie
       -- einen anderen Kreis als invoice_recipients.sql: An Beleg 1400019
       -- fand die eine Abfrage eine Adresse und die andere nicht, und es war
       -- unvorhersehbar, welche Rechnung BT-49 traegt. Die elektronische
       -- Adresse ist die, an die tatsaechlich versendet wird — sie kommt aus
       -- invoice_recipients.sql, ueber ablauf.rechnungsdaten().
       -- Betraege: Kopf ist fuehrend (siehe docs/06_BEFUNDE_LIVE_DB.md)
       f.total_net                                            AS invoicenet,
       f.total_gross                                          AS invoicegross,
       f.total_gross - f.total_net                            AS invoicetaxtotal,
       -- Vom Gast bereits beglichen. CLPAY ist die Umbuchung aufs Debitorenkonto
       -- und damit gerade NICHT bezahlt — sie bleibt offen (BT-115).
       -- Anzahlungen liegen als eigene DEPOSIT-Belege auf demselben Folio und
       -- gehoeren ebenfalls in BT-113 (siehe invoice_deposits.sql).
       NVL(f.cashpay, 0) + NVL(f.ccpay, 0) + NVL(f.deposit, 0)
         -- Umweg ueber FOLIOS statt WHERE folio_no: FOLIO$_TAX_E hat keinen
         -- Index auf FOLIO_NO, FOLIOS_E hat einen auf (FOLIO_NO, BILL_NO).
         -- Das war der Unterschied zwischen 1686 ms und wenigen Millisekunden.
         -- Die RESORT-Bedingung gehoert dazu: FOLIO_TAX_BILLNO_I geht ueber
         -- (RESORT, BILL_NO) und greift ohne sie nicht.
         --
         -- ENTSCHEIDEND ist aber, dass die Unterabfrage NICHT korreliert:
         -- Die Folionummer kommt aus einer eigenen Unterabfrage ueber
         -- :bill_no und nicht als f.folio_no aus der aeusseren Zeile. Nur so
         -- steht der Wert vor der Auswertung fest und der Index laesst sich
         -- ansetzen. Gemessen an derselben Zeile mit demselben Ergebnis:
         --   korreliert    (fo.folio_no = f.folio_no)   1928.5 ms
         --   entkorreliert (eigene Unterabfrage)            0.7 ms
         -- Das Resort allein aendert daran nichts (1780 ms).
         + NVL((SELECT SUM(d.total_gross) FROM @SCHEMA@.folio$_tax d
                 WHERE d.resort = :resort
                   AND d.bill_no IN (SELECT fo.bill_no FROM @SCHEMA@.folios fo
                                      WHERE fo.folio_no = (SELECT k.folio_no
                                                             FROM @SCHEMA@.folio$_tax k
                                                            WHERE k.resort  = :resort
                                                              AND k.bill_no = :bill_no))
                   AND d.status = 'DEPOSIT'
                   AND d.bill_no <> :bill_no), 0)                AS prepaidamount,
       f.total_gross
         - (NVL(f.cashpay, 0) + NVL(f.ccpay, 0) + NVL(f.deposit, 0)) AS payableamount,
       f.folio_no,
       f.clpay                                                AS city_ledger_betrag
  FROM @SCHEMA@.folio$_tax f
  JOIN @SCHEMA@.resort r
    ON r.resort = f.resort
  LEFT JOIN @SCHEMA@.name n
    ON n.name_id = NVL(f.payee_name_id, f.name_id)
  LEFT JOIN @SCHEMA@.name_address adr
    ON adr.name_id = n.name_id AND adr.primary_yn = 'Y'
  LEFT JOIN @SCHEMA@.ar$_account ar
    ON ar.account_code = f.account_code AND ar.resort = f.resort
  LEFT JOIN @SCHEMA@.reservation_name resv
    ON resv.resv_name_id = f.resv_name_id
 WHERE f.bill_no = :bill_no
   -- BILL_NO ist je Resort eindeutig, nicht ueber alle — und der Index geht
   -- ueber (RESORT, BILL_NO).
   AND f.resort  = :resort
