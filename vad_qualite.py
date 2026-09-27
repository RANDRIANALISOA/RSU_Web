# -*- coding: utf-8 -*-
"""vad_qualite.py — Tests de qualité des données collectées par les agents.

Transcription de : « RSU — Tests statistiques et indicateurs de contrôle de la
cohérence et de la fiabilité des données collectées par les agents enquêteurs »
(documentation technique v1.0, août 2026), livrée niveau par niveau. Les SEPT
niveaux sont en place ; seul le chapitre 10 reste à écrire.

    Niveau 1  suivi terrain par agent          (section 3)   ← livré
    Niveau 2  cohérence démographique          (section 4)   ← livré
    Niveau 3  cohérence « cycle de vie »       (section 5)   ← livré
    Niveau 4  logement H1–H10                  (section 6)   ← livré
    Niveau 5  biens AP1–AP4                    (section 7)   ← livré
    Niveau 6  fraude et duplication            (section 8)   ← livré
    Niveau 7  non-réponse et complétude        (section 9)   ← livré
    Score composite de risque                  (section 10)  à faire

Ajouter un niveau = une fonction, une ligne dans `NIVEAUX`. La matrice CE × AE,
la fiche détaillée et l'en-tête groupé de la page s'adaptent d'eux-mêmes.

⚠️ EFFECTIFS. Chaque test déclare l'effectif minimal sous lequel son résultat
n'a pas de sens (`n_min`). En dessous, il rend `None` avec la mention
« effectif insuffisant » plutôt qu'un nombre : sur les données du pilote,
un agent a 1 à 13 ménages là où ces tests en supposent des dizaines. Les tests s'activent
d'eux-mêmes dès que les volumes de production sont atteints.

Aucune dépendance à scipy : les lois utilisées (normale, χ², t) sont approchées
ici avec une précision largement suffisante pour des seuils d'alerte.
"""

import math
from collections import defaultdict

# --------------------------------------------------------------------------
# Quels tests tourner, et sous quels seuils
# --------------------------------------------------------------------------
# Trois listes, un seul endroit. Mesuré sur les données RSU d'octobre 2025
# (15 190 ménages, 248 agents, district de Miandrivazo).
#
# SANS SUPPORT : la variable n'existe pas dans cette version du questionnaire,
# ou le test demande un effectif hors de portée d'un agent. Ils renvoyaient
# « non calculé » pour 100 % des agents. On ne les calcule plus du tout.
TESTS_SANS_SUPPORT = {
    "3.6",    # la modalité « Tsy mahalala » n'existe dans AUCUN libellé
    "4.3",    # indice ONU : demande 800 individus, l'agent médian en a 280
    "5.1.8",  # pas de variable « année de fin d'études » (M15 est un oui/non)
}
# HORS MATRICE : calculés et visibles dans la FICHE de l'agent, mais retirés du
# tableau que lit le superviseur. Deux motifs, et un seul objectif — qu'une
# case rouge veuille dire quelque chose.
TESTS_HORS_MATRICE = {
    # (a) Déjà garantis à la saisie par Survey Solutions : sur 15 190 ménages,
    #     15 portent une erreur de validation et huit de ces règles n'ont
    #     AUCUNE violation. Une colonne verte pour tout le monde n'informe pas,
    #     elle dilue. Le score composite 5.2 continue de les agréger toutes.
    "3.4", "3.5", "4.8.2",
    "5.1.1", "5.1.2", "5.1.4", "5.1.5", "5.1.7", "5.1.9", "5.1.10", "5.1.11",
    # (b) Redondants avec un test conservé, sur les mêmes agents :
    "4.1",   # Whipple  ~ 4.4 ~ 4.2 (phi = 0,42) : on garde Myers, qui utilise
    "4.4",   #   les dix chiffres terminaux et non les seuls 0 et 5
    "6.1",   # chi2 logement ~ 6.3 Bray-Curtis (phi = 0,69) : on garde la
             #   distance, lisible de 0 à 1 et explicable à un agent
    "7.3",   # ACP richesse ~ 7.4 biais global (phi = 0,60) : on garde 7.4,
             #   qui vise le remplissage en bloc plutôt que le niveau de vie
}
# SEUILS RECALIBRÉS. ⚠️ Ceux de la documentation technique RSU ont été écrits
# pour des comparaisons de ZONE ; appliqués à un agent, ils désignaient 43 % à
# 75 % des agents selon le test — un tableau presque entièrement rouge ne
# hiérarchise rien et décrédibilise l'alerte auprès de l'agent qui la reçoit.
# Les valeurs ci-dessous sont calées sur la distribution OBSERVÉE des agents,
# de façon qu'un test désigne l'ordre de 5 à 10 % d'entre eux. Ce sont des
# choix d'exploitation, à faire arbitrer par les statisticiens du RSU : les
# modifier ici change les couleurs, jamais la statistique calculée.
CAL = {
    "4.7.al":   2.58,   "4.7.vg":   1.96,    # |Z| du rapport de masculinité
    "4.8.1.al": 0.001,  "4.8.1.vg": 0.01,    # p du chi2 M7 (était 0,05 / 0,10)
    "6.3.al":   0.95,   "6.3.vg":   0.85,    # Bray-Curtis (était 0,50 / 0,35)
    "6.4.1.al": 8,      "6.4.1.vg": 5,       # pièces : plancher d'invraisemblance
    "6.4.2.al": 5.00,   "6.4.2.vg": 3.50,    # Z de concentration (était 2,58/1,96)
    "7.2.al":   0.07,   "7.2.vg":   0.03,    # delta-alpha (était 0,030 / 0,015)
    "7.4.al":   3.70,   "7.4.vg":   2.90,    # biais global (était 2,0 / 1,5)
    "8.1.al":   2.58,   "8.1.vg":   1.96,    # Z des paires serrées (était 2,58/1,96)
    "8.1.part":  5.0,   "8.1.partvg":  3.0,  # ET part minimale de quasi-doublons
    "8.2.al":   0.001,  "8.2.vg":   0.01,    # p de Benford (était 0,05 / 0,10)
    "8.4.al":   95.0,   "8.4.vg":   80.0,    # % d'adresses agglutinées (était 20/10)
    "9.4.al":   2.58,   "9.4.vg":   1.96,    # Z de l'excès de retraits de membres
    "9.4.part": 25.0,   "9.4.partvg": 15.0,  # ET part minimale de préchargés retirés
    "9.5.al":  -0.50,   "9.5.vg":  -0.25,    # écart moyen roster − taille déclarée
    "8.5.al":   2.58,   "8.5.vg":   1.96,    # Z de Mann-Whitney sur les distances
    "8.5.med": 100.0,   "8.5.medvg": 50.0,   # ET distance médiane minimale, en m
    "9.5.part": 25.0,   "9.5.partvg": 15.0,  # ET part minimale de rosters trop courts
}

# --------------------------------------------------------------------------
# Lois de probabilité (scipy n'est pas dans le venv du projet)
# --------------------------------------------------------------------------
def phi(z):
    """Fonction de répartition de la loi normale centrée réduite."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def p_bilateral(z):
    """p-value bilatérale d'un score Z."""
    return 2.0 * (1.0 - phi(abs(z)))


def chi2_sf(x, k):
    """P(X > x) pour un χ² à k degrés de liberté.

    Série de Gamma incomplète régularisée ; exacte à ~1e-10 pour les valeurs
    rencontrées ici (k ≤ 100)."""
    if x <= 0 or k <= 0:
        return 1.0
    a, xx = k / 2.0, x / 2.0
    if xx < a + 1.0:                                  # développement en série
        terme = 1.0 / a
        somme = terme
        n = a
        for _ in range(500):
            n += 1.0
            terme *= xx / n
            somme += terme
            if terme < somme * 1e-14:
                break
        return 1.0 - somme * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
    # fraction continue (Lentz) pour la borne supérieure
    tiny = 1e-300
    b = xx + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h * math.exp(-xx + a * math.log(xx) - math.lgamma(a))


# --------------------------------------------------------------------------
# Statistiques descriptives
# --------------------------------------------------------------------------
def _betacf(a, b, x):
    """Fraction continue de la bêta incomplète (Lentz)."""
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((a + m2 - 1) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def betainc_reg(a, b, x):
    """Fonction bêta incomplète régularisée I_x(a, b).

    Même esprit que `chi2_sf` : le venv du projet n'a pas scipy, et la
    précision obtenue (~1e-12) dépasse de loin ce qu'exige un seuil d'alerte.
    Le côté de développement est choisi UNE fois (pas de récursion : avec
    a = b et x = 0,5, les deux côtés se renvoyaient l'un à l'autre)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = lambda A, B, X: (math.lgamma(A + B) - math.lgamma(A) - math.lgamma(B)
                          + A * math.log(X) + B * math.log(1 - X))
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb(a, b, x)) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb(b, a, 1 - x)) * _betacf(b, a, 1 - x) / b


def f_sf(f, d1, d2):
    """P(F > f) pour une loi de Fisher à (d1, d2) degrés de liberté."""
    if f is None or f <= 0 or d1 <= 0 or d2 <= 0:
        return 1.0
    return betainc_reg(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * float(f)))


def ks_p(d, n1, n2):
    """p-value asymptotique du test de Kolmogorov-Smirnov à deux échantillons.

    Q(λ) = 2 Σ (−1)^(j−1) e^(−2j²λ²), avec la correction usuelle de λ pour
    les petits effectifs. Sert à afficher, dans la case du tableau, le nombre
    qui décide de la couleur plutôt que la seule distance D."""
    if d is None or not n1 or not n2:
        return None
    ne = math.sqrt(n1 * n2 / float(n1 + n2))
    lam = (ne + 0.12 + 0.11 / ne) * d
    if lam <= 0:
        return 1.0
    q = 2.0 * sum((-1) ** (j - 1) * math.exp(-2.0 * j * j * lam * lam)
                  for j in range(1, 101))
    return min(1.0, max(0.0, q))


def t_sf(t, ddl):
    """P(T > t) pour une loi de Student à `ddl` degrés de liberté."""
    if ddl <= 0:
        return 1.0
    x = ddl / float(ddl + t * t)
    q = 0.5 * betainc_reg(ddl / 2.0, 0.5, x)
    return q if t > 0 else 1.0 - q


def t_quantile(alpha, ddl):
    """t tel que P(T > t) = alpha (queue supérieure), par dichotomie.

    Sert au seuil critique du test de Grubbs, qui s'exprime avec un quantile
    de Student. Pas de scipy : une dichotomie sur `t_sf`, monotone, converge
    en une soixantaine d'itérations à 1e-9 près."""
    if not (0 < alpha < 1) or ddl <= 0:
        return None
    lo, hi = 0.0, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_sf(mid, ddl) > alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return (lo + hi) / 2.0


def grubbs_critique(n, alpha=0.05):
    """Valeur critique du test de Grubbs (document, 6.4).

    G_c = [(n−1)/√n] × √[ t²(α/2n, n−2) / (n−2+t²(α/2n, n−2)) ]"""
    if n < 3:
        return None
    t = t_quantile(alpha / (2.0 * n), n - 2)
    if t is None:
        return None
    t2 = t * t
    return (n - 1) / math.sqrt(n) * math.sqrt(t2 / (n - 2 + t2))


def entropie(effectifs):
    """Entropie de Shannon en bits : H = − Σ p_k log₂ p_k."""
    tot = sum(effectifs)
    if tot <= 0:
        return None
    h = 0.0
    for e in effectifs:
        if e > 0:
            pk = e / float(tot)
            h -= pk * math.log(pk, 2)
    return h


def bray_curtis(pa, pb):
    """Distance de Bray-Curtis entre deux distributions (document, 6.3).

    BC = Σ|p_k,a − p_k,b| / Σ(p_k,a + p_k,b). Sur des distributions
    normalisées, le dénominateur vaut 2 : BC varie de 0 (identiques) à 1."""
    cles = set(pa) | set(pb)
    if not cles:
        return None
    num = sum(abs(pa.get(k, 0.0) - pb.get(k, 0.0)) for k in cles)
    den = sum(pa.get(k, 0.0) + pb.get(k, 0.0) for k in cles)
    return (num / den) if den else None


def spearman(xs, ys):
    """Corrélation de rang de Spearman, ex æquo traités par rangs moyens."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None

    def rangs(v):
        ordre = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[ordre[j + 1]] == v[ordre[i]]:
                j += 1
            moyen = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[ordre[k]] = moyen
            i = j + 1
        return r

    rx, ry = rangs(xs), rangs(ys)
    mx, my = moyenne(rx), moyenne(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return (num / (dx * dy)) if dx and dy else None


def fisher_z_diff(r1, n1, r2, n2):
    """Test de différence de deux corrélations (transformation de Fisher z).

    z = (z₁ − z₂) / √(1/(n₁−3) + 1/(n₂−3)), avec z = ½ ln[(1+r)/(1−r)].
    Renvoie (z, p unilatérale : « r₁ significativement PLUS FAIBLE que r₂ »),
    qui est le sens visé par le document en 6.5."""
    if r1 is None or r2 is None or n1 < 5 or n2 < 5:
        return None, None
    borne = lambda r: max(-0.999999, min(0.999999, r))
    z1 = 0.5 * math.log((1 + borne(r1)) / (1 - borne(r1)))
    z2 = 0.5 * math.log((1 + borne(r2)) / (1 - borne(r2)))
    se = math.sqrt(1.0 / (n1 - 3) + 1.0 / (n2 - 3))
    if not se:
        return None, None
    z = (z1 - z2) / se
    return z, phi(z)                       # P(Z < z) : queue basse


def mann_whitney_z(xs, ys):
    """z du test de Mann-Whitney (Kruskal-Wallis à deux groupes), ex æquo
    corrigés. Positif = `xs` prend des valeurs plus hautes que `ys`."""
    n1, n2 = len(xs), len(ys)
    if n1 < 3 or n2 < 3:
        return None
    tous = sorted([(v, 0) for v in xs] + [(v, 1) for v in ys])
    N = n1 + n2
    rangs = [0.0] * N
    ties = []
    i = 0
    while i < N:
        j = i
        while j + 1 < N and tous[j + 1][0] == tous[i][0]:
            j += 1
        moyen = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            rangs[k] = moyen
        ties.append(j - i + 1)
        i = j + 1
    R1 = sum(r for r, (_v, g) in zip(rangs, tous) if g == 0)
    U = R1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    corr = sum(t ** 3 - t for t in ties)
    var = n1 * n2 / 12.0 * ((N + 1) - corr / float(N * (N - 1)))
    return (U - mu) / math.sqrt(var) if var > 0 else None


def acp_premier_axe(lignes, iterations=300):
    """Premier axe d'une ACP sur matrice de corrélation, sans numpy.

    `lignes` = liste de vecteurs 0/1 de même longueur. Renvoie
    (poids, part de variance expliquée, moyennes, écarts-types, items retenus).
    La matrice de corrélation d'un module de 29 items fait 29×29 : la méthode
    de la puissance itérée y converge en quelques dizaines de tours, pour un
    coût très inférieur à celui d'une diagonalisation complète — et sans
    ajouter numpy aux dépendances du projet."""
    if not lignes:
        return None
    k = len(lignes[0])
    n = len(lignes)
    if n < 5 or k < 3:
        return None
    moy = [sum(l[i] for l in lignes) / float(n) for i in range(k)]
    sd = []
    for i in range(k):
        v = sum((l[i] - moy[i]) ** 2 for l in lignes) / float(n)
        sd.append(math.sqrt(v))
    # Items sans variance : ils n'apportent rien et rendraient la corrélation
    # indéfinie (division par zéro).
    idx = [i for i in range(k) if sd[i] > 1e-9]
    if len(idx) < 3:
        return None
    m = len(idx)
    z = [[(l[i] - moy[i]) / sd[i] for i in idx] for l in lignes]
    C = [[0.0] * m for _ in range(m)]
    for a in range(m):
        for b in range(a, m):
            c = sum(r[a] * r[b] for r in z) / float(n)
            C[a][b] = C[b][a] = c
    v = [1.0 / math.sqrt(m)] * m
    lam = 0.0
    for _ in range(iterations):
        w = [sum(C[a][b] * v[b] for b in range(m)) for a in range(m)]
        norme = math.sqrt(sum(x * x for x in w))
        if norme < 1e-12:
            return None
        nv = [x / norme for x in w]
        if max(abs(nv[a] - v[a]) for a in range(m)) < 1e-10:
            v = nv
            break
        v = nv
    lam = sum(v[a] * sum(C[a][b] * v[b] for b in range(m)) for a in range(m))
    return {"items": idx, "poids": v, "part": lam / float(m),
            "moy": moy, "sd": sd}


def acp_score(acp, ligne):
    """Score factoriel d'un ménage sur le premier axe."""
    if not acp:
        return None
    return sum(w * (ligne[i] - acp["moy"][i]) / acp["sd"][i]
               for w, i in zip(acp["poids"], acp["items"]))


def guttman_erreurs(lignes, ordre):
    """Erreurs de Guttman : réponses s'écartant du scalogramme parfait.

    `ordre` = indices des items triés par prévalence DÉCROISSANTE dans la
    zone. Un ménage qui possède s biens devrait, dans une échelle parfaite,
    posséder exactement les s plus répandus ; chaque réponse qui s'en écarte
    est une erreur. C'est le comptage du document (14 erreurs sur 240
    réponses, et non un comptage par paires d'items)."""
    total = 0
    for l in lignes:
        vals = [l[i] for i in ordre]
        s = sum(vals)
        total += sum(1 for r, x in enumerate(vals) if x != (1 if r < s else 0))
    return total


def cronbach(lignes):
    """Alpha de Cronbach : k/(k−1) × (1 − Σσ²_i / σ²_total)."""
    n = len(lignes)
    if n < 3:
        return None
    k = len(lignes[0])
    if k < 2:
        return None
    var = []
    for i in range(k):
        mo = sum(l[i] for l in lignes) / float(n)
        var.append(sum((l[i] - mo) ** 2 for l in lignes) / float(n))
    scores = [sum(l) for l in lignes]
    mo = sum(scores) / float(n)
    vt = sum((x - mo) ** 2 for x in scores) / float(n)
    if vt <= 0:
        return None
    return k / (k - 1.0) * (1 - sum(var) / vt)


def phi_2x2(n11, n10, n01, n00):
    """Coefficient phi d'une table 2×2 (corrélation de deux binaires)."""
    den = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
    if den <= 0:
        return None
    return (n11 * n00 - n10 * n01) / math.sqrt(den)


def kruskal_binaire(groupes):
    """H de Kruskal-Wallis pour des observations BINAIRES, et sa p-value.

    `groupes` = [(violations, applications), …], un couple par agent. Les
    observations ne prenant que deux valeurs (règle violée ou non), tous les
    ex æquo sont connus d'avance : les zéros partagent le rang (n₀+1)/2 et les
    uns le rang n₀ + (n₁+1)/2. La somme des rangs d'un agent se calcule donc
    sans jamais trier — O(k) au lieu de O(N log N), ce qui rend le test
    calculable pour chacun des 400 agents sans faire s'effondrer la page."""
    g = [(v, n) for v, n in groupes if n > 0]
    k = len(g)
    if k < 2:
        return None, None, None
    N = sum(n for _v, n in g)
    n1 = sum(v for v, _n in g)                       # observations « violée »
    n0 = N - n1
    if N < 2 or n0 == 0 or n1 == 0:                  # aucune variabilité
        return None, None, k - 1
    r0 = (n0 + 1) / 2.0
    r1 = n0 + (n1 + 1) / 2.0
    somme = 0.0
    for v, n in g:
        R = (n - v) * r0 + v * r1
        somme += R * R / n
    h = 12.0 / (N * (N + 1)) * somme - 3.0 * (N + 1)
    # Correction des ex æquo : deux paquets seulement, de tailles n₀ et n₁.
    corr = 1.0 - ((n0 ** 3 - n0) + (n1 ** 3 - n1)) / float(N ** 3 - N)
    if corr > 0:
        h /= corr
    return h, chi2_sf(h, k - 1), k - 1


def tukey(valeurs):
    """(Q1, Q3, IQR, seuil modéré, seuil extrême) — règle de Tukey.

    Le document retient Q3 + 1,5×IQR pour un « outlier modéré » et
    Q3 + 3×IQR pour un « outlier extrême, audit prioritaire ». (Son texte
    mentionne aussi « médiane + 3 IQR » une ligne plus haut : c'est la version
    des SEUILS qui est retenue ici, la seule des deux qui soit chiffrée.)"""
    if not valeurs:
        return (None,) * 5
    q1, q3 = percentile(sorted(valeurs), 0.25), percentile(sorted(valeurs), 0.75)
    if q1 is None or q3 is None:
        return (None,) * 5
    iqr = q3 - q1
    return q1, q3, iqr, q3 + 1.5 * iqr, q3 + 3.0 * iqr


def rang_percentile(v, ref):
    """Position de `v` dans la distribution `ref`, en pourcentage."""
    if v is None or not ref:
        return None
    return 100.0 * sum(1 for x in ref if x < v) / len(ref)


def moyenne(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def ecart_type(v):
    """Écart-type d'échantillon (n−1)."""
    v = [x for x in v if x is not None]
    if len(v) < 2:
        return None
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def mediane(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def percentile(v, p):
    """Percentile par interpolation linéaire, `p` entre 0 et 1."""
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    i = p * (len(v) - 1)
    b = int(i)
    return v[b] + (i - b) * (v[min(b + 1, len(v) - 1)] - v[b])


def z_score(x, m, s):
    if x is None or m is None or not s:
        return None
    return (x - m) / s


# --- Outillage du NIVEAU 6 (fraude et duplication, document §8) -----------
def covariance(lignes):
    """Matrice de covariance (estimateur sans biais) d'un nuage de vecteurs."""
    n = len(lignes)
    if n < 2:
        return None
    k = len(lignes[0])
    moy = [sum(l[j] for l in lignes) / float(n) for j in range(k)]
    cov = [[0.0] * k for _ in range(k)]
    for l in lignes:
        d = [l[j] - moy[j] for j in range(k)]
        for i in range(k):
            for j in range(i, k):
                cov[i][j] += d[i] * d[j]
    for i in range(k):
        for j in range(i, k):
            cov[i][j] /= (n - 1.0)
            cov[j][i] = cov[i][j]
    return cov


def inverse_matrice(m):
    """Inverse par Gauss-Jordan à pivot partiel, sans numpy.

    `None` si la matrice est singulière — cas courant ici : une variable
    constante dans la zone (toutes les maisons du même standing) ou deux
    variables colinéaires rendent Σ non inversible, et la distance de
    Mahalanobis n'est alors pas définissable."""
    k = len(m)
    a = [list(m[i]) + [1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12:
            return None
        a[c], a[p] = a[p], a[c]
        piv = a[c][c]
        a[c] = [x / piv for x in a[c]]
        for r in range(k):
            if r != c and a[r][c]:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [ligne[k:] for ligne in a]


def mahalanobis2(x, y, inv):
    """Carré de la distance de Mahalanobis entre deux vecteurs (D²)."""
    d = [x[j] - y[j] for j in range(len(x))]
    k = len(d)
    return sum(d[i] * inv[i][j] * d[j] for i in range(k) for j in range(k))


def paires_mahalanobis(lignes, inv, plafond=20000):
    """DISTANCES de Mahalanobis de toutes les paires, échantillonnées au besoin.

    Renvoie D = √(D²), et non D². Le document écrit « D² » dans sa formule mais
    chiffre son exemple en DISTANCE : « distance moyenne entre paires de la
    zone : 2,8 (écart-type 0,9) ». Sur quatre variables, la moyenne de D² vaut
    8 et celle de D vaut √8 = 2,83 d'écart-type ≈ 0,9 — ce sont bien ses
    chiffres. Pris au pied de la lettre sur D², son seuil « moyenne − 2 σ »
    vaudrait 8 − 11,3 < 0 : aucune paire ne pourrait jamais l'atteindre et le
    test serait mort-né. On travaille donc sur D.

    Le nombre de paires croît en n² : une commune de 250 ménages en produit
    31 000, quatre communes en produiraient un demi-million pour un gain de
    précision nul sur une moyenne et un écart-type. Au-delà du plafond, on
    parcourt les paires avec un pas constant — échantillon systématique, donc
    reproductible d'un calcul à l'autre (pas de tirage aléatoire)."""
    n = len(lignes)
    total = n * (n - 1) // 2
    if total <= 0 or inv is None:
        return []
    pas = max(1, total // plafond)
    out, k = [], 0
    for i in range(n):
        for j in range(i + 1, n):
            if k % pas == 0:
                out.append(math.sqrt(max(0.0, mahalanobis2(lignes[i], lignes[j], inv))))
            k += 1
    return out


BENFORD = tuple(math.log10(1 + 1.0 / d) for d in range(1, 10))


def premier_chiffre(v):
    """Premier chiffre SIGNIFICATIF (1–9) d'une valeur, ou None."""
    if v is None:
        return None
    s = str(v).strip()
    for ch in s:
        if ch in "123456789":
            return int(ch)
        if ch not in "+-0., ":
            return None
    return None


def chi2_benford(cnt):
    """χ² d'ajustement à la loi de Benford, chiffres rares regroupés. (χ², ddl).

    Exiger les neuf classes imposerait n ≥ 109 (P(9) = 4,6 %, attendu ≥ 5) —
    hors d'atteinte pour un agent. Les classes de droite sont donc fondues dans
    leur voisine jusqu'à ce que chaque effectif attendu atteigne 5, et le ddl
    suit : le test reste valide dès la trentaine d'observations, avec moins de
    finesse. (None, 0) si même ce regroupement ne suffit pas."""
    n = float(sum(cnt))
    if n <= 0:
        return None, 0
    obs, att = [], []
    for i in range(9):
        e = n * BENFORD[i]
        if att and att[-1] < 5:
            obs[-1] += cnt[i]
            att[-1] += e
        else:
            obs.append(cnt[i])
            att.append(e)
    while len(att) > 1 and att[-1] < 5:
        # Le pop() est évalué AVANT l'indexation : on le sort explicitement,
        # sinon « obs[-2] += obs.pop() » vise l'index -2 de la liste déjà
        # raccourcie — hors bornes dès qu'il ne reste que deux classes.
        o, a = obs.pop(), att.pop()
        obs[-1] += o
        att[-1] += a
    if len(att) < 2 or min(att) < 5:
        return None, 0
    return sum((o - a) ** 2 / a for o, a in zip(obs, att)), len(att) - 1


def chi2_homogeneite(a, b):
    """χ² d'homogénéité entre deux distributions d'effectifs de même longueur.

    Les colonnes dont les DEUX effectifs attendus tombent sous 5 sont
    regroupées avec la précédente : sans ce repli, les chiffres rares (8, 9)
    gonflent le χ² sur de très petits effectifs. Renvoie (χ², ddl)."""
    na, nb = float(sum(a)), float(sum(b))
    if na <= 0 or nb <= 0:
        return None, 0
    oa, ob = [], []
    for i in range(len(a)):
        att = (a[i] + b[i]) / (na + nb)
        if oa and att * na < 5 and att * nb < 5:
            oa[-1] += a[i]
            ob[-1] += b[i]
        else:
            oa.append(a[i])
            ob.append(b[i])
    if len(oa) < 2:
        return None, 0
    khi = 0.0
    for x, y in zip(oa, ob):
        tot = x + y
        if tot <= 0:
            continue
        for obs, n_ in ((x, na), (y, nb)):
            att = tot * n_ / (na + nb)
            if att > 0:
                khi += (obs - att) ** 2 / att
    return khi, len(oa) - 1


def regression(xs, ys):
    """Régression linéaire simple : pentes, écart-type des résidus et R².

    `None` si l'explicative est constante (tous les ménages de même taille) :
    la pente n'est alors pas estimable."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = moyenne(xs), moyenne(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b1 = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b0 = my - b1 * mx
    res = [y - (b0 + b1 * x) for x, y in zip(xs, ys)]
    sce = sum(r * r for r in res)
    sct = sum((y - my) ** 2 for y in ys)
    ddl = n - 2
    return {"b0": b0, "b1": b1, "n": n,
            "sigma": math.sqrt(sce / ddl) if ddl > 0 and sce > 0 else None,
            "r2": (1 - sce / sct) if sct > 0 else None}


def distance_m(a, b):
    """Distance en MÈTRES entre deux points (latitude, longitude) décimaux.

    Formule de haversine : à l'échelle d'un fokontany, une approximation plane
    suffirait, mais haversine coûte le même prix et reste juste si le périmètre
    s'étend un jour à toute l'île."""
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def dbscan_agglutines(points, eps, minpts):
    """DBSCAN simplifié : (part des points en amas, nombre d'amas, plus gros amas).

    Un point est un « cœur » s'il compte au moins `minpts` voisins dans le
    rayon `eps` (lui-même compris) ; un amas est une composante connexe de
    cœurs, augmentée des points de bordure qu'ils atteignent. La part rendue
    est celle des points appartenant à un amas quelconque — exactement la
    quantité que le document met sous seuil.

    Coût en n² : sans index spatial, mais n est ici le nombre de ménages d'un
    agent (quelques dizaines), pas celui du district."""
    n = len(points)
    if n < minpts:
        return 0.0, 0, 0
    vois = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if distance_m(points[i], points[j]) <= eps:
                vois[i].append(j)
                vois[j].append(i)
    coeur = [len(vois[i]) + 1 >= minpts for i in range(n)]
    vu, amas, plus_gros = set(), 0, 0
    for i in range(n):
        if not coeur[i] or i in vu:
            continue
        amas += 1
        pile, groupe = [i], set()
        vu.add(i)
        while pile:
            c = pile.pop()
            groupe.add(c)
            for j in vois[c]:
                groupe.add(j)                  # bordure : rattachée, pas étendue
                if coeur[j] and j not in vu:
                    vu.add(j)
                    pile.append(j)
        plus_gros = max(plus_gros, len(groupe))
        vu |= {x for x in groupe if coeur[x]}
    dans = set()
    for i in range(n):
        if coeur[i]:
            dans.add(i)
            dans.update(vois[i])
    return len(dans) / float(n), amas, plus_gros


# --- Outillage du NIVEAU 7 (non-réponse et complétude, document §9) -------
def chi2_2x2(a, b, c, d):
    """χ² d'indépendance d'une table 2×2 et son ddl. (None, 0) si invalide.

    Table : (a) manquants de l'unité, (b) renseignés de l'unité, (c) manquants
    du reste, (d) renseignés du reste. Sans correction de continuité, comme le
    document. Rendu invalide dès qu'un effectif ATTENDU descend sous 5 —
    l'approximation du χ² ne tient plus."""
    n = float(a + b + c + d)
    if n <= 0:
        return None, 0
    l1, l2 = a + b, c + d
    c1, c2 = a + c, b + d
    att = (l1 * c1 / n, l1 * c2 / n, l2 * c1 / n, l2 * c2 / n)
    if min(att) < 5:
        return None, 0
    obs = (a, b, c, d)
    return sum((o - e) ** 2 / e for o, e in zip(obs, att)), 1


def little_mcar(lignes):
    """Statistique d² du test MCAR de Little et son ddl.

    `lignes` = vecteurs de même longueur, `None` pour une valeur manquante. Les
    lignes sont groupées par MOTIF de manquants ; pour chaque motif, la moyenne
    des variables observées est comparée à la moyenne générale, pondérée par
    l'inverse de la covariance restreinte à ces mêmes variables :

        d² = Σ_j n_j (x̄_j − μ̂_j)ᵀ Σ̂_j⁻¹ (x̄_j − μ̂_j),  ddl = Σ_j p_j − p

    Sous H₀ (manquants complètement aléatoires), d² suit approximativement un χ².
    Rejeter H₀ signifie que les ménages dont une variable manque ne ressemblent
    pas aux autres : la non-réponse est structurée, donc porteuse de biais.

    ⚠️ SIMPLIFICATION assumée : μ̂ et Σ̂ sont estimées sur les lignes COMPLÈTES,
    là où le test d'origine les estime par l'algorithme EM. L'écart reste faible
    tant que les lignes complètes dominent, et cela évite d'embarquer un EM dans
    un module qui se passe de numpy. Les motifs dont la sous-covariance n'est pas
    inversible (variable constante sur ce motif) sont ignorés, avec leur ddl."""
    if not lignes:
        return None, 0
    p = len(lignes[0])
    complets = [l for l in lignes if all(x is not None for x in l)]
    if len(complets) < p + 2:
        return None, 0
    # Une variable CONSTANTE sur les lignes complètes (tous les logements d'une
    # ZD ont une pièce, par exemple) rend Σ non inversible et tuerait le test
    # entier. Elle n'apporte rien : on la retire avant d'estimer.
    utiles = [j for j in range(p)
              if (ecart_type([l[j] for l in complets]) or 0) > 0]
    if len(utiles) < 2:
        return None, 0
    if len(utiles) < p:
        lignes = [[l[j] for j in utiles] for l in lignes]
        complets = [[l[j] for j in utiles] for l in complets]
        p = len(utiles)
    mu = [moyenne([l[j] for l in complets]) for j in range(p)]
    sig = covariance(complets)
    if sig is None:
        return None, 0
    motifs = defaultdict(list)
    for l in lignes:
        obs = tuple(j for j in range(p) if l[j] is not None)
        if obs:
            motifs[obs].append(l)
    d2, ddl = 0.0, 0
    for obs, lot in motifs.items():
        inv = inverse_matrice([[sig[i][j] for j in obs] for i in obs])
        if inv is None:
            continue
        k = len(obs)
        ec = [moyenne([l[j] for l in lot]) - mu[j] for j in obs]
        d2 += len(lot) * sum(ec[x] * inv[x][y] * ec[y]
                             for x in range(k) for y in range(k))
        ddl += k
    ddl -= p
    if ddl <= 0 or d2 < 0:
        return None, 0
    return d2, ddl

# --------------------------------------------------------------------------
# Enveloppe d'un résultat de test
# --------------------------------------------------------------------------
# La présentation reprend celle de la documentation RSU : titre numéroté,
# principe, formule, puis deux encadrés — « Exemple appliqué » et « Seuil(s)
# d'alerte indicatif(s) ». Ici l'encadré d'exemple porte le calcul RÉEL de
# l'agent, avec ses propres chiffres, au lieu de l'exemple fictif du document.

def fmt(x, d=2):
    """Nombre à la française : virgule décimale, espace pour les milliers."""
    if x is None:
        return "—"
    if isinstance(x, int) or (isinstance(x, float) and x == int(x) and abs(x) < 1e15):
        return f"{int(x):,}".replace(",", " ")
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def resultat(num, titre, principe, formule, valeur, unite="", n=0, n_min=0,
             calcul=(), conclusion="", seuils=(), alerte=False, portee=None,
             vigilance=False, repere="", stat="", raison=""):
    """Un test, prêt à afficher dans la mise en page du document.

    `portee` décrit l'unité sur laquelle le test a réellement été calculé (voir
    `_escalade`) : l'agent quand son effectif suffit, sinon son équipe, sinon
    la commune. `n < n_min` même au niveau le plus large ⇒ « non calculé ».

    Un résultat obtenu au niveau CE ou commune ne dit RIEN sur l'agent en
    particulier : la page doit l'afficher comme un repère de contexte, jamais
    comme un verdict individuel.

    GRAVITÉ, en quatre états, pour la matrice CE × AE :
        "nd"        effectif insuffisant — rien n'est affirmé ;
        "ok"        calculé, aucun seuil franchi ;
        "vigilance" seuil INTERMÉDIAIRE franchi (`vigilance`) ;
        "alerte"    seuil du DOCUMENT franchi (`alerte`).
    `stat` est la STATISTIQUE DE TEST, affichée dans la case à côté de la
    mesure (« 15,6 % (Z = 2,73) ») : c'est elle qui décide de la couleur
    quand le seuil est relatif à la référence. Vide pour les tests à seuil
    absolu, où la mesure suffit à expliquer la couleur.

    `repere` est la phrase COURTE qui rend la couleur explicable dans la
    matrice. Pour la moitié des tests, la valeur affichée est une mesure et le
    seuil est RELATIF à la référence : sans le repère, deux agents affichant
    « 0,0 % » peuvent être l'un vert et l'autre rouge — constaté sur les
    données du pilote — et la case devient illisible. Le repère va dans
    l'infobulle.

    ⚠️ Les seuils d'ALERTE viennent de la documentation technique RSU ; les
    seuils de VIGILANCE n'y figurent pas — ce sont des paliers intermédiaires
    choisis ici pour graduer la lecture (cf. `SEUILS_VIGILANCE`). Ils alertent
    plus tôt, donc avec plus de faux positifs : à ajuster à l'usage."""
    insuffisant = n < n_min
    portee = portee or {"niveau": "agent", "libelle": "cet agent", "remonte": False}
    if insuffisant:
        # Un test peut être « nd » pour deux raisons très différentes : trop peu
        # d'observations, ou une statistique non définissable malgré un effectif
        # suffisant (rien à quoi comparer, matrice non inversible…). `raison`
        # sert à dire laquelle, au lieu d'imputer à l'effectif un blocage qui
        # n'en vient pas.
        calcul = ([raison] if raison else
                  [f"Effectif disponible : n = {fmt(n)} — le test en demande "
                   f"au moins {fmt(n_min)}.",
                   "Aucun échelon (agent, chef d'équipe, commune) n'atteint "
                   "cet effectif."])
        conclusion = ("→ Test non calculé : la statistique n'est pas "
                      "définissable ici." if raison else
                      "→ Test non calculé : sous cet effectif, le résultat "
                      "serait du bruit et non un indicateur.")
    return {
        "num": num, "titre": titre, "principe": principe,
        "formule": list(formule) if isinstance(formule, (list, tuple)) else [formule],
        "valeur": None if insuffisant else valeur, "unite": unite,
        "n": n, "nMin": n_min, "insuffisant": insuffisant,
        "alerte": bool(alerte) and not insuffisant,
        "vigilance": bool(vigilance) and not bool(alerte) and not insuffisant,
        "gravite": ("nd" if insuffisant else "alerte" if alerte
                    else "vigilance" if vigilance else "ok"),
        "repere": "" if insuffisant else str(repere or ""),
        "stat": "" if insuffisant else str(stat or ""),
        "calcul": list(calcul), "conclusion": conclusion,
        "seuils": list(seuils),
        "portee": portee["niveau"], "porteeLib": portee["libelle"],
        "remonte": portee["remonte"] and not insuffisant,
    }


def _escalade(echelons, effectif, n_min):
    """Premier échelon dont l'effectif atteint `n_min` : agent → CE → commune.

    `echelons` est une liste ordonnée de dicts {niveau, libelle, unites, ref,
    pairs}. `ref` est la population de référence AGRÉGÉE (pour les taux et les
    percentiles) ; `pairs` est la liste des unités COMPARABLES — les autres
    agents de la commune, les autres CE, les autres communes. Le document
    compare à la distribution entre pairs (« la médiane de l'équipe est de
    9 ménages/jour »), pas au cumul de l'équipe : confondre les deux compare
    un agent au total de sa commune et vide le z-score de son sens.
    `effectif` calcule le n du test sur une liste de ménages — il diffère selon
    le test (ménages, entretiens horodatés, réponses, questions éligibles).

    Remonter d'un échelon change la nature de la réponse : on ne mesure plus
    l'agent mais son équipe ou sa commune. Le résultat le signale (`remonte`)
    pour que la page ne le présente jamais comme un verdict individuel."""
    dernier = None
    for i, e in enumerate(echelons):
        n = effectif(e["unites"])
        dernier = (e, n)
        if n >= n_min:
            return (e["unites"], e["ref"], n,
                    {"niveau": e["niveau"], "libelle": e["libelle"],
                     "remonte": i > 0}, e.get("pairs", []))
    e, n = dernier
    return (e["unites"], e["ref"], n,
            {"niveau": e["niveau"], "libelle": e["libelle"], "remonte": True},
            e.get("pairs", []))


# --------------------------------------------------------------------------
# NIVEAU 1 — Indicateurs de suivi terrain par agent (document, section 3)
# --------------------------------------------------------------------------
HAFA = {"H1": 9, "H4": 8, "H5": 7, "H6": 9, "H7": 16, "H8": 9, "H9": 6, "H10": 6}
NSP = {"M19a": 3, "M19b": 3, "M19c": 3, "M19e": 3, "M19f": 3, "M19g": 3,
       "M19h": 3, "M19i": 3, "M19j": 5}
CHAMPS_ATTENDUS = ("H1", "H2", "H4", "H5", "H6", "H7", "H8", "H9", "H10",
                   "nbmembre", "CQ3")

N_MIN = {"productivite": 10, "duree": 10, "completude": 5, "regles": 10,
         "hafa": 20, "nsp": 30}

# Paliers de VIGILANCE (orange) — intermédiaires entre « conforme » et le seuil
# d'ALERTE du document. Ils ne figurent PAS dans la documentation technique :
# ce sont des paliers de lecture, pris sur la même statistique que l'alerte,
# à mi-chemin. Les modifier ne change que la couleur, jamais le verdict rouge.
SEUILS_VIGILANCE = {
    "productivite": "z > 2, ou productivité > 1,5 × la médiane des pairs",
    "duree": "durée médiane sous le 1ᵉʳ quartile de la référence",
    "completude": "taux de complétude < 98 %",
    "regles": "déclenchements > moyenne des pairs + 1 écart-type",
    "hafa": "taux de recours à « Hafa » > 10 %",
    "nsp": "|Z| > 1,96 (seuil à 5 %)",
}
# Le même palier, indexé par numéro de test (ce que la matrice affiche).
# Les paliers du niveau 2 sont ajoutés plus bas, après SEUILS_VIGILANCE2.
VIGILANCE_PAR_TEST = {
    "3.1": SEUILS_VIGILANCE["productivite"], "3.2": SEUILS_VIGILANCE["duree"],
    "3.3": SEUILS_VIGILANCE["completude"], "3.4": SEUILS_VIGILANCE["regles"],
    "3.5": SEUILS_VIGILANCE["hafa"], "3.6": SEUILS_VIGILANCE["nsp"],
}


def niveau1(echelons):
    """Section 3 du document — suivi terrain.

    `echelons` : agent, puis chef d'équipe, puis commune, chacun avec sa
    référence de comparaison (l'échelon du dessus). Chaque test descend cette
    liste jusqu'au premier échelon dont l'effectif suffit."""
    out = []
    ag = echelons[0]["unites"]

    def _jours(ms):
        c = defaultdict(int)
        for m in ms:
            if m.get("date"):
                c[m["date"]] += 1
        return list(c.values())

    # --- 3.1 Productivité journalière -------------------------------------
    u, ref, n, po, pairs = _escalade(echelons, len, N_MIN["productivite"])
    pa = _jours(u)
    # Référence = productivité MOYENNE de chaque pair (autre agent, autre CE,
    # autre commune), et non le cumul de la référence.
    pe = [x for x in (moyenne(_jours(p)) for p in pairs) if x is not None]
    v, m_eq, s_eq, med_eq = moyenne(pa), moyenne(pe), ecart_type(pe), mediane(pe)
    z = z_score(v, m_eq, s_eq)
    al = bool((z is not None and z > 3) or (v is not None and med_eq and v > 2 * med_eq))
    vg = bool((z is not None and z > 2)
              or (v is not None and med_eq and v > 1.5 * med_eq))
    calc = [f"Unité mesurée : {po['libelle']} — {fmt(n)} ménage(s) sur "
            f"{fmt(len(pa))} jour(s) de collecte.",
            f"Productivité : {fmt(v, 1)} ménage(s)/jour.",
            f"Référence — {fmt(len(pe))} unité(s) comparable(s) : médiane "
            f"{fmt(med_eq, 1)}, moyenne {fmt(m_eq, 1)}, écart-type {fmt(s_eq, 2)}."]
    if z is not None:
        calc.append(f"z = ({fmt(v, 1)} − {fmt(m_eq, 1)}) / {fmt(s_eq, 2)} = {fmt(z, 2)}")
    out.append(resultat(
        "3.1", "Productivité journalière",
        "Nombre de ménages complétés par jour et par agent. Une vitesse très "
        "supérieure à celle de l'équipe est incompatible avec le temps minimal "
        "nécessaire pour administrer les 196 questions du questionnaire.",
        "Productivité_a,j = Nombre de questionnaires « complétés » soumis par "
        "l'agent a le jour j",
        v, "ménages/jour", n=n, n_min=N_MIN["productivite"], calcul=calc,
        conclusion=("→ Alerte : vitesse anormalement élevée au regard de la référence."
                    if al else "→ Productivité comparable à la référence."),
        seuils=["z-score > 3 par rapport à la moyenne de l'équipe (même zone, même jour)",
                "Ou : productivité > 2 fois la médiane de l'équipe"],
        repere=(f"médiane des pairs {fmt(med_eq, 1)}/jour"
                + (f" · z = {fmt(z, 2)}" if z is not None else "")),
        stat=(f"z = {fmt(z, 2)}" if z is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 3.2 Durée moyenne de passation -----------------------------------
    nb_duree = lambda ms: sum(1 for m in ms if m.get("duree"))
    u, ref, n, po, _pairs = _escalade(echelons, nb_duree, N_MIN["duree"])
    da = [m["duree"] for m in u if m.get("duree")]
    de = [m["duree"] for m in ref if m.get("duree")]
    p5, v = percentile(de, 0.05), mediane(da)
    q1, q3 = percentile(de, 0.25), percentile(de, 0.75)
    al = bool(v is not None and p5 is not None and v < p5)
    vg = bool(v is not None and q1 is not None and v < q1)
    # La couleur vient de la POSITION de la durée dans la distribution de
    # référence (sous le 5ᵉ percentile = alerte) : c'est ce rang qu'on affiche.
    rang = rang_percentile(v, de)
    out.append(resultat(
        "3.2", "Durée moyenne de passation",
        "Écart entre l'horodatage de fin et celui de début du questionnaire. "
        "Une durée très inférieure à celle de l'équipe, à taille de ménage "
        "comparable, est incompatible avec une administration réelle et "
        "complète du module individus.",
        ["Durée_i = Heure_fin_i − Heure_début_i (en minutes)",
         "Durée_attendue ≈ f(nbmembre_i)  [fonction croissante du nombre de membres]"],
        v, "min", n=n, n_min=N_MIN["duree"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} questionnaire(s) horodaté(s).",
                f"Durée médiane : {fmt(v, 1)} minutes.",
                f"Référence : 5ᵉ percentile {fmt(p5, 1)} min, "
                f"écart interquartile {fmt(q1, 1)}–{fmt(q3, 1)} min."],
        conclusion=("→ Alerte : durée sous le 5ᵉ percentile de la référence."
                    if al else "→ Durée compatible avec la référence."),
        seuils=["Durée < 5ᵉ percentile de la distribution des durées de "
                "l'équipe, à taille de ménage comparable"],
        repere=(f"référence : 5ᵉ pct {fmt(p5, 1)} min, "
                f"quartiles {fmt(q1, 1)}–{fmt(q3, 1)} min"),
        stat=(f"rang {fmt(rang, 1)} %" if rang is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 3.3 Taux de complétude -------------------------------------------
    u, ref, n, po, _pairs = _escalade(echelons, len, N_MIN["completude"])
    att = rempli = 0
    for m in u:
        for c in CHAMPS_ATTENDUS:
            att += 1
            if m.get(c) not in (None, ""):
                rempli += 1
    taux = (100.0 * rempli / att) if att else None
    al = bool(taux is not None and taux < 95)
    vg = bool(taux is not None and taux < 98)
    out.append(resultat(
        "3.3", "Taux de complétude",
        "Part des champs obligatoires effectivement renseignés. Contrôlé ici "
        "sur les caractéristiques du logement (H1 à H10), le nombre de membres "
        "et la date d'enquête.",
        "Taux_complétude_a = (Nb champs obligatoires renseignés) / "
        "(Nb champs obligatoires attendus) × 100",
        taux, "%", n=n, n_min=N_MIN["completude"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} ménage(s).",
                f"Champs attendus : {fmt(len(CHAMPS_ATTENDUS))} × {fmt(n)} = {fmt(att)}.",
                f"Champs renseignés : {fmt(rempli)}.",
                f"Taux = {fmt(rempli)} / {fmt(att)} × 100 = {fmt(taux, 1)} %"],
        conclusion=("→ Alerte : complétude sous le seuil de 95 %."
                    if al else "→ Complétude conforme."),
        seuils=["Taux de complétude < 95 %"],
        repere="seuils absolus : 98 % (vigilance), 95 % (alerte)",
        alerte=al, vigilance=vg, portee=po))

    # --- 3.4 Règles de validation intégrées -------------------------------
    u, ref, n, po, pairs = _escalade(echelons, len, N_MIN["regles"])
    ra = [m.get("erreurs_ss") or 0 for m in u]
    # Le seuil du document porte sur la distribution du TAUX entre unités.
    re_ = [x for x in (moyenne([m.get("erreurs_ss") or 0 for m in p])
                       for p in pairs) if x is not None]
    v, m_eq, s_eq = moyenne(ra), moyenne(re_), ecart_type(re_)
    lim = (m_eq + 2 * s_eq) if (m_eq is not None and s_eq) else None
    al = bool(v is not None and lim is not None and v > lim)
    z4 = z_score(v, m_eq, s_eq)
    lim1 = (m_eq + s_eq) if (m_eq is not None and s_eq) else None
    vg = bool(v is not None and lim1 is not None and v > lim1)
    out.append(resultat(
        "3.4", "Déclenchement des règles de validation",
        "Le questionnaire embarque des règles de validation (V1, W1, message "
        "M1) : H2 entre 1 et 30, cohérence entre M4 et M4b, un seul chef de "
        "ménage. Leur fréquence de déclenchement est un indicateur direct de "
        "la rigueur de saisie, déjà produit par l'outil de collecte.",
        "Taux_règles_a = (Nb de déclenchements V1/W1/M1) / "
        "(Nb de questionnaires soumis par a)",
        v, "par questionnaire", n=n, n_min=N_MIN["regles"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} questionnaire(s).",
                f"Déclenchements : {fmt(sum(ra))}, soit {fmt(v, 2)} en moyenne.",
                f"Référence — {fmt(len(re_))} unité(s) comparable(s) : moyenne "
                f"{fmt(m_eq, 2)}, écart-type {fmt(s_eq, 2)}.",
                f"Seuil = {fmt(m_eq, 2)} + 2 × {fmt(s_eq, 2)} = {fmt(lim, 2)}"],
        conclusion=("→ Alerte : déclenchements très au-dessus de la référence."
                    if al else "→ Fréquence comparable à la référence."),
        seuils=["Taux_règles_a > moyenne de l'équipe + 2 écarts-types"],
        repere=(f"pairs : moyenne {fmt(m_eq, 2)}, seuil d'alerte {fmt(lim, 2)}"),
        stat=(f"z = {fmt(z4, 2)}" if z4 is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 3.5 Recours à « Hafa » (Autre) -----------------------------------
    nb_rep = lambda ms: sum(1 for m in ms for v_ in HAFA if m.get(v_) is not None)
    u, ref, n, po, _pairs = _escalade(echelons, nb_rep, N_MIN["hafa"])
    na = sum(1 for m in u for v_ in HAFA if m.get(v_) == HAFA[v_])
    ne = sum(1 for m in ref for v_ in HAFA if m.get(v_) == HAFA[v_])
    de_ = nb_rep(ref)
    taux = (100.0 * na / n) if n else None
    t_eq = (100.0 * ne / de_) if de_ else None
    al = bool(taux is not None and taux > 15)
    vg = bool(taux is not None and taux > 10)
    out.append(resultat(
        "3.5", "Recours à la modalité « Hafa » (Autre)",
        "Les variables H1, H4, H5, H6, H7, H8, H9 et H10 comportent une "
        "modalité résiduelle « Hafa » avec un champ texte libre. Un usage "
        "excessif signale soit un agent qui ne cherche pas la bonne modalité "
        "dans la liste, soit une réponse inventée faute d'avoir insisté.",
        "Taux_Hafa_a,v = (Nb réponses « Hafa » pour la variable v) / "
        "(Nb réponses totales pour v, agent a)",
        taux, "%", n=n, n_min=N_MIN["hafa"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} réponse(s) aux "
                "8 variables de logement.",
                f"Réponses « Hafa » : {fmt(na)}.",
                f"Taux = {fmt(na)} / {fmt(n)} × 100 = {fmt(taux, 1)} %",
                f"Référence : {fmt(ne)} / {fmt(de_)} = {fmt(t_eq, 1)} %"],
        conclusion=("→ Alerte : recours à « Hafa » au-delà du seuil de 15 %."
                    if al else "→ Recours à « Hafa » dans la norme."),
        seuils=["Taux_Hafa_a,v > 15–20 %, à comparer au taux moyen de l'équipe "
                "pour la même variable"],
        repere=f"référence {fmt(t_eq, 1)} % · seuil d'alerte 15 %",
        alerte=al, vigilance=vg, portee=po))

    # --- 3.6 « Tsy mahalala » (Ne sait pas) — test Z de proportion ---------
    def compte_nsp(ms):
        o = t = 0
        for m in ms:
            for x in m.get("membres", []):
                for v_, code in NSP.items():
                    val = x.get(v_)
                    if val is not None:
                        t += 1
                        if val == code:
                            o += 1
        return o, t

    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: compte_nsp(ms)[1], N_MIN["nsp"])
    x1, n1 = compte_nsp(u)
    xt, nt = compte_nsp(ref)
    x2, n2 = xt - x1, nt - n1
    z = pv = p1 = p2 = pc = None
    if n1 and n2:
        p1, p2 = x1 / n1, x2 / n2
        pc = (x1 + x2) / (n1 + n2)
        den = math.sqrt(pc * (1 - pc) * (1 / n1 + 1 / n2)) if 0 < pc < 1 else 0
        if den:
            z = (p1 - p2) / den
            pv = p_bilateral(z)
    al = bool(z is not None and abs(z) > 2.58)
    vg = bool(z is not None and abs(z) > 1.96)
    calc = [f"Unité mesurée : {po['libelle']}.",
            f"x₁ = {fmt(x1)} réponses « Tsy mahalala » sur n₁ = {fmt(n1)} "
            f"questions éligibles → p₁ = {fmt(p1, 3)}",
            f"Reste de la référence : x₂ = {fmt(x2)} sur n₂ = {fmt(n2)} → "
            f"p₂ = {fmt(p2, 3)}"]
    if z is not None:
        calc += [f"p̂ = ({fmt(x1)} + {fmt(x2)}) / ({fmt(n1)} + {fmt(n2)}) = {fmt(pc, 4)}",
                 f"Z = ({fmt(p1, 3)} − {fmt(p2, 3)}) / √[p̂(1−p̂)(1/n₁ + 1/n₂)] = {fmt(z, 2)}",
                 f"p-value bilatérale = {fmt(pv, 4)}"]
    out.append(resultat(
        "3.6", "Non-réponse « Tsy mahalala » (Ne sait pas)",
        "Plusieurs questions du module emploi proposent une modalité « Tsy "
        "mahalala ». Un test Z de proportion compare le taux de l'unité "
        "mesurée à celui du reste de la référence : un écart significatif "
        "signale un questionnement superficiel.",
        ["Z = (p₁ − p₂) / √[ p̂(1−p̂)(1/n₁ + 1/n₂) ]",
         "avec p̂ = (x₁ + x₂) / (n₁ + n₂)"],
        (100.0 * x1 / n1) if n1 else None, "%", n=n, n_min=N_MIN["nsp"],
        calcul=calc,
        # Le test du document est BILATÉRAL (|Z|) : un agent qui répond « ne
        # sait pas » beaucoup MOINS souvent que ses pairs est signalé lui aussi
        # — il n'a peut-être jamais proposé la modalité, et a rempli à la place.
        # La conclusion doit donc dire DANS QUEL SENS va l'écart : écrire
        # « éludée plus souvent » pour un agent à 0 % face à une référence à
        # 66 % était faux (constaté sur les données du pilote).
        conclusion=(
            ("→ Alerte : cette question est éludée significativement plus "
             "souvent que dans la référence."
             if (z or 0) > 0 else
             "→ Alerte : « ne sait pas » significativement plus RARE que dans "
             "la référence — modalité peut-être jamais proposée, réponse "
             "remplie à la place.") if al else
            ("→ Vigilance : recours au « ne sait pas » plus fréquent que la "
             "référence." if (z or 0) > 0 else
             "→ Vigilance : recours au « ne sait pas » plus rare que la "
             "référence.") if vg else
            "→ Taux de non-réponse comparable à la référence."),
        seuils=["|Z| > 1,96 (seuil à 5 %)",
                "|Z| > 2,58 (seuil à 1 %, retenu ici pour limiter les faux "
                "positifs sur de nombreuses comparaisons simultanées)",
                "Test BILATÉRAL : un taux anormalement BAS est signalé aussi"],
        repere=(f"référence {fmt(100 * p2, 1) if p2 is not None else '—'} %"
                + (f" · Z = {fmt(z, 2)}" if z is not None else "")),
        stat=(f"Z = {fmt(z, 2)}" if z is not None else ""),
        alerte=al, vigilance=vg, portee=po))
    return out


# --------------------------------------------------------------------------
# NIVEAU 2 — Cohérence démographique (document, section 4)
# --------------------------------------------------------------------------
# Codes du questionnaire RSUe : M3 sexe (48 Lahy/homme, 49 Vavy/femme),
# M4 âge en années, M7 lien au chef de ménage (1 chef, 2 conjoint, 3 enfant,
# 4 parent du chef, 5 famille, 6 non-apparenté, 7 employé, 8 sans lien).
SEXE_H, SEXE_F = 48, 49
M7_CHEF, M7_ENFANT, M7_PARENT = 1, 3, 4

# Effectifs minimaux du niveau 2. Le document ne les fixe pas : ce sont les
# planchers en dessous desquels chaque statistique n'a pas de sens (χ² : 5
# individus attendus par chiffre terminal ⇒ 50 âges ; Myers : les dix chiffres
# doivent être représentés sur huit décennies ; IPAS : le document dit lui-même
# qu'il se calcule au niveau de la ZONE, pas de l'agent, d'où un plancher haut
# qui le laisse « nd » par agent et le fait remonter à la commune sur la fiche).
N_MIN2 = {"whipple": 50, "myers": 80, "ipas": 800, "chi2_terminal": 50,
          "icc": 10, "ks": 30, "sexratio": 30, "chi2_m7": 30, "m7_m4": 20}
# IPAS : plancher HAUT et assumé. L'indice repose sur 16 groupes quinquennaux
# × 2 sexes ; en dessous de ~800 individus, certaines cases tombent à quelques
# unités et le rapport de masculinité par groupe part dans tous les sens —
# mesuré sur les données du pilote : 560 individus donnaient IPAS = 474
# pour une grille qui s'arrête à « > 40 = douteux ». Ce n'était pas un diagnostic, mais
# du bruit. Le document dit lui-même que cet indice se lit au niveau de la
# ZONE, pas de l'agent.

SEUILS_VIGILANCE2 = {
    "whipple": "indice ≥ 110 (déclaration « approximative » de la grille ONU)",
    "myers": "Im > 20 (« préférence marquée, agent à surveiller »)",
    "ipas": "IPAS > 20 (qualité moyenne)",
    "chi2_terminal": "p-value < 0,10",
    "icc": "dispersion intra-agent < 60 % de celle des pairs",
    "ks": "D > D critique au seuil de 10 %",
    "sexratio": "rapport hors de l'intervalle [95 ; 105]",
    "chi2_m7": "p-value < 0,10",
    "m7_m4": "taux de violations > 2 %",
}


def _membres_ages(ms, lo=None, hi=None):
    """Âges (M4) des membres de ces ménages, bornés à [lo, hi] si demandé."""
    out = []
    for m in ms:
        for x in m.get("membres", ()):
            a = num(x.get("M4"))
            if a is None:
                continue
            a = int(a)
            if (lo is None or a >= lo) and (hi is None or a <= hi):
                out.append(a)
    return out


def _whipple(ages):
    """Indice de Whipple sur la tranche 23–62 ans (document, 4.1.1)."""
    tr = [a for a in ages if 23 <= a <= 62]
    if not tr:
        return None, 0, 0
    s5 = sum(1 for a in tr if a % 5 == 0)
    return (100.0 * 5 * s5 / len(tr)), s5, len(tr)


def _myers(ages):
    """Indice de Myers par sommes mélangées, âges 10–89 (document, 4.2.1)."""
    a10 = [a for a in ages if 10 <= a <= 89]
    if not a10:
        return None, []
    blend = []
    for d in range(10):
        s1 = sum(1 for a in a10 if a % 10 == d and 10 <= a <= 89)
        s2 = sum(1 for a in a10 if a % 10 == d and 20 <= a <= 89)
        blend.append(1 * s1 + 2 * s2)
    tot = sum(blend)
    if not tot:
        return None, []
    pct = [100.0 * b / tot for b in blend]
    return 0.5 * sum(abs(x - 10) for x in pct), pct


def _quinquennal(ms):
    """{groupe quinquennal: [hommes, femmes]}, groupes 0-4 … 75+."""
    g = defaultdict(lambda: [0, 0])
    for m in ms:
        for x in m.get("membres", ()):
            a, sx = num(x.get("M4")), num(x.get("M3"))
            if a is None or sx not in (SEXE_H, SEXE_F):
                continue
            k = min(int(a) // 5, 15)
            g[k][0 if sx == SEXE_H else 1] += 1
    return g


def _ipas(ms):
    """Indice combiné de précision âge-sexe (document, 4.3).

    ⚠️ Le document définit les deux composantes « répartition par âge » comme
    l'écart absolu moyen des DIFFÉRENCES SUCCESSIVES entre pourcentages de
    groupes quinquennaux. C'est cette définition-là qui est transcrite ici.
    L'indice classique des Nations Unies utilise, lui, des « age ratios »
    (2·P_g / (P_g-1 + P_g+1) comparés à 100) : les deux variantes ne donnent
    pas les mêmes valeurs, et les seuils 20/40 du document valent pour la
    variante du document."""
    g = _quinquennal(ms)
    if not g:
        return None, None, None, None
    ks = sorted(g)
    h = [g[k][0] for k in ks]
    f = [g[k][1] for k in ks]
    th, tf = sum(h), sum(f)
    if not th or not tf:
        return None, None, None, None
    ph = [100.0 * x / th for x in h]
    pf = [100.0 * x / tf for x in f]
    ecart = lambda v: (sum(abs(v[i + 1] - v[i]) for i in range(len(v) - 1))
                       / (len(v) - 1)) if len(v) > 1 else None
    sr = [(100.0 * a / b) for a, b in zip(h, f) if b]
    srs = ecart(sr)
    mh, mf = ecart(ph), ecart(pf)
    if srs is None or mh is None or mf is None:
        return None, None, None, None
    return (3 * srs + mh + mf), srs, mh, mf


def _chi2_terminal(ages):
    """χ² d'ajustement du chiffre terminal à la loi uniforme (document, 4.4)."""
    if not ages:
        return None, None, []
    obs = [sum(1 for a in ages if a % 10 == d) for d in range(10)]
    att = len(ages) / 10.0
    x2 = sum((o - att) ** 2 / att for o in obs)
    return x2, chi2_sf(x2, 9), obs


def _icc(pairs):
    """ANOVA à effet-agent sur `nbmembre` (document, 4.5).

    Renvoie (icc, F, p, CM_inter, CM_intra, n0) pour un ensemble d'unités
    comparables — c'est une statistique de GROUPE, pas d'individu."""
    grp = []
    for pr in pairs:
        v = [num(m.get("nbmembre")) for m in pr]
        v = [x for x in v if x is not None]
        if len(v) >= 2:
            grp.append(v)
    k = len(grp)
    N = sum(len(v) for v in grp)
    if k < 2 or N <= k:
        return (None,) * 6
    gm = sum(sum(v) for v in grp) / N
    sce_inter = sum(len(v) * (moyenne(v) - gm) ** 2 for v in grp)
    sce_intra = sum(sum((x - moyenne(v)) ** 2 for x in v) for v in grp)
    cm_inter = sce_inter / (k - 1)
    cm_intra = sce_intra / (N - k)
    if cm_intra <= 0:
        return (None,) * 6
    n0 = (N - sum(len(v) ** 2 for v in grp) / N) / (k - 1)
    va = (cm_inter - cm_intra) / n0 if n0 else 0.0
    icc = va / (va + cm_intra) if (va + cm_intra) else None
    f = cm_inter / cm_intra
    return icc, f, f_sf(f, k - 1, N - k), cm_inter, cm_intra, n0


def _ks(ech, ref):
    """Statistique D de Kolmogorov-Smirnov entre deux échantillons (4.6)."""
    if not ech or not ref:
        return None, None, None
    a, b = sorted(ech), sorted(ref)
    valeurs = sorted(set(a) | set(b))
    import bisect
    d = 0.0
    for v in valeurs:
        fa = bisect.bisect_right(a, v) / len(a)
        fb = bisect.bisect_right(b, v) / len(b)
        d = max(d, abs(fa - fb))
    fact = math.sqrt((len(a) + len(b)) / float(len(a) * len(b)))
    return d, 1.36 * fact, 1.22 * fact


def _chi2_ajustement(u_cnt, ref_cnt):
    """χ² d'ajustement d'une répartition catégorielle à celle de la référence.

    Les documents décrivent, en 4.8.1 comme en 6.1, un χ² d'INDÉPENDANCE
    « variable × agent » calculé sur tout le tableau agents × modalités.
    Réduit à UN agent — ce qu'exige une ligne de matrice — cela revient à
    comparer sa répartition à celle du reste de la référence : c'est la
    contribution de sa colonne au χ² d'ensemble. Générique : sert à M7
    (niveau 2) comme aux huit variables de logement (niveau 4)."""
    mods = sorted(set(ref_cnt) | set(u_cnt))
    n = sum(u_cnt.get(m, 0) for m in mods)
    tot = sum(ref_cnt.get(m, 0) for m in mods)
    if not n or not tot:
        return None, None, 0
    # Les modalités dont l'effectif ATTENDU est < 5 sont regroupées en une
    # cellule « autres » : sans cela le χ² n'est pas valide (règle de Cochran).
    cellules, obs_reste, att_reste = [], 0, 0.0
    for m in mods:
        att = n * ref_cnt.get(m, 0) / tot
        if att >= 5:
            cellules.append((u_cnt.get(m, 0), att))
        else:
            obs_reste += u_cnt.get(m, 0)
            att_reste += att
    if att_reste >= 5:
        cellules.append((obs_reste, att_reste))
    if len(cellules) < 2:
        return None, None, 0
    x2 = sum((o - a) ** 2 / a for o, a in cellules if a > 0)
    ddl = len(cellules) - 1
    return x2, chi2_sf(x2, ddl), ddl


def _violations_m7_m4(ms):
    """Violations logiques M7 × M4 (document, 4.8.2) : (violations, éligibles).

    ⚠️ Le document écrit qu'un PARENT du chef (M7 = 4) « devrait avoir un âge
    supérieur à celui du chef de ménage moins 12 ans ». Pris au mot, cela
    autoriserait un parent plus jeune de 11 ans que son enfant. La règle
    retenue ici est la lecture conservatrice symétrique de celle des enfants :
    un parent doit avoir AU MOINS 12 ans de plus que le chef. À faire arbitrer
    par les statisticiens du RSU."""
    viol = elig = 0
    for m in ms:
        mem = m.get("membres", ())
        chefs = [num(x.get("M4")) for x in mem if num(x.get("M7")) == M7_CHEF]
        chefs = [a for a in chefs if a is not None]
        if not chefs:
            continue
        age_chef = max(chefs)
        for x in mem:
            lien, a = num(x.get("M7")), num(x.get("M4"))
            if a is None or lien not in (M7_ENFANT, M7_PARENT):
                continue
            elig += 1
            if lien == M7_ENFANT and a > age_chef:
                viol += 1
            elif lien == M7_PARENT and a < age_chef + 12:
                viol += 1
    return viol, elig


def niveau2(echelons):
    """Section 4 du document — cohérence démographique.

    Neuf tests : Whipple, Myers, IPAS, χ² du chiffre terminal, effet-agent sur
    `nbmembre` (ICC/ANOVA), Kolmogorov-Smirnov, rapport de masculinité,
    χ² sur M7 et violations logiques M7 × M4."""
    out = []

    # --- 4.1 Indice de Whipple --------------------------------------------
    n_w = lambda ms: len(_membres_ages(ms, 23, 62))
    u, ref, n, po, _pairs = _escalade(echelons, n_w, N_MIN2["whipple"])
    v, s5, stot = _whipple(_membres_ages(u))
    al = bool(v is not None and v >= 125)
    vg = bool(v is not None and v >= 110)
    grille = ("très précises" if v is None or v < 105 else
              "précises" if v < 110 else "approximatives" if v < 125 else
              "grossières" if v < 175 else "très grossières")
    out.append(resultat(
        "4.1", "Indice de Whipple (attraction des âges en 0 et 5)",
        "Mesure l'attraction des âges déclarés vers les valeurs se terminant "
        "par 0 ou 5, sur la tranche 23–62 ans. Un âge estimé « à vue » se "
        "loge sur les multiples de 5 ; un âge déclaré, non.",
        "Whipple = [Σ âges finissant par 0 ou 5, 23–62 ans] / "
        "[(1/5) × Σ tous les âges 23–62 ans] × 100",
        v, "", n=n, n_min=N_MIN2["whipple"],
        calcul=[f"Unité mesurée : {po['libelle']}.",
                f"S₅ = {fmt(s5)} âges finissant par 0 ou 5 ; "
                f"S_total = {fmt(stot)} âges de 23 à 62 ans.",
                f"Whipple = ({fmt(s5)} / {fmt(stot)}) × 500 = {fmt(v, 1)}",
                f"Grille des Nations Unies : données {grille}."],
        conclusion=("→ Alerte : préférence de chiffre marquée, à auditer "
                    "(back-check terrain)." if al else
                    "→ Vigilance : déclaration approximative des âges." if vg
                    else "→ Pas de préférence de chiffre notable."),
        seuils=["< 105 très précises · 105–110 précises · 110–125 approximatives",
                "125–175 grossières · ≥ 175 très grossières (grille ONU)",
                "Seuil d'alerte retenu par le document : 125"],
        repere=f"grille ONU : données {grille} · 100 = aucun arrondi",
        alerte=al, vigilance=vg, portee=po))

    # --- 4.2 Indice de Myers ----------------------------------------------
    n_m = lambda ms: len(_membres_ages(ms, 10, 89))
    u, ref, n, po, _pairs = _escalade(echelons, n_m, N_MIN2["myers"])
    im, pct = _myers(_membres_ages(u))
    al = bool(im is not None and im > 30)
    vg = bool(im is not None and im > 20)
    qual = ("excellente" if im is None or im <= 5 else "bonne" if im <= 10 else
            "moyenne" if im <= 20 else "faible" if im <= 30 else "très faible")
    pire = (max(range(10), key=lambda d: abs(pct[d] - 10)) if pct else None)
    out.append(resultat(
        "4.2", "Indice de Myers (préférence par chiffre terminal)",
        "Évalue l'attraction ou la répulsion vis-à-vis de CHACUN des dix "
        "chiffres terminaux, et non des seuls 0 et 5. Il dit vers quel "
        "chiffre l'agent arrondit.",
        ["Blended(d) = 1×S1(d) + 2×S2(d) (sommes mélangées, âges 10–89)",
         "P(d) = Blended(d) / Σ Blended(d) × 100",
         "Im = ½ × Σ|P(d) − 10|, d = 0…9"],
        im, "", n=n, n_min=N_MIN2["myers"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} âge(s) de 10 à 89 ans."]
               + ([f"Chiffre le plus attracteur : {pire} "
                   f"({fmt(pct[pire], 1)} % au lieu de 10 %).",
                   "Répartition par chiffre terminal (%) : "
                   + ", ".join(f"{d}:{fmt(pct[d], 1)}" for d in range(10))]
                  if pct else [])
               + [f"Im = {fmt(im, 1)} → qualité {qual}."],
        conclusion=("→ Alerte : très forte suspicion d'estimation grossière "
                    "des âges." if al else
                    "→ Vigilance : préférence marquée, agent à surveiller."
                    if vg else "→ Préférence de chiffre dans la norme."),
        seuils=["0–5 excellente · 5–10 bonne · 10–20 moyenne",
                "> 20–30 faible (agent à surveiller) · > 30 très faible"],
        repere=f"qualité {qual} · 0 = aucune préférence de chiffre",
        alerte=al, vigilance=vg, portee=po))

    # --- 4.3 Indice combiné de précision âge-sexe (ONU) --------------------
    n_i = lambda ms: sum(1 for m in ms for x in m.get("membres", ())
                         if num(x.get("M4")) is not None
                         and num(x.get("M3")) in (SEXE_H, SEXE_F))
    u, ref, n, po, _pairs = _escalade(echelons, n_i, N_MIN2["ipas"])
    ip, srs, mh, mf = _ipas(u)
    al = bool(ip is not None and ip > 40)
    vg = bool(ip is not None and ip > 20)
    out.append(resultat(
        "4.3", "Indice combiné de précision âge-sexe (ONU)",
        "Diagnostic GLOBAL d'une zone : irrégularité de la répartition par "
        "âge des hommes, des femmes, et du rapport de masculinité par groupe "
        "quinquennal. Le document précise qu'il se calcule au niveau de la "
        "ZONE, l'échantillon d'un seul agent étant trop petit pour être "
        "stable par groupe quinquennal — d'où un « nd » fréquent par agent.",
        ["IPAS = 3 × (écart absolu moyen du rapport de masculinité)",
         "     + (écart absolu moyen de la répartition par âge — hommes)",
         "     + (écart absolu moyen de la répartition par âge — femmes)"],
        ip, "", n=n, n_min=N_MIN2["ipas"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} individu(s) "
                "avec âge et sexe.",
                f"Écart moyen du rapport de masculinité : {fmt(srs, 2)}",
                f"Écart moyen de la répartition par âge — hommes : {fmt(mh, 2)} ; "
                f"femmes : {fmt(mf, 2)}",
                f"IPAS = 3 × {fmt(srs, 2)} + {fmt(mh, 2)} + {fmt(mf, 2)} "
                f"= {fmt(ip, 1)}"],
        conclusion=("→ Alerte : qualité douteuse au niveau de la zone."
                    if al else "→ Vigilance : qualité moyenne." if vg
                    else "→ Données globalement fiables."),
        seuils=["< 20 données fiables · 20–40 qualité moyenne",
                "> 40 qualité douteuse au niveau de la zone"],
        repere="< 20 fiable · 20–40 moyen · > 40 douteux",
        alerte=al, vigilance=vg, portee=po))

    # --- 4.4 χ² sur le chiffre terminal de l'âge ---------------------------
    n_c = lambda ms: len(_membres_ages(ms))
    u, ref, n, po, _pairs = _escalade(echelons, n_c, N_MIN2["chi2_terminal"])
    ages_u = _membres_ages(u)
    x2, pv, obs = _chi2_terminal(ages_u)
    al = bool(pv is not None and pv < 0.05)
    vg = bool(pv is not None and pv < 0.10)
    out.append(resultat(
        "4.4", "χ² sur le chiffre terminal de l'âge",
        "Sous l'hypothèse d'absence de préférence, chaque chiffre terminal "
        "devrait apparaître dans 10 % des âges. Le test dit si l'écart "
        "observé est attribuable au hasard ou non.",
        ["χ² = Σ (O_d − E_d)² / E_d, d = 0…9",
         "E_d = n × 0,10 — degrés de liberté = 9"],
        x2, "", n=n, n_min=N_MIN2["chi2_terminal"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} âge(s).",
                f"Effectif attendu par chiffre : {fmt(n / 10.0, 1)}.",
                "Effectifs observés : " + ", ".join(
                    f"{d}:{fmt(obs[d])}" for d in range(10)) if obs else "",
                f"χ² = {fmt(x2, 2)} à 9 ddl → p = {fmt(pv, 4)} "
                f"(valeur critique à 5 % : 16,92)"],
        conclusion=("→ Alerte : préférence de chiffre statistiquement avérée."
                    if al else "→ Vigilance : écart proche du seuil."
                    if vg else "→ Répartition des chiffres compatible avec le hasard."),
        seuils=["p-value < 0,05 (χ² > 16,92 pour 9 ddl) : rejet de l'hypothèse "
                "d'absence de préférence de chiffre"],
        repere=f"p = {fmt(pv, 4)} · valeur critique 16,92 (9 ddl)",
        stat=(f"p = {fmt(pv, 4)}" if pv is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 4.5 Effet-agent sur nbmembre (ICC / ANOVA) ------------------------
    u, ref, n, po, pairs = _escalade(echelons, len, N_MIN2["icc"])
    icc, fv, pf, cmi, cma, n0 = _icc(pairs)
    va = [num(m.get("nbmembre")) for m in u]
    va = [x for x in va if x is not None]
    s_u = ecart_type(va)
    s_pairs = [x for x in (ecart_type([num(m.get("nbmembre")) for m in pr
                                       if num(m.get("nbmembre")) is not None])
                           for pr in pairs) if x]
    med_s = mediane(s_pairs)
    ratio = (100.0 * s_u / med_s) if (s_u is not None and med_s) else None
    al = bool(ratio is not None and ratio < 40)
    vg = bool(ratio is not None and ratio < 60)
    out.append(resultat(
        "4.5", "Effet-agent sur le nombre de membres (ICC / ANOVA)",
        "Répond à la question « nbmembre est-il rempli par tâtonnement ? ». "
        "L'ICC mesure, pour un GROUPE d'agents, la part de variance due à "
        "l'identité de l'agent. Le diagnostic INDIVIDUEL, lui, est celui de "
        "la figure 3 du document : un agent qui invente produit des valeurs "
        "anormalement peu dispersées. La colonne porte donc la dispersion de "
        "l'agent rapportée à celle de ses pairs ; l'ICC du groupe est rappelé "
        "dans le calcul.",
        ["ICC = σ²_agent / (σ²_agent + σ²_résiduelle)",
         "σ̂²_agent = (CM_inter − CM_intra) / n₀ ; σ̂²_résiduelle = CM_intra",
         "F = CM_inter / CM_intra (ddl = k−1 et N−k)",
         "Colonne = écart-type intra-agent ÷ médiane des écarts-types des pairs"],
        ratio, "% de la dispersion des pairs", n=n, n_min=N_MIN2["icc"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} ménage(s).",
                f"Écart-type de nbmembre pour cette unité : {fmt(s_u, 2)} ; "
                f"médiane des pairs : {fmt(med_s, 2)} → {fmt(ratio, 0)} %.",
                f"Groupe de référence : CM_inter = {fmt(cmi, 2)}, "
                f"CM_intra = {fmt(cma, 2)}, n₀ = {fmt(n0, 1)}.",
                f"ICC = {fmt(icc, 3)} ; F = {fmt(fv, 2)} → p = {fmt(pf, 4)}."],
        conclusion=("→ Alerte : dispersion anormalement faible — valeurs "
                    "vraisemblablement estimées ou recopiées." if al else
                    "→ Vigilance : dispersion basse au regard des pairs."
                    if vg else "→ Dispersion comparable à celle des pairs."),
        seuils=["ICC > 0,05 à 0,10 : effet-agent non négligeable (groupe)",
                "ICC > 0,20 : effet-agent fort, action corrective urgente",
                "Colonne (agent) : < 60 % de la dispersion des pairs = "
                "vigilance, < 40 % = alerte"],
        repere=(f"100 % = dispersion des pairs (σ {fmt(med_s, 2)}) · "
                f"ICC du groupe {fmt(icc, 3)}"),
        stat=(f"ICC {fmt(icc, 3)}" if icc is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 4.6 Kolmogorov-Smirnov sur la distribution des âges ---------------
    u, ref, n, po, _pairs = _escalade(echelons, n_c, N_MIN2["ks"])
    a_u, a_ref = _membres_ages(u), _membres_ages(ref)
    d, d5, d10 = _ks(a_u, a_ref)
    al = bool(d is not None and d5 is not None and d > d5)
    vg = bool(d is not None and d10 is not None and d > d10)
    out.append(resultat(
        "4.6", "Kolmogorov-Smirnov : distribution des âges",
        "Compare la distribution complète des âges de l'unité à celle de la "
        "référence. Plus général que le χ² : il est sensible à toute forme "
        "d'écart, pas seulement à la préférence de chiffre.",
        ["D = sup |F_unité(x) − F_référence(x)|",
         "D_critique(α) = c(α) × √[(n₁+n₂)/(n₁×n₂)], c = 1,36 à 5 %"],
        d, "", n=n, n_min=N_MIN2["ks"],
        calcul=[f"Unité mesurée : {po['libelle']} — n₁ = {fmt(len(a_u))} âge(s) ; "
                f"référence n₂ = {fmt(len(a_ref))}.",
                f"D observé = {fmt(d, 3)}.",
                f"D critique à 5 % = {fmt(d5, 3)} ; à 10 % = {fmt(d10, 3)}."],
        conclusion=("→ Alerte : la distribution des âges diffère "
                    "significativement de la référence." if al else
                    "→ Vigilance : écart de distribution proche du seuil."
                    if vg else "→ Distribution des âges conforme à la référence."),
        seuils=["D > D_critique(0,05) : rejet de l'égalité des distributions"],
        repere=f"D critique : {fmt(d5, 3)} à 5 %, {fmt(d10, 3)} à 10 %",
        stat=(f"p = {fmt(ks_p(d, len(a_u), len(a_ref)), 4)}"
              if d is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 4.7 Rapport de masculinité ----------------------------------------
    def _adultes(ms):
        h = f_ = 0
        for m in ms:
            for x in m.get("membres", ()):
                a, sx = num(x.get("M4")), num(x.get("M3"))
                if a is None or not (15 <= a <= 64):
                    continue
                if sx == SEXE_H:
                    h += 1
                elif sx == SEXE_F:
                    f_ += 1
        return h, f_
    n_s = lambda ms: sum(_adultes(ms))
    u, ref, n, po, _pairs = _escalade(echelons, n_s, N_MIN2["sexratio"])
    nh, nf = _adultes(u)
    sr = (100.0 * nh / nf) if nf else None
    # AUCUNE femme dans la tranche : le rapport n'est pas défini — mais c'est
    # l'anomalie la plus grave possible sur ce test, pas une absence de
    # résultat. On le classe donc en ALERTE sans valeur (la case est rouge et
    # vide, l'infobulle explique), au lieu de le cacher derrière un « nd » qui
    # se lirait comme « effectif insuffisant ».
    aucune_femme = bool(nf == 0 and nh)
    n_eff = n
    # La plage [90 ; 108] du document est une norme NATIONALE, calculée sur des
    # centaines de milliers d'individus. Un agent en observe environ 280 : à cet
    # effectif, l'écart-type d'échantillonnage du rapport dépasse à lui seul la
    # largeur de la plage, et 51 % des agents en sortaient sans rien avoir fait
    # de mal — la base entière est d'ailleurs à 91,7, presque au bord. On compare
    # donc la PROPORTION d'hommes de l'agent à celle du RESTE de sa zone par un
    # test de proportion : c'est le même écart, mais rapporté au bruit.
    rh, rf = _adultes(ref)
    rh, rf = rh - nh, rf - nf
    z_sr = None
    n1, n2 = nh + nf, rh + rf
    if n1 and n2 > 0 and rh >= 0 and rf >= 0:
        p1, p2 = nh / float(n1), rh / float(n2)
        pc = (nh + rh) / float(n1 + n2)
        den = math.sqrt(pc * (1 - pc) * (1 / n1 + 1 / n2)) if 0 < pc < 1 else 0
        if den:
            z_sr = (p1 - p2) / den
    sr_ref = (100.0 * rh / rf) if rf else None
    al = bool(aucune_femme or (z_sr is not None and abs(z_sr) > CAL["4.7.al"]))
    vg = bool(z_sr is not None and abs(z_sr) > CAL["4.7.vg"])
    grp = _quinquennal(u)
    det = ", ".join(f"{k*5}-{k*5+4}:{fmt(100.0*g[0]/g[1], 0)}"
                    for k, g in sorted(grp.items()) if g[1]) or "—"
    out.append(resultat(
        "4.7", "Rapport de masculinité (15–64 ans)",
        "Nombre d'hommes pour 100 femmes, comparé au reste de la zone. Un "
        "sexe sur- ou sous-déclaré éloigne l'agent de la composition observée "
        "chez ses voisins immédiats.",
        ["SR = (hommes / femmes) × 100",
         "Z = (p₁ − p₂) / √[ p̂(1−p̂)(1/n₁ + 1/n₂) ] sur la part d'hommes"],
        sr, "hommes / 100 femmes", n=n_eff, n_min=N_MIN2["sexratio"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(nh)} homme(s), "
                f"{fmt(nf)} femme(s) de 15 à 64 ans.",
                f"SR = {fmt(sr, 1)} hommes pour 100 femmes ; reste de la "
                f"zone : {fmt(sr_ref, 1)}.",
                f"Écart rapporté au bruit d'échantillonnage : Z = {fmt(z_sr, 2)}",
                f"Par groupe quinquennal : {det}"],
        conclusion=(f"→ Alerte : aucune femme déclarée sur {fmt(nh)} adulte(s) "
                    "— le rapport n'est pas définissable, l'anomalie est majeure."
                    if aucune_femme else
                    "→ Alerte : composition par sexe nettement différente de "
                    "celle du reste de la zone." if al else
                    "→ Vigilance : composition par sexe un peu décalée par "
                    "rapport à la zone." if vg else
                    "→ Composition par sexe conforme à la zone."),
        seuils=[f"|Z| > {fmt(CAL['4.7.al'], 1)} sur la part d'hommes face au "
                "reste de la zone (la plage [90 ; 108] du document est une "
                "norme nationale, inapplicable à l'effectif d'un agent)"],
        repere=f"zone : {fmt(sr_ref, 0)} h/100 f · {fmt(nh)} h / {fmt(nf)} f",
        stat=(f"Z = {fmt(z_sr, 2)}" if z_sr is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 4.8.1 χ² sur le lien au chef de ménage (M7) -----------------------
    def _cnt_m7(ms):
        c = defaultdict(int)
        for m in ms:
            for x in m.get("membres", ()):
                v_ = num(x.get("M7"))
                if v_ is not None:
                    c[int(v_)] += 1
        return c
    n_m7 = lambda ms: sum(_cnt_m7(ms).values())
    u, ref, n, po, _pairs = _escalade(echelons, n_m7, N_MIN2["chi2_m7"])
    cu, cr = _cnt_m7(u), _cnt_m7(ref)
    x2m, pvm, ddl = _chi2_ajustement(cu, cr)
    al = bool(pvm is not None and pvm < CAL["4.8.1.al"])
    vg = bool(pvm is not None and pvm < CAL["4.8.1.vg"])
    tot_r = sum(cr.values()) or 1
    det_m7 = ", ".join(
        f"{k}: {fmt(cu.get(k, 0))} obs / {fmt(n * cr[k] / tot_r, 1)} att."
        for k in sorted(cr)) or "—"
    out.append(resultat(
        "4.8.1", "χ² sur le lien au chef de ménage (M7)",
        "Dans une même zone, la structure familiale est censée être "
        "homogène. Un agent dont la répartition des liens de parenté s'écarte "
        "de la référence code différemment les modalités — compréhension "
        "inégale, ou remplissage par défaut (tout en « Fianakaviana »).",
        ["χ² = Σ (O_i − E_i)² / E_i sur les modalités de M7",
         "E_i = n × (part de la modalité i dans la référence)"],
        x2m, "", n=n, n_min=N_MIN2["chi2_m7"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} réponse(s) M7.",
                f"Observé / attendu par modalité — {det_m7}",
                f"χ² = {fmt(x2m, 2)} à {fmt(ddl)} ddl → p = {fmt(pvm, 4)}."],
        conclusion=("→ Alerte : codage des liens de parenté significativement "
                    "différent de la référence." if al else
                    "→ Vigilance : écart de codage proche du seuil." if vg
                    else "→ Répartition des liens conforme à la référence."),
        seuils=["p-value < 0,05 : la répartition diffère significativement"],
        repere=f"p = {fmt(pvm, 4)} · {fmt(ddl)} ddl",
        stat=(f"p = {fmt(pvm, 4)}" if pvm is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 4.8.2 Violations logiques M7 × M4 ---------------------------------
    n_v = lambda ms: _violations_m7_m4(ms)[1]
    u, ref, n, po, _pairs = _escalade(echelons, n_v, N_MIN2["m7_m4"])
    viol, elig = _violations_m7_m4(u)
    taux = (100.0 * viol / elig) if elig else None
    vr, er = _violations_m7_m4(ref)
    t_ref = (100.0 * vr / er) if er else None
    al = bool(taux is not None and taux > 3)
    vg = bool(taux is not None and taux > 2)
    out.append(resultat(
        "4.8.2", "Cohérence du lien de parenté avec l'âge (M7 × M4)",
        "Un enfant du chef de ménage ne peut pas être plus âgé que lui ; un "
        "parent du chef doit être nettement plus âgé. Le taux de violation de "
        "ces règles, par agent, mesure la cohérence du roster.",
        ["Violation si M7 = 3 (enfant) et âge > âge du chef",
         "Violation si M7 = 4 (parent) et âge < âge du chef + 12 ans",
         "Taux = violations / membres éligibles × 100"],
        taux, "%", n=n, n_min=N_MIN2["m7_m4"],
        calcul=[f"Unité mesurée : {po['libelle']}.",
                f"Membres éligibles (enfant ou parent du chef, âge connu) : "
                f"{fmt(elig)} ; violations : {fmt(viol)}.",
                f"Taux = {fmt(taux, 2)} % — référence : {fmt(t_ref, 2)} %."],
        conclusion=("→ Alerte : taux de violations logiques au-delà de 3 %."
                    if al else "→ Vigilance : taux de violations au-dessus de "
                    "2 %." if vg else "→ Roster logiquement cohérent."),
        seuils=["Taux de violations M7 × M4 > 2–3 % des rosters d'un agent "
                "(la moyenne d'équipe est généralement proche de 0 %)"],
        repere=f"référence {fmt(t_ref, 2)} % · seuil d'alerte 3 %",
        alerte=al, vigilance=vg, portee=po))
    return out


# --------------------------------------------------------------------------
# NIVEAU 3 — Cohérence « cycle de vie » (document, section 5)
# --------------------------------------------------------------------------
# Le document donne un RÉPERTOIRE de 13 règles logiques (5.1) puis un SCORE
# COMPOSITE qui les résume (5.2). Chaque règle devient ici une colonne portant
# le TAUX DE VIOLATION de l'unité, comparé à la référence par un test Z de
# proportion — « calculer, pour chaque règle, un taux de violation par agent,
# puis tester si ce taux diffère significativement de la moyenne de l'équipe ».
#
# ⚠️ Test UNILATÉRAL, contrairement à 3.6 : pour une règle de cohérence, seul
# un EXCÈS de violations est un défaut. Un agent qui en commet moins que ses
# pairs est simplement soigneux — le signaler n'aurait aucun sens.
N_MIN3 = {"regle": 20, "composite": 50}

M13_JAMAIS = 2          # M13 = Tsia : n'a jamais fréquenté l'école
M16_BIEN = 1            # M16a/M16b = Tsara : lit / écrit « bien »
M6_OUI = 1              # M6 = Eny : possède une CIN
M14_UNIVERSITE = 13     # M14 = Ambaratonga ambony (Université)
# CORRIGÉ le 2026-09-19 : la section 7.5 du document précise « activité
# agricole, d'élevage ou de PÊCHE en M19 (modalités 11, 12, 13) ». Le code 13
# (Pêcheur) manquait à la règle 5.1.13, qui comptait donc en violation les
# ménages de pêcheurs possédant du matériel de pêche.
M19_AGRICOLES = (11, 12, 13)   # Agriculteur, Éleveur, Pêcheur
AGE_CIN = 18            # âge légal de la CIN
AGE_EMPLOI = 15         # module emploi : filtre E, M4 > 15
AGE_INCAPACITE = 5      # module incapacités : filtre E, M4 > 5
AGE_UNIVERSITE = 17     # plancher plausible pour un niveau universitaire


def _annee(m):
    """Année d'enquête du ménage (CQ3, sinon start_ec)."""
    d = m.get("date") or ""
    try:
        return int(str(d)[:4])
    except (TypeError, ValueError):
        return None


def _mem(ms):
    for m in ms:
        for x in m.get("membres", ()):
            yield m, x


# --- Les treize règles du répertoire (document, 5.1) ----------------------
def _r_roster(ms):
    v = a = 0
    for m in ms:
        n = num(m.get("nbmembre"))
        if n is None:
            continue
        a += 1
        if len(m.get("membres", ())) != int(n):
            v += 1
    return v, a


def _r_taille_zd(ms):
    v = a = 0
    for m in ms:
        n, t = num(m.get("nbmembre")), num(m.get("taille_men_efkt"))
        if n is None or t is None or t <= 0:
            continue
        a += 1
        if n < t:
            v += 1
    return v, a


def _r_chef_unique(ms):
    v = a = 0
    for m in ms:
        mem = m.get("membres", ())
        if not mem:
            continue
        a += 1
        if sum(1 for x in mem if num(x.get("M7")) == M7_CHEF) != 1:
            v += 1
    return v, a


def _r_residence(ms):
    v = a = 0
    for _m, x in _mem(ms):
        r, age = num(x.get("M2a")), num(x.get("M4"))
        if r is None or age is None:
            continue
        a += 1
        if r > age:
            v += 1
    return v, a


def _r_age_annee(ms):
    v = a = 0
    for m, x in _mem(ms):
        age, an, ye = num(x.get("M4")), num(x.get("M4b")), _annee(m)
        if age is None or an is None or ye is None:
            continue
        a += 1
        # Année aberrante (M4b = 26 existe dans les données) ou écart > 1 an.
        if not (ye - 120 <= an <= ye) or abs((ye - an) - age) > 1:
            v += 1
    return v, a


def _r_cin_age(ms):
    v = a = 0
    for _m, x in _mem(ms):
        cin, age = num(x.get("M6")), num(x.get("M4"))
        if cin is None or age is None:
            continue
        a += 1
        if cin == M6_OUI and age < AGE_CIN:
            v += 1
    return v, a


def _r_cin_date(ms):
    v = a = 0
    for m, x in _mem(ms):
        d = txt(x.get("M6b"))[:10]
        enq = txt(m.get("CQ3"))[:10]
        if not d or not enq:
            continue
        a += 1
        if d > enq:
            v += 1
    return v, a


def _r_scolarite_annee(ms):
    v = a = 0
    for m, x in _mem(ms):
        an, ye = num(x.get("M15a")), _annee(m)
        if an is None or ye is None:
            continue
        a += 1
        if not (1900 < an <= ye):
            v += 1
    return v, a


def _r_niveau_age(ms):
    v = a = 0
    for _m, x in _mem(ms):
        niv, age = num(x.get("M14")), num(x.get("M4"))
        if niv is None or age is None:
            continue
        a += 1
        if niv == M14_UNIVERSITE and age < AGE_UNIVERSITE:
            v += 1
    return v, a


def _r_emploi_age(ms):
    v = a = 0
    for _m, x in _mem(ms):
        age = num(x.get("M4"))
        if age is None:
            continue
        a += 1
        if num(x.get("M19")) is not None and age <= AGE_EMPLOI:
            v += 1
    return v, a


def _r_incapacite_age(ms):
    v = a = 0
    for _m, x in _mem(ms):
        age = num(x.get("M4"))
        if age is None:
            continue
        a += 1
        if age <= AGE_INCAPACITE and any(
                num(x.get(c)) is not None for c in ("AUEM17a", "AUEM17b", "AUEM17c")):
            v += 1
    return v, a


def _r_alphabetisation(ms):
    v = a = 0
    for _m, x in _mem(ms):
        sco = num(x.get("M13"))
        lire, ecrire = num(x.get("M16a")), num(x.get("M16b"))
        if sco is None or (lire is None and ecrire is None):
            continue
        a += 1
        if sco == M13_JAMAIS and (lire == M16_BIEN or ecrire == M16_BIEN):
            v += 1
    return v, a


def _r_agri_biens(ms):
    v = a = 0
    for m in ms:
        biens = [num(m.get(c)) for c in COLS_AGRI]
        if all(b is None for b in biens):
            continue
        a += 1
        if any(b == 1 for b in biens) and not any(
                num(x.get("M19")) in M19_AGRICOLES for x in m.get("membres", ())):
            v += 1
    return v, a


# (numéro, titre, unité comptée, contrainte déjà dans le formulaire ?, fonction)
REGLES3 = [
    ("5.1.1", "Roster complet",
     "Longueur de la liste des membres = nbmembre.", "ménages",
     "Oui (V1)", _r_roster),
    ("5.1.2", "Taille minimale ZD",
     "nbmembre ≥ taille pré-chargée du ménage (taille_men_efkt).", "ménages",
     "Oui (V1)", _r_taille_zd),
    ("5.1.3", "Chef de ménage unique",
     "Un seul individu porte M7 = 1.", "ménages", "Oui (W1)", _r_chef_unique),
    ("5.1.4", "Durée de résidence",
     "M2a (années de résidence) ≤ M4 (âge).", "membres", "Oui (V1)",
     _r_residence),
    ("5.1.5", "Âge / année de naissance",
     "Cohérence arithmétique entre M4 et M4b (± 1 an), année plausible.",
     "membres", "Oui (M2, alerte)", _r_age_annee),
    ("5.1.6", "CIN et âge légal",
     "Détention de la CIN (M6) seulement si M4 ≥ 18 ans.", "membres",
     "Oui (filtre E)", _r_cin_age),
    ("5.1.7", "Date de délivrance CIN",
     "M6b (date d'obtention) ≤ CQ3 (date d'enquête).", "membres", "Oui (V1)",
     _r_cin_date),
    ("5.1.8", "Scolarisation vs âge",
     "Année de dernière fréquentation (M15a) > 1900 et ≤ année d'enquête.",
     "membres", "Oui (V1)", _r_scolarite_annee),
    ("5.1.9", "Niveau scolaire vs âge",
     "Niveau universitaire (M14) incompatible avec un âge < 17 ans.",
     "membres", "Non — ajouté ici", _r_niveau_age),
    ("5.1.10", "Emploi vs âge",
     "Le module emploi (M19) n'est rempli que si M4 > 15 ans.", "membres",
     "Oui (filtre E)", _r_emploi_age),
    ("5.1.11", "Incapacités vs âge",
     "Les incapacités (AUEM17a-c) ne sont remplies que si M4 > 5 ans.",
     "membres", "Oui (filtre E)", _r_incapacite_age),
    ("5.1.12", "Alphabétisation vs scolarisation",
     "Un individu jamais scolarisé (M13) qui lit ou écrit « Tsara ».",
     "membres", "Non — ajouté ici", _r_alphabetisation),
    ("5.1.13", "Emploi agricole / biens",
     "Biens agricoles déclarés sans aucun membre agriculteur ou éleveur.",
     "ménages", "Non — ajouté ici", _r_agri_biens),
]

SEUILS_VIGILANCE3 = {n: "Z > 1,96 (excès de violations, seuil à 5 %)"
                     for n, _t, _p, _u, _c, _f in REGLES3}
SEUILS_VIGILANCE3["5.2"] = "score > Q3 + 1,5×IQR des pairs (outlier modéré)"


# Comptages déjà faits, le temps d'UNE commune (niveaux 3 et 5). Les treize règles sont
# évaluées sur la même référence et sur les mêmes pairs pour chacun des ~200
# agents d'une commune : sans cache, la référence est reparcourue 200 fois par
# règle (mesuré : 2,2 s pour le district 1106, contre 0,4 s avec).
# ⚠️ La clé contient `id(liste)`, ce qui n'est sûr que pour une liste VIVANTE.
# Seules le sont, pendant toute la commune, la RÉFÉRENCE (`ms`, tenue par
# `par_commune`) et les PAIRS (tenus par `par_ae_com`). Les listes d'unités,
# elles, sont reconstruites à chaque chef d'équipe : une liste libérée peut
# voir son `id` réattribué à la suivante, et le cache rendrait alors les
# comptages du mauvais agent. C'est arrivé — trois cases avaient changé
# d'état entre la version avec et sans cache. D'où `cache=False` par défaut :
# on ne mémorise que ce qui est explicitement stable, et l'unité (quelques
# ménages) est de toute façon peu coûteuse à recompter.
_CACHE_ZONE = {}


def _compte(fn, ms, cache=False):
    """(violations, applications) d'une règle sur ces ménages.

    `cache=True` UNIQUEMENT pour la référence et les pairs (cf. ci-dessus)."""
    if not cache:
        return fn(ms)
    cle = (fn.__name__, id(ms), len(ms))
    r = _CACHE_ZONE.get(cle)
    if r is None:
        r = _CACHE_ZONE[cle] = fn(ms)
    return r


def _memo(nom, ms, calcul):
    """Mémorise un calcul de ZONE le temps d'une commune.

    Mêmes règles que `_compte` : réservé aux listes vivantes pendant toute la
    commune (la référence), jamais aux listes d'unités."""
    cle = (nom, id(ms), len(ms))
    r = _CACHE_ZONE.get(cle)
    if r is None:
        r = _CACHE_ZONE[cle] = calcul()
    return r


def _viol_app(ms, cache=False):
    """Totaux des treize règles pour une unité."""
    v = a = 0
    for _n, _t, _p, _u, _c, f in REGLES3:
        x, y = _compte(f, ms, cache)
        v += x
        a += y
    return v, a


def niveau3(echelons):
    """Section 5 du document — cohérence « cycle de vie ».

    Treize règles logiques, chacune en taux de violation comparé à la
    référence, puis le score composite d'incohérence (5.2) jugé par la règle
    de Tukey sur la distribution des pairs."""
    out = []
    tot_v = tot_a = 0

    for num_, titre, principe, unite_cpt, contrainte, fn in REGLES3:
        u, ref, n, po, _pairs = _escalade(
            echelons, lambda ms, f=fn: f(ms)[1], N_MIN3["regle"])
        v1, n1 = fn(u)
        vt, nt = _compte(fn, ref, cache=True)
        v2, n2 = vt - v1, nt - n1
        tot_v += v1
        tot_a += n1
        taux = (100.0 * v1 / n1) if n1 else None
        t_ref = (100.0 * v2 / n2) if n2 else None
        z = None
        if n1 and n2:
            p1, p2 = v1 / n1, v2 / n2
            pc = (v1 + v2) / (n1 + n2)
            den = math.sqrt(pc * (1 - pc) * (1 / n1 + 1 / n2)) if 0 < pc < 1 else 0
            if den:
                z = (p1 - p2) / den
        al = bool(z is not None and z > 2.58)
        vg = bool(z is not None and z > 1.96)
        out.append(resultat(
            num_, titre,
            principe + " Le document en fait un indicateur statistique : le "
            "taux de violation de l'unité est comparé à celui du reste de la "
            "référence par un test Z de proportion. Contrainte de saisie dans "
            f"le formulaire : {contrainte}.",
            ["Taux_violation = violations / cas applicables × 100",
             "Z = (p₁ − p₂) / √[ p̂(1−p̂)(1/n₁ + 1/n₂) ] — unilatéral"],
            taux, "%", n=n, n_min=N_MIN3["regle"],
            calcul=[f"Unité mesurée : {po['libelle']}.",
                    f"Cas applicables : {fmt(n1)} {unite_cpt} ; "
                    f"violations : {fmt(v1)} → {fmt(taux, 2)} %.",
                    f"Reste de la référence : {fmt(v2)} / {fmt(n2)} "
                    f"= {fmt(t_ref, 2)} %.",
                    (f"Z = {fmt(z, 2)}" if z is not None else
                     "Z non calculable (aucune variabilité dans la référence).")],
            conclusion=("→ Alerte : cette règle est violée significativement "
                        "plus souvent que dans la référence." if al else
                        "→ Vigilance : excès de violations au regard de la "
                        "référence." if vg else
                        "→ Taux de violation comparable à la référence."),
            seuils=["Z > 2,58 (excès significatif au seuil de 1 %)",
                    "Test UNILATÉRAL : seul un excès de violations est signalé",
                    f"Règle déjà contrainte dans le formulaire : {contrainte}"],
            repere=(f"référence {fmt(t_ref, 2)} % · {fmt(n1)} cas applicables"
                    + (f" · contrainte {contrainte}" if contrainte.startswith("Oui")
                       else "")),
            stat=(f"Z = {fmt(z, 2)}" if z is not None else ""),
            alerte=al, vigilance=vg, portee=po))

    # --- 5.2 Score composite d'incohérence --------------------------------
    u, ref, n, po, pairs = _escalade(
        echelons, lambda ms: _viol_app(ms)[1], N_MIN3["composite"])
    v1, n1 = _viol_app(u)

    score = (100.0 * v1 / n1) if n1 else None
    # Distribution des scores des PAIRS : c'est elle qui fixe les seuils.
    scores_pairs, groupes = [], []
    for pr in pairs:
        pv, pa = _viol_app(pr, cache=True)
        if pa >= N_MIN3["composite"]:
            scores_pairs.append(100.0 * pv / pa)
        if pa:
            groupes.append((pv, pa))
    q1, q3, iqr, s_mod, s_ext = tukey(scores_pairs)
    h, ph, ddl = kruskal_binaire(groupes)
    al = bool(score is not None and s_ext is not None and score > s_ext)
    vg = bool(score is not None and s_mod is not None and score > s_mod)
    out.append(resultat(
        "5.2", "Score composite d'incohérence",
        "Résume les treize règles en un seul nombre : la part des cas "
        "applicables qui sont violés, toutes règles confondues. Sa "
        "distribution étant très asymétrique (la plupart des agents près de "
        "zéro, une minorité très haut), le document écarte l'ANOVA au profit "
        "du test non paramétrique de Kruskal-Wallis pour le groupe, et d'une "
        "règle de Tukey pour désigner les agents individuellement.",
        ["Score = (Σ violations) / (Σ cas applicables) × 100",
         "H = [12 / (N(N+1))] × Σ (R_a² / n_a) − 3(N+1), ddl = k−1",
         "Outlier : score > Q3 + 1,5×IQR (modéré) ou Q3 + 3×IQR (extrême)"],
        score, "%", n=n, n_min=N_MIN3["composite"],
        calcul=[f"Unité mesurée : {po['libelle']}.",
                f"{fmt(v1)} violation(s) sur {fmt(n1)} cas applicables "
                f"= {fmt(score, 2)} %.",
                f"Pairs ({fmt(len(scores_pairs))} unités comparables) : "
                f"Q1 = {fmt(q1, 2)} %, Q3 = {fmt(q3, 2)} %, "
                f"IQR = {fmt(iqr, 2)}.",
                f"Seuils de Tukey : modéré > {fmt(s_mod, 2)} %, "
                f"extrême > {fmt(s_ext, 2)} %.",
                (f"Kruskal-Wallis sur le groupe : H = {fmt(h, 2)} à {fmt(ddl)} "
                 f"ddl → p = {fmt(ph, 4)}." if h is not None else
                 "Kruskal-Wallis non calculable (aucune variabilité).")],
        conclusion=("→ Alerte : outlier EXTRÊME au regard de ses pairs — "
                    "audit prioritaire." if al else
                    "→ Vigilance : outlier modéré au regard de ses pairs."
                    if vg else "→ Score d'incohérence dans la norme des pairs."),
        seuils=["Score > Q3 + 1,5×IQR (règle de Tukey) → outlier modéré",
                "Score > Q3 + 3×IQR → outlier extrême, audit prioritaire",
                "Kruskal-Wallis (groupe) : H > χ²(0,05 ; k−1)"],
        repere=(f"pairs : Q3 = {fmt(q3, 2)} %, seuil extrême {fmt(s_ext, 2)} %"
                + (f" · H du groupe {fmt(h, 1)}" if h is not None else "")),
        stat=(f"Q3+3·IQR = {fmt(s_ext, 2)}" if s_ext is not None else ""),
        alerte=al, vigilance=vg, portee=po))
    return out


VIGILANCE_PAR_TEST.update(SEUILS_VIGILANCE3)


# --------------------------------------------------------------------------
# NIVEAU 4 — Caractéristiques du logement H1–H10 (document, section 6)
# --------------------------------------------------------------------------
# Le document décrit CINQ méthodes (6.1 à 6.5), dont les trois premières
# s'appliquent « séparément » aux huit variables catégorielles de logement.
# Une colonne par (méthode × variable) ferait 27 colonnes pour ce seul
# niveau : chaque méthode occupe donc UNE colonne, qui porte la variable la
# plus défavorable des huit, et la fiche détaillée donne le détail des huit.
# Les huit variables sont les clés de HAFA (H1, H4, H5, H6, H7, H8, H9, H10) ;
# H2 (nombre de pièces), numérique, a ses deux tests propres (6.4.1 et 6.4.2).
VARS_H = ("H1", "H4", "H5", "H6", "H7", "H8", "H9", "H10")

N_MIN4 = {"chi2_h": 30, "entropie": 20, "bray": 20,
          "grubbs": 10, "heaping": 20, "poly": 20}

SEUILS_VIGILANCE4 = {
    "6.1": "au moins une variable H significative (Bonferroni × 8)",
    "6.2": "entropie < 65 % de H_max alors que la zone reste ≥ 75 %",
    "6.3": "distance de Bray-Curtis > 0,35",
    "6.4.1": "G > valeur critique de Grubbs au seuil de 10 %",
    "6.4.2": "Z > 1,96 sur la concentration de H2",
    "6.5": "corrélation H1×H5 plus faible que la zone, p < 0,10",
}

# Échelles ORDINALES de « standing » du logement, pour la corrélation 6.5.
# ⚠️ Le document ne donne qu'un exemple, pour H1 : « vato/parpaing > biriky >
# torchis > bois/feuilles > bozaka ». Cet ordre est respecté ; la place des
# modalités qu'il ne cite pas (tôle, planches, matériaux de récupération) et
# les échelles de H4, H5 et H6 sont un classement de bon sens — À FAIRE
# ARBITRER par les statisticiens du RSU. La modalité « Hafa » est exclue :
# elle n'a pas de rang. Rang élevé = matériau de meilleure qualité.
ORDRE_H = {
    "H1": {1: 8, 2: 7, 5: 6, 7: 5, 3: 4, 4: 3, 6: 2, 8: 1},
    "H4": {7: 7, 6: 6, 5: 5, 4: 4, 3: 3, 2: 2, 1: 1},
    "H5": {1: 6, 3: 5, 2: 4, 5: 3, 4: 2, 6: 1},
    "H6": {1: 8, 7: 7, 6: 6, 8: 5, 2: 4, 4: 3, 3: 2, 5: 1},
}


def _cnt_h(ms, var):
    """Effectifs par modalité d'une variable de logement, « Hafa » compris."""
    c = defaultdict(int)
    for m in ms:
        v = num(m.get(var))
        if v is not None:
            c[int(v)] += 1
    return c


def _props(cnt):
    tot = sum(cnt.values())
    return {k: v / float(tot) for k, v in cnt.items()} if tot else {}


def _h2(ms):
    """Valeurs de H2 (nombre de pièces) renseignées."""
    out = []
    for m in ms:
        v = num(m.get("H2"))
        if v is not None:
            out.append(float(v))
    return out


def niveau4(echelons):
    """Section 6 du document — caractéristiques du logement.

    Le fil conducteur : dans une même zone, les matériaux et les
    infrastructures varient peu d'un ménage à l'autre. Tout écart marqué entre
    un agent et sa zone sur ces variables est donc, par construction, un
    effet-agent plutôt qu'un effet de terrain."""
    out = []

    # --- 6.1 χ² d'indépendance agent × modalité, sur les huit variables ----
    nb_men = lambda ms: sum(1 for m in ms
                            if any(num(m.get(v)) is not None for v in VARS_H))
    u, ref, n, po, _pairs = _escalade(echelons, nb_men, N_MIN4["chi2_h"])
    detail, signif, pire = [], 0, None
    for var in VARS_H:
        cu, cr = _cnt_h(u, var), _cnt_h(ref, var)
        x2, pv, ddl = _chi2_ajustement(cu, cr)
        if pv is None:
            detail.append(f"{var} : non calculable")
            continue
        # Bonferroni : huit comparaisons simultanées sur la même unité.
        pc = min(1.0, pv * len(VARS_H))
        detail.append(f"{var} : χ² = {fmt(x2, 1)} ({fmt(ddl)} ddl), "
                      f"p = {fmt(pv, 4)}, corrigée {fmt(pc, 4)}")
        if pc < 0.05:
            signif += 1
        if pire is None or pc < pire[1]:
            pire = (var, pc, x2)
    al = signif >= 2
    vg = signif >= 1
    out.append(resultat(
        "6.1", "χ² agent × modalité sur les 8 variables de logement",
        "Dans une même zone, murs, sol, toit, éclairage, eau, toilettes, "
        "déchets et statut d'occupation varient peu. Si la répartition d'un "
        "agent s'écarte de celle de sa zone, c'est lui qui varie, pas le "
        "terrain. La colonne compte les variables dont l'écart est "
        "significatif après correction de Bonferroni (8 comparaisons).",
        ["χ² = Σ (O_i − E_i)² / E_i sur les modalités de la variable",
         "p corrigée = p × 8 (Bonferroni)"],
        float(signif) if pire else None, "variable(s) sur 8",
        n=n, n_min=N_MIN4["chi2_h"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} ménage(s)."] + detail,
        conclusion=("→ Alerte : plusieurs variables de logement sont codées "
                    "différemment du reste de la zone." if al else
                    "→ Vigilance : une variable de logement s'écarte de la zone."
                    if vg else "→ Répartitions conformes à celles de la zone."),
        seuils=["p corrigée < 0,05 pour au moins 2 des 8 variables : alerte",
                "χ² d'indépendance du document, réduit à un agent"],
        repere=(f"plus forte divergence : {pire[0]} (p corrigée "
                f"{fmt(pire[1], 4)})" if pire else "aucune variable calculable"),
        stat=(f"{signif}/8 signif." if pire else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 6.2 Entropie de Shannon ------------------------------------------
    u, ref, n, po, _pairs = _escalade(echelons, nb_men, N_MIN4["entropie"])
    detail, pires = [], []
    for var in VARS_H:
        cu, cr = _cnt_h(u, var), _cnt_h(ref, var)
        if not cu or not cr:
            continue
        nb_mod = max(len(cr), 2)
        hmax = math.log(nb_mod, 2)
        hu, hz = entropie(list(cu.values())), entropie(list(cr.values()))
        if hu is None or hz is None or not hmax:
            continue
        ru, rz = 100.0 * hu / hmax, 100.0 * hz / hmax
        detail.append(f"{var} : H = {fmt(hu, 2)} bits sur H_max = "
                      f"{fmt(hmax, 2)} ({fmt(ru, 0)} %) ; zone {fmt(rz, 0)} %")
        pires.append((ru, rz, var))
    pires.sort()
    v = pires[0][0] if pires else None
    # Seuil du document, phrase entière : « H(agent) < 50 % de H_max, ALORS QUE
    # les agents voisins de la même zone sont proches de H_max ». Sans la
    # seconde condition, une zone réellement homogène — ce que le document
    # dit lui-même être la norme — ferait virer tout le monde au rouge.
    al = bool(pires and pires[0][0] < 50 and pires[0][1] >= 75)
    vg = bool(pires and pires[0][0] < 65 and pires[0][1] >= 75)
    out.append(resultat(
        "6.2", "Entropie de Shannon des réponses de logement",
        "Un agent qui observe vraiment produit des réponses variées ; un "
        "agent qui recopie la même modalité produit une entropie proche de "
        "zéro. La colonne porte la variable la plus concentrée des huit, en "
        "pourcentage de l'entropie maximale.",
        ["H = − Σ p_k × log₂(p_k)",
         "H_max = log₂(nombre de modalités observées dans la zone)"],
        v, "% de H_max", n=n, n_min=N_MIN4["entropie"],
        calcul=[f"Unité mesurée : {po['libelle']}."] + detail,
        conclusion=("→ Alerte : réponses très concentrées sur une modalité, "
                    "alors que la zone reste variée — remplissage par défaut."
                    if al else
                    "→ Vigilance : réponses plus concentrées que dans la zone."
                    if vg else "→ Diversité des réponses comparable à la zone."),
        seuils=["H(agent) < 50 % de H_max alors que la zone est proche de H_max",
                "La seconde condition est indispensable : une zone réellement "
                "homogène a une entropie basse pour tout le monde"],
        repere=(f"variable la plus concentrée : {pires[0][2]} "
                f"(zone à {fmt(pires[0][1], 0)} % de H_max)" if pires else ""),
        stat=(f"zone {fmt(pires[0][1], 0)} %" if pires else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 6.3 Distance de Bray-Curtis agent / zone -------------------------
    u, ref, n, po, _pairs = _escalade(echelons, nb_men, N_MIN4["bray"])
    detail, bcs = [], []
    for var in VARS_H:
        cu, cr = _cnt_h(u, var), _cnt_h(ref, var)
        # La zone, c'est le reste : on retire l'unité de la référence.
        reste = {k: cr.get(k, 0) - cu.get(k, 0) for k in set(cr) | set(cu)}
        reste = {k: x for k, x in reste.items() if x > 0}
        bc = bray_curtis(_props(cu), _props(reste))
        if bc is None:
            continue
        detail.append(f"{var} : BC = {fmt(bc, 3)}")
        bcs.append((bc, var))
    bcs.sort(reverse=True)
    v = bcs[0][0] if bcs else None
    al = bool(v is not None and v > CAL["6.3.al"])
    vg = bool(v is not None and v > CAL["6.3.vg"])
    out.append(resultat(
        "6.3", "Distance de Bray-Curtis au reste de la zone",
        "Compare directement la distribution des réponses de l'unité à celle "
        "du RESTE de sa zone (elle-même exclue), variable par variable. "
        "0 = distributions identiques, 1 = aucune modalité en commun. La "
        "colonne porte la variable la plus éloignée des huit.",
        ["BC = Σ|p_k,agent − p_k,zone| / Σ(p_k,agent + p_k,zone)"],
        v, "", n=n, n_min=N_MIN4["bray"],
        calcul=[f"Unité mesurée : {po['libelle']}."] + detail,
        conclusion=("→ Alerte : distribution très éloignée de celle de la zone."
                    if al else "→ Vigilance : distribution sensiblement "
                    "différente de la zone." if vg else
                    "→ Distribution proche de celle de la zone."),
        seuils=["Distance de Bray-Curtis > 0,5 (seuil du document)"],
        repere=(f"variable la plus éloignée : {bcs[0][1]} · 0 = identique, "
                "1 = disjointe" if bcs else ""),
        stat=(f"sur {bcs[0][1]}" if bcs else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 6.4.1 Grubbs sur H2 (nombre de pièces) ---------------------------
    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: len(_h2(ms)),
                                      N_MIN4["grubbs"])
    vals = _h2(u)
    g = ecart = extreme = None
    gc5 = gc10 = None
    if len(vals) >= 3:
        mo, sd = moyenne(vals), ecart_type(vals)
        if sd:
            ecarts = [(abs(x - mo) / sd, x) for x in vals]
            g, extreme = max(ecarts)
            gc5, gc10 = grubbs_critique(len(vals), 0.05), grubbs_critique(len(vals), 0.10)
            ecart = mo
    # Grubbs suppose une variable à peu près NORMALE. H2 ne l'est pas : sur
    # les données RSU d'octobre 2025, 75 % des ménages déclarent 1 pièce et
    # 21 % en déclarent 2. Dans une distribution aussi concentrée, le moindre 4-pièces
    # devient « aberrant » au sens de Grubbs, qui désignait ainsi 46 % des
    # agents. On conserve la statistique du document, mais on exige en plus que
    # la valeur extrême soit INVRAISEMBLABLE dans l'habitat observé : c'est
    # cette conjonction qui fait la couleur, et elle s'explique à un agent en
    # une phrase (« vous avez saisi un logement de 15 pièces »).
    al = bool(g is not None and gc5 is not None and g > gc5
              and extreme is not None and extreme >= CAL["6.4.1.al"])
    vg = bool(g is not None and gc10 is not None and g > gc10
              and extreme is not None and extreme >= CAL["6.4.1.vg"])
    out.append(resultat(
        "6.4.1", "Grubbs sur H2 : valeur aberrante du nombre de pièces",
        "Détecte, parmi les réponses d'une unité, une valeur de H2 "
        "statistiquement aberrante au regard de ses propres réponses — "
        "erreur de saisie, ou logement réellement atypique à documenter.",
        ["G = max |x_i − x̄| / s",
         "G_c = [(n−1)/√n] × √[ t²(α/2n, n−2) / (n−2+t²(α/2n, n−2)) ]"],
        g, "", n=n, n_min=N_MIN4["grubbs"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(vals))} valeur(s).",
                f"Moyenne {fmt(ecart, 2)} pièce(s), écart-type "
                f"{fmt(ecart_type(vals), 2)}.",
                f"Valeur la plus extrême : {fmt(extreme, 0)} pièce(s) → "
                f"G = {fmt(g, 2)}.",
                f"G critique : {fmt(gc5, 2)} à 5 %, {fmt(gc10, 2)} à 10 %."],
        conclusion=(f"→ Alerte : {fmt(extreme, 0)} pièces, valeur "
                    "invraisemblable et statistiquement aberrante — à "
                    "vérifier auprès de l'agent." if al else
                    f"→ Vigilance : {fmt(extreme, 0)} pièces, valeur haute à "
                    "confirmer." if vg else
                    "→ Aucun nombre de pièces invraisemblable."),
        seuils=[f"G > G_critique(0,05 ; n) ET valeur extrême ≥ "
                f"{fmt(CAL['6.4.1.al'], 0)} pièces",
                "La seconde condition est indispensable : 96 % des logements "
                "de la base ont 1 ou 2 pièces, Grubbs seul dénonçait 46 % des "
                "agents"],
        repere=(f"valeur extrême {fmt(extreme, 0)} pièces · "
                f"critique {fmt(gc5, 2)}" if g is not None else ""),
        stat=(f"G_c = {fmt(gc5, 2)}" if gc5 is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 6.4.2 Concentration de H2 (heaping) ------------------------------
    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: len(_h2(ms)),
                                      N_MIN4["heaping"])
    cu, cr = _cnt_h(u, "H2"), _cnt_h(ref, "H2")
    n1 = sum(cu.values())
    mode = max(cu, key=lambda k: cu[k]) if cu else None
    p1 = (cu[mode] / float(n1)) if (mode is not None and n1) else None
    n2 = sum(cr.values()) - n1
    x2_ = (cr.get(mode, 0) - cu.get(mode, 0)) if mode is not None else 0
    p2 = (x2_ / float(n2)) if n2 else None
    z = None
    if p1 is not None and p2 is not None and n1 and n2:
        pc = (cu[mode] + x2_) / float(n1 + n2)
        den = math.sqrt(pc * (1 - pc) * (1 / n1 + 1 / n2)) if 0 < pc < 1 else 0
        if den:
            z = (p1 - p2) / den
    al = bool(z is not None and z > CAL["6.4.2.al"])
    vg = bool(z is not None and z > CAL["6.4.2.vg"])
    out.append(resultat(
        "6.4.2", "Concentration de H2 (remplissage par défaut)",
        "Le document demande de compléter Grubbs par un contrôle de "
        "« heaping » : une convergence excessive vers une valeur unique — "
        "« 3 pièces » pour presque tous les ménages — est aussi révélatrice "
        "qu'une valeur extrême isolée. La colonne porte la part de la valeur "
        "la plus fréquente, comparée au reste de la zone.",
        ["p₁ = part de la valeur de H2 la plus fréquente chez l'unité",
         "Z = (p₁ − p₂) / √[ p̂(1−p̂)(1/n₁ + 1/n₂) ] — unilatéral"],
        (100.0 * p1) if p1 is not None else None, "%",
        n=n, n_min=N_MIN4["heaping"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n1)} réponse(s).",
                f"Valeur la plus fréquente : {fmt(mode, 0)} pièce(s), "
                f"{fmt(cu.get(mode, 0))} fois → {fmt(100.0 * p1 if p1 else None, 1)} %.",
                f"Reste de la zone sur cette même valeur : "
                f"{fmt(100.0 * p2 if p2 is not None else None, 1)} %.",
                f"Z = {fmt(z, 2)}"],
        conclusion=("→ Alerte : une seule valeur de H2 domine anormalement."
                    if al else "→ Vigilance : concentration supérieure à la zone."
                    if vg else "→ Dispersion de H2 comparable à la zone."),
        seuils=[f"Z > {fmt(CAL['6.4.2.al'], 2)} sur la part de la valeur "
                "dominante",
                "Test UNILATÉRAL : seul un EXCÈS de concentration est signalé",
                "Le seuil de 2,58 du document désignait 17 % des agents : "
                "96 % des logements de la base ayant 1 ou 2 pièces, une forte "
                "concentration est ici la norme et non l'exception"],
        repere=(f"valeur dominante {fmt(mode, 0)} pièces · zone "
                f"{fmt(100.0 * p2 if p2 is not None else None, 1)} %"
                if mode is not None else ""),
        stat=(f"Z = {fmt(z, 2)}" if z is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 6.5 Cohérence ordinale H1 × H5 -----------------------------------
    def _paires(ms):
        xs, ys = [], []
        for m in ms:
            a, b = num(m.get("H1")), num(m.get("H5"))
            ra = ORDRE_H["H1"].get(int(a)) if a is not None else None
            rb = ORDRE_H["H5"].get(int(b)) if b is not None else None
            if ra is not None and rb is not None:
                xs.append(ra)
                ys.append(rb)
        return xs, ys

    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: len(_paires(ms)[0]),
                                      N_MIN4["poly"])
    xu, yu = _paires(u)
    xr, yr = _paires(ref)
    # Zone = le reste : on retire les paires de l'unité de celles de la référence.
    reste = len(xr) - len(xu)
    ru = spearman(xu, yu)
    rz = spearman(xr, yr)
    z, pv = fisher_z_diff(ru, len(xu), rz, max(reste, 0))
    al = bool(pv is not None and pv < 0.05)
    vg = bool(pv is not None and pv < 0.10)
    out.append(resultat(
        "6.5", "Cohérence des matériaux : corrélation H1 × H5",
        "Un logement aux murs en dur a statistiquement plus de chances "
        "d'avoir un toit en tôle qu'un logement en bozaka. Une corrélation "
        "nettement plus faible que celle de la zone signale des associations "
        "de matériaux improbables — remplissage peu attentif au logement "
        "réellement observé.",
        ["Corrélation de rang entre les échelles ordinales de H1 et H5",
         "z = (z₁ − z₂) / √(1/(n₁−3) + 1/(n₂−3)), z = ½ ln[(1+r)/(1−r)]"],
        ru, "", n=n, n_min=N_MIN4["poly"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(xu))} ménage(s) "
                "avec murs ET toit classables.",
                f"Corrélation de l'unité : {fmt(ru, 3)} ; zone : {fmt(rz, 3)}.",
                f"Différence (Fisher z) : z = {fmt(z, 2)} → p = {fmt(pv, 4)}.",
                "⚠️ Le document demande une corrélation POLYCHORIQUE estimée "
                "par maximum de vraisemblance ; c'est une corrélation de rang "
                "(Spearman) sur les mêmes échelles ordinales qui est calculée "
                "ici — à arbitrer."],
        conclusion=("→ Alerte : cohérence murs/toit significativement plus "
                    "faible que dans la zone." if al else
                    "→ Vigilance : cohérence murs/toit inférieure à la zone."
                    if vg else "→ Cohérence murs/toit comparable à la zone."),
        seuils=["Corrélation de l'agent significativement inférieure à celle "
                "de la zone (test de Fisher z, 5 %)"],
        repere=(f"zone : {fmt(rz, 3)} · échelles ordinales à arbitrer"),
        stat=(f"z = {fmt(z, 2)}" if z is not None else ""),
        alerte=al, vigilance=vg, portee=po))
    return out


VIGILANCE_PAR_TEST.update(SEUILS_VIGILANCE4)


# --------------------------------------------------------------------------
# NIVEAU 5 — Biens du ménage AP1–AP4 (document, section 7)
# --------------------------------------------------------------------------
# Items binaires qui servent à construire l'indice de bien-être matériel :
# leur cohérence interne est un enjeu de qualité de mesure, et un agent qui
# coche en bloc plutôt qu'il n'observe la dégrade de façon mesurable.
N_MIN5 = {"guttman": 20, "cronbach": 20, "acp": 20, "biais": 20, "phi": 30}

SEUILS_VIGILANCE5 = {
    "7.1": "reproductibilité < 0,90 (norme de Guttman) avec excès d'erreurs",
    "7.2": "ΔAlpha > +0,015 en retirant l'unité",
    "7.3": "|z| > 1,96 (Mann-Whitney sur les scores de richesse)",
    "7.4": "biais global > 1,5 (moyenne des |Z| sur les items de biens)",
    "7.5": "cohérence sectorielle plus faible que la zone, p < 0,10",
}


def _ap_lignes(ms):
    """(ménages, vecteurs 0/1) des ménages dont TOUS les items sont renseignés."""
    gardes, lignes = [], []
    for m in ms:
        v = [num(m.get(c)) for c in COLS_AP]
        if any(x is None for x in v):
            continue
        gardes.append(m)
        lignes.append([1 if x else 0 for x in v])
    return gardes, lignes


def _agri_activite(m):
    """Le ménage déclare-t-il au moins un actif du secteur primaire ?"""
    return any(num(x.get("M19")) in M19_AGRICOLES for x in m.get("membres", ()))


def _agri_bien(m):
    """Le ménage possède-t-il au moins un moyen de production agricole ?"""
    return any(num(m.get(c)) == 1 for c in COLS_AGRI)


def _zone_ap(ref):
    """Tout ce qui se calcule UNE fois par zone : prévalences, ACP, alpha."""
    gardes, lignes = _ap_lignes(ref)
    if not lignes:
        return None
    k = len(COLS_AP)
    prev = [sum(l[i] for l in lignes) for i in range(k)]
    ordre = sorted(range(k), key=lambda i: -prev[i])
    return {"cles": {m["key"] for m in gardes}, "lignes": lignes,
            "gardes": gardes, "prev": prev, "ordre": ordre,
            "acp": acp_premier_axe(lignes), "alpha": cronbach(lignes)}


def niveau5(echelons):
    """Section 7 du document — cohérence du module « biens du ménage ».

    Cinq angles sur la même question : les items décrivent-ils un vrai
    ménage observé, ou ont-ils été cochés en bloc ?"""
    out = []
    nb_ap = lambda ms: len(_ap_lignes(ms)[1])

    # --- 7.1 Échelle de Guttman et reproductibilité -----------------------
    u, ref, n, po, _pairs = _escalade(echelons, nb_ap, N_MIN5["guttman"])
    z_ap = _memo("n5_zone", ref, lambda: _zone_ap(ref))
    _gu, lu = _ap_lignes(u)
    k = len(COLS_AP)
    rep_u = rep_z = z1 = None
    err_u = err_r = n_u = n_r = 0
    if z_ap and lu:
        ordre = z_ap["ordre"]
        err_u = guttman_erreurs(lu, ordre)
        n_u = len(lu) * k
        cles_u = {m["key"] for m in _gu}
        reste = [l for m, l in zip(z_ap["gardes"], z_ap["lignes"])
                 if m["key"] not in cles_u]
        err_r = guttman_erreurs(reste, ordre)
        n_r = len(reste) * k
        rep_u = 1 - err_u / float(n_u) if n_u else None
        rep_z = 1 - err_r / float(n_r) if n_r else None
        if n_u and n_r:
            p1, p2 = err_u / float(n_u), err_r / float(n_r)
            pc = (err_u + err_r) / float(n_u + n_r)
            den = math.sqrt(pc * (1 - pc) * (1 / n_u + 1 / n_r)) if 0 < pc < 1 else 0
            if den:
                z1 = (p1 - p2) / den
    excede = bool(z1 is not None and z1 > 1.96)
    al = bool(rep_u is not None and rep_u < 0.85 and excede)
    vg = bool(rep_u is not None and rep_u < 0.90 and excede)
    out.append(resultat(
        "7.1", "Échelle de Guttman : reproductibilité des biens",
        "Une échelle parfaite suppose une hiérarchie : posséder un bien rare "
        "implique presque toujours de posséder les biens courants. Un ménage "
        "qui a une moto mais pas de natte est une « erreur de Guttman ». La "
        "colonne porte la part de réponses conformes à cette hiérarchie.",
        ["Rep = 1 − [ Σ erreurs de Guttman / (n × k) ]",
         f"k = {k} items, classés par prévalence décroissante dans la zone"],
        rep_u, "", n=n, n_min=N_MIN5["guttman"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(lu))} ménage(s) "
                f"aux {k} items renseignés.",
                f"Erreurs : {fmt(err_u)} sur {fmt(n_u)} réponses → "
                f"Rep = {fmt(rep_u, 3)}.",
                f"Reste de la zone : {fmt(err_r)} / {fmt(n_r)} → "
                f"Rep = {fmt(rep_z, 3)}.",
                f"Test de proportion sur le taux d'erreurs : Z = {fmt(z1, 2)}",
                "Norme usuelle de Guttman : Rep ≥ 0,90."],
        conclusion=("→ Alerte : combinaisons de biens statistiquement "
                    "improbables, bien plus fréquentes que dans la zone."
                    if al else "→ Vigilance : hiérarchie des biens moins "
                    "respectée que dans la zone." if vg else
                    "→ Hiérarchie des biens cohérente."),
        seuils=["Rep < 0,85 ET significativement inférieur à celui de la zone",
                "Norme usuelle de l'échelle de Guttman : Rep ≥ 0,90"],
        repere=f"zone : {fmt(rep_z, 3)} · norme 0,90",
        stat=(f"Z = {fmt(z1, 2)}" if z1 is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 7.2 Alpha de Cronbach, leave-one-agent-out -----------------------
    u, ref, n, po, _pairs = _escalade(echelons, nb_ap, N_MIN5["cronbach"])
    z_ap = _memo("n5_zone", ref, lambda: _zone_ap(ref))
    delta = a_glob = a_sans = None
    if z_ap:
        a_glob = z_ap["alpha"]
        cles_u = {m["key"] for m in _ap_lignes(u)[0]}
        reste = [l for m, l in zip(z_ap["gardes"], z_ap["lignes"])
                 if m["key"] not in cles_u]
        a_sans = cronbach(reste)
        if a_glob is not None and a_sans is not None:
            delta = a_sans - a_glob
    al = bool(delta is not None and delta > CAL["7.2.al"])
    vg = bool(delta is not None and delta > CAL["7.2.vg"])
    out.append(resultat(
        "7.2", "Alpha de Cronbach : dégradation de l'échelle",
        f"L'alpha mesure la cohérence interne des {len(COLS_AP)} items. On le recalcule en "
        "retirant l'unité de l'échantillon : s'il S'AMÉLIORE nettement sans "
        "elle, c'est elle qui dégrade l'instrument de mesure — réponses "
        "incohérentes ou tirées au hasard.",
        ["α = [k / (k−1)] × [1 − (Σ σ²_i / σ²_total)]",
         "ΔAlpha = α(zone sans l'unité) − α(zone entière)"],
        delta, "ΔAlpha", n=n, n_min=N_MIN5["cronbach"],
        calcul=[f"Unité mesurée : {po['libelle']}.",
                f"α de la zone entière : {fmt(a_glob, 3)} "
                "(norme usuelle : ≥ 0,70).",
                f"α de la zone SANS cette unité : {fmt(a_sans, 3)}.",
                f"ΔAlpha = {fmt(delta, 4)}"],
        conclusion=("→ Alerte : l'échelle de bien-être est nettement plus "
                    "cohérente sans cette unité." if al else
                    "→ Vigilance : l'unité dégrade légèrement l'échelle."
                    if vg else "→ L'unité ne dégrade pas l'échelle."),
        seuils=["ΔAlpha > +0,03 : l'unité dégrade l'instrument de mesure"],
        repere=f"α de la zone {fmt(a_glob, 3)} · sans l'unité {fmt(a_sans, 3)}",
        stat=(f"α {fmt(a_glob, 2)}→{fmt(a_sans, 2)}"
              if a_glob is not None and a_sans is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 7.3 ACP (indice de richesse) + Mann-Whitney ----------------------
    u, ref, n, po, _pairs = _escalade(echelons, nb_ap, N_MIN5["acp"])
    z_ap = _memo("n5_zone", ref, lambda: _zone_ap(ref))
    moy_u = part = zmw = None
    if z_ap and z_ap["acp"]:
        acp = z_ap["acp"]
        part = 100.0 * acp["part"]
        gu, lu = _ap_lignes(u)
        cles_u = {m["key"] for m in gu}
        su = [acp_score(acp, l) for l in lu]
        sr = [acp_score(acp, l) for m, l in zip(z_ap["gardes"], z_ap["lignes"])
              if m["key"] not in cles_u]
        moy_u = moyenne(su)
        zmw = mann_whitney_z(su, sr)
    al = bool(zmw is not None and abs(zmw) > 2.58)
    vg = bool(zmw is not None and abs(zmw) > 1.96)
    out.append(resultat(
        "7.3", "Indice de richesse (ACP) comparé à la zone",
        f"Le premier axe d'une ACP sur les {len(COLS_AP)} items donne l'indice de richesse "
        "standard. Les scores ne suivant pas une loi normale, la comparaison "
        "entre l'unité et le reste de sa zone se fait par un test de rangs, "
        "comme le prescrit le document.",
        ["Score_i = Σ_k w_k × x_ik (w = poids du 1er axe de l'ACP)",
         "Comparaison des rangs unité / reste de la zone (Mann-Whitney)"],
        moy_u, "score moyen", n=n, n_min=N_MIN5["acp"],
        calcul=[f"Unité mesurée : {po['libelle']}.",
                f"Part de variance expliquée par le 1er axe : {fmt(part, 1)} % "
                + ("(< 20 % : échelle globalement peu cohérente, "
                   "à revoir)." if part is not None and part < 20 else
                   "(norme attendue : 20 à 35 % pour des items binaires)."),
                f"Score moyen de l'unité : {fmt(moy_u, 3)}.",
                f"Test de rangs contre le reste de la zone : z = {fmt(zmw, 2)}"],
        conclusion=("→ Alerte : scores de richesse significativement "
                    "différents de ceux du reste de la zone." if al else
                    "→ Vigilance : scores de richesse en écart de la zone."
                    if vg else "→ Scores de richesse comparables à la zone."),
        seuils=["p < 0,05 au test de rangs : l'unité produit des scores "
                "différents de ses collègues de la même zone",
                "Variance du 1er axe < 20 % : échelle peu cohérente (zone)"],
        repere=f"1er axe : {fmt(part, 1)} % de variance",
        stat=(f"z = {fmt(zmw, 2)}" if zmw is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 7.4 Biais global sur les 29 items --------------------------------
    u, ref, n, po, _pairs = _escalade(echelons, nb_ap, N_MIN5["biais"])
    gu, lu = _ap_lignes(u)
    z_ap = _memo("n5_zone", ref, lambda: _zone_ap(ref))
    biais, pires = None, []
    if z_ap and lu:
        cles_u = {m["key"] for m in gu}
        lr = [l for m, l in zip(z_ap["gardes"], z_ap["lignes"])
              if m["key"] not in cles_u]
        n1, n2 = len(lu), len(lr)
        zs = []
        for i, col in enumerate(COLS_AP):
            if not n1 or not n2:
                continue
            x1 = sum(l[i] for l in lu)
            x2 = sum(l[i] for l in lr)
            p1, p2 = x1 / float(n1), x2 / float(n2)
            pc = (x1 + x2) / float(n1 + n2)
            den = math.sqrt(pc * (1 - pc) * (1 / n1 + 1 / n2)) if 0 < pc < 1 else 0
            if den:
                zi = (p1 - p2) / den
                zs.append(abs(zi))
                pires.append((abs(zi), col, 100 * p1, 100 * p2, zi))
        if zs:
            biais = sum(zs) / float(len(zs))
        pires.sort(reverse=True)
    al = bool(biais is not None and biais > CAL["7.4.al"])
    vg = bool(biais is not None and biais > CAL["7.4.vg"])
    out.append(resultat(
        "7.4", f"Biais global sur les {len(COLS_AP)} items de biens",
        "Chaque item est comparé au reste de la zone par un test de "
        f"proportion ; la moyenne des |Z| sur les {len(COLS_AP)} items dit si le biais est "
        "ponctuel ou systématique. Un agent qui coche presque toujours "
        "« Oui » — ou toujours « Non » — quel que soit le ménage visité, "
        "ressort ici même si aucun item pris isolément ne choque.",
        ["Z_item = (p₁ − p₂) / √[ p̂(1−p̂)(1/n₁ + 1/n₂) ]",
         f"Biais_global = (1/{len(COLS_AP)}) × Σ |Z_item|"],
        biais, "moyenne des |Z|", n=n, n_min=N_MIN5["biais"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(lu))} ménage(s)."]
               + [f"{c} : {fmt(a, 0)} % contre {fmt(b, 0)} % dans la zone "
                  f"(Z = {fmt(zi, 2)})" for _x, c, a, b, zi in pires[:5]]
               + [f"Moyenne des |Z| sur les {len(COLS_AP)} items : {fmt(biais, 2)}"],
        conclusion=("→ Alerte : biais systématique sur l'ensemble du module "
                    "biens — remplissage en bloc plutôt qu'observation."
                    if al else "→ Vigilance : écarts répétés sur les items de "
                    "biens." if vg else "→ Taux de possession conformes à la zone."),
        seuils=["Biais_global > 2 : biais systématique suspecté sur tout le "
                "module biens"],
        repere=(f"item le plus déviant : {pires[0][1]} (Z = {fmt(pires[0][4], 2)})"
                if pires else ""),
        stat=(f"pire {pires[0][1].split('__')[-1]}" if pires else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 7.5 Cohérence sectorielle : biens agricoles × activité -----------
    def _table(ms):
        n11 = n10 = n01 = n00 = 0
        for m in ms:
            b, a_ = _agri_bien(m), _agri_activite(m)
            if b and a_:
                n11 += 1
            elif b:
                n10 += 1
            elif a_:
                n01 += 1
            else:
                n00 += 1
        return n11, n10, n01, n00

    u, ref, n, po, _pairs = _escalade(echelons, len, N_MIN5["phi"])
    tu = _table(u)
    tr = _memo("n5_table", ref, lambda: _table(ref))
    reste = tuple(tr[i] - tu[i] for i in range(4))
    phi_u, phi_z = phi_2x2(*tu), phi_2x2(*reste)
    zf, pv = fisher_z_diff(phi_u, sum(tu), phi_z, max(sum(reste), 0))
    # φ n'est pas définissable dès qu'une marge de la table est vide. Deux cas
    # opposés se cachent derrière ce même « pas de valeur » :
    #  - des ménages possèdent des moyens de production agricole et AUCUN
    #    n'a d'actif du primaire : c'est l'incohérence même que le test
    #    cherche, poussée à son maximum -> ALERTE, case rouge sans valeur ;
    #  - aucun ménage ne possède ni bien ni activité agricole : il n'y a
    #    rien à corréler -> « nd », et surtout pas une case verte vide.
    incoherence_totale = bool(phi_u is None and tu[1] > 0 and (tu[0] + tu[2]) == 0)
    rien_a_dire = bool(phi_u is None and not incoherence_totale)
    n_eff = 0 if rien_a_dire else n
    al = bool(incoherence_totale or (pv is not None and pv < 0.05))
    vg = bool(pv is not None and pv < 0.10)
    out.append(resultat(
        "7.5", "Cohérence sectorielle : biens agricoles × activité",
        "Un ménage qui possède charrue, rizière ou matériel de pêche a "
        "normalement au moins un actif du secteur primaire. La corrélation "
        "entre ces deux faits, nettement plus faible chez une unité que dans "
        "sa zone, signale une incohérence sectorielle.",
        ["φ = (n₁₁×n₀₀ − n₁₀×n₀₁) / √(n₁·×n₀·×n·₁×n·₀)",
         "Comparaison à la zone par transformation de Fisher z"],
        phi_u, "", n=n_eff, n_min=N_MIN5["phi"],
        calcul=[f"Unité mesurée : {po['libelle']}.",
                f"Table 2×2 (bien agricole × actif du primaire) : "
                f"{fmt(tu[0])} / {fmt(tu[1])} / {fmt(tu[2])} / {fmt(tu[3])}.",
                f"φ de l'unité : {fmt(phi_u, 3)} ; reste de la zone : "
                f"{fmt(phi_z, 3)}.",
                f"Différence (Fisher z) : z = {fmt(zf, 2)} → p = {fmt(pv, 4)}.",
                "Activités retenues (M19) : agriculteur, éleveur, pêcheur."],
        conclusion=(
            (f"→ Alerte : {fmt(tu[1])} ménage(s) possèdent des moyens de "
             "production agricole et AUCUN n'a d'actif du secteur primaire — "
             "la corrélation n'est même pas définissable."
             if incoherence_totale else
             "→ Alerte : lien biens agricoles / activité significativement "
             "plus faible que dans la zone.") if al else
            "→ Vigilance : cohérence sectorielle inférieure à la zone."
            if vg else "→ Cohérence sectorielle comparable à la zone."),
        seuils=["φ significativement plus faible que celui du reste de la zone "
                "(test de différence de corrélations, 5 %)"],
        repere=f"zone : {fmt(phi_z, 3)}",
        stat=(f"z = {fmt(zf, 2)}" if zf is not None else ""),
        alerte=al, vigilance=vg, portee=po))
    return out


VIGILANCE_PAR_TEST.update(SEUILS_VIGILANCE5)


VIGILANCE_PAR_TEST.update({
    "4.1": SEUILS_VIGILANCE2["whipple"], "4.2": SEUILS_VIGILANCE2["myers"],
    "4.3": SEUILS_VIGILANCE2["ipas"], "4.4": SEUILS_VIGILANCE2["chi2_terminal"],
    "4.5": SEUILS_VIGILANCE2["icc"], "4.6": SEUILS_VIGILANCE2["ks"],
    "4.7": SEUILS_VIGILANCE2["sexratio"], "4.8.1": SEUILS_VIGILANCE2["chi2_m7"],
    "4.8.2": SEUILS_VIGILANCE2["m7_m4"],
})


# --------------------------------------------------------------------------
# NIVEAU 6 — Détection de fraude et de duplication (document, section 8)
# --------------------------------------------------------------------------
# Changement de question. Les niveaux 2 à 5 cherchent un agent QUI MESURE MAL ;
# celui-ci cherche un agent QUI N'A PAS VISITÉ le ménage : questionnaire recopié
# d'un voisin (8.1), chiffres inventés (8.2), entretien trop rapide pour avoir
# eu lieu (8.3), points GPS immobiles (8.4). Les quatre signaux sont
# indépendants — c'est leur convergence sur un même agent qui fait un dossier,
# pas une case rouge isolée.
N_MIN6 = {"maha": 10, "benford": 30, "duree": 10, "gps": 10,
          # 8.5 se calcule sur les ménages APPARIÉS au dénombrement : sous dix,
          # un seul code mal repris ferait basculer le taux.
          "ecart_den": 10}

SEUILS_VIGILANCE6 = {
    "8.1": "excès de paires très proches vs la zone, Z > 1,96",
    "8.2": "écart à la référence de chiffres significatif à 10 %",
    "8.3": "excès de questionnaires à résidu < −2 face au hasard (Z > 1,96)",
    "8.4": "plus de 10 % des points GPS agglutinés",
    "8.5": "excès de ménages retrouvés loin du point du dénombrement, Z > 1,96",
}

# Les quatre dimensions de la distance de Mahalanobis (document, 8.1).
# ⚠️ Le « score de standing H » reprend les échelles ordinales d'ORDRE_H
# (niveau 4) : même réserve qu'au niveau 4, ces rangs restent à faire arbitrer
# par les statisticiens du RSU.
DIMS_FRAUDE = ("âge du chef de ménage", "taille du ménage",
               "score de richesse AP", "score de standing H")

# DBSCAN : le document propose ε ≈ 15–30 m et MinPts ≈ 3–5, mais met son seuil
# d'alerte sur « un cluster de rayon < 10 mètres ». C'est ce dernier qui
# compte : 10 m est en dessous de la précision GPS courante en milieu bâti, donc
# des points plus serrés que cela ne décrivent pas des maisons différentes.
GPS_EPS_M, GPS_MINPTS = 10.0, 3


def _age_chef(m):
    """Âge (M4) du membre déclaré chef de ménage (M7 = 1), sinon None."""
    for x in m.get("membres", ()):
        if num(x.get("M7")) == M7_CHEF:
            a = num(x.get("M4"))
            if a is not None:
                return float(a)
    return None


def _score_ap(m):
    """Nombre de biens possédés parmi les items AP (None si l'un manque)."""
    total = 0
    for c in COLS_AP:
        v = num(m.get(c))
        if v is None:
            return None
        total += 1 if v else 0
    return float(total)


def _score_h(m):
    """Standing du logement : somme des rangs ordinaux de H1, H4, H5 et H6."""
    total = 0
    for var, rangs in ORDRE_H.items():
        v = num(m.get(var))
        r = rangs.get(int(v)) if v is not None else None
        if r is None:
            return None
        total += r
    return float(total)


def _vecteurs_fraude(ms):
    """(ménages, vecteurs 4D) des ménages dont les quatre dimensions sont là."""
    gardes, lignes = [], []
    for m in ms:
        v = (_age_chef(m), num(m.get("nbmembre")), _score_ap(m), _score_h(m))
        if any(x is None for x in v):
            continue
        gardes.append(m)
        lignes.append([float(x) for x in v])
    return gardes, lignes


def _chiffres_cin(ms):
    """Premiers chiffres significatifs des numéros de CIN (M6a) saisis.

    Le questionnaire VAD ne comporte AUCUNE variable numérique ouverte au sens
    du document (ni superficie, ni cheptel, ni montant) : biens et logement sont
    binaires ou catégoriels. Le seul nombre de grande plage que l'agent SAISIT
    lui-même est le numéro de CIN — et un numéro inventé est précisément la
    fraude que la section 8 vise."""
    out = []
    for m in ms:
        for x in m.get("membres", ()):
            d = premier_chiffre(x.get("M6a"))
            if d:
                out.append(d)
    return out


def _effectifs_chiffres(chiffres):
    return [sum(1 for d in chiffres if d == k) for k in range(1, 10)]


def _duree_points(ms):
    """(taille du ménage, durée en minutes) des entretiens exploitables."""
    out = []
    for m in ms:
        d, nb = m.get("duree"), num(m.get("nbmembre"))
        if d is not None and d > 0 and nb is not None:
            out.append((float(nb), float(d), m))
    return out


def _gps_points(ms):
    """Coordonnées (lat, lon) exploitables, UNE par adresse enquêtée.

    Deux ménages d'un même bâtiment partagent légitimement leur point GPS —
    il y en a 3 081 dans les données RSU d'octobre 2025, et 342 des 885
    points
    partagés s'expliquent par cela seul. Les compter deux fois transformait
    un habitat collectif en « agent immobile ». On ne garde donc qu'un relevé
    par `address_id` ; les ménages sans adresse renseignée comptent chacun
    pour un, comme avant."""
    out, vues = [], set()
    for m in ms:
        la, lo = num(m.get("GPS__Latitude")), num(m.get("GPS__Longitude"))
        if la is None or lo is None or (la == 0 and lo == 0):
            continue
        if not (-90 <= la <= 90 and -180 <= lo <= 180):
            continue
        adr = m.get("address_id")
        if adr not in (None, ""):
            if adr in vues:
                continue
            vues.add(adr)
        out.append((float(la), float(lo)))
    return out


def _zone_fraude(ref):
    """Tout ce qui se calcule UNE fois par zone pour le niveau 6."""
    _g, lignes = _vecteurs_fraude(ref)
    inv = inverse_matrice(covariance(lignes)) if len(lignes) > len(DIMS_FRAUDE) else None
    dist = paires_mahalanobis(lignes, inv) if inv else []
    moy, et = moyenne(dist), ecart_type(dist)
    seuil = (moy - 2 * et) if (moy is not None and et) else None
    serrees = sum(1 for d in dist if d < seuil) if seuil is not None else 0
    return {"inv": inv, "nv": len(lignes), "moy": moy, "et": et, "seuil": seuil,
            "paires": len(dist), "serrees": serrees}


def _zone_chiffres(ref):
    """Distribution des premiers chiffres de la zone, et son ajustement Benford."""
    cnt = _effectifs_chiffres(_chiffres_cin(ref))
    khi, ddl = chi2_benford(cnt)
    p = chi2_sf(khi, ddl) if khi is not None and ddl else None
    return {"cnt": cnt, "n": sum(cnt), "khi": khi, "ddl": ddl, "p": p,
            # Benford ne sert de référence que si la ZONE elle-même s'y conforme.
            "benford": bool(p is not None and p >= 0.05)}


def _zone_duree(ref):
    """Entretiens horodatés de la zone et modèle global, pour l'affichage."""
    pts = _duree_points(ref)
    mod = (regression([p[0] for p in pts], [p[1] for p in pts])
           if len(pts) >= 5 else None)
    return {"pts": pts, "mod": mod}


def _modele_hors_unite(zone, cles):
    """Modèle de durée ajusté sur la zone PRIVÉE de l'unité jugée.

    Sans ce retrait, un agent qui expédie tous ses entretiens tire à lui la
    droite de régression et gonfle l'écart-type des résidus : il devient son
    propre étalon et le test ne le voit plus (masquage). C'est le même
    « leave-one-out » qu'aux tests 7.1 et 7.2, pour la même raison."""
    reste = [p for p in zone["pts"] if p[2]["key"] not in cles]
    if len(reste) < 5:
        return None
    return regression([p[0] for p in reste], [p[1] for p in reste])


def _residus(mod, pts):
    """Résidus standardisés d'un lot d'entretiens face à un modèle donné."""
    if not mod or not mod.get("sigma"):
        return []
    return [(y - (mod["b0"] + mod["b1"] * x)) / mod["sigma"] for x, y, _m in pts]


def niveau6(echelons):
    """Section 8 du document — fraude et duplication.

    Les niveaux précédents demandent « cet agent mesure-t-il bien ? ». Celui-ci
    demande « cet agent est-il allé sur place ? ». Quatre traces indépendantes
    d'un questionnaire qui n'a pas été administré."""
    out = []

    # --- 8.1 Distance de Mahalanobis : doublons statistiques ---------------
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: len(_vecteurs_fraude(ms)[1]), N_MIN6["maha"])
    z = _memo("n6_maha", ref, lambda: _zone_fraude(ref))
    part = zp = dmin = None
    serrees = paires_u = 0
    if z["inv"] is not None and z["seuil"] is not None:
        _gu, lu = _vecteurs_fraude(u)
        du = paires_mahalanobis(lu, z["inv"])
        paires_u = len(du)
        if paires_u:
            dmin = min(du)
            serrees = sum(1 for d in du if d < z["seuil"])
            part = 100.0 * serrees / paires_u
            # Test de proportion contre le reste des paires de la zone.
            n_r = max(0, z["paires"] - paires_u)
            s_r = max(0, z["serrees"] - serrees)
            if n_r:
                p1, p2 = serrees / float(paires_u), s_r / float(n_r)
                pc = (serrees + s_r) / float(paires_u + n_r)
                den = (math.sqrt(pc * (1 - pc) * (1 / float(paires_u) + 1 / float(n_r)))
                       if 0 < pc < 1 else 0)
                if den:
                    zp = (p1 - p2) / den
    # Le Z seul ne suffit pas : sur des milliers de paires, un écart minuscule
    # devient « significatif » sans être notable (à Z > 7, le test désignait
    # encore 14 % des agents). On lui adjoint un plancher d'AMPLEUR — la part
    # des paires réellement quasi identiques — de sorte qu'une alerte se dise
    # à l'agent en clair : « x % de vos questionnaires sont des quasi-doublons ».
    al = bool(zp is not None and zp > CAL["8.1.al"] and serrees
              and part is not None and part >= CAL["8.1.part"])
    vg = bool(zp is not None and zp > CAL["8.1.vg"] and serrees
              and part is not None and part >= CAL["8.1.partvg"])
    # Σ non inversible (une dimension constante dans la zone), aucune paire à
    # comparer, ou unité confondue avec sa zone : le test n'est pas calculable.
    # Il vaut « nd » — surtout pas une case verte, qui affirmerait l'absence de
    # doublons alors que rien n'a été mesuré (cf. le φ du test 7.5).
    n_eff = n if zp is not None else 0
    raison = ("" if n_eff else
              (f"Effectif insuffisant : {fmt(n)} ménage(s) aux quatre "
               f"dimensions renseignées, le test en demande "
               f"{fmt(N_MIN6['maha'])}." if n < N_MIN6["maha"] else
               "Aucune paire de référence hors de cette unité, ou matrice de "
               "covariance non inversible (une dimension constante dans la "
               "zone) : la distance de Mahalanobis n'est pas définissable."))
    out.append(resultat(
        "8.1", "Mahalanobis : questionnaires quasi identiques",
        "Deux ménages différents ne se ressemblent jamais tout à fait. La "
        "distance de Mahalanobis mesure leur écart sur quatre dimensions "
        "(âge du chef, taille du ménage, richesse, standing du logement) en "
        "tenant compte de leurs corrélations. Des paires anormalement proches "
        "chez un même agent trahissent une recopie de questionnaire.",
        ["D²(x, y) = (x − y)ᵀ Σ⁻¹ (x − y) — Σ estimée sur la zone",
         "Paire suspecte : D < moyenne de la zone − 2 écarts-types",
         "Dimensions : " + ", ".join(DIMS_FRAUDE)],
        part, "% de paires suspectes", n=n_eff, n_min=N_MIN6["maha"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(paires_u)} paire(s) "
                f"de ménages comparables.",
                f"Référence de la zone : distance moyenne {fmt(z['moy'], 2)} "
                f"(écart-type {fmt(z['et'], 2)}) sur {fmt(z['paires'])} paires.",
                f"Seuil de suspicion : D < {fmt(z['seuil'], 2)}.",
                f"Paires sous le seuil : {fmt(serrees)} — soit {fmt(part, 1)} % "
                f"(la zone entière en compte {fmt(z['serrees'])}).",
                f"Paire la plus proche de l'unité : D = {fmt(dmin, 2)}.",
                f"Test de proportion contre le reste de la zone : Z = {fmt(zp, 2)}"],
        conclusion=("→ Alerte : bien plus de questionnaires quasi identiques "
                    "que partout ailleurs dans la zone — duplication à "
                    "vérifier ménage par ménage." if al else
                    "→ Vigilance : excès modéré de questionnaires très "
                    "semblables." if vg else
                    "→ Pas d'excès de questionnaires quasi identiques."),
        seuils=["Paire suspecte : D < moyenne de la zone − 2 écarts-types",
                f"Alerte : Z > {fmt(CAL['8.1.al'], 2)} face à la zone ET au "
                f"moins {fmt(CAL['8.1.part'], 0)} % des paires de l'agent sous "
                "le seuil",
                "La condition d'ampleur est indispensable : sur des milliers "
                "de paires, le Z seul restait significatif pour 14 % des "
                "agents sans qu'aucun doublon soit notable"],
        repere=(f"seuil zone D < {fmt(z['seuil'], 2)} · la plus proche "
                f"{fmt(dmin, 2)}"),
        stat=(f"Z = {fmt(zp, 2)}" if zp is not None else ""),
        alerte=al, vigilance=vg, portee=po, raison=raison))

    # --- 8.2 Loi de Benford sur les numéros saisis -------------------------
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: len(_chiffres_cin(ms)), N_MIN6["benford"])
    z = _memo("n6_chiffres", ref, lambda: _zone_chiffres(ref))
    cu = _effectifs_chiffres(_chiffres_cin(u))
    khi_b, ddl_b = chi2_benford(cu)
    reste = [z["cnt"][i] - cu[i] for i in range(9)]
    khi_h, ddl_h = chi2_homogeneite(cu, [max(0, x) for x in reste])
    # Benford ne sert d'étalon que si la ZONE s'y conforme. Sinon la référence
    # est la zone elle-même : on cherche l'agent qui s'écarte de ses collègues.
    if z["benford"]:
        khi, ddl, ref_lib = khi_b, ddl_b, "loi de Benford"
    else:
        khi, ddl, ref_lib = khi_h, ddl_h, "distribution de la zone"
    p = chi2_sf(khi, ddl) if khi is not None and ddl else None
    al = bool(p is not None and p < CAL["8.2.al"])
    vg = bool(p is not None and p < CAL["8.2.vg"])
    # Aucune référence utilisable : la zone ne suit pas Benford ET l'unité EST
    # la zone (rien à quoi la comparer), ou les effectifs ne permettent pas un
    # χ² valide même après regroupement.
    n_eff = n if p is not None else 0
    raison = ("" if n_eff else
              (f"Effectif insuffisant : {fmt(n)} numéro(s) exploitables, le "
               f"test en demande {fmt(N_MIN6['benford'])}."
               if n < N_MIN6["benford"] else
               "La zone ne suit pas la loi de Benford et l'unité couvre toute "
               "la zone : il ne reste aucune référence à laquelle comparer "
               "ses chiffres."))
    out.append(resultat(
        "8.2", "Premiers chiffres : nombres inventés",
        "Les nombres relevés sur le terrain ont une signature : le premier "
        "chiffre est bien plus souvent 1 que 9 (loi de Benford). Des nombres "
        "inventés tendent vers une distribution plus plate. Le test porte sur "
        "le seul nombre de grande plage que l'agent saisit lui-même, le numéro "
        "de CIN.",
        ["P(d) = log₁₀(1 + 1/d), d = 1 … 9  —  P(1) ≈ 30,1 %, P(9) ≈ 4,6 %",
         "χ² = Σ (O_d − E_d)² / E_d, chiffres rares regroupés"],
        khi, "χ²", n=n_eff, n_min=N_MIN6["benford"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(sum(cu))} numéro(s) "
                "exploitables.",
                "Distribution des premiers chiffres : "
                + " ".join(f"{d + 1}:{cu[d]}" for d in range(9)) + ".",
                f"Référence retenue : {ref_lib}.",
                ("La zone suit la loi de Benford (p = "
                 f"{fmt(z['p'], 3)}) : l'écart de l'unité y est confronté."
                 if z["benford"] else
                 "La zone elle-même NE suit PAS la loi de Benford "
                 f"(χ² = {fmt(z['khi'], 1)}, p = {fmt(z['p'], 4)} sur "
                 f"{fmt(z['n'])} numéros). Un écart à Benford ne dirait donc "
                 "rien de l'agent : la référence devient la distribution "
                 "observée chez ses collègues de la zone."),
                f"χ² = {fmt(khi, 2)} à {fmt(ddl)} degré(s) de liberté, "
                f"p = {fmt(p, 4)}",
                f"Pour mémoire, écart à Benford seul : χ² = {fmt(khi_b, 2)}."],
        conclusion=("→ Alerte : les chiffres saisis par cette unité ne suivent "
                    f"pas la {ref_lib} — numéros possiblement inventés." if al
                    else "→ Vigilance : écart de distribution à la limite de "
                    "la significativité." if vg else
                    "→ Distribution des chiffres conforme à la référence."),
        seuils=["p < 0,05 au χ² face à la référence retenue",
                "Référence = Benford si la zone s'y conforme, sinon la zone"],
        repere=f"référence : {ref_lib}",
        stat=(f"p = {fmt(p, 3)}" if p is not None else ""),
        alerte=al, vigilance=vg, portee=po, raison=raison))

    # --- 8.3 Régression de la durée de passation --------------------------
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: len(_duree_points(ms)), N_MIN6["duree"])
    zone = _memo("n6_duree", ref, lambda: _zone_duree(ref))
    pts = _duree_points(u)
    mod = _modele_hors_unite(zone, {p[2]["key"] for p in pts})
    res = _residus(mod, pts)
    part = pire = None
    rapides = doutes = 0
    z2 = None
    if res:
        pire = min(res)
        rapides = sum(1 for r in res if r < -3)
        doutes = sum(1 for r in res if r < -2)
        part = 100.0 * rapides / len(res)
        # Palier de VIGILANCE. « Au moins un résidu < −2 » paraît naturel mais
        # ne vaut rien : sous le modèle, 2,3 % des questionnaires passent ce
        # seuil par hasard, donc un agent de 40 entretiens a deux chances sur
        # trois d'en avoir un — mesuré sur jeu synthétique sans fraudeur, la
        # moitié des agents s'allumait. On teste donc si l'unité en compte
        # PLUS que le hasard n'en donne.
        p0 = 1 - phi(2.0)                       # Φ(−2) ≈ 2,275 %
        den = math.sqrt(p0 * (1 - p0) / len(res))
        if den:
            z2 = (doutes / float(len(res)) - p0) / den
    al = bool(rapides)
    vg = bool(not rapides and z2 is not None and z2 > 1.96)
    # Sans modèle de zone estimable (durées absentes, tailles toutes égales),
    # il n'y a pas de résidu : « nd » plutôt qu'un 0 % rassurant.
    n_eff = n if res else 0
    raison = ("" if n_eff else
              (f"Effectif insuffisant : {fmt(n)} entretien(s) horodatés, le "
               f"test en demande {fmt(N_MIN6['duree'])}."
               if n < N_MIN6["duree"] else
               "Modèle de durée non estimable sur la zone privée de cette "
               "unité : il n'y reste pas assez d'entretiens hors d'elle."))
    out.append(resultat(
        "8.3", "Durée incompatible avec la taille du ménage",
        "Le seuil de durée du niveau 1 ignore la taille du ménage : un "
        "entretien de 12 minutes est normal pour une personne seule, "
        "impossible pour dix. On ajuste donc sur la zone un modèle « durée "
        "attendue selon le nombre de membres », et on regarde de combien "
        "chaque questionnaire passe en dessous.",
        ["Durée_prédite = β₀ + β₁ × nbmembre (régression sur la zone)",
         "Résidu standardisé = (durée observée − durée prédite) / σ_résidus",
         "Modèle ajusté sur la zone PRIVÉE de l'unité jugée (anti-masquage)"],
        part, "% trop rapides", n=n_eff, n_min=N_MIN6["duree"],
        calcul=([f"Unité mesurée : {po['libelle']} — {fmt(len(res))} entretien(s) "
                 "horodatés."]
                + ([f"Modèle ajusté sur la zone SANS cette unité : durée = "
                    f"{fmt(mod['b0'], 1)} + {fmt(mod['b1'], 1)} × nbmembre "
                    f"minutes (R² = {fmt(mod['r2'], 2)}, σ des résidus = "
                    f"{fmt(mod['sigma'], 1)} min, sur {fmt(mod['n'])} "
                    "entretiens). L'unité est retirée du modèle pour qu'elle "
                    "ne serve pas d'étalon à elle-même."]
                   if mod else ["Modèle de la zone non estimable sans cette "
                                "unité (trop peu d'entretiens hors d'elle)."])
                + [f"Questionnaires à résidu < −3 : {fmt(rapides)} "
                   f"(soit {fmt(part, 1)} %) ; à résidu < −2 : {fmt(doutes)} "
                   f"(le hasard en donnerait {fmt(0.02275 * len(res), 1)} — "
                   f"Z = {fmt(z2, 2)}).",
                   f"Résidu le plus bas de l'unité : {fmt(pire, 2)}."]),
        conclusion=("→ Alerte : au moins un questionnaire est trop rapide pour "
                    "avoir été administré, même en tenant compte de la taille "
                    "du ménage." if al else
                    "→ Vigilance : un ou plusieurs entretiens nettement plus "
                    "courts qu'attendu." if vg else
                    "→ Durées compatibles avec la taille des ménages."),
        seuils=["Résidu standardisé < −3 pour au moins un questionnaire"],
        repere=(f"attendu ≈ {fmt(mod['b0'], 0)} + {fmt(mod['b1'], 1)} × membres min"
                if mod else "modèle de zone indisponible"),
        stat=(f"pire résidu {fmt(pire, 1)}" if pire is not None else ""),
        alerte=al, vigilance=vg, portee=po, raison=raison))

    # --- 8.4 Agglutination des points GPS ---------------------------------
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: len(_gps_points(ms)), N_MIN6["gps"])
    pts = _gps_points(u)
    part_gps, amas, plus_gros = dbscan_agglutines(pts, GPS_EPS_M, GPS_MINPTS)
    part_gps = 100.0 * part_gps if pts else None
    al = bool(part_gps is not None and part_gps > CAL["8.4.al"])
    vg = bool(part_gps is not None and part_gps > CAL["8.4.vg"])
    out.append(resultat(
        "8.4", "Points GPS immobiles",
        "Se rendre d'un ménage à l'autre laisse une trace : les points GPS se "
        "dispersent. Des relevés regroupés dans un rayon plus petit que la "
        "précision d'un GPS de terrain décrivent des questionnaires remplis "
        "sans déplacement — au même endroit, voire sans quitter le précédent.",
        [f"DBSCAN(ε = {fmt(GPS_EPS_M, 0)} m, MinPts = {GPS_MINPTS}) : un point "
         "est un « cœur » s'il a MinPts voisins dans le rayon ε",
         "Part des relevés appartenant à un amas"],
        part_gps, "% agglutinés", n=n, n_min=N_MIN6["gps"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(pts))} relevé(s) "
                "GPS exploitables.",
                f"Amas détectés : {fmt(amas)} ; le plus gros regroupe "
                f"{fmt(plus_gros)} relevé(s).",
                f"Part des relevés en amas : {fmt(part_gps, 1)} %.",
                "Rappel : 10 m est inférieur à la précision usuelle d'un GPS "
                "de terrain — des points plus serrés ne décrivent pas des "
                "maisons différentes."],
        conclusion=("→ Alerte : une part importante des relevés se superpose — "
                    "déplacement réel entre ménages peu probable." if al else
                    "→ Vigilance : quelques relevés se superposent." if vg else
                    "→ Relevés GPS dispersés comme attendu."),
        seuils=[f"Plus de {fmt(CAL['8.4.al'], 0)} % des adresses d'un agent "
                f"groupées dans un rayon de {fmt(GPS_EPS_M, 0)} m",
                "Le seuil de 20 % du document désignait 75 % des agents : en "
                "habitat rural dense, des maisons voisines sont réellement à "
                "moins de 10 m les unes des autres"],
        repere=f"{fmt(amas)} amas · le plus gros : {fmt(plus_gros)} relevés",
        stat=(f"{fmt(plus_gros)} points ≤ {fmt(GPS_EPS_M, 0)} m"
              if plus_gros else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 8.5 Écart au point du dénombrement -------------------------------
    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: len(ecart_den(ms)),
                                      N_MIN6["ecart_den"])
    eu = ecart_den(u)
    cles_u = {m.get("key") for _d, m in eu}
    ez = [(d, m) for d, m in ecart_den(ref) if m.get("key") not in cles_u]
    du, dz = [d for d, _m in eu], [d for d, _m in ez]
    loin = sum(1 for d in du if d > DIST_LOIN)
    ailleurs = sum(1 for d in du if d > DIST_AILLEURS)
    part = 100.0 * loin / len(du) if du else None
    part_z = 100.0 * sum(1 for d in dz if d > DIST_LOIN) / len(dz) if dz else None
    med = mediane(du) if du else None
    med_z = mediane(dz) if dz else None
    pire = max(du, default=None)
    # STATISTIQUE DE DÉCISION : Mann-Whitney sur les DISTANCES, et non un test
    # de proportion sur la part au-delà d'un seuil. Trois raisons, mesurées sur
    # le jeu d'essai (tests/test_gps_den.py) :
    #   — un test de proportion est INDÉFINI quand personne, dans la zone, ne
    #     dépasse le seuil : c'est le cas sain, et il ne pouvait alors même pas
    #     confirmer que tout va bien ;
    #   — binariser à 100 m rend invisible l'agent dont TOUS les relevés sont
    #     décalés de 90 m quand ses collègues sont à 20 m ;
    #   — Mann-Whitney travaille sur les RANGS : un `code_den` mal repris, qui
    #     produit un écart de plusieurs centaines de kilomètres, pèse comme
    #     n'importe quelle autre valeur haute au lieu de tout emporter.
    z = mann_whitney_z(du, dz)
    # Et un plancher d'AMPLEUR, comme pour 8.1 et 9.4 : sur vingt ménages, un
    # décalage systématique de 30 m est « significatif » sans rien signifier.
    al = bool(z is not None and z > CAL["8.5.al"]
              and med is not None and med >= CAL["8.5.med"])
    vg = bool(z is not None and z > CAL["8.5.vg"]
              and med is not None and med >= CAL["8.5.medvg"])
    raison = ("" if eu else
              ("Aucun ménage de cette unité n'est apparié au dénombrement : "
               "soit `code_den` n'est pas renseigné, soit la table du "
               "dénombrement est absente de la base."
               if not eu else ""))
    out.append(resultat(
        "8.5", "Écart au point du dénombrement",
        "La VAD retourne chez des ménages DÉJÀ dénombrés : le même logement a "
        "donc été géolocalisé deux fois, à deux mois d'intervalle et par deux "
        "agents différents. Le test 8.4 dit si l'agent s'est déplacé ; "
        "celui-ci dit s'il est allé au BON endroit. Le rapprochement se fait "
        "sur `code_den`, le code de ménage attribué au dénombrement et repris "
        "dans le questionnaire VAD.",
        ["Distance de haversine entre le point VAD et le point du "
         "dénombrement du MÊME code_den",
         "Z de Mann-Whitney entre les distances de l'agent et celles du reste "
         "de la zone — unilatéral, excès seul",
         "Rangs et non valeurs : un écart aberrant ne fausse pas le test"],
        med, "m d'écart médian",
        n=len(eu), n_min=N_MIN6["ecart_den"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(eu))} ménage(s) "
                "appariés au dénombrement (les deux points renseignés).",
                f"Écart médian de l'agent : {fmt(med, 0)} m ; reste de la "
                f"zone : {fmt(med_z, 0)} m.",
                f"Au-delà de {fmt(DIST_LOIN, 0)} m : {fmt(loin)} ménage(s) "
                f"→ {fmt(part, 1)} % (la zone : {fmt(part_z, 1)} %). Au-delà "
                f"de {fmt(DIST_AILLEURS, 0)} m : {fmt(ailleurs)}.",
                f"Écart le plus grand : {fmt(pire, 0)} m.",
                f"Mann-Whitney sur les distances : Z = {fmt(z, 2)}",
                "Deux relevés du même logement diffèrent normalement de "
                "quelques dizaines de mètres : c'est la précision d'un GPS de "
                "terrain, pas une erreur."],
        conclusion=("→ Alerte : cet agent retrouve ses ménages nettement plus "
                    "loin du point du dénombrement que ses voisins — visite "
                    "au mauvais endroit, ou questionnaire rempli sans se "
                    "rendre au logement." if al else
                    "→ Vigilance : écarts au dénombrement plus fréquents que "
                    "dans la zone." if vg else
                    "→ Points VAD cohérents avec ceux du dénombrement."),
        seuils=[f"Z de Mann-Whitney > {fmt(CAL['8.5.al'], 2)} face à la zone "
                f"ET écart médian ≥ {fmt(CAL['8.5.med'], 0)} m",
                f"Vigilance : Z > {fmt(CAL['8.5.vg'], 2)} et écart médian "
                f"≥ {fmt(CAL['8.5.medvg'], 0)} m — ce palier attrape l'agent "
                "dont TOUS les relevés sont décalés sans qu'aucun ne dépasse "
                f"{fmt(DIST_LOIN, 0)} m",
                f"Repère : au-delà de {fmt(DIST_AILLEURS, 0)} m, il ne s'agit "
                "plus du même bâtiment",
                "Un ménage sans `code_den` (ménage nouveau, hors liste "
                "e-Fokontany) n'entre pas dans le calcul",
                "TROIS LIMITES, mesurées sur jeu d'essai (tests/test_gps_den.py) : "
                "le test reste AVEUGLE dans un hameau dont les logements "
                "tiennent dans moins de 60 m ; il accuse à tort un agent dont "
                "le GPS dérive de plus de 150 m quand ses collègues sont à "
                "25 m ; et il ne voit rien si TOUTE l'équipe reste sédentaire, "
                "puisqu'il compare l'agent à ses voisins"],
        repere=(f"zone : {fmt(med_z, 0)} m d'écart médian · "
                f"{fmt(loin)} ménage(s) au-delà de {fmt(DIST_LOIN, 0)} m"),
        stat=(f"Z = {fmt(z, 2)}" if z is not None else ""),
        alerte=al, vigilance=vg, portee=po, raison=raison))

    return out


VIGILANCE_PAR_TEST.update(SEUILS_VIGILANCE6)


# --------------------------------------------------------------------------
# NIVEAU 7 — Non-réponse et complétude (document, section 9)
# --------------------------------------------------------------------------
# Dernier niveau. Il ne juge plus ce qui a été répondu mais ce qui NE L'A PAS
# ÉTÉ : un blanc n'est inoffensif que s'il est aléatoire. Dès qu'il dépend de
# l'agent — module long évité, ménage nombreux écourté —, il devient un biais
# qui se propage à toutes les analyses en aval.
N_MIN7 = {"little": 20, "nr": 20, "couverture": 10,
          # 9.4 se calcule sur les membres PRÉCHARGÉS : sous 30, un seul
          # ménage nombreux ferait basculer le taux.
          "retrait": 30,
          # 9.5 se calcule sur les ménages à taille déclarée.
          "roster": 20}

SEUILS_VIGILANCE7 = {
    "9.1": "p du test de Little < 0,10 (structure de non-réponse douteuse)",
    "9.2.1": "une variable clé dont la non-réponse dépend de l'unité",
    "9.3": "taux de couverture < 95 %",
    "9.4": "excès de retraits face à la zone, Z > 1,96",
    "9.5": "roster plus court de 0,25 personne en moyenne sur 15 % des ménages",
}


def _rsu_accepte(m):
    """Le ménage a-t-il accepté le module RSU (logement + biens) ?

    Sans ce filtre, les 120 ménages qui ont refusé ou n'ont pas été sollicités
    compteraient comme 120 non-réponses sur CHAQUE variable H et AP : la
    non-réponse mesurée tomberait à 14,5 % de bruit structurel au lieu des
    1 % réels, et l'agent qui tombe sur des refus paraîtrait fautif."""
    return num(m.get("Perm_rsu")) == 1


# Variables CLÉS dont on suit la non-réponse (document, 9.2), avec leur
# condition d'APPLICABILITÉ : une question filtrée n'est pas une non-réponse.
VARS_NR_MEN = (
    ("nbmembre", "Nombre de membres", None),
    ("H1", "Matériau des murs", _rsu_accepte),
    ("H2", "Nombre de pièces", _rsu_accepte),
    ("H4", "Matériau du sol", _rsu_accepte),
    ("H5", "Matériau du toit", _rsu_accepte),
    ("H6", "Source d'éclairage", _rsu_accepte),
    ("H7", "Source d'eau de boisson", _rsu_accepte),
    ("H8", "Type de toilettes", _rsu_accepte),
    ("H9", "Évacuation des ordures", _rsu_accepte),
    ("H10", "Statut d'occupation", _rsu_accepte),
)

VARS_NR_MEM = (
    ("M3", "Sexe", None),
    ("M4", "Âge", None),
    ("M7", "Lien au chef de ménage", None),
    ("M2a", "Durée de résidence", None),
    ("M13", "Fréquentation scolaire", None),
    ("M16a", "Sait lire", None),
    ("M15a", "Année de fin d'études",
     lambda x: num(x.get("M13")) is not None and num(x.get("M13")) != M13_JAMAIS),
    ("M6", "Possède une CIN", lambda x: (num(x.get("M4")) or 0) >= AGE_CIN),
    ("M19", "Activité principale", lambda x: (num(x.get("M4")) or 0) > AGE_EMPLOI),
    ("AUEM17a", "Incapacité (vue)",
     lambda x: (num(x.get("M4")) or 0) > AGE_INCAPACITE),
)

# Le module « biens » compte pour UNE variable : ses 29 items sont posés d'un
# bloc, les suivre un par un ferait 29 lignes pour une seule décision d'agent.
NR_TOTAL = len(VARS_NR_MEN) + len(VARS_NR_MEM) + 1


def _nr_unite(ms):
    """{variable: (manquants, applicables)} sur un lot de ménages."""
    out = {}
    for col, _lib, filtre in VARS_NR_MEN:
        manq = app = 0
        for m in ms:
            if filtre and not filtre(m):
                continue
            app += 1
            if num(m.get(col)) is None:
                manq += 1
        out[col] = (manq, app)
    for col, _lib, filtre in VARS_NR_MEM:
        manq = app = 0
        for m in ms:
            for x in m.get("membres", ()):
                if filtre and not filtre(x):
                    continue
                app += 1
                if num(x.get(col)) is None:
                    manq += 1
        out[col] = (manq, app)
    manq = app = 0
    for m in ms:
        if not _rsu_accepte(m):
            continue
        app += 1
        if _score_ap(m) is None:
            manq += 1
    out["AP"] = (manq, app)
    return out


def _nr_libelles():
    lib = {c: l for c, l, _f in VARS_NR_MEN}
    lib.update({c: l for c, l, _f in VARS_NR_MEM})
    lib["AP"] = f"Biens du ménage ({len(COLS_AP)} items)"
    return lib


# Variables NUMÉRIQUES du test de Little : celles qui ont à la fois du sens en
# moyenne et de vrais manquants. Les deux rangs de logement viennent d'ORDRE_H
# (niveau 4), avec la même réserve sur l'ordre des modalités.
def _lignes_mcar(ms):
    """Vecteurs numériques à trous, un par ménage (None = valeur manquante)."""
    out = []
    for m in ms:
        h1, h5 = num(m.get("H1")), num(m.get("H5"))
        out.append([
            num(m.get("nbmembre")),
            num(m.get("taille_men")) or None,
            num(m.get("H2")),
            ORDRE_H["H1"].get(int(h1)) if h1 is not None else None,
            ORDRE_H["H5"].get(int(h5)) if h5 is not None else None,
        ])
    return out


VARS_MCAR = ("nombre de membres", "taille au dénombrement", "nombre de pièces",
             "rang des murs", "rang du toit")


# ------------------------------------------------------------------
# Rapprochement DÉNOMBREMENT ↔ VAD
# ------------------------------------------------------------------
# En conditions réelles, la VAD retourne chez des ménages DÉJÀ dénombrés : le
# même logement a donc été géolocalisé DEUX fois, à deux mois d'intervalle, par
# deux agents différents. Comparer les deux points est le seul contrôle qui
# vérifie qu'un agent s'est bien rendu à la bonne adresse — le test 8.4 dit s'il
# a bougé, celui-ci dit s'il est allé au BON endroit.
#
# La clé du rapprochement est `code_den`, le code de ménage attribué au
# dénombrement et repris tel quel dans le questionnaire VAD.
T_DEN_ROSTER = "segment_roster"
DEN_LAT, DEN_LON = "gps_coord__Latitude", "gps_coord__Longitude"
DEN_CODE = "code_den"

# Seuils de distance, en mètres. Deux relevés du MÊME logement diffèrent
# normalement de quelques dizaines de mètres : c'est la précision d'un GPS de
# terrain, pas une erreur. Au-delà de DIST_LOIN, on ne parle plus de bruit ;
# au-delà de DIST_AILLEURS, on parle d'un autre bâtiment.
DIST_LOIN, DIST_AILLEURS = 100.0, 250.0

MEMBRE_RETIRE = 3          # `membre_valid` : « efa tsy mpikambana intsony »
MOTIFS_RETRAIT = {1: "décès", 2: "déménagement / mariage", 3: "séparation",
                  4: "départ pour études", 5: "autre motif"}


def charger_den(conn):
    """{code_den: (latitude, longitude)} du DÉNOMBREMENT.

    Un même `code_den` peut apparaître plusieurs fois dans le roster (ménages
    scindés, ressaisies) : on garde le PREMIER point valide et on ignore les
    suivants. Prendre la moyenne serait pire — deux points éloignés donneraient
    un milieu qui n'est chez personne.

    Renvoie un dictionnaire vide si la table du dénombrement est absente : le
    test se met alors en « non calculé » au lieu de faire échouer la page."""
    out = {}
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT "{DEN_CODE}", "{DEN_LAT}", "{DEN_LON}" '
                    f'FROM "{T_DEN_ROSTER}"')
        for code, la, lo in cur.fetchall():
            c = txt(code)
            if not c or c in out:
                continue
            la, lo = num(la), num(lo)
            if la is None or lo is None or (la == 0 and lo == 0):
                continue
            if not (-90 <= la <= 90 and -180 <= lo <= 180):
                continue
            out[c] = (float(la), float(lo))
    except Exception:
        return {}
    return out


def ecart_den(ms):
    """Distances (m) entre le point VAD et le point du dénombrement du ménage.

    Ne renvoie que les ménages où les DEUX points existent : un ménage sans
    `code_den` (nouveau ménage, hors liste e-Fokontany) n'a rien à quoi se
    comparer, et l'absence n'est pas une anomalie."""
    out = []
    for m in ms:
        p = m.get("gps_den")
        la, lo = num(m.get("GPS__Latitude")), num(m.get("GPS__Longitude"))
        if not p or la is None or lo is None or (la == 0 and lo == 0):
            continue
        out.append((distance_m((float(la), float(lo)), p), m))
    return out


def _retraits(ms):
    """(retirés, préchargés, motifs) — le rognage du roster, s'il existe.

    Un membre PRÉCHARGÉ est une personne que le registre attendait dans ce
    ménage. L'agent a trois réponses possibles : elle est là (`membre_valid`
    = 1), c'est quelqu'un d'autre (= 2, nouveau membre), ou elle n'en fait
    plus partie (= 3). Le troisième cas est légitime — on déménage, on meurt,
    on se marie — mais c'est aussi la seule manière de raccourcir un roster
    sans laisser de trace ailleurs : la personne retirée ne déclenche pas son
    module individuel, et l'entretien s'abrège d'autant."""
    ret = pre = 0
    motifs = defaultdict(int)
    for m in ms:
        for x in m.get("membres", ()):
            v = num(x.get("membre_valid"))
            if v == MEMBRE_RETIRE:
                ret += 1
                pre += 1
                motifs[num(x.get("nomembre_motif"))] += 1
            elif v == 1:
                pre += 1
    return ret, pre, motifs


def _ecart_roster(ms):
    """Écarts (roster effectif − taille déclarée), ménage par ménage.

    `taille_men` est saisie par l'agent AVANT le roster et n'est pas recalculée
    ensuite : les deux sont donc deux mesures indépendantes du même ménage.
    ⚠️ Ne pas confondre avec `nbmembre`, qui compte les LIGNES du roster —
    membres retirés compris — et vaut donc la taille attendue par construction.
    C'est précisément pourquoi le test 9.3, bâti sur `nbmembre`, ne voit pas
    les retraits : il faut compter les membres effectivement présents."""
    out = []
    for m in ms:
        t = num(m.get("taille_men"))
        if t is None or t <= 0:
            continue
        eff = sum(1 for x in m.get("membres", ())
                  if num(x.get("membre_valid")) != MEMBRE_RETIRE)
        out.append(eff - int(t))
    return out


def _couverture(ms):
    """(personnes recensées, attendues, ménages appariés, source de l'attendu).

    Le document compare à `taille_men_efkt`, préchargée depuis les données
    Fokontany. Cette colonne est **entièrement NULL** dans les données VAD
    (défaut
    de préchargement déjà constaté sur la règle 5.1.2 du niveau 3). On retient
    donc la colonne d'attendu qui apparie le PLUS de ménages, à égalité celle du
    document : `taille_men`, préchargée elle aussi, mais depuis la taille
    relevée au DÉNOMBREMENT (`taille_menD`). Même nature — un attendu préchargé
    avant la visite —, et c'est bien l'écart à cet attendu que le test cherche."""
    best = (0, 0, 0, "")
    for col, src in (("taille_men_efkt",
                      "taille_men_efkt (préchargement e-Fokontany, celle du document)"),
                     ("taille_men",
                      "taille_men (taille relevée au dénombrement)")):
        obs = att = k = 0
        for m in ms:
            a, b = num(m.get("nbmembre")), num(m.get(col))
            if a is None or b is None or b <= 0:
                continue
            obs += a
            att += b
            k += 1
        if k > best[2]:
            best = (obs, att, k, src)
    return best


def niveau7(echelons):
    """Section 9 du document — non-réponse et complétude.

    Un blanc n'est inoffensif que s'il est aléatoire. Trois angles : la
    structure des manquants (9.1), leur dépendance à l'agent variable par
    variable (9.2), et les personnes qui manquent à l'appel (9.3)."""
    out = []

    # --- 9.1 Test MCAR de Little ------------------------------------------
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: len(ms), N_MIN7["little"])
    lignes = _lignes_mcar(u)
    d2, ddl = little_mcar(lignes)
    p = chi2_sf(d2, ddl) if d2 is not None and ddl else None
    motifs = len({tuple(x is not None for x in l) for l in lignes})
    complets = sum(1 for l in lignes if all(x is not None for x in l))
    al = bool(p is not None and p < 0.05)
    vg = bool(p is not None and p < 0.10)
    n_eff = n if p is not None else 0
    raison = ("" if n_eff else
              (f"Effectif insuffisant : {fmt(n)} ménage(s), le test en demande "
               f"{fmt(N_MIN7['little'])}." if n < N_MIN7["little"] else
               "Statistique de Little non définissable : trop peu de ménages "
               "complets pour estimer μ̂ et Σ̂, ou un seul motif de manquants."))
    out.append(resultat(
        "9.1", "MCAR de Little : les manquants sont-ils aléatoires ?",
        "Des valeurs manquantes réparties au hasard s'oublient ; des manquants "
        "qui dépendent de ce que le ménage est — plus nombreux, plus pauvre, "
        "plus éloigné — biaisent tout ce qu'on calculera ensuite. Le test "
        "compare les ménages selon ce qui leur manque : si ceux à qui il "
        "manque quelque chose ne ressemblent pas aux autres, l'hypothèse "
        "d'aléa tombe.",
        ["d² = Σ_j n_j (x̄_j − μ̂_j)ᵀ Σ̂_j⁻¹ (x̄_j − μ̂_j), j = motif de manquants",
         "d² ~ χ² sous H₀ (manquants complètement aléatoires)",
         "Variables suivies : " + ", ".join(VARS_MCAR)],
        d2, "d²", n=n_eff, n_min=N_MIN7["little"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(n)} ménage(s).",
                f"Motifs de manquants distincts : {fmt(motifs)} ; "
                f"ménages complets sur les 5 variables : {fmt(complets)}.",
                f"d² = {fmt(d2, 2)} à {fmt(ddl)} degré(s) de liberté, "
                f"p = {fmt(p, 4)}.",
                "μ̂ et Σ̂ sont estimées sur les ménages complets (le test "
                "d'origine passe par un algorithme EM — écart faible tant que "
                "les ménages complets dominent)."],
        conclusion=("→ Alerte : l'hypothèse MCAR est rejetée — les valeurs "
                    "manquantes dépendent de ce que sont les ménages, elles "
                    "biaisent les analyses en aval." if al else
                    "→ Vigilance : structure de non-réponse à la limite de "
                    "l'aléatoire." if vg else
                    "→ Manquants compatibles avec un simple aléa."),
        seuils=["p < 0,05 au test de Little : la non-réponse est structurée",
                "À croiser avec l'identifiant de l'agent (document, 9.1)"],
        repere=f"{motifs} motif(s) de manquants · {complets} ménages complets",
        stat=(f"p = {fmt(p, 3)}" if p is not None else ""),
        alerte=al, vigilance=vg, portee=po, raison=raison))

    # --- 9.2 / 9.2.1 Matrice de missingness et χ² non-réponse × agent -----
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: len(ms), N_MIN7["nr"])
    cles_u = {m["key"] for m in u}
    reste = [m for m in ref if m["key"] not in cles_u]
    nr_u, nr_r = _nr_unite(u), _nr_unite(reste)
    lib = _nr_libelles()
    detail, signif, pire, calculees = [], 0, None, 0
    for col in list(nr_u):
        mu, au = nr_u[col]
        mr, ar = nr_r[col]
        tu = 100.0 * mu / au if au else None
        tr = 100.0 * mr / ar if ar else None
        x2, ddl = chi2_2x2(mu, au - mu, mr, ar - mr)
        if x2 is None:
            detail.append(f"{col} {lib[col]} : {fmt(tu, 1)} % de non-réponse "
                          f"(zone {fmt(tr, 1)} %) — χ² non calculable")
            continue
        calculees += 1
        pv = chi2_sf(x2, ddl)
        pc = min(1.0, pv * NR_TOTAL)          # Bonferroni : NR_TOTAL variables
        detail.append(f"{col} {lib[col]} : {fmt(tu, 1)} % de non-réponse sur "
                      f"{fmt(au)} cas applicables (zone {fmt(tr, 1)} %) — "
                      f"χ² = {fmt(x2, 1)}, p = {fmt(pv, 4)}, "
                      f"corrigée {fmt(pc, 4)}")
        # Seul un EXCÈS de non-réponse accuse l'unité : en répondre plus que
        # la zone n'est pas un défaut.
        if tu is not None and tr is not None and tu > tr and pc < 0.05:
            signif += 1
            if pire is None or pc < pire[1]:
                pire = (f"{col} {lib[col]}", pc, tu, tr)
    al = signif >= 2
    vg = signif >= 1
    n_eff = n if calculees else 0
    raison = ("" if n_eff else
              (f"Effectif insuffisant : {fmt(n)} ménage(s), le test en demande "
               f"{fmt(N_MIN7['nr'])}." if n < N_MIN7["nr"] else
               f"Aucune des {NR_TOTAL} variables n'est comparable : l'unité "
               "couvre toute sa zone de référence, il ne reste aucun ménage "
               "hors d'elle pour servir de témoin."))
    out.append(resultat(
        "9.2.1", "Non-réponse dépendante de l'agent",
        "Un module long — l'emploi, la scolarité — se laisse volontiers "
        "oublier quand le temps manque. La matrice de non-réponse croise "
        f"chaque variable clé ({NR_TOTAL} au total) avec l'unité, et le χ² dit "
        "lesquelles sont laissées vides plus souvent ici qu'ailleurs dans la "
        "zone. Les questions filtrées ne comptent pas comme non-réponses.",
        ["χ²_v = Σ_a (O_a − E_a)² / E_a sur la table (unité, reste) × "
         "(manquant, renseigné)",
         f"p corrigée = p × {NR_TOTAL} (Bonferroni)"],
        float(signif) if calculees else None, f"variable(s) sur {NR_TOTAL}",
        n=n_eff, n_min=N_MIN7["nr"],
        calcul=([f"Unité mesurée : {po['libelle']} — {fmt(n)} ménage(s). "
                 "Voici sa matrice de non-réponse, variable par variable :"]
                + detail),
        conclusion=("→ Alerte : plusieurs variables clés sont laissées vides "
                    "nettement plus souvent que dans le reste de la zone." if al
                    else "→ Vigilance : une variable clé est sous-remplie par "
                    "rapport à la zone." if vg else
                    "→ Non-réponse comparable au reste de la zone."),
        seuils=[f"p corrigée < 0,05 pour au moins 2 des {NR_TOTAL} variables "
                "clés, en EXCÈS de non-réponse",
                "Les questions non applicables (filtres) sont exclues"],
        repere=(f"pire : {pire[0]} — {fmt(pire[2], 1)} % contre "
                f"{fmt(pire[3], 1)} % dans la zone" if pire else
                "aucune variable en excès de non-réponse"),
        stat=(f"{signif}/{NR_TOTAL} signif." if calculees else ""),
        alerte=al, vigilance=vg, portee=po, raison=raison))

    # --- 9.3 Taux de couverture -------------------------------------------
    u, ref, n, po, _pairs = _escalade(
        echelons, lambda ms: _couverture(ms)[2], N_MIN7["couverture"])
    obs, att, apparies, src = _couverture(u)
    obs_z, att_z, _k, _s = _couverture(ref)
    taux = 100.0 * obs / att if att else None
    taux_z = 100.0 * obs_z / att_z if att_z else None
    manquantes = att - obs
    al = bool(taux is not None and taux < 90)
    vg = bool(taux is not None and taux < 95)
    out.append(resultat(
        "9.3", "Couverture : personnes recensées / attendues",
        "Chaque ménage arrive avec une taille attendue, préchargée avant la "
        "visite. Lister moins de personnes que prévu, de façon répétée et "
        "toujours dans le même sens, c'est abréger la zone plutôt que la "
        "couvrir — le sous-dénombrement que la section 9.3 vise.",
        ["Taux = (Σ nbmembre observé) / (Σ taille attendue) × 100",
         f"Attendu pris dans : {src or '—'}"],
        taux, "%", n=n, n_min=N_MIN7["couverture"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(apparies)} ménage(s) "
                "dont l'attendu est renseigné.",
                f"Personnes recensées : {fmt(obs)} ; attendues : {fmt(att)} "
                f"→ {fmt(manquantes)} personne(s) d'écart.",
                f"Source de l'attendu : {src or 'aucune'}.",
                f"Taux de la zone de référence : {fmt(taux_z, 1)} %.",
                "Un écart peut être réel (départs, décès depuis le "
                "dénombrement) : l'alerte désigne une zone à revisiter, pas "
                "une faute établie."],
        conclusion=("→ Alerte : moins de 90 % des personnes attendues ont été "
                    "recensées — sous-dénombrement à vérifier sur le terrain."
                    if al else "→ Vigilance : couverture en retrait de "
                    "l'attendu." if vg else
                    "→ Couverture conforme à l'attendu."),
        seuils=["Taux de couverture < 90 % sans justification de terrain "
                "documentée (zone recomposée, migration…)"],
        repere=f"zone : {fmt(taux_z, 1)} % · {fmt(manquantes)} personne(s) d'écart",
        stat=(f"{fmt(obs)}/{fmt(att)}" if att else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 9.4 Retrait de membres préchargés --------------------------------
    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: _retraits(ms)[1],
                                      N_MIN7["retrait"])
    ret, pre, motifs = _retraits(u)
    ret_r, pre_r, _mz = _retraits(ref)
    ret_r, pre_r = ret_r - ret, pre_r - pre          # le RESTE de la zone
    part = 100.0 * ret / pre if pre else None
    part_z = 100.0 * ret_r / pre_r if pre_r > 0 else None
    z = None
    if pre and pre_r > 0:
        p1, p2 = ret / float(pre), ret_r / float(pre_r)
        pc = (ret + ret_r) / float(pre + pre_r)
        den = (math.sqrt(pc * (1 - pc) * (1 / float(pre) + 1 / float(pre_r)))
               if 0 < pc < 1 else 0)
        if den:
            z = (p1 - p2) / den
    al = bool(z is not None and z > CAL["9.4.al"]
              and part is not None and part >= CAL["9.4.part"])
    vg = bool(z is not None and z > CAL["9.4.vg"]
              and part is not None and part >= CAL["9.4.partvg"])
    det = ", ".join(f"{MOTIFS_RETRAIT.get(k, 'motif ' + str(k))} : {fmt(v)}"
                    for k, v in sorted(motifs.items(),
                                       key=lambda kv: -kv[1])) or "—"
    out.append(resultat(
        "9.4", "Retrait de membres préchargés",
        "Le ménage arrive avec une liste de personnes attendues. En déclarer "
        "une « plus membre du ménage », c'est la sortir du roster — et avec "
        "elle tout son module individuel. C'est légitime (décès, "
        "déménagement, mariage) et c'est aussi le seul moyen d'abréger un "
        "entretien sans laisser de trace ailleurs : le test 9.3 n'y voit rien, "
        "puisqu'il compte les LIGNES du roster, retirés compris. On compare "
        "donc la part de retraits de l'agent à celle du reste de sa zone, où "
        "les mêmes décès et les mêmes départs ont eu lieu.",
        ["Part = membres déclarés sortis / membres préchargés",
         "Z = (p₁ − p₂) / √[ p̂(1−p̂)(1/n₁ + 1/n₂) ] — unilatéral, excès seul"],
        part, "% des préchargés retirés", n=n, n_min=N_MIN7["retrait"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(ret)} retrait(s) sur "
                f"{fmt(pre)} membre(s) préchargé(s) → {fmt(part, 1)} %.",
                f"Reste de la zone : {fmt(ret_r)} sur {fmt(pre_r)} → "
                f"{fmt(part_z, 1)} %.",
                f"Écart rapporté au bruit : Z = {fmt(z, 2)}",
                f"Motifs invoqués : {det}",
                "Les mêmes événements démographiques touchent toute la zone : "
                "c'est l'ÉCART à ses voisins qui interroge, pas le niveau."],
        conclusion=("→ Alerte : cet agent sort du roster une part de personnes "
                    "attendues bien supérieure à ses voisins — à recontrôler "
                    "ménage par ménage, les personnes retirées n'ayant pas été "
                    "interrogées." if al else
                    "→ Vigilance : retraits plus fréquents que dans la zone."
                    if vg else "→ Retraits comparables au reste de la zone."),
        seuils=[f"Z > {fmt(CAL['9.4.al'], 2)} face à la zone ET au moins "
                f"{fmt(CAL['9.4.part'], 0)} % des préchargés retirés",
                "Test UNILATÉRAL : seul un EXCÈS de retraits est signalé",
                "La condition d'ampleur évite de dénoncer un écart "
                "significatif mais minuscule"],
        repere=(f"zone : {fmt(part_z, 1)} % · {fmt(ret)} personne(s) sortie(s) "
                f"du roster"),
        stat=(f"Z = {fmt(z, 2)}" if z is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    # --- 9.5 Roster plus court que la taille déclarée ---------------------
    u, ref, n, po, _pairs = _escalade(echelons, lambda ms: len(_ecart_roster(ms)),
                                      N_MIN7["roster"])
    ecarts = _ecart_roster(u)
    moy = moyenne(ecarts) if ecarts else None
    exacts = sum(1 for e in ecarts if e == 0)
    courts = sum(1 for e in ecarts if e < 0)
    longs = sum(1 for e in ecarts if e > 0)
    pire = min(ecarts) if ecarts else None
    # La moyenne seule est fragile : un unique ménage saisi « 102 » pour douze
    # personnes — une faute de frappe, pas une habitude — la fait basculer à
    # lui seul. On exige donc aussi qu'une PART notable des ménages soit
    # concernée : c'est la répétition qui fait le tâtonnement, pas l'amplitude
    # d'un cas isolé.
    p_courts = 100.0 * courts / len(ecarts) if ecarts else None
    al = bool(moy is not None and moy <= CAL["9.5.al"]
              and p_courts is not None and p_courts >= CAL["9.5.part"])
    vg = bool(moy is not None and moy <= CAL["9.5.vg"]
              and p_courts is not None and p_courts >= CAL["9.5.partvg"])
    out.append(resultat(
        "9.5", "Roster plus court que la taille déclarée",
        "L'agent annonce d'abord une taille de ménage, puis saisit les "
        "personnes une à une. Les deux mesures sont indépendantes et doivent "
        "coïncider. Saisir SYSTÉMATIQUEMENT moins de personnes qu'annoncé — "
        "toujours dans le même sens — n'est pas une étourderie : c'est un "
        "tâtonnement qui raccourcit le travail restant. Le test ne regarde "
        "que ce sens-là.",
        ["Écart = personnes effectivement saisies − taille déclarée",
         "Moyenne des écarts sur les ménages de l'unité (les membres sortis "
         "du roster ne sont pas comptés comme saisis)"],
        moy, "personne(s) d'écart moyen", n=n, n_min=N_MIN7["roster"],
        calcul=[f"Unité mesurée : {po['libelle']} — {fmt(len(ecarts))} "
                f"ménage(s) à taille déclarée.",
                f"Roster plus COURT qu'annoncé : {fmt(courts)} ménage(s) ; "
                f"exact : {fmt(exacts)} ; plus long : {fmt(longs)}.",
                f"Écart moyen : {fmt(moy, 2)} personne(s) ; "
                f"{fmt(p_courts, 0)} % des ménages sont concernés.",
                f"Écart le plus grand dans le sens du manque : {fmt(pire, 0)} "
                "— un écart isolé de grande amplitude est une faute de saisie, "
                "pas une habitude ; c'est la PART des ménages concernés qui "
                "distingue les deux."],
        conclusion=("→ Alerte : les rosters de cet agent sont "
                    "systématiquement plus courts que les tailles qu'il "
                    "annonce lui-même — vérifier les ménages concernés."
                    if al else
                    "→ Vigilance : tendance à saisir moins de personnes "
                    "qu'annoncé." if vg else
                    "→ Roster et taille déclarée cohérents."),
        seuils=[f"Écart moyen ≤ {fmt(CAL['9.5.al'], 2)} personne ET au moins "
                f"{fmt(CAL['9.5.part'], 0)} % des ménages concernés",
                "Test UNILATÉRAL : un roster plus LONG qu'annoncé n'est pas "
                "signalé ici — c'est une correction, pas un raccourci"],
        repere=(f"{fmt(courts)} roster(s) trop court(s) sur {fmt(len(ecarts))}"
                f" ({fmt(p_courts, 0)} %)" if ecarts else ""),
        stat=(f"pire écart {fmt(pire, 0)}" if pire is not None else ""),
        alerte=al, vigilance=vg, portee=po))

    return out


VIGILANCE_PAR_TEST.update(SEUILS_VIGILANCE7)


NIVEAUX = [
    (1, "Indicateurs de suivi terrain par agent",
     "Section 3 du document — indicateurs calculables quotidiennement à partir "
     "des métadonnées de collecte. Ils ne constituent pas des tests "
     "statistiques formels mais un système d'alerte précoce.", niveau1),
    (2, "Tests de cohérence démographique",
     "Section 4 du document — indices démographiques éprouvés (Whipple, Myers, "
     "indice ONU) et tests d'effet-agent. Ils répondent à la question de "
     "départ : le nombre de membres et les âges sont-ils remplis par "
     "tâtonnement ?", niveau2),
    (3, "Cohérence « cycle de vie »",
     "Section 5 du document — les règles logiques qui lient les modules entre "
     "eux (roster, âges, CIN, scolarité, emploi, biens), transformées en taux "
     "de violation comparables entre agents, puis résumées en un score "
     "composite.", niveau3),
    (4, "Caractéristiques du logement (H1–H10)",
     "Section 6 du document — dans une même zone, les matériaux et les "
     "infrastructures varient peu d'un ménage à l'autre. Tout écart marqué "
     "entre un agent et sa zone sur ces variables est donc un effet-agent, "
     "pas un effet de terrain.", niveau4),
    (5, "Biens du ménage (module AP)",
     "Section 7 du document — les items binaires du module servent à construire "
     "l'indice de bien-être matériel. Cinq angles sur la même question : "
     "décrivent-ils un vrai ménage observé, ou ont-ils été cochés en bloc ?",
     niveau5),
    (6, "Détection de fraude et de duplication",
     "Section 8 du document — les niveaux précédents demandent si l'agent "
     "mesure bien ; celui-ci demande s'il est allé sur place. Quatre traces "
     "indépendantes d'un questionnaire non administré : recopié, inventé, "
     "trop rapide, ou relevé sans déplacement.", niveau6),
    (7, "Non-réponse et complétude",
     "Section 9 du document — dernier niveau : il ne juge plus ce qui a été "
     "répondu mais ce qui ne l'a pas été. Un blanc n'est inoffensif que s'il "
     "est aléatoire ; dès qu'il dépend de l'agent, il devient un biais qui se "
     "propage à toutes les analyses en aval.", niveau7),
]

# --------------------------------------------------------------------------
# Chargement des données brutes nécessaires aux tests
# --------------------------------------------------------------------------
import db_source
import vad_db
from vad_db import txt, num, jour

T_MEN, T_MEM, T_DIAG = vad_db.TABLE_MENAGE, vad_db.TABLE_MEMBRE, vad_db.TABLE_DIAG

# Colonnes ménage lues pour l'ensemble des niveaux (les niveaux 2 à 7 en
# utiliseront davantage ; la liste grandira avec eux).
# Biens AGRICOLES du questionnaire (règle 5.1.13). Le document vise
# « AP09–AP25 », soit toute la famille « Agriculture & élevage » de
# `vad_core.FAMILLE_BIEN`. Pris tel quel, ce périmètre vide la règle de son
# sens : mesuré sur le district 5201, la bêche (136 ménages sur 318), le
# poulet gasy (165) et le puits (103) sont détenus par presque tout le monde,
# et la règle dénonçait alors **64,6 %** des ménages. Restreinte aux MOYENS DE
# PRODUCTION — ceux qu'on ne possède pas sans cultiver — elle tombe à 24,7 %
# et redevient un signal. Élevage et petit outillage restent exclus ; la liste
# est modifiable d'une ligne si les statisticiens du RSU en jugent autrement.
CODES_AGRI = (10,   # charrue (traction animale)
              11,   # charrette (traction animale)
              12,   # herse (traction animale)
              14,   # stockage agricole
              15,   # champ ou rizière (non métayage)
              17,   # matériel de pêche : pirogue, filet
              20,   # irrigation
              25)   # pratique la culture d'exportation
# Items binaires du module « FANANAN'NY TOKANTRANO » (niveau 5). DEUX nommages
# coexistent selon la version du questionnaire, et les données ne disent
# pas laquelle elles portent — d'où la résolution à la lecture, dans `_resoudre_ap()` :
#   - jusqu'aux données RSU de septembre 2025, le module était éclaté en quatre
#     questions et les colonnes s'appelaient `AP1__1`, `AP2__4`, `AP4__25`… —
#     AP1 mobilier, AP2 énergie/TIC, AP3 transport, AP4 agriculture/élevage ;
#   - depuis les données RSU d'octobre 2025, c'est UNE question à choix multiple et
#     les colonnes s'appellent `AP__1` … `AP__26`.
# Le CODE d'item est le même des deux côtés (`AP4__11` et `AP__11` sont tous
# deux la charrette) ; seul le préfixe de groupe a disparu, en même temps que
# les items 27 à 29. Les groupes ne servent qu'à documenter : aucun test ne
# raisonne par groupe, tous parcourent la liste plate `COLS_AP`.
GROUPES_AP = {"AP1": (1, 2, 3, 18, 27),
              "AP2": (4, 5, 6, 7, 8, 26, 28),
              "AP3": (9, 29),
              "AP4": (10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25)}
COLS_AP_GROUPES = tuple(f"{g}__{c}" for g, codes in GROUPES_AP.items() for c in codes)

# Valeurs par défaut : le nommage historique. `_resoudre_ap()` les remplace dès
# que les données lues portent le nommage plat.
COLS_AP = COLS_AP_GROUPES
COLS_AGRI = tuple(f"AP4__{c}" for c in CODES_AGRI)

COLS_MEN_BASE = (("interview__key", "interview__id", "nom_cm", "CQ3", "CQ4",
                  "start_ec", "nbmembre", "taille_men", "taille_men_efkt",
                  "Perm_rsu", "Perm_indiv", "interview__status",
                  "GPS__Latitude", "GPS__Longitude", "H2", "address_id",
             "code_den")
                 + tuple(HAFA))
COLS_MEN = COLS_MEN_BASE + COLS_AP


def _resoudre_ap(dispo):
    """Aligne COLS_AP / COLS_AGRI / COLS_MEN sur le nommage réellement exporté.

    Appelée par `charger()` avec les colonnes du fichier ménage. Sans elle, le
    niveau 5 entier (7.1 à 7.5), la règle 5.1.13 et le test 8.1 restaient « non
    calculables » sur les données RSU d'octobre 2025 : le code cherchait
    `AP1__1`, la base contenait `AP__1`. Les données étaient là, le branchement manquait."""
    global COLS_AP, COLS_AGRI, COLS_MEN
    dispo = set(dispo)
    groupes = [c for c in COLS_AP_GROUPES if c in dispo]
    plat = sorted((c for c in dispo
                   if c.startswith("AP__") and c[4:].isdigit()),
                  key=lambda c: int(c[4:]))
    if len(plat) > len(groupes):
        COLS_AP = tuple(plat)
        COLS_AGRI = tuple(f"AP__{c}" for c in CODES_AGRI if f"AP__{c}" in dispo)
    else:
        COLS_AP = COLS_AP_GROUPES
        COLS_AGRI = tuple(f"AP4__{c}" for c in CODES_AGRI)
    COLS_MEN = COLS_MEN_BASE + COLS_AP
    return COLS_AP
# Niveau 3 : durée de résidence (M2a), CIN (M6, M6b), scolarité (M15a),
# alphabétisation (M16a/M16b), activité (M19) et incapacités (AUEM17a-c).
# Niveau 6 : le NUMÉRO de CIN (M6a) — seul nombre de grande plage saisi par
# l'agent, donc seul support possible du test des premiers chiffres (8.2).
# Niveau 7 : `membre_valid` dit si la ligne est un membre préchargé confirmé
# (1), un nouveau membre (2) ou une personne DÉCLARÉE SORTIE du ménage (3) ;
# `nomembre_motif` porte le motif invoqué pour la sortie. C'est le seul endroit
# de la base où se lit un retrait de personne — donc le seul support possible
# du test 9.4.
COLS_MEM = (("interview__key", "M1a", "M3", "M4", "M4b", "M7", "M13", "M14",
             "M2a", "M6", "M6a", "M6b", "M15a", "M16a", "M16b", "M19",
             "AUEM17a", "AUEM17b", "AUEM17c",
             "membre_valid", "nomembre_motif")
            + tuple(NSP))


def _dataset(conn, table, where="", params=()):
    return db_source.DbDataset(conn, table, where=where, params=params)


# Colonnes RÉELLEMENT présentes dans le dernier lot de données lu.
# `charger()` remplace
# par des valeurs nulles toute colonne attendue et absente : sans cette trace,
# rien ne distingue plus « la variable existe et n'a jamais été remplie » de
# « la variable n'existe pas dans cette version du questionnaire ». Les deux
# sont des incidents, mais pas le même, et `vad_qualite_base` les sépare.
SCHEMA_LU = {"menage": set(), "membre": set()}


def charger(conn, districts=None, communes=None):
    """Ménages (avec leurs membres) du périmètre, prêts pour les tests."""
    where, params = vad_db._clause_perimetre(conn, districts, communes)
    dm = _dataset(conn, T_MEN, where, params)
    cols = set(dm.varnames)
    # Points du dénombrement, indexés par `code_den`. Une seule requête pour
    # tout le périmètre : la table du dénombrement fait des dizaines de milliers
    # de lignes, la relire ménage par ménage serait ruineux.
    pts_den = charger_den(conn)
    SCHEMA_LU["menage"] = set(cols)
    SCHEMA_LU["membre"] = set()
    _resoudre_ap(cols)
    vide = [None] * dm.nobs
    col = lambda n: dm.col(n) if n in cols else vide
    lu = {n: col(n) for n in COLS_MEN}
    com_l, com_c = (dm.col_decoded("CQ8") if "CQ8" in cols else vide), col("CQ8")
    fkt_l = dm.col_decoded("CQ9") if "CQ9" in cols else vide

    agents, ces = {}, {}
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT "interview__key", "responsible" FROM "{T_DIAG}"')
        agents = {k: v for k, v in cur.fetchall()}
    except Exception:
        pass
    try:
        cur.execute('SELECT "interview__key", "CE" FROM "vad_ce"')
        ces = {k: v for k, v in cur.fetchall()}
    except Exception:
        pass
    duree = {}
    try:
        cur.execute(f'SELECT "interview__key", "interview__duration" FROM "{T_DIAG}"')
        duree = {k: _minutes(v) for k, v in cur.fetchall()}
    except Exception:
        pass
    err_ss = {}
    try:
        cur.execute(f'SELECT "interview__key", "entities__errors" FROM "{T_DIAG}"')
        err_ss = {k: num(v) for k, v in cur.fetchall()}
    except Exception:
        pass

    menages = []
    for i in range(dm.nobs):
        k = txt(lu["interview__key"][i])
        m = {n: lu[n][i] for n in COLS_MEN}
        m.update({
            "key": k, "date": jour(lu["CQ3"][i]) or jour(lu["start_ec"][i]),
            "commune": txt(com_l[i]), "code_commune": num(com_c[i]),
            "fokontany": txt(fkt_l[i]),
            "agent": agents.get(k, ""), "ce": ces.get(k, ""),
            "duree": duree.get(k), "erreurs_ss": err_ss.get(k) or 0,
            "gps_den": pts_den.get(txt(lu["code_den"][i])),
            "membres": [],
        })
        menages.append(m)

    par_key = {m["key"]: m for m in menages}
    sous = f'SELECT "interview__key" FROM "{T_MEN}"' + (f" WHERE {where}" if where else "")
    try:
        dmb = _dataset(conn, T_MEM, f'"interview__key" IN ({sous})', params)
    except Exception:
        dmb = None
    if dmb is not None and dmb.nobs:
        mc = set(dmb.varnames)
        SCHEMA_LU["membre"] = set(mc)
        videm = [None] * dmb.nobs
        mcol = lambda n: dmb.col(n) if n in mc else videm
        lum = {n: mcol(n) for n in COLS_MEM}
        # Enquête VAD : pour un membre DÉJÀ CONNU du registre (`membre_valid`
        # = 1), la valeur confirmée reste dans `<var>_preload` et la colonne
        # courante est vide. Sans ce repli, ces membres sortaient des tests
        # avec une valeur manquante : 20 893 membres sur 65 884 dans les
        # données RSU d'octobre 2025, soit un tiers de la base — et pas au hasard, puisque
        # ce sont exactement les ménages revisités. Les niveaux 2, 3 et 7 en
        # étaient faussés (32 % des ménages paraissaient sans chef, et le test
        # 9.2.1 comptait le préchargement comme de la non-réponse).
        pre = {n: mcol(n + "_preload") for n in COLS_MEM
               if (n + "_preload") in mc}
        for i in range(dmb.nobs):
            k = txt(lum["interview__key"][i])
            if k in par_key:
                mem = {n: lum[n][i] for n in COLS_MEM}
                for n, colp in pre.items():
                    if mem.get(n) in (None, "") and colp[i] not in (None, ""):
                        mem[n] = colp[i]
                par_key[k]["membres"].append(mem)
    return menages


def _minutes(v):
    """`interview__duration` de Survey Solutions -> minutes (hh:mm:ss ou nombre)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if ":" in s:
        p = s.split(":")
        try:
            h, mi, se = (float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0)
            return h * 60 + mi + se / 60
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# MATRICE CE × AE : tous les agents, tous les tests, en un tableau
# --------------------------------------------------------------------------
def zone_agent(m):
    """Clé de la ZONE d'un ménage : le fokontany, qualifié par sa commune."""
    return (m["commune"] or "(commune non renseignée)",
            m["fokontany"] or "(fokontany inconnu)")


def reference(ms_ae, par_fkt, par_commune, commune):
    """Ménages auxquels comparer CET agent, et la phrase qui l'explique.

    Le fokontany est la zone de dénombrement du RSU : les ménages y partagent
    l'habitat, les matériaux, le niveau de vie. C'est le seul échelon où
    « toutes choses égales par ailleurs » tient à peu près, donc le seul où un
    écart s'impute à l'agent plutôt qu'au terrain. Mesuré sur les données
    RSU d'octobre 2025, 43 % à 73 % de l'écart entre agents sur les indicateurs qui
    nourrissent les tests (matériaux, biens, taille du ménage, arrondi des
    âges, durée) s'explique par le seul fokontany : comparé à sa commune — a
    fortiori à son district — un agent est d'abord jugé sur son village.

    Repli : un agent SEUL dans son fokontany n'y a pas de pair, et s'y comparer
    reviendrait à se comparer à soi-même — le test deviendrait muet. On remonte
    alors à la commune, et la ligne le dit."""
    zs = {zone_agent(m) for m in ms_ae}
    if not zs:
        return par_commune.get(commune, []), "commune", commune, True
    # La zone est l'UNION des fokontany où l'agent a travaillé — 85 % des
    # agents n'en ont qu'un. L'union, et non le fokontany dominant : plusieurs
    # tests retranchent l'unité de sa référence pour obtenir « le reste de la
    # zone », ce qui exige que tous les ménages de l'agent y soient. Un
    # fokontany dominant laisserait le reliquat dehors et produirait des
    # effectifs négatifs.
    if len(zs) == 1:
        ms_z = par_fkt.get(next(iter(zs)), [])
    else:
        vus, ms_z = set(), []
        for z in sorted(zs):
            for m in par_fkt.get(z, []):
                if id(m) not in vus:
                    vus.add(id(m))
                    ms_z.append(m)
    if len({m["agent"] for m in ms_z}) >= 2:
        lib = " + ".join(sorted(z[1] for z in zs))
        return ms_z, "fokontany", lib, False
    return par_commune.get(commune, []), "commune", commune, True


def _echelon_agent(ae, ms_ae, ms_ref, pairs_ref):
    """Échelon UNIQUE : l'agent. Pas d'escalade vers le CE ni la commune.

    C'est la différence de fond avec la fiche détaillée : dans la matrice, une
    couleur porte sur l'agent de la ligne et sur personne d'autre. Si son
    effectif ne suffit pas, `_escalade` ne trouve pas d'échelon plus large,
    `resultat()` marque `insuffisant` et la cellule vaut « nd ». Afficher à la
    place la valeur de son CE remplirait le tableau de verdicts collectifs
    identiques pour toute une équipe — l'inverse de ce qu'un tableau par agent
    doit montrer. La RÉFÉRENCE de comparaison est donnée par `reference()` :
    le fokontany de l'agent, sa commune s'il y est seul."""
    return [{"niveau": "agent", "libelle": f"l'agent {ae}",
             "unites": ms_ae, "ref": ms_ref, "pairs": pairs_ref}]


def tests_niveau(f, echelons, matrice=False):
    """Tests d'un niveau, une fois retirés ceux qu'on ne montre pas.

    `TESTS_SANS_SUPPORT` disparaît partout — ces tests ne produisent rien.
    `TESTS_HORS_MATRICE` ne disparaît que du tableau du superviseur : la fiche
    détaillée d'un agent les garde, parce que c'est elle qui doit justifier une
    remarque faite à l'agent, et qu'un contrôle resté vert en fait partie."""
    exclus = TESTS_SANS_SUPPORT | (TESTS_HORS_MATRICE if matrice else set())
    return [t for t in f(echelons) if t["num"] not in exclus]


def colonnes():
    """Descripteur des colonnes de tests (num, titre, unité, effectif minimal).

    Obtenu en faisant tourner les niveaux sur un échelon VIDE : la liste des
    tests reste ainsi définie à un seul endroit, le code des niveaux."""
    vide = _echelon_agent("—", [], [], [])
    out = []
    for numero, titre, _d, f in NIVEAUX:
        for t in tests_niveau(f, vide, matrice=True):
            out.append({"num": t["num"], "titre": t["titre"],
                        "unite": t["unite"], "nMin": t["nMin"],
                        "principe": t["principe"], "seuils": t["seuils"],
                        "vigilance": VIGILANCE_PAR_TEST.get(t["num"], ""),
                        "niveau": numero, "niveauTitre": titre})
    return out


def graphiques_agent(ms_ae, ms_ref):
    """Séries à tracer sur la fiche d'un agent : lui, puis sa zone.

    Toujours en POURCENTAGES. Un agent pèse quelques dizaines de ménages face
    à une zone qui en compte plusieurs centaines : superposer des effectifs ne
    comparerait que des charges de travail. Ce sont les mêmes chiffres que les
    tests — la courbe ne prouve rien de plus, elle rend visible en un coup
    d'œil ce qu'un Z-score énonce."""
    def pyr(ms):
        c = defaultdict(int)
        for m in ms:
            for x in m.get("membres", ()):
                a, sx = num(x.get("M4")), num(x.get("M3"))
                if a is None or sx not in (SEXE_H, SEXE_F):
                    continue
                c[(min(int(a) // 5, 16), 1 if sx == SEXE_H else 2)] += 1
        return c
    pa, pz = pyr(ms_ae), pyr(ms_ref)
    ta, tz = sum(pa.values()) or 1, sum(pz.values()) or 1
    pyramide = [{"groupe": (f"{t * 5}-{t * 5 + 4}" if t < 16 else "80 et +"),
                 "aH": round(100.0 * pa.get((t, 1), 0) / ta, 2),
                 "aF": round(100.0 * pa.get((t, 2), 0) / ta, 2),
                 "zH": round(100.0 * pz.get((t, 1), 0) / tz, 2),
                 "zF": round(100.0 * pz.get((t, 2), 0) / tz, 2)}
                for t in range(17)]

    # Préférence de chiffre terminal : le test 4.2 en une image.
    def chiffres(ms):
        a10 = [a for a in _membres_ages(ms) if 10 <= a <= 89]
        t = len(a10) or 1
        return [round(100.0 * sum(1 for a in a10 if a % 10 == d) / t, 2)
                for d in range(10)]

    # Production journalière : la courbe de charge de l'agent.
    par_jour = defaultdict(int)
    for m in ms_ae:
        if m.get("date"):
            par_jour[m["date"]] += 1

    # Durées : même découpage pour l'agent et la zone, en % de ses entretiens.
    bornes = (0, 10, 20, 30, 40, 50, 60, 90, 10 ** 9)
    def durees(ms):
        d = [m["duree"] for m in ms if m.get("duree")]
        t = len(d) or 1
        return [round(100.0 * sum(1 for x in d
                                  if bornes[i] <= x < bornes[i + 1]) / t, 2)
                for i in range(len(bornes) - 1)]
    return {"pyramide": pyramide,
            "chiffres": {"agent": chiffres(ms_ae), "zone": chiffres(ms_ref)},
            "jours": [{"j": k, "n": v} for k, v in sorted(par_jour.items())],
            "durees": {"libelles": ["< 10", "10-20", "20-30", "30-40", "40-50",
                                    "50-60", "60-90", "90 +"],
                       "agent": durees(ms_ae), "zone": durees(ms_ref)}}


def _cellules(ae, ms_ae, ms_com, pairs_com):
    """Une ligne de la matrice : le résultat de chaque test pour CET agent."""
    ech = _echelon_agent(ae, ms_ae, ms_com, pairs_com)
    cells = []
    for _n, _t, _d, f in NIVEAUX:
        for t in tests_niveau(f, ech, matrice=True):
            cells.append({"v": t["valeur"], "g": t["gravite"], "n": t["n"],
                          "nMin": t["nMin"], "r": t["repere"], "s": t["stat"],
                          # « nd » a toujours la même conclusion : la page la
                          # reconstruit, on ne la répète pas des milliers de fois.
                          "c": "" if t["gravite"] == "nd" else t["conclusion"]})
    return cells


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------
def calculer(conn, districts=None, communes=None, cible=None):
    """Arbre Commune → CE → AE, et résultats des tests pour UN agent.

    Deux sorties, pour deux usages (maj 2026-09-19) :

      - `matrice` : TOUS les agents du périmètre, une ligne par (CE, AE), une
        colonne par test, chaque cellule réduite à une valeur + une gravité.
        C'est la vue par défaut : on lit toute une équipe d'un coup d'œil.
      - `resultat` : la fiche DÉTAILLÉE (principe, formule, calcul, seuils)
        du seul agent désigné par `cible` = (commune, ce, ae), atteinte en
        cliquant une ligne de la matrice. C'est elle qui pèse — plusieurs Ko
        par test — d'où le fait qu'elle reste calculée à la demande.

    La ZONE de référence, face à laquelle chaque agent est comparé, est son
    FOKONTANY — la zone de dénombrement dont parle le document quand il dit
    « l'équipe, même ZD ». Un agent qui y est seul n'y a pas de pair : sa
    référence remonte alors à la commune, et la ligne le signale (cf.
    `reference`)."""
    try:
        menages = charger(conn, districts, communes)
    except Exception as e:
        return {"disponible": False, "erreur": str(e), "arbre": [],
                "agents": {}, "niveaux": []}

    par_commune = defaultdict(list)
    for m in menages:
        par_commune[m["commune"] or "(non renseignée)"].append(m)
    # Index des zones de comparaison. Construit UNE fois, et gardé vivant
    # pendant tout l'appel : `_memo` mémorise sur l'identité de la liste de
    # référence, une liste recréée à chaque agent ruinerait le cache.
    par_fkt = defaultdict(list)
    for m in menages:
        par_fkt[zone_agent(m)].append(m)

    arbre, resultat_cible, lignes = [], None, []
    for commune, ms in sorted(par_commune.items()):
        # Les listes de la commune précédente deviennent collectables ici :
        # c'est le seul endroit où le cache du niveau 3 doit être vidé.
        _CACHE_ZONE.clear()
        par_ce = defaultdict(list)
        # Tous les agents de la COMMUNE : ce sont eux les pairs d'un agent, la
        # référence étant la commune et non la seule équipe de son CE.
        par_ae_com = defaultdict(list)
        for m in ms:
            par_ce[m["ce"] or "(CE inconnu)"].append(m)
            par_ae_com[m["agent"] or "(agent inconnu)"].append(m)
        noeud = {"commune": commune, "menages": len(ms), "ces": []}
        for ce, ms_ce in sorted(par_ce.items()):
            par_ae = defaultdict(list)
            for m in ms_ce:
                par_ae[m["agent"] or "(agent inconnu)"].append(m)
            noeud["ces"].append({
                "ce": ce, "menages": len(ms_ce),
                "aes": [{"ae": ae, "menages": len(v),
                         "membres": sum(len(x["membres"]) for x in v)}
                        for ae, v in sorted(par_ae.items())]})
            # Une ligne de matrice par agent de ce chef d'équipe, chacun
            # comparé aux ménages de SA zone (cf. `reference`).
            for ae, ms_ae in sorted(par_ae.items()):
                ms_ref, niv_ref, lib_ref, remonte = reference(
                    ms_ae, par_fkt, par_commune, commune)
                par_ae_ref = defaultdict(list)
                for m in ms_ref:
                    par_ae_ref[m["agent"] or "(agent inconnu)"].append(m)
                lignes.append({
                    "commune": commune, "ce": ce, "ae": ae,
                    "menages": len(ms_ae),
                    "membres": sum(len(x["membres"]) for x in ms_ae),
                    "reference": lib_ref, "referenceNiveau": niv_ref,
                    "referenceMenages": len(ms_ref),
                    "referenceRemonte": remonte,
                    "cellules": _cellules(ae, ms_ae, ms_ref,
                                          list(par_ae_ref.values()))})
            if cible and (commune, ce) == (cible[0], cible[1]) and cible[2] in par_ae:
                ms_ae = par_ae[cible[2]]
                # Échelons d'ESCALADE : agent → chef d'équipe → commune. Chacun
                # est comparé à l'échelon du dessus ; comparer la commune à
                # elle-même donnerait un z-score toujours nul, sa référence est
                # donc l'ensemble du périmètre.
                ms_ref, niv_ref, lib_ref, remonte = reference(
                    ms_ae, par_fkt, par_commune, commune)
                par_ae_ref = defaultdict(list)
                for m in ms_ref:
                    par_ae_ref[m["agent"] or "(agent inconnu)"].append(m)
                echelons = [
                    {"niveau": "agent", "libelle": f"l'agent {cible[2]}",
                     "unites": ms_ae, "ref": ms_ref,
                     "pairs": list(par_ae_ref.values())},
                    {"niveau": "ce", "libelle": f"l'équipe du CE {ce}",
                     "unites": ms_ce, "ref": ms,
                     "pairs": list(par_ce.values())},
                    {"niveau": "commune", "libelle": f"la commune {commune}",
                     "unites": ms, "ref": menages,
                     "pairs": list(par_commune.values())},
                ]
                resultat_cible = {
                    "commune": commune, "ce": ce, "ae": cible[2],
                    "graphiques": graphiques_agent(ms_ae, ms_ref),
                    "reference": lib_ref, "referenceNiveau": niv_ref,
                    "referenceMenages": len(ms_ref),
                    "referenceRemonte": remonte,
                    "menages": len(ms_ae), "menagesCE": len(ms_ce),
                    "membres": sum(len(x["membres"]) for x in ms_ae),
                    "equipe": len(ms), "perimetre": len(menages),
                    "niveaux": [{"numero": n, "titre": t, "description": d,
                                 "tests": tests_niveau(f, echelons)}
                                for n, t, d, f in NIVEAUX]}
        arbre.append(noeud)
    cols = colonnes()
    resume = {"alerte": 0, "vigilance": 0, "ok": 0, "nd": 0}
    for lg in lignes:
        for c in lg["cellules"]:
            resume[c["g"]] += 1
    return {"disponible": True, "arbre": arbre, "resultat": resultat_cible,
            "cible": list(cible) if cible else None,
            "menagesExamines": len(menages),
            "matrice": {"colonnes": cols, "lignes": lignes, "resume": resume,
                        "agents": len(lignes)},
            "niveaux": [{"numero": n, "titre": t, "description": d}
                        for n, t, d, _f in NIVEAUX]}
