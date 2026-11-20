"""Synthetische Beispieldokumente passend zu den eingebauten Mustern der Demo-Daten (pcpoc.synth).

Bewusst gemischt: Manche Ursachen stehen rechtzeitig in Dokumenten, manche gar nicht, ein Dokument ist ohne
Artikelbezug, eines irrelevant. So zeigt die Messung Abdeckung, Vorwarnzeit und Treffsicherheit mit Lücken,
wie sie auch mit echten Dokumenten zu erwarten sind. Die Zahlen sagen nichts über Phoenix Contact aus.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

MONATSNAME = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _m(p: pd.Period) -> str:
    return f"{MONATSNAME[p.month - 1]} {p.year}"


def _d(p: pd.Period, tag: int = 12) -> dt.date:
    return dt.date(p.year, p.month, min(tag, 28))


def dokumente(truth: dict, start: pd.Period) -> list[dict]:
    """Liefert Dokumente als dict(titel, quelle, datum, text, artikel_hinweis)."""
    docs = []
    hyp = [a for a, m in truth.items() if m.get("cluster") == "hyperscaler"]
    for n, a in enumerate(hyp[:3]):
        k = start + int(truth[a]["kstart"])
        menge = int(round(float(truth[a]["P"]), -1))
        if n == 2:  # ohne Artikelnummer, nur über die Zuordnungsliste erkennbar
            text = (f"Gesprächsnotiz Key Account, Termin beim Kunden Rechenzentrumskunde Nord.\n"
                    f"Der Kunde bestätigt den Rollout der neuen Racks. Für die Stromversorgung rechnen sie mit "
                    f"zusätzlich ca. {menge * 12:,} Stück im Jahr, Projekt ab {_m(k)}. Vertrag liegt beim Einkauf zur Unterschrift.".replace(",", "."))
            docs.append(dict(titel="Key Account: Rechenzentrumskunde Nord", quelle="notiz", datum=_d(k - 4), text=text, artikel_hinweis=""))
        else:
            text = (f"CRM-Notiz Vertrieb. Hyperscaler-Projekt für {a}: Der Kunde plant einen Rollout in mehreren Ausbaustufen. "
                    f"Erwartet werden ca. {menge:,} Stück pro Monat ab {_m(k)}. Start abhängig von der Freigabe des Standorts.".replace(",", "."))
            docs.append(dict(titel=f"CRM: Hyperscaler-Projekt {a}", quelle="crm", datum=_d(k - 5), text=text, artikel_hinweis=""))
    peaks = [(a, m["peak"]) for a, m in truth.items() if m.get("peak")]
    for n, (a, pk) in enumerate(peaks):
        if n % 2:  # nur jeder zweite Peak wurde vorher dokumentiert
            continue
        p = start + int(pk["i"])
        text = (f"CRM-Notiz. Distributor-{pk['country']} meldet für {a} eine einmalige Lagerauffüllung "
                f"von ca. {int(pk['qty']):,} Stück im {_m(p)}. Danach wieder normale Abrufe.".replace(",", "."))
        docs.append(dict(titel=f"CRM: Distributor-{pk['country']} Lageraufbau", quelle="crm", datum=_d(p - 2), text=text, artikel_hinweis=""))
    eol = [a for a, m in truth.items() if m.get("cluster") == "ramp_down"]
    for a in eol[:3]:
        k = start + int(truth[a]["kstart"])
        text = (f"Protokoll Produktmanagement. {a} läuft aus, der Nachfolger übernimmt schrittweise. "
                f"Abkündigung: ab {_m(k + 12)} kein Bedarf mehr. Vertrieb informiert die Kunden über die Umstellung.")
        docs.append(dict(titel=f"PM-Protokoll: Auslauf {a}", quelle="protokoll", datum=_d(k - 1), text=text, artikel_hinweis=""))
    schub = [a for a, m in truth.items() if m.get("schub_laufender_monat")]
    if schub:
        letzt = start + 35
        text = ("Vertriebsrunde Oktober. Ein Wettbewerber ist seit Wochen lieferunfähig, mehrere Kunden wechseln zu uns. "
                + " ".join(f"Bei {a} steigt die Nachfrage deutlich, höhere Abrufe ab November erwartet." for a in schub))
        docs.append(dict(titel="Protokoll Vertriebsrunde Oktober", quelle="protokoll", datum=_d(letzt, 24), text=text, artikel_hinweis=""))
    docs.append(dict(titel="MEB-Protokoll September", quelle="protokoll", datum=_d(start + 34, 30),
                     text="Market Evaluation Board. Für die Produktgruppe PG-C erwarten wir 2027 ein Marktwachstum von etwa 10 %. "
                          "Treiber sind Investitionen in Ladeinfrastruktur. Der Anstieg betrifft alle Artikel der Gruppe.",
                     artikel_hinweis=""))
    docs.append(dict(titel="Notiz Messeplanung", quelle="notiz", datum=_d(start + 33, 5),
                     text="Messeplanung 2027: Standfläche steigt um 20 %, Budget ist freigegeben. Keine Auswirkung auf die Planung der Artikel.",
                     artikel_hinweis=""))
    return docs


ZUORDNUNGEN = [dict(begriff="Rechenzentrumskunde Nord", art="kunde", notiz="Beispiel: Kunde → Artikel")]
