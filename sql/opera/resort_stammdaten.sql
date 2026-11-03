-- resort_stammdaten.sql — die Hausdaten fuer ein Schreiben ohne OPERA-Beleg
-- Bindvariable: :resort
--
-- Fuer die Zahlungsanforderung (app/zahlungsanforderung.py). Dieselben Quellen
-- wie der Verkaeuferteil von invoice_header.sql, nur ohne Beleg: Dort gehen die
-- eingefrorenen Werte des Belegs vor (HOTEL_NAME, RESORT_CITY), hier gibt es
-- keinen, also gilt RESORT. USt-IdNr., IBAN und Kontakt kommen wie dort aus der
-- Konfiguration.

SELECT r.name                                   AS suppliername,
       NVL(r.legal_owner, r.name)               AS supplierregistrationname,
       r.street                                 AS supplierstreetname,
       r.city                                   AS suppliercityname,
       r.post_code                              AS supplierpostalzone,
       r.country_code                           AS supplieridentificationcode,
       r.telephone                              AS suppliercontacttelephone,
       r.email                                  AS suppliercontactelectronicmail,
       r.currency_code                          AS documentcurrencycode
  FROM @SCHEMA@.resort r
 WHERE r.resort = :resort
