# -*- coding: utf-8 -*-
"""
equipes.py — Base des Chefs d'Équipe (CE) et des Agents (AE).

Deux tables (créées au démarrage par `creer_tables`) :

    chef_equipe(
        login_ce       TEXT PRIMARY KEY,     -- identifiant du chef d'équipe
        nom_prenom_ce  TEXT NOT NULL)        -- nom et prénom du CE

    agent(
        login_ae       TEXT PRIMARY KEY,     -- identifiant de l'agent enquêteur
        nom_prenom_ae  TEXT NOT NULL,        -- nom et prénom de l'AE
        login_ce       TEXT REFERENCES chef_equipe(login_ce))   -- CE de rattachement

L'Expert « Traitement » remplit ces tables en TÉLÉVERSANT deux fichiers Excel (la
liste des CE et la liste des AE). La transcription est un UPSERT (comme maj_db) :
elle AJOUTE les nouveaux, MET À JOUR les modifiés, et NE SUPPRIME rien.

Note SQLite : les clés étrangères ne sont vérifiées que si `PRAGMA foreign_keys=ON`
(désactivé par défaut) ; l'intégrité (chaque agent rattaché à un CE existant) est de
toute façon garantie côté Python à l'import.

Colonnes Excel attendues (en-têtes, insensible à la casse ; alias tolérés) :
    CE     : login_ce, nom_prenom_ce   (alias nom : nom_prenom, « nom et prenom »)
    Agents : login_ae, nom_prenom_ae, login_ce   (alias nom : nom_prenom)
"""
import io

import admin           # style + _cellstr (réutilisés)
import db_source

ESC = admin.ESC
_cellstr = admin._cellstr


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------
_DDL_CHEF = (
    'CREATE TABLE IF NOT EXISTS "chef_equipe" ('
    '"login_ce" TEXT PRIMARY KEY, "nom_prenom_ce" TEXT NOT NULL)')
_DDL_AGENT = (
    'CREATE TABLE IF NOT EXISTS "agent" ('
    '"login_ae" TEXT PRIMARY KEY, "nom_prenom_ae" TEXT NOT NULL, '
    '"login_ce" TEXT REFERENCES "chef_equipe" ("login_ce"))')


def creer_tables(conn) -> None:
    """Crée `chef_equipe` puis `agent` (FK) si absentes. Idempotent."""
    cur = conn.cursor()
    cur.execute(_DDL_CHEF)
    cur.execute(_DDL_AGENT)
    conn.commit()


# ---------------------------------------------------------------------------
# Accès / comptage
# ---------------------------------------------------------------------------
def compter(conn, district=None) -> dict:
    """Nombre de fiches, borne au DISTRICT quand il est fourni.

    {'chefs', 'agents', 'chefs_sans_district', 'agents_sans_district'}

    Sans `district` (Admin, ou compte sans affectation), on compte tout — c'est
    l'ancien comportement.

    Les fiches SANS district sont comptees a part et non ignorees : elles
    n'apparaissent dans aucun district, donc personne ne les verrait. Un
    responsable qui televerse et lit « 0 agent » doit pouvoir comprendre
    pourquoi plutot que de recommencer son televersement.
    """
    ph = db_source._placeholder(conn)
    cur = conn.cursor()

    def _n(sql, params=()):
        cur.execute(sql, params)
        return cur.fetchone()[0]

    sans_ce = _n('SELECT COUNT(*) FROM "chef_equipe" WHERE "district_ce" IS NULL')
    sans_ae = _n('SELECT COUNT(*) FROM "agent" WHERE "district_ae" IS NULL')

    if district is None:
        return {"chefs": _n('SELECT COUNT(*) FROM "chef_equipe"'),
                "agents": _n('SELECT COUNT(*) FROM "agent"'),
                "chefs_sans_district": sans_ce,
                "agents_sans_district": sans_ae,
                "district": None}
    try:
        code = int(district)
    except (TypeError, ValueError):
        code = None
    if code is None:
        return {"chefs": 0, "agents": 0, "chefs_sans_district": sans_ce,
                "agents_sans_district": sans_ae, "district": None}
    return {
        "chefs": _n(f'SELECT COUNT(*) FROM "chef_equipe" WHERE "district_ce"={ph}',
                    (code,)),
        "agents": _n(f'SELECT COUNT(*) FROM "agent" WHERE "district_ae"={ph}',
                     (code,)),
        "chefs_sans_district": sans_ce,
        "agents_sans_district": sans_ae,
        "district": code,
    }


def _chef_existe(conn, login_ce) -> bool:
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT 1 FROM "chef_equipe" WHERE "login_ce"={ph}', (login_ce,))
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Lien avec les données de dénombrement (interview__diagnostics.responsible)
# ---------------------------------------------------------------------------
_NA = "##N/A##"                            # marqueur « manquant » de Survey Solutions


def _code_propre(v) -> str:
    """Code agent nettoyé ; "" pour un vide ou un « ##N/A## »."""
    s = ("" if v is None else str(v)).strip()
    return "" if s == _NA else s


def _zone_du_login(login):
    """`EQ1_MDTR_0002` -> 'MDTR' (casse ignorée : `bELO` = `BELO`, relevé le
    27/09). None si le login n'a pas la forme PREFIXE_ZONE_NUMERO."""
    parties = str(login or "").strip().split("_")
    if len(parties) >= 3 and parties[1].strip():
        return parties[1].strip().upper()
    return None


def _districts_connus(conn) -> set:
    """Codes présents dans `district` : cible de la clé étrangère `district_ae`.
    Un code hors référentiel ne doit jamais être écrit."""
    cur = conn.cursor()
    try:
        cur.execute('SELECT "code_district" FROM "district"')
        return {int(r[0]) for r in cur.fetchall() if r[0] is not None}
    except Exception:
        return set()


def _unique(vus: dict) -> dict:
    """{clé: {districts}} -> {clé: district} pour les seules clés NON ambiguës."""
    return {k: next(iter(s)) for k, s in vus.items() if len(s) == 1}


def _districts_enquetes(conn, table_diag, table_menage, col_district) -> dict:
    """{code agent: district} d'après les INTERVIEWS : le district où l'agent a
    réellement enquêté, quand il est unique. C'est la source la plus sûre — elle
    ne dépend pas de la façon dont le login a été composé."""
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT DISTINCT d."responsible", m."{col_district}" '
                    f'FROM "{table_diag}" d JOIN "{table_menage}" m '
                    f'ON m."interview__key" = d."interview__key" '
                    f'WHERE d."responsible" IS NOT NULL '
                    f'AND m."{col_district}" IS NOT NULL')
        lignes = cur.fetchall()
    except Exception:
        return {}                         # tables absentes (base neuve)
    vus = {}
    for code, dist in lignes:
        c = _code_propre(code)
        try:
            d = int(float(dist))
        except (TypeError, ValueError):
            continue
        if c:
            vus.setdefault(c, set()).add(d)
    return _unique(vus)


def _districts_par_zone(conn) -> dict:
    """{zone: district} d'après les fiches DÉJÀ rattachées (agents et CE), pour
    les seules zones qui ne pointent que sur UN district — la méthode du
    rétro-remplissage du 27/09. Une zone ambiguë ou inconnue ne donne rien."""
    cur = conn.cursor()
    vus = {}
    for sql in ('SELECT "login_ae","district_ae" FROM "agent" '
                'WHERE "district_ae" IS NOT NULL',
                'SELECT "login_ce","district_ce" FROM "chef_equipe" '
                'WHERE "district_ce" IS NOT NULL'):
        try:
            cur.execute(sql)
            lignes = cur.fetchall()
        except Exception:
            continue                      # colonne district absente (ancien schéma)
        for login, dist in lignes:
            z = _zone_du_login(login)
            if z:
                vus.setdefault(z, set()).add(int(dist))
    return _unique(vus)


def synchroniser_agents_detail(conn, table_diag="interview__diagnostics",
                               table_menage="den_menage",
                               col_district="district") -> dict:
    """Complète `agent` à partir des codes agent présents dans les données de
    collecte (`<table_diag>.responsible`), en posant le DISTRICT dès la création.

    Tout code présent dans les données mais ABSENT de `agent` y est inséré, avec le
    NOM = le CODE (le nom réel vient du téléversement Excel) et chef d'équipe
    inconnu. Ainsi chaque code agent des données a une ligne dans `agent`
    (intégrité de la clé étrangère garantie côté Python).

    Le district est déduit, par ordre de confiance :
      1. des interviews — le district où l'agent a enquêté, s'il est unique ;
      2. du code de zone du login, si cette zone ne désigne qu'un district parmi
         les fiches déjà rattachées ;
      3. sinon NULL. Un district faux se propagerait silencieusement dans tous
         les comptages ; un district vide se voit (page /equipes, filtre Admin).

    Les agents EXISTANTS sans district reçoivent le district par la même règle.
    Un district déjà enregistré n'est JAMAIS remplacé.

    Avant le 2026-09-28, les fiches étaient créées sans district : 613 d'entre
    elles, invisibles de tout responsable, ont dû être supprimées à la main.

    Renvoie {'crees', 'crees_sans_district', 'districts_poses'}. Sans effet si
    la table de collecte n'existe pas encore (base neuve)."""
    bilan = {"crees": 0, "crees_sans_district": 0, "districts_poses": 0}
    creer_tables(conn)
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT DISTINCT "responsible" FROM "{table_diag}" '
                    'WHERE "responsible" IS NOT NULL')
        codes = sorted({c for c in (_code_propre(r[0]) for r in cur.fetchall())
                        if c})
    except Exception:
        return bilan                      # table de collecte absente
    if not codes:
        return bilan

    connus = _districts_connus(conn)
    par_enquete = _districts_enquetes(conn, table_diag, table_menage, col_district)
    par_zone = _districts_par_zone(conn)

    def _district(code):
        d = par_enquete.get(code)
        if d is None:
            d = par_zone.get(_zone_du_login(code))
        return d if d in connus else None

    ph = db_source._placeholder(conn)
    for c in codes:
        cur.execute(f'SELECT "district_ae" FROM "agent" WHERE "login_ae"={ph}', (c,))
        row = cur.fetchone()
        d = _district(c)
        if row is None:
            cur.execute('INSERT INTO "agent" ("login_ae","nom_prenom_ae","login_ce",'
                        f'"district_ae") VALUES ({ph},{ph},NULL,{ph})',
                        (c, c, d))        # nom = code
            bilan["crees"] += 1
            if d is None:
                bilan["crees_sans_district"] += 1
        elif row[0] is None and d is not None:
            cur.execute(f'UPDATE "agent" SET "district_ae"={ph} '
                        f'WHERE "login_ae"={ph} AND "district_ae" IS NULL', (d, c))
            bilan["districts_poses"] += 1
    conn.commit()
    return bilan


def synchroniser_agents(conn) -> int:
    """Dénombrement : voir `synchroniser_agents_detail`. Renvoie le nombre
    d'agents créés (contrat d'origine, attendu par les appelants)."""
    return synchroniser_agents_detail(conn)["crees"]


def noms_agents(conn) -> dict:
    """{code_agent: nom} pour les agents dont le nom est VRAIMENT renseigné
    (nom != code). Sert au rapport pour afficher le nom au lieu du code ; un code
    dont le nom n'a pas encore été renseigné (nom == code) n'y figure pas -> le
    rapport garde le code."""
    creer_tables(conn)
    cur = conn.cursor()
    cur.execute('SELECT "login_ae","nom_prenom_ae" FROM "agent"')
    out = {}
    for code, nom in cur.fetchall():
        c = ("" if code is None else str(code)).strip()
        n = ("" if nom is None else str(nom)).strip()
        if c and n and n != c:
            out[c] = n
    return out


def agents_et_chefs(conn) -> dict:
    """{ login_ae : {"nom": nom_agent, "chef_login": login_ce|"",
                     "chef_nom": nom_chef|""} } pour TOUS les agents connus.
    Sert à l'export (regroupement agent -> chef d'équipe)."""
    creer_tables(conn)
    cur = conn.cursor()
    cur.execute('SELECT a."login_ae", a."nom_prenom_ae", a."login_ce", '
                'c."nom_prenom_ce" FROM "agent" a '
                'LEFT JOIN "chef_equipe" c ON a."login_ce" = c."login_ce"')
    out = {}
    for lae, nae, lce, nce in cur.fetchall():
        code = ("" if lae is None else str(lae)).strip()
        if not code:
            continue
        out[code] = {
            "nom": ("" if nae is None else str(nae)).strip() or code,
            "chef_login": ("" if lce is None else str(lce)).strip(),
            "chef_nom": ("" if nce is None else str(nce)).strip(),
        }
    return out


# ---------------------------------------------------------------------------
# Lecture d'un Excel (openpyxl) -> lignes {colonne: valeur}
# ---------------------------------------------------------------------------
def _lire_xlsx(chemin_xlsx, alias):
    """Lit la 1re feuille. `alias` = {clef_logique: (noms d'en-tête acceptés)}.
    Renvoie (lignes, entetes_manquantes). Chaque ligne = {clef_logique: str}."""
    import openpyxl
    wb = openpyxl.load_workbook(chemin_xlsx, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    entetes = next(it, None)
    if not entetes:
        wb.close()
        return [], list(alias)          # fichier vide -> tout manque
    # index de colonne par en-tête normalisé (minuscule, espaces -> _)
    idx = {}
    for i, h in enumerate(entetes):
        if h is not None:
            cle = str(h).strip().lower().replace(" ", "_")
            idx.setdefault(cle, i)
    # résolution clef logique -> index via les alias
    col = {}
    manquantes = []
    for logique, noms in alias.items():
        trouve = next((idx[n] for n in noms if n in idx), None)
        if trouve is None:
            manquantes.append(logique)
        else:
            col[logique] = trouve
    if manquantes:
        wb.close()
        return [], manquantes
    lignes = []
    for r in it:
        if r is None or all(v is None for v in r):
            continue
        lignes.append({k: (_cellstr(r[i]) if i < len(r) else "")
                       for k, i in col.items()})
    wb.close()
    return lignes, []


_ALIAS_CHEF = {"login_ce": ("login_ce",),
               "nom_prenom_ce": ("nom_prenom_ce", "nom_prenom", "nom_et_prenom")}
_ALIAS_AGENT = {"login_ae": ("login_ae",),
                "nom_prenom_ae": ("nom_prenom_ae", "nom_prenom", "nom_et_prenom"),
                "login_ce": ("login_ce",)}


# ---------------------------------------------------------------------------
# Transcription (UPSERT) depuis les deux Excel
# ---------------------------------------------------------------------------
def _upsert_chef(conn, login_ce, nom, district=None):
    """Renvoie (état, district_pose, conflit).

    `état` : 'ajoute' | 'modifie' | 'inchange' — comme avant.
    `district_pose` : True si le district vient d'être renseigné.
    `conflit` : le district DÉJÀ enregistré s'il diffère de celui demandé —
    auquel cas il est CONSERVÉ. Un téléversement ne déplace pas une équipe d'un
    district à un autre sans qu'on le dise.
    """
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "nom_prenom_ce","district_ce" FROM "chef_equipe" '
                f'WHERE "login_ce"={ph}', (login_ce,))
    row = cur.fetchone()
    if row is None:
        cur.execute('INSERT INTO "chef_equipe" ("login_ce","nom_prenom_ce",'
                    f'"district_ce") VALUES ({ph},{ph},{ph})',
                    (login_ce, nom, district))
        return "ajoute", district is not None, None

    actuel = row[1]
    conflit = (actuel if (district is not None and actuel is not None
                          and int(actuel) != int(district)) else None)
    poser = district is not None and actuel is None
    if poser:
        cur.execute(f'UPDATE "chef_equipe" SET "district_ce"={ph} '
                    f'WHERE "login_ce"={ph}', (district, login_ce))
    if row[0] != nom:
        cur.execute(f'UPDATE "chef_equipe" SET "nom_prenom_ce"={ph} '
                    f'WHERE "login_ce"={ph}', (nom, login_ce))
        return "modifie", poser, conflit
    return ("modifie" if poser else "inchange"), poser, conflit


def _upsert_agent(conn, login_ae, nom, login_ce, district=None):
    """Renvoie (état, district_pose, conflit) — voir `_upsert_chef`."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT "nom_prenom_ae","login_ce","district_ae" FROM "agent" '
                f'WHERE "login_ae"={ph}', (login_ae,))
    row = cur.fetchone()
    if row is None:
        cur.execute('INSERT INTO "agent" ("login_ae","nom_prenom_ae","login_ce",'
                    f'"district_ae") VALUES ({ph},{ph},{ph},{ph})',
                    (login_ae, nom, login_ce, district))
        return "ajoute", district is not None, None

    actuel = row[2]
    conflit = (actuel if (district is not None and actuel is not None
                          and int(actuel) != int(district)) else None)
    poser = district is not None and actuel is None
    if poser:
        cur.execute(f'UPDATE "agent" SET "district_ae"={ph} '
                    f'WHERE "login_ae"={ph}', (district, login_ae))
    if row[0] != nom or (row[1] or "") != (login_ce or ""):
        cur.execute(f'UPDATE "agent" SET "nom_prenom_ae"={ph},"login_ce"={ph} '
                    f'WHERE "login_ae"={ph}', (nom, login_ce, login_ae))
        return "modifie", poser, conflit
    return ("modifie" if poser else "inchange"), poser, conflit


def _bilan_vide():
    return {"ajoutes": 0, "modifies": 0, "inchanges": 0}


def transcrire(conn, chemin_chef_xlsx, chemin_agent_xlsx, district=None):
    """Transcrit les deux Excel vers `chef_equipe` puis `agent` (upsert).

    `district` : code du district d'affectation de celui qui téléverse. Il n'est
    PAS dans le fichier — le modèle Excel ne change pas — mais on le connaît par
    son compte. Posé sur les fiches créées et sur celles dont le district est
    vide ; jamais substitué à un district différent déjà enregistré.

    Renvoie un dict :
        {"chefs": {ajoutes,modifies,inchanges}, "agents": {...},
         "districts_poses": int, "conflits": [(type, login, district_enregistré)],
         "erreurs": [(fichier, ligne, message), ...]}
    Lève ValueError si un fichier a des colonnes manquantes (rien n'est écrit).
    Les CE sont transcrits AVANT les agents (cible des clés étrangères)."""
    creer_tables(conn)
    chefs, manq_c = _lire_xlsx(chemin_chef_xlsx, _ALIAS_CHEF)
    if manq_c:
        raise ValueError("Fichier des Chefs d'Équipe — colonnes manquantes : "
                         + ", ".join(manq_c))
    agents, manq_a = _lire_xlsx(chemin_agent_xlsx, _ALIAS_AGENT)
    if manq_a:
        raise ValueError("Fichier des Agents — colonnes manquantes : "
                         + ", ".join(manq_a))

    res = {"chefs": _bilan_vide(), "agents": _bilan_vide(), "erreurs": [],
           "districts_poses": 0, "conflits": []}
    # 1) Chefs d'équipe
    vus_ce = set()
    for n, ligne in enumerate(chefs, start=2):
        login_ce = ligne["login_ce"].strip()
        nom = ligne["nom_prenom_ce"].strip()
        if not login_ce:
            res["erreurs"].append(("Chefs d'Équipe", n, "login_ce vide"))
            continue
        if not nom:
            res["erreurs"].append(("Chefs d'Équipe", n,
                                   f"nom et prénom vides (login_ce={login_ce})"))
            continue
        etat, pose, conflit = _upsert_chef(conn, login_ce, nom, district)
        res["chefs"][etat + "s"] += 1
        res["districts_poses"] += 1 if pose else 0
        if conflit is not None:
            res["conflits"].append(("Chef d'Équipe", login_ce, conflit))
        vus_ce.add(login_ce)
    # 2) Agents (login_ce doit exister — dans le fichier CE ou déjà en base)
    for n, ligne in enumerate(agents, start=2):
        login_ae = ligne["login_ae"].strip()
        nom = ligne["nom_prenom_ae"].strip()
        login_ce = ligne["login_ce"].strip()
        if not login_ae:
            res["erreurs"].append(("Agents", n, "login_ae vide"))
            continue
        if not nom:
            res["erreurs"].append(("Agents", n,
                                   f"nom et prénom vides (login_ae={login_ae})"))
            continue
        if not login_ce:
            res["erreurs"].append(("Agents", n,
                                   f"login_ce (chef d'équipe) vide (agent {login_ae})"))
            continue
        if login_ce not in vus_ce and not _chef_existe(conn, login_ce):
            res["erreurs"].append(("Agents", n,
                                   f"chef d'équipe inconnu : {login_ce} "
                                   f"(agent {login_ae})"))
            continue
        etat, pose, conflit = _upsert_agent(conn, login_ae, nom, login_ce,
                                           district)
        res["agents"][etat + "s"] += 1
        res["districts_poses"] += 1 if pose else 0
        if conflit is not None:
            res["conflits"].append(("Agent", login_ae, conflit))
    conn.commit()
    return res


# ---------------------------------------------------------------------------
# Modèles Excel (canevas à remplir)
# ---------------------------------------------------------------------------
def modele_chef_xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "chefs_equipe"
    ws.append(["login_ce", "nom_prenom_ce"])
    ws.append(["CE001", "RAKOTO Jean"])
    ws.append(["CE002", "RABE Marie"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def modele_agent_xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "agents"
    ws.append(["login_ae", "nom_prenom_ae", "login_ce"])
    ws.append(["AE001", "RANDRIA Paul", "CE001"])
    ws.append(["AE002", "RASOA Hanta", "CE001"])
    ws.append(["AE003", "RAKOTOSON Luc", "CE002"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Pages (charte visuelle d'admin.py)
# ---------------------------------------------------------------------------
def _entete() -> str:
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Traitement — RSU</title><style>{admin._STYLE}</style></head>'
            f'<body><div class="bar"><b>🗂 Espace Traitement</b>'
            f'<a href="/traitement">Accueil</a>'
            f'<a href="/choix">Tableau de bord</a>'
            f'<span class="sp"></span></div><div class="wrap">')


_CSS_CHOIX = """
<style>
.choix{display:grid;grid-template-columns:repeat(auto-fit,minmax(16.25rem,1fr));
  gap:1rem;margin-top:1rem}
.ca{display:block;text-decoration:none;color:inherit;background:#fff;
  border:1.5px solid #e2e8f0;border-radius:0.875rem;padding:1.25rem 1.25rem 1.125rem;
  transition:.15s;position:relative}
.ca:hover{border-color:#2563eb;box-shadow:0 0.75rem 1.625rem rgba(37,99,235,.14);
  transform:translateY(-2px)}
.ca .ic{font-size:1.875rem;line-height:1;margin-bottom:0.625rem}
.ca .t{font-weight:700;font-size:1rem;margin-bottom:0.375rem}
.ca .d{font-size:0.8125rem;color:#64748b;line-height:1.5}
.ca .go{margin-top:0.75rem;font-weight:700;color:#2563eb;font-size:0.8125rem}
</style>"""


def page_choix_traitement(district_txt) -> str:
    """Accueil de l'Expert Traitement : tableau de bord OU remplir CE/Agents."""
    h = [_entete(), _CSS_CHOIX, '<h1>Espace Traitement</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>.</div>',
         '<div class="choix">',
         '<a class="ca" href="/choix">'
         '<div class="ic">📊</div><div class="t">Tableau de bord — Dénombrement</div>'
         '<div class="d">Consulter le rapport de suivi du dénombrement pour votre '
         'district.</div><div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/equipes">'
         '<div class="ic">👥</div><div class="t">Chefs d’équipe et agents</div>'
         '<div class="d">Consulter, corriger ou supprimer les fiches des CE et '
         'des agents enquêteurs de votre district.</div>'
         '<div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/equipe">'
         '<div class="ic">👔</div><div class="t">Équipe technique</div>'
         '<div class="d">Consulter l’encadrement (Coordonnateur régional, '
         'Superviseurs Techniques par axe, Traitement, Expert survey) affecté à '
         'votre district.</div><div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/traitement/equipes">'
         '<div class="ic">👥</div><div class="t">Remplir la base Chef d’Équipe et '
         'Agent</div>'
         '<div class="d">Téléverser les fichiers Excel des Chefs d’Équipe et des '
         'Agents, puis transcrire vers la base de données.</div>'
         '<div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/vad/general">'
         '<div class="ic">📈</div><div class="t">Tableau de bord — Visite à '
         'domicile</div>'
         '<div class="d">Suivre la VAD de votre district : avancement, '
         'démographie, habitation, biens, eau et assainissement, erreurs.</div>'
         '<div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/traitement/prechargement">'
         '<div class="ic">📦</div><div class="t">Générer la base de préchargement '
         '(VAD)</div>'
         '<div class="d">Produire la base de préchargement et le fichier de charge '
         'par agent (avec équilibrage optionnel) à partir du dénombrement transcrit '
         'de votre district.</div>'
         '<div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/journal">'
         '<div class="ic">📓</div><div class="t">Mon journal de bord</div>'
         '<div class="d">Consigner les activités que vous avez réalisées dans la '
         'journée.</div><div class="go">Ouvrir →</div></a>',
         '</div>', '</div></body></html>']
    return "".join(h)


def _table_bilan(res) -> str:
    def ligne(nom, b):
        return (f'<tr><td>{nom}</td><td>+{b["ajoutes"]}</td>'
                f'<td>~{b["modifies"]}</td><td>={b["inchanges"]}</td></tr>')
    return ('<table><tr><th>Table</th><th>Ajoutés</th><th>Modifiés</th>'
            '<th>Inchangés</th></tr>'
            + ligne("Chefs d’Équipe", res["chefs"])
            + ligne("Agents", res["agents"]) + '</table>')


def page_equipes(conn, district_txt, resultat=None, message=None, erreur=None,
                 district=None) -> str:
    """Formulaire de téléversement des deux Excel + bilan de la transcription.

    `district` : code du district d'affectation. Les nombres affichés lui sont
    bornés — sans cela on montrait les totaux de toute la base à quelqu'un qui
    ne travaille que sur un district.
    """
    n = compter(conn, district)
    h = [_entete(),
         '<p style="margin:0 0 6px"><a href="/traitement">← Accueil Traitement</a></p>',
         '<h1>Base des Chefs d’Équipe et des Agents</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>. '
         + (f'Actuellement en base <b>pour ce district</b> : '
            if n.get("district") is not None else 'Actuellement en base : ')
         + f'<b>{n["chefs"]}</b> chef(s) d’équipe et '
         f'<b>{n["agents"]}</b> agent(s).</div>']
    # Les fiches sans district n'apparaissent dans aucun district : le signaler
    # evite de croire que le televersement a echoue.
    _orphelines = n.get("chefs_sans_district", 0) + n.get("agents_sans_district", 0)
    if n.get("district") is not None and _orphelines:
        h.append(
            f'<div class="err">⚠️ <b>{_orphelines} fiche(s) sans district</b> '
            f'en base ({n["chefs_sans_district"]} chef(s) d’équipe, '
            f'{n["agents_sans_district"]} agent(s)) : elles n’apparaissent dans '
            f'<b>aucun</b> district, donc pas ci-dessus. Elles ont été chargées '
            f'avant le remplissage automatique du district, ou par un compte '
            f'sans affectation.</div>')
    if message:
        h.append(f'<div class="msg">{ESC(message)}</div>')
    if erreur:
        h.append(f'<div class="err">{erreur}</div>')      # HTML autorisé (listes)

    if resultat:
        h.append('<h2>Bilan de la transcription</h2>')
        h.append(_table_bilan(resultat))
        if resultat.get("erreurs"):
            items = "".join(
                f'<li>{ESC(f)} — ligne {ln} : {ESC(m)}</li>'
                for f, ln, m in resultat["erreurs"])
            h.append('<div class="err"><b>Lignes ignorées :</b>'
                     f'<ul>{items}</ul></div>')
        h.append('<p><a href="/traitement/equipes">↻ Nouvelle transcription</a></p>')

    h.append('<h2>Téléverser les fichiers Excel</h2>')
    h.append(
        '<form method="post" action="/traitement/equipes" '
        'enctype="multipart/form-data" class="grid-form">'
        '<div><label>Fichier Excel — Liste des <b>Chefs d’Équipe</b> '
        '(colonnes : login_ce, nom_prenom_ce)</label>'
        '<input type="file" name="fichier_chef" accept=".xlsx" required></div>'
        '<div><label>Fichier Excel — Liste des <b>Agents</b> '
        '(colonnes : login_ae, nom_prenom_ae, login_ce)</label>'
        '<input type="file" name="fichier_agent" accept=".xlsx" required></div>'
        '<div style="align-self:end"><button>Transcrire vers la base</button></div>'
        '</form>')
    h.append('<div class="note">Les deux fichiers sont requis. La transcription '
             '<b>ajoute</b> les nouveaux, <b>met à jour</b> les modifiés et '
             '<b>ne supprime rien</b>. Chaque agent doit référencer un '
             '<b>login_ce</b> présent dans le fichier des Chefs d’Équipe ou déjà en '
             'base.<br>Modèles : '
             '<a href="/traitement/modele/chef.xlsx">⬇ Chefs d’Équipe</a> · '
             '<a href="/traitement/modele/agent.xlsx">⬇ Agents</a>.</div>')
    h.append('</div></body></html>')
    return "".join(h)
