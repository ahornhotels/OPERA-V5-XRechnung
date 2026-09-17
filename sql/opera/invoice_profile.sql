-- invoice_profile.sql — Profildaten des Rechnungsempfaengers zur Anzeige
-- Bindvariablen: :bill_no, :resort, :leitweg_typ, :erechnung_typ
-- Dient der Sichtpruefung durch den Anwender, bevor er versendet.

SELECT n.name_id,
       -- NAME hat keine Spalte NAME: bei Firmen steht der Name in COMPANY,
       -- bei Personen in LAST/FIRST. LAST und FIRST sind in Anfuehrungszeichen,
       -- weil beides in Oracle auch Schluesselwoerter sind.
       COALESCE(n.company, n.legal_company, TRIM(TRIM(n."LAST") || CASE WHEN n."FIRST" IS NOT NULL THEN ', ' || n."FIRST" END)) AS name,
       n."FIRST"                                   AS first,
       n.company,
       n.legal_company,
       n.name_type,
       n.tax1_no,
       n.tax2_no,
       n.language,
       (SELECT MAX(m.membership_card_no)
          FROM @SCHEMA@.memberships m
         WHERE m.name_id = n.name_id
           AND m.membership_type = :leitweg_typ
           AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
           AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)) AS leitweg_id,
       (SELECT MAX(m.membership_type)
          FROM @SCHEMA@.memberships m
         WHERE m.name_id = n.name_id
           AND m.membership_type IN (:leitweg_typ, :erechnung_typ)
           AND (m.inactive_date   IS NULL OR m.inactive_date   > SYSDATE)
           AND (m.expiration_date IS NULL OR m.expiration_date > SYSDATE)) AS erechnung_kennzeichen,
       a.address1, a.address2, a.city, a.zip_code, a.country,
       (SELECT COUNT(*) FROM @SCHEMA@.name_phone p
         WHERE p.name_id = n.name_id AND p.phone_role = 'EMAIL') AS anzahl_mails
  FROM @SCHEMA@.name n
  LEFT JOIN @SCHEMA@.name_address a
    ON a.name_id = n.name_id AND a.primary_yn = 'Y'
 WHERE n.name_id = (SELECT NVL(payee_name_id, name_id)
                      FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort)
