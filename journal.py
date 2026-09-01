# -*- coding: utf-8 -*-
"""
journal.py — Journal de connexion / d'utilisation (audit) et tentatives échouées.

Deux tables dans la MÊME base (via db_source.connect()) :

    journal_connexion(jeton, login, nom_prenom, responsabilite, ip,
                      connexion_le, derniere_activite, deconnexion_le)
        1 ligne par session. Durée = (deconnexion_le ou derniere_activite) - connexion_le.

    tentative_connexion(login_saisi, quand, motif, ip)
        1 ligne par échec de connexion (identifiant inconnu / mot de passe / désactivé).

Une 3e table sert de JOURNAL DE BORD (activités quotidiennes) :

    journal_activite(id, login, nom_prenom, fonction, zone, code_district,
                     date_jour, journal, cree_le)
        1 ligne par ÉCRITURE. L'équipe technique (hors coordonnateurs) y consigne
        chaque jour ses activités ; les coordonnateurs (National/Régional) et
        l'Admin la LISENT, bornés à leur périmètre (`activites`).

Aucun mot de passe n'est stocké ici (uniquement des données de connexion).
Portable SQLite / PostgreSQL (DB-API 2.0, placeholder via db_source).
"""
import datetime
import secrets

import db_source


def _maintenant() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def aujourdhui() -> str:
    """Date du jour au format ISO « AAAA-MM-JJ » (clé de `date_jour`)."""
    return datetime.date.today().isoformat()


def fmt_quand(iso) -> str:
    """Horodatage ISO -> « JJ/MM/AAAA HH:MM » (date + heure + minute), ou l'entrée
    telle quelle si non analysable. Sert à l'affichage de l'historique."""
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso or "—"


def fmt_jour(iso) -> str:
    """Date ISO « AAAA-MM-JJ » -> « JJ/MM/AAAA », ou l'entrée telle quelle."""
    try:
        return datetime.date.fromisoformat(iso).strftime("%d/%m/%Y")
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
    # Journal de bord (activités quotidiennes) : 1 ligne par écriture. `id` est un
    # jeton généré côté Python (portable SQLite/PostgreSQL, pas d'auto-incrément).
    # `code_district` = codes des districts du périmètre, séparés par des virgules
    # (sert au filtrage de LECTURE du Coordonnateur régional, borné à ses districts).
    cur.execute(
        'CREATE TABLE IF NOT EXISTS "journal_activite" ('
        '"id" TEXT PRIMARY KEY, "login" TEXT, "nom_prenom" TEXT, '
        '"fonction" TEXT, "zone" TEXT, "code_district" TEXT, '
        '"date_jour" TEXT, "journal" TEXT, "cree_le" TEXT)')
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


# ---------------------------------------------------------------------------
# Journal de bord (activités quotidiennes) : écriture par l'équipe technique,
# lecture par les coordonnateurs / l'Admin.
# ---------------------------------------------------------------------------
def ecrire_activite(conn, login, nom_prenom, fonction, zone, code_district,
                    date_jour, texte) -> None:
    """Consigne UNE entrée de journal de bord (plusieurs entrées/jour permises)."""
    ph = db_source._placeholder(conn)
    conn.cursor().execute(
        'INSERT INTO "journal_activite" ("id","login","nom_prenom","fonction",'
        '"zone","code_district","date_jour","journal","cree_le") '
        f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (secrets.token_hex(16), login, nom_prenom, fonction, zone,
         str(code_district or ""), date_jour, texte, _maintenant()))
    conn.commit()


def a_ecrit_le(conn, login, date_jour) -> bool:
    """Vrai si `login` a AU MOINS une entrée de journal pour `date_jour`.
    Sert à la bulle de rappel (« vous n'avez pas écrit aujourd'hui »)."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM "journal_activite" '
                f'WHERE "login"={ph} AND "date_jour"={ph}', (login, date_jour))
    return cur.fetchone() is not None


def mes_activites(conn, login, limite=100):
    """Mes propres entrées de journal (plus récente d'abord). Page d'écriture."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute('SELECT "date_jour","zone","journal","cree_le","fonction","nom_prenom" '
                'FROM "journal_activite" '
                f'WHERE "login"={ph} ORDER BY "date_jour" DESC, "cree_le" DESC',
                (login,))
    out = []
    for r in cur.fetchall()[:limite]:
        out.append({"date_jour": r[0], "date_court": fmt_jour(r[0]),
                    "zone": r[1], "journal": r[2],
                    "cree_le": r[3], "cree_court": fmt_quand(r[3]),
                    "fonction": r[4], "nom_prenom": r[5]})
    return out


def activites(conn, districts=None, date_jour=None, login=None,
              district=None, fonction=None, zone=None, nom=None, limite=1000):
    """Journaux de bord pour la LECTURE (coordonnateurs / Admin), récents d'abord.

    `districts` : None = tous les journaux (Coordonnateur Nationale, Admin) ;
    un ensemble de codes = ne garde que les journaux dont `code_district` recoupe
    cet ensemble (Coordonnateur régionale, borné à SES districts). Filtres en plus
    (facultatifs) : `date_jour` (exact), `login` (exact), `district` (UN code : le
    journal doit couvrir ce district), `fonction` (exact), `zone` (exact),
    `nom` (sous-chaîne insensible à la casse sur nom_prenom)."""
    ph = db_source._placeholder(conn)
    clauses, params = [], []
    if date_jour:
        clauses.append(f'"date_jour"={ph}')
        params.append(date_jour)
    if login:
        clauses.append(f'"login"={ph}')
        params.append(login)
    if fonction:
        clauses.append(f'"fonction"={ph}')
        params.append(fonction)
    if zone:
        clauses.append(f'"zone"={ph}')
        params.append(zone)
    if nom:
        clauses.append(f'LOWER("nom_prenom") LIKE {ph}')
        params.append("%" + nom.strip().lower() + "%")
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    cur = conn.cursor()
    cur.execute('SELECT "login","nom_prenom","fonction","zone","code_district",'
                '"date_jour","journal","cree_le" FROM "journal_activite"'
                + where + ' ORDER BY "date_jour" DESC, "cree_le" DESC', tuple(params))
    dset = {str(d) for d in districts} if districts is not None else None
    dcode = str(district) if district not in (None, "") else None
    out = []
    for r in cur.fetchall():
        codes = {c for c in (r[4] or "").replace(" ", "").split(",") if c}
        if dset is not None and not (codes & dset):
            continue
        if dcode is not None and dcode not in codes:
            continue
        out.append({"login": r[0], "nom_prenom": r[1], "fonction": r[2],
                    "zone": r[3], "code_district": r[4],
                    "date_jour": r[5], "date_court": fmt_jour(r[5]),
                    "journal": r[6], "cree_le": r[7], "cree_court": fmt_quand(r[7])})
        if len(out) >= limite:
            break
    return out


def dates_ecrites(conn, logins=None):
    """{login: ensemble des date_jour écrites} pour le suivi de complétude du
    journal. `logins` : None = tous ; sinon restreint à cet ensemble de logins.
    (On lit toute la table puis on filtre en Python -> pas de limite IN SQLite.)"""
    cur = conn.cursor()
    cur.execute('SELECT "login","date_jour" FROM "journal_activite"')
    keep = set(logins) if logins is not None else None
    out = {}
    for lg, d in cur.fetchall():
        if keep is not None and lg not in keep:
            continue
        if d:
            out.setdefault(lg, set()).add(d)
    return out


def options_lecture(conn, districts=None):
    """Valeurs DISTINCTES présentes dans les journaux du périmètre (pour peupler
    les listes déroulantes des filtres de lecture) : {fonctions, zones, noms}.
    `districts` borne au périmètre du lecteur (comme `activites`)."""
    lignes = activites(conn, districts=districts, limite=1000000)
    return {
        "fonctions": sorted({l["fonction"] for l in lignes if l["fonction"]}),
        "zones": sorted({l["zone"] for l in lignes if l["zone"]}),
        "noms": sorted({l["nom_prenom"] for l in lignes if l["nom_prenom"]}),
    }
