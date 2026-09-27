# -*- coding: utf-8 -*-
"""
vad_db.py — Données de la VISITE À DOMICILE (VAD) : schéma et transcription.

La VAD est la 2ᵉ phase du RSU : après le dénombrement, les agents retournent dans
les ménages pour l'entretien complet (composition du ménage, habitation, biens,
eau/assainissement…). L'export Survey Solutions du questionnaire **RSUe** donne
trois fichiers utiles, transcrits ici dans trois tables :

    rsuefkt_25_rN_pil.dta   -> "vad_menage"       1 ligne = 1 ménage interviewé
    RMen.dta                -> "vad_membre"       1 ligne = 1 membre du ménage
    interview__diagnostics.dta -> "vad_diagnostics"  1 ligne = 1 interview (agent,
                                                    statut, durée, erreurs)

⚠️ Le nom du fichier ménage porte la VERSION du questionnaire
(`rsuefkt_25_rN_pil`) : il changera à la prochaine version. `NOMS_MENAGE` liste
les noms acceptés, et `trouver_fichiers()` retient à défaut le .dta de plus haut
niveau qui porte les colonnes attendues — un export renommé reste transcriptible.

Ce que ces tables ont de particulier (par rapport au dénombrement) :

* **La géographie est portée par CQ6..CQ9** (région / district / commune /
  fokontany), codes numériques AVEC value labels, et ce sont des CLÉS ÉTRANGÈRES
  vers `zones` (cf. `db_source.FK_ZONES["vad_menage"]`). Les colonnes
  `region`/`district`/`commune`/`fokontany` du questionnaire sont, elles, des
  valeurs PRÉCHARGÉES au format texte, très souvent « ##N/A## » : inutilisables.
* **`interview_keyden`** relie le ménage VAD au ménage du DÉNOMBREMENT
  (`den_menage`/`segment_roster`) : c'est le pont entre les deux phases.
* **`##N/A##`** est le marqueur « non renseigné » de Survey Solutions. Il est
  traité comme vide PARTOUT (cf. `txt()`), sinon il remonterait comme une réponse.
* L'agent est `vad_diagnostics.responsible`, clé étrangère vers `agent(login_ae)`
  — la même table que le dénombrement, donc les noms d'agents déjà saisis par
  l'Expert Traitement servent aussi ici.

La transcription est un UPSERT (ajoute / met à jour / ne supprime rien), assuré
par `maj_db.maj_table` : c'est la même mécanique que le dénombrement.
"""
import os

import db_source
import maj_db

# Marqueur « non renseigné » de Survey Solutions.
NA = "##N/A##"

# Fichier ménage : le nom porte la version du questionnaire.
NOMS_MENAGE = ("rsuefkt_25_rN_pil.dta",)
NOM_MEMBRE = "RMen.dta"
NOM_DIAG = "interview__diagnostics.dta"

TABLE_MENAGE = "vad_menage"
TABLE_MEMBRE = "vad_membre"
TABLE_DIAG = "vad_diagnostics"

# Colonnes SANS lesquelles un fichier n'est pas le fichier ménage VAD attendu.
COLS_MENAGE_REQUISES = ("interview__key", "CQ7", "CQ9", "nbmembre")
COLS_MEMBRE_REQUISES = ("interview__key", "RMen__id", "M3", "M4")

# Clé d'unicité par table (identité d'une ligne, pour l'upsert).
CLES = {
    TABLE_MENAGE: ("interview__key",),
    TABLE_MEMBRE: ("interview__key", "RMen__id"),
    TABLE_DIAG: ("interview__key",),
}


class ErreurVAD(Exception):
    """Erreur métier (dossier/structure), à afficher telle quelle à l'utilisateur."""


# ---------------------------------------------------------------------------
# Lecture tolérante
# ---------------------------------------------------------------------------
def txt(v) -> str:
    """Valeur -> texte NETTOYÉ : « ##N/A## » et les blancs deviennent "".

    Sans ça, `##N/A##` (le marqueur de Survey Solutions) serait compté comme une
    réponse : 148 ménages « habitant la région ##N/A## », par exemple."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if (s == NA or not s) else s


def num(v):
    """Valeur -> nombre, ou None (chaîne vide, « ##N/A## », texte non numérique)."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    s = txt(v)
    if not s:
        return None
    try:
        return float(s) if ("." in s or "e" in s.lower()) else int(s)
    except ValueError:
        return None


def jour(v) -> str:
    """'AAAA-MM-JJThh:mm:ss' -> 'AAAAMMJJ' (le format de date du dénombrement,
    pour que les deux phases se comparent et se trient pareil). '' si invalide."""
    s = txt(v)
    if len(s) < 10:
        return ""
    j = s[0:4] + s[5:7] + s[8:10]
    return j if (len(j) == 8 and j.isdigit()) else ""


# ---------------------------------------------------------------------------
# Repérage des fichiers dans un dossier d'export
# ---------------------------------------------------------------------------
def _colonnes_dta(chemin) -> list:
    from lire_dta import lire_dta
    try:
        return list(lire_dta(chemin).varnames)
    except Exception:
        return []


def trouver_fichiers(dossier) -> dict:
    """{'menage': chemin|None, 'membre': chemin|None, 'diagnostics': chemin|None}.

    Le fichier ménage est cherché par son nom connu ; à défaut, on prend le
    premier .dta du dossier qui porte les colonnes attendues — ainsi un export
    d'une NOUVELLE version du questionnaire (nom de fichier différent) passe
    quand même, au lieu d'être refusé pour une question de nom."""
    out = {"menage": None, "membre": None, "diagnostics": None}
    if not os.path.isdir(dossier):
        return out
    fichiers = sorted(f for f in os.listdir(dossier) if f.lower().endswith(".dta"))
    par_nom = {f.lower(): os.path.join(dossier, f) for f in fichiers}
    for n in NOMS_MENAGE:
        if n.lower() in par_nom:
            out["menage"] = par_nom[n.lower()]
            break
    if NOM_MEMBRE.lower() in par_nom:
        out["membre"] = par_nom[NOM_MEMBRE.lower()]
    if NOM_DIAG.lower() in par_nom:
        out["diagnostics"] = par_nom[NOM_DIAG.lower()]
    if out["menage"] is None:            # repli : reconnaissance par colonnes
        for f in fichiers:
            chemin = os.path.join(dossier, f)
            if chemin in (out["membre"], out["diagnostics"]):
                continue
            cols = _colonnes_dta(chemin)
            if cols and all(c in cols for c in COLS_MENAGE_REQUISES):
                out["menage"] = chemin
                break
    if out["membre"] is None:
        for f in fichiers:
            chemin = os.path.join(dossier, f)
            if chemin in (out["menage"], out["diagnostics"]):
                continue
            cols = _colonnes_dta(chemin)
            if cols and all(c in cols for c in COLS_MEMBRE_REQUISES):
                out["membre"] = chemin
                break
    return out


def apercu(dossier) -> dict:
    """Ce que contient un dossier d'export, AVANT d'écrire quoi que ce soit :
    {'menage': {...}, 'membre': {...}, 'diagnostics': {...}, 'districts': {...}}.
    Sert à la page de téléversement (montrer ce qui sera transcrit)."""
    from lire_dta import lire_dta
    from collections import Counter
    f = trouver_fichiers(dossier)
    out = {"fichiers": {k: (os.path.basename(v) if v else None)
                        for k, v in f.items()},
           "lignes": {}, "districts": {}, "dates": [], "agents": 0}
    if f["menage"]:
        d = lire_dta(f["menage"])
        out["lignes"]["menage"] = d.nobs
        codes = d.col("CQ7") if "CQ7" in d.varnames else []
        libs = d.col_decoded("CQ7") if "CQ7" in d.varnames else []
        c = Counter((int(k), str(l)) for k, l in zip(codes, libs)
                    if isinstance(k, (int, float)))
        out["districts"] = {f"{lib} ({code})": n
                            for (code, lib), n in c.most_common()}
        if "CQ3" in d.varnames:
            out["dates"] = sorted({jour(v) for v in d.col("CQ3") if jour(v)})
    if f["membre"]:
        out["lignes"]["membre"] = lire_dta(f["membre"]).nobs
    if f["diagnostics"]:
        d = lire_dta(f["diagnostics"])
        out["lignes"]["diagnostics"] = d.nobs
        out["agents"] = len({txt(v) for v in d.col("responsible") if txt(v)})
    return out


def districts_du_dossier(dossier) -> set:
    """Codes district (int) présents dans le fichier ménage — pour vérifier qu'un
    dossier concerne bien le district attendu."""
    from lire_dta import lire_dta
    f = trouver_fichiers(dossier)
    if not f["menage"]:
        return set()
    d = lire_dta(f["menage"])
    if "CQ7" not in d.varnames:
        return set()
    return {int(v) for v in d.col("CQ7") if isinstance(v, (int, float))}


def cles_hors_district(dossier, code_district) -> set:
    """`interview__key` des ménages VAD qui ne sont PAS du district attendu.
    Même logique que `db_source.cles_hors_district` pour le dénombrement : on
    filtre et on avertit, plutôt que de refuser tout le dossier."""
    from lire_dta import lire_dta
    f = trouver_fichiers(dossier)
    if not f["menage"]:
        return set()
    d = lire_dta(f["menage"])
    if "CQ7" not in d.varnames or "interview__key" not in d.varnames:
        return set()
    cd = int(code_district)
    cles, dist = d.col("interview__key"), d.col("CQ7")
    return {cles[i] for i in range(d.nobs)
            if not (isinstance(dist[i], (int, float)) and int(dist[i]) == cd)}


def zones_disponibles(conn, districts=None, communes=None) -> list:
    """Communes et fokontany OÙ IL Y A DES DONNÉES VAD, dans un périmètre.

    Alimente la descente district → commune → fokontany de la carte. On part des
    données (et non du référentiel `zones` entier) pour ne proposer que des zones
    qui afficheront quelque chose ; les libellés, eux, viennent de `zones` — CQ8
    et CQ9 en sont des clés étrangères (cf. db_source.FK_ZONES).

    [{"code": 330701, "nom": "ALAKAMISY…", "n": 19,
      "fokontany": [{"code": 33070102, "nom": "ANALAMASINA", "n": 4}, …]}, …]"""
    if not tables_presentes(conn):
        return []
    where, params = _clause_perimetre(conn, districts, communes)
    cur = conn.cursor()
    cur.execute(f'SELECT "CQ8", "CQ9", COUNT(*) FROM "{TABLE_MENAGE}"'
                + (f" WHERE {where}" if where else "")
                + ' GROUP BY "CQ8", "CQ9"', params)
    brut = [(r[0], r[1], r[2] or 0) for r in cur.fetchall()
            if r[0] is not None and r[1] is not None]
    noms_c, noms_f = _libelles_zones(conn, {int(r[0]) for r in brut},
                                     {int(r[1]) for r in brut})
    par_commune = {}
    for cc, cf, n in brut:
        cc, cf = int(cc), int(cf)
        c = par_commune.setdefault(cc, {"code": cc, "nom": noms_c.get(cc, str(cc)),
                                        "n": 0, "fokontany": []})
        c["n"] += n
        c["fokontany"].append({"code": cf, "nom": noms_f.get(cf, str(cf)), "n": n})
    for c in par_commune.values():
        c["fokontany"].sort(key=lambda f: f["nom"])
    return sorted(par_commune.values(), key=lambda c: c["nom"])


def _libelles_zones(conn, codes_commune, codes_fokontany):
    """({code_commune: nom}, {code_fokontany: nom}) depuis le référentiel `zones`.

    Le nom de fokontany y est suffixé de son code (« AMBALAKELY_33070301 ») : on
    le retire, le code est déjà la valeur de l'option."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()

    def lire(table, colonne, codes):
        codes = sorted(codes)
        if not codes:
            return {}
        out = {}
        for i in range(0, len(codes), 400):          # SQLite borne le nombre de ?
            lot = codes[i:i + 400]
            cur.execute(f'SELECT {colonne}, nom FROM "{table}" '
                        f'WHERE {colonne} IN ({",".join([ph] * len(lot))})', lot)
            out.update({int(c): (n or "") for c, n in cur.fetchall()})
        return out

    noms_c = lire("commune", "code_commune", codes_commune)
    noms_f = lire("fokontany", "code_fokontany", codes_fokontany)
    for code, nom in list(noms_f.items()):
        suffixe = "_" + str(code)
        if nom.endswith(suffixe):
            noms_f[code] = nom[:-len(suffixe)]
    return noms_c, noms_f


# ---------------------------------------------------------------------------
# Transcription (UPSERT) — même mécanique que le dénombrement (maj_db)
# ---------------------------------------------------------------------------
def transcrire(conn, dossier, log=None, dry_run=False, exclure_cles=None) -> dict:
    """Transcrit un dossier d'export VAD vers les trois tables (upsert).

    Renvoie {"tables": [{table, present, ajoutes, modifies, inchanges}, …],
             "total": {...}, "traites": n, "dry_run": bool}.
    Lève ErreurVAD si le fichier MÉNAGE est absent (sans lui, rien à transcrire)."""
    log = log or (lambda *_a: None)
    f = trouver_fichiers(dossier)
    if not f["menage"]:
        raise ErreurVAD(
            "Fichier des ménages VAD introuvable dans ce dossier. Attendu : "
            + " ou ".join(NOMS_MENAGE)
            + " (ou tout .dta portant les colonnes "
            + ", ".join(COLS_MENAGE_REQUISES) + ").")
    maj_db._assurer_meta(conn)
    tables, total, traites = [], [0, 0, 0], 0
    for cle_f, table in (("menage", TABLE_MENAGE), ("membre", TABLE_MEMBRE),
                         ("diagnostics", TABLE_DIAG)):
        chemin = f[cle_f]
        if not chemin:
            log(f"   [ignoré] {cle_f} : fichier absent du dossier.")
            tables.append({"table": table, "present": False,
                           "ajoutes": 0, "modifies": 0, "inchanges": 0})
            continue
        a, m, u = maj_db.maj_table(conn, chemin, table, CLES[table], log,
                                   exclure_cles=exclure_cles)
        total = [total[0] + a, total[1] + m, total[2] + u]
        traites += 1
        tables.append({"table": table, "present": True,
                       "ajoutes": a, "modifies": m, "inchanges": u})
    if dry_run:
        conn.rollback()
        log("[DRY-RUN] Aucune écriture (rollback).")
    else:
        # Tout code agent VAD inconnu de `agent` y est créé (nom = code), comme
        # pour le dénombrement : la clé étrangère reste vraie côté Python.
        n_ag = synchroniser_agents(conn)
        if n_ag:
            log(f"   agent : {n_ag} code(s) agent VAD ajouté(s) (nom = code).")
        conn.commit()
        log(f"BILAN VAD : +{total[0]} ajoutées, ~{total[1]} modifiées, "
            f"={total[2]} inchangées sur {traites} table(s).")
    return {"tables": tables, "traites": traites, "dry_run": dry_run,
            "total": {"ajoutes": total[0], "modifies": total[1],
                      "inchanges": total[2]}}


def synchroniser_agents(conn) -> int:
    """Crée dans `agent` tout code de `vad_diagnostics.responsible` qui y manque
    (nom = le code), comme `equipes.synchroniser_agents` pour le dénombrement."""
    import equipes
    equipes.creer_tables(conn)
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT DISTINCT "responsible" FROM "{TABLE_DIAG}" '
                    'WHERE "responsible" IS NOT NULL')
        codes = [txt(r[0]) for r in cur.fetchall()]
    except Exception:
        return 0
    ph = db_source._placeholder(conn)
    ajoutes = 0
    for c in codes:
        if not c:
            continue
        cur.execute(f'SELECT 1 FROM "agent" WHERE "login_ae"={ph}', (c,))
        if cur.fetchone() is None:
            cur.execute('INSERT INTO "agent" ("login_ae","nom_prenom_ae","login_ce") '
                        f'VALUES ({ph},{ph},NULL)', (c, c))
            ajoutes += 1
    conn.commit()
    return ajoutes


# ---------------------------------------------------------------------------
# Présence des données (le dashboard VAD ne s'ouvre que si elles existent)
# ---------------------------------------------------------------------------
def tables_presentes(conn) -> bool:
    """La table des ménages VAD existe-t-elle ET contient-elle des lignes ?"""
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{TABLE_MENAGE}"')
        return (cur.fetchone()[0] or 0) > 0
    except Exception:
        return False


def compter(conn, districts=None, communes=None) -> dict:
    """{'menages': n, 'membres': m, 'districts': d} sur un périmètre."""
    if not tables_presentes(conn):
        return {"menages": 0, "membres": 0, "districts": 0}
    where, params = _clause_perimetre(conn, districts, communes)
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*), COUNT(DISTINCT "CQ7") FROM "{TABLE_MENAGE}"'
                + (f" WHERE {where}" if where else ""), params)
    n, nd = cur.fetchone()
    sql = (f'SELECT COUNT(*) FROM "{TABLE_MEMBRE}" WHERE "interview__key" IN '
           f'(SELECT "interview__key" FROM "{TABLE_MENAGE}"'
           + (f" WHERE {where}" if where else "") + ")")
    try:
        cur.execute(sql, params)
        m = cur.fetchone()[0] or 0
    except Exception:
        m = 0
    return {"menages": n or 0, "membres": m, "districts": nd or 0}


def _clause_perimetre(conn, districts=None, communes=None, fokontany=None):
    """(clause SQL sur vad_menage, params). Du plus fin au plus large :
    `fokontany` (CQ9) prime sur `communes` (CQ8), qui prime sur `districts` (CQ7).
    C'est la descente district → commune → fokontany de la carte."""
    ph = db_source._placeholder(conn)
    if fokontany is not None:
        codes = tuple(int(f) for f in sorted(fokontany)) if not isinstance(
            fokontany, (int, str)) else (int(fokontany),)
        if not codes:
            return "1 = 0", ()
        return f'"CQ9" IN ({",".join([ph] * len(codes))})', codes
    if communes is not None:
        codes = tuple(int(c) for c in sorted(communes))
        if not codes:
            return "1 = 0", ()
        return f'"CQ8" IN ({",".join([ph] * len(codes))})', codes
    if districts:
        codes = tuple(int(d) for d in sorted(districts))
        return f'"CQ7" IN ({",".join([ph] * len(codes))})', codes
    return "", ()
