-- profil_suche.sql — Kundenprofile nach Namen finden (Zahlungsanforderung)
-- Bindvariablen: :praefix, :resort
--
-- Gesucht wird ueber SNAME = UPPER(COALESCE(COMPANY, LAST)), ungetrimmt —
-- an der Live-DB in 1.106.825 von 1.106.825 Profilen bestaetigt (03.11.2026).
-- Zugriff ueber SEARCH_NAME_IDX (SNAME, SFIRST, NAME_TYPE, CONTACT_YN,
-- ACTIVE_YN): alle Bedingungen stehen im Index, gemessen rund 300 Buffer Gets
-- und 20 ms, gleich ob 5 oder 27.000 Treffer.
--
-- DREI DINGE HALTEN DAS SO:
-- - Nur ein Praefix (LIKE 'ABC%'). Ein Teilwort ('%abc%') laeuft bei
--   seltenen Mustern den ganzen Index (gemessen 7.800 Gets, 236 ms).
-- - ORDER BY n.sname und nichts anderes. Dann liefert der Index die
--   Reihenfolge, es gibt kein SORT, und nach 50 Zeilen ist Schluss. Nach dem
--   Anzeigenamen sortiert waren es 47.569 Gets und ein Volldurchlauf auf
--   NAME_ADDRESS.
-- - UPPER in Oracle, nicht in Python, und den Begriff vorne nicht kuerzen:
--   SNAME behaelt fuehrende Leerzeichen des Originals.
--
-- Typen laut Daten: COMPANY, TRAVEL_AGENT, G (Gruppe), S (Source),
-- D (Person), E (Mitarbeiter). Ansprechpartner (CONTACT_YN = 'Y', rund 63.000)
-- sind Kontakte einer Firma, keine Rechnungsempfaenger. Aktiv heisst BEIDES:
-- INACTIVE_DATE leer und ACTIVE_YN = 'Y' — die beiden widersprechen sich in
-- rund 52.000 Profilen. Die Debitorennummer kommt aus dem Debitorenkonto
-- DIESES Hauses (ACCOUNT_NAMEID_NDX), ausgewertet nur fuer die 50 Treffer.

SELECT * FROM (
  SELECT n.name_id,
         n.name_type,
         COALESCE(n.company,
                  TRIM(TRIM(n."LAST") || CASE WHEN n."FIRST" IS NOT NULL
                                              THEN ', ' || n."FIRST" END)) AS name,
         n.legal_company,
         a.address1,
         a.zip_code,
         a.city,
         a.country,
         (SELECT MAX(ar.account_no)
            FROM @SCHEMA@.ar$_account ar
           WHERE ar.name_id = n.name_id
             AND ar.resort  = :resort)                                     AS debitorennummer
    FROM @SCHEMA@.name n
    LEFT JOIN @SCHEMA@.name_address a
      ON a.name_id = n.name_id AND a.primary_yn = 'Y'
   WHERE n.sname LIKE UPPER(:praefix) || '%'
     AND n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S', 'D', 'E')
     AND n.inactive_date IS NULL
     AND NVL(n.active_yn, 'Y') = 'Y'
     AND NVL(n.contact_yn, 'N') = 'N'
   ORDER BY n.sname
) WHERE ROWNUM <= 50
