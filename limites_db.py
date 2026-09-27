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


# ---------------------------------------------------------------------------
# Contours pour une CARTE (district + communes), allegees
# ---------------------------------------------------------------------------
# Tolerance de simplification, en degres. 0.0002 deg ~ 22 m a Madagascar : c'est
# l'ecart MAXIMUM autorise entre le trace d'origine et le trace allege (garantie
# de Douglas-Peucker), invisible tant qu'on ne zoome pas a la maison pres. Mesure
# sur le district + ses communes : 926 Ko -> 79 Ko (1106), 2 306 Ko -> 187 Ko
# (5201, dont la cote est tres decoupee). A 0.0001 (~11 m), 5201 pesait encore
# 767 Ko ; a 0.0005 (~56 m), le trace commence a couper les meandres.
TOLERANCE_CARTE = 0.0002


def _douglas_peucker(points, tol):
    """Simplification de polyligne (Douglas-Peucker), iterative (pas de recursion
    : un anneau de fokontany peut compter des dizaines de milliers de points)."""
    n = len(points)
    if n < 3:
        return list(points)
    garder = [False] * n
    garder[0] = garder[n - 1] = True
    pile = [(0, n - 1)]
    while pile:
        i, j = pile.pop()
        if j <= i + 1:
            continue
        ax, ay = points[i]
        bx, by = points[j]
        dx, dy = bx - ax, by - ay
        norme = (dx * dx + dy * dy) ** 0.5
        pire, imax = -1.0, i
        for k in range(i + 1, j):
            px, py = points[k]
            if norme == 0:                       # extremites confondues
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:                                # distance point -> segment
                d = abs(dy * px - dx * py + bx * ay - by * ax) / norme
            if d > pire:
                pire, imax = d, k
        if pire > tol:
            garder[imax] = True
            pile.append((i, imax))
            pile.append((imax, j))
    return [points[k] for k in range(n) if garder[k]]


def _alleger(anneaux, tol):
    """Anneaux simplifies ; un anneau reduit a moins de 4 points est ecarte (il
    ne dessinerait plus une surface)."""
    out = []
    for anneau in anneaux or ():
        simple = _douglas_peucker(anneau, tol)
        if len(simple) >= 4:
            out.append(simple)
    return out


def contours_zones(conn, districts=None, communes=None, commune=None,
                   fokontany=None, tolerance=TOLERANCE_CARTE) -> dict:
    """Contours d'une CARTE, au niveau affiche :

        {"niveau": "district"|"commune"|"fokontany",
         "principal": {code: anneaux},    # trace ROUGE = le niveau courant
         "sous":      {code: anneaux}}    # traces BLEUS = ses enfants

    Meme regle que la carte du denombrement. `districts`/`communes` bornent au
    perimetre du role ; `commune`/`fokontany` sont la descente demandee.
    Renvoie des contours vides si le perimetre n'est pas borne (`districts` None)
    ou si les limites du district ne sont pas en base (seuls quatre districts en
    ont, cf. l'en-tete de ce module)."""
    def lire(table, colonne, codes):
        return _charger_niveau(conn, table, colonne, codes)

    def alleger(d):
        return {k: _alleger(v, tolerance) for k, v in d.items()}

    if fokontany:
        return {"niveau": "fokontany",
                "principal": alleger(lire("limite_fokontany", "code_fokontany",
                                          [str(fokontany)])),
                "sous": {}}
    cur = conn.cursor()
    if commune:
        cur.execute('SELECT code_fokontany FROM "fokontany" WHERE code_commune = ?',
                    (int(commune),))
        fkts = [str(r[0]) for r in cur.fetchall()]
        return {"niveau": "commune",
                "principal": alleger(lire("limite_commune", "code_commune",
                                          [str(commune)])),
                "sous": alleger(lire("limite_fokontany", "code_fokontany", fkts))}
    if not districts:
        return {"niveau": "district", "principal": {}, "sous": {}}
    dcodes = sorted(str(d) for d in districts)
    if communes:
        ccodes = sorted(str(c) for c in communes)
    else:
        # Toutes les communes des districts demandes (le referentiel porte la
        # relation ; le code commune commence par le code district).
        ccodes = []
        for d in dcodes:
            cur.execute('SELECT code_commune FROM "commune" WHERE code_district = ?',
                        (int(d),))
            ccodes += [str(r[0]) for r in cur.fetchall()]
    return {"niveau": "district",
            "principal": alleger(lire("limite_district", "code_district", dcodes)),
            "sous": alleger(lire("limite_commune", "code_commune", ccodes))}


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
