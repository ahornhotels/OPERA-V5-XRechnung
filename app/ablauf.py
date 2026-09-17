"""Der Ablauf einer Rechnung: einlesen, pruefen, XML bauen, versenden.
Wird sowohl von der Oberflaeche als auch von der Automatik benutzt —
damit gilt fuer den Knopfdruck und den Automatiklauf dieselbe Logik."""
from __future__ import annotations
import logging
import threading
from pathlib import Path

from . import opera, pfade, store, validate, xml_build, mailer

log = logging.getLogger(__name__)
# An einer Stelle formuliert, damit Setzen und Wiedererkennen nicht
# auseinanderlaufen — eine Textsuche nach einem anderswo geschriebenen Satz
# ist genau die Art Kopplung, die still bricht.
HINWEIS_OHNE_ADRESSE = ("Am Empfängerprofil ist keine E-Mail-Adresse hinterlegt "
                        "— Adresse eintragen oder Profil pflegen")
# Es gibt einen Eintrag, aber er taugt nicht als Empfaenger: mehrere Adressen
# in einem Feld, ein Name davor, ein Semikolon. Wer das als "keine Adresse"
# meldet, schickt jemanden zu einem Profil, an dem sehr wohl etwas steht.
HINWEIS_ADRESSE_UNBRAUCHBAR = ("Am Empfängerprofil steht keine einzelne gültige E-Mail-Adresse "
                               "(mehrere Adressen in einem Feld?) — in OPERA auf eine Adresse "
                               "zurückschneiden")
TRENNER = " · "


def hinweis_dazu(vorher: str | None, hinweis: str) -> str:
    """Einen Hinweis ergaenzen, ohne die vorhandenen zu verlieren."""
    teile = [x.strip() for x in (vorher or "").split(TRENNER) if x.strip()]
    if hinweis not in teile:
        teile.append(hinweis)
    return TRENNER.join(teile)


def hinweis_weg(vorher: str | None, hinweis: str) -> str | None:
    """Einen Hinweis herausnehmen und die anderen stehen lassen.

    Frueher wurde das ganze Feld geleert. Damit verschwand mit der geloesten
    Adressfrage auch der Grund, aus dem der Beleg sonst noch in der
    Sichtpruefung stand — etwa die Firma an der Reservierung."""
    teile = [x.strip() for x in (vorher or "").split(TRENNER) if x.strip() and x.strip() != hinweis]
    return TRENNER.join(teile) or None
BASE = pfade.PROGRAMM


def zur_pruefung(bill_no: int, grund: str) -> None:
    """Einen Beleg in die Sichtpruefung legen und den Grund DAZUschreiben.

    Vorher setzte jede Stelle das Fehlerfeld neu. Bei einem neuen Beleg mit
    Firma an der Reservierung UND ohne Adresse ueberschrieb der zweite Grund
    den ersten; sobald die Adresse gepflegt war, gab _auffrischen den Beleg
    frei, und die Automatik versendete ihn ohne die zugesicherte Pruefung."""
    vorher = (store.rechnung(bill_no) or {}).get("fehler")
    store.setzen(bill_no, status="pruefung", fehler=hinweis_dazu(vorher, grund))


def _ordner(cfg: dict, schluessel: str) -> Path:
    """Die Ablage der erzeugten Rechnungen. Relative Angaben gelten gegenueber
    der INSTALLATION, nicht gegenueber dem Programm.

    Der Unterschied entscheidet ueber aufbewahrungspflichtige Belege: In der
    Konfiguration steht "data/xml". Loeste das gegen das Programmverzeichnis
    auf, laegen die Rechnungen in der Freigabe — und das Aufraeumen alter
    Freigaben loeschte sie nach der dritten Aktualisierung."""
    pfad = pfade.im_bestand(cfg["ablage"][schluessel])
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def einlesen(cfg: dict, tage: int | None = None) -> dict:
    """Holt neue Rechnungen aus OPERA in die Arbeitsliste. Gibt eine Aufstellung
    zurueck: wie viele gelesen, aufgenommen, uebersprungen und warum. Ohne die
    waere nicht nachvollziehbar, warum von 300 Rechnungen 12 uebrig bleiben."""
    a = cfg["automatik"]
    s = cfg.get("auswahl") or {}
    p_auswahl = cfg.get("property") or {}
    zahlen = {"gelesen": 0, "neu": 0, "bekannt": 0, "pruefung": 0,
              "ohne_firmenbezug": 0, "ausland": 0, "zu_klein": 0, "nullbeleg": 0}
    neu = 0
    gelesen = opera.kandidaten(cfg, tage)
    zahlen["gelesen"] = len(gelesen)
    for r in gelesen:
        bezug = r.get("firmenbezug") or "-"

        # Das benutzerdefinierte Kennzeichen an der Firmenkartei. Was ein
        # Eintrag dort BEDEUTET, entscheidet das Haus: Bei einem gewachsenen
        # Karteibestand ist
        # "erlaubt" nur praktikabel, wenn jemand sie vorher anfasst — deshalb
        # ist "schliesst_aus" die Vorgabe. Ein leerer Feldname ueberspringt die
        # Stufe ganz, dann gilt die Auswahl wie bisher.
        kennzeichen = str(r.get("erechnung_kennzeichen") or "").strip()
        bedeutung = (p_auswahl.get("udf_erechnung_bedeutung") or "schliesst_aus").lower()
        if (p_auswahl.get("udf_erechnung") or "").strip():
            if bedeutung == "erlaubt" and not kennzeichen:
                zahlen["ohne_kennzeichen"] = zahlen.get("ohne_kennzeichen", 0) + 1
                continue
            if bedeutung != "erlaubt" and kennzeichen:
                zahlen["ausgeschlossen"] = zahlen.get("ausgeschlossen", 0) + 1
                continue

        # Kein Anhaltspunkt fuer eine Firma — nicht aufnehmen.
        if a.get("nur_mit_firmenbezug", True) and bezug == "-":
            zahlen["ohne_firmenbezug"] += 1
            continue
        # Firma nur an der Reservierung: der Zahler kann eine Privatperson sein.
        if bezug == "RESERVIERUNG" and not s.get("reservierungsfirma_aufnehmen", True):
            zahlen["ohne_firmenbezug"] += 1
            continue
        # Ausland aussortieren. Ein leeres Land wird NICHT stillschweigend als
        # Inland gewertet — die Rechnung kommt in die Pruefung, damit sie
        # nicht unbemerkt verschwindet.
        land = (r.get("empfaenger_land") or "").upper()
        inland = [k.upper() for k in (s.get("inlandskennzeichen") or ["DE"])]
        if s.get("nur_inland", True) and land and land not in inland:
            zahlen["ausland"] += 1
            continue
        ohne_land = s.get("nur_inland", True) and not land
        # Die Betragsgrenze gilt nur fuer POSITIVE Betraege. Vorher lief sie
        # zuerst und verglich auch negative dagegen: Mit der Vorgabe 0 fiel
        # damit jeder negative Beleg als "unter dem Mindestbetrag" heraus —
        # unsichtbar, in keinem Status, und in der Aufstellung unter einer
        # Regel gezaehlt, die niemand gesetzt hat. Der Zweig weiter unten, der
        # ihn sichtbar zuruecklegen sollte, war damit nie erreichbar.
        brutto = float(r.get("total_gross") or 0)
        if brutto > 0 and brutto < float(s.get("mindestbetrag_brutto") or 0):
            zahlen["zu_klein"] += 1
            continue
        satz = {
            "bill_no": int(r["bill_no"]),
            "resort": cfg["property"]["resort"],
            "invoice_no": str(r.get("invoice_no") or ""),
            "issuedate": r.get("issuedate"),
            "total_net": float(r.get("total_net") or 0),
            "total_gross": float(r.get("total_gross") or 0),
            "kunde": r.get("company_name") or r.get("payee_name") or "",
            "leitweg_id": r.get("leitweg_id"),
            "empfaenger_typ": r.get("empfaenger_typ"),
            "empfaenger_land": r.get("empfaenger_land"),
            "city_ledger": float(r.get("city_ledger") or 0),
            "name_id": int(r["name_id"]) if r.get("name_id") else None,
        }
        satz["firmenbezug"] = bezug
        if store.rechnung_anlegen(satz, int(a.get("wartezeit_minuten", 120))):
            neu += 1
            # Firma nur an der Reservierung: nie ohne Sichtpruefung versenden.
            # Ein Beleg kann MEHRERE Gruende haben — gezaehlt wird er trotzdem
            # einmal. Sonst nennt der Bericht mehr Sichtpruefungen, als es
            # Rechnungen gibt.
            in_pruefung = False
            if bezug == "RESERVIERUNG" and s.get("reservierungsfirma_pruefen", True):
                zur_pruefung(satz["bill_no"], "Firma hängt an der Reservierung, nicht am Zahler — bitte prüfen")
                store.protokoll("pruefung", "Firma an der Reservierung — Sichtprüfung",
                                bill_no=satz["bill_no"])
                in_pruefung = True
            if ohne_land:
                zur_pruefung(satz["bill_no"], "Am Empfängerprofil ist kein Land gepflegt — Inland prüfen")
                store.protokoll("pruefung", "kein Land am Profil", bill_no=satz["bill_no"])
                in_pruefung = True
            zahlen["pruefung"] += 1 if in_pruefung else 0
            # Nullbelege und negative Betraege gar nicht erst in den Lauf lassen —
            # sichtbar zuruecklegen, nicht stillschweigend ueberspringen.
            #
            # ABER: Ein negativer KOPFbetrag heisst nicht Gutschrift. Liegen
            # Anzahlungen auf demselben Folio, ist der Kopf nur der Rest, und
            # die Rechnung ist voellig in Ordnung — Beleg 1400015 hat -703,05
            # im Kopf und 9.353,09 in den Zeilen. Solche Faelle gehoeren in die
            # Sichtpruefung, nicht in den Papierkorb.
            #
            # Das gilt auch fuer einen Kopf von GENAU 0,00: Decken die
            # Anzahlungen den Aufenthalt vollstaendig, ist die Schlussrechnung
            # trotzdem geschuldet (Positionen, BT-113 Anzahlung, BT-115 Zahlbetrag
            # 0,00). Vorher wurde sie als Nullbeleg dauerhaft zurueckgelegt.
            mit_anzahlung = str(r.get("ohne_anzahlung") or "J").upper() == "N"
            if satz["total_gross"] <= 0 and mit_anzahlung:
                zur_pruefung(satz["bill_no"],
                             f"Kopfbetrag {satz['total_gross']:.2f}, aber Anzahlungen auf "
                             "demselben Folio — die Zeilensumme entscheidet. Bitte ansehen.")
                store.protokoll("pruefung", "Kopfbetrag nicht positiv, mit Anzahlung",
                                bill_no=satz["bill_no"])
                zahlen["pruefung"] += 0 if in_pruefung else 1
                continue
            if satz["total_gross"] <= 0:
                grund = ("Gesamtbetrag 0,00" if satz["total_gross"] == 0
                         else f"negativer Gesamtbetrag {satz['total_gross']:.2f}")
                store.setzen(satz["bill_no"], status="ignoriert",
                             fehler=f"{grund} — automatisch zurückgelegt")
                store.protokoll("zurueckgelegt", grund, bill_no=satz["bill_no"])
                zahlen["nullbeleg"] += 1
                continue
            # Die Adressfrage wird IMMER gestellt, nicht nur wenn die
            # Automatik Empfaenger vorschlagen darf: Ob eine Rechnung
            # zustellbar ist, haengt nicht an dieser Einstellung.
            adressen = empfaenger_kandidaten(satz["bill_no"])
            if adressen is not None:
                store.setzen(satz["bill_no"], adresse_fehlt=0 if adressen else 1)
            if adressen and a.get("empfaenger_automatisch"):
                store.setzen(satz["bill_no"], empfaenger=adressen[0]["email"])
            elif adressen == []:
                # Es gibt Firmenprofile ganz ohne Mailadresse — gesehen an
                # 1400010 und zwei weiteren. Ohne Adresse ist die Rechnung
                # nicht zustellbar, und BT-49 bleibt leer (Pflichtfeld).
                # Das gehoert vorne gesagt, nicht als Fehler beim Versuch:
                # Jemand muss die Adresse am Profil pflegen oder von Hand
                # eintragen, und das dauert.
                zur_pruefung(satz["bill_no"], adresshinweis(satz["bill_no"]))
                store.protokoll("pruefung", "keine brauchbare Mailadresse am Profil",
                                bill_no=satz["bill_no"])
                zahlen["pruefung"] += 0 if in_pruefung else 1
        else:
            zahlen["bekannt"] += 1
            _auffrischen(satz, a, s, zahlen)
    zahlen["neu"] = neu
    store.protokoll("einlesen", bericht(zahlen))
    # Die Obergrenze gehoert HIER gemeldet, nicht nur auf der Seite des
    # Knopfes: Die Automatik liest ebenso ein, und dort sah es niemand.
    grenze = int(s.get("hoechstens", 2000))
    if zahlen["gelesen"] >= grenze:
        zahlen["grenze_erreicht"] = grenze
        store.protokoll("einlesen", f"ACHTUNG: Obergrenze von {grenze} erreicht — ältere "
                        "Rechnungen fehlen. Zeitraum verkleinern oder Obergrenze erhöhen.",
                        erfolg=False)
    return zahlen


def _auffrischen(satz: dict, a: dict, s: dict, zahlen: dict) -> None:
    """Einen BEKANNTEN Beleg mit neuen Erkenntnissen versorgen.

    rechnung_anlegen() legt nur an, was noch nicht da ist — das ist richtig,
    sonst uebeschriebe ein Einlesen die Handarbeit des Anwenders. Es hatte aber
    zur Folge, dass ein bestehender Datensatz auf ewig in der Fassung des Tages
    stand, an dem er eingelesen wurde: Weder eine inzwischen gepflegte Adresse
    noch eine verbesserte Suche kamen je bei ihm an. Nach der Erweiterung auf
    Rechnungsanschrift und Debitorenkonto blieben 21 Belege als 'ohne Adresse'
    stehen, obwohl sie laengst eine hatten.

    Aufgefrischt wird deshalb, was die Anwendung ABLEITET — nie, was der
    Anwender gesetzt hat: Ein eingetragener Empfaenger, ein Status und ein
    Versandvermerk bleiben unangetastet."""
    bekannt = store.rechnung(satz["bill_no"])
    if not bekannt:
        return
    if bekannt.get("status") in ("gesendet", "ignoriert"):
        return
    aenderungen = {}
    if satz.get("name_id") and not bekannt.get("name_id"):
        aenderungen["name_id"] = satz["name_id"]

    if not (bekannt.get("empfaenger") or "").strip():
        adressen = empfaenger_kandidaten(satz["bill_no"])
        if adressen is not None:
            fehlt = 0 if adressen else 1
            if bekannt.get("adresse_fehlt") != fehlt:
                aenderungen["adresse_fehlt"] = fehlt
        if adressen:
            if a.get("empfaenger_automatisch"):
                aenderungen["empfaenger"] = adressen[0]["email"]
            # Der Hinweis war einmal richtig und ist es nicht mehr.
            if HINWEIS_OHNE_ADRESSE in (bekannt.get("fehler") or "") \
                    or HINWEIS_ADRESSE_UNBRAUCHBAR in (bekannt.get("fehler") or ""):
                rest = hinweis_weg(hinweis_weg(bekannt.get("fehler"), HINWEIS_OHNE_ADRESSE),
                                   HINWEIS_ADRESSE_UNBRAUCHBAR)
                aenderungen["fehler"] = rest
                # Nur zurueck aus der Sichtpruefung, wenn KEIN anderer Grund
                # mehr steht — sonst holte die geloeste Adressfrage einen
                # Beleg heraus, den jemand aus einem anderen Grund ansehen soll.
                if bekannt.get("status") == "pruefung" and not rest:
                    aenderungen["status"] = "neu"
        elif adressen == [] and HINWEIS_OHNE_ADRESSE not in (bekannt.get("fehler") or "") \
                and HINWEIS_ADRESSE_UNBRAUCHBAR not in (bekannt.get("fehler") or ""):
            # Ein Beleg kann schon aus einem anderen Grund in der Sichtpruefung
            # stehen — dann kommt der Hinweis DAZU. Frueher wurde er nur
            # gesetzt, wenn das Feld leer war; gut ein Drittel der Pflegefaelle blieb
            # deshalb unmarkiert.
            aenderungen["fehler"] = hinweis_dazu(bekannt.get("fehler"), adresshinweis(satz["bill_no"]))
            if bekannt.get("status") != "pruefung":
                aenderungen["status"] = "pruefung"
                zahlen["pruefung"] += 1
    # Die Profilnummer nachzutragen ist Buchhaltung, keine Aenderung am Fall.
    # Sie mitzuzaehlen machte aus 21 wirklichen Auffrischungen eine 401 und
    # damit eine Zahl, die "angefasst" heisst und wie "geaendert" aussieht.
    inhaltlich = [k for k in aenderungen if k != "name_id"]
    if aenderungen:
        store.setzen(satz["bill_no"], **aenderungen)
        if inhaltlich:
            zahlen["aufgefrischt"] = zahlen.get("aufgefrischt", 0) + 1
        else:
            zahlen["ergaenzt"] = zahlen.get("ergaenzt", 0) + 1


def aufnehmen(cfg: dict, bill_no: int) -> str:
    """Eine in OPERA gefundene Rechnung von Hand in die Arbeitsliste holen.

    Der Weg fuer alles, was das Einlesen nicht erfasst: aeltere Belege,
    aussortierte, oder solche, nach denen jemand gezielt sucht. Anders als
    beim Einlesen wird hier NICHT gefiltert — wer eine bestimmte Rechnung
    ausdruecklich anfordert, soll sie bekommen. Wuerde sie beim Einlesen
    durchfallen, kommt sie stattdessen mit dem Grund in die Sichtpruefung:
    sichtbar statt stillschweigend verschwunden."""
    treffer = [r for r in opera.suchen(cfg, str(bill_no))
               if int(r.get("bill_no") or 0) == int(bill_no)]
    if not treffer:
        raise LookupError(f"Rechnung {bill_no} ist in OPERA nicht zu finden")
    r = treffer[0]
    s = cfg.get("auswahl") or {}
    a = cfg["automatik"]

    satz = {
        "bill_no": int(r["bill_no"]),
        "resort": cfg["property"]["resort"],
        "invoice_no": str(r.get("invoice_no") or ""),
        "issuedate": r.get("issuedate"),
        "total_net": float(r.get("total_net") or 0),
        "total_gross": float(r.get("total_gross") or 0),
        "kunde": r.get("kunde") or r.get("company_name") or "",
        "empfaenger_typ": r.get("empfaenger_typ"),
        "empfaenger_land": r.get("empfaenger_land"),
        "city_ledger": float(r.get("city_ledger") or 0),
        "name_id": int(r["name_id"]) if r.get("name_id") else None,
        "firmenbezug": r.get("firmenbezug") or "-",
    }
    if not store.rechnung_anlegen(satz, int(a.get("wartezeit_minuten", 120))):
        return f"Rechnung {bill_no} steht bereits in der Arbeitsliste."

    gruende: list[str] = []
    land = (r.get("empfaenger_land") or "").upper()
    inland = [k.upper() for k in (s.get("inlandskennzeichen") or ["DE"])]
    if s.get("nur_inland", True) and land and land not in inland:
        gruende.append(f"Empfänger im Ausland ({land})")
    if not land:
        gruende.append("Am Empfängerprofil ist kein Land gepflegt")
    if satz["firmenbezug"] == "-":
        gruende.append("Kein Firmenbezug erkennbar")
    elif satz["firmenbezug"] == "RESERVIERUNG":
        gruende.append("Firma hängt an der Reservierung, nicht am Zahler")
    if satz["total_gross"] <= 0:
        gruende.append(f"Gesamtbetrag {satz['total_gross']:.2f}")
    elif satz["total_gross"] < float(s.get("mindestbetrag_brutto") or 0):
        gruende.append(f"Gesamtbetrag unter dem Mindestbetrag ({satz['total_gross']:.2f})")
    if str(r.get("beleg_status") or "").upper() != "OK":
        gruende.append(f"Belegstatus {r.get('beleg_status')}")
    # Beim Einlesen kommen nur Endrechnungen (INVOICE) in die Liste. Aus der
    # Suche kam bisher alles — eine Anzahlungs- oder Zwischenrechnung stand
    # ohne Pruefgrund als 'neu' da und ging nach der Wartezeit als Rechnung
    # hinaus, zusaetzlich zur Schlussrechnung fuer denselben Aufenthalt.
    if str(r.get("document_type") or "").upper() != "INVOICE":
        gruende.append(f"Dokumentart {r.get('document_type') or 'leer'}, keine Endrechnung")
    # Das Kennzeichen an der Firmenkartei, wie beim Einlesen.
    p_cfg = cfg.get("property") or {}
    udf = (p_cfg.get("udf_erechnung") or "").strip()
    if udf and satz["name_id"]:
        kennzeichen = opera.udf_feld(satz["name_id"], udf)
        if (p_cfg.get("udf_erechnung_bedeutung") or "schliesst_aus").lower() == "erlaubt":
            if not kennzeichen:
                gruende.append("Am Profil fehlt das E-Rechnungs-Kennzeichen")
        elif kennzeichen:
            gruende.append("Am Profil als 'keine E-Rechnung' gekennzeichnet")

    adressen = empfaenger_kandidaten(satz["bill_no"])
    if adressen is not None:
        store.setzen(satz["bill_no"], adresse_fehlt=0 if adressen else 1)
    if adressen and a.get("empfaenger_automatisch"):
        store.setzen(satz["bill_no"], empfaenger=adressen[0]["email"])
    elif adressen:
        # Der Schalter steht auf "Empfaenger von Hand waehlen". Dann darf auch
        # dieser Weg keine Adresse eintragen — sonst steht die Rechnung mit
        # Status 'neu' und gefuelltem Empfaenger da und wird vom naechsten
        # Automatiklauf verschickt, an eine Adresse, die niemand bestaetigt hat.
        gruende.append("Empfänger noch nicht gewählt")
    elif adressen == []:
        gruende.append(adresshinweis(satz["bill_no"]))

    if gruende:
        store.setzen(satz["bill_no"], status="pruefung",
                     fehler=TRENNER.join(["Von Hand aufgenommen"] + gruende))
    store.protokoll("aufgenommen",
                    "von Hand aus der Suche" + (f" — {'; '.join(gruende)}" if gruende else ""),
                    bill_no=satz["bill_no"])
    return (f"Rechnung {bill_no} aufgenommen"
            + (" — sie steht in der Sichtprüfung: " + "; ".join(gruende) if gruende else "."))


def bericht(z: dict) -> str:
    """Aus der Aufstellung einen Satz machen, der die Frage beantwortet:
    Warum sind aus so vielen Rechnungen so wenige geworden?"""
    teile = [f"{z['gelesen']} gelesen", f"{z['neu']} neu aufgenommen"]
    if z["bekannt"]:
        teile.append(f"{z['bekannt']} bereits bekannt")
    if z["pruefung"]:
        teile.append(f"{z['pruefung']} zur Sichtprüfung")
    for schluessel, text in (("ohne_firmenbezug", "ohne Firmenbezug"),
                             ("ausland", "ausländischer Empfänger"),
                             ("zu_klein", "unter dem Mindestbetrag"),
                             ("nullbeleg", "Nullbeleg"),
                             ("ausgeschlossen", "am Profil ausgeschlossen"),
                             ("ohne_kennzeichen", "ohne E-Rechnungs-Kennzeichen"),
                             ("aufgefrischt", "bekannte Belege aufgefrischt"),
                             ("ergaenzt", "nur Profilnummer nachgetragen")):
        if z.get(schluessel):
            teile.append(f"{z[schluessel]} {text}")
    return ", ".join(teile)


def adresshinweis(bill_no: int) -> str:
    """Welcher Grund gilt: gar keine Adresse oder eine unbrauchbare?"""
    roh = empfaenger_kandidaten(bill_no, roh=True)
    return HINWEIS_ADRESSE_UNBRAUCHBAR if roh else HINWEIS_OHNE_ADRESSE


def empfaenger_kandidaten(bill_no: int, roh: bool = False) -> list[dict] | None:
    """Adressen zur Rechnung, oder None, wenn sie sich nicht lesen liessen.

    Der Unterschied zwischen 'keine Adresse vorhanden' und 'Abfrage
    fehlgeschlagen' ist wichtig: Das eine ist ein Pflegefall im Haus, das
    andere eine Stoerung. Wer beides zu None zusammenfasst, legt bei einem
    Datenbankaussetzer den halben Tagesbestand zur Sichtprüfung."""
    try:
        adressen = opera.empfaenger(bill_no)
    except Exception:
        log.exception("Empfänger konnten nicht gelesen werden (%s)", bill_no)
        return None
    # Nur einzelne gueltige Adressen kommen als Empfaenger in Frage. Aus
    # OPERA-Freitext kommt auch "a@firma.de; b@firma.de" — das als Empfaenger
    # vorzubelegen, ergaebe einen Versand, den der Mailer verweigert, oder
    # einen, der an die falsche Haelfte geht.
    return adressen if roh else [a for a in adressen
                                 if mailer.adresse_gueltig(a.get("email") or "")]


def empfaenger_vorschlag(bill_no: int) -> str | None:
    """Erste Adresse aus der sortierten Kandidatenliste — Debitorenkonto,
    dann als primaer markierte Profiladressen."""
    kandidaten = empfaenger_kandidaten(bill_no)
    return kandidaten[0]["email"] if kandidaten else None


def rechnungsdaten(cfg: dict, bill_no: int) -> dict:
    """Die Rechnungsdaten, wie sie in das XML gehen — fuer die Anzeige UND fuer
    die Erzeugung.

    Es MUSS ein gemeinsamer Weg sein. Als der BT-49-Rueckfall nur in der
    Erzeugung stand, rechneten Detailseite und Erzeugung verschieden: Die
    Seite meldete 'BT-49 fehlt' und sperrte den Versandknopf, waehrend die
    Erzeugung zufrieden war. Der Anwender sah eine versandbereite Rechnung
    mit gueltigem Empfaenger, die sich nicht versenden liess — und es gab
    keinen Weg, es doch zu tun.

    BT-49 ist die elektronische Adresse des Kaeufers und in XRechnung Pflicht
    (PEPPOL-EN16931-R010). Massgeblich ist die Adresse, an die tatsaechlich
    versendet wird: erst die in der Arbeitsliste gewaehlte, sonst die erste
    aus der Kandidatenliste."""
    daten = opera.rechnung(cfg, bill_no)
    satz = store.rechnung(bill_no) or {}
    gewaehlt = (satz.get("empfaenger") or "").strip()
    daten["header"]["customerendpointid"] = gewaehlt or empfaenger_vorschlag(bill_no)

    # Eine von Hand eingetragene Kaeuferreferenz gewinnt gegen ALLES, auch
    # gegen die Leitweg-ID. Sie ist die einzige Stufe, bei der ein Mensch die
    # Rechnung vor Augen hatte und bewusst entschieden hat. Der umgekehrte
    # Fall waere schlimmer: Jemand traegt etwas ein, es wirkt nicht, und er
    # sieht nicht warum. Was passiert, steht in der Herkunftsanzeige.
    eigen = (satz.get("buyerreference") or "").strip()
    if eigen:
        wert, gekuerzt = opera.kuerzen(eigen)
        daten["header"]["buyerreference"] = wert
        daten["header"]["buyerreference_quelle"] = "von Hand eingetragen"
        daten["header"]["buyerreference_gekuerzt"] = gekuerzt or None

    # Wie die Positionen dastehen. Auch das MUSS hier geschehen und nicht erst
    # in der Erzeugung: Die Detailseite zeigt sonst andere Positionen, als
    # hinausgehen.
    art, quelle = positionsart(cfg, satz, daten["header"], daten["lines"])
    daten["positionsart"] = art
    daten["positionsart_quelle"] = quelle
    daten["buchungen"] = len(daten["lines"])
    daten["lines"] = opera.positionen_buendeln(daten["lines"], art)
    opera.rechnungszeitraum_erweitern(daten["header"], daten["lines"])
    # Eine Gruppenrechnung nennt ihre Gaeste an den Positionen. Am Kopf stand
    # sonst weiter der Gast der Kopfreservierung — als Empfaenger der
    # Leistung (BT-70) und in der Gastzeile —, als haette er allein gewohnt.
    gaeste = {z.get("gast_resv_name_id") for z in daten["lines"] if z.get("gast_resv_name_id")}
    if art == "C" and len(gaeste) > 1:
        kopf = daten["header"]
        kopf["gastname"] = None
        if kopf.get("gastzeile_text"):
            kopf["note"] = hinweis_weg(kopf.get("note"), kopf["gastzeile_text"])
    return daten


def positionsart(cfg: dict, satz: dict, kopf: dict, zeilen: list[dict]) -> tuple[str, str]:
    """(Art, Begruendung) fuer diese Rechnung.

    Reihenfolge: die Wahl auf der Detailseite, dann eine feste Vorgabe in der
    Konfiguration (property.positionen), dann die Vorbelegung nach Anzahl der
    Gaeste. Ein unbekannter Wert faellt auf die Vorbelegung zurueck und wird
    protokolliert — er soll nicht stillschweigend A bedeuten."""
    vorschlag, grund = opera.positionsart_vorschlag(kopf, zeilen)
    gewaehlt = (satz.get("positionen") or "").strip().upper()
    if gewaehlt in opera.POSITIONSARTEN:
        return gewaehlt, "von Hand gewählt"
    vorgabe = str((cfg.get("property") or {}).get("positionen") or "automatisch").strip()
    if vorgabe.upper() in opera.POSITIONSARTEN:
        return vorgabe.upper(), "feste Vorgabe der Konfiguration"
    if vorgabe.lower() != "automatisch":
        log.error("Unbekannter Wert property.positionen='%s' — möglich sind "
                  "automatisch, %s. Es gilt die Vorbelegung.", vorgabe,
                  ", ".join(opera.POSITIONSARTEN))
    return vorschlag, f"automatisch: {grund}"


def buyerreference_vorschlaege(kopf: dict) -> list[dict]:
    """Was OPERA zu dieser Rechnung an Referenzen hergibt — zur Auswahl auf
    der Detailseite. Der Anwender soll sehen, was da ist, statt raten zu
    muessen, was die Kette gewaehlt hat."""
    felder = (("leitweg_id_vorhanden", "Leitweg-ID der Behörde"),
              ("buyer_reference1", "Buyer Reference1 an der Reservierung"),
              ("externe_referenz", "External Reference an der Reservierung"),
              ("kundenreferenz", "Kundenreferenz aus der Buchung (oft Portalnummer)"),
              ("reservierungsnummer", "Reservierungsnummer — unsere Nummer, nicht seine"))
    aus, gesehen = [], set()
    for feld, beschreibung in felder:
        wert = str(kopf.get(feld) or "").strip()
        if wert and wert not in gesehen:
            gesehen.add(wert)
            aus.append({"wert": opera.kuerzen(wert)[0], "quelle": beschreibung})
    return aus


class BereitsVersendet(Exception):
    """Die Rechnung ist heraus. Neu erzeugen wuerde die abgelegte Datei
    ersetzen, und niemand saehe es."""


def versendete_fassung(cfg: dict, bill_no: int) -> Path | None:
    """Die archivierte Fassung einer versendeten Rechnung, falls vorhanden."""
    satz = store.rechnung(bill_no) or {}
    if satz.get("status") != "gesendet":
        return None
    archiv = _ordner(cfg, "archiv_ordner") / f"{bill_no}.xml"
    return archiv if archiv.exists() else None


def xml_erzeugen(cfg: dict, bill_no: int, ersetzen: bool = False,
                 ablegen: bool = True, daten: dict | None = None) -> tuple[bytes, Path, list[str]]:
    """Baut das XML, validiert es und legt es ab. Liefert (xml, pfad, hinweise).
    Hinweise sind die Befunde der eigenen Rechenpruefung UND des
    KoSIT-Validators — beides zusammen entscheidet ueber den Versand.

    Eine VERSENDETE Rechnung wird nicht neu gebaut, sondern aus dem Archiv
    zurueckgegeben. Vorher schrieb jeder Aufruf die Datei neu — auch das blosse
    Ansehen des XML, denn die Anzeige geht durch dieselbe Funktion. Danach lag
    dort etwas anderes als beim Kunden, und niemand konnte es sehen. Genau in
    dem Moment, in dem der Kunde nachfragt, sieht man sonst die falsche Datei.

    ersetzen=True ueberschreibt trotzdem — fuer den Fall, dass jemand es
    ausdruecklich will.

    ablegen=False ist das blosse ANSEHEN: gebaut und gerechnet, aber nichts
    geschrieben — keine Datei, kein Befund, kein Protokoll, kein Validator.
    Ein GET darf nichts veraendern; vorher ueberschrieb "XML ansehen" die
    Gruende, aus denen ein Beleg in der Sichtpruefung stand."""
    archiv = None if ersetzen else versendete_fassung(cfg, bill_no)
    if archiv is not None:
        return archiv.read_bytes(), archiv, []

    # Die Version VOR allem anderen: Ist sie unbekannt, entsteht keine Datei.
    version = xml_build.version_aus(cfg)
    # Der Aufrufer darf die Daten mitgeben — der Versand hat sie schon geladen,
    # und ein zweiter Umlauf durch OPERA kostet ohne Not Zeit.
    daten = daten if daten is not None else rechnungsdaten(cfg, bill_no)
    hinweise = xml_build.pruefsummen(daten)
    xml = xml_build.bauen(daten, version)
    pfad = _ordner(cfg, "xml_ordner") / f"{bill_no}.xml"
    if not ablegen:
        return xml, pfad, hinweise
    pfad.write_bytes(xml)

    v = cfg.get("validierung") or {}
    kosit_gelaufen = False
    if v.get("aktiv"):
        try:
            fehler, warnungen = validate.pruefen_ausfuehrlich(cfg, xml)
            kosit_gelaufen = True
            hinweise += [f"KoSIT: {m}" for m in fehler]
            # Warnungen halten den Versand nicht auf, sollen aber nicht
            # verschwinden: Sie landen im Protokoll und sind dort nachlesbar.
            for w in warnungen:
                store.protokoll("validierung", f"KoSIT-{w}", bill_no=bill_no)
        except validate.NichtEingerichtet as e:
            text = f"KoSIT-Validator nicht eingerichtet ({e})"
            if v.get("pflicht"):
                hinweise.append(text + " — Versand gesperrt, solange Pflicht gesetzt ist")
            else:
                log.warning(text)
                store.protokoll("validierung", text, bill_no=bill_no, erfolg=False)
        except validate.ValidierungsFehler as e:
            kosit_gelaufen = True
            hinweise += [f"KoSIT: {m}" for m in e.meldungen]
        except Exception as e:
            # Der Validator ist ein fremdes Programm in einem eigenen Prozess.
            # Was von dort unerwartet kommt, darf die Erzeugung nicht
            # abbrechen — aber es darf auch nicht durchgehen: Ohne Urteil kein
            # Versand. Der Fehler steht vollstaendig im Log.
            log.exception("Validierung mit unerwartetem Fehler (%s)", bill_no)
            hinweise.append(f"KoSIT: unerwarteter Fehler in der Validierung ({e}) — "
                            "kein Versand, bitte das Protokoll ansehen")
    elif v.get("pflicht"):
        # Pflicht heisst Pflicht — auch wenn jemand die Validierung abschaltet.
        # Vorher wirkte 'pflicht' nur bei eingeschalteter Validierung, und das
        # Protokoll meldete "KoSIT ohne Befund", obwohl KoSIT nie lief.
        hinweise.append("KoSIT-Validierung ist abgeschaltet, aber als Pflicht gesetzt — "
                        "kein Versand")

    # Festgehalten wird, in welcher Version die abgelegte Datei steht. Im
    # Uebergang auf 4.0 liegen beide nebeneinander im Archiv, und bei einer
    # Rueckfrage des Kunden muss das ohne Oeffnen der Datei zu sehen sein.
    #
    # Die Befunde gehen in 'pruefbefund', NICHT in 'fehler': Dort stehen die
    # Gruende fuer die Sichtpruefung, und die ueberschrieb jedes Erzeugen.
    store.setzen(bill_no, xml_pfad=str(pfad), xrechnung_version=version,
                 pruefbefund="; ".join(hinweise) if hinweise else None)
    if not hinweise:
        store.protokoll("geprueft",
                        f"XRechnung {version}: Rechenprüfung ohne Befund, "
                        + ("KoSIT ohne Befund" if kosit_gelaufen else "KoSIT nicht gelaufen"),
                        bill_no=bill_no)
    return xml, pfad, hinweise


# Ein Versand zur Zeit. Die Oberflaeche und die Automatik laufen in eigenen
# Threads; zwei Klicks auf "Jetzt versenden", ein zweiter Tab oder ein
# Automatiklauf zur selben Zeit fuhren sonst beide an der Statuspruefung vorbei
# und verschickten dieselbe Rechnung zweimal (§ 14c UStG).
_versand_sperre = threading.Lock()

VERSAND_OFFEN = "Versand begonnen, Ergebnis nicht bestätigt — bitte prüfen, ob die Mail hinausging"


class Beschaeftigt(Exception):
    """Gerade laeuft ein anderer Versand. Kein Fehler, nur ein schlechter
    Zeitpunkt — der Aufrufer soll es sagen statt stumm zu warten."""


def versenden(cfg: dict, bill_no: int, benutzer: str = "system") -> str:
    """Erzeugt das XML und verschickt es. Wirft bei Problemen.
    Rechnungen mit Prueffehlern werden NICHT versendet."""
    # Kurz warten, dann aufgeben: Ein Klick, der eine Minute auf einen
    # Automatiklauf wartet, sieht aus wie eine haengende Anwendung.
    if not _versand_sperre.acquire(timeout=2):
        raise Beschaeftigt("Gerade wird eine andere Rechnung versendet (Automatiklauf). "
                           "Bitte einen Moment warten und es erneut versuchen.")
    try:
        return _versenden(cfg, bill_no, benutzer)
    finally:
        _versand_sperre.release()


def _versenden(cfg: dict, bill_no: int, benutzer: str) -> str:
    satz = store.rechnung(bill_no)
    if not satz:
        raise LookupError(f"Rechnung {bill_no} ist nicht in der Arbeitsliste")
    # Die Sperre gehoert in den Server, nicht nur als grauer Knopf in die
    # Seite: Fuer eine versendete Rechnung lieferte xml_erzeugen die
    # Archivfassung ohne Befund, und jeder weitere Aufruf mailte sie erneut.
    if satz.get("status") == "gesendet":
        raise BereitsVersendet(f"Rechnung {bill_no} ist am {(satz.get('gesendet_am') or '')[:10]} "
                               "bereits versendet worden — kein zweiter Versand.")
    if satz.get("status") == "ignoriert":
        raise ValueError(f"Rechnung {bill_no} ist zurückgelegt und wird nicht versendet.")
    an = (satz.get("empfaenger") or "").strip()
    if not an:
        raise ValueError("Kein Empfänger gewählt")

    automatisch = benutzer in ("automatik", "system")
    daten = rechnungsdaten(cfg, bill_no)
    xml, pfad, hinweise = xml_erzeugen(cfg, bill_no, daten=daten)
    if hinweise:
        store.setzen(bill_no, status="fehler", fehler=hinweis_dazu(
            satz.get("fehler"), "Vorprüfung fehlgeschlagen — Befund auf der Detailseite"))
        store.protokoll("pruefung", "; ".join(hinweise), bill_no=bill_no,
                        benutzer=benutzer, erfolg=False)
        raise ValueError("Vorprüfung fehlgeschlagen: " + "; ".join(hinweise))

    # Gruppenrechnungen nicht automatisch, solange die Gastzuordnung nicht an
    # Daten bestaetigt ist — es sei denn, ein Mensch hat DIESE Rechnung
    # ausdruecklich freigegeben. Ohne diese Ausnahme nahm der naechste Lauf die
    # Freigabe sofort wieder zurueck, Takt fuer Takt.
    if (automatisch and daten.get("positionsart") == "C"
            and not (cfg.get("property") or {}).get("gastzuordnung_bestaetigt")
            and not satz.get("freigabe_am")):
        zur_pruefung(bill_no, GRUPPE_UNGEPRUEFT)
        store.protokoll("pruefung", GRUPPE_UNGEPRUEFT, bill_no=bill_no, benutzer=benutzer)
        return "pruefung"

    if cfg["automatik"].get("testlauf"):
        # Der Status bleibt, wie er ist; vermerkt wird nur, dass der Beleg im
        # Testlauf dran war. Vorher setzte der Testlauf ihn auf 'bereit' — mit
        # demselben Faelligkeitszeitpunkt, und die Automatik nahm bei jedem
        # Takt dieselben aeltesten zwanzig wieder.
        store.setzen(bill_no, testlauf_am=store.jetzt())
        ist_cl = float(satz.get("city_ledger") or 0) > 0
        bcc = ", ".join(mailer.blindkopien(cfg, ist_cl)) or "-"
        store.protokoll("testlauf",
                        f"Kein Versand (Testlauf aktiv). Ziel wäre {an}, BCC {bcc}",
                        bill_no=bill_no, benutzer=benutzer)
        return "testlauf"

    ist_cl = float(satz.get("city_ledger") or 0) > 0

    # Die Archivkopie gehoert VOR den Versand. Sie stand danach, ausserhalb
    # jeder Fehlerbehandlung: Ist der Archivordner voll, schreibgeschuetzt oder
    # eine nicht erreichbare Freigabe, hat der Kunde die Rechnung, der Schreiben
    # scheitert, und die Automatik traegt 'fehler' ein. Der Anwender sieht dann
    # eine fehlgeschlagene Rechnung, die in Wahrheit zugestellt ist, und drueckt
    # noch einmal auf Senden — waehrend versendete_fassung() nichts mehr
    # zurueckgibt, weil sie am Status haengt.
    #
    # Vorher schreiben heisst: Scheitert es, geht gar nichts hinaus, und die
    # Meldung nennt den Grund. Das ist die sichere Richtung.
    archiv = _ordner(cfg, "archiv_ordner") / f"{bill_no}.xml"
    try:
        archiv.write_bytes(xml)
    except OSError as e:
        store.setzen(bill_no, status="fehler",
                     fehler=hinweis_dazu(satz.get("fehler"), f"Archivkopie nicht möglich: {e}"))
        raise ValueError(
            f"Kein Versand: Die Archivkopie liess sich nicht schreiben ({e}). "
            "Ohne Beleg dessen, was hinausgegangen ist, wird nicht versendet.") from e

    # VOR dem Versand festhalten, dass er begonnen hat. Bricht danach etwas ab —
    # der Mailserver trennt nach dem Einliefern, der Dienst wird neu gestartet,
    # das Schreiben des Status scheitert —, steht der Beleg auf 'fehler' mit
    # diesem Vermerk. Die Automatik nimmt ihn nicht wieder auf; ein Mensch
    # sieht nach, ob die Mail hinausging, statt dass sie ein zweites Mal geht.
    store.setzen(bill_no, status="fehler", fehler=hinweis_dazu(satz.get("fehler"), VERSAND_OFFEN))
    try:
        kennung = mailer.senden(cfg, an=an, bill_no=bill_no,
                                issuedate=satz.get("issuedate") or "",
                                xml=xml, xml_name=pfad.name,
                                pdf=mailer.anhang_pdf(cfg, bill_no),
                                city_ledger=ist_cl)
    except mailer.MailFehler as e:
        store.setzen(bill_no, status="fehler",
                     fehler=hinweis_dazu(satz.get("fehler"), f"Versand fehlgeschlagen: {e}"))
        store.protokoll("versand", f"fehlgeschlagen an {an}: {e}", bill_no=bill_no,
                        benutzer=benutzer, erfolg=False)
        raise
    store.setzen(bill_no, status="gesendet", gesendet_am=store.jetzt(), fehler=None,
                 pruefbefund=None)
    bcc = ", ".join(mailer.blindkopien(cfg, ist_cl)) or "-"
    fassung = (store.rechnung(bill_no) or {}).get("xrechnung_version") or "?"
    store.protokoll("versand",
                    f"XRechnung {fassung} an {an}, BCC {bcc}"
                    f"{' (City Ledger)' if ist_cl else ''}, {kennung}",
                    bill_no=bill_no, benutzer=benutzer)
    return kennung


GRUPPE_UNGEPRUEFT = ("Gruppenrechnung je Gast: Die Zuordnung der Buchungen zu den Gästen ist "
                     "an den Daten noch nicht bestätigt — einmal ansehen, dann freigeben "
                     "oder von Hand versenden")
