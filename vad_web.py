# -*- coding: utf-8 -*-
"""
vad_web.py — Pages du TABLEAU DE BORD « Visite à domicile » (VAD).

Un tableau de bord MULTI-PAGES, comme celui du dénombrement : une section par
page (le serveur n'envoie que les agrégats de la section demandée, jamais les
ménages bruts), barre latérale commune, et graphiques Chart.js servis
hors-ligne depuis `assets/`.

    general      Vue globale        avancement, couverture, consentement, zones
    demographie  Démographie        pyramide des âges, masculinité, dépendance,
                                    chef de ménage, scolarisation, activité
    habitation   Habitation         murs / sol / toit / occupation / éclairage
    biens        Biens & actifs     taux de possession des 29 biens
    eau          Eau & assainissement  source d'eau, toilettes, ordures
    gps          Carte GPS          points des ménages + qualité de la capture
    erreurs      Listing d'erreurs  anomalies, ménage par ménage
    agents       Par agent          production et anomalies par enquêteur, et
                                    l'écart entre ce qu'il DÉCLARE avoir
                                    interviewé et ce qui ARRIVE AU SERVEUR

Les données viennent de `vad_core.agrege()`. Les tableaux sont rendus CÔTÉ
SERVEUR (lisibles sans JavaScript) ; seuls les graphiques passent par Chart.js.
"""
import html as _h
import json
import urllib.parse

import config

ESC = _h.escape

# (groupe, identifiant, picto, libellé). Le GROUPE n'est qu'un intertitre dans
# la barre latérale : à dix-huit sections, une liste plate ne se parcourt plus.
# Trois familles, dans l'ordre où on s'en sert — ce que le RSU sait des
# PERSONNES, ce qu'il sait du MÉNAGE, puis comment la collecte s'est passée.
SECTIONS = [
    ("Vue d'ensemble", "general", "🏠", "Vue globale"),
    ("Les personnes", "demographie", "👨‍👩‍👧", "Démographie"),
    ("Les personnes", "education", "🎓", "Éducation"),
    ("Les personnes", "handicap", "♿", "Handicap"),
    ("Les personnes", "identite", "🪪", "Identité & état civil"),
    ("Les personnes", "enfance", "🧒", "Enfance & vulnérabilité"),
    ("Les personnes", "mobilite", "🧭", "Résidence & mobilité"),
    ("Le ménage", "habitation", "🏚️", "Habitation"),
    ("Le ménage", "biens", "🧰", "Biens & actifs"),
    ("Le ménage", "eau", "🚰", "Eau & assainissement"),
    ("Le ménage", "activite", "🌾", "Activité & agriculture"),
    ("Le ménage", "ciblage", "🎯", "Ciblage & joignabilité"),
    ("La collecte", "gps", "🗺️", "Carte GPS"),
    ("La collecte", "err_menage", "🏠", "Erreurs ménage"),
    ("La collecte", "err_individu", "👤", "Erreurs individus"),
    ("La collecte", "qualite_base", "🧪", "Qualité de la base"),
    ("La collecte", "qualite", "🔬", "Test de qualité par agent"),
    ("La collecte", "agents", "👥", "Par agent"),
]
IDS = {s for _g, s, _i, _l in SECTIONS}

_CSS = """
<style>
.sai-filtres{display:flex;flex-wrap:wrap;gap:0.5rem;align-items:flex-end;
  margin:0 0 0.75rem}
.sai-filtres label{display:flex;flex-direction:column;gap:0.2rem;font-size:0.72rem;
  color:#64748b;font-weight:500}
.sai-filtres select,.sai-filtres input{font:inherit;font-size:0.8rem;
  padding:0.35rem 0.45rem;border:1px solid #d7dde5;border-radius:0.4rem;
  background:#fff;min-width:9rem;color:#0f172a}
.sai-filtres select:focus,.sai-filtres input:focus{outline:none;
  border-color:#2563eb;box-shadow:0 0 0 3px #2563eb22}
.sai-filtres button{font:inherit;font-size:0.8rem;padding:0.4rem 0.75rem;
  border:1px solid #d7dde5;border-radius:0.4rem;background:#fff;cursor:pointer;
  color:#334155}
.sai-filtres button:hover{background:#f1f5f9;border-color:#94a3b8}
.sai-compte{font-size:0.8rem;color:#64748b;margin:0 0 0.5rem;font-weight:500}
.sai-compte b{color:#0f172a}
.sai-scroll{overflow:auto;max-height:72vh;border:1px solid #e2e8f0;
  border-radius:0.6rem;background:#fff}
table.sai-tbl{border-collapse:separate;border-spacing:0;font-size:0.78rem;
  width:max-content;min-width:100%}
table.sai-tbl th,table.sai-tbl td{padding:0.4rem 0.55rem;text-align:left;
  border-bottom:1px solid #eef2f6;vertical-align:top}
table.sai-tbl thead th{position:sticky;top:0;z-index:3;background:#f8fafc;
  border-bottom:1px solid #cbd5e1;font-weight:500;color:#334155;
  white-space:nowrap}
table.sai-tbl thead tr.gr th{top:0;z-index:4;font-size:0.68rem;
  text-transform:uppercase;letter-spacing:0.04em;color:#64748b;
  background:#eef2f7;text-align:center;border-bottom:1px solid #cbd5e1}
table.sai-tbl thead tr.hd th{top:1.55rem}
th.sai-err{min-width:10rem;max-width:13rem;white-space:normal;
  background:#fffdf5;border-left:1px solid #f1e9d2}
.sai-var{display:block;font-family:ui-monospace,SFMono-Regular,monospace;
  font-size:0.63rem;color:#a16207;font-weight:400;margin-top:0.1rem}
table.sai-tbl tbody tr:nth-child(even){background:#fcfdfe}
table.sai-tbl tbody tr:hover{background:#eff6ff}
table.sai-tbl tbody tr:hover td.fig{background:#eff6ff}
td.fig,th.fig{position:sticky;left:0;z-index:2;background:#fff;
  border-right:1px solid #e2e8f0;font-weight:500;max-width:14rem}
table.sai-tbl thead th.fig{z-index:5;background:#f8fafc}
td.sai-err-on{background:#fef6e0;color:#8a5a08;white-space:normal;
  line-height:1.35;border-left:1px solid #f1e9d2}
td.sai-err-off{background:#fdfdfc;border-left:1px solid #f4f4f2}
.sai-nb{display:inline-block;min-width:1.35rem;text-align:center;
  padding:0.05rem 0.3rem;border-radius:0.65rem;background:#fde68a;
  color:#78350f;font-size:0.7rem;font-weight:500}
.sai-vide{padding:1.1rem;color:#64748b;font-size:0.85rem;text-align:center}
.qa-doc{max-width:62rem;font-size:0.86rem;line-height:1.65;color:#1e293b}
.qb-ref{margin:0 0 0.55rem;padding:0.35rem 0.6rem;background:#f8fafc;
  border-left:3px solid #94a3b8;border-radius:0.2rem;font-size:0.82rem;
  color:#334155}
.qa-ident{display:flex;flex-wrap:wrap;gap:1.5rem;padding:0.8rem 1rem;margin:0 0 1.6rem;
  background:#f8fafc;border:1px solid #e2e8f0;border-radius:0.5rem;font-size:0.8rem}
.qa-ident b{display:block;font-size:1.05rem;font-weight:500;color:#0f172a}
.qa-ident span{color:#64748b}
.qa-h2{font-size:1.05rem;font-weight:500;color:#0f172a;margin:2rem 0 0.2rem;
  padding-bottom:0.4rem;border-bottom:2px solid #0f172a}
.qa-h2 small{display:block;font-size:0.78rem;color:#475569;font-weight:400;
  margin-top:0.35rem;line-height:1.55;border:0}
.qa-test{margin:1.6rem 0 0}
.qa-h3{font-size:0.95rem;font-weight:500;color:#0f172a;margin:0 0 0.4rem}
.qa-h3 .n{color:#64748b;margin-right:0.45rem}
.qa-p{margin:0 0 0.7rem;text-align:justify}
.qa-f{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.8rem;
  background:#f8fafc;border-left:3px solid #94a3b8;padding:0.55rem 0.9rem;
  margin:0 0 0.9rem;color:#0f172a;white-space:pre-wrap;line-height:1.7}
.qa-box{border:1px solid #cbd5e1;border-radius:0.35rem;margin:0 0 0.8rem;
  background:#fff;overflow:hidden}
.qa-box>.t{padding:0.4rem 0.9rem;background:#f1f5f9;font-size:0.78rem;
  font-weight:500;color:#334155;border-bottom:1px solid #cbd5e1;
  display:flex;justify-content:space-between;align-items:center;gap:1rem}
.qa-box>.c{padding:0.6rem 0.9rem}
.qa-box.al{border-color:#fca5a5}
.qa-box.al>.t{background:#fef2f2;color:#991b1b;border-bottom-color:#fca5a5}
.qa-box.ins>.t{background:#f8fafc;color:#94a3b8}
.qa-box.rem{border-color:#bfdbfe}
.qa-box.rem>.t{background:#eff6ff;color:#1e40af;border-bottom-color:#bfdbfe}
.qa-rem{margin:0 0 0.55rem;padding:0.4rem 0.6rem;background:#eff6ff;
  border-left:3px solid #60a5fa;border-radius:0.25rem;font-size:0.79rem;
  color:#1e3a8a;line-height:1.55}
.qa-pt{display:inline-block;padding:0.1rem 0.5rem;border-radius:0.7rem;
  background:#dbeafe;color:#1e40af;font-size:0.7rem;font-weight:500}
.qa-calc{margin:0;padding:0;list-style:none;font-size:0.82rem;line-height:1.75}
.qa-calc li{padding:0.05rem 0}
.qa-ccl{margin:0.55rem 0 0;font-weight:500;font-size:0.84rem}
.qa-ccl.al{color:#991b1b}
.qa-ccl.ok{color:#166534}
.qa-ccl.ins{color:#64748b;font-weight:400;font-style:italic}
.qa-seuils{margin:0;padding:0 0 0 1.1rem;font-size:0.82rem;line-height:1.7;
  color:#334155}
.qa-val{font-size:1.15rem;font-weight:500;color:#0f172a;white-space:nowrap}
.qa-ok{display:inline-block;padding:0.1rem 0.5rem;border-radius:0.7rem;
  background:#dcfce7;color:#166534;font-size:0.7rem}
.qa-al{display:inline-block;padding:0.1rem 0.5rem;border-radius:0.7rem;
  background:#fee2e2;color:#991b1b;font-size:0.7rem;font-weight:500}
.qa-na{display:inline-block;padding:0.1rem 0.5rem;border-radius:0.7rem;
  background:#f1f5f9;color:#64748b;font-size:0.7rem}
.qa-msg{padding:1.4rem;text-align:center;color:#64748b;font-size:0.85rem;
  border:1px dashed #cbd5e1;border-radius:0.6rem}
.qa-vg{display:inline-block;padding:0.1rem 0.5rem;border-radius:0.7rem;
  background:#ffedd5;color:#9a3412;font-size:0.7rem;font-weight:500}
.qa-box.vg{border-color:#fdba74}
.qa-box.vg>.t{background:#fff7ed;color:#9a3412;border-bottom-color:#fdba74}
.qa-ccl.vg{color:#9a3412}
/* ---- MATRICE des tests de qualité : une ligne par agent, une colonne par test.
   Les deux premières colonnes (CE, AE) restent figées au défilement horizontal,
   l'en-tête au défilement vertical : sur 200 agents et 6 tests, sans cela on
   perd de vue QUI est la ligne qu'on est en train de lire. ---- */
.qm-bar{display:flex;flex-wrap:wrap;gap:0.7rem;align-items:center;
  justify-content:space-between;margin:0 0 0.7rem}
.qm-lg{display:inline-flex;align-items:center;gap:0.35rem;font-size:0.74rem;
  color:#475569;margin-right:0.7rem}
.qm-lg i{width:0.8rem;height:0.8rem;border-radius:0.2rem;display:inline-block;
  border:1px solid #00000014}
.qm-lg.al i{background:#fecaca}
.qm-lg.vg i{background:#fed7aa}
.qm-lg.ok i{background:#bbf7d0}
.qm-lg.nd i{background:#eef2f6}
.qm-out{display:flex;gap:0.6rem;align-items:center;flex-wrap:wrap}
.qm-out input[type=search]{font:inherit;font-size:0.8rem;padding:0.35rem 0.6rem;
  border:1px solid #d7dde5;border-radius:0.45rem;min-width:14rem;background:#fff}
.qm-out label{font-size:0.78rem;color:#475569;display:inline-flex;gap:0.3rem;
  align-items:center;cursor:pointer}
.qm-note{margin:0 0 0.9rem;font-size:0.78rem;color:#64748b;line-height:1.6;
  max-width:62rem}
.qm-wrap{overflow:auto;max-height:calc(100vh - 16rem);border:1px solid #e2e8f0;
  border-radius:0.5rem;background:#fff}
table.qm{border-collapse:separate;border-spacing:0;font-size:0.78rem;width:100%}
table.qm th,table.qm td{padding:0.35rem 0.55rem;border-bottom:1px solid #eef2f6;
  white-space:nowrap}
table.qm thead th{position:sticky;top:0;z-index:3;background:#f8fafc;
  text-align:left;font-weight:500;color:#334155;vertical-align:bottom;
  border-bottom:1px solid #cbd5e1}
table.qm thead th small{display:block;font-weight:400;color:#94a3b8;
  font-size:0.68rem}
table.qm thead tr.qm-niv th{top:0;background:#eef2f7;color:#0f172a;
  font-size:0.72rem;text-align:center;border-bottom:1px solid #cbd5e1;
  border-left:1px solid #cbd5e1}
table.qm thead tr:nth-child(2) th{top:1.75rem}
table.qm th.f1,table.qm td.f1{position:sticky;left:0;z-index:2;background:#fff;
  border-right:1px solid #eef2f6}
table.qm th.f2,table.qm td.f2{position:sticky;left:9.5rem;z-index:2;background:#fff;
  border-right:1px solid #cbd5e1}
table.qm thead th.f1,table.qm thead th.f2{z-index:4;background:#f8fafc}
table.qm tr.qm-com td{position:sticky;left:0;background:#f1f5f9;color:#0f172a;
  font-weight:500;font-size:0.76rem;padding:0.4rem 0.6rem}
table.qm tbody tr:hover td{background:#f8fafc}
table.qm tbody tr:hover td.f1,table.qm tbody tr:hover td.f2{background:#f1f5f9}
table.qm td.num{text-align:right;color:#475569;font-variant-numeric:tabular-nums}
table.qm td.c{text-align:right;font-variant-numeric:tabular-nums;
  border-left:3px solid transparent}
table.qm td.c.al{background:#fecaca;color:#7f1d1d;font-weight:600;
  border-left-color:#dc2626}
table.qm td.c.vg{background:#fed7aa;color:#7c2d12;font-weight:500;
  border-left-color:#ea580c}
table.qm td.c.ok{background:#bbf7d0;color:#14532d}
table.qm td.c.nd{background:#eef2f6;color:#94a3b8;font-style:italic}
/* La statistique de test, à côté de la mesure : plus petite, jamais concurrente. */
.qm-s{font-size:0.68rem;opacity:.72;font-weight:400;
  font-variant-numeric:tabular-nums}
table.qm td.f2 a{color:#1d4ed8;text-decoration:none}
table.qm td.f2 a:hover{text-decoration:underline}
table.qm tbody tr{cursor:pointer}
.qm-vide{padding:1.2rem;text-align:center;color:#64748b;font-size:0.82rem}
.qa-retour{display:inline-block;margin:0 0 1rem;font-size:0.82rem;color:#1d4ed8;
  text-decoration:none}
.qa-retour:hover{text-decoration:underline}
#t-men,#t-ind{font-size:0.78rem}
#t-men th,#t-ind th{vertical-align:bottom;white-space:normal}
th.sai-err{min-width:9rem;max-width:12rem;background:#fffbeb}
.sai-var{font-family:ui-monospace,monospace;font-size:0.65rem;color:#92400e;
  font-weight:400}
td.sai-err-on{background:#fef3c7;color:#92400e;min-width:9rem}
.vad-kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(11.5rem,1fr));
  gap:0.875rem;margin-bottom:1.25rem}
.vad-card{background:#fff;border:1px solid #e2e8f0;border-radius:0.875rem;
  padding:1rem 1.125rem;box-shadow:0 1px 2px rgba(15,23,42,.05)}
.vad-card .l{font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;
  color:#64748b;font-weight:700}
.vad-card .v{font-size:1.75rem;font-weight:800;color:#0f172a;line-height:1.15;
  margin-top:.25rem}
.vad-card .s{font-size:.78rem;color:#64748b;margin-top:.25rem}
.vad-card.ok{border-top:3px solid #10b981}
.vad-card.warn{border-top:3px solid #f59e0b}
.vad-card.bad{border-top:3px solid #ef4444}
.vad-card.info{border-top:3px solid #2563eb}
.vad-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(21rem,1fr));
  gap:1rem;margin-bottom:1.25rem}
.vad-box{background:#fff;border:1px solid #e2e8f0;border-radius:0.875rem;
  padding:1.125rem;box-shadow:0 1px 2px rgba(15,23,42,.05)}
.vad-box h3{margin:0 0 .25rem;font-size:1rem;color:#0f172a}
.vad-box .sub{font-size:.78rem;color:#64748b;margin:0 0 .75rem}
.vad-wrap{position:relative;height:16rem}
.vad-wrap.h20{height:20rem}
.vad-wrap.h28{height:28rem}
.vad-t{width:100%;border-collapse:collapse;font-size:.82rem}
.vad-t th{background:#f1f5f9;text-align:left;padding:.5rem .625rem;
  border-bottom:1px solid #e2e8f0;font-weight:700;color:#334155;position:sticky;top:0}
.vad-t td{padding:.45rem .625rem;border-bottom:1px solid #f1f5f9}
.vad-t tr:hover td{background:#f8fafc}
.vad-t td.n,.vad-t th.n{text-align:right;font-variant-numeric:tabular-nums}
.vad-scroll{max-height:32rem;overflow:auto;border:1px solid #e2e8f0;
  border-radius:0.75rem;background:#fff}
.vad-note{background:#eff6ff;border:1px solid #bfdbfe;border-radius:0.75rem;
  padding:.75rem 1rem;font-size:.85rem;color:#1e3a5f;margin-bottom:1rem}
.vad-alerte{background:#fef2f2;border:1px solid #fecaca;color:#7f1d1d}
.vad-attention{background:#fffbeb;border:1px solid #fde68a;color:#78350f}
.vad-bar{height:.5rem;border-radius:99px;background:#e2e8f0;overflow:hidden;
  margin-top:.35rem}
.vad-bar i{display:block;height:100%;background:#2563eb}
.pillg{display:inline-block;padding:.1rem .5rem;border-radius:99px;font-size:.72rem;
  font-weight:700}
.pillg.bloq{background:#fee2e2;color:#b91c1c}
.pillg.sig{background:#fef3c7;color:#92400e}
/* Même gabarit que la carte du dénombrement (#map de rapport.css) : la carte
   prend la hauteur de la fenêtre, le reste de la page défile au-dessus. */
#vadmap{width:100%;height:calc(100vh - 20rem);min-height:25rem;
  border-radius:0.75rem;border:1px solid #e2e8f0}
@media(max-width:860px){#vadmap{height:60vh;min-height:16rem}}
#vadmap-filters .ar-tab{margin:0}
/* Sous-menu de descente (mêmes classes que le dénombrement) : les entrées sont
   des liens ici, pas des boutons -> il faut retirer le soulignement. */
.nav-sub .nav-sub-item{text-decoration:none}
/* Flèches de dépliage. La flèche de la commune est un BOUTON à part du lien :
   ouvrir une commune pour voir ses fokontany ne doit pas changer de page. */
#vad-drill{max-height:22rem}
.vad-drill-tete{display:block;width:100%;text-align:left;background:none;
  border:none;cursor:pointer;font-family:inherit;color:#94a3b8;font-size:0.6875rem;
  font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  padding:0.375rem 0.625rem 0.375rem 1.125rem;border-radius:0.4375rem}
.vad-drill-tete:hover{background:rgba(255,255,255,0.06);color:#e2e8f0}
.vad-drill-tete .c{display:inline-block;width:0.75rem;font-size:0.6rem}
.vad-com{display:flex;align-items:flex-start}
.vad-com .nav-sub-item.commune{flex:1;padding-left:0.375rem}
.vad-com .nav-sub-item.commune::before{content:none}
.vad-caret{flex:none;width:1.25rem;background:none;border:none;cursor:pointer;
  color:#94a3b8;font-size:0.6rem;line-height:1;padding:0.5rem 0;border-radius:0.25rem}
.vad-caret:hover{background:rgba(255,255,255,0.1);color:#e2e8f0}
/* Le bouton ☰ « masquer les sections » est injecté en tête de .page-head par le
   script global (serveur_app._STYLE_RESPONSIVE) : on met l'en-tête en ligne pour
   qu'il se pose à gauche du titre, et le titre garde son sous-titre dessous. */
.page-head{display:flex;align-items:center;flex-wrap:wrap;column-gap:0.75rem}
.page-head h1{flex:0 0 auto;margin-right:0}
.page-head .page-sub{flex:1 1 100%;margin-top:0}
body.rsu-nav-col .main{width:100%}
.nav-sub .nav-sub-item.all.active,.nav-sub .nav-sub-item.commune.active,
.nav-sub .nav-sub-item.fkt.active{background:rgba(37,99,235,0.28);color:#fff}

/* ====================== Qualité de la base ==========================
   Trois étages de lecture : le bandeau et les cartes de famille se
   parcourent d'un coup d'œil, les graphiques en une minute, les fiches
   d'indicateurs se déplient pour qui veut la démonstration. Chaque famille
   porte sa couleur (--fc), reprise du picto jusqu'au numéro de chaque
   indicateur : sur vingt-cinq contrôles, la couleur oriente plus vite qu'un
   numéro de section. */
.qb-hero{display:flex;flex-wrap:wrap;gap:1.5rem;justify-content:space-between;
  align-items:center;padding:1.6rem 1.8rem;margin:0 0 1.25rem;
  border-radius:1.1rem;color:#fff;
  background:linear-gradient(120deg,#0f172a 0%,#1e3a8a 55%,#1d4ed8 100%);
  box-shadow:0 10px 30px -12px rgba(15,23,42,.55)}
.qb-hero-txt{flex:1 1 22rem;min-width:0}
.qb-hero .k{margin:0;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:#93c5fd;font-weight:700}
.qb-hero h1{margin:.2rem 0 .35rem;font-size:2rem;font-weight:800;line-height:1.1;
  letter-spacing:-.02em}
.qb-hero .s{margin:0;font-size:.9rem;color:#dbeafe;line-height:1.55}
.qb-hero-tags{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.8rem}
.qb-hero-tags .t{font-size:.72rem;padding:.2rem .6rem;border-radius:99px;
  background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22)}
.qb-hero-stats{display:flex;gap:.6rem;flex-wrap:wrap}
.qb-stat{min-width:5.6rem;padding:.7rem .85rem;border-radius:.8rem;text-align:center;
  background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.16)}
.qb-stat b{display:block;font-size:1.7rem;font-weight:800;line-height:1}
.qb-stat span{font-size:.7rem;color:#dbeafe}
.qb-stat.al b{color:#fca5a5} .qb-stat.vg b{color:#fcd34d}
.qb-stat.ok b{color:#6ee7b7} .qb-stat.nd b{color:#cbd5e1}

.qb-fams{display:grid;gap:.875rem;margin:0 0 1.5rem;
  grid-template-columns:repeat(auto-fit,minmax(15rem,1fr))}
.qb-fam{display:block;position:relative;padding:1rem 1.1rem .9rem;
  border:1px solid #e2e8f0;border-top:3px solid var(--fc);border-radius:.9rem;
  background:#fff;text-decoration:none;color:inherit;overflow:hidden;
  box-shadow:0 1px 2px rgba(15,23,42,.05);transition:transform .12s,box-shadow .12s}
.qb-fam:hover{transform:translateY(-2px);box-shadow:0 8px 20px -10px rgba(15,23,42,.35)}
.qb-fam .ic{font-size:1.4rem;line-height:1}
.qb-fam .co{position:absolute;top:.5rem;right:.9rem;font-size:2.6rem;font-weight:800;
  color:var(--fc);opacity:.12;line-height:1}
.qb-fam h3{margin:.45rem 0 .2rem;font-size:.95rem;font-weight:700;color:#0f172a;
  letter-spacing:-.01em}
.qb-fam p{margin:0 0 .55rem;font-size:.78rem;color:#64748b}
.qb-fam p b.al{color:#dc2626} .qb-fam p b.vg{color:#b45309}
.qb-fam p b.ok{color:#059669}
.qb-jauge{display:flex;height:.4rem;border-radius:99px;overflow:hidden;
  background:#eef2f7}
.qb-jauge i{display:block;height:100%}

.qb-sec{margin:2.2rem 0 0;scroll-margin-top:1rem}
.qb-sec-h{display:flex;align-items:center;gap:.9rem;padding:0 0 .7rem;
  border-bottom:2px solid var(--fc);margin-bottom:1rem}
.qb-sec-h .lettre{font-size:2.6rem;font-weight:800;color:var(--fc);opacity:.22;
  line-height:1;flex:0 0 auto}
.qb-sec-h h2{margin:0;font-size:1.2rem;font-weight:800;color:var(--fc);
  letter-spacing:-.02em}
.qb-sec-h p{margin:.15rem 0 0;font-size:.82rem;color:#64748b;font-style:italic;
  line-height:1.5;max-width:60rem}

.qb-cards{display:grid;gap:.875rem;
  grid-template-columns:repeat(auto-fit,minmax(20rem,1fr))}
.qb-ind{background:#fff;border:1px solid #e2e8f0;border-radius:.9rem;
  padding:1rem 1.1rem;box-shadow:0 1px 2px rgba(15,23,42,.05);
  border-left:4px solid #cbd5e1;display:flex;flex-direction:column}
.qb-ind.al{border-left-color:#ef4444} .qb-ind.vg{border-left-color:#f59e0b}
.qb-ind.ok{border-left-color:#10b981} .qb-ind.nd{border-left-color:#cbd5e1}
.qb-ind header{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.qb-ind header .num{font-size:.72rem;font-weight:800;padding:.15rem .45rem;
  border-radius:.35rem;letter-spacing:.02em}
.qb-ind header h3{flex:1 1 9rem;margin:0;font-size:.93rem;font-weight:700;
  color:#0f172a;letter-spacing:-.01em}
.qb-ind .badge{font-size:.66rem;font-weight:800;text-transform:uppercase;
  letter-spacing:.05em;padding:.18rem .5rem;border-radius:99px}
.badge.al{background:#fee2e2;color:#b91c1c} .badge.vg{background:#fef3c7;color:#92400e}
.badge.ok{background:#d1fae5;color:#047857} .badge.nd{background:#f1f5f9;color:#64748b}
.qb-mesure{display:flex;align-items:flex-end;gap:1rem;flex-wrap:wrap;
  margin:.7rem 0 .1rem}
.qb-mesure .v{font-size:2rem;font-weight:800;color:#0f172a;line-height:1;
  font-variant-numeric:tabular-nums;letter-spacing:-.03em}
.qb-mesure .v span{display:block;font-size:.7rem;font-weight:600;color:#94a3b8;
  letter-spacing:0;margin-top:.2rem}
.qb-mesure .ref{flex:1 1 9rem;font-size:.76rem;color:#475569;background:#f8fafc;
  border:1px solid #e2e8f0;border-radius:.5rem;padding:.35rem .55rem;line-height:1.4}
.qb-mesure .ref b{display:block;font-size:.64rem;text-transform:uppercase;
  letter-spacing:.06em;color:#94a3b8}
.qb-ccl{margin:.7rem 0 0;padding:.45rem .65rem;border-radius:.5rem;
  font-size:.82rem;font-weight:600;line-height:1.5}
.qb-ccl.al{background:#fef2f2;color:#991b1b} .qb-ccl.vg{background:#fffbeb;color:#92400e}
.qb-ccl.ok{background:#ecfdf5;color:#065f46} .qb-ccl.nd{background:#f8fafc;color:#64748b}
.qb-pr{margin:.6rem 0 0;font-size:.8rem;color:#64748b;line-height:1.6;
  text-align:justify}
.qb-det{margin-top:.7rem;border-top:1px dashed #e2e8f0;padding-top:.5rem}
.qb-det>summary{cursor:pointer;font-size:.76rem;font-weight:700;color:#2563eb;
  list-style:none;user-select:none}
.qb-det>summary::-webkit-details-marker{display:none}
.qb-det>summary::before{content:"▸ ";transition:.15s}
.qb-det[open]>summary::before{content:"▾ "}
.qb-f{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.74rem;
  background:#0f172a;color:#e2e8f0;padding:.55rem .7rem;border-radius:.45rem;
  margin:.5rem 0;overflow-x:auto;line-height:1.7}
.qb-calc,.qb-seuils{margin:.4rem 0 0;padding-left:1.1rem;font-size:.78rem;
  color:#475569;line-height:1.6}
.qb-calc li,.qb-seuils li{margin-bottom:.2rem}
.qb-st{margin:.7rem 0 0;font-size:.66rem;font-weight:800;text-transform:uppercase;
  letter-spacing:.06em;color:#94a3b8}
.qb-cov td{vertical-align:middle}
.qb-bt{position:relative;min-width:9rem}
.qb-bt .v{font-size:.76rem;font-weight:700;color:#334155;
  font-variant-numeric:tabular-nums}
.qb-bt i{display:block;height:.35rem;border-radius:99px;margin-top:.2rem}
.qb-garde{margin:2.2rem 0 0;padding:1.1rem 1.3rem;border-radius:.9rem;
  background:#fffbeb;border:1px solid #fde68a;color:#78350f}
.qb-garde h3{margin:0 0 .5rem;font-size:.95rem;font-weight:800}
.qb-garde ol{margin:0;padding-left:1.2rem;font-size:.84rem;line-height:1.7}
.qb-garde p{margin:.7rem 0 0;font-size:.84rem}
/* Fiche agent : mêmes briques, deux ajouts propres à elle — le bandeau vert
   sombre qui la distingue au premier coup d'œil de la page « base », et le
   quatrième état « résultat de zone », qui n'est ni conforme ni en alerte mais
   ne parle pas de l'agent. */
.qa-hero{background:linear-gradient(120deg,#052e2b 0%,#0f766e 55%,#0d9488 100%)}
.qa-hero .k{color:#99f6e4} .qa-hero .s{color:#ccfbf1}
.qb-hero-tags .t.warn{background:rgba(251,191,36,.22);
  border-color:rgba(251,191,36,.5);color:#fef3c7;font-weight:700}
.qb-stat.rem b{color:#93c5fd}
.qb-ind.rem{border-left-color:#3b82f6}
.badge.rem{background:#dbeafe;color:#1e40af}
.qb-ccl.rem{background:#eff6ff;color:#1e40af}
.qa-rem{margin:.6rem 0 0;padding:.45rem .65rem;border-radius:.5rem;
  background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af;font-size:.78rem;
  line-height:1.5}
.qa-stat{display:inline-block;margin-left:.3rem;padding:.05rem .35rem;
  border-radius:.3rem;background:#e2e8f0;color:#334155;font-weight:700;
  font-size:.7rem;font-variant-numeric:tabular-nums}
.qa-garde{background:#f0fdfa;border-color:#99f6e4;color:#115e59}
.qa-garde.warn{background:#fffbeb;border-color:#fde68a;color:#78350f}
.qa-garde h3{font-size:.92rem}
.qa-garde p{margin:.4rem 0 0;font-size:.84rem;line-height:1.6}
.qa-ctx .vad-kpi{margin-bottom:0}
.qa-retour{display:inline-block;margin:0 0 .9rem;font-size:.82rem;
  font-weight:700;color:#2563eb;text-decoration:none}
.qa-retour:hover{text-decoration:underline}
@media(max-width:640px){
  .qb-hero{padding:1.2rem}.qb-hero h1{font-size:1.5rem}
  .qb-mesure .v{font-size:1.6rem}.qb-sec-h .lettre{font-size:2rem}
}
</style>"""


# ---------------------------------------------------------------------------
# Briques
# ---------------------------------------------------------------------------
def _n(v, suffixe=""):
    """Nombre affichable : espace fine comme séparateur de milliers, — si vide."""
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    else:
        s = f"{v:,}".replace(",", " ")
    return s + suffixe


def _kpi(libelle, valeur, sous="", genre="info"):
    return (f'<div class="vad-card {genre}"><div class="l">{ESC(libelle)}</div>'
            f'<div class="v">{valeur}</div>'
            + (f'<div class="s">{sous}</div>' if sous else "") + '</div>')


def _box(titre, sous, contenu):
    return (f'<div class="vad-box"><h3>{ESC(titre)}</h3>'
            + (f'<p class="sub">{sous}</p>' if sous else "")
            + contenu + '</div>')


def _canvas(cid, classe="vad-wrap"):
    return f'<div class="{classe}"><canvas id="{cid}"></canvas></div>'


def _table(colonnes, lignes, numeriques=()):
    """Tableau HTML. `colonnes` = [(clef, libellé)], `numeriques` = clefs à droite."""
    th = "".join(f'<th class="{"n" if c in numeriques else ""}">{ESC(l)}</th>'
                 for c, l in colonnes)
    tr = []
    for r in lignes:
        tds = []
        for c, _l in colonnes:
            v = r.get(c)
            cls = ' class="n"' if c in numeriques else ""
            tds.append(f'<td{cls}>{v if isinstance(v, str) else _n(v)}</td>')
        tr.append("<tr>" + "".join(tds) + "</tr>")
    corps = "".join(tr) or ('<tr><td colspan="%d" style="text-align:center;'
                            'color:#94a3b8;padding:1.5rem">Aucune donnée</td></tr>'
                            % len(colonnes))
    return ('<div class="vad-scroll"><table class="vad-t"><thead><tr>' + th
            + "</tr></thead><tbody>" + corps + "</tbody></table></div>")


def _table_repartition(rep, libelle="Modalité", unite="Ménages"):
    """Tableau d'une répartition. `unite` = ce que l'on COMPTE (« Ménages » pour
    une question posée au ménage, « Personnes » pour une question posée au
    membre) : les confondre fausserait la lecture."""
    lignes = [{"lib": ESC(l["lib"]), "n": l["n"],
               "pct": (f'{_n(l["pct"])} %' if l["pct"] is not None else "—")}
              for l in rep["lignes"]]
    return _table([("lib", libelle), ("n", unite), ("pct", "%")],
                  lignes, numeriques=("n", "pct"))


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _p_general(a):
    g = a["global"]
    c, ld = g["couverture"], g["lienDen"]
    cons = g["consentement"]
    rg = a.get("rgph", {})
    # Taille moyenne du RGPH-3 2018 sur le MÊME périmètre, en regard de celle
    # des ménages enregistrés. Absente si les tables RGPH ne sont pas chargées.
    sous_taille = f'taille moyenne {_n(g["taille"]["moy"])}'
    if rg.get("disponible") and rg.get("taille"):
        sous_taille += f' · RGPH-3 2018 : {_n(rg["taille"])}'
    h = ['<div class="vad-kpi">',
         _kpi("Ménages interviewés", _n(g["menages"]),
              f'{_n(g["jours"])} jour(s) de collecte', "info"),
         _kpi("Membres enregistrés", _n(g["membres"]), sous_taille, "info"),
         _kpi("Couverture du dénombrement",
              (f'{_n(c["taux"])} %' if c["taux"] is not None else "—"),
              f'{_n(c["vad"])} visités / {_n(c["denombres"])} dénombrés',
              "ok" if (c["taux"] or 0) >= 80 else "warn"),
         _kpi("Agents actifs", _n(g["agents"]),
              (f'{_n(round(g["menages"] / g["agents"], 1))} ménages/agent'
               if g["agents"] else ""), "info"),
         _kpi("Durée moyenne d'entretien",
              (f'{_n(g["duree"]["moy"])} min' if g["duree"]["moy"] else "—"),
              (f'médiane {_n(g["duree"]["med"])} min' if g["duree"]["med"] else ""),
              "info"),
         '</div>']
    if ld["suspect"]:
        h.append('<div class="vad-note vad-attention"><b>Lien avec le dénombrement '
                 'peu fiable.</b> '
                 f'{_n(ld["avec"])} ménage(s) portent un code de dénombrement, mais '
                 f'seulement <b>{_n(ld["distincts"])}</b> code(s) DISTINCT(s) : le '
                 'préchargement du questionnaire n\'a pas fonctionné. Le '
                 'rapprochement VAD ↔ dénombrement est donc inexploitable en '
                 'l\'état.</div>')
    h.append('<div class="vad-grid">')
    h.append(_box("Avancement quotidien",
                  "Ménages interviewés par jour, et cumul",
                  _canvas("ch-jour")))
    h.append(_box("Statut des interviews",
                  "Tel que remonté par Survey Solutions",
                  _canvas("ch-statut")))
    h.append('</div><div class="vad-grid">')
    h.append(_box("Consentements",
                  "Accord donné pour l'enregistrement au RSU et par les individus",
                  _table([("lib", "Consentement"), ("oui", "Oui"), ("non", "Non")],
                         [{"lib": "Enregistrement RSU", "oui": cons["rsu_oui"],
                           "non": cons["rsu_non"]},
                          {"lib": "Consentement individuel", "oui": cons["indiv_oui"],
                           "non": cons["indiv_non"]}],
                         numeriques=("oui", "non"))))
    h.append(_box("Type de ménage", "Liste e-Fokontany ou nouveau ménage",
                  _table_repartition(g["typemen"], "Type")))
    h.append('</div><div class="vad-grid">')
    lignes_com = g["parCommune"]
    cols_com = [("zone", "Commune"), ("menages", "Ménages"),
                ("membres", "Membres"), ("taille", "Taille moy.")]
    if rg.get("disponible"):
        par = rg["parCommune"]
        for l in lignes_com:
            l["taille_rgph"] = par.get(l.get("code"))
        cols_com.append(("taille_rgph", "Taille RGPH 2018"))
    h.append(_box("Par commune", "Ménages et membres interviewés"
                  + (" — « Taille RGPH 2018 » : même commune au recensement, "
                     "pour comparaison" if rg.get("disponible") else ""),
                  _table(cols_com, lignes_com,
                         numeriques=("menages", "membres", "taille", "taille_rgph"))))
    h.append(_box("Par fokontany", "Ménages et membres interviewés",
                  _table([("zone", "Fokontany"), ("menages", "Ménages"),
                          ("membres", "Membres"), ("taille", "Taille moy.")],
                         g["parFokontany"], numeriques=("menages", "membres", "taille"))))
    h.append('</div>')
    return "".join(h)


def _sai_filtres(pref, regles, avec_membre=False):
    """Barre de filtres d'un listing. Le filtrage se fait dans le navigateur :
    les volumes sont petits (quelques centaines de lignes) et l'utilisateur
    garde une réponse immédiate, sans aller-retour serveur."""
    opts = "".join(f'<option value="{ESC(r["code"])}">{ESC(r["lib"])}</option>'
                   for r in regles)
    rech = ("nom du chef, nom du membre ou clé d'interview" if avec_membre
            else "nom du chef de ménage ou clé d'interview")
    return (
        f'<div class="sai-filtres" id="f-{pref}">'
        f'<label>District<select data-f="district"><option value="">Tous</option></select></label>'
        f'<label>Commune<select data-f="commune"><option value="">Toutes</option></select></label>'
        f'<label>Fokontany<select data-f="fokontany"><option value="">Tous</option></select></label>'
        f'<label>Chef d\'équipe<select data-f="ce"><option value="">Tous</option></select></label>'
        f'<label>Agent (AE)<select data-f="agent"><option value="">Tous</option></select></label>'
        f'<label>Type d\'erreur<select data-f="erreur"><option value="">Tous</option>{opts}</select></label>'
        f'<label>Statut<select data-f="statut"><option value="">Tous</option></select></label>'
        f'<label>Du<input type="date" data-f="du"></label>'
        f'<label>Au<input type="date" data-f="au"></label>'
        f'<label>Recherche<input type="search" data-f="q" placeholder="{rech}"></label>'
        f'<button type="button" data-raz="1">Réinitialiser</button>'
        f'</div>'
        f'<p class="sai-compte" id="c-{pref}"></p>'
        f'<div class="sai-scroll"><table class="sai-tbl" id="t-{pref}">'
        f'<thead></thead><tbody></tbody></table>'
        f'<div class="sai-vide" id="v-{pref}" hidden>Aucune ligne ne correspond aux filtres.</div>'
        f'</div>')


# Couleur et pictogramme de chacun des sept niveaux du document. Même parti
# que la page « Qualité de la base » : sur une fiche qui compte plus de
# quarante tests, la couleur porte la navigation mieux qu'un numéro.
STYLE_NIVEAU = {
    1: ("#0891b2", "📋"), 2: ("#2563eb", "👥"), 3: ("#7c3aed", "🔄"),
    4: ("#ea580c", "🏚️"), 5: ("#059669", "🧰"), 6: ("#dc2626", "🔍"),
    7: ("#db2777", "🕳️"),
}


def _qa_etat(t):
    """(classe, libellé du badge) d'un test de la fiche agent.

    Quatre états, et le quatrième — « remonté » — n'est pas une nuance de
    style : un test calculé sur le chef d'équipe ou la commune décrit cet
    ensemble et PAS l'agent. Il porte donc sa propre couleur, bleue, pour
    qu'une alerte de commune ne soit jamais lue comme une alerte d'agent."""
    if t["insuffisant"]:
        return "nd", "Non calculé"
    if t["remonte"]:
        return "rem", "Résultat de zone"
    if t["alerte"]:
        return "al", "Alerte"
    if t.get("vigilance"):
        return "vg", "À surveiller"
    return "ok", "Conforme"


def _qa_test(t, couleur="#475569"):
    """Un test, en CARTE : le verdict d'abord, la démonstration au clic.

    L'ancienne mise en page reprenait celle de la documentation technique —
    titre, principe, formule, encadré de calcul, encadré de seuils — pour
    chacun des quarante-six tests. C'est la bonne forme pour un document qu'on
    lit une fois de bout en bout ; c'est la mauvaise pour une fiche qu'un chef
    d'équipe ouvre entre deux visites. Le raisonnement n'est pas retiré, il est
    replié."""
    cls, badge = _qa_etat(t)
    val = ("—" if t["insuffisant"] or t["valeur"] is None
           else _qa_nb(t["valeur"]))
    h = [f'<article class="qb-ind {cls}">',
         f'<header><span class="num" style="background:{couleur}1a;'
         f'color:{couleur}">{ESC(t["num"])}</span>',
         f'<h3>{ESC(t["titre"])}</h3>',
         f'<span class="badge {cls}">{ESC(badge)}</span></header>']
    if t["remonte"]:
        h.append('<p class="qa-rem">Effectif insuffisant pour l\'agent '
                 f'(minimum {_n(t["nMin"])}). Le calcul porte sur '
                 f'<b>{ESC(t["porteeLib"])}</b> : ce résultat décrit cet '
                 "ensemble, <b>pas l'agent</b>"
                 + (", et l'écart constaté ne lui est donc pas imputable."
                    if t["alerte"] else ".") + "</p>")
    h.append('<div class="qb-mesure">'
             f'<div class="v">{ESC(val)}<span>{ESC(t["unite"] or "indice")}'
             "</span></div>")
    rep_ = t.get("repere") or ""
    if rep_ or t.get("stat"):
        h.append('<div class="ref"><b>Repère</b>'
                 + ESC(rep_ or "—")
                 + (f' <span class="qa-stat">{ESC(t["stat"])}</span>'
                    if t.get("stat") else "") + "</div>")
    h.append("</div>")
    if t["conclusion"]:
        h.append(f'<p class="qb-ccl {cls}">{ESC(t["conclusion"])}</p>')
    h.append(f'<p class="qb-pr">{ESC(t["principe"])}</p>')
    det = []
    if t["formule"]:
        det.append('<div class="qb-f">'
                   + "<br>".join(ESC(x) for x in t["formule"]) + "</div>")
    if t["calcul"]:
        det.append('<ul class="qb-calc">'
                   + "".join(f"<li>{ESC(x)}</li>" for x in t["calcul"]) + "</ul>")
    if t["seuils"]:
        det.append('<p class="qb-st">Seuil(s) d\'alerte</p>'
                   '<ul class="qb-seuils">'
                   + "".join(f"<li>{ESC(x)}</li>" for x in t["seuils"]) + "</ul>")
    if det:
        det.append(f'<p class="qb-st">Effectif requis : n ≥ {_n(t["nMin"])} '
                   f'· disponible : {_n(t["n"])}</p>')
        h.append('<details class="qb-det"><summary>Comment c\'est calculé'
                 "</summary>" + "".join(det) + "</details>")
    h.append("</article>")
    return "".join(h)


def _uq(x):
    """Valeur prête pour une query string (les codes CE/AE peuvent contenir
    des espaces ou des accents)."""
    return urllib.parse.quote(str(x or ""), safe="")


def _qa_nb(x):
    """Nombre à la française, comme dans le document."""
    if x is None:
        return "—"
    if isinstance(x, float) and x != int(x):
        return f"{x:,.2f}".replace(",", " ").replace(".", ",")
    return f"{int(x):,}".replace(",", " ")


def _qm_nb(x):
    """Nombre compact pour une case du tableau : décimales selon la grandeur.

    Un indice de Whipple s'écrit 167, un taux 46,7 %, une distance K-S 0,012 —
    deux décimales fixes donnaient « 34,55 % » et « 0,01 »."""
    if x is None:
        return "—"
    a = abs(x)
    if a == 0:
        return "0"                       # « 0 », jamais « 0,000 »
    d = 0 if a >= 100 else 1 if a >= 1 else 3
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _qm_cellule(c, col):
    """Une case de la matrice : la valeur, sa couleur, et de quoi la comprendre.

    « nd » n'est pas un trou : c'est un résultat, celui d'un effectif trop
    faible pour que le test dise quoi que ce soit. L'infobulle donne alors
    l'effectif observé et le minimum requis, pour qu'on sache s'il manque
    2 ménages ou 25."""
    g = {"alerte": "al", "vigilance": "vg"}.get(c["g"], c["g"])
    if g == "nd":
        txt = "nd"
        # Infobulle volontairement TÉLÉGRAPHIQUE : elle est répétée sur des
        # milliers de cases (4 771 sur 4 872 au district 5201 aujourd'hui) ;
        # la phrase complète pesait à elle seule ~130 Ko de page.
        info = f'{col["num"]} · n = {c["n"]} / {c["nMin"]} requis'
    else:
        # La case porte la MESURE puis, entre parenthèses, la STATISTIQUE DE
        # TEST quand le seuil est relatif à la référence : « 15,6 % (Z = 2,73) ».
        # Sans elle, deux agents affichant « 0,0 % » pouvaient être l'un vert
        # et l'autre rouge sans que rien, dans la case, ne l'explique.
        txt = _qm_nb(c["v"])
        if c["v"] is not None and col["unite"] in ("%", "min"):
            txt += " " + col["unite"]
        # Le REPÈRE (référence, seuils, effectifs) complète l'infobulle.
        info = (f'{col["num"]} — {c["c"]} (n = {c["n"]}'
                + (f' · {c["r"]}' if c.get("r") else "") + ")")
    st = (f' <span class="qm-s">({ESC(c["s"])})</span>'
          if c.get("s") and g != "nd" else "")
    return f'<td class="c {g}" title="{ESC(info)}">{ESC(txt)}{st}</td>'


def _qm_reference(l):
    """Cellule « Comparé à » : la zone de référence de cet agent.

    Elle n'est pas décorative. Une case rouge ne veut pas dire la même chose
    selon que l'agent a été comparé à son fokontany — où seul lui varie — ou,
    faute de pair, à sa commune, où le village pèse encore sur le résultat. Le
    superviseur qui va parler à l'agent doit voir laquelle des deux il lit."""
    lib = l.get("reference") or "—"
    nb = l.get("referenceMenages") or 0
    if l.get("referenceRemonte"):
        return (f'<td class="f2" style="color:#b45309" title="Cet agent est '
                f'seul dans son fokontany : aucun pair auquel le comparer. La '
                f'référence remonte à la commune ({nb} ménages), où une part '
                f'de l\'écart peut venir du village. À interpréter avec '
                f'prudence.">⚠ commune · {ESC(lib)}</td>')
    return (f'<td class="f2" style="color:#475569" title="Comparé aux '
            f'{nb} ménages de son fokontany.">fokontany · {ESC(lib)}</td>')


def _p_qualite_matrice(q, pref):
    """La MATRICE : une ligne par agent, une colonne par test.

    Elle remplace la sélection préalable d'un agent : on voit toute l'équipe
    d'un coup, et on ouvre la fiche détaillée en cliquant une ligne. Chaque
    cellule est calculée STRICTEMENT sur l'agent de la ligne — jamais remontée
    à son chef d'équipe — pour qu'une couleur n'engage que lui."""
    m = q.get("matrice") or {}
    cols, lignes, res = m.get("colonnes", []), m.get("lignes", []), m.get("resume", {})
    if not lignes:
        return ('<div class="qa-msg">Aucun agent dans ce périmètre : '
                'rien à tester.</div>')
    lg = lambda cl, n, t: (f'<span class="qm-lg {cl}"><i></i>{_n(n)} {t}</span>')
    h = ['<div class="qm-bar"><div>',
         lg("al", res.get("alerte", 0), "en alerte"),
         lg("vg", res.get("vigilance", 0), "à surveiller"),
         lg("ok", res.get("ok", 0), "conformes"),
         lg("nd", res.get("nd", 0), "non calculés"),
         '</div><div class="qm-out">',
         '<input type="search" id="qm-f" placeholder="Filtrer un CE ou un agent…">',
         '<label><input type="checkbox" id="qm-a"> Alertes seulement</label>',
         '</div></div>',
         f'<p class="qm-note"><b>{_n(m.get("agents", 0))} agent(s)</b>, '
         f'{len(cols)} test(s). Chaque case porte sur <b>cet agent seul</b> : '
         'si son effectif n\'atteint pas le minimum du test, la case vaut '
         '<b>nd</b> — le résultat de son équipe n\'y est jamais substitué. '
         'Chaque agent est comparé aux ménages de <b>son fokontany</b>, la zone '
         'où l\'habitat, les matériaux et le niveau de vie sont comparables : '
         'un écart s\'impute alors à l\'agent et non à son village. Un agent '
         'seul dans son fokontany n\'y a pas de pair ; il est alors comparé à '
         'sa commune, et la colonne « Comparé à » le signale. '
         '<b>Cliquez une ligne</b> pour le détail des calculs. '
         '<br>Cette batterie est <b>resserrée</b> : les tests sans support dans '
         'le questionnaire, ceux que Survey Solutions garantit déjà à la saisie '
         'et les doublons statistiques ont été retirés du tableau — ils restent '
         'dans la fiche de l\'agent. Plusieurs seuils ont été <b>recalibrés</b> '
         'sur la distribution réellement observée : ceux du document, écrits '
         'pour des comparaisons de zone, désignaient jusqu\'à 75 % des agents '
         'sur un même test.</p>',
         '<div class="qm-wrap"><table class="qm"><thead>']
    # Premier rang : les NIVEAUX du document, chacun couvrant ses tests. Sur
    # 15 colonnes, sans ce rang on ne sait plus ce qu'on lit.
    groupes = []
    for c in cols:
        if groupes and groupes[-1][0] == c["niveau"]:
            groupes[-1][2] += 1
        else:
            groupes.append([c["niveau"], c["niveauTitre"], 1])
    h.append('<tr class="qm-niv"><th class="f1"></th><th class="f2"></th><th></th>')
    for num, titre, n in groupes:
        h.append(f'<th colspan="{n}">Niveau {num} — {ESC(titre)}</th>')
    h.append('</tr><tr>')
    h.append('<th class="f1">Chef d\'équipe (CE)</th>')
    h.append('<th class="f2">Agent enquêteur (AE)</th>')
    h.append('<th>Ménages</th>')
    h.append('<th title="Zone à laquelle cet agent est comparé. Le fokontany '
             'est la zone de dénombrement : habitat, matériaux et niveau de '
             'vie y sont homogènes, donc un écart y désigne l\'agent. Un '
             'agent seul dans son fokontany est comparé à sa commune — un '
             'écart peut alors venir du village autant que de lui.">'
             'Comparé à</th>')
    for c in cols:
        info = (f'{c["titre"]}. {c["principe"]} — Alerte : '
                + " ; ".join(c["seuils"]) + f'. Vigilance : {c["vigilance"]}. '
                f'Effectif minimal : {c["nMin"]}.')
        court = c["titre"] if len(c["titre"]) <= 34 else c["titre"][:33] + "…"
        h.append(f'<th title="{ESC(info)}"><span>{ESC(c["num"])} '
                 f'{ESC(court)}</span><small>{ESC(c["unite"] or "indice")} · '
                 f'n ≥ {c["nMin"]}</small></th>')
    h.append('</tr></thead><tbody>')
    ncols = 4 + len(cols)
    commune = None
    for l in lignes:
        if l["commune"] != commune:
            commune = l["commune"]
            h.append(f'<tr class="qm-com"><td colspan="{ncols}">'
                     f'{ESC(commune)}</td></tr>')
        url = (f'{pref}/vad/qualite?commune={_uq(l["commune"])}'
               f'&ce={_uq(l["ce"])}&ae={_uq(l["ae"])}')
        al = "1" if any(c["g"] == "alerte" for c in l["cellules"]) else "0"
        cle = ESC((l["ce"] + " " + l["ae"]).lower())
        h.append(f'<tr data-al="{al}" data-k="{cle}" data-u="{ESC(url)}">'
                 f'<td class="f1">{ESC(l["ce"])}</td>'
                 f'<td class="f2"><a href="{ESC(url)}">{ESC(l["ae"])}</a></td>'
                 f'<td class="num">{_n(l["menages"])}</td>'
                 + _qm_reference(l))
        h.extend(_qm_cellule(c, cols[i]) for i, c in enumerate(l["cellules"]))
        h.append('</tr>')
    h.append('</tbody></table></div>'
             '<div class="qm-vide" id="qm-vide" style="display:none">'
             'Aucun agent ne correspond à ce filtre.</div>')
    return "".join(h)


_GRAV = {
    "alerte":    ("al", "#ef4444", "Alerte", "à traiter"),
    "vigilance": ("vg", "#f59e0b", "À surveiller", "à confirmer"),
    "ok":        ("ok", "#10b981", "Conforme", "rien à signaler"),
    "nd":        ("nd", "#94a3b8", "Non calculé", "effectif ou source manquants"),
}


def _qb_jauge(c):
    """Barre empilée alerte / vigilance / conforme / non calculé, en pourcentage."""
    t = c["total"] or 1
    seg = [(c["alerte"], "#ef4444"), (c["vigilance"], "#f59e0b"),
           (c["ok"], "#10b981"), (c["nd"], "#cbd5e1")]
    return ('<div class="qb-jauge">'
            + "".join(f'<i style="width:{100.0 * v / t:.4g}%;background:{col}"></i>'
                      for v, col in seg if v)
            + "</div>")


def _qb_ind(i, couleur):
    """Un indicateur, en CARTE : le verdict d'abord, la démonstration au clic.

    L'ancienne version empilait principe, formule, calcul et seuils pour les
    vingt-cinq indicateurs : quatre écrans de texte gris avant d'apprendre
    quoi que ce soit. Ici la carte tient le résultat — valeur, référence,
    conclusion — et le raisonnement se déplie pour qui le conteste. C'est
    l'ordre dans lequel on lit un tableau de bord, pas une note méthodologique."""
    cls, coul, badge, _s = _GRAV.get(i["gravite"], _GRAV["ok"])
    val = ("—" if i["valeur"] is None else _qa_nb(i["valeur"]))
    h = [f'<article class="qb-ind {cls}">',
         '<header><span class="num" style="background:', couleur, '1a;color:',
         couleur, f'">{ESC(i["num"])}</span>',
         f'<h3>{ESC(i["titre"])}</h3>',
         f'<span class="badge {cls}">{badge}</span></header>',
         '<div class="qb-mesure">',
         f'<div class="v">{ESC(val)}<span>{ESC(i["unite"])}</span></div>']
    if i["reference"]:
        h.append(f'<div class="ref"><b>Référence</b>{ESC(i["reference"])}</div>')
    h.append("</div>")
    if i["conclusion"]:
        h.append(f'<p class="qb-ccl {cls}">{ESC(i["conclusion"])}</p>')
    h.append(f'<p class="qb-pr">{ESC(i["principe"])}</p>')
    det = []
    if i["formule"]:
        det.append('<div class="qb-f">'
                   + "<br>".join(ESC(x) for x in i["formule"]) + "</div>")
    if i["calcul"]:
        det.append('<ul class="qb-calc">'
                   + "".join(f"<li>{ESC(x)}</li>" for x in i["calcul"]) + "</ul>")
    if i["seuils"]:
        det.append('<p class="qb-st">Seuils</p><ul class="qb-seuils">'
                   + "".join(f"<li>{ESC(x)}</li>" for x in i["seuils"]) + "</ul>")
    if det:
        h.append('<details class="qb-det"><summary>Comment c\'est calculé'
                 "</summary>" + "".join(det) + "</details>")
    h.append("</article>")
    return "".join(h)


def _p_qualite_base(a):
    """Page « Qualité de la base » : le RSU vu comme un tout.

    Elle se lit AVANT le tableau par agent. Un défaut qui touche tous les
    agents de la même façon — une variable absente, un filtre cassé, un
    déficit d'hommes adultes — ne crée aucun écart entre eux et reste donc
    invisible dans une comparaison d'agents. Il faut une référence extérieure,
    et c'est ce que cette page apporte : le RGPH-3 et les normes
    démographiques internationales.

    Trois étages de lecture, du plus rapide au plus exigeant : le bandeau et
    les six cartes de famille (cinq secondes), les graphiques (une minute),
    les fiches d'indicateurs et leurs calculs dépliables (le reste)."""
    q = a.get("qualite_base", {})
    if not q.get("disponible"):
        return ('<div class="qa-msg">Qualité de la base non calculable : '
                + ESC(q.get("erreur") or "tables VAD absentes ou incomplètes")
                + ".</div>")
    p, r, fam = q["portee"], q["resume"], q["familles"]
    tot = sum(r.values()) or 1
    sains = r["ok"] + r["vigilance"]
    note = round(100.0 * r["ok"] / tot)
    # Le bandeau : un chiffre, une phrase, et de quoi situer le périmètre.
    if r["alerte"] == 0:
        titre_v, sous_v = "Aucune alerte", "le RSU passe tous les contrôles"
    elif r["alerte"] <= 3:
        titre_v = f'{r["alerte"]} point' + ("s" if r["alerte"] > 1 else "")
        sous_v = "à examiner avant exploitation"
    else:
        titre_v, sous_v = f'{r["alerte"]} alertes', "le RSU demande un arbitrage"
    h = ['<section class="qb-hero">',
         '<div class="qb-hero-txt">',
         '<p class="k">Contrôle qualité des données RSU</p>',
         f'<h1>{ESC(titre_v)}</h1>',
         f'<p class="s">{ESC(sous_v)} — {_n(tot)} indicateurs passés sur '
         f'{_n(p["menages"])} ménages, {_n(p["membres"])} membres, '
         f'{_n(p["communes"])} communes.</p>',
         '<div class="qb-hero-tags">',
         f'<span class="t">RGPH-3 {"chargé" if p["rgph"] else "absent"}</span>',
         f'<span class="t">{_n(p["rejetes"])} interview(s) rejetée(s), exclue(s)</span>',
         f'<span class="t">{_n(note)} % de contrôles verts</span>',
         "</div></div>",
         '<div class="qb-hero-stats">']
    for g, lib in (("alerte", "en alerte"), ("vigilance", "à surveiller"),
                   ("ok", "conformes"), ("nd", "non calculés")):
        cls, coul, _b, _s = _GRAV[g]
        h.append(f'<div class="qb-stat {cls}"><b>{_n(r[g])}</b>'
                 f'<span>{ESC(lib)}</span></div>')
    h.append("</div></section>")

    # --- les six familles, en cartes cliquables --------------------------
    h.append('<div class="qb-fams">')
    for f in fam:
        c, coul = f["compte"], f["couleur"]
        etat = ("al" if c["alerte"] else "vg" if c["vigilance"] else "ok")
        h.append(
            f'<a class="qb-fam {etat}" href="#fam-{f["code"]}" '
            f'style="--fc:{coul}">'
            f'<span class="ic">{f["icone"]}</span>'
            f'<span class="co">{ESC(f["code"])}</span>'
            f'<h3>{ESC(f["titre"])}</h3>'
            f'<p>{_n(c["total"])} indicateurs · '
            + (f'<b class="al">{_n(c["alerte"])} alerte'
               + ("s" if c["alerte"] > 1 else "") + "</b>"
               if c["alerte"] else
               f'<b class="vg">{_n(c["vigilance"])} à surveiller</b>'
               if c["vigilance"] else '<b class="ok">tout est vert</b>')
            + "</p>" + _qb_jauge(c) + "</a>")
    h.append("</div>")

    # --- les graphiques : ce que 25 tableaux ne montrent pas -------------
    g = q.get("graphiques") or {}
    cov = [c for c in q.get("couverture", []) if c["attendu"]]
    cartes = []
    if g.get("pyramide"):
        cartes.append(_box(
            "Pyramide des âges : RSU contre recensement",
            "En % de la population, pour que deux sources de tailles "
            "différentes soient comparables. Les barres pleines sont le RSU, "
            "le trait est le RGPH-3 2018 sur les mêmes communes."
            if g.get("rgph") else "En % de la population du RSU.",
            _canvas("qb-ch-pyr", "vad-wrap h28")))
    if cov:
        cartes.append(_box(
            "Couverture, commune par commune",
            "Ménages enquêtés rapportés aux ménages DÉNOMBRÉS. En cours de "
            "collecte, c'est l'écart entre communes qui informe, pas le niveau.",
            _canvas("qb-ch-cov", "vad-wrap h28")))
    if g.get("chiffres"):
        cartes.append(_box(
            "Sur quel chiffre les âges s'arrêtent-ils ?",
            "Chaque chiffre terminal devrait peser 10 %. Les écarts mesurent "
            "l'arrondi des âges — c'est ce que résument les indices B1 et B2.",
            _canvas("qb-ch-dig", "vad-wrap")))
    cartes.append(_box(
        "Répartition des 25 contrôles",
        "Une lecture d'ensemble du tableau de bord.",
        _canvas("qb-ch-res", "vad-wrap")))
    h.append('<div class="vad-grid">' + "".join(cartes) + "</div>")

    # --- le détail, famille par famille ----------------------------------
    for f in fam:
        coul = f["couleur"]
        h.append(f'<section class="qb-sec" id="fam-{f["code"]}" '
                 f'style="--fc:{coul}">'
                 f'<div class="qb-sec-h"><span class="lettre">{ESC(f["code"])}'
                 "</span>"
                 f'<div><h2>{f["icone"]} {ESC(f["titre"])}</h2>'
                 f'<p>{ESC(f["description"])}</p></div></div>'
                 '<div class="qb-cards">'
                 + "".join(_qb_ind(i, coul) for i in f["indicateurs"])
                 + "</div></section>")

    # --- la couverture en détail -----------------------------------------
    if cov:
        lignes = []
        mx = max(c["taux"] for c in cov) or 1
        for c in sorted(cov, key=lambda c: c["taux"]):
            larg = 100.0 * c["taux"] / mx
            coul = ("#ef4444" if c["taux"] < 25 else
                    "#f59e0b" if c["taux"] < 45 else "#10b981")
            lignes.append(
                f'<tr><td>{ESC(c["nom"])}</td>'
                f'<td class="n">{_n(c["rsu"])}</td>'
                f'<td class="n">{_n(c["attendu"])}</td>'
                f'<td class="qb-bt"><span class="v">{c["taux"]:.1f} %</span>'
                f'<i style="width:{larg:.4g}%;background:{coul}"></i></td></tr>')
        h.append(
            '<section class="qb-sec" style="--fc:#475569">'
            '<div class="qb-sec-h"><span class="lettre">∑</span>'
            "<div><h2>📊 Avancement par commune</h2>"
            "<p>Le détail de l'indicateur A1. Trié du moins couvert au mieux "
            "couvert : c'est le haut du tableau qui appelle une décision "
            "d'affectation.</p></div></div>"
            '<div class="vad-scroll"><table class="vad-t qb-cov"><thead><tr>'
            "<th>Commune</th><th class=\"n\">Enquêtés</th>"
            "<th class=\"n\">Dénombrés</th><th>Couverture</th>"
            "</tr></thead><tbody>" + "".join(lignes) + "</tbody></table></div>"
            "</section>")

    # --- les précautions de lecture, en pied de page ---------------------
    h.append(
        '<section class="qb-garde"><h3>⚠️ Trois précautions de lecture</h3>'
        "<ol><li><b>Sept ans séparent le recensement de la collecte.</b> "
        "Les écarts de <i>structure</i> sont interprétables, les écarts de "
        "<i>niveau</i> ne le sont pas.</li>"
        "<li><b>Le RSU n'est pas exhaustif.</b> On compare des proportions, "
        "jamais des totaux.</li>"
        "<li><b>Les interviews rejetées par le siège sont exclues</b> de tous "
        "les indicateurs. L'indicateur F1 en rend compte à part.</li></ol>"
        "<p>Cette page juge <b>le RSU</b>, pas les enquêteurs. Pour "
        "désigner un agent, c'est l'onglet <i>Test de qualité par agent</i>.</p>"
        "</section>")
    return "".join(h)


def _p_qualite_fiche(r, pref):
    """La fiche d'UN agent : verdict, contexte, courbes, puis les tests.

    Même parti que la page « Qualité de la base », et pour la même raison :
    quarante-six tests présentés à la file forment un mur que personne ne lit.
    Trois étages — le bandeau et les cartes de niveau se parcourent en cinq
    secondes, les quatre courbes en une minute, les fiches de test et leurs
    calculs dépliables pour qui doit justifier une remarque à l'agent."""
    # Décompte par niveau ET total, à partir des tests eux-mêmes : la fiche ne
    # reçoit pas de résumé du serveur, et le calculer ici évite de le tenir à
    # jour à deux endroits.
    tot = {"al": 0, "vg": 0, "ok": 0, "nd": 0, "rem": 0}
    par_niveau = []
    for niv in r["niveaux"]:
        c = {"al": 0, "vg": 0, "ok": 0, "nd": 0, "rem": 0}
        for t in niv["tests"]:
            c[_qa_etat(t)[0]] += 1
        for k in c:
            tot[k] += c[k]
        coul, icone = STYLE_NIVEAU.get(niv["numero"], ("#475569", "•"))
        par_niveau.append((niv, c, coul, icone))
    n_tests = sum(tot.values()) or 1

    remonte = bool(r.get("referenceRemonte"))
    zone = ESC(r.get("reference") or "—")
    if tot["al"] == 0:
        titre_v, sous_v = "Aucune alerte", "cet agent ne ressort sur aucun test"
    elif tot["al"] <= 2:
        titre_v = f'{tot["al"]} alerte' + ("s" if tot["al"] > 1 else "")
        sous_v = "à vérifier avant d'en parler à l'agent"
    else:
        titre_v, sous_v = f'{tot["al"]} alertes', "profil à examiner de près"

    h = [f'<a class="qa-retour" href="{pref}/vad/qualite">← Retour au tableau '
         "des agents</a>",
         '<section class="qb-hero qa-hero">',
         '<div class="qb-hero-txt">',
         f'<p class="k">Fiche agent · {ESC(r["ce"])} · {ESC(r["commune"])}</p>',
         f'<h1>{ESC(r["ae"])}</h1>',
         f'<p class="s"><b>{ESC(titre_v)}</b> — {ESC(sous_v)}. '
         f'{_n(n_tests)} tests passés sur {_n(r["menages"])} ménages et '
         f'{_n(r["membres"])} membres.</p>',
         '<div class="qb-hero-tags">',
         (f'<span class="t warn">⚠ comparé à sa commune · {zone}</span>'
          if remonte else f'<span class="t">comparé à son fokontany · {zone}</span>'),
         f'<span class="t">{_n(r.get("referenceMenages") or 0)} ménages de '
         "référence</span>",
         f'<span class="t">équipe du CE : {_n(r["menagesCE"])} ménages</span>',
         "</div></div>",
         '<div class="qb-hero-stats">']
    for k, lib in (("al", "en alerte"), ("vg", "à surveiller"),
                   ("ok", "conformes"), ("rem", "de zone"), ("nd", "non calculés")):
        if k == "rem" and not tot["rem"]:
            continue
        h.append(f'<div class="qb-stat {k}"><b>{_n(tot[k])}</b>'
                 f"<span>{ESC(lib)}</span></div>")
    h.append("</div></section>")

    # Comment lire la référence : la phrase change de sens selon le repli.
    h.append(
        '<div class="qb-garde qa-garde' + (" warn" if remonte else "") + '">'
        + ("<h3>⚠️ Cet agent est seul dans son fokontany</h3><p>Faute de pair "
           "auquel le comparer, la référence remonte à <b>sa commune</b>. Une "
           "part de l'écart constaté peut donc venir du village plutôt que de "
           "lui : à interpréter avec prudence avant toute remarque.</p>"
           if remonte else
           "<h3>Comment lire cette fiche</h3><p>La référence de comparaison "
           f"est <b>son fokontany</b> ({zone}) : l'habitat, les matériaux et "
           "le niveau de vie y sont homogènes, donc un écart y désigne "
           "l'agent et non son village.</p>")
        + "<p>Chaque test est calculé sur l'agent quand son effectif le "
          "permet. Sinon il remonte au chef d'équipe, puis à la commune, et la "
          "carte l'indique en bleu — <b>ce résultat-là ne vaut pas pour "
          "l'agent</b>.</p></div>")

    # --- les sept niveaux, en cartes cliquables ---------------------------
    h.append('<div class="qb-fams">')
    for niv, c, coul, icone in par_niveau:
        etat = ("al" if c["al"] else "vg" if c["vg"] else "ok")
        n = sum(c.values())
        h.append(
            f'<a class="qb-fam {etat}" href="#niv-{niv["numero"]}" '
            f'style="--fc:{coul}">'
            f'<span class="ic">{icone}</span>'
            f'<span class="co">{niv["numero"]}</span>'
            f'<h3>{ESC(niv["titre"])}</h3>'
            f'<p>{_n(n)} tests · '
            + (f'<b class="al">{_n(c["al"])} alerte'
               + ("s" if c["al"] > 1 else "") + "</b>" if c["al"] else
               f'<b class="vg">{_n(c["vg"])} à surveiller</b>' if c["vg"] else
               '<b class="ok">tout est vert</b>')
            + "</p>"
            + _qb_jauge({"alerte": c["al"], "vigilance": c["vg"],
                         "ok": c["ok"] + c["rem"], "nd": c["nd"],
                         "total": n})
            + "</a>")
    h.append("</div>")

    # --- quatre courbes : l'agent, puis sa zone ---------------------------
    g = r.get("graphiques") or {}
    cartes = []
    if g.get("pyramide"):
        cartes.append(_box(
            "Pyramide des âges : l'agent contre sa zone",
            "En % des personnes enregistrées. Les barres sont l'agent, les "
            "traits sa zone de référence. C'est la lecture visuelle des tests "
            "4.6 et 4.7.",
            _canvas("qa-ch-pyr", "vad-wrap h28")))
    if g.get("chiffres"):
        cartes.append(_box(
            "Sur quel chiffre ses âges s'arrêtent-ils ?",
            "Chaque chiffre terminal devrait peser 10 %. Un pic sur 0 et 5 "
            "signe l'âge estimé plutôt que relevé — c'est ce que mesure "
            "l'indice de Myers (test 4.2).",
            _canvas("qa-ch-dig", "vad-wrap")))
    if g.get("jours"):
        cartes.append(_box(
            "Production journalière",
            "Ménages enquêtés par jour de collecte. Un pic isolé est rarement "
            "une journée exceptionnelle : c'est plus souvent une saisie "
            "différée, qui rend les durées ininterprétables (test 3.1).",
            _canvas("qa-ch-jour", "vad-wrap")))
    if g.get("durees"):
        cartes.append(_box(
            "Durée des entretiens : l'agent contre sa zone",
            "Répartition en % de ses entretiens. Un profil décalé vers la "
            "gauche est le premier signe d'un questionnaire abrégé "
            "(tests 3.2 et 8.3).",
            _canvas("qa-ch-dur", "vad-wrap")))
    if cartes:
        h.append('<div class="vad-grid">' + "".join(cartes) + "</div>")

    # --- le détail, niveau par niveau -------------------------------------
    for niv, _c, coul, icone in par_niveau:
        h.append(
            f'<section class="qb-sec" id="niv-{niv["numero"]}" '
            f'style="--fc:{coul}">'
            f'<div class="qb-sec-h"><span class="lettre">{niv["numero"]}</span>'
            f'<div><h2>{icone} {ESC(niv["titre"])}</h2>'
            f'<p>{ESC(niv["description"])}</p></div></div>'
            '<div class="qb-cards">'
            + "".join(_qa_test(t, coul) for t in niv["tests"])
            + "</div></section>")

    # --- le contexte chiffré, en pied de page -----------------------------
    h.append(
        '<section class="qb-sec qa-ctx" style="--fc:#475569">'
        '<div class="qb-sec-h"><span class="lettre">∑</span>'
        "<div><h2>📐 Effectifs de comparaison</h2>"
        "<p>De quoi situer chaque verdict : plus l'échelon est large, moins "
        "il parle de l'agent.</p></div></div>"
        '<div class="vad-kpi">'
        + _kpi("Ménages de l'agent", _n(r["menages"]),
               f'{_n(r["membres"])} membres enregistrés', "info")
        + _kpi("Zone de référence", _n(r.get("referenceMenages") or 0),
               ("commune — agent seul dans son fokontany" if remonte
                else f'fokontany {zone}'), "warn" if remonte else "ok")
        + _kpi("Équipe du CE", _n(r["menagesCE"]), ESC(r["ce"]))
        + _kpi("Commune", _n(r["equipe"]), ESC(r["commune"]))
        + _kpi("Périmètre entier", _n(r["perimetre"]), "tous districts affichés")
        + "</div></section>")
    return "".join(h)


def _p_qualite(a):
    """Tests de qualité : la MATRICE CE × AE, puis la fiche d'un agent au clic.

    Deux états d'une même page (maj 2026-09-19) :
      - sans `?commune=&ce=&ae=` : le tableau de tous les agents du périmètre ;
      - avec : la fiche détaillée de cet agent, et un retour vers le tableau.
    Le tableau a remplacé la cascade de sélection : on ne choisit plus un agent
    pour savoir s'il pose problème, on voit d'abord ceux qui en posent."""
    q = a.get("qualite", {})
    if not q.get("disponible"):
        return ('<div class="qa-msg">Tests de qualité non calculables : '
                "les tables VAD sont absentes ou incomplètes.</div>")
    pref = config.PREFIXE
    r = q.get("resultat")
    if not r:
        cible = q.get("cible")
        avert = ""
        if cible and any(cible):
            avert = ('<div class="qa-msg">Agent introuvable dans ce périmètre — '
                     "voici le tableau complet.</div>")
        return avert + _p_qualite_matrice(q, pref)
    return _p_qualite_fiche(r, pref)


def _pc(v, d=1):
    """Pourcentage à la française, ou tiret."""
    return "—" if v is None else f"{v:,.{d}f}".replace(",", " ").replace(".", ",") + " %"


def _tab_pct(lignes, col="Catégorie", cle="lib"):
    """Petit tableau {libellé, n, pct} — le format de sortie des sections."""
    return _table([(cle, col), ("n", "Effectif"), ("pctv", "Part")],
                  [{cle: l[cle], "n": _n(l["n"]),
                    "pctv": _pc(l.get("pct"))} for l in lignes],
                  numeriques=("n", "pctv"))


def _p_handicap(a):
    h_ = a["handicap"]
    d = h_["difficulte"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi("Personnes en situation de handicap", _pc(d["pct"]),
             f'{_n(d["n"])} sur {_n(h_["renseignes"])} personnes interrogées',
             "bad" if (d["pct"] or 0) >= 5 else "warn"),
        _kpi("Quelque difficulté seulement", _pc(h_["quelque"]["pct"]),
             f'{_n(h_["quelque"]["n"])} personnes — hors définition stricte'),
        _kpi("Ménages concernés", _pc(h_["menages"]["pct"]),
             f'{_n(h_["menages"]["n"])} ménages sur {_n(h_["menages"]["total"])}',
             "warn"),
        _kpi("Carte de handicap", _n(h_["carte"]["oui"]),
             f'sur {_n(h_["difficulte"]["n"])} personnes concernées',
             "bad" if h_["carte"]["oui"] < d["n"] else "ok"),
        _kpi("Couverture du module", _pc(h_["couverture"]),
             f'{_n(h_["renseignes"])} / {_n(h_["total"])} membres du roster'),
        "</div>",
        '<div class="vad-note">Les sept questions <b>AUEM17a-g</b> du '
        "questionnaire reprennent le <b>Washington Group Short Set</b>, la "
        "norme internationale. Le taux affiché retient la définition stricte — "
        "« beaucoup de difficulté » ou « incapable » dans <b>au moins un</b> "
        "domaine —, seule comparable d'un pays à l'autre. La ligne « quelque "
        "difficulté » est comptée à part : l'inclure doublerait la prévalence "
        "sans rien dire de comparable.</div>",
        '<div class="vad-grid">',
        _box("Prévalence par domaine",
             "Part des personnes déclarant beaucoup de difficulté ou une "
             "incapacité, domaine par domaine.",
             _canvas("ch-hand-dom", "vad-wrap h20")),
        _box("Prévalence par âge",
             "Le handicap croît fortement avec l'âge : c'est le meilleur "
             "contrôle de vraisemblance de la série.",
             _canvas("ch-hand-age", "vad-wrap h20")),
        "</div><div class=\"vad-grid\">",
        _box("Par sexe", "", _tab_pct(h_["parSexe"], "Sexe")),
        _box("Par groupe d'âge", "", _tab_pct(h_["parAge"], "Groupe d'âge")),
        "</div>"])


def _p_identite(a):
    i = a["identite"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi("Acte de naissance", _pc(i["acte"]["pct"]),
             f'{_n(i["acte"]["oui"])} sur {_n(i["acte"]["total"])} personnes',
             "bad" if (i["acte"]["pct"] or 0) < 60 else "warn"),
        _kpi("Enregistrement des naissances", _pc(i["naissances"]["pct"]),
             f'enfants de moins de 5 ans ({_n(i["naissances"]["total"])})',
             "bad" if (i["naissances"]["pct"] or 0) < 60 else "ok"),
        _kpi("Carte d'identité (18 ans et +)", _pc(i["cin"]["pct"]),
             f'{_n(i["cin"]["n"])} sur {_n(i["cin"]["total"])} majeurs interrogés',
             "warn"),
        _kpi("Numéro d'identification unique", _pc(i["nui"]["pct"]),
             f'{_n(i["nui"]["n"])} personnes sur {_n(i["nui"]["total"])}',
             "bad" if (i["nui"]["pct"] or 0) < 30 else "ok"),
        _kpi("Sans aucun document", _pc(i["aucun"]["pct"]),
             f'{_n(i["aucun"]["n"])} personnes', "bad"),
        "</div>",
        '<div class="vad-note vad-attention">C\'est le thème dont dépend toute '
        "la chaîne : <b>un registre social ne peut servir que les personnes "
        "qu'il sait identifier</b>. Une personne sans acte de naissance ne peut "
        "obtenir ni carte d'identité ni compte de paiement — l'absence de "
        "document n'est pas un détail administratif, c'est une exclusion.</div>",
        '<div class="vad-grid">',
        _box("Acte de naissance par groupe d'âge",
             "Un taux qui remonte avec l'âge signale un rattrapage tardif ; un "
             "taux bas chez les tout-petits, un défaut d'enregistrement à la "
             "naissance.", _canvas("ch-id-age", "vad-wrap h20")),
        _box("Détail par âge", "", _tab_pct(i["parAge"], "Groupe d'âge")),
        "</div>"])


def _p_education(a):
    e = a["education"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi(f'Scolarisation {e["scolarisation"]["bornes"]}',
             _pc(e["scolarisation"]["pct"]),
             f'{_n(e["scolarisation"]["n"])} sur {_n(e["scolarisation"]["total"])} enfants',
             "bad" if (e["scolarisation"]["pct"] or 0) < 70 else "ok"),
        _kpi("A déjà fréquenté l'école", _pc(e["aFrequente"]["pct"]),
             f'{_n(e["aFrequente"]["n"])} sur {_n(e["aFrequente"]["total"])}'),
        _kpi("Sait lire (15 ans et +)", _pc(e["lecture"]["pct"]),
             f'{_n(e["lecture"]["n"])} sur {_n(e["lecture"]["total"])}',
             "bad" if (e["lecture"]["pct"] or 0) < 60 else "ok"),
        _kpi("Sait écrire (15 ans et +)", _pc(e["ecriture"]["pct"]),
             f'{_n(e["ecriture"]["n"])} sur {_n(e["ecriture"]["total"])}'),
        "</div>",
        '<div class="vad-note">Deux indicateurs de cette page — '
        "<b>alphabétisation</b> et <b>scolarisation des 6-14 ans</b> — existent "
        "aussi dans le RGPH-3 2018, commune par commune. La confrontation aux "
        "chiffres du recensement se fait dans l'onglet <i>Qualité de la "
        "base</i>, sur le même principe que la pyramide des âges.</div>",
        '<div class="vad-grid">',
        _box("Fréquentation scolaire par âge",
             "Part des personnes qui fréquentent actuellement un établissement.",
             _canvas("ch-edu-age", "vad-wrap h20")),
        _box("Niveau atteint", "Dernière classe fréquentée, tous âges.",
             _canvas("ch-edu-niv", "vad-wrap h20")),
        "</div><div class=\"vad-grid\">",
        _box("Scolarisation et alphabétisation par sexe",
             "L'écart entre filles et garçons est le premier signal à regarder.",
             _table([("lib", "Sexe"), ("s", "Scolarisés 6-14"),
                     ("sn", "Effectif"), ("al", "Savent lire (15+)"),
                     ("an", "Effectif")],
                    [{"lib": r["lib"], "s": _pc(r["scol"]), "sn": _n(r["scolN"]),
                      "al": _pc(r["alpha"]), "an": _n(r["alphaN"])}
                     for r in e["parSexe"]],
                    numeriques=("s", "sn", "al", "an"))),
        _box("Niveau atteint — détail", "",
             _table_repartition(e["niveau"], "Niveau")),
        "</div>"])


def _p_enfance(a):
    e = a["enfance"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi("Enfants de moins de 18 ans", _n(e["enfants"]["n"]),
             f'{_pc(e["enfants"]["pct"])} des personnes enregistrées', "info"),
        _kpi("Orphelins d'au moins un parent", _pc(e["orphelins"]["pct"]),
             f'{_n(e["orphelins"]["n"])} enfants — père {_n(e["orphelins"]["detail"]["pere"])}, '
             f'mère {_n(e["orphelins"]["detail"]["mere"])}, '
             f'les deux {_n(e["orphelins"]["detail"]["deux"])}', "bad"),
        _kpi("Déscolarisés 6-14 ans", _pc(e["deScolarises"]["pct"]),
             f'{_n(e["deScolarises"]["n"])} sur {_n(e["deScolarises"]["total"])}',
             "bad" if (e["deScolarises"]["pct"] or 0) > 25 else "warn"),
        _kpi("Sans acte de naissance", _pc(e["sansActe"]["pct"]),
             f'{_n(e["sansActe"]["n"])} enfants', "bad"),
        _kpi("En situation de handicap", _pc(e["handicap"]["pct"]),
             f'{_n(e["handicap"]["n"])} enfants', "warn"),
        _kpi("Ménages dirigés par un mineur", _n(e["chefsMineurs"]),
             "chefs de ménage de moins de 18 ans",
             "bad" if e["chefsMineurs"] else "ok"),
        "</div>",
        '<div class="vad-note vad-attention">Cette page ne mesure rien de neuf : '
        "elle <b>recoupe</b> les sections Éducation, Handicap et Identité sur "
        "les moins de 18 ans. C'est à cet âge que les critères de ciblage se "
        "cumulent, et un enfant à la fois orphelin, non scolarisé et non "
        "enregistré n'apparaît dans <b>aucune</b> des trois vues prises "
        "séparément.</div>",
        '<div class="vad-kpi">',
        _kpi("Enfants cumulant 2 vulnérabilités ou plus", _pc(e["cumul"]["pct"]),
             f'{_n(e["cumul"]["n"])} enfants sur {_n(e["cumul"]["total"])} — '
             "orphelinage, déscolarisation, absence d'acte, handicap", "bad"),
        "</div>",
        '<div class="vad-grid">',
        _box("Situation d'orphelinage", "",
             _table_repartition(e["repartitionOrphelinage"], "Situation")),
        _box("Répartition des vulnérabilités",
             "Chaque barre est une part des enfants concernés.",
             _canvas("ch-enf", "vad-wrap h20")),
        "</div>"])


def _p_activite(a):
    v = a["activite"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi(f'Activité déclarée ({v["actifs"]["borne"]})', _pc(v["actifs"]["pct"]),
             f'{_n(v["actifs"]["n"])} sur {_n(v["actifs"]["total"])} personnes'),
        _kpi("Ménages déclarant une culture", _pc(v["menagesAgricoles"]["pct"]),
             f'{_n(v["menagesAgricoles"]["n"])} sur {_n(v["menagesAgricoles"]["total"])}',
             "info"),
        _kpi("Ménages avec carte agricole", _pc(v["carteAgricole"]["pct"]),
             f'{_n(v["carteAgricole"]["n"])} sur {_n(v["carteAgricole"]["total"])}',
             "warn" if (v["carteAgricole"]["pct"] or 0) < 10 else "ok"),
        "</div>",
        '<div class="vad-note vad-attention">Les cultures (<b>PT04</b> à '
        "<b>PT06</b>) sont saisies en <b>texte libre</b> : « vary », « Vary », "
        "« VARY » et « tsako » / « katsaka » désignent les mêmes plantes. Le "
        "regroupement ci-dessous met tout en minuscules mais ne corrige ni les "
        "fautes de frappe ni les synonymes — <b>à lire comme un ordre de "
        "grandeur</b>, pas comme une statistique agricole. Une liste fermée "
        "dans le questionnaire réglerait le problème à la source.</div>",
        '<div class="vad-grid">',
        _box("Activité principale déclarée", "Personnes de 15 ans et plus.",
             _canvas("ch-act", "vad-wrap h20")),
        _box("Cultures les plus déclarées",
             "Texte libre normalisé — ordre de grandeur uniquement.",
             _canvas("ch-cult", "vad-wrap h20")),
        "</div><div class=\"vad-grid\">",
        _box("Activité par sexe", "", _tab_pct(v["parSexe"], "Sexe")),
        _box("Activité principale — détail", "",
             _table_repartition(v["activites"], "Activité", "Personnes")),
        "</div>"])


def _p_mobilite(a):
    m = a["mobilite"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi("Présents depuis plus de 6 mois", _pc(m["presents"]["pct"]),
             f'{_n(m["presents"]["n"])} sur {_n(m["presents"]["total"])} personnes',
             "ok"),
        _kpi("Arrivés depuis moins de 6 mois", _pc(m["recents"]["pct"]),
             f'{_n(m["recents"]["n"])} personnes', "info"),
        _kpi("Absents au passage", _pc(m["absents"]["pct"]),
             f'{_n(m["absents"]["n"])} personnes déclarées absentes', "warn"),
        _kpi("Nés hors de leur commune", _pc(m["nesAilleurs"]["pct"]),
             f'{_n(m["nesAilleurs"]["n"])} sur {_n(m["nesAilleurs"]["total"])} '
             "personnes au lieu de naissance renseigné"),
        _kpi("Non-Malgaches", _n(m["etrangers"]["n"]),
             f'{_pc(m["etrangers"]["pct"])} des personnes renseignées'),
        "</div>",
        '<div class="vad-note">La part de « nés hors de leur commune » compare '
        "le <b>lieu de naissance saisi en texte libre</b> au nom de la commune "
        "d'enquête. La comparaison ignore la casse et les espaces, mais reste "
        "approximative : elle donne un ordre de grandeur de la mobilité "
        "interne, pas une mesure.</div>",
        '<div class="vad-grid">',
        _box("Situation de résidence", "",
             _canvas("ch-mob-res", "vad-wrap h20")),
        _box("Motifs d'arrivée dans le ménage",
             "Renseigné pour les membres nouvellement inscrits.",
             _table_repartition(m["motifsArrivee"], "Motif", "Personnes")),
        "</div><div class=\"vad-grid\">",
        _box("Principaux lieux de naissance déclarés",
             "Texte libre — ordre de grandeur.", _tab_pct(m["origines"], "Lieu")),
        _box("Résidence — détail", "",
             _table_repartition(m["residence"], "Situation", "Personnes")),
        "</div>"])


def _p_ciblage(a):
    c = a["ciblage"]
    return "".join([
        '<div class="vad-kpi">',
        _kpi("Ménages classés A / B / C", _pc(c["classes"]["pct"]),
             f'{_n(c["classes"]["n"])} sur {_n(c["classes"]["total"])} ménages',
             "warn" if (c["classes"]["pct"] or 0) < 90 else "ok"),
        _kpi("Ménages réellement joignables", _pc(c["joignables"]["pct"]),
             f'{_n(c["joignables"]["n"])} numéros exploitables sur '
             f'{_n(c["joignables"]["total"])} ménages',
             "bad" if (c["joignables"]["pct"] or 0) < 60 else "ok"),
        _kpi("Numéros factices", _pc(c["telSaisis"]["pct"]),
             f'{_n(c["telSaisis"]["factices"])} sur {_n(c["telSaisis"]["n"])} saisis',
             "bad"),
        _kpi("Chef présent tout l'entretien", _pc(c["presenceChef"]["pct"]),
             f'{_n(c["presenceChef"]["absente"])} entretiens menés sans lui',
             "warn"),
        "</div>",
        '<div class="vad-note vad-attention">Un numéro est jugé <b>joignable</b> '
        "s'il a dix chiffres commençant par 03 <b>et</b> n'est pas une valeur "
        "de remplissage (<code>0300000000</code>, <code>0399999999</code>…). "
        "Ces valeurs passent le masque de saisie sans être des numéros : c'est "
        "la manière la plus courante de contourner un champ obligatoire. Un "
        "registre qui devra notifier des bénéficiaires a besoin de ce chiffre-là, "
        "pas du nombre de champs remplis.</div>",
        '<div class="vad-grid">',
        _box("Classe d'éligibilité", "Renseignée pour une partie des ménages.",
             _canvas("ch-cib-eli", "vad-wrap h20")),
        _box("Type de ménage", "",
             _table_repartition(c["typemen"], "Type")),
        "</div><div class=\"vad-grid\">",
        _box("Présence du chef de ménage pendant l'entretien",
             "Un entretien mené sans le chef repose sur un répondant de "
             "substitution : à croiser avec les tests de qualité.",
             _table_repartition(c["repartitionPresence"], "Situation")),
        _box("Éligibilité — détail", "",
             _table_repartition(c["eligibilite"], "Classe")),
        "</div>"])


def _p_erreurs_saisie(a, quoi):
    """Un listing d'erreurs : `quoi` vaut "men" (ménage) ou "ind" (individu).

    La page ne contient QUE la barre de filtres et le tableau — pas de cartes de
    synthèse, pas de titre, pas de texte explicatif."""
    l = a.get("listing", {})
    if not l.get("disponible"):
        return ('<div class="vad-note vad-attention">Listing non calculable : '
                'les tables VAD sont absentes ou incomplètes.</div>')
    menage = quoi == "men"
    regles = l["reglesMenage"] if menage else l["reglesIndividu"]
    return _sai_filtres(quoi, regles, not menage)


def _p_err_menage(a):
    return _p_erreurs_saisie(a, "men")


def _p_err_individu(a):
    return _p_erreurs_saisie(a, "ind")


def _p_demographie(a):
    d = a["demographie"]
    gr, ch, sc = d["groupes"], d["chef"], d["scolarisation"]
    rg = a.get("rgph", {})
    # Chaque KPI porte, en sous-titre, la valeur RGPH-3 2018 du MÊME périmètre.
    # `_ref` rend une chaîne vide si les tables RGPH ne sont pas chargées, ce
    # qui laisse les cartes exactement dans leur état d'origine.
    def _ref(valeur, unite="", prefixe=" · RGPH-3 2018 : "):
        if not rg.get("disponible") or valeur is None:
            return ""
        return f'{prefixe}<b>{_n(valeur)}</b>{unite}'

    h = ['<div class="vad-kpi">',
         _kpi("Personnes enregistrées", _n(d["total"]),
              f'{_n(d["hommes"])} hommes · {_n(d["femmes"])} femmes'
              + (f' · {_n(d["sansSexe"])} sans sexe renseigné'
                 if d["sansSexe"] else "")
              + _ref(rg.get("total"), " au RGPH-3 2018", " · "), "info"),
         _kpi("Rapport de masculinité",
              (_n(d["masculinite"]) if d["masculinite"] else "—"),
              "hommes pour 100 femmes" + _ref(rg.get("masculinite")), "info"),
         _kpi("Âge moyen", (f'{_n(d["age"]["moy"])} ans' if d["age"]["moy"] else "—"),
              f'médiane {_n(d["age"]["med"])} ans'
              + _ref(rg.get("age", {}).get("moy"), " ans")
              + (f' (médiane {_n(rg["age"]["med"])})'
                 if rg.get("disponible") and rg.get("age", {}).get("med") is not None
                 else ""), "info"),
         _kpi("Moins de 15 ans", f'{_n(gr["pct_moins15"])} %',
              f'65 ans et + : {_n(gr["pct_plus65"])} %'
              + _ref(rg.get("groupes", {}).get("pct_moins15"), " %"), "info"),
         _kpi("Ratio de dépendance",
              (f'{_n(d["dependance"])} %' if d["dependance"] else "—"),
              "(0-14 + 65+) / 15-64" + _ref(rg.get("dependance"), " %"), "info"),
         _kpi("Ménages dirigés par une femme", f'{_n(ch["pct_femmes"])} %',
              f'{_n(ch["femmes"])} sur {_n(ch["n"])} chefs identifiés'
              + _ref(rg.get("chef", {}).get("pct_femmes"), " %"), "info"),
         '</div>']
    if rg.get("disponible"):
        h.append('<div class="vad-note">Les valeurs <b>RGPH-3 2018</b> portent sur '
                 'le même périmètre, effectifs redressés (échantillon au 10 %). '
                 'La VAD étant une enquête <b>ciblée</b>, un écart est attendu : '
                 'ces repères servent à situer les ménages visités, pas à mesurer '
                 'une évolution depuis 2018.</div>')
    h.append('<div class="vad-grid">')
    h.append(_box("Pyramide des âges — RSU (VAD)",
                  "Effectifs par groupe quinquennal — hommes à gauche, femmes à droite",
                  _canvas("ch-pyramide", "vad-wrap h28")))
    if rg.get("disponible"):
        h.append(_box("Pyramide des âges — RGPH-3 2018",
                      "Même district au recensement. Effectifs redressés "
                      f'(échantillon au 10 %) : <b>{_n(rg["total"])}</b> personnes. '
                      "⚠️ La VAD est une enquête <b>ciblée</b> : sa pyramide ne "
                      "décrit pas la population générale, les deux formes ne sont "
                      "pas censées coïncider.",
                      _canvas("ch-pyramide-rgph", "vad-wrap h28")))
    h.append('</div><div class="vad-grid">')
    h.append(_box("Rapport de masculinité par âge — RSU (VAD)",
                  "Hommes pour 100 femmes (100 = parité). Non calculé sous "
                  f'{d["effectifMin"]} femmes dans le groupe ; affichage plafonné '
                  "à 300.",
                  _canvas("ch-masc", "vad-wrap h28")))
    if rg.get("disponible"):
        h.append(_box("Rapport de masculinité par âge — RGPH-3 2018",
                      "Même district au recensement, même échelle et même règle "
                      "de publication. Les effectifs étant très supérieurs, la "
                      "courbe est stable : elle donne le profil de référence.",
                      _canvas("ch-masc-rgph", "vad-wrap h28")))
    h.append('</div><div class="vad-grid">')
    h.append(_box("Lien avec le chef de ménage", "",
                  _table_repartition(d["lien"], "Lien", "Personnes")))
    h.append(_box("État matrimonial", "Personnes de 12 ans et plus",
                  _table_repartition(d["matrimonial"], "Situation", "Personnes")))
    h.append('</div><div class="vad-grid">')
    h.append(_box("Niveau scolaire atteint",
                  'Toutes les personnes dont le niveau est renseigné. '
                  f'Scolarisation des 6-17 ans : <b>{_n(sc["oui"])}</b> sur '
                  f'<b>{_n(sc["cible"])}</b> enfants, soit <b>{_n(sc["taux"])} %</b>',
                  _canvas("ch-niveau", "vad-wrap h20")))
    h.append(_box("Activité principale", "Personnes de 15 ans et plus",
                  _table_repartition(d["activite"], "Activité", "Personnes")))
    h.append('</div>')
    p = d["papiers"]
    h.append('<div class="vad-grid">')
    h.append(_box("Papiers d'identité",
                  "Un indicateur clé pour l'inclusion au registre social",
                  _table([("lib", "Document"), ("oui", "Possède"),
                          ("total", "Interrogés"), ("pct", "%")],
                         [{"lib": "Acte de naissance", "oui": p["acte_oui"],
                           "total": p["acte_total"],
                           "pct": _pct_txt(p["acte_oui"], p["acte_total"])},
                          {"lib": "CIN (18 ans et +)", "oui": p["cin_oui"],
                           "total": p["cin_total"],
                           "pct": _pct_txt(p["cin_oui"], p["cin_total"])},
                          {"lib": "NUI", "oui": p["nui_oui"], "total": p["nui_total"],
                           "pct": _pct_txt(p["nui_oui"], p["nui_total"])}],
                         numeriques=("oui", "total", "pct"))))
    h.append(_box("Taille des ménages",
                  f'Moyenne {_n(d["tailleMenage"]["moy"])} · écart-type '
                  f'{_n(d["tailleMenage"]["et"])} · CV {_n(d["tailleMenage"]["cv"])} %',
                  _canvas("ch-taille", "vad-wrap h20")))
    h.append('</div>')
    return "".join(h)


def _pct_txt(n, t):
    return f"{round(100.0 * n / t, 1)} %".replace(".", ",") if t else "—"


def _p_habitation(a):
    hb = a["habitation"]
    h = ['<div class="vad-kpi">',
         _kpi("Pièces par logement", _n(hb["pieces"]["moy"]),
              f'médiane {_n(hb["pieces"]["med"])}', "info"),
         _kpi("Personnes par pièce", _n(hb["personnesParPiece"]["moy"]),
              "indicateur de peuplement", "info"),
         _kpi("Logements surpeuplés", f'{_n(hb["surpeuple"]["pct"])} %',
              f'plus de 3 personnes par pièce ({_n(hb["surpeuple"]["n"])} ménages)',
              "warn" if (hb["surpeuple"]["pct"] or 0) > 10 else "ok"),
         '</div>',
         '<div class="vad-grid">',
         _box("Matériau des murs", "", _canvas("ch-murs", "vad-wrap h20")),
         _box("Matériau du toit", "", _canvas("ch-toit", "vad-wrap h20")),
         '</div><div class="vad-grid">',
         _box("Matériau du sol", "", _canvas("ch-sol", "vad-wrap h20")),
         _box("Source d'éclairage", "", _canvas("ch-eclairage", "vad-wrap h20")),
         '</div><div class="vad-grid">',
         _box("Statut d'occupation", "", _table_repartition(hb["occupation"], "Statut")),
         _box("Nombre de pièces", "Répartition des logements",
              _table_repartition(hb["piecesDistrib"], "Pièces")),
         '</div>']
    return "".join(h)


def _p_biens(a):
    b = a["biens"]
    lignes = [{"lib": ESC(l["lib"]), "famille": ESC(l["famille"]), "oui": l["oui"],
               "total": l["total"],
               "pct": f'{_n(l["pct"])} %' if l["pct"] is not None else "—"}
              for l in b["lignes"]]
    h = ['<div class="vad-kpi">',
         _kpi("Biens possédés par ménage", _n(b["nbBiens"]["moy"]),
              f'médiane {_n(b["nbBiens"]["med"])} sur {len(b["lignes"])} biens suivis',
              "info"),
         _kpi("Ménages renseignés", _n(b["nbBiens"]["n"]), "sur la question des biens",
              "info"),
         '</div>',
         '<div class="vad-note">Le <b>taux de possession</b> est calculé sur les '
         'ménages ayant répondu à la question. Ces biens servent au calcul du score '
         'de bien-être (proxy means test) : leur qualité de saisie est donc '
         'déterminante.</div>',
         '<div class="vad-grid">',
         _box("Taux de possession", "Tous biens confondus, du plus au moins répandu",
              _canvas("ch-biens", "vad-wrap h28")),
         '</div>',
         _box("Détail par bien", "",
              _table([("lib", "Bien ou actif"), ("famille", "Famille"),
                      ("oui", "Possèdent"), ("total", "Répondants"), ("pct", "%")],
                     lignes, numeriques=("oui", "total", "pct")))]
    return "".join(h)


def _p_eau(a):
    e = a["eau"]
    h = ['<div class="vad-kpi">',
         _kpi("Eau de boisson améliorée", f'{_n(e["eauAmelioree"]["pct"])} %',
              f'{_n(e["eauAmelioree"]["n"])} / {_n(e["eauAmelioree"]["total"])} ménages',
              "ok" if (e["eauAmelioree"]["pct"] or 0) >= 70 else "warn"),
         _kpi("Assainissement amélioré", f'{_n(e["sanitAmelioree"]["pct"])} %',
              f'{_n(e["sanitAmelioree"]["n"])} / {_n(e["sanitAmelioree"]["total"])} ménages',
              "ok" if (e["sanitAmelioree"]["pct"] or 0) >= 50 else "warn"),
         _kpi("Défécation à l'air libre", f'{_n(e["airLibre"]["pct"])} %',
              f'{_n(e["airLibre"]["n"])} ménages',
              "bad" if (e["airLibre"]["pct"] or 0) > 10 else "ok"),
         '</div>',
         '<div class="vad-note vad-attention">Les classements « amélioré » suivent '
         'les définitions <b>JMP (OMS/UNICEF)</b> et sont une <b>proposition</b> : '
         'ils ne viennent pas du questionnaire. À faire valider par les '
         'statisticiens du RSU avant toute publication.</div>',
         '<div class="vad-grid">',
         _box("Source d'eau de boisson", "", _canvas("ch-eau", "vad-wrap h28")),
         _box("Type de toilettes", "", _canvas("ch-sanit", "vad-wrap h28")),
         '</div><div class="vad-grid">',
         _box("Évacuation des ordures", "", _table_repartition(e["ordures"], "Mode")),
         _box("Source d'eau — détail", "", _table_repartition(e["source"], "Source")),
         '</div>']
    return "".join(h)


def _drill_zone(g, section):
    """Sous-menu Commune → Fokontany de la barre latérale, sous « Carte GPS ».

    Même forme que la descente du dénombrement (`nav-sub` / `nav-sub-item`, CSS
    partagé de `assets/rapport.css`), avec en plus des FLÈCHES de dépliage : le
    bandeau « Communes » replie toute la liste, et la flèche d'une commune ouvre
    ses fokontany SANS changer de page. Le libellé, lui, reste un lien : c'est le
    serveur qui recalcule les agrégats sur la zone, donc les indicateurs
    décrivent bien ce que la carte montre.

    Tous les fokontany du périmètre sont écrits (repliés) : cela évite un
    aller-retour serveur pour simplement regarder ce que contient une commune."""
    zones = g.get("zones") or []
    if section != "gps" or not zones:
        return ""
    choix = g.get("choix") or {}
    cc, cf = choix.get("commune"), choix.get("fokontany")
    pref = config.PREFIXE
    tot = sum(c["n"] for c in zones)
    h = ['<div class="nav-sub" id="vad-drill">',
         '<button type="button" class="vad-drill-tete" aria-expanded="true" '
         'aria-controls="vad-drill-liste">'
         f'<span class="c">▾</span> Communes ({_n(len(zones))})</button>',
         '<div class="vad-drill-liste" id="vad-drill-liste">',
         f'<a class="nav-sub-item all{"" if (cc or cf) else " active"}" '
         f'href="{pref}/vad/gps">Tout le district ({_n(tot)})</a>']
    for c in zones:
        ouverte = (c["code"] == cc)
        h.append(
            '<div class="vad-com">'
            f'<button type="button" class="vad-caret" data-com="{c["code"]}" '
            f'aria-expanded="{"true" if ouverte else "false"}" '
            f'aria-label="Afficher les fokontany de {ESC(c["nom"])}">'
            f'{"▾" if ouverte else "▸"}</button>'
            f'<a class="nav-sub-item commune{" active" if (ouverte and not cf) else ""}" '
            f'href="{pref}/vad/gps?commune={c["code"]}">'
            f'{ESC(c["nom"])} ({_n(c["n"])})</a></div>')
        h.append(f'<div class="nav-sub2" data-fkt="{c["code"]}"'
                 + ('' if ouverte else ' hidden') + '>')
        for f in c["fokontany"]:
            h.append(f'<a class="nav-sub-item fkt'
                     f'{" active" if f["code"] == cf else ""}" '
                     f'href="{pref}/vad/gps?fokontany={f["code"]}">'
                     f'{ESC(f["nom"])} ({_n(f["n"])})</a>')
        h.append('</div>')
    h.append('</div></div>')
    return "".join(h)


def _p_gps(a):
    g = a["gps"]
    h = ['<div class="vad-kpi">',
         _kpi("Ménages géolocalisés", f'{_n(g["taux"])} %',
              f'{_n(g["captures"])} / {_n(g["total"])}',
              "ok" if (g["taux"] or 0) >= 95 else "warn"),
         _kpi("Précision moyenne",
              (f'{_n(g["precision"]["moy"])} m' if g["precision"]["moy"] else "—"),
              f'médiane {_n(g["precision"]["med"])} m', "info"),
         _kpi("Points précis (≤ 50 m)", f'{_n(g["precisionBonne"]["pct"])} %',
              f'{_n(g["precisionBonne"]["n"])} / {_n(g["precisionBonne"]["total"])}',
              "ok" if (g["precisionBonne"]["pct"] or 0) >= 70 else "warn"),
         '</div>',
         '<div class="note-box" id="vadmap-note">Chaque point représente un ménage '
         'interviewé et géolocalisé.</div>',
         '<div class="export-bar"><span class="label">Filtrer par date :</span>'
         '<div id="vadmap-filters" style="display:flex;gap:6px;flex-wrap:wrap">'
         '</div></div>',
         '<div id="vadmap"></div>']
    return "".join(h)


def _signe(v):
    """« +32 » / « −7 » / « — », coloré : un écart POSITIF (il est arrivé moins
    que déclaré) se lit en rouge, un écart négatif en orange, zéro en vert."""
    if v is None:
        return "—"
    coul = "#dc2626" if v > 0 else ("#b45309" if v < 0 else "#059669")
    txt = f"+{_n(v)}" if v > 0 else _n(v)
    return f'<b style="color:{coul}">{txt}</b>'


def _p_ecart(a):
    """Bloc « Écart déclaration ↔ serveur » de la page « Par agent ».

    Trois cas : le périmètre est une DESCENTE (commune / fokontany) -> on
    explique pourquoi l'écart ne s'y calcule pas ; AUCUNE déclaration n'a été
    saisie -> on le dit ; sinon KPI + graphique + tableau."""
    e = a.get("ecart") or {}
    if not e.get("dispo"):
        if e.get("raison") == "descente":
            return ('<div class="vad-note">L\'<b>écart entre ce que l\'agent '
                    'déclare et ce qui arrive au serveur</b> se lit sur '
                    '<b>l\'ensemble de votre périmètre</b> : revenez au niveau '
                    'le plus haut (« Tout le périmètre » dans la descente). La '
                    'déclaration de l\'agent est <i>journalière et globale</i> '
                    '(toutes zones confondues), elle ne se ventile ni par '
                    'commune ni par fokontany.</div>')
        return ('<div class="vad-note"><b>Aucune déclaration d\'agent n\'a '
                'encore été saisie pour la visite à domicile sur ce '
                'périmètre</b> : l\'écart avec ce qui arrive au serveur ne peut '
                'pas être calculé. Ces déclarations sont saisies par le '
                '<b>Superviseur Technique</b> (« Déclaration des agents », '
                'phase <i>Visite à domicile</i>).</div>')
    t = e["total"]
    nb_top = sum(1 for r in e["agents"] if r["ecart"] is not None)
    lignes = []
    for r in e["agents"]:
        lignes.append({
            "agent": ESC(r["agent"]),
            "chef": ESC(r["chef"] or "—"),
            "jours": r["joursDeclares"] or "—",
            "declare": ("—" if r["declare"] is None else r["declare"]),
            "recu": r["recu"],
            "ecart": _signe(r["ecart"]),
            "pct": ("—" if r["pct"] is None else f'{_n(r["pct"])} %'),
        })
    return "".join([
        '<div class="vad-note"><b>Écart = déclaré − reçu.</b> « Déclaré » = ce '
        'que l\'agent dit avoir interviewé chaque jour (saisi par le Superviseur '
        'Technique) ; « reçu » = ce qui est réellement arrivé au serveur. Un '
        'écart <b>positif</b> signale qu\'il est arrivé <b>moins</b> que déclaré '
        '(synchronisation en retard, ou sur-déclaration) ; un écart '
        '<b>négatif</b>, qu\'il est arrivé <b>plus</b> que déclaré. « — » : '
        'aucune déclaration saisie pour cet agent — ce n\'est pas un zéro. '
        'Calculé sur tout le périmètre et sur les seuls ménages datés.</div>',
        '<div class="vad-kpi">',
        _kpi("Ménages déclarés", _n(t["declare"]),
             f'{_n(t["declarants"])} agent(s) ayant déclaré', "info"),
        _kpi("Arrivés au serveur", _n(t["recu"]),
             f'{_n(t["agents"])} agent(s) au total', "ok"),
        _kpi("Écart (déclaré − reçu)", _signe(t["ecart"]),
             ("—" if t["pct"] is None else f'{_n(t["pct"])} % du déclaré'),
             ("bad" if (t["ecart"] or 0) > 0 else "warn")),
        '</div>',
        # Hauteur du graphique : 12 barres tiennent dans 28 rem, pas dans 20 —
        # au-delà de huit, Chart.js masque une étiquette sur deux.
        _box("Écart par agent", f"Les {min(12, nb_top)} plus grands écarts",
             _canvas("ch-ecart",
                     "vad-wrap h28" if nb_top > 7 else "vad-wrap h20")),
        _box("Écart déclaration ↔ serveur, par agent",
             f'Le plus gros écart d\'abord · {_n(t["sansDeclaration"])} '
             "agent(s) ont des ménages reçus mais AUCUNE déclaration",
             _table([("agent", "Agent"), ("chef", "Chef d'équipe"),
                     ("jours", "Jours déclarés"),
                     ("declare", "Ménages déclarés"),
                     ("recu", "Ménages reçus au serveur"),
                     ("ecart", "Écart (déclaré − reçu)"),
                     ("pct", "Écart (% du déclaré)")],
                    lignes,
                    numeriques=("jours", "declare", "recu", "ecart", "pct"))),
    ])


# ---------------------------------------------------------------------------
# Couverture par agent (affectation du préchargement ↔ interviews VAD)
# ---------------------------------------------------------------------------
_STATUT_COURT = {130: "Approuvé siège", 120: "Approuvé sup.", 100: "Terminé",
                 65: "Rejeté sup.", 125: "Rejeté siège", 60: "Chez l'agent"}


def _couv_pct(v):
    """Taux de couverture coloré : < 50 % rouge, < 80 % orange, sinon vert."""
    if v is None:
        return "—"
    coul = "#dc2626" if v < 50 else ("#b45309" if v < 80 else "#059669")
    return f'<b style="color:{coul}">{_n(v)} %</b>'


def _lien_agent(code, libelle):
    q = urllib.parse.quote(code, safe="")
    return (f'<a href="{config.PREFIXE}/vad/agents?agent={q}#reste" '
            f'title="Voir les ménages affectés non encore interviewés">'
            f'{ESC(libelle)}</a>')


def _p_doubles(doubles):
    if not doubles:
        return _box("Ménages interviewés plusieurs fois", "",
                    '<p class="sub">Aucun ménage du périmètre n\'a été '
                    'interviewé plus d\'une fois.</p>')
    lignes = [{
        "kd": ESC(d["keyden"]), "n": d["n"],
        "verdict": (f'<b style="color:#dc2626">{ESC(d["verdict"])}</b>'
                    if d["verdict"] != "Double interview" else ESC(d["verdict"])),
        "aff": ESC(d["affecte"] or "—"),
        "agents": "<br>".join(ESC(x) for x in d["agents"]),
        "dates": "<br>".join(_date(x) for x in d["dates"]),
        "statuts": "<br>".join(ESC(_STATUT_COURT.get(s, str(s))) for s in d["statuts"]),
        "cles": "<br>".join(ESC(x) for x in d["cles"]),
    } for d in doubles]
    return _box(
        "Ménages interviewés plusieurs fois",
        f'{_n(len(doubles))} ménage(s) · un ménage n\'est compté qu\'une fois '
        'dans la couverture. Au-delà de 3 interviews d\'une même clé, c\'est '
        'le préchargement qui est en cause (clé distribuée à tort), pas une '
        'double visite.',
        _table([("kd", "Clé ménage (keyden)"), ("n", "Interviews"),
                ("verdict", "Diagnostic"), ("aff", "Agent affecté"),
                ("agents", "Agents"), ("dates", "Dates"),
                ("statuts", "Statuts"), ("cles", "Clés d'interview")],
               lignes, numeriques=("n",)))


def _p_couv_detail(cv, code):
    """Ménages affectés à UN agent et qu'il n'a pas encore interviewés."""
    retour = (f'<a class="qa-retour" href="{config.PREFIXE}/vad/agents">'
              '← Retour au tableau de couverture</a>')
    p = next((x for x in cv["agents"] if x["code"] == code), None)
    if p is None:
        return (retour + '<div class="vad-note">Cet agent n\'a aucun ménage '
                'affecté ni aucune interview dans le préchargement de ce '
                'périmètre.</div>')
    reste = [{
        "i": i, "fkt": ESC(r["fokontany_nom"] or str(r["fokontany"] or "—")),
        "code_den": ESC(r["code_den"] or "—"), "nom": ESC(r["nom_cm"] or "—"),
        "taille": r["taille"], "adr": ESC(r["adresse"] or "—"),
        "desc": ESC(r["description"] or "—"), "kd": ESC(r["keyden"]),
    } for i, r in enumerate(p["resteListe"], 1)]
    return "".join([
        retour,
        '<div class="vad-kpi">',
        _kpi("Ménages affectés", _n(p["affectes"]),
             f'Chef d\'équipe : {ESC(p["ceNom"] or "—")}', "info"),
        _kpi("Affectés interviewés", _n(p["affInterviewes"]),
             f'Couverture {_couv_pct(p["couverture"])}', "ok"),
        _kpi("Reste à interviewer", _n(p["reste"]),
             f'{_n(p["parAutre"])} interviewé(s) par un autre agent', "bad"
             if p["reste"] else "ok"),
        _kpi("Non affectés interviewés", _n(p["nonAffectes"]),
             f'{_n(p["nonAffAutre"])} d\'un autre agent · '
             f'{_n(p["nonAffHors"])} hors préchargement', "warn"),
        '</div>',
        '<div id="reste"></div>',
        _box(f'Ménages affectés à {p["agent"]} et pas encore interviewés',
             f'{_n(len(reste))} ménage(s), par fokontany · un ménage '
             'interviewé par un autre agent n\'y figure pas (il n\'est plus '
             'à faire)',
             _table([("i", "#"), ("fkt", "Fokontany"),
                     ("code_den", "Code dénombrement"),
                     ("nom", "Chef de ménage"), ("taille", "Taille"),
                     ("adr", "Adresse"), ("desc", "Description"),
                     ("kd", "Clé ménage (keyden)")],
                    reste, numeriques=("i", "taille"))),
    ])


def _p_couverture(a):
    """Tableau de couverture par agent, ou le détail d'un agent (`?agent=`)."""
    cv = a.get("couverture") or {}
    sel = a.get("agentSel") or ""
    if not cv.get("dispo"):
        return "".join([
            '<div class="vad-note"><b>Couverture par agent indisponible</b> : '
            'aucune base de préchargement n\'est enregistrée pour ce '
            'périmètre. L\'affectation des ménages aux agents vient du '
            'registre du préchargement (espace Traitement → Préchargement) ; '
            'elle sera calculée dès qu\'un lot aura été généré.</div>',
            _p_doubles(cv.get("doubles") or []),
        ])
    if sel:
        return _p_couv_detail(cv, sel)
    t = cv["total"]
    statuts = cv["statuts"]
    lignes = []
    for p in cv["agents"]:
        l = {"agent": _lien_agent(p["code"], p["agent"]),
             "ce": ESC(p["ceNom"] or "—"),
             "aff": p["affectes"], "affi": p["affInterviewes"],
             "couv": _couv_pct(p["couverture"]),
             "autre": p["parAutre"], "reste": p["reste"],
             "nonaff": p["nonAffectes"], "sanscle": p["sansCle"]}
        for _code, cle, _lib in statuts:
            l[cle] = p[cle]
        lignes.append(l)
    cols = ([("agent", "Agent"), ("ce", "Chef d'équipe"),
             ("aff", "Ménages affectés"), ("affi", "Affectés interviewés"),
             ("couv", "Couverture")]
            + [(cle, lib) for _c, cle, lib in statuts]
            + [("autre", "Interviewés par un autre agent"),
               ("reste", "Reste à interviewer"),
               ("nonaff", "Non affectés interviewés"),
               ("sanscle", "Interviews sans clé")])
    num = tuple(c for c, _l in cols if c not in ("agent", "ce"))
    districts = ", ".join(str(d) for d in t["districts"])
    return "".join([
        '<div class="vad-note"><b>Couverture = ménages affectés à l\'agent '
        'qu\'il a lui-même interviewés ÷ ménages affectés.</b> L\'affectation '
        'est celle de la <b>base de préchargement</b> ; le rapprochement se '
        'fait ménage par ménage sur la clé du dénombrement '
        '(<code>interview_keyden</code>). Un ménage interviewé plusieurs fois '
        'compte une seule fois ; pour lui, on retient le statut le plus '
        'avancé. Un ménage affecté à A mais interviewé par B est « interviewé '
        'par un autre agent » chez A et « non affecté » chez B. <b>Cliquez sur '
        'un agent</b> pour voir les ménages qu\'il lui reste à interviewer.'
        f' Districts comparés (registre présent) : {ESC(districts)}.'
        + (f' {_n(t["horsRegistre"])} interview(s) de districts sans '
           'préchargement enregistré ne sont pas comptées.'
           if t["horsRegistre"] else "") + '</div>',
        '<div class="vad-kpi">',
        _kpi("Ménages affectés", _n(t["affectes"]),
             f'{_n(t["agents"])} agent(s)', "info"),
        _kpi("Affectés interviewés", _n(t["affInterviewes"]),
             f'Couverture {_couv_pct(t["couverture"])}', "ok"),
        _kpi("Reste à interviewer", _n(t["reste"]),
             f'{_n(t["parAutre"])} interviewé(s) par un autre agent',
             "bad" if t["reste"] else "ok"),
        _kpi("Non affectés interviewés", _n(t["nonAffectes"]),
             f'{_n(t["nonAffAutre"])} d\'un autre agent · '
             f'{_n(t["nonAffHors"])} hors préchargement', "warn"),
        _kpi("Ménages interviewés plusieurs fois", _n(len(cv["doubles"])),
             f'{_n(t["sansCle"])} interview(s) sans clé', "warn"
             if cv["doubles"] else "ok"),
        '</div>',
        _box("Couverture par agent",
             "Le moins couvert d'abord · statuts Survey Solutions comptés sur "
             "les ménages affectés interviewés",
             _table(cols, lignes, numeriques=num)),
        _p_doubles(cv["doubles"]),
    ])


def _p_agents(a):
    if a.get("agentSel"):
        return _p_couverture(a)
    lignes = [{"agent": ESC(r["agent"]), "menages": r["menages"],
               "membres": r["membres"], "jours": r["jours"],
               "parJour": r["parJour"], "taille": r["taille"],
               "duree": (f'{_n(r["duree"])} min' if r["duree"] else "—"),
               "anomalies": r["anomalies"]} for r in a["agents"]]
    tot = sum(r["menages"] for r in a["agents"])
    h = ['<div class="vad-kpi">',
         _kpi("Agents ayant travaillé", _n(len(a["agents"])),
              f'{_n(tot)} ménages interviewés au total', "info"),
         '</div>',
         # Couverture de l'affectation du préchargement, en tête : c'est le
         # tableau de suivi de l'avancement agent par agent.
         _p_couverture(a),
         _box("Production par agent",
              "Triée par nombre de ménages interviewés",
              _table([("agent", "Agent"), ("menages", "Ménages"),
                      ("membres", "Membres"), ("jours", "Jours"),
                      ("parJour", "Ménages/jour"), ("taille", "Taille moy."),
                      ("duree", "Durée moy."), ("anomalies", "Anomalies")],
                     lignes,
                     numeriques=("menages", "membres", "jours", "parJour",
                                 "taille", "duree", "anomalies"))),
         # Ce que l'agent DÉCLARE face à ce qui ARRIVE AU SERVEUR.
         _p_ecart(a)]
    return "".join(h)


def _date(d):
    return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if d and len(d) == 8 else "—"


_RENDU = {"general": _p_general, "demographie": _p_demographie,
          "habitation": _p_habitation, "biens": _p_biens, "eau": _p_eau,
          "handicap": _p_handicap, "identite": _p_identite,
          "education": _p_education, "enfance": _p_enfance,
          "activite": _p_activite, "mobilite": _p_mobilite,
          "ciblage": _p_ciblage,
          "gps": _p_gps, "agents": _p_agents,
          "err_menage": _p_err_menage,
          "err_individu": _p_err_individu,
          "qualite": _p_qualite,
          "qualite_base": _p_qualite_base}


# ---------------------------------------------------------------------------
# Page complète
# ---------------------------------------------------------------------------
def page(section, agg, portee, retour="/choix", liens_zone=""):
    """HTML complet d'une section du tableau de bord VAD."""
    section = section if section in IDS else "general"
    pref = config.PREFIXE
    # La descente Commune → Fokontany se glisse SOUS l'entrée de sa section,
    # comme le sous-menu du dénombrement (pas en haut de page).
    drill = _drill_zone(agg.get("gps") or {}, section)
    nav, groupe = [], None
    for g, s_, i, l in SECTIONS:
        if g != groupe:
            groupe = g
            nav.append(f'<div class="nav-section">{ESC(g)}</div>')
        nav.append(f'<a class="nav-item{" active" if s_ == section else ""}" '
                   f'href="{pref}/vad/{s_}"><span class="nav-icon">{i}</span> '
                   f"{ESC(l)}</a>")
        if s_ == section:
            nav.append(drill)
    nav = "".join(nav)
    titre = next(l for _g, s, _i, l in SECTIONS if s == section)
    corps = _RENDU[section](agg)
    # Données des graphiques : seulement celles de la section affichée.
    data = json.dumps(_data_section(section, agg), ensure_ascii=False)
    leaflet = ('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
               '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>'
               if section == "gps" else "")
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RSU 2026 — VAD · {ESC(titre)}</title>
<link rel="stylesheet" href="{pref}/assets/rapport.css">
<script src="{pref}/assets/chart.umd.min.js"></script>{leaflet}{_CSS}
</head><body>
<aside class="sidebar">
  <div class="sidebar-brand"><div class="brand-icon">🏠</div>
    <div><div class="brand-name">RSU 2026</div>
    <div class="brand-sub">Visite à domicile</div></div></div>
  {nav}
  <div class="nav-section" style="margin-top:1rem">Périmètre</div>
  <div style="padding:0 1rem 1rem;font-size:.8rem;color:#94a3b8">
    {ESC(portee)}<br><b>{_n(agg['portee']['menages'])}</b> ménages ·
    <b>{_n(agg['portee']['membres'])}</b> membres</div>
  {liens_zone}
  <div style="padding:0 1rem 1.5rem">
    <a class="nav-item" href="{pref}{retour}">← Mon espace</a></div>
</aside>
<main class="main"><div class="page active">
  <div class="page-head"><h1>{ESC(titre)}</h1>
  <a class="btn btn-primary" href="{pref}/vad/rapport.xlsx"
     title="Classeur Excel du périmètre affiché : Global, Erreur ménage, Erreur Individu, les deux volets du test de qualité de données, et l'écart déclaration-serveur par agent."
     >⬇ Rapport Excel</a>
  <p class="page-sub">{ESC(portee)}</p></div>
  {corps}
</div></main>
<script>const VAD = {data};</script>
<script>{_JS}</script>
</body></html>"""


def _data_section(section, a):
    """Les seules données envoyées au navigateur : celles des graphiques."""
    if section == "general":
        return {"jour": a["global"]["parJour"],
                "statut": a["global"]["statut"]["lignes"]}
    if section == "qualite":
        # La MATRICE est rendue côté serveur et le navigateur se contente de la
        # filtrer : rien à envoyer. Seule la FICHE d'un agent a des courbes, et
        # elles ne pèsent que quelques centaines d'octets.
        r = (a.get("qualite") or {}).get("resultat")
        return {"qa": r["graphiques"]} if r and r.get("graphiques") else {}
    # Sections thématiques : seulement les séries à tracer, jamais les listes
    # de personnes. Quelques centaines d'octets par page.
    if section in ("handicap", "identite", "education", "enfance",
                   "activite", "mobilite", "ciblage"):
        lp = lambda rows: {"l": [r["lib"] for r in rows],
                           "d": [r.get("pct") for r in rows]}
        if section == "handicap":
            h_ = a["handicap"]
            return {"th": {"dom": lp(h_["domaines"]), "age": lp(h_["parAge"])}}
        if section == "identite":
            return {"th": {"age": lp(a["identite"]["parAge"])}}
        if section == "education":
            e = a["education"]
            return {"th": {"age": lp(e["parAge"]),
                           "niv": lp(e["niveau"]["lignes"][:10])}}
        if section == "enfance":
            e = a["enfance"]
            return {"th": {"vuln": {
                "l": ["Orphelins", "Déscolarisés 6-14", "Sans acte",
                      "Handicap", "2 vulnérabilités ou +"],
                "d": [e["orphelins"]["pct"], e["deScolarises"]["pct"],
                      e["sansActe"]["pct"], e["handicap"]["pct"],
                      e["cumul"]["pct"]]}}}
        if section == "activite":
            v = a["activite"]
            return {"th": {"act": lp(v["activites"]["lignes"][:12]),
                           "cult": lp(v["cultures"])}}
        if section == "mobilite":
            return {"th": {"res": lp(a["mobilite"]["residence"]["lignes"])}}
        c = a["ciblage"]
        return {"th": {"eli": lp(c["eligibilite"]["lignes"])}}
    if section == "qualite_base":
        q = a.get("qualite_base") or {}
        if not q.get("disponible"):
            return {}
        cov = [c for c in q.get("couverture", []) if c["attendu"]]
        # Les vingt communes les moins couvertes : au-delà, le graphique
        # devient illisible et le tableau complet suit de toute façon.
        cov = sorted(cov, key=lambda c: c["taux"])[:20]
        return {"qb": {"g": q.get("graphiques") or {},
                       "resume": q.get("resume") or {},
                       "cov": [{"n": c["nom"], "t": round(c["taux"], 1)}
                               for c in cov]}}
    if section in ("err_menage", "err_individu"):
        l = a.get("listing", {})
        men = section == "err_menage"
        return {"saisie": {"pref": "men" if men else "ind",
                           "lignes": l.get("menage" if men else "individu", []),
                           "regles": l.get("reglesMenage" if men
                                           else "reglesIndividu", [])}}
    if section == "demographie":
        d = {"pyramide": a["demographie"]["pyramide"],
             "niveau": a["demographie"]["scolarisation"]["niveau"]["lignes"][:12],
             "taille": a["demographie"]["tailleMenage"]}
        if a.get("rgph", {}).get("disponible"):
            d["pyramideRgph"] = a["rgph"]["pyramide"]
        return d
    if section == "habitation":
        h = a["habitation"]
        return {k: h[k]["lignes"][:12] for k in ("murs", "toit", "sol", "eclairage")}
    if section == "biens":
        return {"biens": [{"lib": l["lib"], "pct": l["pct"]}
                          for l in a["biens"]["lignes"]]}
    if section == "eau":
        return {"eau": a["eau"]["source"]["lignes"][:14],
                "sanit": a["eau"]["toilettes"]["lignes"][:12]}
    if section == "agents":
        e = a.get("ecart") or {}
        if not e.get("dispo"):
            return {}
        # Les 12 plus grands écarts (en valeur absolue), déclarants seulement :
        # au-delà, le graphique n'est plus lisible et le tableau suit.
        top = sorted([r for r in e["agents"] if r["ecart"] is not None],
                     key=lambda r: -abs(r["ecart"]))[:12]
        return {"ecart": {"l": [r["agent"] for r in top],
                          "d": [r["ecart"] for r in top]}}
    if section == "gps":
        # `pref` : la carte va chercher les contours à part (/vad/contours.json),
        # trop lourds pour être inscrits dans la page (cf. limites_db).
        return {"points": a["gps"]["points"], "pref": config.PREFIXE,
                "zone": a["gps"].get("choix") or {}}
    return {}


_JS = r"""
const PAL = ['#2563eb','#0ea5e9','#10b981','#f59e0b','#8b5cf6','#ef4444','#06b6d4',
             '#ec4899','#84cc16','#f97316','#14b8a6','#a855f7','#64748b','#eab308'];
const coul = i => PAL[i % PAL.length];
const el = id => document.getElementById(id);
function mk(id, cfg){ const c = el(id); if(c) new Chart(c, cfg); }
const OPT = {responsive:true, maintainAspectRatio:false};
function barH(id, labels, data, titre){
  mk(id, {type:'bar', data:{labels, datasets:[{label:titre, data,
      backgroundColor:labels.map((_,i)=>coul(i)+'cc'), borderWidth:0}]},
    options:{...OPT, indexAxis:'y',
      plugins:{legend:{display:false}}, scales:{x:{beginAtZero:true}}}});
}
function donut(id, labels, data){
  mk(id, {type:'doughnut', data:{labels, datasets:[{data,
      backgroundColor:labels.map((_,i)=>coul(i)), borderWidth:0, hoverOffset:6}]},
    options:{...OPT, cutout:'62%',
      plugins:{legend:{position:'bottom', labels:{boxWidth:10, padding:10,
        font:{size:11}}}}}});
}

// ---- Écart déclaration <-> serveur (page « Par agent ») --------------
// Rouge = il est arrivé MOINS que déclaré, orange = PLUS que déclaré.
if(VAD.ecart && VAD.ecart.l && VAD.ecart.l.length){
  mk('ch-ecart', {type:'bar',
    data:{labels:VAD.ecart.l, datasets:[{label:'Écart (ménages)', data:VAD.ecart.d,
      backgroundColor:VAD.ecart.d.map(v=>v>0?'#ef4444cc':(v<0?'#f59e0bcc':'#10b981cc')),
      borderWidth:0}]},
    options:{...OPT, indexAxis:'y', plugins:{legend:{display:false}},
      scales:{x:{beginAtZero:true}}}});
}

// ---- Sections thématiques : une ou deux séries par page --------------
// Toutes les séries sont des POURCENTAGES déjà calculés côté serveur : le
// navigateur ne fait que les dessiner, il ne recalcule rien.
if(VAD.th){
  const T = VAD.th, pct = {plugins:{tooltip:{callbacks:{
    label:c=> (c.raw==null?'—':c.raw+' %')}}}};
  const bp = (id, s, titre) => { if(s && s.l && s.l.length) barH(id, s.l, s.d, titre); };
  bp('ch-hand-dom', T.dom, 'Prévalence (%)');
  bp('ch-hand-age', T.age, 'Prévalence (%)');
  bp('ch-id-age',   T.age, "Avec acte de naissance (%)");
  bp('ch-edu-age',  T.age, 'Fréquentent actuellement (%)');
  bp('ch-edu-niv',  T.niv, 'Part des personnes (%)');
  bp('ch-enf',      T.vuln, 'Part des enfants (%)');
  bp('ch-act',      T.act, 'Part des 15 ans et + (%)');
  bp('ch-cult',     T.cult, 'Part des ménages agricoles (%)');
  if(T.res && T.res.l) donut('ch-mob-res', T.res.l, T.res.d);
  if(T.eli && T.eli.l) donut('ch-cib-eli', T.eli.l, T.eli.d);
}

// ---- Fiche d'un agent : quatre lectures graphiques -------------------
// Toujours l'agent CONTRE sa zone, et toujours en pourcentages : il pèse
// quelques dizaines de ménages face à plusieurs centaines, superposer des
// effectifs ne comparerait que des charges de travail.
if(VAD.qa){
  const A = VAD.qa;
  if(A.pyramide && A.pyramide.length){
    const P = A.pyramide;
    mk('qa-ch-pyr', {type:'bar', data:{labels:P.map(x=>x.groupe), datasets:[
      {label:'Hommes (agent)', data:P.map(x=>-x.aH), backgroundColor:'#0d9488',
       borderWidth:0, order:3},
      {label:'Femmes (agent)', data:P.map(x=>x.aF), backgroundColor:'#f472b6',
       borderWidth:0, order:3},
      {type:'line', label:'Zone — hommes', data:P.map(x=>-x.zH),
       borderColor:'#0f172a', borderWidth:2, borderDash:[4,3], pointRadius:2,
       pointBackgroundColor:'#0f172a', fill:false, order:1},
      {type:'line', label:'Zone — femmes', data:P.map(x=>x.zF),
       borderColor:'#7c3aed', borderWidth:2, borderDash:[4,3], pointRadius:2,
       pointBackgroundColor:'#7c3aed', fill:false, order:1}]},
      options:{...OPT, indexAxis:'y',
        scales:{x:{ticks:{callback:v=>Math.abs(v)+' %'}, grid:{color:'#eef2f7'}},
                y:{reverse:true, grid:{display:false}}},
        plugins:{legend:{position:'bottom',
            labels:{boxWidth:10, padding:10, font:{size:11}}},
          tooltip:{callbacks:{label:c=>c.dataset.label+' : '
            + Math.abs(c.raw).toFixed(2)+' %'}}}}});
  }
  if(A.chiffres){
    const ag = A.chiffres.agent || [], zo = A.chiffres.zone || [];
    mk('qa-ch-dig', {type:'bar',
      data:{labels:[0,1,2,3,4,5,6,7,8,9], datasets:[
        {label:"Cet agent", data:ag, borderWidth:0,
         backgroundColor:ag.map(v=> Math.abs(v-10)>=4 ? '#f59e0b' : '#0d9488')},
        {type:'line', label:'Sa zone', data:zo, borderColor:'#64748b',
         borderWidth:2, pointRadius:2, fill:false},
        {type:'line', label:'Attendu (10 %)', data:ag.map(()=>10),
         borderColor:'#ef4444', borderWidth:2, borderDash:[5,4], pointRadius:0,
         fill:false}]},
      options:{...OPT,
        plugins:{legend:{position:'bottom', labels:{boxWidth:10, font:{size:11}}},
          tooltip:{callbacks:{label:c=>c.dataset.label+' : '+c.raw+' %'}}},
        scales:{y:{beginAtZero:true, ticks:{callback:v=>v+' %'},
                   grid:{color:'#eef2f7'}},
                x:{title:{display:true, text:"dernier chiffre de l'âge déclaré"},
                   grid:{display:false}}}}});
  }
  if(A.jours && A.jours.length){
    const fj = s => s && s.length===8 ? s.slice(6,8)+'/'+s.slice(4,6) : s;
    mk('qa-ch-jour', {type:'bar',
      data:{labels:A.jours.map(x=>fj(x.j)), datasets:[{label:'Ménages',
        data:A.jours.map(x=>x.n), backgroundColor:'#0d9488', borderWidth:0}]},
      options:{...OPT, plugins:{legend:{display:false}},
        scales:{y:{beginAtZero:true, grid:{color:'#eef2f7'}},
                x:{grid:{display:false}}}}});
  }
  if(A.durees){
    mk('qa-ch-dur', {type:'bar',
      data:{labels:A.durees.libelles, datasets:[
        {label:'Cet agent', data:A.durees.agent, backgroundColor:'#0d9488',
         borderWidth:0},
        {label:'Sa zone', data:A.durees.zone, backgroundColor:'#cbd5e1',
         borderWidth:0}]},
      options:{...OPT,
        plugins:{legend:{position:'bottom', labels:{boxWidth:10, font:{size:11}}},
          tooltip:{callbacks:{label:c=>c.dataset.label+' : '+c.raw
            +' % de ses entretiens'}}},
        scales:{y:{beginAtZero:true, ticks:{callback:v=>v+' %'},
                   grid:{color:'#eef2f7'}},
                x:{title:{display:true, text:"durée de l'entretien, en minutes"},
                   grid:{display:false}}}}});
  }
}

// ---- Qualité de la base : quatre lectures graphiques ----------------
// Les mêmes chiffres que les fiches d'indicateurs, mais vus d'un coup. Tout
// est en POURCENTAGES : le RSU couvre un tiers des ménages et le RGPH-3 est
// un échantillon au dixième, superposer des effectifs ne comparerait que des
// tailles d'échantillon.
if(VAD.qb){
  const G = VAD.qb.g || {}, R = VAD.qb.resume || {}, C = VAD.qb.cov || [];
  if(G.pyramide && G.pyramide.length){
    const P = G.pyramide, L = P.map(x=>x.groupe);
    const ds = [
      {label:'Hommes (RSU)', data:P.map(x=>-x.sH), backgroundColor:'#2563eb',
       borderWidth:0, order:3},
      {label:'Femmes (RSU)', data:P.map(x=>x.sF), backgroundColor:'#ec4899',
       borderWidth:0, order:3}];
    if(G.rgph){
      ds.push({type:'line', label:'RGPH-3 hommes', data:P.map(x=>-x.rH),
        borderColor:'#0f172a', borderWidth:2, borderDash:[4,3], pointRadius:2,
        pointBackgroundColor:'#0f172a', fill:false, order:1});
      ds.push({type:'line', label:'RGPH-3 femmes', data:P.map(x=>x.rF),
        borderColor:'#7c3aed', borderWidth:2, borderDash:[4,3], pointRadius:2,
        pointBackgroundColor:'#7c3aed', fill:false, order:1});
    }
    mk('qb-ch-pyr', {type:'bar', data:{labels:L, datasets:ds},
      options:{...OPT, indexAxis:'y',
        scales:{x:{ticks:{callback:v=>Math.abs(v)+' %'},
                   grid:{color:'#eef2f7'}},
                y:{reverse:true, grid:{display:false}}},
        plugins:{legend:{position:'bottom',
            labels:{boxWidth:10, padding:10, font:{size:11}}},
          tooltip:{callbacks:{label:c=>c.dataset.label+' : '
            + Math.abs(c.raw).toFixed(2) + ' %'}}}}});
  }
  if(C.length){
    mk('qb-ch-cov', {type:'bar',
      data:{labels:C.map(x=>x.n), datasets:[{label:'Couverture',
        data:C.map(x=>x.t), borderWidth:0,
        backgroundColor:C.map(x=> x.t<25?'#ef4444' : x.t<45?'#f59e0b' : '#10b981')}]},
      options:{...OPT, indexAxis:'y',
        plugins:{legend:{display:false},
          tooltip:{callbacks:{label:c=>c.raw+' % des ménages dénombrés'}}},
        scales:{x:{beginAtZero:true, ticks:{callback:v=>v+' %'},
                   grid:{color:'#eef2f7'}}, y:{grid:{display:false}}}}});
  }
  if(G.chiffres && G.chiffres.length){
    const D = G.chiffres;
    mk('qb-ch-dig', {type:'bar',
      data:{labels:D.map(x=>x.d), datasets:[{label:'Part des âges', data:D.map(x=>x.p),
        borderWidth:0,
        backgroundColor:D.map(x=> Math.abs(x.p-10)>=3 ? '#f59e0b' : '#94a3b8')},
        {type:'line', label:'Attendu (10 %)', data:D.map(()=>10),
         borderColor:'#ef4444', borderWidth:2, borderDash:[5,4], pointRadius:0,
         fill:false}]},
      options:{...OPT,
        plugins:{legend:{position:'bottom', labels:{boxWidth:10, font:{size:11}}},
          tooltip:{callbacks:{label:c=>c.dataset.label+' : '+c.raw+' %'}}},
        scales:{y:{beginAtZero:true, ticks:{callback:v=>v+' %'},
                   grid:{color:'#eef2f7'}},
                x:{title:{display:true, text:"dernier chiffre de l'âge déclaré"},
                   grid:{display:false}}}}});
  }
  mk('qb-ch-res', {type:'doughnut',
    data:{labels:['En alerte','À surveiller','Conformes','Non calculés'],
      datasets:[{data:[R.alerte||0, R.vigilance||0, R.ok||0, R.nd||0],
        backgroundColor:['#ef4444','#f59e0b','#10b981','#cbd5e1'],
        borderWidth:0, hoverOffset:6}]},
    options:{...OPT, cutout:'62%',
      plugins:{legend:{position:'bottom',
        labels:{boxWidth:10, padding:10, font:{size:11}}}}}});
}

// ---- Matrice des tests de qualité : filtre + ouverture d'une fiche ----
// Le tableau est rendu par le serveur ; le navigateur ne fait que le filtrer
// (aucune donnée n'est recalculée ici). Sans JavaScript, le tableau reste
// lisible et chaque agent cliquable par son lien.
(function(){
  const tb = document.querySelector('table.qm tbody');
  if(!tb) return;
  const f = el('qm-f'), a = el('qm-a'), vide = el('qm-vide');
  const lignes = Array.from(tb.querySelectorAll('tr[data-k]'));
  const filtrer = () => {
    const q = (f && f.value || '').trim().toLowerCase();
    const seulAl = !!(a && a.checked);
    let n = 0;
    lignes.forEach(tr => {
      const ok = (!q || tr.dataset.k.indexOf(q) >= 0)
              && (!seulAl || tr.dataset.al === '1');
      tr.style.display = ok ? '' : 'none';
      if(ok) n++;
    });
    // Un en-tête de commune ne s'affiche que s'il reste une ligne dessous.
    Array.from(tb.querySelectorAll('tr.qm-com')).forEach(h => {
      let v = false;
      for(let x = h.nextElementSibling; x && !x.classList.contains('qm-com');
          x = x.nextElementSibling){
        if(x.style.display !== 'none'){ v = true; break; }
      }
      h.style.display = v ? '' : 'none';
    });
    if(vide) vide.style.display = n ? 'none' : '';
  };
  if(f) f.addEventListener('input', filtrer);
  if(a) a.addEventListener('change', filtrer);
  // Clic n'importe où sur la ligne = ouvrir la fiche détaillée de l'agent
  // (le lien sur le nom de l'AE reste, pour le clavier et le clic-droit).
  tb.addEventListener('click', ev => {
    if(ev.target.closest('a')) return;
    const tr = ev.target.closest('tr[data-u]');
    if(tr) location.href = tr.dataset.u;
  });
})();
// ---- Erreurs de saisie : un listing filtré dans le navigateur ----
// Chaque contrôle est une COLONNE : la cellule porte le message de correction
// quand l'erreur est présente, et reste vide sinon.
if(VAD.saisie){
  const S = VAD.saisie, pref = S.pref, lignes = S.lignes;
  // `fig` = colonne figée à gauche pendant le défilement horizontal.
  const BASE = {
    men:[['nom_cm','Chef de ménage',1],['fokontany','Fokontany'],['commune','Commune'],
         ['district','District'],['ce','Chef d\'équipe'],['agent','Agent (AE)'],
         ['date','Date'],['statut','Statut'],['key','Interview']],
    ind:[['membre','Membre',1],['ligne','N°'],['age','Âge'],['nom_cm','Chef de ménage'],
         ['fokontany','Fokontany'],['commune','Commune'],['district','District'],
         ['ce','Chef d\'équipe'],['agent','Agent (AE)'],['date','Date'],
         ['statut','Statut'],['key','Interview']]
  }[pref];
  const jolieDate = d => (d && d.length===8) ? d.slice(6,8)+'/'+d.slice(4,6)+'/'+d.slice(0,4) : '';
  const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const zone = el('f-'+pref);
  if(zone){
    const tbl = el('t-'+pref);
    // Deux rangées d'en-tête : le groupe, puis le nom de chaque colonne.
    tbl.querySelector('thead').innerHTML =
      '<tr class="gr"><th class="fig"></th>'
        + '<th colspan="'+(BASE.length-1)+'">Identification</th>'
        + '<th>Erreurs</th>'
        + '<th colspan="'+S.regles.length+'">Contrôles</th></tr>'
      + '<tr class="hd">'
        + BASE.map(c => '<th'+(c[2]?' class="fig"':'')+'>'+esc(c[1])+'</th>').join('')
        + '<th>Nb</th>'
        + S.regles.map(r => '<th class="sai-err" title="'+esc(r.aide)+'">'
            + esc(r.lib) + '<span class="sai-var">' + esc(r.code) + '</span></th>').join('')
      + '</tr>';
    const tb = tbl.querySelector('tbody');
    ['district','commune','fokontany','ce','agent','statut'].forEach(champ => {
      const sel = zone.querySelector('[data-f="'+champ+'"]');
      if(!sel) return;
      [...new Set(lignes.map(l => l[champ]).filter(v => v!==null && v!==''))]
        .sort().forEach(v => {
          const o = document.createElement('option');
          o.value = v; o.textContent = v; sel.appendChild(o);
        });
    });
    const valeurs = () => {
      const v = {};
      zone.querySelectorAll('[data-f]').forEach(e => v[e.dataset.f] = e.value.trim());
      return v;
    };
    function garde(l, v){
      for(const c of ['district','commune','fokontany','ce','agent']){
        if(v[c] && l[c] !== v[c]) return false;
      }
      if(v.statut && String(l.statut) !== v.statut) return false;
      if(v.erreur && !(l.erreurs||[]).includes(v.erreur)) return false;
      // Les dates sont stockées en AAAAMMJJ : la comparaison de chaînes suffit.
      if(v.du && (!l.date || l.date < v.du.replace(/-/g,''))) return false;
      if(v.au && (!l.date || l.date > v.au.replace(/-/g,''))) return false;
      if(v.q){
        const q = v.q.toLowerCase();
        const cible = [l.nom_cm, l.membre, l.key].filter(Boolean).join(' ').toLowerCase();
        if(!cible.includes(q)) return false;
      }
      return true;
    }
    function rendre(){
      const v = valeurs();
      const vues = lignes.filter(l => garde(l, v));
      tb.innerHTML = vues.map(l => {
        const err = new Set(l.erreurs||[]);
        return '<tr>'
          + BASE.map(c => '<td'+(c[2]?' class="fig"':'')+'>'
              + esc(c[0]==='date' ? jolieDate(l.date) : l[c[0]]) + '</td>').join('')
          + '<td><span class="sai-nb">'+err.size+'</span></td>'
          + S.regles.map(r => err.has(r.code)
              ? '<td class="sai-err-on">'+esc(r.msg)+'</td>'
              : '<td class="sai-err-off"></td>').join('')
          + '</tr>';
      }).join('');
      el('c-'+pref).innerHTML = '<b>' + vues.length + '</b> ligne(s) affichée(s) sur '
        + lignes.length + ' — ' + S.regles.length + ' contrôles';
      el('v-'+pref).hidden = vues.length > 0;
    }
    zone.querySelectorAll('[data-f]').forEach(e => {
      e.addEventListener('input', rendre); e.addEventListener('change', rendre);
    });
    zone.querySelector('[data-raz]').addEventListener('click', () => {
      zone.querySelectorAll('[data-f]').forEach(e => e.value = ''); rendre();
    });
    rendre();
  }
}
// ---- Vue globale ----
if(VAD.jour){
  const L = VAD.jour.map(x=>x.d.slice(6,8)+'/'+x.d.slice(4,6));
  mk('ch-jour', {data:{labels:L, datasets:[
    {type:'bar', label:'Interviews du jour', data:VAD.jour.map(x=>x.n),
     backgroundColor:'#2563eb99', borderRadius:5, order:2},
    {type:'line', label:'Cumul', data:VAD.jour.map(x=>x.cumul), borderColor:'#10b981',
     backgroundColor:'#10b98122', tension:.3, fill:true, yAxisID:'y1', order:1}]},
    options:{...OPT, scales:{y:{beginAtZero:true},
      y1:{position:'right', beginAtZero:true, grid:{drawOnChartArea:false}}}}});
}
if(VAD.statut) donut('ch-statut', VAD.statut.map(x=>x.lib), VAD.statut.map(x=>x.n));
// ---- Démographie ----
if(VAD.pyramide){
  const g = VAD.pyramide.map(x=>x.groupe);
  mk('ch-pyramide', {type:'bar', data:{labels:g, datasets:[
    {label:'Hommes', data:VAD.pyramide.map(x=>-x.H), backgroundColor:'#2563eb'},
    {label:'Femmes', data:VAD.pyramide.map(x=>x.F), backgroundColor:'#ec4899'}]},
    options:{...OPT, indexAxis:'y',
      scales:{x:{stacked:true, ticks:{callback:v=>Math.abs(v)}},
              y:{stacked:true, reverse:true}},
      plugins:{legend:{position:'bottom'},
        tooltip:{callbacks:{label:c=>c.dataset.label+' : '+Math.abs(c.raw)}}}}});
  if(VAD.pyramideRgph){
    const brutR = VAD.pyramideRgph.map(x=>x.ratio);
    const mascR = brutR.map(v=> v==null ? null : Math.min(v, 300));
    mk('ch-masc-rgph', {type:'bar', data:{labels:VAD.pyramideRgph.map(x=>x.groupe),
      datasets:[{label:'Hommes / 100 femmes', data:mascR,
        backgroundColor:brutR.map(v=> v==null?'#cbd5e1':(v>=100?'#2563eb':'#ec4899'))}]},
      options:{...OPT, indexAxis:'y',
        plugins:{legend:{display:false},
          tooltip:{callbacks:{label:c=> brutR[c.dataIndex]==null
            ? 'effectif trop faible' : brutR[c.dataIndex]+' hommes pour 100 femmes'}}},
        scales:{y:{reverse:true}, x:{suggestedMax:200}}}});
    mk('ch-pyramide-rgph', {type:'bar', data:{labels:VAD.pyramideRgph.map(x=>x.groupe),
      datasets:[
      {label:'Hommes', data:VAD.pyramideRgph.map(x=>-x.H), backgroundColor:'#2563eb'},
      {label:'Femmes', data:VAD.pyramideRgph.map(x=>x.F), backgroundColor:'#ec4899'}]},
      options:{...OPT, indexAxis:'y',
        scales:{x:{stacked:true, ticks:{callback:v=>Math.abs(v)}},
                y:{stacked:true, reverse:true}},
        plugins:{legend:{position:'bottom'},
          tooltip:{callbacks:{label:c=>c.dataset.label+' : '+Math.abs(c.raw)}}}}});
  }
  // Ratio calculé par le SERVEUR (null = effectif féminin trop faible) ; on
  // plafonne l'AFFICHAGE à 300 pour qu'un groupe extrême n'écrase pas l'échelle
  // — la valeur réelle reste dans l'infobulle.
  const brut = VAD.pyramide.map(x=>x.ratio);
  const masc = brut.map(v=> v==null ? null : Math.min(v, 300));
  mk('ch-masc', {type:'bar', data:{labels:g, datasets:[{label:'Hommes / 100 femmes',
      data:masc, backgroundColor:brut.map(v=> v==null?'#cbd5e1':(v>=100?'#2563eb':'#ec4899'))}]},
    options:{...OPT, indexAxis:'y',
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=> brut[c.dataIndex]==null
          ? 'effectif trop faible' : brut[c.dataIndex]+' hommes pour 100 femmes'}}},
      scales:{y:{reverse:true}, x:{suggestedMax:200}}}});
}
if(VAD.niveau) barH('ch-niveau', VAD.niveau.map(x=>x.lib), VAD.niveau.map(x=>x.n), 'Personnes');
// ---- Habitation ----
['murs','toit','sol','eclairage'].forEach(k=>{
  if(VAD[k]) donut('ch-'+(k==='murs'?'murs':k), VAD[k].map(x=>x.lib), VAD[k].map(x=>x.n));
});
// ---- Biens ----
if(VAD.biens) barH('ch-biens', VAD.biens.map(x=>x.lib), VAD.biens.map(x=>x.pct), '% de ménages');
// ---- Eau ----
if(VAD.eau) barH('ch-eau', VAD.eau.map(x=>x.lib), VAD.eau.map(x=>x.n), 'Ménages');
if(VAD.sanit) barH('ch-sanit', VAD.sanit.map(x=>x.lib), VAD.sanit.map(x=>x.n), 'Ménages');
// ---- Dépliage du sous-menu des zones (flèches) ----
// La liste entière se replie par le bandeau « Communes » (état mémorisé), et
// chaque commune s'ouvre par sa flèche, sans quitter la page.
(function(){
  const tete = document.querySelector('.vad-drill-tete');
  if(tete){
    const liste = el('vad-drill-liste'), K = 'rsu_vad_drill';
    const pose = ouvert => {
      liste.hidden = !ouvert;
      tete.querySelector('.c').textContent = ouvert ? '▾' : '▸';
      tete.setAttribute('aria-expanded', String(ouvert));
      try{ localStorage.setItem(K, ouvert ? '1' : '0'); }catch(e){}
    };
    let v = null;
    try{ v = localStorage.getItem(K); }catch(e){}
    pose(v === null ? true : v === '1');
    tete.addEventListener('click', () => pose(liste.hidden));
  }
  document.querySelectorAll('.vad-caret').forEach(b => {
    b.addEventListener('click', () => {
      const sous = document.querySelector('.nav-sub2[data-fkt="' + b.dataset.com + '"]');
      if(!sous) return;
      sous.hidden = !sous.hidden;
      b.textContent = sous.hidden ? '▸' : '▾';
      b.setAttribute('aria-expanded', String(!sous.hidden));
    });
  });
})();

// ══════════════════════════════════════════════════════════════════
//  CARTE GPS — même fonctionnement que celle du dénombrement (/vue/gps) :
//  fonds satellite, un point par ménage COLORÉ PAR AGENT, filtre agent par le
//  sélecteur de calques, filtre par date, contours du district (rouge) et des
//  communes (bleu). Les contours sont chargés à part : ils pèsent trop pour
//  être écrits dans la page (cf. limites_db.contours_zones).
// ══════════════════════════════════════════════════════════════════
const PALETTE = ['#2563eb','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4',
  '#ec4899','#84cc16','#f97316','#14b8a6','#6366f1','#eab308'];
const colorOf = i => PALETTE[i % PALETTE.length];

function dateFr(d){
  return (d && d.length===8) ? d.slice(6,8)+'/'+d.slice(4,6)+'/'+d.slice(0,4) : '—';
}

if(VAD.points && el('vadmap')){
  const pts = VAD.points;
  const map = L.map('vadmap', {preferCanvas:true, maxZoom:21});

  // Fonds satellite. maxNativeZoom = dernier niveau où la source a réellement des
  // tuiles ; au-delà, Leaflet agrandit la dernière disponible au lieu d'afficher
  // des cases grises. (Mêmes fonds que la carte du dénombrement.)
  const BingLayer = L.TileLayer.extend({
    getTileUrl: function(c){
      let q = '';
      for(let i=c.z; i>0; i--){
        let d = 0, m = 1 << (i-1);
        if(c.x & m) d += 1;
        if(c.y & m) d += 2;
        q += d;
      }
      return 'https://ecn.t'+(Math.abs(c.x)%4)+'.tiles.virtualearth.net/tiles/a'+q+'.jpeg?g=1';
    }
  });
  const bases = {
    'Bing Aérien (le plus net)': new BingLayer('',{
      maxZoom:21, maxNativeZoom:19, attribution:'Imagerie © Microsoft / Maxar'}),
    'Google Satellite': L.tileLayer('https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',{
      subdomains:['0','1','2','3'], maxZoom:21, maxNativeZoom:19,
      attribution:'Imagerie © Google'}),
    'Google Hybride (routes)': L.tileLayer('https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',{
      subdomains:['0','1','2','3'], maxZoom:21, maxNativeZoom:19,
      attribution:'Imagerie © Google'}),
    'Esri World Imagery': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{
      maxZoom:21, maxNativeZoom:17, attribution:'Tiles © Esri'}),
    'OpenStreetMap': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:19, attribution:'© OpenStreetMap'})
  };
  bases['Bing Aérien (le plus net)'].addTo(map);
  const labels = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png',
    {maxZoom:21, maxNativeZoom:20, opacity:0.8}).addTo(map);
  L.control.scale({imperial:false}).addTo(map);

  // Deux modes, comme la carte du dénombrement :
  //  • PEU d'agents -> couleur = AGENT + case par agent dans le sélecteur de calques ;
  //  • BEAUCOUP -> couleur = DATE (un district compte >100 agents : une liste de
  //    cases par agent serait illisible, et 12 couleurs ne les distinguent pas).
  // Le filtre par date, lui, marche dans les deux cas.
  const GRIS = '#94a3b8';
  const agents = [...new Set(pts.map(p=>p.ag).filter(Boolean))].sort();
  const dates  = [...new Set(pts.map(p=>p.date).filter(Boolean))].sort();
  const parAgent = agents.length > 0 && agents.length <= PALETTE.length;
  const groupes = parAgent ? agents.slice() : dates.slice();
  const couleur = {};
  groupes.forEach((k,i)=>couleur[k]=colorOf(i));
  const cleDe = p => (parAgent ? (p.ag||'') : (p.date||''));
  const cles = groupes.slice();
  if(pts.some(p=>!cleDe(p))) cles.push('');

  // ---- LIAISON AU DÉNOMBREMENT ------------------------------------
  // Le même logement a été géolocalisé au dénombrement, deux mois plus tôt.
  // On le montre en ANTHRACITE — une couleur FIXE, absente de la palette des
  // agents et des dates, pour qu'aucun point de dénombrement ne puisse être
  // pris pour un point VAD —, en plus petit, relié par un trait pointillé.
  // Les ménages dénombrés SANS correspondance VAD ne sont pas envoyés par le
  // serveur : la carte décrit la visite à domicile, pas le dénombrement.
  const DEN = '#111827';
  const denGroupe = L.layerGroup();
  // Registre des paires (visite ↔ dénombrement). Il sert au lien « aller voir
  // l'autre point » des deux popups : chacun ne connaît que son INDICE, et le
  // gestionnaire de clic retrouve la cible ici. Passer par un indice plutôt
  // que par une fonction globale évite d'exposer les marqueurs au reste de la
  // page, et un seul écouteur suffit pour toutes les paires.
  const paires = [];
  const LIEN = 'color:#2563eb;font-size:11px;font-weight:600;text-decoration:none;'
             + 'display:inline-block;margin-top:7px;cursor:pointer';
  const nLies = pts.filter(p=>p.dd!=null).length;

  const overlays = {}, marqueurs = [];
  cles.forEach(k=>{
    const groupe = L.layerGroup();
    pts.filter(p=>cleDe(p)===k).forEach(p=>{
      // L'indice est réservé AVANT de construire le popup : celui de la visite
      // doit déjà pouvoir désigner un point de dénombrement créé après lui.
      const idx = (p.dd!=null) ? paires.push(null) - 1 : -1;
      const mk = L.circleMarker([p.lat,p.lon],{
        radius:5, weight:1.5, color:'#ffffff',
        fillColor:(k===''?GRIS:couleur[k]), fillOpacity:0.9
      }).bindPopup(`<div style="min-width:180px">
          <div style="font-size:11px;color:#64748b">Ménage</div>
          <div style="font-weight:700;font-size:13px;margin-bottom:6px;font-family:ui-monospace,monospace">${p.c||'—'}</div>
          <div style="font-size:11px;color:#64748b">Chef de ménage</div>
          <div style="font-weight:700;font-size:13px;margin-bottom:6px">${p.nom||'—'}</div>
          <div style="font-size:11px;color:#64748b">Date de l'entretien</div>
          <div style="font-weight:600;font-size:12px;margin-bottom:6px">${dateFr(p.date)}</div>
          <div style="font-size:11px;color:#64748b">Code agent</div>
          <div style="font-weight:600;font-size:12px;margin-bottom:6px">${p.ag||'—'}</div>
          <div style="font-size:11px;color:#64748b">Fokontany</div>
          <div style="font-weight:600;font-size:12px;margin-bottom:6px">${p.f||'—'}${p.cm?' · '+p.cm:''}</div>
          <div style="font-size:11px;color:#64748b">Membres · précision GPS</div>
          <div style="font-weight:600;font-size:12px;margin-bottom:${p.dd!=null?'6px':'0'}">${p.n!=null?p.n:'—'} · ${p.acc!=null?p.acc+' m':'—'}</div>`
        + (p.dd!=null
           ? `<div style="font-size:11px;color:#64748b">Écart au point du dénombrement</div>
          <div style="font-weight:700;font-size:13px;color:${DEN}">${p.dd} m</div>
          <a href="#" class="vm-go" data-i="${idx}" data-c="den" style="${LIEN}">→ Voir le point du dénombrement</a>`
           : `<div style="font-size:11px;color:#94a3b8;font-style:italic">Aucun point de dénombrement pour ce ménage</div>`)
        + `</div>`);
      mk._grp = groupe; mk._date = p.date;
      groupe.addLayer(mk); marqueurs.push(mk);
      // Point d'origine + trait de liaison, suspendus au marqueur VAD : les
      // filtres par agent et par date les emportent avec lui, sans quoi la
      // carte garderait des traits pendants vers des points masqués.
      if(p.dd!=null){
        const trait = L.polyline([[p.lat,p.lon],[p.dl,p.dg]],
          {color:DEN, weight:1.5, opacity:0.6, dashArray:'3,4', interactive:false});
        const pd = L.circleMarker([p.dl,p.dg],{
          radius:3.5, weight:1, color:'#ffffff', fillColor:DEN, fillOpacity:0.95
        }).bindPopup(`<div style="min-width:180px">
            <div style="font-size:11px;color:#64748b">Point du DÉNOMBREMENT</div>
            <div style="font-weight:700;font-size:13px;margin-bottom:6px;font-family:ui-monospace,monospace">${p.c||'—'}</div>
            <div style="font-size:11px;color:#64748b">Chef de ménage (VAD)</div>
            <div style="font-weight:700;font-size:13px;margin-bottom:6px">${p.nom||'—'}</div>
            <div style="font-size:11px;color:#64748b">Écart au point de la visite</div>
            <div style="font-weight:700;font-size:13px;color:${DEN}">${p.dd} m</div>
            <a href="#" class="vm-go" data-i="${idx}" data-c="vad" style="${LIEN}">→ Revenir au point de la visite</a>
          </div>`);
        paires[idx] = {vad:mk, den:pd, grp:groupe};
        mk._den = [pd, trait];
        denGroupe.addLayer(pd); denGroupe.addLayer(trait);
      }
    });
    groupe.addTo(map);
    // Case par agent : seulement en mode « par agent » (sinon >100 cases).
    if(parAgent) overlays[k===''?'(agent inconnu)':k] = groupe;
  });
  if(nLies){
    denGroupe.addTo(map);
    overlays['Points du dénombrement (' + nLies + ')'] = denGroupe;
  }
  overlays['Noms de lieux'] = labels;

  // Aller d'un point à son jumeau. La cible peut avoir été masquée par un
  // filtre ou par la case du calque : on la rend visible avant de s'y rendre,
  // sinon le clic ne produirait rien et passerait pour un bug.
  map.on('popupopen', ev=>{
    const dom = ev.popup.getElement();
    if(!dom) return;
    dom.querySelectorAll('.vm-go').forEach(a=>{
      a.onclick = e=>{
        e.preventDefault();
        const P = paires[+a.dataset.i];
        if(!P) return;
        const versDen = a.dataset.c === 'den';
        const cible = versDen ? P.den : P.vad;
        if(versDen && !map.hasLayer(denGroupe)) denGroupe.addTo(map);
        if(!versDen && P.grp && !map.hasLayer(P.grp)) P.grp.addTo(map);
        if(versDen && !denGroupe.hasLayer(cible)) denGroupe.addLayer(cible);
        if(!versDen && P.grp && !P.grp.hasLayer(cible)) P.grp.addLayer(cible);
        map.closePopup();
        // Ouverture DIFFÉRÉE plutôt qu'au 'moveend' : quand les deux points
        // sont quasi confondus, la vue ne bouge pas et 'moveend' ne part
        // jamais — le popup ne s'ouvrirait pas, ce qui se lirait comme un lien
        // cassé alors que c'est le cas le plus sain (écart nul).
        map.flyTo(cible.getLatLng(), Math.max(map.getZoom(), 18), {duration:0.6});
        setTimeout(()=>cible.openPopup(), 700);
      };
    });
  });

  if(marqueurs.length) map.fitBounds(L.featureGroup(marqueurs).getBounds().pad(0.15));
  else map.setView([-18.9,47.5], 6);
  const controle = L.control.layers(bases, overlays, {collapsed:false}).addTo(map);

  // Filtre par DATE : un bouton par date, composable avec le filtre agent (le
  // marqueur est retiré de SON groupe, donc les deux filtres se cumulent).
  const barre = el('vadmap-filters');
  dates.forEach((d,i)=>{
    const b = document.createElement('button');
    b.className = 'ar-tab active';
    b.innerHTML = parAgent ? dateFr(d)
      : '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        + 'background:' + couleur[d] + ';margin-right:5px;vertical-align:middle"></span>'
        + dateFr(d);
    b.onclick = ()=>{
      b.classList.toggle('active');
      const visible = b.classList.contains('active');
      marqueurs.forEach(mk=>{
        if(mk._date!==d) return;
        visible ? mk._grp.addLayer(mk) : mk._grp.removeLayer(mk);
        (mk._den||[]).forEach(o=>
          visible ? denGroupe.addLayer(o) : denGroupe.removeLayer(o));
      });
    };
    barre.appendChild(b);
  });

  // Contours : district en ROUGE, communes en BLEU, comme au dénombrement.
  // Chargés à part et ajoutés dès qu'ils arrivent : la carte est utilisable sans.
  const ROUGE = {color:'#ff2d2d', weight:3, opacity:0.9, fill:false, interactive:false};
  const BLEU  = {color:'#2563ff', weight:2, opacity:0.85, fill:false, interactive:false};
  // La zone affichée suit la descente : le contour rouge est le NIVEAU COURANT
  // (district, commune ou fokontany), les bleus sont ses enfants.
  const zone = VAD.zone || {};
  const qz = [];
  if(zone.fokontany) qz.push('fokontany=' + encodeURIComponent(zone.fokontany));
  else if(zone.commune) qz.push('commune=' + encodeURIComponent(zone.commune));
  const LIB = {district:['du district','des communes'],
               commune:['de la commune','des fokontany'],
               fokontany:['du fokontany','']};
  fetch((VAD.pref||'')+'/vad/contours.json'+(qz.length?'?'+qz.join('&'):''))
   .then(r=>r.ok?r.json():null).then(c=>{
    if(!c) return;
    const lib = LIB[c.niveau] || LIB.district;
    const princ = Object.values(c.principal||{}).map(a=>L.polygon(a, ROUGE));
    const sous  = Object.values(c.sous||{}).map(a=>L.polygon(a, BLEU));
    if(sous.length){
      const g = L.featureGroup(sous).addTo(map);
      controle.addOverlay(g, 'Limites ' + lib[1]);
    }
    if(princ.length){
      const g = L.featureGroup(princ).addTo(map);
      controle.addOverlay(g, 'Limite ' + lib[0]);
      if(g.bringToFront) g.bringToFront();      // le rouge au-dessus du bleu
      // Cadrage sur la ZONE, pas sur les points : un seul relevé aberrant
      // (coordonnée de repli d'un appareil, à 80 km) suffit à étirer la vue au
      // point que la zone n'est plus qu'une tache. Le point aberrant reste
      // atteignable en dézoomant — et il est signalé par le test 8.4.
      map.fitBounds(g.getBounds().pad(0.05));
    }
    const note = el('vadmap-note');
    if(note && (princ.length || sous.length)){
      note.innerHTML += ' Le <strong>contour rouge</strong> est la limite ' + lib[0]
        + (sous.length ? ', les <strong>contours bleus</strong> celles ' + lib[1] : '')
        + '.';
    }
  }).catch(()=>{});

  const note = el('vadmap-note');
  if(note){
    note.innerHTML = 'Chaque point représente un ménage interviewé et géolocalisé. '
      + (parAgent
         ? 'La <strong>couleur du point correspond à l\'agent enquêteur</strong> ('
           + agents.length + ' agent(s)) : filtrez <strong>par agent</strong> avec les '
           + 'cases du sélecteur de calques, en haut à droite, et '
         : 'La <strong>couleur du point correspond à la date</strong> de l\'entretien ('
           + agents.length + ' agents sur ce périmètre, trop nombreux pour une couleur '
           + 'chacun) : filtrez ')
      + '<strong>par date</strong> avec les boutons ci-dessus. '
      + 'Cliquez sur un point pour voir le détail du ménage et son agent.'
      + (nLies
         ? ' Les <span style="display:inline-block;width:9px;height:9px;'
           + 'border-radius:50%;background:' + DEN + ';border:1px solid #fff;'
           + 'vertical-align:middle"></span> <strong>petits points anthracite</strong> '
           + 'sont les positions relevées au <strong>dénombrement</strong> ('
           + nLies + ' ménage(s) appariés sur ' + pts.length + ') : un trait '
           + 'pointillé les relie à la visite, et le popup donne l\'écart en '
           + 'mètres ainsi qu\'un lien pour <strong>sauter d\'un point à '
           + 'l\'autre</strong>. Les ménages dénombrés sans correspondance VAD '
           + 'ne sont pas affichés.'
         : ' Aucun ménage de ce périmètre n\'est apparié au dénombrement : '
           + 'les positions d\'origine ne peuvent pas être affichées.');
  }
  setTimeout(()=>map.invalidateSize(), 200);
}
"""


# ---------------------------------------------------------------------------
# Espace TRAITEMENT : téléversement + transcription des données VAD
# ---------------------------------------------------------------------------
def page_ingestion(district_txt, etat=None, apercu=None, resultat=None,
                   message=None, erreur=None, historique=None) -> str:
    """Page « Transcription — Visite à domicile » de l'espace EXPERT SURVEY.

    C'est l'Expert survey qui ingère les données du terrain — dénombrement ET
    visite à domicile. Deux temps, comme pour le dénombrement : on TÉLÉVERSE le
    dossier d'export (validé et rangé, mais rien n'entre encore en base), puis on
    TRANSCRIT une fois l'aperçu vérifié."""
    import transcription
    h = [transcription._entete(),
         '<p style="margin:0 0 6px"><a href="/transcription">'
         '&larr; Choix du type de données</a></p>',
         '<h1>Transcription — Visite à domicile (VAD)</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>. '
         'La VAD est la 2ᵉ phase du RSU : l’entretien complet dans les ménages '
         '(composition, habitation, biens, eau et assainissement). Téléversez le '
         '<b>dossier d’export Survey Solutions</b> du questionnaire RSUe, puis '
         'transcrivez-le vers la base.</div>']
    if etat and etat.get("menages"):
        h.append(f'<div class="msg">Déjà en base pour ce district : '
                 f'<b>{_n(etat["menages"])}</b> ménage(s) VAD et '
                 f'<b>{_n(etat["membres"])}</b> membre(s).</div>')
    if message:
        h.append(f'<div class="msg">{ESC(message)}</div>')
    if erreur:
        h.append(f'<div class="err">{erreur}</div>')

    if apercu:
        f = apercu.get("fichiers", {})
        lig = apercu.get("lignes", {})
        h.append('<h2>Aperçu du dossier téléversé</h2>')
        h.append('<table><tr><th>Contenu</th><th>Fichier</th><th>Lignes</th></tr>'
                 + "".join(
                     f'<tr><td>{lib}</td><td>{ESC(str(f.get(k) or "— absent —"))}</td>'
                     f'<td>{_n(lig.get(k))}</td></tr>'
                     for k, lib in (("menage", "Ménages interviewés"),
                                    ("membre", "Membres des ménages"),
                                    ("diagnostics", "Diagnostics (agent, statut)")))
                 + '</table>')
        if apercu.get("districts"):
            h.append('<div class="note">Districts présents dans le fichier : '
                     + ", ".join(f"<b>{ESC(d)}</b> ({_n(n)})"
                                 for d, n in apercu["districts"].items())
                     + '.</div>')
        if apercu.get("ecartes"):
            h.append('<div class="err">⚠️ <b>' + _n(apercu["ecartes"])
                     + ' ménage(s) hors de votre district</b> ont été écartés : '
                     'ils ne seront pas transcrits. Le reste du dossier l’est '
                     'normalement.</div>')
        if apercu.get("dates"):
            d = apercu["dates"]
            h.append(f'<div class="note">Période de collecte : du '
                     f'<b>{_date(d[0])}</b> au <b>{_date(d[-1])}</b> · '
                     f'<b>{_n(apercu.get("agents"))}</b> agent(s).</div>')
        h.append('<form method="post" action="/transcription/vad/transcrire">'
                 '<button>Transcrire vers la base de données</button></form>')

    if resultat:
        h.append('<h2>Bilan de la transcription</h2>')
        h.append('<table><tr><th>Table</th><th>Ajoutées</th><th>Mises à jour</th>'
                 '<th>Inchangées</th></tr>'
                 + "".join(
                     f'<tr><td>{ESC(t["table"])}</td><td>+{t["ajoutes"]}</td>'
                     f'<td>~{t["modifies"]}</td><td>={t["inchanges"]}</td></tr>'
                     for t in resultat["tables"]) + '</table>')

    h.append('<h2>Téléverser le dossier d’export VAD</h2>')
    h.append(
        '<form method="post" action="/transcription/vad/upload" '
        'enctype="multipart/form-data" class="grid-form">'
        '<div><label>Dossier d’export Survey Solutions (format <b>STATA</b>) — '
        'choisissez le DOSSIER, pas les fichiers un par un</label>'
        '<input type="file" name="dossier" webkitdirectory directory multiple '
        'required></div>'
        '<div style="align-self:end"><button>Téléverser et vérifier</button></div>'
        '</form>')
    h.append(
        '<div class="note"><b>Ce que le dossier doit contenir</b> : le fichier des '
        '<b>ménages</b> (<code>rsuefkt_…_pil.dta</code>, ou tout .dta portant les '
        'colonnes <code>interview__key</code>, <code>CQ7</code>, <code>CQ9</code>, '
        '<code>nbmembre</code>), le fichier des <b>membres</b> '
        '(<code>RMen.dta</code>) et les <b>diagnostics</b> '
        '(<code>interview__diagnostics.dta</code>). Le sous-dossier '
        '<code>Questionnaire/</code> est conservé mais n’est pas transcrit.<br>'
        'La transcription est <b>additive</b> : elle ajoute les nouvelles '
        'interviews, met à jour celles qui ont changé et ne supprime rien. Les '
        'ménages d’un <b>autre district</b> que le vôtre sont écartés et '
        'signalés.</div>')
    # Historique de CETTE phase uniquement : la VAD a son propre journal, comme
    # le dénombrement a le sien (page_transcription).
    h.append('<h2>Historique — mes opérations de visite à domicile</h2>')
    h.append(transcription._table_historique(
        historique, "Aucun téléversement de visite à domicile pour l’instant."))
    h.append('</div></body></html>')
    return "".join(h)
