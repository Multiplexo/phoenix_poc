"""Pilot „Kontext lesen“: Dokumente einlesen, Ereignisse extrahieren, prüfen, übernehmen und gegen Forecast-Fehler messen.

Ablauf
  1. Upload (Protokoll, Notiz, CRM, Excel-Kommentar, freigegebene Mail) -> Text auslesen und pseudonymisieren
  2. Extraktion: Claude (wenn ANTHROPIC_API_KEY gesetzt) mit Pflicht zum wörtlichen Zitat; sonst Regel-Fallback
  3. Jedes Zitat wird gegen den Dokumenttext geprüft (keine erfundenen Belege)
  4. Prüf-Warteschlange: Planer bestätigt, korrigiert oder lehnt ab
  5. Bestätigte Ereignisse werden zu Projektmenge, Abkündigung oder Distributor-Muster
  6. Messung: Abdeckung großer Forecast-Fehler, Vorwarnzeit, Treffsicherheit der Extraktion

KI-Zugang: Langdock (EU) oder Anthropic direkt, siehe ki_anbieter().

Datenschutz: Mails nur, wenn DOKUMENTE_MAILS_ERLAUBT=1 (Freigabe Datenschutz/Betriebsrat). E-Mail-Adressen und
Telefonnummern werden vor dem Speichern und vor jeder Übertragung entfernt; gespeichert wird nur der bereinigte Text.
"""
from __future__ import annotations

import datetime as dt
import email
import email.policy
import io
import json
import os
import re
import zipfile
from email.utils import parsedate_to_datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Abkuendigung, AccuracyWert, Artikel, Dokument, Ereignis, Projektmenge, Zuordnung

MODELL = "claude-opus-5-5"
MAX_ZEICHEN = 400_000
RICHTUNG = {"projekt": 1, "nachfrage_steigt": 1, "lagerauffuellung": 1, "abkuendigung": -1, "nachfrage_sinkt": -1,
            "lieferproblem": 0, "preis": 0, "sonstiges": 0}


class DokumentFehler(Exception):
    pass


# ---------------------------------------------------------------- Text auslesen
def pseudonymisieren(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[E-Mail]", text)
    text = re.sub(r"(?<!\w)(\+?\d[\d /()-]{7,}\d)(?!\w)", lambda m: "[Telefon]" if sum(c.isdigit() for c in m.group(1)) >= 8 else m.group(1), text)
    return text


def text_auslesen(name: str, daten: bytes) -> tuple[str, dt.date | None, str]:
    """Liefert (Text, Datum aus der Datei falls vorhanden, Titel-Vorschlag)."""
    endung = os.path.splitext(name.lower())[1]
    datum, titel = None, os.path.splitext(name)[0]
    if endung in (".txt", ".md", ".csv"):
        text = daten.decode("utf-8", errors="replace")
    elif endung == ".eml":
        msg = email.message_from_bytes(daten, policy=email.policy.default)
        titel = str(msg.get("subject") or titel)
        try:
            datum = parsedate_to_datetime(msg.get("date")).date() if msg.get("date") else None
        except (TypeError, ValueError):
            datum = None
        body = msg.get_body(preferencelist=("plain", "html"))
        inhalt = body.get_content() if body else ""
        if body is not None and body.get_content_type() == "text/html":
            inhalt = re.sub(r"<[^>]+>", " ", inhalt)
        # Absender/Empfänger bewusst nicht übernehmen (Datenminimierung)
        text = f"Betreff: {titel}\n\n{inhalt}"
    elif endung == ".docx":
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", xml)
    elif endung == ".pdf":
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(daten)).pages)
    elif endung in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(daten), data_only=True)
        teile = []
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.comment:
                        teile.append(f"[{ws.title}!{c.coordinate}] Kommentar: {c.comment.text}")
                    elif isinstance(c.value, str) and len(c.value) > 25:
                        teile.append(f"[{ws.title}!{c.coordinate}] {c.value}")
        text = "\n".join(teile)
    else:
        raise DokumentFehler(f"Dateityp {endung or '?'} wird nicht unterstützt (txt, md, eml, docx, pdf, xlsx).")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        raise DokumentFehler("Im Dokument wurde kein Text gefunden.")
    if len(text) > MAX_ZEICHEN:
        raise DokumentFehler(f"Dokument zu groß ({len(text):,} Zeichen). Bitte aufteilen.".replace(",", "."))
    return pseudonymisieren(text), datum, titel[:200]


def mails_erlaubt() -> bool:
    return os.environ.get("DOKUMENTE_MAILS_ERLAUBT", "0").strip().lower() in ("1", "true", "ja", "on")


def ki_anbieter() -> str | None:
    """Welcher KI-Zugang genutzt wird.

    KI_ANBIETER=langdock   Langdock (EU-Hosting, Anthropic-kompatible Messages-API); LANGDOCK_API_KEY,
                           LANGDOCK_BASE_URL (Standard https://api.langdock.com/anthropic/eu), LANGDOCK_MODELL
    KI_ANBIETER=anthropic  direkt bei Anthropic; ANTHROPIC_API_KEY
    ohne Angabe            Langdock, wenn LANGDOCK_API_KEY gesetzt ist, sonst Anthropic, wenn ANTHROPIC_API_KEY gesetzt ist
    KI_EXTRAKTION=aus      KI abschalten (Regel-Fallback)
    """
    if os.environ.get("KI_EXTRAKTION", "auto") == "aus":
        return None
    wahl = os.environ.get("KI_ANBIETER", "").strip().lower()
    if wahl == "langdock" or (not wahl and os.environ.get("LANGDOCK_API_KEY")):
        return "langdock" if os.environ.get("LANGDOCK_API_KEY") else None
    if wahl in ("anthropic", "") and os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def ki_verfuegbar() -> bool:
    return ki_anbieter() is not None


def ki_modell() -> str:
    if ki_anbieter() == "langdock":
        return os.environ.get("LANGDOCK_MODELL", MODELL)
    return MODELL


def anlegen(name: str, daten: bytes, quelle: str, von: str, datum: dt.date | None = None, titel: str = "",
            artikel_hinweis: str = "") -> Dokument:
    if (quelle == "mail" or name.lower().endswith(".eml")) and not mails_erlaubt():
        raise DokumentFehler("E-Mails sind gesperrt, bis Datenschutz und Betriebsrat zugestimmt haben (DOKUMENTE_MAILS_ERLAUBT).")
    text, datum_datei, titel_datei = text_auslesen(name, daten)
    d = datum or datum_datei
    if d is None:
        raise DokumentFehler("Bitte das Datum des Dokuments angeben (ab wann die Information bekannt war).")
    return Dokument.objects.create(titel=titel or titel_datei, quelle=quelle, dateiname=name, datum=d, text=text,
                                   artikel_hinweis=artikel_hinweis, hochgeladen_von=von)


# ---------------------------------------------------------------- Extraktion
SCHEMA = {
    "type": "object",
    "properties": {"ereignisse": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "artikel": {"type": "string", "description": "Artikelnummer aus der Liste; leer, wenn nicht eindeutig zuordenbar"},
            "typ": {"type": "string", "enum": [t for t, _ in Ereignis.TYPEN]},
            "richtung": {"type": "integer", "enum": [-1, 0, 1], "description": "+1 mehr Bedarf, -1 weniger, 0 unklar"},
            "menge_pro_monat": {"type": "number", "description": "Stück pro Monat; 0 wenn nicht genannt"},
            "ab": {"type": "string", "description": "YYYY-MM, ab wann es wirkt; leer wenn nicht genannt"},
            "bis": {"type": "string", "description": "YYYY-MM oder leer"},
            "kunde": {"type": "string", "description": "Kunde/Distributor/Projekt, leer wenn nicht genannt"},
            "zitat": {"type": "string", "description": "wörtliche, unveränderte Stelle aus dem Dokument"},
            "begruendung": {"type": "string", "description": "ein Satz: warum das für die Bedarfsplanung relevant ist"},
            "konfidenz": {"type": "number", "description": "0 bis 1"},
        },
        "required": ["artikel", "typ", "richtung", "menge_pro_monat", "ab", "bis", "kunde", "zitat", "begruendung", "konfidenz"],
        "additionalProperties": False}}},
    "required": ["ereignisse"],
    "additionalProperties": False,
}

SYSTEM = """Du unterstützt die Bedarfsplanung eines Herstellers von Stromversorgungen.
Du liest ein Dokument (Protokoll, Gesprächsnotiz, CRM-Notiz, Excel-Kommentar oder E-Mail) und findest darin Ereignisse,
die den künftigen Auftragseingang einzelner Artikel verändern: Projektmengen, Abkündigungen, Lagerauffüllungen von
Distributoren, steigende oder sinkende Nachfrage, Lieferprobleme, Preisänderungen.

Regeln:
- Nur Ereignisse, die tatsächlich im Dokument stehen. Nichts ergänzen, nichts schätzen, was nicht genannt ist.
- Jedes Ereignis braucht ein wörtliches Zitat aus dem Dokument, Zeichen für Zeichen unverändert.
- Artikel nur zuordnen, wenn die Nummer genannt ist oder ein Begriff eindeutig über die Zuordnungsliste passt; sonst leer lassen.
- Mengen nur übernehmen, wenn sie genannt sind; Angaben pro Jahr oder Quartal in Stück pro Monat umrechnen.
- Zeitangaben relativ zum Dokumentdatum auflösen (z. B. „ab nächstem Quartal“).
- Konfidenz niedrig, wenn die Aussage vage oder unbestätigt ist („im Gespräch“, „evtl.“).
- Allgemeine Aussagen ohne Bezug zum Bedarf ignorieren."""


def _kontext() -> str:
    arts = "\n".join(f"{a.nummer}: {a.bezeichnung} ({a.produktgruppe}, {a.cluster})" for a in Artikel.objects.filter(aktiv=True))
    zu = "\n".join(f"{z.get_art_display()} „{z.begriff}“ -> {z.artikel}" for z in Zuordnung.objects.all()) or "(keine)"
    return f"<artikel>\n{arts}\n</artikel>\n<zuordnungsliste>\n{zu}\n</zuordnungsliste>"


def _dokument_nachricht(doc: Dokument) -> str:
    return f"<dokument datum=\"{doc.datum}\" quelle=\"{doc.get_quelle_display()}\" titel=\"{doc.titel}\">\n{doc.text}\n</dokument>"


def extrahiere_ki(doc: Dokument) -> list[dict]:
    if ki_anbieter() == "langdock":
        return extrahiere_langdock(doc)
    import anthropic

    client = anthropic.Anthropic(timeout=float(os.environ.get("KI_TIMEOUT", "180")), max_retries=1)
    resp = client.beta.messages.create(
        model=MODELL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=[{"type": "text", "text": SYSTEM}, {"type": "text", "text": _kontext(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": _dokument_nachricht(doc)}],
    )
    if resp.stop_reason == "refusal":
        raise DokumentFehler("Das Modell hat die Auswertung abgelehnt.")
    if resp.stop_reason == "max_tokens":
        raise DokumentFehler("Antwort abgeschnitten; Dokument aufteilen.")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["ereignisse"]


def extrahiere_langdock(doc: Dokument) -> list[dict]:
    """Langdock: Anthropic-kompatible Messages-API in der EU. Bewusst nur Grundfunktionen (keine Beta-Header, kein
    output_config), weil nicht jede Funktion über den Gateway verfügbar ist; das JSON-Format wird im Prompt verlangt
    und hier geprüft. Endpunkt, Authentifizierung und Modellname vor dem ersten Einsatz mit der Langdock-Doku abgleichen."""
    import anthropic

    client = anthropic.Anthropic(api_key=None, auth_token=os.environ["LANGDOCK_API_KEY"],
                                 base_url=os.environ.get("LANGDOCK_BASE_URL", "https://api.langdock.com/anthropic/eu"),
                                 timeout=float(os.environ.get("KI_TIMEOUT", "180")), max_retries=1)
    format_hinweis = ("Antworte ausschließlich mit einem JSON-Objekt nach diesem Schema, ohne weiteren Text:\n"
                      + json.dumps(SCHEMA, ensure_ascii=False))
    resp = client.messages.create(
        model=ki_modell(),
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM + "\n\n" + format_hinweis}, {"type": "text", "text": _kontext()}],
        messages=[{"role": "user", "content": _dokument_nachricht(doc)}],
    )
    if resp.stop_reason == "refusal":
        raise DokumentFehler("Das Modell hat die Auswertung abgelehnt.")
    if resp.stop_reason == "max_tokens":
        raise DokumentFehler("Antwort abgeschnitten; Dokument aufteilen.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _json_ereignisse(text)


def _json_ereignisse(text: str) -> list[dict]:
    """JSON aus einer Modellantwort lesen (auch mit Code-Zaun) und die Felder auf das Schema bringen."""
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, ende = t.find("{"), t.rfind("}")
    if start < 0 or ende < 0:
        raise DokumentFehler("Antwort enthielt kein JSON.")
    try:
        daten = json.loads(t[start:ende + 1])
    except json.JSONDecodeError as e:
        raise DokumentFehler(f"Antwort war kein gültiges JSON: {e}") from e
    felder = SCHEMA["properties"]["ereignisse"]["items"]["required"]
    out = []
    for e in daten.get("ereignisse", []):
        if not isinstance(e, dict) or e.get("typ") not in RICHTUNG:
            continue
        out.append({k: e.get(k, 0 if k in ("richtung", "menge_pro_monat", "konfidenz") else "") for k in felder})
    return out


MONATE = {m: i + 1 for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september",
                                           "oktober", "november", "dezember"])}
REGELN = [("abkuendigung", r"abkündig|auslauf|läuft aus|end of life|eol\b|nachfolger"),
          ("lagerauffuellung", r"lager(auffüllung|aufbau)|auf vorrat|bevorrat"),
          ("projekt", r"projekt|rollout|ausbaustufe|rahmenvertrag|zusätzlich"),
          ("lieferproblem", r"lieferprobl|engpass|lieferverzug|allokation"),
          ("nachfrage_steigt", r"mehr bedarf|steigt|anstieg|wechseln zu uns|zieht an|höhere abrufe"),
          ("nachfrage_sinkt", r"weniger bedarf|sinkt|rückgang|storniert|bricht ein"),
          ("preis", r"preiserhöhung|preissenkung|preisanpassung")]


def extrahiere_regeln(doc: Dokument) -> list[dict]:
    """Einfacher Regel-Fallback ohne KI, nur für Demo und Notbetrieb: Schlüsselwörter je Satz, Artikel/Menge/Zeitpunkt
    aus dem ganzen Dokument. Versteht keine Zusammenhänge; echte Dokumente brauchen die KI-Extraktion."""
    text = doc.text
    low_doc = text.lower()
    zu = [(z.begriff.lower(), z.artikel_liste()) for z in Zuordnung.objects.all()]
    arts_doc = list(dict.fromkeys(re.findall(r"\b[A-Z]-\d{4}\b", text)))
    if not arts_doc:
        arts_doc = [a for b, liste in zu if b in low_doc for a in liste]
    if not arts_doc and doc.artikel_hinweis:
        arts_doc = [a.strip() for a in doc.artikel_hinweis.split(",") if a.strip()]
    def menge_in(t):
        m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*(?:stk|stück)([^.]{0,25})", t)
        if not m:
            return None
        v = float(m.group(1).replace(".", ""))
        return round(v / 12) if re.search(r"(pro|im|je)\s+jahr|jährlich", m.group(2)) else v

    def ab_in(t):
        m = re.search(r"ab\s+(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+(\d{4})", t)
        return f"{m.group(2)}-{MONATE[m.group(1)]:02d}" if m else ""

    menge, ab = menge_in(low_doc), ab_in(low_doc)
    kunde = ""
    m = re.search(r"(distributor-\w+|rechenzentrumskunde \w+|hyperscaler)", text, re.I)
    if m:
        kunde = m.group(1)
    out, gesehen = [], set()
    for satz in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])|\n+", text):
        s = satz.strip()
        if len(s) < 15:
            continue
        typ = next((t for t, rx in REGELN if re.search(rx, s.lower())), None)
        if not typ:
            continue
        arts = re.findall(r"\b[A-Z]-\d{4}\b", s) or arts_doc or [""]
        for a in arts:
            if (typ, a) in gesehen:
                continue
            gesehen.add((typ, a))
            s_menge, s_ab = menge_in(s.lower()), ab_in(s.lower())  # Satz zuerst, sonst Dokument
            out.append(dict(artikel=a, typ=typ, richtung=RICHTUNG[typ], menge_pro_monat=(s_menge or menge or 0) if typ == "projekt" else 0,
                            ab=(s_ab or ab) if typ in ("projekt", "abkuendigung") else "", bis="", kunde=kunde, zitat=s,
                            begruendung="Regel-Fallback: Schlüsselwort gefunden", konfidenz=0.45 if a else 0.2))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower().replace("„", '"').replace("“", '"').replace("”", '"')


def _monat(s: str) -> dt.date | None:
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{1,2})", s)
    return dt.date(int(m.group(1)), int(m.group(2)), 1) if m else None


@transaction.atomic
def auswerten(doc: Dokument, ki: bool = True) -> int:
    """Extrahiert Ereignisse (KI oder Fallback), prüft Zitate, legt Vorschläge an. Liefert Anzahl Vorschläge."""
    doc.ereignisse.filter(status="vorschlag").delete()
    try:
        if ki and ki_verfuegbar():
            roh, verfahren = extrahiere_ki(doc), f"{ki_anbieter()}: {ki_modell()}"
        else:
            roh, verfahren = extrahiere_regeln(doc), "regel-fallback (ohne KI)"
    except Exception as e:
        doc.status, doc.meldung = "fehler", str(e)[:1000]
        doc.save()
        raise
    bekannt = set(Artikel.objects.values_list("nummer", flat=True))
    text_n = _norm(doc.text)
    n = 0
    for e in roh:
        if e.get("typ") not in RICHTUNG:
            continue
        art = e.get("artikel", "").strip()
        if art and art not in bekannt:
            art = ""
        zitat = e.get("zitat", "").strip()
        geprueft = bool(zitat) and _norm(zitat) in text_n
        konf = float(e.get("konfidenz") or 0.5)
        if not geprueft:
            konf = min(konf, 0.2)  # Beleg nicht wörtlich im Dokument -> kaum belastbar
        Ereignis.objects.create(dokument=doc, artikel=art, typ=e["typ"], richtung=int(e.get("richtung") or 0),
                                menge_pro_monat=float(e["menge_pro_monat"]) if e.get("menge_pro_monat") else None,
                                ab=_monat(e.get("ab", "")), bis=_monat(e.get("bis", "")), kunde=e.get("kunde", "")[:120],
                                bekannt_seit=doc.datum, zitat=zitat, zitat_geprueft=geprueft, begruendung=e.get("begruendung", ""),
                                konfidenz=konf, original=e)
        n += 1
    doc.status, doc.verfahren, doc.ausgewertet_am = "fertig", verfahren, timezone.now()
    doc.meldung = f"{n} Ereignisse vorgeschlagen" + ("" if verfahren != "regel-fallback (ohne KI)" else " (Regel-Fallback, ohne KI)")
    doc.save()
    return n


# ---------------------------------------------------------------- Prüfung und Übernahme
FELDER = ("artikel", "typ", "richtung", "menge_pro_monat", "ab", "bis")


@transaction.atomic
def pruefen(ev: Ereignis, aktion: str, von: str, korrektur: dict | None = None) -> Ereignis:
    from . import services
    if aktion == "ablehnen":
        ev.status = "abgelehnt"
    elif aktion == "bestaetigen":
        geaendert = False
        for k, v in (korrektur or {}).items():
            if k not in FELDER or v in (None, ""):
                continue
            if k in ("ab", "bis") and isinstance(v, str):
                v = _monat(v)
            elif k == "menge_pro_monat":
                v = float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) else float(v)
            elif k == "richtung":
                v = int(v)
            if getattr(ev, k) != v:
                setattr(ev, k, v)
                geaendert = True
        if not ev.artikel:
            raise DokumentFehler("Zum Bestätigen muss ein Artikel zugeordnet sein.")
        ev.status = "korrigiert" if geaendert else "bestaetigt"
        ev.uebernommen = _uebernehmen(ev, von)
    else:
        raise DokumentFehler("Unbekannte Aktion")
    ev.geprueft_von, ev.geprueft_am = von, timezone.now()
    ev.save()
    services.protokoll(von, f"Ereignis {ev.id} ({ev.artikel})", ev.get_status_display(), ev.zitat[:200])
    if ev.status != "abgelehnt" and ev.typ in ("projekt", "abkuendigung"):
        services.forecast_lauf(von, "parameter", [ev.artikel], notiz=f"Ereignis aus Dokument „{ev.dokument.titel}“ übernommen")
    return ev


def _uebernehmen(ev: Ereignis, von: str) -> str:
    quelle = f"Dokument: {ev.dokument.titel} ({ev.dokument.datum:%d.%m.%Y})"
    from . import services
    sm = services.stichtag_monat()
    if ev.typ == "projekt" and ev.ab and sm is not None and ev.ab < services.monat(sm):
        return "Kontext (Projekt bereits gestartet, steckt im Auftragseingang)"
    if ev.typ == "projekt" and ev.menge_pro_monat and ev.ab:
        p = Projektmenge.objects.create(artikel=ev.artikel, ab=ev.ab, bis=ev.bis, menge_pro_monat=ev.menge_pro_monat,
                                        quelle=quelle[:80], notiz=ev.zitat[:500], erfasst_von=von)
        return f"Projektmenge {p.id}"
    if ev.typ == "abkuendigung" and ev.ab:
        a = Abkuendigung.objects.create(artikel=ev.artikel, ab=ev.ab, quelle=quelle[:200], erfasst_von=von)
        return f"Abkündigung {a.id}"
    if ev.typ == "lagerauffuellung":
        return "Distributor-Muster (Wissensregel)"
    return "Kontext-Ereignis"


# ---------------------------------------------------------------- Messung
def grosse_fehler(schwelle: float = 0.3, min_stueck: float = 100) -> list[AccuracyWert]:
    out = []
    for v in AccuracyWert.objects.all():
        if v.ist <= 0 and v.forecast <= 0:
            continue
        diff = v.ist - v.forecast
        if abs(diff) >= min_stueck and abs(diff) / max(v.ist, v.forecast, 1) >= schwelle:
            out.append(v)
    return out


def messung(schwelle: float = 0.3, min_stueck: float = 100, fenster_monate: int = 12) -> dict:
    fehler = grosse_fehler(schwelle, min_stueck)
    evs = list(Ereignis.objects.filter(status__in=("bestaetigt", "korrigiert")).exclude(artikel=""))
    je_artikel = {}
    for e in evs:
        je_artikel.setdefault(e.artikel, []).append(e)
    faelle = []
    for v in fehler:
        richtung = 1 if v.ist > v.forecast else -1
        fc_abgabe = _monat_minus(v.monat, v.lag)
        passend = [e for e in je_artikel.get(v.artikel, [])
                   if e.bekannt_seit < v.monat and e.bekannt_seit >= _monat_minus(v.monat, fenster_monate)
                   and (e.richtung == richtung)]
        best = min(passend, key=lambda e: e.bekannt_seit) if passend else None
        vorwarn = _monate_zwischen(best.bekannt_seit, v.monat) if best else None
        faelle.append(dict(wert=v, richtung=richtung, ereignis=best, vorwarnzeit=vorwarn,
                           vor_abgabe=bool(best and best.bekannt_seit <= fc_abgabe), fc_abgabe=fc_abgabe,
                           abweichung=(v.ist - v.forecast) / max(v.forecast, 1)))
    abgedeckt = [f for f in faelle if f["ereignis"]]
    geprueft = Ereignis.objects.exclude(status="vorschlag")
    n_g = geprueft.count()
    je_typ = []
    for t, name in Ereignis.TYPEN:
        g = geprueft.filter(typ=t)
        if not g.exists():
            continue
        treffer = [f for f in abgedeckt if f["ereignis"].typ == t]
        je_typ.append(dict(typ=name, geprueft=g.count(), bestaetigt=g.filter(status__in=("bestaetigt", "korrigiert")).count(),
                           faelle=len(treffer), vorwarnzeit=_mittel([f["vorwarnzeit"] for f in treffer])))
    return dict(
        faelle=sorted(faelle, key=lambda f: (f["ereignis"] is None, f["wert"].artikel, f["wert"].monat)),
        n_fehler=len(faelle), n_abgedeckt=len(abgedeckt),
        abdeckung=len(abgedeckt) / len(faelle) if faelle else None,
        vor_abgabe=sum(1 for f in abgedeckt if f["vor_abgabe"]) / len(faelle) if faelle else None,
        vorwarnzeit=_mittel([f["vorwarnzeit"] for f in abgedeckt]),
        n_geprueft=n_g,
        treffsicherheit=geprueft.filter(status__in=("bestaetigt", "korrigiert")).count() / n_g if n_g else None,
        exakt=geprueft.filter(status="bestaetigt").count() / n_g if n_g else None,
        zitat_ok=Ereignis.objects.filter(zitat_geprueft=True).count() / Ereignis.objects.count() if Ereignis.objects.exists() else None,
        je_typ=je_typ, schwelle=schwelle, min_stueck=min_stueck)


def _monat_minus(d: dt.date, n: int) -> dt.date:
    y, m = d.year, d.month - n
    while m <= 0:
        m += 12
        y -= 1
    return dt.date(y, m, 1)


def _monate_zwischen(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _mittel(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None
