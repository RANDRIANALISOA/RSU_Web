# -*- coding: utf-8 -*-
"""sessions.py — les sessions vivent en BASE, plus en mémoire du processus.

POURQUOI
    `serveur_app._SESSIONS` était un dictionnaire de module. Deux conséquences :

    1. **Un seul processus possible.** Avec plusieurs processus (gunicorn), un
       utilisateur identifié par l'un serait inconnu de l'autre : déconnexions
       aléatoires à chaque requête. C'est ce qui interdisait d'exploiter plus
       d'un cœur — un processus Python n'exécute du bytecode que sur un cœur à
       la fois (GIL), donc 15 cœurs n'auraient rien apporté.
    2. **Tout redémarrage déconnectait tout le monde.** Ce n'est plus le cas.

CE QUI EST STOCKÉ
    Le dictionnaire de session, tel quel, en JSON : `login`, `utilisateur`,
    `selection`, `vad_district`, `_consignes_modale`… La dernière activité
    (`_vu`) est une COLONNE, pas du JSON : c'est le seul champ écrit à chaque
    requête, et on veut pouvoir le filtrer en SQL sans décoder le reste.

ÉCRITURE : EXPLICITE, JAMAIS MAGIQUE
    `lire()` rend un dictionnaire ordinaire. Le modifier ne suffit PAS à le
    persister : l'appelant appelle `ecrire()`. C'est volontaire — un objet qui
    s'enregistre tout seul à chaque affectation rendrait invisibles les écritures
    en base, et il y en a une par requête au maximum.

⚠️ CE MODULE NE VALIDE AUCUN MOT DE PASSE. Il ne fait que conserver une session
   déjà ouverte par `utilisateurs.authentifier()`. Le jeton reste la seule
   preuve d'identité : il n'est ni journalisé ici, ni affiché.
"""
from __future__ import annotations

import json
import time

import db_source

TABLE = "session"


def creer_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{TABLE}" ('
                f'"jeton" TEXT PRIMARY KEY, "login" TEXT, "donnees" TEXT, '
                f'"vu" REAL, "cree" REAL)')
    # Index sur `vu` : la purge et le comptage des sessions actives filtrent
    # dessus à chaque appel de la page d'administration.
    cur.execute(f'CREATE INDEX IF NOT EXISTS ix_session_vu ON "{TABLE}"("vu")')
    conn.commit()


def lire(conn, jeton):
    """Le dictionnaire de session, ou None. `_vu` y est réinjecté.

    Ne juge PAS de l'expiration : c'est l'appelant qui connaît son délai
    d'inactivité, et qui doit aussi clore la session au journal.
    """
    if not jeton:
        return None
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT "donnees","vu" FROM "{TABLE}" WHERE "jeton"={ph}',
                    (jeton,))
    except Exception:
        creer_table(conn)
        return None
    ligne = cur.fetchone()
    if ligne is None:
        return None
    try:
        sess = json.loads(ligne[0] or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(sess, dict):
        return None
    sess["_vu"] = ligne[1] or 0.0
    sess["jeton"] = jeton
    return sess


def ecrire(conn, jeton, sess) -> None:
    """Enregistre la session. `_vu` va dans sa colonne, pas dans le JSON."""
    if not jeton:
        return
    vu = float(sess.get("_vu") or time.time())
    donnees = {k: v for k, v in sess.items() if k != "_vu"}
    # `default=str` : une valeur inattendue (date, Decimal) ne doit pas faire
    # perdre sa session a quelqu'un.
    texte = json.dumps(donnees, ensure_ascii=False, default=str)
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    for essai in (1, 2):
        try:
            cur.execute(
                f'INSERT INTO "{TABLE}" ("jeton","login","donnees","vu","cree") '
                f'VALUES ({ph},{ph},{ph},{ph},{ph}) '
                f'ON CONFLICT("jeton") DO UPDATE SET '
                f'"login"=excluded."login", "donnees"=excluded."donnees", '
                f'"vu"=excluded."vu"',
                (jeton, sess.get("login") or "", texte, vu, time.time()))
            conn.commit()
            return
        except Exception:
            if essai == 1:
                creer_table(conn)
                continue
            raise


def toucher(conn, jeton, quand=None) -> None:
    """N'écrit QUE la dernière activité — le cas courant, une fois par requête.
    Réécrire tout le JSON pour un horodatage serait du gaspillage."""
    ph = db_source._placeholder(conn)
    try:
        conn.cursor().execute(
            f'UPDATE "{TABLE}" SET "vu"={ph} WHERE "jeton"={ph}',
            (float(quand or time.time()), jeton))
        conn.commit()
    except Exception:
        pass


def supprimer(conn, jeton) -> None:
    if not jeton:
        return
    ph = db_source._placeholder(conn)
    try:
        conn.cursor().execute(f'DELETE FROM "{TABLE}" WHERE "jeton"={ph}',
                              (jeton,))
        conn.commit()
    except Exception:
        pass


def compter(conn, inactivite_max) -> int:
    """Sessions encore valides. Remplace `len(_SESSIONS)`, qui comptait aussi
    les sessions expirées tant que personne n'y retouchait."""
    ph = db_source._placeholder(conn)
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{TABLE}" WHERE "vu" >= {ph}',
                    (time.time() - inactivite_max,))
        return int(cur.fetchone()[0] or 0)
    except Exception:
        return 0


def purger(conn, inactivite_max) -> int:
    """Efface les sessions expirées. Sans cela la table grossirait sans fin :
    personne ne revient fermer une session abandonnée."""
    ph = db_source._placeholder(conn)
    try:
        cur = conn.cursor()
        cur.execute(f'DELETE FROM "{TABLE}" WHERE "vu" < {ph}',
                    (time.time() - inactivite_max,))
        n = max(cur.rowcount, 0)
        conn.commit()
        return n
    except Exception:
        return 0
