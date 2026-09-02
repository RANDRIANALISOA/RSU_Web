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
import manuel
import consignes
import rapport_mission
import rapport_word

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
    # Consignes / instructions des Coordonnateurs (tables si absentes).
    consignes.creer_tables(conn)
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

# Rôles bornés à UN district qui peuvent consulter la fiche « Équipe technique »
# de LEUR district (route /equipe). Le Coordonnateur Nationale, lui, y accède par
# la sélection (choix « Équipe technique » du district de son choix).
_ROLES_EQUIPE_DISTRICT = ("Traitement", "Superviseur Technique", "Expert survey")

# Rôles qui atterrissent d'abord sur un MENU d'opération (au lieu de la sélection
# directe) : ils choisissent l'opération (Tableau de bord OU Équipe technique), puis
# — pour ceux dont le district n'est PAS fixé (Coordonnateurs) — le district. Le
# Superviseur Technique (district fixe) va directement au résultat.
_ROLES_MENU_OPERATION = ("Coordonnateur Nationale", "Coordonnateur régionale",
                         "Superviseur Technique")

# Adresse (route) du MENU de chaque rôle à menu — sur le modèle de /traitement :
# chaque rôle a SA page d'accueil dédiée (au lieu de la sélection /choix partagée).
_MENU_CHEMINS = {
    "Coordonnateur Nationale": "/coordonat",
    "Coordonnateur régionale": "/coordoreg",
    "Superviseur Technique": "/suptech",
}

# JOURNAL DE BORD (route /journal). Deux usages selon le rôle :
#  - ÉCRITURE : toute l'équipe technique SAUF les deux coordonnateurs et l'Admin ;
#    chacun consigne ses activités du jour (rappel si rien écrit aujourd'hui).
#  - LECTURE : les deux coordonnateurs + l'Admin lisent les journaux des équipes,
#    bornés à leur périmètre (National/Admin = tout, Régional = ses districts).
_ROLES_JOURNAL_ECRITURE = ("Comités Techniques", "Traitement", "Expert survey",
                           "Superviseur Technique", "Logistique District",
                           "Logistique Inter-Communale")
_ROLES_JOURNAL_LECTURE = ("Coordonnateur Nationale", "Coordonnateur régionale",
                          "Admin")

# RAPPORT DE MISSION — VERSION IA (Word). Réservé à des LOGINS précis (les deux
# Coordonnateurs régionaux), et NON à un rôle : seuls ces comptes peuvent générer
# et télécharger le rapport rédigé par IA. La compilation HORS-LIGNE
# (/rapport-mission) reste, elle, ouverte aux rôles de LECTURE ci-dessus. Pour
# ouvrir l'accès à un autre compte (ex. un futur COORDOREG_03), l'ajouter ici.
LOGINS_RAPPORT_IA = {"COORDOREG_01", "COORDOREG_02"}


def peut_rapport_ia(u) -> bool:
    """Vrai si l'utilisateur connecté peut accéder au rapport de mission IA (Word)."""
    return ((u or {}).get("login") or "").strip() in LOGINS_RAPPORT_IA

# CONSIGNES / INSTRUCTIONS. Émetteurs = les deux Coordonnateurs (le National peut
# viser tous les districts ; le Régional est borné à SES districts). Rôles
# ciblables (destinataires) = tous les rôles sauf Admin (« Tout le monde » vise
# tous ces rôles). Tout le monde peut RECEVOIR (bulle + page /consignes).
_ROLES_CONSIGNE_ENVOI = ("Coordonnateur Nationale", "Coordonnateur régionale")
_ROLES_CONSIGNE_CIBLES = tuple(
    r for r in utilisateurs.RESPONSABILITES if r != "Admin")


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
    if resp in _MENU_CHEMINS:
        return _MENU_CHEMINS[resp]    # menu dédié : /coordonat, /coordoreg, /suptech
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
  :root{{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px)}}

  body{{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:47.5rem;margin:2.25rem auto;
       padding:0 1rem;color:#1c2430;line-height:1.5}}
  h1{{font-size:1.5rem;margin-bottom:0.25rem}}
  .sous{{color:#5a6675;margin-top:0}}
  details{{border:1px solid #dce3ea;border-radius:0.5rem;margin:0.5rem 0;padding:0.375rem 0.75rem}}
  summary{{cursor:pointer;font-weight:600}}
  .n{{color:#8a97a6;font-weight:400}}
  ul{{list-style:none;padding-left:0.5rem;margin:0.5rem 0}}
  li{{padding:0.25rem 0}}
  a{{color:#1b6ef3;text-decoration:none}} a:hover{{text-decoration:underline}}
  .code{{color:#9aa6b3;font-size:.8rem;margin-left:0.375rem}}
  .note{{background:#eef6ff;border:1px solid #cfe2ff;border-radius:0.5rem;padding:0.75rem;
         font-size:.88rem;margin:1.125rem 0}}
  .barre{{display:flex;justify-content:flex-end;margin-bottom:0.25rem}}
  .barre a{{font-size:.85rem;color:#5a6675;border:1px solid #dce3ea;border-radius:0.5rem;
    padding:0.3125rem 0.75rem}}
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
:root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px);}

  *{box-sizing:border-box}
  :root{--bleu:#1b6ef3;--bleu-f:#1558c9;--vert:#17a398;--nuit:#0d2b4e;--texte:#1c2430}
  html,body{min-height:100%}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:var(--texte);margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1.375rem;
    line-height:1.5;background:#0d2b4e}

  /* Image officielle RSU en FOND PLEINE PAGE (couche fixe + zoom lent) */
  .fond{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat;
    animation:zoomlent 22s ease-in-out infinite alternate}
  /* Voile léger par-dessus : donne du contraste sans masquer l'image */
  .voile{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.42) 0%,rgba(21,88,201,.26) 55%,rgba(23,163,152,.30) 130%)}

  /* Cadre : deux colonnes (visuel + formulaire), posé sur l'image */
  .cadre{position:relative;z-index:2;display:flex;width:100%;max-width:58.75rem;
    background:transparent;border-radius:1.25rem;overflow:hidden;
    box-shadow:0 1.875rem 4.375rem rgba(0,0,0,.42);animation:apparaitre .7s ease both}

  /* Colonne gauche : panneau illustré animé (translucide, laisse voir l'image) */
  .visuel{position:relative;flex:1 1 46%;min-width:0;color:#fff;padding:2.375rem 2.125rem;
    display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;
    background:linear-gradient(140deg,rgba(13,43,78,.72) 0%,rgba(21,88,201,.5) 55%,
      rgba(23,163,152,.5) 130%);
    background-size:180% 180%;animation:degrade 12s ease infinite alternate}
  .visuel::before,.visuel::after{content:"";position:absolute;border-radius:50%;
    background:rgba(255,255,255,.09);filter:blur(2px)}
  .visuel::before{width:13.75rem;height:13.75rem;top:-4.375rem;right:-3.75rem;
    animation:flotter 9s ease-in-out infinite}
  .visuel::after{width:9.375rem;height:9.375rem;bottom:-3.125rem;left:-2.5rem;
    animation:flotter 7s ease-in-out infinite reverse}
  .v-haut{position:relative;z-index:2;display:flex;align-items:center;gap:0.75rem}
  .badge{width:3.25rem;height:3.25rem;border-radius:0.875rem;flex:none;background:rgba(255,255,255,.16);
    border:1px solid rgba(255,255,255,.35);display:flex;align-items:center;justify-content:center;
    font-weight:800;letter-spacing:.5px;font-size:1.05rem;backdrop-filter:blur(0.25rem)}
  .v-haut .titre{font-size:1.18rem;font-weight:700;margin:0}
  .v-haut .st{font-size:.82rem;opacity:.85;margin:0}
  .scene{position:relative;z-index:2;align-self:center;width:100%;max-width:20rem;margin:0.5rem 0}
  .accroche{position:relative;z-index:2}
  .accroche h2{font-size:1.32rem;line-height:1.3;margin:0 0 0.875rem}
  .puces{list-style:none;padding:0;margin:0;display:grid;gap:0.625rem}
  .puces li{display:flex;align-items:center;gap:0.6875rem;font-size:.92rem;opacity:0;
    animation:glisser .6s ease forwards}
  .puces li:nth-child(1){animation-delay:.35s}
  .puces li:nth-child(2){animation-delay:.5s}
  .puces li:nth-child(3){animation-delay:.65s}
  .ico{width:2.125rem;height:2.125rem;flex:none;border-radius:0.625rem;background:rgba(255,255,255,.15);
    border:1px solid rgba(255,255,255,.28);display:flex;align-items:center;justify-content:center}

  /* Colonne droite : formulaire (verre dépoli translucide sur l'image) */
  .carte{flex:1 1 54%;min-width:0;padding:2.75rem 2.5rem;display:flex;flex-direction:column;
    justify-content:center;background:rgba(255,255,255,.86);
    backdrop-filter:blur(0.75rem) saturate(120%);-webkit-backdrop-filter:blur(0.75rem) saturate(120%)}
  .bienvenue{font-size:1.5rem;font-weight:700;margin:0 0 0.25rem}
  .sous{color:#5a6675;margin:0 0 1.5rem;font-size:.94rem}
  label{display:block;font-weight:600;font-size:.86rem;margin:0.875rem 0 0.375rem}
  .champ{position:relative}
  .champ svg{position:absolute;left:0.75rem;top:50%;transform:translateY(-50%);opacity:.45}
  input{width:100%;padding:0.75rem 0.875rem 0.75rem 2.625rem;font-size:1rem;color:var(--texte);
    background:#f7f9fc;border:1.5px solid #e1e7ef;border-radius:0.6875rem;outline:none;
    transition:.18s}
  input:focus{border-color:var(--bleu);background:#fff;box-shadow:0 0 0 0.25rem rgba(27,110,243,.14)}
  button.principal{width:100%;margin-top:1.5rem;padding:0.8125rem;font-size:1.02rem;font-weight:700;
    color:#fff;border:none;border-radius:0.6875rem;cursor:pointer;letter-spacing:.3px;
    background:linear-gradient(135deg,var(--bleu),var(--bleu-f));
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.30);transition:.18s}
  button.principal:hover{transform:translateY(-2px);box-shadow:0 0.875rem 1.75rem rgba(27,110,243,.38)}
  button.principal:active{transform:translateY(0)}
  .message{display:none;margin-top:1rem;padding:0.6875rem 0.8125rem;border-radius:0.6875rem;font-size:.88rem;
    background:#fdecea;border:1px solid #f5c6c2;color:#c0392b}
  .message.visible{display:block;animation:glisser .3s ease both}
  .pied{margin-top:1.625rem;font-size:.78rem;color:#9aa6b3;text-align:center;
    display:flex;align-items:center;justify-content:center;gap:0.375rem}

  /* Animations SVG (parties de la scène) */
  .flot{animation:flotter 6s ease-in-out infinite;transform-origin:center}
  .flot-2{animation:flotter 5s ease-in-out infinite .6s;transform-origin:center}
  .anneau{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-out infinite}
  .anneau2{transform-box:fill-box;transform-origin:center;animation:pulse 2.6s ease-out 1.3s infinite}

  @keyframes apparaitre{from{opacity:0;transform:translateY(1.125rem)}to{opacity:1;transform:none}}
  @keyframes glisser{from{opacity:0;transform:translateX(-0.75rem)}to{opacity:1;transform:none}}
  @keyframes flotter{0%,100%{transform:translateY(0)}50%{transform:translateY(-0.625rem)}}
  @keyframes degrade{0%{background-position:0% 50%}100%{background-position:100% 50%}}
  @keyframes pulse{0%{transform:scale(.5);opacity:.7}80%{transform:scale(2.4);opacity:0}100%{opacity:0}}
  @keyframes zoomlent{0%{transform:scale(1)}100%{transform:scale(1.12)}}

  /* Responsive : sur petit écran, on empile et on masque le panneau visuel lourd */
  @media (max-width:820px){
    .cadre{flex-direction:column;max-width:27.5rem}
    .visuel{padding:1.625rem 1.625rem 1.375rem}
    .scene,.accroche h2{display:none}
    .carte{padding:2rem 1.75rem}
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
# Page MENU d'opération (juste après la connexion) pour les rôles de
# _ROLES_MENU_OPERATION : l'utilisateur choisit d'abord CE QU'IL veut faire
# (Tableau de bord OU Équipe technique). Le Superviseur Technique (district fixe)
# est mené directement au résultat ; les Coordonnateurs choisissent ensuite le
# district (page de sélection avec l'opération déjà fixée).
# ---------------------------------------------------------------------------
def page_menu_operation(role: str, utilisateur=None) -> str:
    """Menu d'accueil d'un rôle à menu — MÊME charte que la page Traitement
    (fond clair `admin._STYLE`, barre sombre, cartes `equipes._CSS_CHOIX`), sans
    image de fond. Les liens des cartes pointent vers la route dédiée du rôle
    (`_MENU_CHEMINS`), avec `?op=…` pour l'opération choisie."""
    esc = htmllib.escape
    role = (role or "").strip()
    base = _MENU_CHEMINS.get(role, "/choix")
    # Le Superviseur a un district fixe : sa fiche équipe s'ouvre directement
    # (/equipe). Les Coordonnateurs choisissent d'abord le district (<menu>?op=…).
    fixe = role == "Superviseur Technique"
    href_bord = f"{base}?op=den"
    href_vad = f"{base}?op=vad"
    href_equipe = "/equipe" if fixe else f"{base}?op=equipe"
    suite = "Ouvrir →" if fixe else "Choisir le district →"
    d_lieu = " de votre district." if fixe else " du district de votre choix."
    d_bord = "Consulter le rapport de suivi du dénombrement" + d_lieu
    d_equipe = ("Voir l’encadrement (Coordonnateur régional, Superviseurs "
                "Techniques par axe, Traitement, Expert survey)"
                + (" affecté à votre district." if fixe
                   else " affecté au district de votre choix."))
    cartes = (
        f'<a class="ca" href="{href_bord}">'
        '<div class="ic">📊</div><div class="t">Tableau de bord — Dénombrement</div>'
        f'<div class="d">{d_bord}</div><div class="go">{esc(suite)}</div></a>'
        f'<a class="ca" href="{href_vad}">'
        '<div class="ic">🏠</div><div class="t">Tableau de bord — Visite à domicile</div>'
        f'<div class="d">Suivi des visites à domicile (VAD){d_lieu} '
        '<b>Bientôt disponible</b> — données VAD à venir.</div>'
        f'<div class="go">{esc(suite)}</div></a>'
        f'<a class="ca" href="{href_equipe}">'
        '<div class="ic">👔</div><div class="t">Équipe technique</div>'
        f'<div class="d">{d_equipe}</div>'
        f'<div class="go">{"Ouvrir →" if fixe else esc(suite)}</div></a>')
    # Carte « Journal » — au même niveau que les autres choix. Libellé/description
    # selon le rôle : écriture (équipe technique) ou lecture (coordonnateurs).
    if role in _ROLES_JOURNAL_ECRITURE or role in _ROLES_JOURNAL_LECTURE:
        ecrit_j = role in _ROLES_JOURNAL_ECRITURE
        t_j = "Mon journal de bord" if ecrit_j else "Journaux des équipes"
        d_j = ("Consigner les activités que vous avez réalisées dans la journée."
               if ecrit_j else
               "Lire les journaux de bord des équipes de terrain (filtres par "
               "district, fonction, nom, date).")
        cartes += (
            '<a class="ca" href="/journal">'
            '<div class="ic">📓</div>'
            f'<div class="t">{esc(t_j)}</div>'
            f'<div class="d">{esc(d_j)}</div>'
            '<div class="go">Ouvrir →</div></a>')
    # Carte « Consignes & instructions » — rédaction, réservée aux Coordonnateurs.
    if role in _ROLES_CONSIGNE_ENVOI:
        cartes += (
            '<a class="ca" href="/consignes/nouvelle">'
            '<div class="ic">📣</div>'
            '<div class="t">Consignes &amp; instructions</div>'
            '<div class="d">Rédiger et envoyer une consigne à des rôles et des '
            'districts ciblés (ou à tout le monde).</div>'
            '<div class="go">Ouvrir →</div></a>')
    # Carte « Suivi des rapports journaliers » — réservée aux Coordonnateurs :
    # qui a écrit ou non son journal, par jour, par poste (et par axe).
    if role in _ROLES_CONSIGNE_ENVOI:
        cartes += (
            '<a class="ca" href="/journal/suivi">'
            '<div class="ic">🗓️</div>'
            '<div class="t">Suivi des rapports journaliers</div>'
            '<div class="d">Voir, pour chaque jour passé, si les équipes techniques '
            'ont écrit leur rapport (par poste, et par axe pour les Superviseurs / '
            'Logistiques Inter-Communales).</div>'
            '<div class="go">Ouvrir →</div></a>')
    # Carte « Rapport de mission » — compilation (hors-ligne) des journaux de bord
    # en un rapport structuré. Réservée aux rôles de LECTURE (Coordonnateurs + Admin).
    if role in _ROLES_JOURNAL_LECTURE:
        cartes += (
            '<a class="ca" href="/rapport-mission">'
            '<div class="ic">📄</div>'
            '<div class="t">Rapport de mission</div>'
            '<div class="d">Compiler les journaux de bord d\'une période en un '
            'rapport structuré (district / fonction / personne), imprimable.</div>'
            '<div class="go">Ouvrir →</div></a>')
    entete = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>RSU — {esc(role) or "Menu"}</title><style>{admin._STYLE}</style>'
        f'{equipes._CSS_CHOIX}</head><body>'
        f'<div class="bar"><b>🧭 {esc(role) or "Menu"}</b>'
        '<span class="sp"></span></div><div class="wrap">')
    return (entete
            + '<h1>Que souhaitez-vous faire&nbsp;?</h1>'
            + '<p style="color:#64748b;margin:2px 0 0;font-size:14px">'
              'Choisissez l’opération à effectuer.</p>'
            + f'<div class="choix">{cartes}</div>'
            + '</div></body></html>')


# ---------------------------------------------------------------------------
# Page de SÉLECTION (juste après la connexion) : zone géographique + limites
# + type de suivi. Listes déroulantes dépendantes Province -> Région -> District.
# Quand `op` est fourni (den/vad/equipe), l'opération est DÉJÀ choisie (menu) :
# les vignettes « type de suivi » sont remplacées par un champ caché + un lien
# retour au menu.
# ---------------------------------------------------------------------------
def page_selection(erreur: str = "", utilisateur=None, op=None) -> str:
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
        n_sui = "1"
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
        n_sui = "2"
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
        n_sui = "2"
    bloc_erreur = (
        f'<div class="message visible">{esc(erreur)}</div>'
        if erreur else '<div class="message"></div>')
    geo_json = json.dumps(ARBRE_GEO, ensure_ascii=False)

    # Bloc « opération » : soit l'opération est DÉJÀ choisie via le menu (op fourni)
    # -> champ caché + rappel + lien retour au menu du rôle ; soit on affiche les
    # vignettes « type de suivi » (rôles sans menu, ex. Comités Techniques).
    role_menu = _MENU_CHEMINS.get(
        (utilisateur or {}).get("responsabilite"), "/choix")
    op = (op or "").strip() or None
    _LIB_OP = {"den": "Tableau de bord (dénombrement)",
               "vad": "Visite à domicile", "equipe": "Équipe technique"}
    lien_menu = ""
    if op in _LIB_OP:
        bloc_suivi = (
            f'<input type="hidden" name="suivi" value="{esc(op)}">'
            '<fieldset><legend><span class="num">✓</span> Opération choisie</legend>'
            '<div class="opt" style="cursor:default;background:#eef5ff;'
            'border-color:#bcd3f7"><span><span class="t">'
            f'{esc(_LIB_OP[op])}</span><span class="d">Choisissez le district '
            'ci-dessus, puis continuez.</span></span></div></fieldset>')
        lien_menu = f'<a class="lien-haut" href="{esc(role_menu)}">← Menu</a>'
    else:
        # Choix « Équipe technique » ajouté aux vignettes pour les rôles concernés
        # (cas sans menu ; conservé pour compatibilité).
        role_courant = (utilisateur or {}).get("responsabilite")
        suivi_extra = ''
        if role_courant in _ROLES_MENU_OPERATION:
            suivi_extra = (
                '<label class="suivi">'
                '<input type="radio" name="suivi" value="equipe" required>'
                '<span class="ic"><svg width="22" height="22" viewBox="0 0 24 24" '
                'fill="none" stroke="currentColor" stroke-width="2">'
                '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
                '<circle cx="9" cy="7" r="4"/>'
                '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
                '<path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>'
                '<div class="t">Équipe technique</div>'
                '<div class="d">Encadrement affecté au district</div>'
                '</label>')
        bloc_suivi = (
            '<fieldset><legend><span class="num">' + n_sui + '</span> Type de '
            'suivi</legend><div class="suivis">'
            '<label class="suivi">'
            '<input type="radio" name="suivi" value="den" required>'
            '<span class="ic"><svg width="22" height="22" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11l9-8 9 8"/>'
            '<path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg></span>'
            '<div class="t">Dénombrement</div>'
            '<div class="d">Recensement des ménages</div></label>'
            '<label class="suivi">'
            '<input type="radio" name="suivi" value="vad" required>'
            '<span class="ic"><svg width="22" height="22" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/>'
            '<path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg></span>'
            '<div class="t">Visite à domicile</div>'
            '<div class="d">Interviews sur le terrain</div></label>'
            + suivi_extra + '</div></fieldset>')

    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Zone & type de suivi</title>
<style>
:root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px);}

  *{box-sizing:border-box}
  :root{--bleu:#1b6ef3;--bleu-f:#1558c9;--vert:#17a398;--nuit:#0d2b4e;--texte:#1c2430}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:var(--texte);margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1.375rem;
    line-height:1.5;background:#0d2b4e}
  .fond{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat;
    animation:zoomlent 22s ease-in-out infinite alternate}
  .voile{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.58) 0%,rgba(21,88,201,.42) 55%,rgba(23,163,152,.44) 130%)}

  .carte{position:relative;z-index:2;width:100%;max-width:40rem;
    background:rgba(255,255,255,.90);backdrop-filter:blur(0.875rem) saturate(120%);
    -webkit-backdrop-filter:blur(0.875rem) saturate(120%);border-radius:1.25rem;
    box-shadow:0 1.875rem 4.375rem rgba(0,0,0,.42);padding:2rem 2.125rem;
    animation:apparaitre .6s ease both;max-height:calc(100vh - 2.75rem);overflow:auto}
  .tete{display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem}
  .badge{width:2.875rem;height:2.875rem;border-radius:0.75rem;flex:none;color:#fff;font-weight:800;
    font-size:1rem;display:flex;align-items:center;justify-content:center;
    background:linear-gradient(135deg,var(--bleu),var(--bleu-f))}
  h1{font-size:1.3rem;margin:0}
  .st{color:#5a6675;font-size:.86rem;margin:0}
  .lien-haut{margin-left:auto;font-size:.82rem;color:#5a6675;text-decoration:none;
    border:1px solid #dce3ea;border-radius:0.5rem;padding:0.3125rem 0.6875rem;background:#fff}
  .lien-haut:hover{background:#f4f7fb}

  fieldset{border:none;padding:0;margin:1.375rem 0 0}
  legend{font-weight:700;font-size:.82rem;text-transform:uppercase;letter-spacing:.6px;
    color:#1558c9;padding:0;margin-bottom:0.625rem;display:flex;align-items:center;gap:0.5rem}
  .num{width:1.375rem;height:1.375rem;border-radius:50%;background:#e7f0ff;color:#1558c9;
    display:inline-flex;align-items:center;justify-content:center;font-size:.78rem;flex:none}
  .grille{display:grid;grid-template-columns:1fr 1fr;gap:0.75rem}
  label.champ-l{display:block;font-weight:600;font-size:.84rem;margin:0 0 0.3125rem}
  select,input[type=text]{width:100%;padding:0.6875rem 0.75rem;font-size:.98rem;color:var(--texte);
    background:#f7f9fc;border:1.5px solid #e1e7ef;border-radius:0.625rem;outline:none;transition:.15s}
  select:focus,input[type=text]:focus{border-color:var(--bleu);background:#fff;
    box-shadow:0 0 0 0.1875rem rgba(27,110,243,.14)}
  select:disabled{background:#eef1f5;color:#9aa6b3;cursor:not-allowed}
  .pleine{grid-column:1 / -1}

  .options{display:grid;gap:0.5625rem}
  .opt{display:flex;align-items:flex-start;gap:0.6875rem;border:1.5px solid #e1e7ef;border-radius:0.6875rem;
    padding:0.6875rem 0.8125rem;cursor:pointer;transition:.15s;background:#fbfcfe}
  .opt:hover{border-color:#bcd3f7;background:#f5f9ff}
  .opt input{margin-top:0.1875rem;accent-color:var(--bleu)}
  .opt:has(input:checked){border-color:var(--bleu);background:#eef5ff;
    box-shadow:0 0 0 0.1875rem rgba(27,110,243,.10)}
  .opt .t{font-weight:600;font-size:.93rem}
  .opt .d{font-size:.8rem;color:#6b7787}

  .suivis{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.75rem,1fr));gap:0.75rem}
  .suivi{position:relative;border:1.5px solid #e1e7ef;border-radius:0.875rem;padding:1rem 0.875rem;
    cursor:pointer;text-align:center;transition:.15s;background:#fbfcfe}
  .suivi:hover{border-color:#bcd3f7;background:#f5f9ff}
  .suivi input{position:absolute;opacity:0;pointer-events:none}
  .suivi:has(input:checked){border-color:var(--bleu);background:#eef5ff;
    box-shadow:0 0 0 0.1875rem rgba(27,110,243,.12)}
  .suivi .ic{width:2.75rem;height:2.75rem;margin:0 auto 0.5rem;border-radius:0.75rem;display:flex;
    align-items:center;justify-content:center;background:linear-gradient(135deg,#eaf2ff,#dfeeff);
    color:#1558c9}
  .suivi:has(input:checked) .ic{background:linear-gradient(135deg,var(--bleu),var(--bleu-f));
    color:#fff}
  .suivi .t{font-weight:700;font-size:.98rem}
  .suivi .d{font-size:.78rem;color:#6b7787;margin-top:2px}

  button.principal{width:100%;margin-top:1.625rem;padding:0.8125rem;font-size:1.02rem;font-weight:700;
    color:#fff;border:none;border-radius:0.6875rem;cursor:pointer;letter-spacing:.3px;
    background:linear-gradient(135deg,var(--bleu),var(--bleu-f));
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.30);transition:.18s}
  button.principal:hover{transform:translateY(-2px);box-shadow:0 0.875rem 1.75rem rgba(27,110,243,.38)}
  .message{display:none;margin-top:1rem;padding:0.6875rem 0.8125rem;border-radius:0.6875rem;font-size:.88rem;
    background:#fdecea;border:1px solid #f5c6c2;color:#c0392b}
  .message.visible{display:block}

  @keyframes apparaitre{from{opacity:0;transform:translateY(1rem)}to{opacity:1;transform:none}}
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
        <h1><!--TITRE--></h1>
        <p class="st"><!--SOUS_TITRE--></p>
      </div>
      <!--LIEN_MENU-->
    </div>

    <!--ZONE-->

    <!--BLOC_SUIVI-->

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
</script>
</body></html>"""
    if op in _LIB_OP:
        titre = "Choisir le district"
        sous_titre = f"Opération : {esc(_LIB_OP[op])}. Sélectionnez le district."
    else:
        titre = "Zone &amp; type de suivi"
        sous_titre = "Choisissez où et quoi suivre."
    return (page
            .replace("<!--ZONE-->", zone_html)
            .replace("<!--BLOC_SUIVI-->", bloc_suivi)
            .replace("<!--LIEN_MENU-->", lien_menu)
            .replace("<!--TITRE-->", titre)
            .replace("<!--SOUS_TITRE-->", sous_titre)
            .replace("/*GEO*/", geo_json)
            .replace("<!--ERREUR-->", bloc_erreur))


# ---------------------------------------------------------------------------
# Page RÉCAPITULATIF : confirme la sélection avant d'ouvrir le suivi.
# ---------------------------------------------------------------------------
def page_suivi(sel: dict) -> str:
    libelle_suivi = {"den": "Dénombrement", "vad": "Visite à domicile"}.get(
        sel.get("suivi"), "—")
    esc = htmllib.escape
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Suivi {esc(libelle_suivi)}</title>
<style>
  :root{{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px)}}

  body{{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1.375rem;
    line-height:1.55;background:#0d2b4e}}
  .fond{{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat}}
  .voile{{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.62),rgba(21,88,201,.44) 55%,rgba(23,163,152,.46))}}
  .carte{{position:relative;z-index:2;width:100%;max-width:35rem;background:rgba(255,255,255,.92);
    backdrop-filter:blur(0.875rem);-webkit-backdrop-filter:blur(0.875rem);border-radius:1.25rem;
    box-shadow:0 1.875rem 4.375rem rgba(0,0,0,.42);padding:1.875rem 2rem;animation:app .6s ease both}}
  .tete{{display:flex;align-items:center;gap:0.75rem;margin-bottom:0.875rem}}
  .badge{{width:2.875rem;height:2.875rem;border-radius:0.75rem;color:#fff;font-weight:800;flex:none;
    display:flex;align-items:center;justify-content:center;
    background:linear-gradient(135deg,#1b6ef3,#1558c9)}}
  h1{{font-size:1.28rem;margin:0}}
  .ruban{{display:inline-block;margin-top:2px;font-size:.78rem;font-weight:700;color:#0f9d84;
    background:#e6f7f2;border:1px solid #b8e6da;border-radius:62.4375rem;padding:2px 0.625rem}}
  dl{{margin:1.125rem 0 0;display:grid;grid-template-columns:auto 1fr;gap:0.625rem 1rem}}
  dt{{color:#5a6675;font-size:.82rem;font-weight:600;text-transform:uppercase;letter-spacing:.4px}}
  dd{{margin:0;font-weight:600}}
  .note{{margin-top:1.25rem;background:#eef6ff;border:1px solid #cfe2ff;border-radius:0.6875rem;
    padding:0.75rem 0.875rem;font-size:.86rem;color:#3a5a80}}
  .actions{{display:flex;gap:0.625rem;margin-top:1.375rem;flex-wrap:wrap}}
  .btn{{flex:1;min-width:9.375rem;text-align:center;padding:0.75rem;border-radius:0.6875rem;font-weight:700;
    text-decoration:none;cursor:pointer;border:1.5px solid #dce3ea;color:#1c2430;background:#fff}}
  .btn:hover{{background:#f4f7fb}}
  .btn.p{{color:#fff;border:none;background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.28)}}
  @keyframes app{{from{{opacity:0;transform:translateY(1rem)}}to{{opacity:1;transform:none}}}}
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
  :root{{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px)}}

  body{{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1.375rem;
    line-height:1.55;background:#0d2b4e}}
  .fond{{position:fixed;inset:0;z-index:0;background:url(/img/accueil) center/cover no-repeat}}
  .voile{{position:fixed;inset:0;z-index:0;background:linear-gradient(135deg,
    rgba(13,43,78,.66),rgba(21,88,201,.46) 55%,rgba(23,163,152,.48))}}
  .carte{{position:relative;z-index:2;width:100%;max-width:32.5rem;text-align:center;
    background:rgba(255,255,255,.93);backdrop-filter:blur(0.875rem);
    -webkit-backdrop-filter:blur(0.875rem);border-radius:1.25rem;
    box-shadow:0 1.875rem 4.375rem rgba(0,0,0,.42);padding:2.375rem 2.125rem;animation:app .6s ease both}}
  .ic{{width:4.75rem;height:4.75rem;margin:0 auto 1rem;border-radius:1.25rem;display:flex;
    align-items:center;justify-content:center;color:#b7791f;
    background:linear-gradient(135deg,#fff4d6,#ffe6a8)}}
  h1{{font-size:1.35rem;margin:0 0 0.375rem}}
  .ruban{{display:inline-block;font-size:.76rem;font-weight:700;color:#8a5a00;
    background:#fff4d6;border:1px solid #f0d38a;border-radius:62.4375rem;padding:2px 0.6875rem;
    margin-bottom:0.75rem}}
  p{{color:#41505f;margin:0.5rem 0}}
  .district{{font-weight:700;color:#1c2430}}
  .actions{{display:flex;gap:0.625rem;margin-top:1.5rem;justify-content:center;flex-wrap:wrap}}
  .btn{{padding:0.75rem 1.125rem;border-radius:0.6875rem;font-weight:700;text-decoration:none;
    border:1.5px solid #dce3ea;color:#1c2430;background:#fff}}
  .btn:hover{{background:#f4f7fb}}
  .btn.p{{color:#fff;border:none;background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.28)}}
  @keyframes app{{from{{opacity:0;transform:translateY(1rem)}}to{{opacity:1;transform:none}}}}
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


# ---------------------------------------------------------------------------
# Page « Équipe technique » : encadrement (comptes) affecté à un district.
# Accessible au Coordonnateur Nationale (choix de la sélection, district libre) et
# aux rôles bornés à un district (Traitement, Superviseur Technique, Expert survey
# — via /equipe, district = leur affectation). `retour_href`/`retour_label`
# adaptent le bouton de retour à la provenance.
# ---------------------------------------------------------------------------
def page_equipe_technique(sel: dict, equipes, retour_href="/",
                          retour_label="← Retour à la sélection") -> str:
    """Fiche des comptes d'encadrement affectés au district choisi.

    `equipes` = sortie de utilisateurs.equipe_technique_district :
    [(role, [comptes…]), …]. Servie par _html() (bandeau + no-store)."""
    esc = htmllib.escape
    district_nom = esc(str(sel.get("district_nom", "—")))
    code = esc(str(sel.get("code_district", "")))
    region = esc(str(sel.get("region_nom", "")))
    province = esc(str(sel.get("province_nom", "")))
    total = sum(len(gens) for _, gens in equipes)

    if not equipes:
        corps = ('<div class="vide">Aucun compte d\'encadrement '
                 '(Coordonnateur régional, Superviseur technique, Traitement ou '
                 'Expert survey) n\'est actuellement affecté à ce district.</div>')
    else:
        def carte(u):
            """HTML d'une carte-personne (encadrement)."""
            login = esc(u.get("login") or "")
            nom = esc((u.get("nom_prenom") or u.get("login") or "").strip())
            initiales = esc("".join(p[0] for p in
                                    (u.get("nom_prenom") or login).split()[:2]
                                    ).upper() or "?")
            # Contacts affichés : Téléphone, N° Orange (Float), E-mail (le CIN
            # n'est PAS montré ici — donnée d'identité, hors contacts).
            lignes = []
            if u.get("telephone"):
                lignes.append('<li><span>Téléphone</span>'
                              f'{esc(str(u["telephone"]))}</li>')
            if u.get("numero_orange_float"):
                lignes.append('<li><span>N° Orange (Float)</span>'
                              f'{esc(str(u["numero_orange_float"]))}</li>')
            if u.get("email"):
                lignes.append(f'<li><span>E-mail</span>{esc(str(u["email"]))}</li>')
            off = ('' if u.get("actif", True)
                   else '<span class="off">désactivé</span>')
            lignes_html = (f'<ul class="pd">{"".join(lignes)}</ul>'
                           if lignes else '')
            return (f'<div class="pers"><div class="ph">{initiales}</div>'
                    f'<div class="pi"><div class="pn">{nom}{off}</div>'
                    f'{lignes_html}</div></div>')

        blocs = []
        for role, gens in equipes:
            if role == "Superviseur Technique":
                # Présentation PAR AXE DE SUPERVISION : les Superviseurs Techniques
                # sont regroupés par zone d'affectation (leur jeu de communes). Chaque
                # axe est un sous-titre « Axe de supervision : Commune 1, Commune 2… »
                # suivi, en retrait, de la liste des superviseurs de cette zone.
                axes = {}
                for u in gens:
                    noms = u.get("communes_noms") or [
                        str(c) for c in (u.get("communes_affectation") or [])]
                    cle = tuple(noms)
                    axes.setdefault(cle, []).append(u)
                axes_html = []
                for noms in sorted(axes, key=lambda k: [n.lower() for n in k]):
                    membres = axes[noms]
                    libelle = ", ".join(esc(n) for n in noms) or "—"
                    cartes = "".join(carte(u) for u in membres)
                    axes_html.append(
                        f'<div class="axe"><div class="axe-t">'
                        f'<span class="axe-lbl">Axe de supervision :</span> {libelle}'
                        f'<span class="cnt">{len(membres)}</span></div>'
                        f'<div class="pers-grille axe-grille">{cartes}</div></div>')
                blocs.append(
                    f'<section class="role"><h2>{esc(role)}'
                    f'<span class="cnt">{len(gens)}</span></h2>'
                    f'{"".join(axes_html)}</section>')
            else:
                cartes = "".join(carte(u) for u in gens)
                blocs.append(
                    f'<section class="role"><h2>{esc(role)}'
                    f'<span class="cnt">{len(gens)}</span></h2>'
                    f'<div class="pers-grille">{cartes}</div></section>')
        corps = "".join(blocs)

    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Équipe technique</title>
<style>
:root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px);}

  *{box-sizing:border-box}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    background:#eef2f7;line-height:1.5;padding:4.875rem 1.25rem 3rem}
  .wrap{max-width:57.5rem;margin:0 auto}
  .entete{background:linear-gradient(135deg,#1b6ef3,#1558c9);color:#fff;
    border-radius:1.125rem;padding:1.5rem 1.625rem;box-shadow:0 0.875rem 2.125rem rgba(27,110,243,.28)}
  .entete .ruban{display:inline-block;font-size:.74rem;font-weight:700;
    background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.35);
    border-radius:62.4375rem;padding:2px 0.6875rem;margin-bottom:0.5rem}
  .entete h1{margin:0 0 0.25rem;font-size:1.5rem}
  .entete .meta{opacity:.92;font-size:.92rem}
  .entete .tot{margin-top:0.75rem;font-size:.86rem;opacity:.92}
  .role{background:#fff;border:1px solid #dce3ea;border-radius:1rem;
    padding:1.125rem 1.25rem;margin-top:1.125rem;box-shadow:0 0.5rem 1.375rem rgba(13,43,78,.07)}
  .role h2{display:flex;align-items:center;gap:0.625rem;font-size:1.06rem;margin:0 0 0.875rem;
    color:#12325c}
  .role h2 .cnt{font-size:.76rem;font-weight:700;color:#1558c9;background:#eaf1fd;
    border:1px solid #c7dbf7;border-radius:62.4375rem;padding:1px 0.5625rem}
  .axe{margin:0 0 0.875rem;padding:0 0 0 1rem;border-left:0.1875rem solid #c7dbf7}
  .axe:last-child{margin-bottom:0}
  .axe-t{display:flex;align-items:center;gap:0.5625rem;flex-wrap:wrap;font-size:.98rem;
    font-weight:700;color:#12325c;margin:2px 0 0.625rem}
  .axe-t .axe-lbl{color:#1558c9;font-weight:800}
  .axe-t .cnt{font-size:.72rem;font-weight:700;color:#1558c9;background:#eaf1fd;
    border:1px solid #c7dbf7;border-radius:62.4375rem;padding:1px 0.5rem}
  .pers-grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(15.625rem,1fr));
    gap:0.75rem}
  .pers{display:flex;gap:0.75rem;border:1px solid #e6ebf2;border-radius:0.75rem;
    padding:0.75rem 0.8125rem;background:#fafbfd}
  .ph{width:2.5rem;height:2.5rem;flex:none;border-radius:50%;color:#fff;font-weight:800;
    font-size:.82rem;display:flex;align-items:center;justify-content:center;
    background:linear-gradient(135deg,#1b6ef3,#1558c9)}
  .pi{min-width:0}
  .pn{font-weight:700;font-size:.95rem}
  .pn .off{font-size:.7rem;font-weight:700;color:#9a3b32;background:#fdecea;
    border:1px solid #f0cfca;border-radius:62.4375rem;padding:0 0.4375rem;margin-left:0.375rem}
  .pl{color:#7a8698;font-size:.78rem;margin-bottom:0.375rem;font-family:ui-monospace,monospace}
  .pd{list-style:none;margin:0.375rem 0 0;padding:0;font-size:.82rem;color:#41505f}
  .pd li{display:flex;gap:0.375rem;margin:2px 0}
  .pd li span{color:#8a97a7;flex:none;min-width:4.625rem}
  .vide{background:#fff;border:1px dashed #c7d2df;border-radius:1rem;padding:1.75rem;
    text-align:center;color:#5a6675;margin-top:1.125rem}
  .actions{display:flex;gap:0.625rem;margin-top:1.375rem;flex-wrap:wrap}
  .btn{padding:0.6875rem 1.0625rem;border-radius:0.6875rem;font-weight:700;text-decoration:none;
    border:1.5px solid #dce3ea;color:#1c2430;background:#fff}
  .btn:hover{background:#f4f7fb}
  .btn.p{color:#fff;border:none;background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.26)}
  @media print{body{background:#fff;padding:0}.actions{display:none}
    .entete{box-shadow:none}.role{box-shadow:none;break-inside:avoid}}
</style></head><body><div class="wrap">
  <div class="entete">
    <span class="ruban">Équipe technique du district</span>
    <h1><!--DISTRICT--></h1>
    <div class="meta">Province <!--PROV--> · Région <!--REG--> · Code district <!--CODE--></div>
    <div class="tot"><!--TOT--> personne(s) d'encadrement affectée(s) à ce district.</div>
  </div>
  <!--CORPS-->
  <div class="actions">
    <a class="btn p" href="<!--RETOUR_HREF-->"><!--RETOUR_LABEL--></a>
  </div>
</div></body></html>"""
    return (page
            .replace("<!--DISTRICT-->", district_nom)
            .replace("<!--PROV-->", province or "—")
            .replace("<!--REG-->", region or "—")
            .replace("<!--CODE-->", code or "—")
            .replace("<!--TOT-->", str(total))
            .replace("<!--RETOUR_HREF-->", esc(retour_href))
            .replace("<!--RETOUR_LABEL-->", esc(retour_label))
            .replace("<!--CORPS-->", corps))


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


# ---------------------------------------------------------------------------
# Changer SON PROPRE mot de passe (self-service, tous les rôles connectés).
# ---------------------------------------------------------------------------
MDP_MIN = 6  # longueur minimale d'un nouveau mot de passe


def page_motdepasse(erreur: str = "", succes: bool = False, sess=None) -> str:
    """Page « Modifier mon mot de passe » pour l'utilisateur connecté.

    Servie par _html() (bandeau + no-store injectés). Le formulaire poste vers
    /motdepasse (préfixé par _prefixer). Sur succès, le formulaire est masqué au
    profit d'un message de confirmation."""
    u = (sess or {}).get("utilisateur") or {}
    role = (u.get("responsabilite") or "").strip()
    nom = htmllib.escape((u.get("nom_prenom") or (sess or {}).get("login") or "").strip())
    retour = accueil_role(role)  # préfixé par _prefixer (href commence par « / »)

    if succes:
        bloc = ('<div class="mdp-msg ok">Votre mot de passe a bien été modifié. '
                'Il vous sera demandé à la prochaine connexion.</div>')
        corps = (f'{bloc}<a class="mdp-retour" href="{htmllib.escape(retour)}">'
                 'Retour à mon espace</a>')
    else:
        bloc = (f'<div class="mdp-msg err">{htmllib.escape(erreur)}</div>'
                if erreur else '')
        corps = (
            f'{bloc}'
            '<form method="post" action="/motdepasse" autocomplete="off">'
            '<label for="ancien">Mot de passe actuel</label>'
            '<input type="password" id="ancien" name="ancien" required '
            'autocomplete="current-password">'
            '<label for="nouveau">Nouveau mot de passe</label>'
            '<input type="password" id="nouveau" name="nouveau" required '
            f'minlength="{MDP_MIN}" autocomplete="new-password">'
            f'<p class="mdp-aide">Au moins {MDP_MIN} caractères.</p>'
            '<label for="confirme">Confirmer le nouveau mot de passe</label>'
            '<input type="password" id="confirme" name="confirme" required '
            f'minlength="{MDP_MIN}" autocomplete="new-password">'
            '<button type="submit" class="mdp-btn">Enregistrer</button>'
            f'<a class="mdp-retour" href="{htmllib.escape(retour)}">Annuler</a>'
            '</form>')

    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Mon mot de passe</title>
<style>
:root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px);}

  *{box-sizing:border-box}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    min-height:100vh;display:flex;align-items:flex-start;justify-content:center;
    padding:5.5rem 1.375rem 2.5rem;background:#eef2f7;line-height:1.5}
  .mdp-carte{width:100%;max-width:27.5rem;background:#fff;border:1px solid #dce3ea;
    border-radius:1rem;padding:1.875rem 1.875rem 2.125rem;box-shadow:0 0.75rem 2.125rem rgba(13,43,78,.12)}
  .mdp-carte h1{font-size:1.3rem;margin:0 0 0.25rem}
  .mdp-sous{color:#5a6675;margin:0 0 1.375rem;font-size:.92rem}
  label{display:block;font-weight:600;font-size:.86rem;margin:0.875rem 0 0.375rem}
  input{width:100%;padding:0.75rem 0.875rem;font-size:1rem;color:#1c2430;background:#f7f9fc;
    border:1.5px solid #e1e7ef;border-radius:0.6875rem;outline:none;transition:.18s}
  input:focus{border-color:#1b6ef3;background:#fff;box-shadow:0 0 0 0.25rem rgba(27,110,243,.14)}
  .mdp-aide{color:#7a8698;font-size:.78rem;margin:0.375rem 2px 0}
  .mdp-btn{width:100%;margin-top:1.375rem;padding:0.8125rem;font-size:1.02rem;font-weight:700;
    color:#fff;border:none;border-radius:0.6875rem;cursor:pointer;
    background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.30);transition:.18s}
  .mdp-btn:hover{transform:translateY(-2px);box-shadow:0 0.875rem 1.75rem rgba(27,110,243,.38)}
  .mdp-retour{display:block;text-align:center;margin-top:1rem;color:#1558c9;
    text-decoration:none;font-weight:600;font-size:.9rem}
  .mdp-retour:hover{text-decoration:underline}
  .mdp-msg{padding:0.6875rem 0.8125rem;border-radius:0.6875rem;font-size:.9rem;margin-bottom:0.375rem}
  .mdp-msg.err{background:#fdecea;border:1px solid #f0cfca;color:#c0392b}
  .mdp-msg.ok{background:#e8f7f0;border:1px solid #b8e6d2;color:#127a52}
</style></head>
<body><div class="mdp-carte">
<h1>Modifier mon mot de passe</h1>
<p class="mdp-sous">Compte : <!--NOM--></p>
<!--CORPS-->
</div></body></html>"""
    return page.replace("<!--NOM-->", nom or "—").replace("<!--CORPS-->", corps)


# ---------------------------------------------------------------------------
# « Mon profil » : chaque utilisateur modifie SES informations personnelles
# (CIN, téléphone, N° Orange/Float, e-mail, sexe). Le reste (login, nom, rôle,
# affectation/axe) est en LECTURE SEULE ici — modifiable uniquement par l'Admin.
# ---------------------------------------------------------------------------
def page_profil(u, aff_txt, message: str = "", erreur: str = "") -> str:
    """Page libre-service d'édition du profil. `u` = dict `utilisateurs.obtenir`,
    `aff_txt` = affectation en clair (lecture seule)."""
    esc = htmllib.escape
    v = lambda k: esc(u.get(k) or "")
    role = (u.get("responsabilite") or "").strip()
    retour = accueil_role(role)
    bloc = ""
    if message:
        bloc = f'<div class="jr-msg ok">{esc(message)}</div>'
    elif erreur:
        bloc = f'<div class="jr-msg err">{esc(erreur)}</div>'
    sexe_cur = (u.get("sexe") or "").strip()
    opts_sexe = '<option value="">—</option>' + "".join(
        f'<option value="{s}"{" selected" if s == sexe_cur else ""}>{s}</option>'
        for s in utilisateurs.SEXES)
    champ_style = ('width:100%;padding:11px 13px;font-size:1rem;background:#f7f9fc;'
                   'border:1.5px solid #e1e7ef;border-radius:11px')
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Mon profil</title>'
        f'<style>{_STYLE_JOURNAL}</style></head><body><div class="jr-wrap">'
        '<div class="jr-carte">'
        '<h1>👤 Mon profil</h1>'
        '<p class="jr-sous">Vous pouvez modifier vos informations personnelles '
        'ci-dessous. Les autres informations (login, nom, rôle, zone d’affectation) '
        'ne sont modifiables que par l’administrateur.</p>'
        f'{bloc}'
        '<div class="jr-meta">'
        f'<span><b>Login :</b> {v("login") or "—"}</span>'
        f'<span><b>Nom et Prénom :</b> {v("nom_prenom") or "—"}</span>'
        f'<span><b>Fonction / Poste :</b> {esc(role) or "—"}</span>'
        f'<span><b>Zone / Axe :</b> {esc(aff_txt) or "—"}</span></div>'
        '<form method="post" action="/profil">'
        '<label for="sexe">Sexe</label>'
        f'<select id="sexe" name="sexe" style="{champ_style}">{opts_sexe}</select>'
        '<label for="telephone">Téléphone</label>'
        f'<input type="text" id="telephone" name="telephone" inputmode="tel" '
        f'value="{v("telephone")}" placeholder="0340000000" style="{champ_style}">'
        '<label for="cin">CIN (12 chiffres)</label>'
        f'<input type="text" id="cin" name="cin" inputmode="numeric" '
        f'value="{v("cin")}" placeholder="101012345678" style="{champ_style}">'
        '<label for="email">Adresse e-mail</label>'
        f'<input type="email" id="email" name="email" '
        f'value="{v("email")}" placeholder="nom@example.mg" style="{champ_style}">'
        '<label for="numero_orange_float">N° Orange (Float)</label>'
        f'<input type="text" id="numero_orange_float" name="numero_orange_float" '
        f'inputmode="tel" value="{v("numero_orange_float")}" placeholder="0320000000" '
        f'style="{champ_style}">'
        '<div><button type="submit" class="jr-btn">Enregistrer mes informations'
        '</button></div></form>'
        f'<a class="jr-retour" href="{esc(retour)}">← Retour à mon espace</a>'
        '</div></div></body></html>')


# ---------------------------------------------------------------------------
# Journal de bord (activités quotidiennes) — pages ÉCRITURE / LECTURE.
# ---------------------------------------------------------------------------
def _journal_zone(conn, u):
    """(libellé de la zone/axe, codes de districts séparés par des virgules) pour
    un utilisateur, déduits de son affectation (perimetre) — jamais d'une saisie.

    Alimente les colonnes `zone` et `code_district` du journal : la zone est un
    texte lisible (axe de supervision = communes, ou district(s)), les codes
    servent au filtrage de LECTURE par district (Coordonnateur régional)."""
    districts, communes = perimetre(u)
    codes = ",".join(str(c) for c in sorted(districts)) if districts else ""
    if communes:
        noms = [zones.libelle_commune(conn, c) or str(c) for c in sorted(communes)]
        return ("Axe de supervision : " + ", ".join(noms), codes)
    if districts:
        libs = []
        for c in sorted(districts):
            lib = zones.libelles_district(conn, c)
            libs.append(lib[2] if lib else str(c))
        mot = "District" if len(libs) == 1 else "Districts"
        return (f"{mot} : " + ", ".join(libs), codes)
    return ("Niveau national", codes)


_STYLE_JOURNAL = """
:root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px);}
  *{box-sizing:border-box}
  body{font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430;margin:0;
    min-height:100vh;background:#eef2f7;line-height:1.5;padding:5.25rem 1.25rem 3rem}
  .jr-wrap{max-width:51.25rem;margin:0 auto}
  .jr-carte{background:#fff;border:1px solid #dce3ea;border-radius:1rem;
    padding:1.625rem 1.75rem 1.875rem;box-shadow:0 0.75rem 2.125rem rgba(13,43,78,.10);margin-bottom:1.375rem}
  .jr-carte h1{font-size:1.32rem;margin:0 0 0.25rem}
  .jr-sous{color:#5a6675;margin:0 0 1.125rem;font-size:.92rem}
  .jr-meta{display:flex;flex-wrap:wrap;gap:0.5rem 1.125rem;margin:0 0 1.125rem;font-size:.88rem}
  .jr-meta b{color:#5a6675;font-weight:600}
  label{display:block;font-weight:600;font-size:.86rem;margin:0.875rem 0 0.375rem}
  input[type=date],select{padding:0.6875rem 0.8125rem;font-size:1rem;color:#1c2430;background:#f7f9fc;
    border:1.5px solid #e1e7ef;border-radius:0.6875rem;outline:none}
  textarea{width:100%;min-height:9.375rem;padding:0.8125rem 0.875rem;font-size:1rem;color:#1c2430;
    background:#f7f9fc;border:1.5px solid #e1e7ef;border-radius:0.6875rem;outline:none;
    resize:vertical;font-family:inherit;line-height:1.5}
  input:focus,textarea:focus,select:focus{border-color:#1b6ef3;background:#fff;
    box-shadow:0 0 0 0.25rem rgba(27,110,243,.14)}
  .jr-btn{margin-top:1.125rem;padding:0.75rem 1.375rem;font-size:1rem;font-weight:700;color:#fff;
    border:none;border-radius:0.6875rem;cursor:pointer;
    background:linear-gradient(135deg,#1b6ef3,#1558c9);
    box-shadow:0 0.625rem 1.375rem rgba(27,110,243,.28);transition:.18s}
  .jr-btn:hover{transform:translateY(-2px);box-shadow:0 0.875rem 1.75rem rgba(27,110,243,.36)}
  .jr-retour{display:inline-block;margin-top:0.375rem;color:#1558c9;text-decoration:none;
    font-weight:600;font-size:.9rem}
  .jr-retour:hover{text-decoration:underline}
  .jr-msg{padding:0.6875rem 0.8125rem;border-radius:0.6875rem;font-size:.9rem;margin:0 0 1rem}
  .jr-msg.ok{background:#e8f7f0;border:1px solid #b8e6d2;color:#127a52}
  .jr-msg.err{background:#fdecea;border:1px solid #f0cfca;color:#c0392b}
  .jr-h2{font-size:1.05rem;margin:0 0 0.75rem}
  .jr-vide{color:#7a8698;font-style:italic}
  .jr-e{border:1px solid #e5ebf2;border-radius:0.75rem;padding:0.8125rem 0.9375rem;margin-bottom:0.625rem;
    background:#fbfcfe}
  .jr-e-h{display:flex;flex-wrap:wrap;gap:0.375rem 0.875rem;align-items:baseline;margin-bottom:0.375rem}
  .jr-date{font-weight:700;color:#1558c9}
  .jr-qui{font-weight:700}
  .jr-tag{font-size:.78rem;color:#5a6675;background:#eef2f7;border-radius:62.4375rem;
    padding:2px 0.625rem}
  .jr-txt{white-space:pre-wrap;margin:0;color:#26303c}
  .jr-mod{margin-left:auto;border:1px solid #c7dbf7;background:#eaf1fd;color:#1558c9;
    font-weight:600;font-size:.78rem;border-radius:0.5rem;padding:0.25rem 0.625rem;
    text-decoration:none;transition:.15s;white-space:nowrap}
  .jr-mod:hover{background:#1558c9;color:#fff;border-color:#1558c9}
  .jr-form-en-ligne{display:flex;flex-wrap:wrap;gap:0.75rem;align-items:flex-end}
  .jr-form-en-ligne label{margin:0 0 0.375rem}
  .jr-filtres{display:grid;grid-template-columns:repeat(auto-fit,minmax(11.25rem,1fr));
    gap:0.75rem 0.875rem;align-items:end}
  .jr-filtres label{margin:0 0 0.3125rem}
  .jr-filtres select,.jr-filtres input[type=date],.jr-filtres input[type=text]{
    width:100%;padding:0.625rem 0.75rem;font-size:.95rem;color:#1c2430;background:#f7f9fc;
    border:1.5px solid #e1e7ef;border-radius:0.625rem;outline:none}
  .jr-filtres select:disabled{background:#eef1f5;color:#9aa6b3}
  .jr-actions{display:flex;gap:0.625rem;align-items:center;margin-top:1rem;flex-wrap:wrap}
  .jr-btn.sm{margin-top:0;padding:0.625rem 1.125rem}
"""


def _journal_entree_html(e) -> str:
    """HTML d'UNE entrée de journal (liste), avec date/zone, « écrit le », « modifié
    le » (si modifiée) et un bouton **✏️ Modifier** (vers /journal/modifier?id=)."""
    esc = htmllib.escape
    mod = (f'<span class="jr-tag">modifié le {esc(e.get("modifie_court") or "")}</span>'
           if e.get("modifie_le") else '')
    return (
        '<div class="jr-e"><div class="jr-e-h">'
        f'<span class="jr-date">{esc(e["date_court"])}</span>'
        f'<span class="jr-tag">{esc(e.get("zone") or "")}</span>'
        f'<span class="jr-tag">écrit le {esc(e["cree_court"])}</span>'
        f'{mod}'
        f'<a class="jr-mod" href="/journal/modifier?id={esc(e.get("id") or "")}">'
        '✏️ Modifier</a></div>'
        f'<p class="jr-txt">{esc(e["journal"] or "")}</p></div>')


def page_journal_modifier(u, entree, erreur: str = "") -> str:
    """Formulaire de MODIFICATION d'une entrée de journal (son auteur). Date du jour
    + texte modifiables ; date initiale (`cree_le`) affichée FIGÉE, dernière
    modification affichée si présente."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    champ_style = ('width:100%;padding:11px 13px;font-size:1rem;background:#f7f9fc;'
                   'border:1.5px solid #e1e7ef;border-radius:11px')
    bloc = f'<div class="jr-msg err">{esc(erreur)}</div>' if erreur else ''
    maj = (f'<span><b>Dernière modification :</b> {esc(entree.get("modifie_court"))}'
           '</span>' if entree.get("modifie_le") else '')
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Modifier mon journal</title>'
        f'<style>{_STYLE_JOURNAL}</style></head><body><div class="jr-wrap">'
        '<div class="jr-carte">'
        '<h1>✏️ Modifier une entrée de mon journal</h1>'
        '<p class="jr-sous">Vous pouvez corriger la date et le contenu. La date de '
        'création initiale reste inchangée.</p>'
        f'{bloc}'
        '<div class="jr-meta">'
        f'<span><b>Axe / Zone :</b> {esc(entree.get("zone") or "—")}</span>'
        f'<span><b>Créé le :</b> {esc(entree.get("cree_court"))}</span>'
        f'{maj}</div>'
        '<form method="post" action="/journal/modifier">'
        f'<input type="hidden" name="id" value="{esc(entree.get("id") or "")}">'
        '<label for="date_jour">Date</label>'
        f'<input type="date" id="date_jour" name="date_jour" '
        f'value="{esc(entree.get("date_jour") or "")}" '
        f'max="{esc(journal.aujourdhui())}" required style="{champ_style}">'
        '<label for="journal">Activités de la journée</label>'
        f'<textarea id="journal" name="journal" required>{esc(entree.get("journal") or "")}'
        '</textarea>'
        '<div class="jr-actions"><button type="submit" class="jr-btn">'
        'Enregistrer les modifications</button>'
        '<a class="jr-retour" href="/journal" style="margin-top:0">Annuler</a></div>'
        '</form></div></div></body></html>')


def page_journal_ecrire(u, zone, code_district, date_defaut, mes_entrees,
                        message: str = "", erreur: str = "") -> str:
    """Page « Mon journal de bord » (rôles d'écriture) : formulaire d'entrée du
    jour (nom/fonction/zone pré-remplis, non saisis) + mes dernières entrées."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    nom = (u.get("nom_prenom") or u.get("login") or "").strip()
    retour = accueil_role(role)
    bloc_msg = ""
    if message:
        bloc_msg = f'<div class="jr-msg ok">{esc(message)}</div>'
    elif erreur:
        bloc_msg = f'<div class="jr-msg err">{esc(erreur)}</div>'

    if mes_entrees:
        lignes = "".join(_journal_entree_html(e) for e in mes_entrees)
    else:
        lignes = ('<p class="jr-vide">Aucune entrée pour l’instant. '
                  'Commencez par décrire vos activités du jour ci-dessus.</p>')

    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Mon journal de bord</title>'
        f'<style>{_STYLE_JOURNAL}</style></head><body><div class="jr-wrap">'
        '<div class="jr-carte">'
        '<h1>📓 Mon journal de bord</h1>'
        '<p class="jr-sous">Consignez ici, <b>chaque jour</b>, les activités '
        'réalisées dans la journée.</p>'
        f'{bloc_msg}'
        '<div class="jr-meta">'
        f'<span><b>Nom et Prénom :</b> {esc(nom or "—")}</span>'
        f'<span><b>Fonction / Poste :</b> {esc(role or "—")}</span>'
        f'<span><b>Axe / Zone :</b> {esc(zone or "—")}</span></div>'
        '<form method="post" action="/journal">'
        '<div class="jr-form-en-ligne"><div>'
        '<label for="date_jour">Date</label>'
        f'<input type="date" id="date_jour" name="date_jour" '
        f'value="{esc(date_defaut)}" max="{esc(date_defaut)}" required></div></div>'
        '<label for="journal">Activités de la journée</label>'
        '<textarea id="journal" name="journal" required '
        'placeholder="Décrivez les activités réalisées aujourd’hui…"></textarea>'
        '<div><button type="submit" class="jr-btn">Enregistrer dans mon journal'
        '</button></div></form></div>'
        '<div class="jr-carte">'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;'
        'flex-wrap:wrap;gap:8px">'
        '<h2 class="jr-h2" style="margin:0">Mes dernières entrées</h2>'
        '<a class="jr-retour" href="/journal/historique" style="margin:0">'
        'Voir tout mon journal →</a></div>'
        f'{lignes}'
        f'<a class="jr-retour" href="{esc(retour)}">← Retour à mon espace</a>'
        '</div></div></body></html>')


def page_journal_historique(u, entrees, date_filtre, total) -> str:
    """Page « Historique de mon journal » (rôles d'écriture) : TOUTES les entrées
    que l'utilisateur a écrites (filtrables par date). `total` = nombre total
    (sans filtre) pour l'en-tête."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    nom = (u.get("nom_prenom") or u.get("login") or "").strip()
    if entrees:
        lignes = "".join(_journal_entree_html(e) for e in entrees)
        pied = f'<p class="jr-sous">{len(entrees)} entrée(s) affichée(s).</p>'
    else:
        lignes = ('<p class="jr-vide">Aucune entrée ne correspond à cette date.</p>'
                  if date_filtre else
                  '<p class="jr-vide">Vous n’avez encore écrit aucune entrée.</p>')
        pied = ''
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Historique de mon journal</title>'
        f'<style>{_STYLE_JOURNAL}</style></head><body><div class="jr-wrap">'
        '<div class="jr-carte">'
        '<h1>📚 Historique de mon journal</h1>'
        f'<p class="jr-sous">Toutes les entrées écrites par {esc(nom or "vous")} — '
        f'<b>{total}</b> au total.</p>'
        '<form method="get" action="/journal/historique" class="jr-form-en-ligne">'
        '<div><label for="date">Filtrer par date</label>'
        f'<input type="date" id="date" name="date" value="{esc(date_filtre or "")}">'
        '</div><div><button type="submit" class="jr-btn" style="margin-top:0">'
        'Filtrer</button></div>'
        + ('<div><a class="jr-retour" href="/journal/historique">Tout afficher</a>'
           '</div>' if date_filtre else '')
        + '</form></div>'
        '<div class="jr-carte">'
        f'{pied}{lignes}'
        '<a class="jr-retour" href="/journal">← Retour à mon journal</a>'
        '</div></div></body></html>')


_STYLE_SUIVI = """
  .sv-leg{display:flex;gap:1rem;flex-wrap:wrap;font-size:.85rem;margin:0 0 0.875rem}
  .sv-leg span{display:inline-flex;align-items:center;gap:0.375rem}
  .sv-pastille{width:1rem;height:1rem;border-radius:0.25rem;display:inline-block}
  .sv-wrap{overflow-x:auto;border:1px solid #e5ebf2;border-radius:0.75rem}
  table.sv{border-collapse:collapse;font-size:.8rem;min-width:100%}
  table.sv th,table.sv td{border:1px solid #e9eef4;padding:0.3125rem 0.4375rem;text-align:center;
    white-space:nowrap}
  table.sv th{background:#f4f7fb;color:#33415a;font-weight:700;position:sticky;top:0}
  table.sv th.nom,table.sv td.nom{text-align:left;position:sticky;left:0;z-index:2;
    background:#fff;font-weight:600;min-width:11.875rem;box-shadow:1px 0 0 #e5ebf2}
  table.sv th.nom{background:#f4f7fb;z-index:3}
  table.sv td.ok{background:#e8f7f0;color:#127a52;font-weight:800}
  table.sv td.no{background:#fdecea;color:#c0392b}
  table.sv td.tot{font-weight:800;background:#f7f9fc}
  table.sv tr.grp td{background:#e7f0ff;font-weight:800;text-align:left;color:#1558c9;
    position:sticky;left:0}
  table.sv tr.dist td{background:#eef7f2;font-weight:700;text-align:left;color:#127a52;
    position:sticky;left:0}
  table.sv tr.axe td{background:#f7f9fc;font-style:italic;text-align:left;color:#5a6675}
"""


def page_journal_suivi(u, groupes, dates, dates_par_login, portee,
                       retour_choix=None) -> str:
    """Suivi de complétude du journal (Coordonnateurs + Admin) : tableau
    membres × dates (✓ écrit / ✗ non), groupé par poste — et par DISTRICT puis AXE
    pour les Superviseurs Techniques / Logistiques Inter-Communales.
    `groupes` = [(poste, mode, data)] : mode "flat" -> data=[membres] ;
    mode "district" -> data=[(district_nom, [(axe, [membres])])].
    `retour_choix` (National/Admin) = lien pour changer de district."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    retour = accueil_role(role)
    ndates = len(dates)
    ncols = ndates + 2                       # nom + dates + total
    dates_set = set(dates)

    def _court(d):                            # 'YYYY-MM-DD' -> 'JJ/MM'
        return f"{d[8:10]}/{d[5:7]}" if len(d) >= 10 else d

    def _ligne_membre(m):
        nom = esc((m.get("nom_prenom") or m.get("login") or "").strip())
        ecrites = dates_par_login.get(m["login"], set())
        cells = "".join(
            (f'<td class="ok" title="{esc(journal.fmt_jour(d))}">✓</td>' if d in ecrites
             else f'<td class="no" title="{esc(journal.fmt_jour(d))}">✗</td>')
            for d in dates)
        n = len(ecrites & dates_set)
        return f'<tr><td class="nom">{nom}</td>{cells}<td class="tot">{n}/{ndates}</td></tr>'

    if not dates or not groupes:
        corps = ('<p class="jr-vide">Aucun rapport journalier n’a encore été écrit '
                 'par les équipes de ce périmètre.</p>')
    else:
        entete = ('<tr><th class="nom">Membre</th>'
                  + "".join(f'<th title="{esc(journal.fmt_jour(d))}">{esc(_court(d))}</th>'
                            for d in dates)
                  + '<th>Total</th></tr>')
        lignes = []
        for poste, mode, data in groupes:
            lignes.append(f'<tr class="grp"><td colspan="{ncols}">📋 {esc(poste)}</td></tr>')
            if mode == "district":
                for district_nom, axes in data:
                    lignes.append('<tr class="dist"><td colspan="'
                                  f'{ncols}">🏙️ District : {esc(district_nom)}</td></tr>')
                    for axe, membres in axes:
                        lignes.append('<tr class="axe"><td colspan="'
                                      f'{ncols}">Axe : {esc(axe)}</td></tr>')
                        lignes += [_ligne_membre(m) for m in membres]
            else:                              # flat
                lignes += [_ligne_membre(m) for m in data]
        corps = ('<div class="sv-leg">'
                 '<span><i class="sv-pastille" style="background:#e8f7f0;'
                 'border:1px solid #b8e6d2"></i> ✓ a écrit son journal ce jour</span>'
                 '<span><i class="sv-pastille" style="background:#fdecea;'
                 'border:1px solid #f0cfca"></i> ✗ n’a pas écrit</span></div>'
                 '<div class="sv-wrap"><table class="sv">'
                 f'<thead>{entete}</thead><tbody>{"".join(lignes)}</tbody>'
                 '</table></div>')

    lien_changer = (f'<a class="jr-retour" href="{esc(retour_choix)}" '
                    'style="margin-right:16px">↩ Changer de district</a>'
                    if retour_choix else '')
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Suivi des rapports journaliers</title>'
        f'<style>{_STYLE_JOURNAL}{_STYLE_SUIVI}</style></head>'
        '<body><div class="jr-wrap" style="max-width:1200px"><div class="jr-carte">'
        '<h1>🗓️ Suivi des rapports journaliers</h1>'
        f'<p class="jr-sous">{esc(portee)} — par poste (par district puis axe pour les '
        'Superviseurs Techniques et Logistiques Inter-Communales). '
        f'{ndates} date(s) suivie(s).</p>'
        f'{corps}'
        f'<div style="margin-top:6px">{lien_changer}'
        f'<a class="jr-retour" href="{esc(retour)}">← Retour à mon espace</a></div>'
        '</div></div></body></html>')


def page_journal_suivi_choix(u) -> str:
    """Sélection d'un district (cascade Province→Région→District) avant d'afficher
    le suivi — pour le Coordonnateur National / Admin (zone entière)."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    options_prov = "".join(
        f'<option value="{p["c"]}">{esc(str(p["n"]))}</option>'
        for p in ARBRE_GEO.get("provinces", []))
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Suivi : choisir un district</title>'
        f'<style>{_STYLE_JOURNAL}{_STYLE_SUIVI}</style></head>'
        '<body><div class="jr-wrap"><div class="jr-carte">'
        '<h1>🗓️ Suivi des rapports journaliers</h1>'
        '<p class="jr-sous">Vous gérez plusieurs districts : choisissez d’abord le '
        '<b>district</b> dont vous voulez voir le suivi.</p>'
        '<form method="get" action="/journal/suivi" class="jr-filtres">'
        '<div><label for="province">Province</label>'
        '<select id="province" name="province" required>'
        '<option value="" selected disabled>— Choisir —</option>'
        + options_prov + '</select></div>'
        '<div><label for="region">Région</label>'
        '<select id="region" name="region" required disabled>'
        '<option value="" selected disabled>—</option></select></div>'
        '<div><label for="district">District</label>'
        '<select id="district" name="district" required disabled>'
        '<option value="" selected disabled>—</option></select></div>'
        '<div style="align-self:end"><button type="submit" class="jr-btn" '
        'style="margin-top:0">Afficher le suivi</button></div>'
        '</form>'
        f'<a class="jr-retour" href="{esc(accueil_role(role))}">'
        '← Retour à mon espace</a>'
        '</div></div>'
        '<script>const GEO=' + json.dumps(ARBRE_GEO, ensure_ascii=False) + ';'
        'var sp=document.getElementById("province"),'
        'sr=document.getElementById("region"),sd=document.getElementById("district");'
        'function vd(s,t){s.innerHTML=' + "'<option value=\"\" selected disabled>'+t+'</option>'"
        + ';}'
        'function rp(s,l,t){vd(s,t);(l||[]).forEach(function(o){'
        'var e=document.createElement("option");e.value=o.c;e.textContent=o.n;'
        's.appendChild(e);});s.disabled=!(l&&l.length);}'
        'sp.addEventListener("change",function(){'
        'rp(sr,GEO.regions[sp.value],"— Choisir —");vd(sd,"—");sd.disabled=true;});'
        'sr.addEventListener("change",function(){'
        'rp(sd,GEO.districts[sr.value],"— Choisir —");});'
        '</script></body></html>')


def _geo_reverse():
    """Cartes inverses du référentiel géographique (ARBRE_GEO), codes en str :
    (district -> région, région -> province). Pour pré-remplir la cascade du
    filtre district quand un district est déjà sélectionné."""
    dist2reg, reg2prov = {}, {}
    for reg_code, dists in ARBRE_GEO.get("districts", {}).items():
        for d in dists:
            dist2reg[str(d["c"])] = str(reg_code)
    for prov_code, regs in ARBRE_GEO.get("regions", {}).items():
        for r in regs:
            reg2prov[str(r["c"])] = str(prov_code)
    return dist2reg, reg2prov


def _geo_district_noms():
    """{code_district (str): nom} à plat, depuis ARBRE_GEO."""
    noms = {}
    for dists in ARBRE_GEO.get("districts", {}).values():
        for d in dists:
            noms[str(d["c"])] = str(d["n"])
    return noms


def _filtre_district_html(district_sel, districts_perim):
    """Widget de filtre « district ».

    - Lecteur SANS restriction (National/Admin, districts_perim=None) : cascade
      Province -> Région -> District (pré-remplie si un district est choisi ; JS
      d'enchaînement fourni par page_journal_lecture).
    - Lecteur multi-district (Coordonnateur régionale, districts_perim=set) :
      simple liste déroulante restreinte à SES districts."""
    esc = htmllib.escape
    district_sel = str(district_sel) if district_sel else ""
    if districts_perim is not None:
        noms = _geo_district_noms()
        opts = ['<option value="">— Tous mes districts —</option>']
        for c in sorted(districts_perim):
            sel = ' selected' if str(c) == district_sel else ''
            opts.append(f'<option value="{c}"{sel}>'
                        f'{esc(noms.get(str(c), str(c)))} ({c})</option>')
        return ('<div class="pleine"><label for="district">District</label>'
                '<select id="district" name="district">'
                + "".join(opts) + '</select></div>')
    # National / Admin : cascade complète, pré-remplie côté serveur si un district
    # est sélectionné (le JS ne gère que les changements ultérieurs).
    dist2reg, reg2prov = _geo_reverse()
    reg_sel = dist2reg.get(district_sel) if district_sel else None
    prov_sel = reg2prov.get(reg_sel) if reg_sel else None
    opt_prov = ['<option value="">— Toutes —</option>']
    for p in ARBRE_GEO.get("provinces", []):
        sel = ' selected' if prov_sel and str(p["c"]) == prov_sel else ''
        opt_prov.append(f'<option value="{p["c"]}"{sel}>{esc(str(p["n"]))}</option>')
    opt_reg = ['<option value="">— Toutes —</option>']
    reg_dis = ' disabled'
    if prov_sel:
        reg_dis = ''
        for r in ARBRE_GEO.get("regions", {}).get(prov_sel, []):
            sel = ' selected' if reg_sel and str(r["c"]) == reg_sel else ''
            opt_reg.append(f'<option value="{r["c"]}"{sel}>{esc(str(r["n"]))}</option>')
    opt_dist = ['<option value="">— Tous —</option>']
    dist_dis = ' disabled'
    if reg_sel:
        dist_dis = ''
        for d in ARBRE_GEO.get("districts", {}).get(reg_sel, []):
            sel = ' selected' if str(d["c"]) == district_sel else ''
            opt_dist.append(f'<option value="{d["c"]}"{sel}>{esc(str(d["n"]))}</option>')
    return (
        '<div><label for="province">Province</label>'
        '<select id="province" name="province">' + "".join(opt_prov) + '</select></div>'
        '<div><label for="region">Région</label>'
        f'<select id="region" name="region"{reg_dis}>' + "".join(opt_reg) + '</select></div>'
        '<div><label for="district">District</label>'
        f'<select id="district" name="district"{dist_dis}>'
        + "".join(opt_dist) + '</select></div>')


def _filtre_select(nom, libelle, valeurs, choisi, tout="— Tous —"):
    """<select> simple d'un filtre à partir d'une liste de valeurs distinctes."""
    esc = htmllib.escape
    choisi = choisi or ""
    opts = [f'<option value="">{esc(tout)}</option>']
    for v in valeurs:
        sel = ' selected' if v == choisi else ''
        opts.append(f'<option value="{esc(v)}"{sel}>{esc(v)}</option>')
    return (f'<div><label for="{nom}">{esc(libelle)}</label>'
            f'<select id="{nom}" name="{nom}">' + "".join(opts) + '</select></div>')


def page_journal_lecture(u, entrees, filtres, options, portee_txt,
                         districts_perim) -> str:
    """Page « Journaux des équipes » (coordonnateurs + Admin) : liste bornée au
    périmètre du lecteur, avec filtres District (cascade ou restreint), Fonction,
    Axe/Zone, Nom et Date. `filtres` = valeurs courantes, `options` = valeurs
    distinctes du périmètre pour peupler les listes."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    retour = accueil_role(role)
    actif = any((filtres or {}).get(k) for k in
                ("district", "fonction", "zone", "nom", "date"))
    # Le filtre Axe n'est utilisable qu'avec un district ET une fonction
    # « district + communes » (Superviseur Technique / Logistique Inter-Communale).
    axe_actif = (bool((filtres or {}).get("district"))
                 and (filtres or {}).get("fonction") in _ROLES_DISTRICT_COMMUNES)

    if entrees:
        lignes = "".join(
            '<div class="jr-e"><div class="jr-e-h">'
            f'<span class="jr-date">{esc(e["date_court"])}</span>'
            f'<span class="jr-qui">{esc(e.get("nom_prenom") or e.get("login") or "—")}</span>'
            f'<span class="jr-tag">{esc(e.get("fonction") or "")}</span>'
            f'<span class="jr-tag">{esc(e.get("zone") or "")}</span>'
            f'</div><p class="jr-txt">{esc(e["journal"] or "")}</p></div>'
            for e in entrees)
        pied = f'<p class="jr-sous">{len(entrees)} entrée(s) affichée(s).</p>'
    else:
        lignes = ('<p class="jr-vide">Aucun journal ne correspond '
                  'à ces critères (filtres / périmètre).</p>')
        pied = ''

    bloc_district = _filtre_district_html(
        (filtres or {}).get("district"), districts_perim)
    bloc_fonction = _filtre_select(
        "fonction", "Fonction / Poste", (options or {}).get("fonctions", []),
        (filtres or {}).get("fonction"), tout="— Toutes —")
    # Filtre Axe / Zone de supervision — DÉPENDANT : actif seulement quand un
    # district et une fonction « district + communes » sont choisis (l'axe n'a de
    # sens qu'au sein d'un district). Sinon désactivé avec un libellé explicatif.
    if axe_actif:
        opts_axe = ['<option value="">— Tous les axes —</option>']
        for z in (options or {}).get("axes", []):
            lib = z.split(":", 1)[1].strip() if ":" in z else z
            sel = ' selected' if z == ((filtres or {}).get("zone") or "") else ''
            opts_axe.append(f'<option value="{esc(z)}"{sel}>{esc(lib)}</option>')
        bloc_axe = ('<div><label for="zone">Axe / Zone de supervision</label>'
                    '<select id="zone" name="zone">' + "".join(opts_axe)
                    + '</select></div>')
    else:
        bloc_axe = ('<div><label for="zone">Axe / Zone de supervision</label>'
                    '<select id="zone" name="zone" disabled>'
                    '<option>Choisir un district + fonction Superviseur/Logistique '
                    'Inter-Communale</option></select></div>')
    bloc_nom = (
        '<div><label for="nom">Nom et Prénom</label>'
        '<input type="text" id="nom" name="nom" placeholder="Rechercher un nom…" '
        f'value="{esc((filtres or {}).get("nom") or "")}"></div>')
    bloc_date = (
        '<div><label for="date">Date</label>'
        '<input type="date" id="date" name="date" '
        f'value="{esc((filtres or {}).get("date") or "")}"></div>')

    reinit = ('<a class="jr-retour" href="/journal" style="margin-top:0">'
              'Réinitialiser les filtres</a>' if actif else '')

    # Cascade JS + GEO uniquement pour le lecteur sans restriction (cascade complète).
    script = ""
    if districts_perim is None:
        script = (
            '<script>const GEO=' + json.dumps(ARBRE_GEO, ensure_ascii=False) + ';'
            'const sp=document.getElementById("province"),'
            'sr=document.getElementById("region"),sd=document.getElementById("district");'
            'function vd(s,t){s.innerHTML=' + "'<option value=\"\">'+t+'</option>'" + ';}'
            'function rp(s,l,t){vd(s,t);(l||[]).forEach(function(o){'
            'var e=document.createElement("option");e.value=o.c;e.textContent=o.n;'
            's.appendChild(e);});s.disabled=!(l&&l.length);}'
            'if(sp&&sr&&sd){'
            'sp.addEventListener("change",function(){'
            'rp(sr,GEO.regions[sp.value],"— Toutes —");vd(sd,"— Tous —");sd.disabled=true;});'
            'sr.addEventListener("change",function(){'
            'rp(sd,GEO.districts[sr.value],"— Tous —");});}'
            '</script>')

    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Journaux des équipes</title>'
        f'<style>{_STYLE_JOURNAL}</style></head><body><div class="jr-wrap">'
        '<div class="jr-carte">'
        '<h1>📖 Journaux des équipes</h1>'
        f'<p class="jr-sous">{esc(portee_txt)}</p>'
        '<form method="get" action="/journal">'
        '<div class="jr-filtres">'
        f'{bloc_district}{bloc_fonction}{bloc_axe}{bloc_nom}{bloc_date}'
        '</div>'
        '<p class="jr-sous" style="margin:10px 0 0">Astuce : pour filtrer par '
        '<b>axe / zone de supervision</b>, choisissez d’abord un <b>district</b> et '
        'la <b>fonction</b> « Superviseur Technique » ou « Logistique '
        'Inter-Communale », puis cliquez sur <b>Filtrer</b>.</p>'
        '<div class="jr-actions">'
        '<button type="submit" class="jr-btn sm">Filtrer</button>'
        f'{reinit}</div>'
        '</form></div>'
        '<div class="jr-carte">'
        f'{pied}{lignes}'
        f'<a class="jr-retour" href="{esc(retour)}">← Retour à mon espace</a>'
        '</div>'
        f'{script}'
        '</div></body></html>')


# ---------------------------------------------------------------------------
# Consignes / instructions (Coordonnateurs) — pages RÉDACTION / RÉCEPTION.
# Réutilise la charte `_STYLE_JOURNAL` (classes jr-*) + quelques ajouts.
# ---------------------------------------------------------------------------
_STYLE_CONSIGNE_EXTRA = """
  .cj-grp{border:1px solid #e5ebf2;border-radius:0.75rem;padding:0.75rem 0.875rem;margin-top:0.5rem;
    background:#fbfcfe}
  .cj-cbs{display:flex;flex-wrap:wrap;gap:0.5rem 1rem;margin-top:0.5rem}
  .cj-cb{display:flex;align-items:center;gap:0.4375rem;font-size:.9rem;font-weight:500;
    cursor:pointer}
  .cj-cb input{width:1rem;height:1rem;accent-color:#1b6ef3}
  .cj-tous{font-weight:700;color:#1558c9}
  select[multiple]{width:100%;padding:0.375rem;border:1.5px solid #e1e7ef;border-radius:0.6875rem;
    background:#f7f9fc;font-size:.95rem}
  select[multiple]:disabled{background:#eef1f5;color:#9aa6b3}
  .cj-cible{font-size:.8rem;color:#5a6675;background:#eef2f7;border-radius:62.4375rem;
    padding:2px 0.625rem;margin-right:0.375rem}
  .cj-nonlu{border-left:0.3125rem solid #e79a1b;background:#fffdf6}
  .cj-auteur{font-weight:700}
  .cj-actions{margin-left:auto;display:flex;gap:0.5rem;align-items:center}
  .cj-del-f{display:inline}
  .cj-del-b{border:1px solid #f0cfca;background:#fdecea;color:#c0392b;font-weight:600;
    font-size:.78rem;border-radius:0.5rem;padding:0.25rem 0.625rem;cursor:pointer;transition:.15s}
  .cj-del-b:hover{background:#c0392b;color:#fff;border-color:#c0392b}
  .cj-mod-b{border:1px solid #c7dbf7;background:#eaf1fd;color:#1558c9;font-weight:600;
    font-size:.78rem;border-radius:0.5rem;padding:0.25rem 0.625rem;cursor:pointer;transition:.15s;
    text-decoration:none}
  .cj-mod-b:hover{background:#1558c9;color:#fff;border-color:#1558c9}
"""


def _consigne_districts_widget(districts_perim, selection=None) -> str:
    """<select multiple> des districts (optgroups par région), borné au périmètre
    de l'émetteur (None = tous les districts, sinon seulement les siens).
    `selection` = codes à pré-sélectionner (mode modification)."""
    esc = htmllib.escape
    scope = None if districts_perim is None else {str(d) for d in districts_perim}
    sel_set = {str(s) for s in (selection or set())}
    groupes = []
    for p in ARBRE_GEO.get("provinces", []):
        for r in ARBRE_GEO.get("regions", {}).get(str(p["c"]), []):
            opts = []
            for d in ARBRE_GEO.get("districts", {}).get(str(r["c"]), []):
                if scope is not None and str(d["c"]) not in scope:
                    continue
                sel = ' selected' if str(d["c"]) in sel_set else ''
                opts.append(f'<option value="{d["c"]}"{sel}>'
                            f'{esc(str(d["n"]))} ({d["c"]})</option>')
            if opts:
                groupes.append(f'<optgroup label="{esc(str(r["n"]))}">'
                               + "".join(opts) + '</optgroup>')
    return ('<select id="districts" name="districts" multiple size="8">'
            + "".join(groupes) + '</select>')


def page_consignes_nouvelle(u, envoyees, districts_perim,
                            message: str = "", erreur: str = "", edition=None) -> str:
    """Page de RÉDACTION d'une consigne (Coordonnateurs) : message + destinataires
    (rôles) + districts concernés, puis liste des consignes déjà envoyées.
    `edition` (dict consigne avec au moins id/roles_cibles/districts_cibles/titre/
    message) -> mode MODIFICATION : formulaire pré-rempli, POST vers /consignes/
    modifier."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    ed = edition or {}
    editing = edition is not None
    bloc_msg = ""
    if message:
        bloc_msg = f'<div class="jr-msg ok">{esc(message)}</div>'
    elif erreur:
        bloc_msg = f'<div class="jr-msg err">{esc(erreur)}</div>'

    # Pré-sélection (mode modification) : rôles / districts déjà ciblés.
    ed_roles = ed.get("roles_cibles")
    roles_tous_chk = ed_roles == consignes.TOUS
    roles_set = (set(ed_roles.split("|")) if ed_roles and not roles_tous_chk else set())
    ed_dists = ed.get("districts_cibles")
    dists_tous_chk = ed_dists == consignes.TOUS
    dists_set = ({c for c in ed_dists.split(",") if c}
                 if ed_dists and not dists_tous_chk else set())
    roles_cb = "".join(
        f'<label class="cj-cb"><input type="checkbox" class="cj-role" name="roles" '
        f'value="{esc(r)}"{" checked" if r in roles_set else ""}> {esc(r)}</label>'
        for r in _ROLES_CONSIGNE_CIBLES)
    lib_tous_d = ("Tous mes districts" if districts_perim is not None
                  else "Tous les districts")
    action = "/consignes/modifier" if editing else "/consignes/nouvelle"
    hidden_id = (f'<input type="hidden" name="id" value="{esc(ed.get("id") or "")}">'
                 if editing else '')
    titre_val = esc(ed.get("titre") or "")
    message_val = esc(ed.get("message") or "")
    titre_page = "Modifier une consigne" if editing else "Consignes & instructions"
    btn_label = "Enregistrer les modifications" if editing else "Envoyer la consigne"
    sous = ("Modifiez la consigne ci-dessous. Les destinataires seront de nouveau "
            "notifiés de la version à jour." if editing else
            "Rédigez une consigne et choisissez qui la reçoit (rôles) et pour "
            "quels districts.")
    annuler = ('<a class="jr-retour" href="/consignes/nouvelle" '
               'style="margin-top:0">Annuler</a>' if editing else '')

    if envoyees:
        env_html = "".join(
            '<div class="jr-e"><div class="jr-e-h">'
            f'<span class="jr-date">{esc(e["cree_court"])}</span>'
            f'<span class="cj-cible">👥 {esc(_lib_roles(e["roles_cibles"]))}</span>'
            f'<span class="cj-cible">📍 {esc(_lib_districts(e["districts_cibles"]))}</span>'
            '<span class="cj-actions">'
            f'<a class="cj-mod-b" href="/consignes/modifier?id={esc(e["id"])}" '
            'title="Modifier">✏️ Modifier</a>'
            '<form method="post" action="/consignes/supprimer" class="cj-del-f" '
            'onsubmit="return confirm(\'Supprimer définitivement cette consigne ? '
            'Les destinataires ne la verront plus.\')">'
            f'<input type="hidden" name="id" value="{esc(e["id"])}">'
            '<button type="submit" class="cj-del-b" title="Supprimer / rappeler">'
            '🗑 Supprimer</button></form></span>'
            '</div>'
            + (f'<div class="jr-qui">{esc(e["titre"])}</div>' if e.get("titre") else '')
            + f'<p class="jr-txt">{esc(e["message"] or "")}</p></div>'
            for e in envoyees)
    else:
        env_html = '<p class="jr-vide">Aucune consigne envoyée pour l’instant.</p>'
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Consigne</title>'
        f'<style>{_STYLE_JOURNAL}{_STYLE_CONSIGNE_EXTRA}</style></head>'
        '<body><div class="jr-wrap"><div class="jr-carte">'
        f'<h1>📣 {esc(titre_page)}</h1>'
        f'<p class="jr-sous">{esc(sous)}</p>'
        f'{bloc_msg}'
        f'<form method="post" action="{action}" id="cj-form">{hidden_id}'
        '<label for="titre">Titre (facultatif)</label>'
        f'<input type="text" id="titre" name="titre" value="{titre_val}" '
        'placeholder="Objet de la consigne…" style="width:100%;padding:11px 13px;'
        'font-size:1rem;background:#f7f9fc;border:1.5px solid #e1e7ef;'
        'border-radius:11px">'
        '<label for="message">Message</label>'
        '<textarea id="message" name="message" required '
        f'placeholder="Consigne / instruction à transmettre…">{message_val}</textarea>'
        '<label>Destinataires (rôles)</label>'
        '<div class="cj-grp">'
        '<label class="cj-cb cj-tous"><input type="checkbox" id="roles_tous" '
        f'name="roles_tous" value="1"{" checked" if roles_tous_chk else ""}> '
        'Tout le monde</label>'
        f'<div class="cj-cbs" id="roles_liste">{roles_cb}</div></div>'
        '<label>Districts concernés</label>'
        '<div class="cj-grp">'
        '<label class="cj-cb cj-tous"><input type="checkbox" id="districts_tous" '
        f'name="districts_tous" value="1"{" checked" if dists_tous_chk else ""}> '
        f'{esc(lib_tous_d)}</label>'
        '<div style="margin-top:8px" id="districts_liste">'
        + _consigne_districts_widget(districts_perim, dists_set) +
        '<p class="mdp-aide" style="color:#7a8698;font-size:.78rem;margin:6px 2px 0">'
        'Maintenez Ctrl (⌘ sur Mac) pour sélectionner plusieurs districts.</p>'
        '</div></div>'
        f'<div class="jr-actions"><button type="submit" class="jr-btn">{esc(btn_label)}'
        f'</button>{annuler}</div>'
        '</form></div>'
        '<div class="jr-carte"><h2 class="jr-h2">Consignes envoyées</h2>'
        f'{env_html}'
        f'<a class="jr-retour" href="{esc(accueil_role(role))}">'
        '← Retour à mon espace</a></div></div>'
        '<script>'
        f'var EST_EDIT={"true" if editing else "false"};'
        'var rt=document.getElementById("roles_tous");'
        'var dt=document.getElementById("districts_tous");'
        'var sd=document.getElementById("districts");'
        'function maj(){'
        'document.querySelectorAll(".cj-role").forEach(function(c){'
        'c.disabled=rt.checked;});sd.disabled=dt.checked;}'
        'if(rt&&dt){rt.addEventListener("change",maj);'
        'dt.addEventListener("change",maj);maj();}'
        # Confirmation AVANT envoi/modification : récapitule rôles + districts (JS).
        'var f=document.getElementById("cj-form");'
        'if(f){f.addEventListener("submit",function(e){'
        'var roles;if(rt.checked){roles="Tout le monde";}else{'
        'var rs=[].slice.call(document.querySelectorAll(".cj-role:checked"))'
        '.map(function(c){return c.value;});roles=rs.length?rs.join(", "):"(aucun)";}'
        'var dists;if(dt.checked){dists="'
        + esc(lib_tous_d) + '";}else{'
        'var ds=[].slice.call(sd.selectedOptions).map(function(o){return o.textContent;});'
        'dists=ds.length?ds.join(", "):"(aucun)";}'
        'var verbe=EST_EDIT?"Enregistrer les modifications de cette consigne":'
        '"Envoyer cette consigne";'
        'if(!confirm(verbe+" à :\\n\\n"+'
        '"Rôles : "+roles+"\\n"+"Districts : "+dists+"\\n\\nConfirmer ?")){'
        'e.preventDefault();}});}'
        '</script></body></html>')


def page_consignes_recues(u, recues, est_emetteur, filtres=None) -> str:
    """Page de RÉCEPTION : consignes adressées à l'utilisateur (marquées lues à
    l'ouverture). `est_emetteur` ajoute un bouton « Écrire une consigne ».
    `filtres` = {date, poste} : filtre d'affichage (date d'émission, poste de
    l'émetteur — Coordonnateur Nationale / régionale)."""
    esc = htmllib.escape
    role = (u.get("responsabilite") or "").strip()
    filtres = filtres or {}
    actif = bool(filtres.get("date") or filtres.get("poste") or filtres.get("nom"))
    # Filtre « Poste » : les émetteurs possibles = les deux Coordonnateurs.
    opts_poste = ['<option value="">— Tous les postes —</option>']
    for p in _ROLES_CONSIGNE_ENVOI:
        sel = ' selected' if p == (filtres.get("poste") or "") else ''
        opts_poste.append(f'<option value="{esc(p)}"{sel}>{esc(p)}</option>')
    barre_filtres = (
        '<form method="get" action="/consignes"><div class="jr-filtres">'
        '<div><label for="poste">Poste de l’émetteur</label>'
        '<select id="poste" name="poste">' + "".join(opts_poste) + '</select></div>'
        '<div><label for="nom">Nom de l’émetteur</label>'
        '<input type="text" id="nom" name="nom" placeholder="Rechercher un nom…" '
        f'value="{esc(filtres.get("nom") or "")}"></div>'
        '<div><label for="date">Date</label>'
        f'<input type="date" id="date" name="date" '
        f'value="{esc(filtres.get("date") or "")}"></div></div>'
        '<div class="jr-actions"><button type="submit" class="jr-btn sm">Filtrer'
        '</button>'
        + ('<a class="jr-retour" href="/consignes" style="margin-top:0">'
           'Réinitialiser</a>' if actif else '')
        + '</div></form>')
    if recues:
        liste = "".join(
            f'<div class="jr-e{"" if c["lu"] else " cj-nonlu"}">'
            '<div class="jr-e-h">'
            f'<span class="jr-date">{esc(c["cree_court"])}</span>'
            f'<span class="cj-auteur">{esc(c.get("auteur_nom") or "—")}</span>'
            f'<span class="jr-tag">{esc(c.get("auteur_role") or "")}</span>'
            + ('' if c["lu"] else '<span class="jr-tag" '
               'style="background:#fde7c7;color:#8a5a00">Nouveau</span>')
            + '</div>'
            + (f'<div class="jr-qui">{esc(c["titre"])}</div>' if c.get("titre") else '')
            + f'<p class="jr-txt">{esc(c["message"] or "")}</p></div>'
            for c in recues)
        pied = f'<p class="jr-sous">{len(recues)} consigne(s).</p>'
    else:
        liste = ('<p class="jr-vide">Aucune consigne ne correspond '
                 '(filtres).</p>' if actif else
                 '<p class="jr-vide">Aucune consigne reçue pour l’instant.</p>')
        pied = ''
    bouton = ''
    if est_emetteur:
        bouton = ('<a class="jr-btn" href="/consignes/nouvelle" '
                  'style="display:inline-block;text-decoration:none;margin-bottom:6px">'
                  '✍️ Écrire une consigne</a>')
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Consignes reçues</title>'
        f'<style>{_STYLE_JOURNAL}{_STYLE_CONSIGNE_EXTRA}</style></head>'
        '<body><div class="jr-wrap"><div class="jr-carte">'
        '<h1>📥 Consignes &amp; instructions reçues</h1>'
        '<p class="jr-sous">Instructions transmises par vos coordonnateurs.</p>'
        f'{bouton}'
        f'{barre_filtres}</div>'
        '<div class="jr-carte">'
        f'{pied}{liste}'
        f'<a class="jr-retour" href="{esc(accueil_role(role))}">'
        '← Retour à mon espace</a></div></div></body></html>')


def _lib_roles(roles_cibles) -> str:
    return ("Tout le monde" if roles_cibles == consignes.TOUS
            else ", ".join(roles_cibles.split("|")))


def _lib_districts(districts_cibles) -> str:
    if districts_cibles == consignes.TOUS:
        return "Tous les districts"
    codes = [c for c in districts_cibles.split(",") if c]
    conn = db_source.connect()
    try:
        noms = []
        for c in codes:
            lib = zones.libelles_district(conn, c)
            noms.append(lib[2] if lib else str(c))
    finally:
        conn.close()
    return ", ".join(noms) if noms else "—"


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
_RE_HEAD_FIN = re.compile(r"(</head>)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# NORMALISATION D'AFFICHAGE (Phase 1 — pansement global, réversible).
# Toute l'app est dessinée en pixels FIXES : sur un poste plus petit (ou en
# « mise à l'échelle » Windows 125-150 %), la page paraît « trop grande » et
# déborde. On ajuste ici l'ÉCHELLE de la page entière selon la largeur d'écran,
# UNIQUEMENT VERS LE BAS : les écrans >= _UI_LARGEUR_REF ne sont pas touchés
# (donc le poste de développement reste identique), les plus petits sont
# réduits jusqu'à _UI_ZOOM_MIN pour « rentrer ». Injecté par _html() sur CHAQUE
# page (rapport et login compris). Réglable par la variable d'environnement
# RSU_UI_LARGEUR_REF. Sera retiré une fois la refonte rem (Phase 2) terminée.
# ---------------------------------------------------------------------------
_UI_LARGEUR_REF = int(os.environ.get("RSU_UI_LARGEUR_REF", "1200"))
_UI_ZOOM_MIN = 0.78
_STYLE_RESPONSIVE = (
    '<style id="rsu-responsive">'
    "html{-webkit-text-size-adjust:100%;text-size-adjust:100%;}"
    "img{max-width:100%;height:auto;}"
    "</style>"
    "<script>(function(){var B=" + str(_UI_LARGEUR_REF)
    + ",MIN=" + str(_UI_ZOOM_MIN) + ";"
    # Une page déjà FLUIDE (rem + base clamp, Phase 2) se déclare via la variable
    # CSS --rsu-fluid:1 sur :root -> on NE la zoome PAS (sinon double échelle).
    "function fluide(){try{return (getComputedStyle(document.documentElement)"
    ".getPropertyValue('--rsu-fluid')||'').trim()==='1';}catch(e){return false;}}"
    "function f(){var el=document.documentElement;"
    "if(fluide()){try{el.style.zoom='';}catch(e){}return;}"
    "var w=window.innerWidth||el.clientWidth||B;"
    "var z=(w>=B)?1:Math.max(MIN,w/B);"
    "try{el.style.zoom=z;}catch(e){}}"
    # 'load' : re-vérifie une fois le CSS externe (rapport.css) appliqué.
    "f();window.addEventListener('resize',f);window.addEventListener('load',f);"
    # Bouton REPLIER/DÉPLIER la barre latérale des sections (dashboard uniquement :
    # n'agit que si .sidebar + .topbar existent). Ajoute un ☰ dans la barre du haut ;
    # bascule body.rsu-nav-col (CSS dans rapport.css). État mémorisé ; replié par
    # défaut sur petit écran.
    "function nav(){var sb=document.querySelector('.sidebar'),"
    "tb=document.querySelector('.topbar');"
    "if(!sb||!tb||document.getElementById('rsu-nav-toggle'))return;"
    "var btn=document.createElement('button');btn.id='rsu-nav-toggle';"
    "btn.type='button';btn.className='rsu-nav-toggle';btn.innerHTML='\\u2630';"
    "btn.setAttribute('aria-label','Afficher ou masquer le menu des sections');"
    "tb.insertBefore(btn,tb.firstChild);var K='rsu_nav_col';"
    "function setc(c){document.body.classList.toggle('rsu-nav-col',c);"
    "btn.setAttribute('aria-expanded',String(!c));"
    "try{localStorage.setItem(K,c?'1':'0');}catch(e){}}"
    "var v=null;try{v=localStorage.getItem(K);}catch(e){}"
    "var init=(v===null)?(window.matchMedia&&window.matchMedia('(max-width:860px)').matches)"
    ":(v==='1');setc(!!init);"
    "btn.addEventListener('click',function(){"
    "setc(!document.body.classList.contains('rsu-nav-col'));});}"
    "if(document.readyState!=='loading')nav();"
    "else document.addEventListener('DOMContentLoaded',nav);"
    "})();"
    "</script>"
)


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
    # Lien « Mot de passe » : chaque utilisateur peut changer le sien depuis
    # n'importe quelle page (route /motdepasse, tous rôles). Déjà préfixé.
    mdp_url = config.PREFIXE + "/motdepasse"
    lien_mdp = (
        f'<a class="rsu-b-key" href="{esc(mdp_url)}" title="Modifier mon mot de passe">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="8" cy="15" r="4"/><path d="M10.85 12.15 19 4"/>'
        '<path d="M18 5l2 2"/><path d="M15 8l2 2"/></svg>'
        '<span>Mot de passe</span></a>')
    # Lien « Mon profil » : édition libre-service des infos personnelles (tous rôles).
    profil_url = config.PREFIXE + "/profil"
    lien_profil = (
        f'<a class="rsu-b-pf" href="{esc(profil_url)}" title="Mon profil">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1"/>'
        '</svg><span>Profil</span></a>')
    # Lien « Manuel » : guide d'utilisation adapté au rôle (route /manuel, tous
    # rôles). Déjà préfixé (bandeau inséré après _prefixer).
    manuel_url = config.PREFIXE + "/manuel"
    lien_manuel = (
        f'<a class="rsu-b-doc" href="{esc(manuel_url)}" title="Manuel d\'utilisation">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
        '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'
        '</svg><span>Manuel</span></a>')
    # Lien « Journal » : journal de bord. Libellé selon le rôle — écriture
    # (« Journal ») pour l'équipe technique, lecture (« Journaux ») pour les
    # coordonnateurs / l'Admin. Absent pour les autres. Déjà préfixé.
    lien_journal = ""
    if role in _ROLES_JOURNAL_ECRITURE or role in _ROLES_JOURNAL_LECTURE:
        ecrit = role in _ROLES_JOURNAL_ECRITURE
        j_label = "Journal" if ecrit else "Journaux"
        j_title = "Mon journal de bord" if ecrit else "Journaux des équipes"
        j_url = config.PREFIXE + "/journal"
        lien_journal = (
            f'<a class="rsu-b-jr" href="{esc(j_url)}" title="{esc(j_title)}">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">'
            '<path d="M4 4a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>'
            '<path d="M8 6h7"/><path d="M8 10h7"/><path d="M8 14h4"/></svg>'
            f'<span>{esc(j_label)}</span></a>')
    # Lien « Consignes » : consignes/instructions reçues (tous rôles). Déjà préfixé.
    cs_url = config.PREFIXE + "/consignes"
    lien_consigne = (
        f'<a class="rsu-b-cs" href="{esc(cs_url)}" title="Consignes / instructions">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M3 11l18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>'
        '</svg><span>Consignes</span></a>')
    return (
        '<div id="rsu-bandeau" role="banner">'
        '<button type="button" class="rsu-b-toggle" aria-expanded="true" '
        'aria-label="Afficher ou masquer le menu">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>'
        '<line x1="3" y1="18" x2="21" y2="18"/></svg></button>'
        f'<div class="rsu-b-ava">{esc(initiales)}</div>'
        '<div class="rsu-b-txt">'
        f'<span class="rsu-b-nom">{esc(nom)}</span>'
        f'<span class="rsu-b-role">{esc(role)}</span>'
        '</div>'
        f'{lien_espace}'
        f'{lien_manuel}'
        f'{lien_journal}'
        f'{lien_consigne}'
        f'{lien_profil}'
        f'{lien_mdp}'
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
        '#rsu-bandeau .rsu-b-key{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#1558c9;font-weight:600;border:1px solid #c7dbf7;'
        'background:#eaf1fd;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-key:hover{background:#1558c9;color:#fff;'
        'border-color:#1558c9}'
        '#rsu-bandeau .rsu-b-doc{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#1558c9;font-weight:600;border:1px solid #c7dbf7;'
        'background:#eaf1fd;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-doc:hover{background:#1558c9;color:#fff;'
        'border-color:#1558c9}'
        '#rsu-bandeau .rsu-b-jr{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#1558c9;font-weight:600;border:1px solid #c7dbf7;'
        'background:#eaf1fd;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-jr:hover{background:#1558c9;color:#fff;'
        'border-color:#1558c9}'
        '#rsu-bandeau .rsu-b-cs{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#1558c9;font-weight:600;border:1px solid #c7dbf7;'
        'background:#eaf1fd;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-cs:hover{background:#1558c9;color:#fff;'
        'border-color:#1558c9}'
        '#rsu-bandeau .rsu-b-pf{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#1558c9;font-weight:600;border:1px solid #c7dbf7;'
        'background:#eaf1fd;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-pf:hover{background:#1558c9;color:#fff;'
        'border-color:#1558c9}'
        '#rsu-bandeau .rsu-b-out{display:flex;align-items:center;gap:6px;flex:none;'
        'text-decoration:none;color:#c0392b;font-weight:600;border:1px solid #f0cfca;'
        'background:#fdecea;border-radius:999px;padding:7px 13px;transition:.15s}'
        '#rsu-bandeau .rsu-b-out:hover{background:#c0392b;color:#fff;'
        'border-color:#c0392b}'
        '#rsu-bandeau .rsu-b-toggle{width:30px;height:30px;border-radius:50%;flex:none;'
        'display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;'
        'border:1px solid #c7dbf7;background:#eaf1fd;color:#1558c9;transition:.15s}'
        '#rsu-bandeau .rsu-b-toggle:hover{background:#1558c9;color:#fff;border-color:#1558c9}'
        # État REPLIÉ : ne reste que le bouton + les initiales ; tout le reste caché.
        '#rsu-bandeau.rsu-col .rsu-b-txt,#rsu-bandeau.rsu-col a{display:none!important}'
        '@media print{#rsu-bandeau{display:none!important}}'
        '@media (max-width:560px){#rsu-bandeau .rsu-b-txt{display:none}'
        '#rsu-bandeau .rsu-b-out span,#rsu-bandeau .rsu-b-home span,'
        '#rsu-bandeau .rsu-b-key span,#rsu-bandeau .rsu-b-doc span,'
        '#rsu-bandeau .rsu-b-jr span,#rsu-bandeau .rsu-b-cs span,'
        '#rsu-bandeau .rsu-b-pf span{display:none}}'
        '</style>'
        # Bascule replier/déplier (état mémorisé ; replié par défaut sur petit écran).
        '<script>(function(){var b=document.getElementById("rsu-bandeau");if(!b)return;'
        'var t=b.querySelector(".rsu-b-toggle");if(!t)return;var K="rsu_bandeau_col";'
        'function set(c){b.classList.toggle("rsu-col",c);'
        't.setAttribute("aria-expanded",String(!c));'
        'try{localStorage.setItem(K,c?"1":"0");}catch(e){}}'
        'var v=null;try{v=localStorage.getItem(K);}catch(e){}'
        'var init=(v===null)?(window.matchMedia&&window.matchMedia("(max-width:700px)").matches)'
        ':(v==="1");set(!!init);'
        't.addEventListener("click",function(){set(!b.classList.contains("rsu-col"));});})();'
        '</script>')


# ---------------------------------------------------------------------------
# Bulle de RAPPEL du journal de bord : injectée (comme le bandeau) sur chaque
# page servie à un rôle d'écriture qui n'a RIEN écrit aujourd'hui. Disparaît dès
# qu'une entrée existe pour le jour. Résultat mis en cache dans la session
# (re-vérification en base au plus une fois par 120 s) pour limiter les requêtes.
# ---------------------------------------------------------------------------
def bulle_rappel_journal(sess) -> str:
    if not sess:
        return ""
    u = sess.get("utilisateur") or {}
    role = (u.get("responsabilite") or "").strip()
    login = sess.get("login") or u.get("login")
    if role not in _ROLES_JOURNAL_ECRITURE or not login:
        return ""
    jour = journal.aujourdhui()
    if sess.get("_journal_jour") == jour:
        return ""                     # déjà écrit aujourd'hui (confirmé) -> rien
    now = time.time()
    if now - sess.get("_journal_ck", 0) < 120 and "_journal_bulle" in sess:
        return sess["_journal_bulle"]  # résultat récent réutilisé (pas de requête)
    conn = db_source.connect()
    try:
        ecrit = journal.a_ecrit_le(conn, login, jour)
    finally:
        conn.close()
    sess["_journal_ck"] = now
    if ecrit:
        sess["_journal_jour"] = jour
        sess["_journal_bulle"] = ""
        return ""
    url = config.PREFIXE + "/journal"
    esc = htmllib.escape
    bulle = (
        '<div id="rsu-rappel-jr">'
        '<button type="button" class="rsu-rj-x" aria-label="Fermer" '
        'onclick="this.parentNode.style.display=\'none\'">×</button>'
        '<div class="rsu-rj-ic">📓</div>'
        '<div class="rsu-rj-txt"><b>Pensez à votre journal de bord</b>'
        '<span>Vous n’avez pas encore écrit vos activités aujourd’hui.</span></div>'
        f'<a class="rsu-rj-go" href="{esc(url)}">Écrire maintenant →</a>'
        '<style>'
        '#rsu-rappel-jr{position:fixed;left:16px;bottom:16px;z-index:2147482900;'
        'max-width:340px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;'
        'background:#fff;border:1px solid #f2d9a8;border-left:5px solid #e79a1b;'
        'border-radius:14px;padding:13px 15px 13px 14px;'
        'box-shadow:0 10px 28px rgba(13,43,78,.20);'
        'font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430}'
        '#rsu-rappel-jr .rsu-rj-ic{font-size:1.5rem;line-height:1}'
        '#rsu-rappel-jr .rsu-rj-txt{display:flex;flex-direction:column;'
        'line-height:1.3;min-width:0;flex:1}'
        '#rsu-rappel-jr .rsu-rj-txt b{font-size:.92rem}'
        '#rsu-rappel-jr .rsu-rj-txt span{font-size:.82rem;color:#6b5321}'
        '#rsu-rappel-jr .rsu-rj-go{flex:1 0 100%;text-align:center;text-decoration:none;'
        'font-weight:700;font-size:.86rem;color:#fff;background:#e79a1b;'
        'border-radius:9px;padding:8px 12px;transition:.15s}'
        '#rsu-rappel-jr .rsu-rj-go:hover{background:#c9820f}'
        '#rsu-rappel-jr .rsu-rj-x{position:absolute;top:6px;right:9px;border:none;'
        'background:none;font-size:1.1rem;color:#b0a487;cursor:pointer;line-height:1}'
        '@media print{#rsu-rappel-jr{display:none!important}}'
        '</style></div>')
    sess["_journal_bulle"] = bulle
    return bulle


# ---------------------------------------------------------------------------
# Bulle des CONSIGNES non lues : injectée (comme le bandeau) sur chaque page,
# EN HAUT À GAUCHE (le bandeau occupe le coin haut-droite ; la bulle journal le
# bas-gauche). Visible pour tout utilisateur ayant des consignes non lues ;
# disparaît dès l'ouverture de /consignes. Comptage mis en cache (session,
# re-vérif ≤ 1×/120 s).
# ---------------------------------------------------------------------------
def bulle_consignes(sess) -> str:
    if not sess:
        return ""
    u = sess.get("utilisateur") or {}
    role = (u.get("responsabilite") or "").strip()
    login = sess.get("login") or u.get("login")
    if not role or not login:
        return ""
    now = time.time()
    # Throttle court (30 s) : une consigne est déclenchée par AUTRUI (l'émetteur),
    # donc le cache doit expirer vite pour que le destinataire la voie rapidement.
    if now - sess.get("_consignes_ck", 0) < 30 and "_consignes_n" in sess:
        n = sess["_consignes_n"]
    else:
        conn = db_source.connect()
        try:
            n = consignes.non_lues(conn, login, role, perimetre(u)[0])
        finally:
            conn.close()
        sess["_consignes_ck"] = now
        sess["_consignes_n"] = n
    if not n:
        return ""
    url = config.PREFIXE + "/consignes"
    mot = "consigne" if n == 1 else "consignes"
    return (
        '<div id="rsu-consigne">'
        '<div class="rsu-cs-ic">📣</div>'
        '<div class="rsu-cs-txt"><b>' + str(n) + f' {mot} à lire</b>'
        '<span>Nouvelle(s) instruction(s) de vos coordonnateurs.</span></div>'
        f'<a class="rsu-cs-go" href="{url}">Lire →</a>'
        '<style>'
        '#rsu-consigne{position:fixed;left:16px;top:14px;z-index:2147482800;'
        'max-width:330px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;'
        'background:#fff;border:1px solid #cfe0fb;border-left:5px solid #1b6ef3;'
        'border-radius:14px;padding:11px 14px;box-shadow:0 10px 28px rgba(13,43,78,.20);'
        'font-family:system-ui,"Segoe UI",Arial,sans-serif;color:#1c2430}'
        '#rsu-consigne .rsu-cs-ic{font-size:1.4rem;line-height:1}'
        '#rsu-consigne .rsu-cs-txt{display:flex;flex-direction:column;line-height:1.3;'
        'min-width:0;flex:1}'
        '#rsu-consigne .rsu-cs-txt b{font-size:.9rem}'
        '#rsu-consigne .rsu-cs-txt span{font-size:.8rem;color:#4a5b74}'
        '#rsu-consigne .rsu-cs-go{flex:1 0 100%;text-align:center;text-decoration:none;'
        'font-weight:700;font-size:.85rem;color:#fff;background:#1b6ef3;border-radius:9px;'
        'padding:8px 12px;transition:.15s}'
        '#rsu-consigne .rsu-cs-go:hover{background:#1558c9}'
        '@media print{#rsu-consigne{display:none!important}}'
        '</style></div>')


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
        sess_courante = _session(self)
        bandeau = bandeau_utilisateur(sess_courante)
        # Bulle de rappel du journal (rôles d'écriture n'ayant rien écrit ce jour)
        # injectée avec le bandeau, sur toute page connectée SAUF la page /journal
        # elle-même (où l'utilisateur est justement en train d'écrire).
        chemin_courant = self.path.split("?", 1)[0]
        if chemin_courant not in (PREFIXE + "/journal",):
            bandeau += bulle_rappel_journal(sess_courante)
        # Bulle des consignes non lues, SAUF sur la page /consignes (on y va lire).
        if chemin_courant not in (PREFIXE + "/consignes",):
            bandeau += bulle_consignes(sess_courante)
        if bandeau:
            contenu = _RE_BODY.sub(lambda m: m.group(1) + bandeau, contenu, count=1)
        # Normalisation d'affichage (Phase 1) : injectée juste avant </head> sur
        # TOUTE page (connectée ou non), donc aussi login/erreurs — après les styles
        # de la page (les gardes priment) et sans déplacer <meta charset>.
        # Cf. _STYLE_RESPONSIVE.
        contenu = _RE_HEAD_FIN.sub(
            lambda m: _STYLE_RESPONSIVE + m.group(1), contenu, count=1)
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

        # Changer SON PROPRE mot de passe : accessible à TOUS les rôles connectés.
        # Placé AVANT les gardes de rôle (qui redirigent Expert/Logistique ailleurs).
        if chemin == "/motdepasse":
            self._html(page_motdepasse(sess=sess))
            return

        # « Mon profil » : chaque utilisateur modifie SES infos personnelles (CIN,
        # téléphone, N° Orange/Float, e-mail, sexe). Tous rôles, AVANT les gardes.
        if chemin == "/profil":
            self._profil_get(sess)
            return

        # Manuel d'utilisation adapté au rôle : accessible à TOUS les connectés
        # (avant les gardes de rôle, comme /motdepasse).
        if chemin == "/manuel":
            role = (sess.get("utilisateur") or {}).get("responsabilite")
            self._html(manuel.page_manuel(role))
            return

        # Fiche « Équipe technique » du district d'AFFECTATION, pour les rôles
        # bornés à un district (Traitement, Superviseur Technique, Expert survey).
        # Placé AVANT les gardes de rôle (qui redirigeraient l'Expert/Logistique).
        # Chaque rôle ne voit que l'équipe de SON district (résolu par perimetre()).
        if chemin == "/equipe":
            self._equipe_get(sess)
            return

        # Journal de bord : écriture (équipe technique) OU lecture (coordonnateurs
        # + Admin). Accessible à TOUS les rôles concernés -> placé AVANT les gardes
        # de rôle (qui redirigeraient Expert/Logistique vers leur seul espace).
        if chemin == "/journal":
            self._journal_get(sess)
            return
        # Historique COMPLET de mon journal (rôles d'écriture) : toutes mes entrées.
        if chemin == "/journal/historique":
            self._journal_historique_get(sess)
            return
        # Modifier une de MES entrées de journal (rôles d'écriture).
        if chemin == "/journal/modifier":
            self._journal_modifier_get(sess)
            return
        # Suivi de complétude du journal (Coordonnateurs + Admin) : qui a écrit ou
        # non, par poste (par axe pour Sup. Technique / Logistique Inter-Communale).
        if chemin == "/journal/suivi":
            self._journal_suivi_get(sess)
            return
        # Rapport de mission : synthèse (HORS-LIGNE) des journaux de bord sur une
        # période. Réservé aux rôles de LECTURE du journal (Coordonnateurs + Admin).
        if chemin == "/rapport-mission":
            self._rapport_mission_get(sess)
            return
        # Version RÉDIGÉE PAR IA du rapport de mission (mêmes gardes/périmètre).
        # Ne s'exécute que si l'IA est activée (clé API + RSU_IA_RAPPORT=1).
        if chemin == "/rapport-mission/ia":
            self._rapport_mission_ia_get(sess)
            return

        # Consignes / instructions : réception (tous rôles) + rédaction (les deux
        # Coordonnateurs). Placé AVANT les gardes de rôle (accessible à tous).
        if chemin == "/consignes":
            self._consignes_get(sess)
            return
        if chemin == "/consignes/nouvelle":
            self._consignes_nouvelle_get(sess)
            return
        if chemin == "/consignes/modifier":
            self._consignes_modifier_get(sess)
            return

        # Menus dédiés des rôles à menu (/coordonat, /coordoreg, /suptech), sur le
        # modèle de /traitement : chacun a SA page d'accueil. Placés AVANT les gardes.
        if chemin in _MENU_CHEMINS.values():
            u = sess.get("utilisateur") or {}
            role = (u.get("responsabilite") or "").strip()
            # Un rôle ne voit QUE son propre menu : sinon, on le renvoie chez lui.
            if _MENU_CHEMINS.get(role) != chemin:
                self._redirige(accueil_role(role))
                return
            op = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query).get("op", [""])[0]
            self._menu_operation_get(sess, u, role, op.strip())
            return

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
            u = sess.get("utilisateur") or {}
            role = (u.get("responsabilite") or "").strip()
            # Rôles à MENU : leur accueil est leur route dédiée (/coordonat,
            # /coordoreg, /suptech) -> on y renvoie. (Le tableau de bord reste
            # atteint via <menu>?op=den, la sélection via POST /suivi.)
            if role in _MENU_CHEMINS:
                self._redirige(_MENU_CHEMINS[role])
                return
            # Autres rôles (ex. Comités Techniques) : sélection classique
            # (choix zone + type de suivi).
            self._html(page_selection(utilisateur=u))
        elif chemin == "/suivi":
            sel = sess.get("selection")
            if not sel:
                self._redirige("/choix")  # rien de choisi encore
                return
            if sel.get("suivi") == "vad":
                # Données visites à domicile pas encore disponibles.
                self._html(page_vad_indisponible(sel))
                return
            if sel.get("suivi") == "equipe":
                # Fiche de l'encadrement affecté au district (Coord. Nationale).
                conn = db_source.connect()
                try:
                    equipes = utilisateurs.equipe_technique_district(
                        conn, sel.get("code_district"))
                finally:
                    conn.close()
                self._html(page_equipe_technique(sel, equipes))
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
        elif chemin == "/motdepasse":
            self._traiter_motdepasse()
        elif chemin == "/profil":
            self._traiter_profil()
        elif chemin == "/journal":
            self._journal_post()
        elif chemin == "/journal/modifier":
            self._journal_modifier_post()
        elif chemin == "/consignes/nouvelle":
            self._consignes_nouvelle_post()
        elif chemin == "/consignes/modifier":
            self._consignes_modifier_post()
        elif chemin == "/consignes/supprimer":
            self._consignes_supprimer_post()
        elif chemin == "/rapport-mission/ia/word":
            self._rapport_mission_ia_word_post()
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

    def _equipe_get(self, sess):
        """Fiche « Équipe technique » du district d'affectation de l'utilisateur.

        Réservée aux rôles bornés à un district (Traitement, Superviseur Technique,
        Expert survey) : chacun ne voit que l'équipe de SON district, résolu par
        perimetre() (source de vérité de l'accès), jamais d'une saisie. Le
        Coordonnateur Nationale, lui, passe par la sélection (choix « Équipe
        technique » pour un district de son choix)."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_EQUIPE_DISTRICT:
            # Coord. Nationale -> sélection ; autres rôles -> leur espace.
            self._redirige(accueil_role(role))
            return
        districts, _ = perimetre(u)
        if not districts:
            self._html(page_erreur(
                "Aucun district d'affectation n'est associé à votre compte.", 400), 400)
            return
        code = sorted(districts)[0]            # rôles mono-district : un seul
        conn = db_source.connect()
        try:
            libs = zones.libelles_district(conn, code)
            equipes = utilisateurs.equipe_technique_district(conn, code)
        finally:
            conn.close()
        if not libs:
            self._html(page_erreur("District inconnu dans le référentiel.", 400), 400)
            return
        province_nom, region_nom, district_nom = libs
        sel = {"code_district": int(code), "province_nom": province_nom,
               "region_nom": region_nom, "district_nom": district_nom,
               "suivi": "equipe"}
        self._html(page_equipe_technique(
            sel, equipes, retour_href=accueil_role(role),
            retour_label="← Retour à mon espace"))

    # -----------------------------------------------------------------------
    # Journal de bord (activités quotidiennes)
    # -----------------------------------------------------------------------
    def _rapport_mission_get(self, sess):
        """GET /rapport-mission : formulaire (sans période) ou rapport compilé
        HORS-LIGNE des journaux. Réservé aux rôles de LECTURE du journal
        (Coordonnateurs + Admin) ; borné au périmètre du rôle. Liens NON préfixés
        (préfixés par _html/_prefixer)."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_JOURNAL_LECTURE:
            self._redirige(accueil_role(role))
            return
        districts = perimetre(u)[0]        # None = tous ; set = ses districts
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

        def _val(cle):
            return (q.get(cle, [""])[0] or "").strip()

        debut, fin, district_f = _val("debut"), _val("fin"), _val("district")
        # District choisi borné au périmètre (un district hors périmètre est ignoré).
        if district_f and districts is not None and district_f not in {str(d) for d in districts}:
            district_f = ""
        conn = db_source.connect()
        try:
            if not debut or not fin:
                tous = zones.tous_districts(conn)
                if districts is not None:
                    perim = {str(d) for d in districts}
                    tous = [d for d in tous if d["code"] in perim]
                # Logins autorisés (COORDOREG_01/02) : « Générer le rapport » lance
                # DIRECTEMENT le rapport Word IA (action -> /rapport-mission/ia). Les
                # autres rôles de lecture obtiennent la compilation hors-ligne.
                ia = peut_rapport_ia(u)
                self._html(rapport_mission.page_formulaire(
                    config.DATE_DEBUT_MISSION, journal.aujourdhui(), tous,
                    action="/rapport-mission/ia" if ia else "/rapport-mission",
                    retour_href=accueil_role(role), mode_ia=ia))
                return
            if district_f:
                districts_eff = {district_f}
                perim_label = district_f
            else:
                districts_eff = districts
                perim_label = "Tous mes districts" if districts else "Tous les districts"
            rapport = rapport_mission.synthese_locale(conn, debut, fin, districts_eff)
        finally:
            conn.close()
        params = {"debut": debut, "fin": fin}
        if district_f:
            params["district"] = district_f
        # Bouton « rapport IA (Word) » RÉSERVÉ aux logins autorisés (COORDOREG_01/02).
        ia_href = ("/rapport-mission/ia?" + urllib.parse.urlencode(params)
                   if peut_rapport_ia(u) else "")
        self._html(rapport_mission.rendu_html(
            rapport, perim_label, retour_href="/rapport-mission", ia_href=ia_href))

    def _rapport_mission_ia_get(self, sess):
        """GET /rapport-mission/ia : rapport RÉDIGÉ PAR IA (API Claude) livré en WORD.
        Réservé aux LOGINS autorisés (COORDOREG_01/02), pas à un rôle. Affiche une page
        de progression (streaming + heartbeats pour éviter le 504) puis, la rédaction
        finie, déclenche automatiquement le téléchargement du .docx (conversion du
        Markdown déjà produit, sans 2e appel IA). Périmètre borné comme
        /rapport-mission. Rien ne sort tant que l'IA n'est pas activée (ia_active())."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if not peut_rapport_ia(u):
            self._redirige(accueil_role(role))
            return
        if not rapport_mission.ia_active():
            self._html(rapport_mission.page_ia_inactive("/rapport-mission"))
            return
        districts = perimetre(u)[0]
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

        def _val(cle):
            return (q.get(cle, [""])[0] or "").strip()

        debut, fin, district_f = _val("debut"), _val("fin"), _val("district")
        if not debut or not fin:
            self._redirige("/rapport-mission")
            return
        if district_f and districts is not None and district_f not in {str(d) for d in districts}:
            district_f = ""
        conn = db_source.connect()
        try:
            if district_f:
                districts_eff = {district_f}
                perim_label = district_f
            else:
                districts_eff = districts
                perim_label = "Tous mes districts" if districts else "Tous les districts"
            rapport = rapport_mission.synthese_locale(conn, debut, fin, districts_eff)
        finally:
            conn.close()
        # Réponse EN FLUX : on envoie l'en-tête tout de suite, puis des « heartbeats »
        # pendant que l'IA rédige (octets réguliers) -> le proxy ne coupe pas (pas de
        # 504), même si la génération dure 1-2 min. Écriture directe (pas via _html) ;
        # le lien de retour est donc préfixé à la main.
        retour = config.PREFIXE + "/rapport-mission"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")  # nginx : ne pas tamponner
        self.end_headers()
        w = self.wfile

        def _ecrire(txt):
            w.write(txt.encode("utf-8"))
            w.flush()

        try:
            _ecrire(rapport_mission.ia_stream_entete(rapport, perim_label, retour))
            morceaux = []
            for bout in rapport_mission.synthese_ia_iter(rapport, perim_label):
                morceaux.append(bout)
                w.write(b"<!-- . -->")   # heartbeat : garde la connexion active
                w.flush()
            md = "".join(morceaux).strip()
            if md:
                # Rédaction finie : on déclenche le téléchargement Word (POST du
                # Markdown -> route de conversion, qui renvoie le .docx).
                action = config.PREFIXE + "/rapport-mission/ia/word"
                _ecrire(rapport_mission.ia_stream_word_declenche(
                    md, debut, fin, district_f, action))
            else:
                _ecrire(rapport_mission.ia_stream_erreur("Réponse vide du modèle."))
        except Exception as e:
            try:
                _ecrire(rapport_mission.ia_stream_erreur(str(e)))
            except Exception:
                pass
        try:
            _ecrire(rapport_mission.ia_stream_fin())
        except Exception:
            pass

    def _rapport_mission_ia_word_post(self):
        """POST /rapport-mission/ia/word : convertit le Markdown (déjà rédigé par l'IA,
        ANONYMISÉ) en document WORD moderne et illustré, renvoyé en pièce jointe. Même
        garde (LOGINS_RAPPORT_IA) et même bornage de périmètre. AUCUN nouvel appel IA :
        on reçoit le Markdown produit par la page de progression."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = (sess or {}).get("utilisateur") or {}
        if not peut_rapport_ia(u):
            self._html(page_erreur("Accès réservé.", 403), 403)
            return
        champs = self._corps_formulaire()

        def _val(cle):
            return (champs.get(cle, [""])[0] or "").strip()

        markdown = champs.get("markdown", [""])[0]      # NE PAS strip (mise en forme)
        debut, fin, district_f = _val("debut"), _val("fin"), _val("district")
        if not markdown.strip() or not debut or not fin:
            self._redirige("/rapport-mission")
            return
        districts = perimetre(u)[0]
        if district_f and districts is not None and district_f not in {str(d) for d in districts}:
            district_f = ""
        conn = db_source.connect()
        try:
            if district_f:
                districts_eff = {district_f}
                perim_label = district_f
            else:
                districts_eff = districts
                perim_label = "Tous mes districts" if districts else "Tous les districts"
            # Recompose les stats/graphiques depuis la base (rapide, local, périmètre
            # respecté) — le TEXTE, lui, vient du Markdown reçu.
            rapport = rapport_mission.synthese_locale(conn, debut, fin, districts_eff)
        finally:
            conn.close()
        try:
            data = rapport_word.construire_docx(markdown, rapport, perim_label)
        except Exception as e:
            print(f"[app] erreur génération Word rapport de mission : {e}")
            self._html(rapport_mission.page_ia_erreur(
                f"Échec de la génération Word : {e}", "/rapport-mission"), 500)
            return
        self._octets(
            data,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            rapport_word.nom_fichier(rapport))

    def _journal_get(self, sess):
        """GET /journal : page d'ÉCRITURE (équipe technique) ou de LECTURE
        (coordonnateurs + Admin), selon le rôle. Les autres rôles sont renvoyés
        vers leur espace."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role in _ROLES_JOURNAL_ECRITURE:
            login = sess.get("login") or u.get("login")
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            ok = q.get("ok", [""])[0] == "1"
            maj = q.get("maj", [""])[0] == "1"
            conn = db_source.connect()
            try:
                zone, _codes = _journal_zone(conn, u)
                mes = journal.mes_activites(conn, login)
            finally:
                conn.close()
            msg = ("Votre journal du jour a bien été enregistré." if ok
                   else "Votre entrée de journal a bien été modifiée." if maj
                   else "")
            self._html(page_journal_ecrire(
                u, zone, _codes, journal.aujourdhui(), mes, message=msg))
            return
        if role in _ROLES_JOURNAL_LECTURE:
            districts = perimetre(u)[0]         # None = tout ; set = ses districts
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

            def _val(cle):
                return (q.get(cle, [""])[0] or "").strip()

            district_f = _val("district")
            # Un lecteur multi-district ne peut filtrer que sur SES districts : un
            # district hors périmètre est ignoré (de toute façon `districts` borne
            # déjà les résultats côté journal.activites).
            if district_f and districts is not None:
                perim = {str(d) for d in districts}
                if district_f not in perim:
                    district_f = ""
            fonction_f = _val("fonction")
            zone_f = _val("zone")
            # Le filtre « Axe / Zone de supervision » ne concerne QUE les rôles
            # « district + communes » (Superviseur Technique, Logistique
            # Inter-Communale) et n'a de sens qu'à l'intérieur d'UN district : il
            # n'est actif que si un district ET une de ces fonctions sont choisis.
            axe_actif = bool(district_f) and fonction_f in _ROLES_DISTRICT_COMMUNES
            filtres = {"district": district_f, "fonction": fonction_f,
                       "zone": zone_f if axe_actif else "",
                       "nom": _val("nom"), "date": _val("date")}
            conn = db_source.connect()
            try:
                options = journal.options_lecture(conn, districts=districts)
                # Axes proposés = zones des journaux de CETTE fonction DANS ce district
                # (périmètre respecté). Vide tant que district+fonction non choisis.
                axes = []
                if axe_actif:
                    lignes_axe = journal.activites(
                        conn, districts=districts, district=district_f,
                        fonction=fonction_f)
                    axes = sorted({l["zone"] for l in lignes_axe if l["zone"]})
                options["axes"] = axes
                entrees = journal.activites(
                    conn, districts=districts,
                    date_jour=filtres["date"] or None,
                    district=filtres["district"] or None,
                    fonction=filtres["fonction"] or None,
                    zone=(zone_f if axe_actif else None) or None,
                    nom=filtres["nom"] or None)
            finally:
                conn.close()
            portee = ("Vous consultez tous les journaux de bord des équipes."
                      if districts is None
                      else "Vous consultez les journaux de bord des équipes de vos "
                           "districts affectés.")
            self._html(page_journal_lecture(
                u, entrees, filtres, options, portee, districts))
            return
        # Rôle sans journal (ne devrait pas arriver via le bandeau) -> son espace.
        self._redirige(accueil_role(role))

    def _journal_historique_get(self, sess):
        """GET /journal/historique : TOUTES les entrées de journal écrites par
        l'utilisateur (rôles d'écriture), filtrables par date."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_JOURNAL_ECRITURE:
            self._redirige("/journal")     # lecteurs : pas de journal personnel
            return
        login = sess.get("login") or u.get("login")
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        date_f = (q.get("date", [""])[0] or "").strip()
        conn = db_source.connect()
        try:
            toutes = journal.mes_activites(conn, login, limite=1000000)
        finally:
            conn.close()
        entrees = ([e for e in toutes if e.get("date_jour") == date_f]
                   if date_f else toutes)
        self._html(page_journal_historique(u, entrees, date_f, total=len(toutes)))

    def _journal_modifier_get(self, sess):
        """GET /journal/modifier?id= : formulaire de modification d'UNE de MES
        entrées (rôles d'écriture, propriétaire uniquement)."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_JOURNAL_ECRITURE:
            self._redirige("/journal")
            return
        login = sess.get("login") or u.get("login")
        cid = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
        conn = db_source.connect()
        try:
            e = journal.obtenir_activite(conn, cid, login)
        finally:
            conn.close()
        if not e:
            self._redirige("/journal")       # inconnue / pas à moi
            return
        self._html(page_journal_modifier(u, e))

    def _journal_modifier_post(self):
        """POST /journal/modifier : applique la modification (propriétaire seul).
        `cree_le` reste figé ; `modifie_le` est horodaté."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_JOURNAL_ECRITURE:
            self._html(page_erreur("Modification réservée à l'équipe technique.",
                                   403), 403)
            return
        login = sess.get("login") or u.get("login")
        c = self._corps_formulaire()
        cid = (c.get("id", [""])[0] or "").strip()
        texte = (c.get("journal", [""])[0] or "").strip()
        date_jour = (c.get("date_jour", [""])[0] or "").strip() or journal.aujourdhui()
        if date_jour > journal.aujourdhui():
            date_jour = journal.aujourdhui()
        conn = db_source.connect()
        try:
            e = journal.obtenir_activite(conn, cid, login)
            if not e:
                self._redirige("/journal")
                return
            if not texte:
                e["date_jour"] = date_jour     # conserver la saisie
                self._html(page_journal_modifier(
                    u, e, erreur="Le journal ne peut pas être vide."))
                return
            journal.modifier_activite(conn, cid, login, date_jour, texte)
        finally:
            conn.close()
        self._redirige("/journal?maj=1")

    def _journal_suivi_get(self, sess):
        """GET /journal/suivi : suivi de complétude du journal (Coordonnateurs +
        Admin). Qui a écrit ou non son rapport, par jour, groupé par poste — et par
        DISTRICT puis AXE pour Superviseur Technique / Logistique Inter-Communale.

        Le Coordonnateur National / Admin (zone entière) doit d'abord CHOISIR un
        district (cascade Province→Région→District) ; le Régional voit directement
        ses districts affectés."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_JOURNAL_LECTURE:
            self._redirige(accueil_role(role))
            return
        districts = perimetre(u)[0]              # None (zone entière) ou set
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        district_choisi = (q.get("district", [""])[0] or "").strip()

        if districts is None:
            # National / Admin : choix OBLIGATOIRE d'un district (gère toute la zone).
            if not district_choisi.isdigit():
                self._html(page_journal_suivi_choix(u))
                return
            districts_vue = {int(district_choisi)}
        else:
            districts_vue = {int(x) for x in districts}

        perim = {str(x) for x in districts_vue}
        conn = db_source.connect()
        try:
            membres = []
            for a in utilisateurs.lister(conn):
                if a.get("responsabilite") not in _ROLES_JOURNAL_ECRITURE:
                    continue
                ds = {str(x) for x in (a.get("districts_affectation") or [])}
                if a.get("district_affectation") is not None:
                    ds.add(str(a["district_affectation"]))
                if not (ds & perim):
                    continue
                a["_districts"] = ds
                membres.append(a)
            dates_par_login = journal.dates_ecrites(
                conn, [a["login"] for a in membres])
            cache = {}
            for a in membres:
                if a.get("responsabilite") in _ROLES_DISTRICT_COMMUNES:
                    noms = []
                    for cc in (a.get("communes_affectation") or []):
                        if cc not in cache:
                            cache[cc] = zones.libelle_commune(conn, cc) or str(cc)
                        noms.append(cache[cc])
                    a["communes_noms"] = noms
            # Libellés des districts de la vue (pour les sous-titres par district).
            libs = {}
            for code in districts_vue:
                lib = zones.libelles_district(conn, code)
                libs[str(code)] = (lib[2] if lib else str(code))
        finally:
            conn.close()

        # Colonnes de dates = TOUS les jours de la mission (début → aujourd'hui),
        # y compris les jours où personne n'a écrit -> les manques sont visibles (✗).
        dates = journal.plage_dates(config.DATE_DEBUT_MISSION)

        def _tri_membres(gens):
            return sorted(gens, key=lambda a: (a.get("nom_prenom") or a["login"]))

        # Groupement par poste ; pour les rôles « district + communes » :
        # POSTE -> DISTRICT -> AXE -> membres. Sinon POSTE -> membres.
        groupes = []
        for poste in _ROLES_JOURNAL_ECRITURE:
            gens = [a for a in membres if a.get("responsabilite") == poste]
            if not gens:
                continue
            if poste in _ROLES_DISTRICT_COMMUNES:
                par_district = {}
                for a in gens:
                    # rôle mono-district : district_affectation, sinon 1er du périmètre
                    dcode = (str(a.get("district_affectation"))
                             if a.get("district_affectation") is not None
                             else next(iter(a["_districts"] & perim), ""))
                    par_district.setdefault(dcode, []).append(a)
                blocs = []
                for dcode in sorted(par_district, key=lambda c: libs.get(c, c)):
                    axes = {}
                    for a in par_district[dcode]:
                        noms = a.get("communes_noms") or [
                            str(c) for c in (a.get("communes_affectation") or [])]
                        axes.setdefault(tuple(noms), []).append(a)
                    axes_list = [(", ".join(k) if k else "(sans axe)", _tri_membres(v))
                                 for k, v in sorted(
                                     axes.items(),
                                     key=lambda kv: [n.lower() for n in kv[0]])]
                    blocs.append((libs.get(dcode, dcode), axes_list))
                groupes.append((poste, "district", blocs))
            else:
                groupes.append((poste, "flat", _tri_membres(gens)))

        if districts is None:
            portee = "District : " + libs.get(str(next(iter(districts_vue))), "")
            retour_choix = "/journal/suivi"
        else:
            portee = "Vos districts affectés"
            retour_choix = None
        self._html(page_journal_suivi(
            u, groupes, dates, dates_par_login, portee, retour_choix))

    def _journal_post(self):
        """POST /journal : enregistre UNE entrée de journal (rôles d'écriture)."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_JOURNAL_ECRITURE:
            self._html(page_erreur("Écriture du journal réservée à l'équipe "
                                   "technique.", 403), 403)
            return
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur).decode("utf-8") if longueur else ""
        champs = urllib.parse.parse_qs(corps)
        texte = (champs.get("journal", [""])[0] or "").strip()
        date_jour = (champs.get("date_jour", [""])[0] or "").strip() \
            or journal.aujourdhui()
        # La date ne peut pas être dans le futur (activités DÉJÀ faites).
        if date_jour > journal.aujourdhui():
            date_jour = journal.aujourdhui()
        login = sess.get("login") or u.get("login")
        nom = (u.get("nom_prenom") or login or "").strip()
        conn = db_source.connect()
        try:
            zone, codes = _journal_zone(conn, u)
            if not texte:
                mes = journal.mes_activites(conn, login)
                self._html(page_journal_ecrire(
                    u, zone, codes, journal.aujourdhui(), mes,
                    erreur="Le journal ne peut pas être vide."))
                return
            journal.ecrire_activite(conn, login, nom, role, zone, codes,
                                    date_jour, texte)
        finally:
            conn.close()
        # Une entrée existe désormais pour aujourd'hui -> la bulle de rappel doit
        # disparaître immédiatement (invalider le cache de session).
        if date_jour == journal.aujourdhui():
            sess["_journal_jour"] = date_jour
            sess["_journal_bulle"] = ""
        self._redirige("/journal?ok=1")

    # -----------------------------------------------------------------------
    # Consignes / instructions (Coordonnateurs)
    # -----------------------------------------------------------------------
    def _consignes_get(self, sess):
        """GET /consignes : consignes REÇUES par l'utilisateur (marquées lues à
        l'ouverture -> la bulle disparaît). Tous rôles. Filtres d'AFFICHAGE
        (facultatifs) : poste + nom de l'émetteur, date d'émission."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        login = sess.get("login") or u.get("login")
        districts = perimetre(u)[0]
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

        def _val(cle):
            return (q.get(cle, [""])[0] or "").strip()

        filtres = {"poste": _val("poste"), "nom": _val("nom"), "date": _val("date")}
        conn = db_source.connect()
        try:
            # On récupère TOUTES les consignes adressées (pour marquer lues -> la
            # bulle se vide), et on filtre seulement l'AFFICHAGE.
            recues = consignes.pour_utilisateur(conn, login, role, districts)
            consignes.marquer_toutes_lues(conn, login, role, districts)
        finally:
            conn.close()
        nom_f = filtres["nom"].lower()
        vues = [c for c in recues
                if (not filtres["poste"] or c.get("auteur_role") == filtres["poste"])
                and (not filtres["date"]
                     or (c.get("cree_le") or "")[:10] == filtres["date"])
                and (not nom_f or nom_f in (c.get("auteur_nom") or "").lower())]
        # Vues -> invalider le cache de la bulle (plus de non-lues).
        sess["_consignes_n"] = 0
        sess["_consignes_ck"] = time.time()
        self._html(page_consignes_recues(
            u, vues, est_emetteur=role in _ROLES_CONSIGNE_ENVOI, filtres=filtres))

    def _consignes_nouvelle_get(self, sess):
        """GET /consignes/nouvelle : page de rédaction (Coordonnateurs seulement)."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_CONSIGNE_ENVOI:
            self._redirige("/consignes")       # non-émetteur -> ses consignes reçues
            return
        login = sess.get("login") or u.get("login")
        districts_perim = perimetre(u)[0]
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        msg = {"ok": "Votre consigne a bien été envoyée.",
               "supprime": "La consigne a été supprimée.",
               "modifie": "La consigne a été modifiée."}
        message = next((m for cle, m in msg.items()
                        if q.get(cle, [""])[0] == "1"), "")
        conn = db_source.connect()
        try:
            envoyees = consignes.envoyees_par(conn, login)
        finally:
            conn.close()
        self._html(page_consignes_nouvelle(
            u, envoyees, districts_perim, message=message))

    def _consignes_cibles(self, champs, districts_perim):
        """Lit + valide le formulaire de consigne. Renvoie (titre, message,
        roles_cibles, districts_cibles, erreur|None). Le Régional est borné à SES
        districts (sélection filtrée ; « tous » = tous les siens, pas 'TOUS')."""
        titre = (champs.get("titre", [""])[0] or "").strip()
        message = (champs.get("message", [""])[0] or "").strip()
        roles_tous = champs.get("roles_tous", [""])[0] == "1"
        districts_tous = champs.get("districts_tous", [""])[0] == "1"
        roles_sel = [r for r in champs.get("roles", []) if r in _ROLES_CONSIGNE_CIBLES]
        districts_sel = [d for d in champs.get("districts", []) if d.isdigit()]
        if districts_perim is not None:
            perim = {str(x) for x in districts_perim}
            districts_sel = [d for d in districts_sel if d in perim]
        if not message:
            return (titre, message, None, None,
                    "Le message de la consigne ne peut pas être vide.")
        if not roles_tous and not roles_sel:
            return (titre, message, None, None,
                    "Choisissez au moins un rôle destinataire (ou « Tout le monde »).")
        if not districts_tous and not districts_sel:
            return (titre, message, None, None,
                    "Choisissez au moins un district (ou « Tous les districts »).")
        roles_cibles = consignes.TOUS if roles_tous else roles_sel
        if districts_tous:
            districts_cibles = (consignes.TOUS if districts_perim is None
                                else sorted(str(x) for x in districts_perim))
        else:
            districts_cibles = districts_sel
        return (titre, message, roles_cibles, districts_cibles, None)

    @staticmethod
    def _edition_depuis_form(champs, cid):
        """Reconstruit un dict `edition` depuis le formulaire soumis (pour ré-afficher
        le formulaire de MODIFICATION sans perdre la saisie en cas d'erreur)."""
        roles_tous = champs.get("roles_tous", [""])[0] == "1"
        districts_tous = champs.get("districts_tous", [""])[0] == "1"
        roles = (consignes.TOUS if roles_tous else "|".join(
            r for r in champs.get("roles", []) if r in _ROLES_CONSIGNE_CIBLES))
        dists = (consignes.TOUS if districts_tous else ",".join(
            d for d in champs.get("districts", []) if d.isdigit()))
        return {"id": cid, "titre": (champs.get("titre", [""])[0] or "").strip(),
                "message": (champs.get("message", [""])[0] or "").strip(),
                "roles_cibles": roles, "districts_cibles": dists}

    def _consignes_nouvelle_post(self):
        """POST /consignes/nouvelle : enregistre une consigne (Coordonnateurs)."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_CONSIGNE_ENVOI:
            self._html(page_erreur("Rédaction réservée aux coordonnateurs.", 403), 403)
            return
        login = sess.get("login") or u.get("login")
        nom = (u.get("nom_prenom") or login or "").strip()
        districts_perim = perimetre(u)[0]
        champs = self._corps_formulaire()
        titre, message, roles_cibles, districts_cibles, err = self._consignes_cibles(
            champs, districts_perim)
        conn = db_source.connect()
        try:
            if err:
                self._html(page_consignes_nouvelle(
                    u, consignes.envoyees_par(conn, login), districts_perim,
                    erreur=err))
                return
            consignes.envoyer(conn, login, nom, role, roles_cibles,
                              districts_cibles, titre, message)
        finally:
            conn.close()
        self._redirige("/consignes/nouvelle?ok=1")

    def _consignes_modifier_get(self, sess):
        """GET /consignes/modifier?id= : formulaire pré-rempli (auteur seulement)."""
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_CONSIGNE_ENVOI:
            self._redirige("/consignes")
            return
        login = sess.get("login") or u.get("login")
        cid = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query).get("id", [""])[0]
        districts_perim = perimetre(u)[0]
        conn = db_source.connect()
        try:
            ed = consignes.obtenir(conn, cid)
            if not ed or ed.get("auteur_login") != login:
                self._redirige("/consignes/nouvelle")   # inconnue / pas l'auteur
                return
            envoyees = consignes.envoyees_par(conn, login)
        finally:
            conn.close()
        self._html(page_consignes_nouvelle(
            u, envoyees, districts_perim, edition=ed))

    def _consignes_modifier_post(self):
        """POST /consignes/modifier : applique la modification (auteur seulement)."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_CONSIGNE_ENVOI:
            self._html(page_erreur("Action réservée aux coordonnateurs.", 403), 403)
            return
        login = sess.get("login") or u.get("login")
        districts_perim = perimetre(u)[0]
        champs = self._corps_formulaire()
        cid = (champs.get("id", [""])[0] or "").strip()
        titre, message, roles_cibles, districts_cibles, err = self._consignes_cibles(
            champs, districts_perim)
        conn = db_source.connect()
        try:
            if err:
                self._html(page_consignes_nouvelle(
                    u, consignes.envoyees_par(conn, login), districts_perim,
                    erreur=err, edition=self._edition_depuis_form(champs, cid)))
                return
            ok = consignes.modifier(conn, cid, login, roles_cibles,
                                    districts_cibles, titre, message)
        finally:
            conn.close()
        self._redirige("/consignes/nouvelle?modifie=1" if ok
                       else "/consignes/nouvelle")

    def _consignes_supprimer_post(self):
        """POST /consignes/supprimer : retire une consigne (auteur uniquement)."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        u = (sess or {}).get("utilisateur") or {}
        role = (u.get("responsabilite") or "").strip()
        if role not in _ROLES_CONSIGNE_ENVOI:
            self._html(page_erreur("Action réservée aux coordonnateurs.", 403), 403)
            return
        cid = (self._corps_formulaire().get("id", [""])[0] or "").strip()
        login = sess.get("login") or u.get("login")
        supprime = False
        if cid:
            conn = db_source.connect()
            try:
                supprime = consignes.supprimer(conn, cid, login)
            finally:
                conn.close()
        self._redirige("/consignes/nouvelle?supprime=1" if supprime
                       else "/consignes/nouvelle")

    def _menu_operation_get(self, sess, u, role, op):
        """Menu d'opération des rôles de _ROLES_MENU_OPERATION (Coordonnateurs +
        Superviseur Technique) et son aiguillage selon l'opération choisie.

        - op vide / inconnue  -> affiche le menu (Dénombrement / VAD / Équipe technique).
        - Superviseur (district FIXE) : va DIRECTEMENT au résultat
            (den/vad -> /suivi de son district ; equipe -> /equipe).
        - Coordonnateurs (district à choisir) : ouvre la page de sélection avec
            l'opération déjà fixée (page_selection(op=...)). Le district reste borné
            par perimetre() à la validation du POST.

        La Visite à domicile (op=vad) est un choix À PART ENTIÈRE : elle mène au
        /suivi qui, faute de données VAD, affiche « pas encore disponible » (le vrai
        tableau de bord VAD sera branché plus tard)."""
        if op not in ("den", "vad", "equipe"):
            self._html(page_menu_operation(role, u))
            return
        districts_perim = perimetre(u)[0]
        fixe = districts_perim is not None and len(districts_perim) == 1
        if fixe:
            if op == "equipe":
                self._redirige("/equipe")       # fiche équipe de son district
                return
            # Tableau de bord (dénombrement OU VAD) : district imposé -> on prépare
            # la sélection et on ouvre /suivi (den -> vue générale ; vad -> page
            # « pas encore disponible »).
            code = sorted(districts_perim)[0]
            conn = db_source.connect()
            try:
                libs = zones.libelles_district(conn, code)
            finally:
                conn.close()
            if not libs:
                self._html(page_erreur("District inconnu dans le référentiel.", 400), 400)
                return
            province_nom, region_nom, district_nom = libs
            with _SESSIONS_LOCK:
                sess["selection"] = {
                    "code_district": int(code), "province_nom": province_nom,
                    "region_nom": region_nom, "district_nom": district_nom,
                    "limites": "ocha", "chemin_limites": "", "suivi": op}
            self._redirige("/suivi")
            return
        # Coordonnateurs : choix du district, opération déjà fixée.
        self._html(page_selection(utilisateur=u, op=op))

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
                kw["numero_orange_float"] = g("numero_orange_float") or None
                kw["sexe"] = g("sexe") or None
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
                kw["numero_orange_float"] = g("numero_orange_float") or None
                kw["sexe"] = g("sexe") or None
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

    def _traiter_motdepasse(self):
        """Change le mot de passe de l'utilisateur CONNECTÉ (self-service).

        Vérifie l'ancien mot de passe, applique une politique minimale (longueur,
        confirmation, différent de l'actuel), puis met à jour le condensé. Ne touche
        qu'à SON propre compte (login pris de la session, jamais du formulaire)."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        login = sess.get("login") or (sess.get("utilisateur") or {}).get("login")
        champs = self._corps_formulaire()
        ancien = champs.get("ancien", [""])[0]
        nouveau = champs.get("nouveau", [""])[0]
        confirme = champs.get("confirme", [""])[0]

        conn = db_source.connect()
        try:
            # 1) L'ancien mot de passe doit être correct (compte forcément actif ici).
            if not login or utilisateurs.authentifier(conn, login, ancien) is None:
                self._html(page_motdepasse(
                    "Le mot de passe actuel est incorrect.", sess=sess), 400)
                return
            # 2) Politique minimale sur le nouveau.
            if len(nouveau) < MDP_MIN:
                self._html(page_motdepasse(
                    f"Le nouveau mot de passe doit faire au moins {MDP_MIN} "
                    "caractères.", sess=sess), 400)
                return
            if nouveau != confirme:
                self._html(page_motdepasse(
                    "La confirmation ne correspond pas au nouveau mot de passe.",
                    sess=sess), 400)
                return
            if nouveau == ancien:
                self._html(page_motdepasse(
                    "Le nouveau mot de passe doit être différent de l'actuel.",
                    sess=sess), 400)
                return
            # 3) Application.
            utilisateurs.changer_mot_de_passe(conn, login, nouveau)
            conn.commit()
        finally:
            conn.close()
        print(f"[app] mot de passe modifié par l'utilisateur : {login}")
        self._html(page_motdepasse(succes=True, sess=sess))

    # -----------------------------------------------------------------------
    # « Mon profil » (self-service, tous les rôles)
    # -----------------------------------------------------------------------
    def _profil_login(self, sess):
        return sess.get("login") or (sess.get("utilisateur") or {}).get("login")

    def _profil_page(self, conn, login, message="", erreur=""):
        u = utilisateurs.obtenir(conn, login)
        if u is None:
            return page_erreur("Compte introuvable.", 400)
        aff = utilisateurs.affectation_texte(
            conn, u.get("district_affectation"), u.get("communes_affectation"),
            u.get("districts_affectation"))
        return page_profil(u, aff, message=message, erreur=erreur)

    def _profil_get(self, sess):
        login = self._profil_login(sess)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        ok = q.get("ok", [""])[0] == "1"
        conn = db_source.connect()
        try:
            html = self._profil_page(
                conn, login,
                message=("Vos informations ont bien été enregistrées." if ok else ""))
        finally:
            conn.close()
        self._html(html)

    def _traiter_profil(self):
        """Met à jour les infos PERSONNELLES de l'utilisateur CONNECTÉ (CIN,
        téléphone, N° Orange/Float, e-mail, sexe). Login pris de la SESSION, jamais
        du formulaire ; le rôle/affectation/login ne sont pas touchés."""
        sess = _session(self)
        if sess is None:
            self._redirige("/login")
            return
        login = self._profil_login(sess)
        c = self._corps_formulaire()
        g = lambda k: (c.get(k, [""])[0] or "").strip()
        conn = db_source.connect()
        try:
            try:
                utilisateurs.modifier_profil(
                    conn, login,
                    telephone=g("telephone") or None,
                    cin=g("cin") or None,
                    email=g("email") or None,
                    numero_orange_float=g("numero_orange_float") or None,
                    sexe=g("sexe") or None)
            except ValueError as e:
                self._html(self._profil_page(conn, login,
                                             erreur=htmllib.escape(str(e))), 400)
                return
        finally:
            conn.close()
        print(f"[app] profil mis à jour par l'utilisateur : {login}")
        self._redirige("/profil?ok=1")

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
        suivi = (champs.get("suivi", [""])[0]).strip()
        # Rôle à menu : l'opération (suivi) vient du menu et voyage dans un champ
        # caché -> on la repasse à page_selection sur ré-affichage d'erreur, pour
        # que le formulaire de district conserve l'opération choisie.
        op_form = suivi if u.get("responsabilite") in _ROLES_MENU_OPERATION else None
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
                    utilisateur=u, op=op_form), 400)
                return
        limites = (champs.get("limites", ["ocha"])[0]).strip()
        chemin_lim = (champs.get("chemin_limites", [""])[0]).strip()

        # Validation.
        if not district.isdigit():
            self._html(page_selection("Veuillez choisir un district.",
                                      utilisateur=u, op=op_form), 400)
            return
        # « equipe » (fiche encadrement du district) : proposé aux rôles à menu
        # (Coordonnateurs + Superviseur Technique), chacun sur SON périmètre (borné
        # par la validation zone ci-dessus).
        suivis_ok = ("den", "vad")
        if u.get("responsabilite") in _ROLES_MENU_OPERATION:
            suivis_ok = ("den", "vad", "equipe")
        if suivi not in suivis_ok:
            self._html(page_selection("Veuillez choisir un type de suivi.",
                                      utilisateur=u, op=op_form), 400)
            return
        if limites not in ("ocha", "generer", "dossier"):
            limites = "ocha"
        if limites == "dossier" and not chemin_lim:
            self._html(page_selection(
                "Veuillez indiquer le chemin du dossier de limites.",
                utilisateur=u, op=op_form), 400)
            return

        # Libellés depuis le référentiel (source de vérité) plutôt que le POST.
        conn = db_source.connect()
        try:
            libs = zones.libelles_district(conn, district)
        finally:
            conn.close()
        if not libs:
            self._html(page_selection("District inconnu dans le référentiel.",
                                      utilisateur=u, op=op_form), 400)
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
    # Réutiliser l'adresse : redémarrage immédiat même si le port est en TIME_WAIT.
    socketserver.ThreadingTCPServer.allow_reuse_address = True
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
