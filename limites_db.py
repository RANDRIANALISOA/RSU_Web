# -*- coding: utf-8 -*-
"""
limites_db.py — Limites (contours) District / Commune / Fokontany EN BASE.

Pourquoi ce module ?
--------------------
Par defaut, les contours de la carte viennent des CSV OCHA 2018 embarques
(dossier LimitesFokontany/, lu par rapport_core._limites_integrees). Pour QUATRE
districts (AMBOHIDRATRIMO 1101, ANTANANARIVO AVARADRANO 1106, FENERIVE EST 5201,
VAVATENINA 5206), on dispose de limites CORRIGEES (shapefiles Admin2/3/4, geometrie
officielle INSTAT 2024) qui remplacent OCHA. Ces limites corrigees sont rangees
dans TROIS tables reliees au referentiel `zones` par cles etrangeres :

    limite_district(code_district  PK -> district.code_district,   anneaux, source)
    limite_commune (code_commune   PK -> commune.code_commune,     anneaux, source)
    limite_fokontany(code_fokontany PK -> fokontany.code_fokontany, anneaux, source)

`anneaux` = JSON des anneaux du polygone au format du rapport : une liste
d'anneaux, chaque anneau une liste de points [lat, lon] (WGS84). C'est EXACTEMENT
la forme attendue par `const LIMITES` / `LIMITES_COMMUNE` / `LIMITES_DISTRICT`
du gabarit, donc le serveur peut les injecter telles quelles (via
rapport_core.generer_rapport(contours_override=...)).

Source des geometries : dossier `LimitesQuatreDistrict/<code_district>/` contenant
`<code>_adm2.shp` (district), `<code>_adm3.shp` (communes), `<code>_adm4.shp`
(fokontany). Chaque entite porte son PCODE (ADM2_PCODE=4 chiffres,
ADM3_PCODE=6, ADM4_PCODE=8), qui EST le code de `zones`.

⚠️ Module WEB uniquement (pas de copie dans le projet .exe). Depend de `pyshp`
(import shapefile), deja disponible dans l'environnement.

CLI :
    python limites_db.py                 # charge LimitesQuatreDistrict/ dans la base
    python limites_db.py <dossier>       # charge un autre dossier
    python limites_db.py --list          # districts couverts + nb de contours
"""

import json
import os
import sys

import config

# Casse mixte -> toujours entre guillemets en SQL (piege PostgreSQL, cf. CLAUDE.md).
# Ici les colonnes sont en minuscules, pas de souci ; on garde le style ? -> %s
# via db_source pour PostgreSQL au moment de brancher (paramstyle gere par la conn).

# Niveau shapefile -> (table, colonne code, champ PCODE, longueur du code)
_NIVEAUX = (
    ("adm2", "limite_district",  "code_district",  "ADM2_PCODE", 4),
    ("adm3", "limite_commune",   "code_commune",   "ADM3_PCODE", 6),
    ("adm4", "limite_fokontany", "code_fokontany", "ADM4_PCODE", 8),
)

# Quatre districts corriges (sous-dossiers attendus dans LimitesQuatreDistrict/).
DISTRICTS = ("1101", "1106", "5201", "5206")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def creer_tables(conn) -> None:
    """Cree les 3 tables de limites si absentes (FK vers `zones`).

    Les FK ne sont APPLIQUEES qu'en PostgreSQL (SQLite ne verifie les FK que si
    PRAGMA foreign_keys=ON, off par defaut ; cf. CLAUDE.md). L'integrite est de
    toute facon assuree cote Python (on ne charge que des codes presents dans
    `zones`, verifies a l'insertion)."""
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS limite_district (
               code_district BIGINT PRIMARY KEY REFERENCES district(code_district),
               anneaux TEXT NOT NULL,
               source  TEXT
           )""")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS limite_commune (
               code_commune BIGINT PRIMARY KEY REFERENCES commune(code_commune),
               anneaux TEXT NOT NULL,
               source  TEXT
           )""")
    cur.execute(
        """CREATE TABLE IF NOT EXISTS limite_fokontany (
               code_fokontany BIGINT PRIMARY KEY REFERENCES fokontany(code_fokontany),
               anneaux TEXT NOT NULL,
               source  TEXT
           )""")
    conn.commit()


# ---------------------------------------------------------------------------
# Geometrie shapefile -> anneaux [[lat, lon], ...]
# ---------------------------------------------------------------------------
def _anneaux_depuis_shape(shape) -> list:
    """pyshp shape (Polygon/MultiPolygon) -> [[[lat, lon], ...], ...].

    Les points du shapefile sont (lon, lat) (WGS84, verifie via .prj GCS_WGS_1984).
    `shape.parts` donne l'index de debut de chaque anneau ; on decoupe et on
    inverse en [lat, lon] pour coller au format du rapport (const LIMITES)."""
    pts = shape.points
    parts = list(shape.parts) + [len(pts)]
    anneaux = []
    for i in range(len(parts) - 1):
        ring = [[float(lat), float(lon)] for lon, lat in pts[parts[i]:parts[i + 1]]]
        if len(ring) >= 3:
            anneaux.append(ring)
    return anneaux


def _lire_shapefile(chemin, champ_code, longueur):
    """Lit un .shp -> {code(str): anneaux}. Le code vient du champ PCODE (tronque
    a `longueur` par securite). Ignore les entites sans geometrie exploitable."""
    import shapefile  # pyshp
    r = shapefile.Reader(chemin)
    champs = [f[0] for f in r.fields[1:]]
    if champ_code not in champs:
        raise ValueError(f"{os.path.basename(chemin)} : champ {champ_code} absent "
                         f"(champs: {champs})")
    idx = champs.index(champ_code)
    out = {}
    for sr in r.shapeRecords():
        code = str(sr.record[idx]).strip()[:longueur]
        if not code or not code.isdigit():
            continue
        anneaux = _anneaux_depuis_shape(sr.shape)
        if anneaux:
            out[code] = anneaux
    return out


# ---------------------------------------------------------------------------
# Chargement en base
# ---------------------------------------------------------------------------
def _codes_zones(conn, table, colonne) -> set:
    """Ensemble des codes (str) presents dans une table de `zones`."""
    cur = conn.cursor()
    cur.execute(f"SELECT {colonne} FROM {table}")
    return {str(r[0]) for r in cur.fetchall()}


def _upsert(conn, table, colonne, code, anneaux, source) -> None:
    """Insere ou remplace un contour (cle = code, entier pour coller au type des
    tables `zones` en BIGINT et faire jouer la FK en PostgreSQL)."""
    cur = conn.cursor()
    js = json.dumps(anneaux, ensure_ascii=False)
    # SQLite : INSERT OR REPLACE ; PostgreSQL : ON CONFLICT. On teste puis
    # UPDATE/INSERT pour rester portable (peu de lignes, cout negligeable).
    cur.execute(f"SELECT 1 FROM {table} WHERE {colonne}=?", (int(code),))
    if cur.fetchone():
        cur.execute(f"UPDATE {table} SET anneaux=?, source=? WHERE {colonne}=?",
                    (js, source, int(code)))
    else:
        cur.execute(f"INSERT INTO {table} ({colonne}, anneaux, source) VALUES (?,?,?)",
                    (int(code), js, source))


def charger_shapefiles(conn, dossier=None, log=print) -> dict:
    """Lit les shapefiles des 4 districts et remplit les 3 tables (upsert).

    Ne charge QUE les codes presents dans `zones` (integrite FK garantie cote
    Python) ; signale les codes ignores. Renvoie un bilan structure."""
    dossier = dossier or config.LIMITES_QUATRE_DIR
    if not os.path.isdir(dossier):
        raise FileNotFoundError(f"Dossier de limites introuvable : {dossier}")
    creer_tables(conn)

    # Codes valides du referentiel (pour la verification FK cote Python).
    valides = {
        "limite_district":  _codes_zones(conn, "district",  "code_district"),
        "limite_commune":   _codes_zones(conn, "commune",   "code_commune"),
        "limite_fokontany": _codes_zones(conn, "fokontany", "code_fokontany"),
    }

    bilan = {"districts": [], "totaux": {"district": 0, "commune": 0, "fokontany": 0},
             "ignores": []}
    for d in sorted(os.listdir(dossier)):
        sous = os.path.join(dossier, d)
        if not os.path.isdir(sous):
            continue
        detail = {"code": d, "district": 0, "commune": 0, "fokontany": 0}
        for suffixe, table, colonne, champ, longueur in _NIVEAUX:
            shp = os.path.join(sous, f"{d}_{suffixe}.shp")
            if not os.path.isfile(shp):
                log(f"   [{d}] {os.path.basename(shp)} absent, ignore")
                continue
            contours = _lire_shapefile(shp, champ, longueur)
            niveau = table.split("_", 1)[1]  # district/commune/fokontany
            n = 0
            for code, anneaux in contours.items():
                if code not in valides[table]:
                    bilan["ignores"].append((niveau, code))
                    continue
                _upsert(conn, table, colonne, code, anneaux,
                        "LimitesQuatreDistrict (INSTAT 2024)")
                n += 1
            detail[niveau] = n
            bilan["totaux"][niveau] += n
        bilan["districts"].append(detail)
        log(f"   [{d}] district={detail['district']} commune={detail['commune']} "
            f"fokontany={detail['fokontany']}")
    conn.commit()
    if bilan["ignores"]:
        log(f"   ATTENTION : {len(bilan['ignores'])} code(s) hors referentiel ignore(s) : "
            f"{bilan['ignores'][:10]}")
    return bilan


# ---------------------------------------------------------------------------
# Lecture des contours (pour le rapport)
# ---------------------------------------------------------------------------
def _charger_niveau(conn, table, colonne, codes) -> dict:
    """{code(str): anneaux} pour les codes demandes presents dans la table."""
    codes = {str(c) for c in codes if c is not None}
    if not codes:
        return {}
    cur = conn.cursor()
    out = {}
    # Requete groupee (IN) : on convertit en int pour matcher le type BIGINT.
    ints = sorted({int(c) for c in codes if str(c).isdigit()})
    if not ints:
        return {}
    marques = ",".join("?" for _ in ints)
    cur.execute(f"SELECT {colonne}, anneaux FROM {table} "
                f"WHERE {colonne} IN ({marques})", ints)
    for code, js in cur.fetchall():
        try:
            out[str(code)] = json.loads(js)
        except (TypeError, ValueError):
            pass
    return out


def contours_pour(conn, codes_fkt) -> dict:
    """Contours corriges pour un ensemble de fokontany (codes 8 chiffres).

    Deduit les communes (6 chiffres) et districts (4 chiffres) des codes fokontany
    et renvoie un dict pret pour rapport_core.generer_rapport(contours_override=) :
        {"fkt": {code8: anneaux}, "commune": {code6: ...}, "district": {code4: ...}}
    Seuls les codes REELLEMENT presents en base (districts corriges) sont renvoyes ;
    pour les autres, le rapport gardera les contours OCHA."""
    codes_fkt = [str(c) for c in codes_fkt if c is not None and str(c).isdigit()]
    codes_com = {c[:6] for c in codes_fkt if len(c) >= 6}
    codes_dis = {c[:4] for c in codes_fkt if len(c) >= 4}
    return {
        "fkt":      _charger_niveau(conn, "limite_fokontany", "code_fokontany", codes_fkt),
        "commune":  _charger_niveau(conn, "limite_commune",   "code_commune",   codes_com),
        "district": _charger_niveau(conn, "limite_district",  "code_district",  codes_dis),
    }


def districts_couverts(conn) -> set:
    """Ensemble des codes district (str) ayant des limites corrigees en base."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT code_district FROM limite_district")
        return {str(r[0]) for r in cur.fetchall()}
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli(argv) -> int:
    import db_source
    conn = db_source.connect()
    try:
        creer_tables(conn)
        if argv and argv[0] in ("--list", "list"):
            for niveau, table in (("districts", "limite_district"),
                                  ("communes", "limite_commune"),
                                  ("fokontany", "limite_fokontany")):
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"{niveau:10s}: {cur.fetchone()[0]}")
            print("districts couverts:", sorted(districts_couverts(conn)))
            return 0
        dossier = argv[0] if argv else None
        print("Chargement des limites corrigees (LimitesQuatreDistrict) ...")
        bilan = charger_shapefiles(conn, dossier)
        t = bilan["totaux"]
        print(f"OK : {t['district']} district(s), {t['commune']} commune(s), "
              f"{t['fokontany']} fokontany charges.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
