#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
affectation_agents.py
=====================

Équilibrage de la charge d'enquête entre agents, pour la base de préchargement
(voir base_prechargement.py, feuilles « nouveau » / « e_fokontany »).

Deux scénarios d'affectation des ménages à interviewer :

  • « denombrement » (défaut historique) : l'agent qui a DÉNOMBRÉ le ménage
    revient l'interviewer. Aucune redistribution — chaque segment garde son agent.

  • « equilibre » : on redistribue les ménages pour que chaque agent ait ~le même
    nombre de ménages à interviewer, en respectant des règles strictes :
      1. un SEGMENT ne peut avoir qu'UN seul agent (unité indéplaçable) ;
      2. un agent ne change JAMAIS de commune (garanti : dans ces données aucun
         agent n'est à cheval sur deux communes) ;
      3. quand un segment est réaffecté, il va à l'agent SOUS-CHARGÉ le plus
         PROCHE (par centroïde GPS de son secteur de dénombrement) — donc pas
         un fokontany lointain ; les segments d'un agent restent groupés.

    Stratégie « déplacement minimal » : on part de l'affectation d'origine (chaque
    agent sur ses segments) et on ne déplace QUE le strict nécessaire pour réduire
    le déséquilibre, chaque déplacement diminuant l'écart L1 à la cible.

L'équilibrage est fait COMMUNE PAR COMMUNE : la cible de charge d'une commune est
(nb de ménages de la commune) / (nb d'agents de la commune).

Bibliothèque standard uniquement.
"""

from __future__ import annotations

import math
from collections import Counter


# ---------------------------------------------------------------------------
# Géométrie
# ---------------------------------------------------------------------------
def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en km entre deux points WGS84."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _centre_pondere(points):
    """Centroïde (lat, lon) pondéré par le nombre de ménages. None si vide.
    `points` = itérable de (lat, lon, poids)."""
    slat = slon = spds = 0.0
    for lat, lon, pds in points:
        slat += lat * pds
        slon += lon * pds
        spds += pds
    if spds == 0:
        return None
    return (slat / spds, slon / spds)


# ---------------------------------------------------------------------------
# Équilibrage d'une commune
# ---------------------------------------------------------------------------
def _equilibrer_commune(unites, tol_frac: float = 0.10,
                        echanges: bool = False) -> dict:
    """`unites` = liste de dicts {sid, n, lat, lon, agent} (lat/lon = centroïde
    du segment, peut être None). Renvoie {sid: agent_final}.

    Chaque segment (sid) est indivisible. On ne redistribue qu'entre les agents
    déjà présents dans la commune, jamais vers un autre agent/commune.

    `tol_frac` : bande morte autour de la cible (0.10 = on s'arrête à ±10 % ;
    0.0 = on pousse jusqu'à l'optimum L1 atteignable). Plus c'est petit, plus on
    déplace de segments (agents plus souvent hors de leur fokontany d'origine).
    `echanges` : si vrai, phase finale d'ÉCHANGES de segments entre un agent
    sur-chargé et un sous-chargé (troquer un gros segment contre un petit), pour
    resserrer encore l'équilibre là où de simples transferts ne suffisent pas."""
    agents = sorted({u["agent"] for u in unites if u["agent"]})
    proprio = {u["sid"]: u["agent"] for u in unites}
    if len(agents) < 2:
        return proprio                       # rien à équilibrer

    nb = {u["sid"]: u["n"] for u in unites}
    pos = {u["sid"]: (u["lat"], u["lon"]) for u in unites}
    total = sum(u["n"] for u in unites)
    cible = total / len(agents)
    tol = tol_frac * cible                    # bande morte anti-oscillation

    charge = Counter()
    for u in unites:
        charge[u["agent"]] += u["n"]

    # Ancre de chaque agent = centroïde de SES segments d'origine (là où il a
    # dénombré). Sert à mesurer la proximité d'un segment réaffecté.
    pts_commune = [(u["lat"], u["lon"], u["n"]) for u in unites
                   if u["lat"] is not None]
    centre_commune = _centre_pondere(pts_commune)
    ancre = {}
    for a in agents:
        pts = [(u["lat"], u["lon"], u["n"]) for u in unites
               if u["agent"] == a and u["lat"] is not None]
        ancre[a] = _centre_pondere(pts) or centre_commune

    # Nombre de segments détenus par agent (on n'en vide jamais un totalement).
    nb_seg = Counter(proprio.values())

    garde = 0
    while garde < 500_000:
        garde += 1
        surcharge = max(agents, key=lambda a: charge[a])
        if charge[surcharge] <= cible + tol:
            break                             # plus personne au-dessus de la cible
        if nb_seg[surcharge] <= 1:
            # L'agent le plus chargé n'a qu'un segment : on ne peut pas le
            # scinder. On tente le suivant le plus chargé ayant ≥2 segments.
            candidats_surcharge = sorted(
                (a for a in agents if charge[a] > cible + tol and nb_seg[a] > 1),
                key=lambda a: -charge[a])
            if not candidats_surcharge:
                break
            surcharge = candidats_surcharge[0]

        # Meilleur déplacement : un segment de `surcharge` vers un agent
        # sous-chargé, qui (a) réduit l'écart L1 total, (b) va au receveur dont
        # l'ancre est la plus proche du segment.
        meilleur = None
        for sid, a in proprio.items():
            if a != surcharge:
                continue
            n_sid = nb[sid]
            slat, slon = pos[sid]
            for rec in agents:
                if rec == surcharge or charge[rec] >= cible - tol:
                    continue
                avant = abs(charge[surcharge] - cible) + abs(charge[rec] - cible)
                apres = (abs(charge[surcharge] - n_sid - cible)
                         + abs(charge[rec] + n_sid - cible))
                if apres >= avant:
                    continue                  # doit améliorer l'équilibre
                if slat is None or ancre[rec] is None:
                    d = float("inf")
                else:
                    d = _haversine(slat, slon, ancre[rec][0], ancre[rec][1])
                cle = (d, str(sid), str(rec))
                if meilleur is None or cle < meilleur[0]:
                    meilleur = (cle, sid, rec)
        if meilleur is None:
            break

        _, sid, rec = meilleur
        proprio[sid] = rec
        charge[surcharge] -= nb[sid]
        charge[rec] += nb[sid]
        nb_seg[surcharge] -= 1
        nb_seg[rec] += 1

    # --- Phase d'échanges (mode « équilibrage fort ») ----------------------
    # Là où les transferts simples ne suffisent plus (indivisibilité des
    # segments), on TROQUE un gros segment d'un agent sur-chargé contre un plus
    # petit d'un agent sous-chargé : les deux se rapprochent de la cible. Échange
    # 1 pour 1 → nul agent n'est vidé. L'agent change alors de fokontany : c'est
    # justement ce que ce mode autorise pour améliorer l'équilibre.
    if echanges:
        seg_of: dict = {}
        for sid, a in proprio.items():
            seg_of.setdefault(a, []).append(sid)
        garde = 0
        while garde < 100_000:
            garde += 1
            surs = [a for a in agents if charge[a] > cible + 1e-9]
            sous = [a for a in agents if charge[a] < cible - 1e-9]
            meilleur_ech = None                 # (gain, A, B, sa, sb)
            for a_sur in surs:
                for a_sous in sous:
                    for sa in seg_of[a_sur]:
                        na = nb[sa]
                        for sb in seg_of[a_sous]:
                            nbb = nb[sb]
                            if na <= nbb:
                                continue        # a_sur doit céder un + gros segment
                            avant = (abs(charge[a_sur] - cible)
                                     + abs(charge[a_sous] - cible))
                            apres = (abs(charge[a_sur] - na + nbb - cible)
                                     + abs(charge[a_sous] - nbb + na - cible))
                            gain = avant - apres
                            if gain > 1e-9 and (meilleur_ech is None
                                                or gain > meilleur_ech[0]):
                                meilleur_ech = (gain, a_sur, a_sous, sa, sb)
            if meilleur_ech is None:
                break
            _, a_sur, a_sous, sa, sb = meilleur_ech
            proprio[sa] = a_sous
            proprio[sb] = a_sur
            charge[a_sur] += nb[sb] - nb[sa]
            charge[a_sous] += nb[sa] - nb[sb]
            seg_of[a_sur].remove(sa)
            seg_of[a_sur].append(sb)
            seg_of[a_sous].remove(sb)
            seg_of[a_sous].append(sa)

    return proprio


# ---------------------------------------------------------------------------
# Point d'entrée : équilibrage global (toutes communes)
# ---------------------------------------------------------------------------
def equilibrer_charge(unites, log=None, tol_frac: float = 0.10,
                      echanges: bool = False) -> dict:
    """`unites` = liste de dicts {sid, commune, n, lat, lon, agent}.
    Renvoie {sid: agent_final}. Traite chaque commune indépendamment.

    `tol_frac` / `echanges` : voir _equilibrer_commune. Mode « équilibrage »
    standard = (0.10, False) ; mode « équilibrage fort » = (0.0, True)."""
    par_commune = {}
    for u in unites:
        par_commune.setdefault(u["commune"], []).append(u)

    affectation = {}
    for commune, lot in par_commune.items():
        res = _equilibrer_commune(lot, tol_frac=tol_frac, echanges=echanges)
        affectation.update(res)
        if log:
            deplaces = sum(1 for u in lot if res[u["sid"]] != u["agent"])
            log(f"   Commune {commune} : {len(lot)} segments, "
                f"{len({u['agent'] for u in lot})} agents, "
                f"{deplaces} segment(s) redistribué(s)")
    return affectation
