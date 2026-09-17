"""XRechnung-Erzeugung. Die Normalisierungsregeln stammen aus der
Suite8-Vorlage (reference/XRechnung_Slim, GPLv3) — sie sind gegen den
KoSIT-Validator erarbeitet und werden hier unveraendert uebernommen:
Z-Kategorie auf 0 % (BR-Z-08), leere 0/0-Zeilen verwerfen (BR-CO-17),
negative Positionen als Abschlag (BR-27, BR-S-01)."""
from __future__ import annotations
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from lxml import etree

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).resolve().parent / "xml_templates"

# autoescape=True, nicht select_autoescape(["xml"]): Die Vorlage heisst
# xrechnung_3.0.xml.j2 und endet auf .j2, nicht auf .xml — die Auswahl nach
# Dateiendung war damit wirkungslos, und das Maskieren hing an einzeln
# gesetzten |e-Filtern. Ein Gastname wie "Meyer & Soehne GmbH" machte die
# Rechnung unbaubar (xmlParseEntityRef), und zwar dauerhaft: Der Name kommt
# unveraendert aus OPERA. Derselbe Wert war in BT-22 maskiert und in BT-70
# roh — dieselbe Zeichenkette, zwei Behandlungen.
def _leer_statt_none(wert):
    """Fehlende Werte werden leer, nicht zur Zeichenkette 'None'.

    Jinja setzt None als "None" ein. Fehlt am Profil die als primaer markierte
    Anschrift, lieferte die Abfrage NULL — und im Dokument stand dann
    <cbc:CityName>None</cbc:CityName> und ein Laenderkennzeichen 'None', das
    kein ISO-Code ist. Das sieht nach einem Wert aus und ist keiner.

    Zeichen, die XML 1.0 verbietet (Steuerzeichen ausser Tab, Zeilenumbruch
    und Wagenruecklauf), fallen weg. Sie kommen aus OPERA-Freitext — ein
    kopierter Text mit einem Formularvorschub machte die Rechnung unbaubar,
    dauerhaft, weil der Text sich nicht aendert."""
    if wert is None:
        return ""
    if isinstance(wert, str):
        return _XML_VERBOTEN.sub("", wert)
    return wert


_XML_VERBOTEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


_env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                   autoescape=True, finalize=_leer_statt_none,
                   trim_blocks=True, lstrip_blocks=True)


def _fmt(wert) -> str:
    if wert is None:
        return "0.00"
    try:
        return f"{Decimal(str(wert)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    except (InvalidOperation, ValueError):
        return "0.00"


def _preis(wert) -> str:
    """Einzelpreis: bis zu vier Nachkommastellen, mindestens zwei. Betraege
    sind auf zwei Stellen begrenzt, BT-146 ist davon ausgenommen — genau
    diese Freiheit braucht die Nachrechnung Menge mal Preis."""
    try:
        d = Decimal(str(wert or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return "0.00"
    text = f"{d:.4f}".rstrip("0")
    ganz, _, bruch = text.partition(".")
    return f"{ganz}.{bruch.ljust(2, '0')}"


_env.filters["fmt"] = _fmt
_env.filters["preis"] = _preis


class XmlFehler(Exception):
    pass


CENT = Decimal("0.01")


def _rund(wert) -> Decimal:
    """Kaufmaennisch auf zwei Stellen — dieselbe Regel wie die Ausgabe."""
    return _dez(wert).quantize(CENT, rounding=ROUND_HALF_UP)


def _einzelpreis(betrag: Decimal, menge) -> Decimal:
    """BT-146 aus dem Positionsbetrag ableiten, mit vier Nachkommastellen.

    PEPPOL-EN16931-R120 rechnet Menge mal Einzelpreis nach und vergleicht mit
    dem Positionsbetrag. OPERAs Preise sind krumm (6.0748); auf zwei Stellen
    gerundet und mit 2 multipliziert fehlt ein Cent — an einem Beleg auf 56
    Positionen. EN 16931 nimmt BT-146 ausdruecklich von der Zweistelligkeit
    aus, deshalb wird hier nicht gerundet, sondern der Preis aus dem Betrag
    gebildet. Damit stimmt die Multiplikation auch nach einer Verschiebung
    des Rundungsrests."""
    m = _dez(menge)
    if m == 0:
        m = Decimal(1)
    return (betrag / m).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _preis_setzen(zeile: dict, betrag: Decimal) -> None:
    """BT-146 zur Position setzen — so, dass Menge mal Preis den Betrag trifft.

    Vier Nachkommastellen reichen fast immer und lesen sich natuerlich. Die
    Regel rundet beide Seiten auf zwei Stellen, und der Fehler je Stueck
    betraegt hoechstens einen halben Zehntausendstel — er faellt also erst bei
    Mengen ueber rund hundert ins Gewicht. Bei Menge 3 geht es noch auf
    (10.00 / 3 = 3.3333, mal 3 = 9.9999, gerundet 10.00).

    Fuer die Mengen, bei denen es nicht mehr aufgeht, gibt es BT-149: Der
    Preis ist dann der volle Positionsbetrag und die Menge steht als
    Bezugsmenge daneben. Die Multiplikation geht ohne Rundung auf. Der Fall
    ist selten — geraten wird hier nichts, gerechnet wird es."""
    menge = _dez(zeile.get("invoicedquantity"))
    if menge < 0 and betrag >= 0:
        # Negative Menge bei positivem Betrag: Die Position wird dem Kunden
        # BERECHNET (ein Abschlag waere ein negativer Betrag). Der Preis als
        # Betrag / Menge waere dann negativ — BR-27 (und im Rueckfall eine
        # negative Bezugsmenge, R121), beides fatal. Die eigene Gegenprobe
        # rechnete -1 x -50 = 50 und schwieg. Das Vorzeichen der Menge traegt
        # hier keine Aussage; im Dokument steht sie positiv.
        menge = -menge
        zeile["invoicedquantity"] = format(menge.normalize(), "f") if menge != menge.to_integral_value() \
            else int(menge)
        zeile["menge_umgedreht"] = True
    if menge == 0:
        # Menge 0 mit einem Betrag ist keine Position, die sich nachrechnen
        # laesst: PEPPOL-EN16931-R120 rechnet 0 x Preis = 0 und vergleicht mit
        # dem Betrag. Frueher fiel die Menge hier stillschweigend auf 1
        # zurueck, waehrend die Vorlage weiterhin 0 ausgab — und die eigene
        # Gegenprobe benutzte denselben Rueckfall und war deshalb blind.
        # Die Menge wird auf 1 gesetzt, sichtbar im Dokument.
        zeile["invoicedquantity"] = 1
        zeile["menge_ersetzt"] = True
        menge = Decimal(1)
    preis = _einzelpreis(betrag, menge)
    zeile.pop("pricebasequantity", None)
    if _rund(menge * preis) == _rund(betrag):
        zeile["priceamount"] = str(preis)
    else:
        zeile["priceamount"] = str(betrag)
        # normalize() allein liefert bei 300 die Form 3E+2 — als xs:decimal
        # ungueltig, und das Dokument waere unbrauchbar gewesen, ohne dass es
        # beim Bauen auffaellt.
        zeile["pricebasequantity"] = format(menge.normalize(), "f")


def _gruppe(kategorie, prozent) -> tuple[str, Decimal]:
    """Schluessel einer Steuergruppe: Kategorie und Satz."""
    return (str(kategorie or "S").upper(), _rund(prozent))


def _dez(wert) -> Decimal:
    try:
        return Decimal(str(wert or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _normalisieren(rechnung: dict) -> dict:
    """Bringt die OPERA-Zahlen in die Form, die EN 16931 verlangt:
    Z-Kategorie auf 0 %, negative Positionen als Abschlag auf Dokumentebene,
    und — der heikle Teil — alle Betraege auf zwei Stellen gerundet, bevor
    irgendetwas summiert wird.

    Zum Runden: OPERA fuehrt Nettobetraege ungerundet (157.73831775701...).
    Wer daraus erst die Summe bildet und dann rundet, bekommt einen anderen
    Wert, als die im Dokument sichtbaren Positionen ergeben — bei 21 Positionen
    waren es zwei Cent. Die Pruefregeln rechnen aber gegen das, was im
    Dokument steht (BR-CO-10, BR-S-08). Also erst runden, dann summieren.

    Die dabei entstehende Differenz zur OPERA-Summe wird nicht stehengelassen,
    sondern auf die groesste Position derselben Steuergruppe gelegt. Sonst
    wuerde die Rechnung einen anderen Betrag fordern als die, die der Gast in
    der Hand hat — und der ist fiskalisch festgeschrieben."""
    zeilen, abschlaege = [], []
    for z in rechnung.get("lines") or []:
        z = dict(z)
        if str(z.get("classifiedtaxcategoryid") or "").upper() == "Z":
            z["classifiedtaxcategorypercent"] = 0
        netto = _rund(z.get("lineextensionamountnet"))
        # Nur der BETRAG entscheidet, nicht der Einzelpreis. Der Preis wird in
        # invoice_lines.sql als Betrag durch Menge gebildet und ist auch dann
        # negativ, wenn die MENGE negativ ist — bei positivem Betrag. Dann
        # wurde eine Gutschrift daraus gemacht, obwohl die Position dem Kunden
        # berechnet wird: aus +50,00 wurde ein Abzug von 50,00, also 100,00
        # Unterschied. BT-146 wird ohnehin neu aus dem Betrag abgeleitet, der
        # gelesene Preis wird sonst nirgends verwendet.
        if netto < 0:
            # Bei der Darstellung je Gast gehoert der Gast auch an den
            # Abschlag — sonst stuende ein Rabatt fuer Zimmer 214 namenlos auf
            # Rechnungsebene, und die Aufteilung auf die Reisenden ginge nicht.
            grund = z.get("itemname") or "Abschlag"
            if z.get("gast_kennung"):
                grund = f"{grund} · {z['gast_kennung']}"
            abschlaege.append({
                "amount": str(abs(netto)),
                "category": z.get("classifiedtaxcategoryid") or "S",
                "percent": z.get("classifiedtaxcategorypercent") or 0,
                "reason": grund,
            })
        else:
            z["lineextensionamountnet"] = str(netto)
            _preis_setzen(z, netto)
            zeilen.append(z)

    # --- Steuergruppen: eine je Kategorie und Satz ---------------------------
    # Die Aufteilung wird aus dem gebildet, was tatsaechlich im Dokument steht.
    # Eine Kategorie, die in einer Position vorkommt, MUSS in der Aufteilung
    # auftauchen (BR-S-01, BR-Z-01) — auch dann, wenn sie sich zu null aufhebt.
    # Genau das war der Fall: Zwei Zeilen "Deposit Tax" mit +147.22 und -147.22
    # in Kategorie Z, aber kein Z-Block in der Aufteilung.
    opera_buckets: dict[tuple[str, Decimal], dict] = {}
    for b in rechnung.get("tax_breakdown") or []:
        b = dict(b)
        if str(b.get("taxcategoryid") or "").upper() == "Z":
            b["taxcategorypercent"] = 0
            if _dez(b.get("taxamount")) != 0:
                b["taxamount"] = "0.00"
        opera_buckets[_gruppe(b.get("taxcategoryid"), b.get("taxcategorypercent"))] = b

    gruppen: dict[tuple[str, Decimal], dict] = {}
    for i, z in enumerate(zeilen):
        g = gruppen.setdefault(
            _gruppe(z.get("classifiedtaxcategoryid"), z.get("classifiedtaxcategorypercent")),
            {"zeilen": [], "abzug": Decimal(0), "abzuege": 0})
        g["zeilen"].append(i)
    for a in abschlaege:
        g = gruppen.setdefault(_gruppe(a.get("category"), a.get("percent")),
                               {"zeilen": [], "abzug": Decimal(0), "abzuege": 0})
        g["abzug"] += _dez(a.get("amount"))
        g["abzuege"] += 1
    for schluessel, b in opera_buckets.items():
        if _dez(b.get("taxableamount")) or _dez(b.get("taxamount")):
            gruppen.setdefault(schluessel, {"zeilen": [], "abzug": Decimal(0), "abzuege": 0})

    steuer = []
    for (kategorie, prozent), g in gruppen.items():
        summe = sum(_dez(zeilen[i].get("lineextensionamountnet")) for i in g["zeilen"])
        basis = summe - g["abzug"]
        bucket = opera_buckets.get((kategorie, prozent))
        if bucket is not None:
            # Rundungsrest auf die groesste Position derselben Gruppe legen.
            # Die Grenze haengt an der Anzahl der Positionen: Jede kann
            # hoechstens einen HALBEN Cent beisteuern, und die Summe aus OPERA
            # rundet selbst noch einmal — also 0,005 * (n + 1). Was darueber
            # hinausgeht, ist kein Rundungsrest, sondern eine echte Abweichung;
            # die bleibt stehen und faellt in der Vorpruefung auf.
            #
            # Hier stand ein GANZER Cent je Position, also das Doppelte. Bei 21
            # Positionen waren das 0,22 statt 0,11 — eine echte Fehlbuchung von
            # 0,15 wurde damit stillschweigend auf die groesste Position
            # geschoben, und die Gegenprobe verglich danach zwei gleiche
            # Zahlen. Die Rechnung haette einen Positionsbetrag ausgewiesen,
            # den es im Haus nicht gibt.
            #
            # ABSCHLAEGE ZAEHLEN MIT: Auch sie sind einzeln gerundete Betraege
            # und tragen je einen halben Cent bei. Solange jede Buchung eine
            # Position war, fiel das kaum auf; seit der Buendelung werden aus
            # acht Positionen drei, waehrend sechs Rabatte mit verschiedenen
            # Betraegen einzeln bleiben — die Grenze sank auf 0,02 bei einem
            # echten Rundungsrest von 0,03, und eine gueltige Rechnung wurde
            # gesperrt.
            rest = _rund(bucket.get("taxableamount")) - basis
            grenze = (Decimal("0.005") * (len(g["zeilen"]) + g["abzuege"] + 1)).max(Decimal("0.01"))
            if rest and abs(rest) <= grenze and g["zeilen"]:
                groesste = max(g["zeilen"],
                               key=lambda i: abs(_dez(zeilen[i].get("lineextensionamountnet"))))
                alt = _dez(zeilen[groesste].get("lineextensionamountnet"))
                zeilen[groesste]["lineextensionamountnet"] = str(alt + rest)
                _preis_setzen(zeilen[groesste], alt + rest)
                basis += rest
        eintrag = dict(bucket) if bucket is not None else {
            "taxcategoryid": kategorie, "taxcategorypercent": float(prozent)}
        eintrag["taxableamount"] = str(basis)
        # Der Steuerbetrag wird aus der GERUNDETEN Grundlage gerechnet, auch
        # wenn OPERA einen eigenen fuehrt. BR-S-09 verlangt genau das:
        # Steuerbetrag = gerundete Grundlage mal Satz. OPERAs Wert stammt aus
        # der ungerundeten Grundlage und weicht dann um einen Cent ab —
        # gesehen an Beleg 1400010: Grundlage 33.87, OPERA 6.43, richtig 6.44.
        if kategorie == "Z" or prozent == 0:
            eintrag["taxamount"] = "0.00"
        else:
            eintrag["taxamount"] = str(_rund(basis * prozent / 100))
        steuer.append(eintrag)
    # Reihenfolge stabil halten: erst die OPERA-Bloecke, dann Ergaenztes
    reihenfolge = list(opera_buckets.keys())
    steuer.sort(key=lambda e: reihenfolge.index(
        _gruppe(e.get("taxcategoryid"), e.get("taxcategorypercent")))
        if _gruppe(e.get("taxcategoryid"), e.get("taxcategorypercent")) in reihenfolge
        else len(reihenfolge))

    aus = dict(rechnung)
    aus["lines"] = zeilen
    aus["tax_breakdown"] = steuer
    aus["allowances"] = abschlaege

    # --- Summen aus dem, was im Dokument steht ------------------------------
    #   BR-CO-10  BT-106 = Summe der Positionen
    #   BR-CO-11  BT-107 = Summe der Abschlaege
    #   BR-CO-13  BT-109 = BT-106 - BT-107 + BT-108
    #   BR-CO-14  BT-110 = Summe der Steuerbetraege
    #   BR-CO-15  BT-112 = BT-109 + BT-110
    # Frueher stand in BT-106 das Rechnungsnetto aus OPERA. Das enthaelt einen
    # Abzug bereits und ist ungerundet — beides passte nicht zu den Positionen.
    summen = dict(rechnung.get("totals") or {})
    opera_brutto = _rund(summen.get("invoicegross")) if "invoicegross" in summen else None
    positionen = sum(_dez(z.get("lineextensionamountnet")) for z in zeilen)
    abzug = sum(_dez(a.get("amount")) for a in abschlaege)
    # BT-110 ist die Summe der GERUNDETEN Steuerbetraege (BR-CO-14). Vorher kam
    # der Wert aus OPERAs ungerundeter Gesamtsumme und lag einen Cent neben der
    # Summe der ausgewiesenen Bloecke.
    steuersumme = sum(_dez(e.get("taxamount")) for e in steuer)
    summen["invoicenet"] = float(positionen)
    summen["taxexclusiveamount"] = float(positionen - abzug)
    summen["invoicetaxtotal"] = float(steuersumme)
    summen["invoicegross"] = float(positionen - abzug + steuersumme)
    if abzug:
        summen["allowancetotalamount"] = float(abzug)

    # --- BT-114: der Cent, der sich nicht wegrechnen laesst -----------------
    # Zwei Rundungen stossen hier aufeinander, und sie sind nicht beide
    # gleichzeitig erfuellbar: Jede Steuergruppe muss fuer sich stimmen
    # (BR-S-09), und das Dokument muss in sich aufgehen (BR-CO-14, BR-CO-15).
    # Die Summe der einzeln gerundeten Werte ist aber nicht immer der gerundete
    # Gesamtwert, den OPERA fuehrt — an Beleg 1400010 ein Cent.
    #
    # Fuer genau diesen Fall gibt es BT-114. Damit bleibt das Dokument
    # regelkonform UND der Zahlbetrag trifft die Forderung des Hauses auf den
    # Cent. Ohne das forderte die Rechnung 10,64, wo im City Ledger 10,63
    # offenstehen. Was groesser ist als ein Rundungsrest, wird nicht
    # ausgeglichen, sondern faellt in der Vorpruefung auf.
    rest = (opera_brutto - _dez(summen["invoicegross"])) if opera_brutto is not None else Decimal(0)
    if rest and abs(rest) <= Decimal("0.05"):
        summen["roundingamount"] = float(rest)
    aus["totals"] = summen
    return aus


def aufbereiten(rechnung: dict) -> dict:
    """Die Rechnung so, wie sie im XML steht — gerundet, mit Abschlaegen und
    Preisen. Fuer die Detailseite: Sie zeigte bisher die ungerundeten Betraege
    aus OPERA, und die wichen von der Datei ab."""
    return _normalisieren(rechnung)


def ausgleich_vorab(rechnung: dict) -> Decimal:
    """BT-114, sofern gesetzt. Eigene Funktion, weil der Wert an zwei Stellen
    gebraucht wird, bevor der Rechnungskopf geprueft ist."""
    return _dez((rechnung.get("totals") or {}).get("roundingamount"))


def pruefsummen(rechnung: dict) -> list[str]:
    """Rechnerische Vorpruefung. Leere Liste heisst: sauber.
    Faengt die Regeln ab, an denen KoSIT sonst scheitert.

    Geprueft wird der Stand NACH der Normalisierung — sonst pruefte man etwas
    anderes, als spaeter im XML steht. Die Rohdaten bleiben daneben stehen:
    Die Normalisierung bildet die Summen selbst und macht das Dokument damit
    in sich stimmig. Ob es auch zu OPERA passt, sagt nur der Vergleich mit den
    ungerechneten Zahlen."""
    roh = rechnung
    rechnung = _normalisieren(rechnung)
    fehler: list[str] = []
    summe_zeilen = sum(_dez(z.get("lineextensionamountnet")) for z in rechnung.get("lines") or [])
    netto = _dez((rechnung.get("totals") or {}).get("invoicenet"))
    brutto = _dez((rechnung.get("totals") or {}).get("invoicegross"))
    if abs(summe_zeilen - netto) > Decimal("0.02"):
        fehler.append(f"BR-CO-10: Summe der Positionen {summe_zeilen} != Rechnungsnetto {netto}")
    # Gegen die OPERA-Zahlen pruefen, nicht gegen die selbst gebildete Summe:
    # Zeilensumme muss Kopf + Anzahlungsbelege desselben Folios ergeben.
    abzug = sum(_dez(a.get("amount")) for a in rechnung.get("allowances") or [])
    k = rechnung.get("kontrolle") or {}
    if k:
        # Gegen die OPERA-Zahlen wird mit den Positionen VOR der Aufteilung
        # verglichen: Dort ist eine Gutschrift eine negative Zeile, hier ist
        # sie ein Abschlag. Ohne das Zurueckrechnen meldet die Klammer bei
        # jeder Gutschrift eine Abweichung, die es nicht gibt.
        soll = _dez(k.get("kopf_netto")) + _dez(k.get("anzahlung_netto"))
        if abs((summe_zeilen - abzug) - soll) > Decimal("0.02"):
            fehler.append(
                f"Folio-Klammer: Positionen {summe_zeilen - abzug} != Kopf {_dez(k.get('kopf_netto'))} "
                f"+ Anzahlungen {_dez(k.get('anzahlung_netto'))}. Rechnung nicht automatisch verarbeiten.")
    steuer_summe = sum(_dez(b.get("taxamount")) for b in rechnung.get("tax_breakdown") or [])
    if abs((netto - abzug + steuer_summe) - brutto) > Decimal("0.02"):
        fehler.append(f"BR-CO-15: Netto {netto} - Abschläge {abzug} + Steuer "
                      f"{steuer_summe} != Brutto {brutto}")
    basis = sum(_dez(b.get("taxableamount")) for b in rechnung.get("tax_breakdown") or [])
    if abs(basis - (netto - abzug)) > Decimal("0.02"):
        fehler.append(f"BR-S-08: Bemessungsgrundlagen {basis} != Positionen minus "
                      f"Abschlaege {netto - abzug}")

    # Gegenprobe zu OPERA, je Steuergruppe. Die Normalisierung legt einen
    # Rundungsrest auf die groesste Position, damit das Dokument in sich
    # aufgeht. Genau deshalb faellt eine ECHTE Abweichung dort nicht mehr auf —
    # sie muss hier auffallen, gegen die ungerechneten Zahlen aus OPERA.
    opera_basis: dict[tuple[str, Decimal], Decimal] = {}
    for b in roh.get("tax_breakdown") or []:
        prozent = 0 if str(b.get("taxcategoryid") or "").upper() == "Z" \
            else b.get("taxcategorypercent")
        opera_basis[_gruppe(b.get("taxcategoryid"), prozent)] = _rund(b.get("taxableamount"))
    for e in rechnung.get("tax_breakdown") or []:
        g = _gruppe(e.get("taxcategoryid"), e.get("taxcategorypercent"))
        if g in opera_basis and abs(_dez(e.get("taxableamount")) - opera_basis[g]) > Decimal("0.02"):
            fehler.append(
                f"Steuergruppe {g[0]}/{g[1]} %: Positionen ergeben {_dez(e.get('taxableamount'))}, "
                f"OPERA fuehrt {opera_basis[g]}. Das ist kein Rundungsrest — bitte prüfen.")
    k_brutto = _dez((rechnung.get("kontrolle") or {}).get("kopf_brutto")) + \
        _dez((rechnung.get("kontrolle") or {}).get("anzahlung_brutto"))
    if k_brutto and abs((brutto + ausgleich_vorab(rechnung)) - k_brutto) > Decimal("0.02"):
        fehler.append(
            f"Gesamtbetrag {brutto} weicht von OPERA ab ({k_brutto}). Die Rechnung "
            "wuerde einen anderen Betrag fordern als der Beleg im Haus.")
    kopf = rechnung.get("header") or {}
    # BR-CO-16: Zahlbetrag = Gesamtbetrag mit USt minus Anzahlung.
    # BT-113 ist ein BRUTTO-Betrag — wer hier versehentlich das Netto der
    # Anzahlungsbelege einsetzt, erzeugt ein in sich stimmiges XML mit
    # falschem Zahlbetrag. Das faellt sonst niemandem auf.
    prepaid = _dez(kopf.get("prepaidamount"))
    payable = _dez(kopf.get("payableamount"))
    ausgleich = _dez((rechnung.get("totals") or {}).get("roundingamount"))
    if kopf.get("payableamount") is not None:
        if abs((brutto - prepaid + ausgleich) - payable) > Decimal("0.02"):
            fehler.append(
                f"BR-CO-16: Brutto {brutto} - Anzahlung {prepaid} + Ausgleich "
                f"{ausgleich} != Zahlbetrag {payable}")
    anz_brutto = sum(_dez(a.get("total_gross")) for a in rechnung.get("deposits") or [])
    if anz_brutto and prepaid < anz_brutto:
        fehler.append(
            f"BT-113: Anzahlungsbelege brutto {anz_brutto}, gemeldet {prepaid} — "
            "vermutlich das Netto statt des Bruttos verwendet")
    if not kopf.get("buyerreference"):
        fehler.append("BR-DE-15: BuyerReference (Leitweg-ID) fehlt")
    if kopf.get("leitweg_udf_fehler"):
        fehler.append(
            f"Das Feld für die Leitweg-ID an der Kartei enthält "
            f"„{kopf.get('leitweg_udf')}“ — {kopf['leitweg_udf_fehler']}. "
            "Als Käuferreferenz wird der Wert deshalb nicht verwendet; für eine "
            "Behörde ist die Rechnung damit nicht zustellbar.")
    if kopf.get("buyerreference_gekuerzt"):
        fehler.append(
            f"BT-10 war {kopf['buyerreference_gekuerzt']} Zeichen lang und wurde auf "
            f"{len(str(kopf.get('buyerreference') or ''))} gekuerzt. Das Feld ist fuer eine "
            "Referenz gedacht, nicht fuer einen Satz — bitte den Eintrag an der "
            "Reservierung ansehen.")
    # Pflichtangaben, die bisher niemand geprueft hat. Fehlten sie, stand im
    # Dokument die Zeichenkette "None" — und die Vorpruefung meldete nichts.
    for feld, name in (("documentcurrencycode", "BT-5: Waehrung"),
                       ("issuedate", "BT-2: Rechnungsdatum"),
                       ("customername", "BT-44: Name des Empfaengers"),
                       ("customercityname", "BT-52: Ort des Empfaengers"),
                       ("customeridentificationcode", "BT-55: Land des Empfaengers")):
        if not str(kopf.get(feld) or "").strip():
            fehler.append(f"{name} fehlt — ohne sie ist die Rechnung nicht gueltig.")
    land = str(kopf.get("customeridentificationcode") or "").strip()
    if land and (len(land) != 2 or not land.isalpha()):
        fehler.append(f"BT-55: '{land}' ist kein Laenderkennzeichen aus zwei "
                      "Buchstaben (BR-CL-14).")
    if not kopf.get("customerendpointid"):
        fehler.append("BT-49: elektronische Adresse des Empfaengers fehlt "
                      "(PEPPOL-EN16931-R010) — Empfaenger auswaehlen")
    if not kopf.get("suppliercompanyid"):
        fehler.append("BT-31: USt-IdNr. des Hauses fehlt (Konfiguration)")
    # BR-DE-6 und BR-DE-7: Telefon UND E-Mail des Hauses sind in XRechnung
    # Pflicht. Fehlt eines, lehnt der Validator ab — und ohne diese Pruefung
    # erfuhr man das erst dort, mit einer Meldung ohne Bezug zur Konfiguration.
    if not str(kopf.get("suppliercontacttelephone") or "").strip():
        fehler.append("BR-DE-6 (BT-42): Telefonnummer des Hauses fehlt — unter Konfiguration → "
                      "Haus eintragen")
    if not str(kopf.get("suppliercontactelectronicmail") or "").strip():
        fehler.append("BR-DE-7 (BT-43): E-Mail-Adresse des Hauses fehlt — unter Konfiguration → "
                      "Haus eintragen")
    if not kopf.get("payeefinancialaccountid"):
        fehler.append("BG-17: IBAN fehlt (Konfiguration)")
    # PEPPOL-EN16931-R120 rechnet Menge mal Einzelpreis nach. Das ist beim
    # Bauen sichergestellt; die Pruefung steht hier, weil ein stiller
    # Rundungsfall in der Preisbildung sonst erst beim Empfaenger auffiele.
    for nr, z in enumerate(rechnung.get("lines") or [], 1):
        if z.get("menge_ersetzt"):
            fehler.append(
                f"Position {nr} ({z.get('itemname')}) hatte die Menge 0 bei einem "
                f"Betrag von {_rund(z.get('lineextensionamountnet'))}. Sie steht "
                "jetzt auf 1 — bitte in OPERA ansehen.")
        # Kein Rueckfall auf 1: Die Gegenprobe muss die Menge pruefen, die im
        # Dokument steht, sonst prueft sie ihre eigene Annahme.
        menge = _dez(z.get("invoicedquantity"))
        bezug = _dez(z.get("pricebasequantity")) or Decimal(1)
        gerechnet = _rund(_dez(z.get("priceamount")) * menge / bezug)
        if gerechnet != _rund(z.get("lineextensionamountnet")):
            fehler.append(
                f"PEPPOL-EN16931-R120, Position {nr}: {menge} x "
                f"{_dez(z.get('priceamount'))} ergibt {gerechnet}, ausgewiesen ist "
                f"{_rund(z.get('lineextensionamountnet'))}")
    # PEPPOL-EN16931-R110/R111: Der Zeitraum einer Position muss im
    # Rechnungszeitraum liegen. Fatal im KoSIT-Regelwerk — und bei Gruppen
    # mit verschiedenen Anreisetagen der naheliegende Fehler, sobald der Kopf
    # nur den Aufenthalt einer Reservierung traegt.
    if kopf.get("startdate") and kopf.get("enddate"):
        for nr, z in enumerate(rechnung.get("lines") or [], 1):
            if z.get("zeitraum_beginn") and str(z["zeitraum_beginn"]) < str(kopf["startdate"]):
                fehler.append(f"PEPPOL-EN16931-R110, Position {nr}: Beginn {z['zeitraum_beginn']} "
                              f"liegt vor dem Rechnungszeitraum ({kopf['startdate']})")
            if z.get("zeitraum_ende") and str(z["zeitraum_ende"]) > str(kopf["enddate"]):
                fehler.append(f"PEPPOL-EN16931-R111, Position {nr}: Ende {z['zeitraum_ende']} "
                              f"liegt nach dem Rechnungszeitraum ({kopf['enddate']})")
    if not (rechnung.get("lines") or []):
        fehler.append("BG-25: Die Rechnung hat keine Position")

    # Letzte Verteidigungslinie gegen den Namen eines FREMDEN Gastes.
    # opera._ohne_personenbezug raeumt Routing-Hinweise und Rufnummern aus
    # REMARK heraus (dort steht "Routed From <Name> Of Room <Nr>", an echten
    # Daten in 14,9 % der belegten Werte). Kommt so etwas hier trotzdem an,
    # ist der Filter umgangen worden — dann wird nicht versendet, sondern
    # nachgesehen. Lieber eine Rechnung in der Pruefung als der Aufenthalt
    # eines Unbeteiligten bei einer fremden Firma.
    for nr, z in enumerate(rechnung.get("lines") or [], 1):
        bem = str(z.get("bemerkung") or "")
        if "routed from" in bem.lower():
            fehler.append(f"Position {nr}: Die Bemerkung nennt einen fremden Gast "
                          "(Routing-Hinweis aus OPERA). Nicht versenden.")
        # Ab 13 Stellen, nicht ab 6. Diese Stelle stand kurz auf 6 — das haette
        # jede Rechnung mit einer Gutscheinnummer blockiert ("Voucher 09000001",
        # acht Stellen) und Abrechnungsnummern mit sechs dazu. Beides sind
        # Angaben, mit denen der Kunde die Position zuordnet; sie hier
        # anzuhalten waere ein sicherer Schaden gegen einen hypothetischen.
        #
        # 13 Stellen ist Kartenlaenge (13 bis 19) und die Laenge einer
        # internationalen Rufnummer. Kuerzere Rufnummern faengt der Filter an
        # der Quelle, wo das FELD bekannt ist — dort ist REFERENCE scharf
        # gestellt (ab 5) und REMARK locker (opera._ZIFFERN_AB). Ohne das Feld
        # laesst sich eine Gutscheinnummer von einer Ortsrufnummer nicht
        # unterscheiden, und hier ist das Feld nicht mehr bekannt.
        elif re.search(r"\d{13,}", bem):
            fehler.append(f"Position {nr}: Die Bemerkung enthaelt eine sehr lange "
                          "Ziffernfolge — das sieht nach Karten- oder Rufnummer "
                          "aus. Nicht versenden.")

    # Der Beleg muss in OPERA NOCH eine gueltige Endrechnung sein. Beim
    # Einlesen war er es; waehrend der Wartezeit kann er storniert worden
    # sein (VOID) und fiel dann aus der Einleseliste — versendet wurde er
    # trotzdem. Gelesen wird der Status bei jedem Erzeugen neu.
    status = str(kopf.get("beleg_status") or "").strip().upper()
    art = str(kopf.get("document_type") or "").strip().upper()
    if "beleg_status" in kopf and status != "OK":
        fehler.append(f"Der Beleg hat in OPERA den Status „{status or 'leer'}“, nicht OK — "
                      "vermutlich storniert. Nicht versenden.")
    if "document_type" in kopf and art != "INVOICE":
        fehler.append(f"Der Beleg ist in OPERA ein „{art or 'leer'}“, keine Endrechnung "
                      "(INVOICE). Nicht als Rechnung versenden.")

    # Unabhaengige Gegenprobe gegen die Buckets des RECHNUNGSKOPFS. Die
    # Steueraufteilung oben kommt aus den Positionen; die Probe dagegen
    # verglich bisher die Positionen mit sich selbst. Angewandt nur, wenn der
    # Kopf in sich aufgeht (Summe der Buckets = Kopfnetto) und keine Anzahlung
    # im Spiel ist — mit Anzahlung traegt der Kopf nur den Rest.
    kopfbuckets = roh.get("tax_kopf") or []
    if kopfbuckets and not (rechnung.get("deposits") or []):
        je_satz: dict[Decimal, Decimal] = {}
        for b in kopfbuckets:
            satz = _rund(b.get("taxcategorypercent") or 0)
            je_satz[satz] = je_satz.get(satz, Decimal(0)) + _dez(b.get("taxableamount"))
        kopf_netto = _dez((rechnung.get("kontrolle") or {}).get("kopf_netto"))
        if abs(sum(je_satz.values()) - kopf_netto) <= Decimal("0.02"):
            gebildet: dict[Decimal, Decimal] = {}
            for e in rechnung.get("tax_breakdown") or []:
                satz = _rund(0 if str(e.get("taxcategoryid") or "").upper() == "Z"
                             else e.get("taxcategorypercent"))
                gebildet[satz] = gebildet.get(satz, Decimal(0)) + _dez(e.get("taxableamount"))
            # Sicherung gegen eine Annahme, die niemand an Daten geprueft hat:
            # Fuehrt der Kopf die Saetze anders als die Positionen — etwa 0.19
            # statt 19 —, passte kein einziger Satz zusammen, und die Gegenprobe
            # sperrte JEDE Rechnung. Ohne eine einzige Ueberschneidung wird sie
            # deshalb nicht angewandt, sondern vermerkt.
            # Verglichen werden die Saetze UEBER NULL: Die Kategorie Z steht
            # in beiden Listen mit 0 und wuerde sonst immer eine Gemeinsamkeit
            # vortaeuschen.
            kopf_saetze = {s for s in je_satz if s > 0}
            doku_saetze = {s for s in gebildet if s > 0}
            if kopf_saetze and doku_saetze and not (kopf_saetze & doku_saetze):
                log.warning("Steuersaetze des Rechnungskopfs (%s) passen zu keinem Satz der "
                            "Positionen (%s) — die Gegenprobe gegen den Kopf bleibt aus",
                            sorted(kopf_saetze), sorted(doku_saetze))
            else:
                for satz in sorted(set(je_satz) | set(gebildet)):
                    a, b = gebildet.get(satz, Decimal(0)), _rund(je_satz.get(satz, Decimal(0)))
                    if abs(a - b) > Decimal("0.02"):
                        fehler.append(
                            f"Steuersatz {satz} %: Die Positionen ergeben {a}, der Rechnungskopf in "
                            f"OPERA fuehrt {b}. Bitte in OPERA prüfen.")
    # Nullbelege: Gesamtbetrag 0,00, aber eine City-Ledger-Zahlung dagegen.
    # In der Zielmenge drei Stueck in 90 Tagen — vermutlich Ausgleichs- oder
    # Umbuchungspaare. Daraus entstuende eine Rechnung ueber 0,00 EUR mit einem
    # Zahlbetrag, der zu nichts passt. Solche Belege gehoeren nicht in den Versand.
    # Massgeblich ist, was OPERA meldet: Ob ein Beleg eine Gutschrift ist,
    # entscheidet der Beleg, nicht unsere nachgerechnete Summe.
    roh_summen = roh.get("totals") or {}
    gemeldet = _dez(roh_summen.get("invoicegross")) if "invoicegross" in roh_summen else brutto
    if gemeldet == 0:
        fehler.append("Nullbeleg: Gesamtbetrag 0,00 — kein Versand, bitte im Haus klären")
    elif gemeldet < 0:
        fehler.append(f"Negativer Gesamtbetrag {gemeldet} — gehoert als Gutschrift (381) "
                      "ausgegeben, nicht als Rechnung (380)")
    return fehler


def _leere_elemente_entfernen(wurzel) -> int:
    """Elemente ohne Inhalt und ohne Kinder entfernen. Gibt die Anzahl zurueck.

    XRechnung verbietet leere Elemente (KoSIT-Regel R008). Die Vorlage schreibt
    aber jedes Feld hin, auch ein optionales ohne Wert — bei einer Rechnung, an
    deren Profil keine Strasse steht, entstand <cbc:StreetName></cbc:StreetName>
    und die Rechnung wurde zurueckgewiesen. Und zwar aus dem falschen Grund:
    BT-50 ist optional, die Rechnung waere OHNE das Element gueltig gewesen.
    Der Anwender sah nur "Document MUST not contain empty elements", ohne zu
    erfahren, welches.

    Statt in der Vorlage zwanzig {% if %} zu verteilen — von denen der naechste
    eines vergisst — wird hier einmal aufgeraeumt. Was PFLICHT ist und fehlt,
    meldet die Vorpruefung beim Namen; das ist die verstaendlichere Auskunft.

    Mehrfach, weil ein Elternteil leer wird, sobald sein letztes Kind geht."""
    entfernt = 0
    while True:
        weg = [el for el in wurzel.iter()
               if el is not wurzel and len(el) == 0
               and not (el.text or "").strip()]
        if not weg:
            return entfernt
        for el in weg:
            el.getparent().remove(el)
            entfernt += 1


# Die XRechnung-Versionen, die diese Anwendung erzeugen kann. Eine neue Version
# ist ein Eintrag hier, eine Vorlage in xml_templates/ und ein Regelwerk unter
# validation/<regelwerk>/ — siehe docs/03_NORM_UND_TERMINE.md.
#
# XRechnung 4.0 steht bewusst NICHT darin: Am 14.09.2026 gibt es weder die
# Spezifikation noch ein Regelwerk. Eine Vorlage ohne Validator waere geraten.
VERSIONEN = {
    "3.0.2": {
        "vorlage": "xrechnung_3.0.xml.j2",
        # BT-24. Seit 3.0 xeinkauf.de, nicht mehr xoev-de — mit der alten
        # Kennung greift im Validator kein Pruefszenario.
        "customizationid": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
        "regelwerk": "xrechnung-3.0.2",
    },
}
STANDARD_VERSION = "3.0.2"
# Frueher hiess der Parameter von bauen() "3.0". Wer das noch uebergibt, meint 3.0.2.
_ALTE_NAMEN = {"3.0": "3.0.2"}


def version_aus(cfg: dict | None) -> str:
    """Die eingestellte XRechnung-Version. Wirft XmlFehler bei einem
    unbekannten Wert — eine Rechnung in einer Version, die niemand pruefen
    kann, soll gar nicht erst entstehen, statt still auf 3.0.2 zu fallen."""
    roh = str(((cfg or {}).get("xrechnung") or {}).get("version") or STANDARD_VERSION).strip()
    version = _ALTE_NAMEN.get(roh, roh)
    if version not in VERSIONEN:
        raise XmlFehler(f"XRechnung-Version „{roh}“ ist nicht verfügbar — möglich: "
                        + ", ".join(VERSIONEN))
    return version


def bauen(rechnung: dict, version: str = STANDARD_VERSION) -> bytes:
    version = _ALTE_NAMEN.get(version, version)
    if version not in VERSIONEN:
        raise XmlFehler(f"XRechnung-Version „{version}“ ist nicht verfügbar — möglich: "
                        + ", ".join(VERSIONEN))
    angaben = VERSIONEN[version]
    aufbereitet = _normalisieren(rechnung)
    vorlage = _env.get_template(angaben["vorlage"])
    xml = vorlage.render(customizationid=angaben["customizationid"],
                         **aufbereitet).encode("utf-8")
    try:
        baum = etree.fromstring(xml)
    except etree.XMLSyntaxError as e:
        raise XmlFehler(f"XML ist nicht wohlgeformt: {e}") from e
    if _leere_elemente_entfernen(baum):
        xml = etree.tostring(baum, xml_declaration=True, encoding="UTF-8",
                             pretty_print=True)
    return xml
