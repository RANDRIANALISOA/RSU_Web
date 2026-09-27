# -*- coding: utf-8 -*-
"""
declarations.py — DÉCLARATIONS des agents (ménages dénombrés / interviewés).

Une table (créée au démarrage par `creer_tables`) :

    declaration_agent(
        code_agent     TEXT NOT NULL REFERENCES agent(login_ae),  -- Code_Agent
        date           TEXT NOT NULL,        -- Date, au format AAAAMMJJ
        type_operation TEXT NOT NULL,        -- 'DEN' (dénombrement) ou 'VAD'
        nombre         INTEGER NOT NULL,     -- Nombre de ménages déclaré ce jour-là
        PRIMARY KEY ("code_agent","date","type_operation"))

C'est ce que l'AGENT DÉCLARE : le nombre de ménages qu'il dit avoir dénombrés
(phase de dénombrement) ou interviewés (VAD) un jour donné. À ne pas confondre
avec ce qui ARRIVE AU SERVEUR (tables du dénombrement) : l'écart entre les deux
est justement ce que le rapport Excel met en évidence (feuille « Écart
déclaration-serveur »).

Ce sont les **Superviseurs Techniques** qui saisissent ces déclarations, en
téléversant un classeur Excel bâti sur le MODÈLE fourni par l'application
(route /declaration) :

    | code_agent | 05/09/2026 | 06/09/2026 | … |   <- ligne 1 : en-têtes (dates)
    | AE001      |     28     |     31     | … |   <- une ligne par agent
    | AE002      |            |     19     | … |

Colonne 1 = le code de l'agent ; colonnes 2 à n = les DATES (une par jour). Une
cellule vide = pas de déclaration ce jour-là (rien n'est écrit en base ; ce n'est
PAS un zéro). Les en-têtes de date sont acceptées en date Excel, JJ/MM/AAAA,
AAAA-MM-JJ ou AAAAMMJJ.

La transcription est un UPSERT (comme `equipes.py` / `maj_db.py`) : elle AJOUTE
les nouvelles déclarations, MET À JOUR celles qui ont changé, et NE SUPPRIME rien.

Note SQLite : les clés étrangères ne sont vérifiées que si `PRAGMA foreign_keys=ON`
(désactivé par défaut) ; l'intégrité (code agent connu, et du périmètre du
superviseur) est de toute façon garantie côté Python à l'import.
"""
import datetime
import io

import admin           # style + _cellstr (réutilisés)
import db_source
import equipes         # _CSS_CHOIX : mêmes cartes de choix que l'espace Traitement

ESC = admin.ESC
_cellstr = admin._cellstr

# Opérations déclarables : clef d'URL -> (code stocké, libellé).
OPERATIONS = {
    "den": ("DEN", "Dénombrement"),
    "vad": ("VAD", "Visite à domicile (VAD)"),
}
_LIB_TYPE = {"DEN": "Dénombrement", "VAD": "Visite à domicile (VAD)"}
_UNITE = {"DEN": "ménages dénombrés", "VAD": "ménages interviewés"}


def libelle(type_operation: str) -> str:
    """'DEN' -> 'Dénombrement' ; 'VAD' -> 'Visite à domicile (VAD)'."""
    return _LIB_TYPE.get((type_operation or "").upper(), type_operation or "")


def unite(type_operation: str) -> str:
    """Ce que COMPTE le nombre déclaré, pour les libellés de l'interface."""
    return _UNITE.get((type_operation or "").upper(), "ménages")


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------
_DDL = (
    'CREATE TABLE IF NOT EXISTS "declaration_agent" ('
    '"code_agent" TEXT NOT NULL REFERENCES "agent" ("login_ae"), '
    '"date" TEXT NOT NULL, '
    '"type_operation" TEXT NOT NULL, '
    '"nombre" INTEGER NOT NULL, '
    'PRIMARY KEY ("code_agent","date","type_operation"))')


_DDL_INDEX = ('CREATE INDEX IF NOT EXISTS "idx_declaration_agent_code" '
              'ON "declaration_agent" ("code_agent")')


def creer_tables(conn) -> None:
    """Crée `declaration_agent` (+ son index) si absente. Idempotent.

    À appeler APRÈS `equipes.creer_tables` : `code_agent` est une CLÉ ÉTRANGÈRE
    vers `agent(login_ae)`, la table principale des agents. L'index sert la
    jointure `declaration_agent -> agent -> chef_equipe`, seul chemin d'accès au
    nom de l'agent et à son chef d'équipe (jamais recopiés ici)."""
    cur = conn.cursor()
    cur.execute(_DDL)
    cur.execute(_DDL_INDEX)
    conn.commit()


# ---------------------------------------------------------------------------
# Dates : normalisation vers AAAAMMJJ (le format des dates du dénombrement,
# cf. rapport_core._date_j) pour que déclaration et serveur se comparent.
# ---------------------------------------------------------------------------
def _norm_date(v) -> str:
    """En-tête de colonne -> 'AAAAMMJJ', ou '' si ce n'est pas une date.

    Accepte : date/datetime Excel, 'JJ/MM/AAAA', 'JJ-MM-AAAA', 'AAAA-MM-JJ',
    'AAAAMMJJ' et 'AAAA-MM-JJThh:mm:ss'."""
    if v is None:
        return ""
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y%m%d")
    if isinstance(v, datetime.date):
        return v.strftime("%Y%m%d")
    s = str(v).strip()
    if not s:
        return ""
    s = s.split("T", 1)[0].split(" ", 1)[0]
    chiffres = s.replace("/", "").replace("-", "").replace(".", "")
    if not chiffres.isdigit():
        return ""
    if "/" in s or "-" in s or "." in s:
        bouts = s.replace("-", "/").replace(".", "/").split("/")
        if len(bouts) != 3:
            return ""
        a, b, c = (x.strip() for x in bouts)
        if len(a) == 4:                       # AAAA/MM/JJ
            annee, mois, jour = a, b, c
        else:                                 # JJ/MM/AAAA
            jour, mois, annee = a, b, c
        try:
            d = datetime.date(int(annee), int(mois), int(jour))
        except ValueError:
            return ""
        return d.strftime("%Y%m%d")
    if len(chiffres) == 8:                    # AAAAMMJJ
        try:
            datetime.datetime.strptime(chiffres, "%Y%m%d")
        except ValueError:
            return ""
        return chiffres
    return ""


def jj_mm_aaaa(d: str) -> str:
    """'AAAAMMJJ' -> 'JJ/MM/AAAA' (affichage). Inchangé si format inattendu."""
    s = (d or "").strip()
    return f"{s[6:8]}/{s[4:6]}/{s[0:4]}" if len(s) == 8 and s.isdigit() else s


# ---------------------------------------------------------------------------
# Périmètre : quels codes agent un superviseur a-t-il le droit de déclarer ?
# ---------------------------------------------------------------------------
def _sous_requete_perimetre(conn, districts, communes):
    """(clause SQL sur den_menage, paramètres) bornant le périmètre, ou (None, ())
    si le périmètre est « toute la base »."""
    ph = db_source._placeholder(conn)
    if communes is not None:
        codes = tuple(int(c) for c in sorted(communes))
        if not codes:
            return "1 = 0", ()            # périmètre VIDE : aucune commune affectée
        marks = ",".join([ph] * len(codes))
        return f'"commune" IN ({marks})', codes
    if districts:
        codes = tuple(int(d) for d in sorted(districts))
        marks = ",".join([ph] * len(codes))
        return f'"district" IN ({marks})', codes
    return None, ()


def _sous_requete_perimetre_vad(conn, districts, communes):
    """Le pendant VAD de `_sous_requete_perimetre` : la clause porte sur
    `vad_menage`, dont le district est `CQ7` et la commune `CQ8`."""
    ph = db_source._placeholder(conn)
    if communes is not None:
        codes = tuple(int(c) for c in sorted(communes))
        if not codes:
            return "1 = 0", ()
        marks = ",".join([ph] * len(codes))
        return f'"CQ8" IN ({marks})', codes
    if districts:
        codes = tuple(int(d) for d in sorted(districts))
        marks = ",".join([ph] * len(codes))
        return f'"CQ7" IN ({marks})', codes
    return None, ()


def _codes_den(conn, districts, communes) -> set:
    cur = conn.cursor()
    clause, params = _sous_requete_perimetre(conn, districts, communes)
    sql = ('SELECT DISTINCT "responsible" FROM "interview__diagnostics" '
           'WHERE "responsible" IS NOT NULL')
    if clause is not None:
        sql += (' AND "interview__key" IN (SELECT "interview__key" '
                f'FROM "den_menage" WHERE {clause})')
    try:
        cur.execute(sql, params)
    except Exception:
        return set()                         # base neuve (tables absentes)
    return {str(r[0]).strip() for r in cur.fetchall() if str(r[0] or "").strip()}


def _codes_vad(conn, districts, communes) -> set:
    cur = conn.cursor()
    clause, params = _sous_requete_perimetre_vad(conn, districts, communes)
    sql = ('SELECT DISTINCT "responsible" FROM "vad_diagnostics" '
           'WHERE "responsible" IS NOT NULL')
    if clause is not None:
        sql += (' AND "interview__key" IN (SELECT "interview__key" '
                f'FROM "vad_menage" WHERE {clause})')
    try:
        cur.execute(sql, params)
    except Exception:
        return set()                         # VAD pas encore transcrite
    return {str(r[0]).strip() for r in cur.fetchall() if str(r[0] or "").strip()}


def codes_perimetre(conn, districts=None, communes=None,
                    type_operation=None) -> set:
    """Codes agent VUS DANS LES DONNÉES du périmètre (ce qui est arrivé au
    serveur). `districts`/`communes` = None ou vide -> toute la base.

    `type_operation` :
      - 'DEN'  : les agents du DÉNOMBREMENT ;
      - 'VAD'  : ceux du dénombrement ET ceux de la visite à domicile. L'union,
        et non les seuls agents VAD : un agent peut avoir à déclarer une VAD
        dont AUCUNE donnée n'est encore arrivée (c'est justement l'écart le plus
        parlant), et certains agents n'apparaissent QUE dans la VAD ;
      - None   : l'union des deux phases (page de choix, simple bornage).
    """
    top = (type_operation or "").upper()
    if top == "DEN":
        return _codes_den(conn, districts, communes)
    return _codes_den(conn, districts, communes) | _codes_vad(conn, districts,
                                                              communes)


def dates_perimetre(conn, districts=None, communes=None,
                    type_operation=None) -> list:
    """Dates (AAAAMMJJ, triées) déjà observées dans le périmètre, pour
    pré-remplir les colonnes du modèle Excel.

    Celles de la PHASE demandée : le dénombrement (`den_menage.date`) ou la
    visite à domicile (`vad_menage.CQ3`, à défaut `start_ec`). Proposer les
    dates du dénombrement pour déclarer une VAD menée deux mois plus tard
    ferait remplir les mauvaises colonnes."""
    cur = conn.cursor()
    if (type_operation or "").upper() == "VAD":
        clause, params = _sous_requete_perimetre_vad(conn, districts, communes)
        sql = ('SELECT DISTINCT "CQ3", "start_ec" FROM "vad_menage" '
               'WHERE 1 = 1')
        if clause is not None:
            sql += f" AND {clause}"
    else:
        clause, params = _sous_requete_perimetre(conn, districts, communes)
        sql = 'SELECT DISTINCT "date" FROM "den_menage" WHERE "date" IS NOT NULL'
        if clause is not None:
            sql += f' AND {clause}'
    try:
        cur.execute(sql, params)
    except Exception:
        return []
    out = set()
    for ligne in cur.fetchall():
        for v in ligne:                      # VAD : CQ3, sinon start_ec
            d = _norm_date(v)
            if d:
                out.add(d)
                break
    return sorted(out)


# ---------------------------------------------------------------------------
# Lecture / écriture
# ---------------------------------------------------------------------------
def compter(conn, type_operation=None, codes=None) -> dict:
    """{'lignes': n, 'agents': a, 'total': somme des nombres} pour l'opération
    (toutes opérations si `type_operation` est None), bornée à `codes` si fourni."""
    creer_tables(conn)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    where, params = [], []
    if type_operation:
        where.append(f'"type_operation" = {ph}')
        params.append(type_operation.upper())
    if codes is not None:
        codes = sorted(codes)
        if not codes:
            return {"lignes": 0, "agents": 0, "total": 0}
        where.append(f'"code_agent" IN ({",".join([ph] * len(codes))})')
        params.extend(codes)
    sql = ('SELECT COUNT(*), COUNT(DISTINCT "code_agent"), '
           'COALESCE(SUM("nombre"),0) FROM "declaration_agent"')
    if where:
        sql += " WHERE " + " AND ".join(where)
    cur.execute(sql, tuple(params))
    n, a, t = cur.fetchone()
    return {"lignes": n or 0, "agents": a or 0, "total": int(t or 0)}


def par_agent_date(conn, type_operation, codes=None) -> dict:
    """{(code_agent, date AAAAMMJJ): nombre déclaré} pour une opération.
    `codes` (itérable) borne la lecture aux agents demandés."""
    creer_tables(conn)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    sql = ('SELECT "code_agent","date","nombre" FROM "declaration_agent" '
           f'WHERE "type_operation" = {ph}')
    params = [(type_operation or "").upper()]
    if codes is not None:
        codes = sorted(codes)
        if not codes:
            return {}
        sql += f' AND "code_agent" IN ({",".join([ph] * len(codes))})'
        params.extend(codes)
    cur.execute(sql, tuple(params))
    return {(str(c), str(d)): int(n or 0) for c, d, n in cur.fetchall()}


def par_agent_date_perimetre(conn, type_operation, codes_serveur,
                             ac=None) -> dict:
    """Déclarations {(code_agent, date AAAAMMJJ): nombre} BORNÉES À UN PÉRIMÈTRE.

    `codes_serveur` : les codes agent dont des données sont ARRIVÉES AU SERVEUR
    dans le périmètre (un district, ou les communes affectées). On y ajoute les
    agents qui ont déclaré et qui dépendent d'un chef d'équipe du périmètre :
    un agent peut avoir déclaré alors que RIEN n'est encore arrivé — c'est
    justement l'écart le plus parlant, il ne doit pas disparaître du tableau.

    `ac` = equipes.agents_et_chefs(conn) ; lu ici s'il n'est pas fourni.
    La table `declaration_agent` n'a PAS de colonne géographique : c'est ce
    rattachement agent -> chef d'équipe qui borne la lecture au périmètre."""
    ac = ac if ac is not None else equipes.agents_et_chefs(conn)
    codes_serveur = {str(c).strip() for c in (codes_serveur or ())
                     if str(c).strip()}
    ce_perimetre = {ac.get(c, {}).get("chef_login") for c in codes_serveur}
    ce_perimetre.discard("")
    ce_perimetre.discard(None)
    return {
        (code, d): n
        for (code, d), n in par_agent_date(conn, type_operation).items()
        if code in codes_serveur
        or ac.get(code, {}).get("chef_login") in ce_perimetre
    }


def recap_agents(conn, type_operation, codes) -> list:
    """Récapitulatif par agent, PAR JOINTURE sur la table principale `agent`.

    Renvoie [{code, nom, chef, jours, total}] pour les `codes` demandés (tous les
    agents du périmètre, y compris ceux qui n'ont encore RIEN déclaré). Le nom et
    le chef d'équipe viennent de `agent` / `chef_equipe` — ils ne sont stockés ni
    dans `declaration_agent` ni dans le classeur Excel : une seule source de
    vérité, mise à jour par l'Expert Traitement (`equipes.transcrire`).

    `nom` vaut "" quand le nom n'a pas encore été renseigné (la synchronisation
    `equipes.synchroniser_agents` crée alors l'agent avec nom = code)."""
    creer_tables(conn)
    codes = sorted(codes or [])
    if not codes:
        return []
    ph = db_source._placeholder(conn)
    top = (type_operation or "").upper()
    cur = conn.cursor()
    out = []
    for i in range(0, len(codes), 400):          # paquets : limite de paramètres
        paquet = codes[i:i + 400]
        marks = ",".join([ph] * len(paquet))
        cur.execute(
            'SELECT a."login_ae", a."nom_prenom_ae", a."login_ce", '
            'c."nom_prenom_ce", COUNT(d."date"), COALESCE(SUM(d."nombre"),0) '
            'FROM "agent" a '
            'LEFT JOIN "chef_equipe" c ON a."login_ce" = c."login_ce" '
            'LEFT JOIN "declaration_agent" d '
            f'  ON d."code_agent" = a."login_ae" AND d."type_operation" = {ph} '
            f'WHERE a."login_ae" IN ({marks}) '
            'GROUP BY a."login_ae", a."nom_prenom_ae", a."login_ce", '
            'c."nom_prenom_ce"',
            tuple([top] + paquet))
        for code, nom, lce, nce, jours, total in cur.fetchall():
            code = str(code).strip()
            nom = ("" if nom is None else str(nom)).strip()
            out.append({
                "code": code,
                "nom": "" if nom == code else nom,   # nom == code => non renseigné
                "chef": (("" if nce is None else str(nce)).strip()
                         or ("" if lce is None else str(lce)).strip()),
                "jours": int(jours or 0),
                "total": int(total or 0),
            })
    out.sort(key=lambda r: ((r["chef"] or "\uffff"), r["nom"] or r["code"]))
    return out


def _agents_connus(conn) -> set:
    cur = conn.cursor()
    cur.execute('SELECT "login_ae" FROM "agent"')
    return {str(r[0]).strip() for r in cur.fetchall() if str(r[0] or "").strip()}


def _upsert(conn, code_agent, date, type_operation, nombre):
    """Renvoie 'ajoute' | 'modifie' | 'inchange'."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT "nombre" FROM "declaration_agent" '
                f'WHERE "code_agent"={ph} AND "date"={ph} AND "type_operation"={ph}',
                (code_agent, date, type_operation))
    row = cur.fetchone()
    if row is None:
        cur.execute('INSERT INTO "declaration_agent" '
                    '("code_agent","date","type_operation","nombre") '
                    f'VALUES ({ph},{ph},{ph},{ph})',
                    (code_agent, date, type_operation, nombre))
        return "ajoute"
    if int(row[0] or 0) != nombre:
        cur.execute(f'UPDATE "declaration_agent" SET "nombre"={ph} '
                    f'WHERE "code_agent"={ph} AND "date"={ph} '
                    f'AND "type_operation"={ph}',
                    (nombre, code_agent, date, type_operation))
        return "modifie"
    return "inchange"


# ---------------------------------------------------------------------------
# Lecture du classeur Excel : format LARGE (agent en ligne, dates en colonnes)
# ---------------------------------------------------------------------------
def _lire_xlsx(chemin_xlsx):
    """Lit la 1re feuille du modèle « déclaration ».

    Renvoie (cellules, dates, erreurs_entete) :
      - `cellules` = [(ligne_excel, code_agent, date AAAAMMJJ, valeur_brute)] pour
        toute cellule NON VIDE des colonnes 2..n ;
      - `dates`    = les dates des colonnes reconnues (ordre du fichier) ;
      - `erreurs_entete` = liste de messages (aucune date lisible, etc.).
    Lève ValueError si le fichier est vide ou illisible."""
    import openpyxl
    wb = openpyxl.load_workbook(chemin_xlsx, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    entetes = next(it, None)
    if not entetes:
        wb.close()
        raise ValueError("Le classeur est vide : aucune ligne d'en-tête.")
    # Colonnes 2..n : une date par colonne (la colonne 1 porte le code agent).
    col_date, refusees = {}, []
    for i, h in enumerate(entetes):
        if i == 0 or h is None or str(h).strip() == "":
            continue
        d = _norm_date(h)
        if d:
            col_date[i] = d
        else:
            refusees.append(f"colonne {i + 1} (« {_cellstr(h)} »)")
    erreurs = []
    if refusees:
        erreurs.append("En-têtes ignorées, ce ne sont pas des dates : "
                       + ", ".join(refusees) + ".")
    if not col_date:
        wb.close()
        raise ValueError(
            "Aucune colonne de DATE reconnue (ligne 1, à partir de la colonne 2). "
            "Attendu : une date par colonne (ex. 05/09/2026), comme dans le modèle.")
    cellules = []
    for n, r in enumerate(it, start=2):
        if r is None or all(v is None for v in r):
            continue
        code = _cellstr(r[0]) if len(r) > 0 else ""
        for i, d in col_date.items():
            brut = r[i] if i < len(r) else None
            if brut is None or str(brut).strip() == "":
                continue            # cellule vide = pas de déclaration ce jour-là
            cellules.append((n, code, d, brut))
    wb.close()
    dates = [col_date[i] for i in sorted(col_date)]
    return cellules, dates, erreurs


def _entier(v):
    """Valeur de cellule -> entier >= 0, ou None si ce n'est pas un nombre valide."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, float):
        return int(v) if v.is_integer() and v >= 0 else None
    s = str(v).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() and f >= 0 else None


def transcrire(conn, chemin_xlsx, type_operation, codes_autorises=None):
    """Transcrit un classeur de déclarations vers `declaration_agent` (upsert).

    `type_operation` ∈ {'DEN','VAD'} ; `codes_autorises` (set) borne l'import aux
    agents du périmètre du superviseur — un code agent inconnu de ce périmètre ET
    déjà vu ailleurs dans les données est refusé (ligne ignorée, signalée).

    Renvoie {"bilan": {ajoutes,modifies,inchanges}, "dates": [...],
             "agents": n, "total": somme des nombres écrits/confirmés,
             "erreurs": [(ligne, message), ...]}.
    Lève ValueError si le classeur n'est pas exploitable (rien n'est écrit)."""
    creer_tables(conn)
    top = (type_operation or "").upper()
    if top not in ("DEN", "VAD"):
        raise ValueError(f"Type d'opération inconnu : {type_operation!r}.")
    cellules, dates, err_entete = _lire_xlsx(chemin_xlsx)

    connus = _agents_connus(conn)
    res = {"bilan": {"ajoutes": 0, "modifies": 0, "inchanges": 0},
           "dates": dates, "agents": 0, "total": 0,
           "erreurs": [(1, m) for m in err_entete]}
    vus_agents = set()
    signales = set()          # un même code agent n'est signalé qu'une fois
    for ligne, code, date, brut in cellules:
        code = (code or "").strip()
        if not code:
            if ("vide", ligne) not in signales:
                signales.add(("vide", ligne))
                res["erreurs"].append((ligne, "code agent vide (colonne 1)"))
            continue
        if code not in connus:
            if code not in signales:
                signales.add(code)
                res["erreurs"].append(
                    (ligne, f"code agent inconnu de la base : {code}"))
            continue
        if codes_autorises is not None and code not in codes_autorises:
            if code not in signales:
                signales.add(code)
                res["erreurs"].append(
                    (ligne, f"agent hors de votre périmètre : {code}"))
            continue
        nombre = _entier(brut)
        if nombre is None:
            res["erreurs"].append(
                (ligne, f"{code} / {jj_mm_aaaa(date)} : « {_cellstr(brut)} » "
                        "n'est pas un nombre entier positif"))
            continue
        res["bilan"][_upsert(conn, code, date, top, nombre) + "s"] += 1
        res["total"] += nombre
        vus_agents.add(code)
    res["agents"] = len(vus_agents)
    conn.commit()
    return res


# ---------------------------------------------------------------------------
# Modèle Excel (canevas à remplir par le Superviseur Technique)
# ---------------------------------------------------------------------------
def modele_xlsx(conn, type_operation, districts=None, communes=None,
                nb_jours=14) -> bytes:
    """Classeur modèle à DEUX feuilles : « declaration » (la grille à remplir —
    colonne 1 = code agent, colonnes 2..n = dates) et « mode d'emploi ».

    Le classeur ne porte AUCUN renseignement sur les agents (nom, chef d'équipe) :
    ils vivent dans la table `agent` (et `chef_equipe`), à laquelle
    `declaration_agent` est reliée par le CODE AGENT (clé étrangère
    `code_agent` -> `agent(login_ae)`). Les dupliquer dans le classeur ouvrirait
    une seconde source de vérité, qui divergerait à la première correction de nom.

    Les codes agent et les dates sont PRÉ-REMPLIS depuis les données déjà
    arrivées au serveur pour le périmètre ; à défaut de dates observées (cas du
    VAD, pas encore collecté), on propose `nb_jours` jours à partir d'aujourd'hui."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    creer_tables(conn)
    top = (type_operation or "").upper()
    codes = sorted(codes_perimetre(conn, districts, communes, top))
    dates = dates_perimetre(conn, districts, communes, top)
    if not dates:
        aujourdhui = datetime.date.today()
        dates = [(aujourdhui + datetime.timedelta(days=i)).strftime("%Y%m%d")
                 for i in range(nb_jours)]

    entete_f = Font(bold=True, color="FF1F2937")
    entete_fill = PatternFill("solid", fgColor="FFDBEAFE")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "declaration"
    ws.append(["code_agent"] + [jj_mm_aaaa(d) for d in dates])
    for j in range(1, len(dates) + 2):
        c = ws.cell(row=1, column=j)
        c.font = entete_f
        c.fill = entete_fill
        c.alignment = Alignment(horizontal=("left" if j == 1 else "center"))
    for code in codes:
        ws.append([code])
    ws.column_dimensions["A"].width = 22
    for j in range(2, len(dates) + 2):
        ws.column_dimensions[get_column_letter(j)].width = 12
    ws.freeze_panes = "B2"

    # Mode d'emploi (2e et DERNIÈRE feuille) : la règle de lecture, en clair.
    notice = wb.create_sheet("mode d'emploi")
    for txt in (
            f"Déclaration des agents — {libelle(top)}",
            "",
            "Feuille « declaration » (la SEULE lue par l'application) :",
            "  • Colonne 1 : le CODE de l'agent. C'est la SEULE identification "
            "demandée :",
            "    le nom de l'agent et son chef d'équipe sont déjà dans la base "
            "(table « agent »),",
            "    à laquelle la déclaration est reliée par ce code.",
            "  • Colonnes 2 à n : une DATE par colonne (ligne 1).",
            f"  • Chaque cellule : le NOMBRE de {unite(top)} DÉCLARÉ par l'agent "
            "ce jour-là.",
            "  • Cellule VIDE = aucune déclaration ce jour-là (ce n'est PAS un "
            "zéro : rien n'est écrit en base).",
            "",
            "Les codes déjà inscrits en colonne 1 sont CEUX DE VOS AGENTS : ne les "
            "modifiez pas.",
            "Un code inconnu de la base, ou hors de votre périmètre, est refusé "
            "(la ligne est signalée).",
            "La correspondance code → nom de l'agent et chef d'équipe est "
            "rappelée sur la page",
            "de téléversement de l'application, et reprise automatiquement dans "
            "les rapports.",
            "",
            "Vous pouvez ajouter des colonnes de dates ou en retirer.",
            "La transcription AJOUTE les nouvelles déclarations, MET À JOUR celles "
            "qui ont changé, et NE SUPPRIME rien."):
        notice.append([txt])
    notice.column_dimensions["A"].width = 100
    notice["A1"].font = Font(bold=True, size=13)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Pages (charte visuelle d'admin.py, comme equipes.py)
# ---------------------------------------------------------------------------
def _entete(titre="Déclarations des agents") -> str:
    return ('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{ESC(titre)} — RSU</title><style>{admin._STYLE}</style></head>'
            '<body><div class="bar"><b>📝 Déclarations des agents</b>'
            '<a href="/suptech">Mon espace</a>'
            '<a href="/declaration">Déclarations</a>'
            '<span class="sp"></span></div><div class="wrap">')


def page_choix(district_txt, compteurs=None) -> str:
    """Choix de l'opération déclarée : Dénombrement ou VAD."""
    compteurs = compteurs or {}

    def _resume(cle):
        c = compteurs.get(cle) or {}
        if not c.get("lignes"):
            return "Aucune déclaration saisie pour l’instant."
        return (f'Déjà en base : <b>{c["lignes"]}</b> déclaration(s) pour '
                f'<b>{c["agents"]}</b> agent(s) — total <b>{c["total"]}</b> ménages.')

    h = [_entete(), equipes._CSS_CHOIX,
         '<h1>Déclaration du nombre de ménages dénombrés / interviewés par les '
         'agents</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>. '
         'Choisissez la phase concernée, puis téléversez le classeur Excel des '
         'déclarations (modèle fourni).</div>',
         '<div class="choix">',
         '<a class="ca" href="/declaration/den">'
         '<div class="ic">🏠</div><div class="t">Dénombrement</div>'
         '<div class="d">Nombre de ménages que chaque agent déclare avoir '
         '<b>dénombrés</b>, par jour.<br>'
         f'{_resume("DEN")}</div><div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/declaration/vad">'
         '<div class="ic">🗣️</div><div class="t">Visite à domicile (VAD)</div>'
         '<div class="d">Nombre de ménages que chaque agent déclare avoir '
         '<b>interviewés</b> pendant la VAD, par jour.<br>'
         f'{_resume("VAD")}</div><div class="go">Ouvrir →</div></a>',
         '</div>', '</div></body></html>']
    return "".join(h)


def _table_bilan(res) -> str:
    b = res["bilan"]
    return ('<table><tr><th>Déclarations</th><th>Ajoutées</th><th>Mises à jour</th>'
            '<th>Inchangées</th><th>Agents</th><th>Total déclaré</th></tr>'
            f'<tr><td>{len(res.get("dates") or [])} date(s) lue(s)</td>'
            f'<td>+{b["ajoutes"]}</td><td>~{b["modifies"]}</td>'
            f'<td>={b["inchanges"]}</td><td>{res.get("agents", 0)}</td>'
            f'<td>{res.get("total", 0)}</td></tr></table>')


def page_declaration(conn, cle_op, district_txt, codes_perim=None,
                     resultat=None, message=None, erreur=None) -> str:
    """Page d'une opération : rappel du format, modèle, téléversement, bilan."""
    top, lib = OPERATIONS[cle_op]
    c = compter(conn, top, codes=codes_perim)
    h = [_entete(lib),
         '<p style="margin:0 0 6px"><a href="/declaration">← Choix de la '
         'phase</a></p>',
         f'<h1>Déclarations des agents — {ESC(lib)}</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>. '
         f'Actuellement en base pour vos agents : <b>{c["lignes"]}</b> '
         f'déclaration(s), <b>{c["agents"]}</b> agent(s), '
         f'total <b>{c["total"]}</b> {ESC(unite(top))}.</div>']
    if message:
        h.append(f'<div class="msg">{ESC(message)}</div>')
    if erreur:
        h.append(f'<div class="err">{erreur}</div>')       # HTML autorisé (listes)

    if resultat:
        h.append('<h2>Bilan de la transcription</h2>')
        h.append(_table_bilan(resultat))
        if resultat.get("erreurs"):
            items = "".join(f'<li>ligne {ln} : {ESC(m)}</li>'
                            for ln, m in resultat["erreurs"])
            h.append('<div class="err"><b>Cellules ignorées :</b>'
                     f'<ul>{items}</ul></div>')
        h.append(f'<p><a href="/declaration/{cle_op}">↻ Nouvelle '
                 'transcription</a></p>')

    h.append('<h2>Téléverser le classeur des déclarations</h2>')
    h.append(
        f'<form method="post" action="/declaration/{cle_op}" '
        'enctype="multipart/form-data" class="grid-form">'
        '<div><label>Chemin du classeur Excel des déclarations '
        f'(<b>{ESC(lib)}</b>) — colonne 1 : code de l’agent ; colonnes 2 à n : '
        'les dates</label>'
        '<input type="file" name="fichier" accept=".xlsx" required></div>'
        '<div style="align-self:end"><button>Transcrire vers la base de '
        'données</button></div></form>')
    # Correspondance code -> agent, LUE PAR JOINTURE sur la table principale
    # `agent` (et `chef_equipe`) : elle remplace l'ancienne feuille « agents » du
    # classeur, qui dupliquait ces renseignements. Repliée par défaut.
    recap = recap_agents(conn, top, codes_perim or [])
    if recap:
        n_dec = sum(1 for r in recap if r["jours"])
        lignes = "".join(
            '<tr><td>{c}</td><td>{n}</td><td>{ce}</td><td>{j}</td>'
            '<td>{t}</td></tr>'.format(
                c=ESC(r["code"]),
                n=(ESC(r["nom"]) if r["nom"]
                   else '<i style="color:#94a3b8">nom non renseigné</i>'),
                ce=(ESC(r["chef"]) if r["chef"]
                    else '<i style="color:#94a3b8">non affecté</i>'),
                j=(r["jours"] or "—"), t=(r["total"] or "—"))
            for r in recap)
        h.append(
            '<details style="margin-top:14px"><summary style="cursor:pointer;'
            'font-weight:700">Vos agents '
            f'({len(recap)}) — {n_dec} avec au moins une déclaration</summary>'
            '<div class="note" style="margin-top:8px">Le <b>code</b> est la seule '
            'chose à saisir dans le classeur : le nom et le chef d’équipe sont '
            'lus dans la <b>base des agents</b> (remplie par l’Expert Traitement) '
            'à laquelle la déclaration est reliée par ce code.</div>'
            '<table><tr><th>Code de l’agent</th><th>Agent</th>'
            '<th>Chef d’équipe</th><th>Jours déclarés</th>'
            f'<th>Total déclaré</th></tr>{lignes}</table></details>')

    h.append(
        '<div class="note"><b>Format attendu</b> (celui du modèle) : en '
        '<b>ligne 1</b>, la colonne 1 porte l’intitulé du code agent et les '
        '<b>colonnes 2 à n</b> portent les <b>dates</b> (05/09/2026, 2026-09-05 '
        'ou une vraie date Excel). Ensuite, <b>une ligne par agent</b> : son '
        f'<b>code</b> en colonne 1, puis le nombre de {ESC(unite(top))} '
        '<b>déclaré</b> pour chaque date. Une cellule <b>vide</b> = pas de '
        'déclaration ce jour-là (ce n’est pas un zéro).<br>'
        'La transcription <b>ajoute</b> les nouvelles déclarations, '
        '<b>met à jour</b> celles qui ont changé et <b>ne supprime rien</b>. '
        'Seuls les agents de <b>votre périmètre</b> sont acceptés.<br>'
        'Le classeur ne demande <b>que le code</b> de l’agent : son nom et son '
        'chef d’équipe sont déjà en base (table des agents), reliés à la '
        'déclaration par ce code.<br>'
        f'Modèle pré-rempli avec les codes de vos agents : '
        f'<a href="/declaration/modele/{cle_op}.xlsx">⬇ Télécharger le modèle '
        f'{ESC(lib)}</a>.</div>')
    h.append('</div></body></html>')
    return "".join(h)
