"""Mailversand. Der BCC aus der Konfiguration wird IMMER gesetzt — er ist die
Mitschrift des Hauses und kann in der Oberflaeche nicht uebergangen werden.

Rechnungen, die ueber das Debitorenkonto ausgecheckt wurden (City Ledger),
bekommen zusaetzlich eine zweite Blindkopie. Der Grund ist fachlich: Diese
Rechnungen sind nicht bezahlt, sondern stehen beim Debitor offen — sie gehen
die Debitorenbuchhaltung an, nicht nur die allgemeine."""
from __future__ import annotations
import logging
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from . import pfade

log = logging.getLogger(__name__)


class MailFehler(Exception):
    pass


# Genau EINE Adresse, ohne Anzeigenamen, ohne Trenner. Streng mit Absicht:
# Die Adresse kommt aus OPERA-Freitext oder von Hand. "a@kunde.de; b@fremd.de"
# passierte die Positivliste ueber endswith("@kunde.de"), und je nach
# Python-Version ging die Mail an die ERSTE, nicht freigegebene Adresse.
_EINE_ADRESSE = re.compile(r"^[^@\s,;<>()\"']+@[^@\s,;<>()\"']+\.[^@\s,;<>()\"']+$")


def adresse_gueltig(adresse: str) -> bool:
    return bool(_EINE_ADRESSE.match((adresse or "").strip()))


def empfaenger_erlaubt(cfg: dict, adresse: str) -> bool:
    """Sicherheitsnetz gegen den gefaehrlichsten Fehlgriff der Anwendung:
    eine Testmail an einen echten Gast. Solange 'erlaubte_empfaenger' gefuellt
    ist, geht nichts an eine andere Adresse — geprueft im Code, nicht per
    Absprache. Eintraege sind entweder ganze Adressen oder '@domain'.

    Was keine einzelne gueltige Adresse ist, ist nie erlaubt — auch nicht bei
    leerer Liste."""
    ziel = (adresse or "").strip().lower()
    if not adresse_gueltig(ziel):
        return False
    liste = [e.strip().lower() for e in (cfg["mail"].get("erlaubte_empfaenger") or []) if e.strip()]
    if not liste:
        return True
    return any(ziel == e or (e.startswith("@") and ziel.endswith(e)) for e in liste)


def host_pruefen(cfg: dict, sekunden: float = 3.0) -> str:
    """Ist der eingetragene Mailserver plausibel? Leerer String heisst:
    nichts zu beanstanden.

    Geprueft wird der Name UND der Port. Die Namensaufloesung allein reicht
    nicht — der Fall, der das ausgeloest hat, loeste sauber auf: Der Name zeigte
    auf einen Webserver, und auf Port 25 antwortete dort nichts. Eine Anwendung,
    die nur nachschlaegt, haette 'in Ordnung' gemeldet und beim ersten echten
    Versand versagt.

    Angemeldet wird sich nicht und gesendet erst recht nicht; es wird nur
    geschaut, ob jemand zuhoert. Das ist der Unterschied zum Knopf 'Testmail
    senden' — den drueckt man erst, wenn man schon vertraut."""
    m = cfg.get("mail") or {}
    host = (m.get("smtp_host") or "").strip()
    if not host:
        return "Es ist kein Mailserver eingetragen."
    port = int(m.get("smtp_port") or 25)
    try:
        socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return (f"Der Mailserver '{host}' lässt sich nicht auflösen ({e.strerror or e}). "
                "Solange das so ist, scheitert jeder Versand — Schreibweise pruefen.")
    except OSError as e:
        return f"Der Mailserver '{host}' liess sich nicht prüfen: {e}"
    try:
        with socket.create_connection((host, port), sekunden):
            # Bewusst NICHT weiter: Ob dort wirklich SMTP spricht, zeigte erst
            # die Begruessungszeile ("220 ..."). Das waere machbar, aber die
            # Grenze ist hier richtig gezogen — wer wissen will, ob der Versand
            # funktioniert, hat den Knopf "Testmail senden". Bisher ist noch
            # niemand darueber gestolpert; wenn doch, steht hier die Stelle.
            return ""
    except OSError as e:
        return (f"'{host}' gibt es, aber auf Port {port} antwortet kein Mailserver "
                f"({getattr(e, 'strerror', None) or e}). Entweder ist der Name der eines "
                "Webservers, oder der Port stimmt nicht — 25, 465 oder 587 sind ueblich.")


def _text(vorlage: str, werte: dict) -> str:
    """Vorlage fuellen. Scheitert das — unbekannter Platzhalter, eine
    Formatangabe wie {bill_no:05}, eine einzelne geschweifte Klammer —, bleibt
    der Text, wie er ist. Vorher fing das nur KeyError und IndexError; ein
    ValueError liess JEDEN Versand scheitern."""
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        log.warning("Mailvorlage nicht fuellbar, bleibt unverändert: %r", vorlage[:80])
        return vorlage


def anhang_pdf(cfg: dict, bill_no: int) -> Path | None:
    """Sucht die PDF-Rechnung im konfigurierten Ordner. Optional."""
    m = cfg["mail"]
    ordner = (m.get("pdf_ordner") or "").strip()
    if not ordner:
        return None
    # Relativ zur INSTALLATION, nicht zum Arbeitsverzeichnis — das ist im
    # Freigabebetrieb die jeweilige Freigabe.
    pfad = pfade.im_bestand(ordner) / _text(m.get("pdf_muster") or "{bill_no}.pdf", {"bill_no": bill_no})
    return pfad if pfad.exists() else None


def blindkopien(cfg: dict, city_ledger: bool) -> list[str]:
    """Welche Blindkopien gehen mit? Die allgemeine immer, die zusaetzliche
    nur bei Rechnungen, die ueber das Debitorenkonto ausgecheckt wurden.
    Doppelte Eintraege werden zusammengefasst — sonst bekaeme dieselbe
    Adresse die Mail zweimal, wenn beide Felder gleich belegt sind."""
    m = cfg["mail"]
    liste = [(m.get("bcc") or "").strip()]
    if city_ledger:
        liste.append((m.get("bcc_city_ledger") or "").strip())
    aus: list[str] = []
    for adresse in liste:
        if adresse and adresse.lower() not in [a.lower() for a in aus]:
            aus.append(adresse)
    return aus


def senden(cfg: dict, *, an: str, bill_no: int, issuedate: str,
           xml: bytes, xml_name: str, pdf: Path | None = None,
           city_ledger: bool = False) -> str:
    """Verschickt eine Rechnung. Gibt die Message-ID zurueck.
    Wirft MailFehler, wenn der Versand nicht moeglich ist."""
    m = cfg["mail"]
    if not m.get("aktiv"):
        raise MailFehler("Der Mailversand ist in der Konfiguration abgeschaltet.")
    if not an:
        raise MailFehler("Keine Empfängeradresse gewählt.")
    if not adresse_gueltig(an):
        raise MailFehler(f"'{an}' ist keine einzelne gültige E-Mail-Adresse. "
                         "Mehrere Adressen oder Namen davor gehen nicht.")
    if not empfaenger_erlaubt(cfg, an):
        erlaubt = ", ".join(cfg["mail"].get("erlaubte_empfaenger") or [])
        raise MailFehler(
            f"'{an}' steht nicht auf der Liste erlaubter Empfänger ({erlaubt}). "
            "Solange diese Liste gefuellt ist, geht keine Mail nach draussen.")

    werte = {"bill_no": bill_no, "issuedate": issuedate,
             "absender_name": m.get("absender_name") or "",
             "empfaenger": an}

    nachricht = EmailMessage()
    nachricht["From"] = formataddr((m.get("absender_name") or "", m["absender"]))
    nachricht["To"] = an
    bcc_liste = blindkopien(cfg, city_ledger)
    # Auch die Blindkopien gehen durch das Sicherheitsnetz: Ein Tippfehler in
    # der BCC-Adresse schickt eine Kundenrechnung an einen Fremden, und zwar
    # unbemerkt — genau deshalb ist es eine Blindkopie.
    for adresse in bcc_liste:
        if not adresse_gueltig(adresse):
            raise MailFehler(f"Die Blindkopie '{adresse}' ist keine einzelne gültige Adresse.")
        if not empfaenger_erlaubt(cfg, adresse):
            raise MailFehler(
                f"Die Blindkopie an '{adresse}' steht nicht auf der Liste erlaubter "
                "Empfaenger. Entweder die Adresse berichtigen oder die Liste ergaenzen.")
    if bcc_liste:
        nachricht["Bcc"] = ", ".join(bcc_liste)
    nachricht["Subject"] = _text(m.get("betreff") or "Rechnung {bill_no}", werte)
    nachricht["Date"] = formatdate(localtime=True)
    nachricht["Message-ID"] = make_msgid()
    nachricht.set_content(_text(m.get("text") or "", werte))

    nachricht.add_attachment(xml, maintype="application", subtype="xml", filename=xml_name)
    if pdf and pdf.exists():
        nachricht.add_attachment(pdf.read_bytes(), maintype="application",
                                 subtype="pdf", filename=pdf.name)

    empfaenger = [an] + bcc_liste
    art = (m.get("verschluesselung") or "starttls").lower()
    host, port = m["smtp_host"], int(m["smtp_port"])
    if art not in ("ssl", "starttls") and m.get("benutzer"):
        # Benutzer und Passwort gingen sonst im Klartext ueber die Leitung.
        raise MailFehler("Anmeldung am Mailserver ohne Verschlüsselung wird nicht gemacht — "
                         "unter Konfiguration 'starttls' oder 'ssl' wählen.")
    # Das Zertifikat des Servers wird GEPRUEFT. Ohne Kontext nimmt smtplib einen
    # ungeprueften, und jeder im Netzpfad koennte Passwort und Rechnungen
    # mitlesen oder die IBAN tauschen.
    kontext = ssl.create_default_context()
    try:
        if art == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=kontext)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            server.ehlo()
            if art == "starttls":
                server.starttls(context=kontext)
                server.ehlo()
            if m.get("benutzer"):
                server.login(m["benutzer"], m.get("passwort") or "")
            abgelehnt = server.send_message(nachricht, from_addr=m["absender"], to_addrs=empfaenger)
    except ssl.SSLError as e:
        raise MailFehler(f"Das Zertifikat des Mailservers ist nicht vertrauenswürdig: {e}") from e
    except (smtplib.SMTPException, OSError) as e:
        raise MailFehler(f"SMTP-Fehler: {e}") from e
    # smtplib wirft nur, wenn ALLE Empfaenger abgelehnt werden. Die Blindkopie
    # des Hauses ist immer dabei — lehnte der Server nur den Kunden ab, galt
    # die Rechnung als gesendet, und die Kopie im Haus liess es so aussehen.
    abgelehnt = {k.lower(): v for k, v in (abgelehnt or {}).items()}
    if an.lower() in abgelehnt:
        code, text = abgelehnt[an.lower()]
        raise MailFehler(f"Der Mailserver hat den Empfänger {an} abgelehnt ({code} "
                         f"{text.decode(errors='replace') if isinstance(text, bytes) else text}). "
                         "Die Blindkopie im Haus ist trotzdem angekommen.")
    if abgelehnt:
        log.warning("Blindkopie abgelehnt: %s", abgelehnt)
    return nachricht["Message-ID"]


def test(cfg: dict, an: str) -> str:
    """Testmail an eine Adresse — prueft Server, Anmeldung und BCC."""
    return senden(cfg, an=an, bill_no=0, issuedate="",
                  xml=b"<test/>", xml_name="test.xml")
