# -*- coding: utf-8 -*-
"""manuel_ui.py — Briques de rendu, illustrations et styles du manuel intégré.

Importé par `manuel.py` (assemblage de la page) et `manuel_roles.py` (contenu par
rôle). Tout ce qui produit du HTML « présentation » (étapes, encadrés, maquettes
Excel, schémas de flux, arborescences) vit ici pour rester réutilisable.
"""

import base64
import html as _h
import os

# Dossier des VRAIES captures d'écran (facultatives). Déposez-y des PNG/JPG aux
# noms attendus (voir images/manuel/README.txt) : le manuel les affiche alors à la
# place de l'illustration correspondante. Absent -> on garde l'illustration.
_IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "manuel")
_EXT_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".gif": "image/gif"}


def capture(noms, legende, remplacement=""):
    """Renvoie une VRAIE capture (embarquée en data-URI) si le fichier existe dans
    images/manuel/, sinon `remplacement` (une illustration déjà rendue via figure(),
    ou "" pour n'afficher qu'une capture optionnelle). `noms` = nom de fichier ou
    liste de candidats."""
    if isinstance(noms, str):
        noms = [noms]
    for nom in noms:
        ext = os.path.splitext(nom)[1].lower()
        chemin = os.path.join(_IMG_DIR, nom)
        if ext in _EXT_MIME and os.path.isfile(chemin):
            try:
                with open(chemin, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
            except OSError:
                continue
            uri = f"data:{_EXT_MIME[ext]};base64,{b64}"
            return figure(f'<img class="shot" src="{uri}" '
                          f'alt="{_h.escape(legende)}">', legende)
    return remplacement


# --- Briques de texte ------------------------------------------------------
def p(txt):
    return f"<p>{txt}</p>"


def etapes(items):
    return '<ol class="etapes">' + "".join(f"<li>{t}</li>" for t in items) + "</ol>"


def puces(items):
    return '<ul class="puces">' + "".join(f"<li>{t}</li>" for t in items) + "</ul>"


def h3(txt):
    return f"<h3>{_h.escape(txt)}</h3>"


def callout(genre, titre, txt):
    ic = {"astuce": "💡", "attention": "⚠️", "info": "ℹ️"}.get(genre, "ℹ️")
    return (f'<div class="callout {genre}"><div class="co-ic">{ic}</div>'
            f'<div><strong>{_h.escape(titre)}</strong><div>{txt}</div></div></div>')


def astuce(txt, titre="Astuce"):
    return callout("astuce", titre, txt)


def attention(txt, titre="À noter"):
    return callout("attention", titre, txt)


def info(txt, titre="Information"):
    return callout("info", titre, txt)


def figure(inner, legende):
    return (f'<figure class="illus">{inner}'
            f'<figcaption>{_h.escape(legende)}</figcaption></figure>')


def bouton(txt):
    """Rendu inline d'un bouton de l'application (pour le désigner précisément)."""
    return f'<span class="btn-demo">{_h.escape(txt)}</span>'


def carte(txt):
    """Rendu inline d'une « carte » de choix de l'application."""
    return f'<span class="carte-demo">{_h.escape(txt)}</span>'


# --- Illustrations ---------------------------------------------------------
def flux(pas):
    """Schéma de flux horizontal : cartes numérotées reliées par des flèches.
    `pas` = [(titre, description), …]."""
    cartes = []
    for i, (titre, desc) in enumerate(pas, start=1):
        cartes.append(
            f'<div class="fx-carte"><div class="fx-num">{i}</div>'
            f'<div class="fx-t">{_h.escape(titre)}</div>'
            f'<div class="fx-d">{_h.escape(desc)}</div></div>')
    return ('<div class="flux">'
            + '<div class="fx-fleche">→</div>'.join(cartes) + '</div>')


def tableur(colonnes, lignes, note=None):
    """Maquette d'un fichier Excel : lettres de colonnes + en-tête + lignes."""
    from openpyxl.utils import get_column_letter
    lettres = "".join(f"<th class='xl-col'>{get_column_letter(j)}</th>"
                      for j in range(1, len(colonnes) + 1))
    entete = "".join(f"<td class='xl-h'>{_h.escape(str(c))}</td>" for c in colonnes)
    corps = ""
    for i, lg in enumerate(lignes, start=2):
        cells = "".join(f"<td>{_h.escape(str(v))}</td>" for v in lg)
        corps += f"<tr><th class='xl-row'>{i}</th>{cells}</tr>"
    note_html = f'<div class="xl-note">{_h.escape(note)}</div>' if note else ""
    return ('<div class="tableur-wrap"><table class="tableur">'
            f'<tr><th class="xl-corner"></th>{lettres}</tr>'
            f'<tr><th class="xl-row">1</th>{entete}</tr>'
            f'{corps}</table>{note_html}</div>')


def arbre(lignes):
    """Arborescence de fichiers (monospace)."""
    return '<pre class="arbre">' + "\n".join(_h.escape(l) for l in lignes) + "</pre>"


def illus_bandeau():
    return figure(
        '<div class="demo-bandeau">'
        '<div class="db-ava">RA</div>'
        '<div class="db-txt"><span class="db-nom">Votre nom…</span>'
        '<span class="db-role">Votre rôle</span></div>'
        '<span class="db-pill db-home">⌂ Mon espace</span>'
        '<span class="db-pill">🔑 Mot de passe</span>'
        '<span class="db-pill">📘 Manuel</span>'
        '<span class="db-pill db-out">⎋ Déconnexion</span>'
        '</div>',
        "Le bandeau, présent en haut à droite de chaque page une fois connecté.")


def illus_dashboard():
    """Maquette schématique du tableau de bord (barre latérale + contenu)."""
    menu = "".join(
        f'<div class="dbd-item{" on" if k=="Vue générale" else ""}">{k}</div>'
        for k in ["Vue générale", "Par agent", "Par zone", "Carte GPS",
                  "Capture GPS", "Qualité", "Historique", "Segments multiples"])
    return figure(
        '<div class="dbd">'
        f'<div class="dbd-side"><div class="dbd-side-t">SECTIONS</div>{menu}'
        '<div class="dbd-drill">▸ Commune → Fokontany</div></div>'
        '<div class="dbd-main"><div class="dbd-h">Vue générale — District</div>'
        '<div class="dbd-kpis"><span></span><span></span><span></span><span></span></div>'
        '<div class="dbd-panel">Couverture, qualité, graphiques…</div>'
        '<div class="dbd-float">⬇ Exporter rapport</div></div>'
        '</div>',
        "Le tableau de bord : sections à gauche, contenu au centre, bouton "
        "d'export en bas à droite.")


# --- Styles ----------------------------------------------------------------
CSS = """
*{box-sizing:border-box}
body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
  background:#eef2f7;line-height:1.6;padding:78px 18px 60px}
.man-wrap{max-width:1060px;margin:0 auto;display:grid;
  grid-template-columns:230px 1fr;gap:26px;align-items:start}
.man-toc{position:sticky;top:90px;background:#fff;border:1px solid #dce3ea;
  border-radius:14px;padding:16px 14px;font-size:.88rem;max-height:calc(100vh - 120px);
  overflow:auto}
.man-toc h3{margin:0 0 10px;font-size:.74rem;text-transform:uppercase;
  letter-spacing:.06em;color:#7a8698}
.man-toc a{display:block;padding:6px 9px;border-radius:8px;text-decoration:none;
  color:#31404f;margin-bottom:2px}
.man-toc a:hover{background:#eef5ff;color:#1558c9}
.man-toc a.grp{margin-top:10px;font-weight:700;color:#12325c}
.man-main{min-width:0}
.man-tete{background:linear-gradient(135deg,#1b6ef3,#1558c9);color:#fff;
  border-radius:18px;padding:26px 28px;box-shadow:0 14px 34px rgba(27,110,243,.28);
  margin-bottom:22px}
.man-tete .ruban{display:inline-block;font-size:.74rem;font-weight:700;
  background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.35);
  border-radius:999px;padding:2px 11px;margin-bottom:8px}
.man-tete h1{margin:0 0 6px;font-size:1.6rem}
.man-tete p{margin:0;opacity:.94}
section.man-sec{background:#fff;border:1px solid #dce3ea;border-radius:16px;
  padding:22px 26px;margin-bottom:18px;box-shadow:0 8px 22px rgba(13,43,78,.06);
  scroll-margin-top:90px}
section.man-sec h2{margin:0 0 12px;font-size:1.22rem;color:#12325c;
  display:flex;align-items:center;gap:10px}
section.man-sec h2 .n{width:28px;height:28px;flex:none;border-radius:8px;
  background:#eaf1fd;color:#1558c9;font-size:.86rem;font-weight:800;display:flex;
  align-items:center;justify-content:center}
.man-sec p{margin:10px 0}
.man-sec h3{font-size:1.02rem;color:#1c2430;margin:18px 0 8px}
ol.etapes{margin:12px 0;padding-left:0;counter-reset:et;list-style:none}
ol.etapes>li{position:relative;padding:8px 8px 8px 40px;margin:6px 0;
  background:#f7f9fc;border:1px solid #e8edf3;border-radius:10px;counter-increment:et}
ol.etapes>li::before{content:counter(et);position:absolute;left:9px;top:8px;
  width:22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#1b6ef3,#1558c9);
  color:#fff;font-size:.78rem;font-weight:800;display:flex;align-items:center;
  justify-content:center}
ul.puces{margin:10px 0;padding-left:20px}
ul.puces li{margin:5px 0}
.btn-demo{display:inline-block;background:linear-gradient(135deg,#1b6ef3,#1558c9);
  color:#fff;font-weight:600;font-size:.82rem;border-radius:8px;padding:2px 10px;
  white-space:nowrap}
.carte-demo{display:inline-block;background:#eef5ff;border:1px solid #bcd3f7;
  color:#12325c;font-weight:600;font-size:.82rem;border-radius:8px;padding:2px 10px}
.callout{display:flex;gap:12px;border-radius:12px;padding:12px 14px;margin:14px 0;
  font-size:.92rem}
.callout .co-ic{font-size:1.1rem;flex:none}
.callout.astuce{background:#e8f7f0;border:1px solid #b8e6d2}
.callout.attention{background:#fef6e7;border:1px solid #f5d99a}
.callout.info{background:#eaf1fd;border:1px solid #c7dbf7}
figure.illus{margin:16px 0;padding:16px;background:#f7f9fc;border:1px solid #e8edf3;
  border-radius:12px;overflow-x:auto}
figure.illus figcaption{margin-top:10px;font-size:.82rem;color:#6b7787;
  font-style:italic;text-align:center}
.flux{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;justify-content:center}
.fx-carte{flex:1 1 150px;min-width:140px;max-width:210px;background:#fff;
  border:1px solid #d7e0ea;border-radius:12px;padding:12px;text-align:center}
.fx-num{width:26px;height:26px;margin:0 auto 6px;border-radius:50%;color:#fff;
  font-weight:800;font-size:.8rem;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#17a398,#0e857c)}
.fx-t{font-weight:700;font-size:.9rem}
.fx-d{font-size:.78rem;color:#6b7787;margin-top:3px}
.fx-fleche{display:flex;align-items:center;color:#9fb2c6;font-size:1.3rem;font-weight:700}
.tableur-wrap{overflow-x:auto}
table.tableur{border-collapse:collapse;font-size:.82rem;background:#fff;
  min-width:520px;font-family:ui-monospace,"Cascadia Code",monospace}
table.tableur th,table.tableur td{border:1px solid #cfd8e3;padding:5px 9px;
  text-align:left;white-space:nowrap}
table.tableur .xl-col,table.tableur .xl-row,table.tableur .xl-corner{
  background:#eef2f7;color:#7a8698;text-align:center;font-weight:600}
table.tableur .xl-h{background:#dbeafe;font-weight:700;color:#12325c}
.xl-note{font-size:.8rem;color:#6b7787;margin-top:8px}
pre.arbre{background:#0d2b4e;color:#dbe7f5;border-radius:10px;padding:14px 16px;
  font-size:.82rem;line-height:1.5;overflow-x:auto;margin:14px 0}
.demo-bandeau{display:inline-flex;align-items:center;gap:8px;background:#fff;
  border:1px solid #dce3ea;border-radius:999px;padding:6px 8px;
  box-shadow:0 6px 18px rgba(13,43,78,.14);flex-wrap:wrap}
.demo-bandeau .db-ava{width:28px;height:28px;border-radius:50%;color:#fff;
  font-weight:800;font-size:.7rem;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#1b6ef3,#1558c9)}
.demo-bandeau .db-txt{display:flex;flex-direction:column;line-height:1.1}
.demo-bandeau .db-nom{font-weight:700;font-size:.8rem}
.demo-bandeau .db-role{font-size:.7rem;color:#5a6675}
.db-pill{font-size:.74rem;font-weight:600;border-radius:999px;padding:4px 9px;
  border:1px solid #c7dbf7;background:#eaf1fd;color:#1558c9}
.db-pill.db-out{border-color:#f0cfca;background:#fdecea;color:#c0392b}
.dbd{display:flex;gap:10px;min-width:520px}
.dbd-side{flex:none;width:180px;background:#0d2b4e;border-radius:10px;padding:10px;
  color:#cfe0f2}
.dbd-side-t{font-size:.66rem;letter-spacing:.08em;color:#7fa7d4;margin-bottom:6px}
.dbd-item{font-size:.78rem;padding:5px 8px;border-radius:7px;margin:2px 0}
.dbd-item.on{background:#1b6ef3;color:#fff;font-weight:700}
.dbd-drill{font-size:.72rem;color:#9fc0e6;margin-top:8px;border-top:1px solid #24466e;
  padding-top:8px}
.dbd-main{flex:1;background:#fff;border:1px solid #dce3ea;border-radius:10px;
  padding:12px;position:relative}
.dbd-h{font-weight:700;color:#12325c;margin-bottom:10px}
.dbd-kpis{display:flex;gap:8px;margin-bottom:10px}
.dbd-kpis span{flex:1;height:34px;background:#eef5ff;border:1px solid #d7e6fb;
  border-radius:8px}
.dbd-panel{height:70px;background:#f7f9fc;border:1px dashed #cdd8e4;border-radius:8px;
  display:flex;align-items:center;justify-content:center;color:#7a8698;font-size:.8rem}
.dbd-float{position:absolute;right:12px;bottom:12px;background:linear-gradient(135deg,#17a398,#0e857c);
  color:#fff;font-size:.72rem;font-weight:700;border-radius:999px;padding:5px 10px}
img.shot{max-width:100%;height:auto;display:block;margin:0 auto;border-radius:8px;
  border:1px solid #d7e0ea;box-shadow:0 6px 18px rgba(13,43,78,.12)}
.man-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}
.man-btn{display:inline-flex;align-items:center;gap:8px;background:#fff;
  border:1.5px solid #dce3ea;border-radius:10px;padding:10px 16px;cursor:pointer;
  color:#1c2430;font-weight:700;font-size:.92rem;text-decoration:none;font-family:inherit}
.man-btn:hover{background:#f4f7fb}
.man-btn.p{color:#fff;border:none;background:linear-gradient(135deg,#1b6ef3,#1558c9);
  box-shadow:0 10px 22px rgba(27,110,243,.26)}
.man-actions{margin-top:8px}
.man-actions a{display:inline-block;background:#fff;border:1.5px solid #dce3ea;
  border-radius:10px;padding:10px 16px;text-decoration:none;color:#1c2430;font-weight:700}
.man-actions a:hover{background:#f4f7fb}
@media (max-width:820px){.man-wrap{grid-template-columns:1fr}.man-toc{display:none}}
@media print{body{background:#fff;padding:0}
  .man-toc,.man-actions,.man-toolbar{display:none}
  .man-tete{box-shadow:none;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  section.man-sec{box-shadow:none;break-inside:avoid;border:1px solid #ccc}
  img.shot{box-shadow:none}}
"""
