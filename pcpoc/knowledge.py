"""Planungswissen strukturieren.

Die Wissensbasis (knowledge.yaml) ist das eigentliche "Gedächtnis" des PoC: Regeln,
die heute nur in den Köpfen der Demand Planner stecken (Projektmengen, Abkündigungen,
Distributoren mit Lagerauffüllung, Wachstumsannahmen), jeweils mit Quelle und Datum.

Optional kann ein Sprachmodell Gesprächsnotizen aus den Planer-Terminen in
Regel-Vorschläge übersetzen. Wichtig:
  * Es werden nur die Notizen gesendet, keine SAP-Daten.
  * Vor dem Einsatz mit echten Notizen Freigabe durch Phoenix Contact (Datenschutz,
    Informationssicherheit) einholen.
  * Ergebnis sind VORSCHLÄGE. Ein Mensch prüft sie und übernimmt sie in knowledge.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "regeln": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "typ": {"type": "string", "enum": ["projekt", "eol", "lagerauffuellung", "marktwachstum", "sonstiges"]},
                    "artikel": {"type": "string", "description": "Artikelnummer, leer wenn nicht genannt"},
                    "kunde": {"type": "string", "description": "Kunde/Distributor, leer wenn nicht genannt"},
                    "produktgruppe": {"type": "string"},
                    "ab": {"type": "string", "description": "YYYY-MM, leer wenn unbekannt"},
                    "menge_pro_monat": {"type": "number", "description": "0 wenn keine Menge genannt"},
                    "faktor_pa": {"type": "number", "description": "z. B. 0.1 für +10 % p. a., 0 wenn nicht genannt"},
                    "notiz": {"type": "string", "description": "Regel in einem Satz, auf Deutsch"},
                    "zitat": {"type": "string", "description": "wörtliche Stelle aus den Notizen, auf die sich die Regel stützt"},
                    "unsicher": {"type": "boolean", "description": "true, wenn die Notiz mehrdeutig ist und nachgefragt werden muss"},
                },
                "required": ["typ", "artikel", "kunde", "produktgruppe", "ab", "menge_pro_monat", "faktor_pa",
                             "notiz", "zitat", "unsicher"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["regeln"],
    "additionalProperties": False,
}

SYSTEM = (
    "Du hilfst, das Erfahrungswissen von Demand Plannern in der Bedarfsplanung zu strukturieren. "
    "Du bekommst Gesprächsnotizen. Extrahiere daraus nur Regeln, die tatsächlich in den Notizen stehen: "
    "Projektmengen (typ projekt), Abkündigungen (eol), Kunden/Distributoren mit unregelmäßiger Lagerauffüllung "
    "(lagerauffuellung), Wachstumsannahmen (marktwachstum) oder sonstige Planungsregeln. Erfinde keine Werte. "
    "Was nicht genannt ist, bleibt leer bzw. 0. Belege jede Regel mit einem wörtlichen Zitat. "
    "Markiere mehrdeutige Aussagen mit unsicher=true."
)


def extract_rules(notes: str, model: str = "claude-opus-5-5") -> list[dict]:
    import anthropic  # optional dependency

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RULE_SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": f"<notizen>\n{notes}\n</notizen>"}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Anfrage wurde vom Modell abgelehnt")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Antwort abgeschnitten (max_tokens)")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["regeln"]


def to_yaml_proposals(rules: list[dict], source: str, erfasst_am: str, erfasst_von: str) -> str:
    out = []
    for i, r in enumerate(rules, 1):
        clean = {k: v for k, v in r.items() if v not in ("", 0, 0.0, None) or k == "unsicher"}
        clean = {"id": f"V-{i:03d}", **clean, "quelle": source, "erfasst_am": erfasst_am, "erfasst_von": erfasst_von,
                 "status": "vorschlag"}
        out.append(clean)
    return ("# VORSCHLÄGE aus Gesprächsnotizen. Prüfen, korrigieren und erst dann nach knowledge.yaml übernehmen.\n"
            + yaml.safe_dump({"regeln": out}, allow_unicode=True, sort_keys=False))


def extract_file(notes_path: str | Path, out_path: str | Path, source: str, erfasst_am: str, erfasst_von: str,
                 model: str = "claude-opus-5-5") -> Path:
    rules = extract_rules(Path(notes_path).read_text(encoding="utf-8"), model=model)
    p = Path(out_path)
    p.write_text(to_yaml_proposals(rules, source, erfasst_am, erfasst_von), encoding="utf-8")
    return p
