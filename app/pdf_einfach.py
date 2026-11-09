"""Ein einfaches PDF ohne fremde Bibliothek: eine A4-Seite mit Text, Linien,
Flaechen und einem Bild (Logo), Schrift Helvetica normal und fett.

Warum selbst: Eine PDF-Bibliothek (fpdf2) braucht Pillow mit kompilierten
Teilen, und eine neue Abhaengigkeit muss beim Update auf dem Server per pip
nachgezogen werden. Genau das scheiterte dort am 03.11.2026, die
Aktualisierung wurde nicht eingespielt. Fuer ein einseitiges Schreiben reicht
dieser Baustein, und er laeuft ueberall, wo Python laeuft.

Helvetica ist eine der 14 Standardschriften, die jeder PDF-Betrachter
mitbringt; sie wird nicht eingebettet. Kodiert wird mit WinAnsiEncoding, also
nur Latin-1 (Umlaute und ß, aber kein €). Was darueber hinausgeht, muss der
Aufrufer vorher ersetzen; hier wird es zu '?'.

Bilder: JPEG wird unveraendert eingebettet. PNG wird entpackt und neu
gepackt, damit auch Transparenz (Alphakanal, transparente Palettenfarbe)
stimmt: 8 Bit je Kanal, Graustufen, RGB oder Palette, ohne Interlacing.

Formularfelder: Textfelder, die der Empfaenger in einem PDF-Programm
ausfuellen kann (AcroForm). Jedes Feld bringt sein Erscheinungsbild selbst
mit, damit ein vorbelegter Wert auch dort zu sehen ist, wo ein Betrachter
Felder nicht selbst zeichnet. Der Rahmen steht im Seiteninhalt: Ausgedruckt
bleibt so ein Kasten zum Ausfuellen von Hand.

Koordinaten in Millimetern, gemessen von der linken OBEREN Ecke; bei Text ist
y die Grundlinie."""
from __future__ import annotations

import struct
import zlib

MM = 72 / 25.4
BREITE_MM, HOEHE_MM = 210.0, 297.0

# Zeichenbreiten in 1/1000 der Schriftgroesse fuer die Zeichen 32 bis 255
# (Adobe-Metriken der Standardschrift Helvetica, WinAnsi).
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 350,
    556, 350, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350,
    350, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 350, 500, 667,
    278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333,
    400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611,
    667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,
    556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,
]
_HELVETICA_FETT = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 350,
    556, 350, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 350, 611, 350,
    350, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 350, 500, 667,
    278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333,
    400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611,
    722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,
    556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278,
    611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,
]
_SCHRIFTEN = {False: (b"F1", _HELVETICA), True: (b"F2", _HELVETICA_FETT)}


class BildFehler(ValueError):
    """Das Bild laesst sich nicht einbetten. Der Text sagt warum."""


def _latin1(text: str) -> bytes:
    aus = bytearray()
    for z in str(text or ""):
        n = ord(z)
        aus.append(n if (32 <= n < 127 or 160 <= n < 256) else 63)   # sonst '?'
    return bytes(aus)


def breite(text: str, groesse: float, fett: bool = False) -> float:
    """Breite eines Texts in Millimetern."""
    tabelle = _SCHRIFTEN[fett][1]
    return sum(tabelle[b - 32] for b in _latin1(text)) * groesse / 1000 / MM


def umbrechen(text: str, max_breite: float, groesse: float, fett: bool = False) -> list[str]:
    """Text in Zeilen, die hoechstens max_breite (mm) breit sind. Umbrochen
    wird an Leerzeichen und an Zeilenumbruechen im Text; ein einzelnes zu
    langes Wort wird hart geteilt."""
    zeilen: list[str] = []
    for absatz in str(text or "").replace("\r\n", "\n").split("\n"):
        zeile = ""
        for wort in absatz.split(" "):
            versuch = f"{zeile} {wort}" if zeile else wort
            if breite(versuch, groesse, fett) <= max_breite:
                zeile = versuch
                continue
            if zeile:
                zeilen.append(zeile)
            while len(wort) > 1 and breite(wort, groesse, fett) > max_breite:
                teil = len(wort) - 1
                while teil > 1 and breite(wort[:teil], groesse, fett) > max_breite:
                    teil -= 1
                zeilen.append(wort[:teil])
                wort = wort[teil:]
            zeile = wort
        zeilen.append(zeile)
    return zeilen


def _pdf_string(text: str) -> bytes:
    roh = _latin1(text).replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + roh + b")"


# ------------------------------------------------------------------ Bilder
def _jpeg(daten: bytes) -> dict:
    """Groesse und Farbraum aus dem SOF-Abschnitt; die Daten bleiben, wie sie sind."""
    i = 2
    while i + 9 < len(daten):
        if daten[i] != 0xFF:
            raise BildFehler("Die JPEG-Datei ist beschädigt.")
        marke = daten[i + 1]
        laenge = struct.unpack(">H", daten[i + 2:i + 4])[0]
        if marke in (0xC0, 0xC1, 0xC2):
            hoehe, breite_px = struct.unpack(">HH", daten[i + 5:i + 9])
            kanaele = daten[i + 9]
            raum = {1: b"/DeviceGray", 3: b"/DeviceRGB", 4: b"/DeviceCMYK"}.get(kanaele)
            if raum is None:
                raise BildFehler("Dieses JPEG hat eine ungewöhnliche Farbtiefe.")
            extra = b" /Decode [1 0 1 0 1 0 1 0]" if kanaele == 4 else b""
            return {"breite": breite_px, "hoehe": hoehe, "farbraum": raum,
                    "daten": daten, "filter": b"/DCTDecode", "extra": extra, "maske": None}
        i += 2 + laenge
    raise BildFehler("In der JPEG-Datei steht keine Bildgröße.")


def _png(daten: bytes) -> dict:
    """PNG entpacken, Zeilenfilter aufloesen, Farbe und Transparenz trennen."""
    i, idat, palette, trns = 8, b"", b"", b""
    kopf = None
    while i + 8 <= len(daten):
        laenge = struct.unpack(">I", daten[i:i + 4])[0]
        art = daten[i + 4:i + 8]
        inhalt = daten[i + 8:i + 8 + laenge]
        if art == b"IHDR":
            kopf = struct.unpack(">IIBBBBB", inhalt)
        elif art == b"PLTE":
            palette = inhalt
        elif art == b"tRNS":
            trns = inhalt
        elif art == b"IDAT":
            idat += inhalt
        elif art == b"IEND":
            break
        i += 12 + laenge
    if kopf is None:
        raise BildFehler("Die PNG-Datei ist beschädigt.")
    b, h, tiefe, typ, _, _, interlace = kopf
    if tiefe != 8 or interlace or typ not in (0, 2, 3, 4, 6):
        raise BildFehler("Dieses PNG wird nicht unterstützt (nur 8 Bit je Kanal, ohne "
                         "Interlacing). Bitte als normales PNG oder als JPG speichern.")
    if b * h > 4_000_000:
        raise BildFehler("Das Bild ist zu groß. Für ein Logo reichen 1.000 Pixel Breite.")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[typ]
    roh = zlib.decompress(idat)
    zeile = b * bpp
    pixel = bytearray()
    vorige = bytearray(zeile)
    for y in range(h):
        start = y * (zeile + 1)
        f = roh[start]
        akt = bytearray(roh[start + 1:start + 1 + zeile])
        if f == 1:
            for x in range(bpp, zeile):
                akt[x] = (akt[x] + akt[x - bpp]) & 0xFF
        elif f == 2:
            for x in range(zeile):
                akt[x] = (akt[x] + vorige[x]) & 0xFF
        elif f == 3:
            for x in range(zeile):
                links = akt[x - bpp] if x >= bpp else 0
                akt[x] = (akt[x] + ((links + vorige[x]) >> 1)) & 0xFF
        elif f == 4:
            for x in range(zeile):
                a = akt[x - bpp] if x >= bpp else 0
                c = vorige[x - bpp] if x >= bpp else 0
                bb = vorige[x]
                p = a + bb - c
                pa, pb, pc = abs(p - a), abs(p - bb), abs(p - c)
                akt[x] = (akt[x] + (a if pa <= pb and pa <= pc else bb if pb <= pc else c)) & 0xFF
        elif f != 0:
            raise BildFehler("Die PNG-Datei ist beschädigt (unbekannter Zeilenfilter).")
        pixel += akt
        vorige = akt
    farbe, alpha = bytearray(), bytearray()
    if typ == 0:
        farbe, raum = pixel, b"/DeviceGray"
        if len(trns) >= 2:
            grau = struct.unpack(">H", trns[:2])[0] & 0xFF
            alpha = bytearray(0 if v == grau else 255 for v in pixel)
    elif typ == 2:
        farbe, raum = pixel, b"/DeviceRGB"
        if len(trns) >= 6:
            r, g, bl = (struct.unpack(">H", trns[k:k + 2])[0] & 0xFF for k in (0, 2, 4))
            alpha = bytearray(0 if (pixel[k], pixel[k + 1], pixel[k + 2]) == (r, g, bl) else 255
                              for k in range(0, len(pixel), 3))
    elif typ == 3:
        raum = b"/DeviceRGB"
        for v in pixel:
            farbe += palette[v * 3:v * 3 + 3] or b"\x00\x00\x00"
        if trns:
            alpha = bytearray(trns[v] if v < len(trns) else 255 for v in pixel)
    elif typ == 4:
        farbe, alpha, raum = pixel[0::2], pixel[1::2], b"/DeviceGray"
    else:
        raum = b"/DeviceRGB"
        for k in range(0, len(pixel), 4):
            farbe += pixel[k:k + 3]
            alpha.append(pixel[k + 3])
    maske = None
    if alpha and min(alpha) < 255:
        maske = zlib.compress(bytes(alpha))
    return {"breite": b, "hoehe": h, "farbraum": raum, "daten": zlib.compress(bytes(farbe)),
            "filter": b"/FlateDecode", "extra": b"", "maske": maske}


def bild_lesen(daten: bytes) -> dict:
    """Ein Bild fuer die Einbettung vorbereiten. Wirft BildFehler."""
    if daten[:3] == b"\xff\xd8\xff":
        return _jpeg(daten)
    if daten[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            return _png(daten)
        except (zlib.error, struct.error, IndexError) as e:
            raise BildFehler("Die PNG-Datei ist beschädigt.") from e
    raise BildFehler("Nur PNG oder JPG.")


# ------------------------------------------------------------------ Seite
class Seite:
    def __init__(self) -> None:
        self._inhalt: list[bytes] = []
        self._bilder: list[dict] = []
        self._felder: list[dict] = []

    def _y(self, y_mm: float) -> float:
        return (HOEHE_MM - y_mm) * MM

    def text(self, x: float, y: float, text: str, groesse: float = 10, fett: bool = False,
             grau: float = 0.0, ausrichtung: str = "links") -> None:
        """Text mit Grundlinie bei y. ausrichtung: links (x ist der Anfang),
        rechts (x ist das Ende) oder mitte (x ist die Mitte)."""
        if ausrichtung == "rechts":
            x -= breite(text, groesse, fett)
        elif ausrichtung == "mitte":
            x -= breite(text, groesse, fett) / 2
        name = _SCHRIFTEN[fett][0]
        self._inhalt.append(b"BT %.3f g /%s %.2f Tf %.2f %.2f Td " % (
            grau, name, groesse, x * MM, self._y(y)) + _pdf_string(text) + b" Tj ET")

    def linie(self, x1: float, y1: float, x2: float, y2: float, grau: float = 0.45,
              staerke: float = 0.3) -> None:
        self._inhalt.append(b"%.3f G %.2f w %.2f %.2f m %.2f %.2f l S" % (
            grau, staerke * MM, x1 * MM, self._y(y1), x2 * MM, self._y(y2)))

    def flaeche(self, x: float, y: float, b: float, h: float,
                rgb: tuple = (0.95, 0.94, 0.91)) -> None:
        """Gefuelltes Rechteck, (x, y) ist die linke obere Ecke."""
        self._inhalt.append(b"%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f 0 g" % (
            *rgb, x * MM, self._y(y + h), b * MM, h * MM))

    def rahmen(self, x: float, y: float, b: float, h: float, grau: float = 0.6,
               staerke: float = 0.25) -> None:
        """Rechteck ohne Fuellung, (x, y) ist die linke obere Ecke."""
        self._inhalt.append(b"%.3f G %.2f w %.2f %.2f %.2f %.2f re S" % (
            grau, staerke * MM, x * MM, self._y(y + h), b * MM, h * MM))

    def feld(self, name: str, x: float, y: float, b: float, h: float, wert: str = "",
             groesse: float = 9, mehrzeilig: bool = False) -> None:
        """Ein ausfuellbares Textfeld mit Rahmen; (x, y) ist die linke obere
        Ecke. name ist der technische Feldname (nur Buchstaben, Ziffern, _)
        und muss auf der Seite eindeutig sein."""
        if not name or not all(z.isascii() and (z.isalnum() or z == "_") for z in name):
            raise ValueError(f"Feldname {name!r}: nur Buchstaben, Ziffern und _.")
        if any(f["name"] == name for f in self._felder):
            raise ValueError(f"Feldname {name!r} gibt es schon.")
        self.rahmen(x, y, b, h)
        self._felder.append({"name": name, "x": x, "y": y, "b": b, "h": h,
                             "wert": str(wert or ""), "groesse": groesse,
                             "mehrzeilig": mehrzeilig})

    def bild(self, bild: dict, x: float, y: float, b: float, h: float) -> None:
        """Ein mit bild_lesen vorbereitetes Bild; (x, y) ist die linke obere Ecke."""
        nr = len(self._bilder) + 1
        self._bilder.append(bild)
        self._inhalt.append(b"q %.2f 0 0 %.2f %.2f %.2f cm /Im%d Do Q" % (
            b * MM, h * MM, x * MM, self._y(y + h), nr))

    def pdf(self, titel: str = "", autor: str = "", komprimieren: bool = True) -> bytes:
        inhalt = b"\n".join(self._inhalt)
        objekte: list[bytes] = []

        def neu(obj: bytes) -> int:
            objekte.append(obj)
            return len(objekte)

        def strom(daten: bytes, kopf: bytes = b"") -> bytes:
            return b"<< " + kopf + b" /Length %d >>\nstream\n" % len(daten) + daten + b"\nendstream"

        katalog = neu(b"")          # 1, wird unten gefuellt
        seiten = neu(b"")           # 2
        f1 = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                 b"/Encoding /WinAnsiEncoding >>")
        f2 = neu(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                 b"/Encoding /WinAnsiEncoding >>")
        bilder = []
        for bild in self._bilder:
            maske = b""
            if bild["maske"] is not None:
                m = neu(strom(bild["maske"], b"/Type /XObject /Subtype /Image /Width %d /Height %d "
                              b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode"
                              % (bild["breite"], bild["hoehe"])))
                maske = b" /SMask %d 0 R" % m
            bilder.append(neu(strom(bild["daten"], b"/Type /XObject /Subtype /Image /Width %d "
                                    b"/Height %d /ColorSpace %s /BitsPerComponent 8 /Filter %s%s%s"
                                    % (bild["breite"], bild["hoehe"], bild["farbraum"],
                                       bild["filter"], bild["extra"], maske))))
        if komprimieren:
            inhalt_nr = neu(strom(zlib.compress(inhalt), b"/Filter /FlateDecode"))
        else:
            inhalt_nr = neu(strom(inhalt))
        xobj = b" ".join(b"/Im%d %d 0 R" % (k + 1, nr) for k, nr in enumerate(bilder))
        seite = len(objekte) + 1 + 2 * len(self._felder)   # nach den Feldern
        felder = []
        for f in self._felder:
            bb, hh = f["b"] * MM, f["h"] * MM
            g = f["groesse"]
            # Erscheinungsbild: der vorbelegte Wert, eine Zeile, linksbuendig.
            # Mehrzeilige Felder beginnen oben, einzeilige stehen mittig.
            grund = hh - g * 1.15 if f["mehrzeilig"] else (hh - g * 0.72) / 2
            text = b""
            if f["wert"]:
                text = (b"BT /F1 %.2f Tf 0 g 2 %.2f Td " % (g, grund)
                        + _pdf_string(f["wert"]) + b" Tj ET")
            bild_ = neu(strom(b"/Tx BMC q 1 1 %.2f %.2f re W n " % (bb - 2, hh - 2) + text
                              + b" Q EMC",
                              b"/Type /XObject /Subtype /Form /BBox [0 0 %.2f %.2f] "
                              b"/Resources << /Font << /F1 %d 0 R >> >>" % (bb, hh, f1)))
            x0, y0 = f["x"] * MM, self._y(f["y"] + f["h"])
            felder.append(neu(
                b"<< /Type /Annot /Subtype /Widget /FT /Tx /T " + _pdf_string(f["name"])
                + b" /Rect [%.2f %.2f %.2f %.2f] /F 4 /P %d 0 R /Ff %d /DA (/F1 %.2f Tf 0 g)"
                % (x0, y0, x0 + bb, y0 + hh, seite, 4096 if f["mehrzeilig"] else 0, g)
                + (b" /V " + _pdf_string(f["wert"]) if f["wert"] else b"")
                + b" /BS << /W 0 >> /MK << >> /AP << /N %d 0 R >> >>" % bild_))
        annots = (b" /Annots [" + b" ".join(b"%d 0 R" % n for n in felder) + b"]"
                  if felder else b"")
        nr_seite = neu(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                   b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >>%s >> /Contents %d 0 R%s >>"
                   % (seiten, BREITE_MM * MM, HOEHE_MM * MM, f1, f2,
                      (b" /XObject << " + xobj + b" >>") if bilder else b"", inhalt_nr,
                      annots))
        if nr_seite != seite:   # die Felder verweisen vorab auf diese Nummer
            raise RuntimeError("PDF: Seitenobjekt an unerwarteter Stelle.")
        formular = (b" /AcroForm << /Fields [" + b" ".join(b"%d 0 R" % n for n in felder)
                    + b"] /DA (/F1 9 Tf 0 g) /DR << /Font << /F1 %d 0 R >> >> >>" % f1
                    if felder else b"")
        objekte[katalog - 1] = b"<< /Type /Catalog /Pages %d 0 R%s >>" % (seiten, formular)
        objekte[seiten - 1] = b"<< /Type /Pages /Kids [%d 0 R] /Count 1 >>" % seite
        info = neu(b"<< /Title " + _pdf_string(titel) + b" /Author " + _pdf_string(autor)
                   + b" /Producer (OPERA XRechnung) >>")

        aus = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        stellen = []
        for nr, obj in enumerate(objekte, 1):
            stellen.append(len(aus))
            aus += b"%d 0 obj\n" % nr + obj + b"\nendobj\n"
        xref = len(aus)
        aus += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
        for s in stellen:
            aus += b"%010d 00000 n \n" % s
        aus += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objekte) + 1, katalog, info, xref)
        return bytes(aus)
