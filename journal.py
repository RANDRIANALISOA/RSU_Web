# -*- coding: utf-8 -*-
"""
journal.py — Journal de connexion / d'utilisation (audit) et tentatives échouées.

Deux tables dans la MÊME base (via db_source.connect()) :

    journal_connexion(jeton, login, nom_prenom, responsabilite, ip,
                      connexion_le, derniere_activite, deconnexion_le)
        1 ligne par session. Durée = (deconnexion_le ou derniere_activite) - connexion_le.

    tentative_connexion(login_saisi, quand, motif, ip)
        1 ligne par échec de connexion (identifiant inconnu / mot de passe / désactivé).

Aucun mot de passe n'est stocké ici (uniquement des données de connexion).
Portable SQLite / PostgreSQL (DB-API 2.0, placeholder via db_source).
"""
import datetime

import db_source


def _maintenant() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def fmt_quand(iso) -> str:
    """Horodatage ISO -> « JJ/MM/AAAA HH:MM » (date + heure + minute), ou l'entrée
    telle quelle si non analysable. Sert à l'affichage de l'historique."""
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso or "—"


def creer_tables(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        'CREATE TABLE IF NOT EXISTS "journal_connexion" ('
        '"jeton" TEXT PRIMARY KEY, "login" TEXT, "nom_prenom" TEXT, '
        '"responsabilite" TEXT, "ip" TEXT, "connexion_le" TEXT, '
        '"derniere_activite" TEXT, "deconnexion_le" TEXT)')
    cur.execute(
        'CREATE TABLE IF NOT EXISTS "tentative_connexion" ('
        '"login_saisi" TEXT, "quand" TEXT, "motif" TEXT, "ip" TEXT)')
    # Historique des transcriptions : 1 ligne par ÉVÉNEMENT (téléversement OU
    # transcription), réussi OU échoué. `evenement`/`statut`/`detail` ajoutés
    # ensuite ; les colonnes ajoutes/modifies/inchanges ne sont remplies que pour
    # une transcription réussie.
    cur.execute(
        'CREATE TABLE IF NOT EXISTS "journal_transcription" ('
        '"login" TEXT, "nom_prenom" TEXT, "district" TEXT, "quand" TEXT, '
        '"evenement" TEXT, "statut" TEXT, "detail" TEXT, '
        '"fichiers" TEXT, "ajoutes" BIGINT, "modifies" BIGINT, "inchanges" BIGINT)')
    _migrer_transcription(conn)
    conn.commit()


def _colonnes(conn, table) -> set:
    """Ensemble des noms de colonnes d'une table (SQLite ou PostgreSQL)."""
    cur = conn.cursor()
    if db_source._est_sqlite(conn):
        cur.execute(f'PRAGMA table_info("{table}")')
        return {r[1] for r in cur.fetchall()}
    cur.execute('SELECT column_name FROM information_schema.columns '
                'WHERE table_name = %s', (table,))
    return {r[0] for r in cur.fetchall()}


def _migrer_transcription(conn) -> None:
    """Ajoute les colonnes evenement/statut/detail aux bases antérieures (où
    `journal_transcription` n'avait que le bilan des transcriptions réussies)."""
    cols = _colonnes(conn, "journal_transcription")
    if not cols:                       # table absente : creer_tables s'en charge
        return
    for col in ("evenement", "statut", "detail"):
        if col not in cols:
            conn.cursor().execute(
                f'ALTER TABLE "journal_transcription" ADD COLUMN "{col}" TEXT')


def ouvrir(conn, jeton, login, nom_prenom, responsabilite, ip="") -> None:
    """Enregistre le début d'une session (à la connexion réussie)."""
    ph = db_source._placeholder(conn)
    now = _maintenant()
    conn.cursor().execute(
        'INSERT INTO "journal_connexion" ("jeton","login","nom_prenom",'
        '"responsabilite","ip","connexion_le","derniere_activite","deconnexion_le") '
        f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},NULL)",
        (jeton, login, nom_prenom, responsabilite, ip, now, now))
    conn.commit()


def toucher(conn, jeton) -> None:
    """Met à jour la dernière activité d'une session encore ouverte."""
    ph = db_source._placeholder(conn)
    conn.cursor().execute(
        f'UPDATE "journal_connexion" SET "derniere_activite"={ph} '
        f'WHERE "jeton"={ph} AND "deconnexion_le" IS NULL', (_maintenant(), jeton))
    conn.commit()


def fermer(conn, jeton) -> None:
    """Clôt une session (à la déconnexion) -> fige la durée."""
    ph = db_source._placeholder(conn)
    now = _maintenant()
    conn.cursor().execute(
        f'UPDATE "journal_connexion" SET "deconnexion_le"={ph}, '
        f'"derniere_activite"={ph} WHERE "jeton"={ph} AND "deconnexion_le" IS NULL',
        (now, now, jeton))
    conn.commit()


def tentative(conn, login_saisi, motif, ip="") -> None:
    """Enregistre une tentative de connexion échouée."""
    ph = db_source._placeholder(conn)
    conn.cursor().execute(
        'INSERT INTO "tentative_connexion" ("login_saisi","quand","motif","ip") '
        f"VALUES ({ph},{ph},{ph},{ph})", (login_saisi, _maintenant(), motif, ip))
    conn.commit()


# ---------------------------------------------------------------------------
# Lectures (pour la page Admin)
# ---------------------------------------------------------------------------
def _duree(debut, fin) -> str:
    """Durée lisible H:MM:SS entre deux horodatages ISO, ou '—'."""
    try:
        d = datetime.datetime.fromisoformat(debut)
        f = datetime.datetime.fromisoformat(fin)
    except (TypeError, ValueError):
        return "—"
    s = max(0, int((f - d).total_seconds()))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def journal(conn, limite=200):
    """Sessions récentes (plus récente d'abord) avec durée et statut calculés."""
    cur = conn.cursor()
    cur.execute('SELECT "login","nom_prenom","responsabilite","ip","connexion_le",'
                '"derniere_activite","deconnexion_le" FROM "journal_connexion" '
                'ORDER BY "connexion_le" DESC')
    out = []
    for login, nom, resp, ip, cnx, act, dcx in cur.fetchall()[:limite]:
        fin = dcx or act
        out.append({
            "login": login, "nom_prenom": nom, "responsabilite": resp, "ip": ip,
            "connexion_le": cnx, "deconnexion_le": dcx,
            "duree": _duree(cnx, fin),
            "statut": "terminée" if dcx else "en cours",
        })
    return out


def tentatives(conn, limite=100):
    """Tentatives de connexion échouées (plus récente d'abord)."""
    cur = conn.cursor()
    cur.execute('SELECT "login_saisi","quand","motif","ip" '
                'FROM "tentative_connexion" ORDER BY "quand" DESC')
    return [{"login_saisi": r[0], "quand": r[1], "motif": r[2], "ip": r[3]}
            for r in cur.fetchall()[:limite]]


def consigner(conn, login, nom_prenom, district, evenement, statut,
              detail="", fichiers="", ajoutes=None, modifies=None,
              inchanges=None) -> None:
    """Consigne UN événement d'ingestion (qui, quand, district, issue).

    `evenement` : « Téléversement » ou « Transcription ».
    `statut`    : « Réussi » ou « Échec ».
    `detail`    : message lisible (fichiers reçus, ou motif du refus).
    Les compteurs ajoutes/modifies/inchanges ne sont donnés que pour une
    transcription réussie (None sinon)."""
    ph = db_source._placeholder(conn)
    conn.cursor().execute(
        'INSERT INTO "journal_transcription" ("login","nom_prenom","district",'
        '"quand","evenement","statut","detail","fichiers","ajoutes","modifies",'
        '"inchanges") '
        f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (login, nom_prenom, str(district), _maintenant(), evenement, statut,
         detail, fichiers, ajoutes, modifies, inchanges))
    conn.commit()


def transcriptions(conn, limite=100, login=None):
    """Historique des transcriptions (plus récente d'abord).

    `login` : si fourni, ne renvoie que les événements de cet utilisateur (page
    Expert). Les anciennes lignes (avant les colonnes evenement/statut) sont
    interprétées comme une « Transcription » « Réussi »."""
    ph = db_source._placeholder(conn)
    where = f' WHERE "login" = {ph}' if login else ''
    params = (login,) if login else ()
    cur = conn.cursor()
    cur.execute('SELECT "login","nom_prenom","district","quand","evenement",'
                '"statut","detail","fichiers","ajoutes","modifies","inchanges" '
                'FROM "journal_transcription"' + where +
                ' ORDER BY "quand" DESC', params)
    out = []
    for r in cur.fetchall()[:limite]:
        out.append({
            "login": r[0], "nom_prenom": r[1], "district": r[2], "quand": r[3],
            "quand_court": fmt_quand(r[3]),
            "evenement": r[4] or "Transcription",     # anciennes lignes
            "statut": r[5] or "Réussi",
            "detail": r[6] or r[7] or "",             # detail, sinon fichiers
            "fichiers": r[7], "ajoutes": r[8], "modifies": r[9], "inchanges": r[10]})
    return out
