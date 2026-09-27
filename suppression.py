# -*- coding: utf-8 -*-
"""
suppression.py — Suppression des données d'UN district (réservée au rôle Admin).

Pendant destructif de la transcription (`maj_db.py` / `vad_db.py`), qui n'efface
JAMAIS rien : quand un district a été transcrit par erreur, avec un mauvais
export ou sur un questionnaire périmé, il faut pouvoir repartir de zéro SUR CE
DISTRICT sans toucher aux dix-neuf autres.

Le choix se fait comme pour l'ouverture d'un tableau de bord (cf. `page_selection`
de serveur_app) : **un district** (cascade Province → Région → District) et
**l'opération** — Dénombrement, Visite à domicile, ou LES DEUX (cases à cocher,
choix multiple).

Ce qui est supprimé, par opération
----------------------------------
    Dénombrement (`den`)          Visite à domicile (`vad`)
    ─────────────────────         ──────────────────────────
    den_menage                    vad_menage       (le PARENT : district = CQ7)
    segment_roster                vad_membre
    interview__diagnostics        vad_diagnostics
                                  vad_ce
    prechargement_* (registre du préchargement, par code_district)

Le district n'est porté que par la table PARENT (`den_menage."district"`,
`vad_menage."CQ7"`) : les tables filles s'y rattachent par `interview__key`. On
calcule donc d'abord les clés du district (`cles_cibles`), on supprime les filles,
**puis** le parent.

Deux sources pour le périmètre : la base ET le dossier téléversé
---------------------------------------------------------------
Un export se téléverse et se transcrit FICHIER PAR FICHIER : la base peut garder
des lignes que la table parente ne désigne plus (des `interview__diagnostics`
sans ménage, ou des lignes de ménage dont `district` est resté vide). Les compter
« par sous-requête sur le parent » les laisserait en place — ce serait un district
supprimé à moitié, et c'est exactement ce qu'il a fallu rattraper à la main pour
VAVATENINA (`deploy/supprimer_vavatenina.py`, journal 2026-09-21). `cles_cibles`
complète donc les clés de la base par celles du `.dta` MÉNAGE du dossier, en
écartant celles que la base attribue explicitement à un AUTRE district (même
règle qu'à l'ingestion, cf. `db_source.cles_hors_district`).

Les comparatifs RGPH ↔ RSU sont VIDÉS, pas supprimés
----------------------------------------------------
`comp_taille_menage` et `comp_pyramide` (cf. `comparaison_rgph_rsu.py`) mettent
côte à côte DEUX sources : le RGPH-3 2018 et le RSU. Elles existent pour les 120
districts, même sans une seule interview RSU — leurs colonnes `*_rgph` sont le
recensement, pas notre collecte. En supprimer les lignes effacerait donc la
référence RGPH du district. On remet seulement à NULL le **volet RSU** :

    comp_taille_menage  <- segment_roster.taille_menD  => opération DÉNOMBREMENT
    comp_pyramide       <- vad_membre M3/M4            => opération VAD

(Attention à la maille de `comp_taille_menage` : la ligne du district porte le
code dans `code`, `code_district` étant NULL ; seules les lignes de COMMUNE ont
`code_district` rempli. D'où la clause en deux branches.)

Ce qui n'est PAS touché (volontairement)
----------------------------------------
* `_schema` / `_value_labels` : la STRUCTURE des tables (noms de colonnes, value
  labels), pas des données de district. Les effacer casserait la lecture des
  autres districts.
* le référentiel `zones` (province/région/district/commune/fokontany), les
  comptes, les équipes, les journaux, les consignes, le RGPH.
(En revanche les `.dta` TÉLÉVERSÉS partent AVEC les données : voir plus bas.)

Le dossier des `.dta` téléversés part aussi
-------------------------------------------
Effacer les lignes sans effacer les fichiers laisserait le district à moitié
supprimé : l'Expert survey retrouverait son export sur la page de transcription
et un clic le réinjecterait. Chaque opération a donc son dossier, supprimé en
même temps que ses tables :

    Dénombrement      config.UPLOAD_DIR/<code_district>/
    Visite à domicile config.UPLOAD_DIR/VAD/<code_district>/

`_dossier_sur` refuse tout chemin qui ne serait pas EXACTEMENT ce dossier-là
(chemin réel, sous UPLOAD_DIR, nom = le code district) : une erreur de calcul ne
doit pas pouvoir viser un autre dossier du serveur.

Toute suppression est CONSIGNÉE dans `journal_transcription` (via
`journal.consigner`), donc visible dans les journaux d'ingestion de /admin :
« Suppression des données » côté dénombrement, « Suppression des données VAD »
côté visite à domicile (c'est le suffixe VAD qui sépare les deux journaux).
"""
import html
import json
import os
import shutil
import unicodedata

import config
import db_source
import journal
import zones

ESC = html.escape

# Les deux opérations, et les tables qui portent leurs données.
#   parent  : (table, colonne_district, libellé) -> seule table qui connaît le district
#   filles  : [(table, libellé)]  -> rattachées au parent par interview__key
#   remises : comparatifs RGPH↔RSU dont on VIDE le volet RSU (jamais la ligne)
OPERATIONS = {
    "den": {
        "libelle": "Dénombrement",
        "detail": "Segments dénombrés, bâtiments/ménages listés, diagnostics d’interview",
        "parent": ("den_menage", "district", "Segments dénombrés (1 ligne = 1 segment)"),
        "filles": [
            ("segment_roster", "Bâtiments et ménages listés dans les segments"),
            ("interview__diagnostics", "Diagnostics d’interview (agent, durée, rejets)"),
        ],
        "remises": [{
            "table": "comp_taille_menage",
            "libelle": "Comparaison RGPH ↔ RSU : taille des ménages",
            "set": '"menages_rsu" = NULL, "taille_rsu" = NULL, "ecart" = NULL',
            # Ligne du district : le code est dans `code` (code_district NULL) ;
            # lignes de commune : rattachées par `code_district`.
            "where": '(("niveau" = \'district\' AND "code" = {ph})'
                     ' OR ("niveau" = \'commune\' AND "code_district" = {ph}))',
            "params": 2,
            "rempli": '"menages_rsu" IS NOT NULL',
        }],
        # Tables qui portent ELLES-MÊMES le code district : supprimées par
        # `WHERE code_district = ?`. Le REGISTRE du préchargement (VAD) part avec
        # le dénombrement dont il est issu (décision 2026-09-22, phase de test) :
        # sans lui, une nouvelle transcription du district verrait ses ménages
        # exclus comme « déjà préchargés ». Les lots en dernier (tables parentes).
        "par_district": [
            ("prechargement_ensemble", "Préchargement : ménages déjà préchargés (Ensemble)"),
            ("prechargement_nouveau", "Préchargement : feuille nouveau"),
            ("prechargement_efokontany", "Préchargement : feuille e_fokontany"),
            ("prechargement_lot", "Préchargement : lots (sorties) enregistrés"),
        ],
        # Dossier des .dta téléversés : UPLOAD_DIR/<code>/ (cf. _transcription_post).
        "dossier": (),
        "evenement": "Suppression des données",
    },
    "vad": {
        "libelle": "Visite à domicile",
        "detail": "Ménages visités, membres du ménage, diagnostics, rattachement au chef d’équipe",
        # La géographie OBSERVÉE de la VAD est CQ7 (la colonne `district` de ce
        # questionnaire est une valeur PRÉCHARGÉE, souvent « ##N/A## ») — même
        # clé que le périmètre du tableau de bord (vad_db._clause_perimetre).
        "parent": ("vad_menage", "CQ7", "Ménages visités (1 ligne = 1 ménage)"),
        "filles": [
            ("vad_membre", "Membres des ménages visités"),
            ("vad_diagnostics", "Diagnostics d’interview (agent, durée, rejets)"),
            ("vad_ce", "Rattachement interview → chef d’équipe"),
        ],
        "remises": [{
            "table": "comp_pyramide",
            "libelle": "Comparaison RGPH ↔ RSU : pyramide des âges",
            "set": '"effectif_rsu" = NULL, "pct_rsu" = NULL',
            "where": '"code_district" = {ph}',
            "params": 1,
            "rempli": '"effectif_rsu" IS NOT NULL',
        }],
        # Dossier des .dta téléversés : UPLOAD_DIR/VAD/<code>/.
        "dossier": ("VAD",),
        "evenement": "Suppression des données VAD",
    },
}

ORDRE = ("den", "vad")          # ordre d'affichage / de traitement


def libelle(op) -> str:
    return OPERATIONS[op]["libelle"] if op in OPERATIONS else str(op)


def confirmation_ok(saisi, nom_district) -> bool:
    """La saisie de confirmation correspond-elle au nom du district ?

    Comparaison tolérante (accents, casse, espaces) : on demande un geste
    DÉLIBÉRÉ, pas une dictée — « miandrivazo » confirme MIANDRIVAZO, « le district »
    ne confirme rien."""
    def cle(v):
        v = unicodedata.normalize("NFD", (v or "").strip())
        v = "".join(c for c in v if unicodedata.category(c) != "Mn")
        return " ".join(v.upper().split())
    attendu = cle(nom_district)
    return bool(attendu) and cle(saisi) == attendu


def normaliser(ops) -> list:
    """Filtre et ordonne les opérations demandées. [] si rien de valide."""
    demandees = set(ops or ())
    return [o for o in ORDRE if o in demandees]


# ---------------------------------------------------------------------------
# Le dossier des .dta téléversés (une opération = un dossier par district)
# ---------------------------------------------------------------------------
def chemin_dossier(op, code_district) -> str:
    """UPLOAD_DIR[/VAD]/<code_district> — le dossier où l'Expert survey a téléversé
    ses .dta pour cette opération (cf. _transcription_post / _transcription_vad_post)."""
    return os.path.join(config.UPLOAD_DIR,
                        *OPERATIONS[op]["dossier"], str(int(code_district)))


def _dossier_sur(op, code_district):
    """Le chemin à supprimer, ou None s'il n'est pas EXACTEMENT le dossier attendu.

    Garde-fou d'une suppression récursive : on recalcule les chemins réels
    (`realpath`, donc liens symboliques résolus) et on exige que le dossier soit
    un descendant direct de UPLOAD_DIR[/VAD] et porte le code du district. Sans
    ce contrôle, un UPLOAD_DIR mal configuré ou un code inattendu pourrait viser
    n'importe quel dossier du serveur."""
    racine = os.path.realpath(os.path.join(config.UPLOAD_DIR,
                                           *OPERATIONS[op]["dossier"]))
    cible = os.path.realpath(chemin_dossier(op, code_district))
    if os.path.dirname(cible) != racine:
        return None
    if os.path.basename(cible) != str(int(code_district)):
        return None
    return cible if os.path.isdir(cible) else None


def etat_dossier(op, code_district) -> dict:
    """{'chemin', 'existe', 'fichiers', 'octets'} — ce que l'Admin verra avant de
    confirmer. `fichiers` compte TOUT le contenu, sous-dossiers compris (l'export
    Survey Solutions apporte un sous-dossier `Questionnaire`)."""
    chemin = chemin_dossier(op, code_district)
    cible = _dossier_sur(op, code_district)
    out = {"chemin": chemin, "existe": cible is not None,
           "fichiers": 0, "octets": 0}
    if cible is None:
        return out
    for racine, _dirs, fichiers in os.walk(cible):
        for f in fichiers:
            out["fichiers"] += 1
            try:
                out["octets"] += os.path.getsize(os.path.join(racine, f))
            except OSError:
                pass
    return out


def taille_lisible(octets) -> str:
    """« 12,4 Mo » — le volume que l'Admin va libérer, en unités parlantes."""
    o = float(octets or 0)
    for unite in ("o", "Ko", "Mo", "Go"):
        if o < 1024 or unite == "Go":
            return (f"{o:.0f} {unite}" if unite == "o"
                    else f"{o:.1f} {unite}".replace(".", ","))
        o /= 1024
    return f"{o:.1f} Go"


def supprimer_dossier(op, code_district) -> dict:
    """Efface le dossier des .dta de cette opération. {'chemin','supprime','erreur'}.

    Une erreur de FICHIER n'annule pas la suppression des DONNÉES (déjà commitée) :
    elle est renvoyée pour être affichée et journalisée, à traiter à la main."""
    chemin = chemin_dossier(op, code_district)
    cible = _dossier_sur(op, code_district)
    if cible is None:
        return {"chemin": chemin, "supprime": False, "erreur": None}
    try:
        shutil.rmtree(cible)
        return {"chemin": chemin, "supprime": True, "erreur": None}
    except OSError as e:
        return {"chemin": chemin, "supprime": False, "erreur": str(e)}


# ---------------------------------------------------------------------------
# Lecture : ce qu'il y a à supprimer
# ---------------------------------------------------------------------------
def _existe(conn, table) -> bool:
    """La table est-elle présente ? (une base neuve n'a pas encore les tables VAD)"""
    try:
        conn.cursor().execute(f'SELECT 1 FROM "{table}" LIMIT 1')
        return True
    except Exception:
        return False


def _un(conn, sql, params=()) -> int:
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return int((cur.fetchone() or [0])[0] or 0)
    except Exception:
        return 0


LOT = 400       # taille des paquets d'interview__key (limite de paramètres SQL)


def _lots(cles):
    cles = list(cles)
    for i in range(0, len(cles), LOT):
        yield cles[i:i + LOT]


def _compter_cles(conn, table, cles, extra="", params_extra=()) -> int:
    """COUNT des lignes de `table` portant l'une de ces interview__key, par paquets."""
    if not cles or not _existe(conn, table):
        return 0
    ph = db_source._placeholder(conn)
    n = 0
    for lot in _lots(cles):
        trous = ",".join([ph] * len(lot))
        n += _un(conn, f'SELECT COUNT(*) FROM "{table}" '
                       f'WHERE "interview__key" IN ({trous}){extra}',
                 tuple(params_extra) + tuple(lot))
    return n


def _supprimer_cles(conn, table, cles, extra="") -> int:
    """DELETE des lignes portant l'une de ces interview__key, par paquets."""
    if not cles or not _existe(conn, table):
        return 0
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    n = 0
    for lot in _lots(cles):
        trous = ",".join([ph] * len(lot))
        cur.execute(f'DELETE FROM "{table}" '
                    f'WHERE "interview__key" IN ({trous}){extra}', tuple(lot))
        n += max(cur.rowcount, 0)
    return n


def cles_dossier(op, code_district) -> set:
    """interview__key du fichier MÉNAGE téléversé pour cette opération.

    Un export peut être téléversé et transcrit FICHIER PAR FICHIER : la base
    garde alors des `interview__diagnostics` (ou des lignes de ménage sans
    district renseigné) que la table parente ne désigne plus. C'est ce qui est
    arrivé à VAVATENINA (cf. `deploy/supprimer_vavatenina.py`, journal 2026-09-21)
    et c'est mesurable aujourd'hui : 22 lignes `den_menage` à `district` NULL
    appartiennent à VOHIBATO, 12 à LALANGINA d'après leurs dossiers. Le dossier
    est donc la SECONDE source de vérité sur le périmètre du district."""
    dossier = _dossier_sur(op, code_district)
    if dossier is None:
        return set()
    try:
        if op == "vad":
            import vad_db
            chemin = vad_db.trouver_fichiers(dossier)["menage"]
        else:
            chemin = os.path.join(dossier, db_source.FICHIERS["den"][0])
            chemin = chemin if os.path.isfile(chemin) else None
        if not chemin:
            return set()
        from lire_dta import lire_dta
        d = lire_dta(chemin)
        if "interview__key" not in d.varnames:
            return set()
        return {v for v in d.col("interview__key") if v}
    except Exception:
        return set()            # dossier illisible : on s'en tient à la base


def cles_cibles(conn, code_district, op) -> dict:
    """Les interview__key à effacer. {'base': [...], 'orphelines': [...]}

    * `base`       : celles que la table PARENTE rattache à ce district ;
    * `orphelines` : celles que seul le DOSSIER téléversé connaît, et dont la
      table parente ne dit PAS qu'elles appartiennent à un autre district (ligne
      absente, ou `district` NULL). Une interview saisie hors zone, rattachée en
      base à un autre district, est ainsi laissée tranquille — c'est la règle que
      `db_source.cles_hors_district` applique déjà à l'ingestion."""
    ph = db_source._placeholder(conn)
    code = int(code_district)
    p_table, p_col, _lib = OPERATIONS[op]["parent"]
    base = set()
    if _existe(conn, p_table):
        cur = conn.cursor()
        cur.execute(f'SELECT "interview__key" FROM "{p_table}" '
                    f'WHERE "{p_col}" = {ph}', (code,))
        base = {r[0] for r in cur.fetchall() if r[0]}
    candidates = cles_dossier(op, code_district) - base
    if candidates and _existe(conn, p_table):
        # On écarte celles que la base attribue explicitement à un AUTRE district.
        ailleurs = set()
        cur = conn.cursor()
        for lot in _lots(sorted(candidates)):
            trous = ",".join([ph] * len(lot))
            cur.execute(f'SELECT "interview__key" FROM "{p_table}" '
                        f'WHERE "interview__key" IN ({trous}) '
                        f'AND "{p_col}" IS NOT NULL AND "{p_col}" <> {ph}',
                        tuple(lot) + (code,))
            ailleurs |= {r[0] for r in cur.fetchall()}
        candidates -= ailleurs
    return {"base": sorted(base), "orphelines": sorted(candidates)}


def details(conn, code_district, op, cles=None) -> list:
    """[{'table','libelle','lignes'}] : le décompte table par table, dans l'ORDRE
    de suppression (filles, puis parent). `cles` évite de recalculer `cles_cibles`."""
    ph = db_source._placeholder(conn)
    code = int(code_district)
    p_table, p_col, p_lib = OPERATIONS[op]["parent"]
    if not _existe(conn, p_table):
        return []
    cles = cles or cles_cibles(conn, code_district, op)
    toutes = cles["base"] + cles["orphelines"]
    out = [{"table": table, "libelle": lib,
            "lignes": _compter_cles(conn, table, toutes)}
           for table, lib in OPERATIONS[op]["filles"] if _existe(conn, table)]
    # Parent : les lignes du district, PLUS celles que seul le dossier rattache
    # ici et dont le district est resté vide.
    n = _un(conn, f'SELECT COUNT(*) FROM "{p_table}" WHERE "{p_col}" = {ph}',
            (code,))
    n += _compter_cles(conn, p_table, cles["orphelines"],
                       extra=f' AND "{p_col}" IS NULL')
    out.append({"table": p_table, "libelle": p_lib, "lignes": n})
    for table, lib in OPERATIONS[op].get("par_district", ()):
        if _existe(conn, table):
            out.append({"table": table, "libelle": lib,
                        "lignes": _un(conn, f'SELECT COUNT(*) FROM "{table}" '
                                            f'WHERE "code_district" = {ph}', (code,))})
    return out


def _clause_remise(conn, r):
    """(clause WHERE, params) d'une remise à vide, pour CE district."""
    ph = db_source._placeholder(conn)
    return r["where"].replace("{ph}", ph)


def details_remises(conn, code_district, op) -> list:
    """[{'table','libelle','lignes'}] : les lignes de comparatif RGPH ↔ RSU dont le
    volet RSU sera remis à vide (celles qui portent encore une valeur RSU)."""
    code = int(code_district)
    out = []
    for r in OPERATIONS[op].get("remises", ()):
        if not _existe(conn, r["table"]):
            continue
        where = _clause_remise(conn, r)
        out.append({
            "table": r["table"], "libelle": r["libelle"],
            "lignes": _un(conn, f'SELECT COUNT(*) FROM "{r["table"]}" '
                                f'WHERE {where} AND {r["rempli"]}',
                          (code,) * r["params"])})
    return out


def compter(conn, code_district, ops=ORDRE) -> dict:
    """{op: {'total': n, 'tables': [...], 'dossier': {...}}} pour les opérations
    demandées — les lignes en base ET le dossier de .dta qui partira avec."""
    out = {}
    for op in normaliser(ops):
        cles = cles_cibles(conn, code_district, op)
        tables = details(conn, code_district, op, cles)
        out[op] = {"total": sum(t["lignes"] for t in tables), "tables": tables,
                   "orphelines": len(cles["orphelines"]),
                   "remises": details_remises(conn, code_district, op),
                   "dossier": etat_dossier(op, code_district)}
    return out


def _vide() -> dict:
    return {"den": 0, "vad": 0, "f_den": 0, "f_vad": 0}


def inventaire(conn) -> list:
    """[{'code','nom','den','vad','f_den','f_vad'}] — les districts qui ont quelque
    chose à supprimer : des lignes en base (`den`/`vad`, tables parentes) et/ou des
    fichiers téléversés (`f_den`/`f_vad`). Un district téléversé mais pas encore
    transcrit n'a que des fichiers : il doit apparaître quand même."""
    noms = {int(d["code"]): d["nom"] for d in zones.tous_districts(conn)}
    lignes = {}
    for op, (table, col) in (("den", ("den_menage", "district")),
                             ("vad", ("vad_menage", "CQ7"))):
        if not _existe(conn, table):
            continue
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT "{col}", COUNT(*) FROM "{table}" '
                        f'WHERE "{col}" IS NOT NULL GROUP BY "{col}"')
            for code, n in cur.fetchall():
                try:
                    code = int(code)
                except (TypeError, ValueError):
                    continue        # valeur non numérique (préchargement « ##N/A## »)
                lignes.setdefault(code, _vide())[op] = int(n or 0)
        except Exception:
            continue
    # Les dossiers de .dta : on liste le contenu de UPLOAD_DIR[/VAD] plutôt que de
    # tester les 120 districts un par un.
    for op in ORDRE:
        racine = os.path.join(config.UPLOAD_DIR, *OPERATIONS[op]["dossier"])
        try:
            contenu = os.listdir(racine)
        except OSError:
            continue
        for nom in contenu:
            if not nom.isdigit():
                continue            # « VAD » (dossier de l'autre phase), divers
            etat = etat_dossier(op, int(nom))
            if etat["existe"]:
                lignes.setdefault(int(nom), _vide())[f"f_{op}"] = etat["fichiers"]
    return [dict(v, code=c, nom=noms.get(c, "—"))
            for c, v in sorted(lignes.items(), key=lambda kv: noms.get(kv[0], ""))]


# ---------------------------------------------------------------------------
# Écriture : la suppression elle-même
# ---------------------------------------------------------------------------
def supprimer(conn, code_district, ops) -> dict:
    """Supprime les données des opérations demandées pour CE district.

    {op: {'total': n, 'tables': [{'table','libelle','lignes'}], 'remises': [...],
    'dossier': {...}}} — `lignes` est le nombre de lignes RÉELLEMENT supprimées.

    Les clés à effacer sont calculées AVANT toute écriture (`cles_cibles` lit la
    table parente, qui va disparaître), les filles partent AVANT le parent, et un
    seul commit clôt l'ensemble : une erreur en cours de route ne laisse pas une
    opération à moitié faite."""
    ph = db_source._placeholder(conn)
    code = int(code_district)
    cur = conn.cursor()
    out = {}
    try:
        for op in normaliser(ops):
            p_table, p_col, p_lib = OPERATIONS[op]["parent"]
            faits = []
            if _existe(conn, p_table):
                cles = cles_cibles(conn, code_district, op)
                toutes = cles["base"] + cles["orphelines"]
                for table, lib in OPERATIONS[op]["filles"]:
                    if not _existe(conn, table):
                        continue
                    faits.append({
                        "table": table, "libelle": lib,
                        "lignes": _supprimer_cles(conn, table, toutes)})
                cur.execute(f'DELETE FROM "{p_table}" WHERE "{p_col}" = {ph}', (code,))
                n = max(cur.rowcount, 0)
                n += _supprimer_cles(conn, p_table, cles["orphelines"],
                                     extra=f' AND "{p_col}" IS NULL')
                faits.append({"table": p_table, "libelle": p_lib, "lignes": n})
            for table, lib in OPERATIONS[op].get("par_district", ()):
                if not _existe(conn, table):
                    continue
                cur.execute(f'DELETE FROM "{table}" WHERE "code_district" = {ph}',
                            (code,))
                faits.append({"table": table, "libelle": lib,
                              "lignes": max(cur.rowcount, 0)})
            # Comparatifs RGPH ↔ RSU : on VIDE le volet RSU, la ligne (et donc
            # le RGPH) reste. Compté à part : ce n'est pas une suppression.
            vides = []
            for r in OPERATIONS[op].get("remises", ()):
                if not _existe(conn, r["table"]):
                    continue
                where = _clause_remise(conn, r)
                cur.execute(f'UPDATE "{r["table"]}" SET {r["set"]} '
                            f'WHERE {where} AND {r["rempli"]}',
                            (code,) * r["params"])
                vides.append({"table": r["table"], "libelle": r["libelle"],
                              "lignes": max(cur.rowcount, 0)})
            out[op] = {"total": sum(f["lignes"] for f in faits), "tables": faits,
                       "remises": vides}
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    # Les FICHIERS après le commit : une erreur de disque ne doit pas faire
    # perdre une suppression de données réussie (elle est signalée, à la place).
    for op in out:
        out[op]["dossier"] = supprimer_dossier(op, code_district)
    return out


def consigner(conn, utilisateur, code_district, resultats) -> None:
    """Trace la suppression dans les journaux d'ingestion (/admin), une ligne PAR
    OPÉRATION — c'est le suffixe « VAD » de l'événement qui range la ligne dans le
    bon journal (cf. journal.phase_evenement)."""
    login = (utilisateur or {}).get("login") or ""
    nom = (utilisateur or {}).get("nom_prenom") or login
    for op, res in resultats.items():
        detail = " · ".join(f'{t["table"]} : {t["lignes"]}' for t in res["tables"]) \
                 or "aucune ligne"
        vides = " · ".join(f'{r["table"]} vidé : {r["lignes"]}'
                           for r in res.get("remises", ()) if r["lignes"])
        d = res.get("dossier") or {}
        if d.get("erreur"):
            fichiers = f'dossier {d["chemin"]} NON supprimé : {d["erreur"]}'
        elif d.get("supprime"):
            fichiers = f'dossier .dta supprimé ({d["chemin"]})'
        else:
            fichiers = "aucun dossier .dta à supprimer"
        journal.consigner(
            conn, login, nom, code_district, OPERATIONS[op]["evenement"],
            "Réussi", detail=f'{res["total"]} ligne(s) supprimée(s) — {detail}'
                             + (f' — {vides}' if vides else '')
                             + f' — {fichiers}')


# ---------------------------------------------------------------------------
# Rendu HTML
# ---------------------------------------------------------------------------
def _cascade(conn, code_pre=None) -> str:
    """Cascade Province → Région → District (seul « district » est soumis).
    `code_pre` pré-sélectionne un district (retour d'une confirmation annulée)."""
    geo = zones.arbre_geo(conn)
    prov_opts = "".join(f'<option value="{p["c"]}">{ESC(str(p["n"]))}</option>'
                        for p in geo["provinces"])
    return (
        '<div class="grid-form">'
        '<div><label for="s-prov">Province</label>'
        f'<select id="s-prov"><option value="">— province —</option>{prov_opts}</select></div>'
        '<div><label for="s-reg">Région</label>'
        '<select id="s-reg" disabled><option value="">— région —</option></select></div>'
        '<div><label for="s-dist">District</label>'
        '<select id="s-dist" name="district" required disabled>'
        '<option value="">— district —</option></select></div>'
        '</div>'
        '<script>(function(){'
        f'var GEO={json.dumps(geo, ensure_ascii=False)};'
        f'var PRE={json.dumps(int(code_pre)) if code_pre else "null"};'
        'var P=document.getElementById("s-prov"),R=document.getElementById("s-reg"),'
        'D=document.getElementById("s-dist");'
        'function opt(v,t){var o=document.createElement("option");o.value=v;o.textContent=t;return o;}'
        'function fill(s,l,ph){s.innerHTML="";s.appendChild(opt("",ph));'
        '(l||[]).forEach(function(x){s.appendChild(opt(x.c,x.n));});s.disabled=!(l&&l.length);}'
        'P.addEventListener("change",function(){fill(R,GEO.regions[P.value],"— région —");'
        'fill(D,[],"— district —");});'
        'R.addEventListener("change",function(){fill(D,GEO.districts[R.value],"— district —");});'
        'if(PRE!=null){var r2p={},d2r={};'
        'Object.keys(GEO.regions).forEach(function(p){GEO.regions[p].forEach(function(x){r2p[x.c]=p;});});'
        'Object.keys(GEO.districts).forEach(function(r){GEO.districts[r].forEach(function(x){d2r[x.c]=r;});});'
        'var reg=d2r[PRE];if(reg!=null){var prov=r2p[reg];P.value=prov;'
        'fill(R,GEO.regions[prov],"— région —");R.value=reg;'
        'fill(D,GEO.districts[reg],"— district —");D.value=PRE;}}'
        '})();</script>')


def _cases_operations(coches=()) -> str:
    """Les cases à cocher « quoi supprimer » — CHOIX MULTIPLE (den, vad, ou les deux)."""
    lignes = "".join(
        '<label style="display:flex;gap:.55rem;align-items:flex-start;'
        'background:#fff;border:1px solid #e2e8f0;border-radius:.625rem;'
        'padding:.625rem .875rem;margin-bottom:.5rem;cursor:pointer;font-size:.8125rem;'
        'color:#1e293b">'
        f'<input type="checkbox" name="operation" value="{op}" style="margin-top:.2rem"'
        f'{" checked" if op in coches else ""}>'
        f'<span><b>{ESC(OPERATIONS[op]["libelle"])}</b><br>'
        f'<small>{ESC(OPERATIONS[op]["detail"])}</small></span></label>'
        for op in ORDRE)
    return ('<fieldset style="border:none;padding:0;margin:0">'
            '<label>Données à supprimer — plusieurs choix possibles</label>'
            + lignes
            + '<small>Pour chaque opération cochée : les tables de la base '
              '<b>et</b> le dossier des <code>.dta</code> téléversés du district.'
              '</small></fieldset>')


_AVERTISSEMENT = (
    '<div class="err"><b>⚠ Opération irréversible.</b> Les lignes effacées ne sont '
    'pas récupérables depuis l’application, et le <b>dossier des fichiers '
    '<code>.dta</code> téléversés</b> du district est supprimé avec elles : seule '
    'une RESTAURATION DE SAUVEGARDE, ou un nouveau téléversement de l’export '
    'Survey&nbsp;Solutions, ramènerait ces données.</div>')


def _table_inventaire(inv) -> str:
    lignes = "".join(
        f'<tr><td>{ESC(x["nom"])} ({x["code"]})</td>'
        f'<td>{x["den"] or "—"}</td><td>{x["f_den"] or "—"}</td>'
        f'<td>{x["vad"] or "—"}</td><td>{x["f_vad"] or "—"}</td></tr>' for x in inv) \
        or ('<tr><td colspan="5"><small>Aucune donnée ni fichier en base.'
            '</small></td></tr>')
    return ('<table><tr><th>District</th><th>Segments dénombrés</th>'
            '<th>Fichiers dén.</th><th>Ménages visités (VAD)</th>'
            '<th>Fichiers VAD</th></tr>' + lignes + '</table>')


def page_suppression(conn, message=None, erreur=None, code_pre=None,
                     coches=()) -> str:
    """Étape 1 : choisir le district et ce qu'on supprime. Ne supprime rien —
    le POST mène à la page de CONFIRMATION, qui montre les décomptes exacts."""
    import admin                     # import local : admin ne dépend pas de nous
    msg = f'<div class="msg">{message}</div>' if message else ''
    err = f'<div class="err">{ESC(erreur)}</div>' if erreur else ''
    return (admin._entete("suppr")
            + '<h1>Suppression des données d’un district</h1>'
            + '<small>Espace réservé au rôle Admin.</small>'
            + msg + err + _AVERTISSEMENT
            + '<form method="post" action="/admin/suppression">'
              '<input type="hidden" name="action" value="verifier">'
              '<h2>1. District concerné</h2>'
            + _cascade(conn, code_pre)
            + '<h2>2. Données à supprimer</h2>'
            + _cases_operations(coches)
            + '<p><button type="submit">Vérifier ce qui sera supprimé</button> '
              '<a href="/admin"><button type="button" class="sec">Annuler</button></a></p>'
              '</form>'
            + '<h2>Données actuellement en base</h2>'
            + '<div class="note">Lignes des tables PARENTES '
              '(<code>den_menage</code> pour le dénombrement, <code>vad_menage</code> '
              'pour la visite à domicile) et nombre de fichiers <code>.dta</code> '
              'téléversés, par district.</div>'
            + _table_inventaire(inventaire(conn))
            + admin._pied())


def page_confirmation(conn, code_district, ops, district_txt,
                      erreur=None) -> str:
    """Étape 2 : le décompte EXACT, table par table, et la confirmation par saisie
    du NOM du district — un clic de trop ne doit pas vider un district."""
    import admin
    ops = normaliser(ops)
    comptes = compter(conn, code_district, ops)
    total = sum(c["total"] for c in comptes.values())
    nom_district = (district_txt or "").split(" (")[0]
    blocs = ""
    for op in ops:
        c = comptes[op]
        lignes = "".join(
            f'<tr><td><code>{ESC(t["table"])}</code></td>'
            f'<td>{ESC(t["libelle"])}</td>'
            f'<td><b>{t["lignes"]}</b></td></tr>' for t in c["tables"]) \
            or '<tr><td colspan="3"><small>Table absente de la base.</small></td></tr>'
        remises = "".join(
            f'<tr><td><code>{ESC(r["table"])}</code></td>'
            f'<td>{ESC(r["libelle"])}</td><td><b>{r["lignes"]}</b></td></tr>'
            for r in c["remises"])
        if remises:
            remises = ('<table style="margin-top:.5rem"><tr><th>Table</th>'
                       '<th>Comparatif</th><th>Lignes dont le volet RSU '
                       'est vidé</th></tr>' + remises + '</table>'
                       '<div class="note">Ces lignes ne sont PAS supprimées : elles '
                       'portent aussi le RGPH-3 2018, qui reste. Seules les colonnes '
                       'RSU repassent à vide.</div>')
        if c.get("orphelines"):
            remises += (
                '<div class="note"><b>' + str(c["orphelines"]) + ' interview(s)</b> '
                'que seul le dossier téléversé rattache à ce district (ligne absente '
                'de la table parente, ou <code>district</code> resté vide) sont '
                'incluses dans les décomptes ci-dessus. Celles que la base attribue '
                'à un AUTRE district sont, elles, laissées intactes.</div>')
        if op == "den" and any(t["table"] == "prechargement_ensemble" and t["lignes"]
                               for t in c["tables"]):
            remises += (
                '<div class="note" style="background:#fff4d6;border-color:#f0d38a">'
                'Le <b>registre du préchargement</b> de ce district est effacé avec '
                'le dénombrement : tous ses ménages redeviendront « à précharger ». '
                'Hors phase de test, cela ferait renvoyer sur le terrain des ménages '
                'déjà préchargés.</div>')
        d = c["dossier"]
        if d["existe"]:
            fichiers = ('<div class="note">Dossier des <code>.dta</code> téléversés '
                        f'à supprimer : <code>{ESC(d["chemin"])}</code> — '
                        f'<b>{d["fichiers"]} fichier(s)</b>, '
                        f'{ESC(taille_lisible(d["octets"]))}.</div>')
        else:
            fichiers = ('<div class="note">Aucun dossier de <code>.dta</code> '
                        f'téléversé pour cette opération '
                        f'(<code>{ESC(d["chemin"])}</code>).</div>')
        blocs += (f'<h2>{ESC(OPERATIONS[op]["libelle"])} — '
                  f'{c["total"]} ligne(s)</h2>'
                  '<table><tr><th>Table</th><th>Contenu</th>'
                  '<th>Lignes supprimées</th></tr>' + lignes + '</table>'
                  + remises + fichiers)
    caches = "".join(f'<input type="hidden" name="operation" value="{op}">'
                     for op in ops)
    dossiers = sum(1 for op in ops if comptes[op]["dossier"]["existe"])
    vides = sum(r["lignes"] for op in ops for r in comptes[op]["remises"])
    if total == 0 and dossiers == 0 and vides == 0:
        corps = ('<div class="note">Il n’y a <b>aucune donnée ni aucun fichier</b> '
                 'à supprimer pour ce district et ces opérations.</div>'
                 '<p><a href="/admin/suppression">'
                 '<button type="button" class="sec">← Revenir au choix</button></a></p>')
    else:
        corps = (
            '<form method="post" action="/admin/suppression">'
            '<input type="hidden" name="action" value="confirmer">'
            f'<input type="hidden" name="district" value="{int(code_district)}">'
            + caches
            + '<div class="grid-form" style="grid-template-columns:1fr">'
              '<div><label for="s-conf">Pour confirmer, tapez le nom du district : '
              f'<b>{ESC(nom_district)}</b></label>'
              '<input id="s-conf" name="confirmation" autocomplete="off" required '
              f'placeholder="{ESC(nom_district)}" style="width:100%"></div></div>'
              '<p><button type="submit" class="danger">Supprimer définitivement</button> '
              '<a href="/admin/suppression">'
              '<button type="button" class="sec">Annuler</button></a></p>'
              '</form>')
    err = f'<div class="err">{ESC(erreur)}</div>' if erreur else ''
    return (admin._entete("suppr")
            + '<h1>Confirmer la suppression</h1>'
            + f'<small>District <b>{ESC(district_txt)}</b> — '
              f'{ESC(" et ".join(libelle(o) for o in ops))}.</small>'
            + err + _AVERTISSEMENT + blocs + corps + admin._pied())


def resume_html(district_txt, resultats) -> str:
    """Message de réussite (HTML) affiché en haut de la page après suppression :
    les lignes par table, et le sort du dossier de .dta."""
    parts = []
    for op, res in resultats.items():
        detail = ", ".join(f'{ESC(t["table"])} : {t["lignes"]}'
                           for t in res["tables"])
        vides = ", ".join(f'{ESC(r["table"])} : {r["lignes"]}'
                          for r in res.get("remises", ()) if r["lignes"])
        d = res.get("dossier") or {}
        if d.get("supprime"):
            fichiers = f' · dossier <code>{ESC(d["chemin"])}</code> supprimé'
        elif d.get("erreur"):
            fichiers = (f' · <b>dossier <code>{ESC(d["chemin"])}</code> NON '
                        f'supprimé</b> : {ESC(d["erreur"])} (à retirer à la main)')
        else:
            fichiers = ' · aucun dossier <code>.dta</code> à supprimer'
        parts.append(f'<b>{ESC(OPERATIONS[op]["libelle"])}</b> — '
                     f'{res["total"]} ligne(s) supprimée(s)'
                     + (f' ({detail})' if detail else '')
                     + (f' · volet RSU vidé ({vides})' if vides else '')
                     + fichiers)
    return (f'Données supprimées pour le district <b>{ESC(district_txt)}</b>.<br>'
            + "<br>".join(parts))
