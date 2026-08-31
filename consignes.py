# -*- coding: utf-8 -*-
"""
consignes.py — Consignes / instructions données par les Coordonnateurs.

Un Coordonnateur (National ou régional) rédige une CONSIGNE et choisit :
  - les RÔLES destinataires (« Tout le monde » ou une sélection de rôles) ;
  - les DISTRICTS concernés (« Tous » ou une sélection).
Chaque destinataire (dont le rôle ET le district correspondent) la reçoit :
une BULLE d'info l'avertit des consignes non lues ; l'ouverture les marque lues.

Deux tables (même base que le reste, via db_source) :

    consigne(id, auteur_login, auteur_nom, auteur_role, roles_cibles,
             districts_cibles, titre, message, cree_le)
        roles_cibles     : 'TOUS' ou libellés séparés par « | ».
        districts_cibles : 'TOUS' ou codes de district séparés par « , ».

    consigne_lecture(consigne_id, login, lu_le)   -- 1 ligne = « login a lu »
        clé primaire (consigne_id, login).

Portable SQLite / PostgreSQL (DB-API 2.0, placeholder via db_source).
"""
import datetime
import secrets

import db_source

TOUS = "TOUS"          # valeur sentinelle : « tous les rôles » / « tous les districts »


def _maintenant() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def fmt_quand(iso) -> str:
    """Horodatage ISO -> « JJ/MM/AAAA HH:MM », ou l'entrée telle quelle."""
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso or "—"


def creer_tables(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        'CREATE TABLE IF NOT EXISTS "consigne" ('
        '"id" TEXT PRIMARY KEY, "auteur_login" TEXT, "auteur_nom" TEXT, '
        '"auteur_role" TEXT, "roles_cibles" TEXT, "districts_cibles" TEXT, '
        '"titre" TEXT, "message" TEXT, "cree_le" TEXT)')
    cur.execute(
        'CREATE TABLE IF NOT EXISTS "consigne_lecture" ('
        '"consigne_id" TEXT, "login" TEXT, "lu_le" TEXT, '
        'PRIMARY KEY ("consigne_id","login"))')
    conn.commit()


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
def envoyer(conn, auteur_login, auteur_nom, auteur_role,
            roles_cibles, districts_cibles, titre, message) -> str:
    """Enregistre une consigne. `roles_cibles`/`districts_cibles` : la sentinelle
    TOUS, ou un itérable de valeurs (jointes par « | » / « , »). Renvoie l'id."""
    roles, dists = _cibles_txt(roles_cibles, districts_cibles)
    cid = secrets.token_hex(16)
    ph = db_source._placeholder(conn)
    conn.cursor().execute(
        'INSERT INTO "consigne" ("id","auteur_login","auteur_nom","auteur_role",'
        '"roles_cibles","districts_cibles","titre","message","cree_le") '
        f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (cid, auteur_login, auteur_nom, auteur_role, roles, dists,
         titre or "", message, _maintenant()))
    conn.commit()
    return cid


# ---------------------------------------------------------------------------
# Ciblage : une consigne concerne-t-elle un utilisateur ?
# ---------------------------------------------------------------------------
def _concerne(role, districts, roles_cibles, districts_cibles) -> bool:
    """Vrai si un utilisateur (role, ensemble de districts) est destinataire.

    `districts` = ensemble de codes (str/int) ou None (pas d'affectation / zone
    entière) : un ciblage district PRÉCIS ne concerne pas un utilisateur sans
    district ; un ciblage TOUS le concerne (si le rôle correspond)."""
    if roles_cibles != TOUS:
        if role not in set(roles_cibles.split("|")):
            return False
    if districts_cibles != TOUS:
        cibles = {c for c in districts_cibles.split(",") if c}
        if not districts:
            return False
        if not ({str(d) for d in districts} & cibles):
            return False
    return True


def _lignes(conn, limite=500):
    cur = conn.cursor()
    cur.execute('SELECT "id","auteur_login","auteur_nom","auteur_role",'
                '"roles_cibles","districts_cibles","titre","message","cree_le" '
                'FROM "consigne" ORDER BY "cree_le" DESC')
    return cur.fetchall()[:limite]


def _ids_lus(conn, login) -> set:
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "consigne_id" FROM "consigne_lecture" WHERE "login"={ph}',
                (login,))
    return {r[0] for r in cur.fetchall()}


def pour_utilisateur(conn, login, role, districts, limite=200):
    """Consignes destinées à cet utilisateur (plus récente d'abord), chacune avec
    un champ `lu` (bool). `districts` = ensemble de codes ou None."""
    lus = _ids_lus(conn, login)
    out = []
    for r in _lignes(conn):
        if not _concerne(role, districts, r[4], r[5]):
            continue
        out.append({
            "id": r[0], "auteur_login": r[1], "auteur_nom": r[2],
            "auteur_role": r[3], "roles_cibles": r[4], "districts_cibles": r[5],
            "titre": r[6], "message": r[7], "cree_le": r[8],
            "cree_court": fmt_quand(r[8]), "lu": r[0] in lus})
        if len(out) >= limite:
            break
    return out


def non_lues(conn, login, role, districts) -> int:
    """Nombre de consignes destinées à l'utilisateur et NON encore lues."""
    return sum(1 for c in pour_utilisateur(conn, login, role, districts)
               if not c["lu"])


def marquer_toutes_lues(conn, login, role, districts) -> int:
    """Marque lues toutes les consignes destinées à l'utilisateur (à l'ouverture
    de la page). Renvoie le nombre nouvellement marqué."""
    lus = _ids_lus(conn, login)
    ph = db_source._placeholder(conn)
    now = _maintenant()
    cur = conn.cursor()
    n = 0
    for c in pour_utilisateur(conn, login, role, districts):
        if c["id"] in lus:
            continue
        cur.execute('INSERT INTO "consigne_lecture" ("consigne_id","login","lu_le") '
                    f"VALUES ({ph},{ph},{ph})", (c["id"], login, now))
        n += 1
    if n:
        conn.commit()
    return n


def _cibles_txt(roles_cibles, districts_cibles):
    """Normalise (roles, districts) vers leur forme stockée : TOUS ou jointure."""
    roles = TOUS if roles_cibles == TOUS else "|".join(str(r) for r in roles_cibles)
    dists = (TOUS if districts_cibles == TOUS
             else ",".join(str(d) for d in districts_cibles))
    return roles, dists


def obtenir(conn, consigne_id):
    """Renvoie une consigne (dict) par son id, ou None. Sert au pré-remplissage
    du formulaire de modification."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT "id","auteur_login","auteur_nom","auteur_role",'
                '"roles_cibles","districts_cibles","titre","message","cree_le" '
                f'FROM "consigne" WHERE "id"={ph}', (consigne_id,))
    r = cur.fetchone()
    if not r:
        return None
    return {"id": r[0], "auteur_login": r[1], "auteur_nom": r[2],
            "auteur_role": r[3], "roles_cibles": r[4], "districts_cibles": r[5],
            "titre": r[6], "message": r[7], "cree_le": r[8],
            "cree_court": fmt_quand(r[8])}


def modifier(conn, consigne_id, auteur_login, roles_cibles, districts_cibles,
             titre, message) -> bool:
    """Met à jour une consigne (destinataires, titre, message) SI `auteur_login`
    en est l'auteur. **Réinitialise les accusés de lecture** : la consigne modifiée
    redevient « non lue » pour ses destinataires (ils revoient la version à jour,
    la bulle se ré-affiche). Renvoie True si modifiée, False sinon."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "auteur_login" FROM "consigne" WHERE "id"={ph}',
                (consigne_id,))
    row = cur.fetchone()
    if not row or row[0] != auteur_login:
        return False
    roles, dists = _cibles_txt(roles_cibles, districts_cibles)
    cur.execute('UPDATE "consigne" SET "roles_cibles"={p},"districts_cibles"={p},'
                '"titre"={p},"message"={p} WHERE "id"={p}'.format(p=ph),
                (roles, dists, titre or "", message, consigne_id))
    cur.execute(f'DELETE FROM "consigne_lecture" WHERE "consigne_id"={ph}',
                (consigne_id,))
    conn.commit()
    return True


def supprimer(conn, consigne_id, auteur_login) -> bool:
    """Supprime une consigne ET ses lectures — SEULEMENT si `auteur_login` en est
    l'auteur (un coordonnateur ne peut retirer que SES propres consignes). Renvoie
    True si une consigne a bien été supprimée, False sinon (inconnue / pas l'auteur)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "auteur_login" FROM "consigne" WHERE "id"={ph}',
                (consigne_id,))
    row = cur.fetchone()
    if not row or row[0] != auteur_login:
        return False
    cur.execute(f'DELETE FROM "consigne_lecture" WHERE "consigne_id"={ph}',
                (consigne_id,))
    cur.execute(f'DELETE FROM "consigne" WHERE "id"={ph}', (consigne_id,))
    conn.commit()
    return True


def envoyees_par(conn, login, limite=200):
    """Consignes émises par `login` (plus récente d'abord)."""
    out = []
    for r in _lignes(conn):
        if r[1] != login:
            continue
        out.append({
            "id": r[0], "auteur_login": r[1], "auteur_nom": r[2],
            "auteur_role": r[3], "roles_cibles": r[4], "districts_cibles": r[5],
            "titre": r[6], "message": r[7], "cree_le": r[8],
            "cree_court": fmt_quand(r[8])})
        if len(out) >= limite:
            break
    return out
