#!/usr/bin/env bash
# Installation finale de RSU-Web — à lancer avec sudo :
#     sudo bash /home/rse/rsu-web/deploy/installer.sh
# Idempotent : peut être relancé sans danger.
set -e

echo "==> 1/5  Installation du service systemd"
cp /home/rse/rsu-web/deploy/rsu-web.service /etc/systemd/system/rsu-web.service
systemctl daemon-reload
systemctl enable --now rsu-web

echo "==> 2/5  Attente du démarrage de l'application (3 s)"
sleep 3
systemctl --no-pager --lines=0 status rsu-web | head -4 || true

echo "==> 3/5  Vérification de la syntaxe Apache (AVANT de recharger)"
if ! apache2ctl configtest; then
    echo "!! ERREUR de syntaxe Apache — rechargement ANNULÉ. Rien n'a été cassé." >&2
    exit 1
fi

echo "==> 4/5  Rechargement d'Apache (applique la route /rsu-web/)"
systemctl reload apache2

echo "==> 5/5  Test de bout en bout"
echo -n "   app locale  (127.0.0.1:8000/rsu-web/login) : "
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8000/rsu-web/login || true
echo -n "   via Apache  (http  /rsu-web/login)         : "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -H 'Host: rse.instat.mg' http://127.0.0.1/rsu-web/login || true
echo -n "   via Apache  (https /rsu-web/login)         : "
curl -sk -o /dev/null -w "HTTP %{http_code}\n" -H 'Host: rse.instat.mg' https://127.0.0.1/rsu-web/login || true

echo
echo "TERMINÉ. L'application doit être accessible sur :"
echo "    https://rse.instat.mg/rsu-web/"
