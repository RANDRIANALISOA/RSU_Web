# -*- coding: utf-8 -*-
"""vad_listing.py — portage du do-file INSTAT « listing des erreurs VAD ».

Reproduit, depuis la BASE et non depuis les `.dta`, les quatre classeurs que
`do_listing_erreur_VAD_RSU_V2.do` produit, et les emballe dans un `.zip` dont le
contenu dépend du rôle :

    Traitement / Expert survey / Coordonnateur / Admin
        TABLEAU_DE_BORD_VAD_<district>_<date>.xlsx
        base_erreur_menage_numero_X_<date>.xlsx
        base_erreur_membre_numero_X_<date>.xlsx
        ERREUR_MENAGE_<CE>_<date>.xlsx
    Superviseur Technique
        TABLEAU_DE_BORD_VAD_<district>_<date>.xlsx
        ERREUR_MENAGE_<CE>_<date>.xlsx

POURQUOI UN PORTAGE ET PAS L'APPEL DU DO-FILE
    Stata n'est pas sur le serveur, et le do-file suppose une arborescence
    Windows (C:\\RSU_VAGUE2\\VAD). Les données, elles, sont déjà en base :
    `vad_menage` porte les 177 colonnes du questionnaire ménage et `vad_membre`
    les 113 du roster, value labels compris (`_value_labels`). Tout ce que le
    do-file lit dans l'export s'y retrouve — À UNE EXCEPTION PRÈS, le login du
    chef d'équipe : voir `charger_ce()`.

FIDÉLITÉ AUX VALEURS MANQUANTES DE STATA — le point délicat
    En Stata, un manquant est PLUS GRAND que tout nombre : `M4>5` est VRAI quand
    `M4` est manquant. Le do-file s'en protège partout par `& !missing(M4)`, et
    s'appuie à l'inverse sur `M4<12`, qui est FAUX sur un manquant. `_gt`/`_ge`
    et `_lt` ci-dessous reproduisent exactement ces deux comportements ; les
    écrire naïvement inverserait le sens de plusieurs contrôles.

    Côté chaînes : "" = question NON POSÉE (filtre), "##N/A##" = question POSÉE
    mais SANS RÉPONSE. `missing()` ne vaut que pour la première ; le do-file
    teste "##N/A##" explicitement là où il le faut. On fait de même.

LES MESSAGES SONT ÉCRITS EN CLAIR DANS LES CELLULES
    Le do-file obtient ses messages malgaches par un `label define 0 "" 1 "…"`
    qu'`export excel` transcrit dans la cellule. openpyxl n'a pas de value
    labels : on écrit donc la chaîne directement, ce qui donne le même classeur.
"""
from __future__ import annotations

import datetime
import io
import math
import os
import re
import unicodedata
import zipfile

from openpyxl import Workbook

import config
import db_source
import lire_dta
import vad_db

# ---------------------------------------------------------------------------
# Paramètres — ÉTAPE 1 du do-file
# ---------------------------------------------------------------------------
STATUTS = (100, 120)      # 100 Completed, 120 ApprovedBySupervisor
TAILLE_LOT = 199          # ménages par fichier Expert Survey Solutions
DUREE_MIN = 10            # minutes : durée minimale d'une interview
ECART_TAILLE = 3          # écart max. entre membres VAD et dénombrement
DIST_MAX = 5              # km entre GPS du ménage et GPS du ZD

# Qui reçoit quoi. `perimetre()` borne déjà un SupTech à SES communes : il ne
# verra donc que ses propres chefs d'équipe, sans filtre supplémentaire ici.
ROLES_COMPLET = ("Admin", "Traitement", "Expert survey",
                 "Coordonnateur Nationale", "Coordonnateur régionale")
ROLES_RESTREINT = ("Superviseur Technique",)

# ---------------------------------------------------------------------------
# Les erreurs : nom, titre de colonne, message affiché dans la cellule.
# Titres et messages repris MOT POUR MOT du do-file : ces fichiers sont relus
# par des gens qui connaissent les libellés de l'an dernier.
# ---------------------------------------------------------------------------
ERR_MENAGE = (
    ("erreur_fokontany", "erreur fokontany",
     "Tsy feno ny fokontany/commune"),
    ("err_bien", "erreur possession de biens",
     "Misy tsy feno ny fananan'ny tokantrano"),
    ("erreur_refus_RSU", "erreur Permission RSU",
     "Tsy mazava ny antony fandavana/tsy feno ny consentement RSU/etc..."),
    ("err_caract_log", "erreur caractéristiques du logement",
     "Misy tsy feno ny toetrin'ny trano fonenana"),
)
ERR_INDIVIDU = ("err_individu", "err_individu",
                "Misy erreur mahakasika ny olona ao an-tokantrano")

ERR_MEMBRE = (
    ("err_membre", "err_membre",
     "Hamarino sao membre ménage ihany: raha mihoatra ny 6mois ny absence dia "
     "tsy membre intsony sinon mbola membre ihany"),
    ("err_cm_cj", "err_cm_cj",
     "Tsy misy lohatokantrano/Lohatokatrano mihoatra ny roa/Vady roa ao anaty "
     "tokantrano iray/Taonan'ny lohatokantrano na ny vadiny latsaky ny 12 taona"),
    ("err_sexe_cm_cj", "err_sexe_cm_cj",
     "Mitovy fananahana (sexe) ny lohatokantrano sy ny vadiny"),
    ("err_M7_M3_M4_M8_M5_vide", "err_M7_M3_M4_M8_M5_vide",
     "Misy tsy feno ny  lien de parente, sexe, age en année révolue, copie "
     "d'acte de naissance, statut matrimonial"),
    ("err_education", "err_education",
     "Misy tsy feno ny section education et alphabetisation"),
    ("err_handicap", "err_handicap", "Misy tsy feno ny section handicap"),
    ("err_validation_e_fkt", "err_validation_e_fkt",
     "Tsy azo valider'na ny information e-fokontany banga, atao TSIA foana ny valiny"),
    ("err_emploi", "err_emploi", "Misy tsy feno ny section asa (emploi)"),
    ("err_emploi_coherence", "err_emploi_coherence",
     "Hamarino ny asa: tsy mifanaraka ny valiny (mpianatra nefa tsy mianatra, "
     "misotro ronono latsaky ny 40 taona, fanjakana nefa asa manokana, CNAPS)"),
)

NOMS_ERR_MENAGE = [n for n, _, _ in ERR_MENAGE]
NOMS_ERR_MEMBRE = [n for n, _, _ in ERR_MEMBRE]
MSG_MENAGE = dict((n, m) for n, _, m in ERR_MENAGE)
MSG_MEMBRE = dict((n, m) for n, _, m in ERR_MEMBRE)

# Caractéristiques du logement. H3 n'existe PAS dans les données (vérifié sur
# `vad_menage`) : son absence de la liste du do-file est correcte, pas un oubli.
CARACT_LOG = ("H1", "H2", "H4", "H5", "H6", "H7", "H8", "H9", "H10")
# Handicap : AUEM17h n'existe pas non plus — même remarque.
HANDICAP = ("AUEM17a", "AUEM17b", "AUEM17c", "AUEM17d", "AUEM17e", "AUEM17f",
            "AUEM17g", "AUEM17i")
EMPLOI = ("M19a", "M19b", "M19c", "M19d", "M19e", "M19f", "M19g", "M19h",
          "M19i", "M19j")
OCCUPE = (1, 2, 3, 4, 11, 12, 13)

# Feuil3 du fichier membre : erreur -> variables du questionnaire (45 lignes).
FEUIL3 = (
    ("err_cm_cj", "M7"),
    ("err_sexe_cm_cj", "M3"), ("err_sexe_cm_cj", "M7"),
    ("err_handicap", "AUEM17a"), ("err_handicap", "AUEM17b"),
    ("err_handicap", "AUEM17c"), ("err_handicap", "AUEM17d"),
    ("err_handicap", "AUEM17e"), ("err_handicap", "AUEM17f"),
    ("err_handicap", "AUEM17g"), ("err_handicap", "AUEM17i"),
    ("err_M7_M3_M4_M8_M5_vide", "M3"), ("err_M7_M3_M4_M8_M5_vide", "M4"),
    ("err_M7_M3_M4_M8_M5_vide", "M5"), ("err_M7_M3_M4_M8_M5_vide", "M7"),
    ("err_M7_M3_M4_M8_M5_vide", "M8"),
    ("err_education", "M13"), ("err_education", "M14"),
    ("err_education", "M15"), ("err_education", "M16a"),
    ("err_education", "M16b"),
    ("err_validation_e_fkt", "M1b"), ("err_validation_e_fkt", "M4a"),
    ("err_validation_e_fkt", "M5e"), ("err_validation_e_fkt", "M7"),
    ("err_validation_e_fkt", "M3"), ("err_validation_e_fkt", "M8"),
    ("err_emploi", "M19"), ("err_emploi", "M19a"), ("err_emploi", "M19b"),
    ("err_emploi", "M19c"), ("err_emploi", "M19d"), ("err_emploi", "M19da"),
    ("err_emploi", "M19e"), ("err_emploi", "M19f"), ("err_emploi", "M19g"),
    ("err_emploi", "M19h"), ("err_emploi", "M19i"), ("err_emploi", "M19j"),
    ("err_emploi_coherence", "M19"), ("err_emploi_coherence", "M19a"),
    ("err_emploi_coherence", "M19d"), ("err_emploi_coherence", "M19e"),
    ("err_emploi_coherence", "M13"), ("err_emploi_coherence", "M15"),
)

T_REGISTRE = "vad_registre_erreurs"
T_CE = "vad_ce"


# ---------------------------------------------------------------------------
# Sémantique Stata des valeurs manquantes (cf. docstring du module)
# ---------------------------------------------------------------------------
def _vide(v) -> bool:
    """`missing(v)` de Stata : `.`/`.a`..`.z` (None ici) et, pour une chaîne, la
    chaîne vide. « ##N/A## » n'est PAS manquant — c'est une réponse absente sur
    une question POSÉE, testée explicitement là où le do-file le fait."""
    return v is None or (isinstance(v, str) and v.strip() == "")


def _num(v):
    """Valeur numérique, ou None si elle n'en est pas une."""
    if v is None or isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _gt(v, seuil) -> bool:
    """`v > seuil & !missing(v)` — la forme TOUJOURS employée par le do-file."""
    v = _num(v)
    return v is not None and v > seuil


def _ge(v, seuil) -> bool:
    v = _num(v)
    return v is not None and v >= seuil


def _lt(v, seuil) -> bool:
    """`v < seuil` de Stata : FAUX sur un manquant, puisqu'un manquant y est plus
    grand que tout nombre. C'est sur ce comportement que reposent `M4<12`
    (err_cm_cj) et `M4<40` (err_emploi_coherence)."""
    v = _num(v)
    return v is not None and v < seuil


def _eq(v, val) -> bool:
    v = _num(v)
    return v is not None and v == val


def _dans(v, *vals) -> bool:
    """`inlist()` de Stata sur des nombres : faux sur un manquant."""
    v = _num(v)
    return v is not None and v in vals


def _txt(v) -> str:
    return "" if v is None else str(v)


def _na(v) -> bool:
    """Chaîne vide ou « ##N/A## » — le `inlist(x,"","##N/A##")` du do-file."""
    return _txt(v).strip() in ("", "##N/A##")


# ---------------------------------------------------------------------------
# Horodatage — « 20260926_07H30 », exactement le `$date` du do-file
# ---------------------------------------------------------------------------
def decalage_client(valeur):
    """Minutes a l'EST de UTC, lues du parametre `tz` ajoute par le navigateur.

    None si absent ou aberrant — on retombe alors sur l'horloge du serveur
    plutot que de refuser l'export. Bornes : -12h a +14h, l'amplitude reelle
    des fuseaux.
    """
    try:
        n = int(str(valeur).strip())
    except (TypeError, ValueError):
        return None
    return n if -720 <= n <= 840 else None


def maintenant(decalage=None):
    """Heure du POSTE de l'utilisateur, ou celle du serveur a defaut.

    On ne prend pas une date fabriquee par le navigateur : elle finirait telle
    quelle dans le nom des fichiers. Le decalage, lui, est un entier borne.
    """
    if decalage is None:
        return datetime.datetime.now()
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=decalage)).replace(tzinfo=None)


def horodatage(quand=None) -> str:
    return (quand or datetime.datetime.now()).strftime("%Y%m%d_%HH%M")


def _assaini(nom) -> str:
    """Nom utilisable comme dossier dans un ZIP : accents retirés, caractères
    interdits remplacés. Un libellé de commune contenant « / » créerait sinon un
    niveau de dossier fantôme, et un « : » casserait l'extraction sous Windows."""
    nom = unicodedata.normalize("NFKD", _txt(nom)).encode("ascii", "ignore").decode()
    nom = re.sub(r"[^A-Za-z0-9 ._-]+", "_", nom).strip(" ._-")
    return nom or "SANS_NOM"


# ---------------------------------------------------------------------------
# Le chef d'équipe (CQ2) — la seule donnée absente de l'ingestion courante
# ---------------------------------------------------------------------------
def charger_ce(conn, districts=None) -> int:
    """Remplit `vad_ce` (interview__key -> login du CE) depuis
    `interview__actions.dta`, qui n'est PAS ingéré par `vad_db`.

    Le do-file prend le CE dans `interview__actions` filtré sur `action == 0`
    (SupervisorAssigned), en gardant la DERNIÈRE action par interview : un
    transfert d'équipe doit donner le CE actuel, pas le premier.

    Lecture par `lire_dta` — Python pur : ni pandas ni pyreadstat ne sont
    installés sur ce serveur, et `charger_ce_vad.py` (qui importe pyreadstat) ne
    peut donc pas y tourner.

    Renvoie le nombre d'interviews renseignées. Sans fichier, renvoie 0 sans
    lever : le rapport reste produit, avec « SANS_CE ».
    """
    trouves = []
    racine = os.path.join(config.UPLOAD_DIR, "VAD")
    for code in (sorted(districts) if districts else _dossiers_vad(racine)):
        chemin = os.path.join(racine, str(code), "interview__actions.dta")
        if os.path.exists(chemin):
            trouves.append(chemin)
    if not trouves:
        return 0

    dernier = {}          # key -> (date, time, login)
    for chemin in trouves:
        try:
            d = lire_dta.lire_dta(chemin)
        except Exception:
            continue
        cols = set(d.varnames)
        if not {"interview__key", "action", "responsible__name"} <= cols:
            continue
        cles = d.col("interview__key")
        actions = d.col("action")
        logins = d.col("responsible__name")
        dates = d.col("date") if "date" in cols else [None] * d.nobs
        heures = d.col("time") if "time" in cols else [None] * d.nobs
        for i in range(d.nobs):
            if not _eq(actions[i], 0):
                continue
            cle, login = _txt(cles[i]).strip(), _txt(logins[i]).strip()
            if not cle or not login:
                continue
            rang = (_txt(dates[i]), _txt(heures[i]))
            if cle not in dernier or rang >= dernier[cle][0]:
                dernier[cle] = (rang, login)

    if not dernier:
        return 0
    cur = conn.cursor()
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{T_CE}" '
                f'("interview__key" TEXT, "CE" TEXT)')
    ph = db_source._placeholder(conn)
    for cle, (_rang, login) in dernier.items():
        cur.execute(f'DELETE FROM "{T_CE}" WHERE "interview__key" = {ph}', (cle,))
        cur.execute(f'INSERT INTO "{T_CE}" VALUES ({ph}, {ph})', (cle, login))
    cur.execute(f'CREATE INDEX IF NOT EXISTS ix_vad_ce '
                f'ON "{T_CE}"("interview__key")')
    conn.commit()
    return len(dernier)


def _dossiers_vad(racine) -> list:
    try:
        return sorted(n for n in os.listdir(racine) if n.isdigit())
    except OSError:
        return []


def _ce_par_interview(conn, districts=None, cles=None) -> dict:
    """interview__key -> login du CE, avec deux replis successifs.

    1. `vad_ce`, alimentée par `charger_ce()` — la voie du do-file ;
    2. `agent.login_ce` via l'enquêteur (`vad_diagnostics.responsible`), quand
       l'export des actions n'est plus sur le disque mais que les équipes ont
       été téléversées ;
    3. « SANS_CE », comme le do-file.

    Le repli 2 n'est pas cosmétique : sans lui, le jour où le dossier d'export
    est purgé, les fichiers par CE deviendraient un seul fichier « SANS_CE ».
    """
    out = {}
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT "interview__key", "CE" FROM "{T_CE}"')
        for k, v in cur.fetchall():
            if _txt(v).strip():
                out[_txt(k)] = _txt(v).strip()
    except Exception:
        pass
    if cles is None or not set(cles) - set(out):
        return out
    try:
        cur.execute('SELECT d."interview__key", a."login_ce" '
                    'FROM "vad_diagnostics" d '
                    'JOIN "agent" a ON a."login_ae" = d."responsible" '
                    'WHERE a."login_ce" IS NOT NULL AND a."login_ce" <> \'\'')
        for k, v in cur.fetchall():
            out.setdefault(_txt(k), _txt(v).strip())
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Lecture — ÉTAPES 4 à 6 du do-file
# ---------------------------------------------------------------------------
def _dataset(conn, table, where="", params=()):
    return db_source.DbDataset(conn, table, where, params)


def _colonnes(d, noms, decode=()):
    """{nom: colonne}. Une variable absente rend une colonne de None plutôt que
    de faire échouer le rapport : le questionnaire bouge d'une vague à l'autre."""
    cols = set(d.varnames)
    vide = [None] * d.nobs
    out = {}
    for n in noms:
        if n not in cols:
            out[n] = vide
        else:
            out[n] = d.col_decoded(n) if n in decode else d.col(n)
    return out


def lire(conn, districts=None, communes=None) -> dict:
    """Ménages contrôlés et membres, avec toutes les erreurs calculées.

    Reproduit l'ordre du do-file : erreurs ménage (§5), erreurs membres (§6),
    puis remontée de `err_individu` sur le ménage.
    """
    where, params = vad_db._clause_perimetre(conn, districts, communes)
    dm = _dataset(conn, vad_db.TABLE_MENAGE, where, params)
    cols_men = set(dm.varnames)

    biens = sorted(c for c in cols_men
                   if c.startswith(("AP1__", "AP2__", "AP3__", "AP4__")))
    simples = (("interview__key", "interview__id", "nom_cm", "CQ10",
                "Perm_indiv", "Perm_rsu", "Perm_rsuNo", "interview__status",
                "CQ3", "CQ4", "nbmembre", "taille_men", "has__errors",
                "GPS__Latitude", "GPS__Longitude", "GPS_Lat_ZD", "GPS_Long_ZD",
                "CQ7", "CQ8", "CQ9")
               + CARACT_LOG + tuple(biens))
    lu = _colonnes(dm, simples)
    lib = _colonnes(dm, ("CQ6", "CQ7", "CQ8", "CQ9"),
                    decode=("CQ6", "CQ7", "CQ8", "CQ9"))

    # Doublons d'ID RSU : comptés sur TOUTES les interviews, avant le filtre de
    # statut — comme le do-file, qui les calcule avant `keep if statut_ok`.
    compte_id = {}
    for i in range(dm.nobs):
        cle = _txt(lu["CQ10"][i]).strip()
        if cle not in ("", "##N/A##"):
            compte_id[cle] = compte_id.get(cle, 0) + 1

    ce_map = _ce_par_interview(conn, districts,
                              [_txt(k) for k in lu["interview__key"]])
    enq_map = _enqueteurs(conn)

    menages = []
    for i in range(dm.nobs):
        # Interviews terminées ou approuvées seulement…
        if not _dans(lu["interview__status"][i], *STATUTS):
            continue
        # … et ménage présent ou ayant accepté le RSU.
        if not (_eq(lu["Perm_indiv"][i], 1) or _eq(lu["Perm_rsu"][i], 1)):
            continue
        cle = _txt(lu["interview__key"][i])
        perm_rsu = lu["Perm_rsu"][i]
        accepte = _eq(perm_rsu, 1)

        m = {
            "key": cle,
            "id": _txt(lu["interview__id"][i]),
            "nom_cm": _txt(lu["nom_cm"][i]),
            "CQ6": _txt(lib["CQ6"][i]), "CQ7": _txt(lib["CQ7"][i]),
            "CQ8": _txt(lib["CQ8"][i]), "CQ9": _txt(lib["CQ9"][i]),
            "code_district": _num(lu["CQ7"][i]),
            "_code_commune": _num(lu["CQ8"][i]),
            "CQ10": _txt(lu["CQ10"][i]),
            "CQ2": ce_map.get(cle) or "SANS_CE",
            "CQ1": enq_map.get(cle) or "SANS_ENQ",
        }

        # 5.1 Fokontany / commune vide
        m["erreur_fokontany"] = _vide(lu["CQ9"][i]) or _vide(lu["CQ8"][i])

        # 5.2 Possession de biens : tout ménage qui a accepté le RSU DOIT les
        # avoir. Un manquant couvre les deux cas du do-file — bien affiché sans
        # réponse (.a) et section jamais ouverte (.).
        m["err_bien"] = accepte and any(_vide(lu[b][i]) for b in biens)

        # 5.4 Refus du RSU sans motif clair (moins de 5 caractères, ou ##N/A##)
        motif = _txt(lu["Perm_rsuNo"][i])
        m["erreur_refus_RSU"] = (_eq(perm_rsu, 2)
                                 and (motif.strip() == "##N/A##"
                                      or len(motif.strip()) < 5))

        # 5.5 Caractéristiques du logement
        m["err_caract_log"] = accepte and any(_vide(lu[h][i]) for h in CARACT_LOG)

        # Contrôles complémentaires (tableau de bord seulement)
        m["_perm_indiv"] = lu["Perm_indiv"][i]
        m["_perm_rsu"] = perm_rsu
        m["_nb_meme_id"] = compte_id.get(_txt(lu["CQ10"][i]).strip())
        m["_nbmembre"] = _num(lu["nbmembre"][i])
        m["_taille_men"] = _num(lu["taille_men"][i])
        m["_has_errors"] = _num(lu["has__errors"][i])
        m["_duree"] = _duree(lu["CQ3"][i], lu["CQ4"][i])
        m["_dist"] = _distance(lu["GPS__Latitude"][i], lu["GPS__Longitude"][i],
                               lu["GPS_Lat_ZD"][i], lu["GPS_Long_ZD"][i])
        m["_lat"] = _num(lu["GPS__Latitude"][i])
        menages.append(m)

    membres = _lire_membres(conn, where, params, set(m["key"] for m in menages))

    # Remontée : un ménage dont au moins un membre faute porte err_individu
    fautifs = set(x["key"] for x in membres if x["err_ensemble"])
    for m in menages:
        m["err_individu"] = m["key"] in fautifs
        m["err_total"] = any(m[n] for n in NOMS_ERR_MENAGE) or m["err_individu"]

    # Le nom du chef de ménage et la géographie viennent du ménage (le do-file
    # les rapatrie par un merge m:1 avant de calculer les erreurs membres).
    par_cle = dict((m["key"], m) for m in menages)
    for x in membres:
        m = par_cle.get(x["key"])
        if m:
            for champ in ("nom_cm", "CQ6", "CQ7", "CQ8", "CQ9", "CQ2", "CQ1",
                          "id", "_code_commune"):
                x[champ] = m[champ]
    membres = [x for x in membres if x["key"] in par_cle]
    return {"menages": menages, "membres": membres}


def _enqueteurs(conn) -> dict:
    """interview__key -> login de l'enquêteur (`responsible` de vad_diagnostics),
    le CQ1 du do-file."""
    out = {}
    try:
        cur = conn.cursor()
        cur.execute('SELECT "interview__key", "responsible" FROM "vad_diagnostics"')
        for k, v in cur.fetchall():
            if _txt(v).strip():
                out[_txt(k)] = _txt(v).strip()
    except Exception:
        pass
    return out


def _lire_membres(conn, where, params, cles_gardees) -> list:
    sous = f'SELECT "interview__key" FROM "{vad_db.TABLE_MENAGE}"' + (
        f" WHERE {where}" if where else "")
    try:
        d = _dataset(conn, vad_db.TABLE_MEMBRE,
                     f'"interview__key" IN ({sous})', params)
    except Exception:
        return []
    if not d.nobs:
        return []

    NUM_PRELOAD = ("M7", "M3", "M8")
    TXT_PRELOAD = ("M4a", "M5e", "M6a", "M6b", "M6d", "M7a", "M7b")
    noms = (("interview__key", "RMen__id", "M1a", "membre_valid",
             "nomembre_motif_Oth", "M3", "M4", "M5", "M7", "M8",
             "M13", "M14", "M15", "M16a", "M16b", "M19", "M19da", "M1b")
            + HANDICAP + EMPLOI + NUM_PRELOAD + TXT_PRELOAD
            + tuple(f"{v}_preload" for v in NUM_PRELOAD + TXT_PRELOAD + ("M1b",))
            + tuple(f"{v}_valid" for v in NUM_PRELOAD + TXT_PRELOAD + ("M1b",)))
    lu = _colonnes(d, tuple(dict.fromkeys(noms)))

    # Première passe : récupérer les valeurs préchargées validées (§6.1), puis
    # les agrégats par ménage (nb de CM, de conjoints, sexes) — le do-file les
    # calcule par `egen … by(interview__key)` avant de tester.
    lignes = []
    for i in range(d.nobs):
        v = dict((n, lu[n][i]) for n in lu)
        # 6.1 Le membre était déjà dans e-fokontany et l'enquêteur a VALIDÉ
        # l'information préchargée : la question n'est pas posée, on reprend la
        # valeur préchargée. Sans cela tout ménage déjà connu serait en erreur.
        for x in NUM_PRELOAD:
            if (_vide(v.get(x)) and _eq(v.get(f"{x}_valid"), 1)
                    and not _vide(v.get(f"{x}_preload"))):
                v[x] = v[f"{x}_preload"]
        for x in TXT_PRELOAD:
            if (_na(v.get(x)) and _eq(v.get(f"{x}_valid"), 1)
                    and not _na(v.get(f"{x}_preload"))):
                v[x] = v[f"{x}_preload"]
        v["key"] = _txt(v["interview__key"])
        v["actif"] = _dans(v.get("membre_valid"), 1, 2)
        lignes.append(v)

    agg = {}
    for v in lignes:
        a = agg.setdefault(v["key"], {"nb_cm": 0, "nb_cj": 0,
                                      "sexe_cm": None, "sexe_cj": None})
        if v["actif"] and _eq(v.get("M7"), 1):
            a["nb_cm"] += 1
            s = _num(v.get("M3"))
            if s is not None:
                a["sexe_cm"] = s if a["sexe_cm"] is None else max(a["sexe_cm"], s)
        if v["actif"] and _eq(v.get("M7"), 2):
            a["nb_cj"] += 1
            s = _num(v.get("M3"))
            if s is not None:
                a["sexe_cj"] = s if a["sexe_cj"] is None else max(a["sexe_cj"], s)

    out = []
    for v in lignes:
        a = agg[v["key"]]
        actif = v["actif"]
        M4, M7 = v.get("M4"), v.get("M7")

        # 6.2 Motif « non membre » qui ressemble à une absence temporaire
        motif = _txt(v.get("nomembre_motif_Oth")).upper()
        v["err_membre"] = ("IASA" in motif) or ("KARAMA" in motif)
        # Le do-file vide la colonne quand il n'y a pas d'erreur : c'est cette
        # colonne qui est envoyée aux Experts, pas le motif brut.
        v["nomemnre_motif_Oth_util"] = motif if v["err_membre"] else ""

        # 6.3 Pas de CM, plusieurs CM, plusieurs conjoints, CM/conjoint < 12 ans
        v["err_cm_cj"] = bool(actif and (
            a["nb_cm"] != 1
            or (a["nb_cj"] > 1 and _dans(M7, 1, 2))
            or (_dans(M7, 1, 2) and _lt(M4, 12))))

        # 6.4 CM et conjoint de même sexe
        v["err_sexe_cm_cj"] = bool(
            actif and _dans(M7, 1, 2) and a["nb_cm"] == 1 and a["nb_cj"] == 1
            and a["sexe_cm"] is not None and a["sexe_cm"] == a["sexe_cj"]
            and not v["err_cm_cj"])

        # 6.5 Lien, sexe, âge, acte de naissance, statut matrimonial
        v["err_M7_M3_M4_M8_M5_vide"] = bool(actif and (
            _vide(M7) or _vide(v.get("M3")) or _vide(M4) or _vide(v.get("M5"))
            or (_vide(v.get("M8")) and _ge(M4, 10))))

        # 6.6 Éducation et alphabétisation
        M13 = v.get("M13")
        v["err_education"] = bool(actif and (
            (_ge(M4, 5) and _vide(M13))
            or (_eq(M13, 1) and (_vide(v.get("M14")) or _vide(v.get("M15"))))
            or (not _vide(M13) and (_vide(v.get("M16a")) or _vide(v.get("M16b"))))))

        # 6.7 Handicap (plus de 5 ans)
        v["err_handicap"] = bool(
            actif and _gt(M4, 5) and any(_vide(v.get(h)) for h in HANDICAP))

        # 6.8 Information e-fokontany vide mais validée
        val = False
        for x in ("M1b", "M4a", "M5e"):
            if _na(v.get(f"{x}_preload")) and _eq(v.get(f"{x}_valid"), 1):
                val = True
        for x in ("M7", "M3", "M8"):
            if _vide(v.get(f"{x}_preload")) and _eq(v.get(f"{x}_valid"), 1):
                val = True
        if (_vide(v.get("M8")) and _lt(M4, 10)) or not _eq(v.get("membre_valid"), 1):
            val = False
        v["err_validation_e_fkt"] = val

        # 6.9 Emploi — section ajoutée cette vague
        M19 = v.get("M19")
        occupe = _dans(M19, *OCCUPE)
        err = False
        if actif and _gt(M4, 15) and _vide(M19):
            err = True
        if actif and occupe and any(_vide(v.get(x)) for x in EMPLOI):
            err = True
        if actif and _dans(v.get("M19d"), 1, 2) and _txt(v.get("M19da")).strip() == "##N/A##":
            err = True
        v["err_emploi"] = err

        # 6.10 Cohérence de l'emploi
        v["err_emploi_coherence"] = bool(actif and (
            (_eq(M19, 7) and (_eq(M13, 2) or _eq(v.get("M15"), 2)))
            or (_eq(M19, 8) and _lt(M4, 40))
            or (_eq(M19, 1) and _eq(v.get("M19d"), 3))
            or (_eq(v.get("M19e"), 1) and _eq(v.get("M19a"), 2))))

        v["err_ensemble"] = any(v[n] for n in NOMS_ERR_MEMBRE)
        out.append(v)
    return out


def _duree(debut, fin):
    """Durée d'interview en minutes, depuis CQ3/CQ4 (« 2026-09-11T05:09:08 »).

    ⚠️ Le do-file ne traite pas le passage de minuit autrement : une durée
    négative reste négative, donc sous le seuil, donc signalée. On garde ce
    comportement — signaler une interview à cheval sur minuit n'est pas absurde.
    """
    a, b = _instant(debut), _instant(fin)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 60.0


def _instant(v):
    t = _txt(v).strip().replace("T", " ")
    if not t:
        return None
    for forme in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                  "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(t[:19], forme)
        except ValueError:
            continue
    return None


def _distance(lat, lon, lat_zd, lon_zd):
    """Distance haversine en km entre le ménage et le point de référence du ZD.
    Même formule que le do-file (rayon 6371 km)."""
    lat, lon = _num(lat), _num(lon)
    lat_zd, lon_zd = _num(lat_zd), _num(lon_zd)
    if None in (lat, lon, lat_zd, lon_zd):
        return None
    r = math.pi / 180
    h = (math.sin(r * (lat_zd - lat) / 2) ** 2
         + math.cos(r * lat) * math.cos(r * lat_zd)
         * math.sin(r * (lon_zd - lon) / 2) ** 2)
    return 2 * 6371 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


# ---------------------------------------------------------------------------
# Registre des ménages signalés — ÉTAPES 8 et 11 du do-file
# ---------------------------------------------------------------------------
def _creer_registre(conn):
    conn.cursor().execute(
        f'CREATE TABLE IF NOT EXISTS "{T_REGISTRE}" ('
        f'"interview__key" TEXT PRIMARY KEY, "nb_signalements" INTEGER, '
        f'"date_premier" TEXT, "date_dernier" TEXT)')
    conn.commit()


def _lire_registre(conn) -> dict:
    _creer_registre(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "interview__key","nb_signalements","date_premier",'
                f'"date_dernier" FROM "{T_REGISTRE}"')
    return dict((_txt(r[0]), {"nb": r[1], "premier": _txt(r[2]),
                              "dernier": _txt(r[3])}) for r in cur.fetchall())


def _maj_registre(conn, cles, cachet):
    """Incrémente le compteur de signalements — mais AU PLUS UNE FOIS PAR JOUR.

    ⚠️ Écart assumé avec le do-file, et c'est le seul. Le do-file incrémente à
    chaque exécution, ce qui est juste quand une personne le lance une fois par
    jour. Ici, quatre rôles peuvent cliquer sur le bouton le même matin : sans
    ce garde-fou, un ménage signalé une seule fois afficherait « Relance n°4 ».
    La date du jour sert donc de verrou.
    """
    _creer_registre(conn)
    jour = cachet.split("_")[0]
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    for cle in cles:
        cur.execute(f'SELECT "nb_signalements","date_premier","date_dernier" '
                    f'FROM "{T_REGISTRE}" WHERE "interview__key" = {ph}', (cle,))
        ligne = cur.fetchone()
        if ligne is None:
            cur.execute(f'INSERT INTO "{T_REGISTRE}" VALUES ({ph},{ph},{ph},{ph})',
                        (cle, 1, cachet, cachet))
        elif _txt(ligne[2]).split("_")[0] != jour:
            cur.execute(f'UPDATE "{T_REGISTRE}" SET "nb_signalements" = {ph}, '
                        f'"date_dernier" = {ph} WHERE "interview__key" = {ph}',
                        ((ligne[0] or 0) + 1, cachet, cle))
    conn.commit()


# ---------------------------------------------------------------------------
# La répartition SupTech / commune — l'équivalent web de REPARTITION_EQUIPES
# ---------------------------------------------------------------------------
def _suptech_par_commune(conn) -> dict:
    """code_commune -> login du Superviseur Technique.

    Le do-file lit un Excel rempli à la main (`0_PARAMETRES`). Ici l'information
    existe déjà en base : `superviseur_commune` affecte chaque SupTech à ses
    communes. Une donnée déjà saisie ne se redemande pas.
    """
    out = {}
    try:
        cur = conn.cursor()
        cur.execute('SELECT "code_commune", "login" FROM "superviseur_commune"')
        for code, login in cur.fetchall():
            out.setdefault(int(code), _txt(login))
    except Exception:
        pass
    return out


def _affectations(conn, menages) -> dict:
    """CE -> (suptech, commune). La commune retenue est celle où le CE a le PLUS
    de ménages, comme le `bysort CQ2 (n): keep if _n==_N` du do-file."""
    sup_par_commune = _suptech_par_commune(conn)
    code_par_nom = {}
    compte = {}
    for m in menages:
        compte.setdefault(m["CQ2"], {})
        nom = m["CQ8"] or "COMMUNE_NON_DEFINIE"
        compte[m["CQ2"]][nom] = compte[m["CQ2"]].get(nom, 0) + 1
        code_par_nom.setdefault(nom, m.get("_code_commune"))
    out = {}
    for ce, communes in compte.items():
        nom = max(sorted(communes), key=lambda c: communes[c])
        code = code_par_nom.get(nom)
        out[ce] = (sup_par_commune.get(code) or "SANS_SUPTECH", nom)
    return out


# ---------------------------------------------------------------------------
# Écriture des classeurs
# ---------------------------------------------------------------------------
def _feuille(wb, titre, entetes, lignes, premiere=False):
    ws = wb.active if premiere else wb.create_sheet()
    ws.title = titre[:31]
    ws.append(list(entetes))
    for l in lignes:
        ws.append(list(l))
    return ws


def _octets(wb) -> bytes:
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def nom_tableau_de_bord(district, cachet) -> str:
    return f"TABLEAU_DE_BORD_VAD_{district}_{cachet}.xlsx"


def tableau_de_bord(donnees, district, cachet) -> bytes:
    """Les 5 feuilles de l'ÉTAPE 7 : nombre de ménages et de personnes par type
    d'erreur, taux par CE puis par enquêteur, et les contrôles complémentaires."""
    menages, membres = donnees["menages"], donnees["membres"]
    wb = Workbook()

    # menage_par_type
    lignes = [(n, sum(1 for m in menages if m[n])) for n in NOMS_ERR_MENAGE]
    lignes.append((ERR_INDIVIDU[0], sum(1 for m in menages if m["err_individu"])))
    _feuille(wb, "menage_par_type", ("erreur", "nb_menages"), lignes, premiere=True)

    # membre_par_type
    _feuille(wb, "membre_par_type", ("erreur", "nb_personnes"),
             [(n, sum(1 for x in membres if x[n])) for n in NOMS_ERR_MEMBRE])

    # par_CE puis par_enqueteur — mêmes colonnes, mêmes tris
    for titre, cles in (("par_CE", ("CQ2",)), ("par_enqueteur", ("CQ2", "CQ1"))):
        groupes = {}
        for m in menages:
            k = tuple(m[c] for c in cles)
            g = groupes.setdefault(k, [0, 0])
            g[0] += 1
            g[1] += 1 if m["err_total"] else 0
        lignes = []
        for k, (total, err) in groupes.items():
            taux = round(100.0 * err / total, 1) if total else 0.0
            lignes.append(tuple(k) + (total, err, taux))
        lignes.sort(key=lambda r: -r[-1])
        entetes = (("chef_equipe",) if cles == ("CQ2",)
                   else ("chef_equipe", "enqueteur"))
        _feuille(wb, titre,
                 entetes + ("menages_controles", "menages_avec_erreur",
                            "taux_erreur_pct"), lignes)

    # controles_complementaires
    entetes = ("interview__key", "CQ7", "CQ8", "CQ9", "nom_cm", "CQ2", "CQ1",
               "CQ10", "duree_min", "dist_km", "cc_district", "cc_incomplet",
               "cc_idrsu_double", "cc_refus_avec_motif", "cc_taille",
               "cc_duree", "cc_gps", "cc_suso")
    lignes = []
    for m in menages:
        cc = _complementaires(m, district)
        if not any(cc):
            continue
        lignes.append((m["key"], m["CQ7"], m["CQ8"], m["CQ9"], m["nom_cm"],
                       m["CQ2"], m["CQ1"], m["CQ10"],
                       _arrondi(m["_duree"]), _arrondi(m["_dist"]))
                      + tuple(1 if c else 0 for c in cc))
    _feuille(wb, "controles_complementaires", entetes, lignes)
    return _octets(wb)


def _complementaires(m, district) -> tuple:
    """Les 8 drapeaux `cc_*`, dans l'ordre de création du do-file."""
    code = m.get("code_district")
    return (
        code is not None and district is not None and code != district,
        _eq(m["_perm_indiv"], 1) and _vide(m["_perm_rsu"]),
        (m["_nb_meme_id"] or 0) > 1,
        _eq(m["_perm_rsu"], 2) and not m["erreur_refus_RSU"],
        (m["_nbmembre"] is not None and m["_taille_men"] is not None
         and abs(m["_nbmembre"] - m["_taille_men"]) >= ECART_TAILLE),
        m["_duree"] is not None and m["_duree"] < DUREE_MIN,
        m["_lat"] is None or (m["_dist"] is not None and m["_dist"] > DIST_MAX),
        _gt(m["_has_errors"], 0),
    )


def _arrondi(v):
    return None if v is None else round(v, 2)


def _cellule_men(m, nom):
    """Le message si l'erreur est présente, une cellule VIDE sinon — c'est ce
    que donne le `label define 0 "" 1 "…"` du do-file."""
    return MSG_MENAGE[nom] if m[nom] else ""


def fichiers_experts(donnees, signalements, cachet) -> list:
    """[(nom, octets)] — les `base_erreur_menage/membre_numero_X`, par lots de
    199 ménages, le MÊME numéro de lot des deux côtés (le do-file le fait en
    reportant `lot` sur les membres)."""
    menages = [m for m in donnees["menages"] if m["err_total"]]
    if not menages:
        return []
    # Ordre du do-file : commune, fokontany, CE, enquêteur, identifiant.
    menages.sort(key=lambda m: (m["CQ8"], m["CQ9"], m["CQ2"], m["CQ1"], m["key"]))
    for i, m in enumerate(menages):
        m["_lot"] = i // TAILLE_LOT + 1
    lot_par_cle = dict((m["key"], m["_lot"]) for m in menages)
    cles = set(lot_par_cle)

    # Membres en erreur des ménages signalés, numérotés par ménage
    membres = [x for x in donnees["membres"]
               if x["err_ensemble"] and x["key"] in cles]
    membres.sort(key=lambda x: (x["key"], _num(x.get("RMen__id")) or 0))
    rang = {}
    for x in membres:
        rang[x["key"]] = rang.get(x["key"], 0) + 1
        x["_rang"] = rang[x["key"]]
    max_men = max(rang.values()) if rang else 1

    out = []
    for lot in sorted(set(lot_par_cle.values())):
        out.append((f"base_erreur_menage_numero_{lot}_{cachet}.xlsx",
                    _classeur_menage_experts(
                        [m for m in menages if m["_lot"] == lot],
                        signalements)))
        out.append((f"base_erreur_membre_numero_{lot}_{cachet}.xlsx",
                    _classeur_membre_experts(
                        [m for m in menages if m["_lot"] == lot],
                        [x for x in membres if lot_par_cle[x["key"]] == lot],
                        max_men)))
    return out


def _classeur_menage_experts(menages, signalements) -> bytes:
    wb = Workbook()
    entetes = (["Identifiant", "region", "district", "commune", "fokontany",
                "nom_cm", "chef d'equipe", "enqueteur", " "]
               + [t for _, t, _ in ERR_MENAGE] + [ERR_INDIVIDU[1], "DETAIL"])
    lignes = []
    for m in menages:
        lignes.append([m["key"], m["CQ6"], m["CQ7"], m["CQ8"], m["CQ9"],
                       m["nom_cm"], m["CQ2"], m["CQ1"], ""]
                      + [_cellule_men(m, n) for n in NOMS_ERR_MENAGE]
                      + [ERR_INDIVIDU[2] if m["err_individu"] else "", ""])
    _feuille(wb, "Feuil1", entetes, lignes, premiere=True)
    _feuille(wb, "Feuil2", ("Identifiant", "interview__id"),
             [(m["key"], m["id"]) for m in menages])
    return _octets(wb)


def _classeur_membre_experts(menages, membres, max_men) -> bytes:
    """Feuil1 au format LARGE : les colonnes sont groupées PAR ERREUR puis par
    numéro de membre (« 1 err_membre », « 2 err_membre », …), exactement comme
    la double boucle `foreach stub … forvalues j` du do-file."""
    stubs = ["err_membre", "nomemnre_motif_Oth_util"] + NOMS_ERR_MEMBRE[1:]
    entetes = (["Identifiant", "region", "district", "commune", "fokontany",
                "nom_cm", "chef d'equipe", "enqueteur"]
               + [f"{j} {s}" for s in stubs for j in range(1, max_men + 1)])

    par_cle = {}
    for x in membres:
        par_cle.setdefault(x["key"], {})[x["_rang"]] = x

    lignes = []
    for m in menages:
        if m["key"] not in par_cle:
            continue          # ménage signalé pour une erreur MÉNAGE seulement
        rangs = par_cle[m["key"]]
        ligne = [m["key"], m["CQ6"], m["CQ7"], m["CQ8"], m["CQ9"],
                 m["nom_cm"], m["CQ2"], m["CQ1"]]
        for s in stubs:
            for j in range(1, max_men + 1):
                x = rangs.get(j)
                if x is None:
                    ligne.append("")
                elif s == "nomemnre_motif_Oth_util":
                    ligne.append(x["nomemnre_motif_Oth_util"])
                else:
                    ligne.append(MSG_MEMBRE[s] if x[s] else "")
        lignes.append(ligne)

    wb = Workbook()
    _feuille(wb, "Feuil1", entetes, lignes, premiere=True)
    _feuille(wb, "Feuil2", ("Identifiant", "interview__id"),
             [(m["key"], m["id"]) for m in menages if m["key"] in par_cle])
    _feuille(wb, "Feuil3", ("err_membre", "nomemnre_motif_Oth_util"), FEUIL3)
    return _octets(wb)


def fichiers_ce(conn, donnees, signalements, cachet) -> list:
    """[(chemin_dans_le_zip, octets)] — un classeur par chef d'équipe, rangé
    sous <SupTech>/<commune>/ comme le do-file range ses dossiers."""
    menages = [m for m in donnees["menages"] if m["err_total"]]
    if not menages:
        return []
    affect = _affectations(conn, menages)
    par_ce = {}
    for m in menages:
        par_ce.setdefault(m["CQ2"], []).append(m)
    cles_ce = dict((ce, set(m["key"] for m in lst)) for ce, lst in par_ce.items())
    membres = [x for x in donnees["membres"] if x["err_ensemble"]]

    out = []
    for ce in sorted(par_ce):
        sup, commune = affect.get(ce, ("SANS_SUPTECH", "COMMUNE_NON_DEFINIE"))
        chemin = (f"5_ERREURS_SUPTECH_CE/{_assaini(sup)}/{_assaini(commune)}/"
                  f"ERREUR_MENAGE_{_assaini(ce)}_{cachet}.xlsx")
        out.append((chemin, _classeur_ce(
            par_ce[ce], [x for x in membres if x["key"] in cles_ce[ce]],
            signalements)))
    return out


def _classeur_ce(menages, membres, signalements) -> bytes:
    wb = Workbook()

    # erreur_menage
    entetes = (["Identifiant", "commune", "fokontany", "nom_cm", "enqueteur",
                "Signalement"] + [t for _, t, _ in ERR_MENAGE]
               + [ERR_INDIVIDU[1]])
    lignes = []
    for m in sorted(menages, key=lambda m: (m["CQ9"], m["key"])):
        lignes.append([m["key"], m["CQ8"], m["CQ9"], m["nom_cm"], m["CQ1"],
                       signalements.get(m["key"], "Vaovao")]
                      + [_cellule_men(m, n) for n in NOMS_ERR_MENAGE]
                      + [ERR_INDIVIDU[2] if m["err_individu"] else ""])
    _feuille(wb, "erreur_menage", entetes, lignes, premiere=True)

    # recap_enqueteur
    compte = {}
    for m in menages:
        compte[m["CQ1"]] = compte.get(m["CQ1"], 0) + 1
    _feuille(wb, "recap_enqueteur", ("enqueteur", "menages_avec_erreur"),
             sorted(compte.items()))

    # erreur_membre — une ligne par personne, avec son NOM : c'est ce qui rend
    # la liste utilisable sur le terrain.
    if membres:
        entetes = (["Identifiant", "nom_cm", "Numero membre", "Anarana",
                    "enqueteur", "Signalement", "nomemnre_motif_Oth_util"]
                   + [t for _, t, _ in ERR_MEMBRE])
        lignes = []
        for x in sorted(membres, key=lambda x: (x["key"],
                                                _num(x.get("RMen__id")) or 0)):
            lignes.append([x["key"], x.get("nom_cm", ""), x.get("RMen__id"),
                           _txt(x.get("M1a")), x.get("CQ1", ""),
                           signalements.get(x["key"], "Vaovao"),
                           x["nomemnre_motif_Oth_util"]]
                          + [MSG_MEMBRE[n] if x[n] else "" for n in NOMS_ERR_MEMBRE])
        _feuille(wb, "erreur_membre", entetes, lignes)
    return _octets(wb)


# ---------------------------------------------------------------------------
# L'archive — ce que le bouton « Rapport Excel » renvoie
# ---------------------------------------------------------------------------
def role_complet(role) -> bool:
    return _txt(role).strip() in ROLES_COMPLET


def autorise(role) -> bool:
    return role_complet(role) or _txt(role).strip() in ROLES_RESTREINT


def libelle_district(districts) -> str:
    if districts and len(districts) == 1:
        return str(sorted(districts)[0])
    return "TOUS" if not districts else "_".join(str(d) for d in sorted(districts))


def nom_zip(districts, cachet) -> str:
    return f"LISTING_ERREURS_VAD_{libelle_district(districts)}_{cachet}.zip"


def generer_zip(conn, role, districts=None, communes=None, quand=None,
                majr=True, decalage=None) -> tuple:
    """(nom_du_zip, octets). `role` décide du contenu (cf. en-tête du module).

    `majr=False` produit l'archive SANS toucher au registre : utile pour un
    essai, et pour ne pas transformer une consultation en signalement.
    """
    cachet = horodatage(quand or maintenant(decalage))
    charger_ce(conn, districts)              # CQ2 : voir charger_ce()
    donnees = lire(conn, districts, communes)
    district = sorted(districts)[0] if districts and len(districts) == 1 else None

    # Étiquette « Vaovao » / « Relance n°X », lue AVANT la mise à jour.
    registre = _lire_registre(conn)
    cles_err = [m["key"] for m in donnees["menages"] if m["err_total"]]
    signalements = {}
    for cle in cles_err:
        nb = (registre.get(cle) or {}).get("nb")
        signalements[cle] = f"Relance n°{nb}" if nb else "Vaovao"

    complet = role_complet(role)
    fichiers = [(f"6_TABLEAU_DE_BORD/{nom_tableau_de_bord(libelle_district(districts), cachet)}",
                 tableau_de_bord(donnees, district, cachet))]
    if complet:
        for nom, data in fichiers_experts(donnees, signalements, cachet):
            fichiers.append((f"4_ERREURS_EXPERTS_SURVEY/{nom}", data))
    fichiers.extend(fichiers_ce(conn, donnees, signalements, cachet))
    fichiers.append(("LISEZ-MOI.txt",
                     _lisez_moi(role, districts, cachet, donnees, complet)
                     .encode("utf-8")))

    if majr and cles_err:
        _maj_registre(conn, cles_err, cachet)

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for chemin, data in fichiers:
            z.writestr(chemin, data)
    return nom_zip(districts, cachet), tampon.getvalue()


def _lisez_moi(role, districts, cachet, donnees, complet) -> str:
    menages = donnees["menages"]
    err = [m for m in menages if m["err_total"]]
    lignes = [
        "LISTING DES ERREURS DE LA VISITE A DOMICILE (VAD)",
        "=" * 52, "",
        f"Genere le        : {cachet}",
        f"District         : {libelle_district(districts)}",
        f"Role demandeur   : {role}",
        f"Menages controles: {len(menages)}",
        f"Menages en erreur: {len(err)}",
        "",
        "Contenu de cette archive",
        "------------------------",
        "6_TABLEAU_DE_BORD/   statistiques et controles complementaires",
    ]
    if complet:
        lignes.append("4_ERREURS_EXPERTS_SURVEY/  a transmettre aux Experts "
                      "Survey Solutions (lots de 199 menages)")
    lignes += [
        "5_ERREURS_SUPTECH_CE/  un classeur par chef d'equipe, range par "
        "SupTech puis commune",
        "",
        "Ces fichiers reprennent les controles et la presentation du do-file",
        "Stata << do_listing_erreur_VAD_RSU_V2.do >> : memes erreurs, memes",
        "titres de colonnes, memes messages en malgache.",
        "",
        "Une cellule VIDE = pas d'erreur. Une cellule remplie porte la",
        "consigne a appliquer.",
        "",
        "ATTENTION : ces fichiers contiennent des donnees NOMINATIVES (nom du",
        "chef de menage, nom des membres). A ne pas diffuser hors de l'equipe.",
    ]
    if not complet:
        lignes += ["",
                   "Role Superviseur Technique : l'archive ne contient pas les",
                   "fichiers destines aux Experts Survey Solutions."]
    return "\n".join(lignes) + "\n"
