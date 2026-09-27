"""export_vad.py — Export Excel du rapport « Visite à domicile » (VAD).

Le pendant de `export_rapport.py`, qui fait la même chose pour le dénombrement.
Les styles sont d'ailleurs IMPORTÉS de ce module plutôt que redéfinis : un
classeur VAD et un classeur dénombrement doivent se ressembler, et deux jeux de
constantes de couleur finiraient par diverger.

Neuf feuilles, dans l'ordre où on les lit :

  1. « Global »                        avancement, couverture, statuts,
                                       consentement, puis le détail par commune
                                       et par fokontany ;
  2. « Erreur ménage »                 une ligne par ménage en anomalie et UNE
                                       COLONNE PAR CONTRÔLE (la cellule porte le
                                       message de correction), comme le listing
                                       du tableau de bord et le dofile d'origine ;
  3. « Erreur Individu »               la même chose au niveau de la personne ;
  4. « Test qualité données globale »  les indicateurs de `vad_qualite_base` —
                                       le RSU confronté au RGPH-3 et aux normes
                                       démographiques ;
  5. « Test qualité données par Agent » la matrice agent × test de
                                       `vad_qualite`, une ligne par enquêteur ;
  6. « Écart par agent »               une ligne par AGENT × DATE, pour TOUS
                                       les agents (déclaration saisie ou non) :
                                       déclaré, arrivé au serveur, écart, et les
                                       interviews arrivées par statut ;
                                       sous-total par agent, total général.
  7. « Couverture par agent »          l'AFFECTATION du préchargement face aux
                                       interviews VAD : ménages affectés,
                                       affectés interviewés, couverture, statuts,
                                       non affectés interviewés ;
  8. « Reste à interviewer »           les ménages affectés et pas encore
                                       interviewés, agent par agent ;
  9. « Doubles interviews »            les ménages interviewés plus d'une fois.

⚠️ Les noms de feuilles sont volontairement plus courts que les intitulés des
pages : Excel refuse tout nom de feuille au-delà de 31 caractères, et « Test de
qualité de données globale » en compte 34. Les titres écrits DANS la feuille,
eux, sont complets.
"""

import datetime
import io
import re
import unicodedata

import vad_core
import vad_qualite
import vad_qualite_base

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from export_rapport import (_BORDURE, _COMMUNE_FILL, _DROITE, _ENTETE_F,
                            _ENTETE_FILL, _SOURCE_F, _SOUS, _TITRE, _TOTAL_F,
                            _TOTAL_FILL, _ecrire_entete, _ligne, _sous_titre,
                            _titre)

ND = "—"

# Couleurs des verdicts, alignées sur celles du tableau de bord. ARGB opaque
# (préfixe « FF ») : sans lui, certains lecteurs rendent le fond transparent.
_FILL = {
    "alerte": PatternFill("solid", fgColor="FFFEE2E2"),
    "vigilance": PatternFill("solid", fgColor="FFFEF3C7"),
    "ok": PatternFill("solid", fgColor="FFD1FAE5"),
    "nd": PatternFill("solid", fgColor="FFF1F5F9"),
    "rem": PatternFill("solid", fgColor="FFDBEAFE"),
}
_VERDICT = {"alerte": "Alerte", "vigilance": "À surveiller", "ok": "Conforme",
            "nd": "Non calculé", "rem": "Résultat de zone"}


def _jour(d):
    """« 20251014 » -> « 14/10/2025 ». Laisse passer ce qui n'a pas ce format."""
    s = str(d or "")
    return f"{s[6:8]}/{s[4:6]}/{s[0:4]}" if len(s) == 8 and s.isdigit() else (s or ND)


def _v(x):
    """Valeur prête pour une cellule : None -> tiret, arrondi des flottants."""
    if x is None:
        return ND
    if isinstance(x, float):
        return round(x, 2)
    return x


def _entete(ws, portee, note):
    """Bloc d'en-tête commun aux cinq feuilles. Renvoie la 1re ligne libre."""
    ws.cell(row=1, column=1, value="RSU 2026 — Visite à domicile").font = _TITRE
    ws.cell(row=2, column=1, value=f"Périmètre : {portee}").font = _SOUS
    ws.cell(row=3, column=1, value="Généré le : "
            + datetime.datetime.now().strftime("%d/%m/%Y %H:%M"))
    ws.cell(row=4, column=1, value=note).font = _SOURCE_F
    return 6


def _source(ws, ligne, texte="Source : Visite à domicile, RSU 2026"):
    ws.cell(row=ligne, column=1, value=texte).font = _SOURCE_F
    return ligne + 2


# ---------------------------------------------------------------------------
# Feuille 1 — Global
# ---------------------------------------------------------------------------
def _detail_communes(ws, r, cc):
    """Détail par commune : couverture (ménages dénombrés = attendus) et
    comparaison RSU ↔ RGPH-3 2018 de la taille des ménages et du rapport de
    masculinité. Écart = RSU − RGPH-3. Calcul : `vad_core._couverture_communes`."""
    lignes = cc.get("lignes") or []
    if not lignes:
        return r
    r = _sous_titre(ws, r, "Détail par commune — couverture et comparaison "
                    "au RGPH-3 2018 (la moins couverte d'abord)", 12)
    # En-tête sur DEUX lignes : un groupe « Taille moyenne des ménages » et un
    # groupe « Rapport de masculinité », chacun séparé en RSU | RGPH-3 | Écart.
    groupes = [(1, 5, ""), (6, 8, "Taille moyenne des ménages"),
               (9, 11, "Rapport de masculinité (hommes pour 100 femmes)")]
    for c1, c2, lib in groupes:
        for j in range(c1, c2 + 1):
            c = ws.cell(row=r, column=j, value=lib if j == c1 else None)
            c.font, c.fill, c.border = _ENTETE_F, _ENTETE_FILL, _BORDURE
            c.alignment = Alignment(horizontal="center", vertical="center",
                                    wrap_text=True)
        if c2 > c1 and lib:
            ws.merge_cells(start_row=r, start_column=c1, end_row=r,
                           end_column=c2)
    r = _ecrire_entete(
        ws, r + 1,
        ["Commune", "Code", "Ménages attendus (dénombrés)",
         "Ménages interviewés", "Couverture (%)",
         "RSU", "RGPH-3", "Écart (RSU − RGPH-3)",
         "RSU", "RGPH-3", "Écart (RSU − RGPH-3)"],
        [34, 12, 16, 14, 13, 12, 12, 14, 12, 12, 14])
    for z in lignes:
        r = _ligne(ws, r, [z["commune"], z["code"] or ND, _v(z["attendus"]),
                           z["interviewes"], _v(z["couverture"]),
                           _v(z["tailleRsu"]), _v(z["tailleRgph"]),
                           _v(z["ecartTaille"]), _v(z["mascRsu"]),
                           _v(z["mascRgph"]), _v(z["ecartMasc"])])
    t = cc.get("total") or {}
    r = _ligne(ws, r, ["Total", "", _v(t.get("attendus")), t.get("interviewes"),
                       _v(t.get("couverture")), _v(t.get("tailleRsu")),
                       _v(t.get("tailleRgph")), _v(t.get("ecartTaille")),
                       _v(t.get("mascRsu")), _v(t.get("mascRgph")),
                       _v(t.get("ecartMasc"))], total=True)
    r = _ligne(ws, r, [
        "Ménages attendus = ménages du dénombrement. Un ménage interviewé "
        "plusieurs fois compte une fois. Taille = personnes ÷ ménages. Rapport "
        "de masculinité = hommes pour 100 femmes (âges renseignés). Écart = "
        "RSU − RGPH-3. RGPH-3 2018 : échantillon 10 %, redressé ×10."]
        + [""] * 10)
    return _source(ws, r + 1, "Sources : Visite à domicile et dénombrement, "
                              "RSU 2026 ; RGPH-3 2018 (INSTAT)")


def _feuille_global(wb, agg, portee):
    ws = wb.active
    ws.title = "Global"
    g = agg["global"]
    r = _entete(ws, portee,
                "Vue d'ensemble de la collecte : avancement, couverture, "
                "statuts et consentement, puis le détail par zone.")

    r = _titre(ws, r, "Synthèse")
    r = _ecrire_entete(ws, r, ["Indicateur", "Valeur", "Précision"],
                       [42, 16, 46])
    taille, duree = g.get("taille") or {}, g.get("duree") or {}
    cv = g.get("couverture") or {}
    lignes = [
        ("Ménages interviewés", g.get("menages"), ""),
        ("Personnes enregistrées", g.get("membres"), ""),
        ("Agents ayant travaillé", g.get("agents"), ""),
        ("Jours de collecte", g.get("jours"),
         (f'du {_jour((g.get("dates") or [""])[0])} au '
          f'{_jour((g.get("dates") or [""])[-1])}') if g.get("dates") else ""),
        ("Taille moyenne du ménage", _v(taille.get("moy")),
         f'écart-type {_v(taille.get("et"))} · médiane {_v(taille.get("med"))}'),
        ("Durée médiane d'entretien (min)", _v(duree.get("med")),
         f'moyenne {_v(duree.get("moy"))} min'),
        ("Ménages dénombrés sur le périmètre", cv.get("denombres"), ""),
        ("Taux de couverture VAD / dénombrement", _v(cv.get("taux")),
         "en % des ménages dénombrés"),
    ]
    for lib, val, pre in lignes:
        r = _ligne(ws, r, [lib, _v(val), pre])
    r = _source(ws, r + 1)

    r = _titre(ws, r, "Avancement par jour")
    r = _ecrire_entete(ws, r, ["Date", "Ménages du jour", "Cumul"], [18, 18, 18])
    for d in g.get("parJour") or []:
        r = _ligne(ws, r, [_jour(d["d"]), d["n"], d["cumul"]])
    r = _source(ws, r + 1)

    for cle, lib, col in (("statut", "Statut des interviews", "Statut"),
                          ("typemen", "Type de ménage", "Type")):
        bloc = g.get(cle) or {}
        r = _titre(ws, r, lib)
        r = _ecrire_entete(ws, r, [col, "Ménages", "Part (%)"], [42, 14, 14])
        for l in bloc.get("lignes") or []:
            r = _ligne(ws, r, [l["lib"], l["n"], _v(l["pct"])])
        r = _ligne(ws, r, ["Total", bloc.get("total"), 100.0], total=True)
        r = _source(ws, r + 1)

    cons = g.get("consentement") or {}
    r = _titre(ws, r, "Consentement")
    r = _ecrire_entete(ws, r, ["Consentement", "Oui", "Non"], [42, 14, 14])
    r = _ligne(ws, r, ["Module RSU", cons.get("rsu_oui"), cons.get("rsu_non")])
    r = _ligne(ws, r, ["Données individuelles", cons.get("indiv_oui"),
                       cons.get("indiv_non")])
    r = _source(ws, r + 1)

    r = _detail_communes(ws, r, agg.get("couvCommune") or {})
    for cle, lib, col in (("parFokontany", "Détail par fokontany", "Fokontany"),):
        rows = g.get(cle) or []
        if not rows:
            continue
        r = _sous_titre(ws, r, lib, 5)
        r = _ecrire_entete(ws, r, [col, "Code", "Ménages", "Membres",
                                   "Taille moyenne"], [34, 14, 14, 14, 16])
        for z in rows:
            r = _ligne(ws, r, [z["zone"], z.get("code"), z["menages"],
                               z["membres"], _v(z.get("taille"))])
        r = _ligne(ws, r, ["Total", "", sum(z["menages"] for z in rows),
                           sum(z["membres"] for z in rows), ""], total=True)
        r = _source(ws, r + 1)
    ws.freeze_panes = "A6"
    return ws


# ---------------------------------------------------------------------------
# Feuilles 2 et 3 — les deux listings d'erreurs
# ---------------------------------------------------------------------------
def _feuille_erreurs(wb, agg, portee, individu):
    """Un listing d'anomalies, dans la forme du tableau de bord (et du dofile
    d'origine) : **une colonne par contrôle**, la cellule portant le message de
    correction quand l'anomalie est présente, et restant vide sinon.

    C'est ce qui permet à une équipe de corriger : on voit d'un coup d'œil QUELS
    contrôles ont sauté sur QUELLE ligne, on filtre sur une colonne pour traiter
    une anomalie à la fois, et on trie par nombre d'anomalies. Une colonne unique
    qui concatène les libellés (ce que faisait cette feuille) ne permet ni l'un
    ni l'autre — elle reste, en plus des colonnes, pour lire une ligne d'un coup.

    Les codes de règle (`err_M7_M3_M4_M8_M5_vide`…) sont doublés de leur libellé
    dans l'intitulé de colonne : un classeur part à des gens qui n'ont pas le
    dictionnaire des variables sous les yeux. La feuille ne porte QUE le tableau
    — ni légende des règles, ni liste des contrôles non calculables (retirées à
    la demande, 2026-09-21) ; les deux restent lisibles sur le tableau de bord.
    """
    titre = "Erreur Individu" if individu else "Erreur ménage"
    ws = wb.create_sheet(titre)
    l = agg.get("listing") or {}
    regles = l.get("reglesIndividu" if individu else "reglesMenage") or []
    rows = l.get("individu" if individu else "menage") or []
    r = _entete(ws, portee,
                ("Une ligne par PERSONNE présentant au moins une anomalie de "
                 "saisie." if individu else
                 "Une ligne par MÉNAGE présentant au moins une anomalie de "
                 "saisie.")
                + " Une COLONNE PAR CONTRÔLE : la cellule porte le message de "
                  "correction quand l'anomalie est présente, et reste vide "
                  "sinon. Mêmes règles et mêmes lignes que le listing du "
                  "tableau de bord.")
    if not l.get("disponible"):
        ws.cell(row=r, column=1, value="Listing non calculable : tables VAD "
                                       "absentes ou incomplètes.")
        return ws
    r = _titre(ws, r, f"{titre} — {len(rows)} ligne(s), "
                      f"{len(regles)} contrôle(s)")

    # Colonnes d'identification : (clé dans la ligne, intitulé, largeur).
    # Mêmes champs que la barre du tableau de bord, plus le statut de
    # l'interview et, pour une personne, le motif d'absence saisi (c'est lui
    # qu'on relit pour trancher « err_membre »).
    ident = ([("key", "Clé interview", 16), ("nom_cm", "Chef de ménage", 30),
              ("membre", "Membre", 26), ("ligne", "N° ligne", 9),
              ("age", "Âge", 7), ("date", "Date", 12),
              ("region", "Région", 18), ("district", "District", 18),
              ("commune", "Commune", 22), ("fokontany", "Fokontany", 26),
              ("agent", "Agent (AE)", 20), ("ce", "Chef d'équipe", 20),
              ("statut", "Statut", 10), ("motif", "Motif d'absence saisi", 26)]
             if individu else
             [("key", "Clé interview", 16), ("nom_cm", "Chef de ménage", 30),
              ("date", "Date", 12), ("region", "Région", 18),
              ("district", "District", 18), ("commune", "Commune", 22),
              ("fokontany", "Fokontany", 26), ("agent", "Agent (AE)", 20),
              ("ce", "Chef d'équipe", 20), ("statut", "Statut", 10)])
    fige = 3 if individu else 2          # colonnes gardées à l'écran au défilement

    cols = ([t for _k, t, _w in ident] + ["Nb anomalies", "Anomalie(s)"]
            + [f'{x["lib"]}\n({x["code"]})' for x in regles])
    larg = ([w for _k, _t, w in ident] + [11, 34] + [26] * len(regles))
    r_ent = r
    r = _ecrire_entete(ws, r, cols, larg)
    n_ident = len(ident)

    for x in rows:
        err = set(x.get("erreurs") or [])
        base = [_jour(x.get("date")) if k == "date" else _v(x.get(k))
                for k, _t, _w in ident]
        # Ordre des libellés = celui des colonnes. Un code qui ne serait pas
        # dans la liste des règles actives est affiché tel quel plutôt
        # qu'escamoté : mieux vaut un code brut qu'une anomalie invisible.
        libs = ([g["lib"] for g in regles if g["code"] in err]
                + sorted(c for c in err if c not in {g["code"] for g in regles}))
        vals = (base + [len(err), " ; ".join(libs) or ND]
                + [(g["msg"] if g["code"] in err else None) for g in regles])
        ligne_courante = r
        r = _ligne(ws, r, vals)
        # Fond rouge sur les seules cellules qui portent une anomalie.
        for j, g in enumerate(regles, start=n_ident + 3):
            if g["code"] in err:
                c = ws.cell(row=ligne_courante, column=j)
                c.fill = _FILL["alerte"]
                c.alignment = Alignment(vertical="top", wrap_text=True)

    derniere = max(r - 1, r_ent)
    ws.freeze_panes = f"{get_column_letter(fige + 1)}{r_ent + 1}"
    ws.auto_filter.ref = f"A{r_ent}:{get_column_letter(len(cols))}{derniere}"

    r = _source(ws, r + 1,
                f'Source : listing d\'erreurs VAD — '
                f'{l.get("menagesExamines") or 0} ménage(s) et '
                f'{l.get("membresExamines") or 0} personne(s) examinés.')

    # Pas de légende des règles ni de liste des contrôles non calculables en
    # bas de feuille (retirées à la demande, 2026-09-21) : la feuille ne porte
    # QUE le tableau. L'intitulé de chaque colonne garde le code de la règle,
    # et les deux listes restent lisibles sur le tableau de bord.
    return ws


# ---------------------------------------------------------------------------
# Feuille 4 — Test de qualité de données GLOBALE
# ---------------------------------------------------------------------------
def _feuille_qualite_base(wb, qb, portee):
    ws = wb.create_sheet("Test qualité données globale")
    r = _entete(ws, portee,
                "Test de qualité de données GLOBALE — les données du RSU "
                "confrontées au RGPH-3 2018 et aux normes démographiques "
                "internationales. Cette feuille juge les DONNÉES, pas les "
                "enquêteurs.")
    if not qb.get("disponible"):
        ws.cell(row=r, column=1,
                value="Non calculable : " + str(qb.get("erreur") or "tables absentes"))
        return ws
    # Pas de bloc « Synthèse » (retiré à la demande, 2026-09-21) : la feuille
    # ouvre directement sur le détail des indicateurs.
    r = _titre(ws, r, "Test de qualité de données globale — détail")
    cols = ["Famille", "N°", "Indicateur", "Valeur", "Unité", "Référence",
            "Verdict", "Conclusion", "Seuil(s)"]
    r = _ecrire_entete(ws, r, cols, [30, 7, 40, 12, 24, 40, 15, 58, 58])
    for f in qb["familles"]:
        for i in f["indicateurs"]:
            r = _ligne(ws, r,
                       [f'{f["code"]}. {f["titre"]}', i["num"], i["titre"],
                        _v(i["valeur"]), i["unite"] or "", i["reference"] or "",
                        _VERDICT.get(i["gravite"], i["gravite"]),
                        i["conclusion"] or "", " ; ".join(i["seuils"])],
                       fill=_FILL.get(i["gravite"]))
    r = _source(ws, r + 1)

    cov = [c for c in qb.get("couverture", []) if c["attendu"]]
    if cov:
        r = _sous_titre(ws, r, "Couverture, commune par commune (référence : "
                        "ménages dénombrés)", 4)
        r = _ecrire_entete(ws, r, ["Commune", "Ménages enquêtés",
                                   "Ménages attendus (dénombrés)",
                                   "Couverture (%)"],
                           [34, 18, 18, 18])
        for c in sorted(cov, key=lambda c: c["taux"]):
            r = _ligne(ws, r, [c["nom"], c["rsu"], c["attendu"], _v(c["taux"])])
        tr, ta = sum(c["rsu"] for c in cov), sum(c["attendu"] for c in cov)
        r = _ligne(ws, r, ["Total", tr, ta,
                           _v(round(100.0 * tr / ta, 1) if ta else None)],
                   total=True)
        r = _source(ws, r + 1)
    ws.freeze_panes = "A6"
    return ws


# ---------------------------------------------------------------------------
# Feuille 5 — Test de qualité de données PAR AGENT
# ---------------------------------------------------------------------------
def _feuille_qualite_agents(wb, q, portee):
    """La matrice agent × test, une ligne par enquêteur.

    La feuille porte DEUX rangs d'en-tête : le numéro du test, puis son
    intitulé. Sans le second, une colonne « 6.4.2 » ne dit rien à qui ouvre le
    classeur sans avoir le tableau de bord sous les yeux."""
    ws = wb.create_sheet("Test qualité données par Agent")
    r = _entete(ws, portee,
                "Test de qualité de données PAR AGENT. Chaque case porte sur "
                "l'agent de la ligne et sur personne d'autre ; « nd » signifie "
                "que son effectif n'atteint pas le minimum du test. La colonne "
                "« Comparé à » dit à quelle zone il a été confronté.")
    if not q.get("disponible"):
        ws.cell(row=r, column=1, value="Non calculable : tables VAD absentes.")
        return ws
    m = q.get("matrice") or {}
    cols, lignes = m.get("colonnes", []), m.get("lignes", [])
    # Pas de bloc « Synthèse » (retiré à la demande, 2026-09-21) : la feuille
    # ouvre directement sur la matrice.
    r = _titre(ws, r, "Matrice agent × test")
    fixes = ["Commune", "Chef d'équipe", "Agent", "Ménages", "Membres",
             "Comparé à"]
    tete = r
    # Rang 1 : numéro de test. Rang 2 : intitulé, en plus petit.
    for j, lib in enumerate(fixes, start=1):
        c = ws.cell(row=tete, column=j, value=lib)
        c.font, c.fill, c.border = _ENTETE_F, _ENTETE_FILL, _BORDURE
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.merge_cells(start_row=tete, start_column=j,
                       end_row=tete + 1, end_column=j)
    for k, col in enumerate(cols):
        j = len(fixes) + 1 + k
        c = ws.cell(row=tete, column=j, value=col["num"])
        c.font, c.fill, c.border = _ENTETE_F, _ENTETE_FILL, _BORDURE
        c.alignment = Alignment(horizontal="center", vertical="center")
        c2 = ws.cell(row=tete + 1, column=j, value=col["titre"])
        c2.font = Font(bold=True, size=8, color="FF374151")
        c2.fill, c2.border = _ENTETE_FILL, _BORDURE
        c2.alignment = Alignment(horizontal="center", vertical="center",
                                 wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = 13
    for j, w in enumerate((24, 20, 22, 10, 10, 30), start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[tete].height = 16
    ws.row_dimensions[tete + 1].height = 58
    r = tete + 2
    for lg in lignes:
        ref = ("commune (agent seul dans son fokontany) : " if lg.get("referenceRemonte")
               else "fokontany : ") + str(lg.get("reference") or ND)
        base = [lg["commune"], lg["ce"], lg["ae"], lg["menages"], lg["membres"], ref]
        for j, v in enumerate(base, start=1):
            c = ws.cell(row=r, column=j, value=v)
            c.border = _BORDURE
            if isinstance(v, (int, float)):
                c.alignment = _DROITE
        for k, cell in enumerate(lg["cellules"]):
            c = ws.cell(row=r, column=len(fixes) + 1 + k,
                        value=(ND if cell["g"] == "nd" else _v(cell["v"])))
            c.border = _BORDURE
            c.fill = _FILL.get(cell["g"], _FILL["nd"])
            c.alignment = _DROITE
        r += 1
    r = _source(ws, r + 1)

    r = _titre(ws, r, "Légende des tests")
    r = _ecrire_entete(ws, r, ["N°", "Niveau", "Test", "Unité",
                               "Effectif minimal", "Seuil d'alerte"],
                       [8, 34, 42, 22, 16, 60])
    for col in cols:
        r = _ligne(ws, r, [col["num"], f'{col["niveau"]}. {col["niveauTitre"]}',
                           col["titre"], col["unite"] or "", col["nMin"],
                           " ; ".join(col["seuils"])])
    r = _source(ws, r + 1)
    ws.freeze_panes = f"D{tete + 2}"
    return ws


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
# Feuille 6 — Écart entre la DÉCLARATION des agents et ce qui arrive au serveur
# ---------------------------------------------------------------------------
def _feuille_ecart(wb, agg, portee):
    """Une ligne par AGENT × DATE, pour TOUS les agents du périmètre, qu'ils
    aient déclaré ou non : nom et login de l'agent, chef d'équipe, date,
    ménages déclarés, arrivés au serveur, écart (déclaré − arrivé), puis la
    ventilation par statut des interviews arrivées. Un sous-total par agent,
    un total général. Calcul : `vad_core._sec_ecart_dates`."""
    ws = wb.create_sheet("Écart par agent")
    e = agg.get("ecartDates") or {}
    lignes, statuts = e.get("lignes") or [], e.get("statuts") or ()
    r = _entete(ws, portee,
                "Écart = DÉCLARÉ par l'agent − ARRIVÉ au serveur, jour par jour. "
                "Écart > 0 : il est arrivé MOINS que déclaré (synchronisation "
                "en retard, ou sur-déclaration). Écart < 0 : il est arrivé PLUS "
                "que déclaré. « — » : aucune déclaration saisie ce jour-là (ce "
                "n'est pas un zéro). Tous les agents figurent, même sans "
                "déclaration. Les statuts ventilent les interviews arrivées.")
    r = _titre(ws, r, "Tableau — Déclaré et arrivé au serveur, par agent et "
                      "par date")
    cles = [k for _c, k, _l in statuts]
    r = _ecrire_entete(
        ws, r,
        ["Agent (AE)", "Login", "Chef d'équipe", "Date", "Ménages déclarés",
         "Arrivés au serveur", "Écart (déclaré − arrivé)"]
        + [lib for _c, _k, lib in statuts],
        [28, 22, 26, 12, 14, 14, 16] + [13] * len(statuts))
    ws.freeze_panes = f"B{r}"
    if not lignes:
        ws.cell(row=r, column=1, value="Aucune interview ni aucune déclaration "
                                       "sur ce périmètre.")
        return ws

    def somme(ls, k):
        return sum(l[k] for l in ls)

    def dec_total(ls):
        d = [l["declare"] for l in ls if l["declare"] is not None]
        return sum(d) if d else None

    par_agent = {}
    for l in lignes:
        par_agent.setdefault(l["code"], []).append(l)
    for code, ls in par_agent.items():
        for l in ls:
            r = _ligne(ws, r, [l["agent"], l["code"], l["chef"] or ND,
                               _jour(l["date"]), _v(l["declare"]), l["recu"],
                               _v(l["ecart"])] + [l[k] for k in cles])
        dec = dec_total(ls)
        # Écart du sous-total : sur les SEULS jours déclarés, pour ne pas
        # compter comme manquant ce qui est arrivé un jour non déclaré.
        ec = (sum(l["ecart"] for l in ls if l["ecart"] is not None)
              if dec is not None else None)
        r = _ligne(ws, r, [f"Sous-total {ls[0]['agent']}", code, "",
                           f"{len(ls)} jour(s)", _v(dec), somme(ls, "recu"),
                           _v(ec)] + [somme(ls, k) for k in cles], total=True)
    dec = dec_total(lignes)
    ec = (sum(l["ecart"] for l in lignes if l["ecart"] is not None)
          if dec is not None else None)
    r = _ligne(ws, r, [f"TOTAL — {len(par_agent)} agent(s)", "", "", "",
                       _v(dec), somme(lignes, "recu"), _v(ec)]
               + [somme(lignes, k) for k in cles], total=True)
    sd = e.get("sansDate") or {}
    if sd:
        r = _ligne(ws, r, [f"{sum(sd.values())} interview(s) sans date valide, "
                           "non comparables à une déclaration, ne figurent pas "
                           "dans ce tableau."] + [""] * (6 + len(cles)))
    _source(ws, r + 1, "Sources : déclarations des agents (Superviseur "
                       "Technique) et Visite à domicile, RSU 2026")
    return ws


def _feuille_couverture(wb, agg, portee):
    """Couverture par agent (affectation du préchargement ↔ VAD), puis les
    ménages restant à interviewer agent par agent, puis les doubles
    interviews. Mêmes nombres que la page « Par agent » (`vad_core`,
    section « couverture »)."""
    cv = agg.get("couverture") or {}
    ws = wb.create_sheet("Couverture par agent")
    r = _entete(ws, portee,
                "Couverture = ménages AFFECTÉS à l'agent (base de "
                "préchargement) qu'il a LUI-MÊME interviewés ÷ ménages "
                "affectés. Rapprochement ménage par ménage sur la clé "
                "interview_keyden. Un ménage interviewé plusieurs fois compte "
                "une fois (statut le plus avancé retenu). Affecté à A mais "
                "interviewé par B : « par un autre agent » chez A, « non "
                "affecté » chez B.")
    r = _titre(ws, r, "Tableau — Couverture par agent (le moins couvert d'abord)")
    if not cv.get("dispo"):
        ws.cell(row=r, column=1,
                value=("Aucune base de préchargement n'est enregistrée pour "
                       "ce périmètre : la couverture par agent ne peut pas "
                       "être calculée."))
        r += 2
    else:
        statuts = cv["statuts"]
        r = _ecrire_entete(
            ws, r,
            ["Agent", "Login", "Chef d'équipe", "Ménages affectés",
             "Affectés interviewés", "Couverture (%)"]
            + [lib for _c, _k, lib in statuts]
            + ["Interviewés par un autre agent", "Reste à interviewer",
               "Non affectés interviewés", "dont affectés à un autre agent",
               "dont hors préchargement", "Interviews sans clé"],
            [28, 22, 24, 12, 12, 12] + [12] * len(statuts)
            + [14, 12, 14, 14, 14, 12])
        # En-tête et nom de l'agent figés au défilement.
        ws.freeze_panes = f"B{r}"
        for p in cv["agents"]:
            r = _ligne(ws, r, [p["agent"], p["code"], p["ceNom"] or ND,
                               p["affectes"], p["affInterviewes"],
                               _v(p["couverture"])]
                       + [p[k] for _c, k, _l in statuts]
                       + [p["parAutre"], p["reste"], p["nonAffectes"],
                          p["nonAffAutre"], p["nonAffHors"], p["sansCle"]])
        t = cv["total"]
        r = _ligne(ws, r, [f"TOTAL — {t['agents']} agent(s)", "", "",
                           t["affectes"], t["affInterviewes"],
                           _v(t["couverture"])]
                   + [t[k] for _c, k, _l in statuts]
                   + [t["parAutre"], t["reste"], t["nonAffectes"],
                      t["nonAffAutre"], t["nonAffHors"], t["sansCle"]],
                   total=True)
        r = _source(ws, r, "Sources : base de préchargement (registre) et "
                           "Visite à domicile, RSU 2026")

    ws2 = wb.create_sheet("Reste à interviewer")
    r2 = _entete(ws2, portee,
                 "Ménages affectés à chaque agent par le préchargement et "
                 "qu'AUCUN agent n'a encore interviewés. Un ménage interviewé "
                 "par un autre agent n'y figure pas.")
    r2 = _titre(ws2, r2, "Tableau — Ménages restant à interviewer, par agent")
    r2 = _ecrire_entete(
        ws2, r2,
        ["Agent", "Login", "Chef d'équipe", "Fokontany", "Code dénombrement",
         "Chef de ménage", "Taille", "Adresse", "Description",
         "Clé ménage (keyden)"],
        [26, 22, 22, 30, 22, 30, 8, 24, 30, 20])
    ws2.freeze_panes = f"B{r2}"
    for p in cv.get("agents") or []:
        for m in p["resteListe"]:
            r2 = _ligne(ws2, r2, [p["agent"], p["code"], p["ceNom"] or ND,
                                  m["fokontany_nom"] or _v(m["fokontany"]),
                                  m["code_den"] or ND, m["nom_cm"] or ND,
                                  _v(m["taille"]), m["adresse"] or ND,
                                  m["description"] or ND, m["keyden"]])
    _source(ws2, r2, "Source : base de préchargement (registre), RSU 2026")

    ws3 = wb.create_sheet("Doubles interviews")
    r3 = _entete(ws3, portee,
                 "Ménages (clé interview_keyden) interviewés plus d'une fois. "
                 "Au-delà de 3 interviews d'une même clé, c'est le "
                 "préchargement qui est en cause, pas une double visite.")
    r3 = _titre(ws3, r3, "Tableau — Ménages interviewés plusieurs fois")
    r3 = _ecrire_entete(
        ws3, r3,
        ["Clé ménage (keyden)", "Nb interviews", "Diagnostic",
         "Agent affecté", "Clé d'interview", "Agent", "Date", "Statut"],
        [20, 12, 22, 24, 18, 24, 12, 12])
    ws3.freeze_panes = f"B{r3}"
    for d in cv.get("doubles") or []:
        for i, cle in enumerate(d["cles"]):
            r3 = _ligne(ws3, r3, [d["keyden"], d["n"], d["verdict"],
                                  d["affecte"] or ND, cle, d["agents"][i],
                                  _jour(d["dates"][i]), _v(d["statuts"][i])])
    _source(ws3, r3)
    return ws


# ---------------------------------------------------------------------------
def nom_fichier(districts=None, quand=None):
    """« Rapport_VAD_<district>_<AAAAMMJJ>_<HHhMM>.xlsx », ex.
    Rapport_VAD_6305_20260926_1745.xlsx. <district> = le CODE du district ;
    plusieurs districts -> codes joints par « - » ; tout le pays -> « TOUS »."""
    d = quand or datetime.datetime.now()
    codes = sorted(int(c) for c in districts) if districts else []
    dis = "-".join(str(c) for c in codes) if codes else "TOUS"
    return f"Rapport_VAD_{dis}_{d.strftime('%Y%m%d_%H%M')}.xlsx"


def generer_classeur(conn, districts=None, communes=None, portee_lib="RSU 2026"):
    """Classeur VAD complet (openpyxl Workbook) pour le périmètre demandé.

    Les trois sources sont appelées SÉPARÉMENT et non via `vad_core.agrege`
    d'un seul coup : celui-ci ne calcule les tests de qualité que pour la
    section affichée, alors que le classeur les veut tous."""
    agg = vad_core.agrege(conn, districts, communes,
                          portee_lib=portee_lib, section="export")
    qb = vad_qualite_base.calculer(conn, districts, communes)
    q = vad_qualite.calculer(conn, districts, communes)
    wb = Workbook()
    _feuille_global(wb, agg, portee_lib)
    _feuille_erreurs(wb, agg, portee_lib, individu=False)
    _feuille_erreurs(wb, agg, portee_lib, individu=True)
    _feuille_qualite_base(wb, qb, portee_lib)
    _feuille_qualite_agents(wb, q, portee_lib)
    _feuille_ecart(wb, agg, portee_lib)
    _feuille_couverture(wb, agg, portee_lib)
    return wb


def generer_bytes(conn, districts=None, communes=None, portee_lib="RSU 2026"):
    """Classeur sérialisé (bytes), prêt à télécharger."""
    wb = generer_classeur(conn, districts, communes, portee_lib)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
