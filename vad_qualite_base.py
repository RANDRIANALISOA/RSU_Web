# -*- coding: utf-8 -*-
"""
vad_qualite_base.py — Tests de qualité de la BASE, et non de l'agent.

`vad_qualite.py` répond à « quel enquêteur pose problème ? ». Ce module répond
à la question d'avant : « ces données tiennent-elles debout ? ». Ce n'est pas
la même question et ce ne sont pas les mêmes tests — un défaut qui touche TOUS les
agents de la même façon (une variable vide, un filtre de questionnaire cassé,
un déficit d'hommes adultes) est invisible dans une comparaison entre agents,
puisqu'il n'y crée aucun écart. Il faut une référence extérieure.

Cette référence est double :
  * le RGPH-3 2018, chargé dans `rgph_age_commune`, `rgph_men_commune` et
    `rgph_commune` (agrégats par commune, codes RSU) ;
  * les normes démographiques internationales (Whipple, Myers, indice ONU),
    qui ne demandent aucune source externe mais un effectif — inatteignable
    chez un agent, disponible ici.

⚠️ Le RGPH-3 date de 2018 et le RSU de 2025 : les écarts de STRUCTURE sont
interprétables, les écarts de NIVEAU ne le sont pas. Et le RSU n'est pas
exhaustif (la couverture n'est que partielle en cours de collecte) : on compare
des proportions, jamais des totaux.

Vingt-cinq indicateurs, six familles. Ajouter un indicateur = une fonction qui
renvoie un `_ind(...)`, une ligne dans sa famille.
"""
from collections import Counter, defaultdict
import re

import vad_qualite as VQ
from vad_qualite import num, txt, jour, fmt

# --------------------------------------------------------------------------
# Seuils
# --------------------------------------------------------------------------
# Trois origines, distinguées dans le libellé de chaque indicateur :
#   — normes internationales (Whipple, Myers, ONU, Duncan) : reprises telles quelles ;
#   — écarts au RGPH-3 : fixés ici, faute de norme publiée sur ce que doit être
#     l'écart acceptable entre un registre social et un recensement de 2018 ;
#   — contrôles internes (unicité, complétude) : fixés ici également.
# Les deux dernières catégories sont des choix d'exploitation, à faire arbitrer
# par les statisticiens du RSU. Les modifier ne change que les couleurs.
SEUILS = {
    "A1": (2.0, 3.0),      # rapport couverture max / min entre communes
    "A2": (5.0, 10.0),     # indice de dissimilarité de Duncan, en %
    "A3": (3.0, 5.0),      # écart du rapport de masculinité au RGPH
    "A4": (0.30, 0.50),    # écart de la taille moyenne du ménage au RGPH
    "A5": (3.0, 5.0),      # écart de la part de chefs de ménage femmes, en points
    "A6": (3.0, 5.0),      # écart max par grand groupe d'âge, en points
    "B1": (110.0, 125.0),  # Whipple — échelle ONU
    "B2": (10.0, 20.0),    # Myers — échelle du document RSU
    "B3": (3.0, 5.0),      # écart max d'un chiffre terminal à 10 %, en points
    "B4": (20.0, 40.0),    # indice combiné âge-sexe — seuils du document RSU
    "C1": (5.0, 10.0),     # taux médian de non-réponse sur les variables clés
    "C2": (1, 1),          # nb de variables présentes mais intégralement vides
    "C3": (5.0, 10.0),     # % de ménages sans GPS
    "C4": (0.5, 2.0),      # % de ménages sans aucun membre
    "D1": (1, 1),          # nb de clés d'interview en double
    "D2": (1.0, 3.0),      # % de CIN portés par plusieurs personnes
    "D3": (0.5, 2.0),      # % de CIN à valeur de remplissage
    "D4": (0.5, 2.0),      # % de ménages à signature (chef + fokontany) dupliquée
    "E1": (1.0, 3.0),      # % de ménages sans chef déclaré
    "E2": (3.0, 8.0),      # % de ménages dont le roster s'écarte de taille_men de 3+
    "E3": (0.5, 2.0),      # % de ménages sans commune identifiée
    "F1": (1.0, 5.0),      # % d'interviews rejetées encore dans les données
    "F2": (2.0, 3.0),      # rapport jour le plus chargé / jour médian
    "F3": (5.0, 10.0),     # % d'entretiens de moins de 10 minutes
    "F4": (0.5, 2.0),      # % de ménages portant une erreur de validation SS
}
# Statuts Survey Solutions écartés du calcul des indicateurs. Un questionnaire
# rejeté par le siège n'est pas de la donnée : le compter reviendrait à juger la
# base sur ce qu'on a déjà décidé de ne pas garder. On ne l'ignore pas pour
# autant — l'indicateur F1 en rend compte, séparément.
STATUTS_REJETES = {65, 125}
DUREE_COURTE = 10.0        # minutes : en dessous, l'entretien est signalé


def _ind(num_, titre, principe, formule, valeur, unite="", reference="",
         calcul=(), conclusion="", seuils=(), gravite="ok", stat="",
         sens="haut"):
    """Un indicateur, dans la même grammaire que `vad_qualite.resultat()`.

    `sens` dit de quel côté se trouve le défaut : "haut" (plus c'est grand,
    pire c'est), "bas", ou "" quand la gravité est calculée à la main."""
    return {"num": num_, "titre": titre, "principe": principe,
            "formule": list(formule) if isinstance(formule, (list, tuple))
                       else [formule],
            "valeur": valeur, "unite": unite, "reference": reference,
            "calcul": list(calcul), "conclusion": conclusion,
            "seuils": list(seuils), "gravite": gravite, "stat": stat}


def _grav(code, valeur, sens="haut"):
    """Gravité d'une valeur au regard de SEUILS[code]."""
    if valeur is None:
        return "nd"
    vg, al = SEUILS[code]
    if sens == "haut":
        return "alerte" if valeur >= al else "vigilance" if valeur >= vg else "ok"
    return "alerte" if valeur <= al else "vigilance" if valeur <= vg else "ok"


def _pct(a, b):
    return (100.0 * a / b) if b else None


# --------------------------------------------------------------------------
# La référence extérieure : RGPH-3 2018, agrégé sur le MÊME périmètre
# --------------------------------------------------------------------------
def _rgph(conn, codes_commune):
    """Agrégats RGPH-3 des communes réellement couvertes par le RSU.

    Comparer le RSU à « Madagascar » n'aurait aucun sens : on restreint le
    recensement aux communes où le RSU a travaillé, en passant par les codes
    RSU (`cc_rsu`) et jamais par les noms."""
    if not codes_commune:
        return None
    cc = [int(c) for c in codes_commune if c is not None]
    if not cc:
        return None
    q = ",".join("?" * len(cc))
    cur = conn.cursor()
    out = {"pyr": Counter(), "menages": 0, "chefs": 0, "chefs_femmes": 0,
           "communes": set(), "attendus": {}}
    try:
        for a, s, n in cur.execute(
                f'SELECT "age","sexe","n" FROM "rgph_age_commune" '
                f'WHERE "cc_rsu" IN ({q})', cc):
            if a is None or s not in (1, 2):
                continue
            out["pyr"][(min(int(a) // 5, 16), int(s))] += int(n or 0)
    except Exception:
        return None
    try:
        for c_, men, chefs, cf in cur.execute(
                f'SELECT "cc_rsu","menages","chefs","chefs_femmes" '
                f'FROM "rgph_men_commune" WHERE "cc_rsu" IN ({q})', cc):
            out["communes"].add(c_)
            out["menages"] += int(men or 0)
            out["chefs"] += int(chefs or 0)
            out["chefs_femmes"] += int(cf or 0)
    except Exception:
        pass
    try:
        for c_, nb in cur.execute(
                f'SELECT "code_commune","nombreMenage" FROM "commune" '
                f'WHERE "code_commune" IN ({q})', cc):
            if nb:
                out["attendus"][int(c_)] = int(nb)
    except Exception:
        pass
    return out if sum(out["pyr"].values()) else None


def _pyramide(menages):
    """Pyramide du RSU : {(tranche quinquennale, sexe 1/2): effectif}."""
    p = Counter()
    for m in menages:
        for x in m.get("membres", ()):
            a, sx = num(x.get("M4")), num(x.get("M3"))
            if a is None or sx not in (VQ.SEXE_H, VQ.SEXE_F):
                continue
            p[(min(int(a) // 5, 16), 1 if sx == VQ.SEXE_H else 2)] += 1
    return p


def _parts(cnt):
    t = sum(cnt.values()) or 1
    return {k: v / float(t) for k, v in cnt.items()}


def _duncan(a, b):
    """Indice de dissimilarité : la part d'effectif à déplacer pour superposer
    les deux répartitions. 0 = identiques, 100 = disjointes."""
    pa, pb = _parts(a), _parts(b)
    if not pa or not pb:
        return None
    return 100.0 * 0.5 * sum(abs(pa.get(k, 0) - pb.get(k, 0))
                             for k in set(pa) | set(pb))


def _sr(cnt, lo, hi):
    """Rapport de masculinité d'une tranche d'âge, sur une pyramide."""
    h = sum(v for (t, s), v in cnt.items() if s == 1 and lo <= t * 5 < hi)
    f = sum(v for (t, s), v in cnt.items() if s == 2 and lo <= t * 5 < hi)
    return (100.0 * h / f) if f else None


def _part_age(cnt, lo, hi):
    t = sum(cnt.values())
    return _pct(sum(v for (tr, _s), v in cnt.items() if lo <= tr * 5 < hi), t)


# --------------------------------------------------------------------------
# FAMILLE A — Couverture (référence : DÉNOMBREMENT) et représentativité
# (référence : RGPH-3)
# --------------------------------------------------------------------------
def famille_a(ms, rg, couverture):
    out = []
    # --- A1 dispersion de la couverture entre communes --------------------
    # Le rapport max/min porte sur les communes DÉJÀ visitées (une commune à
    # 0 % rendrait le rapport infini) ; les communes dénombrées et pas encore
    # visitées sont comptées à part dans le calcul.
    taux = [c["taux"] for c in couverture if c["taux"] and c["rsu"]]
    non_visitees = sum(1 for c in couverture if c["attendu"] and not c["rsu"])
    rap = (max(taux) / min(taux)) if taux and min(taux) > 0 else None
    tot_r = sum(c["rsu"] for c in couverture)
    tot_a = sum(c["attendu"] or 0 for c in couverture)
    out.append(_ind(
        "A1", "Dispersion de la couverture entre communes",
        "En cours de collecte, le NIVEAU de couverture ne dit rien — elle est "
        "partielle par construction. Sa DISPERSION, si : des communes qui "
        "avancent cinq fois moins vite que d'autres signalent un problème "
        "d'affectation, d'accès ou de disponibilité des listes.",
        ["Couverture(commune) = ménages enquêtés / ménages dénombrés",
         "Rapport = max(couverture) / min(couverture)"],
        rap, "× entre la commune la mieux et la moins couverte",
        reference=f"{fmt(_pct(tot_r, tot_a), 1)} % de couverture d'ensemble "
                  f"({fmt(tot_r)} / {fmt(tot_a)} ménages dénombrés)"
                  if tot_a else "ménages dénombrés indisponibles",
        calcul=[f"{len(taux)} commune(s) visitée(s) et dénombrée(s) ; "
                f"{non_visitees} commune(s) dénombrée(s) sans aucune "
                "interview (hors du rapport max/min)."]
               + [f"{c['nom']} : {fmt(c['rsu'])} / {fmt(c['attendu'])} = "
                  f"{fmt(c['taux'], 1)} %"
                  for c in sorted((c for c in couverture if c["rsu"] and c["taux"]),
                                  key=lambda c: c["taux"])[:3]]
               + ["…"]
               + [f"{c['nom']} : {fmt(c['rsu'])} / {fmt(c['attendu'])} = "
                  f"{fmt(c['taux'], 1)} %"
                  for c in sorted(couverture, key=lambda c: -(c["taux"] or 0))[:3]],
        conclusion=("→ Alerte : l'avancement est très inégal d'une commune à "
                    "l'autre — à rapprocher du calendrier d'affectation."
                    if _grav("A1", rap) == "alerte" else
                    "→ Vigilance : écart d'avancement notable entre communes."
                    if _grav("A1", rap) == "vigilance" else
                    "→ Avancement homogène entre communes."),
        seuils=[f"Rapport ≥ {SEUILS['A1'][1]:.0f} : alerte ; "
                f"≥ {SEUILS['A1'][0]:.0f} : vigilance",
                "Seuils d'exploitation, sans norme publiée"],
        gravite=_grav("A1", rap),
        stat=(f"{fmt(min(taux), 0)} % – {fmt(max(taux), 0)} %" if taux else "")))

    if not rg:
        for n_, t in (("A2", "Écart de structure à la pyramide RGPH-3"),
                      ("A3", "Rapport de masculinité 15-64 ans"),
                      ("A4", "Taille moyenne des ménages"),
                      ("A5", "Part des chefs de ménage femmes"),
                      ("A6", "Structure par grand groupe d'âge")):
            out.append(_ind(n_, t, "Comparaison au RGPH-3 2018.", [], None,
                            conclusion="→ Non calculé : les agrégats RGPH-3 ne "
                                       "sont pas chargés pour ce périmètre "
                                       "(tables rgph_age_commune / "
                                       "rgph_men_commune).",
                            gravite="nd"))
        return out

    ps, pr = _pyramide(ms), rg["pyr"]
    # --- A2 indice de dissimilarité de Duncan -----------------------------
    d = _duncan(ps, pr)
    out.append(_ind(
        "A2", "Écart de structure à la pyramide RGPH-3",
        "Superpose la pyramide du RSU à celle du recensement sur les "
        "MÊMES communes, par groupe quinquennal et par sexe. L'indice donne "
        "la part de l'effectif qu'il faudrait déplacer pour que les deux "
        "coïncident : c'est le résumé le plus compact de la représentativité.",
        ["ID = ½ × Σ |p_RSU(g) − p_RGPH(g)| × 100",
         "g = 17 groupes d'âge × 2 sexes"],
        d, "%",
        reference=f"RGPH-3 2018, {fmt(sum(pr.values()))} individus sur "
                  f"{len(rg['communes'])} commune(s)",
        calcul=[f"RSU : {fmt(sum(ps.values()))} individus datés et sexés.",
                f"RGPH-3 : {fmt(sum(pr.values()))} individus sur le même périmètre.",
                f"Indice de dissimilarité = {fmt(d, 1)} %."],
        conclusion=("→ Alerte : la structure par âge et sexe du RSU "
                    "s'éloigne nettement du recensement — vérifier le champ "
                    "couvert avant d'exploiter la base."
                    if _grav("A2", d) == "alerte" else
                    "→ Vigilance : écart de structure à surveiller."
                    if _grav("A2", d) == "vigilance" else
                    "→ Structure par âge et sexe conforme au recensement."),
        seuils=["< 5 % : bon accord · 5-10 % : à surveiller · > 10 % : à investiguer",
                "Sept ans séparent les deux sources : un écart résiduel est normal"],
        gravite=_grav("A2", d)))

    # --- A3 rapport de masculinité ----------------------------------------
    s_e, s_r = _sr(ps, 15, 65), _sr(pr, 15, 65)
    e_e, e_r = _sr(ps, 0, 15), _sr(pr, 0, 15)
    ec = abs(s_e - s_r) if (s_e is not None and s_r is not None) else None
    out.append(_ind(
        "A3", "Rapport de masculinité 15-64 ans",
        "Le déficit d'hommes en âge actif est la sous-déclaration la plus "
        "courante d'un registre de ménages : l'homme absent au moment du "
        "passage n'est pas inscrit. On le teste en confrontant les âges "
        "actifs au recensement, et en contrôlant sur les 0-14 ans — un écart "
        "qui n'apparaît QUE chez les adultes désigne la collecte, pas la "
        "démographie.",
        ["SR = (hommes / femmes) × 100, par grand groupe d'âge"],
        s_e, "hommes / 100 femmes",
        reference=f"RGPH-3 : {fmt(s_r, 1)}",
        calcul=[f"15-64 ans — RSU {fmt(s_e, 1)} contre {fmt(s_r, 1)} au "
                f"RGPH-3 (écart {fmt(ec, 1)}).",
                f"0-14 ans (contrôle) — RSU {fmt(e_e, 1)} contre "
                f"{fmt(e_r, 1)} au RGPH-3.",
                "Si l'écart n'existe que sur les 15-64 ans, il vient de la "
                "collecte ; s'il existe aussi sur les enfants, il vient du "
                "champ couvert."],
        conclusion=("→ Alerte : déficit marqué sur un sexe en âge actif — "
                    "à confronter à la migration de travail locale avant "
                    "toute conclusion." if _grav("A3", ec) == "alerte" else
                    "→ Vigilance : écart notable au recensement sur les âges "
                    "actifs." if _grav("A3", ec) == "vigilance" else
                    "→ Rapport de masculinité conforme au recensement."),
        seuils=[f"Écart ≥ {SEUILS['A3'][1]:.0f} points : alerte ; "
                f"≥ {SEUILS['A3'][0]:.0f} : vigilance",
                "Seuils d'exploitation, sans norme publiée"],
        gravite=_grav("A3", ec), stat=f"écart {fmt(ec, 1)}"))

    # --- A4 taille moyenne du ménage --------------------------------------
    nm = len([m for m in ms if m.get("membres")])
    t_e = (sum(len(m.get("membres", ())) for m in ms) / float(nm)) if nm else None
    t_r = (rg["menages"] and sum(pr.values()) / float(rg["menages"])) or None
    ec4 = abs(t_e - t_r) if (t_e is not None and t_r) else None
    out.append(_ind(
        "A4", "Taille moyenne des ménages",
        "Un roster systématiquement tronqué — membres oubliés, absents non "
        "inscrits — se voit d'abord ici. C'est l'indicateur le plus robuste "
        "de la comparaison au recensement, parce qu'il ne dépend ni de l'âge "
        "ni du sexe déclarés.",
        ["Taille = membres inscrits / ménages ayant au moins un membre"],
        t_e, "personnes par ménage",
        reference=f"RGPH-3 : {fmt(t_r, 2)}",
        calcul=[f"RSU : {fmt(sum(len(m.get('membres', ())) for m in ms))} "
                f"membres pour {fmt(nm)} ménages → {fmt(t_e, 2)}.",
                f"RGPH-3 sur le même périmètre : {fmt(t_r, 2)}.",
                f"Écart : {fmt(ec4, 2)} personne(s)."],
        conclusion=("→ Alerte : les ménages du RSU sont nettement plus "
                    "petits ou plus grands qu'au recensement — suspicion de "
                    "roster incomplet." if _grav("A4", ec4) == "alerte" else
                    "→ Vigilance : écart de taille moyenne à surveiller."
                    if _grav("A4", ec4) == "vigilance" else
                    "→ Taille moyenne conforme au recensement."),
        seuils=[f"Écart ≥ {SEUILS['A4'][1]:.2f} personne : alerte ; "
                f"≥ {SEUILS['A4'][0]:.2f} : vigilance"],
        gravite=_grav("A4", ec4), stat=f"écart {fmt(ec4, 2)}"))

    # --- A5 chefs de ménage femmes ----------------------------------------
    cf = sum(1 for m in ms for x in m.get("membres", ())
             if num(x.get("M7")) == VQ.M7_CHEF and num(x.get("M3")) == VQ.SEXE_F)
    ct = sum(1 for m in ms for x in m.get("membres", ())
             if num(x.get("M7")) == VQ.M7_CHEF)
    p_e = _pct(cf, ct)
    p_r = _pct(rg["chefs_femmes"], rg["chefs"])
    ec5 = abs(p_e - p_r) if (p_e is not None and p_r is not None) else None
    out.append(_ind(
        "A5", "Part des chefs de ménage femmes",
        "Variable de contrôle classique : elle bouge lentement dans le temps, "
        "elle est bien mesurée au recensement, et un écart important signale "
        "soit un champ couvert différent, soit une désignation du chef de "
        "ménage mal comprise par les enquêteurs.",
        ["Part = chefs de ménage de sexe féminin / chefs de ménage"],
        p_e, "%", reference=f"RGPH-3 : {fmt(p_r, 1)} %",
        calcul=[f"RSU : {fmt(cf)} femmes sur {fmt(ct)} chefs → {fmt(p_e, 1)} %.",
                f"RGPH-3 : {fmt(rg['chefs_femmes'])} sur {fmt(rg['chefs'])} "
                f"→ {fmt(p_r, 1)} %.",
                f"Écart : {fmt(ec5, 1)} point(s)."],
        conclusion=("→ Alerte : la désignation du chef de ménage diffère "
                    "nettement du recensement." if _grav("A5", ec5) == "alerte"
                    else "→ Vigilance : écart à surveiller."
                    if _grav("A5", ec5) == "vigilance" else
                    "→ Part conforme au recensement."),
        seuils=[f"Écart ≥ {SEUILS['A5'][1]:.0f} points : alerte ; "
                f"≥ {SEUILS['A5'][0]:.0f} : vigilance"],
        gravite=_grav("A5", ec5), stat=f"écart {fmt(ec5, 1)} pt"))

    # --- A6 structure par grand groupe d'âge ------------------------------
    grp = ((0, 15, "0-14 ans"), (15, 65, "15-64 ans"), (65, 200, "65 ans et +"))
    det, ecs = [], []
    for lo, hi, lib in grp:
        a, b = _part_age(ps, lo, hi), _part_age(pr, lo, hi)
        if a is not None and b is not None:
            ecs.append(abs(a - b))
            det.append(f"{lib} : RSU {fmt(a, 1)} % contre {fmt(b, 1)} % "
                       f"au RGPH-3 ({fmt(a - b, 1)} point)")
    mx = max(ecs) if ecs else None
    out.append(_ind(
        "A6", "Structure par grand groupe d'âge",
        "Décompose l'écart global de A2 en trois blocs lisibles. Un déficit "
        "d'enfants désigne un roster tronqué ; un excès de personnes âgées, "
        "un arrondi des âges vers le haut ; un excès d'âges actifs, un champ "
        "couvert particulier.",
        ["Part(g) = effectif du groupe / effectif total, RSU et RGPH-3"],
        mx, "points d'écart maximal",
        reference="RGPH-3 2018, mêmes communes",
        calcul=det,
        conclusion=("→ Alerte : un groupe d'âge s'écarte fortement du "
                    "recensement." if _grav("A6", mx) == "alerte" else
                    "→ Vigilance : écart notable sur un groupe d'âge."
                    if _grav("A6", mx) == "vigilance" else
                    "→ Répartition par grand groupe d'âge conforme."),
        seuils=[f"Écart ≥ {SEUILS['A6'][1]:.0f} points : alerte ; "
                f"≥ {SEUILS['A6'][0]:.0f} : vigilance"],
        gravite=_grav("A6", mx)))
    return out


# --------------------------------------------------------------------------
# FAMILLE B — Précision de la mesure (normes démographiques internationales)
# --------------------------------------------------------------------------
def famille_b(ms):
    """Les trois indices classiques d'arrondi des âges, plus l'indice ONU.

    Ils ne demandent aucune source externe : seulement un effectif. C'est
    précisément pourquoi ils ont leur place ici et pas dans le tableau par
    agent — l'indice combiné ONU réclame 800 individus, quand l'agent médian
    en observe 280. Il ne disparaît pas du dispositif, il change d'étage."""
    out = []
    ages = VQ._membres_ages(ms)
    wh, s5, n5 = VQ._whipple(ages)
    q = ("très précise" if wh is not None and wh < 105 else
         "précise" if wh is not None and wh < 110 else
         "approximative" if wh is not None and wh < 125 else
         "grossière" if wh is not None and wh < 175 else "très grossière")
    out.append(_ind(
        "B1", "Indice de Whipple (arrondi en 0 et 5)",
        "Mesure l'attraction des âges se terminant par 0 ou 5 sur la tranche "
        "23-62 ans. C'est l'indicateur de référence de la qualité de la "
        "déclaration d'âge, et le seul dont l'échelle d'interprétation soit "
        "normalisée au niveau international.",
        ["W = (Σ âges terminés par 0 ou 5) / (n / 5) × 100",
         "n = âges de 23 à 62 ans"],
        wh, "", reference="norme ONU : 100 = aucune attraction",
        calcul=[f"{fmt(n5)} âge(s) de 23 à 62 ans, dont {fmt(s5)} terminés "
                f"par 0 ou 5.",
                f"W = {fmt(wh, 1)} → déclaration {q}."],
        conclusion=(f"→ Alerte : déclaration d'âge {q} — les analyses par "
                    "groupe d'âge fin doivent être maniées avec prudence."
                    if _grav("B1", wh) == "alerte" else
                    f"→ Vigilance : déclaration d'âge {q}."
                    if _grav("B1", wh) == "vigilance" else
                    f"→ Déclaration d'âge {q}."),
        seuils=["< 105 très précise · 105-110 précise · 110-125 approximative",
                "125-175 grossière · > 175 très grossière (échelle ONU)"],
        gravite=_grav("B1", wh), stat=f"qualité {q}"))

    im, pct = VQ._myers(ages)
    pire = max(range(10), key=lambda d: abs(pct[d] - 10)) if pct else None
    out.append(_ind(
        "B2", "Indice de Myers (préférence par chiffre terminal)",
        "Là où Whipple ne regarde que 0 et 5, Myers examine les dix chiffres. "
        "Il dit non seulement qu'il y a arrondi, mais vers quel chiffre — "
        "information utile pour reprendre la formation des enquêteurs.",
        ["Im = ½ × Σ |P(d) − 10|, d = 0…9, sommes mélangées sur 10-89 ans"],
        im, "", reference="0 = aucune préférence",
        calcul=([f"Chiffre le plus attracteur : {pire} "
                 f"({fmt(pct[pire], 1)} % au lieu de 10 %)."] if pct else [])
               + (["Répartition (%) : "
                   + ", ".join(f"{d}:{fmt(pct[d], 1)}" for d in range(10))]
                  if pct else []),
        conclusion=("→ Alerte : préférence de chiffre très marquée sur "
                    "l'ensemble de la base." if _grav("B2", im) == "alerte" else
                    "→ Vigilance : préférence de chiffre notable."
                    if _grav("B2", im) == "vigilance" else
                    "→ Préférence de chiffre dans la norme."),
        seuils=["0-5 excellente · 5-10 bonne · 10-20 moyenne · > 20 faible"],
        gravite=_grav("B2", im)))

    mx = max(abs(pct[d] - 10) for d in range(10)) if pct else None
    out.append(_ind(
        "B3", "Écart maximal d'un chiffre terminal",
        "Le détail derrière Myers : de combien de points le chiffre le plus "
        "attracteur dépasse-t-il les 10 % attendus ? Un seul chiffre très "
        "au-dessus se corrige par la formation ; un profil étalé sur "
        "plusieurs chiffres relève de l'absence d'état civil.",
        ["max |P(d) − 10|, d = 0…9"],
        mx, "points", reference="10 % attendus par chiffre",
        calcul=([f"Chiffre {pire} : {fmt(pct[pire], 1)} % au lieu de 10 %."]
                if pct else []),
        conclusion=("→ Alerte : un chiffre terminal domine nettement."
                    if _grav("B3", mx) == "alerte" else
                    "→ Vigilance : préférence visible pour un chiffre."
                    if _grav("B3", mx) == "vigilance" else
                    "→ Chiffres terminaux équilibrés."),
        seuils=[f"Écart ≥ {SEUILS['B3'][1]:.0f} points : alerte ; "
                f"≥ {SEUILS['B3'][0]:.0f} : vigilance"],
        gravite=_grav("B3", mx), stat=(f"chiffre {pire}" if pire is not None else "")))

    ip, srs, mh, mf = VQ._ipas(ms)
    out.append(_ind(
        "B4", "Indice combiné de précision âge-sexe (ONU)",
        "Diagnostic d'ensemble : irrégularité de la répartition par âge des "
        "hommes, puis des femmes, puis du rapport de masculinité d'un groupe "
        "quinquennal au suivant. Il demande environ 800 individus, ce qui le "
        "rend inutilisable pour juger un agent — mais parfaitement adapté à "
        "l'échelle du RSU.",
        ["IPAS = 3 × SRS + ARSM + ARSF",
         "SRS = écart absolu moyen des rapports de masculinité successifs",
         "ARSM / ARSF = irrégularité de la répartition par âge, par sexe"],
        ip, "", reference="seuils du document RSU : 20 / 40",
        calcul=[f"Écart moyen des rapports de masculinité successifs : {fmt(srs, 2)}",
                f"Irrégularité hommes : {fmt(mh, 2)} · femmes : {fmt(mf, 2)}",
                f"IPAS = 3 × {fmt(srs, 2)} + {fmt(mh, 2)} + {fmt(mf, 2)} = {fmt(ip, 1)}"],
        conclusion=("→ Alerte : données d'âge et de sexe globalement peu "
                    "précises à l'échelle du RSU."
                    if _grav("B4", ip) == "alerte" else
                    "→ Vigilance : précision âge-sexe moyenne."
                    if _grav("B4", ip) == "vigilance" else
                    "→ Précision âge-sexe satisfaisante."),
        seuils=["< 20 précis · 20-40 moyennement précis · > 40 imprécis"],
        gravite=_grav("B4", ip)))
    return out


# --------------------------------------------------------------------------
# FAMILLE C — Complétude
# --------------------------------------------------------------------------
# Variables OBLIGATOIRES : celles qui ne dépendent d'aucun filtre du
# questionnaire. Un taux de non-réponse n'a de sens que sur elles — mesuré sur
# une variable conditionnelle (le module emploi, posé aux seuls 15 ans et
# plus), il compte comme « manquant » ce que le questionnaire a délibérément
# sauté, et affiche 60 % de vide sur une collecte parfaite.
VARS_OBLIG_MEN = ("CQ3", "nbmembre", "taille_men", "H1", "H2", "H4", "H5",
                  "H6", "H7", "H8", "H9", "H10")
VARS_OBLIG_MEM = ("M3", "M4", "M7")


def famille_c(ms, colonnes_men, colonnes_mem):
    out = []
    mem = [x for m in ms for x in m.get("membres", ())]
    det, taux = [], []
    for lot, rows, lib in ((VARS_OBLIG_MEN, ms, "ménage"),
                           (VARS_OBLIG_MEM, mem, "membre")):
        for c in lot:
            if not rows:
                continue
            miss = sum(1 for r in rows if r.get(c) in (None, ""))
            p = _pct(miss, len(rows))
            taux.append(p)
            det.append((p, f"{c} ({lib}) : {fmt(p, 1)} % manquant "
                           f"({fmt(miss)} / {fmt(len(rows))})"))
    det.sort(reverse=True)
    med = sorted(taux)[len(taux) // 2] if taux else None
    out.append(_ind(
        "C1", "Non-réponse sur les variables obligatoires",
        "Taux de valeurs manquantes sur les seules variables posées à TOUS — "
        "jamais sur les variables conditionnelles, dont le vide est voulu par "
        "le questionnaire et ne dit rien de la qualité.",
        ["Taux médian de manquant sur "
         f"{len(VARS_OBLIG_MEN)} variables ménage et "
         f"{len(VARS_OBLIG_MEM)} variables membre"],
        med, "% (médiane)", reference="0 % attendu sur une variable obligatoire",
        calcul=[t for _p, t in det[:6]] + ["…"],
        conclusion=("→ Alerte : non-réponse importante sur des variables qui "
                    "devraient toujours être renseignées."
                    if _grav("C1", med) == "alerte" else
                    "→ Vigilance : non-réponse notable sur les variables "
                    "obligatoires." if _grav("C1", med) == "vigilance" else
                    "→ Variables obligatoires correctement renseignées."),
        seuils=[f"Médiane ≥ {SEUILS['C1'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['C1'][0]:.0f} % : vigilance"],
        gravite=_grav("C1", med),
        stat=(det[0][1].split(" :")[0] if det else "")))

    # --- C2 variables attendues absentes ou intégralement vides -----------
    # Deux incidents distincts, et le second est le plus insidieux :
    #   ABSENTE — la colonne n'existe pas dans les données. Le questionnaire a
    #     changé de nom de variable, et tout test qui s'en sert est devenu muet
    #     sans que rien ne le signale. C'est exactement ce qui avait éteint le
    #     niveau 5 entier (`AP1__1` renommé `AP__1`).
    #   VIDE — la colonne existe et n'a jamais été remplie. Là, c'est le
    #     questionnaire ou la collecte qui est en cause, pas le traitement.
    absentes, vides = [], []
    for lot, rows, lib, schema in (
            (colonnes_men, ms, "ménage", VQ.SCHEMA_LU.get("menage") or set()),
            (colonnes_mem, mem, "membre", VQ.SCHEMA_LU.get("membre") or set())):
        for c in lot:
            if schema and c not in schema:
                absentes.append(f"{c} ({lib})")
            elif rows and all(r.get(c) in (None, "") for r in rows):
                vides.append(f"{c} ({lib})")
    total = len(absentes) + len(vides)
    out.append(_ind(
        "C2", "Variables attendues absentes ou vides",
        "Le contrôle de schéma. Une colonne que le traitement attend et que "
        "le RSU ne contient pas éteint silencieusement tous les tests qui "
        "s'en servent — aucun message d'erreur, juste des résultats « non "
        "calculés » qu'on finit par prendre pour normaux. Une colonne "
        "présente mais vide de bout en bout pose la même question, du côté "
        "de la collecte.",
        ["Nombre de variables attendues absentes du RSU",
         "+ nombre de variables présentes dont 100 % des valeurs manquent"],
        total, "variable(s)", reference="0 attendu",
        calcul=([f"ABSENTES du RSU ({len(absentes)}) : "
                 + ", ".join(absentes[:10])
                 + (" …" if len(absentes) > 10 else "")] if absentes else [])
               + ([f"PRÉSENTES mais vides ({len(vides)}) : "
                   + ", ".join(vides[:10])
                   + (" …" if len(vides) > 10 else "")] if vides else [])
               + ([] if total else ["Toutes les variables attendues sont "
                                    "présentes et renseignées."]),
        conclusion=("→ Alerte : le traitement attend des variables que "
                    "le RSU ne fournit pas — les tests qui en dépendent "
                    "sont muets, pas conformes." if absentes else
                    "→ Alerte : des variables sont présentes mais jamais "
                    "renseignées." if vides else
                    "→ Schéma conforme : toutes les variables attendues sont "
                    "présentes et portent des valeurs."),
        seuils=["Toute variable attendue absente ou vide est une alerte",
                "Vérifier d'abord le nom de la variable dans la version "
                "courante du questionnaire"],
        gravite="alerte" if total else "ok",
        stat=(f"{len(absentes)} absente(s), {len(vides)} vide(s)"
              if total else "")))

    # --- C3 GPS -----------------------------------------------------------
    sans = sum(1 for m in ms if num(m.get("GPS__Latitude")) is None
               or num(m.get("GPS__Longitude")) is None)
    p3 = _pct(sans, len(ms))
    out.append(_ind(
        "C3", "Ménages sans coordonnées GPS",
        "Le point GPS conditionne la cartographie, le contrôle de "
        "déplacement des agents (test 8.4) et tout rapprochement ultérieur "
        "avec une base d'adresses. Son absence se rattrape mal après coup.",
        ["Part des ménages sans latitude ou sans longitude exploitable"],
        p3, "%", reference="0 % attendu",
        calcul=[f"{fmt(sans)} ménage(s) sans point GPS sur {fmt(len(ms))}."],
        conclusion=("→ Alerte : une part importante de la base n'est pas "
                    "localisable." if _grav("C3", p3) == "alerte" else
                    "→ Vigilance : localisation manquante sur une fraction "
                    "notable." if _grav("C3", p3) == "vigilance" else
                    "→ Localisation quasi complète."),
        seuils=[f"≥ {SEUILS['C3'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['C3'][0]:.0f} % : vigilance"],
        gravite=_grav("C3", p3)))

    # --- C4 ménages sans membre ------------------------------------------
    vide = sum(1 for m in ms if not m.get("membres"))
    p4 = _pct(vide, len(ms))
    out.append(_ind(
        "C4", "Ménages sans aucun membre au roster",
        "Un ménage enregistré dont le roster est vide n'est pas exploitable : "
        "ni taille, ni composition, ni éligibilité. Ce sont des "
        "questionnaires à reprendre, pas à corriger.",
        ["Part des ménages dont le roster ne contient aucune ligne"],
        p4, "%", reference="0 % attendu",
        calcul=[f"{fmt(vide)} ménage(s) sans membre sur {fmt(len(ms))}."],
        conclusion=("→ Alerte : trop de questionnaires sans composition de "
                    "ménage." if _grav("C4", p4) == "alerte" else
                    "→ Vigilance : quelques questionnaires sans roster."
                    if _grav("C4", p4) == "vigilance" else
                    "→ Tous les ménages ont un roster."),
        seuils=[f"≥ {SEUILS['C4'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['C4'][0]:.1f} % : vigilance"],
        gravite=_grav("C4", p4)))
    return out


# --------------------------------------------------------------------------
# FAMILLE D — Unicité et duplication
# --------------------------------------------------------------------------
_REMPLISSAGE = re.compile(r"^(?:(\d)\1{5,}|.*(?:999999|000000))$")


def famille_d(ms):
    out = []
    # --- D1 unicité de la clé d'interview ---------------------------------
    cles = Counter(m.get("key") for m in ms if m.get("key"))
    dbl = [k for k, v in cles.items() if v > 1]
    out.append(_ind(
        "D1", "Unicité de la clé d'interview",
        "Contrôle d'intégrité de base : deux lignes portant la même clé "
        "signifient des données corrompues ou une fusion ratée, et toute "
        "statistique calculée dessus est fausse. Il doit rester vert.",
        ["Nombre de valeurs d'interview__key apparaissant plus d'une fois"],
        len(dbl), "clé(s) en double", reference="0 exigé",
        calcul=[f"{fmt(len(cles))} clé(s) distincte(s) pour {fmt(len(ms))} ligne(s)."]
               + ([f"En double : {', '.join(map(str, dbl[:8]))}"] if dbl else []),
        conclusion=("→ Alerte : le RSU contient des doublons de clé — ne "
                    "rien exploiter avant correction." if dbl else
                    "→ Chaque ménage porte une clé unique."),
        seuils=["Toute clé dupliquée est une alerte"],
        gravite="alerte" if dbl else "ok"))

    # --- D2 / D3 numéros de CIN -------------------------------------------
    cin = [txt(x.get("M6a")) for m in ms for x in m.get("membres", ())
           if txt(x.get("M6a"))]
    remp = [v for v in cin if _REMPLISSAGE.match(v)]
    vrais = [v for v in cin if not _REMPLISSAGE.match(v)]
    c = Counter(vrais)
    part = [(k, v) for k, v in c.items() if v > 1]
    pers = sum(v for _k, v in part)
    p2 = _pct(pers, len(vrais))
    # Le même numéro dans DEUX ménages distincts est plus grave que deux fois
    # dans le même : c'est soit une double inscription, soit une saisie copiée.
    men_par_cin = defaultdict(set)
    for m in ms:
        for x in m.get("membres", ()):
            v = txt(x.get("M6a"))
            if v and not _REMPLISSAGE.match(v):
                men_par_cin[v].add(m.get("key"))
    inter = [v for v, s in men_par_cin.items() if len(s) > 1]
    out.append(_ind(
        "D2", "Numéros de CIN portés par plusieurs personnes",
        "Le RSU utilisera le CIN comme identifiant : un numéro partagé est "
        "soit une faute de saisie, soit une double inscription. Les deux se "
        "corrigent, mais pas de la même manière — d'où le décompte séparé des "
        "numéros que l'on retrouve dans des ménages DIFFÉRENTS.",
        ["Part des CIN plausibles apparaissant plus d'une fois",
         "Les valeurs de remplissage sont exclues (voir D3)"],
        p2, "%", reference="0 % exigé pour un identifiant",
        calcul=[f"{fmt(len(vrais))} numéro(s) plausible(s) saisi(s).",
                f"{fmt(len(part))} numéro(s) porté(s) par {fmt(pers)} "
                f"personne(s) → {fmt(p2, 2)} %.",
                f"Dont {fmt(len(inter))} numéro(s) présent(s) dans des "
                f"ménages différents."],
        conclusion=("→ Alerte : l'unicité du CIN n'est pas assurée — à "
                    "reprendre avant tout appariement."
                    if _grav("D2", p2) == "alerte" else
                    "→ Vigilance : quelques numéros de CIN sont partagés."
                    if _grav("D2", p2) == "vigilance" else
                    "→ Numéros de CIN uniques."),
        seuils=[f"≥ {SEUILS['D2'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['D2'][0]:.0f} % : vigilance"],
        gravite=_grav("D2", p2),
        stat=f"{fmt(len(inter))} inter-ménages"))

    p3 = _pct(len(remp), len(cin))
    top = Counter(remp).most_common(4)
    out.append(_ind(
        "D3", "Valeurs de remplissage dans le numéro de CIN",
        "Quand le numéro n'est pas connu, l'enquêteur invente une valeur "
        "acceptée par le masque de saisie — des 9, des 0. Ce n'est pas une "
        "faute d'enquêteur, c'est une règle de validation manquante : le "
        "champ devrait refuser ces valeurs ou proposer « non disponible ».",
        ["Part des CIN de la forme 999999999999, 000000000000, …999999"],
        p3, "%", reference="0 % attendu",
        calcul=[f"{fmt(len(remp))} valeur(s) de remplissage sur "
                f"{fmt(len(cin))} numéro(s) saisi(s)."]
               + ([f"Les plus fréquentes : "
                   + ", ".join(f"{k} ×{v}" for k, v in top)] if top else []),
        conclusion=("→ Alerte : le champ CIN accepte massivement des valeurs "
                    "factices — ajouter une règle de validation."
                    if _grav("D3", p3) == "alerte" else
                    "→ Vigilance : présence de valeurs factices dans le CIN."
                    if _grav("D3", p3) == "vigilance" else
                    "→ Pas de valeur de remplissage détectée."),
        seuils=[f"≥ {SEUILS['D3'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['D3'][0]:.1f} % : vigilance"],
        gravite=_grav("D3", p3)))

    # --- D4 signature du ménage ------------------------------------------
    sig = Counter()
    for m in ms:
        nom = (txt(m.get("nom_cm")) or "").strip().upper()
        if nom:
            sig[(nom, m.get("fokontany") or "")] += 1
    dup = [(k, v) for k, v in sig.items() if v > 1]
    nmen = sum(v for _k, v in dup)
    p4 = _pct(nmen, sum(sig.values()))
    out.append(_ind(
        "D4", "Ménages de même chef dans le même fokontany",
        "Deux ménages portant le même nom de chef dans le même fokontany "
        "sont, le plus souvent, le même ménage enquêté deux fois — ou deux "
        "homonymes, ce qui arrive. C'est une liste à vérifier, pas un verdict.",
        ["Part des ménages dont le couple (nom du chef, fokontany) "
         "apparaît plus d'une fois"],
        p4, "%", reference="homonymie résiduelle attendue",
        calcul=[f"{fmt(len(dup))} signature(s) dupliquée(s) couvrant "
                f"{fmt(nmen)} ménage(s) sur {fmt(sum(sig.values()))} nommés."],
        conclusion=("→ Alerte : trop de ménages homonymes dans un même "
                    "fokontany pour que ce soit de l'homonymie."
                    if _grav("D4", p4) == "alerte" else
                    "→ Vigilance : quelques ménages à vérifier pour doublon."
                    if _grav("D4", p4) == "vigilance" else
                    "→ Pas de duplication apparente de ménages."),
        seuils=[f"≥ {SEUILS['D4'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['D4'][0]:.1f} % : vigilance"],
        gravite=_grav("D4", p4)))
    return out


# --------------------------------------------------------------------------
# FAMILLE E — Cohérence structurelle
# --------------------------------------------------------------------------
def famille_e(ms):
    out = []
    # --- E1 chef de ménage -----------------------------------------------
    nb = Counter(sum(1 for x in m.get("membres", ())
                     if num(x.get("M7")) == VQ.M7_CHEF) for m in ms)
    sans, multi = nb.get(0, 0), sum(v for k, v in nb.items() if k >= 2)
    p1 = _pct(sans, len(ms))
    out.append(_ind(
        "E1", "Ménages sans chef déclaré",
        "Chaque ménage doit avoir un chef et un seul : c'est lui qui porte "
        "l'éligibilité et le rattachement administratif. Attention, cet "
        "indicateur est sensible au PRÉCHARGEMENT — un membre déjà connu du "
        "registre garde son lien de parenté dans la colonne `M7_preload`, et "
        "le lire au mauvais endroit faisait apparaître un tiers des ménages "
        "comme sans chef.",
        ["Part des ménages où aucun membre ne porte M7 = 1"],
        p1, "%", reference="0 % attendu",
        calcul=[f"{fmt(sans)} ménage(s) sans chef, {fmt(multi)} avec deux "
                f"chefs ou plus, sur {fmt(len(ms))}."],
        conclusion=("→ Alerte : trop de ménages sans chef identifié."
                    if _grav("E1", p1) == "alerte" else
                    "→ Vigilance : quelques ménages sans chef identifié."
                    if _grav("E1", p1) == "vigilance" else
                    "→ Chef de ménage identifié presque partout."),
        seuils=[f"≥ {SEUILS['E1'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['E1'][0]:.0f} % : vigilance"],
        gravite=_grav("E1", p1), stat=f"{fmt(multi)} à 2 chefs ou +"))

    # --- E2 taille déclarée contre roster ---------------------------------
    ec = Counter()
    pires = []
    for m in ms:
        t = num(m.get("taille_men"))
        if t is None:
            continue
        e = len(m.get("membres", ())) - int(t)
        ec[abs(e)] += 1
        if abs(e) >= 5:
            pires.append((abs(e), int(t), len(m.get("membres", ())), m.get("key")))
    tot = sum(ec.values())
    gros = sum(v for k, v in ec.items() if k >= 3)
    p2 = _pct(gros, tot)
    pires.sort(reverse=True)
    out.append(_ind(
        "E2", "Taille déclarée contre effectif du roster",
        "`taille_men` est saisie par l'enquêteur, le roster est construit "
        "ligne à ligne : les deux doivent coïncider. Un écart de 1 ou 2 peut "
        "venir d'un membre absent retiré en cours d'entretien ; un écart de "
        "trois ou plus est une erreur à reprendre, et la liste est courte.",
        ["Part des ménages dont |roster − taille_men| ≥ 3"],
        p2, "%", reference="0 % attendu",
        calcul=[f"Sur {fmt(tot)} ménage(s) à taille déclarée : "
                f"{fmt(_pct(ec.get(0, 0), tot), 1)} % exacts, "
                f"{fmt(_pct(ec.get(1, 0), tot), 1)} % à ±1, "
                f"{fmt(_pct(ec.get(2, 0), tot), 1)} % à ±2, "
                f"{fmt(p2, 1)} % à ±3 ou plus."]
               + ([f"Écarts les plus grands : "
                   + " ; ".join(f"déclaré {t} / roster {r}"
                                for _e, t, r, _k in pires[:4])] if pires else []),
        conclusion=("→ Alerte : la taille déclarée et le roster divergent trop "
                    "souvent." if _grav("E2", p2) == "alerte" else
                    "→ Vigilance : divergences à reprendre sur une liste "
                    "courte." if _grav("E2", p2) == "vigilance" else
                    "→ Taille déclarée et roster cohérents."),
        seuils=[f"≥ {SEUILS['E2'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['E2'][0]:.0f} % : vigilance"],
        gravite=_grav("E2", p2), stat=f"{fmt(len(pires))} écarts ≥ 5"))

    # --- E3 rattachement géographique -------------------------------------
    sans = sum(1 for m in ms if not m.get("code_commune"))
    p3 = _pct(sans, len(ms))
    out.append(_ind(
        "E3", "Ménages sans commune identifiée",
        "Un ménage sans code commune sort de tous les agrégats territoriaux, "
        "de la comparaison au recensement et du calcul de couverture. Il "
        "n'est pas perdu, il est invisible — ce qui est pire.",
        ["Part des ménages sans code commune exploitable"],
        p3, "%", reference="0 % attendu",
        calcul=[f"{fmt(sans)} ménage(s) sans commune sur {fmt(len(ms))}."],
        conclusion=("→ Alerte : une part notable de la base échappe aux "
                    "agrégats territoriaux." if _grav("E3", p3) == "alerte" else
                    "→ Vigilance : quelques ménages sans rattachement."
                    if _grav("E3", p3) == "vigilance" else
                    "→ Tous les ménages sont rattachés à une commune."),
        seuils=[f"≥ {SEUILS['E3'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['E3'][0]:.1f} % : vigilance"],
        gravite=_grav("E3", p3)))
    return out


# --------------------------------------------------------------------------
# FAMILLE F — Processus et paradonnées
# --------------------------------------------------------------------------
def famille_f(ms, rejetes):
    out = []
    n = len(ms) + rejetes
    p1 = _pct(rejetes, n)
    out.append(_ind(
        "F1", "Interviews rejetées présentes dans les données",
        "Un questionnaire rejeté par le siège a été écarté par le contrôle "
        "qualité : il n'est pas de la donnée. Tous les indicateurs de cette "
        "page l'excluent. Reste à savoir combien il y en a — un taux qui "
        "monte signale un problème en amont, pas dans la base.",
        ["Part des interviews de statut rejeté dans les données brutes"],
        p1, "%", reference="exclus du calcul des autres indicateurs",
        calcul=[f"{fmt(rejetes)} interview(s) rejetée(s) sur {fmt(n)} "
                f"enregistrée(s) ; {fmt(len(ms))} retenue(s) pour cette page."],
        conclusion=("→ Alerte : taux de rejet élevé — à examiner avec les "
                    "chefs d'équipe." if _grav("F1", p1) == "alerte" else
                    "→ Vigilance : taux de rejet à surveiller."
                    if _grav("F1", p1) == "vigilance" else
                    "→ Taux de rejet faible."),
        seuils=[f"≥ {SEUILS['F1'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['F1'][0]:.0f} % : vigilance"],
        gravite=_grav("F1", p1)))

    # --- F2 régularité de la collecte -------------------------------------
    j = Counter(m["date"] for m in ms if m.get("date"))
    vals = sorted(j.values())
    med = vals[len(vals) // 2] if vals else None
    rap = (max(vals) / float(med)) if (vals and med) else None
    out.append(_ind(
        "F2", "Régularité du rythme de collecte",
        "Un pic isolé — une journée qui pèse plusieurs fois la médiane — est "
        "rarement une journée exceptionnelle sur le terrain : c'est plus "
        "souvent une saisie différée de plusieurs jours de travail, ce qui "
        "rend les durées d'entretien et les dates ininterprétables.",
        ["Rapport = ménages du jour le plus chargé / ménages du jour médian"],
        rap, "×",
        reference=(f"{len(j)} jour(s) de collecte, du {jour(min(j)) or min(j)} "
                   f"au {jour(max(j)) or max(j)}" if j else "dates absentes"),
        calcul=([f"Jour médian : {fmt(med)} ménage(s) ; jour le plus chargé : "
                 f"{fmt(max(vals))} ; le plus creux : {fmt(min(vals))}."]
                if vals else ["Aucune date de collecte exploitable."]),
        conclusion=("→ Alerte : le volume journalier est très irrégulier — "
                    "vérifier les dates de saisie."
                    if _grav("F2", rap) == "alerte" else
                    "→ Vigilance : rythme de collecte irrégulier."
                    if _grav("F2", rap) == "vigilance" else
                    "→ Rythme de collecte régulier."),
        seuils=[f"≥ {SEUILS['F2'][1]:.0f} × : alerte ; "
                f"≥ {SEUILS['F2'][0]:.0f} × : vigilance"],
        gravite=_grav("F2", rap)))

    # --- F3 entretiens très courts ----------------------------------------
    dur = [m["duree"] for m in ms if m.get("duree")]
    court = sum(1 for d in dur if d < DUREE_COURTE)
    p3 = _pct(court, len(dur))
    dur_t = sorted(dur)
    out.append(_ind(
        "F3", f"Entretiens de moins de {DUREE_COURTE:.0f} minutes",
        "Un questionnaire ménage complet ne se remplit pas en dix minutes. "
        "Cet indicateur ne désigne personne — le test 8.3 du tableau par "
        "agent s'en charge — il dit seulement quelle part de la base repose "
        "sur des entretiens trop rapides pour avoir été administrés.",
        [f"Part des entretiens de durée < {DUREE_COURTE:.0f} minutes"],
        p3, "%",
        reference=(f"médiane {fmt(dur_t[len(dur_t) // 2], 0)} min" if dur_t
                   else "durées absentes"),
        calcul=([f"{fmt(court)} entretien(s) sous {DUREE_COURTE:.0f} min sur "
                 f"{fmt(len(dur))} chronométré(s).",
                 f"Distribution : p05 {fmt(dur_t[int(len(dur_t) * .05)], 0)} min, "
                 f"médiane {fmt(dur_t[len(dur_t) // 2], 0)}, "
                 f"p95 {fmt(dur_t[int(len(dur_t) * .95)], 0)}."]
                if dur_t else ["Aucune durée exploitable."]),
        conclusion=("→ Alerte : une part importante des entretiens est trop "
                    "courte pour être plausible."
                    if _grav("F3", p3) == "alerte" else
                    "→ Vigilance : entretiens courts en nombre notable."
                    if _grav("F3", p3) == "vigilance" else
                    "→ Durées d'entretien plausibles."),
        seuils=[f"≥ {SEUILS['F3'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['F3'][0]:.0f} % : vigilance"],
        gravite=_grav("F3", p3)))

    # --- F4 erreurs de validation résiduelles -----------------------------
    err = sum(1 for m in ms if (m.get("erreurs_ss") or 0) > 0)
    p4 = _pct(err, len(ms))
    out.append(_ind(
        "F4", "Erreurs de validation Survey Solutions résiduelles",
        "Survey Solutions bloque la plupart des incohérences à la saisie. "
        "Celles qui subsistent dans des questionnaires approuvés ont été validées "
        "malgré l'avertissement : elles méritent un regard, et leur rareté "
        "explique pourquoi les règles logiques qui les doublent ont été "
        "retirées du tableau par agent.",
        ["Part des ménages portant au moins une erreur de validation"],
        p4, "%", reference="0 % attendu sur des questionnaires approuvés",
        calcul=[f"{fmt(err)} ménage(s) avec erreur de validation sur "
                f"{fmt(len(ms))}."],
        conclusion=("→ Alerte : des incohérences bloquantes ont été validées "
                    "en nombre." if _grav("F4", p4) == "alerte" else
                    "→ Vigilance : quelques erreurs de validation acceptées."
                    if _grav("F4", p4) == "vigilance" else
                    "→ Pratiquement aucune erreur de validation résiduelle."),
        seuils=[f"≥ {SEUILS['F4'][1]:.0f} % : alerte ; "
                f"≥ {SEUILS['F4'][0]:.1f} % : vigilance"],
        gravite=_grav("F4", p4)))
    return out


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------
def _graphiques(ms, rg):
    """Séries prêtes à tracer. Le texte dit le verdict, la courbe le rend évident.

    Tout est en POURCENTAGES et jamais en effectifs : le RSU couvre 35 % des
    ménages et le RGPH-3 est un échantillon au dixième — superposer des
    effectifs bruts ne comparerait que des tailles d'échantillon."""
    ps = _pyramide(ms)
    pr = (rg or {}).get("pyr") or Counter()
    tot_s, tot_r = sum(ps.values()) or 1, sum(pr.values()) or 1
    pyr = []
    for t in range(17):
        lib = f"{t * 5}-{t * 5 + 4}" if t < 16 else "80 et +"
        pyr.append({
            "groupe": lib,
            "sH": round(100.0 * ps.get((t, 1), 0) / tot_s, 2),
            "sF": round(100.0 * ps.get((t, 2), 0) / tot_s, 2),
            "rH": round(100.0 * pr.get((t, 1), 0) / tot_r, 2) if pr else None,
            "rF": round(100.0 * pr.get((t, 2), 0) / tot_r, 2) if pr else None,
        })
    _im, pct = VQ._myers(VQ._membres_ages(ms))
    chiffres = [{"d": d, "p": round(pct[d], 2)} for d in range(10)] if pct else []
    return {"pyramide": pyr, "chiffres": chiffres, "rgph": bool(pr)}


# Couleur d'accent et pictogramme de chaque famille. Six familles, six repères
# visuels : sur une page de 25 indicateurs, la couleur porte la navigation plus
# vite qu'un numéro.
STYLE_FAMILLE = {
    "A": ("#2563eb", "🌍"),
    "B": ("#7c3aed", "📐"),
    "C": ("#0891b2", "🧩"),
    "D": ("#db2777", "🔑"),
    "E": ("#ea580c", "🏗️"),
    "F": ("#059669", "⏱️"),
}

FAMILLES = (
    ("A", "Couverture et représentativité",
     "Confrontation au RGPH-3 2018 agrégé sur les mêmes communes. Répond à "
     "« la base décrit-elle la population qu'elle prétend décrire ? »"),
    ("B", "Précision de la mesure",
     "Indices démographiques normalisés. Ils ne demandent aucune source "
     "externe, seulement un effectif — celui du RSU, pas d'un agent."),
    ("C", "Complétude",
     "Ce qui manque, en distinguant le vide voulu par le questionnaire du "
     "vide subi."),
    ("D", "Unicité et duplication",
     "Un registre social vit de ses identifiants : ce qui est compté deux "
     "fois sera servi deux fois."),
    ("E", "Cohérence structurelle",
     "Les contrôles qu'aucune comparaison entre agents ne peut faire, parce "
     "qu'ils portent sur la construction même de l'enregistrement."),
    ("F", "Processus et paradonnées",
     "Ce que la collecte dit d'elle-même : statuts, calendrier, durées."),
)


def calculer(conn, districts=None, communes=None):
    """Indicateurs de qualité des DONNÉES RSU, pour le périmètre demandé.

    Même contrat de sortie que `vad_qualite.calculer` : un dictionnaire
    sérialisable, `disponible` à False si les tables manquent."""
    try:
        tous = VQ.charger(conn, districts, communes)
    except Exception as e:
        return {"disponible": False, "erreur": str(e), "familles": []}
    if not tous:
        return {"disponible": False, "erreur": "aucun ménage dans ce périmètre",
                "familles": []}

    rejete = lambda m: num(m.get("interview__status")) in STATUTS_REJETES
    ms = [m for m in tous if not rejete(m)]
    n_rejetes = len(tous) - len(ms)

    codes = {m.get("code_commune") for m in ms if m.get("code_commune")}
    rg = _rgph(conn, codes)

    # Couverture commune par commune, pour A1 et pour le tableau de la page.
    noms = {}
    try:
        for c_, nom in conn.execute('SELECT "code_commune","nom" FROM "commune"'):
            noms[int(c_)] = nom
    except Exception:
        pass
    # RÉFÉRENCE = LE DÉNOMBREMENT (et non plus la projection RGPH-3 de
    # `commune.nombreMenage`) : ménages attendus = ménages dénombrés de la
    # commune, ménages enquêtés = ménages DISTINCTS interviewés (une même clé
    # `interview_keyden` compte une fois), toutes interviews confondues — la
    # même règle que le détail par commune de la feuille « Global ».
    import vad_core                      # import local : vad_core importe ce module
    attendus = vad_core._denombres_par_commune(conn, districts, communes)
    keyden = {}
    try:
        for k, kd in conn.execute('SELECT "interview__key","interview_keyden" '
                                  f'FROM "{VQ.T_MEN}"'):
            keyden[k] = txt(kd)
    except Exception:
        pass
    vus = defaultdict(set)
    par_com = Counter()
    for m in tous:
        code = m.get("code_commune")
        if not code:
            continue
        kd = keyden.get(m.get("interview__key"))
        if kd:
            if kd in vus[code]:
                continue
            vus[code].add(kd)
        par_com[int(code)] += 1
    couverture = []
    for code in sorted(set(par_com) | set(attendus),
                       key=lambda c: -par_com.get(c, 0)):
        nb, att = par_com.get(code, 0), attendus.get(code)
        couverture.append({"code": int(code),
                           "nom": noms.get(int(code), str(code)),
                           "rsu": nb, "attendu": att,
                           "taux": _pct(nb, att) if att else None})

    cols_men = [c for c in VQ.COLS_MEN
                if c not in ("interview__key", "interview__id")]
    cols_mem = [c for c in VQ.COLS_MEM if c != "interview__key"]
    blocs = [famille_a(ms, rg, couverture), famille_b(ms),
             famille_c(ms, cols_men, cols_mem), famille_d(ms),
             famille_e(ms), famille_f(ms, n_rejetes)]

    familles, resume = [], Counter()
    for (code, titre, desc), inds in zip(FAMILLES, blocs):
        compte = Counter(i["gravite"] for i in inds)
        for g, k in compte.items():
            resume[g] += k
        coul, icone = STYLE_FAMILLE.get(code, ("#475569", "•"))
        familles.append({"code": code, "titre": titre, "description": desc,
                         "couleur": coul, "icone": icone,
                         "indicateurs": inds,
                         "compte": {"alerte": compte["alerte"],
                                    "vigilance": compte["vigilance"],
                                    "ok": compte["ok"], "nd": compte["nd"],
                                    "total": len(inds)}})
    return {
        "disponible": True,
        "portee": {"menages": len(ms), "membres": sum(len(m.get("membres", ()))
                                                      for m in ms),
                   "communes": len(codes), "rejetes": n_rejetes,
                   "rgph": bool(rg)},
        "resume": {"alerte": resume["alerte"], "vigilance": resume["vigilance"],
                   "ok": resume["ok"], "nd": resume["nd"]},
        "familles": familles,
        "couverture": couverture,
        "graphiques": _graphiques(ms, rg),
    }
