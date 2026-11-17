#!/bin/sh
# Passwortschutz. Der Bericht trägt Logo und Markenelemente von Phoenix Contact und
# später echte Planungsdaten: Ohne Zugangsdaten wird NICHTS ausgeliefert (fail closed).
set -e
if [ -n "$BASIC_AUTH_USER" ] && [ -n "$BASIC_AUTH_PASSWORD" ]; then
  printf '%s:{PLAIN}%s\n' "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD" > /etc/nginx/.htpasswd
  chmod 640 /etc/nginx/.htpasswd && chown root:nginx /etc/nginx/.htpasswd
  printf 'auth_basic "PoC Bedarfsplanung";\nauth_basic_user_file /etc/nginx/.htpasswd;\n' > /etc/nginx/auth.conf
  echo "Basic Auth aktiv für Benutzer $BASIC_AUTH_USER"
else
  echo "BASIC_AUTH_USER/BASIC_AUTH_PASSWORD fehlen: Bericht wird gesperrt ausgeliefert." >&2
  rm -rf /usr/share/nginx/html/*
  cp /usr/share/nginx/locked/index.html /usr/share/nginx/html/index.html
  : > /etc/nginx/auth.conf
fi
