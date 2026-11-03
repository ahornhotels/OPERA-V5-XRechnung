-- profil_mails.sql — E-Mail-Adressen eines Profils (Zahlungsanforderung)
-- Bindvariablen: :name_id, :resort
--
-- Wie invoice_recipients.sql, nur vom Profil aus statt vom Beleg: erst die
-- Adresse am Debitorenkonto, dann die primaere, dann die uebrigen.

SELECT quelle, email, primaer, sortierung
  FROM (
        SELECT 'Debitorenkonto' AS quelle, ar.email_address AS email, 'Y' AS primaer, 1 AS sortierung
          FROM @SCHEMA@.ar$_account ar
         WHERE ar.name_id = :name_id
           AND ar.resort  = :resort
           AND ar.email_address IS NOT NULL
        UNION ALL
        SELECT 'Profil', ph.phone_number, NVL(ph.primary_yn, 'N'),
               CASE WHEN NVL(ph.primary_yn, 'N') = 'Y' THEN 2 ELSE 3 END
          FROM @SCHEMA@.name_phone ph
         WHERE ph.name_id    = :name_id
           AND ph.phone_role = 'EMAIL'
           AND ph.phone_number IS NOT NULL
           AND (ph.inactive_date IS NULL OR ph.inactive_date > SYSDATE)
       )
 ORDER BY sortierung, email
