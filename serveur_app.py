# -*- coding: utf-8 -*-
"""
serveur_app.py — Application web pilotée par la BASE DE DONNÉES (étape 3).

Différence avec serveur_web.py (le prototype par upload) : ici l'utilisateur
n'envoie plus de fichiers. Le serveur lit la base (SQLite en simulation,
PostgreSQL en production) et, quand on choisit un fokontany, ne génère et
n'envoie QUE ce fokontany.

    Accueil (/)            -> menu Commune -> Fokontany (léger, ~quelques Ko)
    /fokontany/<num_fkt>   -> rapport ALLÉGÉ de ce fokontany (~150 Ko au lieu de 25 Mo)

Le rapport d'un fokontany réutilise LE MÊME gabarit que l'exe, sans modification :
on donne simplement à rapport_core une source filtrée sur ce fokontany
(db_source.source_db(conn, fkt=...)).

⚠️ Toujours un PROTOTYPE local (pas de login/HTTPS). À sécuriser avant mise en ligne
(voir CLAUDE.md §6-7).

Lancement :   python serveur_app.py
"""

import email
import html as htmllib
import http.cookies
import http.server
import json
import os
import re
import secrets
import shutil
import socketserver
import tempfile
import threading
import time
import unicodedata
import urllib.parse

import rapport_core
import db_source
import config
import zones
import utilisateurs
import journal
import admin
import maj_db
import transcription
import logistique
import equipes
import export_rapport
import prechargement
import limites_db

PORT = 8000

# ---------------------------------------------------------------------------
# Authentification (Étape 4) — vérification CÔTÉ SERVEUR + session par cookie.
# Les comptes vivent désormais dans la table `utilisateurs` (module utilisateurs),
# avec mots de passe HACHÉS (PBKDF2). Gérer les comptes : `python utilisateurs.py`.
# ---------------------------------------------------------------------------
PREFIXE = config.PREFIXE            # toute l'appli est servie sous /rsu (config.py)
COOKIE_SESSION = "rsu_session"
# Jetons de session valides -> identifiant connecté.
_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()
# Expiration par INACTIVITÉ : une session sans requête depuis ce délai est invalidée
# (l'utilisateur doit se reconnecter). Le cookie a aussi une durée max absolue (8 h).
INACTIVITE_MAX = 30 * 60   # secondes (30 min)

# Bannière officielle RSU / E-Fokontany affichée sur la page de connexion
# (fournie par un membre du projet, droit d'usage confirmé).
IMAGE_ACCUEIL = os.path.join(config.IMAGES_DIR, "images.jfif")

# Menu Commune -> {code_fokontany: libellé}, construit une fois au démarrage.
ARBRE = {}
TOTAL_MENAGES = 0
# Arbre géographique Province -> Région -> District (référentiel `zones`),
# construit une fois au démarrage pour les listes déroulantes dépendantes.
ARBRE_GEO = {"provinces": [], "regions": {}, "districts": {}}
# Cache des rapports fokontany déjà générés : code -> HTML.
_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _vider_cache() -> None:
    """Purge le cache des rapports. À appeler après tout changement de données
    (transcription du dénombrement) ou de noms d'agents (base CE/Agents) — sinon
    une page mise en cache resservirait d'anciens codes/valeurs."""
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Préparation : base peuplée + menu
# ---------------------------------------------------------------------------
def preparer():
    """Peuple la base si besoin (depuis les .dta) et construit le menu."""
    global ARBRE, TOTAL_MENAGES
    conn = db_source.connect()
    cur = conn.cursor()
    # La table den_menage existe-t-elle ? (sinon : première transcription)
    try:
        cur.execute('SELECT COUNT(*) FROM "den_menage"')
        cur.fetchone()
    except Exception:
        print("Base vide : transcription des .dta…")
        db_source.charger_dta_vers_db(config.DATA_DIR, conn, print)

    den = db_source.DbDataset(conn, "den_menage")
    communes = den.col_decoded("commune")
    fkts = den.col_decoded("fokontany")
    codes = den.col("num_fkt")
    arbre = {}
    for c, f, code in zip(communes, fkts, codes):
        if code is None:
            continue
        commune = (c or "(commune inconnue)")
        scode = str(code)
        label = (f or scode)
        arbre.setdefault(commune, {})
        arbre[commune].setdefault(scode, label)
    ARBRE = arbre

    ros = db_source.DbDataset(conn, "segment_roster")
    TOTAL_MENAGES = ros.nobs

    # Référentiel géographique (Excel FKT_ampiasan_SS) : chargé si absent.
    global ARBRE_GEO
    zones.assurer_zones(conn)
    ARBRE_GEO = zones.arbre_geo(conn)

    # Clés étrangères géographiques de den_menage -> zones : ajoutées à une base
    # antérieure (reconstruction unique, données conservées). Après les zones (cibles).
    if db_source.assurer_fk_den_menage(conn):
        print("den_menage : cles etrangeres vers zones ajoutees (migration).")

    # Comptes de connexion : table + compte d'amorçage si la table est vide.
    utilisateurs.creer_table(conn)
    if utilisateurs.assurer_bootstrap(conn):
        print("ATTENTION : aucun utilisateur -> compte d'amorcage RSU/RSU cree ; "
              "changez-le (python utilisateurs.py passwd RSU).")
    # Journal de connexion / d'utilisation (audit) : tables si absentes.
    journal.creer_tables(conn)
    # Base des Chefs d'Équipe / Agents (remplie par l'Expert Traitement).
    equipes.creer_tables(conn)
    # Clé étrangère agent sur interview__diagnostics (migration SQLite si besoin),
    # puis complétion de `agent` par les codes présents dans le dénombrement.
    if db_source.assurer_fk_diagnostics(conn):
        print("interview__diagnostics : cle etrangere vers agent ajoutee (migration).")
    nb_ag = equipes.synchroniser_agents(conn)
    if nb_ag:
        print(f"agent : {nb_ag} code(s) agent du denombrement ajoute(s) (nom = code).")

    # Limites CORRIGÉES (4 districts) : tables + chargement des shapefiles si la
    # table est vide et le dossier présent. Ces contours remplacent OCHA au rendu.
    limites_db.creer_tables(conn)
    if not limites_db.districts_couverts(conn) and os.path.isdir(config.LIMITES_QUATRE_DIR):
        try:
            bilan = limites_db.charger_shapefiles(conn, log=lambda *_: None)
            t = bilan["totaux"]
            print(f"limites corrigees chargees : {t['district']} district(s), "
                  f"{t['commune']} commune(s), {t['fokontany']} fokontany.")
        except Exception as e:
            print(f"limites corrigees : chargement ignore ({e}).")
    conn.commit()

    conn.close()
    nb_fkt = sum(len(v) for v in ARBRE.values())
    nb_dist = sum(len(v) for v in ARBRE_GEO["districts"].values())
    print(f"Menu prêt : {len(ARBRE)} communes, {nb_fkt} fokontany, "
          f"{TOTAL_MENAGES} ménages.")
    print(f"Zones prêtes : {len(ARBRE_GEO['provinces'])} provinces, "
          f"{sum(len(v) for v in ARBRE_GEO['regions'].values())} régions, "
          f"{nb_dist} districts.")


# ---------------------------------------------------------------------------
# Génération à la demande d'un rapport de fokontany (mise en cache)
# ---------------------------------------------------------------------------
def rapport_fokontany(code: str) -> str:
    with _CACHE_LOCK:
        if code in _CACHE:
            return _CACHE[code]
    conn = db_source.connect()  # une connexion par requête (sûr en multi-thread)
    try:
        tmp = tempfile.mkdtemp(prefix="rsu_fkt_")
        chemins = {
            "rapport": tmp,
            "limites": config.LIMITES_DIR,
            "templates": config.TEMPLATES_DIR,
        }
        out = rapport_core.generer_rapport(
            chemins, source=db_source.source_db(conn, fkt=code),
            assets_url=config.PREFIXE + "/assets",
            agents_noms=equipes.noms_agents(conn),
            contours_override=limites_db.contours_pour(conn, [code]))
        with open(out, "r", encoding="utf-8") as f:
            page = f.read()
    finally:
        conn.close()
    with _CACHE_LOCK:
        _CACHE[code] = page
    return page


# ---------------------------------------------------------------------------
# Génération du rapport de SUIVI d'un DISTRICT (dénombrement)
# ---------------------------------------------------------------------------
# Correspondance : choix de limites de la page de sélection -> mode rapport_core.
_MODE_LIMITES = {"ocha": "integrees", "generer": "auto", "dossier": "dossier"}

# Sections du dashboard multi-pages (une page HTML par section, cf. /vue/<section>).
SECTIONS_VALIDES = {"general", "agent", "zone", "gps", "gpscap",
                    "qualite", "historique", "multi"}

# Sections « résumé » servies en mode ALLÉGÉ (agrégats serveur au lieu des ménages
# bruts) aux périmètres district/commune. Élargi au fur et à mesure du câblage ;
# le fokontany reste toujours en données brutes (déjà léger). Preuve : test_agrege.py.
SECTIONS_ALLEGEES = {"general"}

# Groupes de rôles (source de vérité : utilisateurs.py).
_ROLES_ZONE_ENTIERE = utilisateurs._ROLES_ZONE_ENTIERE           # tous districts
_ROLES_DISTRICT_COMMUNES = utilisateurs._ROLES_DISTRICT_COMMUNES  # district + communes
_ROLES_LOGISTIQUE = utilisateurs._ROLES_LOGISTIQUE               # espace logistique (pas de dashboard)


def accueil_role(resp) -> str:
    """Page principale d'un rôle (là où la connexion l'amène, et où le lien
    « Mon espace » du bandeau le ramène). Source de vérité unique du routage
    par rôle (redirection après login ET retour depuis le dashboard)."""
    if resp == "Admin":
        return "/admin"
    if resp == "Expert survey":
        return "/transcription"
    if resp in _ROLES_LOGISTIQUE:
        return "/logistique"
    if resp == "Traitement":
        return "/traitement"          # accueil : tableau de bord OU base CE/Agents
    return "/choix"


def perimetre(u) -> tuple:
    """Périmètre géographique AUTORISÉ d'un utilisateur connecté.

    Renvoie (districts, communes) :
      - districts = None  -> tous les districts (Admin, Coordonnateur Nationale, ou
        compte sans affectation) ; aucune restriction.
      - districts = set(codes) -> restreint à CES districts : 1 pour un rôle
        mono-district (Traitement, Logistique District, Superviseur, Logistique
        Communale, Expert), 1 à 5 pour un rôle multi-district (Coordonnateur
        régionale, Comités Techniques). Le dashboard n'en affiche qu'UN à la fois.
      - communes = None  -> toutes les communes des districts autorisés.
      - communes = set(codes 6 chiffres) -> restreint à ces communes seulement
        (rôles « district + communes »). Un set VIDE = aucune commune.
    C'est la SOURCE DE VÉRITÉ de l'accès ; l'UI de sélection n'est qu'un confort.
    """
    u = u or {}
    resp = u.get("responsabilite")
    if resp in _ROLES_ZONE_ENTIERE:
        return (None, None)
    districts = {int(x) for x in (u.get("districts_affectation") or [])}
    if u.get("district_affectation") is not None:
        districts.add(int(u["district_affectation"]))
    if not districts:
        return (None, None)                 # pas d'affectation -> pas de restriction
    if resp in _ROLES_DISTRICT_COMMUNES:
        communes = {str(c) for c in (u.get("communes_affectation") or [])}
        return (districts, communes)
    return (districts, None)


def rapport_vue(sel: dict, section: str, level: str, code,
                communes_autorisees=None) -> str:
    """Une page du dashboard multi-pages : UNE section pour UN périmètre.

    Périmètre `level` ∈ district / commune / fokontany. Les données sont filtrées
    côté serveur (source_db) -> page légère. Le gabarit reçoit ACTIVE_SECTION,
    SCOPE (label de périmètre) et NAV_TREE (arbre commune->fokontany du district
    pour la barre latérale). Mise en cache par (section, périmètre, mode limites)."""
    code_district = sel["code_district"]
    mode = _MODE_LIMITES.get(sel.get("limites"), "integrees")
    # La clé de cache inclut le périmètre de communes autorisées : deux
    # utilisateurs du même district mais aux communes différentes ne doivent pas
    # partager une page (barre latérale / contours filtrés différemment).
    filtre = ",".join(sorted(communes_autorisees)) if communes_autorisees else ""
    cle = (f'vue:{section}:{level}:{code}:{code_district}:{mode}:'
           f'{sel.get("chemin_limites","")}:{filtre}')
    with _CACHE_LOCK:
        if cle in _CACHE:
            return _CACHE[cle]

    conn = db_source.connect()
    try:
        agents_noms = equipes.noms_agents(conn)   # {code: nom} si nom renseigné
        nav_tree = zones.reference_district(conn, code_district)
        # Superviseur « strict » : la barre latérale, les contours de carte et la
        # liste de référence ne montrent QUE ses communes assignées.
        if communes_autorisees is not None:
            nav_tree = [z for z in nav_tree if z["ccode"] in communes_autorisees]
        if level == "commune":
            source = db_source.source_db(conn, commune=int(code))
            codes_geo = [z["fkt"] for z in nav_tree if z["ccode"] == str(code)]
            nom = next((z["commune"] for z in nav_tree if z["ccode"] == str(code)),
                       str(code))
            # `commune` = NOM (clé de communeCodeMap côté gabarit) -> le contour de
            # commune s'affiche même SANS ménage (mpaFilter lit SCOPE, pas MENAGES).
            scope = {"level": "commune", "code": str(code), "ccode": str(code),
                     "commune": nom, "label": "Commune : " + nom}
        elif level == "fokontany":
            source = db_source.source_db(conn, fkt=int(code))
            codes_geo = [str(code)]
            z = next((z for z in nav_tree if z["fkt"] == str(code)), None)
            scope = {"level": "fokontany", "code": str(code),
                     "ccode": z["ccode"] if z else "",
                     "commune": z["commune"] if z else "",
                     "label": "Fokontany : " + (z["label"] if z else str(code))}
        elif communes_autorisees is not None:
            # Superviseur : la vue « globale » agrège UNIQUEMENT ses communes
            # affectées (union), pas tout le district. Ex. 120 + 80 = 200 ménages.
            source = db_source.source_db(
                conn, communes=[int(c) for c in communes_autorisees])
            codes_geo = [z["fkt"] for z in nav_tree]      # = fokontany de ses communes
            n = len(communes_autorisees)
            scope = {"level": "district", "code": str(code_district),
                     "label": ("Mes communes affectées"
                               + (f" ({n})" if n > 1 else ""))}
        else:  # district (périmètre par défaut)
            source = db_source.source_db(conn, district=code_district)
            codes_geo = zones.codes_fokontany_district(conn, code_district)
            lib = zones.libelles_district(conn, code_district)
            scope = {"level": "district", "code": str(code_district),
                     "label": "District : " + (lib[2] if lib else str(code_district))}

        tmp = tempfile.mkdtemp(prefix="rsu_vue_")
        chemins = {
            "rapport": tmp,
            "limites": config.LIMITES_DIR,
            "templates": config.TEMPLATES_DIR,
            "limites_mode": mode,
            "limites_dossier": sel.get("chemin_limites", ""),
        }
        alleger = (section in SECTIONS_ALLEGEES
                   and level in ("district", "commune"))
        # Couverture (dénombrement réalisé vs projection ménages 2025) : sur la
        # page « Vue générale » aux niveaux district/commune. On fournit l'attendu
        # (nombreMenage) des communes du périmètre ; le moteur calcule le reste.
        menages_attendus = None
        if section == "general" and level in ("district", "commune"):
            if level == "commune":
                ccodes = {str(code)}
            else:  # district : toutes les communes du périmètre (nav_tree)
                ccodes = {z["ccode"] for z in nav_tree if z.get("ccode")}
            menages_attendus = zones.attendus_communes(conn, ccodes)
        out = rapport_core.generer_rapport(
            chemins,
            source=source,
            codes_geo=codes_geo,
            autoriser_vide=True,
            zones_ref=nav_tree,
            assets_url=config.PREFIXE + "/assets",
            section=section,
            scope=scope,
            nav_tree=nav_tree,
            alleger=alleger,
            nav_base=config.PREFIXE + "/vue",
            agents_noms=agents_noms,
            menages_attendus=menages_attendus,
            contours_override=limites_db.contours_pour(conn, codes_geo))
        with open(out, "r", encoding="utf-8") as f:
            page = f.read()
    finally:
        conn.close()
    with _CACHE_LOCK:
        _CACHE[cle] = page
    return page


def rapport_district(sel: dict) -> str:
    """Rapport de dénombrement filtré sur le district choisi.

    - Filtre les données sur `code_district` (0 ligne -> rapport à sections vides).
    - Force les contours de TOUT le district (codes fokontany depuis `zones`) pour
      que la carte affiche ses limites même sans ménage dénombré.
    - Applique le mode de limites choisi (OCHA 2018 / générées / dossier).
    """
    code_district = sel["code_district"]
    mode = _MODE_LIMITES.get(sel.get("limites"), "integrees")
    cle = f'den:{code_district}:{mode}:{sel.get("chemin_limites","")}'
    with _CACHE_LOCK:
        if cle in _CACHE:
            return _CACHE[cle]

    conn = db_source.connect()
    try:
        codes_geo = zones.codes_fokontany_district(conn, code_district)
        ref_zones = zones.reference_district(conn, code_district)
        tmp = tempfile.mkdtemp(prefix="rsu_dist_")
        chemins = {
            "rapport": tmp,
            "limites": config.LIMITES_DIR,
            "templates": config.TEMPLATES_DIR,
            "limites_mode": mode,
            "limites_dossier": sel.get("chemin_limites", ""),
        }
        out = rapport_core.generer_rapport(
            chemins,
            source=db_source.source_db(conn, district=code_district),
            codes_geo=codes_geo,
            autoriser_vide=True,
            zones_ref=ref_zones,
            assets_url=config.PREFIXE + "/assets",
            agents_noms=equipes.noms_agents(conn),
            contours_override=limites_db.contours_pour(conn, codes_geo))
        with open(out, "r", encoding="utf-8") as f:
            page = f.read()
    finally:
        conn.close()
    with _CACHE_LOCK:
        _CACHE[cle] = page
    return page


# ---------------------------------------------------------------------------
# Page d'accueil (menu)
# ---------------------------------------------------------------------------
def page_accueil() -> str:
    blocs = []
    for commune in sorted(ARBRE, key=lambda s: s.lower()):
        items = sorted(ARBRE[commune].items(), key=lambda kv: kv[1].lower())
        liens = "".join(
            f'<li><a href="/fokontany/{htmllib.escape(code)}">'
            f'{htmllib.escape(label)}</a> '
            f'<span class="code">{htmllib.escape(code)}</span></li>'
            for code, label in items)
        blocs.append(
            f'<details><summary>{htmllib.escape(commune)} '
            f'<span class="n">({len(items)})</span></summary>'
            f'<ul>{liens}</ul></details>')
    menu = "\n".join(blocs)
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport RSU 2026 — Accueil</title>
<style>
  body{{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:760px;margin:36px auto;
       padding:0 16px;color:#1c2430;line-height:1.5}}
  h1{{font-size:1.5rem;margin-bottom:4px}}
  .sous{{color:#5a6675;margin-top:0}}
  details{{border:1px solid #dce3ea;border-radius:8px;margin:8px 0;padding:6px 12px}}
  summary{{cursor:pointer;font-weight:600}}
  .n{{color:#8a97a6;font-weight:400}}
  ul{{list-style:none;padding-left:8px;margin:8px 0}}
  li{{padding:4px 0}}
  a{{color:#1b6ef3;text-decoration:none}} a:hover{{text-decoration:underline}}
  .code{{color:#9aa6b3;font-size:.8rem;margin-left:6px}}
  .note{{background:#eef6ff;border:1px solid #cfe2ff;border-radius:8px;padding:12px;
         font-size:.88rem;margin:18px 0}}
  .barre{{display:flex;justify-content:flex-end;margin-bottom:4px}}
  .barre a{{font-size:.85rem;color:#5a6675;border:1px solid #dce3ea;border-radius:8px;
    padding:5px 12px}}
  .barre a:hover{{background:#f4f7fb;text-decoration:none}}
</style></head><body>
<h1>Rapport RSU 2026</h1>
<p class="sous">{TOTAL_MENAGES} ménages · {len(ARBRE)} communes ·
{sum(len(v) for v in ARBRE.values())} fokontany</p>
<div class="note">Choisissez un <strong>fokontany</strong> : le serveur ne charge que
ses données (page légère, quelques centaines de ménages), au lieu de tout envoyer d'un
coup.</div>
{menu}
</body></html>"""


# ---------------------------------------------------------------------------
# Page de connexion (login) — servie AVANT tout accès au menu
# ---------------------------------------------------------------------------
def page_login(erreur: bool = False) -> str:
    bloc_erreur = (
        '<div class="message visible">Identifiant ou mot de passe incorrect.</div>'
        if erreur else '<div class="message"></div>')
    # Chaîne normale (pas f-string) : les accolades du CSS/SVG restent littérales.
    # Seul point d'injection : le marqueur <!--ERREUR--> ci-dessous.
    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Connexion</title>
<style>
  *{box-sizing:border-box}
  :root{--bleu:#1b6ef3;--bleu-f:#1558c9;--vert:#17a398;--nuit:#0d2b4e;--texte:#1c2430}
  html,body{height:100%}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:var(--texte);margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px;
    line-height:1.5;background:#0d2b4e}

  /* Image officielle RSU en FOND PLEINE PAGE (couche fixe + zoom lent) */
  .fond{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat;
    animation:zoomlent 22s ease-in-out infinite alternate}
  /* Voile léger par-dessus : donne du contraste sans masquer l'image */
  .voile{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.42) 0%,rgba(21,88,201,.26) 55%,rgba(23,163,152,.30) 130%)}

  /* Cadre : deux colonnes (visuel + formulaire), posé sur l'image */
  .cadre{position:relative;z-index:2;display:flex;width:100%;max-width:940px;
    background:transparent;border-radius:20px;overflow:hidden;
    box-shadow:0 30px 70px rgba(0,0,0,.42);animation:apparaitre .7s ease both}

  /* Colonne gauche : panneau illustré animé (translucide, laisse voir l'image) */
  .visuel{position:relative;flex:1 1 46%;min-width:0;color:#fff;padding:38px 34px;
    display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;
    background:linear-gradient(140deg,rgba(13,43,78,.72) 0%,rgba(21,88,201,.5) 55%,
      rgba(23,163,152,.5) 130%);
    background-size:180% 180%;animation:degrade 12s ease infinite alternate}
  .visuel::before,.visuel::after{content:"";position:absolute;border-radius:50%;
    background:rgba(255,255,255,.09);filter:blur(2px)}
  .visuel::before{width:220px;height:220px;top:-70px;right:-60px;
    animation:flotter 9s ease-in-out infinite}
  .visuel::after{width:150px;height:150px;bottom:-50px;left:-40px;
    animation:flotter 7s ease-in-out infinite reverse}
  .v-haut{position:relative;z-index:2;display:flex;align-items:center;gap:12px}
  .badge{width:52px;height:52px;border-radius:14px;flex:none;background:rgba(255,255,255,.16);
    border:1px solid rgba(255,255,255,.35);display:flex;align-items:center;justify-content:center;
    font-weight:800;letter-spacing:.5px;font-size:1.05rem;backdrop-filter:blur(4px)}
  .v-haut .titre{font-size:1.18rem;font-weight:700;margin:0}
  .v-haut .st{font-size:.82rem;opacity:.85;margin:0}
  .scene{position:relative;z-index:2;align-self:center;width:100%;max-width:320px;margin:8px 0}
  .accroche{position:relative;z-index:2}
  .accroche h2{font-size:1.32rem;line-height:1.3;margin:0 0 14px}
  .puces{list-style:none;padding:0;margin:0;display:grid;gap:10px}
  .puces li{display:flex;align-items:center;gap:11px;font-size:.92rem;opacity:0;
    animation:glisser .6s ease forwards}
  .puces li:nth-child(1){animation-delay:.35s}
  .puces li:nth-child(2){animation-delay:.5s}
  .puces li:nth-child(3){animation-delay:.65s}
  .ico{width:34px;height:34px;flex:none;border-radius:10px;background:rgba(255,255,255,.15);
    border:1px solid rgba(255,255,255,.28);display:flex;align-items:center;justify-content:center}

  /* Colonne droite : formulaire (verre dépoli translucide sur l'image) */
  .carte{flex:1 1 54%;min-width:0;padding:44px 40px;display:flex;flex-direction:column;
    justify-content:center;background:rgba(255,255,255,.86);
    backdrop-filter:blur(12px) saturate(120%);-webkit-backdrop-filter:blur(12px) saturate(120%)}
  .bienvenue{font-size:1.5rem;font-weight:700;margin:0 0 4px}
  .sous{color:#5a6675;margin:0 0 24px;font-size:.94rem}
  label{display:block;font-weight:600;font-size:.86rem;margin:14px 0 6px}
  .champ{position:relative}
  .champ svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);opacity:.45}
  input{width:100%;padding:12px 14px 12px 42px;font-size:1rem;color:var(--texte);
    background:#f7f9fc;border:1.5px solid #e1e7ef;border-radius:11px;outline:none;
    transition:.18s}
  input:focus{border-color:var(--bleu);background:#fff;box-shadow:0 0 0 4px rgba(27,110,243,.14)}
  button.principal{width:100%;margin-top:24px;padding:13px;font-size:1.02rem;font-weight:700;
    color:#fff;border:none;border-radius:11px;cursor:pointer;letter-spacing:.3px;
    background:linear-gradient(135deg,var(--bleu),var(--bleu-f));
    box-shadow:0 10px 22px rgba(27,110,243,.30);transition:.18s}
  button.principal:hover{transform:translateY(-2px);box-shadow:0 14px 28px rgba(27,110,243,.38)}
  button.principal:active{transform:translateY(0)}
  .message{display:none;margin-top:16px;padding:11px 13px;border-radius:11px;font-size:.88rem;
    background:#fdecea;border:1px solid #f5c6c2;color:#c0392b}
  .message.visible{display:block;animation:glisser .3s ease both}
  .pied{margin-top:26px;font-size:.78rem;color:#9aa6b3;text-align:center;
    display:flex;align-items:center;justify-content:center;gap:6px}

  /* Animations SVG (parties de la scène) */
  .flot{animation:flotter 6s ease-in-out infinite;transform-origin:center}
  .flot-2{animation:flotter 5s ease-in-out infinite .6s;transform-origin:center}
  .anneau{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-out infinite}
  .anneau2{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-out 1.3s infinite}

  @keyframes apparaitre{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
  @keyframes glisser{from{opacity:0;transform:translateX(-12px)}to{opacity:1;transform:none}}
  @keyframes flotter{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
  @keyframes degrade{0%{background-position:0% 50%}100%{background-position:100% 50%}}
  @keyframes pulse{0%{transform:scale(.5);opacity:.7}80%{transform:scale(2.4);opacity:0}100%{opacity:0}}
  @keyframes zoomlent{0%{transform:scale(1)}100%{transform:scale(1.12)}}

  /* Responsive : sur petit écran, on empile et on masque le panneau visuel lourd */
  @media (max-width:820px){
    .cadre{flex-direction:column;max-width:440px}
    .visuel{padding:26px 26px 22px}
    .scene,.accroche h2{display:none}
    .carte{padding:32px 28px}
  }
  @media (prefers-reduced-motion:reduce){
    *{animation:none!important}
  }
</style></head><body>
  <div class="fond" aria-hidden="true"></div>
  <div class="voile" aria-hidden="true"></div>
  <div class="cadre">

    <!-- ======== Colonne illustrée ======== -->
    <aside class="visuel">
      <div class="v-haut">
        <div class="badge">RSU</div>
        <div>
          <p class="titre">Suivi RSU 2026</p>
          <p class="st">Registre Social Unique</p>
        </div>
      </div>

      <svg class="scene" viewBox="0 0 320 250" xmlns="http://www.w3.org/2000/svg"
           aria-hidden="true">
        <defs>
          <linearGradient id="ile" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#2fd6b8"/><stop offset="1" stop-color="#0f9d84"/>
          </linearGradient>
          <linearGradient id="carte" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#eaf3ff"/>
          </linearGradient>
        </defs>

        <!-- Île stylisée de Madagascar + points de collecte (fokontany) -->
        <g class="flot" opacity=".95">
          <path d="M196 18 C222 40 228 74 220 108 C214 136 232 160 224 196
                   C217 226 198 240 186 244 C176 247 172 232 176 210
                   C181 182 165 162 164 132 C163 104 158 70 170 46
                   C178 30 182 26 196 18 Z"
                fill="url(#ile)" stroke="rgba(255,255,255,.5)" stroke-width="2"/>
          <!-- points GPS des fokontany -->
          <circle cx="192" cy="70" r="4.5" fill="#fff"/>
          <circle cx="200" cy="120" r="4.5" fill="#fff"/>
          <circle cx="188" cy="170" r="4.5" fill="#fff"/>
          <circle cx="205" cy="200" r="4.5" fill="#fff"/>
          <!-- anneaux qui pulsent -->
          <circle cx="192" cy="70" r="6" fill="none" stroke="#fff" stroke-width="2" class="anneau"/>
          <circle cx="188" cy="170" r="6" fill="none" stroke="#fff" stroke-width="2" class="anneau2"/>
        </g>

        <!-- Fiche « ménage » qui flotte : maison + famille + coche -->
        <g class="flot-2" transform="translate(18,120)">
          <rect x="0" y="0" width="150" height="104" rx="14" fill="url(#carte)"
                stroke="rgba(13,43,78,.10)"/>
          <!-- maison -->
          <path d="M24 46 L44 30 L64 46 Z" fill="#1b6ef3"/>
          <rect x="30" y="46" width="28" height="24" rx="2" fill="#3f86f6"/>
          <rect x="40" y="56" width="8" height="14" fill="#eaf3ff"/>
          <!-- famille (3 têtes) -->
          <circle cx="92" cy="34" r="9" fill="#17a398"/>
          <circle cx="112" cy="34" r="9" fill="#0f9d84"/>
          <circle cx="102" cy="46" r="7" fill="#2fd6b8"/>
          <rect x="80" y="46" width="44" height="22" rx="11" fill="#d7efe9"/>
          <!-- ligne « visite validée » -->
          <rect x="20" y="82" width="82" height="8" rx="4" fill="#dbe7f5"/>
          <circle cx="122" cy="86" r="12" fill="#17a398"/>
          <path d="M116 86 l4 5 l8 -10" fill="none" stroke="#fff" stroke-width="2.6"
                stroke-linecap="round" stroke-linejoin="round"/>
        </g>
      </svg>

      <div class="accroche">
        <h2>Dénombrement &amp; visites à domicile, suivis en temps réel.</h2>
        <ul class="puces">
          <li><span class="ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="#fff" stroke-width="2"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>
              </span>Ménages recensés par fokontany</li>
          <li><span class="ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="#fff" stroke-width="2"><path d="M21 10c0 6-9 12-9 12S3 16 3 10a9 9 0 1118 0z"/>
              <circle cx="12" cy="10" r="3"/></svg></span>Localisation GPS des visites</li>
          <li><span class="ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="#fff" stroke-width="2"><path d="M9 11l3 3L22 4"/>
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
              </span>Qualité des interviews contrôlée</li>
        </ul>
      </div>
    </aside>

    <!-- ======== Colonne formulaire ======== -->
    <form class="carte" method="post" action="/login" autocomplete="off">
      <h1 class="bienvenue">Connexion</h1>
      <p class="sous">Accédez au tableau de suivi du dénombrement RSU 2026.</p>

      <label for="login">Identifiant</label>
      <div class="champ">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1c2430"
             stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/></svg>
        <input type="text" id="login" name="login" placeholder="Votre identifiant"
               autocomplete="username" required autofocus>
      </div>

      <label for="motdepasse">Mot de passe</label>
      <div class="champ">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1c2430"
             stroke-width="2"><rect x="4" y="10" width="16" height="11" rx="2"/>
             <path d="M8 10V7a4 4 0 018 0v3"/></svg>
        <input type="password" id="motdepasse" name="motdepasse"
               placeholder="Votre mot de passe" autocomplete="current-password" required>
      </div>

      <!--ERREUR-->

      <button type="submit" class="principal">Se connecter</button>

      <p class="pied">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9aa6b3"
             stroke-width="2"><rect x="4" y="10" width="16" height="11" rx="2"/>
             <path d="M8 10V7a4 4 0 018 0v3"/></svg>
        Application interne · Données confidentielles
      </p>
    </form>

  </div>
</body></html>"""
    return page.replace("<!--ERREUR-->", bloc_erreur)


# ---------------------------------------------------------------------------
# Page de SÉLECTION (juste après la connexion) : zone géographique + limites
# + type de suivi. Listes déroulantes dépendantes Province -> Région -> District.
# ---------------------------------------------------------------------------
def page_selection(erreur: str = "", utilisateur=None) -> str:
    esc = htmllib.escape
    # Le périmètre du rôle borne la zone géographique proposée :
    #  - zone entière (Admin, Coordonnateur Nationale) -> cascade libre Prov/Rég/Dist ;
    #  - 1 seul district (Traitement, Superviseur, Logistique, Expert…) -> district
    #    FIXE (affiché, non modifiable) ;
    #  - plusieurs districts (Coordonnateur régionale, Comités Techniques) -> liste
    #    déroulante limitée à SES districts.
    districts_perim = perimetre(utilisateur)[0] if utilisateur else None
    if districts_perim is not None and len(districts_perim) == 1:
        code = sorted(districts_perim)[0]
        conn = db_source.connect()
        try:
            lib = zones.libelles_district(conn, code)
        finally:
            conn.close()
        nom = f"{lib[2]} ({code})" if lib else str(code)
        prov, reg = (lib[0], lib[1]) if lib else ("", "")
        zone_html = (
            '<fieldset><legend><span class="num">✓</span> Votre district (affecté)'
            '</legend>'
            '<div class="opt" style="cursor:default;background:#eef5ff;'
            'border-color:#bcd3f7">'
            f'<span><span class="t">{esc(nom)}</span>'
            f'<span class="d">Province {esc(str(prov))} · Région {esc(str(reg))} — '
            'district défini par votre affectation, non modifiable.</span></span>'
            '</div></fieldset>')
        n_lim, n_sui = "1", "2"
    elif districts_perim is not None:
        # Multi-district : liste déroulante restreinte à ses districts affectés.
        conn = db_source.connect()
        try:
            libs = {c: zones.libelles_district(conn, c) for c in districts_perim}
        finally:
            conn.close()
        options = "".join(
            f'<option value="{c}">'
            f'{esc((libs[c][2] if libs[c] else str(c)))} ({c})</option>'
            for c in sorted(districts_perim))
        zone_html = (
            '<fieldset><legend><span class="num">1</span> Votre district '
            '(parmi vos affectations)</legend>'
            '<div class="grille"><div class="pleine">'
            '<label class="champ-l" for="district">District</label>'
            '<select id="district" name="district" required>'
            '<option value="" selected disabled>— Choisir un district —</option>'
            + options + '</select></div></div></fieldset>')
        n_lim, n_sui = "2", "3"
    else:
        options_prov = "".join(
            f'<option value="{p["c"]}">{esc(str(p["n"]))}</option>'
            for p in ARBRE_GEO["provinces"])
        zone_html = (
            '<fieldset><legend><span class="num">1</span> Zone géographique</legend>'
            '<div class="grille"><div class="pleine">'
            '<label class="champ-l" for="province">Province</label>'
            '<select id="province" name="province" required>'
            '<option value="" selected disabled>— Choisir une province —</option>'
            + options_prov + '</select></div>'
            '<div><label class="champ-l" for="region">Région</label>'
            '<select id="region" name="region" required disabled>'
            '<option value="" selected disabled>—</option></select></div>'
            '<div><label class="champ-l" for="district">District</label>'
            '<select id="district" name="district" required disabled>'
            '<option value="" selected disabled>—</option></select></div>'
            '</div></fieldset>')
        n_lim, n_sui = "2", "3"
    bloc_erreur = (
        f'<div class="message visible">{esc(erreur)}</div>'
        if erreur else '<div class="message"></div>')
    geo_json = json.dumps(ARBRE_GEO, ensure_ascii=False)

    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Zone & type de suivi</title>
<style>
  *{box-sizing:border-box}
  :root{--bleu:#1b6ef3;--bleu-f:#1558c9;--vert:#17a398;--nuit:#0d2b4e;--texte:#1c2430}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:var(--texte);margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px;
    line-height:1.5;background:#0d2b4e}
  .fond{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat;
    animation:zoomlent 22s ease-in-out infinite alternate}
  .voile{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.58) 0%,rgba(21,88,201,.42) 55%,rgba(23,163,152,.44) 130%)}

  .carte{position:relative;z-index:2;width:100%;max-width:640px;
    background:rgba(255,255,255,.90);backdrop-filter:blur(14px) saturate(120%);
    -webkit-backdrop-filter:blur(14px) saturate(120%);border-radius:20px;
    box-shadow:0 30px 70px rgba(0,0,0,.42);padding:32px 34px;
    animation:apparaitre .6s ease both;max-height:calc(100vh - 44px);overflow:auto}
  .tete{display:flex;align-items:center;gap:12px;margin-bottom:4px}
  .badge{width:46px;height:46px;border-radius:12px;flex:none;color:#fff;font-weight:800;
    font-size:1rem;display:flex;align-items:center;justify-content:center;
    background:linear-gradient(135deg,var(--bleu),var(--bleu-f))}
  h1{font-size:1.3rem;margin:0}
  .st{color:#5a6675;font-size:.86rem;margin:0}
  .lien-haut{margin-left:auto;font-size:.82rem;color:#5a6675;text-decoration:none;
    border:1px solid #dce3ea;border-radius:8px;padding:5px 11px;background:#fff}
  .lien-haut:hover{background:#f4f7fb}

  fieldset{border:none;padding:0;margin:22px 0 0}
  legend{font-weight:700;font-size:.82rem;text-transform:uppercase;letter-spacing:.6px;
    color:#1558c9;padding:0;margin-bottom:10px;display:flex;align-items:center;gap:8px}
  .num{width:22px;height:22px;border-radius:50%;background:#e7f0ff;color:#1558c9;
    display:inline-flex;align-items:center;justify-content:center;font-size:.78rem;flex:none}
  .grille{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  label.champ-l{display:block;font-weight:600;font-size:.84rem;margin:0 0 5px}
  select,input[type=text]{width:100%;padding:11px 12px;font-size:.98rem;color:var(--texte);
    background:#f7f9fc;border:1.5px solid #e1e7ef;border-radius:10px;outline:none;transition:.15s}
  select:focus,input[type=text]:focus{border-color:var(--bleu);background:#fff;
    box-shadow:0 0 0 3px rgba(27,110,243,.14)}
  select:disabled{background:#eef1f5;color:#9aa6b3;cursor:not-allowed}
  .pleine{grid-column:1 / -1}

  .options{display:grid;gap:9px}
  .opt{display:flex;align-items:flex-start;gap:11px;border:1.5px solid #e1e7ef;border-radius:11px;
    padding:11px 13px;cursor:pointer;transition:.15s;background:#fbfcfe}
  .opt:hover{border-color:#bcd3f7;background:#f5f9ff}
  .opt input{margin-top:3px;accent-color:var(--bleu)}
  .opt:has(input:checked){border-color:var(--bleu);background:#eef5ff;
    box-shadow:0 0 0 3px rgba(27,110,243,.10)}
  .opt .t{font-weight:600;font-size:.93rem}
  .opt .d{font-size:.8rem;color:#6b7787}
  #zone-dossier{margin-top:9px;display:none}
  #zone-dossier.actif{display:block}

  .suivis{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .suivi{position:relative;border:1.5px solid #e1e7ef;border-radius:14px;padding:16px 14px;
    cursor:pointer;text-align:center;transition:.15s;background:#fbfcfe}
  .suivi:hover{border-color:#bcd3f7;background:#f5f9ff}
  .suivi input{position:absolute;opacity:0;pointer-events:none}
  .suivi:has(input:checked){border-color:var(--bleu);background:#eef5ff;
    box-shadow:0 0 0 3px rgba(27,110,243,.12)}
  .suivi .ic{width:44px;height:44px;margin:0 auto 8px;border-radius:12px;display:flex;
    align-items:center;justify-content:center;background:linear-gradient(135deg,#eaf2ff,#dfeeff);
    color:#1558c9}
  .suivi:has(input:checked) .ic{background:linear-gradient(135deg,var(--bleu),var(--bleu-f));
    color:#fff}
  .suivi .t{font-weight:700;font-size:.98rem}
  .suivi .d{font-size:.78rem;color:#6b7787;margin-top:2px}

  button.principal{width:100%;margin-top:26px;padding:13px;font-size:1.02rem;font-weight:700;
    color:#fff;border:none;border-radius:11px;cursor:pointer;letter-spacing:.3px;
    background:linear-gradient(135deg,var(--bleu),var(--bleu-f));
    box-shadow:0 10px 22px rgba(27,110,243,.30);transition:.18s}
  button.principal:hover{transform:translateY(-2px);box-shadow:0 14px 28px rgba(27,110,243,.38)}
  .message{display:none;margin-top:16px;padding:11px 13px;border-radius:11px;font-size:.88rem;
    background:#fdecea;border:1px solid #f5c6c2;color:#c0392b}
  .message.visible{display:block}

  @keyframes apparaitre{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
  @keyframes zoomlent{0%{transform:scale(1)}100%{transform:scale(1.12)}}
  @media (max-width:560px){.grille,.suivis{grid-template-columns:1fr}}
  @media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
  <div class="fond" aria-hidden="true"></div>
  <div class="voile" aria-hidden="true"></div>

  <form class="carte" method="post" action="/suivi">
    <div class="tete">
      <div class="badge">RSU</div>
      <div>
        <h1>Zone &amp; type de suivi</h1>
        <p class="st">Choisissez où et quoi suivre.</p>
      </div>
    </div>

    <!--ZONE-->

    <!-- ÉTAPE : limites administratives -->
    <fieldset>
      <legend><span class="num"><!--NLIM--></span> Limites administratives</legend>
      <div class="options">
        <label class="opt">
          <input type="radio" name="limites" value="ocha" checked>
          <span><span class="t">Limites OCHA 2018</span>
            <span class="d">Contours administratifs officiels (référence par défaut).</span></span>
        </label>
        <label class="opt">
          <input type="radio" name="limites" value="generer">
          <span><span class="t">Générer les limites automatiquement</span>
            <span class="d">L'application calcule les contours à partir des données.</span></span>
        </label>
        <label class="opt">
          <input type="radio" name="limites" value="dossier">
          <span style="width:100%"><span class="t">Choisir un dossier de limites</span>
            <span class="d">Indiquer le chemin d'un dossier contenant les contours.</span>
            <span id="zone-dossier">
              <input type="text" name="chemin_limites" id="chemin_limites"
                     placeholder="Ex. C:\\Users\\...\\LimitesFokontany">
            </span>
          </span>
        </label>
      </div>
    </fieldset>

    <!-- ÉTAPE : type de suivi -->
    <fieldset>
      <legend><span class="num"><!--NSUI--></span> Type de suivi</legend>
      <div class="suivis">
        <label class="suivi">
          <input type="radio" name="suivi" value="den" required>
          <span class="ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"><path d="M3 11l9-8 9 8"/>
            <path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg></span>
          <div class="t">Dénombrement</div>
          <div class="d">Recensement des ménages</div>
        </label>
        <label class="suivi">
          <input type="radio" name="suivi" value="vad" required>
          <span class="ic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/>
            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg></span>
          <div class="t">Visite à domicile</div>
          <div class="d">Interviews sur le terrain</div>
        </label>
      </div>
    </fieldset>

    <!--ERREUR-->
    <button type="submit" class="principal">Continuer</button>
  </form>

<script>
  const GEO = /*GEO*/;
  const selProv = document.getElementById("province");
  const selReg  = document.getElementById("region");
  const selDist = document.getElementById("district");

  function vider(sel, texte){
    sel.innerHTML = '<option value="" selected disabled>' + texte + '</option>';
  }
  function remplir(sel, liste, texte){
    vider(sel, texte);
    (liste || []).forEach(function(o){
      const opt = document.createElement("option");
      opt.value = o.c; opt.textContent = o.n; sel.appendChild(opt);
    });
    sel.disabled = !(liste && liste.length);
  }

  // Cascade province -> région -> district : seulement si ces champs existent
  // (absents quand le district est déjà connu, ex. rôle Traitement).
  if (selProv && selReg && selDist) {
    selProv.addEventListener("change", function(){
      remplir(selReg, GEO.regions[selProv.value], "— Choisir une région —");
      vider(selDist, "—"); selDist.disabled = true;
    });
    selReg.addEventListener("change", function(){
      remplir(selDist, GEO.districts[selReg.value], "— Choisir un district —");
    });
  }

  // Activer le champ « chemin du dossier » seulement si l'option est cochée.
  const zoneDossier = document.getElementById("zone-dossier");
  const champChemin = document.getElementById("chemin_limites");
  document.querySelectorAll('input[name="limites"]').forEach(function(r){
    r.addEventListener("change", function(){
      const actif = document.querySelector('input[name="limites"]:checked').value === "dossier";
      zoneDossier.classList.toggle("actif", actif);
      champChemin.required = actif;
      if (actif) champChemin.focus();
    });
  });
</script>
</body></html>"""
    return (page
            .replace("<!--ZONE-->", zone_html)
            .replace("<!--NLIM-->", n_lim)
            .replace("<!--NSUI-->", n_sui)
            .replace("/*GEO*/", geo_json)
            .replace("<!--ERREUR-->", bloc_erreur))


# ---------------------------------------------------------------------------
# Page RÉCAPITULATIF : confirme la sélection avant d'ouvrir le suivi.
# ---------------------------------------------------------------------------
def page_suivi(sel: dict) -> str:
    libelle_limites = {
        "ocha": "Limites OCHA 2018",
        "generer": "Limites générées automatiquement",
        "dossier": "Dossier de limites : " + (sel.get("chemin_limites") or "—"),
    }.get(sel.get("limites"), "—")
    libelle_suivi = {"den": "Dénombrement", "vad": "Visite à domicile"}.get(
        sel.get("suivi"), "—")
    esc = htmllib.escape
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Suivi {esc(libelle_suivi)}</title>
<style>
  body{{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px;
    line-height:1.55;background:#0d2b4e}}
  .fond{{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat}}
  .voile{{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.62),rgba(21,88,201,.44) 55%,rgba(23,163,152,.46))}}
  .carte{{position:relative;z-index:2;width:100%;max-width:560px;background:rgba(255,255,255,.92);
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-radius:20px;
    box-shadow:0 30px 70px rgba(0,0,0,.42);padding:30px 32px;animation:app .6s ease both}}
  .tete{{display:flex;align-items:center;gap:12px;margin-bottom:14px}}
  .badge{{width:46px;height:46px;border-radius:12px;color:#fff;font-weight:800;flex:none;
    display:flex;align-items:center;justify-content:center;
    background:linear-gradient(135deg,#1b6ef3,#1558c9)}}
  h1{{font-size:1.28rem;margin:0}}
  .ruban{{display:inline-block;margin-top:2px;font-size:.78rem;font-weight:700;color:#0f9d84;
    background:#e6f7f2;border:1px solid #b8e6da;border-radius:999px;padding:2px 10px}}
  dl{{margin:18px 0 0;display:grid;grid-template-columns:auto 1fr;gap:10px 16px}}
  dt{{color:#5a6675;font-size:.82rem;font-weight:600;text-transform:uppercase;letter-spacing:.4px}}
  dd{{margin:0;font-weight:600}}
  .note{{margin-top:20px;background:#eef6ff;border:1px solid #cfe2ff;border-radius:11px;
    padding:12px 14px;font-size:.86rem;color:#3a5a80}}
  .actions{{display:flex;gap:10px;margin-top:22px;flex-wrap:wrap}}
  .btn{{flex:1;min-width:150px;text-align:center;padding:12px;border-radius:11px;font-weight:700;
    text-decoration:none;cursor:pointer;border:1.5px solid #dce3ea;color:#1c2430;background:#fff}}
  .btn:hover{{background:#f4f7fb}}
  .btn.p{{color:#fff;border:none;background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 10px 22px rgba(27,110,243,.28)}}
  @keyframes app{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:none}}}}
</style></head><body>
  <div class="fond"></div><div class="voile"></div>
  <div class="carte">
    <div class="tete">
      <div class="badge">RSU</div>
      <div>
        <h1>Suivi prêt à ouvrir</h1>
        <span class="ruban">{esc(libelle_suivi)}</span>
      </div>
    </div>
    <dl>
      <dt>Province</dt><dd>{esc(str(sel.get('province_nom','—')))}</dd>
      <dt>Région</dt><dd>{esc(str(sel.get('region_nom','—')))}</dd>
      <dt>District</dt><dd>{esc(str(sel.get('district_nom','—')))}</dd>
      <dt>Limites</dt><dd>{esc(libelle_limites)}</dd>
      <dt>Type de suivi</dt><dd>{esc(libelle_suivi)}</dd>
    </dl>
    <div class="note">Sélection enregistrée. La vue de suivi détaillée (par
      fokontany du district choisi) est l'étape suivante du développement.</div>
    <div class="actions">
      <a class="btn" href="/">← Changer la sélection</a>
      <a class="btn p" href="/menu">Voir le menu fokontany (démo)</a>
    </div>
  </div>
</body></html>"""


# ---------------------------------------------------------------------------
# Page « Visite à domicile — pas encore disponible »
# ---------------------------------------------------------------------------
def page_vad_indisponible(sel: dict) -> str:
    esc = htmllib.escape
    district = esc(str(sel.get("district_nom", "—")))
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Visite à domicile</title>
<style>
  body{{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:22px;
    line-height:1.55;background:#0d2b4e}}
  .fond{{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat}}
  .voile{{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.66),rgba(21,88,201,.46) 55%,rgba(23,163,152,.48))}}
  .carte{{position:relative;z-index:2;width:100%;max-width:520px;text-align:center;
    background:rgba(255,255,255,.93);backdrop-filter:blur(14px);
    -webkit-backdrop-filter:blur(14px);border-radius:20px;
    box-shadow:0 30px 70px rgba(0,0,0,.42);padding:38px 34px;animation:app .6s ease both}}
  .ic{{width:76px;height:76px;margin:0 auto 16px;border-radius:20px;display:flex;
    align-items:center;justify-content:center;color:#b7791f;
    background:linear-gradient(135deg,#fff4d6,#ffe6a8)}}
  h1{{font-size:1.35rem;margin:0 0 6px}}
  .ruban{{display:inline-block;font-size:.76rem;font-weight:700;color:#8a5a00;
    background:#fff4d6;border:1px solid #f0d38a;border-radius:999px;padding:2px 11px;
    margin-bottom:12px}}
  p{{color:#41505f;margin:8px 0}}
  .district{{font-weight:700;color:#1c2430}}
  .actions{{display:flex;gap:10px;margin-top:24px;justify-content:center;flex-wrap:wrap}}
  .btn{{padding:12px 18px;border-radius:11px;font-weight:700;text-decoration:none;
    border:1.5px solid #dce3ea;color:#1c2430;background:#fff}}
  .btn:hover{{background:#f4f7fb}}
  .btn.p{{color:#fff;border:none;background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 10px 22px rgba(27,110,243,.28)}}
  @keyframes app{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:none}}}}
</style></head><body>
  <div class="fond"></div><div class="voile"></div>
  <div class="carte">
    <div class="ic"><svg width="38" height="38" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/>
      <path d="M12 7v6"/><path d="M12 16.5v.5"/></svg></div>
    <span class="ruban">En cours de conception</span>
    <h1>Suivi « Visite à domicile » indisponible</h1>
    <p>Le suivi des <strong>interviews / visites à domicile</strong> n'est
      <strong>pas encore disponible</strong> : les données correspondantes ne sont
      pas encore intégrées à l'application. Cette vue est en cours de conception.</p>
    <p>District demandé : <span class="district">{district}</span></p>
    <div class="actions">
      <a class="btn p" href="/">← Retour à la sélection</a>
      <a class="btn" href="/logout">Se déconnecter</a>
    </div>
  </div>
</body></html>"""


def _session(handler):
    """Renvoie le dict de session du visiteur si valide ET non expiré, sinon None.

    Expiration par INACTIVITÉ (INACTIVITE_MAX) : au-delà du délai sans requête, la
    session est invalidée (l'utilisateur devra se reconnecter). L'objet est partagé
    (mutable) : le modifier sous _SESSIONS_LOCK met à jour la session.
    """
    brut = handler.headers.get("Cookie")
    if not brut:
        return None
    morceau = http.cookies.SimpleCookie(brut).get(COOKIE_SESSION)
    if not morceau:
        return None
    jeton = morceau.value
    with _SESSIONS_LOCK:
        sess = _SESSIONS.get(jeton)
    if sess is None:
        return None
    now = time.time()
    if now - sess.get("_vu", now) > INACTIVITE_MAX:      # trop longtemps inactif
        with _SESSIONS_LOCK:
            _SESSIONS.pop(jeton, None)
        try:                                             # clôt la session au journal
            conn = db_source.connect()
            journal.fermer(conn, jeton)
            conn.close()
        except Exception:
            pass
        return None
    sess["_vu"] = now
    return sess


def page_erreur(msg: str, code: int = 400) -> str:
    return (f'<!doctype html><meta charset="utf-8"><body style="font-family:'
            f'system-ui;max-width:640px;margin:40px auto">'
            f'<h1>Oups</h1><p>{htmllib.escape(msg)}</p>'
            f'<p><a href="/">&larr; Retour au menu</a></p></body>')


_RE_LIEN = re.compile(r'(href|action|src)="(/[^"]*)"')


def _prefixer(html_str: str) -> str:
    """Préfixe par /rsu les URL internes (href/action/src commençant par « / », et
    url(/img/accueil) du CSS). Laisse intactes les URL externes (http…, tel:, mailto:),
    les ancres et celles déjà préfixées. « / » (racine) -> page de choix."""
    P = config.PREFIXE

    def repl(m):
        attr, url = m.group(1), m.group(2)
        if url == P or url.startswith(P + "/"):
            return m.group(0)
        if url == "/":
            return f'{attr}="{P}/choix"'
        return f'{attr}="{P}{url}"'

    return (_RE_LIEN.sub(repl, html_str)
            .replace("url(/img/accueil)", f"url({P}/img/accueil)"))


# ---------------------------------------------------------------------------
# Bandeau utilisateur : identite + role + deconnexion, en haut a DROITE de
# CHAQUE page servie a un utilisateur connecte. Centralise ici et injecte par
# _html() apres la balise <body> : une seule source, presente partout (pages
# de selection/admin/transcription ET rapport), sans toucher chaque gabarit.
# ---------------------------------------------------------------------------
_RE_BODY = re.compile(r"(<body[^>]*>)", re.IGNORECASE)


def bandeau_utilisateur(sess) -> str:
    """HTML du bandeau (barre fixe haut-droite) pour la session donnee.

    Vide si pas de session valide -> rien n'est injecte sur les pages publiques
    (login, erreurs avant connexion). Le lien de deconnexion est deja prefixe
    (config.PREFIXE) : le bandeau est insere APRES _prefixer(), donc jamais
    re-prefixe (et il fonctionne aussi sur le rapport, servi sans prefixage).
    """
    if not sess:
        return ""
    u = sess.get("utilisateur") or {}
    nom = (u.get("nom_prenom") or sess.get("login") or "").strip()
    role = (u.get("responsabilite") or "").strip()
    if not nom:
        return ""
    esc = htmllib.escape
    initiales = "".join(p[0] for p in nom.split()[:2]).upper() or "?"
    logout = config.PREFIXE + "/logout"
    # Lien « Mon espace » : ramène le rôle à sa page principale (Admin -> /admin,
    # etc.). Sans lui, un Admin parti sur le dashboard (/choix, /vue) n'avait aucun
    # retour vers son espace sinon en se déconnectant. Déjà préfixé (bandeau inséré
    # après _prefixer, cf. plus bas), comme le lien de déconnexion.
    accueil = config.PREFIXE + accueil_role(role)
    lien_espace = (
        f'<a class="rsu-b-home" href="{esc(accueil)}" title="Mon espace">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M3 9.5 12 3l9 6.5"/>'
        '<path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>'
        '<span>Mon espace</span></a>')
    return (
        '<div id="rsu-bandeau" role="banner">'
        f'<div class="rsu-b-ava">{esc(initiales)}</div>'
        '<div class="rsu-b-txt">'
        f'<span class="rsu-b-nom">{esc(nom)}</span>'
        f'<span class="rsu-b-role">{esc(role)}</span>'
        '</div>'
        f'{lien_espace}'
        f'<a class="rsu-b-out" href="{esc(logout)}" title="Se deconnecter">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<polyline points="16 17 21 12 16 7"/>'
        '<line x1="21" y1="12" x2="9" y2="12"/></svg>'
        '<span>Déconnexion</span></a></div>'
        '<style>'
        '#rsu-bandeau{position:fixed;top:12px;right:14px;z-index:2147483000;'
        'display:flex;align-items:center;gap:10px;'
        'background:rgba(255,255,255,.96);-webkit-backdrop-filter:blur(6px);'
        'backdrop-filter:blur(6px);border:1px solid #dce3ea;border-radius:999px;'
        'padding:5px 7px 5px 7px;box-shadow:0 6px 18px rgba(13,43,78,.18);'
        'font-family:system-ui,"Segoe UI",Arial,sans-serif;font-size:.82rem;'
        'color:#1c2430;max-width:calc(100vw - 28px)}'
        '#rsu-bandeau .rsu-b-ava{width:30px;height:30px;border-radius:50%;flex:none;'
        'display:flex;align-items:center;justify-content:center;font-weight:800;'
        'font-size:.72rem;color:#fff;background:linear-gradient(135deg,#1b6ef3,#1558c9)}'
        '#rsu-bandeau .rsu-b-txt{display:flex;flex-direction:column;line-height:1.15;'
        'min-width:0;max-width:200px}'
        '#rsu-bandeau .rsu-b-nom{font-weight:700;white-space:nowrap;overflow:hidden;'
        'text-overflow:ellipsis}'
        '#rsu-bandeau .rsu-b-role{color:#5a6675;font-size:.72rem;white-space:nowrap;'
        'overflow:hidden;text-overflow:ellipsis}'
        '#rsu-bandeau .rsu-b-home{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#1558c9;font-weight:600;border:1px solid #c7dbf7;'
        'background:#eaf1fd;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-home:hover{background:#1558c9;color:#fff;'
        'border-color:#1558c9}'
        '#rsu-bandeau .rsu-b-out{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#c0392b;font-weight:600;border:1px solid #f0cfca;'
        'background:#fdecea;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-out:hover{background:#c0392b;color:#fff;'
        'border-color:#c0392b}'
        '@media print{#rsu-bandeau{display:none!important}}'
        '@media (max-width:560px){#rsu-bandeau .rsu-b-txt{display:none}'
        '#rsu-bandeau .rsu-b-out span,#rsu-bandeau .rsu-b-home span{display:none}}'
        '</style>')


# ---------------------------------------------------------------------------
# Téléversement d'un DOSSIER (webkitdirectory) : préserver les sous-dossiers
# ---------------------------------------------------------------------------
def _relpath_upload(nom: str) -> str:
    """Chemin relatif SÛR d'un fichier téléversé, sous-dossiers PRÉSERVÉS.

    Le navigateur (webkitdirectory) envoie un chemin « dossier_choisi/[sous-dossier/
    …/]fichier ». On retire le 1er segment (le dossier racine choisi) et on garde le
    reste — ainsi « Questionnaire/ » et tout autre sous-dossier sont conservés. On
    écarte les segments vides, « . », « .. » et ceux à « : » (lecteur Windows) pour
    empêcher toute traversée de dossier. Renvoie '' si rien d'exploitable."""
    parts = [p for p in (nom or "").replace("\\", "/").split("/")
             if p and p not in (".", "..") and ":" not in p]
    if len(parts) >= 2:
        parts = parts[1:]                 # retirer le dossier racine choisi
    return "/".join(parts)


def _sous_dossier(base: str, cible: str) -> bool:
    """Vrai si `cible` reste bien à l'intérieur de `base` (garde anti-traversée)."""
    base_n = os.path.normpath(base)
    cible_n = os.path.normpath(cible)
    return cible_n == base_n or cible_n.startswith(base_n + os.sep)


# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):

    def _html(self, contenu: str, code: int = 200, entetes=None, prefixer=True):
        # Préfixe les liens internes par /rsu, SAUF pour le rapport (déjà préfixé à la
        # source via assets_url/nav_base, et volumineux -> on évite un regex inutile).
        if prefixer:
            contenu = _prefixer(contenu)
        # Bandeau utilisateur (identite + role + deconnexion) en haut a droite de
        # TOUTE page servie a un connecte. Insere APRES _prefixer (lien /logout deja
        # prefixe), y compris sur le rapport (prefixer=False). Rien si non connecte.
        bandeau = bandeau_utilisateur(_session(self))
        if bandeau:
            contenu = _RE_BODY.sub(lambda m: m.group(1) + bandeau, contenu, count=1)
        octets = contenu.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(octets)))
        # Pages dynamiques = JAMAIS mises en cache : (1) sécurité (données RSU
        # nominatives ne doivent pas rester en cache disque du navigateur) et
        # (2) sinon un navigateur ressert une copie cachée de /choix SANS repasser
        # par le serveur -> les gardes de rôle (Expert survey) sont contournés.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        for cle, val in (entetes or []):
            self.send_header(cle, val)
        self.end_headers()
        self.wfile.write(octets)

    def _fichier(self, chemin_fichier: str, mime: str):
        try:
            with open(chemin_fichier, "rb") as f:
                data = f.read()
        except OSError:
            self._html(page_erreur("Ressource introuvable.", 404), 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _redirige(self, vers: str, entetes=None):
        # Les cibles internes ("/login", "/vue/...") sont automatiquement préfixées
        # par /rsu ; les URL déjà préfixées ou absolues (http…) sont laissées telles.
        if (vers.startswith("/") and vers != PREFIXE
                and not vers.startswith(PREFIXE + "/")):
            vers = PREFIXE + vers
        self.send_response(303)  # See Other
        self.send_header("Location", vers)
        for cle, val in (entetes or []):
            self.send_header(cle, val)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        brut = self.path.split("?", 1)[0]
        # Toute l'appli vit sous /rsu : on ramène les URL sans préfixe.
        if brut in ("/", ""):
            self._redirige("/choix")           # -> /rsu/choix
            return
        if not (brut == PREFIXE or brut.startswith(PREFIXE + "/")):
            self._redirige(brut)               # ex. /admin -> /rsu/admin
            return
        chemin = brut[len(PREFIXE):] or "/"     # "/rsu/vue/general" -> "/vue/general"
        if chemin == "/":
            self._redirige("/choix")           # /rsu ou /rsu/ -> /rsu/choix
            return

        # --- Pages publiques (sans connexion) ---
        if chemin == "/img/accueil":
            self._fichier(IMAGE_ACCUEIL, "image/jpeg")
            return
        if chemin.startswith("/assets/"):
            # CSS + Chart.js du rapport (aucune donnée : sert avant le login).
            nom = os.path.basename(chemin)  # basename => pas de traversée de dossier
            ext = os.path.splitext(nom)[1].lower()
            mime = {"css": "text/css; charset=utf-8",
                    "js": "application/javascript; charset=utf-8"}.get(
                        ext.lstrip("."), "application/octet-stream")
            self._fichier(os.path.join(config.ASSETS_DIR, nom), mime)
            return
        if chemin == "/login":
            erreur = "erreur=1" in self.path
            self._html(page_login(erreur))
            return
        if chemin == "/logout":
            self.deconnecter()
            return

        # --- À partir d'ici, connexion OBLIGATOIRE ---
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return

        # Journal : rafraîchir la dernière activité de la session (throttlé ~60 s).
        jeton = sess.get("jeton")
        if jeton and time.time() - sess.get("_touch", 0) > 60:
            sess["_touch"] = time.time()
            c = db_source.connect()
            try:
                journal.toucher(c, jeton)
            finally:
                c.close()

        if chemin == "/admin" or chemin.startswith("/admin/"):
            self._admin_get(chemin, sess)
            return
        if chemin == "/transcription":
            self._transcription_choix_get(sess)     # choix Dénombrement / VAD
            return
        if chemin == "/transcription/denombrement":
            self._transcription_get(sess)           # page de transcription (dénombrement)
            return
        if chemin == "/transcription/vad":
            self._transcription_vad_get(sess)        # VAD : pas encore disponible
            return

        # Espace LOGISTIQUE (Responsables Logistiques) : pages dédiées, réservées.
        if chemin == "/logistique" or chemin.startswith("/logistique/"):
            self._logistique_get(chemin, sess)
            return

        # Espace TRAITEMENT : accueil (choix) + remplissage base CE/Agents.
        # Le tableau de bord reste accessible via /choix (rôle non fermé).
        if chemin == "/traitement" or chemin.startswith("/traitement/"):
            self._traitement_get(chemin, sess)
            return

        resp_courant = (sess.get("utilisateur") or {}).get("responsabilite")
        # L'Expert survey n'a accès qu'à sa page de transcription : les pages de
        # sélection et le dashboard (choix / suivi / vue / menu / fokontany) lui
        # sont fermées. Toute autre route authentifiée le renvoie sur /transcription
        # (les routes publiques et /logout sont déjà traitées plus haut).
        if resp_courant == "Expert survey":
            self._redirige("/transcription")
            return
        # Les Responsables Logistiques n'ont PAS accès au tableau de bord : toute
        # route de sélection/dashboard les renvoie vers leur espace logistique.
        if resp_courant in _ROLES_LOGISTIQUE:
            self._redirige("/logistique")
            return

        if chemin == "/choix":
            # Première page après connexion : choix zone + limites + type de suivi
            # (zone masquée pour un Traitement, dont le district est déjà connu).
            self._html(page_selection(utilisateur=sess.get("utilisateur")))
        elif chemin == "/suivi":
            sel = sess.get("selection")
            if not sel:
                self._redirige("/choix")  # rien de choisi encore
                return
            if sel.get("suivi") == "vad":
                # Données visites à domicile pas encore disponibles.
                self._html(page_vad_indisponible(sel))
                return
            # Dénombrement : le dashboard multi-pages démarre sur la vue générale
            # du district.
            self._redirige("/vue/general")
        elif chemin.startswith("/vue/") or chemin == "/vue":
            sel = sess.get("selection")
            if not sel:
                self._redirige("/choix")
                return
            if sel.get("suivi") == "vad":
                self._html(page_vad_indisponible(sel))
                return
            parts = [p for p in chemin.split("/") if p]  # ['vue', section, level?, code?]
            section = parts[1] if len(parts) > 1 else "general"
            if section not in SECTIONS_VALIDES:
                self._html(page_erreur("Section inconnue."), 404)
                return
            level, code = "district", None
            if len(parts) >= 4 and parts[2] in ("commune", "fokontany"):
                level, code = parts[2], parts[3]
                if not str(code).isdigit():
                    self._html(page_erreur("Code de zone invalide."), 400)
                    return
            # Respect de l'affectation : district imposé, commune/fokontany bornés.
            statut, communes = self._perimetre_vue(
                sess.get("utilisateur"), sel, section, level, code)
            if statut == "stop":
                return
            try:
                self._html(rapport_vue(sel, section, level, code, communes),
                           prefixer=False)
            except rapport_core.ErreurRapport as e:
                self._html(page_erreur(str(e)), 404)
            except Exception as e:
                self._html(page_erreur("Erreur inattendue : " + repr(e)), 500)
        elif chemin == "/export/rapport.xlsx":
            # Export Excel du rapport (district courant, borné à l'affectation).
            sel = sess.get("selection")
            if not sel:
                self._redirige("/choix")
                return
            if sel.get("suivi") == "vad":
                self._html(page_vad_indisponible(sel))
                return
            # Réutilise la logique de périmètre de /vue (district imposé + communes).
            statut, communes = self._perimetre_vue(
                sess.get("utilisateur"), sel, "general", "district", None)
            if statut == "stop":
                return
            code_district = sel["code_district"]
            conn = db_source.connect()
            try:
                lib = zones.libelles_district(conn, code_district)
                nom = lib[2] if lib else str(code_district)
                data = export_rapport.generer_bytes(
                    conn, code_district, nom, communes)
            finally:
                conn.close()
            # Nom de fichier ASCII (Content-Disposition) : accents/espaces -> _.
            sans_accent = "".join(
                c for c in unicodedata.normalize("NFD", nom)
                if unicodedata.category(c) != "Mn")
            slug = re.sub(r"[^A-Za-z0-9]+", "_", sans_accent).strip("_") \
                or str(code_district)
            self._octets(
                data,
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet",
                f"Rapport_RSU2026_{slug}.xlsx")
        elif chemin == "/menu":
            # Menu global commune->fokontany (hérité) : réservé aux rôles voyant
            # TOUTE la zone. Un utilisateur affecté est renvoyé sur son dashboard.
            if perimetre(sess.get("utilisateur"))[0] is not None:
                self._redirige("/vue/general")
                return
            self._html(page_accueil())
        elif chemin.startswith("/fokontany/"):
            code = chemin.split("/fokontany/", 1)[1].strip("/")
            if not code.isdigit():
                self._html(page_erreur("Code de fokontany invalide."), 400)
                return
            # Respect de l'affectation : le fokontany doit être dans le périmètre.
            if not self._zone_autorisee(sess.get("utilisateur"), "fokontany", code):
                self._html(page_erreur("Zone hors de votre affectation.", 403), 403)
                return
            try:
                self._html(rapport_fokontany(code), prefixer=False)
            except rapport_core.ErreurRapport as e:
                self._html(page_erreur(str(e)), 404)
            except Exception as e:
                self._html(page_erreur("Erreur inattendue : " + repr(e)), 500)
        else:
            self._html(page_erreur("Page inconnue.", 404), 404)

    # -----------------------------------------------------------------------
    # Respect de l'AFFECTATION (périmètre géographique par rôle)
    # -----------------------------------------------------------------------
    def _zone_autorisee(self, u, level, code) -> bool:
        """True si (level, code) est DANS le périmètre d'affectation de `u`.

        `level` ∈ 'commune' | 'fokontany'. Zone entière (ou sans affectation) ->
        toujours True. Sinon la zone doit appartenir à l'UN des districts affectés,
        et — pour un rôle « district + communes » — à l'une de ses communes."""
        districts, acom = perimetre(u)
        if districts is None:
            return True
        ccode = None
        conn = db_source.connect()
        try:
            for d in districts:               # 1 district (mono) ou 1 à 5 (multi)
                ref = zones.reference_district(conn, d)
                if level == "commune":
                    if str(code) in {z["ccode"] for z in ref}:
                        ccode = str(code)
                        break
                else:                         # fokontany : retrouver sa commune
                    z = next((z for z in ref if z["fkt"] == str(code)), None)
                    if z:
                        ccode = z["ccode"]
                        break
        finally:
            conn.close()
        if ccode is None:
            return False                      # hors des districts affectés
        if acom is not None and ccode not in acom:
            return False                      # rôle communes : hors de ses communes
        return True

    def _perimetre_vue(self, u, sel, section, level, code):
        """Applique l'affectation au périmètre demandé d'une page /vue.

        Renvoie (statut, communes_filtre) :
          - ("ok", communes) -> autorisé ; `communes` (set ou None) à passer à
            rapport_vue pour filtrer la barre latérale/carte (rôle communes).
          - ("stop", None)   -> réponse déjà envoyée (redirection ou 403) :
            l'appelant doit s'arrêter."""
        districts, acom = perimetre(u)
        if districts is None:
            return ("ok", None)               # zone entière : aucun filtre.
        # Le district AFFICHÉ doit appartenir au périmètre. La sélection le borne
        # déjà ; on re-vérifie (défense en profondeur) et on retombe sur un district
        # autorisé si la session en porte un hors périmètre.
        if sel.get("code_district") not in districts:
            sel["code_district"] = sorted(districts)[0]
        if acom is not None and not acom:
            self._html(page_erreur("Aucune commune ne vous est affectée.", 403), 403)
            return ("stop", None)
        if level == "district":
            if acom is None:
                return ("ok", None)           # district entier autorisé (mono/multi).
            # Rôle communes : la vue « globale » agrège SES communes affectées
            # (rapport_vue reçoit `acom`), SAUF la Carte GPS (points ménage
            # nominatifs) qui n'a pas de vue globale -> descente sur une commune.
            if section == "gps":
                self._redirige(f"/vue/{section}/commune/{sorted(acom)[0]}")
                return ("stop", None)
            return ("ok", acom)
        if not self._zone_autorisee(u, level, code):
            self._html(page_erreur("Zone hors de votre affectation.", 403), 403)
            return ("stop", None)
        return ("ok", acom)

    def do_POST(self):
        brut = self.path.split("?", 1)[0]
        if not (brut == PREFIXE or brut.startswith(PREFIXE + "/")):
            self._html(page_erreur("Page inconnue.", 404), 404)
            return
        chemin = brut[len(PREFIXE):] or "/"
        if chemin == "/login":
            self._traiter_login()
        elif chemin == "/suivi":
            self._traiter_selection()
        elif chemin in ("/admin/utilisateurs", "/admin/import"):
            self._admin_post(chemin)
        elif chemin in ("/transcription/upload", "/transcription/transcrire"):
            self._transcription_post(chemin)
        elif chemin == "/traitement/equipes":
            self._traitement_equipes_post()
        elif chemin == "/traitement/prechargement":
            self._traitement_prechargement_post()
        else:
            self._html(page_erreur("Page inconnue.", 404), 404)

    # -----------------------------------------------------------------------
    # Espace ADMIN (réservé au rôle Admin)
    # -----------------------------------------------------------------------
    def _admin_ok(self, sess):
        """Renvoie le dict utilisateur si Admin, sinon envoie un 403 et renvoie None."""
        u = (sess or {}).get("utilisateur") or {}
        if u.get("responsabilite") == "Admin":
            return u
        self._html(page_erreur("Accès réservé à l'administrateur.", 403), 403)
        return None

    def _octets(self, data: bytes, mime: str, nom_fichier: str):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", f'attachment; filename="{nom_fichier}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _admin_get(self, chemin, sess):
        u = self._admin_ok(sess)
        if u is None:
            return
        conn = db_source.connect()
        try:
            if chemin == "/admin":
                with _SESSIONS_LOCK:
                    nb = len(_SESSIONS)
                self._html(admin.page_admin(conn, u, nb))
            elif chemin == "/admin/utilisateurs":
                self._html(admin.page_admin_utilisateurs(conn))
            elif chemin == "/admin/utilisateurs/ajouter":
                self._html(admin.page_admin_ajouter(conn))
            elif chemin == "/admin/utilisateurs/modifier":
                qs = urllib.parse.parse_qs(self.path.split("?", 1)[1]
                                           if "?" in self.path else "")
                login = (qs.get("login", [""])[0]).strip()
                self._html(admin.page_admin_modifier(conn, login))
            elif chemin == "/admin/journal":
                self._html(admin.page_journal(conn))
            elif chemin == "/admin/modele.xlsx":
                self._octets(admin.modele_xlsx(),
                             "application/vnd.openxmlformats-officedocument."
                             "spreadsheetml.sheet", "modele_utilisateurs.xlsx")
            elif chemin == "/admin/export/journal.csv":
                self._octets(admin.export_journal_csv(conn),
                             "text/csv; charset=utf-8", "journal_connexion.csv")
            elif chemin == "/admin/export/utilisateurs.csv":
                self._octets(admin.export_utilisateurs_csv(conn),
                             "text/csv; charset=utf-8", "utilisateurs.csv")
            else:
                self._html(page_erreur("Page admin inconnue.", 404), 404)
        finally:
            conn.close()

    def _upload_fichiers(self):
        """Liste des (nom, octets) de TOUS les fichiers d'un POST multipart/form-data.
        Parse via le module `email` (stdlib) — `cgi` étant retiré des Python récents."""
        ctype = self.headers.get("Content-Type", "")
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur) if longueur else b""
        if "multipart/form-data" not in ctype:
            return []
        msg = email.message_from_bytes(
            b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + corps)
        return [(part.get_filename(), part.get_payload(decode=True))
                for part in msg.walk() if part.get_filename()]

    def _upload_fichier(self):
        """(nom, octets) du premier fichier téléversé, ou (None, None)."""
        fichiers = self._upload_fichiers()
        return fichiers[0] if fichiers else (None, None)

    def _upload_par_champ(self):
        """{nom_du_champ: (nom_fichier, octets)} pour un POST multipart avec
        PLUSIEURS champs fichier nommés (ex. fichier_chef / fichier_agent)."""
        ctype = self.headers.get("Content-Type", "")
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur) if longueur else b""
        if "multipart/form-data" not in ctype:
            return {}
        msg = email.message_from_bytes(
            b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + corps)
        out = {}
        for part in msg.walk():
            nom_fichier = part.get_filename()
            if not nom_fichier:
                continue
            champ = part.get_param("name", header="content-disposition")
            if champ:
                out[champ] = (nom_fichier, part.get_payload(decode=True))
        return out

    # -----------------------------------------------------------------------
    # Espace EXPERT SURVEY : téléversement des .dta + transcription
    # -----------------------------------------------------------------------
    def _transcription_ok(self, sess):
        """Renvoie le dict utilisateur si Expert survey affecté à un district, sinon
        envoie un 403 et renvoie None."""
        u = (sess or {}).get("utilisateur") or {}
        if u.get("responsabilite") == "Expert survey" and u.get("district_affectation"):
            return u
        self._html(page_erreur(
            "Accès réservé à l'Expert survey affecté à un district.", 403), 403)
        return None

    def _district_txt(self, conn, code):
        lib = zones.libelles_district(conn, code)
        return f"{lib[2]} ({code})" if lib else str(code)

    # -----------------------------------------------------------------------
    # Espace LOGISTIQUE (Responsables Logistiques : District / Communale)
    # -----------------------------------------------------------------------
    def _logistique_ok(self, sess):
        """Renvoie l'utilisateur si rôle logistique, sinon 403 + None."""
        u = (sess or {}).get("utilisateur") or {}
        if u.get("responsabilite") in _ROLES_LOGISTIQUE:
            return u
        self._html(page_erreur("Accès réservé aux Responsables Logistiques.", 403), 403)
        return None

    def _logistique_contexte(self, u) -> dict:
        """Contexte d'affichage : rôle, district, et communes (Logistique Inter-Communale)."""
        conn = db_source.connect()
        try:
            code = u.get("district_affectation")
            district_txt = self._district_txt(conn, int(code)) if code else "—"
            communes = []
            if u.get("responsabilite") == "Logistique Inter-Communale":
                for cc in (u.get("communes_affectation") or []):
                    nom = zones.libelle_commune(conn, cc)
                    communes.append(f"{nom} ({cc})" if nom else str(cc))
        finally:
            conn.close()
        return {"role": u.get("responsabilite", ""),
                "district_txt": district_txt, "communes": communes}

    def _logistique_get(self, chemin, sess):
        u = self._logistique_ok(sess)
        if u is None:
            return
        ctx = self._logistique_contexte(u)
        section = chemin[len("/logistique"):].strip("/") or "accueil"
        pages = {
            "accueil": logistique.page_accueil,
            "taches": logistique.page_taches,
            "paiement": logistique.page_paiement,
            "pieces": logistique.page_pieces,
            "budget": logistique.page_budget,
        }
        fn = pages.get(section)
        if fn is None:
            self._html(page_erreur("Page logistique inconnue.", 404), 404)
            return
        self._html(fn(ctx))

    def _transcription_choix_get(self, sess):
        """Page de CHOIX de l'Expert : transcription Dénombrement ou Visite à domicile."""
        u = self._transcription_ok(sess)
        if u is None:
            return
        code = int(u["district_affectation"])
        conn = db_source.connect()
        try:
            txt = self._district_txt(conn, code)
        finally:
            conn.close()
        self._html(transcription.page_choix_transcription(txt))

    def _transcription_vad_get(self, sess):
        """Transcription Visite à domicile : page « pas encore disponible » (la
        structure de base VAD n'existe pas encore)."""
        u = self._transcription_ok(sess)
        if u is None:
            return
        code = int(u["district_affectation"])
        conn = db_source.connect()
        try:
            txt = self._district_txt(conn, code)
        finally:
            conn.close()
        self._html(transcription.page_vad_transcription(txt))

    def _transcription_get(self, sess):
        u = self._transcription_ok(sess)
        if u is None:
            return
        code = int(u["district_affectation"])
        conn = db_source.connect()
        try:
            txt = self._district_txt(conn, code)
            hist = journal.transcriptions(conn, limite=20, login=u["login"])
        finally:
            conn.close()
        self._html(transcription.page_transcription(txt, historique=hist))

    def _transcription_post(self, chemin):
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = self._transcription_ok(sess)
        if u is None:
            return
        code = int(u["district_affectation"])
        dossier = os.path.join(config.UPLOAD_DIR, str(code))
        attendus = {fn for _k, (fn, _tb) in db_source.FICHIERS.items()}
        # Phase (pour la journalisation, y compris en cas d'exception maj_db).
        phase = ("Téléversement" if chemin == "/transcription/upload"
                 else "Transcription")
        apercu = resultat = message = erreur = None
        conn = db_source.connect()
        try:
            txt = self._district_txt(conn, code)
            if chemin == "/transcription/upload":
                # On écrit d'abord dans un TEMPORAIRE, on VALIDE, et on ne déplace
                # vers UPLOAD_DIR/<code>/ que si tout est bon (aucun fichier douteux
                # laissé dans le dossier réel).
                tmp = tempfile.mkdtemp(prefix="rsu_up_")
                try:
                    # On conserve TOUS les fichiers du dossier choisi par l'Expert
                    # (pas seulement les 3 .dta), SOUS-DOSSIERS COMPRIS (« Questionnaire/ »
                    # et autres). Les chemins relatifs sont recréés dans le temporaire.
                    recus = []
                    for nom, data in self._upload_fichiers():
                        rel = _relpath_upload(nom)
                        if not rel or not data:
                            continue
                        dst = os.path.join(tmp, *rel.split("/"))
                        if not _sous_dossier(tmp, dst):    # garde anti-traversée
                            continue
                        os.makedirs(os.path.dirname(dst) or tmp, exist_ok=True)
                        with open(dst, "wb") as f:
                            f.write(data)
                        recus.append(rel)
                    # Les 3 .dta requis doivent être présents à la RACINE du dossier
                    # (c'est là que maj_db et la vérif. de district les lisent).
                    racine = {r for r in recus if "/" not in r}
                    manquants = [fn for fn in attendus if fn not in racine]
                    if manquants:
                        erreur = ("Téléversement refusé — fichiers .dta requis "
                                  "manquants : " + ", ".join(sorted(manquants))
                                  + ". Le dossier doit contenir au moins ces 3 fichiers.")
                        journal.consigner(
                            conn, u["login"], u.get("nom_prenom", ""), code,
                            "Téléversement", "Échec",
                            detail="Fichiers manquants : " + ", ".join(sorted(manquants)))
                    else:
                        # Le dossier doit concerner UNIQUEMENT le district de l'Expert
                        # (variable `district` de DEN_MENAGE.dta).
                        districts = db_source.districts_du_den(tmp)
                        if districts != {code}:
                            trouve = (", ".join(str(x) for x in sorted(districts))
                                      or "aucun district identifiable")
                            erreur = ("Téléversement refusé — ce dossier concerne le "
                                      f"district <b>{trouve}</b>, alors que vous êtes "
                                      f"affecté au district <b>{code}</b>. "
                                      "Vérifiez le dossier sélectionné.")
                            journal.consigner(
                                conn, u["login"], u.get("nom_prenom", ""), code,
                                "Téléversement", "Échec",
                                detail=f"District {trouve} au lieu de {code}")
                        else:
                            os.makedirs(dossier, exist_ok=True)
                            for rel in recus:
                                src = os.path.join(tmp, *rel.split("/"))
                                dst = os.path.join(dossier, *rel.split("/"))
                                os.makedirs(os.path.dirname(dst) or dossier,
                                            exist_ok=True)
                                if os.path.exists(dst):   # remplacer (Windows: rename
                                    os.remove(dst)        # échoue si la cible existe)
                                shutil.move(src, dst)
                            apercu = maj_db.maj_depuis_dossier(
                                dossier, conn, log=lambda *a: None, dry_run=True)
                            apercu["fichiers"] = recus
                            journal.consigner(
                                conn, u["login"], u.get("nom_prenom", ""), code,
                                "Téléversement", "Réussi",
                                detail=(f"{len(recus)} fichier(s) reçu(s) : "
                                        + ", ".join(recus)),
                                fichiers=", ".join(recus))
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            else:  # /transcription/transcrire : appliquer sur les fichiers déjà reçus
                if not os.path.isdir(dossier) or not os.listdir(dossier):
                    erreur = "Aucun fichier téléversé. Recommencez."
                    journal.consigner(
                        conn, u["login"], u.get("nom_prenom", ""), code,
                        "Transcription", "Échec", detail="Aucun fichier téléversé")
                else:
                    resultat = maj_db.maj_depuis_dossier(
                        dossier, conn, log=lambda *a: None, dry_run=False)
                    presents = ", ".join(t["table"] for t in resultat["tables"]
                                         if t["present"])
                    tot = resultat["total"]
                    message = "Transcription terminée et validée."
                    journal.consigner(
                        conn, u["login"], u.get("nom_prenom", ""), code,
                        "Transcription", "Réussi",
                        detail=(f"+{tot['ajoutes']} ajoutées · ~{tot['modifies']} "
                                f"modifiées · ={tot['inchanges']} inchangées"),
                        fichiers=presents, ajoutes=tot["ajoutes"],
                        modifies=tot["modifies"], inchanges=tot["inchanges"])
                    # Nouveaux codes agent éventuels -> compléter `agent` (nom = code)
                    # et purger le cache (données changées).
                    equipes.synchroniser_agents(conn)
                    _vider_cache()
        except maj_db.ErreurMaj as e:
            erreur = htmllib.escape(str(e))
            journal.consigner(conn, u["login"], u.get("nom_prenom", ""), code,
                              phase, "Échec", detail=str(e))
        finally:
            hist = journal.transcriptions(conn, limite=20, login=u["login"])
            conn.close()
        self._html(transcription.page_transcription(
            txt, apercu=apercu, resultat=resultat, message=message,
            erreur=erreur, historique=hist))

    # -----------------------------------------------------------------------
    # Espace TRAITEMENT : base des Chefs d'Équipe et des Agents
    # -----------------------------------------------------------------------
    def _traitement_ok(self, sess):
        """Renvoie l'utilisateur si rôle « Traitement », sinon 403 + None."""
        u = (sess or {}).get("utilisateur") or {}
        if u.get("responsabilite") == "Traitement":
            return u
        self._html(page_erreur("Accès réservé à l'Expert Traitement.", 403), 403)
        return None

    def _traitement_get(self, chemin, sess):
        u = self._traitement_ok(sess)
        if u is None:
            return
        conn = db_source.connect()
        try:
            code = u.get("district_affectation")
            txt = self._district_txt(conn, code) if code else "—"
            if chemin == "/traitement":
                self._html(equipes.page_choix_traitement(txt))
            elif chemin == "/traitement/equipes":
                self._html(equipes.page_equipes(conn, txt))
            elif chemin == "/traitement/prechargement":
                self._html(prechargement.page_prechargement(txt))
            elif chemin == "/traitement/modele/chef.xlsx":
                self._octets(equipes.modele_chef_xlsx(),
                             "application/vnd.openxmlformats-officedocument."
                             "spreadsheetml.sheet", "modele_chefs_equipe.xlsx")
            elif chemin == "/traitement/modele/agent.xlsx":
                self._octets(equipes.modele_agent_xlsx(),
                             "application/vnd.openxmlformats-officedocument."
                             "spreadsheetml.sheet", "modele_agents.xlsx")
            else:
                self._html(page_erreur("Page inconnue.", 404), 404)
        finally:
            conn.close()

    def _traitement_equipes_post(self):
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = self._traitement_ok(sess)
        if u is None:
            return
        champs = self._upload_par_champ()
        conn = db_source.connect()
        resultat = message = erreur = None
        tmp = tempfile.mkdtemp(prefix="rsu_equipes_")
        try:
            code = u.get("district_affectation")
            txt = self._district_txt(conn, code) if code else "—"
            data_chef = (champs.get("fichier_chef") or (None, None))[1]
            data_agent = (champs.get("fichier_agent") or (None, None))[1]
            if not data_chef or not data_agent:
                erreur = ("Les <b>deux</b> fichiers Excel sont requis "
                          "(Chefs d'Équipe et Agents).")
            else:
                p_chef = os.path.join(tmp, "chefs.xlsx")
                p_agent = os.path.join(tmp, "agents.xlsx")
                with open(p_chef, "wb") as f:
                    f.write(data_chef)
                with open(p_agent, "wb") as f:
                    f.write(data_agent)
                try:
                    resultat = equipes.transcrire(conn, p_chef, p_agent)
                    c, a = resultat["chefs"], resultat["agents"]
                    message = (f"Transcription terminée : Chefs +{c['ajoutes']}/"
                               f"~{c['modifies']} · Agents +{a['ajoutes']}/"
                               f"~{a['modifies']}.")
                    _vider_cache()   # noms d'agents changés -> rapport à régénérer
                except ValueError as e:            # colonnes manquantes, etc.
                    erreur = htmllib.escape(str(e))
            page = equipes.page_equipes(conn, txt, resultat=resultat,
                                        message=message, erreur=erreur)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            conn.close()
        self._html(page)

    def _traitement_prechargement_post(self):
        """Génère la base de préchargement + la charge par agent -> ZIP en
        téléchargement. Rôle Traitement uniquement ; district = affectation."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = self._traitement_ok(sess)
        if u is None:
            return
        # Parse multipart : champ texte « mode » + fichiers « exclure » (0..n).
        ctype = self.headers.get("Content-Type", "")
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur) if longueur else b""
        mode = "denombrement"
        exclure = []
        if "multipart/form-data" in ctype:
            msg = email.message_from_bytes(
                b"Content-Type: " + ctype.encode()
                + b"\r\nMIME-Version: 1.0\r\n\r\n" + corps)
            for part in msg.walk():
                champ = part.get_param("name", header="content-disposition")
                fichier = part.get_filename()
                if fichier:
                    if champ == "exclure":
                        octets = part.get_payload(decode=True)
                        if octets:
                            exclure.append((fichier, octets))
                elif champ == "mode":
                    val = part.get_payload(decode=True)
                    if val:
                        mode = val.decode("utf-8", "replace").strip()

        conn = db_source.connect()
        try:
            code = u.get("district_affectation")
            txt = self._district_txt(conn, code) if code else "—"
            if not code:
                self._html(prechargement.page_prechargement(
                    txt, erreur="Aucun district d'affectation : impossible de "
                                "générer la base de préchargement."))
                return
            try:
                nom_zip, octets_zip = prechargement.generer_zip(
                    conn, int(code), mode=mode, exclure_fichiers=exclure)
            except rapport_core.ErreurDonnees as e:
                self._html(prechargement.page_prechargement(
                    txt, erreur=htmllib.escape(str(e))))
                return
        finally:
            conn.close()
        self._octets(octets_zip, "application/zip", nom_zip)

    def _admin_post(self, chemin):
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = self._admin_ok(sess)
        if u is None:
            return
        conn = db_source.connect()
        try:
            if chemin == "/admin/import":
                # L'import (comme l'ajout) reste sur la page « Ajouter ».
                message, erreur = self._admin_importer(conn)
                page = admin.page_admin_ajouter(conn, message=message, erreur=erreur)
            else:
                action, message, erreur = self._admin_action_utilisateur(conn)
                if action == "ajouter":
                    page = admin.page_admin_ajouter(conn, message=message, erreur=erreur)
                elif action == "modifier" and erreur:
                    # échec -> rester sur le formulaire pré-rempli pour corriger
                    login = (self._corps_modifier_login or "").strip()
                    page = admin.page_admin_modifier(
                        conn, login, message=message, erreur=erreur)
                else:   # modifier (succès) / actif / suppr / reset -> retour à la liste
                    page = admin.page_admin_utilisateurs(
                        conn, message=message, erreur=erreur)
        finally:
            conn.close()
        self._html(page)

    def _affectation_kw(self, c, resp):
        """Construit les kwargs d'affectation selon le rôle (mono / multi / communes /
        zone entière) à partir du corps de formulaire `c`. Ne transmet que les champs
        utiles au rôle -> pas de valeur parasite d'un widget masqué."""
        g = lambda k: (c.get(k, [""])[0]).strip()
        districts = [x for x in c.get("district_multi", []) if x.strip()]
        communes = [x for x in c.get("commune_multi", []) if x.strip()]
        if resp in utilisateurs._ROLES_MULTI_DISTRICT:
            return {"districts_affectation": districts or None}
        if resp in utilisateurs._ROLES_DISTRICT_COMMUNES:
            return {"commune_affectation": communes or None}   # district déduit
        if resp in utilisateurs._ROLES_UN_DISTRICT:
            return {"district_affectation": g("district") or None}
        return {}                                              # zone entière

    def _admin_action_utilisateur(self, conn):
        c = self._corps_formulaire()
        g = lambda k: (c.get(k, [""])[0]).strip()
        action = g("action")
        login = g("login")
        self._corps_modifier_login = login
        try:
            if action == "modifier":
                resp = g("responsabilite")
                kw = self._affectation_kw(c, resp)
                kw["telephone"] = g("telephone") or None
                kw["cin"] = g("cin") or None
                kw["email"] = g("email") or None
                kw["mot_de_passe"] = c.get("mot_de_passe", [""])[0] or None
                utilisateurs.modifier(conn, login, g("nom_prenom"), resp, **kw)
                conn.commit()
                return (action, f"Utilisateur « {login} » modifié.", None)
            if action == "ajouter":
                # Formulaire en lignes de cascade : le district d'un rôle mono vient
                # de "district" ; les districts multi de "district_multi" (×5) ; les
                # communes de "commune_multi" (×5). Le RÔLE décide des champs utilisés.
                resp = g("responsabilite")
                kw = self._affectation_kw(c, resp)
                kw["telephone"] = g("telephone") or None
                kw["cin"] = g("cin") or None
                kw["email"] = g("email") or None
                utilisateurs.ajouter(
                    conn, g("login"), g("nom_prenom"), resp,
                    c.get("mot_de_passe", [""])[0], **kw)
                conn.commit()
                return (action, f"Utilisateur « {g('login')} » ajouté.", None)
            if action == "actif":
                utilisateurs.definir_actif(conn, login, g("etat") == "on")
                conn.commit()
                return (action, f"Compte « {login} » "
                        f"{'activé' if g('etat')=='on' else 'désactivé'}.", None)
            if action == "suppr":
                utilisateurs.supprimer(conn, login)
                conn.commit()
                return (action, f"Utilisateur « {login} » supprimé.", None)
            if action == "reset":
                mdp = c.get("mdp", [""])[0]
                if not mdp:
                    return (action, None, "Mot de passe vide.")
                utilisateurs.changer_mot_de_passe(conn, login, mdp)
                conn.commit()
                return (action, f"Mot de passe de « {login} » réinitialisé.", None)
            return (action, None, "Action inconnue.")
        except ValueError as e:
            return (action, None, htmllib.escape(str(e)))

    def _admin_importer(self, conn):
        nom, data = self._upload_fichier()
        if not data:
            return (None, "Aucun fichier reçu (attendu : un .xlsx).")
        tmp = os.path.join(tempfile.mkdtemp(prefix="rsu_import_"), "import.xlsx")
        with open(tmp, "wb") as f:
            f.write(data)
        try:
            ajoutes, erreurs = admin.importer_excel(conn, tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        message = (f"{ajoutes} utilisateur(s) importé(s) depuis "
                   f"« {htmllib.escape(nom or 'fichier')} ». "
                   f"Pensez à SUPPRIMER le fichier (mots de passe en clair).")
        erreur = None
        if erreurs:
            lignes = "".join(f"<li>Ligne {n} : {htmllib.escape(m)}</li>"
                             for n, m in erreurs)
            erreur = f"{len(erreurs)} ligne(s) rejetée(s) :<ul>{lignes}</ul>"
        return (message, erreur)

    def _corps_formulaire(self) -> dict:
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur).decode("utf-8") if longueur else ""
        return urllib.parse.parse_qs(corps)

    def _traiter_login(self):
        champs = self._corps_formulaire()
        login = (champs.get("login", [""])[0]).strip()
        mdp = champs.get("motdepasse", [""])[0]
        ip = self.client_address[0] if self.client_address else ""

        conn = db_source.connect()
        try:
            u = utilisateurs.authentifier(conn, login, mdp)
            if u:
                jeton = secrets.token_hex(16)
                with _SESSIONS_LOCK:
                    _SESSIONS[jeton] = {"login": u["login"], "selection": None,
                                        "utilisateur": u, "jeton": jeton}
                journal.ouvrir(conn, jeton, u["login"], u.get("nom_prenom", ""),
                               u.get("responsabilite", ""), ip)
            else:
                # Motif tracé pour l'admin (jamais montré à l'usager).
                motif = utilisateurs.raison_echec(conn, login, mdp) or "échec"
                journal.tentative(conn, login, motif, ip)
        finally:
            conn.close()

        if u:
            cookie = (f"{COOKIE_SESSION}={jeton}; Path={PREFIXE}; HttpOnly; "
                      f"SameSite=Lax; Max-Age=28800")  # 8 h
            print(f"[app] connexion réussie : {u['login']} ({u['responsabilite']})")
            # Chaque rôle arrive sur sa page principale ; les autres sur la sélection.
            dest = accueil_role(u.get("responsabilite"))
            self._redirige(dest, entetes=[("Set-Cookie", cookie)])
        else:
            print(f"[app] échec de connexion : {login!r}")
            self._redirige("/login?erreur=1")

    def _traiter_selection(self):
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = sess.get("utilisateur") or {}
        # Expert survey / Responsables Logistiques : pas d'accès à la sélection
        # (dashboard fermé) -> renvoi sur leur espace, comme côté GET.
        if u.get("responsabilite") == "Expert survey":
            self._redirige("/transcription")
            return
        if u.get("responsabilite") in _ROLES_LOGISTIQUE:
            self._redirige("/logistique")
            return
        champs = self._corps_formulaire()
        # Le district est borné par le périmètre du rôle :
        #  - zone entière -> district libre du POST ;
        #  - 1 district affecté -> IMPOSÉ (POST ignoré) ;
        #  - multi-district -> POST accepté SEULEMENT s'il est dans ses districts.
        districts_perim = perimetre(u)[0]
        district = (champs.get("district", [""])[0]).strip()
        if districts_perim is not None:
            if len(districts_perim) == 1:
                district = str(sorted(districts_perim)[0])       # imposé
            elif not (district.isdigit() and int(district) in districts_perim):
                self._html(page_selection(
                    "Veuillez choisir un district parmi vos affectations.",
                    utilisateur=u), 400)
                return
        limites = (champs.get("limites", ["ocha"])[0]).strip()
        chemin_lim = (champs.get("chemin_limites", [""])[0]).strip()
        suivi = (champs.get("suivi", [""])[0]).strip()

        # Validation.
        if not district.isdigit():
            self._html(page_selection("Veuillez choisir un district.",
                                      utilisateur=u), 400)
            return
        if suivi not in ("den", "vad"):
            self._html(page_selection("Veuillez choisir un type de suivi.",
                                      utilisateur=u), 400)
            return
        if limites not in ("ocha", "generer", "dossier"):
            limites = "ocha"
        if limites == "dossier" and not chemin_lim:
            self._html(page_selection(
                "Veuillez indiquer le chemin du dossier de limites.",
                utilisateur=u), 400)
            return

        # Libellés depuis le référentiel (source de vérité) plutôt que le POST.
        conn = db_source.connect()
        try:
            libs = zones.libelles_district(conn, district)
        finally:
            conn.close()
        if not libs:
            self._html(page_selection("District inconnu dans le référentiel.",
                                      utilisateur=u), 400)
            return
        province_nom, region_nom, district_nom = libs

        selection = {
            "code_district": int(district),
            "province_nom": province_nom,
            "region_nom": region_nom,
            "district_nom": district_nom,
            "limites": limites,
            "chemin_limites": chemin_lim,
            "suivi": suivi,
        }
        with _SESSIONS_LOCK:
            sess["selection"] = selection
        print(f"[app] sélection : district={district_nom} suivi={suivi} "
              f"limites={limites}")
        self._redirige("/suivi")

    def deconnecter(self):
        """Invalide la session et renvoie vers la page de connexion."""
        brut = self.headers.get("Cookie")
        jeton = None
        if brut:
            morceau = http.cookies.SimpleCookie(brut).get(COOKIE_SESSION)
            if morceau:
                jeton = morceau.value
                with _SESSIONS_LOCK:
                    _SESSIONS.pop(jeton, None)
        if jeton:
            conn = db_source.connect()
            try:
                journal.fermer(conn, jeton)          # fige la durée de la session
            finally:
                conn.close()
        expire = f"{COOKIE_SESSION}=; Path={PREFIXE}; Max-Age=0"
        self._redirige("/login", entetes=[("Set-Cookie", expire)])

    def log_message(self, fmt, *args):
        print("[app]", fmt % args)


def main():
    print("Préparation de la base et du menu…")
    preparer()
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        url = f"http://127.0.0.1:{PORT}/"
        print(f"Application RSU (base de données) en ligne : {url}")
        print("Ctrl+C pour arrêter.")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nArrêt du serveur.")


if __name__ == "__main__":
    main()
