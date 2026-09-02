"""Rapport de mission — synthèse des journaux de bord quotidiens.

VERSION HORS-LIGNE (par défaut) : compile et structure les entrées de la table
`journal_activite` (via journal.activites) en un rapport lisible, SANS aucun appel
externe — aucune donnée ne sort du serveur. C'est la maquette à valider avant toute
décision d'utiliser une IA.

SYNTHÈSE RÉDIGÉE PAR IA (option, DÉSACTIVÉE par défaut) : `synthese_ia()` appellerait
l'API Claude pour produire une rédaction narrative. Elle n'est JAMAIS appelée tant que
`ia_active()` est faux (il faut RSU_IA_RAPPORT=1 ET une clé ANTHROPIC_API_KEY), afin
qu'aucune donnée ne parte à l'extérieur sans décision explicite (confidentialité,
cf. CLAUDE.md). Le branchement réel reste à faire.
"""
import datetime
import html as htmllib
import os

import journal
import zones


# ---------------------------------------------------------------------------
# Collecte + synthèse HORS-LIGNE (déterministe, aucune sortie de données)
# ---------------------------------------------------------------------------
def _noms_districts(conn):
    try:
        return {d["code"]: d["nom"] for d in zones.tous_districts(conn)}
    except Exception:
        return {}


def collecter(conn, debut, fin, districts=None):
    """Entrées de journal entre `debut` et `fin` (ISO), bornées au périmètre."""
    jours = set(journal.plage_dates(debut, fin))
    if not jours:
        return []
    ent = journal.activites(conn, districts=districts, limite=1000000)
    return [e for e in ent if e.get("date_jour") in jours]


def synthese_locale(conn, debut, fin, districts=None):
    """Structure les journaux en un dict : stats + district -> fonction -> personne."""
    entrees = collecter(conn, debut, fin, districts)
    noms_d = _noms_districts(conn)
    jours_periode = journal.plage_dates(debut, fin)

    par_district = {}
    redacteurs, jours_couverts = set(), set()
    for e in entrees:
        redacteurs.add(e.get("login"))
        jours_couverts.add(e.get("date_jour"))
        codes = [c for c in (e.get("code_district") or "").replace(" ", "").split(",") if c]
        if not codes:
            codes = ["(sans district)"]
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

    return {
        "debut": debut, "fin": fin,
        "genere_le": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "stats": {
            "n_entrees": len(entrees),
            "n_redacteurs": len(redacteurs),
            "n_jours_couverts": len(jours_couverts),
            "n_jours_periode": len(jours_periode),
            "n_districts": len(districts_out),
        },
        "districts": districts_out,
    }


# ---------------------------------------------------------------------------
# Rendu HTML (page complète : _html y injecte bandeau + responsive)
# ---------------------------------------------------------------------------
_STYLE = (
    ":root{--rsu-fluid:1;font-size:clamp(11px, 0.18vw + 9.5px, 13px)}"
    "*{box-sizing:border-box}"
    "body{margin:0;font-family:system-ui,'Segoe UI',Arial,sans-serif;color:#1c2430;"
    "background:#eef2f7;line-height:1.55;padding:84px 1.25rem 3rem}"
    ".rm-wrap{max-width:60rem;margin:0 auto}"
    ".rm-bar{display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:1rem}"
    ".rm-bar h1{font-size:1.35rem;margin:0;flex:1;min-width:12rem}"
    ".rm-sub{color:#5a6675;font-size:.9rem;margin:.15rem 0 0}"
    ".rm-card{background:#fff;border:1px solid #dce3ea;border-radius:0.9rem;"
    "padding:1rem 1.15rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(13,43,78,.06)}"
    ".rm-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));gap:.7rem}"
    ".rm-kpi{background:#f8fafc;border:1px solid #e2e8f0;border-radius:.7rem;padding:.7rem .85rem}"
    ".rm-kpi .n{font-size:1.5rem;font-weight:800}"
    ".rm-kpi .l{font-size:.7rem;text-transform:uppercase;letter-spacing:.4px;color:#64748b}"
    ".rm-dist{font-size:1.05rem;font-weight:800;margin:.2rem 0 .1rem;color:#12325c}"
    ".rm-fct{font-size:.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;"
    "color:#1558c9;margin:.9rem 0 .35rem;border-bottom:1px solid #e2e8f0;padding-bottom:.2rem}"
    ".rm-pers{font-weight:700;margin:.5rem 0 .2rem}"
    ".rm-ent{margin:0 0 .4rem;padding-left:.9rem;border-left:3px solid #c7dbf7}"
    ".rm-date{font-size:.72rem;font-weight:700;color:#5a6675}"
    ".rm-txt{white-space:pre-wrap;margin:.1rem 0 0}"
    ".rm-note{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:.7rem;"
    "padding:.7rem .9rem;font-size:.85rem;margin-bottom:1rem}"
    ".rm-btn{display:inline-flex;align-items:center;gap:.4rem;text-decoration:none;"
    "background:#1558c9;color:#fff;font-weight:700;border:none;border-radius:.6rem;"
    "padding:.5rem .9rem;font-size:.85rem;cursor:pointer}"
    ".rm-btn.sec{background:#eaf1fd;color:#1558c9;border:1px solid #c7dbf7}"
    ".rm-empty{color:#5a6675;text-align:center;padding:2rem}"
    "@media print{body{padding:0;background:#fff}.rm-noprint{display:none!important}"
    ".rm-card{box-shadow:none;break-inside:avoid}}"
)


def _fmt_txt(t):
    return htmllib.escape(t or "").strip()


def rendu_html(rapport, perimetre_label, retour_href, ia_html=""):
    esc = htmllib.escape
    s = rapport["stats"]
    blocs = []
    if not rapport["districts"]:
        blocs.append('<div class="rm-card rm-empty">Aucune entrée de journal sur '
                     'cette période / ce périmètre.</div>')
    for d in rapport["districts"]:
        parts = [f'<div class="rm-card"><div class="rm-dist">{esc(d["nom"])} '
                 f'<span style="color:#8a97a6;font-weight:400">({esc(d["code"])}) · '
                 f'{d["n_entrees"]} entrée(s)</span></div>']
        for f in d["fonctions"]:
            parts.append(f'<div class="rm-fct">{esc(f["fonction"])}</div>')
            for p in f["personnes"]:
                parts.append(f'<div class="rm-pers">{esc(p["nom"])}</div>')
                for e in p["entrees"]:
                    parts.append(
                        '<div class="rm-ent">'
                        f'<div class="rm-date">{esc(e.get("date_court") or e.get("date_jour") or "")}</div>'
                        f'<div class="rm-txt">{_fmt_txt(e.get("journal"))}</div></div>')
        parts.append('</div>')
        blocs.append("".join(parts))

    kpis = (
        '<div class="rm-kpis">'
        f'<div class="rm-kpi"><div class="n">{s["n_entrees"]}</div>'
        '<div class="l">Entrées</div></div>'
        f'<div class="rm-kpi"><div class="n">{s["n_redacteurs"]}</div>'
        '<div class="l">Rédacteurs</div></div>'
        f'<div class="rm-kpi"><div class="n">{s["n_jours_couverts"]}/{s["n_jours_periode"]}</div>'
        '<div class="l">Jours couverts</div></div>'
        f'<div class="rm-kpi"><div class="n">{s["n_districts"]}</div>'
        '<div class="l">Districts</div></div></div>')

    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RSU 2026 — Rapport de mission</title>'
        f'<style>{_STYLE}</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar rm-noprint">'
        '<h1>Rapport de mission</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a>'
        '<button class="rm-btn" onclick="window.print()">🖨 Imprimer / PDF</button>'
        '</div>'
        f'<p class="rm-sub">Période <strong>{esc(rapport["debut"])}</strong> → '
        f'<strong>{esc(rapport["fin"])}</strong> · Périmètre : {esc(perimetre_label)} · '
        f'généré le {esc(rapport["genere_le"])}</p>'
        '<div class="rm-note rm-noprint">📋 <strong>Compilation automatique</strong> des '
        'journaux de bord (aucune IA, aucune donnée envoyée à l\'extérieur). '
        'Une synthèse rédigée par IA pourra être ajoutée après décision (confidentialité).'
        '</div>'
        f'{ia_html}'
        f'<div class="rm-card">{kpis}</div>'
        + "".join(blocs) +
        '</div></body></html>')


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
        ".rm-f{display:grid;gap:.8rem;max-width:26rem}"
        ".rm-f label{font-weight:600;font-size:.85rem;display:block;margin-bottom:.2rem}"
        ".rm-f input,.rm-f select{width:100%;padding:.5rem .6rem;border:1px solid #cbd5e1;"
        "border-radius:.5rem;font-size:.9rem;font-family:inherit}"
        '</style></head><body><div class="rm-wrap">'
        '<div class="rm-bar"><h1>Rapport de mission</h1>'
        f'<a class="rm-btn sec" href="{esc(retour_href)}">← Retour</a></div>'
        '<p class="rm-sub">Compile les journaux de bord de la période choisie en un '
        'rapport structuré (hors-ligne, aucune donnée envoyée à l\'extérieur).</p>'
        f'<form class="rm-card rm-f" method="get" action="{esc(action)}">'
        f'<div><label>Du</label><input type="date" name="debut" value="{esc(debut_defaut)}" required></div>'
        f'<div><label>Au</label><input type="date" name="fin" value="{esc(fin_defaut)}" required></div>'
        f'<div><label>District</label><select name="district">{"".join(opts)}</select></div>'
        '<div><button class="rm-btn" type="submit">Générer le rapport</button></div>'
        '</form></div></body></html>')


# ---------------------------------------------------------------------------
# SYNTHÈSE IA (option, DÉSACTIVÉE par défaut — aucune sortie de données sans
# décision explicite). Rien ci-dessous n'est appelé tant que ia_active() est faux.
# ---------------------------------------------------------------------------
def ia_active() -> bool:
    """Vrai seulement si l'IA a été EXPLICITEMENT activée (env) ET une clé existe."""
    return (os.environ.get("RSU_IA_RAPPORT", "").strip() == "1"
            and bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()))


def synthese_ia(rapport):
    """(À BRANCHER) rédige une synthèse narrative via l'API Claude.

    Volontairement NON implémentée pour l'instant : tant que la décision de
    confidentialité (envoi des journaux à l'API) n'est pas prise, on ne code pas
    l'appel. Voir la discussion / le CLAUDE.md. Le squelette :

        import anthropic  # dépendance serveur à ajouter au venv
        client = anthropic.Anthropic()            # clé via ANTHROPIC_API_KEY
        texte = _journaux_en_texte(rapport)       # mise en forme des entrées
        msg = client.messages.create(
            model="claude-opus-5",                # modèle par défaut recommandé
            max_tokens=8000,
            system="Tu rédiges le rapport de mission RSU 2026 pour l'INSTAT ...",
            messages=[{"role": "user", "content": texte}],
        )
        return msg.content[0].text
    """
    raise NotImplementedError("Synthèse IA non activée (décision de confidentialité requise).")
