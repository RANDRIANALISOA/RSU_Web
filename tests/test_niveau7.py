# -*- coding: utf-8 -*-
"""
test_niveau7.py — Preuve que les tests de NON-RÉPONSE désignent le bon agent.

Les cinq tests de la section 9 (`vad_qualite.niveau7`) ne jugent pas ce qui a
été répondu mais ce qui ne l'a pas été. Ce test fabrique une zone dont on
connaît la vérité, puis vérifie sensibilité ET spécificité — comme
`test_niveau6.py`, et pour la même raison : un seuil trop lâche se voit
uniquement sur une zone SANS fautif.

DEUX fautifs, parce que ce sont deux fraudes différentes.

Le FAUTIF cumule les signatures de non-réponse :

    9.1   ses manquants ne sont pas aléatoires — il saute le module logement
          précisément chez les ménages NOMBREUX, ceux qui prennent du temps ;
    9.2.1 il laisse vides les modules longs (année de fin d'études, activité)
          bien plus souvent que ses collègues ;
    9.3   il inscrit deux personnes de moins que l'attendu préchargé.

Le ROGNEUR, lui, répond à tout — il raccourcit le ROSTER :

    9.4   il déclare « plus membre du ménage » une large part des personnes
          que le registre attendait, ce qui les sort du questionnaire ;
    9.5   il saisit systématiquement moins de personnes que la taille qu'il
          a lui-même annoncée.

Le scénario du rogneur vérifie AUSSI que **9.3 reste vert** sur lui. Ce n'est
pas une tolérance, c'est la raison d'être de 9.4 : 9.3 compare `nbmembre` —
les LIGNES du roster, membres sortis compris — à l'attendu, et ne peut donc
rien voir d'un rognage. Si ce jour arrive où 9.3 se met au rouge ici, c'est
que sa définition a changé et qu'il faut relire 9.4.

Aucune base de données n'est nécessaire, tirage à graine FIXE.

Lancer (depuis la racine du projet) :
    python tests/test_niveau7.py
"""
import os
import random
import sys

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RACINE not in sys.path:
    sys.path.insert(0, _RACINE)

import vad_qualite as Q

GRAINE = 20260919
N_MENAGES = 30          # > n_min de 9.1 et 9.2.1 (20), de 9.3 (10), de 9.5 (20)
TESTS = ("9.1", "9.2.1", "9.3", "9.4", "9.5")
# Part des membres PRÉSENTS qui étaient préchargés (les autres sont de
# nouveaux membres). Elle fixe le dénominateur de 9.4 : trop basse, aucun
# agent n'atteindrait les 30 préchargés qu'exige le test.
PART_PRECHARGES = 0.6
MOTIF_DEMENAGEMENT = 2  # le motif de sortie le plus courant dans la vraie base
# Bruit toléré sur une zone SANS fautif : 9 agents × 5 tests = 45 cellules, et
# plusieurs tests travaillent à 5 %. Une alerte isolée reste du hasard ; deux
# signeraient un seuil trop lâche.
TOLERANCE_BRUIT = 1

H_CODES = {"H1": (1, 2, 3, 4, 5), "H4": (1, 2, 3, 4, 5, 6, 7),
           "H5": (1, 2, 3, 4, 5, 6), "H6": (1, 2, 3, 4, 6, 7, 8),
           "H7": (1, 2, 3), "H8": (1, 2, 3), "H9": (1, 2, 3), "H10": (1, 2, 3)}


def _membre(age, saute_long, valid=2, motif=None):
    """Un membre du ménage ; `saute_long` vide les modules qui prennent du temps.

    `valid` reprend `membre_valid` du questionnaire : 1 = préchargé confirmé,
    2 = nouveau membre, 3 = déclaré SORTI du ménage. C'est la seule variable
    qui porte un rognage de roster, donc le seul support de 9.4."""
    x = {"M3": random.choice((1, 2)), "M4": age, "M7": 3, "M2a": min(age, 10),
         "M13": random.choice((1, 2)), "M16a": 1, "M6a": None,
         "membre_valid": valid, "nomembre_motif": motif,
         "AUEM17a": 2 if age > Q.AGE_INCAPACITE else None}
    x["M15a"] = None if (saute_long or x["M13"] == Q.M13_JAMAIS) else 2015
    x["M19"] = None if (saute_long or age <= Q.AGE_EMPLOI) else 11
    return x


def _pre():
    """Ce membre présent était-il préchargé (`membre_valid` = 1) ou nouveau (2) ?"""
    return 1 if random.random() < PART_PRECHARGES else 2


def _menage(cle, agent, nb, attendu, saute_h, saute_long, retires=0):
    """Un ménage : `nb` personnes PRÉSENTES et `retires` déclarées sorties.

    ⚠️ `nbmembre` compte les LIGNES du roster — sorties comprises —, comme dans
    les données réelles du RSU. C'est exactement ce qui rend 9.3 aveugle au
    rognage, et le
    fixture doit reproduire ce piège plutôt que le corriger."""
    m = {"key": cle, "agent": agent, "ce": "CE1", "commune": "SYNTHESE",
         "nbmembre": nb + retires, "taille_men": attendu, "Perm_rsu": 1,
         "H2": None if saute_h else random.randint(1, 5)}
    for v, codes in H_CODES.items():
        m[v] = None if saute_h else random.choice(codes)
    for c in Q.COLS_AP:
        m[c] = random.choice((0, 1))
    m["membres"] = [{"M7": 1, "M4": random.randint(25, 70), "M3": 1, "M2a": 10,
                     "M13": 1, "M16a": 1, "M15a": 2000, "M19": 11,
                     "M6a": None, "AUEM17a": 2,
                     "membre_valid": _pre(), "nomembre_motif": None}]
    m["membres"] += [_membre(random.randint(1, 60), saute_long, valid=_pre())
                     for _ in range(int(nb) - 1)]
    m["membres"] += [_membre(random.randint(1, 60), saute_long,
                             valid=Q.MEMBRE_RETIRE, motif=MOTIF_DEMENAGEMENT)
                     for _ in range(int(retires))]
    return m


def honnete(agent, n=N_MENAGES):
    """Manquants rares et SANS rapport avec le ménage ; roster quasi complet.

    `attendu` est la taille relevée au dénombrement ; l'agent honnête retrouve
    tout le monde, à un absent près de temps en temps. L'écart n'est PAS
    constant : sinon `nbmembre` et `taille_men` seraient parfaitement
    colinéaires et la covariance du test de Little ne serait pas inversible."""
    out = []
    for i in range(n):
        attendu = random.randint(2, 9)
        nb = attendu - (1 if random.random() < 0.10 else 0)
        # Une sortie de ménage de temps en temps : les gens déménagent et se
        # marient pour de bon. Un agent honnête n'en est pas exempt, sinon
        # 9.4 se déclencherait au premier retrait légitime.
        out.append(_menage(f"{agent}-{i}", agent, max(1, nb), attendu,
                           saute_h=(random.random() < 0.10),   # aléatoire = MCAR
                           saute_long=False,
                           retires=(1 if random.random() < 0.30 else 0)))
    return out


def fautif(agent, n=N_MENAGES):
    """Saute le logement chez les GROS ménages, vide les modules longs, écourte."""
    out = []
    for i in range(n):
        attendu = random.randint(4, 11)
        nb = max(1, attendu - random.choice((1, 2, 3)))            # 9.3
        out.append(_menage(f"{agent}-{i}", agent, nb, attendu,
                           saute_h=(attendu >= 8),                 # 9.1
                           saute_long=(random.random() < 0.85),    # 9.2.1
                           retires=(1 if random.random() < 0.30 else 0)))
    return out


def rogneur(agent, n=N_MENAGES):
    """Répond à tout, mais raccourcit le roster : il sort les gens du ménage.

    Deux signatures, et une troisième qui doit rester MUETTE :
      9.4  il déclare sortis deux à quatre préchargés par ménage, là où ses
           collègues en déclarent un de temps en temps ;
      9.5  il saisit une à trois personnes de moins que la taille qu'il a
           lui-même annoncée ;
      9.3  reste vert, parce que `nbmembre` compte les lignes du roster,
           sorties comprises — c'est le trou que 9.4 vient boucher."""
    out = []
    for i in range(n):
        attendu = random.randint(5, 11)
        nb = max(1, attendu - random.choice((1, 2, 3)))            # 9.5
        out.append(_menage(f"{agent}-{i}", agent, nb, attendu,
                           saute_h=(random.random() < 0.10),       # comme un honnête
                           saute_long=False,
                           retires=random.choice((2, 3, 4))))      # 9.4
    return out


def gravites(lots):
    ref = [m for lot in lots.values() for m in lot]
    pairs = list(lots.values())
    out = {}
    for ae, lot in lots.items():
        Q._CACHE_ZONE.clear()
        ech = Q._echelon_agent(ae, lot, ref, pairs)
        out[ae] = {t["num"]: t["gravite"] for t in Q.niveau7(ech)}
    return out


def _montrer(g):
    for ae in sorted(g):
        print("   %-8s " % ae
              + "  ".join("%s:%-9s" % (t, g[ae][t]) for t in TESTS))


def _sensibilite(coupable, fabrique, vises, muets=()):
    """9 honnêtes + 1 coupable. Il doit être rouge sur `vises`, vert sur `muets`.

    Le bruit chez les honnêtes est toléré au même niveau que dans le scénario
    de spécificité, et pour la même raison : 9.1 et 9.2.1 travaillent à 5 %,
    donc une fausse alerte sur neuf agents est le comportement ATTENDU d'un
    test de niveau 5 %. Exiger zéro reviendrait à tester la chance du tirage
    plutôt que les seuils."""
    random.seed(GRAINE)
    lots = {"AE%d" % i: honnete("AE%d" % i) for i in range(1, 10)}
    lots[coupable] = fabrique(coupable)
    g = gravites(lots)
    _montrer(g)
    manques = [t for t in vises if g[coupable][t] != "alerte"]
    parle = [t for t in muets if g[coupable][t] == "alerte"]
    faux = [(ae, t) for ae in g if ae != coupable
            for t in TESTS if g[ae][t] == "alerte"]
    if manques:
        print("   ECHEC : %s passe au travers de %s"
              % (coupable, ", ".join(manques)))
    if parle:
        print("   ECHEC : %s s'est declenche sur %s alors qu'il doit rester"
              " aveugle a cette fraude — sa definition a change"
              % (", ".join(parle), coupable))
    if len(faux) > TOLERANCE_BRUIT:
        print("   ECHEC : %d alerte(s) chez les honnetes (tolerance %d) -> %s"
              % (len(faux), TOLERANCE_BRUIT, faux))
    else:
        print("   (%d alerte(s) de bruit chez les honnetes, tolerance : %d)"
              % (len(faux), TOLERANCE_BRUIT))
    return not manques and not parle and len(faux) <= TOLERANCE_BRUIT


def scenario_fautif():
    """Le fautif de NON-RÉPONSE : rouge sur 9.1, 9.2.1 et 9.3.

    Il déclenche aussi 9.5 — il écourte ses rosters, c'est cohérent — mais on
    ne l'exige pas : ce n'est pas la fraude qu'il incarne."""
    return _sensibilite("FAUTIF", fautif, ("9.1", "9.2.1", "9.3"))


def scenario_rogneur():
    """Le ROGNEUR : rouge sur 9.4 et 9.5, et 9.3 doit rester VERT.

    Ce dernier point est l'objet même du scénario. 9.3 compare `nbmembre` — les
    lignes du roster, personnes sorties comprises — à l'attendu : un rognage ne
    l'émeut pas. 9.4 n'existe que pour ça. Si 9.3 se met au rouge ici, c'est
    que sa définition a bougé, et il faut relire 9.4 avant de le garder."""
    return _sensibilite("ROGNEUR", rogneur, ("9.4", "9.5"), muets=("9.3",))


def scenario_sans_fautif():
    """Zone entièrement honnête : au plus une alerte (bruit des seuils à 5 %)."""
    random.seed(GRAINE)
    g = gravites({"AE%d" % i: honnete("AE%d" % i) for i in range(1, 10)})
    _montrer(g)
    alertes = [(ae, t) for ae in g for t in TESTS if g[ae][t] == "alerte"]
    if len(alertes) > TOLERANCE_BRUIT:
        print("   ECHEC : %d alertes sur une zone sans fautif -> %s"
              % (len(alertes), alertes))
        return False
    print("   (%d alerte(s) de bruit, tolérance : %d)"
          % (len(alertes), TOLERANCE_BRUIT))
    return True


def main():
    print("NIVEAU 7 — non-reponse et completude : %d menages par agent" % N_MENAGES)
    print("\n1. Zone avec un fautif de NON-REPONSE (sensibilite) :")
    ok1 = scenario_fautif()
    print("\n2. Zone avec un ROGNEUR de roster (sensibilite) :")
    ok2 = scenario_rogneur()
    print("\n3. Zone sans fautif (specificite) :")
    ok3 = scenario_sans_fautif()
    tout = ok1 and ok2 and ok3
    print("\nRESULTAT : " + ("TOUT CONFORME" if tout else "ECHEC"))
    return 0 if tout else 1


if __name__ == "__main__":
    raise SystemExit(main())
