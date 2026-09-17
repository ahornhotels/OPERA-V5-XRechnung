-- 03_stammdaten_leitweg.sql — Profil, Adresse, USt-IdNr., Leitweg-ID (nur lesend)
-- DEFINE OPERA_OWNER = OPERA

PROMPT == Profil- und Adressobjekte ==
SELECT object_type, object_name
  FROM all_objects
 WHERE owner = '&&OPERA_OWNER'
   AND object_type IN ('TABLE','VIEW')
   AND (object_name LIKE 'NAME%' OR object_name LIKE '%ADDRESS%' OR object_name LIKE '%PROFILE%')
 ORDER BY object_type, object_name;

PROMPT == Kandidaten fuer USt-IdNr. / Steuernummer ==
SELECT table_name, column_name, data_type, data_length
  FROM all_tab_columns
 WHERE owner = '&&OPERA_OWNER'
   AND (column_name LIKE '%TAX_ID%' OR column_name LIKE '%VAT%' OR column_name LIKE '%FISCAL%')
 ORDER BY table_name, column_name;

PROMPT == Kandidaten fuer die Leitweg-ID (BT-10): UDFs und Freifelder am Profil ==
SELECT table_name, column_name, data_type, data_length
  FROM all_tab_columns
 WHERE owner = '&&OPERA_OWNER'
   AND (   column_name LIKE 'UDF%'
        OR column_name LIKE '%USER_DEFINED%'
        OR column_name LIKE '%REFERENCE%'
        OR column_name LIKE '%EXTERNAL_REF%' )
   AND table_name LIKE '%NAME%'
 ORDER BY table_name, column_name;

PROMPT == Kommunikationsdaten (E-Mail des Rechnungsempfaengers, BT-49) ==
SELECT table_name, column_name, data_type
  FROM all_tab_columns
 WHERE owner = '&&OPERA_OWNER'
   AND (column_name LIKE '%PHONE%' OR column_name LIKE '%EMAIL%' OR column_name LIKE '%COMMUNICATION%')
 ORDER BY table_name, column_name;

PROMPT == Debitoren / City Ledger ==
SELECT object_type, object_name
  FROM all_objects
 WHERE owner = '&&OPERA_OWNER'
   AND object_name LIKE 'AR%'
 ORDER BY object_type, object_name;
