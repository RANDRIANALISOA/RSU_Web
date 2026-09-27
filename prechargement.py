# -*- coding: utf-8 -*-
"""
prechargement.py — Génération web de la BASE DE PRÉCHARGEMENT (VAD).

Portage WEB de `..\\RSU_Rapport\\base_prechargement.py` : produit le même classeur
Excel **base_prechargement_<version>.xlsx** (3 feuilles : Ensemble / nouveau /
e_fokontany) ET le fichier **charge_agents_<version>.xlsx** (récapitulatif de la
charge par agent), avec le MÊME équilibrage de charge (`affectation_agents.py`,
copié depuis le projet exe). Les deux fichiers sont renvoyés dans une archive ZIP.

DIFFÉRENCE ESSENTIELLE avec la version exe : les données ne sont pas lues dans des
`.dta` mais dans la **base SQL** (via `db_source.DbDataset`), filtrées sur le
district d'affectation de l'Expert « Traitement ».

GÉOGRAPHIE : DEUX formats au choix — codes OU libellés (journal 2026-09-26)
--------------------------------------------------------------------------
La base de préchargement se génère ET se retélécharge dans DEUX formats
(`format_geo` = 'code' ou 'libelle', cf. `_rendre_geo`) ; le choix est offert à la
génération et, pour chaque lot déjà enregistré, à l'historique (deux boutons) :

    format 'code'      region 52 / district 5201 / commune 520109 / fokontany 52010904
    format 'libelle'   region ANALANJIROFO / district FENERIVE EST /
                       commune MIORIMIVALANA / fokontany MIORIMIVALANA_52010904

Seules ces 4 colonnes changent. DANS LES DEUX CAS :
  • `fkt_recherche` = **nom** du fokontany (champ de recherche par libellé) ;
  • le fichier `charge_agents_<version>.xlsx` affiche les **noms** de commune/
    fokontany (résumé RH lisible), via les méta internes `_com` / `_fktnom`.

Le REGISTRE stocke la forme canonique (colonnes en CODES + `code_fokontany` en méta) ;
`_rendre_geo` dérive tout du **code fokontany 8 chiffres** (`_fkt_code` /
`code_fokontany`), donc un lot se retélécharge indifféremment en codes ou en libellés,
y compris les lots créés avant cette évolution (dont les colonnes portaient des
libellés). Les codes restent lus dans `den_menage` (ou déduits par `_codes_hierarchie`).

CE / ENQ : deux sources, dans cet ordre
---------------------------------------
  • ENQ (agent enquêteur) = `interview__diagnostics.responsible` (CODE agent),
    joint aux ménages par `interview__key` ;
  • CE (chef d'équipe) = `base_login_ce.dta` du dossier téléversé du district
    (`interview__key` -> `responsible__name`, rôle 2) — la SOURCE directe ;
    à défaut, le chef de l'agent via les tables `equipes` (`agent.login_ce`).
    Ce repli ne suffisait pas : `agent.login_ce` est vide pour 3 867 des 4 422
    agents (les agents *découverts à l'ingestion des diagnostics* n'ont que leur
    code, cf. journal 2026-09-22), et la colonne CE sortait donc vide.
CE et ENQ portent TOUJOURS des CODES (le nom reste le libellé côté base /
rapport, jamais dans ces colonnes).

L'unité indéplaçable de l'équilibrage reste l'`interview__key` (une visite de
dénombrement = un seul agent, ~quelques dizaines de ménages), exactement comme dans
le programme exe. Après équilibrage, l'ENQ change mais le CE d'origine est conservé.

⚠️ QUESTIONNAIRE DE SEPTEMBRE 2026 : `ID_efkt` (scan du carnet e-Fokontany) et
`num_fkt` ont disparu. Lus par `_col_opt` (colonne absente -> None) : tous les
ménages partent donc en « nouveau » et la feuille **e_fokontany est VIDE**
(Ensemble == nouveau). Comportement attendu tant que le carnet n'est pas recollecté.

REGISTRE (maj 2026-09-22, transposition du do-file « RSU VAGUE 2 -
PRECHARGEMENT ») : chaque sortie est un LOT enregistré en base (tables
`prechargement_lot` / `_ensemble` / `_nouveau` / `_efokontany`) ; un ménage
préchargé une fois n'est jamais renvoyé. On ne téléverse plus les anciens
fichiers pour les exclure. Seules les interviews terminées ou approuvées
(statuts 100/120/130) sont préchargées, et l'on peut restreindre une sortie à
certains fokontany. Voir la section « REGISTRE » ci-dessous.

Bibliothèque standard + openpyxl (déjà utilisé partout dans le web).
"""
from __future__ import annotations

import io
import os
import statistics
import urllib.parse
import zipfile
from collections import Counter
from datetime import datetime

import config
import db_source
import equipes
import zones
from affectation_agents import equilibrer_charge
from rapport_core import ErreurDonnees, _log_noop


# ---------------------------------------------------------------------------
# Colonnes exportées par feuille (ordre = fichier de référence, cf. exe)
# ---------------------------------------------------------------------------
COLS_ENSEMBLE = [
    "interview__key", "region", "district", "commune", "fokontany",
    "fkt_recherche", "nom_cm", "IdeFKT", "taille_men", "adresse", "description",
    "gps_coord__Latitude", "gps_coord__Longitude", "code_den",
    "CE", "ENQ", "interview_keyden",
]
COLS_EFOKONTANY = COLS_ENSEMBLE
# `IdeFKT_recherche` ne figure PAS dans le fichier de référence (19 colonnes,
# journal 2026-09-22) : la colonne a été retirée pour s'y conformer.
COLS_NOUVEAU = [
    "interview__key", "region", "district", "commune", "fokontany",
    "fkt_recherche", "nom_cm", "taille_men", "CQ17_preload", "description",
    "GPS_Lat_ZD", "GPS_Long_ZD", "code_den", "_responsible", "_quantity",
    "typemen", "mode_enreg", "nom_projet", "interview_keyden",
]

# Modes d'affectation acceptés (mêmes clés que le programme exe).
MODES = ("denombrement", "equilibre", "equilibre_fort")
LIBELLE_MODE = {
    "denombrement": "Dénombrement (aucune redistribution)",
    "equilibre": "Équilibré (±10 %, agents groupés)",
    "equilibre_fort": "Équilibré fort (échanges ; un agent peut changer de fokontany)",
}

# Format géographique de la sortie (journal 2026-09-26) : les 4 colonnes
# region/district/commune/fokontany du fichier de préchargement sont écrites soit en
# CODES, soit en LIBELLÉS. `fkt_recherche` (recherche par nom) et le fichier
# charge_agents restent en NOMS dans les DEUX cas. Le registre stocke toujours les
# CODES (valeur canonique) : chaque lot peut donc être retéléchargé dans l'un ou
# l'autre format à tout moment.
FORMATS_GEO = ("code", "libelle")
LIBELLE_FORMAT = {"code": "Codes", "libelle": "Libellés"}


def _format_ok(f) -> str:
    """Normalise le format géographique demandé (défaut : 'code')."""
    f = (f or "code").strip().lower()
    return f if f in FORMATS_GEO else "code"


# ---------------------------------------------------------------------------
# Helpers d'apurement (identiques au programme exe base_prechargement.py)
# ---------------------------------------------------------------------------
def _est_na(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() in ("", "##N/A##"))


def _sans_na(v) -> str:
    return "" if _est_na(v) else str(v)


def _col_opt(d, nom, defaut=None) -> list:
    """Colonne OPTIONNELLE d'un dataset : la colonne, ou une colonne a `defaut`.

    Le questionnaire de septembre 2026 a retire `ID_efkt` (scan du carnet
    e-Fokontany) et `num_fkt`. Indispensable de passer par ici : `DbDataset.col`
    fabrique un `SELECT "<nom>"`, et SQLite, faute de colonne de ce nom, retombe
    sur une CHAINE LITTERALE -> la colonne vaut le texte « ID_efkt » partout, sans
    la moindre erreur (et PostgreSQL, lui, echouerait franchement).
    """
    return d.col(nom) if nom in d.varnames else [defaut] * d.nobs


def _nettoyer_idefkt(raw) -> str:
    """ID_efkt -> code du carnet e-fokontany, ou '' (reproduit le dofile)."""
    s = "" if raw is None else str(raw)
    if len(s) > 80:
        i = s.find("|")
        if i >= 0:
            s = s[i + 1:].strip()
    if len(s) < 15:
        s = ""
    return s


def _gps_num(v):
    """Coordonnée GPS -> float exploitable, ou None (manquante/nulle)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f == 0 else f


def _gps_txt(v) -> str:
    """Coordonnée GPS -> texte ('' si manquante ou nulle)."""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _sans_na(v)
    if f == 0:
        return ""
    return repr(round(f, 8))


def _int(v):
    """Code géographique -> int, ou None (valeur textuelle, « ##N/A## », vide)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _libelles_zones(conn, code_district: int) -> dict:
    """Libellés du référentiel `zones` pour CE district (une requête par niveau).

    {'region': 'ANALANJIROFO', 'district': 'FENERIVE EST',
     'communes': {520101: 'AMBATOHARANANA', …},
     'fokontany': {52010101: 'AMBODIHASINA_52010101', …}}

    Le référentiel est préféré aux value labels du questionnaire : mêmes valeurs
    (vérifié sur FENERIVE EST), mais il ne dépend pas de la version du
    questionnaire téléversé, et il couvre les 20 256 fokontany du pays."""
    lib = zones.libelles_district(conn, int(code_district))
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "code_commune", "nom" FROM "commune" '
                f'WHERE "code_district" = {ph}', (int(code_district),))
    communes = {_int(c): n for c, n in cur.fetchall() if _int(c) is not None}
    cur.execute(f'SELECT f."code_fokontany", f."nom" FROM "fokontany" f '
                f'JOIN "commune" c ON c."code_commune" = f."code_commune" '
                f'WHERE c."code_district" = {ph}', (int(code_district),))
    fokontany = {_int(c): n for c, n in cur.fetchall() if _int(c) is not None}
    return {"region": (lib[1] if lib else ""),
            "district": (lib[2] if lib else ""),
            "communes": communes, "fokontany": fokontany}


# Fichier de l'export Survey Solutions qui porte le LOGIN DU CHEF D'ÉQUIPE
# (rôle 2) par interview. Il n'est pas transcrit en base (il ne fait pas partie de
# `db_source.FICHIERS`) mais il reste dans le dossier téléversé du district.
FICHIER_CE = "base_login_ce.dta"
ROLE_CE = 2


def _ce_du_dossier(code_district: int, log) -> dict:
    """{interview__key: login CE} lu dans `base_login_ce.dta` du dossier du district.

    Renvoie {} si le fichier est absent ou illisible — l'appelant retombe alors sur
    `agent.login_ce`. On filtre sur `responsible__role == 2` quand la colonne est
    là : le fichier ne contient en principe que des chefs d'équipe, mais s'il
    arrive un export mêlant les rôles, un login d'ENQUÊTEUR dans la colonne CE
    passerait inaperçu."""
    dossier = os.path.join(config.UPLOAD_DIR, str(int(code_district)))
    chemin = os.path.join(dossier, FICHIER_CE)
    if not os.path.isfile(chemin):
        log(f"   CE : {FICHIER_CE} absent du dossier televerse "
            f"-> repli sur agent.login_ce")
        return {}
    try:
        from lire_dta import lire_dta
        d = lire_dta(chemin)
        if "interview__key" not in d.varnames or "responsible__name" not in d.varnames:
            log(f"   CE : {FICHIER_CE} sans interview__key/responsible__name "
                f"-> repli sur agent.login_ce")
            return {}
        cles = d.col("interview__key")
        noms = d.col("responsible__name")
        roles = d.col("responsible__role") if "responsible__role" in d.varnames \
            else [ROLE_CE] * d.nobs
        out = {}
        for i, k in enumerate(cles):
            if not k or k in out:
                continue
            if _int(roles[i]) not in (None, ROLE_CE):
                continue
            ce = _sans_na(noms[i])
            if ce:
                out[k] = ce
        log(f"   CE : {len(out)} interview(s) rattachees a un chef d'equipe "
            f"({FICHIER_CE})")
        return out
    except Exception as e:
        log(f"   CE : {FICHIER_CE} illisible ({type(e).__name__}) "
            f"-> repli sur agent.login_ce")
        return {}


def _codes_hierarchie(code8, reg_brut, dis_brut, com_brut):
    """Code fokontany (8 chiffres) -> (region, district, commune, fokontany)."""
    try:
        c = int(code8)
    except (TypeError, ValueError):
        c = None
    if c and c >= 1_000_000:
        return (c // 1_000_000, c // 10_000, c // 100, c)
    return (reg_brut, dis_brut, com_brut, code8)


# ---------------------------------------------------------------------------
# REGISTRE des ménages déjà préchargés (tables en base)
# ---------------------------------------------------------------------------
# Transposition de l'étape 7 du do-file « RSU VAGUE 2 - PRECHARGEMENT » : un
# ménage envoyé UNE fois n'est JAMAIS renvoyé. Le do-file tient ce registre dans
# `5_REGISTRE/MENAGES_DEJA_ENVOYES_<district>.dta` ; ici, il vit dans la base,
# en trois tables qui reprennent À L'IDENTIQUE les trois feuilles du classeur,
# plus un journal des sorties (`prechargement_lot`) :
#
#   prechargement_lot         une ligne par fichier généré (date, auteur, mode,
#                             fokontany retenus, effectifs)
#   prechargement_ensemble    feuille « Ensemble »     } une ligne par ménage,
#   prechargement_nouveau     feuille « nouveau »      } clé = interview_keyden,
#   prechargement_efokontany  feuille « e_fokontany »  } rattachée à son lot
#
# `Ensemble` contient TOUS les ménages envoyés (= nouveau + e_fokontany) : c'est
# lui qui fait foi pour l'exclusion. Les deux autres sont gardées pour pouvoir
# reproduire le classeur envoyé tel quel (téléchargement d'un lot, ou du total).
#
# Les ménages sont inscrits AU MOMENT DE LA GÉNÉRATION, dans la même transaction
# que le lot : un fichier généré est un fichier envoyé (règle du do-file :
# « Chaque fichier créé doit être envoyé »). Une erreur de génération ne laisse
# donc rien au registre ; un lot généré par erreur s'ANNULE (le dernier seulement).
#
# Les téléversements de « préchargements déjà générés » (ancienne exclusion par
# fichier Excel) n'ont plus lieu d'être et ont été retirés.
CLE_MENAGE = "interview_keyden"
T_LOT = "prechargement_lot"
T_FEUILLES = (("Ensemble", "prechargement_ensemble", COLS_ENSEMBLE),
              ("nouveau", "prechargement_nouveau", COLS_NOUVEAU),
              ("e_fokontany", "prechargement_efokontany", COLS_EFOKONTANY))
# Méta stockées avec chaque ménage (hors classeur) : le lot, la clé géographique
# (pour le choix des fokontany), le segment (pour la charge par agent) et le
# rang de la ligne dans le fichier (pour le reproduire dans le même ordre).
_META = ("lot_id", "code_district", "code_fokontany", "segment", "rang")
_COLS_ENTIERES = {"code_district", "code_fokontany", "taille_men", "_quantity",
                  "typemen", "mode_enreg", "nom_projet", "rang"}

# Statuts Survey Solutions retenus (do-file, étape 5.1) : 100 = Completed,
# 120 = ApprovedBySupervisor, 130 = ApprovedByHeadquarters. Une interview
# rejetée n'entre PAS au registre : elle sera préchargée à une sortie
# ultérieure, une fois corrigée et approuvée.
STATUTS_OK = (100, 120, 130)


def creer_tables(conn) -> None:
    """Crée les tables du registre si elles sont absentes (idempotent)."""
    cur = conn.cursor()
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{T_LOT}" ('
                '"lot_id" TEXT PRIMARY KEY, "code_district" INTEGER NOT NULL, '
                '"cree_le" TEXT NOT NULL, "login" TEXT, "nom_prenom" TEXT, '
                '"mode" TEXT, "fokontany" TEXT, "nb_ensemble" INTEGER, '
                '"nb_nouveau" INTEGER, "nb_efokontany" INTEGER, "version" TEXT)')
    for _titre, table, cols in T_FEUILLES:
        defs = []
        for c in _META + tuple(cols):
            if c == CLE_MENAGE:
                defs.append(f'"{c}" TEXT PRIMARY KEY')
            elif c in _COLS_ENTIERES:
                defs.append(f'"{c}" INTEGER')
            else:
                defs.append(f'"{c}" TEXT')
        cur.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(defs)})')
        cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_lot" '
                    f'ON "{table}" ("lot_id")')
        cur.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_district" '
                    f'ON "{table}" ("code_district")')
    conn.commit()


def registre(conn, code_district: int) -> set:
    """interview_keyden déjà préchargés pour ce district (feuille Ensemble)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "{CLE_MENAGE}" FROM "prechargement_ensemble" '
                f'WHERE "code_district" = {ph}', (int(code_district),))
    return {r[0] for r in cur.fetchall() if r[0]}


def lots(conn, code_district: int) -> list:
    """Les sorties du district, de la plus ancienne à la plus récente, numérotées."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "lot_id", "cree_le", "login", "nom_prenom", "mode", '
                f'"fokontany", "nb_ensemble", "nb_nouveau", "nb_efokontany", '
                f'"version" FROM "{T_LOT}" WHERE "code_district" = {ph} '
                f'ORDER BY "cree_le", "lot_id"', (int(code_district),))
    cles = ("lot_id", "cree_le", "login", "nom_prenom", "mode", "fokontany",
            "nb_ensemble", "nb_nouveau", "nb_efokontany", "version")
    out = [dict(zip(cles, r)) for r in cur.fetchall()]
    for i, lot in enumerate(out, 1):
        lot["numero"] = i
    return out


def lot(conn, code_district: int, lot_id: str):
    """Le lot demandé, s'il appartient bien à CE district (sinon None)."""
    for x in lots(conn, code_district):
        if x["lot_id"] == lot_id:
            return x
    return None


def _enregistrer(conn, code_district, lot_id, version, u, mode, fkt_choisis,
                 ensemble, nouveau, efokontany) -> None:
    """Inscrit le lot et ses ménages au registre (SANS commit : l'appelant clôt)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    fkt_txt = ("TOUS" if not fkt_choisis
               else ",".join(str(c) for c in sorted(fkt_choisis)))
    cur.execute(f'INSERT INTO "{T_LOT}" ("lot_id", "code_district", "cree_le", '
                f'"login", "nom_prenom", "mode", "fokontany", "nb_ensemble", '
                f'"nb_nouveau", "nb_efokontany", "version") VALUES '
                f'({",".join([ph] * 11)})',
                (lot_id, int(code_district),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 (u or {}).get("login"), (u or {}).get("nom_prenom"), mode,
                 fkt_txt, len(ensemble), len(nouveau), len(efokontany), version))
    for (_titre, table, cols), lignes in zip(
            T_FEUILLES, (ensemble, nouveau, efokontany)):
        if not lignes:
            continue
        noms = _META + tuple(cols)
        sql = (f'INSERT INTO "{table}" ({", ".join(chr(34) + c + chr(34) for c in noms)}) '
               f'VALUES ({",".join([ph] * len(noms))})')
        vals = []
        for rang, r in enumerate(lignes, 1):
            meta = (lot_id, int(code_district), r.get("_fkt_code"), r.get("_seg"),
                    rang)
            v = []
            for c in cols:
                x = r.get(c, "")
                if c in _COLS_ENTIERES:
                    x = _int(x)
                v.append(x)
            vals.append(meta + tuple(v))
        cur.executemany(sql, vals)


def _lignes_registre(conn, code_district, lot_id=None) -> tuple:
    """(ensemble, nouveau, efokontany) relus du registre, prêts pour l'écriture
    des classeurs (colonnes du fichier + méta `_com`/`_fktnom`/`_seg` de la charge)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    out = []
    for _titre, table, cols in T_FEUILLES:
        noms = ("segment", "code_fokontany") + tuple(cols)
        where = '"code_district" = ' + ph
        params = [int(code_district)]
        if lot_id:
            where += ' AND "lot_id" = ' + ph
            params.append(lot_id)
        cur.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in noms)} '
                    f'FROM "{table}" WHERE {where} '
                    f'ORDER BY "lot_id", "rang"', params)
        lignes = []
        for row in cur.fetchall():
            r = {c: ("" if v is None else v) for c, v in zip(noms, row)}
            r["_seg"] = r.pop("segment")
            r["_fkt_code"] = _int(r.pop("code_fokontany"))   # clé géo (méta registre)
            r["_com"] = r.get("commune", "")
            r["_fktnom"] = str(r.get("fokontany", ""))
            if "_responsible" in r and "ENQ" not in r:
                r["ENQ"] = r["_responsible"]
            lignes.append(r)
        out.append(lignes)
    return tuple(out)


def zip_lot(conn, code_district: int, lot_id: str, format_geo="code"):
    """Reconstitue le ZIP d'un lot (préchargement + charge par agent). Le format
    géographique (`format_geo` = 'code' ou 'libelle') est appliqué à la relecture du
    registre : un même lot se retélécharge en CODES ou en LIBELLÉS. (nom, octets)
    ou None."""
    x = lot(conn, code_district, lot_id)
    if x is None:
        return None
    fmt = _format_ok(format_geo)
    ensemble, nouveau, efokontany = _lignes_registre(conn, code_district, lot_id)
    _rendre_geo(conn, code_district, (ensemble, nouveau, efokontany), fmt)
    version = x["version"] or x["lot_id"]
    tag = "codes" if fmt == "code" else "libelles"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"base_prechargement_{version}_{tag}.xlsx",
                   _octets_prechargement(ensemble, nouveau, efokontany))
        z.writestr(f"charge_agents_{version}.xlsx", _octets_charge(ensemble))
    return (f"prechargement_district{int(code_district)}_lot{x['numero']}_"
            f"{version}_{tag}.zip", buf.getvalue())


def xlsx_total(conn, code_district: int, format_geo="code"):
    """Classeur de TOUS les ménages préchargés du district (les 3 feuilles,
    toutes sorties confondues), au format `format_geo` ('code' ou 'libelle').
    (nom, octets) ; lève ErreurDonnees si vide."""
    fmt = _format_ok(format_geo)
    ensemble, nouveau, efokontany = _lignes_registre(conn, code_district)
    if not ensemble:
        raise ErreurDonnees("Aucun ménage n'a encore été préchargé pour ce district.")
    _rendre_geo(conn, code_district, (ensemble, nouveau, efokontany), fmt)
    tag = "codes" if fmt == "code" else "libelles"
    return (f"prechargement_district{int(code_district)}_TOTAL_{tag}_"
            f"{datetime.now().strftime('%Y%m%d_%HH%MMN')}.xlsx",
            _octets_prechargement(ensemble, nouveau, efokontany))


def annuler_dernier_lot(conn, code_district: int, lot_id: str) -> dict:
    """Retire du registre le DERNIER lot du district (et lui seul) : ses ménages
    redeviennent « à précharger ». Refuse tout autre lot — annuler un lot ancien
    rouvrirait des ménages qu'un lot plus récent peut déjà avoir contournés."""
    tous = lots(conn, code_district)
    if not tous:
        raise ErreurDonnees("Aucun lot à annuler pour ce district.")
    dernier = tous[-1]
    if dernier["lot_id"] != lot_id:
        raise ErreurDonnees("Seul le DERNIER lot peut être annulé.")
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    try:
        for _titre, table, _cols in T_FEUILLES:
            cur.execute(f'DELETE FROM "{table}" WHERE "lot_id" = {ph}', (lot_id,))
        cur.execute(f'DELETE FROM "{T_LOT}" WHERE "lot_id" = {ph}', (lot_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return dernier


# ---------------------------------------------------------------------------
# Apurement commun (génération ET décompte par fokontany)
# ---------------------------------------------------------------------------
def _ligne_vide(nom_d, surnom, taille, adresse) -> bool:
    """Ligne de segment_roster vide (do-file, étape 5.3)."""
    return (nom_d == "##N/A##" and surnom == "##N/A##"
            and taille is None and adresse == "##N/A##")


def _statut_ok(statut) -> bool:
    return _int(statut) in STATUTS_OK


def fokontany_disponibles(conn, code_district: int) -> list:
    """Les fokontany du district qui ont des ménages préchargeables, groupés par
    commune, avec leurs effectifs :

        [{'code': 520101, 'nom': 'AMBATOHARANANA',
          'fokontany': [{'code': 52010101, 'nom': 'AMBODIHASINA_52010101',
                         'total': 120, 'deja': 80, 'reste': 40}, …]}, …]

    `total` = ménages éligibles (mêmes règles que la génération : statut
    terminé/approuvé, lignes vides et codes invalides écartés) ; `deja` = déjà
    au registre ; `reste` = à précharger."""
    ph = db_source._placeholder(conn)
    cols_den = db_source.colonnes_table(conn, "den_menage")
    if not cols_den:
        return []
    col_fkt = db_source.colonne_code_fokontany(cols_den)
    a_statut = "interview__status" in cols_den
    cur = conn.cursor()
    cur.execute(f'SELECT "interview__key", "{col_fkt}"'
                + (', "interview__status"' if a_statut else '')
                + f' FROM "den_menage" WHERE "district" = {ph}',
                (int(code_district),))
    den = {}
    for row in cur.fetchall():
        k = row[0]
        if not k or k in den:
            continue
        if a_statut and not _statut_ok(row[2]):
            continue
        den[k] = _int(row[1])
    if not den:
        return []
    deja = registre(conn, code_district)
    compte = {}                 # code fokontany -> [total, deja]
    vus = set()
    cur.execute('SELECT r."interview__key", r."segment_roster__id", r."nom_cmD", '
                'r."surnom", r."taille_menD", r."adresse", r."code_den" '
                'FROM "segment_roster" r WHERE r."interview__key" IN '
                f'(SELECT "interview__key" FROM "den_menage" WHERE "district" = {ph})',
                (int(code_district),))
    for k, srid, nom_d, surnom, taille, adr, code_den in cur.fetchall():
        fkt = den.get(k)
        if fkt is None:
            continue
        if _ligne_vide(nom_d, surnom, taille, adr) or _sans_na(code_den) == "//()":
            continue
        keyden = k + "-" + ("" if srid is None else str(int(srid))).zfill(3)
        if keyden in vus:
            continue
        vus.add(keyden)
        c = compte.setdefault(fkt, [0, 0])
        c[0] += 1
        if keyden in deja:
            c[1] += 1
    libz = _libelles_zones(conn, code_district)
    communes = {}
    for fkt, (total, n_deja) in compte.items():
        ccom = fkt // 100 if fkt and fkt >= 1_000_000 else None
        com = communes.setdefault(ccom, {
            "code": ccom, "nom": libz["communes"].get(ccom) or str(ccom or "?"),
            "fokontany": []})
        com["fokontany"].append({
            "code": fkt, "nom": libz["fokontany"].get(fkt) or str(fkt),
            "total": total, "deja": n_deja, "reste": total - n_deja})
    out = sorted(communes.values(), key=lambda c: c["nom"])
    for c in out:
        c["fokontany"].sort(key=lambda f: f["nom"])
    return out


# ---------------------------------------------------------------------------
# Lecture des ménages depuis la base (district) + apurement
# ---------------------------------------------------------------------------
def _charger_menages(conn, code_district: int, log):
    """Reconstruit (ensemble, nouveau, efokontany) pour un district, depuis la base.

    ENQ = code agent (interview__diagnostics.responsible) ; CE = chef d'équipe via
    les tables `equipes`. Reproduit fidèlement l'apurement du programme exe."""
    src = db_source.source_db(conn, district=code_district)
    den = src("den")
    ros = src("roster")
    diag = src("diagnostics")

    log("[1/4] Lecture de DEN_MENAGE (zones geographiques)...")
    den_keys = den.col("interview__key")
    den_reg = den.col("region")
    den_dis = den.col("district")
    den_com = den.col("commune")
    den_fkt = den.col("fokontany")
    den_fkt_dec = den.col_decoded("fokontany")
    # `num_fkt` a disparu du questionnaire : le code 8 chiffres est desormais
    # porte par `fokontany` lui-meme (meme valeur). Absent -> colonne a None.
    den_num = _col_opt(den, "num_fkt")
    den_seg = den.col("segment")
    # Statut Survey Solutions (do-file, étape 5.1) : seules les interviews
    # terminées ou approuvées sont préchargées ; une rejetée le sera plus tard.
    a_statut = "interview__status" in den.varnames
    den_stat = den.col("interview__status") if a_statut else [None] * den.nobs
    if not a_statut:
        log("   ATTENTION : interview__status absent de DEN_MENAGE -> "
            "aucun filtre de statut applique")
    den_index = {}
    n_drop_statut = 0
    for i, k in enumerate(den_keys):
        if k in den_index:
            continue
        if a_statut and not _statut_ok(den_stat[i]):
            den_index[k] = None          # interview écartée (statut)
            n_drop_statut += 1
            continue
        code8 = den_fkt[i] if den_fkt[i] is not None else den_num[i]
        den_index[k] = {
            "region": den_reg[i], "district": den_dis[i],
            "commune": den_com[i], "code8": code8,
            "fkt_recherche": den_fkt_dec[i],
            "segment": "" if den_seg[i] is None else str(den_seg[i]),
        }

    libz = _libelles_zones(conn, code_district)
    log(f"   Libelles : region {libz['region'] or '?'} / district "
        f"{libz['district'] or '?'} ; {len(libz['communes'])} communes, "
        f"{len(libz['fokontany'])} fokontany au referentiel")

    log("[2/4] Derivation CE / ENQ (diagnostics + equipes)...")
    # ENQ (agent enquêteur) par interview__key = interview__diagnostics.responsible.
    d_keys = diag.col("interview__key")
    d_resp = diag.col("responsible")
    enq_index = {}
    for i, k in enumerate(d_keys):
        if k not in enq_index:
            enq_index[k] = _sans_na(d_resp[i])
    # CE (chef d'équipe) : chef de l'agent, via les tables equipes.
    liens = equipes.agents_et_chefs(conn)   # {code_agent: {nom, chef_login, chef_nom}}
    log(f"   ENQ : {len(enq_index)} interviews ; agents connus : {len(liens)}")
    # CE : le dossier televerse d'abord (source directe), `agent.login_ce` ensuite.
    ce_par_cle = _ce_du_dossier(code_district, log)

    log("[3/4] Lecture de segment_roster (menages) + apurement...")
    r_key = ros.col("interview__key")
    r_srid = ros.col("segment_roster__id")
    r_nom = ros.col("nom_cm")
    r_nomD = ros.col("nom_cmD")
    r_surnom = ros.col("surnom")
    r_taille = ros.col("taille_menD")
    r_adr = ros.col("adresse")
    r_desc = ros.col("description")
    r_lat = ros.col("gps_coord__Latitude")
    r_lon = ros.col("gps_coord__Longitude")
    r_code = ros.col("code_den")
    # `ID_efkt` (scan du carnet e-Fokontany) n'est plus collecte -> colonne vide,
    # donc TOUS les menages partent en « nouveau » et la feuille e_fokontany est
    # vide. C'est le comportement attendu tant que le carnet n'est pas recollecte.
    r_idefkt = _col_opt(ros, "ID_efkt")

    ensemble, nouveau, efokontany = [], [], []
    vus = set()
    n_drop_vide = n_drop_code = n_drop_nomerge = n_drop_statutm = 0
    for i in range(ros.nobs):
        k = r_key[i]
        if k not in den_index:              # pas dans DEN_MENAGE (_merge != 3)
            n_drop_nomerge += 1
            continue
        info = den_index[k]
        if info is None:                    # statut rejeté / en cours
            n_drop_statutm += 1
            continue
        if _ligne_vide(r_nomD[i], r_surnom[i], r_taille[i], r_adr[i]):
            n_drop_vide += 1
            continue
        code_den = _sans_na(r_code[i])
        if code_den == "//()":
            n_drop_code += 1
            continue
        srid = "" if r_srid[i] is None else str(int(r_srid[i]))
        keyden = k + "-" + srid.zfill(3)
        if keyden in vus:
            continue
        vus.add(keyden)

        reg_c, dis_c, com_c, fkt_c = _codes_hierarchie(
            info["code8"], info["region"], info["district"], info["commune"])
        # CODES (et non libellés) pour region/district/commune/fokontany : la base
        # de préchargement attend les CODES du référentiel `zones` (retour aux codes,
        # journal 2026-09-26). Les LIBELLÉS ne servent plus qu'à `fkt_recherche`
        # (recherche par NOM) et au fichier de charge (lisibilité). Repli du nom sur
        # le value label du questionnaire, puis sur le code, pour ne pas vider la
        # colonne quand une zone manque au référentiel.
        reg, dis, com, fkt = reg_c, dis_c, com_c, fkt_c
        com_nom = libz["communes"].get(_int(com_c)) or str(com_c)
        fkt_nom = (libz["fokontany"].get(_int(fkt_c))
                   or _sans_na(info["fkt_recherche"]) or str(fkt_c))
        idefkt = _nettoyer_idefkt(r_idefkt[i])
        est_nouveau = (idefkt == "")
        adresse = "" if _est_na(r_adr[i]) else str(r_adr[i]).upper()
        lat, lon = _gps_txt(r_lat[i]), _gps_txt(r_lon[i])
        lat_n, lon_n = _gps_num(r_lat[i]), _gps_num(r_lon[i])
        enq = enq_index.get(k, "")
        ce = ce_par_cle.get(k, "")               # CODE du chef d'équipe (login_ce)
        if not ce:
            lien = liens.get(enq)
            if lien:
                ce = lien.get("chef_login") or ""

        base = {
            "interview__key": k,
            "interview_keyden": keyden,
            "region": reg, "district": dis, "commune": com, "fokontany": fkt,
            # fokontany = CODE ; fkt_recherche garde le NOM (recherche par libellé).
            "fkt_recherche": fkt_nom,
            "nom_cm": _sans_na(r_nom[i]),
            "taille_men": "" if r_taille[i] is None else r_taille[i],
            "description": _sans_na(r_desc[i]),
            "code_den": code_den,
            "CE": ce, "ENQ": enq,
            # Méta internes (préfixe _) : équilibrage + charge par agent. Le fichier
            # de charge affiche les NOMS (commune/fokontany) pour rester lisible.
            "_sid": k, "_seg": info["segment"], "_com": com_nom,
            "_fkt_code": _int(fkt_c),
            "_fktnom": fkt_nom,
            "_lat": lat_n, "_lon": lon_n, "_agent": enq,
        }
        ligne_ens = {**base, "IdeFKT": idefkt, "adresse": adresse,
                     "gps_coord__Latitude": lat, "gps_coord__Longitude": lon}
        ensemble.append(ligne_ens)
        if est_nouveau:
            nouveau.append({**base, "CQ17_preload": adresse,
                            "GPS_Lat_ZD": lat, "GPS_Long_ZD": lon,
                            "_responsible": enq, "_quantity": 1,
                            "typemen": 2, "mode_enreg": 1, "nom_projet": 1})
        else:
            efokontany.append(ligne_ens)

    n_ce = sum(1 for r in ensemble if r["CE"])
    log(f"   {len(ensemble)} menages : {len(efokontany)} e-fokontany, "
        f"{len(nouveau)} nouveaux (ignores : {n_drop_nomerge} sans segment, "
        f"{n_drop_vide} vides, {n_drop_code} code invalide, "
        f"{n_drop_statutm} d'interviews non approuvees "
        f"[{n_drop_statut} interview(s)])")
    log(f"   CE renseigne sur {n_ce}/{len(ensemble)} menages ; "
        f"ENQ sur {sum(1 for r in ensemble if r['ENQ'])}")
    return ensemble, nouveau, efokontany


# ---------------------------------------------------------------------------
# Équilibrage de la charge (délègue à affectation_agents, comme l'exe)
# ---------------------------------------------------------------------------
def _appliquer_affectation(ensemble, nouveau, efokontany, mode: str, log):
    if mode not in ("equilibre", "equilibre_fort"):
        log("Affectation : agent du denombrement (aucune redistribution).")
        return
    fort = (mode == "equilibre_fort")
    if fort:
        log("Equilibrage FORT de la charge (par commune, avec echanges)...")
    else:
        log("Equilibrage de la charge entre agents (par commune)...")
    agg: dict = {}
    for r in ensemble:
        u = agg.get(r["_sid"])
        if u is None:
            u = agg[r["_sid"]] = {
                "sid": r["_sid"], "commune": r["_com"], "n": 0,
                "agent": r["_agent"], "_slat": 0.0, "_slon": 0.0, "_w": 0}
        u["n"] += 1
        if r["_lat"] is not None and r["_lon"] is not None:
            u["_slat"] += r["_lat"]
            u["_slon"] += r["_lon"]
            u["_w"] += 1
    unites = []
    for u in agg.values():
        u["lat"] = u["_slat"] / u["_w"] if u["_w"] else None
        u["lon"] = u["_slon"] / u["_w"] if u["_w"] else None
        unites.append(u)
    affect = equilibrer_charge(unites, log,
                               tol_frac=(0.0 if fort else 0.10), echanges=fort)
    n_moves = 0
    for r in ensemble:
        na = affect.get(r["_sid"], r["_agent"])
        if na != r["ENQ"]:
            n_moves += 1
        r["ENQ"] = na
    for r in efokontany:
        r["ENQ"] = affect.get(r["_sid"], r["_agent"])
    for r in nouveau:
        r["_responsible"] = affect.get(r["_sid"], r["_agent"])
    log(f"   {n_moves} menage(s) reaffecte(s) a un autre agent "
        f"(le CE d'origine est conserve).")


# ---------------------------------------------------------------------------
# Format géographique (codes / libellés) appliqué avant l'écriture
# ---------------------------------------------------------------------------
def _rendre_geo(conn, code_district, feuilles, format_geo) -> tuple:
    """Applique le format géographique aux lignes AVANT l'écriture des classeurs.

    La CLÉ de vérité est le **code fokontany 8 chiffres** (`_fkt_code`, ou la méta
    `code_fokontany` relue du registre) : region/district/commune/fokontany en sont
    dérivés (`code//1e6`, `//1e4`, `//100`, code). C'est robuste quel que soit ce que
    portent les colonnes stockées (codes des nouveaux lots OU libellés des lots créés
    avant le 2026-09-26).
      • format_geo == 'code'    : les 4 colonnes reçoivent les CODES dérivés ;
      • format_geo == 'libelle' : elles reçoivent les LIBELLÉS du référentiel `zones`
        (repli sur le code si la zone y manque).
    DANS LES DEUX CAS : `fkt_recherche` = NOM du fokontany (champ de recherche) et les
    méta de charge `_com` / `_fktnom` = NOMS (le fichier charge_agents reste lisible).
    Modifie les dicts en place et renvoie le tuple des feuilles."""
    format_geo = _format_ok(format_geo)
    libz = _libelles_zones(conn, int(code_district))
    for lignes in feuilles:
        for r in lignes:
            code_fkt = _int(r.get("_fkt_code"))
            if code_fkt is None:
                code_fkt = _int(r.get("code_fokontany"))   # relecture registre
            if code_fkt is not None and code_fkt >= 1_000_000:
                code_reg, code_dis = code_fkt // 1_000_000, code_fkt // 10_000
                code_com = code_fkt // 100
            else:
                code_reg = code_dis = code_com = None
            nom_com = (libz["communes"].get(code_com)
                       or (str(code_com) if code_com is not None
                           else str(r.get("commune") or "")))
            nom_fkt = (libz["fokontany"].get(code_fkt)
                       or _sans_na(r.get("fkt_recherche"))
                       or (str(code_fkt) if code_fkt is not None
                           else str(r.get("fokontany") or "")))
            if format_geo == "code":
                if code_reg is not None:
                    r["region"], r["district"] = code_reg, code_dis
                    r["commune"], r["fokontany"] = code_com, code_fkt
            else:                                          # libelle
                r["region"] = libz["region"] or (
                    str(code_reg) if code_reg is not None else r.get("region"))
                r["district"] = libz["district"] or (
                    str(code_dis) if code_dis is not None else r.get("district"))
                r["commune"] = nom_com
                r["fokontany"] = nom_fkt
            # Communs aux deux formats : recherche par nom + charge lisible.
            r["fkt_recherche"] = nom_fkt
            r["_com"] = nom_com
            r["_fktnom"] = nom_fkt
    return feuilles


# ---------------------------------------------------------------------------
# Écriture des deux classeurs -> octets
# ---------------------------------------------------------------------------
def _octets_prechargement(ensemble, nouveau, efokontany) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook(write_only=True)
    for titre, cols, lignes in (
            ("Ensemble", COLS_ENSEMBLE, ensemble),
            ("nouveau", COLS_NOUVEAU, nouveau),
            ("e_fokontany", COLS_EFOKONTANY, efokontany)):
        ws = wb.create_sheet(titre)
        ws.append(cols)
        for ligne in lignes:
            ws.append([ligne.get(c, "") for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _stats(valeurs):
    """min, max, médiane, moyenne, écart-type (arrondis) d'une liste."""
    if not valeurs:
        return (0, 0, 0, 0, 0)
    mn, mx = min(valeurs), max(valeurs)
    med = round(statistics.median(valeurs), 1)
    moy = round(statistics.fmean(valeurs), 1)
    ect = round(statistics.pstdev(valeurs), 1) if len(valeurs) > 1 else 0
    return (mn, mx, med, moy, ect)


def _octets_charge(ensemble) -> bytes:
    """Fichier de charge par agent (reflète l'affectation finale, colonne ENQ)."""
    import openpyxl
    par_agent: Counter = Counter()
    par_segment: Counter = Counter()
    agent_commune: dict = {}
    for r in ensemble:
        agent_final = r["ENQ"]
        com = r["_com"]
        par_agent[agent_final] += 1
        par_segment[(com, r["_fktnom"], r["_seg"], agent_final)] += 1
        agent_commune.setdefault(agent_final, com)

    wbc = openpyxl.Workbook(write_only=True)
    ws1 = wbc.create_sheet("Par_agent")
    ws1.append(["code_agent", "commune", "nb_menages"])
    for agent_final in sorted(par_agent):
        ws1.append([agent_final, agent_commune.get(agent_final, ""),
                    par_agent[agent_final]])
    ws2 = wbc.create_sheet("Par_segment")
    ws2.append(["commune", "fokontany", "segment", "code_agent", "nb_menages"])
    for cle in sorted(par_segment):
        ws2.append([cle[0], cle[1], cle[2], cle[3], par_segment[cle]])

    ws3 = wbc.create_sheet("Statistiques")
    charges = list(par_agent.values())
    total_men = sum(charges)
    nb_agents = len(par_agent)
    nb_com = len(set(agent_commune.values()))
    g_mn, g_mx, g_med, g_moy, g_ect = _stats(charges)
    ws3.append(["Statistiques globales (charge = nb de menages par agent)"])
    ws3.append(["Indicateur", "Valeur"])
    ws3.append(["Nombre d'agents", nb_agents])
    ws3.append(["Nombre de communes", nb_com])
    ws3.append(["Nombre total de menages", total_men])
    ws3.append(["Minimum (menages/agent)", g_mn])
    ws3.append(["Maximum (menages/agent)", g_mx])
    ws3.append(["Mediane (menages/agent)", g_med])
    ws3.append(["Moyenne (menages/agent)", g_moy])
    ws3.append(["Ecart-type (menages/agent)", g_ect])
    ws3.append([])

    charges_par_com: dict = {}
    menages_par_com: Counter = Counter()
    for agent_final, com in agent_commune.items():
        charges_par_com.setdefault(com, []).append(par_agent[agent_final])
    for r in ensemble:
        menages_par_com[r["_com"]] += 1
    ws3.append(["Repartition des agents et de la charge par commune"])
    ws3.append(["Commune", "Nombre d'agents", "Nombre de menages",
                "Min", "Max", "Mediane", "Moyenne", "Ecart-type"])
    for com in sorted(charges_par_com):
        vals = charges_par_com[com]
        c_mn, c_mx, c_med, c_moy, c_ect = _stats(vals)
        ws3.append([com, len(vals), menages_par_com[com],
                    c_mn, c_mx, c_med, c_moy, c_ect])
    ws3.append([])

    tranches = [(0, 50), (51, 100), (101, 150), (151, 200),
                (201, 300), (301, 500), (501, 10**9)]
    libelles = ["1 - 50", "51 - 100", "101 - 150", "151 - 200",
                "201 - 300", "301 - 500", "501 et +"]
    hist = [0] * len(tranches)
    for ch in charges:
        for idx, (lo, hi) in enumerate(tranches):
            if lo <= ch <= hi:
                hist[idx] += 1
                break
    ws3.append(["Repartition des agents par tranche de charge"])
    ws3.append(["Tranche (menages)", "Nombre d'agents"])
    for lib, nb in zip(libelles, hist):
        ws3.append([lib, nb])

    buf = io.BytesIO()
    wbc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Point d'entrée web : génère UN LOT et l'inscrit au registre
# ---------------------------------------------------------------------------
def generer_lot(conn, code_district: int, mode: str = "denombrement",
                fokontany=None, utilisateur=None, log=None) -> dict:
    """Génère UN lot de préchargement pour le district et l'inscrit au registre.

    * `fokontany` : ensemble de codes fokontany (8 chiffres) à retenir, ou None /
      vide = tous (do-file, étape 6) ;
    * les ménages DÉJÀ au registre sont retirés (étape 7) ;
    * le lot et ses ménages sont enregistrés dans la même transaction que la
      génération (étape 9).

    Renvoie le lot ({'lot_id', 'numero', 'nb_ensemble', …}). Le ZIP se retélécharge
    ensuite par `zip_lot`. Lève ErreurDonnees s'il n'y a rien à précharger."""
    log = log or _log_noop
    mode = (mode or "denombrement").strip().lower()
    if mode not in MODES:
        mode = "denombrement"
    code = int(code_district)
    fkt_choisis = {int(c) for c in (fokontany or ()) if _int(c) is not None}

    ensemble, nouveau, efokontany = _charger_menages(conn, code, log)
    if not ensemble:
        raise ErreurDonnees(
            "Aucun menage exploitable pour ce district : rien a precharger. "
            "Le denombrement a-t-il ete transcrit, et les interviews sont-elles "
            "terminees ou approuvees ?")

    if fkt_choisis:
        ensemble = [r for r in ensemble if r["_fkt_code"] in fkt_choisis]
        log(f"Choix des fokontany : {len(fkt_choisis)} retenu(s) -> "
            f"{len(ensemble)} menage(s).")
        if not ensemble:
            raise ErreurDonnees("Aucun menage dans les fokontany choisis.")

    deja = registre(conn, code)
    avant = len(ensemble)
    ensemble = [r for r in ensemble if r[CLE_MENAGE] not in deja]
    log(f"Registre : {len(deja)} menage(s) deja precharge(s) dans le district ; "
        f"{avant - len(ensemble)} retire(s) -> {len(ensemble)} a precharger.")
    if not ensemble:
        raise ErreurDonnees(
            f"AUCUN NOUVEAU MENAGE : les {avant} menage(s) "
            + ("des fokontany choisis " if fkt_choisis else "du district ")
            + "ont tous deja ete precharges. Rien a envoyer aujourd'hui.")
    garder = {r[CLE_MENAGE] for r in ensemble}
    nouveau = [r for r in nouveau if r[CLE_MENAGE] in garder]
    efokontany = [r for r in efokontany if r[CLE_MENAGE] in garder]

    log("[4/4] Affectation des agents + enregistrement du lot...")
    _appliquer_affectation(ensemble, nouveau, efokontany, mode, log)

    maintenant = datetime.now()
    version = maintenant.strftime("%Y%m%d_%HH%MMN")
    lot_id = f"{code}_{maintenant.strftime('%Y%m%d%H%M%S%f')}"
    try:
        _enregistrer(conn, code, lot_id, version, utilisateur, mode, fkt_choisis,
                     ensemble, nouveau, efokontany)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    x = lot(conn, code, lot_id)
    log(f"Lot n°{x['numero']} enregistre : {len(ensemble)} menage(s).")
    return x


# ---------------------------------------------------------------------------
# Pages (charte visuelle d'admin.py / equipes.py)
# ---------------------------------------------------------------------------
import admin  # noqa: E402  (après les fonctions : évite un cycle au chargement)

ESC = admin.ESC


def _note_ce(code_district) -> str:
    """Dit si le login du CHEF D'ÉQUIPE pourra être renseigné, pour CE district.

    La colonne `CE` vient de `base_login_ce.dta` (cf. `_ce_du_dossier`). Ce fichier
    n'est pas exigé au téléversement : sans lui, la colonne sort vide et rien ne le
    disait — d'où cette note, qui regarde le dossier du district et nomme le fichier
    à inclure dans l'export Survey Solutions."""
    if not code_district:
        return ""
    etat = _ce_du_dossier(int(code_district), _log_noop)
    if etat:
        return ('<div class="note">Login du <b>chef d&rsquo;&eacute;quipe</b> : '
                f'<code>{FICHIER_CE}</code> est pr&eacute;sent dans votre dossier '
                f'({len(etat)} interview(s) rattach&eacute;es) &mdash; la colonne '
                '<b>CE</b> sera renseign&eacute;e.</div>')
    return ('<div class="note" style="background:#fff4d6;border-color:#f0d38a">'
            'La colonne <b>CE</b> (login du chef d&rsquo;&eacute;quipe) sortira '
            '<b>vide</b> : le fichier <code>' + FICHIER_CE + '</code> n&rsquo;est pas '
            'dans le dossier de votre district. C&rsquo;est lui qui porte le login du '
            'chef d&rsquo;&eacute;quipe par interview (r&ocirc;le 2) ; la table des '
            'agents de la base, elle, ne le conna&icirc;t pas pour les agents '
            'd&eacute;couverts &agrave; la transcription. <b>Incluez '
            f'<code>{FICHIER_CE}</code> dans votre export Survey Solutions</b> et '
            't&eacute;l&eacute;versez-le avec les autres <code>.dta</code> : il est '
            'conserv&eacute; tel quel dans le dossier, sans transcription.</div>')


_CSS_PAGE = """<style>
.pk-fkt{border:1px solid #d6dbe6;border-radius:.5rem;padding:.4rem .7rem;margin:.35rem 0;background:#fff}
.pk-fkt summary{cursor:pointer;font-weight:600}
.pk-fkt label{display:block;margin:.2rem 0 .2rem 1.2rem;font-weight:normal}
.pk-fkt label.fini{color:#94a3b8}
.pk-fkt .pk-com{margin-left:0;font-weight:600}
.pk-chiffres{display:flex;gap:.8rem;flex-wrap:wrap;margin:.4rem 0 .8rem}
.pk-chiffres div{background:#fff;border:1px solid #d6dbe6;border-radius:.5rem;padding:.5rem .9rem}
.pk-chiffres b{display:block;font-size:1.3rem;color:#12325c}
#pk-liste[hidden]{display:none}
div.ok{padding:.625rem .875rem;border-radius:.625rem;margin:.6rem 0;border:1px solid #bbf7d0}
</style>"""

_JS_PAGE = """<script>
(function(){
  var liste=document.getElementById('pk-liste');
  function maj(){var c=document.querySelector('input[name=portee]:checked');
    if(liste) liste.hidden=!(c&&c.value==='choix');}
  document.querySelectorAll('input[name=portee]').forEach(function(r){
    r.addEventListener('change',maj);});
  maj();
  document.querySelectorAll('.pk-toutcom').forEach(function(t){
    t.addEventListener('change',function(){
      var bloc=t.closest('details');
      bloc.querySelectorAll('input[name=fokontany]:not(:disabled)').forEach(
        function(c){c.checked=t.checked;});});});
  var f=document.getElementById('pk-form');
  if(f) f.addEventListener('submit',function(e){
    var c=document.querySelector('input[name=portee]:checked');
    if(c&&c.value==='choix'&&!document.querySelector('input[name=fokontany]:checked')){
      e.preventDefault(); alert('Cochez au moins un fokontany, ou choisissez « Tous les fokontany ».');}
  });
  var dl=document.getElementById('pk-auto');
  if(dl) setTimeout(function(){window.location.href=dl.getAttribute('href');},400);
})();
</script>"""


def _bloc_fokontany(communes, choisis=()) -> str:
    """Choix « Tous les fokontany » / choix multiple, fokontany groupés par commune."""
    choisis = {int(c) for c in choisis if _int(c) is not None}
    tous = not choisis
    h = ['<div><label><b>Fokontany à précharger</b></label>',
         '<label style="display:block;margin:6px 0"><input type="radio" '
         f'name="portee" value="tous"{" checked" if tous else ""}> '
         'Tous les fokontany</label>',
         '<label style="display:block;margin:6px 0"><input type="radio" '
         f'name="portee" value="choix"{"" if tous else " checked"}> '
         'Choisir des fokontany (choix multiple, par commune)</label>',
         '<div id="pk-liste">']
    for com in communes:
        reste = sum(f["reste"] for f in com["fokontany"])
        ouvert = " open" if any(f["code"] in choisis for f in com["fokontany"]) else ""
        h.append(f'<details class="pk-fkt"{ouvert}><summary>{ESC(com["nom"])} '
                 f'— {reste} ménage(s) à précharger, {len(com["fokontany"])} '
                 'fokontany</summary>'
                 '<label class="pk-com"><input type="checkbox" class="pk-toutcom"'
                 f'{"" if reste else " disabled"}> Toute la commune</label>')
        for f in com["fokontany"]:
            fini = f["reste"] == 0
            coche = " checked" if f["code"] in choisis and not fini else ""
            h.append(f'<label class="{"fini" if fini else ""}">'
                     f'<input type="checkbox" name="fokontany" value="{f["code"]}"'
                     f'{coche}{" disabled" if fini else ""}> {ESC(f["nom"])} — '
                     f'<b>{f["reste"]}</b> à précharger'
                     f' <small>({f["deja"]} déjà préchargé(s) sur {f["total"]})</small>'
                     '</label>')
        h.append('</details>')
    h.append('</div></div>')
    return "".join(h)


def _table_lots(tous) -> str:
    if not tous:
        return ('<div class="note">Aucun préchargement n’a encore été enregistré '
                'pour ce district.</div>')
    lignes = []
    dernier = tous[-1]["lot_id"]
    for x in reversed(tous):
        fkt = x["fokontany"] or "TOUS"
        fkt_txt = ("Tous" if fkt == "TOUS"
                   else f'{len(fkt.split(","))} fokontany')
        annuler = ""
        if x["lot_id"] == dernier:
            annuler = (
                '<form method="post" action="/traitement/prechargement/annuler" '
                'style="display:inline" onsubmit="return confirm(\'Annuler le lot n°'
                f'{x["numero"]} ? Ses {x["nb_ensemble"]} ménage(s) redeviendront '
                '« à précharger ». Ne le faites que si ce fichier n’a PAS été '
                'envoyé.\')">'
                f'<input type="hidden" name="lot" value="{ESC(x["lot_id"])}">'
                '<button class="danger" style="padding:.2rem .6rem">Annuler</button>'
                '</form>')
        lien = "/traitement/prechargement/lot?id=" + urllib.parse.quote(x["lot_id"])
        lignes.append(
            f'<tr><td><b>{x["numero"]}</b></td><td>{ESC(x["cree_le"] or "")}</td>'
            f'<td>{ESC(x["nom_prenom"] or x["login"] or "")}</td>'
            f'<td>{ESC(LIBELLE_MODE.get(x["mode"], x["mode"] or "")).split(" (")[0]}</td>'
            f'<td>{ESC(fkt_txt)}</td><td>{x["nb_nouveau"]}</td>'
            f'<td>{x["nb_efokontany"]}</td><td><b>{x["nb_ensemble"]}</b></td>'
            f'<td>ZIP : <a href="{lien}&fmt=code">Codes</a> · '
            f'<a href="{lien}&fmt=libelle">Libellés</a> {annuler}</td></tr>')
    return ('<table><tr><th>Lot</th><th>Généré le</th><th>Par</th><th>Mode</th>'
            '<th>Fokontany</th><th>nouveau</th><th>e_fokontany</th><th>Ensemble</th>'
            '<th>Télécharger (ZIP)</th></tr>' + "".join(lignes) + '</table>'
            '<p style="display:flex;gap:8px;flex-wrap:wrap">'
            '<a href="/traitement/prechargement/total.xlsx?fmt=code">'
            '<button type="button" class="sec">Fichier TOTAL — Codes</button></a>'
            '<a href="/traitement/prechargement/total.xlsx?fmt=libelle">'
            '<button type="button" class="sec">Fichier TOTAL — Libellés</button></a>'
            '</p><div class="note">Le fichier TOTAL regroupe toutes les sorties du '
            'district. <b>Codes</b> = region/district/commune/fokontany en codes ; '
            '<b>Libellés</b> = en noms. <code>fkt_recherche</code> reste le nom du '
            'fokontany dans les deux cas.</div>')


def page_prechargement(conn, district_txt, code_district=None, erreur=None,
                       message=None, lot_ok=None, choisis=(),
                       format_ok="code") -> str:
    """Formulaire : fokontany + mode d'affectation -> génération d'un lot ;
    historique des lots (retéléchargement, annulation du dernier, fichier total)."""
    h = [equipes._entete(), _CSS_PAGE,
         '<p style="margin:0 0 6px"><a href="/traitement">'
         '&larr; Accueil Traitement</a></p>',
         '<h1>Base de pr&eacute;chargement (VAD)</h1>',
         f'<div class="note">District d&rsquo;affectation : <b>{ESC(district_txt)}</b>. '
         'Chaque sortie produit une archive ZIP : la <b>base de pr&eacute;chargement</b> '
         '(Ensemble / nouveau / e_fokontany) et la <b>charge par agent</b>. '
         'Les ménages exportés sont <b>enregistrés dans la base</b> : '
         '<b>un ménage préchargé une fois n’est jamais renvoyé</b>. '
         'Seules les interviews <b>terminées ou approuvées</b> sont préchargées ; '
         'une interview rejetée le sera à une prochaine sortie, une fois '
         'approuvée.</div>',
         '<div class="note" style="background:#fff4d6;border-color:#f0d38a">'
         'La feuille <b>e_fokontany</b> est <b>vide</b> : le questionnaire en cours '
         'ne collecte plus le scan du carnet e-Fokontany (<code>ID_efkt</code>). Tous '
         'les ménages sont donc en <b>nouveau</b>, et Ensemble = nouveau.</div>',
         _note_ce(code_district)]
    if erreur:
        h.append(f'<div class="err">{erreur}</div>')
    if message:
        h.append(f'<div class="ok">{message}</div>')
    if lot_ok:
        fmt = _format_ok(format_ok)
        autre = "libelle" if fmt == "code" else "code"
        base = ('/traitement/prechargement/lot?id='
                + urllib.parse.quote(lot_ok["lot_id"]))
        h.append(f'<div class="ok">Lot n°{lot_ok["numero"]} enregistré : '
                 f'<b>{lot_ok["nb_ensemble"]}</b> ménage(s). Le téléchargement au '
                 f'format <b>{ESC(LIBELLE_FORMAT[fmt])}</b> démarre ; sinon '
                 f'<a id="pk-auto" href="{base}&fmt={fmt}">cliquez ici</a> '
                 f'(ou <a href="{base}&fmt={autre}">au format '
                 f'{ESC(LIBELLE_FORMAT[autre])}</a>). '
                 '<b>Envoyez ce fichier aux Experts Survey Solutions.</b></div>')

    communes = fokontany_disponibles(conn, code_district) if code_district else []
    total = sum(f["total"] for c in communes for f in c["fokontany"])
    deja = sum(f["deja"] for c in communes for f in c["fokontany"])
    h.append('<div class="pk-chiffres">'
             f'<div>Ménages préchargeables<b>{total}</b></div>'
             f'<div>Déjà préchargés<b>{deja}</b></div>'
             f'<div>Reste à précharger<b>{total - deja}</b></div></div>')

    opts = "".join(
        f'<label style="display:block;margin:6px 0">'
        f'<input type="radio" name="mode" value="{m}"'
        f'{" checked" if m == "denombrement" else ""}> {ESC(LIBELLE_MODE[m])}</label>'
        for m in MODES)
    aide_fmt = {"code": "region/district/commune/fokontany en CODES",
                "libelle": "region/district/commune/fokontany en NOMS"}
    fmt_opts = "".join(
        f'<label style="display:block;margin:6px 0">'
        f'<input type="radio" name="format_geo" value="{f}"'
        f'{" checked" if f == "code" else ""}> {ESC(LIBELLE_FORMAT[f])} '
        f'<small>({ESC(aide_fmt[f])})</small></label>'
        for f in FORMATS_GEO)
    h.append('<h2>Nouvelle sortie</h2>')
    if total - deja <= 0:
        h.append('<div class="note"><b>Aucun nouveau ménage</b> à précharger '
                 'pour ce district. Rien à envoyer aujourd’hui.</div>')
    else:
        h.append(
            '<form id="pk-form" method="post" action="/traitement/prechargement" '
            'class="grid-form" style="grid-template-columns:1fr">'
            + _bloc_fokontany(communes, choisis)
            + '<div><label><b>Mode d&rsquo;affectation des m&eacute;nages aux '
              f'agents</b></label>{opts}</div>'
              '<div><label><b>Format g&eacute;ographique du fichier</b></label>'
              f'{fmt_opts}</div>'
              '<div><button>G&eacute;n&eacute;rer, enregistrer et '
              't&eacute;l&eacute;charger (ZIP)</button></div></form>')
        h.append('<div class="note">Modes : <b>D&eacute;nombrement</b> = chaque '
                 'm&eacute;nage reste &agrave; l&rsquo;agent qui l&rsquo;a '
                 'd&eacute;nombr&eacute;. <b>&Eacute;quilibr&eacute;</b> = '
                 'r&eacute;partit la charge (&plusmn;10 %) sans changer de commune. '
                 '<b>&Eacute;quilibr&eacute; fort</b> = pousse l&rsquo;&eacute;quilibre '
                 'par des &eacute;changes de segments. L&rsquo;&eacute;quilibrage ne '
                 'porte que sur les ménages de la sortie.</div>')
    h.append('<h2>Préchargements déjà enregistrés</h2>'
             + (_table_lots(lots(conn, code_district)) if code_district else ''))
    h.append('<div class="note">Seul le <b>dernier</b> lot peut être annulé : ses '
             'ménages redeviennent « à précharger ». N’annulez un lot que si son '
             'fichier n’a <b>pas</b> été envoyé.</div>')
    h.append(_JS_PAGE)
    h.append('</div></body></html>')
    return "".join(h)
