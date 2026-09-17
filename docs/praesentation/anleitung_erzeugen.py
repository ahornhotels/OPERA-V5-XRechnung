# -*- coding: utf-8 -*-
"""Erzeugt XRechnung_Anleitung_Anwender.pptx — die Schritt-fuer-Schritt-Anleitung
fuer alle, die im Alltag Rechnungen verschicken. Ohne Konfiguration.

Kein Bestandteil der Anwendung. Die Bilder kommen aus anleitung_aufnahmen.py
(echte Oberflaeche, erfundene Musterdaten):

    python docs/praesentation/anleitung_aufnahmen.py /tmp/aufnahmen
    python docs/praesentation/anleitung_erzeugen.py  /tmp/aufnahmen

Wer den Text aendert, prueft ihn gegen den Code, nicht gegen das Handbuch:
Welcher Knopf wann grau ist und welche Rolle was darf, steht in
app/templates/detail.html und app/main.py. Eine Anleitung, die einen Knopf
verspricht, den es nicht gibt, kostet mehr Vertrauen als gar keine.
"""
import pathlib
import struct
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

BILDER = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "aufnahmen")
ZIEL = pathlib.Path(__file__).resolve().parent / "XRechnung_Anleitung_Anwender.pptx"
STAND = "Stand 16.09.2026"

# --- Hausfarben wie in erzeugen.py -----------------------------------------
AKZENT = RGBColor(0x74, 0x5B, 0x2F)
AKZENT_HELL = RGBColor(0xAD, 0x92, 0x60)
DUNKEL = RGBColor(0x1A, 0x1A, 0x1A)
GRUND = RGBColor(0xF6, 0xF4, 0xF0)
WEISS = RGBColor(0xFF, 0xFF, 0xFF)
TEXT = RGBColor(0x2A, 0x28, 0x24)
LEISE = RGBColor(0x7A, 0x74, 0x6C)
ROT = RGBColor(0xD0, 0x02, 0x1B)          # dieselbe Farbe wie die Markierungen im Bild
ZEILE_ALT = RGBColor(0xEE, 0xEA, 0xE3)

# Die vier Kastenarten. Farbe UND Wort tragen die Bedeutung — wer die Folien
# schwarz-weiss druckt, sieht das Wort noch.
ARTEN = {
    "TIPP":    (RGBColor(0x1F, 0x5C, 0x3D), RGBColor(0xE3, 0xF0, 0xE8)),
    "HINWEIS": (RGBColor(0x8A, 0x4B, 0x12), RGBColor(0xFB, 0xEF, 0xDC)),
    "ACHTUNG": (RGBColor(0xA0, 0x20, 0x20), RGBColor(0xF8, 0xE1, 0xDE)),
    "FRAGE":   (RGBColor(0x2E, 0x4F, 0x7A), RGBColor(0xE2, 0xEA, 0xF4)),
}
STATUSFARBEN = {  # wie in app/static/stil.css
    "Neu": (RGBColor(0xEE, 0xEA, 0xE3), TEXT),
    "Prüfung": (RGBColor(0xFB, 0xEF, 0xDC), RGBColor(0x8A, 0x4B, 0x12)),
    "Bereit": (RGBColor(0xF1, 0xEA, 0xDC), AKZENT),
    "Gesendet": (RGBColor(0xE3, 0xF0, 0xE8), RGBColor(0x1F, 0x5C, 0x3D)),
    "Fehler": (RGBColor(0xF8, 0xE1, 0xDE), RGBColor(0xA0, 0x20, 0x20)),
    "Zurückgelegt": (RGBColor(0xEA, 0xE7, 0xE2), LEISE),
}

DISPLAY, BODY = "Georgia", "Trebuchet MS"
BREITE, HOEHE = Inches(13.333), Inches(7.5)
RAND = Inches(0.7)

prs = Presentation()
prs.slide_width, prs.slide_height = BREITE, HOEHE
LEER = prs.slide_layouts[6]
nummer = [0]


def kasten(folie, x, y, b, h, farbe, rahmen=None, radius=False, linie=1.0):
    form = folie.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, x, y, b, h)
    if radius:
        form.adjustments[0] = 0.08
    form.fill.solid()
    form.fill.fore_color.rgb = farbe
    if rahmen is None:
        form.line.fill.background()
    else:
        form.line.color.rgb = rahmen
        form.line.width = Pt(linie)
    form.shadow.inherit = False
    return form


def absaetze(tf, inhalt, groesse, farbe, schrift=BODY, fett=False, abstand=1.2,
             ausrichtung=PP_ALIGN.LEFT, danach=4):
    """Text mit **fett** in Zeilen. Jede Zeile ein Absatz."""
    for i, zeile in enumerate(inhalt.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = ausrichtung
        p.line_spacing = abstand
        p.space_after = Pt(danach)
        for j, stueck in enumerate(zeile.split("**")):
            if not stueck:
                continue
            r = p.add_run()
            r.text = stueck
            r.font.size = Pt(groesse)
            r.font.name = schrift
            r.font.bold = fett or (j % 2 == 1)
            r.font.color.rgb = farbe


def text(folie, x, y, b, h, inhalt, groesse=15, farbe=TEXT, schrift=BODY, fett=False,
         ausrichtung=PP_ALIGN.LEFT, anker=MSO_ANCHOR.TOP, abstand=1.2, danach=4):
    tb = folie.shapes.add_textbox(x, y, b, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anker
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    absaetze(tf, inhalt, groesse, farbe, schrift, fett, abstand, ausrichtung, danach)
    return tb


def seite(rubrik, titel):
    folie = prs.slides.add_slide(LEER)
    kasten(folie, 0, 0, BREITE, HOEHE, GRUND)
    kasten(folie, 0, 0, BREITE, Inches(0.12), AKZENT_HELL)
    text(folie, RAND, Inches(0.38), Inches(11), Inches(0.3), rubrik.upper(),
         groesse=11, farbe=AKZENT, fett=True)
    text(folie, RAND, Inches(0.66), Inches(12), Inches(0.7), titel,
         groesse=28, farbe=DUNKEL, schrift=DISPLAY)
    nummer[0] += 1
    text(folie, RAND, HOEHE - Inches(0.42), Inches(9), Inches(0.3),
         f"XRechnung · Anleitung für den Alltag · {STAND} · Bilder mit Musterdaten",
         groesse=9.5, farbe=LEISE)
    text(folie, BREITE - RAND - Inches(1), HOEHE - Inches(0.42), Inches(1), Inches(0.3),
         str(nummer[0]), groesse=10, farbe=LEISE, ausrichtung=PP_ALIGN.RIGHT)
    return folie


def bildgroesse(pfad):
    with open(pfad, "rb") as f:
        kopf = f.read(24)
    return struct.unpack(">II", kopf[16:24])


def bild(folie, name, x, y, b_max, h_max, rahmen=True):
    """Bild einpassen, Seitenverhaeltnis bleibt. Gibt (x, y, b, h) zurueck."""
    pfad = BILDER / f"{name}.png"
    w, h = bildgroesse(pfad)
    faktor = min(b_max / w, h_max / h)
    b, hh = int(w * faktor), int(h * faktor)
    if rahmen:
        kasten(folie, x - Pt(1.5), y - Pt(1.5), b + Pt(3), hh + Pt(3), RGBColor(0xD8, 0xD2, 0xC6))
    folie.shapes.add_picture(str(pfad), x, y, b, hh)
    return x, y, b, hh


def marke(folie, x, y, zahl, d=Inches(0.36)):
    k = folie.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    k.fill.solid()
    k.fill.fore_color.rgb = ROT
    k.line.fill.background()
    k.shadow.inherit = False
    tf = k.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    absaetze(tf, str(zahl), 14, WEISS, fett=True, ausrichtung=PP_ALIGN.CENTER, danach=0)


def schritte(folie, x, y, b, eintraege, groesse=15, abstand=0.18):
    """Nummerierte Erklaerung passend zu den roten Ziffern im Bild.
    eintraege: Liste von (zahl oder None, text). Hoehe wird geschaetzt."""
    oben = y
    for zahl, inhalt in eintraege:
        zeilen = max(1, sum(max(1, int(len(z) / (b / Inches(1) * 7.3 * 15 / groesse)) + 1)
                            for z in inhalt.replace("**", "").split("\n")))
        h = Inches(0.27 * zeilen * groesse / 15)
        if zahl is not None:
            marke(folie, x, oben - Inches(0.02), zahl)
        text(folie, x + Inches(0.52), oben, b - Inches(0.52), h, inhalt, groesse=groesse)
        oben += h + Inches(abstand)
    return oben


def hinweis(folie, x, y, b, art, inhalt, groesse=13.5, h=None):
    farbe, grund = ARTEN[art]
    zeilen = sum(max(1, int(len(z) / (b / Inches(1) * 8.0 * 13.5 / groesse)) + 1)
                 for z in inhalt.replace("**", "").split("\n"))
    h = h or Inches(0.5 + 0.25 * zeilen * groesse / 13.5)
    kasten(folie, x, y, b, h, grund, radius=True)
    kasten(folie, x, y, Inches(0.09), h, farbe)
    etikett = "?  FRAGE" if art == "FRAGE" else art
    text(folie, x + Inches(0.28), y + Inches(0.12), b - Inches(0.4), Inches(0.3), etikett,
         groesse=11, farbe=farbe, fett=True)
    text(folie, x + Inches(0.28), y + Inches(0.4), b - Inches(0.45), h - Inches(0.45),
         inhalt, groesse=groesse, farbe=TEXT, danach=2)
    return y + h


def frage(folie, x, y, b, f, a, groesse=13):
    """FAQ-Eintrag: Frage fett in Blau, Antwort darunter."""
    farbe, grund = ARTEN["FRAGE"]
    zeilen_a = sum(max(1, int(len(z) / (b / Inches(1) * 9.4 * 13 / groesse)) + 1)
                   for z in a.replace("**", "").split("\n"))
    zeilen_f = max(1, int(len(f) / (b / Inches(1) * 8.8)) + 1)
    h = Inches(0.26 + 0.25 * (zeilen_f + zeilen_a) * groesse / 13)
    kasten(folie, x, y, b, h, grund, radius=True)
    kasten(folie, x, y, Inches(0.09), h, farbe)
    text(folie, x + Inches(0.28), y + Inches(0.12), b - Inches(0.42), Inches(0.3 * zeilen_f),
         "? " + f, groesse=groesse + 0.5, farbe=farbe, fett=True, danach=0)
    text(folie, x + Inches(0.28), y + Inches(0.14 + 0.25 * zeilen_f * groesse / 13) + Inches(0.06),
         b - Inches(0.42), Inches(0.25 * zeilen_a), a, groesse=groesse, danach=1)
    return y + h + Inches(0.14)


def statusschild(folie, x, y, name, b=Inches(1.55)):
    grund, farbe = STATUSFARBEN[name]
    k = kasten(folie, x, y, b, Inches(0.36), grund, radius=True)
    tf = k.text_frame
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    absaetze(tf, name, 13, farbe, fett=True, ausrichtung=PP_ALIGN.CENTER, danach=0)


LINKS_B = Inches(4.55)                    # Textspalte links
BILD_X = RAND + LINKS_B + Inches(0.35)    # Bild rechts
BILD_B = BREITE - BILD_X - RAND
INHALT_Y = Inches(1.55)
INHALT_H = HOEHE - INHALT_Y - Inches(0.62)

# =============================================================================
# 1 Titel
# =============================================================================
f = prs.slides.add_slide(LEER)
kasten(f, 0, 0, BREITE, HOEHE, DUNKEL)
kasten(f, 0, 0, Pt(10), HOEHE, AKZENT_HELL)
text(f, Inches(1), Inches(1.6), Inches(11), Inches(0.4), "ANLEITUNG FÜR DEN ALLTAG",
     groesse=13, farbe=AKZENT_HELL, fett=True)
text(f, Inches(1), Inches(2.1), Inches(11.3), Inches(1.6), "XRechnung verschicken —\nSchritt für Schritt",
     groesse=46, farbe=WEISS, schrift=DISPLAY, abstand=1.05)
text(f, Inches(1), Inches(4.25), Inches(10.5), Inches(1.2),
     "Für alle, die Firmenrechnungen aus OPERA als XRechnung an Kunden schicken.\n"
     "Ohne Technik, ohne Einstellungen — nur das, was Sie jeden Tag brauchen.",
     groesse=18, farbe=RGBColor(0xDD, 0xD8, 0xD0), abstand=1.3)
kasten(f, Inches(1), Inches(5.75), Inches(0.9), Pt(2.5), AKZENT_HELL)
text(f, Inches(1), Inches(5.95), Inches(11), Inches(0.8),
     f"{STAND} · Alle Bildschirmfotos zeigen erfundene Musterdaten, keine echten Kunden oder Gäste.",
     groesse=12.5, farbe=RGBColor(0xA8, 0xA2, 0x9A))

# =============================================================================
# 2 Worum geht es?
# =============================================================================
f = seite("Einführung", "Worum geht es?")
karten = [
    ("1", "Firmen wollen Rechnungen als Datei",
     "Firmenkunden und Behörden bekommen ihre Rechnung zusätzlich als **XRechnung** — "
     "eine Datei, die ihr Buchhaltungsprogramm selbst einliest. Das ist Pflicht."),
    ("2", "Das Programm erledigt die Arbeit",
     "Es holt die fertigen Rechnungen aus OPERA, baut die Datei, **prüft sie** und verschickt sie "
     "per E-Mail. Sie schauen drauf und drücken auf „Versenden“."),
    ("3", "OPERA bleibt, wie es ist",
     "Das Programm **liest nur**. Es kann in OPERA nichts ändern, verschieben oder löschen. "
     "Beträge korrigieren Sie wie immer in OPERA."),
]
kb = (BREITE - 2 * RAND - 2 * Inches(0.35)) / 3
for i, (zahl, titel, inhalt) in enumerate(karten):
    x = RAND + i * (kb + Inches(0.35))
    kasten(f, x, Inches(1.65), kb, Inches(3.85), WEISS, rahmen=RGBColor(0xE2, 0xDD, 0xD3), radius=True)
    marke(f, x + Inches(0.3), Inches(1.9), zahl, d=Inches(0.5))
    text(f, x + Inches(0.3), Inches(2.55), kb - Inches(0.6), Inches(0.8), titel,
         groesse=19, farbe=DUNKEL, schrift=DISPLAY)
    text(f, x + Inches(0.3), Inches(3.45), kb - Inches(0.6), Inches(2.0), inhalt, groesse=14)
hinweis(f, RAND, Inches(5.75), BREITE - 2 * RAND, "HINWEIS",
        "Die XRechnung ist **dieselbe Rechnung** wie in OPERA, nur als Datei. Es entsteht keine zweite "
        "Rechnung und keine zweite Forderung — das steht auch so in der E-Mail an den Kunden.")

# =============================================================================
# 3 Der Weg
# =============================================================================
f = seite("Überblick", "Ihr Weg in sechs Schritten")
wege = [("Anmelden", "im Browser"), ("Liste", "Was ist neu?"),
        ("Öffnen", "Klick auf die Nummer"), ("Empfänger", "stimmt die Adresse?"),
        ("Prüfen", "„XML erzeugen“"), ("Versenden", "„Jetzt versenden“")]
wb = (BREITE - 2 * RAND - 5 * Inches(0.25)) / 6
for i, (titel, unter) in enumerate(wege):
    x = RAND + i * (wb + Inches(0.25))
    kasten(f, x, Inches(1.9), wb, Inches(2.35), WEISS, rahmen=AKZENT_HELL, radius=True, linie=1.5)
    marke(f, x + wb / 2 - Inches(0.3), Inches(2.1), i + 1, d=Inches(0.6))
    text(f, x + Inches(0.08), Inches(2.85), wb - Inches(0.16), Inches(0.7), titel, groesse=14.5,
         fett=True, farbe=DUNKEL, ausrichtung=PP_ALIGN.CENTER)
    text(f, x + Inches(0.08), Inches(3.55), wb - Inches(0.16), Inches(0.6), unter, groesse=12.5,
         farbe=LEISE, ausrichtung=PP_ALIGN.CENTER)
    if i < 5:
        pfeil = f.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + wb + Inches(0.03), Inches(2.9),
                                   Inches(0.19), Inches(0.3))
        pfeil.fill.solid(); pfeil.fill.fore_color.rgb = AKZENT_HELL
        pfeil.line.fill.background()
text(f, RAND, Inches(4.5), Inches(12), Inches(0.5),
     "Die meisten Rechnungen sind in einer Minute erledigt. Die Folien danach erklären jeden Schritt "
     "und die Sonderfälle.", groesse=16)
hinweis(f, RAND, Inches(5.2), Inches(5.8), "TIPP",
        "Die **roten Ziffern** in den Bildern gehören zu den Ziffern im Text daneben.")
hinweis(f, RAND + Inches(6.1), Inches(5.2), BREITE - 2 * RAND - Inches(6.1), "HINWEIS",
        "Versenden, Empfänger wählen und Zurücklegen geht nur mit der Rolle **„verwalten“**. "
        "Sehen Sie diese Knöpfe nicht, fehlt Ihnen das Recht.")

# =============================================================================
# 4 Anmelden
# =============================================================================
f = seite("Schritt 1", "Anmelden")
bild(f, "01_anmelden", BILD_X + Inches(1.3), INHALT_Y, BILD_B - Inches(1.3), Inches(4.3))
y = schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B, [
    (None, "Öffnen Sie im Browser die Adresse, die Sie von der IT bekommen haben. "
           "Am besten als **Lesezeichen** speichern."),
    (1, "**Benutzer** eintragen."),
    (2, "**Passwort** eintragen."),
    (3, "Auf **„Anmelden“** klicken."),
])
hinweis(f, RAND, y + Inches(0.15), LINKS_B, "HINWEIS",
        "Nach **8 Stunden** meldet das Programm Sie ab — dann einfach neu anmelden.\n"
        "Nach **5 falschen Passwörtern** ist der Zugang kurz gesperrt. Warten Sie etwas, bevor Sie es erneut versuchen.")
hinweis(f, BILD_X + Inches(1.3), Inches(6.0), BILD_B - Inches(1.3), "TIPP",
        "Passwort vergessen? Das kann die IT zurücksetzen.", h=Inches(0.72))

# =============================================================================
# 5 Liste
# =============================================================================
f = seite("Schritt 2", "Die Liste: alle Rechnungen auf einen Blick")
bx, by, bb, bh = bild(f, "02_liste", Inches(5.0), INHALT_Y, BREITE - Inches(5.0) - RAND, INHALT_H)
y = schritte(f, RAND, INHALT_Y + Inches(0.05), Inches(4.0), [
    (1, "**Jetzt einlesen** holt neue Rechnungen aus OPERA."),
    (2, "**Reiter** filtern nach Status. Die Zahl zeigt, wie viele es sind."),
    (3, "**Suchen** nach Nummer, Kunde oder E-Mail-Adresse."),
    (4, "**Rechnungsnummer anklicken** öffnet die Rechnung."),
    (5, "**Status** und darunter in Rot der Grund, wenn etwas zu tun ist."),
], groesse=14)
hinweis(f, RAND, y + Inches(0.1), Inches(4.0), "TIPP",
        "Auf eine **Spaltenüberschrift** klicken sortiert. Noch einmal klicken dreht die Reihenfolge um.",
        groesse=13)

# =============================================================================
# 6 Status
# =============================================================================
f = seite("Schritt 2", "Was bedeutet der Status — und was tue ich?")
zeilen = [
    ("Neu", "Gerade eingelesen, noch nichts entschieden.", "Öffnen, Empfänger prüfen, versenden."),
    ("Prüfung", "Hier muss ein Mensch draufschauen. Der Grund steht darunter.",
     "Grund lesen, siehe Sonderfälle. Wird **nie** automatisch verschickt."),
    ("Bereit", "Empfänger ist gewählt, die Rechnung wartet auf den Versand.",
     "Prüfen und versenden — oder die Automatik abwarten."),
    ("Gesendet", "Per E-Mail an den Kunden verschickt.", "Nichts. Fertig."),
    ("Fehler", "Die Prüfung hat etwas gefunden. Wird nicht verschickt.",
     "Rechnung öffnen, rote Meldung lesen, siehe Folie „Wenn es rot wird“."),
    ("Zurückgelegt", "Aus dem Lauf genommen, zum Beispiel ein Nullbeleg.", "Nichts."),
]
y = Inches(1.65)
kasten(f, RAND, y, BREITE - 2 * RAND, Inches(0.42), DUNKEL)
for x_off, titel in ((Inches(0.2), "STATUS"), (Inches(2.2), "DAS HEISST"), (Inches(7.3), "DAS TUN SIE")):
    text(f, RAND + x_off, y + Inches(0.1), Inches(4), Inches(0.3), titel, groesse=11.5, farbe=GRUND, fett=True)
y += Inches(0.42)
for i, (name, heisst, tun) in enumerate(zeilen):
    kasten(f, RAND, y, BREITE - 2 * RAND, Inches(0.6), WEISS if i % 2 == 0 else ZEILE_ALT)
    statusschild(f, RAND + Inches(0.2), y + Inches(0.12), name)
    text(f, RAND + Inches(2.2), y + Inches(0.08), Inches(4.9), Inches(0.5), heisst, groesse=13.5)
    text(f, RAND + Inches(7.3), y + Inches(0.08), Inches(4.6), Inches(0.5), tun, groesse=13.5)
    y += Inches(0.6)
hinweis(f, RAND, y + Inches(0.15), BREITE - 2 * RAND, "HINWEIS",
        "Oben rechts steht **„Automatik an“** oder **„aus“**. Ist sie an, verschickt das Programm Rechnungen "
        "im Status Neu oder Bereit mit Empfänger nach einer Wartezeit selbst — Rechnungen in **Prüfung** nie.")

# =============================================================================
# 7 Einlesen
# =============================================================================
f = seite("Schritt 2", "Neue Rechnungen holen")
bild(f, "03_einlesen", RAND, INHALT_Y, BREITE - 2 * RAND, Inches(1.9))
y = schritte(f, RAND, Inches(3.75), Inches(6.2), [
    (3, "Auf **„Jetzt einlesen“** klicken. Das dauert ein paar Sekunden."),
    (1, "Oben erscheint, **was passiert ist**: wie viele gelesen, wie viele neu, "
        "wie viele zur Prüfung — und warum andere nicht aufgenommen wurden."),
    (2, "Der **Zeitraum** steht normalerweise richtig. Nur ändern, wenn Sie gezielt ältere Rechnungen holen sollen."),
], groesse=14.5)
x2 = RAND + Inches(6.6)
y2 = hinweis(f, x2, Inches(3.7), BREITE - RAND - x2, "TIPP",
             "Ist die Automatik an, liest das Programm alle paar Minuten von selbst ein. "
             "Der Takt steht über der Liste.")
hinweis(f, x2, y2 + Inches(0.15), BREITE - RAND - x2, "ACHTUNG",
        "**„Durchlauf starten“** verschickt sofort alle fälligen Rechnungen. "
        "Nur drücken, wenn das so abgesprochen ist.")

# =============================================================================
# 7b Wenn die Automatik gerade arbeitet
# =============================================================================
f = seite("Gut zu wissen", "Wenn die Automatik gerade arbeitet")
bild(f, "19_automatik_arbeitet", RAND, INHALT_Y, BREITE - 2 * RAND, Inches(2.2))
y = schritte(f, RAND, Inches(4.0), Inches(6.4), [
    (1, "Oben rechts steht **„Automatik arbeitet …“**."),
    (2, "Darunter erklärt ein Streifen, was gerade gesperrt ist."),
    (3, "**Einlesen**, **Durchlauf starten** und **Jetzt versenden** sind grau."),
], groesse=14.5)
hinweis(f, RAND + Inches(6.8), Inches(3.95), BREITE - 2 * RAND - Inches(6.8), "TIPP",
        "Das dauert meist Sekunden. Einfach die Seite neu laden — danach geht wieder alles. "
        "So kommen sich Ihr Klick und der automatische Lauf nicht in die Quere.")

# =============================================================================
# 8 Rechnung oeffnen
# =============================================================================
f = seite("Schritt 3", "Die Rechnung: die vier Knöpfe")
bild(f, "05_detail_oben", BILD_X - Inches(0.3), INHALT_Y, BILD_B + Inches(0.3), INHALT_H)
y = schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B - Inches(0.3), [
    (1, "**XML erzeugen** baut die Datei und **prüft** sie. Das schadet nie — erst prüfen, dann versenden."),
    (2, "**XML ansehen** öffnet die Datei. Sie sieht technisch aus; das ist normal."),
    (3, "**Jetzt versenden** schickt die Rechnung an den Empfänger. Ist der Knopf grau, fehlt noch etwas."),
    (4, "**Zurücklegen** nimmt die Rechnung aus dem Lauf."),
], groesse=14)
hinweis(f, RAND, y + Inches(0.1), LINKS_B - Inches(0.3), "HINWEIS",
        "Die Zeile **„Blindkopie geht an“** zeigt, wer im Haus eine Kopie bekommt. "
        "Darum müssen Sie sich nicht kümmern.", groesse=13)

# =============================================================================
# 9 Empfaenger
# =============================================================================
f = seite("Schritt 4", "Wohin geht die Rechnung?")
bild(f, "06_empfaenger", BILD_X, INHALT_Y, BILD_B, Inches(2.6))
y = schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B, [
    (1, "Das Programm zeigt alle Adressen, die in OPERA zu dieser Rechnung stehen. Die **oberste** ist meist die richtige: "
        "zuerst **„Debitorenkonto“**, dann Adressen mit **„primär“**."),
    (2, "Steht die richtige nicht dabei: **von Hand** eintragen. Genau abtippen."),
    (3, "Auf **„Empfänger übernehmen“** klicken. Der Status wird **Bereit**."),
], groesse=14.5)
y2 = hinweis(f, BILD_X, Inches(4.3), BILD_B, "HINWEIS",
             "Stand die Rechnung in **Prüfung**, bleibt sie dort — eine Adresse zu wählen ist noch keine "
             "Freigabe. Sonst wird der Status **Bereit**, und die Automatik darf sie verschicken.")
hinweis(f, BILD_X, y2 + Inches(0.12), BILD_B, "TIPP",
        "Eine von Hand eingetragene Adresse gilt **nur für diese Rechnung**. Damit die nächste Rechnung sie auch hat, "
        "gehört sie in OPERA an das Kundenprofil.", groesse=13)

# =============================================================================
# 10 Kaeuferreferenz
# =============================================================================
f = seite("Schritt 4 · nur bei Bedarf", "Bestellnummer des Kunden eintragen")
bild(f, "07_kaeuferreferenz", BILD_X, INHALT_Y, BILD_B, Inches(3.2))
y = text(f, RAND, INHALT_Y, LINKS_B, Inches(1.2),
         "Manche Firmen verlangen ihre **Bestellnummer** auf der Rechnung — sonst können sie sie nicht zuordnen. "
         "Das Programm nennt das **Käuferreferenz**.", groesse=15)
schritte(f, RAND, Inches(3.0), LINKS_B, [
    (1, "Die Nummer des Kunden **von Hand** eintragen."),
    (2, "Auf **„Käuferreferenz übernehmen“** klicken."),
], groesse=15)
hinweis(f, RAND, Inches(4.75), LINKS_B, "HINWEIS",
        "Steht in der Rechnung **„Ersatzwert“**, hat der Kunde keine Nummer hinterlegt. Für normale Firmen ist das in Ordnung.")
y2 = hinweis(f, BILD_X, Inches(4.95), BILD_B, "TIPP",
             "Für den Empfang: Die Bestellnummer gehört **vor dem Check-out** in OPERA in das Feld "
             "**„Buyer Reference1“** der Reservierung. Dann kommt sie von selbst auf die Rechnung.")

# =============================================================================
# 11 Positionen
# =============================================================================
f = seite("Schritt 4 · meist nichts zu tun", "Wie die Positionen auf der Rechnung stehen")
halb = (BREITE - 2 * RAND - Inches(0.4)) / 2
bild(f, "08_positionen_einzel", RAND, Inches(2.2), halb, Inches(2.6))
bild(f, "09_positionen_gruppe", RAND + halb + Inches(0.4), Inches(1.55), halb * 0.62, Inches(4.2))
text(f, RAND, Inches(1.55), halb, Inches(0.6),
     "**Einzelrechnung:** gleiche Leistungen zum gleichen Preis stehen zusammen — „3 × Übernachtung“.",
     groesse=14.5)
xg = RAND + halb + Inches(0.4) + halb * 0.62 + Inches(0.25)
text(f, xg, Inches(1.6), BREITE - RAND - xg, Inches(2.4),
     "**Gruppe:** je Gast eine Zeile mit **Zimmer und Name**, dazu der Aufenthalt.\n\n"
     "Das Programm erkennt selbst, ob es eine Gruppe ist (1).", groesse=14.5)
y = schritte(f, RAND, Inches(5.05), halb, [
    (1, "Nur wenn der Kunde es anders möchte: andere Art wählen, **„Übernehmen“**."),
    (2, "Die Tabelle zeigt danach genau das, was verschickt wird."),
], groesse=14)
hinweis(f, xg, Inches(4.15), BREITE - RAND - xg, "HINWEIS",
        "Die **Beträge** ändern sich dabei nie — nur die Darstellung.", groesse=13)

# =============================================================================
# 12 Pruefen
# =============================================================================
f = seite("Schritt 5", "Prüfen: „XML erzeugen“")
bild(f, "10_xml_erzeugt", RAND, INHALT_Y, BREITE - 2 * RAND, Inches(2.3))
y = schritte(f, RAND, Inches(4.15), Inches(6.2), [
    (None, "Klicken Sie in der Rechnung auf **„XML erzeugen“**. Das Programm rechnet nach und prüft die "
           "Datei mit dem offiziellen Prüfprogramm."),
    (1, "Steht oben **„XML erzeugt“** ohne weitere Hinweise: **alles in Ordnung.**"),
    (2, "Der Knopf **„Jetzt versenden“** ist dann dunkel und klickbar."),
], groesse=14.5)
hinweis(f, RAND + Inches(6.6), Inches(4.1), BREITE - 2 * RAND - Inches(6.6), "TIPP",
        "Sie können „XML erzeugen“ **so oft drücken, wie Sie wollen**. Es verschickt nichts und ändert nichts in OPERA.")

# =============================================================================
# 13 Rot
# =============================================================================
f = seite("Schritt 5", "Wenn es rot wird")
bild(f, "11_vorpruefung_rot", BILD_X + Inches(1.0), INHALT_Y, BILD_B - Inches(1.0), Inches(3.05))
y = schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B - Inches(0.3), [
    (1, "Unter **„Vorprüfung“** steht in Rot, was fehlt oder nicht passt."),
    (2, "Solange etwas rot ist, bleibt **„Jetzt versenden“ grau**. Es kann nichts Falsches hinausgehen."),
], groesse=14.5)
meldungen = [
    ("… E-Mail / BT-49 fehlt", "Empfänger wählen oder von Hand eintragen."),
    ("Ort, Land oder Name des Empfängers fehlt", "Anschrift in OPERA am Kundenprofil ergänzen, dann die Rechnung neu öffnen."),
    ("Positionen / Summe / Folio-Klammer / Steuergruppe", "Nicht selbst korrigieren — an die Buchhaltung melden."),
    ("KoSIT: …", "Das offizielle Prüfprogramm beanstandet etwas. Rechnungsnummer an die IT geben."),
    ("Nullbeleg / negativer Betrag", "Gehört nicht in den Versand. Zurücklegen."),
]
ty = Inches(5.02)
kasten(f, RAND, ty - Inches(0.36), BREITE - 2 * RAND, Inches(0.36), DUNKEL)
text(f, RAND + Inches(0.15), ty - Inches(0.3), Inches(5), Inches(0.3), "STEHT DORT …", groesse=11, farbe=GRUND, fett=True)
text(f, RAND + Inches(5.4), ty - Inches(0.3), Inches(5), Inches(0.3), "… DANN", groesse=11, farbe=GRUND, fett=True)
for i, (m, a) in enumerate(meldungen):
    kasten(f, RAND, ty + i * Inches(0.36), BREITE - 2 * RAND, Inches(0.36), WEISS if i % 2 == 0 else ZEILE_ALT)
    text(f, RAND + Inches(0.15), ty + i * Inches(0.36) + Inches(0.07), Inches(5.2), Inches(0.3), m, groesse=12, fett=True)
    text(f, RAND + Inches(5.4), ty + i * Inches(0.36) + Inches(0.07), Inches(6.5), Inches(0.3), a, groesse=12)
hinweis(f, RAND, Inches(3.55), LINKS_B - Inches(0.3), "ACHTUNG",
        "Beträge werden **nie** hier korrigiert, sondern in OPERA.", groesse=13, h=Inches(0.98))

# =============================================================================
# 14 Versenden
# =============================================================================
f = seite("Schritt 6", "Versenden")
bild(f, "12_testlauf", BILD_X, INHALT_Y, BILD_B, Inches(1.75))
bild(f, "12b_versendet", BILD_X, Inches(3.55), BILD_B, Inches(1.3))
y = schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B, [
    (None, "In der Rechnung auf **„Jetzt versenden“** klicken."),
    (None, "Oben erscheint **„Versendet“** (unteres Bild). Der Status wird **Gesendet**, "
           "und im Verlauf steht, an wen und wann."),
    (1, "Steht dort **„Testlauf: nicht wirklich versendet“**, ist das Programm im Probebetrieb — "
        "es geht **nichts** an den Kunden."),
    (2, "Den Probebetrieb erkennen Sie oben am Wort **„Testlauf“**."),
], groesse=14)
hinweis(f, BILD_X, Inches(5.15), BILD_B, "ACHTUNG",
        "Versendet ist versendet. Eine verschickte Rechnung lässt sich **nicht zurückholen** und im Programm "
        "**nicht noch einmal** verschicken. Also vorher: Empfänger stimmt? Prüfung grün?")

# =============================================================================
# 15 Sonderfall Firma an Reservierung
# =============================================================================
f = seite("Sonderfall", "„Firma hängt an der Reservierung“ — wer bekommt die Rechnung?")
bild(f, "13_sichtpruefung", BILD_X - Inches(0.3), INHALT_Y, BILD_B + Inches(0.3), Inches(2.95))
schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B - Inches(0.3), [
    (1, "Das Programm ist sich **nicht sicher**: Eine Firma hat gebucht, bezahlt hat vielleicht der Gast selbst."),
    (2, "Schauen Sie auf **„Bezahlt über“**."),
    (None, "Gehört die Rechnung der Firma: Empfänger wählen, dann **„Prüfung abgeschlossen“** — "
           "oder gleich **„Jetzt versenden“**."),
], groesse=14)
ey = Inches(5.05)
eb = (BREITE - 2 * RAND - Inches(0.6)) / 3
entscheid = [
    ("City Ledger", "Die Firma zahlt über ihr Debitorenkonto.",
     "→ Empfänger der Firma wählen, prüfen, versenden.", ARTEN["TIPP"]),
    ("Karte oder bar", "Der Gast hat selbst bezahlt. Die Rechnung gehört ihm, nicht der Firma.",
     "→ **Zurücklegen.** Keine XRechnung an die Firma.", ARTEN["HINWEIS"]),
    ("Unsicher?", "Lieber einmal fragen als falsch verschicken.",
     "→ Liegen lassen, Buchhaltung fragen. Geht nicht automatisch hinaus.", ARTEN["FRAGE"]),
]
text(f, RAND, Inches(4.6), Inches(12), Inches(0.4), "Bezahlt über …", groesse=16, fett=True, farbe=DUNKEL)
for i, (titel, erkl, tun, (farbe, grund)) in enumerate(entscheid):
    x = RAND + i * (eb + Inches(0.3))
    kasten(f, x, ey, eb, Inches(1.8), grund, radius=True)
    kasten(f, x, ey, Inches(0.09), Inches(1.8), farbe)
    text(f, x + Inches(0.28), ey + Inches(0.1), eb - Inches(0.4), Inches(0.35), titel, groesse=15.5, fett=True, farbe=farbe)
    text(f, x + Inches(0.28), ey + Inches(0.45), eb - Inches(0.4), Inches(0.6), erkl, groesse=12.5)
    text(f, x + Inches(0.28), ey + Inches(1.1), eb - Inches(0.4), Inches(0.65), tun, groesse=12.5)

# =============================================================================
# 15b Prüfung abschliessen
# =============================================================================
f = seite("Sonderfall", "Eine geprüfte Rechnung freigeben")
bild(f, "13b_freigeben", RAND, INHALT_Y, BREITE - 2 * RAND, Inches(2.3))
y = schritte(f, RAND, Inches(4.05), Inches(6.3), [
    (None, "Erst den **Empfänger** wählen und übernehmen (weiter unten auf der Seite)."),
    (2, "**„Prüfung abgeschlossen“** gibt die Rechnung frei — ab dann darf die Automatik sie verschicken."),
    (3, "Oder Sie schicken sie gleich selbst: **„Jetzt versenden“**."),
], groesse=14.5)
x2 = RAND + Inches(6.7)
y2 = hinweis(f, x2, Inches(4.0), BREITE - RAND - x2, "HINWEIS",
             "Eine Adresse zu wählen ist **keine** Freigabe. Sonst ginge eine Rechnung hinaus, "
             "während Sie noch prüfen, wem sie gehört.")
hinweis(f, x2, y2 + Inches(0.15), BREITE - RAND - x2, "TIPP",
        "Gehört die Rechnung doch dem Gast? Dann **„Zurücklegen“**. Versehentlich zurückgelegt: "
        "**„Wieder aufnehmen“**.")

# =============================================================================
# 16 Sonderfall keine Adresse
# =============================================================================
f = seite("Sonderfall", "Beim Kunden ist keine E-Mail-Adresse hinterlegt")
bild(f, "14_keine_adresse", BILD_X, INHALT_Y, BILD_B, Inches(2.0))
bild(f, "14b_ohne_adresse_knopf", BILD_X, Inches(3.9), BILD_B * 0.62, Inches(1.0))
y = schritte(f, RAND, INHALT_Y + Inches(0.05), LINKS_B, [
    (1, "Ohne Adresse lässt sich die Rechnung **nicht verschicken**. Sie bleibt in **Prüfung** liegen."),
    (2, "**Schnell:** Adresse von Hand eintragen (Kunde anrufen oder aus einer Mail) und übernehmen."),
    (None, "**Dauerhaft:** Adresse in OPERA am Kundenprofil eintragen und danach **„Jetzt einlesen“** — "
           "dann findet das Programm sie auch bei allen weiteren Rechnungen."),
], groesse=14)
hinweis(f, BILD_X, Inches(5.05), BILD_B, "TIPP",
        "Der Knopf **„… ohne Adresse“** in der Liste (Bild unten rechts) lädt eine **Excel-Liste**: "
        "welche Kunden keine Adresse haben, wie viele Rechnungen daran hängen. "
        "Oben stehen die, bei denen sich die Pflege am meisten lohnt.")

# =============================================================================
# 17 Suchen
# =============================================================================
f = seite("Gut zu wissen", "Eine bestimmte Rechnung finden")
bild(f, "15_suche", RAND, INHALT_Y, BREITE - 2 * RAND, Inches(2.6))
schritte(f, RAND, Inches(4.45), Inches(6.2), [
    (1, "**Rechnungsnummer** in das Suchfeld eintragen und **„Suchen“** klicken."),
    (2, "Steht die Rechnung noch nicht in der Liste, zeigt das Programm sie unter **„In OPERA gefunden“**. "
        "**„In die Liste holen“** nimmt sie auf."),
], groesse=14.5)
x2 = RAND + Inches(6.6)
y2 = hinweis(f, x2, Inches(4.4), BREITE - RAND - x2, "HINWEIS",
             "In OPERA sucht das Programm **nur nach Nummern**, nicht nach Namen. Namen findet es in der Liste.")
hinweis(f, x2, y2 + Inches(0.15), BREITE - RAND - x2, "HINWEIS",
        "Eine so geholte Rechnung kommt erst in **Prüfung** — mit dem Grund dabei.")

# =============================================================================
# 18 Versendet
# =============================================================================
f = seite("Gut zu wissen", "Eine Rechnung ist schon verschickt")
bild(f, "16_versendet", RAND, INHALT_Y, BREITE - 2 * RAND, Inches(2.0))
schritte(f, RAND, Inches(3.85), Inches(6.2), [
    (1, "Statt „XML erzeugen“ steht dort **„Trotzdem neu erzeugen“**. **Nicht drücken** — außer die IT sagt es."),
    (2, "**„Jetzt versenden“** ist grau. Eine Rechnung geht nie zweimal hinaus."),
    (None, "Fragt der Kunde nach: **„XML ansehen“** zeigt genau die Datei, die er bekommen hat. "
           "Im Verlauf unten steht, **an welche Adresse** und **wann**."),
], groesse=14.5)
hinweis(f, RAND + Inches(6.6), Inches(3.8), BREITE - 2 * RAND - Inches(6.6), "HINWEIS",
        "Die Tabelle **„Positionen“** einer versendeten Rechnung wird neu berechnet und kann anders aussehen als "
        "die verschickte Datei. Maßgeblich ist, was **„XML ansehen“** zeigt.")

# =============================================================================
# 19 Zuruecklegen und Verlauf
# =============================================================================
f = seite("Gut zu wissen", "Zurücklegen und Nachvollziehen")
text(f, RAND, INHALT_Y, Inches(5.6), Inches(0.4), "Zurücklegen", groesse=20, schrift=DISPLAY, farbe=DUNKEL)
text(f, RAND, INHALT_Y + Inches(0.5), Inches(5.6), Inches(1.6),
     "Nimmt eine Rechnung aus dem Lauf. Sie wird **nicht** verschickt, weder von Hand noch automatisch.\n"
     "Sinnvoll, wenn der Gast selbst bezahlt hat oder die Rechnung gar keine Firmenrechnung ist.", groesse=14.5)
hinweis(f, RAND, INHALT_Y + Inches(2.1), Inches(5.6), "ACHTUNG",
        "Aus Versehen zurückgelegt? **„Wieder aufnehmen“** holt die Rechnung zurück — "
        "sie landet dann in der Prüfung, nicht im Versand.")
xr = RAND + Inches(6.0)
text(f, xr, INHALT_Y, BREITE - RAND - xr, Inches(0.4), "Wer hat was gemacht?", groesse=20, schrift=DISPLAY, farbe=DUNKEL)
bild(f, "17_protokoll", xr, INHALT_Y + Inches(0.55), BREITE - RAND - xr, Inches(2.6))
text(f, xr, Inches(4.9), BREITE - RAND - xr, Inches(1.2),
     "Oben im Menü unter **„Protokoll“** (1) steht jede Aktion mit Zeit und Benutzer — auch, an welche Adresse "
     "verschickt wurde. In jeder Rechnung steht unten derselbe **Verlauf** nur für diese Rechnung.", groesse=14)

# =============================================================================
# 20-22 FAQ
# =============================================================================
faq = [
    ("Warum steht eine Rechnung nicht in der Liste?",
     "Aufgenommen werden nur **abgeschlossene Firmenrechnungen an Kunden in Deutschland** aus dem eingestellten "
     "Zeitraum. Suchen Sie nach der **Rechnungsnummer** — findet das Programm sie in OPERA, holen Sie sie mit "
     "„In die Liste holen“."),
    ("Warum wurde eine Rechnung nicht automatisch verschickt?",
     "Mögliche Gründe: Status **Prüfung** oder **Fehler** · **kein Empfänger** gewählt · die **Wartezeit** läuft noch · "
     "Automatik ist **aus** oder im **Testlauf** · Rechnungen über das **Debitorenkonto** gehen in der Grundeinstellung nur von Hand hinaus."),
    ("Ich kann nicht auf „Jetzt versenden“ klicken.",
     "Der Knopf ist **grau**, wenn kein Empfänger gewählt ist, die Prüfung rot ist oder die Rechnung schon "
     "verschickt oder zurückgelegt wurde. **Fehlt** der Knopf ganz, hat Ihr Zugang die Rolle „ansehen“ — fragen Sie die IT."),
    ("Der Kunde sagt, er hat nichts bekommen.",
     "Rechnung öffnen: Steht der Status auf **Gesendet**? Der **Verlauf** zeigt Adresse und Uhrzeit. "
     "Bitten Sie den Kunden, im **Spam-Ordner** nachzusehen. Stand oben „Testlauf“, ging nichts hinaus. "
     "Sonst: Rechnungsnummer an die IT."),
    ("Ich habe an die falsche Adresse verschickt.",
     "Im Programm lässt sich das nicht rückgängig machen oder neu verschicken. Geben Sie **sofort** "
     "Rechnungsnummer und die richtige Adresse an die IT."),
    ("Der Kunde möchte seine Bestellnummer auf der Rechnung.",
     "Noch nicht verschickt: in der Rechnung unter **Käuferreferenz** eintragen. Schon verschickt: an die IT. "
     "Für die Zukunft: Empfang trägt sie **vor dem Check-out** in „Buyer Reference1“ ein."),
    ("Der Betrag stimmt nicht.",
     "Das Programm übernimmt die Beträge aus OPERA, es rechnet nichts um. Die Rechnung **in OPERA** korrigieren "
     "lassen. Die falsche **nicht** versenden, sondern zurücklegen."),
    ("Bei einer Gruppe fehlen die Namen der Gäste.",
     "Unter **„Positionen“** die Art **„Je Gast und Zimmer“** wählen und „Übernehmen“. Das Programm wählt sie "
     "normalerweise selbst, sobald mehrere Reservierungen auf der Rechnung sind."),
    ("Muss ich zusätzlich ein PDF schicken?",
     "Die E-Mail enthält die **XML-Datei** — das ist die Rechnung. Ein PDF hängt derzeit **nicht** mit. "
     "Möchte der Kunde eines, schicken Sie es wie gewohnt aus OPERA."),
    ("Oben steht „Automatik arbeitet“, die Knöpfe sind grau.",
     "Dann läuft gerade ein automatischer Durchlauf; er dauert meist Sekunden. Kurz warten und die "
     "Seite neu laden — danach sind Einlesen und Versenden wieder frei."),
    ("Was heißt „Ersatzwert“ bei der Käuferreferenz?",
     "Der Kunde hat keine Bestellnummer hinterlegt, deshalb steht dort unsere Reservierungsnummer. "
     "Für Firmen ist das **in Ordnung**. Für **Behörden** nicht — die brauchen eine Leitweg-ID: bitte an die Buchhaltung."),
    ("Die XML-Datei sieht unleserlich aus.",
     "Das ist **richtig so**. Die Datei ist für das Buchhaltungsprogramm des Kunden gemacht, nicht zum Lesen."),
    ("Kann ich etwas kaputt machen?",
     "In OPERA **nein** — das Programm liest dort nur. „XML erzeugen“ und „Jetzt einlesen“ sind immer harmlos. "
     "Endgültig sind nur **Versenden** und **Zurücklegen**."),
    ("Oben steht „Testlauf“. Was heißt das?",
     "Das Programm arbeitet im **Probebetrieb**: Es prüft alles, verschickt aber **nichts**. "
     "Die Meldung nach „Jetzt versenden“ lautet dann „Testlauf: nicht wirklich versendet“."),
    ("Ich sehe „Konfiguration“ im Menü.",
     "Das ist für die IT. Bitte dort **nichts ändern** — Einstellungen wirken auf alle Rechnungen."),
]
pro_seite = 5
seiten = [faq[i:i + pro_seite] for i in range(0, len(faq), pro_seite)]
spalte_b = (BREITE - 2 * RAND - Inches(0.35)) / 2
for n, teil in enumerate(seiten, 1):
    f = seite("Häufige Fragen", f"Fragen, die oft kommen ({n}/{len(seiten)})")
    ys = [INHALT_Y, INHALT_Y]
    for i, (q, a) in enumerate(teil):
        s = 0 if ys[0] <= ys[1] else 1
        ys[s] = frage(f, RAND + s * (spalte_b + Inches(0.35)), ys[s], spalte_b, q, a)

# =============================================================================
# 23 Spickzettel
# =============================================================================
f = seite("Zum Ausdrucken", "Spickzettel")
liste = [
    "Anmelden, Liste öffnen — Reiter **Prüfung** und **Fehler** zuerst ansehen.",
    "„Firma an der Reservierung“? → auf **„Bezahlt über“** schauen.",
    "**Empfänger** prüfen, **„Empfänger übernehmen“**, in Prüfung dazu **„Prüfung abgeschlossen“**.",
    "Hat der Kunde eine **Bestellnummer** genannt? → Käuferreferenz eintragen.",
    "**„XML erzeugen“** — nichts Rotes? Sonst Meldung lesen.",
    "**„Jetzt versenden“** — Meldung „Versendet“, Status **Gesendet**.",
    "Gast hat selbst bezahlt oder Nullbeleg? → **Zurücklegen**.",
    "Beträge falsch? → **In OPERA** korrigieren, nicht hier.",
]
y = INHALT_Y + Inches(0.05)
for i, punkt in enumerate(liste, 1):
    kasten(f, RAND, y, Inches(0.36), Inches(0.36), WEISS, rahmen=AKZENT, radius=True, linie=1.5)
    text(f, RAND + Inches(0.55), y + Inches(0.03), Inches(7.4), Inches(0.5), f"{i}.  {punkt}", groesse=15)
    y += Inches(0.56)
xk = RAND + Inches(8.35)
kasten(f, xk, INHALT_Y, BREITE - RAND - xk, Inches(5.25), WEISS, rahmen=RGBColor(0xE2, 0xDD, 0xD3), radius=True)
text(f, xk + Inches(0.3), INHALT_Y + Inches(0.25), Inches(3.5), Inches(0.4), "Bei Fragen", groesse=20,
     schrift=DISPLAY, farbe=DUNKEL)
text(f, xk + Inches(0.3), INHALT_Y + Inches(0.85), BREITE - RAND - xk - Inches(0.6), Inches(3.4),
     "**Buchhaltung** — Beträge, Empfänger, Behörden\n\n______________________\n\n"
     "**IT** — Zugang, Fehlermeldungen, versehentlich verschickt oder zurückgelegt\n\n______________________\n\n"
     "Immer die **Rechnungsnummer** mitschicken.", groesse=14)
hinweis(f, RAND, Inches(5.9), Inches(7.95), "TIPP",
        "Harmlos und beliebig oft: „Jetzt einlesen“, „XML erzeugen“, „XML ansehen“. Endgültig: „Jetzt versenden“, „Zurücklegen“.",
        groesse=13, h=Inches(0.98))

prs.save(ZIEL)
print("gespeichert:", ZIEL, f"({nummer[0] + 1} Folien)")
