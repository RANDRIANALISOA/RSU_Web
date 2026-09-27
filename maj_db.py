# -*- coding: utf-8 -*-
"""
maj_db.py — Mise à jour INCRÉMENTALE de la base depuis les .dta.

Met à jour les tables `den_menage`, `interview__diagnostics`, `segment_roster`
à partir d'un DOSSIER de fichiers `.dta` de mêmes noms (la SOURCE reste les .dta).

Règle demandée : on ne SUPPRIME rien. On :
    • AJOUTE les lignes absentes de la base ;
    • MODIFIE les lignes dont au moins une valeur a changé ;
    • laisse INCHANGÉES les autres (relancer sur les mêmes .dta ne change rien).

Cible = la base pointée par db_source.connect() : SQLite en local par défaut,
PostgreSQL si `RSU_DB_URL` est défini. Tout passe par la DB-API 2.0 (portable).

Identité d'une ligne (clé) par table :
    interview__diagnostics : interview__key
    den_menage             : interview__key
    segment_roster         : (interview__key, segment_roster__id)

Usage :
    python maj_db.py                       # dossier = config.DATA_DIR
    python maj_db.py D:\\export_du_jour     # autre dossier de .dta
    python maj_db.py D:\\export_du_jour --dry-run   # simuler, ne rien écrire
"""
import os
import sys

import config
import db_source
from lire_dta import lire_dta
from rapport_core import _REQUIS

class ErreurMaj(Exception):
    """Erreur métier de mise à jour (fichier/structure). Utilisable côté web : le
    serveur l'attrape et affiche un message propre (contrairement à SystemExit qui
    tuerait le thread de la requête)."""


# Clé d'unicité par table SQL (voir en-tête). Une ligne .dta = une clé.
CLES = {
    "interview__diagnostics": ("interview__key",),
    "den_menage": ("interview__key",),
    "segment_roster": ("interview__key", "segment_roster__id"),
}

# Colonnes EXIGÉES par table, déduites de `rapport_core._REQUIS` (qui les liste
# par nom de fichier) via `db_source.FICHIERS`. Garde-fou depuis que la structure
# est RÉCONCILIÉE au lieu d'être exigée à l'identique (cf. `maj_table`) : un .dta
# peut apporter des colonnes en plus ou en moins, mais s'il n'a pas celles-là,
# ce n'est pas un export de dénombrement et on refuse. Les tables VAD n'y
# figurent pas : `vad_db.trouver_fichiers` fait déjà ce contrôle de son côté.
REQUISES = {tb: tuple(_REQUIS.get(fn, ()))
            for _k, (fn, tb) in db_source.FICHIERS.items()}


# ---------------------------------------------------------------------------
# Méta (schéma + value labels) — créées si absentes, JAMAIS supprimées en bloc.
# ---------------------------------------------------------------------------
def _assurer_meta(conn):
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS "_schema" ('
                '"source_table" TEXT, "ordinal" BIGINT, '
                '"varname" TEXT, "set_name" TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS "_value_labels" ('
                '"source_table" TEXT, "set_name" TEXT, '
                '"code" BIGINT, "label" TEXT)')


def _colonnes_connues(conn, table):
    """Colonnes de la table telles qu'enregistrées dans `_schema` (ordre d'origine)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "varname" FROM "_schema" WHERE "source_table"={ph} '
                f'ORDER BY "ordinal"', (table,))
    return [r[0] for r in cur.fetchall()]


def _colonnes_sql(conn, table):
    """Colonnes RÉELLES de la table SQL (`_rid` compris), ou [] si elle n'existe pas.

    `_schema` dit ce que la base est censée porter ; ceci dit ce qu'elle porte
    VRAIMENT. Les deux peuvent diverger après un aperçu (dry-run) : le rollback
    annule les écritures de `_schema`, mais le CREATE / ALTER TABLE, lui, est
    déjà passé en autocommit côté sqlite3. D'où les gardes « si la colonne n'y
    est pas déjà » plus bas : un aperçu suivi de son application ne doit pas
    échouer sur une colonne en double.

    ⚠️ On interroge le CATALOGUE, jamais la table : un `SELECT` sur une table
    absente lève, et sous PostgreSQL une requête en erreur AVORTE la transaction
    en cours (tout ce qui suit échouerait). `PRAGMA table_info` et
    `information_schema.columns` renvoient, eux, une liste vide sans rien lever."""
    cur = conn.cursor()
    if db_source._est_sqlite(conn):
        cur.execute(f'PRAGMA table_info("{table}")')
        return [r[1] for r in cur.fetchall()]
    cur.execute('SELECT "column_name" FROM "information_schema"."columns" '
                'WHERE "table_name"=%s ORDER BY "ordinal_position"', (table,))
    return [r[0] for r in cur.fetchall()]


def _setnames_connus(conn, table):
    """{colonne: set_name} tels qu'enregistrés dans `_schema` pour cette table."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "varname","set_name" FROM "_schema" '
                f'WHERE "source_table"={ph}', (table,))
    return {r[0]: (r[1] or "") for r in cur.fetchall()}


def _ajouter_colonnes(conn, d, table, noms):
    """ALTER TABLE ADD COLUMN pour les colonnes que le .dta apporte EN PLUS.

    Les lignes déjà en base gardent NULL sur ces colonnes : on n'invente pas une
    valeur pour une question qui n'était pas posée à l'époque. Renvoie la liste
    des colonnes réellement ajoutées."""
    fk = db_source._fk_de(table)
    physiques = set(_colonnes_sql(conn, table))
    cur = conn.cursor()
    ajoutees = []
    for nom in noms:
        if nom in physiques:            # déjà ajoutée (aperçu précédent, cf. _colonnes_sql)
            continue
        col = f'"{nom}" {db_source._sql_type(d.col(nom))}'
        if nom in fk:                   # même clé étrangère déclarative qu'à la création
            ztable, pk = fk[nom]
            col += f' REFERENCES "{ztable}" ("{pk}")'
        cur.execute(f'ALTER TABLE "{table}" ADD COLUMN {col}')
        ajoutees.append(nom)
    return ajoutees


def _ecrire_meta(conn, d, table, ordre=None):
    """(Re)écrit le schéma et les value labels de CETTE table (les autres intactes).

    `ordre` : liste COMPLÈTE des colonnes de la table quand elle en porte plus que
    le .dta courant (questionnaire qui a évolué — colonnes ajoutées, colonnes
    disparues qu'on conserve). Par défaut, les colonnes du .dta. Les colonnes
    absentes du fichier gardent le `set_name` déjà enregistré, et seuls les jeux
    de value labels PORTÉS par le .dta sont remplacés : ceux des colonnes absentes
    restent en place, sinon le rapport perdrait leurs libellés."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    setnames = {nom: (d.val_label_names[i] if i < len(d.val_label_names) else "") or ""
                for i, nom in enumerate(d.varnames)}
    if ordre is None:
        ordre, anciens = list(d.varnames), {}
    else:
        anciens = _setnames_connus(conn, table)
    cur.execute(f'DELETE FROM "_schema" WHERE "source_table"={ph}', (table,))
    for i, nom in enumerate(ordre):
        setname = setnames.get(nom, anciens.get(nom, ""))
        cur.execute('INSERT INTO "_schema" '
                    '("source_table","ordinal","varname","set_name") '
                    f'VALUES ({ph},{ph},{ph},{ph})', (table, i, nom, setname))
    for setname in {s for s in d.val_label_names if s}:
        cur.execute(f'DELETE FROM "_value_labels" WHERE "source_table"={ph} '
                    f'AND "set_name"={ph}', (table, setname))
        for code, label in d.value_labels.get(setname, {}).items():
            cur.execute('INSERT INTO "_value_labels" '
                        '("source_table","set_name","code","label") '
                        f'VALUES ({ph},{ph},{ph},{ph})', (table, setname, code, label))


def _index_unique(conn, table, cles):
    """Index unique sur la clé (intégrité + accélère les UPDATE). Best effort."""
    cur = conn.cursor()
    cols = ",".join(f'"{c}"' for c in cles)
    try:
        cur.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "ux_{table}" '
                    f'ON "{table}" ({cols})')
    except Exception as e:   # ex. doublons de clé préexistants : on prévient, sans bloquer
        print(f"   (index unique non créé sur {table} : {e})")


def _creer_table(conn, d, table):
    # Clés étrangères géographiques (den_menage -> zones) : mêmes définitions que
    # le chargement complet, cibles assurées au préalable.
    db_source._assurer_cibles_fk(conn, table)
    conn.cursor().execute(
        f'CREATE TABLE "{table}" ({", ".join(db_source._coldefs(d, table))})')


# ---------------------------------------------------------------------------
# Upsert d'une table depuis son .dta
# ---------------------------------------------------------------------------
def maj_table(conn, dta_path, table, cles, log=print, exclure_cles=None):
    """Renvoie (ajoutes, modifies, inchanges).

    `exclure_cles` : interview__key a NE PAS transcrire (lignes hors du district
    de l'Expert, cf. db_source.cles_hors_district). Les 3 tables se rattachent au
    segment par interview__key, donc le meme jeu de cles les filtre toutes.
    """
    d = lire_dta(dta_path)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cols = list(d.varnames)
    for c in cles:
        if c not in cols:
            raise ErreurMaj(f"[{table}] colonne clé « {c} » absente du .dta.")
    manquantes = [c for c in REQUISES.get(table, ()) if c not in cols]
    if manquantes:
        raise ErreurMaj(
            f"[{table}] {os.path.basename(dta_path)} n'a pas les colonnes "
            f"indispensables au rapport : {', '.join(manquantes)}. "
            f"Ce fichier n'est pas un export de dénombrement RSU.")
    colonnes = [d.col(n) for n in cols]              # une liste par colonne
    idx_cle = [cols.index(c) for c in cles]
    n = d.nobs

    def ligne(i):
        return tuple(colonnes[j][i] for j in range(len(cols)))

    # Lignes a transcrire (toutes, sauf celles ecartees par interview__key).
    if exclure_cles and "interview__key" in cols:
        ik = colonnes[cols.index("interview__key")]
        retenues = [i for i in range(n) if ik[i] not in exclure_cles]
    else:
        retenues = list(range(n))

    connues = _colonnes_connues(conn, table)
    physiques = _colonnes_sql(conn, table)
    if physiques and not connues:
        # La table existe mais `_schema` est vide : un aperçu (dry-run) l'a créée
        # puis le rollback a effacé son schéma. On repart de ses colonnes réelles
        # plutôt que de la recréer (ce qui échouerait).
        connues = [c for c in physiques if c != "_rid"]

    # --- Table absente : création + chargement complet (première fois) ---
    if not physiques:
        _creer_table(conn, d, table)
        _ecrire_meta(conn, d, table)
        marks = ",".join([ph] * (len(cols) + 1))
        sql = (f'INSERT INTO "{table}" ("_rid",'
               + ",".join(f'"{c}"' for c in cols) + f') VALUES ({marks})')
        cur.executemany(sql, [(r,) + ligne(i) for r, i in enumerate(retenues)])
        _index_unique(conn, table, cles)
        log(f'   table "{table}" créée : {len(retenues)} lignes ajoutées.')
        return (len(retenues), 0, 0)

    # --- Table existante : STRUCTURE RÉCONCILIÉE ---------------------------
    # Le questionnaire du dénombrement évolue d'une version à l'autre (celui de
    # septembre 2026 ajoute `nbr_max_men` à DEN_MENAGE). Exiger des colonnes
    # identiques à celles de la base faisait refuser tout le dossier pour une
    # colonne d'écart, et imposait un rechargement complet. On accepte donc un
    # export dont la structure diffère, dès lors qu'il porte bien les colonnes
    # clés et celles dont le rapport a besoin (vérifiées plus haut) :
    #   • colonne du .dta absente de la base -> ajoutée (ALTER TABLE) ; les
    #     lignes déjà transcrites y restent NULL ;
    #   • colonne de la base absente du .dta -> CONSERVÉE : les lignes anciennes
    #     gardent leur valeur, les nouvelles la laissent NULL ;
    #   • ordre des colonnes différent -> sans effet, tout se fait par NOM.
    # L'ordre enregistré dans `_schema` reste celui de la base, les nouvelles
    # colonnes venant à la suite : ce qui était déjà lu ne se décale pas.
    nouvelles = [c for c in cols if c not in connues]
    if nouvelles:
        _ajouter_colonnes(conn, d, table, nouvelles)
        log(f'   table "{table}" : {len(nouvelles)} colonne(s) ajoutée(s) par ce '
            f'questionnaire ({", ".join(nouvelles)}).')
    absentes = [c for c in connues if c not in cols]
    if absentes:
        log(f'   table "{table}" : {len(absentes)} colonne(s) de la base absente(s) '
            f'de ce .dta, conservée(s) ({", ".join(absentes[:5])}'
            f'{"…" if len(absentes) > 5 else ""}).')
    ordre = connues + nouvelles

    # Lignes existantes : clé -> tuple(valeurs dans l'ordre `cols`).
    sel = ",".join(f'"{c}"' for c in cols)
    cur.execute(f'SELECT {sel} FROM "{table}"')
    existant = {}
    for row in cur.fetchall():
        row = tuple(row)
        existant[tuple(row[k] for k in idx_cle)] = row
    cur.execute(f'SELECT MAX("_rid") FROM "{table}"')
    mx = cur.fetchone()[0]
    mx = -1 if mx is None else mx

    ajouts, modifs, inchange = [], [], 0
    for i in retenues:
        vals = ligne(i)
        cle = tuple(vals[k] for k in idx_cle)
        anc = existant.get(cle)
        if anc is None:
            ajouts.append(vals)
        elif anc != vals:
            modifs.append(vals)
        else:
            inchange += 1

    if ajouts:
        marks = ",".join([ph] * (len(cols) + 1))
        sql = (f'INSERT INTO "{table}" ("_rid",' + sel + f') VALUES ({marks})')
        cur.executemany(sql, [(mx + 1 + p,) + v for p, v in enumerate(ajouts)])

    if modifs:
        set_clause = ",".join(f'"{c}"={ph}' for c in cols)
        where = " AND ".join(f'"{c}"={ph}' for c in cles)
        sql = f'UPDATE "{table}" SET {set_clause} WHERE {where}'
        cur.executemany(sql, [v + tuple(v[k] for k in idx_cle) for v in modifs])

    _ecrire_meta(conn, d, table, ordre)   # rafraîchit les value labels (peuvent s'étendre)
    _index_unique(conn, table, cles)
    log(f'   table "{table}" : +{len(ajouts)} ajoutées, ~{len(modifs)} modifiées, '
        f'={inchange} inchangées (total .dta : {n}).')
    return (len(ajouts), len(modifs), inchange)


def maj_depuis_dossier(data_dir, conn, log=print, dry_run=False,
                       exclure_cles=None):
    """Transcrit (upsert) tous les .dta d'un dossier. Renvoie un résultat structuré :
        {"tables": [{table, present, ajoutes, modifies, inchanges}, ...],
         "total": {"ajoutes","modifies","inchanges"}, "traites": n, "dry_run": bool}
    Lève ErreurMaj (fichier/structure). Web-safe (pas de SystemExit).

    `exclure_cles` : interview__key a ecarter sur les 3 tables (segments hors du
    district de l'Expert, cf. db_source.cles_hors_district).
    """
    _assurer_meta(conn)
    tables, total, traites = [], [0, 0, 0], 0
    for table, cles in CLES.items():
        fname = next(fn for _k, (fn, tb) in db_source.FICHIERS.items() if tb == table)
        chemin = os.path.join(data_dir, fname)
        if not os.path.isfile(chemin):
            log(f"   [ignoré] {fname} absent du dossier.")
            tables.append({"table": table, "present": False,
                           "ajoutes": 0, "modifies": 0, "inchanges": 0})
            continue
        a, m, u = maj_table(conn, chemin, table, cles, log,
                            exclure_cles=exclure_cles)
        total = [total[0] + a, total[1] + m, total[2] + u]
        traites += 1
        tables.append({"table": table, "present": True,
                       "ajoutes": a, "modifies": m, "inchanges": u})
    if traites == 0:
        raise ErreurMaj(f"Aucun fichier .dta attendu trouvé dans : {data_dir}")
    if dry_run:
        conn.rollback()
        log("\n[DRY-RUN] Aucune écriture (rollback). Bilan simulé ci-dessous.")
    else:
        conn.commit()
        log("\nMise à jour validée (commit).")
    log(f"BILAN : +{total[0]} ajoutées, ~{total[1]} modifiées, "
        f"={total[2]} inchangées sur {traites} table(s).")
    return {"tables": tables, "traites": traites, "dry_run": dry_run,
            "total": {"ajoutes": total[0], "modifies": total[1],
                      "inchanges": total[2]}}


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv[1:]
    data_dir = args[0] if args else config.DATA_DIR
    if not os.path.isdir(data_dir):
        raise SystemExit(f"Dossier introuvable : {data_dir}")

    moteur = "PostgreSQL" if os.environ.get("RSU_DB_URL", "").startswith("postgres") \
        else "SQLite (local)"
    print(f"Source .dta : {data_dir}")
    print(f"Base cible  : {moteur}" + ("   [DRY-RUN]" if dry else ""))
    conn = db_source.connect()
    try:
        maj_depuis_dossier(data_dir, conn, print, dry_run=dry)
    except ErreurMaj as e:
        raise SystemExit(f"Erreur : {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
