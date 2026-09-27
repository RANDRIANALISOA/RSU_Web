"""export_rapport.py — Export Excel du rapport de dénombrement (par district).

Produit un classeur .xlsx à partir des données en base (via le moteur `rapport_core`
pour construire la liste des ménages, exactement comme le rapport HTML) :

  Feuille 1 « Rapport global » :
    - Couverture par commune vs projection RGPH-3 2025 (+ total district) ;
    - Qualité / structure par commune : dénombrés, personnes, taille moyenne du
      ménage, écart-type de la taille, coefficient de variation de la taille,
      % de ménages présents, % GPS (+ total) ;
    - Un tableau par commune : détail par fokontany (mêmes colonnes).
  Feuille 2 « Dénombrement par agent-jour » :
    - Ménages dénombrés par agent et par jour, regroupés par commune puis par chef
      d'équipe ; une colonne par date.
  Feuille 3 « BaseDenParAgent » : table plate (commune, chef, agent, fokontany, dates).
  Feuille 4 « segment_multiple » : rapport « Segments multiples » (mêmes résultats que
    la page du tableau de bord) — un MÊME AGENT qui dénombre plus d'une fois le MÊME
    code de segment dans un MÊME fokontany (compté sur DEN_MENAGE) ; colonnes
    Fokontany / Segment / Agent / Nombre.
  Feuille 5 « Écart par agent » : SYNTHÈSE de l'écart déclaration <-> serveur,
    un agent = une ligne (jours déclarés, ménages déclarés, ménages reçus au
    serveur, écart, % du déclaré), le plus gros écart d'abord. Mêmes chiffres
    que la page « Par agent » du tableau de bord — un seul calcul,
    `rapport_core.ecart_declaration`.
  Feuille 6 « Écart déclaration-serveur » : le DÉTAIL par date de la feuille 5 —
    pour chaque agent, par chef d'équipe et par date, le nombre de ménages
    DÉCLARÉ (table `declaration_agent`, saisie du Superviseur Technique) face au
    nombre REÇU AU SERVEUR, et leur écart.

Les colonnes liées au CARNET e-Fokontany (avec / sans carnet, carnet scanné) ont été
RETIRÉES : la question a disparu du questionnaire de septembre 2026, ces colonnes ne
portaient plus que des « n/d ». Elles sont remplacées par des renseignements
réellement collectés : taille des ménages (moyenne et écart-type), personnes
dénombrées et taux de ménages présents.

Définitions : taille du ménage = `taille_menD` (seules les tailles > 0 entrent dans
la moyenne et l'écart-type) ; l'écart-type est celui de la POPULATION (le
dénombrement est exhaustif sur le périmètre) ; le coefficient de variation est
l'écart-type rapporté à la moyenne, en % ; ménage présent = `presence` = 1 ;
GPS capturé = latitude ET longitude numériques.
"""

import collections
import datetime
import io
import statistics

import db_source
import rapport_core
import zones
import equipes
import declarations

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# --- Styles ---------------------------------------------------------------
# NB : couleurs en ARGB 8 chiffres avec alpha OPAQUE « FF ». Sans le préfixe,
# openpyxl stocke un alpha « 00 » (transparent) que certains lecteurs (LibreOffice…)
# respectent -> fond « transparent » (blanc) + police blanche = texte invisible.
_TITRE = Font(bold=True, size=14, color="FF1F2937")
_SOUS = Font(bold=True, size=11, color="FF374151")
# En-tête : texte FONCÉ sur fond CLAIR (et non blanc sur bleu). Ainsi, même si un
# lecteur n'applique pas le remplissage, le texte reste lisible (jamais blanc/blanc).
_ENTETE_F = Font(bold=True, color="FF1F2937")
_ENTETE_FILL = PatternFill("solid", fgColor="FFDBEAFE")
_TOTAL_F = Font(bold=True)
_TOTAL_FILL = PatternFill("solid", fgColor="FFE5E7EB")
_COMMUNE_FILL = PatternFill("solid", fgColor="FFEFF6FF")
_bord = Side(style="thin", color="FFD1D5DB")
_BORDURE = Border(left=_bord, right=_bord, top=_bord, bottom=_bord)
_CENTRE = Alignment(horizontal="center")
_DROITE = Alignment(horizontal="right")


def _has_gps(m):
    la, lo = m.get("lat"), m.get("lon")
    return isinstance(la, (int, float)) and isinstance(lo, (int, float))


ND = "—"           # valeur non calculable (aucun ménage, aucune taille renseignée)

# Colonnes des tableaux « structure des ménages » (feuille 1). Les anciennes
# colonnes du carnet e-Fokontany (avec / sans carnet, scanné) ont disparu avec la
# question elle-même ; on publie à la place ce qui est RÉELLEMENT collecté.
_COLS_STRUCT = ["Ménages dénombrés", "Personnes dénombrées",
                "Taille moyenne du ménage", "Écart-type de la taille du ménage",
                "Coefficient de variation de la taille (%)",
                "Ménages présents (%)", "GPS capturé (%)"]
_LARG_STRUCT = [18, 18, 18, 20, 22, 16, 16]


def _stats(ms):
    """Indicateurs d'une liste de ménages, sous forme de LIGNE de tableau (sans
    le libellé de tête) : dénombrés, personnes, taille moyenne, écart-type de la
    taille, % de ménages présents, % GPS.

    Seules les tailles > 0 entrent dans la moyenne / l'écart-type (une taille nulle
    ou absente n'est pas un ménage d'une personne : c'est une taille non renseignée,
    même règle que le gabarit du tableau de bord). L'écart-type est celui de la
    POPULATION : sur un périmètre, le dénombrement est exhaustif.
    Renvoie aussi les cumuls nécessaires aux TOTAUX (voir `_cumul`)."""
    total = len(ms)
    tailles = [m["taille"] for m in ms if (m.get("taille") or 0) > 0]
    presents = sum(1 for m in ms if m.get("presence") == 1)
    renseignes = sum(1 for m in ms if m.get("presence") in (1, 2))
    gps = sum(1 for m in ms if _has_gps(m))
    return {
        "total": total,
        "tailles": tailles,
        "presents": presents,
        "presence_renseignee": renseignes,
        "gps": gps,
    }


def _cumul(acc, st):
    """Ajoute les indicateurs d'un sous-périmètre à un accumulateur de total."""
    acc["total"] += st["total"]
    acc["tailles"].extend(st["tailles"])
    acc["presents"] += st["presents"]
    acc["presence_renseignee"] += st["presence_renseignee"]
    acc["gps"] += st["gps"]
    return acc


def _acc_vide():
    return {"total": 0, "tailles": [], "presents": 0,
            "presence_renseignee": 0, "gps": 0}


def _ligne_struct(st):
    """Indicateurs -> les 7 cellules du tableau « structure des ménages ».

    Le COEFFICIENT DE VARIATION (écart-type / moyenne, en %) est la dispersion
    RELATIVE : il se compare d'une commune à l'autre même quand les tailles
    moyennes diffèrent, là où l'écart-type seul ne le permet pas. Calculé sur la
    moyenne et l'écart-type NON arrondis."""
    tailles = st["tailles"]
    personnes = sum(tailles)
    moy_x = (personnes / len(tailles)) if tailles else None
    ect_x = statistics.pstdev(tailles) if len(tailles) >= 2 else None
    moy = round(moy_x, 2) if moy_x is not None else ND
    ect = round(ect_x, 2) if ect_x is not None else ND
    cv = (round(100.0 * ect_x / moy_x, 1)
          if (ect_x is not None and moy_x) else ND)
    pres = (round(100.0 * st["presents"] / st["presence_renseignee"], 1)
            if st["presence_renseignee"] else ND)
    pgps = round(100.0 * st["gps"] / st["total"], 1) if st["total"] else ND
    return [st["total"], personnes, moy, ect, cv, pres, pgps]


def _donnees_scope(conn, code_district, communes_autorisees):
    """Construit, via le moteur (codes agent bruts), les données du périmètre :
    (menages, segments_den). `segments_den` = 1 objet par ligne DEN_MENAGE
    (fktcode, seg, agent, commune) — base du rapport « segments multiples »."""
    if communes_autorisees:
        source = db_source.source_db(
            conn, communes=[int(c) for c in communes_autorisees])
    else:
        source = db_source.source_db(conn, district=code_district)
    diag = rapport_core._charger_diagnostics(source("diagnostics"), agents_noms=None)
    seg_by_key, seg_liste = rapport_core._charger_segments(source("den"), diag)
    menages = rapport_core._construire_menages(source("roster"), seg_by_key)
    segments_den = rapport_core._construire_segments_den(seg_liste)
    return menages, segments_den


def _ecrire_entete(ws, ligne, colonnes, largeurs=None):
    for j, titre in enumerate(colonnes, start=1):
        c = ws.cell(row=ligne, column=j, value=titre)
        c.font = _ENTETE_F
        c.fill = _ENTETE_FILL
        c.border = _BORDURE
        # Retour à la ligne : les intitulés longs s'affichent en entier.
        c.alignment = Alignment(
            horizontal=("center" if j > 1 else "left"),
            vertical="center", wrap_text=True)
    ws.row_dimensions[ligne].height = 42
    if largeurs:
        for j, w in enumerate(largeurs, start=1):
            ws.column_dimensions[get_column_letter(j)].width = w
    return ligne + 1


def _ligne(ws, ligne, valeurs, total=False, fill=None):
    for j, v in enumerate(valeurs, start=1):
        c = ws.cell(row=ligne, column=j, value=v)
        c.border = _BORDURE
        if j > 1 and isinstance(v, (int, float)):
            c.alignment = _DROITE
        if total:
            c.font = _TOTAL_F
        if fill:
            c.fill = fill
        elif total:
            c.fill = _TOTAL_FILL
    return ligne + 1


_SOURCE_F = Font(italic=True, size=9, color="FF6B7280")


def _titre(ws, ligne, texte):
    """Titre de tableau (gras) suivi d'une LIGNE VIDE. Renvoie la ligne de
    l'en-tête à écrire ensuite (titre en `ligne`, vide en `ligne+1`)."""
    ws.cell(row=ligne, column=1, value=texte).font = _SOUS
    return ligne + 2


def _sous_titre(ws, ligne, texte, ncols):
    """Titre de sous-section (habillé d'un fond clair) + ligne vide."""
    c = ws.cell(row=ligne, column=1, value=texte)
    c.font = _SOUS
    for j in range(1, ncols + 1):
        ws.cell(row=ligne, column=j).fill = _COMMUNE_FILL
    return ligne + 2


def _source(ws, ligne):
    """« Source » en ITALIQUE sous un tableau + une ligne vide. Renvoie la ligne
    suivante libre."""
    ws.cell(row=ligne, column=1,
            value="Source : Dénombrement RSU 2026").font = _SOURCE_F
    return ligne + 2


def _entete_document(ws, nom_district, note):
    """Bloc d'en-tête IDENTIQUE sur toutes les feuilles (parité de style avec la
    feuille « Rapport global ») : titre, district, date de génération, puis une
    note de lecture propre à la feuille (en italique). Renvoie la 1re ligne de
    contenu (6, avec une ligne vide en 5)."""
    ws.cell(row=1, column=1, value="Dénombrement RSU 2026").font = _TITRE
    ws.cell(row=2, column=1, value=f"District : {nom_district}").font = _SOUS
    ws.cell(row=3, column=1,
            value="Généré le : "
            + datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    ws.cell(row=4, column=1, value=note).font = _SOURCE_F
    return 6


# ---------------------------------------------------------------------------
# Feuille 1 : Rapport global
# ---------------------------------------------------------------------------
def _feuille_global(wb, conn, code_district, nom_district, menages,
                    communes_autorisees):
    ws = wb.active
    ws.title = "Rapport global"

    # Référentiel : communes et fokontany du périmètre (inclut les vides).
    ref = zones.reference_district(conn, code_district)
    if communes_autorisees is not None:
        ref = [z for z in ref if z["ccode"] in communes_autorisees]
    communes = {}       # ccode -> nom
    fkt_par_commune = {}  # ccode -> [(fkt, label)]
    for z in ref:
        communes.setdefault(z["ccode"], z["commune"])
        fkt_par_commune.setdefault(z["ccode"], []).append((z["fkt"], z["label"]))
    ordre_com = sorted(communes, key=lambda c: (communes[c] or "", c))

    # Ménages regroupés par commune (fktcode[:6]) et par fokontany (fktcode).
    par_com, par_fkt = {}, {}
    for m in menages:
        fc = m.get("fktcode") or ""
        cc = fc[:6] if len(fc) >= 6 else ""
        par_com.setdefault(cc, []).append(m)
        par_fkt.setdefault(fc, []).append(m)

    # -- En-tête du document (bloc partagé) --
    r = _entete_document(
        ws, nom_district,
        "Lecture : sauf « Personnes dénombrées », « Taille… » et les colonnes "
        "« (%) », les valeurs sont des NOMBRES DE MÉNAGES. « Ménages attendus » = "
        "projection RGPH-3 2025 ; « Ménages dénombrés » = ménages recensés "
        "(RSU 2026) ; « Taille du ménage » = nombre de personnes du ménage "
        "(tailles renseignées uniquement) ; « Coefficient de variation » = "
        "écart-type ÷ moyenne, en % (dispersion RELATIVE, comparable d'une "
        "commune à l'autre) ; « — » = non calculable.")

    # -- Tableau 1 : couverture par commune (projection RGPH-3 2025) --
    r = _titre(ws, r, "Tableau 1 — Couverture du dénombrement "
               "(ménages dénombrés vs projection RGPH-3 2025)")
    r = _ecrire_entete(
        ws, r,
        ["Commune", "Ménages attendus (projection RGPH-3 2025)",
         "Ménages dénombrés (RSU 2026)", "Taux de couverture (%)"],
        largeurs=[34, 30, 26, 20])
    attendus = zones.attendus_communes(conn, ordre_com)
    tot_att = tot_real = 0
    for cc in ordre_com:
        att = (attendus.get(cc, {}).get("attendu") or 0)
        real = len(par_com.get(cc, []))
        tot_att += att
        tot_real += real
        pct = round(100.0 * real / att, 1) if att else None
        r = _ligne(ws, r, [communes[cc], att, real,
                           (pct if pct is not None else "—")])
    pct_tot = round(100.0 * tot_real / tot_att, 1) if tot_att else None
    r = _ligne(ws, r, ["TOTAL DISTRICT", tot_att, tot_real,
                       (pct_tot if pct_tot is not None else "—")], total=True)
    r = _source(ws, r)

    # -- Tableau 2 : structure des ménages et qualité, par commune --
    r = _titre(ws, r, "Tableau 2 — Structure des ménages et qualité du "
               "dénombrement, par commune")
    r = _ecrire_entete(ws, r, ["Commune"] + _COLS_STRUCT,
                       largeurs=[34] + _LARG_STRUCT)
    tot = _acc_vide()
    for cc in ordre_com:
        st = _stats(par_com.get(cc, []))
        _cumul(tot, st)
        r = _ligne(ws, r, [communes[cc]] + _ligne_struct(st))
    r = _ligne(ws, r, ["TOTAL DISTRICT"] + _ligne_struct(tot), total=True)
    r = _source(ws, r)

    # -- Tableau 3 : détail par commune (par fokontany) --
    r = _titre(ws, r, "Tableau 3 — Détail par commune (par fokontany)")
    ncol_struct = 1 + len(_COLS_STRUCT)
    for cc in ordre_com:
        r = _sous_titre(ws, r, f"Commune : {communes[cc]}", ncol_struct)
        r = _ecrire_entete(ws, r, ["Fokontany"] + _COLS_STRUCT,
                           largeurs=[34] + _LARG_STRUCT)
        tot_c = _acc_vide()
        for fkt, label in sorted(fkt_par_commune.get(cc, []),
                                 key=lambda x: (x[1] or "", x[0])):
            st = _stats(par_fkt.get(fkt, []))
            _cumul(tot_c, st)
            r = _ligne(ws, r, [label] + _ligne_struct(st))
        r = _ligne(ws, r, [f"Total {communes[cc]}"] + _ligne_struct(tot_c),
                   total=True)
        r += 1                                   # espace entre communes
    r = _source(ws, r)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Feuille 2 : Dénombrement par agent et par jour
# ---------------------------------------------------------------------------
def _feuille_agents(wb, conn, nom_district, menages):
    ws = wb.create_sheet("Dénombrement par agent-jour")
    ac = equipes.agents_et_chefs(conn)
    from collections import defaultdict

    # Dates observées (AAAAMMJJ valides) triées.
    dates = sorted({m["date"] for m in menages
                    if rapport_core._valid_date(m.get("date"))})

    def _jj(d):
        return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d) == 8 else d

    # Regroupement : chef d'équipe -> (commune, agent) -> {date: n}. Le chef est
    # identifié par son NOM s'il est renseigné, sinon par son CODE (login_ce) —
    # ainsi « un tableau par chef » tient dès que le lien existe, même sans nom.
    cnt = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for m in menages:
        d = m.get("date")
        if not rapport_core._valid_date(d):
            continue
        commune = m.get("commune") or "(commune inconnue)"
        code = (m.get("agent") or "").strip()
        info = ac.get(code, {})
        agent_nom = info.get("nom") or code or "(agent inconnu)"
        chef = (info.get("chef_nom") or info.get("chef_login")
                or "(chef non affecté)")
        cnt[chef][(commune, agent_nom)][d] += 1

    # -- En-tête du document (bloc partagé, identique au « Rapport global ») --
    r = _entete_document(
        ws, nom_district,
        "Un tableau par chef d'équipe. Chaque valeur (colonnes de dates) "
        "= NOMBRE DE MÉNAGES DÉNOMBRÉS par l'agent ce jour-là.")
    r = _titre(ws, r, "Tableau — Dénombrement par agent et par jour "
               "(un tableau par chef d'équipe)")

    ncol = 2 + len(dates) + 1                     # Commune + Agent + dates + Total
    entete = ["Commune", "Agent"] + [_jj(d) for d in dates] + ["Total"]
    largeurs = [26, 28] + [11] * len(dates) + [10]

    # Un TABLEAU par chef d'équipe (même style que le « Rapport global »).
    def _tri_chef(k):
        return (1, k) if k.startswith("(chef") else (0, k)   # « non affecté » en dernier
    for chef in sorted(cnt, key=_tri_chef):
        r = _sous_titre(ws, r, f"Chef d'équipe : {chef}", ncol)
        r = _ecrire_entete(ws, r, entete, largeurs=largeurs)
        sous = cnt[chef]
        tot_col = [0] * len(dates)
        for (commune, agent_nom) in sorted(sous, key=lambda x: (x[0], x[1])):
            par_date = sous[(commune, agent_nom)]
            row = [commune, agent_nom]
            tot = 0
            for k, d in enumerate(dates):
                n = par_date.get(d, 0)
                row.append(n if n else "")
                tot += n
                tot_col[k] += n
            row.append(tot)
            r = _ligne(ws, r, row)
        r = _ligne(ws, r, [f"Total {chef}", ""]
                   + [g if g else "" for g in tot_col] + [sum(tot_col)], total=True)
        r = _source(ws, r)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Feuille 3 : BaseDenParAgent (table PLATE, une ligne par agent×zone)
# ---------------------------------------------------------------------------
def _feuille_base_agents(wb, conn, nom_district, menages):
    """Table « base » plate : une ligne par (commune, chef, agent, fokontany),
    colonnes = dates, cellule = nombre de ménages dénombrés. Pensée pour un
    tableau croisé dynamique / export brut."""
    ws = wb.create_sheet("BaseDenParAgent")
    ac = equipes.agents_et_chefs(conn)
    from collections import defaultdict

    dates = sorted({m["date"] for m in menages
                    if rapport_core._valid_date(m.get("date"))})

    def _jj(d):
        return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d) == 8 else d

    # (commune, chef_nom, agent_nom, fokontany) -> {date: n}
    cnt = defaultdict(lambda: defaultdict(int))
    for m in menages:
        d = m.get("date")
        if not rapport_core._valid_date(d):
            continue
        commune = m.get("commune") or "(commune inconnue)"
        fkt = m.get("fkt") or m.get("fktcode") or ""
        code = (m.get("agent") or "").strip()
        info = ac.get(code, {})
        agent_nom = info.get("nom") or code or "(agent inconnu)"
        chef = (info.get("chef_nom") or info.get("chef_login")
                or "(chef non affecté)")
        cnt[(commune, chef, agent_nom, fkt)][d] += 1

    # -- En-tête du document (bloc partagé, identique au « Rapport global ») --
    r = _entete_document(
        ws, nom_district,
        "Une ligne par (commune, chef d'équipe, agent, fokontany). "
        "Chaque valeur de date = NOMBRE DE MÉNAGES DÉNOMBRÉS ce jour-là.")
    r = _titre(ws, r, "Tableau — Base dénombrement par agent et par jour")

    entete = (["Commune", "Chef d'équipe", "Agent", "Fokontany"]
              + [_jj(d) for d in dates] + ["Total"])
    largeurs = [24, 24, 26, 28] + [11] * len(dates) + [10]
    r = _ecrire_entete(ws, r, entete, largeurs=largeurs)

    grand = [0] * len(dates)
    for cle in sorted(cnt, key=lambda k: (k[0], k[1], k[2], k[3])):
        commune, chef, agent, fkt = cle
        par_date = cnt[cle]
        row = [commune, chef, agent, fkt]
        tot = 0
        for k, d in enumerate(dates):
            n = par_date.get(d, 0)
            row.append(n if n else "")
            tot += n
            grand[k] += n
        row.append(tot)
        r = _ligne(ws, r, row)
    r = _ligne(ws, r, ["TOTAL", "", "", ""]
               + [g if g else "" for g in grand] + [sum(grand)], total=True)
    r = _source(ws, r)
    # Fige les 4 colonnes de gauche + le bloc d'en-tête (jusqu'à la ligne d'en-tête
    # du tableau en ligne 8 : bloc document 1-4, titre 6, en-tête 8).
    ws.freeze_panes = "E9"


# ---------------------------------------------------------------------------
# Feuille 4 : segment_multiple (rapport « Segments multiples »)
# ---------------------------------------------------------------------------
def _feuille_segments_multiples(wb, conn, code_district, nom_district,
                                segments_den, communes_autorisees):
    """Rapport « Segments multiples » (même définition que le gabarit).

    Un segment est MULTIPLE quand un MÊME AGENT dénombre plus d'une fois le MÊME
    code de segment dans un MÊME fokontany — compté sur les lignes DEN_MENAGE
    (`segments_den`). Clé = (fokontany, code, agent) : on ne mélange pas les S01
    de fokontany différents, et deux agents qui font chacun le S01 d'un même
    fokontany ne sont PAS un doublon (partage de travail ; règle révisée le
    2026-09-17). Colonnes Fokontany / Segment / Agent / Nombre, comme la page du
    tableau de bord."""
    ws = wb.create_sheet("segment_multiple")
    ac = equipes.agents_et_chefs(conn)

    # Libellés fokontany depuis le référentiel (comme NAV_TREE côté gabarit).
    ref = zones.reference_district(conn, code_district)
    if communes_autorisees is not None:
        ref = [z for z in ref if z["ccode"] in communes_autorisees]
    fkt_label = {z["fkt"]: z["label"] for z in ref}

    # Regroupement par (fokontany, code segment, AGENT) : n = lignes DEN_MENAGE.
    groups = {}
    for s in segments_den:
        fk = (str(s.get("fktcode")).strip() if s.get("fktcode") else "") \
            or "(fkt manquant)"
        code = (str(s.get("seg")).strip() if s.get("seg") else "") \
            or "(code manquant)"
        ag = (s.get("agent") or "").strip()
        # Nom de l'agent s'il est renseigne dans `agent`, sinon son code.
        agent = (ac.get(ag, {}).get("nom") or ag) if ag else "(agent inconnu)"
        groups[(fk, code, agent)] = groups.get((fk, code, agent), 0) + 1

    multiples = [(fk, code, agent, n)
                 for (fk, code, agent), n in groups.items() if n > 1]
    # Tri : libellé de fokontany, nombre décroissant, code, agent.
    multiples.sort(key=lambda x: ((fkt_label.get(x[0]) or x[0]), -x[3], x[1], x[2]))

    nb_fkt = len({m[0] for m in multiples})
    portee = "ce district" if communes_autorisees is None else "ces communes"
    r = _entete_document(
        ws, nom_district,
        f"Un segment est « multiple » quand un MÊME AGENT dénombre plus d'une fois "
        f"le MÊME code de segment dans un MÊME fokontany (d'après DEN_MENAGE). "
        f"Deux agents différents qui font chacun le S01 d'un même fokontany ne sont "
        f"PAS un doublon : c'est un partage de travail. {len(multiples)} cas dans "
        f"{nb_fkt} fokontany · {len(segments_den)} segment(s) dénombré(s) dans "
        f"{portee}.")
    r = _titre(ws, r, "Tableau — Segments multiples "
               "(mêmes résultats que la page « Segments multiples » du tableau de bord)")
    r = _ecrire_entete(
        ws, r,
        ["Fokontany", "Segment", "Agent", "Nombre de fois dénombré"],
        largeurs=[34, 16, 34, 22])

    if multiples:
        for fk, code, agent, n in multiples:
            label = fkt_label.get(fk) or fk
            r = _ligne(ws, r, [label, code, agent, n])
        r = _ligne(ws, r,
                   [f"TOTAL — {len(multiples)} cas", "", "",
                    sum(m[3] for m in multiples)], total=True)
    else:
        r = _ligne(ws, r, ["Aucun segment multiple dans ce périmètre", "", "", ""])
    r = _source(ws, r)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Écart DÉCLARATION <-> SERVEUR : données communes aux feuilles 5 et 6
# ---------------------------------------------------------------------------
def _ecart_donnees(conn, menages):
    """(ac, recu, declare, codes_serveur) pour le périmètre du classeur.

    - `recu` : {(code agent, date AAAAMMJJ): ménages arrivés au serveur} — les
      ménages sans date valide sont ignorés (comparables à aucune déclaration) ;
    - `declare` : {(code agent, date): ménages DÉCLARÉS}, borné au périmètre
      (agents ayant des données ici, plus ceux rattachés à un chef d'équipe du
      périmètre : un agent peut avoir déclaré alors que RIEN n'est encore arrivé).
    """
    ac = equipes.agents_et_chefs(conn)
    recu = collections.defaultdict(int)
    codes_serveur = set()
    for m in menages:
        d = m.get("date")
        if not rapport_core._valid_date(d):
            continue
        code = (m.get("agent") or "").strip()
        recu[(code, d)] += 1
        if code:
            codes_serveur.add(code)
    declare = declarations.par_agent_date_perimetre(conn, "DEN", codes_serveur, ac)
    return ac, recu, declare, codes_serveur


# ---------------------------------------------------------------------------
# Feuille 5 : Écart déclaration-serveur PAR AGENT (une ligne par agent)
# ---------------------------------------------------------------------------
def _feuille_ecart_agent(wb, conn, nom_district, menages):
    """Synthèse PAR AGENT de l'écart déclaration <-> serveur : un agent, une
    ligne (jours déclarés, ménages déclarés, ménages reçus, écart, % du déclaré),
    le plus gros écart d'abord.

    Mêmes chiffres que la page « Par agent » du tableau de bord : le calcul est
    fait par `rapport_core.ecart_declaration`, une seule source de vérité. La
    feuille suivante en donne le DÉTAIL par date, chef d'équipe par chef d'équipe.
    """
    ws = wb.create_sheet("Écart par agent")
    ac, _recu, declare, codes_serveur = _ecart_donnees(conn, menages)

    def _chef(code):
        info = ac.get(code, {})
        return (info.get("chef_nom") or info.get("chef_login")
                or "(chef non affecté)")

    def _nom(code):
        return (ac.get(code, {}).get("nom") or code or "(agent inconnu)")

    synth = rapport_core.ecart_declaration(
        menages, declare,
        {c: _chef(c) for c in (codes_serveur | {c for c, _ in declare})})

    r = _entete_document(
        ws, nom_district,
        "Un agent, une ligne. Écart = DÉCLARÉ par l'agent − REÇU au serveur, sur "
        "toute la période. Écart > 0 : il est arrivé MOINS que déclaré "
        "(synchronisation en retard, ou sur-déclaration). Écart < 0 : il est "
        "arrivé PLUS que déclaré. « — » : aucune déclaration saisie pour cet "
        "agent (ce n'est pas un zéro). Le détail par date figure sur la feuille "
        "« Écart déclaration-serveur ».")
    r = _titre(ws, r, "Tableau — Écart déclaration-serveur par agent "
               "(le plus gros écart d'abord)")

    # Sans AUCUNE déclaration saisie, le tableau ne porterait que des « — » :
    # on l'annonce en une ligne (même règle que la page « Par agent »).
    if not synth["total"]["declarants"]:
        r = _ligne(ws, r, [
            "Aucune déclaration d'agent n'a été saisie pour ce périmètre : "
            "l'écart ne peut pas être calculé. Ces déclarations sont saisies par "
            "le Superviseur Technique (« Déclaration des agents »).",
            "", "", "", "", "", ""])
        if synth["agents"]:
            r = _ligne(ws, r, [
                f"{synth['total']['agents']} agent(s) ont des données reçues au "
                f"serveur ({synth['total']['recu']} ménages).",
                "", "", "", "", "", ""])
        r = _source(ws, r)
        ws.freeze_panes = "A2"
        return

    r = _ecrire_entete(
        ws, r,
        ["Agent", "Chef d'équipe", "Jours déclarés", "Ménages déclarés",
         "Ménages reçus au serveur", "Écart (déclaré − reçu)",
         "Écart (% du déclaré)"],
        largeurs=[30, 26, 14, 18, 22, 20, 20])
    for a in synth["agents"]:
        r = _ligne(ws, r, [
            _nom(a["agent"]), a["chef"] or ND,
            a["joursDeclares"] or ND,
            ND if a["declare"] is None else a["declare"],
            a["recu"],
            ND if a["ecart"] is None else a["ecart"],
            ND if a["pct"] is None else a["pct"]])
    t = synth["total"]
    r = _ligne(ws, r, [f"TOTAL — {t['agents']} agent(s)", "", "",
                       t["declare"], t["recu"], t["ecart"],
                       (t["pct"] if t["pct"] is not None else ND)], total=True)
    r = _ligne(ws, r, [f"{t['declarants']} agent(s) avec déclaration saisie ; "
                       f"{t['sansDeclaration']} agent(s) avec des données reçues "
                       f"mais AUCUNE déclaration.", "", "", "", "", "", ""])
    r = _source(ws, r)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Feuille 6 : Écart DÉCLARATION / SERVEUR, DÉTAIL par chef d'équipe et par date
# ---------------------------------------------------------------------------
def _feuille_ecart_declaration(wb, conn, nom_district, menages):
    """Confronte, pour chaque agent, par chef d'équipe et par date :
      - le nombre de ménages DÉCLARÉ par l'agent (table `declaration_agent`,
        saisie par le Superviseur Technique depuis un modèle Excel) ;
      - le nombre REÇU AU SERVEUR (ménages effectivement transcrits) ;
      - leur ÉCART (déclaré − reçu) : positif = l'agent déclare plus qu'il n'est
        arrivé (données non synchronisées, ou sur-déclaration) ; négatif = il est
        arrivé plus que déclaré.

    Périmètre : les agents ayant des données dans ce district/ces communes, plus
    ceux qui ont déclaré et dépendent d'un chef d'équipe du périmètre (cas d'un
    agent qui déclare alors que RIEN n'est encore arrivé au serveur)."""
    ws = wb.create_sheet("Écart déclaration-serveur")
    ac, recu, declare, codes_serveur = _ecart_donnees(conn, menages)

    def _jj(d):
        return f"{d[6:8]}/{d[4:6]}/{d[0:4]}" if len(d) == 8 else d

    def _chef(code):
        info = ac.get(code, {})
        return (info.get("chef_nom") or info.get("chef_login")
                or "(chef non affecté)")

    def _nom(code):
        return (ac.get(code, {}).get("nom") or code or "(agent inconnu)")

    # chef -> (agent, date) -> [déclaré|None, reçu|None]
    lignes = collections.defaultdict(dict)
    for (code, d), n in declare.items():
        lignes[_chef(code)].setdefault((code, d), [None, None])[0] = n
    for (code, d), n in recu.items():
        lignes[_chef(code)].setdefault((code, d), [None, None])[1] = n

    nb_vad = declarations.compter(conn, "VAD")["lignes"]
    note_vad = ("" if not nb_vad else
                f" {nb_vad} déclaration(s) VAD sont également en base : elles ne "
                "sont pas comparables tant que les données VAD n'arrivent pas au "
                "serveur.")
    r = _entete_document(
        ws, nom_district,
        "Écart = DÉCLARÉ par l'agent − REÇU au serveur, pour chaque agent et "
        "chaque date, regroupé par chef d'équipe. Écart > 0 : il est arrivé MOINS "
        "que déclaré (synchronisation en retard, ou sur-déclaration). Écart < 0 : "
        "il est arrivé PLUS que déclaré. « — » : pas de déclaration saisie pour "
        "ce jour-là (ce n'est pas un zéro)." + note_vad)
    if not lignes:
        r = _titre(ws, r, "Tableau — Déclaration des agents face aux données "
                   "reçues (dénombrement)")
        r = _ligne(ws, r, ["Aucune déclaration saisie et aucune donnée reçue "
                           "pour ce périmètre.", "", "", "", "", ""])
        r = _source(ws, r)
        ws.freeze_panes = "A2"
        return

    r = _titre(ws, r, "Détail par date — Déclaration des agents face aux données "
               "reçues (dénombrement, un tableau par chef d'équipe)")

    entete = ["Agent", "Date", "Ménages déclarés", "Ménages reçus au serveur",
              "Écart (déclaré − reçu)", "Écart (% du déclaré)"]
    largeurs = [30, 14, 18, 22, 20, 20]

    def _tri_chef(k):
        return (1, k) if k.startswith("(chef") else (0, k)

    g_dec = g_rec = 0
    for chef in sorted(lignes, key=_tri_chef):
        r = _sous_titre(ws, r, f"Chef d'équipe : {chef}", len(entete))
        r = _ecrire_entete(ws, r, entete, largeurs=largeurs)
        sous = lignes[chef]
        t_dec = t_rec = 0
        for (code, d) in sorted(sous, key=lambda k: (_nom(k[0]), k[1])):
            dec, rec = sous[(code, d)]
            rec_n = rec or 0
            t_rec += rec_n
            if dec is None:
                r = _ligne(ws, r, [_nom(code), _jj(d), ND, rec_n, ND, ND])
                continue
            t_dec += dec
            ecart = dec - rec_n
            pct = round(100.0 * ecart / dec, 1) if dec else ND
            r = _ligne(ws, r, [_nom(code), _jj(d), dec, rec_n, ecart, pct])
        e = t_dec - t_rec
        r = _ligne(ws, r,
                   [f"Total {chef}", "", t_dec, t_rec, e,
                    (round(100.0 * e / t_dec, 1) if t_dec else ND)], total=True)
        r = _source(ws, r)
        g_dec += t_dec
        g_rec += t_rec

    ge = g_dec - g_rec
    r = _ligne(ws, r, ["TOTAL — tous chefs d'équipe", "", g_dec, g_rec, ge,
                       (round(100.0 * ge / g_dec, 1) if g_dec else ND)],
               total=True)
    r = _source(ws, r)
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def generer_classeur(conn, code_district, nom_district, communes_autorisees=None):
    """Renvoie le classeur Excel (openpyxl Workbook) du district."""
    menages, segments_den = _donnees_scope(conn, code_district,
                                           communes_autorisees)
    wb = Workbook()
    _feuille_global(wb, conn, code_district, nom_district, menages,
                    communes_autorisees)
    _feuille_agents(wb, conn, nom_district, menages)
    _feuille_base_agents(wb, conn, nom_district, menages)
    _feuille_segments_multiples(wb, conn, code_district, nom_district,
                                segments_den, communes_autorisees)
    _feuille_ecart_agent(wb, conn, nom_district, menages)
    _feuille_ecart_declaration(wb, conn, nom_district, menages)
    return wb


def generer_bytes(conn, code_district, nom_district, communes_autorisees=None):
    """Renvoie le classeur sérialisé (bytes) prêt à télécharger."""
    wb = generer_classeur(conn, code_district, nom_district, communes_autorisees)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def nom_fichier(code_district, quand=None):
    """« Rapport_DEN_<code district>_<AAAAMMJJ>_<HHMM>.xlsx », ex.
    Rapport_DEN_6305_20260926_1745.xlsx — même format que le classeur VAD
    (`export_vad.nom_fichier`)."""
    d = quand or datetime.datetime.now()
    return f"Rapport_DEN_{code_district}_{d.strftime('%Y%m%d_%H%M')}.xlsx"
