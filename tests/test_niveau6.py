# -*- coding: utf-8 -*-
"""
test_niveau6.py — Preuve que les tests de FRAUDE désignent le bon agent.

Les quatre tests de la section 8 (`vad_qualite.niveau6`) cherchent un agent qui
n'est pas allé sur place. Ce test fabrique une zone dont on connaît la vérité —
des agents honnêtes et, selon le scénario, un fraudeur — puis vérifie deux
choses, aussi importantes l'une que l'autre :

    1. SENSIBILITÉ : le fraudeur est rouge sur les QUATRE tests ;
    2. SPÉCIFICITÉ : les honnêtes ne le sont pas, y compris quand la zone ne
       contient AUCUN fraudeur (c'est là que des seuils mal choisis se voient —
       cf. le palier de vigilance de 8.3, corrigé grâce à ce scénario).

Le fraudeur cumule les quatre signatures : il recopie un même questionnaire
(8.1), invente ses numéros de CIN (8.2), expédie ses entretiens (8.3) et relève
tous ses GPS sans bouger (8.4).

Aucune base de données n'est nécessaire : les ménages sont fabriqués ici, au
format que `vad_qualite.charger` produit. Tirage à graine FIXE, donc résultat
reproductible.

Lancer (depuis la racine du projet) :
    python tests/test_niveau6.py
"""
import os
import random
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RACINE not in sys.path:
    sys.path.insert(0, _RACINE)

import vad_qualite as Q

GRAINE = 20260919
N_MENAGES = 40          # par agent : au-dessus du n_min de chacun des 4 tests
TESTS = ("8.1", "8.2", "8.3", "8.4")

# Modalités valides des variables de logement qui composent le « score H ».
H_CODES = {"H1": (1, 2, 3, 4, 5), "H4": (1, 2, 3, 4, 5, 6, 7),
           "H5": (1, 2, 3, 4, 5, 6), "H6": (1, 2, 3, 4, 6, 7, 8)}


def _menage(cle, agent, ap_n, h_codes, nb, age_chef, duree, gps, cin):
    m = {"key": cle, "agent": agent, "ce": "CE1", "commune": "SYNTHESE",
         "nbmembre": nb, "duree": duree,
         "GPS__Latitude": gps[0], "GPS__Longitude": gps[1]}
    biens = set(random.sample(list(Q.COLS_AP), ap_n))
    for c in Q.COLS_AP:
        m[c] = 1 if c in biens else 0
    m.update(h_codes)
    m["membres"] = [{"M7": 1, "M4": age_chef, "M6a": cin}] + [
        {"M7": 3, "M4": random.randint(1, 30), "M6a": None}
        for _ in range(int(nb) - 1)]
    return m


def honnete(agent, n=N_MENAGES):
    """Un agent qui observe : ménages variés, durées conformes, GPS dispersés."""
    out = []
    for i in range(n):
        nb = random.randint(2, 9)
        h = {v: random.choice(c) for v, c in H_CODES.items()}
        out.append(_menage(
            f"{agent}-{i}", agent, random.randint(3, 20), h, nb,
            random.randint(25, 70),
            10 + 4.5 * nb + random.gauss(0, 4),
            (-21.45 + random.uniform(-0.01, 0.01),
             47.10 + random.uniform(-0.01, 0.01)),
            # Premiers chiffres 1, 2 ou 3 : la signature de CIN de la zone.
            "%d%011d" % (random.choice((1, 1, 1, 2, 2, 3)),
                         random.randint(0, 10 ** 11 - 1))))
    return out


def fraudeur(agent, n=N_MENAGES):
    """Un agent qui n'y est pas allé : il recopie, invente, expédie, ne bouge pas."""
    modele = honnete(agent, 1)[0]
    out = []
    for i in range(n):
        m = dict(modele)
        m["key"] = f"{agent}-{i}"
        m["membres"] = [dict(x) for x in modele["membres"]]
        m["duree"] = (10 + 4.5 * m["nbmembre"]) / 3.5          # 8.3
        m["GPS__Latitude"] = -21.4500 + random.uniform(-2e-5, 2e-5)   # 8.4
        m["GPS__Longitude"] = 47.1000 + random.uniform(-2e-5, 2e-5)
        m["membres"][0]["M6a"] = "%d%011d" % (random.randint(4, 9),   # 8.2
                                              random.randint(0, 10 ** 11 - 1))
        out.append(m)
    return out


def gravites(lots):
    """{agent: {num de test: gravité}} pour une zone donnée."""
    ref = [m for lot in lots.values() for m in lot]
    pairs = list(lots.values())
    out = {}
    for ae, lot in lots.items():
        # La mémorisation de zone est indexée par identité de liste : on la vide
        # entre deux agents, comme le fait `calculer` entre deux communes.
        Q._CACHE_ZONE.clear()
        ech = Q._echelon_agent(ae, lot, ref, pairs)
        out[ae] = {t["num"]: t["gravite"] for t in Q.niveau6(ech)}
    return out


def _montrer(g):
    for ae in sorted(g):
        print("   %-8s " % ae
              + "  ".join("%s:%-9s" % (t, g[ae][t]) for t in TESTS))


def scenario_fraudeur():
    """9 honnêtes + 1 fraudeur : il doit être rouge partout, eux nulle part."""
    random.seed(GRAINE)
    lots = {"AE%d" % i: honnete("AE%d" % i) for i in range(1, 10)}
    lots["FRAUDE"] = fraudeur("FRAUDE")
    g = gravites(lots)
    _montrer(g)
    manques = [t for t in TESTS if g["FRAUDE"][t] != "alerte"]
    faux = [(ae, t) for ae in g if ae != "FRAUDE"
            for t in TESTS if g[ae][t] == "alerte"]
    if manques:
        print("   ECHEC : le fraudeur passe au travers de %s" % ", ".join(manques))
    if faux:
        print("   ECHEC : agent honnete en alerte -> %s" % faux)
    return not manques and not faux


def scenario_sans_fraudeur():
    """Zone entièrement honnête : au plus une alerte, le bruit des seuils.

    Le seuil rouge de 8.3 est celui du document (un résidu standardisé < −3) ;
    il se déclenche par hasard sur ~5 % des agents de 40 entretiens. On tolère
    donc UNE alerte sur neuf agents, pas davantage."""
    random.seed(GRAINE)
    lots = {"AE%d" % i: honnete("AE%d" % i) for i in range(1, 10)}
    g = gravites(lots)
    _montrer(g)
    alertes = [(ae, t) for ae in g for t in TESTS if g[ae][t] == "alerte"]
    if len(alertes) > 1:
        print("   ECHEC : %d alertes sur une zone sans fraudeur -> %s"
              % (len(alertes), alertes))
        return False
    print("   (%d alerte(s) de bruit, tolérance : 1)" % len(alertes))
    return True


def main():
    print("NIVEAU 6 — detection de fraude : %d menages par agent" % N_MENAGES)
    print("\n1. Zone avec un fraudeur (sensibilite) :")
    ok1 = scenario_fraudeur()
    print("\n2. Zone sans fraudeur (specificite) :")
    ok2 = scenario_sans_fraudeur()
    print("\nRESULTAT : " + ("TOUT CONFORME" if ok1 and ok2 else "ECHEC"))
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
