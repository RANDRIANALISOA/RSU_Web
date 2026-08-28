# -*- coding: utf-8 -*-
"""
serveur_web.py — PROTOTYPE de version web de RapportRSU.

But : montrer comment la MEME logique metier que l'exe (rapport_core.generer_rapport)
peut etre exposee dans un navigateur, sans reecrire les calculs.

Principe :
    Navigateur  --(upload des 3 .dta)-->  ce serveur  --appelle-->  rapport_core
    Navigateur  <--(le Rapport HTML)----  ce serveur  <--renvoie--  chemin du .html

Contraintes respectees :
    - Bibliotheque STANDARD uniquement (http.server) : aucune installation.
      Se lance par :  python serveur_web.py
    - Reutilise rapport_core.py / lire_dta.py (copies partagees) tels quels.
    - Les chemins (contours, gabarits) viennent de config.py.

⚠️  PROTOTYPE de demonstration, PAS un serveur de production :
    - pas d'authentification (a ajouter avant toute mise en ligne) ;
    - le corps de la requete est lu en memoire (ok pour ~50 Mo en local) ;
    - un seul utilisateur a la fois suffit pour la demo.
    Pour un vrai deploiement : FastAPI/Flask + login + HTTPS + serveur interne INSTAT.
    Etape suivante prevue : lire directement la BASE (source_db) au lieu de l'upload.
"""

import html
import http.server
import os
import socketserver
import tempfile
import uuid
import webbrowser

import rapport_core
import config

PORT = 8000

# Fichiers .dta attendus par rapport_core (champ du formulaire -> nom sur disque).
FICHIERS_ATTENDUS = {
    "den": "DEN_MENAGE.dta",
    "roster": "segment_roster.dta",
    "diag": "interview__diagnostics.dta",
}

# Rapports generes de cette session : id -> chemin du .html sur le disque.
RAPPORTS = {}


# ---------------------------------------------------------------------------
# Analyse multipart/form-data (upload de fichiers) en bibliotheque standard.
# Le module `cgi` ayant disparu en Python 3.13, on parse a la main.
# ---------------------------------------------------------------------------
def _parse_multipart(body: bytes, boundary: bytes) -> dict:
    """Renvoie {nom_champ: {"filename": str|None, "data": bytes}}."""
    resultat = {}
    sep = b"--" + boundary
    for part in body.split(sep):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        entete, _, data = part.partition(b"\r\n\r\n")
        entete_txt = entete.decode("utf-8", "replace")
        nom = None
        filename = None
        for ligne in entete_txt.split("\r\n"):
            if ligne.lower().startswith("content-disposition"):
                for morceau in ligne.split(";"):
                    morceau = morceau.strip()
                    if morceau.startswith('name="'):
                        nom = morceau[6:-1]
                    elif morceau.startswith('filename="'):
                        filename = morceau[10:-1]
        if nom is not None:
            resultat[nom] = {"filename": filename, "data": data}
    return resultat


# ---------------------------------------------------------------------------
# Pages HTML du serveur (la page d'accueil ; le rapport lui-meme vient du core).
# ---------------------------------------------------------------------------
PAGE_ACCUEIL = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RapportRSU — version web (prototype)</title>
<style>
  body{{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:640px;margin:40px auto;
       padding:0 16px;color:#1c2430;line-height:1.5}}
  h1{{font-size:1.4rem}}
  .carte{{border:1px solid #d5dde6;border-radius:10px;padding:20px;margin-top:16px}}
  label{{display:block;margin:14px 0 4px;font-weight:600;font-size:.92rem}}
  input[type=file],select{{width:100%;padding:8px;border:1px solid #c3ccd6;border-radius:6px}}
  button{{margin-top:22px;background:#1b6ef3;color:#fff;border:0;border-radius:7px;
          padding:12px 20px;font-size:1rem;cursor:pointer}}
  .note{{background:#fff7e6;border:1px solid #ffe1a8;border-radius:8px;padding:12px;
         font-size:.86rem;margin-top:20px}}
  small{{color:#5a6675}}
</style></head><body>
<h1>Générer le Rapport RSU 2026</h1>
<p>Sélectionnez les trois fichiers <code>.dta</code> du dénombrement, puis lancez la
génération. Le rapport interactif s'ouvre dans le navigateur.</p>
<form class="carte" method="post" action="/generer" enctype="multipart/form-data">
  <label>DEN_MENAGE.dta <small>(1 ligne par segment)</small></label>
  <input type="file" name="den" accept=".dta" required>
  <label>segment_roster.dta <small>(1 ligne par ménage)</small></label>
  <input type="file" name="roster" accept=".dta" required>
  <label>interview__diagnostics.dta <small>(agent, durée, statut)</small></label>
  <input type="file" name="diag" accept=".dta" required>
  <label>Limites des fokontany (contours de la carte)</label>
  <select name="limites_mode">
    <option value="integrees">Intégrées (OCHA 2018) — recommandé</option>
    <option value="auto">Automatiques (enveloppe des points GPS)</option>
  </select>
  <button type="submit">Générer le rapport</button>
</form>
<div class="note"><strong>Prototype de démonstration.</strong> Sans authentification :
à ne pas exposer sur internet en l'état. Données personnelles → héberger en interne
INSTAT, ajouter un login et HTTPS avant toute mise en ligne.</div>
</body></html>"""


def _page_erreur(msg: str) -> str:
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Erreur</title><style>body{{font-family:system-ui,sans-serif;max-width:640px;
margin:40px auto;padding:0 16px}}.err{{background:#fdecec;border:1px solid #f5b5b5;
border-radius:8px;padding:16px;white-space:pre-wrap}}</style></head><body>
<h1>La génération a échoué</h1>
<div class="err">{html.escape(msg)}</div>
<p><a href="/">&larr; Réessayer</a></p></body></html>"""


# ---------------------------------------------------------------------------
# Le handler HTTP.
# ---------------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):

    def _envoyer_html(self, contenu: str, code: int = 200):
        octets = contenu.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(octets)))
        self.end_headers()
        self.wfile.write(octets)

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self._envoyer_html(PAGE_ACCUEIL)
        elif self.path.startswith("/rapport/"):
            rid = self.path.split("/rapport/", 1)[1]
            chemin = RAPPORTS.get(rid)
            if chemin and os.path.isfile(chemin):
                with open(chemin, "r", encoding="utf-8") as f:
                    self._envoyer_html(f.read())
            else:
                self._envoyer_html(_page_erreur("Rapport introuvable."), 404)
        else:
            self._envoyer_html(_page_erreur("Page inconnue."), 404)

    def do_POST(self):
        if self.path != "/generer":
            self._envoyer_html(_page_erreur("Chemin inconnu."), 404)
            return

        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            self._envoyer_html(_page_erreur("Requête invalide (pas de fichiers)."), 400)
            return
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode("utf-8")
        taille = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(taille)
        champs = _parse_multipart(body, boundary)

        # Dossier de travail isole pour cette generation.
        travail = tempfile.mkdtemp(prefix="rsu_web_")
        data_dir = os.path.join(travail, "DATA")
        rapport_dir = os.path.join(travail, "Rapport")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(rapport_dir, exist_ok=True)

        # Ecrire les .dta uploades sous les noms attendus par rapport_core.
        for champ, nom_fichier in FICHIERS_ATTENDUS.items():
            info = champs.get(champ)
            if not info or not info["data"]:
                self._envoyer_html(_page_erreur(
                    f"Fichier manquant : {nom_fichier}"), 400)
                return
            with open(os.path.join(data_dir, nom_fichier), "wb") as f:
                f.write(info["data"])

        mode = "integrees"
        if champs.get("limites_mode"):
            mode = champs["limites_mode"]["data"].decode("utf-8", "replace").strip()

        chemins = {
            "data": data_dir,
            "rapport": rapport_dir,
            "limites": config.LIMITES_DIR,
            "templates": config.TEMPLATES_DIR,
            "limites_mode": mode,
        }

        journal = []
        try:
            out = rapport_core.generer_rapport(chemins, journal.append)
        except rapport_core.ErreurRapport as e:
            self._envoyer_html(_page_erreur(str(e)), 400)
            return
        except Exception as e:  # garde-fou prototype
            self._envoyer_html(_page_erreur(
                "Erreur inattendue : " + repr(e) + "\n\n"
                + "\n".join(journal)), 500)
            return

        rid = uuid.uuid4().hex[:12]
        RAPPORTS[rid] = out
        # Rediriger vers le rapport genere.
        self.send_response(303)
        self.send_header("Location", "/rapport/" + rid)
        self.end_headers()

    def log_message(self, fmt, *args):  # journal serveur plus discret
        print("[web]", fmt % args)


def main():
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        url = f"http://127.0.0.1:{PORT}/"
        print(f"Serveur RapportRSU (prototype) en ligne : {url}")
        print("Ctrl+C pour arreter.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nArret du serveur.")


if __name__ == "__main__":
    main()
