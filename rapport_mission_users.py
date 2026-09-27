# -*- coding: utf-8 -*-
"""
rapport_mission_users.py — Rapport de mission INDIVIDUEL (un fichier Word par
utilisateur), généré LOCALEMENT (aucune IA/API) à partir de SON journal de bord.

Arborescence produite (à la racine du projet) :
    rapport_mission/<code_district>/rapport_<login>.docx

Le rendu réutilise `rapport_word.construire_docx` (même page de garde INSTAT, KPI,
graphiques, annexe des pièces jointes) que le rapport de mission de district : le
document ressemble donc au modèle, mais le TEXTE des sections est une compilation
FACTUELLE du journal de l'utilisateur (pas de rédaction IA — donc aucune donnée ne
sort du serveur).

Périmètre = les 4 districts du projet (config via DISTRICTS). Régénération à la
demande : `python rapport_mission_users.py` (ou appel de `generer_tous`).
"""
from __future__ import annotations

import os

import config
import db_source
import rapport_mission
import rapport_word
import zones

DISTRICTS = ("1101", "1106", "5201", "5206")
RACINE = os.path.join(config.BASE, "rapport_mission")
# Corps RÉDIGÉ par l'assistant (Claude Opus, en session) : un Markdown par login.
# S'il existe, il remplace la compilation mécanique -> rapport de qualité « IA »,
# rédigé/traduit à partir du journal. Sinon on retombe sur `_markdown` (mécanique).
DOSSIER_TEXTES = os.path.join(RACINE, "_textes")
# Journaux bruts exportés pour rédaction (matière première lue par l'assistant).
DOSSIER_JOURNAUX = os.path.join(RACINE, "_journaux")

_SOUS_TITRE_IA = ("Rapport rédigé à partir du journal de bord de l'agent "
                  "(synthèse et traduction). À relire et valider avant diffusion.")
_SOUS_TITRE_AUTO = ("Rapport individuel compilé automatiquement à partir du journal "
                    "de bord de l'agent (traitement local, sans rédaction). "
                    "À relire et valider avant diffusion.")

# Concept/justification et conclusion : textes de base EN FRANÇAIS (factuels, non IA).
_CONCEPT = (
    "Le Registre Social Unique (RSU) 2026 vise à constituer une base de données "
    "unique et fiable des ménages, support des programmes de protection sociale. "
    "La mission de terrain consiste à préparer, superviser et suivre le dénombrement "
    "des ménages : mobilisation et formation des équipes (chefs d'équipe et agents), "
    "organisation logistique, contrôle de la couverture et de la qualité des données, "
    "et remontée quotidienne de l'information via le journal de bord. Le présent "
    "rapport restitue la contribution individuelle de l'agent à cette mission.")


def _chemin_relatif(rel_ok=True):
    return RACINE


def chemin_rapport(login: str, code_district) -> str:
    """Chemin ABSOLU du fichier Word d'un utilisateur (qu'il existe ou non)."""
    return os.path.join(RACINE, str(code_district), f"rapport_{login}.docx")


def trouver_rapport(login: str, code_district=None):
    """Chemin du rapport EXISTANT d'un utilisateur, ou None. Cherche d'abord dans son
    district, puis dans les 4 districts (au cas où l'affectation aurait changé)."""
    candidats = []
    if code_district:
        candidats.append(chemin_rapport(login, code_district))
    candidats += [chemin_rapport(login, d) for d in DISTRICTS]
    for c in candidats:
        if os.path.isfile(c):
            return c
    return None


def _aplati(txt: str) -> str:
    """Texte de journal -> un seul paragraphe sûr pour le Markdown (pas de retour à
    la ligne, pas de caractère de tête interprété comme titre/liste/tableau)."""
    t = " ".join((txt or "").split())
    while t[:1] in ("#", "|", "-", "*", ">"):
        t = t[1:].lstrip()
    return t


def _periode(entrees):
    dates = sorted(e.get("date_jour") for e in entrees if e.get("date_jour"))
    return (dates[0], dates[-1]) if dates else ("", "")


def _markdown(rapport, entrees, nom, role, district_nom) -> str:
    """Corps Markdown du rapport individuel (sections 1 à 7), à partir du journal."""
    st = rapport["stats"]
    L = []
    L.append("## 1. Introduction")
    L.append(
        f"Le présent rapport individuel rend compte de la mission menée par "
        f"**{nom}**" + (f" ({role})" if role else "") + " dans le cadre du "
        f"**Registre Social Unique (RSU) 2026**, pour le district de "
        f"**{district_nom}**, sur la période du **{rapport['debut']}** au "
        f"**{rapport['fin']}**. Il est établi automatiquement à partir des "
        f"**{st['n_entrees']} entrée(s)** du journal de bord, renseignées sur "
        f"**{st['n_jours_couverts']} jour(s)**.")
    L.append("")
    L.append("## 2. Concept et justification")
    L.append(_CONCEPT)
    L.append("")

    L.append("## 3. Déroulement de la mission")
    if entrees:
        L.append("Chronologie des activités consignées au journal :")
        for e in entrees:
            d = e.get("date_court") or e.get("date_jour") or ""
            zone = e.get("zone")
            corps = _aplati(e.get("journal"))
            if len(corps) > 400:
                corps = corps[:400].rstrip() + "…"
            tete = d + (f" — {zone}" if zone else "")
            L.append(f"- **{tete}** : {corps}")
    else:
        L.append("Aucune activité n'a été consignée sur la période.")
    L.append("")

    L.append("## 4. Problèmes rencontrés et solutions")
    if rapport["problemes"]:
        for p in rapport["problemes"]:
            marque = "✅ " if p.get("a_solution") else "⚠️ "
            L.append(f"- {marque}**{p.get('date_court') or ''}** : "
                     f"{_aplati(p.get('journal'))[:300]}")
    else:
        L.append("Aucun problème particulier n'a été signalé sur la période.")
    L.append("")

    L.append("## 5. Itinéraire")
    if rapport["itineraire"]:
        L.append("| Date | Zone(s) d'intervention |")
        L.append("|---|---|")
        for it in rapport["itineraire"]:
            zones_txt = ", ".join(it.get("zones") or []) or "—"
            L.append(f"| {it.get('date_court') or it.get('date')} | {zones_txt} |")
    else:
        L.append("Aucun déplacement consigné.")
    L.append("")

    L.append("## 6. Conclusion")
    L.append(
        f"Sur la période, l'agent a consigné **{st['n_entrees']} entrée(s)** de "
        f"journal couvrant **{st['n_jours_couverts']} jour(s)** sur "
        f"**{st['n_jours_periode']} jour(s)** de mission. Ce suivi régulier a permis "
        "de documenter l'avancement des activités, de tracer les difficultés et les "
        "solutions apportées, et d'assurer la remontée d'information vers la "
        "coordination. La poursuite de ce suivi quotidien reste essentielle jusqu'à "
        "l'achèvement de la mission.")
    L.append("")

    L.append("## 7. Annexe — Journaux détaillés")
    for e in entrees:
        d = e.get("date_court") or e.get("date_jour") or ""
        zone = e.get("zone")
        L.append(f"**{d}" + (f" — {zone}" if zone else "") + "**")
        L.append(_aplati(e.get("journal")) or "(entrée vide)")
        L.append("")
    return "\n".join(L)


def generer_un(conn, login: str, log=print) -> str | None:
    """Génère le rapport Word d'UN utilisateur (à partir de son journal). Renvoie le
    chemin écrit, ou None s'il n'a aucune entrée de journal."""
    ph = db_source._placeholder(conn)
    cur = conn.cursor()
    cur.execute(f'SELECT "nom_prenom","fonction","code_district" '
                f'FROM "journal_activite" WHERE "login"={ph} '
                f'ORDER BY "date_jour" LIMIT 1', (login,))
    row = cur.fetchone()
    if row is None:
        return None
    nom = row[0] or login
    role = row[1] or ""
    code_district = (row[2] or "").split(",")[0].strip()

    debut_fin = rapport_mission.collecter(conn, "2026-01-01", "2030-12-31",
                                          {code_district}, login=login)
    debut, fin = _periode(debut_fin)
    if not debut:
        return None
    rapport = rapport_mission.synthese_locale(conn, debut, fin, {code_district},
                                              login=login)
    entrees = sorted(rapport_mission.collecter(conn, debut, fin, {code_district},
                                               login=login),
                     key=lambda e: e.get("date_jour") or "")
    pieces = rapport_mission.pieces_jointes(conn, rapport)
    district_nom = (rapport["districts"][0]["nom"] if rapport["districts"]
                    else code_district)
    perim_label = f"{nom} · {district_nom}"
    # Corps : rédaction de l'assistant si disponible (_textes/<login>.md), sinon
    # compilation mécanique de secours.
    texte = os.path.join(DOSSIER_TEXTES, f"{login}.md")
    if os.path.isfile(texte):
        with open(texte, encoding="utf-8") as fh:
            md = fh.read()
        sous_titre = _SOUS_TITRE_IA
    else:
        md = _markdown(rapport, entrees, nom, role, district_nom)
        sous_titre = _SOUS_TITRE_AUTO
    data = rapport_word.construire_docx(
        md, rapport, perim_label, pieces, equipe=None, sous_titre=sous_titre)

    dossier = os.path.join(RACINE, code_district)
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"rapport_{login}.docx")
    with open(chemin, "wb") as fh:
        fh.write(data)
    log(f"  écrit {chemin} ({len(data)//1024} Ko, {rapport['stats']['n_entrees']} entrées)")
    return chemin


def dump_journaux(conn, districts=DISTRICTS, log=print) -> dict:
    """Exporte le journal BRUT de chaque utilisateur (matière première pour la
    rédaction) dans `rapport_mission/_journaux/<login>.txt`. Renvoie {login: chemin}."""
    os.makedirs(DOSSIER_JOURNAUX, exist_ok=True)
    ph = db_source._placeholder(conn)
    faits = {}
    for login in _logins_avec_journal(conn, districts):
        cur = conn.cursor()
        cur.execute(f'SELECT "nom_prenom","fonction","zone","code_district",'
                    f'"date_jour","journal" FROM "journal_activite" '
                    f'WHERE "login"={ph} ORDER BY "date_jour","cree_le"', (login,))
        rows = cur.fetchall()
        if not rows:
            continue
        nom, role = rows[0][0] or login, rows[0][1] or ""
        code_d = (rows[0][3] or "").split(",")[0].strip()
        district_nom = zones.libelles_district(conn, int(code_d))[2] if code_d.isdigit() else code_d
        lignes = [f"LOGIN: {login}", f"NOM: {nom}", f"FONCTION: {role}",
                  f"DISTRICT: {code_d} — {district_nom}",
                  f"NB ENTRÉES: {len(rows)}", "=" * 70, ""]
        for _n, _f, zone, _cd, date_jour, journal in rows:
            lignes.append(f"### {date_jour}" + (f" — zone: {zone}" if zone else ""))
            lignes.append((journal or "(vide)").strip())
            lignes.append("")
        chemin = os.path.join(DOSSIER_JOURNAUX, f"{login}.txt")
        with open(chemin, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lignes))
        faits[login] = chemin
    log(f"Journaux exportés : {len(faits)} fichier(s) sous {DOSSIER_JOURNAUX}/.")
    return faits


def _logins_avec_journal(conn, districts=DISTRICTS):
    ph = db_source._placeholder(conn)
    marks = ",".join([ph] * len(districts))
    cur = conn.cursor()
    cur.execute(f'SELECT DISTINCT "login" FROM "journal_activite" '
                f'WHERE "code_district" IN ({marks}) AND "login" IS NOT NULL '
                f'ORDER BY "login"', tuple(districts))
    return [r[0] for r in cur.fetchall() if r[0]]


def generer_tous(conn, districts=DISTRICTS, log=print) -> dict:
    """(Re)génère le rapport Word de TOUS les utilisateurs ayant un journal dans les
    districts donnés. Renvoie un bilan {login: chemin}."""
    logins = _logins_avec_journal(conn, districts)
    log(f"Génération des rapports individuels : {len(logins)} utilisateur(s).")
    faits = {}
    for lg in logins:
        try:
            c = generer_un(conn, lg, log=log)
            if c:
                faits[lg] = c
        except Exception as e:
            log(f"  ⚠️ {lg} : échec ({e})")
    log(f"Terminé : {len(faits)} rapport(s) écrit(s) sous {RACINE}/<district>/.")
    return faits


def main() -> int:
    import sys
    conn = db_source.connect()
    try:
        zones.assurer_zones(conn)
        if "--dump" in sys.argv[1:]:
            dump_journaux(conn)            # exporte les journaux bruts (rédaction)
        elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            for lg in sys.argv[1:]:        # (re)génère des logins précis
                generer_un(conn, lg)
        else:
            generer_tous(conn)             # (re)génère tout le monde
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
