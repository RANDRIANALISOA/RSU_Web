"""Rapport de mission — synthèse des journaux de bord quotidiens (EN FRANÇAIS).

Le rapport suit un PLAN de rapport de mission classique :
  1. Introduction
  2. Concept et justification
  3. Déroulement de la mission          (rempli depuis les journaux)
  4. Problèmes rencontrés et solutions  (candidats détectés + à affiner)
  5. Itinéraire                          (chronologie, depuis les journaux)
  6. Conclusion
  7. Annexe — Journaux détaillés         (compilation intégrale)

VERSION HORS-LIGNE (par défaut) : aucune donnée ne sort du serveur. Les sections
« données » (3, 5, 7 + chiffres) sont remplies automatiquement à partir de la table
`journal_activite` ; les sections « rédigées » (1, 2, 4, 6) reçoivent un texte de base
EN FRANÇAIS, à personnaliser — ce sont celles qu'une IA (API Claude) rédigerait le
mieux (voir synthese_ia(), DÉSACTIVÉE tant que la décision de confidentialité n'est
pas prise : cf. CLAUDE.md).
"""
import datetime
import html as htmllib
import os
import re
import unicodedata

import journal
import zones


# ---------------------------------------------------------------------------
# Collecte + analyse HORS-LIGNE (déterministe, aucune sortie de données)
# ---------------------------------------------------------------------------
def _noms_districts(conn):
    try:
        return {d["code"]: d["nom"] for d in zones.tous_districts(conn)}
    except Exception:
        return {}


def _norm(s):
    """minuscule + sans accents, pour la détection de mots-clés."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Mots-clés (normalisés) repérant un problème / une difficulté / une solution.
_MOTS_PROBLEME = ("probleme", "difficulte", "panne", "retard", "rupture", "blocage",
                  "incident", "manque", "insuffis", "erreur", "coupure", "reseau",
                  "contrainte", "obstacle", "absence", "indisponib")
_MOTS_SOLUTION = ("solution", "resolu", "corrige", "regle", "remedie", "pallier",
                  "contourne", "rattrap")


def collecter(conn, debut, fin, districts=None):
    """Entrées de journal entre `debut` et `fin` (ISO), bornées au périmètre."""
    jours = set(journal.plage_dates(debut, fin))
    if not jours:
        return []
    ent = journal.activites(conn, districts=districts, limite=1000000)
    return [e for e in ent if e.get("date_jour") in jours]


def _codes_de(e):
    return [c for c in (e.get("code_district") or "").replace(" ", "").split(",") if c]


def synthese_locale(conn, debut, fin, districts=None):
    """Structure les journaux : stats + regroupement + itinéraire + problèmes."""
    entrees = collecter(conn, debut, fin, districts)
    noms_d = _noms_districts(conn)
    jours_periode = journal.plage_dates(debut, fin)

    # Regroupement district -> fonction -> personne (pour l'annexe / le déroulement).
    par_district = {}
    redacteurs, jours_couverts, fonctions_vues = set(), set(), set()
    for e in entrees:
        redacteurs.add(e.get("login"))
        jours_couverts.add(e.get("date_jour"))
        if e.get("fonction"):
            fonctions_vues.add(e.get("fonction"))
        codes = _codes_de(e) or ["(sans district)"]
        for c in codes:
            (par_district.setdefault(c, {})
                         .setdefault(e.get("fonction") or "(sans fonction)", {})
                         .setdefault(e.get("nom_prenom") or e.get("login") or "?", [])
                         .append(e))

    districts_out = []
    for c in sorted(par_district, key=lambda x: noms_d.get(x, x)):
        fonctions = []
        n_ent_d = 0
        for fct in sorted(par_district[c]):
            personnes = []
            for nom in sorted(par_district[c][fct]):
                items = sorted(par_district[c][fct][nom], key=lambda e: e.get("date_jour") or "")
                n_ent_d += len(items)
                personnes.append({"nom": nom, "entrees": items})
            fonctions.append({"fonction": fct, "personnes": personnes})
        districts_out.append({"code": c, "nom": noms_d.get(c, c),
                              "n_entrees": n_ent_d, "fonctions": fonctions})

    # Itinéraire : par date, les districts et zones où une activité a été consignée.
    par_jour = {}
    for e in entrees:
        j = e.get("date_jour")
        if not j:
            continue
        d = par_jour.setdefault(j, {"date_court": e.get("date_court") or j,
                                    "districts": set(), "zones": set()})
        for c in _codes_de(e):
            d["districts"].add(noms_d.get(c, c))
        if e.get("zone"):
            d["zones"].add(e.get("zone"))
    itineraire = [{"date": j, "date_court": par_jour[j]["date_court"],
                   "districts": sorted(par_jour[j]["districts"]),
                   "zones": sorted(par_jour[j]["zones"])}
                  for j in sorted(par_jour)]

    # Problèmes / solutions : entrées dont le texte contient un mot-clé (candidats).
    problemes = []
    for e in sorted(entrees, key=lambda e: e.get("date_jour") or ""):
        n = _norm(e.get("journal"))
        a_pb = any(m in n for m in _MOTS_PROBLEME)
        a_sol = any(m in n for m in _MOTS_SOLUTION)
        if a_pb or a_sol:
            problemes.append({
                "date_court": e.get("date_court") or e.get("date_jour") or "",
                "nom": e.get("nom_prenom") or e.get("login") or "?",
                "fonction": e.get("fonction") or "",
                "districts": [noms_d.get(c, c) for c in _codes_de(e)],
                "journal": e.get("journal") or "",
                "a_solution": a_sol,
            })

    return {
        "debut": debut, "fin": fin,
        "genere_le": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "stats": {
            "n_entrees": len(entrees),
            "n_redacteurs": len(redacteurs),
            "n_jours_couverts": len(jours_couverts),
            "n_jours_periode": len(jours_periode),
            "n_districts": len(districts_out),
            "n_fonctions": len(fonctions_vues),
        },
        "districts": districts_out,
        "itineraire": itineraire,
        "problemes": problemes,
    }


# ---------------------------------------------------------------------------
# Textes de base EN FRANÇAIS des sections rédigées (à personnaliser / à générer)
# ---------------------------------------------------------------------------
def _intro(r, perimetre_label):
    return (
        "Le présent rapport rend compte du déroulement de la mission menée dans le "
        "cadre du <strong>Registre Social Unique (RSU) 2026</strong>, sur la période "
        f"du <strong>{htmllib.escape(r['debut'])}</strong> au "
        f"<strong>{htmllib.escape(r['fin'])}</strong>, pour le périmètre : "
        f"<strong>{htmllib.escape(perimetre_label)}</strong>. Il est établi à partir "
        "des journaux de bord renseignés quotidiennement par les équipes de terrain. "
        "Il présente le concept et la justification de la mission, son déroulement, "
        "les difficultés rencontrées et les solutions adoptées, l'itinéraire suivi, "
        "puis une conclusion.")


def _concept():
    return (
        "La mission s'inscrit dans l'opération de <strong>dénombrement des ménages</strong> "
        "du RSU 2026, dont l'objectif est de constituer une base de données fiable et "
        "actualisée des ménages en vue du ciblage des programmes de protection sociale. "
        "Elle mobilise une équipe technique (traitement, experts survey, superviseurs "
        "techniques, logistique) sous la coordination nationale et régionale. "
        "<em>[Section à personnaliser : rappeler ici les objectifs précis, la zone "
        "d'intervention et les résultats attendus de la mission.]</em>")


def _conclusion(r):
    s = r["stats"]
    return (
        f"Sur la période considérée, la mission a donné lieu à <strong>{s['n_entrees']} "
        f"entrées</strong> de journal renseignées par <strong>{s['n_redacteurs']} "
        f"membres</strong> de l'équipe, couvrant <strong>{s['n_jours_couverts']} jours</strong> "
        f"sur {s['n_jours_periode']} et <strong>{s['n_districts']} district(s)</strong>. "
        "<em>[Section à personnaliser : bilan global, degré d'atteinte des objectifs, "
        "recommandations et perspectives.]</em>")


# ---------------------------------------------------------------------------
# Rendu HTML (page complète : _html y injecte bandeau + responsive)
# ---------------------------------------------------------------------------
_STYLE = (
    ":root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px)}"
    "*{box-sizing:border-box}"
    "body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;color:#1c2430;"
    "background:#eef2f7;line-height:1.6;padding:84px 1.25rem 3rem}"
    ".rm-wrap{max-width:56rem;margin:0 auto}"
    ".rm-bar{display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:1rem}"
    ".rm-bar h1{font-size:1.4rem;margin:0;flex:1;min-width:12rem}"
    ".rm-doc{background:#fff;border:1px solid #dce3ea;border-radius:0.6rem;"
    "padding:2rem 2.2rem;box-shadow:0 1px 3px rgba(13,43,78,.06)}"
    ".rm-garde{text-align:center;border-bottom:2px solid #12325c;padding-bottom:1.2rem;margin-bottom:1.4rem}"
    ".rm-garde .pays{font-size:.8rem;letter-spacing:.5px;color:#5a6675;text-transform:uppercase}"
    ".rm-garde .titre{font-size:1.6rem;font-weight:800;color:#12325c;margin:.5rem 0 .2rem}"
    ".rm-garde .st{color:#5a6675;font-size:.95rem}"
    ".rm-h2{font-size:1.15rem;font-weight:800;color:#12325c;margin:1.6rem 0 .5rem;"
    "padding-bottom:.25rem;border-bottom:1px solid #e2e8f0}"
    ".rm-h3{font-size:1rem;font-weight:800;color:#1558c9;margin:1rem 0 .3rem}"
    ".rm-h4{font-weight:700;margin:.6rem 0 .2rem}"
    ".rm-p{margin:.3rem 0 .6rem;text-align:justify}"
    ".rm-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(7.5rem,1fr));gap:.6rem;margin:.6rem 0 1rem}"
    ".rm-kpi{background:#f8fafc;border:1px solid #e2e8f0;border-radius:.6rem;padding:.6rem .75rem;text-align:center}"
    ".rm-kpi .n{font-size:1.4rem;font-weight:800;color:#12325c}"
    ".rm-kpi .l{font-size:.68rem;text-transform:uppercase;letter-spacing:.4px;color:#64748b}"
    ".rm-ent{margin:0 0 .45rem;padding-left:.9rem;border-left:3px solid #c7dbf7}"
    ".rm-date{font-size:.72rem;font-weight:700;color:#5a6675}"
    ".rm-txt{white-space:pre-wrap;margin:.1rem 0 0}"
    "table.rm-tab{width:100%;border-collapse:collapse;font-size:.85rem;margin:.4rem 0 1rem}"
    "table.rm-tab th,table.rm-tab td{border:1px solid #e2e8f0;padding:.4rem .55rem;text-align:left;vertical-align:top}"
    "table.rm-tab th{background:#f1f5fb;color:#12325c}"
    ".rm-pb{border-left:3px solid #f59e0b}"
    ".rm-sol{border-left:3px solid #10b981}"
    ".rm-tag{display:inline-block;font-size:.68rem;font-weight:700;border-radius:1rem;padding:.05rem .5rem;margin-left:.4rem}"
    ".rm-tag.pb{background:#fef3c7;color:#92400e}.rm-tag.sol{background:#d1fae5;color:#065f46}"
    ".rm-note{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:.6rem;"
    "padding:.6rem .85rem;font-size:.82rem;margin:1rem 0}"
    ".rm-edit{background:#eff6ff;border:1px dashed #93c5fd;color:#1e3a8a;border-radius:.5rem;"
    "padding:.15rem .4rem;font-size:.8rem}"
    ".rm-btn{display:inline-flex;align-items:center;gap:.4rem;text-decoration:none;"
    "background:#1558c9;color:#fff;font-weight:700;border:none;border-radius:.6rem;"
    "padding:.5rem .9rem;font-size:.85rem;cursor:pointer}"
    ".rm-btn.sec{background:#eaf1fd;color:#1558c9;border:1px solid #c7dbf7}"
    ".rm-empty{color:#5a6675;text-align:center;padding:1.5rem}"
    "@media print{body{padding:0;background:#fff}.rm-noprint{display:none!important}"
    ".rm-doc{box-shadow:none;border:none;padding:0}.rm-h2{break-after:avoid}"
    ".rm-ent,table.rm-tab tr{break-inside:avoid}}"
)


def _sec(num, titre, corps):
    return f'<div class="rm-h2">{num}. {htmllib.escape(titre)}</div>{corps}'


def rendu_html(rapport, perimetre_label, retour_href, ia_html="", ia_href=""):
    esc = htmllib.escape
    r = rapport
    s = r["stats"]
    bouton_ia = (f'<a class="rm-btn" href="{esc(ia_href)}">🤖 Version rédigée par IA</a>'
                 if ia_href else "")

    kpis = (
        '<div class="rm-kpis">'
        f'<div class="rm-kpi"><div class="n">{s["n_entrees"]}</div><div class="l">Entrées</div></div>'
        f'<div class="rm-kpi"><div class="n">{s["n_redacteurs"]}</div><div class="l">Rédacteurs</div></div>'
        f'<div class="rm-kpi"><div class="n">{s["n_jours_couverts"]}/{s["n_jours_periode"]}</div><div class="l">Jours couverts</div></div>'
        f'<div class="rm-kpi"><div class="n">{s["n_districts"]}</div><div class="l">Districts</div></div>'
        f'<div class="rm-kpi"><div class="n">{s.get("n_fonctions", 0)}</div><div class="l">Fonctions</div></div>'
        '</div>')

    # 1. Introduction
    sec1 = _sec("1", "Introduction", f'<p class="rm-p">{_intro(r, perimetre_label)}</p>')
    # 2. Concept et justification
    sec2 = _sec("2", "Concept et justification", f'<p class="rm-p">{_concept()}</p>')
    # 3. Déroulement de la mission (données)
    corps3 = [kpis]
    if not r["districts"]:
        corps3.append('<div class="rm-empty">Aucune entrée de journal sur cette période.</div>')
    for d in r["districts"]:
        corps3.append(f'<div class="rm-h3">District de {esc(d["nom"])} '
                      f'<span style="color:#8a97a6;font-weight:400">({esc(d["code"])}) · '
                      f'{d["n_entrees"]} entrée(s)</span></div>')
        for f in d["fonctions"]:
            corps3.append(f'<div class="rm-h4">{esc(f["fonction"])}</div>')
            for p in f["personnes"]:
                corps3.append(f'<div style="font-weight:600;margin:.3rem 0 .1rem">{esc(p["nom"])}</div>')
                for e in p["entrees"]:
                    corps3.append(
                        '<div class="rm-ent">'
                        f'<div class="rm-date">{esc(e.get("date_court") or e.get("date_jour") or "")}</div>'
                        f'<div class="rm-txt">{esc((e.get("journal") or "").strip())}</div></div>')
    sec3 = _sec("3", "Déroulement de la mission", "".join(corps3))

    # 4. Problèmes rencontrés et solutions adoptées (candidats détectés)
    if r["problemes"]:
        lignes = []
        for p in r["problemes"]:
            tag = '<span class="rm-tag sol">solution</span>' if p["a_solution"] else '<span class="rm-tag pb">problème</span>'
            cls = "rm-sol" if p["a_solution"] else "rm-pb"
            lieu = " · ".join(p["districts"]) if p["districts"] else ""
            lignes.append(
                f'<div class="rm-ent {cls}"><div class="rm-date">{esc(p["date_court"])} — '
                f'{esc(p["nom"])} ({esc(p["fonction"])}) {esc(lieu)}{tag}</div>'
                f'<div class="rm-txt">{esc(p["journal"].strip())}</div></div>')
        corps4 = ('<p class="rm-p">Éléments <strong>signalés dans les journaux</strong> '
                  'mentionnant une difficulté ou une solution (repérage automatique par '
                  'mots-clés — <span class="rm-edit">à relire et synthétiser</span>) :</p>'
                  + "".join(lignes))
    else:
        corps4 = ('<p class="rm-p"><span class="rm-edit">Aucun élément détecté '
                  'automatiquement. Section à compléter manuellement.</span></p>')
    sec4 = _sec("4", "Problèmes rencontrés et solutions adoptées", corps4)

    # 5. Itinéraire (données)
    if r["itineraire"]:
        rows = ['<table class="rm-tab"><tr><th>Date</th><th>District(s)</th>'
                '<th>Zone(s) / axe(s)</th></tr>']
        for it in r["itineraire"]:
            rows.append(f'<tr><td>{esc(it["date_court"])}</td>'
                        f'<td>{esc(", ".join(it["districts"]) or "—")}</td>'
                        f'<td>{esc(", ".join(it["zones"]) or "—")}</td></tr>')
        rows.append('</table>')
        corps5 = "".join(rows)
    else:
        corps5 = '<div class="rm-empty">Aucun déplacement consigné.</div>'
    sec5 = _sec("5", "Itinéraire", corps5)

    # 6. Conclusion
    sec6 = _sec("6", "Conclusion", f'<p class="rm-p">{_conclusion(r)}</p>')

    garde = (
        '<div class="rm-garde">'
        '<div class="pays">République de Madagascar — INSTAT</div>'
        '<div class="titre">Rapport de mission — RSU 2026</div>'
        f'<div class="st">Période du {esc(r["debut"])} au {esc(r["fin"])} · '
        f'{esc(perimetre_label)}<br>Établi le {esc(r["genere_le"])}</div></div>')

    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission</title>'
        f'<style>{_STYLE}</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar rm-noprint"><h1>Rapport de mission</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a>'
        f'{bouton_ia}'
        '<button class="rm-btn" onclick="window.print()">🖨 Imprimer / PDF</button></div>'
        '<div class="rm-note rm-noprint">📋 <strong>Compilation automatique</strong> '
        '(aucune IA, aucune donnée envoyée à l\'extérieur). Les sections <em>Introduction</em>, '
        '<em>Concept et justification</em>, <em>Problèmes/solutions</em> et <em>Conclusion</em> '
        'contiennent un texte de base <span class="rm-edit">à personnaliser</span> — c\'est '
        'ce qu\'une IA rédigerait automatiquement une fois activée.</div>'
        f'{ia_html}'
        '<div class="rm-doc">'
        + garde + sec1 + sec2 + sec3 + sec4 + sec5 + sec6 +
        '<div class="rm-h2">7. Annexe — Journaux détaillés</div>'
        '<p class="rm-p" style="color:#5a6675">Le déroulement (section 3) reprend déjà '
        'l\'intégralité des journaux, regroupés par district, fonction et personne.</p>'
        '</div></div></body></html>')


def page_formulaire(debut_defaut, fin_defaut, districts_dispo, action, retour_href):
    """Formulaire de choix (période + district facultatif)."""
    esc = htmllib.escape
    opts = ['<option value="">Tous mes districts</option>']
    for d in districts_dispo:
        opts.append(f'<option value="{esc(d["code"])}">{esc(d["nom"])} ({esc(d["code"])})</option>')
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission</title>'
        f'<style>{_STYLE}'
        ".rm-f{display:grid;gap:.8rem;max-width:26rem;background:#fff;border:1px solid #dce3ea;"
        "border-radius:.7rem;padding:1.2rem}"
        ".rm-f label{font-weight:600;font-size:.85rem;display:block;margin-bottom:.2rem}"
        ".rm-f input,.rm-f select{width:100%;padding:.5rem .6rem;border:1px solid #cbd5e1;"
        "border-radius:.5rem;font-size:.9rem;font-family:inherit}"
        '</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar"><h1>Rapport de mission</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a></div>'
        '<p style="color:#5a6675">Compile les journaux de bord de la période choisie en '
        'un rapport de mission structuré (en français), imprimable. Hors-ligne : aucune '
        'donnée n\'est envoyée à l\'extérieur.</p>'
        f'<form class="rm-f" method="get" action="{esc(action)}">'
        f'<div><label>Du</label><input type="date" name="debut" value="{esc(debut_defaut)}" required></div>'
        f'<div><label>Au</label><input type="date" name="fin" value="{esc(fin_defaut)}" required></div>'
        f'<div><label>District</label><select name="district">{"".join(opts)}</select></div>'
        '<div><button class="rm-btn" type="submit">Générer le rapport</button></div>'
        '</form></div></body></html>')


# ---------------------------------------------------------------------------
# SYNTHÈSE IA (option, DÉSACTIVÉE par défaut — aucune sortie de données sans
# décision explicite). Rien ci-dessous n'est appelé tant que ia_active() est faux.
# Le PLAN imposé à l'IA est celui du rapport ci-dessus (sections 1 à 6, en français).
# ---------------------------------------------------------------------------
_SYSTEM_IA = (
    "Tu es chargé de rédiger, EN FRANÇAIS, un RAPPORT DE MISSION complet et "
    "professionnel pour le programme Registre Social Unique (RSU) 2026 de l'INSTAT "
    "(Madagascar), à partir des journaux de bord quotidiens fournis.\n\n"
    "Consignes :\n"
    "- N'invente AUCUN fait ni chiffre : appuie-toi UNIQUEMENT sur les journaux "
    "fournis. Si une information manque, ne l'invente pas.\n"
    "- Écris au format MARKDOWN (titres #, ##, ###, listes, tableaux quand c'est "
    "utile), un texte fluide, structuré et factuel.\n"
    "- Parle des « équipes » et « binômes » plutôt que de personnes nommées (les "
    "noms ne sont volontairement pas fournis).\n"
    "- Reprends les chiffres présents dans les journaux (nombres de dossiers, "
    "candidats, doublons…) et SIGNALE les écarts éventuels à vérifier.\n"
    "- Structure recommandée (adapte-la au contenu réel des journaux) : un en-tête "
    "(titre, période, zones d'intervention, activité principale), puis : "
    "1. Introduction ; 2. Objectifs de la mission ; 3. Déroulement de la mission "
    "(par phase et/ou par district) ; 4. Réception, dépouillement et traitement des "
    "dossiers ; 5. Apurement et sélection ; 6. Préparation et organisation ; "
    "7. Coordination et communication ; 8. Difficultés rencontrées ; 9. Solutions et "
    "mesures d'adaptation ; 10. Résultats obtenus ; 11. Synthèse par district "
    "(tableau) ; 12. Appréciation générale ; 13. Recommandations ; 14. Conclusion.\n"
    "- Reste synthétique tout en étant complet."
)


def ia_active() -> bool:
    """Vrai seulement si l'IA a été EXPLICITEMENT activée (env) ET une clé existe."""
    return (os.environ.get("RSU_IA_RAPPORT", "").strip() == "1"
            and bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()))


def _journaux_en_texte(rapport, perimetre_label):
    """Met en forme les journaux pour l'IA — SANS les noms des personnes (seulement
    date, fonction, district et texte)."""
    lignes = [
        f"Période : du {rapport['debut']} au {rapport['fin']}.",
        f"Périmètre : {perimetre_label}.",
        "Districts concernés : "
        + (", ".join(d["nom"] for d in rapport["districts"]) or "—") + ".",
        "",
        "JOURNAUX DE BORD (noms des personnes volontairement omis) :",
    ]
    for d in rapport["districts"]:
        items = []
        for f in d["fonctions"]:
            for p in f["personnes"]:
                for e in p["entrees"]:
                    items.append((e.get("date_jour") or "",
                                  e.get("fonction") or f["fonction"],
                                  (e.get("journal") or "").strip()))
        items.sort(key=lambda x: x[0])
        lignes.append("")
        lignes.append(f"=== District de {d['nom']} ({d['code']}) ===")
        for dj, fct, txt in items:
            if txt:
                lignes.append(f"[{dj}] ({fct}) {txt}")
    return "\n".join(lignes)


def _client_ia():
    """Client Anthropic (clé via ANTHROPIC_API_KEY). Si la clé est liée à un
    workspace, l'API exige l'en-tête anthropic-workspace-id : transmis depuis
    ANTHROPIC_WORKSPACE_ID quand défini."""
    import anthropic  # dépendance serveur (pip install anthropic)
    kwargs = {}
    wsid = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if wsid:
        kwargs["default_headers"] = {"anthropic-workspace-id": wsid}
    return anthropic.Anthropic(**kwargs)


def synthese_ia_iter(rapport, perimetre_label):
    """Génère le rapport (Markdown) via l'API Claude (Opus 5) EN FLUX : produit les
    morceaux de texte au fur et à mesure. Permet de garder la connexion active
    (heartbeats) pendant la génération -> pas de 504 côté proxy. Lève une exception
    (clé, crédit, réseau…) dès la 1re lecture du flux."""
    client = _client_ia()
    contenu = ("Rédige le rapport de mission à partir des journaux de bord "
               "ci-dessous.\n\n" + _journaux_en_texte(rapport, perimetre_label))
    with client.messages.stream(
        model="claude-opus-5",
        max_tokens=20000,
        thinking={"type": "adaptive"},
        system=_SYSTEM_IA,
        messages=[{"role": "user", "content": contenu}],
    ) as stream:
        # On itère TOUS les événements (réflexion comprise) et on émet "" comme
        # heartbeat : ainsi des octets circulent AUSSI pendant la phase de réflexion
        # (sinon le proxy couperait avant le 1er texte). Seuls les deltas de texte
        # portent du contenu.
        for event in stream:
            if getattr(event, "type", "") == "content_block_delta" and \
               getattr(event.delta, "type", "") == "text_delta":
                yield event.delta.text
            else:
                yield ""
        msg = stream.get_final_message()
        if getattr(msg, "stop_reason", None) == "refusal":
            raise RuntimeError("La génération a été déclinée par le modèle.")


def synthese_ia(rapport, perimetre_label):
    """Version bloquante : renvoie tout le Markdown (utilise le flux en interne)."""
    return "".join(synthese_ia_iter(rapport, perimetre_label)).strip()


# --- Rendu EN FLUX de la page IA (évite le 504 : octets envoyés régulièrement) ---
def ia_stream_entete(rapport, perimetre_label, retour_href):
    """Début de la page IA (envoyé immédiatement) : en-tête + placeholder animé."""
    esc = htmllib.escape
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission (IA)</title>'
        f'<style>{_STYLE}'
        "@keyframes rmspin{to{transform:rotate(360deg)}}"
        ".rm-spin{display:inline-block;width:1.1rem;height:1.1rem;border:2px solid #c7dbf7;"
        "border-top-color:#1558c9;border-radius:50%;animation:rmspin .8s linear infinite;"
        "vertical-align:middle;margin-right:.5rem}"
        '</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar rm-noprint"><h1>Rapport de mission — version IA</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a></div>'
        f'<div id="rm-gen" class="rm-note rm-noprint"><span class="rm-spin"></span>'
        '<strong>Génération en cours…</strong> (rédaction par IA, ~1 à 2 min — '
        'ne fermez pas la page).</div>')


def ia_stream_corps(markdown, rapport, perimetre_label):
    """Rapport final : injecté après le placeholder, qu'on retire ensuite."""
    esc = htmllib.escape
    return (
        '<div class="rm-note rm-noprint">🤖 <strong>Rédigé par IA</strong> à partir des '
        'journaux de bord (sans les noms). '
        f'Période {esc(rapport["debut"])} → {esc(rapport["fin"])} · {esc(perimetre_label)}. '
        '<span class="rm-edit">À relire avant diffusion.</span> '
        '<button class="rm-btn" onclick="window.print()">🖨 Imprimer / PDF</button></div>'
        f'<div class="rm-doc">{markdown_html(markdown)}</div>'
        '<script>var g=document.getElementById("rm-gen");if(g)g.remove();</script>')


def ia_stream_erreur(message):
    esc = htmllib.escape
    return ('<div class="rm-note"><strong>La génération a échoué.</strong><br>'
            f'Détail : {esc(message)}</div>'
            '<script>var g=document.getElementById("rm-gen");if(g)g.remove();</script>')


def ia_stream_fin():
    return "</div></body></html>"


# --- Markdown -> HTML (petit convertisseur, sans dépendance) --------------------
def _md_inline(t):
    t = htmllib.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", t)
    return t


def _md_table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    header = cells[0]
    body = cells[1:]
    if len(cells) > 1 and all(set(c) <= set("-: ") and c for c in cells[1]):
        body = cells[2:]
    th = "".join(f"<th>{_md_inline(c)}</th>" for c in header)
    trs = "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in r) + "</tr>"
                  for r in body)
    return f'<table class="rm-tab"><tr>{th}</tr>{trs}</table>'


def markdown_html(md):
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out, para = [], []
    i, n = 0, len(lines)

    def flush():
        if para:
            out.append("<p>" + " ".join(_md_inline(x) for x in para) + "</p>")
            para.clear()

    while i < n:
        s = lines[i].strip()
        if s.startswith("|") and s.count("|") >= 2:
            flush()
            tbl = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            out.append(_md_table(tbl))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            out.append(f"<h{min(len(m.group(1)) + 1, 4)}>{_md_inline(m.group(2))}"
                       f"</h{min(len(m.group(1)) + 1, 4)}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            flush()
            out.append("<hr>")
            i += 1
            continue
        ol = re.match(r"^\d+[.)]\s+(.*)$", s)
        ul = re.match(r"^[-*]\s+(.*)$", s)
        if ol or ul:
            flush()
            tag = "ol" if ol else "ul"
            items = []
            while i < n:
                ss = lines[i].strip()
                mm = (re.match(r"^\d+[.)]\s+(.*)$", ss) if tag == "ol"
                      else re.match(r"^[-*]\s+(.*)$", ss))
                if not mm:
                    break
                items.append(f"<li>{_md_inline(mm.group(1))}</li>")
                i += 1
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if s == "":
            flush()
            i += 1
            continue
        para.append(s)
        i += 1
    flush()
    return "".join(out)


def rendu_ia(rapport, perimetre_label, retour_href, markdown):
    """Page du rapport RÉDIGÉ PAR IA (Markdown converti en HTML)."""
    esc = htmllib.escape
    corps = markdown_html(markdown)
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission (IA)</title>'
        f'<style>{_STYLE}</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar rm-noprint"><h1>Rapport de mission — version IA</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a>'
        '<button class="rm-btn" onclick="window.print()">🖨 Imprimer / PDF</button></div>'
        '<div class="rm-note rm-noprint">🤖 <strong>Rédigé par IA</strong> à partir des '
        'journaux de bord (sans les noms des personnes). '
        f'Période {esc(rapport["debut"])} → {esc(rapport["fin"])} · {esc(perimetre_label)} · '
        f'généré le {esc(rapport["genere_le"])}. '
        '<span class="rm-edit">À relire et valider avant diffusion.</span></div>'
        f'<div class="rm-doc">{corps}</div>'
        '</div></body></html>')


def page_ia_inactive(retour_href):
    esc = htmllib.escape
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission (IA)</title>'
        f'<style>{_STYLE}</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar"><h1>Rapport de mission — version IA</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a></div>'
        '<div class="rm-doc"><div class="rm-h2">Fonction IA non activée</div>'
        '<p class="rm-p">La génération par IA est désactivée. Pour l\'activer sur le '
        'serveur (après décision de confidentialité) :</p>'
        '<ol><li>installer le SDK : <code>pip install anthropic</code> ;</li>'
        '<li>définir la clé : variable d\'environnement <code>ANTHROPIC_API_KEY</code> ;</li>'
        '<li>activer : <code>RSU_IA_RAPPORT=1</code> ;</li>'
        '<li>redémarrer le service.</li></ol>'
        '<p class="rm-p">En attendant, la <strong>compilation hors-ligne</strong> reste '
        'disponible (bouton « Retour »).</p></div></div></body></html>')


def page_ia_erreur(message, retour_href):
    esc = htmllib.escape
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission (IA)</title>'
        f'<style>{_STYLE}</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar"><h1>Rapport de mission — version IA</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a></div>'
        '<div class="rm-doc"><div class="rm-h2">La génération a échoué</div>'
        f'<p class="rm-p">Détail : {esc(message)}</p>'
        '<p class="rm-p">Vérifiez la clé API, l\'accès Internet du serveur, puis '
        'réessayez. La compilation hors-ligne reste disponible.</p></div>'
        '</div></body></html>')
