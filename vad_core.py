# -*- coding: utf-8 -*-
"""
vad_core.py — Moteur d'agrégation du tableau de bord VISITE À DOMICILE (VAD).

Lit les tables `vad_menage` / `vad_membre` / `vad_diagnostics` (cf. vad_db.py)
pour un PÉRIMÈTRE (districts et/ou communes) et renvoie un dictionnaire
d'agrégats prêt à afficher — un bloc par section du tableau de bord :

    portee        où l'on se trouve, et ce qui a été lu
    global        avancement, couverture vs dénombrement, statut, consentement
    demographie   pyramide des âges, masculinité, dépendance, chef de ménage,
                  scolarisation, activité, papiers d'identité
    habitation    murs / sol / toit / occupation / éclairage / pièces
    biens         taux de possession des 29 biens et actifs (AP01..AP29)
    eau           source d'eau, toilettes, ordures (+ part « améliorée »)
    gps           capture GPS, précision, points pour la carte
    erreurs       listing des anomalies, ménage par ménage
    agents        production par agent (interviews, membres, durée, erreurs)

TOUT passe par `vad_db.txt()` / `num()` : le marqueur « ##N/A## » de Survey
Solutions est traité comme VIDE, sinon il ressortirait comme une modalité de
réponse à part entière.

⚠️ Les classements « source d'eau améliorée » et « installation sanitaire
améliorée » (constantes `EAU_AMELIOREE` / `SANIT_AMELIOREE`) sont une PROPOSITION
inspirée des définitions JMP (OMS/UNICEF), à faire valider par les statisticiens
du RSU : ils ne viennent pas du questionnaire lui-même.
"""
import math
import threading
import time
import re
from collections import Counter, defaultdict

import db_source
import declarations
import equipes
import rapport_core        # ecart_declaration : le MÊME calcul que le dénombrement
import vad_db
import vad_qualite
import vad_qualite_base
from vad_db import txt, num, jour

T_MEN, T_MEM, T_DIAG = vad_db.TABLE_MENAGE, vad_db.TABLE_MEMBRE, vad_db.TABLE_DIAG

# ---------------------------------------------------------------------------
# Libellés FRANÇAIS des questions (le questionnaire est en malgache : les
# MODALITÉS restent telles qu'elles ont été collectées, mais les intitulés de
# section sont traduits pour les coordonnateurs).
# ---------------------------------------------------------------------------
LIB_QUESTION = {
    "H1": "Matériau des murs",
    "H2": "Nombre de pièces",
    "H4": "Matériau du sol",
    "H5": "Matériau du toit",
    "H6": "Source d'éclairage",
    "H7": "Source d'eau de boisson",
    "H8": "Type de toilettes",
    "H9": "Évacuation des ordures",
    "H10": "Statut d'occupation du logement",
    "M3": "Sexe", "M4": "Âge", "M7": "Lien avec le chef de ménage",
    "M8": "État matrimonial", "M13": "Fréquente un établissement scolaire",
    "M14": "Niveau scolaire atteint", "M19": "Activité principale",
    "M5": "Acte de naissance", "M6": "Carte d'identité (CIN)",
    "possession_NUI": "Possède un NUI",
    "typemen": "Type de ménage", "Perm_rsu": "Consentement RSU",
    "Perm_indiv": "Consentement individuel",
}

# Biens et actifs : code de modalité -> libellé (extrait du questionnaire,
# aperçu français). Les colonnes du .dta sont AP1__<code> … AP4__<code>.
BIENS = {
    1: "Chaise (avec pied et dossier)", 2: "Table (avec pied, bien droit)",
    3: "Natte", 4: "Lampe pétrole", 5: "Poste radio",
    6: "Radio avec cassette, CD, MP3", 7: "Téléviseur", 8: "Lecteur CD/DVD",
    9: "Bicyclette", 10: "Charrue (traction animale)",
    11: "Charrette (traction animale)", 12: "Herse (traction animale)",
    13: "Bêche", 14: "Stockage agricole", 15: "Champ ou rizière (non métayage)",
    16: "Zébu", 17: "Matériel de pêche : pirogue, filet",
    18: "Réfrigérateur / congélateur", 19: "Puits", 20: "Irrigation",
    21: "Porc", 22: "Chèvre / mouton", 23: "Poulet gasy", 24: "Ruche",
    25: "Pratique la culture d'exportation", 26: "Téléphone portable",
    27: "Lit", 28: "Panneau solaire", 29: "Moto / scooter",
}
# Regroupement des biens par famille (l'ordre des sous-questions du formulaire).
FAMILLE_BIEN = {
    "Biens domestiques": (1, 2, 3, 18, 27),
    "Équipements & communication": (4, 5, 6, 7, 8, 26, 28),
    "Transport": (9, 29),
    "Agriculture & élevage": (10, 11, 12, 13, 14, 15, 16, 17, 19, 20,
                              21, 22, 23, 24, 25),
}

# Les sept domaines du WASHINGTON GROUP SHORT SET, tels que le questionnaire
# RSUe les pose (AUEM17a-g), avec l'intitulé français correspondant. L'échelle
# est celle de la norme : 1 aucune difficulté, 2 quelque difficulté, 3 beaucoup
# de difficulté, 4 incapable. La définition internationale du handicap retient
# « beaucoup de difficulté ou incapable dans AU MOINS un domaine » — c'est
# `HAND_DIFFICILE`, et c'est le seul seuil comparable d'un pays à l'autre.
AUEM_DOMAINES = {
    "AUEM17a": "Marcher ou monter un escalier",
    "AUEM17b": "Voir, même avec des lunettes",
    "AUEM17c": "Entendre, même avec un appareil",
    "AUEM17d": "Se souvenir ou se concentrer",
    "AUEM17e": "Soins personnels (se laver, s'habiller)",
    "AUEM17f": "Communiquer, se faire comprendre",
    "AUEM17g": "Autre difficulté",
}
HAND_DIFFICILE = (3, 4)      # « beaucoup de difficulté » ou « incapable »
HAND_QUELQUE = 2             # « quelque difficulté » — hors définition stricte

# Âges de référence des sections thématiques. Ils ne viennent pas du
# questionnaire : ce sont les bornes usuelles des indicateurs internationaux
# (scolarisation primaire 6-14, alphabétisation 15 ans et plus, majorité à 18).
AGE_ENFANT, AGE_SCOL = 17, (6, 14)
AGE_ALPHA, AGE_MAJEUR, AGE_ACTIF = 15, 18, 15

# Classements « améliorés » — PROPOSITION (JMP OMS/UNICEF), à valider.
EAU_AMELIOREE = {1, 2, 3, 4, 5, 6, 7, 9, 12, 13}
SANIT_AMELIOREE = {3, 4, 5}

# Bornes d'âge pour la pyramide (groupes quinquennaux, dernier ouvert).
AGE_MAX_GROUPE = 80
# Effectif FÉMININ minimum d'un groupe d'âge pour publier un rapport de
# masculinité : en dessous, le rapport est du bruit (voir _sec_demographie).
MIN_EFFECTIF_RATIO = 5


# ---------------------------------------------------------------------------
# Lecture des tables, bornée au périmètre
# ---------------------------------------------------------------------------
def _dataset(conn, table, where="", params=()):
    return db_source.DbDataset(conn, table, where, tuple(params))


def _lire(conn, districts=None, communes=None, fokontany=None):
    """(menages, membres) : listes de dicts, déjà nettoyés et décodés.

    ⚠️ PERFORMANCE : chaque colonne n'est lue QU'UNE FOIS, avant la boucle.
    `DbDataset.col_decoded()` refait une requête sur `_value_labels` à chaque
    appel — l'appeler dans la boucle sur les ménages relisait les 7 352 libellés
    de fokontany à chaque ligne, et la page mettait des minutes à s'ouvrir."""
    where, params = vad_db._clause_perimetre(conn, districts, communes, fokontany)
    dm = _dataset(conn, T_MEN, where, params)
    cols = set(dm.varnames)
    vide = [None] * dm.nobs

    def col(nom, decode=False):
        """Colonne entière, lue UNE fois (liste), ou une colonne de None."""
        if nom not in cols:
            return vide
        return dm.col_decoded(nom) if decode else dm.col(nom)

    K = col("interview__key"); KD = col("interview_keyden"); CD = col("code_den")
    NOM = col("nom_cm")
    R = col("CQ6", True); D = col("CQ7", True); C = col("CQ8", True)
    F = col("CQ9", True)
    Dn = col("CQ7"); Cn = col("CQ8"); Fn = col("CQ9")
    DATE = col("CQ3"); DEB = col("start_ec"); FIN = col("CQ4")
    NB = col("nbmembre"); TA = col("taille_men")
    TM = col("typemen", True); TMc = col("typemen")
    PR = col("Perm_rsu"); PI = col("Perm_indiv")
    ST = col("interview__status"); STl = col("interview__status", True)
    ER = col("has__errors")
    LAT = col("GPS__Latitude"); LON = col("GPS__Longitude"); ACC = col("GPS__Accuracy")
    # Thèmes ajoutés : ciblage (`eligibility`), agriculture (`carte_agri`,
    # `PT04`-`PT06`), joignabilité (`num_phone`) et conditions de passation
    # (`CQ62` : le chef de ménage a-t-il assisté à l'entretien ?).
    # Point du DÉNOMBREMENT, indexé par `code_den` : une seule requête pour
    # tout le périmètre. C'est ce qui permet de relier sur la carte le ménage
    # visité en VAD au même ménage dénombré deux mois plus tôt.
    pts_den = vad_qualite.charger_den(conn)
    ELI = col("eligibility", True); CAG = col("carte_agri"); CAGl = col("carte_agri", True)
    TEL = col("num_phone"); CQ62 = col("CQ62"); CQ62l = col("CQ62", True)
    PT = [col(f"PT0{i}") for i in (4, 5, 6)]
    H = {}
    for q in ("H1", "H2", "H4", "H5", "H6", "H7", "H8", "H9", "H10"):
        H[q] = col(q)
        H[q + "_l"] = col(q, True) if q != "H2" else vide
    # Biens : 1 lecture par colonne d'item présente dans la table. DEUX
    # nommages coexistent selon la version du questionnaire — `AP1__3` jusqu'à
    # septembre 2025, `AP__3` depuis octobre, le CODE d'item restant le même.
    # Ne chercher que l'ancien vidait silencieusement toute la section
    # « Biens & actifs » sur les données récentes.
    biens_cols = {}
    for code in BIENS:
        for nom in (f"AP__{code}", *(f"AP{q}__{code}" for q in (1, 2, 3, 4))):
            if nom in cols:
                biens_cols[code] = col(nom)
                break

    menages = []
    for i in range(dm.nobs):
        menages.append({
            "key": txt(K[i]), "keyden": txt(KD[i]), "code_den": txt(CD[i]),
            "nom_cm": txt(NOM[i]),
            "region": txt(R[i]), "district": txt(D[i]),
            "commune": txt(C[i]), "fokontany": txt(F[i]),
            "code_district": num(Dn[i]), "code_commune": num(Cn[i]),
            "code_fokontany": num(Fn[i]),
            "date": jour(DATE[i]) or jour(DEB[i]), "fin": jour(FIN[i]),
            "nbmembre": num(NB[i]), "taille": num(TA[i]),
            "typemen": txt(TM[i]), "typemen_code": num(TMc[i]),
            "perm_rsu": num(PR[i]), "perm_indiv": num(PI[i]),
            "statut": num(ST[i]), "statut_lib": txt(STl[i]),
            "erreurs": num(ER[i]) or 0,
            "lat": LAT[i] if isinstance(LAT[i], (int, float)) else None,
            "lon": LON[i] if isinstance(LON[i], (int, float)) else None,
            "acc": ACC[i] if isinstance(ACC[i], (int, float)) else None,
            "H1": num(H["H1"][i]), "H1_l": txt(H["H1_l"][i]),
            "H2": num(H["H2"][i]),
            "H4": num(H["H4"][i]), "H4_l": txt(H["H4_l"][i]),
            "H5": num(H["H5"][i]), "H5_l": txt(H["H5_l"][i]),
            "H6": num(H["H6"][i]), "H6_l": txt(H["H6_l"][i]),
            "H7": num(H["H7"][i]), "H7_l": txt(H["H7_l"][i]),
            "H8": num(H["H8"][i]), "H8_l": txt(H["H8_l"][i]),
            "H9": num(H["H9"][i]), "H9_l": txt(H["H9_l"][i]),
            "H10": num(H["H10"][i]), "H10_l": txt(H["H10_l"][i]),
            "biens": {code: num(c[i]) for code, c in biens_cols.items()},
            "eligibilite": txt(ELI[i]),
            "carte_agri": num(CAG[i]), "carte_agri_l": txt(CAGl[i]),
            "tel": txt(TEL[i]),
            "cq62": num(CQ62[i]), "cq62_l": txt(CQ62l[i]),
            "cultures": [txt(c[i]) for c in PT if txt(c[i])],
            "gps_den": pts_den.get(txt(CD[i])),
        })

    membres = []
    if menages:
        sous = (f'SELECT "interview__key" FROM "{T_MEN}"'
                + (f" WHERE {where}" if where else ""))
        try:
            dmb = _dataset(conn, T_MEM, f'"interview__key" IN ({sous})', params)
        except Exception:
            dmb = None
        if dmb is not None and dmb.nobs:
            mc = set(dmb.varnames)
            videm = [None] * dmb.nobs

            def mcol(nom, decode=False):
                if nom not in mc:
                    return videm
                return dmb.col_decoded(nom) if decode else dmb.col(nom)

            mK = mcol("interview__key"); SX = mcol("M3", True)
            AG = mcol("M4"); AN = mcol("M4b")
            LI = mcol("M7", True); LIc = mcol("M7"); MA = mcol("M8", True)
            SC = mcol("M13"); SCl = mcol("M13", True); NV = mcol("M14", True)
            AC = mcol("M19", True); ACT = mcol("M5"); CIN = mcol("M6")
            NUI = mcol("possession_NUI"); SM = mcol("membre_valid", True)
            # Thèmes ajoutés : handicap (les sept domaines du Washington Group
            # + la carte), orphelinage, scolarisation en cours, alphabétisation,
            # résidence, nationalité et lieu de naissance.
            HND = {v: mcol(v) for v in AUEM_DOMAINES}
            HCA = mcol("AUEM17i")
            ORP = mcol("M10"); ORPl = mcol("M10", True)
            SCA = mcol("M15"); LIR = mcol("M16a"); ECR = mcol("M16b")
            RES = mcol("M2"); RESl = mcol("M2", True); NAT = mcol("MNat")
            NAI = mcol("M5e"); ARR = mcol("nouvomembre_motif", True)
            for i in range(dmb.nobs):
                membres.append({
                    "key": txt(mK[i]), "sexe": txt(SX[i]), "age": num(AG[i]),
                    "annee": num(AN[i]), "lien": txt(LI[i]),
                    "lien_code": num(LIc[i]), "matri": txt(MA[i]),
                    "scol": num(SC[i]), "scol_l": txt(SCl[i]),
                    "niveau": txt(NV[i]), "activite": txt(AC[i]),
                    "acte": num(ACT[i]), "cin": num(CIN[i]), "nui": num(NUI[i]),
                    "statut_membre": txt(SM[i]),
                    "hand": {v: num(HND[v][i]) for v in AUEM_DOMAINES},
                    "hand_carte": num(HCA[i]),
                    "orphelin": num(ORP[i]), "orphelin_l": txt(ORPl[i]),
                    "scol_act": num(SCA[i]),
                    "lire": num(LIR[i]), "ecrire": num(ECR[i]),
                    "residence": num(RES[i]), "residence_l": txt(RESl[i]),
                    "nationalite": num(NAT[i]), "naissance": txt(NAI[i]),
                    "motif_arrivee": txt(ARR[i]),
                })
    return menages, membres


def _diagnostics(conn, cles):
    """{interview__key: {agent, duree_min, rejets, erreurs}} pour ces clés."""
    if not cles:
        return {}
    out = {}
    try:
        d = _dataset(conn, T_DIAG)
    except Exception:
        return {}
    cols = set(d.varnames)

    def c(nom):
        return d.col(nom) if nom in cols else [None] * d.nobs

    k, resp = c("interview__key"), c("responsible")
    dur, rej, err = (c("interview__duration"), c("rejections__sup"),
                     c("entities__errors"))
    for i in range(d.nobs):
        cle = txt(k[i])
        if cle not in cles:
            continue
        out[cle] = {"agent": txt(resp[i]), "duree": _duree_min(dur[i]),
                    "rejets": num(rej[i]) or 0, "erreurs": num(err[i]) or 0}
    return out


def _duree_min(v):
    """Durée d'interview -> minutes entières, ou None.

    Survey Solutions écrit « JJ.HH:MM:SS » (ex. `00.00:54:01` = 54 min 1 s) : le
    nombre de JOURS précède l'heure, séparé par un POINT. Sans ce cas, toutes les
    durées étaient illisibles et la colonne restait vide."""
    s = txt(v)
    if not s:
        return None
    if ":" in s:
        jours = 0
        tete, _, reste = s.partition(":")
        if "." in tete:                       # « JJ.HH » -> jours + heures
            j, _, h = tete.partition(".")
            try:
                jours, tete = int(j), h
            except ValueError:
                return None
        p = [tete] + reste.split(":")
        try:
            heures = int(p[0])
            minutes = int(p[1]) if len(p) > 1 else 0
            secondes = int(float(p[2])) if len(p) > 2 else 0
        except ValueError:
            return None
        return (jours * 24 + heures) * 60 + minutes + (1 if secondes >= 30 else 0)
    n = num(s)
    return int(n / 60) if n is not None else None


# ---------------------------------------------------------------------------
# Petits calculs partagés
# ---------------------------------------------------------------------------
def _pct(n, t, d=1):
    return round(100.0 * n / t, d) if t else None


def _stats(valeurs):
    """{'n','moy','et','cv','med'} d'une liste de nombres (None si vide)."""
    v = [x for x in valeurs if isinstance(x, (int, float))]
    if not v:
        return {"n": 0, "moy": None, "et": None, "cv": None, "med": None}
    n = len(v)
    moy = sum(v) / n
    et = math.sqrt(sum((x - moy) ** 2 for x in v) / n)
    s = sorted(v)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"n": n, "moy": round(moy, 2), "et": round(et, 2),
            "cv": (round(100 * et / moy, 1) if moy else None),
            "med": round(med, 1)}


def _repartition(valeurs, libelles=None, tri_effectif=True):
    """[{'lib','n','pct'}] d'une variable qualitative (vides ignorés)."""
    v = [x for x in valeurs if txt(x)]
    c = Counter(txt(x) for x in v)
    total = sum(c.values())
    lignes = [{"lib": k, "n": n, "pct": _pct(n, total)} for k, n in c.items()]
    lignes.sort(key=(lambda r: -r["n"]) if tri_effectif else (lambda r: r["lib"]))
    return {"total": total, "lignes": lignes}


def _groupe_age(a):
    """Âge -> libellé de groupe quinquennal ('0-4' … '80+'), ou None."""
    if not isinstance(a, (int, float)) or a < 0 or a > 120:
        return None
    a = int(a)
    if a >= AGE_MAX_GROUPE:
        return f"{AGE_MAX_GROUPE}+"
    b = (a // 5) * 5
    return f"{b}-{b + 4}"


def _ordre_groupes():
    g = [f"{b}-{b + 4}" for b in range(0, AGE_MAX_GROUPE, 5)]
    return g + [f"{AGE_MAX_GROUPE}+"]


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _sec_global(conn, menages, membres, diag, districts, communes):
    dates = sorted({m["date"] for m in menages if m["date"]})
    par_jour = Counter(m["date"] for m in menages if m["date"])
    cumul, c = [], 0
    for d in dates:
        c += par_jour[d]
        cumul.append({"d": d, "n": par_jour[d], "cumul": c})
    agents = {diag.get(m["key"], {}).get("agent") for m in menages}
    agents.discard("")
    agents.discard(None)
    # Même piège que dans `_sec_demographie` : compter les membres ménage par
    # ménage en reparcourant toute la liste coûtait 15 190 × 65 884 comparaisons,
    # soit 200 secondes sur un district. Un seul comptage suffit.
    taille_par_cle = Counter(x["key"] for x in membres)
    tailles = [taille_par_cle.get(m["key"], 0) for m in menages]
    durees = [diag.get(m["key"], {}).get("duree") for m in menages]
    return {
        "menages": len(menages),
        "membres": len(membres),
        "taille": _stats(tailles),
        "agents": len(agents),
        "jours": len(dates),
        "dates": dates,
        "parJour": cumul,
        "duree": _stats([d for d in durees if d]),
        "statut": _repartition([m["statut_lib"] for m in menages]),
        "typemen": _repartition([m["typemen"] for m in menages]),
        "consentement": {
            "rsu_oui": sum(1 for m in menages if m["perm_rsu"] == 1),
            "rsu_non": sum(1 for m in menages if m["perm_rsu"] == 2),
            "indiv_oui": sum(1 for m in menages if m["perm_indiv"] == 1),
            "indiv_non": sum(1 for m in menages if m["perm_indiv"] == 2),
        },
        "lienDen": _lien_denombrement(menages),
        # Ménages DISTINCTS (une clé `interview_keyden` compte une fois) : même
        # règle que le détail par commune et le test de qualité globale.
        "couverture": _couverture(conn, _nb_menages(menages), districts, communes),
        "parCommune": _par_zone(menages, membres, "commune"),
        "parFokontany": _par_zone(menages, membres, "fokontany"),
    }


def _lien_denombrement(menages):
    """Qualité du rattachement VAD -> dénombrement (`interview_keyden`).

    On ne se contente pas de compter les liens renseignés : un lien PARTAGÉ par
    des dizaines de ménages ne vaut rien. `distincts` et `suspect` disent si le
    préchargement a fonctionné."""
    avec = [m["keyden"] for m in menages if m["keyden"]]
    distincts = len(set(avec))
    attendus = [m for m in menages if m["typemen_code"] == 1]
    return {
        "avec": len(avec), "sans": len(menages) - len(avec),
        "distincts": distincts,
        "attendus": len(attendus),
        "manquants_attendus": sum(1 for m in attendus if not m["keyden"]),
        # Moins d'un code distinct pour 3 liens : le préchargement est défectueux.
        "suspect": bool(avec) and distincts * 3 < len(avec),
    }


def _nb_menages(menages):
    """Ménages DISTINCTS interviewés : une même clé `interview_keyden` compte
    une fois ; une interview sans clé compte pour un ménage."""
    return (len({m["keyden"] for m in menages if m["keyden"]})
            + sum(1 for m in menages if not m["keyden"]))


def _couverture(conn, n_vad, districts, communes):
    """VAD réalisées vs ménages DÉNOMBRÉS du même périmètre : le vrai
    dénominateur de l'avancement (ce sont ces ménages qu'il faut visiter)."""
    try:
        if communes is not None:
            codes = [int(c) for c in communes]
            if not codes:
                return {"denombres": 0, "vad": n_vad, "taux": None}
            src = db_source.source_db(conn, communes=codes)
        elif districts:
            src = db_source.source_db(conn, district=int(sorted(districts)[0]))
        else:
            src = db_source.source_db(conn)
        n_den = src("roster").nobs
    except Exception:
        return {"denombres": 0, "vad": n_vad, "taux": None}
    return {"denombres": n_den, "vad": n_vad, "taux": _pct(n_vad, n_den)}


def _denombres_par_commune(conn, districts=None, communes=None):
    """{code commune: ménages dénombrés} — lignes de `segment_roster` rattachées
    à `den_menage` par `interview__key`, même base que `_couverture` (le total
    des communes égale donc le « Ménages dénombrés » de la synthèse)."""
    ph = db_source._placeholder(conn)
    if communes is not None:
        codes = tuple(int(c) for c in communes)
        where = f'd."commune" IN ({",".join([ph] * len(codes))})'
    elif districts:
        codes = tuple(int(d) for d in districts)
        where = f'd."district" IN ({",".join([ph] * len(codes))})'
    else:
        codes, where = (), ""
    if where and not codes:
        return {}
    try:
        cur = conn.cursor()
        cur.execute('SELECT d."commune", COUNT(*) FROM "segment_roster" s '
                    'JOIN "den_menage" d ON d."interview__key" = s."interview__key"'
                    + (f" WHERE {where}" if where else "")
                    + ' GROUP BY d."commune"', codes)
        return {int(c): n for c, n in cur.fetchall() if c is not None}
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return {}


def _masculinite(membres):
    """Hommes / femmes × 100 sur les membres d'âge renseigné — la règle de
    `_sec_demographie`, pour qu'une commune se lise comme le total."""
    h = f = 0
    for x in membres:
        if not _groupe_age(x["age"]):
            continue
        s = (x["sexe"] or "").lower()
        if s.startswith("lahy"):
            h += 1
        elif s.startswith("vavy"):
            f += 1
    return round(100.0 * h / f, 1) if f else None


def _ecart(a, b, d=2):
    return round(a - b, d) if a is not None and b is not None else None


def _couverture_communes(conn, menages, membres, rgph, districts=None,
                         communes=None):
    """Par commune : ménages attendus (dénombrés), interviewés, couverture,
    taille des ménages RSU vs RGPH-3 2018, rapport de masculinité RSU vs
    RGPH-3, et leurs écarts (RSU − RGPH).

    Une commune dénombrée mais pas encore visitée figure avec 0 interviewé :
    c'est justement ce qu'un tableau de couverture doit montrer. Un ménage
    interviewé plusieurs fois (même `interview_keyden`) n'est compté qu'une fois."""
    den = _denombres_par_commune(conn, districts, communes)
    par = defaultdict(list)
    for m in menages:
        par[m["code_commune"]].append(m)
    memb = defaultdict(list)
    cle_com = {m["key"]: m["code_commune"] for m in menages}
    for x in membres:
        memb[cle_com.get(x["key"])].append(x)
    noms = {}
    codes = sorted({c for c in set(den) | set(par) if c is not None})
    if codes:
        try:
            ph = db_source._placeholder(conn)
            cur = conn.cursor()
            cur.execute('SELECT "code_commune", "nom" FROM "commune" WHERE '
                        f'"code_commune" IN ({",".join([ph] * len(codes))})',
                        tuple(codes))
            noms = {int(c): n for c, n in cur.fetchall()}
        except Exception:
            noms = {}
    t_rgph = (rgph or {}).get("parCommune") or {}
    m_rgph = (rgph or {}).get("masculiniteCommune") or {}

    def interviewes(ms):
        cles = {m["keyden"] for m in ms if m["keyden"]}
        return len(cles) + sum(1 for m in ms if not m["keyden"])

    lignes = []
    for c in codes + ([None] if None in par else []):
        ms, mb = par.get(c, []), memb.get(c, [])
        att, n = den.get(c), interviewes(ms)
        t_rsu = round(len(mb) / len(ms), 2) if ms else None
        t_rg = t_rgph.get(c) if c is not None else None
        ma_rsu = _masculinite(mb) if mb else None
        ma_rg = m_rgph.get(c) if c is not None else None
        lignes.append({
            "code": c, "commune": (noms.get(c) or (str(c) if c else
                                                   "(commune non renseignée)")),
            "attendus": att, "interviewes": n,
            "couverture": _pct(n, att) if att else None,
            "tailleRsu": t_rsu, "tailleRgph": t_rg,
            "ecartTaille": _ecart(t_rsu, t_rg),
            "mascRsu": ma_rsu, "mascRgph": ma_rg,
            "ecartMasc": _ecart(ma_rsu, ma_rg, 1)})
    lignes.sort(key=lambda l: (l["couverture"] is None, l["couverture"] or 0))
    att = sum(den.values())
    n = interviewes(menages)
    t_rsu = round(len(membres) / len(menages), 2) if menages else None
    t_rg = (rgph or {}).get("taille")
    ma_rsu = _masculinite(membres) if membres else None
    ma_rg = (rgph or {}).get("masculinite")
    total = {"attendus": att, "interviewes": n,
             "couverture": _pct(n, att) if att else None,
             "tailleRsu": t_rsu, "tailleRgph": t_rg,
             "ecartTaille": _ecart(t_rsu, t_rg),
             "mascRsu": ma_rsu, "mascRgph": ma_rg,
             "ecartMasc": _ecart(ma_rsu, ma_rg, 1)}
    return {"lignes": lignes, "total": total}


def _par_zone(menages, membres, champ):
    """Récapitulatif par commune ou par fokontany (ménages, membres, taille)."""
    par = defaultdict(list)
    for m in menages:
        par[m[champ] or "(non renseigné)"].append(m)
    memb = Counter(x["key"] for x in membres)
    out = []
    for zone, ms in par.items():
        n_mem = sum(memb.get(m["key"], 0) for m in ms)
        # `code` sert à joindre la zone au référentiel RGPH (cf. _sec_rgph).
        codes = {m.get("code_" + champ) for m in ms} - {None}
        out.append({"zone": zone, "code": (codes.pop() if len(codes) == 1 else None),
                    "menages": len(ms), "membres": n_mem,
                    "taille": round(n_mem / len(ms), 2) if ms else None})
    out.sort(key=lambda r: -r["menages"])
    return out


# ---------------------------------------------------------------------------
# Référence RGPH-3 2018 (INSTAT) — pour affichage en regard des données VAD
# ---------------------------------------------------------------------------
# Les tables `rgph_individu` / `rgph_menage` portent les codes géographiques du
# référentiel RSU (colonnes cd_rsu / cc_rsu), posés par rgph3/03_recoder.py.
# Elles peuvent être absentes (déploiement sans les données RGPH) : dans ce cas
# `disponible` vaut False et le tableau de bord n'affiche simplement pas le
# volet de comparaison.
# ⚠️ Le RGPH est un échantillon au 10 % : les effectifs sont REDRESSÉS ×10.
RGPH_REDRESSEMENT = 10


def _rgph_dispo(conn) -> bool:
    """Les pré-agrégats (rgph3/07) sont-ils là ? Sinon, repli microdonnées."""
    for t in ("rgph_age_commune", "rgph_individu"):
        try:
            conn.cursor().execute(f'SELECT 1 FROM "{t}" LIMIT 1')
            return True
        except Exception:
            continue
    return False


def _rgph_source(conn):
    """Table à interroger : le pré-agrégat s'il existe, sinon les microdonnées.

    Le pré-agrégat (241 000 lignes) évite de balayer les 2,5 M de lignes de
    `rgph_individu` à chaque page — 3,7 s en périmètre national."""
    try:
        conn.cursor().execute('SELECT 1 FROM "rgph_age_commune" LIMIT 1')
        return "agrege"
    except Exception:
        return "micro"


def _rgph_perimetre(conn, districts, communes):
    """(clause SQL sur les tables rgph_*, params). `communes` prime."""
    ph = db_source._placeholder(conn)
    if communes is not None:
        codes = tuple(int(c) for c in sorted(communes))
        if not codes:
            return "1 = 0", ()
        return f'"cc_rsu" IN ({",".join([ph] * len(codes))})', codes
    if districts:
        codes = tuple(int(d) for d in sorted(districts))
        return f'"cd_rsu" IN ({",".join([ph] * len(codes))})', codes
    return "", ()


def _sec_rgph(conn, districts=None, communes=None):
    """Pyramide et taille des ménages du RGPH-3 2018 sur le même périmètre."""
    vide = {"disponible": False, "pyramide": [], "total": 0, "menages": 0,
            "taille": None, "parCommune": {}}
    if not _rgph_dispo(conn):
        return vide
    where, params = _rgph_perimetre(conn, districts, communes)
    w = f" WHERE {where}" if where else ""
    cur = conn.cursor()
    ordre = _ordre_groupes()
    pyr = {g: {"H": 0, "F": 0} for g in ordre}
    src_t = _rgph_source(conn)
    try:
        if src_t == "agrege":
            cur.execute(f'SELECT "age", "sexe", SUM("n") FROM "rgph_age_commune"{w}'
                        ' GROUP BY "age", "sexe"', params)
        else:
            cur.execute(f'SELECT "P08", "P05", COUNT(*) FROM "rgph_individu"{w}'
                        + (" AND" if w else " WHERE")
                        + ' "P08" IS NOT NULL AND "P05" IS NOT NULL'
                        + ' GROUP BY "P08", "P05"', params)
        lignes = cur.fetchall()
    except Exception:
        return vide
    total = h = f = 0
    somme_ages = 0
    jeunes = adultes = vieux = 0
    par_age = {}                       # age -> effectif, pour la médiane exacte
    for age, sexe, n in lignes:
        g = _groupe_age(age)
        if g is None:
            continue
        n *= RGPH_REDRESSEMENT
        total += n
        pyr[g]["H" if int(sexe) == 1 else "F"] += n
        if int(sexe) == 1:
            h += n
        else:
            f += n
        a = int(age)
        somme_ages += a * n
        par_age[a] = par_age.get(a, 0) + n
        if a < 15:
            jeunes += n
        elif a < 65:
            adultes += n
        else:
            vieux += n

    # Médiane exacte à partir de la distribution cumulée (pas d'approximation).
    mediane, cumul = None, 0
    for a in sorted(par_age):
        cumul += par_age[a]
        if cumul >= total / 2:
            mediane = a
            break

    # Chefs de ménage : P03 = 0 dans la nomenclature RGPH.
    chefs_n = chefs_f = 0
    try:
        if src_t == "agrege":
            cur.execute(f'SELECT SUM("chefs"), SUM("chefs_femmes")'
                        f' FROM "rgph_men_commune"{w}', params)
            a, b = cur.fetchone()
            chefs_n = (a or 0) * RGPH_REDRESSEMENT
            chefs_f = (b or 0) * RGPH_REDRESSEMENT
        else:
            cur.execute(f'SELECT "P05", COUNT(*) FROM "rgph_individu"{w}'
                        + (" AND" if w else " WHERE") + ' "P03" = 0 GROUP BY "P05"',
                        params)
            for sexe, n in cur.fetchall():
                n *= RGPH_REDRESSEMENT
                chefs_n += n
                if sexe is not None and int(sexe) == 2:
                    chefs_f += n
    except Exception:
        pass

    # Taille moyenne : population / ménages, globale et par commune.
    par_commune, menages = {}, 0
    try:
        if src_t == "agrege":
            cur.execute(f'SELECT a."cc_rsu", m."menages", SUM(a."n")'
                        f' FROM "rgph_age_commune" a'
                        f' JOIN "rgph_men_commune" m ON m."cc_rsu" = a."cc_rsu"'
                        # `where` porte déjà sur "cc_rsu" ou "cd_rsu", deux
                        # colonnes présentes dans rgph_age_commune : il suffit
                        # de la préfixer par l'alias de cette table.
                        + (f' WHERE a.{where}' if where else "")
                        + ' GROUP BY a."cc_rsu", m."menages"', params)
        else:
            cur.execute(f'SELECT "cc_rsu", COUNT(DISTINCT "IDMEN"), COUNT(*)'
                        f' FROM "rgph_individu"{w} GROUP BY "cc_rsu"', params)
        for cc, nm, npop in cur.fetchall():
            menages += nm
            if nm:
                par_commune[int(cc)] = round(npop / nm, 2)
    except Exception:
        pass
    # Rapport de masculinité PAR COMMUNE (hommes / femmes × 100, tous âges
    # renseignés) : même règle que la valeur globale ci-dessus.
    masc_commune = {}
    try:
        if src_t == "agrege":
            cur.execute(f'SELECT "cc_rsu", "sexe", SUM("n") FROM "rgph_age_commune"'
                        + (f" WHERE {where} AND" if where else " WHERE")
                        + ' "age" IS NOT NULL GROUP BY "cc_rsu", "sexe"', params)
        else:
            cur.execute(f'SELECT "cc_rsu", "P05", COUNT(*) FROM "rgph_individu"'
                        + (f" WHERE {where} AND" if where else " WHERE")
                        + ' "P08" IS NOT NULL GROUP BY "cc_rsu", "P05"', params)
        hf = defaultdict(lambda: [0, 0])
        for cc, sexe, n in cur.fetchall():
            if cc is None or sexe is None:
                continue
            hf[int(cc)][0 if int(sexe) == 1 else 1] += n
        masc_commune = {cc: round(100.0 * hh / ff, 1)
                        for cc, (hh, ff) in hf.items() if ff}
    except Exception:
        pass
    pop = sum(p["H"] + p["F"] for p in pyr.values())
    # Même règle de publication que pour la VAD (cf. _sec_demographie) : pas de
    # rapport sous MIN_EFFECTIF_RATIO femmes. Le seuil ne mord jamais ici (les
    # effectifs RGPH sont redressés ×10), mais garder la règle rend les deux
    # graphiques strictement comparables.
    for g in ordre:
        F = pyr[g]["F"]
        pyr[g]["ratio"] = (round(100.0 * pyr[g]["H"] / F, 1)
                           if F >= MIN_EFFECTIF_RATIO else None)
    return {
        "disponible": True,
        "masculiniteCommune": masc_commune,
        "pyramide": [{"groupe": g, "H": pyr[g]["H"], "F": pyr[g]["F"],
                      "ratio": pyr[g]["ratio"]} for g in ordre],
        "total": total,
        "hommes": h, "femmes": f,
        "masculinite": (round(100.0 * h / f, 1) if f else None),
        "age": {"moy": (round(somme_ages / total, 1) if total else None),
                "med": mediane},
        "groupes": {"pct_moins15": _pct(jeunes, total),
                    "pct_plus65": _pct(vieux, total)},
        "dependance": (round(100.0 * (jeunes + vieux) / adultes, 1) if adultes else None),
        "chef": {"n": chefs_n, "femmes": chefs_f,
                 "pct_femmes": _pct(chefs_f, chefs_n)},
        "menages": menages * RGPH_REDRESSEMENT,
        "taille": (round(pop / (menages * RGPH_REDRESSEMENT), 2) if menages else None),
        "parCommune": par_commune,
    }


# ---------------------------------------------------------------------------
# Listings d'erreurs de saisie — transcription du dofile INSTAT
#   do_listing_d_erreur_20_districts_08102025.do
# ---------------------------------------------------------------------------
# Deux listings distincts : erreurs MÉNAGE et erreurs INDIVIDU. Chaque règle
# porte le nom de sa variable Stata d'origine, pour que la correspondance avec
# le dofile reste vérifiable ligne à ligne.
#
# Le dofile calcule PLUS de règles qu'il n'en exporte : les contrôles « Autre »
# (erreur_*_Oth) sont actifs mais absents du `keep`, et les contrôles CIN,
# grossesse et valeurs aberrantes sont en commentaire. Tous sont repris ici :
# ce sont des erreurs réelles d'agent enquêteur.
#
# NON CALCULABLES sur l'export VAD actuel, et signalés comme tels :
#   err_SR / err_SR_ppl / err_SRp  -> SR01..SR09 absentes
#   err_milieu                     -> `Milieu` absente
#   err_suptot / err_supcult / err_sup / err_rendmnt -> PT01..PT03, typeculture,
#                                     SR10 absentes (bloc agriculture)
# Chacune se réactive d'elle-même si les colonnes apparaissent dans un export.

CARACT_LOG = ("H1", "H2", "H4", "H5", "H6", "H7", "H8", "H9", "H10")
SR_VARS = tuple(f"SR{i:02d}" for i in range(1, 10))
AGRI_VARS = ("PT01", "PT02", "PT03", "typeculture", "SR10")
HANDICAP = ("AUEM17a", "AUEM17b", "AUEM17d", "AUEM17e", "AUEM17f", "AUEM17g",
            "AUEM17i")
STATUTS_RETENUS = (100, 120)

# Contrôles « Autre » : un texte libre qui contient l'un de ces mots désigne en
# fait une modalité existante — l'agent aurait dû la cocher (dofile l. 164-232).
MOTS_OTH = {
    "typemen_motif_Oth": ("FANTATRA", "VAO", "RECHERCHE", "NIFINDRA", "NIORINA"),
    "H1_Oth": ("TANY", "FALAFA", "CIMENT", "BIRIKY", "TANIMANGA", "MANTA",
               " SIMBA", "BOZAKA", "PLANCH", "SIMENITR", "VATO", "DUR"),
    "H4_Oth": ("PLANCH", "HAZO", "SIMENIT", "TANY", "CIMEN", "BET"),
    "H5_Oth": ("SIMEN", "HAZO", "CIMEN", "TOLE", "BOZAK", "FANITS"),
    "H6_Oth": ("MISY", "HAZO", "KITAY", "BATTERIE", "BATER", "AMPOUL"),
    "H7_Oth": ("MISY", "HAZO", "KITAY", "BATTERIE", "BATER", "AMPOUL", "PILE",
               "TORCHE", "LAMP", "LEMP", "KELY", "JIRO"),
    "H8_Oth": ("MIS", "TSY", "VATO", "MINDRANA", "LAVAK", "FOSS"),
    "H9_Oth": ("MISY", "TS", "LAVA", "ZEZIK", "RAN", "DORANA"),
    "H10_Oth": ("TRANO", "PETRAKA", "PANDOVA", "NDRANA"),
}
MSG_OTH = {
    "typemen_motif_Oth": "antony tsy nahatafiditra azy e-fokontany",
    "H1_Oth": "mur extérieur", "H4_Oth": "gorodona(plancher)",
    "H5_Oth": "ny tafo(toit)", "H6_Oth": "Electricité", "H7_Oth": "Electricité",
    "H8_Oth": "toilette", "H9_Oth": "Evacuation d'ordures",
    "H10_Oth": "ny occupation dans le logement",
}
LIB_OTH = {
    "typemen_motif_Oth": "Motif de non-enregistrement e-Fokontany",
    "H1_Oth": "Mur extérieur", "H4_Oth": "Plancher", "H5_Oth": "Toit",
    "H6_Oth": "Électricité", "H7_Oth": "Eau", "H8_Oth": "Toilette",
    "H9_Oth": "Évacuation d'ordures", "H10_Oth": "Occupation du logement",
}

# Chaque règle : (code Stata, en-tête de colonne, message porté par la cellule
# quand l'erreur est présente, explication). Le message reprend le `lab def` du
# dofile — c'est le texte que lit l'agent pour corriger, en malgache.
ERREURS_MENAGE = [
    ("erreur_refus_RSU", "Permission RSU",
     "Tsy mazava ny antony fandavana/tsy feno ny consentement RSU/etc...",
     "Consentement RSU refusé ou motif de refus non renseigné"),
    ("erreur_fokontany", "Commune / fokontany",
     "Tsy feno ny fokontany/commune",
     "Commune ou fokontany non renseigné"),
    ("err_caract_log", "Caractéristiques du logement",
     "Misy tsy feno ny toetrin'ny trano fonenana",
     "Au moins une caractéristique vide : mur, pièces, plancher, toit, "
     "électricité, eau, toilette, ordures, occupation"),
    ("err_bien", "Possession de biens",
     "Misy tsy feno ny fananan'ny tokantrano",
     "Au moins un bien du ménage non renseigné"),
    ("H2_aberante", "Nombre de pièces aberrant", "oui",
     "H2 au-delà de Q3 + 1,5 × écart interquartile, calculé dans le fokontany"),
    ("err_SR", "Source de revenu incomplète", "Misy tsy feno ny loharanombola",
     "Une source SR01..SR09 non renseignée"),
    ("err_SR_ppl", "Pas de source principale", "Tsy misy loharanombola fototra",
     "Aucune source déclarée principale"),
    ("err_SRp", "Aucune source de revenu", "Tsy misy loharanombola mihitsy",
     "Toutes les sources à « aucune »"),
    ("err_milieu", "Milieu non renseigné", "tsy feno ny milieu",
     "Variable `Milieu` vide"),
    ("err_suptot", "Superficie incohérente", "Misy tsy marina ny velarantany",
     "PT01 + PT02 < PT03"),
    ("err_supcult", "Superficie cultivée",
     "Diso ny velarantany nambolena/fambolena",
     "PT03 = 0 alors que le ménage cultive"),
    ("err_sup", "Superficie aberrante",
     "Misy velarantany ambony be, avereno kajiana sao diso",
     "Une superficie dépasse 5 ha"),
    ("err_rendmnt", "Rendement céréalier",
     "Diso ny velarantany/fatran'ny céréales",
     "Rendement au-delà de 5 000 kg/ha"),
    ("err_autre", "Texte « Autre » à relire",
     "Misy « Autre à préciser » voasoratra, hamarino",
     "Un champ « Autre à préciser » est rempli : à relire même si le texte ne "
     "correspond à aucune modalité existante"),
]
ERREURS_MENAGE += [
    (f"erreur_{k}", f"Modalité « Autre » — {LIB_OTH[k]}",
     f"Amarino/ahitsio ny modalité {MSG_OTH[k]}",
     "Le texte libre désigne une modalité existante : l'agent aurait dû la cocher")
    for k in MOTS_OTH]

ERREURS_INDIVIDU = [
    ("err_membre", "Membre du ménage à confirmer",
     "Hamarino sao membre ménage ihany: raha mihoatra ny 6mois ny absence dia "
     "tsy membre intsony sinon mbola membre ihany",
     "Motif d'absence évoquant un travail (IASA/KARAMA)"),
    ("err_cm_cj", "Chef de ménage / conjoint",
     "Tsy misy lohatokantrano/Lohatokatrano mihoatra ny roa/Vady roa ao anaty "
     "tokantrano iray/Taonan'ny lohatokantrano na ny vadiny latsaky ny 12 taona",
     "Aucun ou plusieurs chefs, deux conjoints, ou chef/conjoint de moins de 12 ans"),
    ("err_sexe_cm_cj", "Sexe chef et conjoint",
     "Mitovy fananahana (sexe) ny lohatokantrano sy ny vadiny",
     "Le chef de ménage et son conjoint ont le même sexe"),
    ("err_M7_M3_M4_M8_M5_vide", "Identification incomplète",
     "Misy tsy feno ny lien de parente, sexe, age en année révolue, copie "
     "d'acte de naissance, statut matrimonial",
     "Lien de parenté, sexe, âge, acte de naissance ou statut matrimonial manquant"),
    ("err_education", "Éducation et alphabétisation",
     "Misy tsy feno ny section education et alphabetisation",
     "Regroupe les trois contrôles suivants"),
    ("err_M13", "Scolarisation non renseignée",
     "Tsy feno ny M13 (fianarana)",
     "M13 vide pour une personne de 5 ans ou plus"),
    ("err_M14", "Dernière classe non renseignée",
     "Tsy feno ny M14 (kilasy farany)",
     "M14 vide alors que la personne a été scolarisée"),
    ("err_alphabet", "Alphabétisation non renseignée",
     "Tsy feno ny M16a/M16b (mamaky sy manoratra)",
     "Lecture (M16a) ou écriture (M16b) du malagasy non renseignée"),
    ("err_handicap", "Handicap", "Misy tsy feno ny section handicap",
     "Au moins une question handicap vide au-delà de 5 ans"),
    ("err_validation_e_fkt", "Validation e-Fokontany",
     "Tsy azo valider'na ny information e-fokontany banga, atao TSIA foana ny valiny",
     "Information e-Fokontany vide mais validée : la réponse doit être « non »"),
    ("err_M12", "Grossesse non renseignée", "Tsy feno ny M12 (bevohoka)",
     "M12 vide pour une femme de 15 ans ou plus"),
    ("err_cin", "Numéro CIN manquant", "Tsy misy Numéro CIN",
     "M6a vide pour une personne de 18 ans ou plus"),
    ("err_date_cin", "Date de délivrance CIN", "Tsy misy Date de delivrance CIN",
     "M6b vide pour une personne de 18 ans ou plus"),
    ("err_lieu_cin", "Lieu de délivrance CIN", "Tsy misy Lieu de delivrance CIN",
     "M6d vide pour une personne de 18 ans ou plus"),
]

# Règles dépendant de colonnes qui peuvent manquer : elles sont retirées de la
# liste affichée quand la source n'est pas là, plutôt que de sortir « 0 erreur »
# — un zéro trompeur est pire qu'une règle absente.
DEP_MENAGE = {"err_SR": SR_VARS, "err_SR_ppl": SR_VARS, "err_SRp": SR_VARS,
              "err_milieu": ("Milieu",), "err_suptot": AGRI_VARS,
              "err_supcult": AGRI_VARS, "err_sup": AGRI_VARS,
              "err_rendmnt": AGRI_VARS}
# Côté individu, la colonne existe mais peut être ENTIÈREMENT vide — c'est le
# cas de M6_valid dans l'export courant. La règle rendrait alors « 0 erreur »,
# ce qui se lit comme « tout va bien » : on la retire plutôt de la liste.
DEP_INDIVIDU = {"err_cin": ("M6_valid",), "err_date_cin": ("M6_valid",),
                "err_lieu_cin": ("M6_valid",)}


def _vide(v):
    """Équivalent de `>=.` en Stata : valeur manquante."""
    return v is None or v == ""


def _oth_touche(texte, mots):
    t = (texte or "").upper()
    return any(m in t for m in mots)


def _q(valeurs, p):
    """Quantile (méthode du plus proche rang, comme `pctile` de Stata)."""
    v = sorted(x for x in valeurs if isinstance(x, (int, float)))
    if not v:
        return None
    i = max(0, min(len(v) - 1, int(round(p * len(v) + 0.5)) - 1))
    return v[i]


def _lire_erreurs(conn, districts=None, communes=None):
    """Colonnes brutes des règles du dofile. Lecture SÉPARÉE de `_lire` : ces
    colonnes ne servent qu'aux listings, les charger pour toutes les sections
    ralentirait les autres pages."""
    where, params = vad_db._clause_perimetre(conn, districts, communes)
    dm = _dataset(conn, T_MEN, where, params)
    cols = set(dm.varnames)
    vide = [None] * dm.nobs

    def col(nom, decode=False):
        if nom not in cols:
            return vide
        return dm.col_decoded(nom) if decode else dm.col(nom)

    biens = [c for c in cols
             if c.startswith(("AP__", "AP1__", "AP2__", "AP3__", "AP4__"))]
    srs = [v for v in SR_VARS if v in cols]
    simple = (("interview__key", "interview__id", "nom_cm", "Perm_rsu",
               "interview__status", "CQ3", "CQ10_already_yes_scan",
               "CQ10_already_yes_saisi", "Milieu", "Perm_indiv") + CARACT_LOG
              + tuple(MOTS_OTH) + AGRI_VARS)
    lu = {n: col(n) for n in simple}
    lu_lib = {n: col(n, True) for n in ("CQ6", "CQ7", "CQ8", "CQ9")}
    lu_code = {n: col(n) for n in ("CQ7", "CQ8", "CQ9")}
    lu_b = {n: col(n) for n in biens}

    menages = []
    for i in range(dm.nobs):
        menages.append({
            "key": txt(lu["interview__key"][i]), "id": txt(lu["interview__id"][i]),
            "nom_cm": txt(lu["nom_cm"][i]), "perm_rsu": num(lu["Perm_rsu"][i]),
            "perm_indiv": num(lu["Perm_indiv"][i]),
            "statut": num(lu["interview__status"][i]), "date": jour(lu["CQ3"][i]),
            "region": txt(lu_lib["CQ6"][i]), "district": txt(lu_lib["CQ7"][i]),
            "commune": txt(lu_lib["CQ8"][i]), "fokontany": txt(lu_lib["CQ9"][i]),
            "code_district": num(lu_code["CQ7"][i]),
            "code_commune": num(lu_code["CQ8"][i]),
            "code_fokontany": num(lu_code["CQ9"][i]),
            "deja": bool(txt(lu["CQ10_already_yes_scan"][i])
                         or txt(lu["CQ10_already_yes_saisi"][i])),
            "milieu": lu["Milieu"][i],
            "H2": lu["H2"][i],
            "log": [lu[h][i] for h in CARACT_LOG],
            "oth": {k: txt(lu[k][i]) for k in MOTS_OTH},
            "agri": {k: lu[k][i] for k in AGRI_VARS},
            "biens": [lu_b[b][i] for b in biens],
            "sr": [lu[s][i] if s in lu else col(s)[i] for s in srs],
        })
    return menages, _lire_erreurs_membres(conn, where, params), cols


def _lire_erreurs_membres(conn, where, params):
    sous = (f'SELECT "interview__key" FROM "{T_MEN}"'
            + (f" WHERE {where}" if where else ""))
    try:
        d = _dataset(conn, T_MEM, f'"interview__key" IN ({sous})', params)
    except Exception:
        return []
    if not d.nobs:
        return []
    cols = set(d.varnames)
    vide = [None] * d.nobs

    def col(nom):
        return d.col(nom) if nom in cols else vide

    noms = (("interview__key", "interview__id", "RMen__id", "M1a", "M3", "M4",
             "M5", "M6", "M6a", "M6b", "M6d", "M7", "M8", "M12", "M13", "M14",
             "M16a", "M16b", "membre_valid", "nomembre_motif_Oth", "M6_valid",
             "M3_preload", "M7_preload", "M1b_preload", "M4a_preload",
             "M5e_preload", "M6_preload", "M8_preload", "M1b_valid",
             "M4a_valid", "M5e_valid", "M7_valid", "M3_valid", "M8_valid")
            + HANDICAP)
    lu = {n: col(n) for n in noms}
    return [{n: lu[n][i] for n in noms} for i in range(d.nobs)]


def _ce_par_interview(conn):
    """interview__key -> chef d'équipe (table `vad_ce`, cf. charger_ce_vad.py)."""
    try:
        cur = conn.cursor()
        cur.execute('SELECT "interview__key", "CE" FROM "vad_ce"')
        return {k: v for k, v in cur.fetchall()}
    except Exception:
        return {}


def _sec_listing_erreurs(conn, districts=None, communes=None, diag=None):
    try:
        menages, membres, cols = _lire_erreurs(conn, districts, communes)
    except Exception:
        return {"disponible": False, "menage": [], "individu": [],
                "reglesMenage": [], "reglesIndividu": [], "nonCalculables": []}
    diag = diag or {}
    ces = _ce_par_interview(conn)
    actives = {c for c, _l, _m, _a in ERREURS_MENAGE
               if all(v in cols for v in DEP_MENAGE.get(c, ()))}
    absentes = [(l, sorted(set(DEP_MENAGE[c]) - cols))
                for c, l, _m, _a in ERREURS_MENAGE if c not in actives]
    # Une colonne présente mais vide sur toutes les lignes est traitée comme
    # absente : la règle ne peut rien détecter.
    remplies = {v for v in ("M6_valid",)
                if any(not _vide(x.get(v)) for x in membres)}
    act_ind = {c for c, _l, _m, _a in ERREURS_INDIVIDU
               if all(v in remplies for v in DEP_INDIVIDU.get(c, ()))}
    absentes += [(l, [v + " (vide sur toutes les lignes)"
                      for v in DEP_INDIVIDU[c]])
                 for c, l, _m, _a in ERREURS_INDIVIDU if c not in act_ind]

    # H2 aberrante : seuil de Tukey calculé DANS le fokontany (dofile l. 234-242).
    par_fkt = defaultdict(list)
    for m in menages:
        par_fkt[m["code_fokontany"]].append(m["H2"])
    seuils = {}
    for k, vals in par_fkt.items():
        q1, q3 = _q(vals, 0.25), _q(vals, 0.75)
        seuils[k] = (q3 + 1.5 * (q3 - q1)) if (q1 is not None and q3 is not None) else None

    l_men = []
    for m in menages:
        if m["statut"] not in STATUTS_RETENUS:
            continue
        if not (m["perm_indiv"] == 1 or m["perm_rsu"] == 1):
            continue
        e = {}
        e["erreur_refus_RSU"] = bool(m["perm_rsu"] is not None and m["perm_rsu"] > 1)
        e["erreur_fokontany"] = _vide(m["code_commune"]) or _vide(m["code_fokontany"])
        e["err_caract_log"] = m["perm_rsu"] == 1 and any(_vide(v) for v in m["log"])
        e["err_bien"] = (m["perm_rsu"] == 1 and m["deja"]
                         and any(_vide(v) for v in m["biens"]))
        e["err_autre"] = any(m["oth"][k] for k in MOTS_OTH)
        s = seuils.get(m["code_fokontany"])
        e["H2_aberante"] = bool(s is not None and isinstance(m["H2"], (int, float))
                                and m["H2"] > s)
        for k, mots in MOTS_OTH.items():
            e[f"erreur_{k}"] = _oth_touche(m["oth"][k], mots)
        if "err_milieu" in actives:
            e["err_milieu"] = _vide(m["milieu"])
        if "err_SR" in actives:
            sr = m["sr"]
            e["err_SR"] = m["perm_rsu"] == 1 and m["deja"] and any(_vide(v) for v in sr)
            e["err_SR_ppl"] = m["deja"] and not any(v == 1 for v in sr)
            e["err_SRp"] = m["deja"] and all(v == 4 or _vide(v) for v in sr)
        if "err_suptot" in actives:
            a = m["agri"]
            p1, p2, p3 = a["PT01"], a["PT02"], a["PT03"]
            nb = lambda v: v if isinstance(v, (int, float)) else 0
            e["err_suptot"] = nb(p1) + nb(p2) < nb(p3)
            e["err_supcult"] = p3 == 0 and a["typeculture"] == 1
            e["err_sup"] = any(isinstance(v, (int, float)) and v > 5 for v in (p1, p2, p3))
            e["err_rendmnt"] = bool(isinstance(a["SR10"], (int, float)) and p3
                                    and a["SR10"] * 50 / p3 > 5000)
        actifs = [k for k, v in e.items() if v]
        if not actifs:
            continue
        d = diag.get(m["key"], {})
        l_men.append({
            "key": m["key"], "nom_cm": m["nom_cm"], "date": m["date"],
            "region": m["region"], "district": m["district"],
            "commune": m["commune"], "fokontany": m["fokontany"],
            "agent": d.get("agent", ""), "ce": ces.get(m["key"], ""),
            "statut": m["statut"], "erreurs": actifs,
        })

    # ----- erreurs INDIVIDU -----
    par_men = defaultdict(list)
    for x in membres:
        par_men[x["interview__id"]].append(x)
    geo = {m["id"]: m for m in menages}
    l_ind = []
    for iid, mm in par_men.items():
        m = geo.get(iid)
        if m is None or m["statut"] not in STATUTS_RETENUS:
            continue
        liens = [(x["M7"] if not _vide(x["M7"]) else x["M7_preload"]) for x in mm]
        n_chef = sum(1 for v in liens if v == 1)
        n_conj = sum(1 for v in liens if v == 2)
        sexes_cc = [(x["M3"] if not _vide(x["M3"]) else x["M3_preload"])
                    for x, v in zip(mm, liens) if v is not None and v < 3]
        cm_cj_ko = (n_chef != 1) or (n_conj > 1)
        sexe_ko = (not cm_cj_ko
                   and any(sexes_cc.count(s) == 2 for s in (48, 49, 1, 2)))
        for x, lien in zip(mm, liens):
            age = x["M4"]
            valid = x["membre_valid"]
            majeur = isinstance(age, (int, float)) and age >= 18
            e = {}
            motif = (x["nomembre_motif_Oth"] or "").upper()
            e["err_membre"] = ("IASA" in motif) or ("KARAMA" in motif)
            e["err_cm_cj"] = bool(cm_cj_ko or (lien is not None and lien < 3
                                               and age is not None and age < 12))
            e["err_sexe_cm_cj"] = bool(sexe_ko and lien is not None and lien < 3)
            vides = [x["M7"] if not _vide(x["M7"]) else x["M7_preload"],
                     x["M3"] if not _vide(x["M3"]) else x["M3_preload"],
                     x["M4"], x["M5"], x["M8"]]
            if _vide(x["M8"]) and age is not None and age < 10:
                vides = vides[:4]
            e["err_M7_M3_M4_M8_M5_vide"] = bool(valid != 3
                                                and any(_vide(v) for v in vides))
            e["err_M13"] = bool(valid != 3 and _vide(x["M13"])
                                and age is not None and age >= 5)
            e["err_M14"] = bool(valid != 3 and x["M13"] == 1 and _vide(x["M14"]))
            e["err_alphabet"] = bool(valid != 3 and x["M13"] == 1
                                     and (_vide(x["M16a"]) or _vide(x["M16b"])))
            e["err_education"] = e["err_M13"] or e["err_M14"] or e["err_alphabet"]
            e["err_handicap"] = bool(valid != 3 and age is not None and age > 5
                                     and any(_vide(x[h]) for h in HANDICAP))
            e["err_M12"] = bool(x["M3"] in (2, 49) and age is not None
                                and age >= 15 and _vide(x["M12"]))
            # CIN : le dofile ajoute `nb_com < 6` (commentaires déjà posés sur la
            # variable). L'export ne contient aucun commentaire de variable, la
            # condition est donc toujours vraie et n'est pas reprise.
            if "err_cin" in act_ind:
                cin_cible = majeur and x["M6_valid"] in (1, 2)
                e["err_cin"] = bool(cin_cible and _vide(x["M6a"]))
                e["err_date_cin"] = bool(cin_cible and _vide(x["M6b"]))
                e["err_lieu_cin"] = bool(cin_cible and _vide(x["M6d"]))
            vf = False
            for n in ("M1b", "M4a", "M5e"):
                if x.get(n + "_valid") == 1 and (x.get(n + "_preload") or "") in ("", "##N/A##"):
                    vf = True
            for n in ("M7", "M3", "M6", "M8"):
                if x.get(n + "_valid") == 1 and _vide(x.get(n + "_preload")):
                    vf = True
            if valid != 1 or (_vide(x["M8"]) and age is not None and age < 10):
                vf = False
            e["err_validation_e_fkt"] = vf
            actifs = [k for k, v in e.items() if v]
            if not actifs:
                continue
            d = diag.get(m["key"], {})
            l_ind.append({
                "key": m["key"], "nom_cm": m["nom_cm"], "membre": txt(x["M1a"]),
                "ligne": num(x["RMen__id"]), "age": num(age), "date": m["date"],
                "region": m["region"], "district": m["district"],
                "commune": m["commune"], "fokontany": m["fokontany"],
                "agent": d.get("agent", ""), "ce": ces.get(m["key"], ""),
                "statut": m["statut"],
                "motif": txt(x["nomembre_motif_Oth"]) if e["err_membre"] else "",
                "erreurs": actifs,
            })

    return {
        "disponible": True,
        "menagesExamines": len(menages), "membresExamines": len(membres),
        "ceConnus": sum(1 for m in menages if ces.get(m["key"])),
        "menage": l_men, "individu": l_ind,
        "reglesMenage": [{"code": c, "lib": l, "msg": m, "aide": a}
                         for c, l, m, a in ERREURS_MENAGE if c in actives],
        "reglesIndividu": [{"code": c, "lib": l, "msg": m, "aide": a}
                           for c, l, m, a in ERREURS_INDIVIDU if c in act_ind],
        # Plus affiché dans la page, mais conservé : sert à savoir quelles
        # règles du dofile un export donné ne permet pas de contrôler.
        "nonCalculables": [{"lib": l, "manque": mq} for l, mq in absentes],
    }


def _sec_demographie(menages, membres):
    ordre = _ordre_groupes()
    # Effectif de chaque ménage, compté UNE fois. La version précédente
    # reparcourait la liste des membres pour chaque ménage : 15 190 × 65 884,
    # soit un milliard de comparaisons et 215 secondes sur un district entier
    # — à elle seule la quasi-totalité du temps d'ouverture du tableau de bord.
    taille_par_cle = Counter(x["key"] for x in membres)
    pyr = {g: {"H": 0, "F": 0} for g in ordre}
    for x in membres:
        g = _groupe_age(x["age"])
        if not g:
            continue
        s = (x["sexe"] or "").lower()
        if s.startswith("lahy"):
            pyr[g]["H"] += 1
        elif s.startswith("vavy"):
            pyr[g]["F"] += 1
    h = sum(v["H"] for v in pyr.values())
    f = sum(v["F"] for v in pyr.values())
    ages = [x["age"] for x in membres if isinstance(x["age"], (int, float))]
    j = sum(1 for a in ages if a < 15)
    ad = sum(1 for a in ages if 15 <= a < 65)
    v = sum(1 for a in ages if a >= 65)
    chefs = [x for x in membres if x["lien_code"] == 1]
    ch_f = sum(1 for x in chefs if (x["sexe"] or "").lower().startswith("vavy"))
    scol = [x for x in membres
            if isinstance(x["age"], (int, float)) and 6 <= x["age"] <= 17]
    actifs = [x for x in membres
              if isinstance(x["age"], (int, float)) and x["age"] >= 15]
    majeurs = [x for x in membres
               if isinstance(x["age"], (int, float)) and x["age"] >= 18]
    # Rapport de masculinité PAR GROUPE : au-dessous d'un effectif plancher, le
    # rapport n'a aucun sens (1 femme pour 17 hommes = 1 700 %, ce qui écrasait
    # l'échelle du graphique). On ne le calcule qu'à partir de MIN_EFFECTIF_RATIO
    # femmes, et on le plafonne à l'affichage.
    for g in ordre:
        F = pyr[g]["F"]
        pyr[g]["ratio"] = (round(100.0 * pyr[g]["H"] / F, 1)
                           if F >= MIN_EFFECTIF_RATIO else None)
    return {
        "pyramide": [{"groupe": g, "H": pyr[g]["H"], "F": pyr[g]["F"],
                      "ratio": pyr[g]["ratio"]} for g in ordre],
        "effectifMin": MIN_EFFECTIF_RATIO,
        "total": len(membres),
        "sansSexe": len(membres) - h - f,
        "hommes": h, "femmes": f,
        "masculinite": (round(100.0 * h / f, 1) if f else None),
        "age": _stats(ages),
        "groupes": {"moins15": j, "de15a64": ad, "plus65": v,
                    "pct_moins15": _pct(j, len(ages)),
                    "pct_15a64": _pct(ad, len(ages)),
                    "pct_plus65": _pct(v, len(ages))},
        "dependance": (round(100.0 * (j + v) / ad, 1) if ad else None),
        "tailleMenage": _stats([taille_par_cle.get(m["key"], 0)
                                for m in menages]),
        "chef": {
            "n": len(chefs),
            "femmes": ch_f, "pct_femmes": _pct(ch_f, len(chefs)),
            "age": _stats([x["age"] for x in chefs]),
        },
        "lien": _repartition([x["lien"] for x in membres]),
        "matrimonial": _repartition([x["matri"] for x in membres
                                     if isinstance(x["age"], (int, float))
                                     and x["age"] >= 12]),
        "scolarisation": {
            "cible": len(scol),
            "oui": sum(1 for x in scol if x["scol"] == 1),
            "taux": _pct(sum(1 for x in scol if x["scol"] == 1), len(scol)),
            "niveau": _repartition([x["niveau"] for x in membres]),
        },
        "activite": _repartition([x["activite"] for x in actifs]),
        "papiers": {
            "acte_oui": sum(1 for x in membres if x["acte"] == 1),
            "acte_total": sum(1 for x in membres if x["acte"] in (1, 2, 3)),
            "cin_oui": sum(1 for x in majeurs if x["cin"] == 1),
            "cin_total": sum(1 for x in majeurs if x["cin"] in (1, 2)),
            "nui_oui": sum(1 for x in membres if x["nui"] == 1),
            "nui_total": sum(1 for x in membres if x["nui"] in (1, 2)),
        },
    }


def _sec_habitation(menages):
    pieces = [m["H2"] for m in menages if isinstance(m["H2"], (int, float))
              and 0 < m["H2"] < 30]
    # Surpeuplement : personnes par pièce (seuil usuel > 3 = surpeuplé).
    ratio = []
    for m in menages:
        n = m["nbmembre"]
        p = m["H2"]
        if isinstance(n, (int, float)) and isinstance(p, (int, float)) and p > 0:
            ratio.append(n / p)
    return {
        "murs": _repartition([m["H1_l"] for m in menages]),
        "sol": _repartition([m["H4_l"] for m in menages]),
        "toit": _repartition([m["H5_l"] for m in menages]),
        "occupation": _repartition([m["H10_l"] for m in menages]),
        "eclairage": _repartition([m["H6_l"] for m in menages]),
        "pieces": _stats(pieces),
        "piecesDistrib": _repartition([str(int(p)) for p in pieces],
                                      tri_effectif=False),
        "personnesParPiece": _stats(ratio),
        "surpeuple": {"n": sum(1 for r in ratio if r > 3), "total": len(ratio),
                      "pct": _pct(sum(1 for r in ratio if r > 3), len(ratio))},
    }


def _sec_biens(menages):
    """Taux de possession de chaque bien, par famille. Un bien vaut 1 = possédé."""
    lignes = []
    for code, lib in BIENS.items():
        vals = [m["biens"].get(code) for m in menages]
        rep = [v for v in vals if v in (0, 1)]
        if not rep:
            continue
        oui = sum(1 for v in rep if v == 1)
        famille = next((f for f, codes in FAMILLE_BIEN.items() if code in codes),
                       "Autres")
        lignes.append({"code": code, "lib": lib, "famille": famille,
                       "oui": oui, "total": len(rep), "pct": _pct(oui, len(rep))})
    lignes.sort(key=lambda r: -(r["pct"] or 0))
    # Nombre de biens possédés par ménage (indicateur synthétique simple).
    nb = []
    for m in menages:
        rep = [v for v in m["biens"].values() if v in (0, 1)]
        if rep:
            nb.append(sum(1 for v in rep if v == 1))
    return {"lignes": lignes, "nbBiens": _stats(nb),
            "familles": list(FAMILLE_BIEN)}


def _sec_eau(menages):
    eau = [m for m in menages if m["H7"] is not None]
    san = [m for m in menages if m["H8"] is not None]
    n_eau = sum(1 for m in eau if m["H7"] in EAU_AMELIOREE)
    n_san = sum(1 for m in san if m["H8"] in SANIT_AMELIOREE)
    n_air = sum(1 for m in san if m["H8"] == 1)          # défécation à l'air libre
    return {
        "source": _repartition([m["H7_l"] for m in menages]),
        "toilettes": _repartition([m["H8_l"] for m in menages]),
        "ordures": _repartition([m["H9_l"] for m in menages]),
        "eauAmelioree": {"n": n_eau, "total": len(eau),
                         "pct": _pct(n_eau, len(eau))},
        "sanitAmelioree": {"n": n_san, "total": len(san),
                           "pct": _pct(n_san, len(san))},
        "airLibre": {"n": n_air, "total": len(san), "pct": _pct(n_air, len(san))},
    }


def _hand_etat(m):
    """(renseigné, difficulté au sens strict, quelque difficulté) d'une personne.

    « Au sens strict » = la définition du Washington Group : beaucoup de
    difficulté ou incapacité dans au moins un des sept domaines. C'est ce seuil
    qui se compare d'un pays à l'autre ; « quelque difficulté » est reporté à
    part parce qu'il gonfle la prévalence sans être comparable."""
    v = [m.get("hand", {}).get(d) for d in AUEM_DOMAINES]
    if all(x is None for x in v):
        return False, False, False
    return True, any(x in HAND_DIFFICILE for x in v), any(x == HAND_QUELQUE for x in v)


def _sec_handicap(menages, membres):
    """Section « Handicap » — les sept domaines du Washington Group."""
    rens = [m for m in membres if _hand_etat(m)[0]]
    dur = [m for m in rens if _hand_etat(m)[1]]
    leg = [m for m in rens if _hand_etat(m)[2] and not _hand_etat(m)[1]]
    domaines = []
    for code, lib in AUEM_DOMAINES.items():
        v = [m["hand"].get(code) for m in membres if m.get("hand", {}).get(code)]
        k = sum(1 for x in v if x in HAND_DIFFICILE)
        domaines.append({"lib": lib, "n": k, "total": len(v), "pct": _pct(k, len(v))})
    domaines.sort(key=lambda r: -(r["pct"] or 0))
    # Prévalence par âge : elle croît fortement après 60 ans, et c'est le
    # meilleur contrôle de vraisemblance de la série.
    par_age, par_sexe = [], []
    for lo, hi, lib in ((0, 17, "0-17 ans"), (18, 39, "18-39 ans"),
                        (40, 59, "40-59 ans"), (60, 200, "60 ans et +")):
        g = [m for m in rens if isinstance(m["age"], (int, float))
             and lo <= m["age"] <= hi]
        k = sum(1 for m in g if _hand_etat(m)[1])
        par_age.append({"lib": lib, "n": k, "total": len(g), "pct": _pct(k, len(g))})
    for sx in sorted({txt(m["sexe"]) for m in rens if txt(m["sexe"])}):
        g = [m for m in rens if txt(m["sexe"]) == sx]
        k = sum(1 for m in g if _hand_etat(m)[1])
        par_sexe.append({"lib": sx, "n": k, "total": len(g), "pct": _pct(k, len(g))})
    cles = {m["key"] for m in dur}
    carte = Counter(m.get("hand_carte") for m in dur if m.get("hand_carte"))
    return {
        "renseignes": len(rens), "total": len(membres),
        "couverture": _pct(len(rens), len(membres)),
        "difficulte": {"n": len(dur), "pct": _pct(len(dur), len(rens))},
        "quelque": {"n": len(leg), "pct": _pct(len(leg), len(rens))},
        "domaines": domaines, "parAge": par_age, "parSexe": par_sexe,
        "menages": {"n": len(cles), "total": len(menages),
                    "pct": _pct(len(cles), len(menages))},
        "carte": {"oui": carte.get(1, 0), "non": carte.get(2, 0),
                  "nsp": carte.get(3, 0)},
    }


def _sec_identite(menages, membres):
    """Section « Identité » — acte de naissance, CIN, NUI.

    Le thème dont dépend toute la chaîne : un registre social ne peut servir
    que des personnes qu'il sait identifier. On compte les documents là où ils
    sont exigibles — la CIN à partir de 18 ans, jamais avant."""
    acte = [m for m in membres if m.get("acte") in (1, 2, 3)]
    avec_acte = sum(1 for m in acte if m["acte"] == 1)
    sans_acte = sum(1 for m in acte if m["acte"] == 2)
    nsp_acte = sum(1 for m in acte if m["acte"] == 3)
    majeurs = [m for m in membres if isinstance(m["age"], (int, float))
               and m["age"] >= AGE_MAJEUR]
    cin = [m for m in majeurs if m.get("cin") in (1, 2)]
    avec_cin = sum(1 for m in cin if m["cin"] == 1)
    nui = [m for m in membres if m.get("nui") in (1, 2)]
    avec_nui = sum(1 for m in nui if m["nui"] == 1)
    # Enregistrement des naissances : l'indicateur ODD 16.9.1 porte sur les
    # moins de 5 ans, seul âge où l'absence d'acte est encore rattrapable
    # simplement.
    petits = [m for m in acte if isinstance(m["age"], (int, float)) and m["age"] < 5]
    petits_ok = sum(1 for m in petits if m["acte"] == 1)
    par_age = []
    for lo, hi, lib in ((0, 4, "0-4 ans"), (5, 17, "5-17 ans"),
                        (18, 59, "18-59 ans"), (60, 200, "60 ans et +")):
        g = [m for m in acte if isinstance(m["age"], (int, float))
             and lo <= m["age"] <= hi]
        k = sum(1 for m in g if m["acte"] == 1)
        par_age.append({"lib": lib, "n": k, "total": len(g), "pct": _pct(k, len(g))})
    # Personnes sans AUCUN document : ni acte, ni CIN (si majeur), ni NUI.
    aucun = 0
    for m in membres:
        if m.get("acte") == 1 or m.get("nui") == 1:
            continue
        if isinstance(m["age"], (int, float)) and m["age"] >= AGE_MAJEUR \
                and m.get("cin") == 1:
            continue
        if m.get("acte") in (2, 3) or m.get("nui") == 2 or m.get("cin") == 2:
            aucun += 1
    return {
        "acte": {"oui": avec_acte, "non": sans_acte, "nsp": nsp_acte,
                 "total": len(acte), "pct": _pct(avec_acte, len(acte))},
        "cin": {"n": avec_cin, "total": len(cin), "pct": _pct(avec_cin, len(cin)),
                "majeurs": len(majeurs)},
        "nui": {"n": avec_nui, "total": len(nui), "pct": _pct(avec_nui, len(nui))},
        "naissances": {"n": petits_ok, "total": len(petits),
                       "pct": _pct(petits_ok, len(petits))},
        "parAge": par_age,
        "aucun": {"n": aucun, "total": len(membres),
                  "pct": _pct(aucun, len(membres))},
    }


def _sec_education(membres):
    """Section « Éducation » — fréquentation, niveau atteint, alphabétisation."""
    freq = [m for m in membres if m.get("scol") in (1, 2)]
    a_frequente = sum(1 for m in freq if m["scol"] == 1)
    act = [m for m in membres if m.get("scol_act") in (1, 2)]
    en_cours = sum(1 for m in act if m["scol_act"] == 1)
    scol_age = [m for m in act if isinstance(m["age"], (int, float))
                and AGE_SCOL[0] <= m["age"] <= AGE_SCOL[1]]
    scol_age_ok = sum(1 for m in scol_age if m["scol_act"] == 1)
    alpha = [m for m in membres if isinstance(m["age"], (int, float))
             and m["age"] >= AGE_ALPHA and m.get("lire") in (1, 2, 3)]
    # M16a / M16b : 1 « bien », 2 « un peu », 3 « pas du tout ».
    sait_lire = sum(1 for m in alpha if m["lire"] in (1, 2))
    ecr = [m for m in membres if isinstance(m["age"], (int, float))
           and m["age"] >= AGE_ALPHA and m.get("ecrire") in (1, 2, 3)]
    sait_ecrire = sum(1 for m in ecr if m["ecrire"] in (1, 2))
    par_sexe = []
    for sx in sorted({txt(m["sexe"]) for m in scol_age if txt(m["sexe"])}):
        g = [m for m in scol_age if txt(m["sexe"]) == sx]
        k = sum(1 for m in g if m["scol_act"] == 1)
        a = [m for m in alpha if txt(m["sexe"]) == sx]
        ka = sum(1 for m in a if m["lire"] in (1, 2))
        par_sexe.append({"lib": sx, "scol": _pct(k, len(g)), "scolN": len(g),
                         "alpha": _pct(ka, len(a)), "alphaN": len(a)})
    par_age = []
    for lo, hi in ((6, 10), (11, 14), (15, 17), (18, 24)):
        g = [m for m in act if isinstance(m["age"], (int, float))
             and lo <= m["age"] <= hi]
        k = sum(1 for m in g if m["scol_act"] == 1)
        par_age.append({"lib": f"{lo}-{hi} ans", "n": k, "total": len(g),
                        "pct": _pct(k, len(g))})
    return {
        "aFrequente": {"n": a_frequente, "total": len(freq),
                       "pct": _pct(a_frequente, len(freq))},
        "enCours": {"n": en_cours, "total": len(act),
                    "pct": _pct(en_cours, len(act))},
        "scolarisation": {"n": scol_age_ok, "total": len(scol_age),
                          "pct": _pct(scol_age_ok, len(scol_age)),
                          "bornes": f"{AGE_SCOL[0]}-{AGE_SCOL[1]} ans"},
        "lecture": {"n": sait_lire, "total": len(alpha),
                    "pct": _pct(sait_lire, len(alpha))},
        "ecriture": {"n": sait_ecrire, "total": len(ecr),
                     "pct": _pct(sait_ecrire, len(ecr))},
        "niveau": _repartition([m["niveau"] for m in membres]),
        "parSexe": par_sexe, "parAge": par_age,
    }


def _sec_enfance(menages, membres):
    """Section « Enfance » — orphelinage, scolarisation, handicap, état civil.

    Elle ne mesure rien de neuf : elle recoupe les trois sections précédentes
    sur les moins de 18 ans, parce que c'est à cet âge que les critères de
    ciblage se cumulent et qu'un enfant non enregistré, non scolarisé et
    orphelin n'apparaît dans aucune des trois vues prises isolément."""
    enf = [m for m in membres if isinstance(m["age"], (int, float))
           and m["age"] <= AGE_ENFANT]
    orph = [m for m in enf if m.get("orphelin") in (1, 2, 3, 4)]
    n_orph = sum(1 for m in orph if m["orphelin"] in (1, 2, 3))
    detail = {"pere": sum(1 for m in orph if m["orphelin"] == 1),
              "mere": sum(1 for m in orph if m["orphelin"] == 2),
              "deux": sum(1 for m in orph if m["orphelin"] == 3)}
    scol = [m for m in enf if m.get("scol_act") in (1, 2)
            and AGE_SCOL[0] <= m["age"] <= AGE_SCOL[1]]
    hors = sum(1 for m in scol if m["scol_act"] == 2)
    acte = [m for m in enf if m.get("acte") in (1, 2, 3)]
    sans_acte = sum(1 for m in acte if m["acte"] != 1)
    hrens = [m for m in enf if _hand_etat(m)[0]]
    hand = sum(1 for m in hrens if _hand_etat(m)[1])
    # Cumul : orphelin ET déscolarisé ET/OU sans acte. C'est la liste courte
    # que le ciblage cherche, et elle se calcule en une passe.
    cumul = 0
    for m in enf:
        k = 0
        if m.get("orphelin") in (1, 2, 3):
            k += 1
        if m.get("scol_act") == 2 and AGE_SCOL[0] <= m["age"] <= AGE_SCOL[1]:
            k += 1
        if m.get("acte") in (2, 3):
            k += 1
        if _hand_etat(m)[1]:
            k += 1
        if k >= 2:
            cumul += 1
    # Ménages dont le chef est mineur.
    chefs_mineurs = sum(1 for m in membres if m.get("lien_code") == 1
                        and isinstance(m["age"], (int, float))
                        and m["age"] < AGE_MAJEUR)
    return {
        "enfants": {"n": len(enf), "total": len(membres),
                    "pct": _pct(len(enf), len(membres))},
        "orphelins": {"n": n_orph, "total": len(orph),
                      "pct": _pct(n_orph, len(orph)), "detail": detail},
        "deScolarises": {"n": hors, "total": len(scol), "pct": _pct(hors, len(scol))},
        "sansActe": {"n": sans_acte, "total": len(acte),
                     "pct": _pct(sans_acte, len(acte))},
        "handicap": {"n": hand, "total": len(hrens), "pct": _pct(hand, len(hrens))},
        "cumul": {"n": cumul, "total": len(enf), "pct": _pct(cumul, len(enf))},
        "chefsMineurs": chefs_mineurs,
        "repartitionOrphelinage": _repartition([m["orphelin_l"] for m in enf]),
    }


def _sec_activite(menages, membres):
    """Section « Activité & agriculture » — emploi déclaré et moyens agricoles."""
    actifs = [m for m in membres if isinstance(m["age"], (int, float))
              and m["age"] >= AGE_ACTIF]
    avec = [m for m in actifs if txt(m["activite"])]
    par_sexe = []
    for sx in sorted({txt(m["sexe"]) for m in actifs if txt(m["sexe"])}):
        g = [m for m in actifs if txt(m["sexe"]) == sx]
        k = sum(1 for m in g if txt(m["activite"]))
        par_sexe.append({"lib": sx, "n": k, "total": len(g),
                         "pct": _pct(k, len(g))})
    agri = [m for m in menages if m.get("cultures")]
    carte = [m for m in menages if m.get("carte_agri") in (1, 2, 3)]
    avec_carte = sum(1 for m in carte if m["carte_agri"] in (1, 2))
    # Cultures déclarées : saisie en TEXTE LIBRE (« vary », « Vary », « VARY »),
    # donc normalisées à la volée. Le regroupement reste approximatif : il ne
    # corrige ni les fautes de frappe ni les synonymes (« tsako » / « katsaka »).
    cult = Counter()
    for m in agri:
        for c in m["cultures"]:
            k = txt(c).strip().lower()
            if k and k not in ("##n/a##", ".", "-"):
                cult[k] += 1
    cultures = [{"lib": k, "n": v, "pct": _pct(v, len(agri))}
                for k, v in cult.most_common(15)]
    return {
        "actifs": {"n": len(avec), "total": len(actifs),
                   "pct": _pct(len(avec), len(actifs)),
                   "borne": f"{AGE_ACTIF} ans et plus"},
        "activites": _repartition([m["activite"] for m in actifs]),
        "parSexe": par_sexe,
        "menagesAgricoles": {"n": len(agri), "total": len(menages),
                             "pct": _pct(len(agri), len(menages))},
        "carteAgricole": {"n": avec_carte, "total": len(carte),
                          "pct": _pct(avec_carte, len(carte))},
        "cultures": cultures,
        "cultureTexteLibre": True,
    }


def _sec_mobilite(menages, membres):
    """Section « Résidence & mobilité » — présence, nationalité, origine."""
    res = [m for m in membres if m.get("residence") in (1, 2, 3, 4)]
    c = Counter(m["residence"] for m in res)
    nat = [m for m in membres if m.get("nationalite") in (1, 2)]
    etrangers = sum(1 for m in nat if m["nationalite"] == 2)
    # Né hors de sa commune de résidence : comparaison de LIBELLÉS, insensible
    # à la casse et aux espaces. Approximatif — la saisie est libre — mais
    # suffisant pour un ordre de grandeur de la mobilité interne.
    par_cle = {m["key"]: txt(m["commune"]) for m in menages}
    norm = lambda x: " ".join(txt(x).lower().split()) if txt(x) else ""
    nes = [m for m in membres if txt(m.get("naissance"))]
    ailleurs = sum(1 for m in nes
                   if norm(m["naissance"]) and norm(par_cle.get(m["key"]))
                   and norm(m["naissance"]) != norm(par_cle.get(m["key"])))
    return {
        "residence": _repartition([m["residence_l"] for m in membres]),
        "presents": {"n": c.get(1, 0), "total": len(res),
                     "pct": _pct(c.get(1, 0), len(res))},
        "recents": {"n": c.get(2, 0), "pct": _pct(c.get(2, 0), len(res))},
        "absents": {"n": c.get(3, 0), "pct": _pct(c.get(3, 0), len(res))},
        "visiteurs": {"n": c.get(4, 0), "pct": _pct(c.get(4, 0), len(res))},
        "etrangers": {"n": etrangers, "total": len(nat),
                      "pct": _pct(etrangers, len(nat))},
        "nesAilleurs": {"n": ailleurs, "total": len(nes),
                        "pct": _pct(ailleurs, len(nes))},
        "origines": _repartition([m["naissance"] for m in membres])["lignes"][:15],
        "motifsArrivee": _repartition([m["motif_arrivee"] for m in membres]),
    }


# Un numéro joignable : dix chiffres commençant par 03, et qui ne soit pas une
# valeur de remplissage. `0300000000` et `0399999999` passent le format sans
# être des numéros — c'est même la manière la plus courante de contourner un
# champ obligatoire.
_TEL_FORME = re.compile(r"^0[23]\d{8}$")
_TEL_BIDON = re.compile(r"^0[23](\d)\1{7}$|0{6,}|9{6,}")


def _tel_joignable(v):
    t = "".join(ch for ch in txt(v) if ch.isdigit())
    if not t or not _TEL_FORME.match(t):
        return False
    return not _TEL_BIDON.search(t)


def _sec_ciblage(menages):
    """Section « Ciblage & joignabilité » — éligibilité, type de ménage, contact.

    Moins un thème descriptif qu'un état des lieux opérationnel : de quoi
    dispose-t-on pour décider, et pourra-t-on recontacter les ménages retenus ?"""
    eli = [m for m in menages if txt(m.get("eligibilite"))]
    tel_saisis = [m for m in menages if txt(m.get("tel"))]
    joignables = [m for m in tel_saisis if _tel_joignable(m["tel"])]
    cq = [m for m in menages if m.get("cq62") in (1, 2, 3)]
    complet = sum(1 for m in cq if m["cq62"] == 1)
    absent = sum(1 for m in cq if m["cq62"] == 3)
    return {
        "eligibilite": _repartition([m["eligibilite"] for m in menages]),
        "classes": {"n": len(eli), "total": len(menages),
                    "pct": _pct(len(eli), len(menages))},
        "typemen": _repartition([m["typemen"] for m in menages]),
        "joignables": {"n": len(joignables), "total": len(menages),
                       "pct": _pct(len(joignables), len(menages))},
        "telSaisis": {"n": len(tel_saisis),
                      "factices": len(tel_saisis) - len(joignables),
                      "pct": _pct(len(tel_saisis) - len(joignables),
                                  len(tel_saisis))},
        "presenceChef": {"complete": complet, "absente": absent, "total": len(cq),
                         "pct": _pct(complet, len(cq))},
        "repartitionPresence": _repartition([m["cq62_l"] for m in menages]),
    }


def _sec_gps(menages, diag=None):
    """Capture GPS + un point par ménage géolocalisé.

    Chaque point porte l'AGENT et la DATE : c'est ce qui colore et filtre la carte
    du dénombrement, dont celle-ci reprend le fonctionnement. L'agent vit dans
    `vad_diagnostics` (`responsible`), pas dans la table des ménages, d'où `diag`."""
    diag = diag or {}
    avec = [m for m in menages if m["lat"] is not None and m["lon"] is not None]
    acc = [m["acc"] for m in avec if isinstance(m["acc"], (int, float))]
    return {
        "total": len(menages), "captures": len(avec),
        "taux": _pct(len(avec), len(menages)),
        "precision": _stats(acc),
        "precisionBonne": {
            "n": sum(1 for a in acc if a <= 50), "total": len(acc),
            "pct": _pct(sum(1 for a in acc if a <= 50), len(acc))},
        # Ménages dont on connaît AUSSI le point du dénombrement. Ceux du
        # dénombrement sans correspondance VAD ne sont pas envoyés du tout :
        # la carte décrit la visite à domicile, pas le dénombrement.
        "lies": sum(1 for m in avec if m.get("gps_den")),
        "ecart": _stats([_distance_m((m["lat"], m["lon"]), m["gps_den"])
                         for m in avec if m.get("gps_den")]),
        "points": [_point_carte(m, diag) for m in avec],
    }


def _distance_m(a, b):
    """Distance de haversine, en mètres. Même formule que `vad_qualite`."""
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2)
         * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _point_carte(m, diag):
    """Un point de la carte. `dl`/`dg`/`dd` ne sont présents que si le ménage
    est relié au dénombrement — la carte s'en sert pour décider d'afficher, ou
    non, le point d'origine et le trait de liaison."""
    p = {"lat": round(m["lat"], 6), "lon": round(m["lon"], 6),
         "f": m["fokontany"], "cm": m["commune"],
         "c": m["code_den"] or m["key"],
         "nom": m["nom_cm"], "date": m["date"],
         "ag": diag.get(m["key"], {}).get("agent", ""),
         "n": m["nbmembre"],
         "acc": (round(m["acc"]) if isinstance(m["acc"], (int, float)) else None)}
    d = m.get("gps_den")
    if d:
        p["dl"] = round(d[0], 6)
        p["dg"] = round(d[1], 6)
        p["dd"] = round(_distance_m((m["lat"], m["lon"]), d))
    return p


# Anomalies recherchées : (code, libellé, gravité). « bloquant » = à corriger
# avant exploitation ; « signal » = à vérifier.
ANOMALIES = [
    ("statut", "Interview non approuvée par le superviseur", "signal"),
    ("erreurs", "Interview signalée en erreur par Survey Solutions", "bloquant"),
    ("sans_gps", "Aucune coordonnée GPS", "bloquant"),
    ("gps_imprecis", "GPS imprécis (> 100 m)", "signal"),
    ("sans_lien_den",
     "Ménage annoncé « liste e-Fokontany » mais sans lien vers le dénombrement",
     "bloquant"),
    ("membres_absents", "Aucun membre listé", "bloquant"),
    ("nb_incoherent", "Nombre de membres déclaré ≠ membres listés", "signal"),
    ("sans_chef", "Aucun chef de ménage dans la liste des membres", "bloquant"),
    ("plusieurs_chefs", "Plusieurs chefs de ménage", "signal"),
    ("sexe_manquant", "Membre(s) sans sexe", "signal"),
    ("age_manquant", "Membre(s) sans âge", "signal"),
    ("age_aberrant", "Âge hors bornes (> 110 ans)", "signal"),
    ("refus_poursuivi", "Consentement RSU refusé mais entretien réalisé", "signal"),
    ("doublon_den", "Même ménage du dénombrement visité 2 ou 3 fois", "bloquant"),
    ("lien_den_douteux",
     "Code du dénombrement répété plus de 3 fois (préchargement défectueux)",
     "signal"),
]

# Au-delà de ce nombre de répétitions, un même `interview_keyden` ne traduit plus
# une double visite mais un PRÉCHARGEMENT DÉFECTUEUX (le même code recopié sur des
# dizaines de ménages) : deux diagnostics très différents, à ne pas confondre.
SEUIL_DOUBLON_DEN = 3


def _sec_erreurs(menages, membres, diag):
    par_men = defaultdict(list)
    for x in membres:
        par_men[x["key"]].append(x)
    vus_keyden = Counter(m["keyden"] for m in menages if m["keyden"])
    lignes = []
    for m in menages:
        mm = par_men.get(m["key"], [])
        chefs = sum(1 for x in mm if x["lien_code"] == 1)
        pbs = []
        if m["statut"] not in (120, 130):
            pbs.append("statut")
        if (m["erreurs"] or 0) > 0:
            pbs.append("erreurs")
        if m["lat"] is None or m["lon"] is None:
            pbs.append("sans_gps")
        elif isinstance(m["acc"], (int, float)) and m["acc"] > 100:
            pbs.append("gps_imprecis")
        # Un ménage « Tokantrano vaovao » (nouveau) n'a PAS à être rattaché au
        # dénombrement : l'absence de lien n'est une anomalie que pour un ménage
        # annoncé comme venant de la liste e-Fokontany (typemen = 1).
        if not m["keyden"]:
            if m["typemen_code"] == 1:
                pbs.append("sans_lien_den")
        elif vus_keyden[m["keyden"]] > SEUIL_DOUBLON_DEN:
            pbs.append("lien_den_douteux")
        elif vus_keyden[m["keyden"]] > 1:
            pbs.append("doublon_den")
        if not mm:
            pbs.append("membres_absents")
        else:
            if isinstance(m["nbmembre"], (int, float)) and int(m["nbmembre"]) != len(mm):
                pbs.append("nb_incoherent")
            if chefs == 0:
                pbs.append("sans_chef")
            elif chefs > 1:
                pbs.append("plusieurs_chefs")
            if any(not x["sexe"] for x in mm):
                pbs.append("sexe_manquant")
            if any(x["age"] is None for x in mm):
                pbs.append("age_manquant")
            if any(isinstance(x["age"], (int, float)) and x["age"] > 110 for x in mm):
                pbs.append("age_aberrant")
        if m["perm_rsu"] == 2 and mm:
            pbs.append("refus_poursuivi")
        if pbs:
            d = diag.get(m["key"], {})
            lignes.append({
                "key": m["key"], "code_den": m["code_den"],
                "agent": d.get("agent", ""), "date": m["date"],
                "commune": m["commune"], "fokontany": m["fokontany"],
                "nbmembre": m["nbmembre"], "membres": len(mm),
                "problemes": pbs,
            })
    compte = Counter(p for l in lignes for p in l["problemes"])
    grav = {c: g for c, _lib, g in ANOMALIES}
    return {
        "menages": len(menages),
        "avecAnomalie": len(lignes),
        "pct": _pct(len(lignes), len(menages)),
        "types": [{"code": c, "lib": lib, "gravite": g, "n": compte.get(c, 0)}
                  for c, lib, g in ANOMALIES],
        "bloquants": sum(n for c, n in compte.items() if grav.get(c) == "bloquant"),
        "lignes": sorted(lignes, key=lambda l: (-len(l["problemes"]), l["date"])),
    }


def _sec_agents(menages, membres, diag):
    memb = Counter(x["key"] for x in membres)
    par = defaultdict(lambda: {"n": 0, "membres": 0, "jours": set(),
                               "durees": [], "erreurs": 0})
    for m in menages:
        d = diag.get(m["key"], {})
        a = d.get("agent") or "(agent inconnu)"
        p = par[a]
        p["n"] += 1
        p["membres"] += memb.get(m["key"], 0)
        if m["date"]:
            p["jours"].add(m["date"])
        if d.get("duree"):
            p["durees"].append(d["duree"])
        if (m["erreurs"] or 0) > 0 or m["statut"] not in (120, 130):
            p["erreurs"] += 1
    out = []
    for a, p in par.items():
        out.append({
            "agent": a, "menages": p["n"], "membres": p["membres"],
            "jours": len(p["jours"]),
            "parJour": round(p["n"] / len(p["jours"]), 1) if p["jours"] else None,
            "duree": _stats(p["durees"])["moy"],
            "taille": round(p["membres"] / p["n"], 2) if p["n"] else None,
            "anomalies": p["erreurs"],
        })
    out.sort(key=lambda r: -r["menages"])
    return out


def _sec_ecart_declaration(conn, menages, diag, codes, noms, descente=False):
    """Écart, PAR AGENT, entre les ménages qu'il DÉCLARE avoir interviewés et
    ceux qui sont ARRIVÉS AU SERVEUR (table `vad_menage`).

    La déclaration vient de `declaration_agent` (type « VAD »), saisie par le
    Superviseur Technique. Le calcul est celui du dénombrement
    (`rapport_core.ecart_declaration`) : un seul code, donc les mêmes règles —
    écart = déclaré − reçu, « — » quand rien n'a été déclaré (ce n'est pas un
    zéro), ménages sans date valide écartés.

    `codes` = codes agent BRUTS présents au serveur dans le périmètre ;
    `noms` = {code: nom}, pour parler la même langue que le reste de la page
    (les agrégats VAD affichent le NOM de l'agent quand il est renseigné).

    `descente` : au niveau commune / fokontany, on ne calcule RIEN. L'agent
    déclare un nombre PAR JOUR, pas par zone : confronter sa déclaration
    entière aux seuls ménages d'une commune fabriquerait un écart faux."""
    if descente:
        return {"dispo": False, "raison": "descente", "agents": [], "total": {}}
    ac = equipes.agents_et_chefs(conn)
    brut = declarations.par_agent_date_perimetre(conn, "VAD", codes, ac)
    declare, chefs = {}, {}
    for (code, d), n in brut.items():
        cle = noms.get(code, code)
        declare[(cle, d)] = declare.get((cle, d), 0) + n
    for code in set(codes) | {c for c, _ in brut}:
        info = ac.get(code, {})
        chefs[noms.get(code, code)] = (info.get("chef_nom")
                                       or info.get("chef_login") or "")
    lignes = [{"agent": (diag.get(m["key"], {}).get("agent")
                         or "(agent inconnu)"),
               "date": m["date"]} for m in menages]
    out = rapport_core.ecart_declaration(lignes, declare, chefs)
    out["dispo"] = bool(out["total"]["declarants"])
    out["raison"] = "" if out["dispo"] else "aucune"
    return out


def _sec_ecart_dates(conn, menages, agent_code, noms):
    """Une ligne par AGENT × DATE, pour TOUS les agents du périmètre — qu'ils
    aient déclaré ou non : déclaré (None = pas de déclaration, ce n'est pas un
    zéro), arrivé au serveur (interviews datées), écart = déclaré − arrivé, et
    la ventilation des interviews arrivées par statut Survey Solutions.
    Alimente la feuille Excel « Écart par agent »."""
    ac = equipes.agents_et_chefs(conn)
    codes = {c for c in agent_code.values() if c}
    try:
        declare = declarations.par_agent_date_perimetre(conn, "VAD", codes, ac)
    except Exception:
        declare = {}
    cles_statut = [c for _s, c, _l in STATUTS_COUV] + [STATUT_AUTRE[1]]
    lignes = {}

    def ligne(code, d):
        l = lignes.get((code, d))
        if l is None:
            info = ac.get(code, {})
            l = lignes[(code, d)] = {
                "code": code, "agent": noms.get(code, code), "date": d,
                "chef": info.get("chef_nom") or info.get("chef_login") or "",
                "declare": None, "recu": 0, **{c: 0 for c in cles_statut}}
        return l

    sans_date = Counter()
    for m in menages:
        code = agent_code.get(m["key"]) or "(agent inconnu)"
        if not m["date"]:
            sans_date[code] += 1
            continue
        l = ligne(code, m["date"])
        l["recu"] += 1
        l[_cle_statut(m["statut"])] += 1
    for (code, d), n in declare.items():
        ligne(code, d)["declare"] = int(n or 0)
    out = sorted(lignes.values(), key=lambda l: (l["agent"], l["date"]))
    for l in out:
        l["ecart"] = (l["declare"] - l["recu"]
                      if l["declare"] is not None else None)
    return {"lignes": out, "statuts": STATUTS_COUV + (STATUT_AUTRE,),
            "sansDate": dict(sans_date)}


# ---------------------------------------------------------------------------
# Couverture par agent : l'AFFECTATION du préchargement face aux interviews VAD
# ---------------------------------------------------------------------------
# La base de préchargement (registre `prechargement_ensemble`, qui fait foi)
# dit EXACTEMENT quels ménages ont été affectés à quel agent (`ENQ`). La VAD
# garde la même clé, `interview_keyden` (= clé de l'interview du dénombrement
# + « - » + rang du ménage dans le segment, sur 3 chiffres). Le rapprochement se
# fait donc ménage par ménage, sans approximation.
#
# Règles (validées avec l'utilisateur, 2026-09-26) :
#   - un ménage compte UNE fois, même interviewé plusieurs fois (la double
#     interview est signalée à part, dans `doubles`) ;
#   - « affectés interviewés » = interviewés PAR L'AGENT AFFECTÉ ;
#   - un ménage affecté à A mais interviewé par B : « interviewé par un autre »
#     chez A (il n'est plus à faire), « non affecté interviewé » chez B ;
#   - les statuts Survey Solutions sont ventilés, pas filtrés : pour un ménage
#     interviewé plusieurs fois, on garde le statut le plus avancé.
# Colonnes de statut, dans l'ordre d'affichage. Tout autre code -> « en cours ».
STATUTS_COUV = ((130, "approuveHq", "Approuvé siège"),
                (120, "approuveSup", "Approuvé superviseur"),
                (100, "termine", "Terminé"),
                (65, "rejeteSup", "Rejeté superviseur"),
                (125, "rejeteHq", "Rejeté siège"))
STATUT_AUTRE = (None, "enCours", "En cours / autre")
_RANG_STATUT = {code: i for i, (code, _c, _l) in enumerate(STATUTS_COUV)}
T_PRECH = "prechargement_ensemble"


def _cle_statut(s):
    for code, cle, _l in STATUTS_COUV:
        if s == code:
            return cle
    return STATUT_AUTRE[1]


def _requete(conn, sql, params=()):
    """Lignes d'une requête, ou None si la table manque (base neuve). Sur
    PostgreSQL une requête en échec annule la transaction : on la relâche."""
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        return cur.fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def _affectations(conn, districts=None, communes=None, fokontany=None):
    """{keyden: ménage affecté} du registre de préchargement, borné au
    périmètre par le code fokontany 8 chiffres (commune = code // 100)."""
    ph = db_source._placeholder(conn)
    if fokontany is not None:
        codes = ((int(fokontany),) if isinstance(fokontany, (int, str))
                 else tuple(int(f) for f in fokontany))
        where = f'"code_fokontany" IN ({",".join([ph] * len(codes))})'
    elif communes is not None:
        codes = tuple(int(c) for c in communes)
        where = f'("code_fokontany" / 100) IN ({",".join([ph] * len(codes))})'
    elif districts:
        codes = tuple(int(d) for d in districts)
        where = f'"code_district" IN ({",".join([ph] * len(codes))})'
    else:
        codes, where = (), ""
    if where and not codes:
        return {}
    rows = _requete(
        conn,
        'SELECT "interview_keyden", "ENQ", "CE", "code_district", '
        '"code_fokontany", "fkt_recherche", "nom_cm", "taille_men", "adresse", '
        '"description", "code_den", "lot_id" FROM "' + T_PRECH + '"'
        + (f" WHERE {where}" if where else ""), codes)
    out = {}
    for (kd, enq, ce, dis, fkt, fnom, nom, taille, adr, desc, cden,
         lot) in rows or ():
        kd = txt(kd)
        if not kd or kd in out:
            continue
        out[kd] = {"keyden": kd, "enq": txt(enq), "ce": txt(ce),
                   "district": num(dis), "fokontany": num(fkt),
                   "fokontany_nom": txt(fnom), "nom_cm": txt(nom),
                   "taille": num(taille), "adresse": txt(adr),
                   "description": txt(desc), "code_den": txt(cden),
                   "lot": txt(lot)}
    return out


def _vad_par_keyden(conn):
    """{keyden: [interviews VAD]} sur TOUTE la table : un ménage affecté dans
    le périmètre reste reconnu comme interviewé même si l'interview porte une
    zone mal saisie (la clé, elle, vient du préchargement)."""
    ag = {}
    for k, r in (_requete(conn, f'SELECT "interview__key", "responsible" '
                                f'FROM "{T_DIAG}"') or ()):
        ag.setdefault(txt(k), txt(r))
    out = defaultdict(list)
    for k, kd, st, d in (_requete(
            conn, f'SELECT "interview__key", "interview_keyden", '
                  f'"interview__status", "CQ3" FROM "{T_MEN}"') or ()):
        kd = txt(kd)
        if kd:
            out[kd].append({"key": txt(k), "agent": ag.get(txt(k), ""),
                            "statut": num(st), "date": jour(d)})
    return out


def _sec_couverture_agents(conn, menages, agent_code, noms, districts=None,
                           communes=None, fokontany=None):
    """Tableau de couverture par agent + reste à faire + doubles interviews.

    `agent_code` = {interview__key: code agent BRUT} (le préchargement porte
    des codes, pas des noms) ; `noms` sert seulement à l'affichage."""
    aff = _affectations(conn, districts, communes, fokontany)
    vad = _vad_par_keyden(conn)
    vide = {"dispo": False, "agents": [], "total": {}, "doubles": [],
            "statuts": STATUTS_COUV + (STATUT_AUTRE,)}
    doubles = _doubles(menages, vad, aff, noms)
    if not aff:
        return dict(vide, doubles=doubles)
    # Seuls les districts qui ONT un registre sont comparables : ailleurs,
    # toute interview passerait à tort pour « non affectée ».
    dis_reg = {a["district"] for a in aff.values()}
    cles_statut = [c for _s, c, _l in STATUTS_COUV] + [STATUT_AUTRE[1]]
    par = {}

    def ligne(code):
        p = par.get(code)
        if p is None:
            p = par[code] = {"code": code, "agent": noms.get(code, code),
                             "ce": "", "affectes": 0, "affInterviewes": 0,
                             "parAutre": 0, "reste": 0, "nonAffectes": 0,
                             "nonAffAutre": 0, "nonAffHors": 0,
                             "sansCle": 0, "resteListe": [],
                             **{c: 0 for c in cles_statut}}
        return p

    for kd, a in aff.items():
        code = a["enq"] or "(sans agent)"
        p = ligne(code)
        p["ce"] = p["ce"] or a["ce"]
        p["affectes"] += 1
        its = vad.get(kd, [])
        siens = [i for i in its if i["agent"] == a["enq"]]
        if siens:
            p["affInterviewes"] += 1
            best = min(siens, key=lambda i: _RANG_STATUT.get(i["statut"], 99))
            p[_cle_statut(best["statut"])] += 1
        elif its:
            p["parAutre"] += 1
        else:
            p["reste"] += 1
            p["resteListe"].append(a)
    # Interviews de l'agent HORS de sa liste (une fois par ménage), et
    # interviews sans clé : on ne sait pas à quel ménage dénombré elles
    # correspondent, elles ne couvrent donc personne.
    vus = defaultdict(set)
    hors_registre = 0
    for m in menages:
        code = agent_code.get(m["key"])
        if not code:
            continue
        if m["code_district"] not in dis_reg:
            hors_registre += 1
            continue
        kd = m["keyden"]
        if not kd:
            ligne(code)["sansCle"] += 1
            continue
        if (aff.get(kd) or {}).get("enq") == code or kd in vus[code]:
            continue
        vus[code].add(kd)
        p = ligne(code)
        p["nonAffectes"] += 1
        # Affecté à un AUTRE agent, ou absent du préchargement (ménage jamais
        # envoyé, ou envoyé par un fichier antérieur au registre).
        p["nonAffAutre" if kd in aff else "nonAffHors"] += 1
    chefs = equipes.agents_et_chefs(conn)
    agents = []
    for p in par.values():
        lien = chefs.get(p["code"]) or {}
        p["ce"] = (p["ce"] or lien.get("chef_login") or "")
        p["ceNom"] = lien.get("chef_nom") or p["ce"]
        p["couverture"] = _pct(p["affInterviewes"], p["affectes"])
        p["resteListe"].sort(key=lambda a: (a["fokontany_nom"], a["code_den"]))
        agents.append(p)
    # Le moins couvert d'abord (les agents sans affectation à la fin).
    agents.sort(key=lambda p: (p["couverture"] is None,
                               p["couverture"] or 0, -p["affectes"]))
    somme = lambda c: sum(p[c] for p in agents)
    total = {c: somme(c) for c in ("affectes", "affInterviewes", "parAutre",
                                   "reste", "nonAffectes", "nonAffAutre",
                                   "nonAffHors", "sansCle",
                                   *cles_statut)}
    total["couverture"] = _pct(total["affInterviewes"], total["affectes"])
    total["agents"] = len(agents)
    total["horsRegistre"] = hors_registre
    total["districts"] = sorted(d for d in dis_reg if d is not None)
    return {"dispo": True, "agents": agents, "total": total,
            "doubles": doubles, "statuts": STATUTS_COUV + (STATUT_AUTRE,)}


def _doubles(menages, vad, aff, noms):
    """Ménages (keyden) interviewés PLUSIEURS FOIS parmi ceux du périmètre.

    Au-delà de SEUIL_DOUBLON_DEN interviews, ce n'est plus une double visite
    mais un préchargement défectueux (une même clé distribuée à tort) : le
    verdict le dit, comme la règle `lien_den_douteux` du listing."""
    out = []
    for kd in sorted({m["keyden"] for m in menages if m["keyden"]}):
        its = vad.get(kd, [])
        if len(its) < 2:
            continue
        its = sorted(its, key=lambda i: (i["date"] or "", i["key"]))
        a = aff.get(kd) or {}
        out.append({
            "keyden": kd, "n": len(its),
            "verdict": ("Préchargement suspect" if len(its) > SEUIL_DOUBLON_DEN
                        else "Double interview"),
            "affecte": noms.get(a.get("enq"), a.get("enq") or ""),
            "agents": [noms.get(i["agent"], i["agent"]) or "?" for i in its],
            "dates": [i["date"] for i in its],
            "statuts": [i["statut"] for i in its],
            "cles": [i["key"] for i in its],
        })
    out.sort(key=lambda d: (-d["n"], d["keyden"]))
    return out


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Cache des agregats — mesure le 2026-09-28 : 255 ms de calcul par appel pour
# 228 menages. RSU-web tourne en UN SEUL processus : le GIL serialise ces
# calculs, ils sont donc le plafond de debit des pages lourdes. Les donnees ne
# bougent qu'aux transcriptions, pas entre deux clics.
# ---------------------------------------------------------------------------
CACHE_SECONDES = 60
_CACHE_AGREGE = {}
_CACHE_AGREGE_LOCK = threading.Lock()


def vider_cache() -> None:
    """Purge les agregats. Appele par `serveur_app._vider_cache()` apres TOUT
    changement de donnees : sans cela une transcription resterait invisible
    jusqu'a l'expiration."""
    with _CACHE_AGREGE_LOCK:
        _CACHE_AGREGE.clear()


def agrege(conn, districts=None, communes=None, portee_lib="", section="",
           cible=None, commune=None, fokontany=None) -> dict:
    """Agregats du tableau de bord VAD, avec cache de `CACHE_SECONDES`.

    Le perimetre fait PARTIE de la cle : deux utilisateurs de perimetres
    differents ne peuvent pas se voir servir le meme resultat.

    Le dictionnaire rendu est une COPIE DE SURFACE. `serveur_app` y ecrit
    `agg["agentSel"]` apres coup : sans cette copie, la selection d'un
    utilisateur fuirait vers les suivants — un bug invisible en test a un seul
    utilisateur, et systematique en production.
    """
    cle = (frozenset(districts) if districts else None,
           frozenset(communes) if communes else None,
           portee_lib, section, cible, commune, fokontany)
    maintenant = time.time()
    with _CACHE_AGREGE_LOCK:
        garde = _CACHE_AGREGE.get(cle)
        if garde is not None and maintenant - garde[0] < CACHE_SECONDES:
            return dict(garde[1])
    # Calcul HORS verrou : deux perimetres differents peuvent progresser en
    # parallele, et une requete lente ne bloque pas les lectures du cache.
    valeur = _agrege_calcul(conn, districts, communes, portee_lib, section,
                            cible, commune, fokontany)
    with _CACHE_AGREGE_LOCK:
        _CACHE_AGREGE[cle] = (maintenant, valeur)
    return dict(valeur)


def _agrege_calcul(conn, districts=None, communes=None, portee_lib="", section="",
                   cible=None, commune=None, fokontany=None) -> dict:
    """Tous les agrégats du tableau de bord VAD pour un périmètre.

    `section` évite un calcul lourd inutile : les tests de qualité (une
    trentaine de tests par agent) ne sont calculés que pour la section qui les
    affiche.

    `districts`/`communes` = le périmètre du RÔLE (ce à quoi l'utilisateur a
    droit) ; `commune`/`fokontany` = la DESCENTE demandée à l'intérieur, comme la
    carte du dénombrement. Le périmètre du rôle reste la borne : la descente est
    validée contre `vad_db.zones_disponibles()` avant d'arriver ici."""
    # Périmètre effectif = le plus fin des deux (la descente d'abord).
    communes_eff = {int(commune)} if commune else communes
    menages, membres = _lire(conn, districts, communes_eff, fokontany)
    diag = _diagnostics(conn, {m["key"] for m in menages})
    noms = {}
    try:
        import equipes
        noms = equipes.noms_agents(conn)
    except Exception:
        pass
    # Codes agent BRUTS (avant remplacement par le nom) : c'est sur eux que
    # portent les déclarations (`declaration_agent.code_agent`).
    codes_agents = {d["agent"] for d in diag.values() if d.get("agent")}
    agent_code = {k: d["agent"] for k, d in diag.items() if d.get("agent")}
    for d in diag.values():                       # nom de l'agent si renseigné
        d["agent"] = noms.get(d["agent"], d["agent"])
    rgph = _sec_rgph(conn, districts, communes_eff)
    return {
        "portee": {"libelle": portee_lib, "menages": len(menages),
                   "membres": len(membres)},
        "global": _sec_global(conn, menages, membres, diag, districts, communes_eff),
        "demographie": _sec_demographie(menages, membres),
        "rgph": rgph,
        # Couverture et comparaison RSU ↔ RGPH-3, commune par commune (feuille
        # « Global » du classeur Excel).
        "couvCommune": _couverture_communes(conn, menages, membres, rgph,
                                            districts, communes_eff),
        "listing": _sec_listing_erreurs(conn, districts, communes_eff, diag),
        "habitation": _sec_habitation(menages),
        "biens": _sec_biens(menages),
        "eau": _sec_eau(menages),
        # Sections thématiques ajoutées. Toutes travaillent sur les listes
        # déjà en mémoire — aucune relecture de la base —, elles coûtent donc
        # une fraction de seconde et sont calculées pour toutes les pages.
        "handicap": _sec_handicap(menages, membres),
        "identite": _sec_identite(menages, membres),
        "education": _sec_education(membres),
        "enfance": _sec_enfance(menages, membres),
        "activite": _sec_activite(menages, membres),
        "mobilite": _sec_mobilite(menages, membres),
        "ciblage": _sec_ciblage(menages),
        # Les zones proposées à la descente sont celles du périmètre du RÔLE
        # (pas de la descente en cours), sinon on ne pourrait plus remonter.
        "gps": dict(_sec_gps(menages, diag),
                    zones=(vad_db.zones_disponibles(conn, districts, communes)
                           if section == "gps" else []),
                    choix={"commune": int(commune) if commune else None,
                           "fokontany": int(fokontany) if fokontany else None}),
        # Conservé bien que plus affiché : la section « Listing d'erreurs » a
        # été remplacée par les deux listings du dofile (err_menage /
        # err_individu). Le calcul est peu coûteux et la donnée reste
        # disponible si l'on veut rétablir cette vue.
        "erreurs": _sec_erreurs(menages, membres, diag),
        "agents": _sec_agents(menages, membres, diag),
        # Couverture par agent (affectation du préchargement ↔ VAD) : lit tout
        # le registre et toute la VAD, donc seulement pour la page « Par agent »
        # et le classeur Excel (section « export »).
        "ecartDates": (_sec_ecart_dates(conn, menages, agent_code, noms)
                       if section == "export" else {"lignes": []}),
        "couverture": (_sec_couverture_agents(conn, menages, agent_code, noms,
                                              districts, communes_eff, fokontany)
                       if section in ("agents", "export")
                       else {"dispo": False, "agents": [], "total": {},
                             "doubles": []}),
        # Écart entre ce que l'agent DÉCLARE et ce qui ARRIVE AU SERVEUR.
        # Calculé au périmètre du RÔLE seulement (pas pendant une descente).
        "ecart": _sec_ecart_declaration(
            conn, menages, diag, codes_agents, noms,
            descente=bool(commune or fokontany)),
        "qualite": (vad_qualite.calculer(conn, districts, communes, cible)
                    if section == "qualite" else {"disponible": False}),
        # Qualité de l'EXPORT, pas de l'agent : confrontation au RGPH-3 et
        # contrôles de schéma, d'unicité et de complétude. Aussi coûteux que
        # la matrice par agent, donc calculé seulement quand on l'affiche.
        "qualite_base": (vad_qualite_base.calculer(conn, districts, communes)
                         if section == "qualite_base"
                         else {"disponible": False}),
    }
