-- profil_anschrift.sql — Empfaenger einer Zahlungsanforderung
-- Bindvariablen: :name_id, :resort
--
-- Name, Firmierung, Hauptanschrift und Debitorennummer (app/zahlungsanforderung.py).
-- Alle Zugriffe ueber Indizes: NAME_PK, NAME_ADRESS_UNIQUE (NAME_ID,
-- PRIMARY_YN), ACCOUNT_NAMEID_NDX (NAME_ID, RESORT).

SELECT n.name_id,
       n.name_type,
       COALESCE(n.company,
                TRIM(TRIM(n."LAST") || CASE WHEN n."FIRST" IS NOT NULL
                                            THEN ', ' || n."FIRST" END))   AS name,
       n.legal_company,
       a.address1,
       a.address2,
       a.zip_code,
       a.city,
       a.country,
       (SELECT MAX(ar.account_no)
          FROM @SCHEMA@.ar$_account ar
         WHERE ar.name_id = n.name_id
           AND ar.resort  = :resort)                                       AS debitorennummer
  FROM @SCHEMA@.name n
  LEFT JOIN @SCHEMA@.name_address a
    ON a.name_id = n.name_id AND a.primary_yn = 'Y'
 WHERE n.name_id = :name_id
