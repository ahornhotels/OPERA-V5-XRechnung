"""Seiten der Zahlungsanforderung (app/zahlungsanforderung.py).

Eingebunden am Ende von app/main.py. Ablauf: Kunde suchen, Angaben
eintragen, pruefen, senden."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import config, mailer
from . import zahlungsanforderung as za
from .main import _darf_verwalten, _kontext, seiten

router = APIRouter()

FELDER = ("nummer", "brutto_7", "brutto_19", "grund", "faellig", "von", "bis", "referenz",
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
    except Exception:
        liste = []
    return seiten.TemplateResponse(request, "zahlungsanforderung.html", _kontext(
        request, suche=suche, treffer=treffer, kunde=kunde, name_id=name_id, werte=werte,
        vorschau=vorschau, meldung=meldung, fehler=fehler, liste=liste,
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
        dokument = za.pdf(cfg, eingabe, k, h)
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
        ergebnis = za.versenden(config.laden(), werte, name_id or 0, request.state.benutzer,
                                mit_mail=werte["aktion"] != "ablegen")
    except Exception as e:
        return _seite(request, name_id=name_id, werte=werte, fehler=str(e))
    nummer = werte.get("nummer", "").strip()
    meldung = {"testlauf": f"Testlauf aktiv — die Zahlungsanforderung {nummer} wurde geprüft, "
                           "aber weder abgelegt noch versendet.",
               "abgelegt": f"Zahlungsanforderung {nummer} abgelegt (nicht versendet).",
               }.get(ergebnis, f"Zahlungsanforderung {nummer} versendet.")
    return RedirectResponse("/zahlungsanforderung?" + urlencode({"meldung": meldung}),
                            status_code=303)


@router.get("/zahlungsanforderung/ablage/{nummer}.pdf")
def ablage(request: Request, nummer: str):
    satz = za.satz_lesen(nummer) if za.NUMMER_MUSTER.match(nummer or "") else None
    pfad = Path(satz["pdf_pfad"]) if satz and satz.get("pdf_pfad") else None
    if not pfad or not pfad.is_file():
        return Response("Nicht in der Ablage.", media_type="text/plain; charset=utf-8",
                        status_code=404)
    return Response(pfad.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{pfad.name}"'})
