"""Stornorechnung zu einer versendeten Rechnung, die in OPERA storniert wurde.

OPERA erzeugt bei einem Storno keinen eigenen Beleg: Die Zeile der Rechnung
wird ueberschrieben (STATUS VOID, Betrag 0), die Buchungen wandern auf den
Ersatzbeleg (docs/06_BEFUNDE_LIVE_DB.md, Storno-Zaehlung). Aus OPERA laesst
sich die stornierte Rechnung deshalb nicht mehr bauen.

Gebaut wird sie aus der archivierten XRechnung — genau dem, was der Kunde
bekommen hat. Daraus wird eine Gutschrift (UBL CreditNote, Typ 381) mit
denselben Parteien, Positionen und Betraegen, eigener Nummer und Verweis auf
die stornierte Rechnung (BG-3). Die Betraege bleiben positiv: In einer
CreditNote bedeutet ein positiver Betrag eine Gutschrift.

Nummer: Rechnungsnummer mit "-S" (Entscheidung des Hauses, 02.11.2026).
Eindeutig, weil jede Rechnung hoechstens einmal storniert wird, und sofort
dem Original zuzuordnen.
"""
from __future__ import annotations

from lxml import etree

NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CREDIT = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
ENDUNG = "-S"

# Was in UBL nach BillingReference kommt, bis zum Lieferanten. Der neue
# Verweis gehoert vor das erste davon (oder vor einen vorhandenen Verweis).
_NACH_VERWEIS = ("BillingReference", "DespatchDocumentReference", "ReceiptDocumentReference",
                 "StatementDocumentReference", "OriginatorDocumentReference",
                 "ContractDocumentReference", "AdditionalDocumentReference",
                 "ProjectReference", "Signature", "AccountingSupplierParty")


class KeinStorno(ValueError):
    """Aus dieser Datei laesst sich keine Stornorechnung bauen."""


def nummer(rechnungsnummer) -> str:
    return f"{rechnungsnummer}{ENDUNG}"


def vermerk(rechnungsnummer: str, datum: str) -> str:
    return (f"Stornorechnung: Die Rechnung {rechnungsnummer} vom {datum} ist storniert und "
            "wird hiermit vollständig aufgehoben.")


def _cbc(name: str) -> str:
    return f"{{{CBC}}}{name}"


def _cac(name: str) -> str:
    return f"{{{CAC}}}{name}"


def _lokal(el) -> str:
    return etree.QName(el).localname


def aus_rechnung(xml: bytes, ausgestellt: str) -> bytes:
    """Baut aus einer XRechnung (UBL Invoice) die Stornorechnung.
    ausgestellt: Datum der Stornorechnung, JJJJ-MM-TT."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    try:
        alt = etree.fromstring(xml, parser)
    except etree.XMLSyntaxError as e:
        raise KeinStorno(f"Die archivierte Rechnung ist kein lesbares XML ({e}).") from e
    if alt.tag == f"{{{NS_CREDIT}}}CreditNote":
        raise KeinStorno("Die archivierte Fassung ist selbst eine Gutschrift. Eine Gutschrift "
                         "wird nicht mit einer Stornorechnung aufgehoben — bitte von Hand klären.")
    if alt.tag != f"{{{NS_INVOICE}}}Invoice":
        raise KeinStorno("Die archivierte Fassung ist keine XRechnung (UBL Invoice).")

    id_el = alt.find(_cbc("ID"))
    datum_el = alt.find(_cbc("IssueDate"))
    if id_el is None or not (id_el.text or "").strip() or datum_el is None:
        raise KeinStorno("In der archivierten Rechnung fehlen Nummer oder Datum.")
    alte_nummer, altes_datum = id_el.text.strip(), (datum_el.text or "").strip()

    neu = etree.Element(f"{{{NS_CREDIT}}}CreditNote",
                        nsmap={"ubl": NS_CREDIT, "cac": CAC, "cbc": CBC})
    neu.text = alt.text
    for kind in list(alt):
        neu.append(kind)          # verschiebt, samt nachfolgendem Leerraum

    # Kopf
    neu.find(_cbc("ID")).text = nummer(alte_nummer)
    neu.find(_cbc("IssueDate")).text = ausgestellt
    for el in neu.findall(_cbc("DueDate")):
        neu.remove(el)
    typ = neu.find(_cbc("InvoiceTypeCode"))
    if typ is None:
        raise KeinStorno("In der archivierten Rechnung fehlt der Rechnungstyp.")
    typ.tag, typ.text = _cbc("CreditNoteTypeCode"), "381"
    notiz = etree.Element(_cbc("Note"))
    notiz.text = vermerk(alte_nummer, altes_datum)
    notiz.tail = typ.tail
    typ.addnext(notiz)

    # BG-3: Verweis auf die stornierte Rechnung, vor allen anderen Verweisen
    verweis = etree.Element(_cac("BillingReference"))
    ref = etree.SubElement(verweis, _cac("InvoiceDocumentReference"))
    etree.SubElement(ref, _cbc("ID")).text = alte_nummer
    etree.SubElement(ref, _cbc("IssueDate")).text = altes_datum
    ziel = next((k for k in neu if isinstance(k.tag, str) and _lokal(k) in _NACH_VERWEIS), None)
    if ziel is None:
        raise KeinStorno("In der archivierten Rechnung fehlt der Rechnungssteller.")
    verweis.tail = "\n\n  "
    ziel.addprevious(verweis)

    # Zahlung: Das Haus schuldet dem Kunden. 97 = Verrechnung, ohne eigene
    # Kontoverbindung — wie bei jeder Gutschrift (Vorlage, PaymentMeans).
    for zm in neu.findall(_cac("PaymentMeans")):
        code = zm.find(_cbc("PaymentMeansCode"))
        if code is not None:
            code.text = "97"
        for konto in zm.findall(_cac("PayeeFinancialAccount")):
            zm.remove(konto)

    # Positionen
    for el in neu.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag == _cac("InvoiceLine"):
            el.tag = _cac("CreditNoteLine")
        elif el.tag == _cbc("InvoicedQuantity"):
            el.tag = _cbc("CreditedQuantity")

    return etree.tostring(neu, xml_declaration=True, encoding="UTF-8") + b"\n"
