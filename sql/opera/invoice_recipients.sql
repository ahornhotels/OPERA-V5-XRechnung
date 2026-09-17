-- invoice_recipients.sql — alle E-Mail-Adressen, die zu einer Rechnung gehoeren
-- Bindvariablen: :bill_no, :resort
--
-- Der Anwender waehlt in der Oberflaeche aus, wohin die XRechnung geht.
-- Deshalb werden ALLE Kandidaten geliefert, nicht nur der erste Treffer:
--   * alle E-Mail-Adressen des Rechnungsempfaengers (PAYEE bzw. NAME)
--   * alle E-Mail-Adressen des Adressaten, falls gepflegt
--   * die Adresse des Debitorenkontos
-- Sortiert: Debitorenkonto, dann der ZAHLER (primaer vor sonstigen), dann
-- die Rechnungsanschrift, zuletzt das Folio-Profil.
--
-- DAS FOLIO-PROFIL (NAME_ID) NUR, WENN ES KEINEN ANDEREN ZAHLER GIBT. Bei
-- einer Firmenrechnung ist NAME_ID in aller Regel der GAST. Vorher standen
-- seine privaten Adressen gleichrangig neben denen der Firma, sortiert wurde
-- nach dem Alphabet — "anna.meyer@…" vor "rechnung@firma…", und die Automatik
-- schickte die Firmenrechnung ins private Postfach des Gastes. Hat die Firma
-- selbst keine Adresse, ist das jetzt ein Pflegefall und kein Gast-Postfach.

WITH beleg AS (
    SELECT bill_no, name_id, payee_name_id, addressee_name_id, account_code, resort
      FROM @SCHEMA@.folio$_tax
     WHERE bill_no = :bill_no
       AND resort  = :resort
),
profile AS (
    SELECT b.payee_name_id AS name_id, 'Zahler'      AS rolle FROM beleg b WHERE b.payee_name_id IS NOT NULL
    UNION
    SELECT b.name_id,                  'Profil'            FROM beleg b
     WHERE b.name_id IS NOT NULL
       AND (b.payee_name_id IS NULL OR b.payee_name_id = b.name_id)
    UNION
    SELECT b.addressee_name_id,        'Rechnungsanschrift' FROM beleg b WHERE b.addressee_name_id IS NOT NULL
)
SELECT quelle, rolle, name_id, email, typ, primaer, sortierung
  FROM (
        SELECT 'Profil'                       AS quelle,
               p.rolle                        AS rolle,
               p.name_id                      AS name_id,
               ph.phone_number                AS email,
               ph.phone_type                  AS typ,
               NVL(ph.primary_yn, 'N')        AS primaer,
               CASE WHEN p.rolle = 'Zahler' AND NVL(ph.primary_yn,'N') = 'Y' THEN 2
                    WHEN p.rolle = 'Zahler'                               THEN 3
                    WHEN p.rolle = 'Rechnungsanschrift'                   THEN 4
                    WHEN NVL(ph.primary_yn,'N') = 'Y'                     THEN 5
                    ELSE 6 END                AS sortierung
          FROM profile p
          JOIN @SCHEMA@.name_phone ph ON ph.name_id = p.name_id
         WHERE ph.phone_role = 'EMAIL'
           AND ph.phone_number IS NOT NULL
           AND (ph.inactive_date IS NULL OR ph.inactive_date > SYSDATE)
        UNION ALL
        SELECT 'Debitorenkonto', 'AR-Konto', ar.name_id, ar.email_address, 'AR', 'Y', 1
          FROM beleg b
          JOIN @SCHEMA@.ar$_account ar
            ON ar.account_code = b.account_code AND ar.resort = b.resort
         WHERE ar.email_address IS NOT NULL
       )
 ORDER BY sortierung, email
