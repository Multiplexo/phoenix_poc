"""Datenmodell der Planungsplattform (Briefing: Datenmodell Matrix + DTO, versionierte Forecast-Stände, Loop).

Übersicht (Details und Diagramm in docs/SPEZIFIKATION.md):
  Stammdaten     Artikel, MatrixVersion/MatrixEintrag (Artikel x Land -> Standort, quartalsweise gepflegt)
  Bewegungsdaten Auftragseingang (DTO), Bestand (Bestand/Transit/Intercompany je Standort), ImportLauf
  Parameter      Marktwachstum (global/Produktgruppe/Artikel, mit Beschluss), Projektmenge, AusreisserEntscheidung
  Forecast       ForecastLauf -> ArtikelForecast (Status, Freigaben) -> ForecastZeile (Standort x Monat, Brutto -> Netto)
  Loop           AccuracyWert (Forecast-Stand mit WBZ-Versatz gegen Ist), Signal (Ping), Protokoll
"""
from django.db import models


class Artikel(models.Model):
    nummer = models.CharField(max_length=40, unique=True)
    bezeichnung = models.CharField(max_length=200, blank=True)
    produktgruppe = models.CharField(max_length=60, blank=True)
    cluster = models.CharField(max_length=30, default="standard")
    cluster_quelle = models.CharField(max_length=20, default="stamm")  # stamm | planer
    wbz_monate = models.PositiveSmallIntegerField(null=True, blank=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["nummer"]

    def __str__(self):
        return self.nummer


class ImportLauf(models.Model):
    ARTEN = [("dto", "Auftragseingang (DTO)"), ("bestand", "Bestand / Transit / Intercompany"), ("matrix", "Matrix"),
             ("artikel", "Artikelstamm"), ("historie", "Forecast-Historie")]
    art = models.CharField(max_length=20, choices=ARTEN)
    quelle = models.CharField(max_length=20, default="datei")  # datei | rest
    dateiname = models.CharField(max_length=255, blank=True)
    stand = models.DateField(null=True, blank=True)  # Stichtag des Exports
    von = models.CharField(max_length=60)
    am = models.DateTimeField(auto_now_add=True)
    zeilen = models.IntegerField(default=0)
    meldungen = models.TextField(blank=True)

    class Meta:
        ordering = ["-am"]


class MatrixVersion(models.Model):
    bezeichnung = models.CharField(max_length=40)  # z. B. Q4/2026
    gueltig_ab = models.DateField()
    erstellt_von = models.CharField(max_length=60)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geprueft_von = models.CharField(max_length=60, blank=True)
    geprueft_am = models.DateTimeField(null=True, blank=True)
    notiz = models.TextField(blank=True)

    class Meta:
        ordering = ["-gueltig_ab", "-id"]


class MatrixEintrag(models.Model):
    version = models.ForeignKey(MatrixVersion, on_delete=models.CASCADE, related_name="eintraege")
    artikel = models.CharField(max_length=40, default="*")  # * = Standardregel für alle Artikel
    land = models.CharField(max_length=4)
    standort = models.CharField(max_length=60)

    class Meta:
        ordering = ["artikel", "land"]
        unique_together = [("version", "artikel", "land")]


class Auftragseingang(models.Model):
    datum = models.DateField(db_index=True)
    artikel = models.CharField(max_length=40, db_index=True)
    land = models.CharField(max_length=4, blank=True)
    kunde = models.CharField(max_length=80, blank=True)
    menge = models.FloatField()
    importlauf = models.ForeignKey(ImportLauf, on_delete=models.CASCADE, null=True)


class Bestand(models.Model):
    ARTEN = [("bestand", "Lagerbestand"), ("transit", "Transit"), ("intercompany", "Intercompany-Zulauf")]
    stichtag = models.DateField(db_index=True)
    artikel = models.CharField(max_length=40, db_index=True)
    standort = models.CharField(max_length=60)
    art = models.CharField(max_length=20, choices=ARTEN)
    menge = models.FloatField()
    importlauf = models.ForeignKey(ImportLauf, on_delete=models.CASCADE, null=True)


class Marktwachstum(models.Model):
    """Governance für Wachstumsfaktoren (Briefing: Market Evaluation Board, z. B. +10 %)."""
    EBENEN = [("global", "Global"), ("produktgruppe", "Produktgruppe"), ("artikel", "Artikel")]
    ebene = models.CharField(max_length=20, choices=EBENEN)
    schluessel = models.CharField(max_length=60, blank=True)  # Produktgruppe oder Artikelnummer
    wachstum_pa = models.FloatField()  # 0.10 = +10 % p. a.
    gueltig_ab = models.DateField()
    beschlossen_von = models.CharField(max_length=80, default="Market Evaluation Board")
    notiz = models.TextField(blank=True)
    erfasst_von = models.CharField(max_length=60)
    erfasst_am = models.DateTimeField(auto_now_add=True)
    aktiv = models.BooleanField(default=True)

    class Meta:
        ordering = ["ebene", "schluessel", "-gueltig_ab"]


class Projektmenge(models.Model):
    """Projektgebundene Zusatzmengen (Briefing: z. B. „Amazon +1000“)."""
    artikel = models.CharField(max_length=40, db_index=True)
    standort = models.CharField(max_length=60, blank=True)  # leer = anteilig nach Länderverteilung
    ab = models.DateField()  # erster Monat
    bis = models.DateField(null=True, blank=True)
    menge_pro_monat = models.FloatField()
    quelle = models.CharField(max_length=80, blank=True)
    notiz = models.TextField(blank=True)
    erfasst_von = models.CharField(max_length=60)
    erfasst_am = models.DateTimeField(auto_now_add=True)
    aktiv = models.BooleanField(default=True)


class AusreisserEntscheidung(models.Model):
    """Ausreißer werden nur geflaggt; bereinigt wird erst nach Entscheidung des Planers (Human-in-the-Loop)."""
    artikel = models.CharField(max_length=40, db_index=True)
    monat = models.DateField()
    entscheidung = models.CharField(max_length=20, choices=[("bereinigen", "Bereinigen"), ("behalten", "Behalten")])
    notiz = models.TextField(blank=True)
    von = models.CharField(max_length=60)
    am = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("artikel", "monat")]


class ForecastLauf(models.Model):
    ANLAESSE = [("manuell", "Manuell"), ("import", "Nach Import"), ("ping", "Nach Abweichung"), ("parameter", "Parameter geändert"),
                ("historie", "Historie (Excel)")]
    stichtag_monat = models.DateField()  # erster Monat des Forecasts
    anlass = models.CharField(max_length=20, choices=ANLAESSE)
    von = models.CharField(max_length=60)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    parameter = models.JSONField(default=dict)
    notiz = models.TextField(blank=True)

    class Meta:
        ordering = ["-erstellt_am", "-id"]


class ArtikelForecast(models.Model):
    STATUS = [("berechnet", "Forecast berechnet"), ("warte_freigabe", "Warte auf Freigabe"),
              ("freigegeben_1", "Freigegeben (Stufe 1)"), ("freigegeben", "Freigegeben"), ("abgelehnt", "Abgelehnt"),
              ("ersetzt", "Ersetzt")]
    lauf = models.ForeignKey(ForecastLauf, on_delete=models.CASCADE, related_name="artikel_forecasts")
    artikel = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS, default="berechnet")
    erklaerung = models.JSONField(default=dict)
    brutto_summe = models.FloatField(default=0)
    netto_summe = models.FloatField(default=0)
    freigabe1_von = models.CharField(max_length=60, blank=True)
    freigabe1_am = models.DateTimeField(null=True, blank=True)
    freigabe2_von = models.CharField(max_length=60, blank=True)
    freigabe2_am = models.DateTimeField(null=True, blank=True)
    kommentar = models.TextField(blank=True)

    class Meta:
        ordering = ["-lauf__erstellt_am", "-id"]
        unique_together = [("lauf", "artikel")]


class ForecastZeile(models.Model):
    af = models.ForeignKey(ArtikelForecast, on_delete=models.CASCADE, related_name="zeilen")
    standort = models.CharField(max_length=60, blank=True)  # leer = Artikelebene (Historie aus Excel)
    monat = models.DateField()
    stat = models.FloatField(default=0)
    wachstum = models.FloatField(default=0)
    projekt = models.FloatField(default=0)
    brutto = models.FloatField(default=0)
    abzug_bestand = models.FloatField(default=0)
    netto = models.FloatField(default=0)


class AccuracyWert(models.Model):
    """Freigegebener Forecast-Stand mit WBZ-Versatz gegen Ist, je Artikel und Monat (persistiert über die Zeit)."""
    artikel = models.CharField(max_length=40, db_index=True)
    monat = models.DateField()
    lag = models.PositiveSmallIntegerField()
    forecast = models.FloatField()
    stat = models.FloatField(null=True)
    ist = models.FloatField()
    af = models.ForeignKey(ArtikelForecast, on_delete=models.SET_NULL, null=True)
    berechnet_am = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("artikel", "monat", "lag")]


class Signal(models.Model):
    ARTEN = [("ping", "Abweichung kurzfristig"), ("abweichung", "Abweichung mit WBZ-Versatz"), ("ausreisser", "Ausreißer-Verdacht"),
             ("matrix", "Matrix")]
    artikel = models.CharField(max_length=40, db_index=True, blank=True)
    art = models.CharField(max_length=20, choices=ARTEN)
    text = models.TextField()
    details = models.JSONField(default=dict)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    offen = models.BooleanField(default=True)
    erledigt_von = models.CharField(max_length=60, blank=True)
    erledigt_am = models.DateTimeField(null=True, blank=True)
    neuer_vorschlag = models.ForeignKey(ArtikelForecast, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-erstellt_am"]


class Protokoll(models.Model):
    """Nachvollziehbarkeit: wer hat wann was geändert oder freigegeben."""
    am = models.DateTimeField(auto_now_add=True)
    von = models.CharField(max_length=60)
    objekt = models.CharField(max_length=80)
    aktion = models.CharField(max_length=80)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-am"]
