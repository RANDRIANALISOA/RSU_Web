# -*- coding: utf-8 -*-
"""
db_source.py — Source de données « base de données SQL » pour le rapport RSU.

CONTEXTE (voir CLAUDE.md, section version web) : en production, les données ne
viendront pas de fichiers .dta mais d'une **base PostgreSQL** (les .dta actuels en
sont un export). Ce module simule cette architecture :

    1. `charger_dta_vers_db(DATA, conn)` transcrit les .dta dans une base SQL
       (une table par fichier + tables meta pour les value labels).
    2. `DbDataset(conn, table)` expose une table SQL avec EXACTEMENT la même
       interface qu'un objet `lire_dta.Dta` : `.nobs`, `.varnames`, `.col(nom)`,
       `.col_decoded(nom)`. `rapport_core` fonctionne alors sans modification.
    3. `source_db(conn)` renvoie le resolveur attendu par
       `rapport_core.generer_rapport(chemins, source=...)`.

PORTABLE SQLite <-> PostgreSQL : tout passe par la **DB-API 2.0** (PEP 249). Le
MÊME code marche pour `sqlite3` (bibliothèque standard, zéro installation, pour
simuler tout de suite) et pour `psycopg` (PostgreSQL, en production). Seule la
connexion change — voir `connect()`.

    # Simulation locale (défaut) :
    python simuler_db.py

    # Bascule PostgreSQL (quand la base sera accessible) :
    set RSU_DB_URL=postgresql://user:mdp@hote:5432/rsu   (Windows: set ; bash: export)
    pip install "psycopg[binary]"
    python simuler_db.py
"""

import os

from lire_dta import lire_dta
from rapport_core import _REQUIS, ErreurStructure, ErreurDonnees

BASE = os.path.dirname(os.path.abspath(__file__))

# Jeu logique -> (nom du fichier .dta, nom de la table SQL).
FICHIERS = {
    "diagnostics": ("interview__diagnostics.dta", "interview__diagnostics"),
    "den": ("DEN_MENAGE.dta", "den_menage"),
    "roster": ("segment_roster.dta", "segment_roster"),
}

# Clés étrangères des colonnes géographiques vers le référentiel `zones` :
# {table_donnees: {colonne: (table_zone, colonne_PK)}}. `fokontany` et `num_fkt`
# sont le même code à 8 chiffres -> tous deux vers fokontany(code_fokontany).
FK_ZONES = {
    "den_menage": {
        "region":    ("region",    "code_region"),
        "district":  ("district",  "code_district"),
        "commune":   ("commune",   "code_commune"),
        "fokontany": ("fokontany", "code_fokontany"),
        "num_fkt":   ("fokontany", "code_fokontany"),
    },
}

# Clé étrangère AGENT : le code agent (« responsible » = enquêteur ayant réalisé
# l'interview) de `interview__diagnostics` référence `agent(login_ae)`. Le lien
# vers un CHEF d'équipe se fait ensuite via `agent.login_ce`. den_menage et
# segment_roster n'ont PAS de code agent propre : ils s'y relient par interview__key
# (-> interview__diagnostics -> agent). Comme pour FK_ZONES, la clé est DÉCLARATIVE
# (SQLite ne l'applique pas ; l'intégrité est garantie côté Python par
# equipes.synchroniser_agents, qui crée toute ligne agent manquante). ⚠️ Sur
# PostgreSQL (FK appliquées), il faut synchroniser `agent` AVANT de charger
# interview__diagnostics, sinon l'insert violerait la contrainte.
FK_AGENT = {
    "interview__diagnostics": {"responsible": ("agent", "login_ae")},
}


def _fk_de(table: str) -> dict:
    """FK déclaratives d'une table (zones + agent réunies)."""
    fk = dict(FK_ZONES.get(table, {}))
    fk.update(FK_AGENT.get(table, {}))
    return fk


# ---------------------------------------------------------------------------
# Connexion : SQLite par défaut (stdlib), PostgreSQL si RSU_DB_URL est défini.
# ---------------------------------------------------------------------------
def connect():
    """Renvoie une connexion DB-API 2.0. SQLite par défaut, sinon PostgreSQL."""
    url = os.environ.get("RSU_DB_URL", "").strip()
    if url.startswith("postgres"):
        import psycopg  # psycopg 3 ; `pip install "psycopg[binary]"`
        return psycopg.connect(url)
    import sqlite3
    chemin = os.environ.get("RSU_SQLITE", os.path.join(BASE, "rsu_local.sqlite"))
    return sqlite3.connect(chemin)


def _placeholder(conn) -> str:
    """'?' pour sqlite3 (paramstyle qmark), '%s' pour psycopg (pyformat)."""
    mod = type(conn).__module__.split(".")[0]
    return "%s" if mod.startswith("psycopg") else "?"


def _sql_type(valeurs) -> str:
    """Déduit un type SQL portable (SQLite + PostgreSQL) d'une colonne."""
    a_float = a_int = a_txt = False
    for v in valeurs:
        if v is None:
            continue
        if isinstance(v, bool):
            a_int = True
        elif isinstance(v, int):
            a_int = True
        elif isinstance(v, float):
            a_float = True
        else:
            a_txt = True
    if a_txt:
        return "TEXT"
    if a_float:
        return "DOUBLE PRECISION"
    if a_int:
        return "BIGINT"
    return "TEXT"


def _est_sqlite(conn) -> bool:
    return _placeholder(conn) == "?"


def _coldefs(d, table: str) -> list:
    """Définitions de colonnes d'une table de données (`_rid` + colonnes du .dta),
    en ajoutant les clés étrangères déclaratives : géographiques (FK_ZONES) pour
    `den_menage`, et agent (FK_AGENT) pour `interview__diagnostics`."""
    fk = _fk_de(table)
    defs = ['"_rid" BIGINT']
    for nom in d.varnames:
        col = f'"{nom}" {_sql_type(d.col(nom))}'
        if nom in fk:
            ztable, pk = fk[nom]
            col += f' REFERENCES "{ztable}" ("{pk}")'
        defs.append(col)
    return defs


def districts_du_den(dossier: str) -> set:
    """Ensemble des codes district (int) présents dans DEN_MENAGE.dta d'un dossier —
    pour vérifier qu'un dossier à transcrire concerne bien LE district attendu. Les
    valeurs manquantes (None) sont ignorées. Renvoie set() si le fichier est absent
    ou n'a pas de colonne `district`."""
    fname = FICHIERS["den"][0]
    chemin = os.path.join(dossier, fname)
    if not os.path.isfile(chemin):
        return set()
    d = lire_dta(chemin)
    if "district" not in d.varnames:
        return set()
    return {int(v) for v in d.col("district") if v is not None}


def _assurer_cibles_fk(conn, table: str) -> None:
    """Les tables cibles des FK doivent exister avant de créer une table qui les
    référence (obligatoire en PostgreSQL ; sans effet sinon)."""
    if table in FK_ZONES:
        import zones  # import LOCAL -> pas de cycle (db_source n'importe pas zones au module)
        zones.assurer_zones(conn)
    if table in FK_AGENT:
        import equipes  # import LOCAL -> pas de cycle
        equipes.creer_tables(conn)


def assurer_fk_den_menage(conn) -> bool:
    """SQLite : si `den_menage` existe SANS clés étrangères (schéma antérieur), la
    reconstruit AVEC les FK vers `zones`, en conservant les données. Renvoie True si
    reconstruite. (PostgreSQL : les installations neuves ont déjà les FK.)"""
    if not _est_sqlite(conn):
        return False
    cur = conn.cursor()
    row = cur.execute("SELECT sql FROM sqlite_master WHERE type='table' "
                      "AND name='den_menage'").fetchone()
    if not row or "REFERENCES" in (row[0] or "").upper():
        return False                      # absente, ou déjà dotée des FK
    _assurer_cibles_fk(conn, "den_menage")
    info = cur.execute('PRAGMA table_info("den_menage")').fetchall()  # (cid,nom,type,…)
    fk = FK_ZONES["den_menage"]
    defs = []
    for _cid, nom, typ, *_ in info:
        c = f'"{nom}" {typ or "TEXT"}'
        if nom in fk:
            ztable, pk = fk[nom]
            c += f' REFERENCES "{ztable}" ("{pk}")'
        defs.append(c)
    cols = ",".join(f'"{r[1]}"' for r in info)
    cur.execute('ALTER TABLE "den_menage" RENAME TO "_den_menage_old"')
    cur.execute(f'CREATE TABLE "den_menage" ({", ".join(defs)})')
    cur.execute(f'INSERT INTO "den_menage" ({cols}) SELECT {cols} FROM "_den_menage_old"')
    cur.execute('DROP TABLE "_den_menage_old"')
    conn.commit()
    return True


def assurer_fk_diagnostics(conn) -> bool:
    """SQLite : si `interview__diagnostics` existe SANS clé étrangère (schéma
    antérieur), la reconstruit AVEC la FK `responsible` -> `agent(login_ae)`, données
    conservées. Renvoie True si reconstruite. La table `agent` est assurée d'abord."""
    if not _est_sqlite(conn):
        return False
    cur = conn.cursor()
    row = cur.execute("SELECT sql FROM sqlite_master WHERE type='table' "
                      "AND name='interview__diagnostics'").fetchone()
    if not row or "REFERENCES" in (row[0] or "").upper():
        return False                      # absente, ou déjà dotée de la FK
    _assurer_cibles_fk(conn, "interview__diagnostics")
    info = cur.execute('PRAGMA table_info("interview__diagnostics")').fetchall()
    fk = _fk_de("interview__diagnostics")
    defs = []
    for _cid, nom, typ, *_ in info:
        c = f'"{nom}" {typ or "TEXT"}'
        if nom in fk:
            ztable, pk = fk[nom]
            c += f' REFERENCES "{ztable}" ("{pk}")'
        defs.append(c)
    cols = ",".join(f'"{r[1]}"' for r in info)
    cur.execute('ALTER TABLE "interview__diagnostics" RENAME TO "_diag_old"')
    cur.execute(f'CREATE TABLE "interview__diagnostics" ({", ".join(defs)})')
    cur.execute(f'INSERT INTO "interview__diagnostics" ({cols}) '
                'SELECT ' + cols + ' FROM "_diag_old"')
    cur.execute('DROP TABLE "_diag_old"')
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# ETL : .dta -> base SQL
# ---------------------------------------------------------------------------
def _creer_meta(conn):
    """Tables meta : schéma (ordre + jeu de labels par colonne) et value labels."""
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS "_schema"')
    cur.execute('DROP TABLE IF EXISTS "_value_labels"')
    cur.execute('CREATE TABLE "_schema" ('
                '"source_table" TEXT, "ordinal" BIGINT, '
                '"varname" TEXT, "set_name" TEXT)')
    cur.execute('CREATE TABLE "_value_labels" ('
                '"source_table" TEXT, "set_name" TEXT, '
                '"code" BIGINT, "label" TEXT)')


def _transcrire_un(conn, dta_path: str, table: str, log):
    """Transcrit un .dta dans une table SQL + alimente les tables meta."""
    d = lire_dta(dta_path)
    ph = _placeholder(conn)
    cur = conn.cursor()

    # 1. (Re)création de la table de données. `_rid` conserve l'ORDRE d'origine.
    #    Les colonnes géographiques de den_menage reçoivent leurs clés étrangères
    #    vers `zones` (dont on s'assure de l'existence au préalable).
    _assurer_cibles_fk(conn, table)
    cur.execute(f'DROP TABLE IF EXISTS "{table}"')
    cur.execute(f'CREATE TABLE "{table}" ({", ".join(_coldefs(d, table))})')

    # 2. Meta : ordre des colonnes + jeu de value labels associé à chacune.
    for i, nom in enumerate(d.varnames):
        setname = d.val_label_names[i] if i < len(d.val_label_names) else ""
        cur.execute(
            f'INSERT INTO "_schema" ("source_table","ordinal","varname","set_name")'
            f" VALUES ({ph},{ph},{ph},{ph})",
            (table, i, nom, setname or ""))

    # 3. Meta : value labels (uniquement les jeux réellement utilisés par ce fichier).
    sets_utiles = {s for s in d.val_label_names if s}
    for setname in sets_utiles:
        for code, label in d.value_labels.get(setname, {}).items():
            cur.execute(
                f'INSERT INTO "_value_labels" '
                f'("source_table","set_name","code","label")'
                f" VALUES ({ph},{ph},{ph},{ph})",
                (table, setname, code, label))

    # 4. Données : insertion en masse (une transaction).
    cols = ['"_rid"'] + [f'"{n}"' for n in d.varnames]
    marks = ",".join([ph] * len(cols))
    sql = f'INSERT INTO "{table}" ({",".join(cols)}) VALUES ({marks})'
    colonnes = [d.col(n) for n in d.varnames]
    lignes = [tuple([i] + [colonnes[j][i] for j in range(len(d.varnames))])
              for i in range(d.nobs)]
    cur.executemany(sql, lignes)
    log(f'   table "{table}" : {d.nobs} lignes, {len(d.varnames)} colonnes')


def charger_dta_vers_db(data_dir: str, conn, log=print, fichiers=None):
    """Transcrit les .dta requis (par défaut les 3 du rapport) dans la base SQL."""
    fichiers = fichiers or FICHIERS
    log("Transcription des .dta vers la base SQL…")
    _creer_meta(conn)
    for _kind, (fname, table) in fichiers.items():
        chemin = os.path.join(data_dir, fname)
        if not os.path.isfile(chemin):
            raise ErreurDonnees(f"Fichier .dta introuvable pour la base : {fname}")
        _transcrire_un(conn, chemin, table, log)
    conn.commit()
    log("Transcription terminée (commit).")


# ---------------------------------------------------------------------------
# ETL multi-sources : plusieurs dossiers .dta (districts) -> mêmes tables
# ---------------------------------------------------------------------------
def _transcrire_multi(conn, dta_paths: list, table: str, log):
    """Transcrit PLUSIEURS .dta de MÊME structure dans UNE table SQL.

    Les lignes sont concaténées (`_rid` continu, ordre = ordre des sources), les
    value labels sont unionnés (dédupliqués par set_name+code). Sert à réunir les
    données de plusieurs districts (MAMPIKONY + Antsirabe + …) dans une base."""
    datasets = [lire_dta(p) for p in dta_paths]
    ref = datasets[0]
    for p, d in zip(dta_paths[1:], datasets[1:]):
        if d.varnames != ref.varnames:
            raise ErreurStructure(
                f"Structure différente pour « {table} » dans {os.path.basename(p)} "
                f"(colonnes incompatibles avec la 1re source).")

    ph = _placeholder(conn)
    cur = conn.cursor()

    # 1. Table : type de chaque colonne déduit sur TOUTES les sources réunies.
    cur.execute(f'DROP TABLE IF EXISTS "{table}"')
    coldefs = ['"_rid" BIGINT']
    for nom in ref.varnames:
        valeurs = []
        for d in datasets:
            valeurs.extend(d.col(nom))
        coldefs.append(f'"{nom}" {_sql_type(valeurs)}')
    cur.execute(f'CREATE TABLE "{table}" ({", ".join(coldefs)})')

    # 2. _schema : depuis la référence (structure commune à toutes les sources).
    for i, nom in enumerate(ref.varnames):
        setname = ref.val_label_names[i] if i < len(ref.val_label_names) else ""
        cur.execute(
            f'INSERT INTO "_schema" ("source_table","ordinal","varname","set_name")'
            f" VALUES ({ph},{ph},{ph},{ph})",
            (table, i, nom, setname or ""))

    # 3. _value_labels : union sur toutes les sources (1re occurrence gardée).
    merged: dict = {}
    for d in datasets:
        for s in {x for x in d.val_label_names if x}:
            m = merged.setdefault(s, {})
            for code, label in d.value_labels.get(s, {}).items():
                m.setdefault(code, label)
    for setname, mapping in merged.items():
        for code, label in mapping.items():
            cur.execute(
                f'INSERT INTO "_value_labels" '
                f'("source_table","set_name","code","label")'
                f" VALUES ({ph},{ph},{ph},{ph})",
                (table, setname, code, label))

    # 4. Données : concaténées, _rid continu sur l'ensemble des sources.
    cols = ['"_rid"'] + [f'"{n}"' for n in ref.varnames]
    marks = ",".join([ph] * len(cols))
    sql = f'INSERT INTO "{table}" ({",".join(cols)}) VALUES ({marks})'
    rid = 0
    total = 0
    for d in datasets:
        colonnes = [d.col(n) for n in ref.varnames]
        lignes = []
        for i in range(d.nobs):
            lignes.append(tuple([rid] + [colonnes[j][i]
                                         for j in range(len(ref.varnames))]))
            rid += 1
        if lignes:
            cur.executemany(sql, lignes)
        total += d.nobs
    log(f'   table "{table}" : {total} lignes '
        f'({len(dta_paths)} sources), {len(ref.varnames)} colonnes')


def charger_dta_multi_vers_db(data_dirs: list, conn, log=print, fichiers=None):
    """Transcrit les .dta de PLUSIEURS dossiers (concaténés) dans la base SQL.

    Chaque dossier doit contenir les mêmes fichiers (même structure). Reconstruit
    entièrement les tables (les données existantes sont remplacées par l'union)."""
    fichiers = fichiers or FICHIERS
    log(f"Transcription de {len(data_dirs)} sources vers la base SQL…")
    _creer_meta(conn)
    for _kind, (fname, table) in fichiers.items():
        paths = []
        for dd in data_dirs:
            p = os.path.join(dd, fname)
            if not os.path.isfile(p):
                raise ErreurDonnees(f"Fichier .dta introuvable : {p}")
            paths.append(p)
        _transcrire_multi(conn, paths, table, log)
    conn.commit()
    log("Transcription terminée (commit).")


# ---------------------------------------------------------------------------
# Adaptateur : une table SQL vue comme un objet .dta (interface de lire_dta.Dta)
# ---------------------------------------------------------------------------
class DbDataset:
    """Expose une table SQL avec l'interface consommée par rapport_core.

    `where`/`params` (optionnels) restreignent les lignes lues — utilisé pour ne
    charger qu'un fokontany (voir source_db(conn, fkt=...)). Sans eux, toute la
    table est lue (comportement d'origine).
    """

    def __init__(self, conn, table: str, where: str = "", params=()):
        self.conn = conn
        self.table = table
        self._ph = _placeholder(conn)
        self._where = f" WHERE {where}" if where else ""
        self._params = tuple(params)
        cur = conn.cursor()
        cur.execute(
            f'SELECT "varname","set_name" FROM "_schema" '
            f'WHERE "source_table"={self._ph} ORDER BY "ordinal"', (table,))
        lignes = cur.fetchall()
        if not lignes:
            raise ErreurStructure(
                f"La table « {table} » est absente de la base "
                f"(transcription non effectuée ?).")
        self.varnames = [r[0] for r in lignes]
        self._setname = {r[0]: (r[1] or "") for r in lignes}
        cur.execute(f'SELECT COUNT(*) FROM "{table}"{self._where}', self._params)
        self.nobs = cur.fetchone()[0]
        self._cache = {}

    def col(self, name: str) -> list:
        """Colonne brute (mêmes types que lire_dta : nombres / None / chaînes)."""
        if name not in self._cache:
            cur = self.conn.cursor()
            cur.execute(
                f'SELECT "{name}" FROM "{self.table}"{self._where} '
                f'ORDER BY "_rid"', self._params)
            self._cache[name] = [r[0] for r in cur.fetchall()]
        return self._cache[name]

    def col_decoded(self, name: str) -> list:
        """Colonne avec value labels appliqués (comme Dta.col_decoded)."""
        raw = self.col(name)
        setn = self._setname.get(name, "")
        if not setn:
            return raw
        cur = self.conn.cursor()
        cur.execute(
            f'SELECT "code","label" FROM "_value_labels" '
            f'WHERE "source_table"={self._ph} AND "set_name"={self._ph}',
            (self.table, setn))
        mapping = {c: l for c, l in cur.fetchall()}
        if not mapping:
            return raw
        out = []
        for v in raw:
            if v is None:
                out.append(None)
            elif v in mapping:
                out.append(mapping[v])
            else:
                out.append(v)
        return out


# ---------------------------------------------------------------------------
# Resolveur pour rapport_core.generer_rapport(chemins, source=source_db(conn))
# ---------------------------------------------------------------------------
def source_db(conn, fkt=None, district=None, commune=None, communes=None):
    """Renvoie une fonction kind -> DbDataset, avec validation des colonnes.

    Filtrage optionnel (au plus un des quatre) :
    - `fkt` (code num_fkt) : seules les lignes de CE fokontany. DEN filtré sur
      num_fkt, ROSTER/DIAGNOSTICS via les interview__key de ce fokontany. Rend une
      page « un fokontany » légère (≈ quelques centaines de ménages).
    - `commune` (code_commune, 6 chiffres) : toutes les lignes de CETTE commune.
      DEN filtré sur la colonne `commune`, ROSTER/DIAGNOSTICS via ses
      interview__key. Sert la vue « périmètre commune » du dashboard multi-pages.
    - `communes` (liste de code_commune) : l'UNION de PLUSIEURS communes. DEN
      filtré sur `commune IN (...)`, ROSTER/DIAGNOSTICS via leurs interview__key.
      Sert la vue « globale » d'un Superviseur Technique = agrégat de SES communes
      affectées uniquement (et non tout le district).
    - `district` (code_district) : toutes les lignes de CE district. DEN filtré
      sur la colonne `district`, ROSTER/DIAGNOSTICS via ses interview__key. Sert
      la vue « suivi par district » (0 ligne si le district n'a pas de données).

    Sans filtre : toute la base.
    """
    ph = _placeholder(conn)
    codes_communes = tuple(int(c) for c in communes) if communes else ()

    def resolveur(kind: str) -> DbDataset:
        fname, table = FICHIERS[kind]
        if district is not None:
            if kind == "den":
                ds = DbDataset(conn, table, f'"district" = {ph}',
                               (int(district),))
            else:  # roster / diagnostics : via les interview__key du district
                ds = DbDataset(
                    conn, table,
                    f'"interview__key" IN '
                    f'(SELECT "interview__key" FROM "den_menage" '
                    f'WHERE "district" = {ph})',
                    (int(district),))
        elif codes_communes:
            marks = ",".join([ph] * len(codes_communes))
            if kind == "den":
                ds = DbDataset(conn, table, f'"commune" IN ({marks})',
                               codes_communes)
            else:  # roster / diagnostics : via les interview__key de ces communes
                ds = DbDataset(
                    conn, table,
                    f'"interview__key" IN '
                    f'(SELECT "interview__key" FROM "den_menage" '
                    f'WHERE "commune" IN ({marks}))',
                    codes_communes)
        elif commune is not None:
            if kind == "den":
                ds = DbDataset(conn, table, f'"commune" = {ph}',
                               (int(commune),))
            else:  # roster / diagnostics : via les interview__key de la commune
                ds = DbDataset(
                    conn, table,
                    f'"interview__key" IN '
                    f'(SELECT "interview__key" FROM "den_menage" '
                    f'WHERE "commune" = {ph})',
                    (int(commune),))
        elif fkt is None:
            ds = DbDataset(conn, table)
        elif kind == "den":
            ds = DbDataset(conn, table, f'"num_fkt" = {ph}', (int(fkt),))
        else:  # roster / diagnostics : rattachés au fokontany via interview__key
            ds = DbDataset(
                conn, table,
                f'"interview__key" IN '
                f'(SELECT "interview__key" FROM "den_menage" '
                f'WHERE "num_fkt" = {ph})',
                (int(fkt),))
        manquantes = [c for c in _REQUIS.get(fname, []) if c not in ds.varnames]
        if manquantes:
            raise ErreurStructure(
                f"La table « {table} » ne contient pas : "
                f"{', '.join(manquantes)}.")
        return ds
    return resolveur
