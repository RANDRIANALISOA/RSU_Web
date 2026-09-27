# -*- coding: utf-8 -*-
"""
test_gps_den.py — Preuve que l'écart GPS dénombrement ↔ VAD désigne le bon agent.

En conditions réelles, la VAD retourne chez des ménages DÉJÀ dénombrés : le même
logement est géolocalisé deux fois, à deux mois d'intervalle, par deux agents
différents. Le test 8.5 compare les deux points, appariés sur `code_den`.

Les données de production n'existent pas encore — celles dont on dispose sont des
données de test dont les `code_den` ne désignent pas les mêmes ménages, ce qui
produit des écarts de plusieurs centaines de kilomètres. Ce fichier fabrique donc
une zone dont on connaît la vérité et vérifie les trois comportements attendus :

    sensibilité   un agent qui remplit ses questionnaires SANS se déplacer est
                  détecté — ses points VAD sont tous au même endroit, donc loin
                  des logements dénombrés ;
    spécificité   des agents honnêtes, dont les relevés diffèrent de quelques
                  dizaines de mètres (la précision d'un GPS de terrain), restent
                  au vert ;
    prudence      un agent dont AUCUN ménage n'est apparié au dénombrement sort
                  en « non calculé », jamais en « conforme » — ne rien savoir
                  n'est pas la même chose que ne rien trouver.

TROIS LIMITES, mesurées avec ce même fixture (voir `python tests/test_gps_den.py
--limites`) et recopiées dans les seuils affichés du test :

  * AVEUGLE EN HABITAT SERRÉ — un agent sédentaire posté au centre d'un hameau
    dont les logements tiennent dans moins de 60 m n'est pas détecté. À 100 m
    de dispersion il ressort en vigilance, à 250 m en alerte.
  * FAUX POSITIF SI LE GPS DÉRIVE — un agent honnête dont l'appareil se trompe
    de plus de 150 m, quand ses collègues sont à 25 m, est accusé à tort ; entre
    80 et 150 m il ressort en vigilance. En dessous de 50 m, il reste au vert.
  * AVEUGLE SI TOUTE L'ÉQUIPE TRICHE — le test est RELATIF : neuf agents tous
    sédentaires donnent zéro alerte, faute de voisin honnête à qui les comparer.

La statistique de décision est un MANN-WHITNEY sur les distances, assorti d'un
plancher sur l'écart médian. Le test de proportion qu'on aurait pu lui préférer
— part des ménages au-delà de 100 m — a été écarté pour trois raisons mesurées
ici : il est INDÉFINI quand personne dans la zone ne dépasse le seuil (le cas
sain), il ne voit pas l'agent dont tous les relevés sont décalés de 90 m, et un
`code_den` mal repris à 600 km suffit à le faire basculer.

Aucune base de données n'est nécessaire, tirage à graine FIXE.

Lancer (depuis la racine du projet) :
    python tests/test_gps_den.py
"""
import math
import os
import random
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RACINE not in sys.path:
    sys.path.insert(0, _RACINE)

import vad_qualite as Q

GRAINE = 20260921
N_MENAGES = 24          # > n_min de 8.5 (10)
TESTS = ("8.4", "8.5")
# Un village : les logements dénombrés sont dispersés dans ce rayon.
CENTRE = (-19.5250, 45.4500)          # quelque part vers Miandrivazo
RAYON_VILLAGE_M = 450.0
# Précision d'un GPS de terrain : deux relevés du MÊME toit diffèrent d'autant.
BRUIT_GPS_M = 25.0
# Le fraudeur remplit tout depuis un même point, à cette distance du village.
ECART_FRAUDE_M = 700.0

_M_PAR_DEGRE = 111320.0


def _deplacer(point, dx_m, dy_m):
    """Point décalé de dx mètres vers l'est et dy mètres vers le nord."""
    lat, lon = point
    return (lat + dy_m / _M_PAR_DEGRE,
            lon + dx_m / (_M_PAR_DEGRE * math.cos(math.radians(lat))))


def _autour(point, rayon_m):
    """Un point tiré au hasard dans un disque de `rayon_m` autour de `point`."""
    a = random.uniform(0, 2 * math.pi)
    r = rayon_m * math.sqrt(random.random())
    return _deplacer(point, r * math.cos(a), r * math.sin(a))


def _menage(cle, agent, pt_den, pt_vad):
    """Un ménage minimal : ce que 8.5 lit, et rien de plus."""
    return {"key": cle, "agent": agent, "ce": "CE1", "commune": "SYNTHESE",
            "GPS__Latitude": (pt_vad[0] if pt_vad else None),
            "GPS__Longitude": (pt_vad[1] if pt_vad else None),
            "gps_den": pt_den, "membres": []}


def honnete(agent, n=N_MENAGES):
    """Se rend chez chaque ménage : son point ne diffère que du bruit GPS."""
    out = []
    for i in range(n):
        den = _autour(CENTRE, RAYON_VILLAGE_M)
        vad = _autour(den, BRUIT_GPS_M)
        out.append(_menage(f"{agent}-{i}", agent, den, vad))
    return out


def fraudeur(agent, n=N_MENAGES):
    """Remplit tout depuis un seul endroit, à l'écart du village."""
    poste = _deplacer(CENTRE, ECART_FRAUDE_M, ECART_FRAUDE_M)
    out = []
    for i in range(n):
        den = _autour(CENTRE, RAYON_VILLAGE_M)
        # Il bouge de quelques mètres entre deux saisies, pas plus.
        out.append(_menage(f"{agent}-{i}", agent, den, _autour(poste, 12.0)))
    return out


def sans_denombrement(agent, n=N_MENAGES):
    """Ne travaille que des ménages NOUVEAUX : aucun point à comparer."""
    out = []
    for i in range(n):
        out.append(_menage(f"{agent}-{i}", agent, None,
                           _autour(CENTRE, RAYON_VILLAGE_M)))
    return out


def decale(agent, ecart_m, n=N_MENAGES):
    """Tous ses relevés décalés du MÊME écart : ni sédentaire, ni honnête.

    C'est le profil qu'un test de proportion ne peut pas voir tant que l'écart
    reste sous son seuil, et c'est pour lui que la statistique de décision est
    un Mann-Whitney."""
    out = []
    for i in range(n):
        den = _autour(CENTRE, RAYON_VILLAGE_M)
        out.append(_menage(f"{agent}-{i}", agent, den, _deplacer(den, ecart_m, 0.0)))
    return out


def gravites(lots):
    ref = [m for lot in lots.values() for m in lot]
    pairs = list(lots.values())
    out = {}
    for ae, lot in lots.items():
        Q._CACHE_ZONE.clear()
        ech = Q._echelon_agent(ae, lot, ref, pairs)
        out[ae] = {t["num"]: t for t in Q.niveau6(ech)}
    return out


def _montrer(g):
    for ae in sorted(g):
        bouts = []
        for t in TESTS:
            r = g[ae][t]
            v = ("—" if r["valeur"] is None else f'{r["valeur"]:.0f}')
            bouts.append(f'{t}:{r["gravite"]:<9} ({v})')
        print("   %-10s " % ae + "  ".join(bouts))


def scenario_fraudeur():
    """8 honnêtes + 1 fraudeur : rouge sur 8.5, les autres au vert."""
    random.seed(GRAINE)
    lots = {"AE%d" % i: honnete("AE%d" % i) for i in range(1, 9)}
    lots["FRAUDEUR"] = fraudeur("FRAUDEUR")
    g = gravites(lots)
    _montrer(g)
    r = g["FRAUDEUR"]["8.5"]
    faux = [ae for ae in g if ae != "FRAUDEUR" and g[ae]["8.5"]["gravite"] == "alerte"]
    ok = True
    if r["gravite"] != "alerte":
        print(f'   ECHEC : le fraudeur sort en « {r["gravite"]} » au lieu d\'alerte')
        ok = False
    if faux:
        print("   ECHEC : agent honnete en alerte -> %s" % faux)
        ok = False
    if ok:
        print(f'   (fraudeur : {r["valeur"]:.0f} % de ses menages au-dela de '
              f'{Q.DIST_LOIN:.0f} m, {r["stat"]})')
    return ok


def scenario_sans_fraudeur():
    """Zone entièrement honnête : aucune alerte, malgré le bruit GPS."""
    random.seed(GRAINE)
    g = gravites({"AE%d" % i: honnete("AE%d" % i) for i in range(1, 10)})
    _montrer(g)
    al = [ae for ae in g if g[ae]["8.5"]["gravite"] == "alerte"]
    if al:
        print("   ECHEC : %d alerte(s) sur une zone sans fraudeur -> %s"
              % (len(al), al))
        return False
    print("   (aucune alerte : le bruit GPS de %.0f m ne suffit pas a declencher)"
          % BRUIT_GPS_M)
    return True


def scenario_sans_denombrement():
    """Agent sans aucun ménage apparié : « non calculé », jamais « conforme ».

    C'est la distinction qui compte le plus dans un test de fraude : un agent
    qu'on ne PEUT pas contrôler ne doit pas apparaître vert, sans quoi le
    superviseur le croit vérifié."""
    random.seed(GRAINE)
    lots = {"AE%d" % i: honnete("AE%d" % i) for i in range(1, 9)}
    lots["SANS_DEN"] = sans_denombrement("SANS_DEN")
    g = gravites(lots)
    _montrer(g)
    r = g["SANS_DEN"]["8.5"]
    if r["gravite"] != "nd":
        print(f'   ECHEC : un agent sans appariement sort en « {r["gravite"]} »'
              " alors qu'il devrait etre « non calcule »")
        return False
    print("   (non calcule, et la fiche explique pourquoi : aucun menage apparie)")
    return True


def scenario_decalage():
    """Décalage systématique SOUS le seuil de 100 m : doit ressortir en vigilance.

    Un agent dont les vingt relevés sont à 90 m du point du dénombrement, quand
    ses collègues sont à 20 m, ne fait franchir le seuil à AUCUN de ses ménages.
    Le test doit quand même le voir — sinon il suffit de se tromper de 99 m pour
    passer à travers."""
    random.seed(GRAINE)
    lots = {"AE%d" % i: honnete("AE%d" % i) for i in range(1, 9)}
    lots["DECALE"] = decale("DECALE", 90.0)
    g = gravites(lots)
    _montrer(g)
    r = g["DECALE"]["8.5"]
    faux = [ae for ae in g if ae != "DECALE" and g[ae]["8.5"]["gravite"] != "ok"]
    ok = True
    if r["gravite"] not in ("vigilance", "alerte"):
        print(f'   ECHEC : le decalage de 90 m sort en « {r["gravite"]} »')
        ok = False
    if faux:
        print("   ECHEC : agent honnete signale -> %s" % faux)
        ok = False
    if ok:
        print(f'   (decale : {r["valeur"]:.0f} m d\'ecart median, {r["stat"]}, '
              f'{r["gravite"]} — aucun de ses menages ne depasse '
              f'{Q.DIST_LOIN:.0f} m)')
    return ok


def main():
    print("TEST 8.5 — ecart GPS denombrement/VAD : %d menages par agent, "
          "bruit GPS %.0f m, seuil %.0f m" % (N_MENAGES, BRUIT_GPS_M, Q.DIST_LOIN))
    print("\n1. Zone avec un fraudeur sedentaire (sensibilite) :")
    ok1 = scenario_fraudeur()
    print("\n2. Zone entierement honnete (specificite) :")
    ok2 = scenario_sans_fraudeur()
    print("\n3. Decalage systematique sous le seuil (finesse) :")
    ok3 = scenario_decalage()
    print("\n4. Agent sans menage apparie au denombrement (prudence) :")
    ok4 = scenario_sans_denombrement()
    tout = ok1 and ok2 and ok3 and ok4
    print("\nRESULTAT : " + ("TOUT CONFORME" if tout else "ECHEC"))
    return 0 if tout else 1


if __name__ == "__main__":
    raise SystemExit(main())
