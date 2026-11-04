"""Seiten der Zahlungsanforderung (app/zahlungsanforderung.py).

Eingebunden am Ende von app/main.py. Ablauf: Kunde suchen, Angaben
eintragen, pruefen, senden."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import config, mailer
from . import zahlungsanforderung as za
from .main import _darf_verwalten, _kontext, seiten

router = APIRouter()

FELDER = ("brutto_7", "brutto_19", "grund", "faellig", "von", "bis", "referenz",
          "empfaenger")


async def _form(request: Request) -> tuple[dict, int | None]:
    form = await request.form()
    werte = {f: str(form.get(f) or "") for f in FELDER}
    # Eine eigene Adresse geht vor die Auswahl aus dem Profil.
    eigene = str(form.get("empfaenger_eigen") or "").strip()
    if eigene:
        werte["empfaenger"] = eigene
    werte["empfaenger_eigen"] = eigene
    werte["aktion"] = str(form.get("aktion") or "")
    try:
        name_id = int(str(form.get("name_id") or ""))
    except ValueError:
        name_id = None
    return werte, name_id


def _seite(request: Request, *, suche: str = "", name_id: int | None = None,
           werte: dict | None = None, vorschau: dict | None = None,
           meldung: str = "", fehler: str = ""):
    cfg = config.laden()
    treffer: list = []
    kunde: dict = {}
    if suche and not fehler:
        try:
            treffer = za.kunden_suchen(cfg, suche)
            if not treffer and len(suche.strip()) >= za.SUCHE_MINDESTENS:
                meldung = meldung or f"Kein Profil beginnt mit „{suche.strip()}“."
        except Exception as e:
            fehler = f"Die Suche in OPERA ging nicht: {e}"
    if name_id and not fehler:
        try:
            kunde = za.kunde(cfg, name_id)
        except Exception as e:
            fehler = f"Das Profil ließ sich nicht lesen: {e}"
    werte = werte or {}
    if kunde and not werte:
        werte = {"faellig": za.faellig_vorgabe(cfg),
                 "empfaenger": (kunde.get("mails") or [{}])[0].get("email", "")}
    try:
        liste = za.liste(50)
        naechste = za.naechste_nummer(cfg)
        for a in liste:
            a["pdf_da"] = za.pdf_datei(cfg, a["nummer"], a) is not None
    except Exception:
        liste, naechste = [], ""
    return seiten.TemplateResponse(request, "zahlungsanforderung.html", _kontext(
        request, suche=suche, treffer=treffer, kunde=kunde, name_id=name_id, werte=werte,
        vorschau=vorschau, meldung=meldung, fehler=fehler, liste=liste, naechste=naechste,
        euro=za.euro, datum=za.datum, hinweis=za.HINWEIS_KEINE_RECHNUNG,
        testlauf=bool((cfg.get("automatik") or {}).get("testlauf")),
        blindkopien=mailer.blindkopien(cfg, False)))


@router.get("/zahlungsanforderung", response_class=HTMLResponse)
def maske(request: Request, suche: str = "", name_id: int | None = None, meldung: str = ""):
    return _seite(request, suche=suche, name_id=name_id, meldung=meldung)


@router.post("/zahlungsanforderung/pruefen", response_class=HTMLResponse)
async def pruefen(request: Request):
    """Prueft die Angaben und zeigt die Zusammenfassung. Schreibt nichts."""
    werte, name_id = await _form(request)
    if not name_id:
        return _seite(request, fehler="Bitte zuerst einen Kunden auswählen.")
    try:
        eingabe, _, _, befunde = za.vorbereiten(config.laden(), werte, name_id)
    except za.Eingabefehler as e:
        return _seite(request, name_id=name_id, werte=werte, fehler=str(e))
    except Exception as e:
        return _seite(request, name_id=name_id, werte=werte,
                      fehler=f"Die Zahlungsanforderung ließ sich nicht vorbereiten: {e}")
    return _seite(request, name_id=name_id, werte=werte,
                  vorschau={"eingabe": eingabe, "befunde": befunde})


@router.post("/zahlungsanforderung/pdf")
async def pdf_ansehen(request: Request):
    """Das PDF, wie es hinausginge. Schreibt nichts, vergibt keine Nummer."""
    werte, name_id = await _form(request)
    cfg = config.laden()
    try:
        eingabe, k, h, _ = za.vorbereiten(cfg, werte, name_id or 0)
        dokument = za.pdf(cfg, eingabe, k, h)   # mit der voraussichtlichen Nummer
    except Exception as e:
        return Response(f"Nicht möglich: {e}", media_type="text/plain; charset=utf-8",
                        status_code=409)
    return Response(dokument, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{eingabe["nummer"]}.pdf"'})


@router.post("/zahlungsanforderung/senden", response_class=HTMLResponse)
async def senden(request: Request):
    werte, name_id = await _form(request)
    if not _darf_verwalten(request):
        return _seite(request, name_id=name_id, werte=werte,
                      fehler="Keine Berechtigung — Versenden dürfen nur Verwalter.")
    try:
        ergebnis, nummer = za.versenden(config.laden(), werte, name_id or 0,
                                        request.state.benutzer,
                                        mit_mail=werte["aktion"] != "ablegen")
    except Exception as e:
        return _seite(request, name_id=name_id, werte=werte, fehler=str(e))
    meldung = {"testlauf": f"Testlauf aktiv — die Zahlungsanforderung wurde geprüft, aber keine "
                           f"Nummer vergeben (voraussichtlich {nummer}), nichts abgelegt und "
                           "nichts versendet.",
               "abgelegt": f"Zahlungsanforderung {nummer} abgelegt (nicht versendet).",
               }.get(ergebnis, f"Zahlungsanforderung {nummer} versendet.")
    return RedirectResponse("/zahlungsanforderung?" + urlencode({"meldung": meldung}),
                            status_code=303)


@router.get("/zahlungsanforderung/ablage/{nummer}.pdf")
def ablage(request: Request, nummer: str):
    pfad = za.pdf_datei(config.laden(), nummer)
    if not pfad:
        return Response("Nicht in der Ablage.", media_type="text/plain; charset=utf-8",
                        status_code=404)
    return Response(pfad.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{pfad.name}"'})


@router.get("/zahlungsanforderung/suche", response_class=HTMLResponse)
def suche(request: Request, q: str = "", von: str = "", bis: str = "", status: str = ""):
    """Alle abgelegten Zahlungsanforderungen durchsuchen. Liest nur die
    eigene Ablage, nicht OPERA."""
    treffer, mehr, fehler = [], False, ""
    try:
        treffer, mehr = za.suchen(q, von, bis, status)
    except ValueError as e:
        fehler = f"Die Suche ging nicht: {e}"
    gesucht = bool(q.strip() or von or bis or status)
    cfg = config.laden()
    for t in treffer:
        t["pdf_da"] = za.pdf_datei(cfg, t["nummer"], t) is not None
    return seiten.TemplateResponse(request, "zahlungsanforderung_suche.html", _kontext(
        request, q=q, von=von, bis=bis, status=status, status_wahl=za.STATUS_WAHL,
        liste=treffer, mehr=mehr, hoechstens=za.SUCHE_HOECHSTENS, gesucht=gesucht,
        fehler=fehler, euro=za.euro, datum=za.datum))


# ------------------------------------------------------------------ Vorlage
# Logo und Texte des Schreibens, nur fuer Verwalter.

def _vorlage_seite(request: Request, werte: dict | None = None, meldung: str = "",
                   fehler: str = ""):
    logo = za.logo_pfad()
    return seiten.TemplateResponse(request, "zahlungsanforderung_vorlage.html", _kontext(
        request, werte=werte or za.vorlage_laden(), vorgabe=za.VORLAGE_VORGABE,
        platzhalter=za.PLATZHALTER, laengen=za.LAENGEN, logo=logo,
        ausrichtungen=za.AUSRICHTUNGEN, bloecke=za.BLOECKE, regeln=za.LAYOUT_REGELN,
        naechste_zahl=_still(za.naechste_zahl), naechste=_still(za.naechste_nummer, config.laden()),
        logo_stand=int(logo.stat().st_mtime) if logo else 0,
        meldung=meldung, fehler=fehler))


def _still(f, *a):
    try:
        return f(*a)
    except Exception:
        return ""


def _texte(form) -> dict:
    """Texte und Anordnung aus dem Formular. Was fehlt, bleibt weg — dann
    gilt die Vorgabe."""
    return {f: str(form.get(f)) for f in za.VORLAGE_VORGABE if form.get(f) is not None}


@router.get("/zahlungsanforderung/vorlage", response_class=HTMLResponse)
def vorlage(request: Request, meldung: str = ""):
    if not _darf_verwalten(request):
        return RedirectResponse("/zahlungsanforderung?meldung=Keine Berechtigung", status_code=303)
    return _vorlage_seite(request, meldung=meldung)


@router.post("/zahlungsanforderung/vorlage", response_class=HTMLResponse)
async def vorlage_speichern(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/zahlungsanforderung?meldung=Keine Berechtigung", status_code=303)
    form = await request.form()
    werte = za.VORLAGE_VORGABE if form.get("aktion") == "vorgabe" else _texte(form)
    try:
        za.vorlage_speichern(werte)
    except za.Eingabefehler as e:
        return _vorlage_seite(request, werte=dict(za.vorlage_laden(), **_texte(form)),
                              fehler=str(e))
    meldung = ("Vorgaben wiederhergestellt." if form.get("aktion") == "vorgabe"
               else "Vorlage gespeichert.")
    return RedirectResponse("/zahlungsanforderung/vorlage?" + urlencode({"meldung": meldung}),
                            status_code=303)


@router.post("/zahlungsanforderung/vorlage/muster")
async def vorlage_muster(request: Request):
    """Muster-PDF mit den Texten aus dem Formular, ohne sie zu speichern."""
    if not _darf_verwalten(request):
        return Response("Keine Berechtigung.", media_type="text/plain; charset=utf-8",
                        status_code=403)
    try:
        texte = za.vorlage_pruefen(_texte(await request.form()))
        dokument = za.muster(config.laden(), texte)
    except za.Eingabefehler as e:
        return Response(f"So geht es nicht: {e}", media_type="text/plain; charset=utf-8",
                        status_code=409)
    return Response(dokument, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="muster.pdf"'})


@router.post("/zahlungsanforderung/vorlage/logo", response_class=HTMLResponse)
async def vorlage_logo(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/zahlungsanforderung?meldung=Keine Berechtigung", status_code=303)
    form = await request.form()
    if form.get("aktion") == "entfernen":
        za.logo_entfernen()
        meldung = "Logo entfernt."
    else:
        datei = form.get("logo")
        daten = await datei.read(za.LOGO_HOECHSTENS + 1) if hasattr(datei, "read") else b""
        try:
            za.logo_speichern(daten)
        except za.Eingabefehler as e:
            return _vorlage_seite(request, fehler=str(e))
        meldung = "Logo gespeichert."
    return RedirectResponse("/zahlungsanforderung/vorlage?" + urlencode({"meldung": meldung}),
                            status_code=303)


@router.get("/zahlungsanforderung/vorlage/logo")
def vorlage_logo_zeigen(request: Request):
    pfad = za.logo_pfad()
    if not pfad:
        return Response(status_code=404)
    return Response(pfad.read_bytes(),
                    media_type="image/jpeg" if pfad.suffix == ".jpg" else "image/png")


@router.post("/zahlungsanforderung/vorlage/nummer", response_class=HTMLResponse)
async def vorlage_nummer(request: Request):
    """Die naechste Nummer des laufenden Kreises setzen."""
    if not _darf_verwalten(request):
        return RedirectResponse("/zahlungsanforderung?meldung=Keine Berechtigung", status_code=303)
    form = await request.form()
    try:
        za.naechste_setzen(form.get("naechste"))
    except za.Eingabefehler as e:
        return _vorlage_seite(request, fehler=str(e))
    meldung = f"Nächste Nummer: {za.naechste_nummer(config.laden())}"
    return RedirectResponse("/zahlungsanforderung/vorlage?" + urlencode({"meldung": meldung}),
                            status_code=303)
