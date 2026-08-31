# -*- coding: utf-8 -*-
"""
utilisateurs.py — Comptes de connexion en base de données.

Table `utilisateurs` (dans la MÊME base que le reste, via db_source.connect() :
SQLite en local, PostgreSQL si RSU_DB_URL). Champs :

    login                 TEXT  (clé, identifiant de connexion, unique)
    nom_prenom            TEXT  (Nom et prénom)
    responsabilite        TEXT  parmi RESPONSABILITES (Coordonnateur / Expert survey
                                / Traitement / Superviseur Technique)
    mot_de_passe          TEXT  HACHÉ (PBKDF2-HMAC-SHA256, jamais en clair)
    telephone             TEXT  numéro de téléphone (facultatif, NULL possible)
    cin                   TEXT  Carte d'Identité Nationale, 12 chiffres (facultatif)
    email                 TEXT  adresse e-mail (facultatif, NULL possible)
    district_affectation  BIGINT  code district, CLÉ ÉTRANGÈRE -> district(code_district) ;
                                  NULL = toute la zone
    actif                 INT     1 = peut se connecter, 0 = désactivé
    cree_le               TEXT    horodatage ISO

Les communes d'un Superviseur (1 à 7) sont dans une table de LIAISON (une commune
ne pouvant pas être une clé étrangère si on en met plusieurs dans une colonne) :

    superviseur_commune(login -> utilisateurs.login,  code_commune -> commune.code_commune)
    PK (login, code_commune)  ;  0 ligne pour les rôles sans commune précise.

Note SQLite : les clés étrangères ne sont vérifiées que si `PRAGMA foreign_keys=ON`
(désactivé par défaut) ; PostgreSQL (production) les applique nativement. L'intégrité
est de toute façon garantie côté Python par `valider_affectation`.

Règle d'affectation selon la responsabilité (validée à l'ajout) :
    Admin / Coordonnateur -> district = NULL (toute la zone),  commune = NULL (toutes)
    Expert survey         -> district = un district,           commune = NULL (toutes
    Traitement                                                  les communes du district)
    Superviseur Technique -> district = un district,           commune = 1 à 7 communes
                                                                de ce district (liste)

SÉCURITÉ : le mot de passe n'est JAMAIS stocké ni journalisé en clair. Seul un
condensé PBKDF2 salé est enregistré ; la vérification est à temps constant.

CLI de gestion (l'admin saisit le mot de passe au clavier, jamais en argument) :
    python utilisateurs.py init                 # crée la table (+ compte d'amorçage)
    python utilisateurs.py add                  # ajoute un utilisateur (interactif)
    python utilisateurs.py list                 # liste les comptes (sans les mots de passe)
    python utilisateurs.py passwd <login>       # change le mot de passe
    python utilisateurs.py actif  <login> on|off
    python utilisateurs.py del    <login>
"""
import datetime
import getpass
import hashlib
import hmac
import re
import secrets
import sys

import db_source
import zones

# Table de RÉFÉRENCE des responsabilités : (code, libellé). L'ORDRE du tuple =
# ordre d'affichage ET numérotation des codes (séquentiels 1→9). `code_responsable`
# est la clé primaire référencée par `utilisateurs.code_responsable` : tout
# changement d'ordre ici est propagé aux comptes existants par `_renumeroter_codes`
# (migration au démarrage, identifie chaque rôle par son LIBELLE).
RESPONSABILITES_REF = (
    (1, "Admin"),
    (2, "Comités Techniques"),
    (3, "Coordonnateur Nationale"),
    (4, "Coordonnateur régionale"),
    (5, "Traitement"),
    (6, "Expert survey"),
    (7, "Superviseur Technique"),
    (8, "Logistique District"),
    (9, "Logistique Inter-Communale"),
)
LIBELLE_PAR_CODE = {code: lib for code, lib in RESPONSABILITES_REF}
CODE_PAR_LIBELLE = {lib: code for code, lib in RESPONSABILITES_REF}
RESPONSABILITES = tuple(lib for _c, lib in RESPONSABILITES_REF)   # libellés valides

# Libellé (dont libellés HÉRITÉS) -> code CIBLE actuel. Sert à la migration d'une
# base à l'ancien schéma `responsabilite` TEXT vers `code_responsable`. = CODE_PAR_LIBELLE
# + alias hérités ("Coordonnateur", "Logistique Communale").
_MIGRATION_CODE = {
    **CODE_PAR_LIBELLE,
    "Coordonnateur": CODE_PAR_LIBELLE["Coordonnateur Nationale"],
    "Logistique Communale": CODE_PAR_LIBELLE["Logistique Inter-Communale"],
}

# Formes d'affectation par rôle :
_ROLES_ZONE_ENTIERE = ("Admin", "Coordonnateur Nationale")            # tous districts
_ROLES_MULTI_DISTRICT = ("Coordonnateur régionale", "Comités Techniques")  # 1 à 5 districts
_ROLES_UN_DISTRICT = ("Traitement", "Logistique District", "Expert survey")  # 1 district
_ROLES_DISTRICT_COMMUNES = ("Superviseur Technique", "Logistique Inter-Communale")  # district + 1 à 7 communes
# Rôles « Responsable Logistique et Financier » : espace dédié (logistique.py),
# PAS d'accès au tableau de bord des données. L'affectation reste gérée par les
# groupes ci-dessus (Logistique District = 1 district ; Logistique Inter-Communale =
# 1 district + 1 à 7 communes).
_ROLES_LOGISTIQUE = ("Logistique District", "Logistique Inter-Communale")

MAX_COMMUNES_SUPERVISEUR = 7     # communes d'un rôle « district + communes »
MAX_DISTRICTS = 5                # districts d'un rôle « multi-district »

# Compte d'amorçage : créé UNIQUEMENT si la table est vide, pour ne pas se retrouver
# verrouillé dehors. Rôle Admin. ⚠️ mot de passe faible connu -> à changer aussitôt.
_BOOTSTRAP = {"login": "RSU", "mot_de_passe": "RSU",
              "nom_prenom": "Administrateur RSU", "responsabilite": "Admin"}

_ITERATIONS = 200_000

# Validation simple d'un e-mail (x@y.z) — permissive, juste pour écarter les fautes.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Hachage des mots de passe (bibliothèque standard)
# ---------------------------------------------------------------------------
def hacher(mot_de_passe: str, iterations: int = _ITERATIONS) -> str:
    """Renvoie « pbkdf2_sha256$<iterations>$<sel_hex>$<condensé_hex> »."""
    sel = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, iterations)
    return f"pbkdf2_sha256${iterations}${sel.hex()}${dk.hex()}"


def verifier(mot_de_passe: str, stocke: str) -> bool:
    """Compare (temps constant) un mot de passe au condensé stocké."""
    try:
        algo, it, sel_hex, hash_hex = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", mot_de_passe.encode("utf-8"), bytes.fromhex(sel_hex), int(it))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


# ---------------------------------------------------------------------------
# Schéma + accès
# ---------------------------------------------------------------------------
# Table de référence des responsabilités (code_responsable PK, libelle_responsable).
_DDL_RESPONSABILITE = (
    'CREATE TABLE IF NOT EXISTS "responsabilite" ('
    '"code_responsable" BIGINT PRIMARY KEY, "libelle_responsable" TEXT NOT NULL)')
# Schéma cible. `code_responsable` -> responsabilite ; district_affectation -> district.
# telephone / cin / email : coordonnées de l'utilisateur, facultatives (NULL possible).
# numero_orange_float : numéro Orange (Orange Money) servant au « Float » de l'équipe
# technique — facultatif (NULL possible), validé comme un téléphone (8-15 chiffres).
_COLS_UTILISATEURS = (
    '"login" TEXT PRIMARY KEY, "nom_prenom" TEXT NOT NULL, '
    '"code_responsable" BIGINT NOT NULL REFERENCES "responsabilite" ("code_responsable"), '
    '"mot_de_passe" TEXT NOT NULL, '
    '"telephone" TEXT, "cin" TEXT, "email" TEXT, '
    '"numero_orange_float" TEXT, "sexe" TEXT, '
    '"district_affectation" BIGINT REFERENCES "district" ("code_district"), '
    '"actif" INTEGER NOT NULL DEFAULT 1, "cree_le" TEXT NOT NULL')
_COLS_CIBLE = {"login", "nom_prenom", "code_responsable", "mot_de_passe",
               "telephone", "cin", "email", "numero_orange_float", "sexe",
               "district_affectation", "actif", "cree_le"}
# Table de liaison : les communes (FK) d'un rôle « district + communes ».
_DDL_LIAISON = (
    'CREATE TABLE IF NOT EXISTS "superviseur_commune" ('
    '"login" TEXT NOT NULL REFERENCES "utilisateurs" ("login") ON DELETE CASCADE, '
    '"code_commune" BIGINT NOT NULL REFERENCES "commune" ("code_commune"), '
    'PRIMARY KEY ("login","code_commune"))')
# Table de liaison : les districts (FK) d'un rôle « multi-district » (1 à 5).
_DDL_LIAISON_DISTRICT = (
    'CREATE TABLE IF NOT EXISTS "responsable_district" ('
    '"login" TEXT NOT NULL REFERENCES "utilisateurs" ("login") ON DELETE CASCADE, '
    '"code_district" BIGINT NOT NULL REFERENCES "district" ("code_district"), '
    'PRIMARY KEY ("login","code_district"))')


def creer_table(conn) -> None:
    """Crée `responsabilite` (+ seed), `utilisateurs` et les tables de liaison si
    absentes, puis migre. Les tables `district`/`commune`/`responsabilite` (cibles
    des clés étrangères) doivent exister d'abord : on les assure avant `utilisateurs`.

    ORDRE IMPORTANT : on LIT l'ancien mapping `responsabilite` AVANT de le re-seeder,
    pour pouvoir renuméroter les `code_responsable` des comptes existants (par LIBELLE)
    si les codes ont changé (RESPONSABILITES_REF). Le re-seed vient ensuite fixer les
    libellés de la table de référence sur les nouveaux codes."""
    zones.assurer_zones(conn)          # cibles des FK district/commune
    cur = conn.cursor()
    cur.execute(_DDL_RESPONSABILITE)   # cible de la FK code_responsable
    avant = _lire_responsabilites(conn)   # état AVANT re-seed (pour la renumérotation)
    cur.execute(f'CREATE TABLE IF NOT EXISTS "utilisateurs" ({_COLS_UTILISATEURS})')
    cur.execute(_DDL_LIAISON)
    cur.execute(_DDL_LIAISON_DISTRICT)
    _migrer(conn)                      # ancien schéma TEXT -> code_responsable si besoin
    _renumeroter_codes(conn, avant)    # remappe les comptes vers les nouveaux codes
    _seed_responsabilites(conn)        # fixe les libellés de responsabilite (codes cibles)
    conn.commit()


def _lire_responsabilites(conn) -> dict:
    """{code_responsable(int): libelle} actuel de la table de référence (ou {} si vide)."""
    cur = conn.cursor()
    cur.execute('SELECT "code_responsable","libelle_responsable" FROM "responsabilite"')
    return {int(c): l for c, l in cur.fetchall()}


def _renumeroter_codes(conn, avant: dict) -> None:
    """Renumérotation des `code_responsable` des comptes si les codes ont changé.

    `avant` = mapping {ancien_code: libellé} lu AVANT le re-seed. On construit
    ancien_code -> nouveau_code en passant par le LIBELLE (identité stable du rôle),
    puis on remappe `utilisateurs.code_responsable` en UNE passe (CASE : pas de
    double-application). Idempotent : rien si base neuve (`avant` vide) ou déjà au
    schéma cible (chaque ancien code == nouveau code)."""
    if not avant:
        return
    remap = {}
    for ancien_code, libelle in avant.items():
        nouveau = CODE_PAR_LIBELLE.get(libelle)
        if nouveau is not None and nouveau != ancien_code:
            remap[ancien_code] = nouveau
    if not remap:
        return
    cases = " ".join(f"WHEN {o} THEN {n}" for o, n in sorted(remap.items()))
    conn.cursor().execute(
        f'UPDATE "utilisateurs" SET "code_responsable" = '
        f'CASE "code_responsable" {cases} ELSE "code_responsable" END')
    conn.commit()


def _seed_responsabilites(conn) -> None:
    """Insère les 9 responsabilités de référence si absentes (idempotent)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    for code, lib in RESPONSABILITES_REF:
        cur.execute(f'SELECT "libelle_responsable" FROM "responsabilite" '
                    f'WHERE "code_responsable"={ph}', (code,))
        row = cur.fetchone()
        if row is None:
            cur.execute('INSERT INTO "responsabilite" ("code_responsable",'
                        f'"libelle_responsable") VALUES ({ph},{ph})', (code, lib))
        elif row[0] != lib:               # libellé corrigé -> mettre à jour
            cur.execute(f'UPDATE "responsabilite" SET "libelle_responsable"={ph} '
                        f'WHERE "code_responsable"={ph}', (lib, code))
    conn.commit()


def _est_sqlite(conn) -> bool:
    return not type(conn).__module__.split(".")[0].startswith("psycopg")


def _migrer(conn) -> None:
    """Si `utilisateurs` a un schéma antérieur (colonnes différentes de la cible, ou
    ancienne colonne `commune_affectation`, ou CHECK), la reconstruit vers le schéma
    à clés étrangères en conservant les comptes (SQLite ; en prod PG, install neuve)."""
    if not _est_sqlite(conn):
        return
    if set(_colonnes_table(conn, "utilisateurs")) == _COLS_CIBLE:
        return
    _reconstruire(conn)


def _reconstruire(conn) -> None:
    cur = conn.cursor()
    anciennes = _colonnes_table(conn, "utilisateurs")
    sel = ",".join(f'"{c}"' for c in anciennes)
    lignes = [dict(zip(anciennes, r))
              for r in cur.execute(f'SELECT {sel} FROM "utilisateurs"').fetchall()]
    cur.execute('ALTER TABLE "utilisateurs" RENAME TO "_utilisateurs_old"')
    cur.execute(f'CREATE TABLE "utilisateurs" ({_COLS_UTILISATEURS})')
    ph = db_source._placeholder(conn)
    for o in lignes:
        # code_responsable : soit déjà présent (re-migration), soit dérivé de
        # l'ancien libellé texte `responsabilite`.
        code = _to_int(o.get("code_responsable"))
        if code is None:
            code = _MIGRATION_CODE.get(o.get("responsabilite"), 1)   # défaut Admin
        cur.execute(
            'INSERT INTO "utilisateurs" ("login","nom_prenom","code_responsable",'
            '"mot_de_passe","telephone","cin","email","numero_orange_float","sexe",'
            '"district_affectation","actif","cree_le") '
            f'VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})',
            (o.get("login"), o.get("nom_prenom"), code,
             o.get("mot_de_passe"), o.get("telephone"), o.get("cin"),
             o.get("email"), o.get("numero_orange_float"), o.get("sexe"),
             _to_int(o.get("district_affectation")),
             o.get("actif", 1), o.get("cree_le")))
        # ancienne colonne comma-séparée -> table de liaison
        for cc in _normaliser_communes(o.get("commune_affectation")):
            ci = _to_int(cc)
            if ci is None:
                continue
            try:
                cur.execute('INSERT INTO "superviseur_commune" '
                            f'("login","code_commune") VALUES ({ph},{ph})',
                            (o.get("login"), ci))
            except Exception:
                pass
    cur.execute('DROP TABLE "_utilisateurs_old"')


def _to_int(v):
    if v in (None, ""):
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _colonnes_table(conn, table) -> list:
    """Noms de colonnes d'une table, portable SQLite/PostgreSQL (via description)."""
    cur = conn.cursor()
    cur.execute(f'SELECT * FROM "{table}" WHERE 1=0')
    return [d[0] for d in cur.description]


def _communes_de(conn, login) -> list:
    """Codes commune (int) affectés à un login (table de liaison), triés."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "code_commune" FROM "superviseur_commune" '
                f'WHERE "login"={ph} ORDER BY "code_commune"', (login,))
    return [r[0] for r in cur.fetchall()]


def _districts_de(conn, login) -> list:
    """Codes district (int) affectés à un login « multi-district » (liaison), triés."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "code_district" FROM "responsable_district" '
                f'WHERE "login"={ph} ORDER BY "code_district"', (login,))
    return [r[0] for r in cur.fetchall()]


def _codes_int(valeurs, quoi) -> list:
    """Normalise une saisie (None / code / 'a,b' / liste) en codes int uniques."""
    codes = []
    for x in _normaliser_communes(valeurs):     # même normalisation (dé-doublonnée)
        ci = _to_int(x)
        if ci is None:
            raise ValueError(f"Code {quoi} invalide : {x}.")
        if ci not in codes:
            codes.append(ci)
    return codes


def _normaliser_communes(commune) -> list:
    """Transforme une saisie (None / code / 'c1,c2' / liste) en liste de codes,
    dédoublonnée en gardant l'ordre."""
    if commune in (None, ""):
        return []
    if isinstance(commune, (list, tuple, set)):
        items = [str(x).strip() for x in commune]
    else:
        items = [x.strip() for x in str(commune).split(",")]
    out = []
    for x in items:
        if x and x not in out:
            out.append(x)
    return out


def _valider_tel(valeur, quoi):
    """Normalise/valide un numéro de type téléphone (facultatif). None si vide.
    Chiffres, espaces, '+', '-', '.' et '()' tolérés ; 8 à 15 chiffres."""
    v = (valeur or "").strip() or None
    if v is not None:
        chiffres = "".join(c for c in v if c.isdigit())
        if not (8 <= len(chiffres) <= 15) or any(
                c not in "0123456789 +-.()" for c in v):
            raise ValueError(f"{quoi} invalide : {valeur}.")
    return v


def valider_coordonnees(telephone, cin, email, numero_orange_float=None):
    """Normalise et valide les coordonnées facultatives.

    Renvoie (telephone|None, cin|None, email|None, numero_orange_float|None).
    Chaque champ vide -> None.
    - téléphone / numero_orange_float : chiffres, espaces, '+', '-', '.' et '()'
      tolérés ; 8 à 15 chiffres (le n° Orange sert au « Float » Orange Money).
    - CIN       : Carte d'Identité Nationale malgache = exactement 12 chiffres
                  (les espaces de saisie sont retirés).
    - e-mail    : format simple « x@y.z ».
    Lève ValueError si un champ fourni est manifestement invalide."""
    tel = _valider_tel(telephone, "Numéro de téléphone")
    orange = _valider_tel(numero_orange_float, "Numéro Orange (Float)")
    cin = (cin or "").strip() or None
    if cin is not None:
        cin = cin.replace(" ", "")
        if not (cin.isdigit() and len(cin) == 12):
            raise ValueError(f"CIN invalide (12 chiffres attendus) : {cin}.")
    email = (email or "").strip() or None
    if email is not None:
        if not _EMAIL_RE.match(email):
            raise ValueError(f"Adresse e-mail invalide : {email}.")
    return (tel, cin, email, orange)


# Sexe : facultatif (NULL possible). Valeurs canoniques stockées « Masculin » /
# « Féminin » ; saisies courantes (M/H/F, homme/femme…) normalisées.
SEXES = ("Masculin", "Féminin")
_SEXE_ALIAS = {
    "m": "Masculin", "h": "Masculin", "masculin": "Masculin", "homme": "Masculin",
    "male": "Masculin",
    "f": "Féminin", "féminin": "Féminin", "feminin": "Féminin", "femme": "Féminin",
    "female": "Féminin",
}


def valider_sexe(sexe):
    """Normalise le sexe vers « Masculin »/« Féminin » (ou None si vide).
    Lève ValueError si la valeur n'est pas reconnue."""
    s = (sexe or "").strip()
    if not s:
        return None
    val = _SEXE_ALIAS.get(s.lower())
    if val is None:
        raise ValueError(
            f"Sexe invalide (« Masculin » ou « Féminin » attendu) : {sexe}.")
    return val


def valider_affectation(conn, responsabilite, district, communes, districts=None):
    """Normalise et valide l'affectation selon la responsabilité.

    Renvoie (district:int|None, [communes:int], [districts:int]) :
    - zone entière (Admin, Coordonnateur Nationale) : (None, [], [])
    - multi-district (Coordonnateur régionale, Comités Techniques) : (None, [], [1-5])
    - un district (Traitement, Logistique District, Expert survey) : (d, [], [])
    - district + communes (Superviseur Technique, Logistique Inter-Communale) : (d, [1-7], [])
    Lève ValueError si l'affectation est incohérente avec le rôle."""
    d = _to_int(district)
    if responsabilite in _ROLES_ZONE_ENTIERE:
        return (None, [], [])                          # toute la zone
    if responsabilite in _ROLES_MULTI_DISTRICT:
        codes = _codes_int(districts, "district")
        if not 1 <= len(codes) <= MAX_DISTRICTS:
            raise ValueError(f"{responsabilite} : de 1 à {MAX_DISTRICTS} "
                             "district(s) attendu(s).")
        for dc in codes:
            if zones.libelles_district(conn, dc) is None:
                raise ValueError(f"District d'affectation inconnu : {dc}.")
        return (None, [], codes)
    if responsabilite in _ROLES_UN_DISTRICT:
        if d is None:
            raise ValueError(f"{responsabilite} : un district d'affectation est requis.")
        if zones.libelles_district(conn, d) is None:
            raise ValueError(f"District d'affectation inconnu : {district}.")
        return (d, [], [])
    if responsabilite in _ROLES_DISTRICT_COMMUNES:
        codes = _codes_int(communes, "commune")
        if not 1 <= len(codes) <= MAX_COMMUNES_SUPERVISEUR:
            raise ValueError(f"{responsabilite} : de 1 à "
                             f"{MAX_COMMUNES_SUPERVISEUR} commune(s) attendue(s).")
        # Le district est DÉDUIT des communes (elles doivent toutes appartenir au
        # MÊME district) ; si un district est aussi fourni (import Excel), il doit
        # coïncider.
        dists = set()
        for c in codes:
            dc = zones.district_de_commune(conn, c)
            if dc is None:
                raise ValueError(f"Commune inconnue : {c}.")
            dists.add(dc)
        if len(dists) != 1:
            raise ValueError("Les communes choisies doivent appartenir au MÊME "
                             "district.")
        dd = dists.pop()
        if d is not None and d != dd:
            raise ValueError(f"Les communes n'appartiennent pas au district {district}.")
        return (dd, codes, [])
    raise ValueError("Responsabilité invalide. Choix : " + ", ".join(RESPONSABILITES))


def ajouter(conn, login: str, nom_prenom: str, responsabilite: str,
            mot_de_passe: str, district_affectation=None,
            commune_affectation=None, districts_affectation=None,
            telephone=None, cin=None, email=None,
            numero_orange_float=None, sexe=None, actif: bool = True) -> None:
    """Insère un utilisateur (mot de passe haché, affectation validée selon le rôle).
    Les communes d'un rôle « district+communes » et les districts d'un rôle
    « multi-district » vont dans leur table de liaison. Lève ValueError si invalide.
    `commune_affectation`/`districts_affectation` : liste de codes, 'a,b', ou None.
    `telephone`/`cin`/`email` : coordonnées facultatives (validées si fournies).
    `numero_orange_float` : n° Orange (Float) facultatif (validé si fourni)."""
    login = (login or "").strip()
    nom_prenom = (nom_prenom or "").strip()
    if not login:
        raise ValueError("Le login est obligatoire.")
    if not nom_prenom:
        raise ValueError("Le nom et prénom sont obligatoires.")
    if responsabilite not in RESPONSABILITES:
        raise ValueError(
            "Responsabilité invalide. Choix : " + ", ".join(RESPONSABILITES))
    if not mot_de_passe:
        raise ValueError("Le mot de passe est obligatoire.")
    if _existe(conn, login):
        raise ValueError(f"Le login « {login} » existe déjà.")
    telephone, cin, email, numero_orange_float = valider_coordonnees(
        telephone, cin, email, numero_orange_float)
    sexe = valider_sexe(sexe)
    da, communes, districts = valider_affectation(
        conn, responsabilite, district_affectation, commune_affectation,
        districts_affectation)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO "utilisateurs" ("login","nom_prenom","code_responsable",'
        '"mot_de_passe","telephone","cin","email","numero_orange_float","sexe",'
        '"district_affectation","actif","cree_le") '
        f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (login, nom_prenom, CODE_PAR_LIBELLE[responsabilite], hacher(mot_de_passe),
         telephone, cin, email, numero_orange_float, sexe, da, 1 if actif else 0,
         datetime.datetime.now().isoformat(timespec="seconds")))
    for c in communes:
        cur.execute('INSERT INTO "superviseur_commune" ("login","code_commune") '
                    f'VALUES ({ph},{ph})', (login, c))
    for dc in districts:
        cur.execute('INSERT INTO "responsable_district" ("login","code_district") '
                    f'VALUES ({ph},{ph})', (login, dc))


def modifier(conn, login: str, nom_prenom: str, responsabilite: str,
             district_affectation=None, commune_affectation=None,
             districts_affectation=None, telephone=None, cin=None, email=None,
             numero_orange_float=None, sexe=None, mot_de_passe=None) -> None:
    """Met à jour un utilisateur EXISTANT (le login est la clé, non modifiable).

    Réécrit les renseignements (nom, rôle, coordonnées, affectation). L'affectation
    est revalidée selon le NOUVEAU rôle, et les tables de liaison sont reconstruites.
    `mot_de_passe` : si fourni (non vide), il est rehaché ; sinon inchangé.
    Lève ValueError si le login n'existe pas ou si l'affectation est invalide."""
    login = (login or "").strip()
    nom_prenom = (nom_prenom or "").strip()
    if not _existe(conn, login):
        raise ValueError(f"Login inconnu : {login}.")
    if not nom_prenom:
        raise ValueError("Le nom et prénom sont obligatoires.")
    if responsabilite not in RESPONSABILITES:
        raise ValueError(
            "Responsabilité invalide. Choix : " + ", ".join(RESPONSABILITES))
    telephone, cin, email, numero_orange_float = valider_coordonnees(
        telephone, cin, email, numero_orange_float)
    sexe = valider_sexe(sexe)
    da, communes, districts = valider_affectation(
        conn, responsabilite, district_affectation, commune_affectation,
        districts_affectation)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(
        'UPDATE "utilisateurs" SET "nom_prenom"={p},"code_responsable"={p},'
        '"telephone"={p},"cin"={p},"email"={p},"numero_orange_float"={p},'
        '"sexe"={p},"district_affectation"={p} '
        'WHERE "login"={p}'.format(p=ph),
        (nom_prenom, CODE_PAR_LIBELLE[responsabilite], telephone, cin, email,
         numero_orange_float, sexe, da, login))
    if mot_de_passe:
        cur.execute(f'UPDATE "utilisateurs" SET "mot_de_passe"={ph} '
                    f'WHERE "login"={ph}', (hacher(mot_de_passe), login))
    # Reconstruire les tables de liaison (le rôle a pu changer de forme).
    cur.execute(f'DELETE FROM "superviseur_commune" WHERE "login"={ph}', (login,))
    cur.execute(f'DELETE FROM "responsable_district" WHERE "login"={ph}', (login,))
    for c in communes:
        cur.execute('INSERT INTO "superviseur_commune" ("login","code_commune") '
                    f'VALUES ({ph},{ph})', (login, c))
    for dc in districts:
        cur.execute('INSERT INTO "responsable_district" ("login","code_district") '
                    f'VALUES ({ph},{ph})', (login, dc))


def _existe(conn, login: str) -> bool:
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT 1 FROM "utilisateurs" WHERE "login"={ph}', (login,))
    return cur.fetchone() is not None


def modifier_profil(conn, login: str, telephone=None, cin=None, email=None,
                    numero_orange_float=None, sexe=None) -> bool:
    """Mise à jour LIBRE-SERVICE des informations PERSONNELLES d'un compte :
    téléphone, CIN, e-mail, n° Orange (Float), sexe UNIQUEMENT. Ne touche JAMAIS
    au login, au rôle, à l'affectation, au nom ni au mot de passe (réservés à
    l'Admin). Valide les champs. Renvoie True si le compte existe."""
    login = (login or "").strip()
    if not _existe(conn, login):
        raise ValueError(f"Login inconnu : {login}.")
    telephone, cin, email, numero_orange_float = valider_coordonnees(
        telephone, cin, email, numero_orange_float)
    sexe = valider_sexe(sexe)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(
        'UPDATE "utilisateurs" SET "telephone"={p},"cin"={p},"email"={p},'
        '"numero_orange_float"={p},"sexe"={p} WHERE "login"={p}'.format(p=ph),
        (telephone, cin, email, numero_orange_float, sexe, login))
    conn.commit()
    return cur.rowcount > 0


def changer_mot_de_passe(conn, login: str, nouveau: str) -> bool:
    if not nouveau:
        raise ValueError("Le mot de passe est obligatoire.")
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'UPDATE "utilisateurs" SET "mot_de_passe"={ph} WHERE "login"={ph}',
                (hacher(nouveau), login))
    return cur.rowcount > 0


def definir_actif(conn, login: str, actif: bool) -> bool:
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'UPDATE "utilisateurs" SET "actif"={ph} WHERE "login"={ph}',
                (1 if actif else 0, login))
    return cur.rowcount > 0


def supprimer(conn, login: str) -> bool:
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    # Tables de liaison d'abord (ON DELETE CASCADE ne s'applique pas si les FK ne
    # sont pas actives — SQLite par défaut), puis le compte.
    cur.execute(f'DELETE FROM "superviseur_commune" WHERE "login"={ph}', (login,))
    cur.execute(f'DELETE FROM "responsable_district" WHERE "login"={ph}', (login,))
    cur.execute(f'DELETE FROM "utilisateurs" WHERE "login"={ph}', (login,))
    return cur.rowcount > 0


def lister(conn) -> list:
    """Liste les comptes SANS les mots de passe. `responsabilite` = libellé (via
    JOIN) ; communes_affectation / districts_affectation = listes de codes."""
    cur = conn.cursor()
    cur.execute('SELECT u."login",u."nom_prenom",r."libelle_responsable",'
                'u."district_affectation",u."actif",u."cree_le",u."code_responsable",'
                'u."telephone",u."cin",u."email",u."numero_orange_float",u."sexe" '
                'FROM "utilisateurs" u LEFT JOIN "responsabilite" r '
                'ON u."code_responsable"=r."code_responsable" ORDER BY u."login"')
    comptes = [{"login": r[0], "nom_prenom": r[1],
                "responsabilite": r[2] or LIBELLE_PAR_CODE.get(r[6], ""),
                "district_affectation": r[3], "actif": bool(r[4]),
                "cree_le": r[5], "code_responsable": r[6],
                "telephone": r[7], "cin": r[8], "email": r[9],
                "numero_orange_float": r[10], "sexe": r[11]}
               for r in cur.fetchall()]
    for u in comptes:
        u["communes_affectation"] = _communes_de(conn, u["login"])
        u["districts_affectation"] = _districts_de(conn, u["login"])
    return comptes


def obtenir(conn, login: str):
    """Renvoie le compte (même forme que `lister()`) pour un login, ou None.
    Sert au pré-remplissage du formulaire de modification."""
    for u in lister(conn):
        if u["login"] == (login or "").strip():
            return u
    return None


# Rôles composant « l'équipe technique » d'un district (ordre d'affichage). Ce
# sont des COMPTES affectés au district (pas les agents de terrain) : d'abord le
# Coordonnateur régional qui le couvre, puis le Traitement, l'Expert survey, et
# enfin les Superviseurs Techniques (présentés par axe de supervision, cf.
# serveur_app.page_equipe_technique).
ROLES_EQUIPE_TECHNIQUE = ("Coordonnateur régionale", "Traitement",
                          "Expert survey", "Superviseur Technique")


def equipe_technique_district(conn, code_district):
    """Personnel (comptes) affecté à un district, groupé par rôle.

    Renvoie une liste ordonnée [(role, [comptes...]), ...] pour les rôles de
    ROLES_EQUIPE_TECHNIQUE ayant au moins une personne rattachée au district —
    soit par `district_affectation` (rôles mono-district), soit par la liaison
    `responsable_district` (rôles multi-district, ex. Coordonnateur régionale).
    Chaque compte a la forme de `lister()` (nom, login, contact, communes)."""
    try:
        code = int(code_district)
    except (TypeError, ValueError):
        return []
    par_role = {r: [] for r in ROLES_EQUIPE_TECHNIQUE}
    for u in lister(conn):
        role = u.get("responsabilite")
        if role not in par_role:
            continue
        da = u.get("district_affectation")
        da = int(da) if da is not None and str(da).isdigit() else None
        dists = {int(d) for d in (u.get("districts_affectation") or [])
                 if str(d).isdigit()}
        if da == code or code in dists:
            par_role[role].append(u)
    for r in par_role:
        par_role[r].sort(key=lambda x: (x.get("nom_prenom") or x.get("login") or ""))
    # Noms des communes d'affectation des Superviseurs Techniques : sert à nommer
    # leur « axe de supervision » (regroupement par zone dans la fiche). On résout
    # une seule fois chaque code -> libellé.
    noms_communes = {}
    for u in par_role.get("Superviseur Technique", []):
        for cc in (u.get("communes_affectation") or []):
            if cc not in noms_communes:
                noms_communes[cc] = zones.libelle_commune(conn, cc) or str(cc)
        u["communes_noms"] = [noms_communes[cc]
                              for cc in (u.get("communes_affectation") or [])]
    return [(r, par_role[r]) for r in ROLES_EQUIPE_TECHNIQUE if par_role[r]]


def authentifier(conn, login: str, mot_de_passe: str):
    """Renvoie {login, nom_prenom, responsabilite (libellé), code_responsable,
    district_affectation, communes_affectation, districts_affectation} si
    identifiants valides ET compte actif, sinon None. Sert au /login (l'affectation
    servira au filtrage du dashboard)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT u."nom_prenom",r."libelle_responsable",u."mot_de_passe",'
                'u."actif",u."district_affectation",u."code_responsable" '
                'FROM "utilisateurs" u LEFT JOIN "responsabilite" r '
                'ON u."code_responsable"=r."code_responsable" '
                f'WHERE u."login"={ph}', ((login or "").strip(),))
    row = cur.fetchone()
    if not row:
        return None
    nom_prenom, libelle, condense, actif, district, code = row
    if not actif or not verifier(mot_de_passe, condense):
        return None
    lg = login.strip()
    return {"login": lg, "nom_prenom": nom_prenom,
            "responsabilite": libelle or LIBELLE_PAR_CODE.get(code, ""),
            "code_responsable": code, "district_affectation": district,
            "communes_affectation": _communes_de(conn, lg),
            "districts_affectation": _districts_de(conn, lg)}


def raison_echec(conn, login: str, mot_de_passe: str):
    """Motif d'un échec de connexion, pour le JOURNAL admin (jamais montré à l'usager) :
    'identifiant inconnu' / 'compte désactivé' / 'mot de passe incorrect', ou None si
    les identifiants sont en fait valides."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT "mot_de_passe","actif" FROM "utilisateurs" '
                f'WHERE "login"={ph}', ((login or "").strip(),))
    row = cur.fetchone()
    if not row:
        return "identifiant inconnu"
    condense, actif = row
    if not actif:
        return "compte désactivé"
    if not verifier(mot_de_passe, condense):
        return "mot de passe incorrect"
    return None


def affectation_texte(conn, district, communes, districts=None) -> str:
    """Libellé lisible d'une affectation (pour l'affichage/CLI).

    `communes`/`districts` : listes de codes (ou chaîne 'a,b'). Un rôle
    « multi-district » a `districts` rempli (et `district` None)."""
    dcodes = _normaliser_communes(districts)
    if dcodes:                                         # rôle multi-district
        noms = []
        for dc in dcodes:
            lib = zones.libelles_district(conn, dc)
            noms.append(lib[2] if lib else str(dc))
        mot = "district" if len(noms) == 1 else "districts"
        return f"{len(noms)} {mot} : {', '.join(noms)}"
    if not district:
        return "Toute la zone"
    lib = zones.libelles_district(conn, district)
    nd = lib[2] if lib else district
    codes = _normaliser_communes(communes)
    if not codes:
        return f"District {nd} (toutes communes)"
    noms = [zones.libelle_commune(conn, c) or str(c) for c in codes]
    mot = "commune" if len(noms) == 1 else "communes"
    return f"District {nd} / {mot} : {', '.join(noms)}"


def assurer_bootstrap(conn) -> bool:
    """Si la table est VIDE, crée le compte d'amorçage (RSU/RSU). Renvoie True si créé.
    À appeler au démarrage du serveur pour ne jamais être verrouillé dehors."""
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM "utilisateurs"')
    if cur.fetchone()[0] == 0:
        ajouter(conn, actif=True, **_BOOTSTRAP)
        return True
    return False


# ---------------------------------------------------------------------------
# CLI de gestion (mot de passe saisi au clavier, jamais en argument shell)
# ---------------------------------------------------------------------------
def _choisir_responsabilite() -> str:
    print("Responsabilité :")
    for i, r in enumerate(RESPONSABILITES, 1):
        print(f"  {i}. {r}")
    while True:
        c = input(f"Numéro (1-{len(RESPONSABILITES)}) : ").strip()
        if c.isdigit() and 1 <= int(c) <= len(RESPONSABILITES):
            return RESPONSABILITES[int(c) - 1]
        print("  Choix invalide.")


def _choisir_geo(liste, label) -> str:
    """Choix dans une liste [{code, nom}] par code exact ou par nom (sous-chaîne)."""
    while True:
        s = input(f"{label} (nom ou code, ? pour lister) : ").strip()
        if s in ("", "?"):
            for e in liste:
                print(f"   {e['code']:>8}  {e['nom']}")
            continue
        for e in liste:
            if e["code"] == s:
                return e["code"]
        cand = [e for e in liste if s.lower() in e["nom"].lower()]
        if len(cand) == 1:
            return cand[0]["code"]
        if not cand:
            print("   Aucun résultat, réessayez.")
        else:
            print("   Plusieurs correspondances — précisez :")
            for e in cand[:20]:
                print(f"   {e['code']:>8}  {e['nom']}")


def _choisir_communes(conn, district, maxi):
    """Choisit de 1 à `maxi` communes du district (codes)."""
    dispo = zones.communes_district(conn, district)
    choisies = []
    print(f"Communes d'affectation (1 à {maxi}) :")
    while len(choisies) < maxi:
        restantes = [e for e in dispo if e["code"] not in choisies]
        if not restantes:
            break
        c = _choisir_geo(restantes, f"  Commune #{len(choisies) + 1}")
        choisies.append(c)
        if len(choisies) >= maxi:
            break
        if input("  Ajouter une autre commune ? (o/N) : ").strip().lower() != "o":
            break
    return choisies


def _choisir_districts(conn, maxi):
    """Choisit de 1 à `maxi` districts (codes) pour un rôle multi-district."""
    dispo = zones.tous_districts(conn)
    choisis = []
    print(f"Districts d'affectation (1 à {maxi}) :")
    while len(choisis) < maxi:
        restants = [e for e in dispo if e["code"] not in choisis]
        if not restants:
            break
        d = _choisir_geo(restants, f"  District #{len(choisis) + 1}")
        choisis.append(d)
        if len(choisis) >= maxi:
            break
        if input("  Ajouter un autre district ? (o/N) : ").strip().lower() != "o":
            break
    return choisis


def _saisir_affectation(conn, responsabilite):
    """Renvoie (district, communes, districts) saisis selon le rôle."""
    if responsabilite in _ROLES_ZONE_ENTIERE:
        print("Affectation : toute la zone (aucun district/commune à choisir).")
        return (None, None, None)
    if responsabilite in _ROLES_MULTI_DISTRICT:
        return (None, None, _choisir_districts(conn, MAX_DISTRICTS))
    d = _choisir_geo(zones.tous_districts(conn), "District d'affectation")
    if responsabilite in _ROLES_UN_DISTRICT:
        print("Affectation : tout le district (toutes ses communes).")
        return (d, None, None)
    # District + 1 à MAX_COMMUNES_SUPERVISEUR communes.
    return (d, _choisir_communes(conn, d, MAX_COMMUNES_SUPERVISEUR), None)


def _saisir_coordonnees():
    """Saisit téléphone / CIN / e-mail / n° Orange (Float) — tous facultatifs,
    revalidés à chaque essai."""
    tel = input("Téléphone (facultatif) : ").strip()
    cin = input("CIN — 12 chiffres (facultatif) : ").strip()
    email = input("Adresse e-mail (facultatif) : ").strip()
    orange = input("Numéro Orange - Float (facultatif) : ").strip()
    valider_coordonnees(tel, cin, email, orange)   # lève ValueError si invalide
    return (tel or None, cin or None, email or None, orange or None)


def _saisir_mot_de_passe() -> str:
    while True:
        p1 = getpass.getpass("Mot de passe : ")
        if len(p1) < 4:
            print("  Trop court (4 caractères minimum).")
            continue
        p2 = getpass.getpass("Confirmer     : ")
        if p1 != p2:
            print("  Les deux saisies diffèrent.")
            continue
        return p1


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "list"
    conn = db_source.connect()
    try:
        creer_table(conn)
        if cmd == "init":
            cree = assurer_bootstrap(conn)
            conn.commit()
            print("Table « utilisateurs » prête.")
            if cree:
                print("ATTENTION : compte d'amorcage cree : RSU / RSU -- CHANGEZ-LE "
                      "tout de suite (python utilisateurs.py passwd RSU).")
        elif cmd == "add":
            zones.assurer_zones(conn)        # référentiel géo pour les listes
            login = input("Login : ").strip()
            nom = input("Nom et prénom : ").strip()
            resp = _choisir_responsabilite()
            tel, cin, email, orange = _saisir_coordonnees()
            district, commune, districts = _saisir_affectation(conn, resp)
            mdp = _saisir_mot_de_passe()
            ajouter(conn, login, nom, resp, mdp,
                    district_affectation=district, commune_affectation=commune,
                    districts_affectation=districts,
                    telephone=tel, cin=cin, email=email,
                    numero_orange_float=orange)
            conn.commit()
            print(f"Utilisateur « {login} » ajouté ({resp} — "
                  f"{affectation_texte(conn, district, commune, districts)}).")
        elif cmd == "list":
            comptes = lister(conn)
            if not comptes:
                print("(aucun utilisateur)")
            for u in comptes:
                etat = "actif" if u["actif"] else "DÉSACTIVÉ"
                aff = affectation_texte(conn, u["district_affectation"],
                                        u["communes_affectation"],
                                        u["districts_affectation"])
                print(f'  {u["login"]:<16} {u["responsabilite"]:<22} {etat:<10} '
                      f'{u["nom_prenom"]:<24} {aff}')
        elif cmd == "passwd" and len(args) >= 2:
            if not _existe(conn, args[1]):
                print(f"Login inconnu : {args[1]}"); return 1
            changer_mot_de_passe(conn, args[1], _saisir_mot_de_passe())
            conn.commit()
            print(f"Mot de passe de « {args[1]} » modifié.")
        elif cmd == "actif" and len(args) >= 3 and args[2] in ("on", "off"):
            if definir_actif(conn, args[1], args[2] == "on"):
                conn.commit()
                print(f"« {args[1]} » : {'activé' if args[2]=='on' else 'désactivé'}.")
            else:
                print(f"Login inconnu : {args[1]}"); return 1
        elif cmd == "del" and len(args) >= 2:
            if supprimer(conn, args[1]):
                conn.commit()
                print(f"Utilisateur « {args[1]} » supprimé.")
            else:
                print(f"Login inconnu : {args[1]}"); return 1
        else:
            print(__doc__)
            return 1
    except ValueError as e:
        print("Erreur :", e)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
