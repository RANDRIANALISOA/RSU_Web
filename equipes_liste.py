# -*- coding: utf-8 -*-
"""
equipes_liste.py — Consulter, modifier et supprimer les Chefs d'Équipe et les
Agents Enquêteurs d'un district.

Ouvert à trois rôles (route /equipes) :
  • **Admin**          — tous les districts, plus les fiches sans district ;
  • **Traitement**     — son district d'affectation, et lui seul ;
  • **Expert survey**  — idem.

⚠️ LE PÉRIMÈTRE EST APPLIQUÉ ICI, PAS DANS L'ÉCRAN. Chaque lecture et chaque
écriture repasse par `_districts_autorises()`. Un Traitement qui forgerait une
requête POST sur un agent d'un autre district est refusé — masquer un bouton
n'a jamais protégé une donnée.

Le district vient des colonnes `agent.district_ae` et `chef_equipe.district_ce`
(clés étrangères vers `district`), ajoutées le 2026-09-27. Les fiches dont le
district n'a pas pu être déterminé restent à NULL : elles ne sont visibles que
de l'Admin, via le filtre « district non renseigné » — un district faux se
propagerait silencieusement dans tous les comptages, un district vide se voit.
"""

import html
import re
import urllib.parse

import admin
import db_source
import zones

ESC = html.escape

# Les rôles qui ont accès à cette page. Admin voit tout ; les deux autres sont
# bornés à leur district d'affectation.
ROLES_AUTORISES = ("Admin", "Traitement", "Expert survey")
ROLES_TOUS_DISTRICTS = ("Admin",)

SANS_DISTRICT = "__sans__"          # valeur du filtre « district non renseigné »

# Lignes par page. Sans pagination, la liste des 12 815 agents produisait une
# page de 6,6 Mo : plusieurs minutes de chargement depuis Madagascar, et un
# navigateur à genoux. Le principe du projet est de n'envoyer que ce qui
# s'affiche.
PAR_PAGE = 100


# ── Périmètre ────────────────────────────────────────────────────────────────

def autorise(utilisateur) -> bool:
    return (utilisateur or {}).get("responsabilite") in ROLES_AUTORISES


def _districts_autorises(utilisateur):
    """Codes de district que cet utilisateur a le droit de voir.

    `None` = aucune restriction (Admin). Un ensemble sinon — vide si le compte
    n'a aucune affectation, auquel cas il ne verra rien, ce qui est le
    comportement voulu : sans affectation, pas de périmètre.
    """
    u = utilisateur or {}
    if u.get("responsabilite") in ROLES_TOUS_DISTRICTS:
        return None
    codes = {int(x) for x in (u.get("districts_affectation") or [])}
    if u.get("district_affectation") is not None:
        codes.add(int(u["district_affectation"]))
    return codes


def _peut_toucher(utilisateur, code_district) -> bool:
    """Cet utilisateur peut-il modifier une fiche de ce district ?"""
    permis = _districts_autorises(utilisateur)
    if permis is None:
        return True
    if code_district is None:
        return False            # fiche sans district : Admin seulement
    return int(code_district) in permis


# ── Lecture ──────────────────────────────────────────────────────────────────

def _ph(conn):
    """Marqueur de paramètre : '?' en SQLite, '%s' en PostgreSQL.

    On passe par `db_source._placeholder`, comme `equipes.py` et `zones.py` :
    une seule source de vérité pour toute l'application.
    """
    return db_source._placeholder(conn)


def lister_chefs(conn, districts=None, texte="", district_filtre=""):
    """[{login, nom, district, nb_agents}] triés par login."""
    cur = conn.cursor()
    cur.execute(
        'SELECT c."login_ce", c."nom_prenom_ce", c."district_ce", '
        '       (SELECT COUNT(*) FROM "agent" a WHERE a."login_ce" = c."login_ce") '
        'FROM "chef_equipe" c ORDER BY c."login_ce"')
    lignes = [{"login": r[0] or "", "nom": r[1] or "",
               "district": r[2], "nb_agents": r[3] or 0} for r in cur.fetchall()]
    return _filtrer(lignes, districts, texte, district_filtre)


def lister_agents(conn, districts=None, texte="", district_filtre="", chef=""):
    """[{login, nom, chef_login, chef_nom, district}] triés par login."""
    cur = conn.cursor()
    cur.execute(
        'SELECT a."login_ae", a."nom_prenom_ae", a."login_ce", '
        '       c."nom_prenom_ce", a."district_ae" '
        'FROM "agent" a LEFT JOIN "chef_equipe" c ON c."login_ce" = a."login_ce" '
        'ORDER BY a."login_ae"')
    lignes = [{"login": r[0] or "", "nom": r[1] or "", "chef_login": r[2] or "",
               "chef_nom": r[3] or "", "district": r[4]} for r in cur.fetchall()]
    lignes = _filtrer(lignes, districts, texte, district_filtre)
    if chef:
        lignes = [l for l in lignes if l["chef_login"] == chef]
    return lignes


def _filtrer(lignes, districts, texte, district_filtre):
    # 1) Le périmètre du rôle — non négociable.
    if districts is not None:
        lignes = [l for l in lignes
                  if l["district"] is not None and int(l["district"]) in districts]
    # 2) Le filtre choisi à l'écran.
    if district_filtre == SANS_DISTRICT:
        lignes = [l for l in lignes if l["district"] is None]
    elif district_filtre:
        lignes = [l for l in lignes
                  if l["district"] is not None and str(l["district"]) == district_filtre]
    # 3) La recherche libre : login OU nom, sans tenir compte de la casse.
    if texte:
        aiguille = texte.lower()
        lignes = [l for l in lignes
                  if aiguille in l["login"].lower() or aiguille in l["nom"].lower()]
    return lignes


def lire_chef(conn, login):
    cur = conn.cursor()
    cur.execute(f'SELECT "login_ce", "nom_prenom_ce", "district_ce" '
                f'FROM "chef_equipe" WHERE "login_ce" = {_ph(conn)}', (login,))
    r = cur.fetchone()
    return {"login": r[0], "nom": r[1] or "", "district": r[2]} if r else None


def lire_agent(conn, login):
    cur = conn.cursor()
    cur.execute(f'SELECT "login_ae", "nom_prenom_ae", "login_ce", "district_ae" '
                f'FROM "agent" WHERE "login_ae" = {_ph(conn)}', (login,))
    r = cur.fetchone()
    return ({"login": r[0], "nom": r[1] or "", "chef_login": r[2] or "",
             "district": r[3]} if r else None)


# ── Écriture ─────────────────────────────────────────────────────────────────

# Convention de login observée dans la base : PRÉFIXE_ZONE_NUMÉRO, par exemple
# CE_MDTR_001 ou EQ1_MDTR_0002. On ne l'IMPOSE pas — une équipe peut avoir ses
# propres codes, et refuser une saisie légitime serait pire qu'un login atypique.
# Mais on la rappelle à l'écran, parce que c'est d'elle que se déduit le district
# quand la colonne n'est pas renseignée.
_RE_LOGIN = re.compile(r"^[A-Za-z0-9_.\-]{3,40}$")


def _valider_login(valeur, deja_pris):
    login = (valeur or "").strip()
    if not _RE_LOGIN.match(login):
        raise ValueError(
            "Login invalide : 3 à 40 caractères, lettres, chiffres, point, "
            "tiret ou souligné uniquement.")
    if deja_pris:
        raise ValueError(f"Le login « {login} » existe déjà.")
    return login


def _district_obligatoire(conn, utilisateur, valeur):
    """À la CRÉATION, le district est exigé — contrairement à la modification.

    Une fiche créée sans district serait invisible de son propre auteur dès la
    page rechargée : un Traitement ne voit que son district. Autant le refuser
    tout de suite.
    """
    code = _valider_district(conn, utilisateur, valeur, None)
    if code is None:
        raise ValueError("Le district est obligatoire.")
    return code


def ajouter_chef(conn, utilisateur, login, nom, district):
    """Crée un chef d'équipe. Le district est exigé et doit être dans le périmètre."""
    ph = _ph(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT 1 FROM "chef_equipe" WHERE "login_ce" = {ph}',
                ((login or "").strip(),))
    login = _valider_login(login, cur.fetchone() is not None)

    nom = " ".join((nom or "").split())
    if len(nom) < 3:
        raise ValueError("Le nom et prénom sont obligatoires (3 caractères minimum).")
    code = _district_obligatoire(conn, utilisateur, district)

    cur.execute('INSERT INTO "chef_equipe" ("login_ce","nom_prenom_ce",'
                f'"district_ce") VALUES ({ph},{ph},{ph})', (login, nom, code))
    conn.commit()
    return login


def ajouter_agent(conn, utilisateur, login, nom, chef_login, district):
    """Crée un agent enquêteur. Le chef d'équipe est facultatif, le district non."""
    ph = _ph(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT 1 FROM "agent" WHERE "login_ae" = {ph}',
                ((login or "").strip(),))
    login = _valider_login(login, cur.fetchone() is not None)

    nom = " ".join((nom or "").split())
    if len(nom) < 3:
        raise ValueError("Le nom et prénom sont obligatoires (3 caractères minimum).")
    code = _district_obligatoire(conn, utilisateur, district)

    chef_login = (chef_login or "").strip()
    if chef_login:
        chef = lire_chef(conn, chef_login)
        if not chef:
            raise ValueError(f"Chef d'équipe inconnu : {chef_login}.")
        if not _peut_toucher(utilisateur, chef["district"]):
            raise PermissionError("Ce chef d'équipe n'est pas dans votre district.")

    cur.execute('INSERT INTO "agent" ("login_ae","nom_prenom_ae","login_ce",'
                f'"district_ae") VALUES ({ph},{ph},{ph},{ph})',
                (login, nom, chef_login or None, code))
    conn.commit()
    return login


def modifier_chef(conn, utilisateur, login, nom, district):
    fiche = lire_chef(conn, login)
    if not fiche:
        raise ValueError("Chef d'équipe introuvable.")
    if not _peut_toucher(utilisateur, fiche["district"]):
        raise PermissionError("Ce chef d'équipe n'est pas dans votre district.")
    nom = " ".join((nom or "").split())
    if len(nom) < 3:
        raise ValueError("Le nom et prénom sont obligatoires (3 caractères minimum).")
    code = _valider_district(conn, utilisateur, district, fiche["district"])
    ph = _ph(conn)
    conn.cursor().execute(
        f'UPDATE "chef_equipe" SET "nom_prenom_ce" = {ph}, "district_ce" = {ph} '
        f'WHERE "login_ce" = {ph}', (nom, code, login))
    conn.commit()


def modifier_agent(conn, utilisateur, login, nom, chef_login, district):
    fiche = lire_agent(conn, login)
    if not fiche:
        raise ValueError("Agent introuvable.")
    if not _peut_toucher(utilisateur, fiche["district"]):
        raise PermissionError("Cet agent n'est pas dans votre district.")
    nom = " ".join((nom or "").split())
    if len(nom) < 3:
        raise ValueError("Le nom et prénom sont obligatoires (3 caractères minimum).")

    chef_login = (chef_login or "").strip()
    if chef_login:
        chef = lire_chef(conn, chef_login)
        if not chef:
            raise ValueError(f"Chef d'équipe inconnu : {chef_login}.")
        if not _peut_toucher(utilisateur, chef["district"]):
            raise PermissionError("Ce chef d'équipe n'est pas dans votre district.")

    code = _valider_district(conn, utilisateur, district, fiche["district"])
    ph = _ph(conn)
    conn.cursor().execute(
        f'UPDATE "agent" SET "nom_prenom_ae" = {ph}, "login_ce" = {ph}, '
        f'"district_ae" = {ph} WHERE "login_ae" = {ph}',
        (nom, chef_login or None, code, login))
    conn.commit()


def _valider_district(conn, utilisateur, valeur, actuel):
    """Le district demandé, ou l'actuel si le champ est laissé vide.

    Un utilisateur borné ne peut pas déplacer une fiche hors de son périmètre :
    ce serait un moyen détourné de la faire disparaître de sa vue.
    """
    valeur = (str(valeur) if valeur is not None else "").strip()
    if not valeur:
        return actuel
    if not valeur.isdigit():
        raise ValueError("Code district invalide.")
    code = int(valeur)
    cur = conn.cursor()
    cur.execute(f'SELECT 1 FROM "district" WHERE "code_district" = {_ph(conn)}', (code,))
    if not cur.fetchone():
        raise ValueError(f"District inconnu : {code}.")
    if not _peut_toucher(utilisateur, code):
        raise PermissionError("Vous ne pouvez pas affecter une fiche à ce district.")
    return code


def supprimer_chef(conn, utilisateur, login, detacher=False):
    """Supprime un chef d'équipe.

    REFUSE s'il a encore des agents, sauf `detacher=True` — auquel cas les
    agents sont détachés (leur `login_ce` passe à NULL) avant la suppression.
    Supprimer en silence laisserait des agents pointant sur un chef disparu.
    """
    fiche = lire_chef(conn, login)
    if not fiche:
        raise ValueError("Chef d'équipe introuvable.")
    if not _peut_toucher(utilisateur, fiche["district"]):
        raise PermissionError("Ce chef d'équipe n'est pas dans votre district.")

    ph = _ph(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "agent" WHERE "login_ce" = {ph}', (login,))
    rattaches = cur.fetchone()[0]
    if rattaches and not detacher:
        raise ValueError(
            f"{rattaches} agent(s) dépendent encore de ce chef d'équipe. "
            f"Cochez « détacher les agents » pour confirmer.")
    if rattaches:
        cur.execute(f'UPDATE "agent" SET "login_ce" = NULL WHERE "login_ce" = {ph}',
                    (login,))
    cur.execute(f'DELETE FROM "chef_equipe" WHERE "login_ce" = {ph}', (login,))
    conn.commit()
    return rattaches


def supprimer_agent(conn, utilisateur, login):
    fiche = lire_agent(conn, login)
    if not fiche:
        raise ValueError("Agent introuvable.")
    if not _peut_toucher(utilisateur, fiche["district"]):
        raise PermissionError("Cet agent n'est pas dans votre district.")
    conn.cursor().execute(
        f'DELETE FROM "agent" WHERE "login_ae" = {_ph(conn)}', (login,))
    conn.commit()


# ── Écrans ───────────────────────────────────────────────────────────────────

def _noms_districts(conn):
    return {d["code"]: d["nom"] for d in zones.tous_districts(conn)}


def _district_texte(code, noms):
    if code is None:
        return '<span class="pill ko">non renseigné</span>'
    return f'{ESC(noms.get(str(code), "?"))} <small>({code})</small>'


def _options_districts(conn, utilisateur, choisi="", avec_sans=True):
    permis = _districts_autorises(utilisateur)
    out = ['<option value="">— Tous les districts —</option>']
    for d in sorted(zones.tous_districts(conn), key=lambda d: d["nom"]):
        if permis is not None and int(d["code"]) not in permis:
            continue
        sel = " selected" if d["code"] == str(choisi) else ""
        out.append(f'<option value="{d["code"]}"{sel}>{ESC(d["nom"])} ({d["code"]})</option>')
    if avec_sans and permis is None:
        sel = " selected" if choisi == SANS_DISTRICT else ""
        out.append(f'<option value="{SANS_DISTRICT}"{sel}>— District non renseigné —</option>')
    return "".join(out)


def page_liste(conn, utilisateur, onglet="ce", district="", texte="", chef="",
               page=1, message=None, erreur=None) -> str:
    """L'écran principal : deux onglets (chefs d'équipe / agents), filtrés."""
    permis = _districts_autorises(utilisateur)
    noms = _noms_districts(conn)
    onglet = "ae" if onglet == "ae" else "ce"

    if onglet == "ce":
        lignes = lister_chefs(conn, permis, texte, district)
        total = len(lister_chefs(conn, permis))
    else:
        lignes = lister_agents(conn, permis, texte, district, chef)
        total = len(lister_agents(conn, permis))

    # Découpage en pages : on ne rend que la tranche demandée.
    retenues = len(lignes)
    pages = max(1, (retenues + PAR_PAGE - 1) // PAR_PAGE)
    page = max(1, min(int(page or 1), pages))
    debut = (page - 1) * PAR_PAGE
    lignes = lignes[debut:debut + PAR_PAGE]

    msg = f'<div class="msg">{ESC(message)}</div>' if message else ""
    err = f'<div class="err">{ESC(erreur)}</div>' if erreur else ""

    # Bandeau de périmètre : dire À QUI appartient ce qu'on regarde évite de
    # croire consulter la liste nationale alors qu'on voit un seul district.
    if permis is None:
        portee = "Vous voyez <b>tous les districts</b>."
    elif permis:
        libelles = ", ".join(sorted(ESC(noms.get(str(c), str(c))) for c in permis))
        portee = f"Périmètre : <b>{libelles}</b>."
    else:
        portee = ("<b>Aucun district ne vous est affecté</b> : cette liste reste "
                  "vide tant qu'un administrateur ne vous en attribue pas un.")

    bouton = (f'<p><a href="/equipes/{onglet}/ajouter"><button type="button">'
              f'+ Ajouter un {"chef d&rsquo;équipe" if onglet == "ce" else "agent"}'
              f'</button></a> &nbsp; <small>Le téléversement Excel reste '
              f'disponible depuis l&rsquo;espace Traitement.</small></p>')

    ongl = (
        f'<p class="onglets">'
        f'<a href="/equipes?onglet=ce" class="{"actif" if onglet == "ce" else ""}">'
        f'Chefs d\'équipe</a> '
        f'<a href="/equipes?onglet=ae" class="{"actif" if onglet == "ae" else ""}">'
        f'Agents enquêteurs</a></p>')

    champ_chef = ""
    if onglet == "ae":
        champ_chef = ('<div><label for="chef">Chef d\'équipe</label>'
                      f'<input type="text" id="chef" name="chef" '
                      f'placeholder="login du CE" value="{ESC(chef)}"></div>')

    filtres = (
        f'<form method="get" action="/equipes" class="grid-form">'
        f'<input type="hidden" name="onglet" value="{onglet}">'
        f'<div><label for="district">District</label>'
        f'<select id="district" name="district">'
        f'{_options_districts(conn, utilisateur, district)}</select></div>'
        f'<div><label for="q">Login ou nom</label>'
        f'<input type="text" id="q" name="q" placeholder="Rechercher…" '
        f'value="{ESC(texte)}"></div>'
        f'{champ_chef}'
        f'<div style="align-self:end"><button>Filtrer</button></div>'
        f'</form>')

    actif = bool(district or texte or chef)
    reinit = (f' — <a href="/equipes?onglet={onglet}">réinitialiser les filtres</a>'
              if actif else '')
    position = (f'{debut + 1}–{debut + len(lignes)} sur {retenues}'
                if retenues else '0')
    filtre_txt = f' (filtré sur {total} au total)' if actif else ''
    compteur = f'<p><small>{position}{filtre_txt}{reinit}</small></p>'

    # Navigation entre pages, en conservant les filtres courants.
    def lien_page(n, libelle):
        params = {"onglet": onglet, "page": n}
        if district:
            params["district"] = district
        if texte:
            params["q"] = texte
        if chef:
            params["chef"] = chef
        return (f'<a href="/equipes?{urllib.parse.urlencode(params)}">'
                f'{libelle}</a>')

    if pages > 1:
        morceaux = []
        if page > 1:
            morceaux.append(lien_page(page - 1, "‹ précédente"))
        morceaux.append(f'<b>page {page} sur {pages}</b>')
        if page < pages:
            morceaux.append(lien_page(page + 1, "suivante ›"))
        navigation = ('<p class="pagination"><small>'
                      + ' &nbsp; '.join(morceaux) + '</small></p>')
    else:
        navigation = ''
    compteur += navigation

    tableau = _table_chefs(lignes, noms) if onglet == "ce" \
        else _table_agents(lignes, noms)

    return (admin._entete()
            + "<h1>Chefs d'équipe et agents enquêteurs</h1>"
            + msg + err
            + f'<div class="msg">{portee}</div>'
            + ongl + bouton + filtres + compteur + tableau + navigation
            + admin._pied())


def _table_chefs(lignes, noms) -> str:
    rows = ""
    for l in lignes:
        lg = ESC(l["login"])
        rows += (
            f'<tr><td><b>{lg}</b></td><td>{ESC(l["nom"])}</td>'
            f'<td>{_district_texte(l["district"], noms)}</td>'
            f'<td>{l["nb_agents"]}</td>'
            f'<td><a href="/equipes/ce/modifier?login={urllib.parse.quote(l["login"])}">'
            f'<button type="button" class="sec">Modifier</button></a> '
            f'<form class="inline" method="post" action="/equipes/ce/supprimer" '
            f'onsubmit="return confirm(\'Supprimer le chef d\\\'équipe {lg} ?\')">'
            f'<input type="hidden" name="login" value="{lg}">'
            f'<label><input type="checkbox" name="detacher" value="1"> '
            f'détacher les agents</label> '
            f'<button class="danger">Supprimer</button></form></td></tr>')
    if not rows:
        rows = ('<tr><td colspan="5"><small>Aucun chef d\'équipe ne correspond.'
                '</small></td></tr>')
    return ('<table><tr><th>Login</th><th>Nom et prénom</th><th>District</th>'
            '<th>Agents</th><th>Actions</th></tr>' + rows + '</table>')


def _table_agents(lignes, noms) -> str:
    rows = ""
    for l in lignes:
        lg = ESC(l["login"])
        if l["chef_login"]:
            chef = (f'<b>{ESC(l["chef_login"])}</b>'
                    + (f'<br><small>{ESC(l["chef_nom"])}</small>' if l["chef_nom"] else ""))
        else:
            chef = '<span class="pill ko">sans chef</span>'
        rows += (
            f'<tr><td><b>{lg}</b></td><td>{ESC(l["nom"])}</td><td>{chef}</td>'
            f'<td>{_district_texte(l["district"], noms)}</td>'
            f'<td><a href="/equipes/ae/modifier?login={urllib.parse.quote(l["login"])}">'
            f'<button type="button" class="sec">Modifier</button></a> '
            f'<form class="inline" method="post" action="/equipes/ae/supprimer" '
            f'onsubmit="return confirm(\'Supprimer l\\\'agent {lg} ?\')">'
            f'<input type="hidden" name="login" value="{lg}">'
            f'<button class="danger">Supprimer</button></form></td></tr>')
    if not rows:
        rows = ('<tr><td colspan="5"><small>Aucun agent ne correspond.</small>'
                '</td></tr>')
    return ('<table><tr><th>Login</th><th>Nom et prénom</th>'
            '<th>Chef d\'équipe</th><th>District</th><th>Actions</th></tr>'
            + rows + '</table>')


def page_modifier(conn, utilisateur, genre, login, erreur=None) -> str:
    """Formulaire de modification d'un chef d'équipe (`ce`) ou d'un agent (`ae`)."""
    fiche = lire_chef(conn, login) if genre == "ce" else lire_agent(conn, login)
    if not fiche:
        return admin._entete() + '<h1>Fiche introuvable</h1>' \
            + '<p><a href="/equipes">← Retour à la liste</a></p>' + admin._pied()
    if not _peut_toucher(utilisateur, fiche["district"]):
        return (admin._entete() + '<h1>Accès refusé</h1>'
                + '<div class="err">Cette fiche n\'est pas dans votre district.</div>'
                + '<p><a href="/equipes">← Retour à la liste</a></p>' + admin._pied())

    err = f'<div class="err">{ESC(erreur)}</div>' if erreur else ""
    titre = "chef d'équipe" if genre == "ce" else "agent enquêteur"
    onglet = "ce" if genre == "ce" else "ae"

    champ_chef = ""
    if genre == "ae":
        # Les chefs proposés sont ceux du périmètre : on ne rattache pas un
        # agent à un chef qu'on n'a pas le droit de voir.
        chefs = lister_chefs(conn, _districts_autorises(utilisateur))
        options = ['<option value="">— sans chef d\'équipe —</option>']
        for c in chefs:
            sel = " selected" if c["login"] == fiche["chef_login"] else ""
            options.append(f'<option value="{ESC(c["login"])}"{sel}>'
                           f'{ESC(c["login"])} — {ESC(c["nom"])}</option>')
        champ_chef = ('<div><label for="chef">Chef d\'équipe</label>'
                      f'<select id="chef" name="chef">{"".join(options)}</select></div>')

    return (admin._entete()
            + f'<h1>Modifier le {titre}</h1>' + err
            + f'<form method="post" action="/equipes/{onglet}/modifier" class="grid-form">'
            + f'<input type="hidden" name="login" value="{ESC(fiche["login"])}">'
            + '<div><label>Login</label>'
            + f'<input type="text" value="{ESC(fiche["login"])}" disabled>'
            + '<small>Identifie la fiche : non modifiable.</small></div>'
            + '<div><label for="nom">Nom et prénom</label>'
            + f'<input type="text" id="nom" name="nom" required '
            + f'value="{ESC(fiche["nom"])}"></div>'
            + champ_chef
            + '<div><label for="district">District</label>'
            + f'<select id="district" name="district">'
            + _options_districts(conn, utilisateur, str(fiche["district"] or ""),
                                 avec_sans=False)
            + '</select><small>Laisser « Tous les districts » ne change rien.</small></div>'
            + '<div style="align-self:end"><button>Enregistrer</button> '
            + f'<a href="/equipes?onglet={onglet}">Annuler</a></div>'
            + '</form>' + admin._pied())


def page_ajouter(conn, utilisateur, genre, valeurs=None, erreur=None) -> str:
    """Formulaire de création d'un chef d'équipe (`ce`) ou d'un agent (`ae`).

    Les valeurs saisies sont réinjectées en cas d'erreur : refaire toute la
    saisie parce qu'un login était déjà pris est inutilement pénible.
    """
    v = valeurs or {}
    err = f'<div class="err">{ESC(erreur)}</div>' if erreur else ""
    titre = "chef d'équipe" if genre == "ce" else "agent enquêteur"
    exemple = "CE_MDTR_001" if genre == "ce" else "EQ1_MDTR_0002"

    champ_chef = ""
    if genre == "ae":
        chefs = lister_chefs(conn, _districts_autorises(utilisateur))
        options = ['<option value="">— sans chef d\'équipe —</option>']
        for c in chefs:
            sel = " selected" if c["login"] == v.get("chef", "") else ""
            options.append(f'<option value="{ESC(c["login"])}"{sel}>'
                           f'{ESC(c["login"])} — {ESC(c["nom"])}</option>')
        champ_chef = ('<div><label for="chef">Chef d\'équipe</label>'
                      f'<select id="chef" name="chef">{"".join(options)}</select>'
                      '<small>Facultatif : rattachable plus tard.</small></div>')

    return (admin._entete()
            + f'<h1>Ajouter un {titre}</h1>' + err
            + '<div class="msg">Le téléversement Excel reste disponible : '
              'cette page sert aux ajouts ponctuels et aux corrections.</div>'
            + f'<form method="post" action="/equipes/{genre}/ajouter" class="grid-form">'
            + '<div><label for="login">Login <span style="color:#c00">*</span></label>'
            + f'<input type="text" id="login" name="login" required maxlength="40" '
            + f'value="{ESC(v.get("login", ""))}" placeholder="{exemple}">'
            + f'<small>Convention observée : PRÉFIXE_ZONE_NUMÉRO, ex. {exemple}. '
              'Le code de zone sert à retrouver le district des fiches '
              'anciennes.</small></div>'
            + '<div><label for="nom">Nom et prénom <span style="color:#c00">*</span></label>'
            + f'<input type="text" id="nom" name="nom" required '
            + f'value="{ESC(v.get("nom", ""))}"></div>'
            + champ_chef
            + '<div><label for="district">District <span style="color:#c00">*</span></label>'
            + '<select id="district" name="district" required>'
            + _options_districts(conn, utilisateur, v.get("district", ""),
                                 avec_sans=False)
            + '</select></div>'
            + '<div style="align-self:end"><button>Créer</button> '
            + f'<a href="/equipes?onglet={genre}">Annuler</a></div>'
            + '</form>' + admin._pied())
