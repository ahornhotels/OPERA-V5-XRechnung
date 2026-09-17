# Discovery-Skripte

Alle Skripte lesen **ausschließlich** aus dem Oracle Data Dictionary
(`ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_VIEWS`, …) bzw. mit `SELECT` aus
OPERA-Tabellen. Keine DDL, keine DML, keine Änderungen an der Live-DB.

**Reihenfolge:** `04` → `05`. Die Skripte `01`–`03` stammen aus der Zeit vor dem
Live-Dictionary und suchen das Schema noch blind ab — sie werden nur noch
gebraucht, wenn eine weitere Installation dazukommt.

`04_objekte_verifizieren.sql` prüft die Annahmen aus dem Live-Dictionary
(Views vs. `_E`-Tabellen, Properties, Steuersätze, `REPORT_DESTINATIONS`).
`05_stichprobe_rechnung.sql` zieht **eine** bekannte Rechnung komplett —
dafür `BILL` auf eine echte, abgeschlossene Firmenrechnung setzen.

`06_positionen_gast.sql` prüft, ob die Zuordnung einer Buchung zum Gast
über `ORIGINAL_RESV_NAME_ID`/`ORIGINAL_ROOM` stimmt, auf der die Darstellung
„je Gast und Zimmer“ beruht (docs/14_POSITIONEN.md). **Vor dem ersten Versand
einer Gruppenrechnung fahren.**

`07_supplement.sql` klärt, in welcher Spalte der Text aus dem Feld
„Supplement" der Buchungsmaske landet. **Beantwortet:** Es ist
`FINANCIAL_TRANSACTIONS.REMARK` — nachgewiesen, indem in einem Haus alle
Textspalten nach einem bekannten Supplement-Text durchsucht wurden. Die
Anwendung liest diese Spalte als Vorgabe. Das Skript bleibt hier, um dasselbe
in einer anderen Installation nachzuprüfen: Eine Spalte `SUPPLEMENT` gibt es
in `FINANCIAL_TRANSACTIONS` nicht, und die Druckansicht speist sich aus einer
Tabelle, die nach dem Druck wieder geleert wird.

Ausgabe jeweils sichern (`spool`), dann werten wir sie gemeinsam aus.

Ausführen z. B. mit SQL*Plus/SQLcl als Benutzer mit Lesezugriff auf das
OPERA-Schema:

```
sqlplus user/pass@OPERA
SQL> set pagesize 200 linesize 300 trimspool on
SQL> spool 01_umgebung.log
SQL> @01_umgebung.sql
SQL> spool off
```
