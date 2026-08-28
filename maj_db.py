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


def _ecrire_meta(conn, d, table):
    """(Re)écrit le schéma et les value labels de CETTE table (les autres intactes)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'DELETE FROM "_schema" WHERE "source_table"={ph}', (table,))
    cur.execute(f'DELETE FROM "_value_labels" WHERE "source_table"={ph}', (table,))
    for i, nom in enumerate(d.varnames):
        setname = d.val_label_names[i] if i < len(d.val_label_names) else ""
        cur.execute('INSERT INTO "_schema" '
                    '("source_table","ordinal","varname","set_name") '
                    f'VALUES ({ph},{ph},{ph},{ph})', (table, i, nom, setname or ""))
    for setname in {s for s in d.val_label_names if s}:
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
def maj_table(conn, dta_path, table, cles, log=print):
    """Renvoie (ajoutes, modifies, inchanges)."""
    d = lire_dta(dta_path)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cols = list(d.varnames)
    for c in cles:
        if c not in cols:
            raise ErreurMaj(f"[{table}] colonne clé « {c} » absente du .dta.")
    colonnes = [d.col(n) for n in cols]              # une liste par colonne
    idx_cle = [cols.index(c) for c in cles]
    n = d.nobs

    def ligne(i):
        return tuple(colonnes[j][i] for j in range(len(cols)))

    connues = _colonnes_connues(conn, table)

    # --- Table absente : création + chargement complet (première fois) ---
    if not connues:
        _creer_table(conn, d, table)
        _ecrire_meta(conn, d, table)
        marks = ",".join([ph] * (len(cols) + 1))
        sql = (f'INSERT INTO "{table}" ("_rid",'
               + ",".join(f'"{c}"' for c in cols) + f') VALUES ({marks})')
        cur.executemany(sql, [(i,) + ligne(i) for i in range(n)])
        _index_unique(conn, table, cles)
        log(f'   table "{table}" créée : {n} lignes ajoutées.')
        return (n, 0, 0)

    # --- Table existante : la structure des colonnes doit correspondre ---
    if connues != cols:
        raise ErreurMaj(
            f"[{table}] structure différente : les colonnes du .dta ne correspondent "
            f"pas à celles de la base. Un changement de questionnaire nécessite un "
            f"rechargement complet (db_source.charger_dta_vers_db), pas un update.")

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
    for i in range(n):
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

    _ecrire_meta(conn, d, table)          # rafraîchit les value labels (peuvent s'étendre)
    _index_unique(conn, table, cles)
    log(f'   table "{table}" : +{len(ajouts)} ajoutées, ~{len(modifs)} modifiées, '
        f'={inchange} inchangées (total .dta : {n}).')
    return (len(ajouts), len(modifs), inchange)


def maj_depuis_dossier(data_dir, conn, log=print, dry_run=False):
    """Transcrit (upsert) tous les .dta d'un dossier. Renvoie un résultat structuré :
        {"tables": [{table, present, ajoutes, modifies, inchanges}, ...],
         "total": {"ajoutes","modifies","inchanges"}, "traites": n, "dry_run": bool}
    Lève ErreurMaj (fichier/structure). Web-safe (pas de SystemExit)."""
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
        a, m, u = maj_table(conn, chemin, table, cles, log)
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
