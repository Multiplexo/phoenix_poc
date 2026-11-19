"""Basic Auth für die ganze Plattform, mehrbenutzerfähig.

  BASIC_AUTH_USER / BASIC_AUTH_PASSWORD   ein Zugang (wie bisher)
  BASIC_AUTH_USERS                        weitere Zugänge "name:passwort;name2:passwort2" (bis ~10 Planer)

Der angemeldete Name wird an Freigaben und Änderungen geschrieben (request.planer).
Ohne konfigurierte Zugänge liefert die Plattform nichts aus (fail closed); lokal mit DJANGO_DEBUG=1 offen.
"""
import base64
import hmac
import os

from django.conf import settings
from django.http import HttpResponse

OPEN_PATHS = ("/healthz", "/favicon.ico", "/robots.txt")


def users() -> dict[str, str]:
    u = {}
    if os.environ.get("BASIC_AUTH_USER") and os.environ.get("BASIC_AUTH_PASSWORD"):
        u[os.environ["BASIC_AUTH_USER"]] = os.environ["BASIC_AUTH_PASSWORD"]
    for pair in os.environ.get("BASIC_AUTH_USERS", "").split(";"):
        if ":" in pair:
            name, pw = pair.split(":", 1)
            if name.strip() and pw:
                u[name.strip()] = pw
    return u


class BasicAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in OPEN_PATHS:
            request.planer = "system"
            return self.get_response(request)
        known = users()
        if not known:
            if settings.DEBUG or getattr(settings, "TESTING", False):
                request.planer = os.environ.get("USER", "lokal")
                return self.get_response(request)
            return HttpResponse("Zugang nicht eingerichtet: BASIC_AUTH_USER/BASIC_AUTH_PASSWORD setzen.", status=503,
                                content_type="text/plain; charset=utf-8")
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.startswith("Basic "):
            try:
                name, pw = base64.b64decode(header[6:]).decode("utf-8").split(":", 1)
            except Exception:
                name, pw = "", ""
            if name in known and hmac.compare_digest(known[name], pw):
                request.planer = name
                return self.get_response(request)
        r = HttpResponse("Anmeldung erforderlich", status=401, content_type="text/plain; charset=utf-8")
        r["WWW-Authenticate"] = 'Basic realm="PoC Bedarfsplanung", charset="UTF-8"'
        return r
