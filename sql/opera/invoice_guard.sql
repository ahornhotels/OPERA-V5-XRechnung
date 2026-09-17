-- invoice_guard.sql — Vorpruefung, VOR dem Erzeugen der XRechnung ausfuehren.
-- Bindvariablen: :bill_no, :resort
--
-- Anzahlungs-Codes dieses Hauses. DEPOSIT_TYPE ist unbenutzt und
-- IND_DEPOSIT_YN markiert die zulaessigen Zahlungsarten, nicht die Umbuchungen —
-- beide taugen nicht als Regel. Ableitbar sind die Codes ueber
--   tc_group='TAX' AND tc_subgroup='TAX10'  (Deposit Tax 19/7/0 %)
--   tc_subgroup='INT-PAY'                   (Umbuchungen; 9211 und 9557 ausschliessen)
--
-- anzahlung_vorhanden = 'J' -> die Zeilen umfassen das GANZE Folio, der Kopf
--   nur den Restbetrag. Die Rechnung ist trotzdem verwertbar: die Anzahlungen
--   stehen als eigene Belege mit STATUS='DEPOSIT' auf demselben FOLIO_NO
--   (invoice_deposits.sql) und gehen als BG-3 BillingReference und BT-113
--   PrepaidAmount in die XRechnung ein. Pruefgroesse ist dann
--   netto_mit_anzahlung_ok statt netto_ok.
-- netto_ok / brutto_ok = 'N' -> Rechnung nicht automatisch verarbeiten,
--   sondern zur Sichtpruefung ausschleusen. In der Zielmenge (City Ledger ohne
--   Anzahlungs-Codes) lag die Quote bei 353 von 353.

SELECT f.bill_no,
       f.document_type,
       f.status,
       f.total_net,
       f.total_gross,
       z.zeilen_netto,
       z.zeilen_brutto,
       z.zeilen,
       -- Haengt am selben Folio ein Anzahlungsbeleg? STATUS = 'DEPOSIT' ist eine
       -- OPERA-Systemkonstante (nur OK, DEPOSIT, VOID, ZERO, englisch auch in
       -- deutschsprachigen Installationen) — das gilt in jedem Haus. Vorher
       -- stand hier eine Liste von Umsatzcodes, die in jedem anderen Haus
       -- falsch gewesen waere UND in diesem unvollstaendig war: Die drei
       -- haeufigsten Anzahlungscodes fehlten darin. Der Weg ueber FOLIOS statt
       -- direkt ueber FOLIO_NO ist Absicht — siehe invoice_deposits.sql.
       CASE WHEN EXISTS (SELECT 1 FROM @SCHEMA@.folio$_tax d
                          WHERE d.resort = f.resort
                            AND d.bill_no IN (SELECT fo.bill_no
                                                FROM @SCHEMA@.folios fo
                                               WHERE fo.folio_no = f.folio_no)
                            AND d.bill_no <> f.bill_no
                            AND d.status   = :anzahlung_status) /*ODER_CODES*/
            THEN 'J' ELSE 'N' END                                   AS anzahlung_vorhanden,
       CASE WHEN ABS(NVL(z.zeilen_netto, 0)  - f.total_net)   <= 0.02
            THEN 'J' ELSE 'N' END                                   AS netto_ok,
       CASE WHEN ABS(NVL(z.zeilen_brutto, 0) - f.total_gross) <= 0.02
            THEN 'J' ELSE 'N' END                                   AS brutto_ok,
       -- Mit Anzahlungen: Zeilensumme = Kopf + Summe der DEPOSIT-Belege
       dep.anzahl_deposits,
       dep.deposit_netto,
       dep.deposit_brutto,
       CASE WHEN ABS(NVL(z.zeilen_netto, 0)
                     - (f.total_net + NVL(dep.deposit_netto, 0))) <= 0.02
            THEN 'J' ELSE 'N' END                                   AS netto_mit_anzahlung_ok,
       CASE WHEN ABS(NVL(z.zeilen_brutto, 0)
                     - (f.total_gross + NVL(dep.deposit_brutto, 0))) <= 0.02
            THEN 'J' ELSE 'N' END                                   AS brutto_mit_anzahlung_ok,
       (SELECT NVL(SUM(t.net_amount), 0)
          FROM @SCHEMA@.financial_transactions t
         WHERE t.bill_no = f.bill_no
           AND t.gross_amount IS NULL
           AND t.tax_rate IS NOT NULL)                              AS steuerzeilen_summe
  FROM @SCHEMA@.folio$_tax f
  -- Die Einschraenkung auf die Rechnung gehoert IN die Unterabfrage. Stand sie
  -- nur in der Join-Bedingung, musste Oracle sie erst durch die Gruppierung
  -- schieben — darauf sollte man sich nicht verlassen, wenn die Tabelle alle
  -- Buchungszeilen des Hauses traegt.
  LEFT JOIN (SELECT bill_no,
                    SUM(net_amount)   AS zeilen_netto,
                    SUM(gross_amount) AS zeilen_brutto,
                    COUNT(*)          AS zeilen
               FROM @SCHEMA@.financial_transactions
              WHERE gross_amount IS NOT NULL
                AND bill_no = :bill_no
                AND resort  = :resort
              GROUP BY bill_no) z
    ON z.bill_no = f.bill_no
  -- Die Anzahlungen desselben Folios. Frueher stand hier eine Inline-Sicht,
  -- die ALLE DEPOSIT-Belege des Hauses nach FOLIO_NO gruppierte und danach auf
  -- eines davon einschraenkte — ein voller Tabellendurchlauf je Aufruf, 1721 ms.
  -- Jetzt wird erst ueber FOLIOS (Index auf FOLIO_NO, BILL_NO) die BILL_NO-Liste
  -- geholt und dann ueber den BILL_NO-Index gelesen.
  LEFT JOIN (SELECT COUNT(*)           AS anzahl_deposits,
                    SUM(d.total_net)   AS deposit_netto,
                    SUM(d.total_gross) AS deposit_brutto
               FROM @SCHEMA@.folio$_tax d
              WHERE d.status = :anzahlung_status
                -- RESORT gehoert dazu: Der Index geht ueber (RESORT, BILL_NO)
                -- und greift ohne diese Bedingung nicht.
                AND d.resort = :resort
                AND d.bill_no IN (SELECT fo.bill_no
                                    FROM @SCHEMA@.folios fo
                                   WHERE fo.folio_no = (SELECT k.folio_no
                                                          FROM @SCHEMA@.folio$_tax k
                                                         WHERE k.bill_no = :bill_no
                                                           AND k.resort  = :resort))) dep
    ON 1 = 1
 WHERE f.bill_no = :bill_no
   AND f.resort  = :resort
