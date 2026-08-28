#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rapport_core.py
===============

Moteur de generation du rapport HTML RSU 2026 (portage Python du dofile
`rapport_RSU.do`). Utilise le lecteur `.dta` maison `lire_dta` : aucune
dependance externe (ni pandas ni pyreadstat).

Fonction principale :
    generer_rapport(chemins, log)

    chemins : dict {'data', 'templates', 'rapport', 'limites'} (dossiers).
    log     : fonction (str)->None pour tracer l'avancement (facultatif).

Produit  : <rapport>/Rapport_RSU2026.html, assemble ainsi :
    template_head.html
    + const META = {...}
    + const MENAGES = [ ... ]        (1 objet par menage, roster)
    + const SEGMENTS_DEN = [ ... ]   (1 objet par ligne DEN_MENAGE)
    + const LIMITES = { ... }        (contours fokontany, LimitesFokontany/.../<num_fkt>.csv)
    + const LIMITES_COMMUNE = { ... }(contours commune, LimitesFokontany/.../<code_commune>.csv)
    + const LIMITES_DISTRICT = {...}(contours district, LimitesFokontany/<code_district>/<code_district>.csv)
    + template_tail.html

L'echappement JSON est gere par json.dumps() : contrairement au dofile Stata,
aucun nettoyage manuel de guillemets/apostrophes/antislash n'est necessaire
(voir CLAUDE.md §3.3 / §6).
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import zipfile
from datetime import datetime

from lire_dta import lire_dta


# ---------------------------------------------------------------------------
# Localisation des gabarits (templeteHtml) — INTERNE, non demande a l'utilisateur
# ---------------------------------------------------------------------------
# Les gabarits sont des fichiers de conception, figes : ils ne sont pas choisis
# par l'utilisateur. En exe PyInstaller, ils sont EMBARQUES dans le paquet et
# extraits dans sys._MEIPASS (donc caches / non modifiables). En script .py,
# on les lit dans le dossier templeteHtml/ situe a cote du script.
def dossier_templates() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "templeteHtml")  # type: ignore[attr-defined]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "templeteHtml")


# ---------------------------------------------------------------------------
# Localisation des assets (CSS + Chart.js) — allegement des pages du rapport
# ---------------------------------------------------------------------------
# Le CSS et la librairie de graphiques (Chart.js) sont sortis du gabarit dans
# assets/ pour que la page HTML servie reste LEGERE (le navigateur met en cache
# rapport.css et chart.umd.min.js). Chart.js est une COPIE LOCALE : les canvas
# s'affichent donc sans connexion internet. Deux modes a l'assemblage :
#   - assets_url fourni (web) : le head reference /assets/... (fichiers servis).
#   - assets_url absent (exe)  : le head EMBARQUE le contenu (fichier autonome).
def dossier_assets() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "assets")  # type: ignore[attr-defined]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _tete_assets(head: str, tpl_dir: str, assets_url):
    """Remplace les marqueurs <!--RSU_STYLES--> et <!--RSU_CHARTJS--> du head.

    assets_url (ex. "/assets") -> references externes (page legere, cache navigateur).
    None -> contenu embarque (fichier HTML autonome, comme l'exe).
    """
    assets_dir = os.path.join(os.path.dirname(tpl_dir), "assets")
    if not os.path.isdir(assets_dir):
        assets_dir = dossier_assets()
    css_path = os.path.join(assets_dir, "rapport.css")
    js_path = os.path.join(assets_dir, "chart.umd.min.js")

    if assets_url:
        base = assets_url.rstrip("/")
        styles = f'<link rel="stylesheet" href="{base}/rapport.css"/>'
        chartjs = f'<script src="{base}/chart.umd.min.js"></script>'
    else:
        # Mode autonome : on embarque le CSS et Chart.js dans le fichier.
        try:
            with open(css_path, "r", encoding="utf-8") as f:
                styles = "<style>\n" + f.read() + "\n</style>"
        except OSError:
            styles = ""  # gabarit sans CSS : mieux vaut une page nue qu'une erreur
        try:
            with open(js_path, "r", encoding="utf-8") as f:
                chartjs = "<script>\n" + f.read() + "\n</script>"
        except OSError:
            # Repli : Chart.js depuis le CDN (necessite alors une connexion).
            chartjs = ('<script src="https://cdn.jsdelivr.net/npm/'
                       'chart.js@4.4.0/dist/chart.umd.min.js"></script>')

    return head.replace("<!--RSU_STYLES-->", styles).replace(
        "<!--RSU_CHARTJS-->", chartjs)


# ---------------------------------------------------------------------------
# Localisation des limites (LimitesFokontany) — INTERNE, non demande a l'utilisateur
# ---------------------------------------------------------------------------
# Les contours district/commune/fokontany sont figes (issus du shapefile OCHA via
# la correspondance) : comme les gabarits, ils sont EMBARQUES dans l'exe et lus
# depuis sys._MEIPASS. En script .py, on les lit dans LimitesFokontany/ a cote du
# script. Ce dossier n'est donc plus demande ni distribue separement.
def dossier_limites() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "LimitesFokontany")  # type: ignore[attr-defined]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "LimitesFokontany")


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def _log_noop(_msg: str) -> None:
    pass


def parse_duree_cspro(duree_str) -> int | None:
    """Duree CSPro 'DD.HH:MM:SS' (ex '00.22:40:44') -> minutes (arrondi)."""
    if duree_str is None:
        return None
    try:
        s = str(duree_str).strip()
        if not s:
            return None
        jours, reste = s.split(".", 1)
        hh, mm, ss = reste.split(":")
        minutes = int(jours) * 1440 + int(hh) * 60 + int(mm) + int(ss) / 60
        return round(minutes)
    except Exception:
        return None


def _txt(v) -> str:
    """Valeur -> chaine propre ('' si None)."""
    return "" if v is None else str(v)


def _date_j(date_str) -> str:
    """'AAAA-MM-JJThh:mm:ss' -> 'AAAAMMJJ' (ou '' si invalide)."""
    s = _txt(date_str)
    if len(s) < 10:
        return ""
    j = s[0:4] + s[5:7] + s[8:10]
    return j if (len(j) == 8 and j.isdigit()) else ""


# ---------------------------------------------------------------------------
# Erreurs "métier" (messages clairs pour l'utilisateur, sans traceback)
# ---------------------------------------------------------------------------
class ErreurRapport(Exception):
    """Erreur prévue, à afficher telle quelle à l'utilisateur."""


class ErreurDonnees(ErreurRapport):
    """Fichier .dta manquant, illisible ou vide."""


class ErreurStructure(ErreurRapport):
    """Le .dta existe mais n'a pas les colonnes attendues."""


# Colonnes indispensables par fichier (pour détecter une base non conforme).
_REQUIS = {
    "interview__diagnostics.dta": [
        "interview__key", "responsible", "interview__status",
        "rejections__sup", "interview__duration",
    ],
    "DEN_MENAGE.dta": [
        "interview__key", "region", "district", "commune", "fokontany",
        "num_fkt", "segment", "assignment__id",
    ],
    "segment_roster.dta": [
        "interview__key", "nom_cmD", "code_den", "num_bat", "carnet",
        "presence", "indication", "taille_menD",
        "gps_coord__Latitude", "gps_coord__Longitude", "adresse", "date",
    ],
}


def _ouvrir(path: str):
    """Ouvre et VALIDE un .dta. Lève ErreurDonnees / ErreurStructure sinon."""
    nom = os.path.basename(path)
    if not os.path.isfile(path):
        raise ErreurDonnees(
            f"Fichier de données introuvable : {nom}.\n"
            f"Vérifiez que le dossier DATA contient bien ce fichier.")
    try:
        d = lire_dta(path)
    except ErreurRapport:
        raise
    except Exception as e:
        raise ErreurDonnees(
            f"Impossible de lire {nom} : le fichier est peut-être endommagé "
            f"ou n'est pas un fichier Stata .dta valide.\n"
            f"(détail technique : {type(e).__name__})")

    manquantes = [c for c in _REQUIS.get(nom, []) if c not in d.varnames]
    if manquantes:
        raise ErreurStructure(
            f"La structure de « {nom} » ne correspond pas à celle attendue.\n"
            f"Colonne(s) manquante(s) : {', '.join(manquantes)}.\n"
            f"Vérifiez que vous utilisez bien l'export de dénombrement RSU 2026.")
    return d


# ---------------------------------------------------------------------------
# 1. Diagnostics : agent, statut, rejets, duree (par interview__key)
# ---------------------------------------------------------------------------
def _charger_diagnostics(d, agents_noms=None) -> dict:
    """`agents_noms` (optionnel) : {code_agent: nom}. Si fourni, le code agent
    (`responsible`) est remplacé par le NOM de l'agent quand il est renseigné dans
    la table `agent` (nom != code) — le rapport affiche alors le nom au lieu du code.
    Absent (exe) : comportement inchangé (code brut)."""
    keys = d.col("interview__key")
    agent = d.col("responsible")
    statut = d.col("interview__status")
    rejet = d.col("rejections__sup")
    duree = d.col("interview__duration")
    noms = agents_noms or {}

    out: dict = {}
    for i, k in enumerate(keys):
        code = _txt(agent[i])
        out[k] = {
            "agent": noms.get(code, code),      # nom si renseigné, sinon le code
            "statut_seg": statut[i],
            "rejet": rejet[i] if rejet[i] is not None else 0,
            "duree_min": parse_duree_cspro(duree[i]),
        }
    return out


# ---------------------------------------------------------------------------
# 2. Segments (DEN_MENAGE) : zone geo decodee + fusion diagnostics
# ---------------------------------------------------------------------------
def _charger_segments(d, diag: dict):
    """Renvoie (seg_by_key, seg_liste) : index par interview__key + ordre DEN."""
    keys = d.col("interview__key")
    region = d.col_decoded("region")
    district = d.col_decoded("district")
    commune = d.col_decoded("commune")
    fokontany = d.col_decoded("fokontany")
    numfkt = d.col("num_fkt")
    segment = d.col("segment")
    assign = d.col("assignment__id")

    seg_by_key: dict = {}
    seg_liste: list = []
    for i, k in enumerate(keys):
        dd = diag.get(k, {})
        code = "" if numfkt[i] is None else str(numfkt[i])
        rec = {
            "region": _txt(region[i]),
            "district": _txt(district[i]),
            "commune": _txt(commune[i]),
            "fokontany": _txt(fokontany[i]),
            "num_fkt": numfkt[i],
            "fktcode": code,
            "segment": _txt(segment[i]),
            "assignment__id": assign[i],
            "agent": dd.get("agent", ""),
            "statut_seg": dd.get("statut_seg"),
            "rejet": dd.get("rejet", 0),
            "duree_min": dd.get("duree_min"),
        }
        seg_by_key[k] = rec
        seg_liste.append(rec)
    return seg_by_key, seg_liste


# ---------------------------------------------------------------------------
# 3. Menages (segment_roster) : niveau final -> objets MENAGES
# ---------------------------------------------------------------------------
def _construire_menages(d, seg_by_key: dict) -> list:
    keys = d.col("interview__key")
    nom_cmD = d.col("nom_cmD")
    surnom = d.col("surnom")
    code_den = d.col("code_den")
    num_bat = d.col("num_bat")
    carnet = d.col("carnet")
    presence = d.col("presence")
    indication = d.col("indication")
    taille = d.col("taille_menD")
    lat = d.col("gps_coord__Latitude")
    lon = d.col("gps_coord__Longitude")
    adresse = d.col("adresse")
    date = d.col("date")

    menages: list = []
    for i in range(d.nobs):
        s = seg_by_key.get(keys[i], {})

        nom = _txt(nom_cmD[i])
        if not nom.strip():
            nom = _txt(surnom[i])

        menages.append({
            "sid": s.get("assignment__id"),
            "id": _txt(code_den[i]),
            "nom": nom,
            "agent": s.get("agent", ""),
            "region": s.get("region", ""),
            "district": s.get("district", ""),
            "commune": s.get("commune", ""),
            "fkt": s.get("fokontany", ""),
            "fktcode": s.get("fktcode", ""),
            "seg": s.get("segment", ""),
            "bat": num_bat[i],
            "date": _date_j(date[i]),
            "carnet": carnet[i],
            "presence": presence[i],
            "elec": indication[i],
            "taille": taille[i],
            "lat": None if lat[i] is None else round(lat[i], 8),
            "lon": None if lon[i] is None else round(lon[i], 8),
            "adresse": _txt(adresse[i]),
            "tps": s.get("duree_min"),
            "statut": s.get("statut_seg"),
            "rejet": s.get("rejet", 0) or 0,
        })
    return menages


# ---------------------------------------------------------------------------
# 4. SEGMENTS_DEN : 1 objet par ligne DEN_MENAGE
# ---------------------------------------------------------------------------
def _construire_segments_den(seg_liste: list) -> list:
    return [{
        "fktcode": r["fktcode"],
        "seg": r["segment"],
        "agent": r["agent"],
        "commune": r["commune"],
    } for r in seg_liste]


# ---------------------------------------------------------------------------
# 5. AGREGATION SERVEUR (dashboard multi-pages allege)
# ---------------------------------------------------------------------------
# Pour les periodes district/commune, la page n'affiche que des AGREGATS : on les
# calcule ici cote serveur pour ne PAS embarquer les dizaines de milliers de
# menages bruts (page 100x plus legere, meme rendu). Les formules ci-dessous sont
# la COPIE FIDELE de celles du gabarit (template_tail.html) — un test
# d'equivalence (test_agrege.py) verifie champ par champ l'egalite avec le JS.
def _js_round(x: float) -> int:
    """Math.round de JavaScript (arrondit .5 vers le HAUT), != round() de Python."""
    return int(math.floor(x + 0.5))


def _avg(vals) -> int:
    vals = list(vals)
    return _js_round(sum(vals) / len(vals)) if vals else 0


def _pct(n, t) -> int:
    return _js_round(n / t * 100) if t else 0


def _valid_date(d) -> bool:
    return isinstance(d, str) and bool(re.fullmatch(r"\d{8}", d))


def _has_carnet(m) -> bool:
    return m["carnet"] == 1 or m["carnet"] == 2


def _commune_of(m) -> str:
    c = m.get("commune")
    return c if (isinstance(c, str) and c.strip()) else "(commune inconnue)"


def _fkt_key(m) -> str:
    return m.get("fktcode") or m.get("fkt") or ""


def _segments_agg(menages: list) -> list:
    """Agrege les menages en segments par couple (sid x fokontany) — meme cle et
    meme « premier vu » que le JS (template_tail.html l.81-97)."""
    seg_map: dict = {}
    ordre: list = []
    for m in menages:
        fc = _fkt_key(m)
        key = (m.get("sid"), fc)
        s = seg_map.get(key)
        if s is None:
            s = {"sid": m.get("sid"), "agent": m.get("agent", ""),
                 "region": m.get("region", ""), "district": m.get("district", ""),
                 "commune": _commune_of(m), "fkt": m.get("fkt", ""), "fktcode": fc,
                 "seg": m.get("seg", ""), "statut": m.get("statut"),
                 "rejet": m.get("rejet", 0), "tps": m.get("tps"),
                 "n": 0, "nPresent": 0, "nCarnet": 0, "_bats": set()}
            seg_map[key] = s
            ordre.append(key)
        s["n"] += 1
        if m.get("presence") == 1:
            s["nPresent"] += 1
        if _has_carnet(m):
            s["nCarnet"] += 1
        if m.get("bat"):
            s["_bats"].add(m.get("bat"))
    segs = []
    for key in ordre:
        s = seg_map[key]
        s["batsN"] = len(s.pop("_bats"))
        segs.append(s)
    return segs


def agrege(menages: list, segments: list = None) -> dict:
    """Calcule TOUS les agregats d'un perimetre (district/commune), a l'identique
    du gabarit. Renvoie {"segments": [...], "summary": {...}}.

    `segments` : sortie de _segments_agg (recalculee si absente)."""
    if segments is None:
        segments = _segments_agg(menages)

    total = len(menages)
    # Dates valides triees (isValidDate + tri lexicographique comme en JS).
    dates = sorted({m["date"] for m in menages if _valid_date(m.get("date"))})

    # -- General --
    nb_presents = sum(1 for m in menages if m.get("presence") == 1)
    nb_carnet = sum(1 for m in menages if _has_carnet(m))
    tps_seg = [s["tps"] for s in segments if (s["tps"] or 0) > 0]
    nb_bat = len({(m.get("sid"), m.get("bat")) for m in menages})
    agents_actifs = sorted({m["agent"] for m in menages if m.get("agent")})
    daily = [{"d": d,
              "total": sum(1 for m in menages if m.get("date") == d),
              "present": sum(1 for m in menages
                             if m.get("date") == d and m.get("presence") == 1)}
             for d in dates]
    agents_per_day = [{"d": d,
                       "n": len({m["agent"] for m in menages
                                 if m.get("date") == d and m.get("agent")})}
                      for d in dates]
    general = {
        "total": total,
        "nbPresents": nb_presents,
        "nbCarnet": nb_carnet,
        "nbSegments": len(segments),
        "nbBat": nb_bat,
        "tps": _avg(tps_seg),
        "nAgents": len(agents_actifs),
        "dates": dates,
        "daily": daily,
        "agentsPerDay": agents_per_day,
        "presence": [nb_presents, sum(1 for m in menages if m.get("presence") == 2)],
        "carnet": [sum(1 for m in menages if m.get("carnet") == c) for c in (1, 2, 3, 4)],
    }

    # -- Taux de capture GPS (hasGps = lat ET lon des nombres finis) --
    def _has_gps(m):
        la, lo = m.get("lat"), m.get("lon")
        return (isinstance(la, (int, float)) and math.isfinite(la)
                and isinstance(lo, (int, float)) and math.isfinite(lo))
    ok = sum(1 for m in menages if _has_gps(m))
    gpscap = {"total": total, "ok": ok, "ko": total - ok}

    # -- Qualite --
    tailles = [m["taille"] for m in menages if (m.get("taille") or 0) > 0]
    max_t = min(max(tailles) if tailles else 0, 15)
    bins = []
    for b in range(1, max_t + 1):
        cnt = (sum(1 for t in tailles if t >= b) if b == max_t
               else sum(1 for t in tailles if t == b))
        bins.append({"b": b, "count": cnt, "last": b == max_t})
    nb_gps_lat = sum(1 for m in menages
                     if m.get("lat") and abs(m["lat"]) < 90)   # qualite : lat seule
    qualite = {
        "carnet": general["carnet"],
        "presence": general["presence"],
        "elec": [sum(1 for m in menages if m.get("elec") == 1),
                 sum(1 for m in menages if m.get("elec") == 2)],
        "statut": [sum(1 for s in segments if s["statut"] == 120),
                   sum(1 for s in segments if s["statut"] != 120)],
        "gps": [nb_gps_lat, total - nb_gps_lat],
        "taille": {"maxT": max_t, "bins": bins},
    }

    # -- Historique --
    hist_rows = []
    for d in dates:
        ms_d = [m for m in menages if m.get("date") == d]
        sids = {m.get("sid") for m in ms_d}
        hist_rows.append({
            "d": d,
            "menages": len(ms_d),
            "segments": len(sids),
            "agents": len({m.get("agent") for m in ms_d}),
            "tps": _avg([s["tps"] for s in segments
                         if s["sid"] in sids and (s["tps"] or 0) > 0]),
        })
    historique = {
        "dates": dates,
        "perDate": hist_rows,
        "kpis": {"jours": len(dates),
                 "first": dates[0] if dates else None,
                 "last": dates[-1] if dates else None,
                 "moy": _avg([r["menages"] for r in hist_rows])},
    }

    # -- Par agent (recap) --
    agents = []
    for a in agents_actifs:
        am = [m for m in menages if m.get("agent") == a]
        asg = [s for s in segments if s["agent"] == a]
        agents.append({
            "agent": a, "n": len(am), "nSeg": len(asg),
            "nPresent": sum(1 for m in am if m.get("presence") == 1),
            "nCarnet": sum(1 for m in am if _has_carnet(m)),
            "presPct": _pct(sum(1 for m in am if m.get("presence") == 1), len(am)),
            "carnPct": _pct(sum(1 for m in am if _has_carnet(m)), len(am)),
            "tps": _avg([s["tps"] for s in asg if (s["tps"] or 0) > 0]),
        })

    return {
        "segments": segments,
        "summary": {
            "general": general,
            "gpscap": gpscap,
            "qualite": qualite,
            "historique": historique,
            "agents": agents,
        },
    }


# ---------------------------------------------------------------------------
# 5bis. COUVERTURE : denombrement realise vs projection menages RGPH-3 2025
# ---------------------------------------------------------------------------
def couverture(menages: list, attendus: dict, niveau: str = "district") -> dict:
    """Indicateurs de couverture du denombrement par rapport au nombre de menages
    attendus (projection RGPH-3 2025, colonne commune.nombreMenage).

    `attendus` : { code_commune(str 6) : {"nom": str, "attendu": int|None} } pour
    toutes les communes du perimetre.
    Rythme = menages realises / jours travailles observes (moyenne GLOBALE, choix
    utilisateur). jours_restants = ceil(menages_restants / rythme) si < 100 %,
    sinon 0 (denombrement fiable). None si le rythme est inconnu (0 realise/0 jour).
    """
    def _jr(restant, rythme):
        if restant <= 0:
            return 0
        if not rythme or rythme <= 0:
            return None
        return int(math.ceil(restant / rythme))

    # Realise et jours travailles PAR commune (code = fktcode[:6]).
    real, jours = {}, {}
    for m in menages:
        fc = m.get("fktcode") or ""
        cc = fc[:6] if len(fc) >= 6 else ""
        if not cc:
            continue
        real[cc] = real.get(cc, 0) + 1
        if _valid_date(m.get("date")):
            jours.setdefault(cc, set()).add(m["date"])

    total_real = len(menages)
    total_jours = len({m["date"] for m in menages if _valid_date(m.get("date"))})
    total_attendu = sum((v.get("attendu") or 0) for v in attendus.values())
    rythme = (total_real / total_jours) if total_jours else 0.0
    restant = max(0, total_attendu - total_real)
    pct = (100.0 * total_real / total_attendu) if total_attendu else None
    fiable = (pct is not None and pct >= 100)

    communes = []
    for cc, info in attendus.items():
        a = info.get("attendu") or 0
        r = real.get(cc, 0)
        j = len(jours.get(cc, ()))
        ry = (r / j) if j else 0.0
        communes.append({
            "code": cc,
            "nom": info.get("nom", cc),
            "attendu": a,
            "realise": r,
            "pct": (100.0 * r / a) if a else None,
            "joursTravailles": j,
            "joursRestants": (0 if (a and r >= a) else (_jr(max(0, a - r), ry)
                                                        if a else None)),
        })
    # Communes les plus en retard d'abord (taux croissant ; None = non commence).
    communes.sort(key=lambda x: (x["pct"] if x["pct"] is not None else -1.0,
                                 x["nom"]))
    return {
        "niveau": niveau,
        "attendu": total_attendu,
        "realise": total_real,
        "pct": pct,
        "fiable": fiable,
        "joursTravailles": total_jours,
        "rythme": rythme,
        "menagesRestants": restant,
        "joursRestants": (0 if fiable else _jr(restant, rythme)),
        "communes": communes,
    }


# ---------------------------------------------------------------------------
# 5. LIMITES : contours des fokontany (CSV -> anneaux [[lat,lon],...])
# ---------------------------------------------------------------------------
def _parser_contour(lignes) -> list:
    """Itérable de lignes 'part,seq,lon,lat' -> anneaux [[lat,lon],...] (WGS84)."""
    rings: list = []
    cur: list | None = None
    curpart = None
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        champs = ligne.split(",")
        if len(champs) < 4:
            continue
        try:
            part = int(champs[0])
        except ValueError:
            continue  # ligne d'en-tete "part,seq,lon,lat"
        try:
            lon = float(champs[2])
            lat = float(champs[3])
        except ValueError:
            continue
        if part != curpart:
            cur = []
            rings.append(cur)
            curpart = part
        cur.append([lat, lon])
    return rings


class _SourceLimites:
    """Accès aux CSV de contours par chemin relatif ('d/c/f.csv'), depuis soit un
    DOSSIER LimitesFokontany/ (développement), soit un ZIP LimitesFokontany.zip
    embarqué dans l'exe (bien plus rapide à extraire qu'un dossier de ~19 000
    fichiers). On lit un zip -> pas d'extraction disque, accès indexé."""
    def __init__(self, dossier: str):
        self._dir = None
        self._zip = None
        if dossier and os.path.isdir(dossier):
            self._dir = dossier
        else:
            zpath = (dossier or "") + ".zip"
            if os.path.isfile(zpath):
                self._zip = zipfile.ZipFile(zpath)

    def rings(self, relpath: str):
        """relpath en '/' (ex. '1403/140301/14030101.csv') -> anneaux, ou None."""
        if self._dir is not None:
            p = os.path.join(self._dir, *relpath.split("/"))
            if not os.path.isfile(p):
                return None
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return _parser_contour(f)
        if self._zip is not None:
            try:
                data = self._zip.read(relpath)
            except KeyError:
                return None
            return _parser_contour(data.decode("utf-8", "replace").splitlines())
        return None

    def close(self):
        if self._zip is not None:
            self._zip.close()


def _construire_limites(seg_liste: list, source: "_SourceLimites", log) -> dict:
    codes = sorted({r["fktcode"] for r in seg_liste if r["fktcode"]})
    limites: dict = {}
    trouves = 0
    for code in codes:
        rings = source.rings(f"{code[:4]}/{code[:6]}/{code}.csv")
        if rings:
            limites[code] = rings
            trouves += 1
    log(f"   contours trouves : {trouves} / {len(codes)} fokontany")
    return limites


def _construire_limites_commune(seg_liste: list, source: "_SourceLimites", log) -> dict:
    """Contours de commune : CSV nommé par le code commune (6 premiers chiffres du
    num_fkt) dans LimitesFokontany/<district(4)>/<commune(6)>/<commune(6)>.csv."""
    codes = sorted({r["fktcode"][:6] for r in seg_liste
                    if r["fktcode"] and len(r["fktcode"]) >= 6})
    limites: dict = {}
    trouves = 0
    for code in codes:
        rings = source.rings(f"{code[:4]}/{code}/{code}.csv")
        if rings:
            limites[code] = rings
            trouves += 1
    log(f"   contours communes  : {trouves} / {len(codes)} communes")
    return limites


def _construire_limites_district(seg_liste: list, source: "_SourceLimites", log) -> dict:
    """Contours de district : CSV nommé par le code district (4 premiers chiffres
    du num_fkt) dans LimitesFokontany/<district(4)>/<district(4)>.csv."""
    codes = sorted({r["fktcode"][:4] for r in seg_liste
                    if r["fktcode"] and len(r["fktcode"]) >= 4})
    limites: dict = {}
    trouves = 0
    for code in codes:
        rings = source.rings(f"{code}/{code}.csv")
        if rings:
            limites[code] = rings
            trouves += 1
    log(f"   contours districts : {trouves} / {len(codes)} districts")
    return limites


def _limites_integrees(seg_liste: list, limites_dir: str, log) -> tuple:
    """Mode 1 : contours OCHA 2018 embarques (dossier/zip LimitesFokontany)."""
    source = _SourceLimites(limites_dir)
    fkt = _construire_limites(seg_liste, source, log)
    com = _construire_limites_commune(seg_liste, source, log)
    dis = _construire_limites_district(seg_liste, source, log)
    source.close()
    return fkt, com, dis


# ---------------------------------------------------------------------------
# 5b. LIMITES — Mode AUTO : enveloppe convexe des points GPS des menages
# ---------------------------------------------------------------------------
# Aucune donnee externe : on calcule, pour chaque fokontany / commune / district,
# le contour (enveloppe convexe) entourant les positions GPS reelles des menages
# denombres. Hors-ligne, sans dependance. Souvent plus fidele qu'OCHA 2018 pour
# les fokontany recents absents du shapefile (voir CLAUDE.md 5.6).
def _enveloppe_convexe(points: list) -> list:
    """Monotone chain (Andrew). points = [(x, y), ...] -> sommets du contour
    en (x, y), sens anti-horaire, sans repetition du premier point."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts[:]                       # degenere (0/1/2 points distincts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    bas = []
    for p in pts:
        while len(bas) >= 2 and cross(bas[-2], bas[-1], p) <= 0:
            bas.pop()
        bas.append(p)
    haut = []
    for p in reversed(pts):
        while len(haut) >= 2 and cross(haut[-2], haut[-1], p) <= 0:
            haut.pop()
        haut.append(p)
    return bas[:-1] + haut[:-1]


def _coord_valide(la, lo) -> bool:
    return (isinstance(la, (int, float)) and isinstance(lo, (int, float))
            and abs(la) < 90 and abs(lo) < 180 and (la != 0 or lo != 0))


def _limites_auto(menages: list, log) -> tuple:
    """Mode 2 : contours generes = enveloppe convexe des menages geolocalises."""
    fkt_pts: dict = {}
    com_pts: dict = {}
    dis_pts: dict = {}
    for m in menages:
        code = m.get("fktcode") or ""
        la, lo = m.get("lat"), m.get("lon")
        if not code or not _coord_valide(la, lo):
            continue
        p = (lo, la)                        # (x=lon, y=lat)
        fkt_pts.setdefault(code, []).append(p)
        if len(code) >= 6:
            com_pts.setdefault(code[:6], []).append(p)
        if len(code) >= 4:
            dis_pts.setdefault(code[:4], []).append(p)

    def _hulls(groupes: dict) -> dict:
        out: dict = {}
        for code, pts in groupes.items():
            h = _enveloppe_convexe(pts)
            if len(h) >= 3:
                ring = [[y, x] for (x, y) in h]   # (x=lon, y=lat) -> [lat, lon]
                ring.append(ring[0])              # fermer l'anneau
                out[code] = [ring]
        return out

    fkt, com, dis = _hulls(fkt_pts), _hulls(com_pts), _hulls(dis_pts)
    log(f"   contours generes (enveloppe des menages) : "
        f"{len(fkt)} fokontany, {len(com)} communes, {len(dis)} districts")
    return fkt, com, dis


# ---------------------------------------------------------------------------
# 5c. LIMITES — Mode DOSSIER : limites fournies par l'utilisateur (CSV / JSON)
# ---------------------------------------------------------------------------
# L'utilisateur donne un dossier ; on l'explore (recursif) et on indexe chaque
# fichier .csv / .json / .geojson par le CODE du fokontany (ou commune/district).
#   • Nom de fichier = code (ex. 44050604.csv, 440506.json) -> rattachement direct.
#   • GeoJSON FeatureCollection : chaque entite est rattachee via une propriete de
#     code (num_fkt, code, fktcode, cod_fkt...) si presente.
# Les coordonnees sont normalisees en [lat, lon] via les bornes de Madagascar,
# donc l'ordre lon/lat des fichiers importe peu.
_CLES_CODE = ("num_fkt", "numfkt", "fktcode", "code_fkt", "codefkt", "cod_fkt",
              "code", "cod", "pcode", "id")


def _en_latlon(a, b):
    """Deux nombres (ordre inconnu) -> [lat, lon], detecte via bornes Madagascar.
    Par defaut (hors bornes) suppose l'ordre GeoJSON/CSV interne (lon, lat)."""
    try:
        a = float(a); b = float(b)
    except (TypeError, ValueError):
        return None
    lat_ok = lambda v: -26.5 <= v <= -11.0
    lon_ok = lambda v: 42.0 <= v <= 51.5
    if lat_ok(a) and lon_ok(b):
        return [a, b]
    if lat_ok(b) and lon_ok(a):
        return [b, a]
    return [b, a]                           # suppose (a, b) = (lon, lat)


def _parser_contour_souple(lignes) -> list:
    """CSV tolerant : accepte 'part,seq,lon,lat' (format interne) ou 2 colonnes
    'lon,lat'/'lat,lon'. Renvoie des anneaux [[lat, lon], ...]."""
    rings: list = []
    cur = None
    curpart = None
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        champs = [c.strip() for c in ligne.replace(";", ",").split(",")]
        nums = []
        for c in champs:
            try:
                nums.append(float(c))
            except ValueError:
                nums.append(None)
        if all(n is None for n in nums):
            continue                        # ligne d'en-tete
        if (len(nums) >= 4 and nums[0] is not None
                and nums[2] is not None and nums[3] is not None
                and float(nums[0]).is_integer()):
            part = int(nums[0])
            latlon = _en_latlon(nums[2], nums[3])
        else:
            coords = [n for n in nums if n is not None]
            if len(coords) < 2:
                continue
            part = 0
            latlon = _en_latlon(coords[-2], coords[-1])
        if latlon is None:
            continue
        if part != curpart:
            cur = []
            rings.append(cur)
            curpart = part
        cur.append(latlon)
    return [r for r in rings if len(r) >= 3]


def _anneaux_depuis_polygon(coords) -> list:
    rings = []
    if not isinstance(coords, list):
        return rings
    for anneau in coords:
        r = []
        if isinstance(anneau, list):
            for pt in anneau:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    ll = _en_latlon(pt[0], pt[1])
                    if ll is not None:
                        r.append(ll)
        if len(r) >= 3:
            rings.append(r)
    return rings


def _geom_en_anneaux(geom) -> list:
    if not isinstance(geom, dict):
        return []
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Polygon":
        return _anneaux_depuis_polygon(c)
    if t == "MultiPolygon":
        out = []
        for poly in (c or []):
            out.extend(_anneaux_depuis_polygon(poly))
        return out
    return []


def _geojson_en_anneaux(obj) -> list:
    """Objet nomme par le fichier -> anneaux fusionnes (Polygon/MultiPolygon/
    Feature/FeatureCollection), ou tableau d'anneaux [[[lat,lon],...],...]."""
    if isinstance(obj, list):
        return _anneaux_depuis_polygon(obj)
    if not isinstance(obj, dict):
        return []
    t = obj.get("type")
    if t in ("Polygon", "MultiPolygon"):
        return _geom_en_anneaux(obj)
    if t == "Feature":
        return _geom_en_anneaux(obj.get("geometry"))
    if t == "FeatureCollection":
        out = []
        for feat in obj.get("features", []):
            out.extend(_geom_en_anneaux((feat or {}).get("geometry")))
        return out
    return []


def _code_de_proprietes(props: dict):
    if not isinstance(props, dict):
        return None
    bas = {str(k).lower(): v for k, v in props.items()}
    for cle in _CLES_CODE:
        if cle in bas and bas[cle] not in (None, ""):
            return str(bas[cle]).strip()
    return None


def _lire_fichier_limite(chemin: str):
    """Un fichier .csv / .json / .geojson -> anneaux [[lat,lon],...], ou None."""
    ext = os.path.splitext(chemin)[1].lower()
    try:
        if ext == ".csv":
            with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                rings = _parser_contour_souple(f)
        else:
            with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                rings = _geojson_en_anneaux(json.load(f))
    except Exception:
        return None
    return rings or None


def _lire_hierarchie(user_dir: str, relbase: str):
    """Cherche <user_dir>/<relbase>.csv|.json|.geojson (structure identique à
    LimitesFokontany) et renvoie ses anneaux, ou None."""
    for ext in (".csv", ".json", ".geojson"):
        p = os.path.join(user_dir, *(relbase + ext).split("/"))
        if os.path.isfile(p):
            rings = _lire_fichier_limite(p)
            if rings:
                return rings
    return None


def _indexer_limites_utilisateur(user_dir: str, log) -> dict:
    """Repli : explore TOUT le dossier -> {code(str): anneaux}. Le code vient du
    NOM de fichier (dossier à plat) ou d'une propriété (GeoJSON multi-entités)."""
    index: dict = {}
    n_fichiers = 0
    for racine, _dirs, fichiers in os.walk(user_dir):
        for fn in fichiers:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in (".csv", ".json", ".geojson"):
                continue
            n_fichiers += 1
            chemin = os.path.join(racine, fn)
            stem = os.path.splitext(fn)[0].strip()
            rings = _lire_fichier_limite(chemin)
            if rings:
                index.setdefault(stem, rings)
            # GeoJSON FeatureCollection : rattachement par propriete de code.
            if ext in (".json", ".geojson"):
                try:
                    with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                        obj = json.load(f)
                except Exception:
                    obj = None
                if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
                    for feat in obj.get("features", []):
                        feat = feat or {}
                        code = _code_de_proprietes(feat.get("properties"))
                        r = _geom_en_anneaux(feat.get("geometry"))
                        if code and r:
                            index.setdefault(code, r)
    log(f"   (repli) {n_fichiers} fichier(s) explorés, {len(index)} code(s) indexés")
    return index


def _limites_dossier(seg_liste: list, user_dir: str, log) -> tuple:
    """Mode 3 : contours fournis par l'utilisateur, rattachés par code (num_fkt
    exact ; commune = 6 premiers chiffres ; district = 4 premiers).

    Structure RECOMMANDÉE = la même que LimitesFokontany (lecture ciblée, rapide) :
        <district(4)>/<commune(6)>/<num_fkt>.csv      (fokontany)
        <district(4)>/<commune(6)>/<commune(6)>.csv   (commune)
        <district(4)>/<district(4)>.csv               (district)
    Chaque .csv peut être remplacé par .json/.geojson. En repli, un dossier à plat
    (fichiers nommés par code) ou un GeoJSON multi-entités (propriété de code) est
    aussi accepté."""
    if not user_dir or not os.path.isdir(user_dir):
        raise ErreurDonnees(
            "Le dossier de limites indiqué est introuvable :\n"
            f"{user_dir}\nVérifiez le chemin, ou choisissez un autre mode de limites.")

    codes_fkt = sorted({r["fktcode"] for r in seg_liste if r["fktcode"]})
    codes_com = sorted({r["fktcode"][:6] for r in seg_liste
                        if r["fktcode"] and len(r["fktcode"]) >= 6})
    codes_dis = sorted({r["fktcode"][:4] for r in seg_liste
                        if r["fktcode"] and len(r["fktcode"]) >= 4})

    # 1) Structure hiérarchique (comme LimitesFokontany) : on ne lit que le
    #    fichier attendu pour chaque code -> rapide même sur un gros jeu.
    fkt, com, dis = {}, {}, {}
    for code in codes_fkt:
        r = _lire_hierarchie(user_dir, f"{code[:4]}/{code[:6]}/{code}")
        if r:
            fkt[code] = r
    for code in codes_com:
        r = _lire_hierarchie(user_dir, f"{code[:4]}/{code}/{code}")
        if r:
            com[code] = r
    for code in codes_dis:
        r = _lire_hierarchie(user_dir, f"{code}/{code}")
        if r:
            dis[code] = r

    # 2) Repli SEULEMENT si la hiérarchie n'a rien donné (l'utilisateur a un
    #    dossier à plat ou un GeoJSON multi-entités) : on évite un parcours complet
    #    et coûteux quand la structure hiérarchique est déjà en place.
    if not (fkt or com or dis):
        index = _indexer_limites_utilisateur(user_dir, log)
        for code in codes_fkt:
            if code not in fkt and code in index:
                fkt[code] = index[code]
        for code in codes_com:
            if code not in com and code in index:
                com[code] = index[code]
        for code in codes_dis:
            if code not in dis and code in index:
                dis[code] = index[code]

    log(f"   contours utilisateur rattachés : {len(fkt)}/{len(codes_fkt)} fokontany, "
        f"{len(com)}/{len(codes_com)} communes, {len(dis)}/{len(codes_dis)} districts")
    if not (fkt or com or dis):
        raise ErreurDonnees(
            "Aucune limite exploitable trouvée dans :\n" f"{user_dir}\n\n"
            "Organisez le dossier comme LimitesFokontany :\n"
            "  <district(4 chiffres)>/<commune(6)>/<num_fkt>.csv\n"
            "(ou .json/.geojson). Un dossier à plat avec des fichiers nommés par le "
            "num_fkt (ex. 44050604.csv), ou un GeoJSON avec une propriété de code, "
            "sont aussi acceptés.")
    return fkt, com, dis


# ---------------------------------------------------------------------------
# 6. Date du rapport (date max observee -> JJ/MM/AAAA)
# ---------------------------------------------------------------------------
def _date_rapport(menages: list) -> str:
    dates = [m["date"] for m in menages if m["date"]]
    if not dates:
        return datetime.today().strftime("%d/%m/%Y")
    d = max(dates)
    return f"{d[6:8]}/{d[4:6]}/{d[0:4]}"


# ---------------------------------------------------------------------------
# 7. Assemblage HTML
# ---------------------------------------------------------------------------
def generer_rapport(chemins: dict, log=None, source=None,
                    codes_geo=None, autoriser_vide=False, zones_ref=None,
                    assets_url=None, section=None, scope=None,
                    nav_tree=None, alleger=False, nav_base="/vue",
                    agents_noms=None, menages_attendus=None,
                    contours_override=None) -> str:
    """Genere le rapport HTML. Renvoie le chemin du fichier produit.

    `source` (optionnel) : resolveur kind -> dataset, ou kind est
    "diagnostics"/"den"/"roster". S'il est fourni, les donnees viennent de cette
    source (ex. base SQL via db_source.source_db) au lieu des .dta du dossier
    DATA. Le dataset renvoye doit exposer .nobs/.varnames/.col/.col_decoded
    (meme interface que lire_dta.Dta). L'assemblage du rapport est identique.

    `autoriser_vide` (optionnel, defaut False) : si True, un jeu de donnees vide
    (0 segment / 0 menage) ne leve plus d'erreur mais produit un rapport avec
    toutes les sections VIDES. Utile au web pour un district sans donnees.

    `codes_geo` (optionnel) : iterable de codes fokontany (8 chiffres) dont on
    veut TOUJOURS afficher les contours sur la carte, meme sans menage denombre
    (mode « suivi par district » : la carte montre les limites du district
    choisi). N'affecte que les contours OCHA/dossier, pas les donnees.

    `zones_ref` (optionnel) : liste de reference des unites du district issue du
    referentiel `zones` (complet) — [{"fkt","label","commune","ccode"}, ...].
    Ecrite dans le rapport comme `const ZONES_REF`; le gabarit fusionne ces
    communes/fokontany dans sa hierarchie pour afficher TOUTES les unites du
    district (meme sans donnees), afin de reperer les zones oubliees. Sans elle,
    le gabarit se comporte comme avant (rapport exe : ZONES_REF non defini).

    `contours_override` (optionnel) : dict {"fkt", "commune", "district"} de
    contours {code(str): anneaux} qui REMPLACENT ceux du mode choisi pour les
    codes fournis (limites corrigees de certains districts, cf. limites_db.py).
    Defaut None -> comportement inchange (exe non concerne).
    """
    log = log or _log_noop

    rapport_dir = chemins["rapport"]
    # Limites et gabarits : internes (embarques dans l'exe) sauf override explicite
    # via chemins (utile pour regenerer les CSV en developpement).
    limites_dir = chemins.get("limites") or dossier_limites()
    tpl_dir = chemins.get("templates") or dossier_templates()

    head_path = os.path.join(tpl_dir, "template_head.html")
    tail_path = os.path.join(tpl_dir, "template_tail.html")
    out_path = os.path.join(rapport_dir, "Rapport_RSU2026.html")

    for p in (head_path, tail_path):
        if not os.path.isfile(p):
            raise ErreurRapport(
                "Gabarits du rapport introuvables. L'application est peut-être "
                "endommagée : réinstallez RapportRSU.")

    # Source des donnees : soit les .dta (defaut), soit un resolveur injecte.
    if source is None:
        data_dir = chemins["data"]
        if not os.path.isdir(data_dir):
            raise ErreurDonnees(
                f"Le dossier DATA est introuvable :\n{data_dir}\n"
                f"Sélectionnez le dossier contenant les fichiers .dta.")
        den_path = os.path.join(data_dir, "DEN_MENAGE.dta")
        roster_path = os.path.join(data_dir, "segment_roster.dta")
        diag_path = os.path.join(data_dir, "interview__diagnostics.dta")
        ouvrir_diag = lambda: _ouvrir(diag_path)
        ouvrir_den = lambda: _ouvrir(den_path)
        ouvrir_ros = lambda: _ouvrir(roster_path)
    else:
        ouvrir_diag = lambda: source("diagnostics")
        ouvrir_den = lambda: source("den")
        ouvrir_ros = lambda: source("roster")

    log("[1/6] Lecture des diagnostics (agent, duree, statut)…")
    diag_d = ouvrir_diag()
    diag = _charger_diagnostics(diag_d, agents_noms)

    log("[2/6] Lecture des segments (DEN_MENAGE) + fusion…")
    den_d = ouvrir_den()
    if den_d.nobs == 0 and not autoriser_vide:
        raise ErreurDonnees(
            "Le fichier DEN_MENAGE.dta ne contient aucun segment : "
            "il n'y a rien à générer.")
    seg_by_key, seg_liste = _charger_segments(den_d, diag)
    log(f"   {len(seg_liste)} segments (lignes DEN_MENAGE)")

    log("[3/6] Lecture des menages (segment_roster) + fusion…")
    ros_d = ouvrir_ros()
    if ros_d.nobs == 0 and not autoriser_vide:
        raise ErreurDonnees(
            "Le fichier segment_roster.dta ne contient aucun ménage : "
            "il n'y a rien à générer.")
    menages = _construire_menages(ros_d, seg_by_key)
    log(f"   {len(menages)} menages")

    log("[4/6] Construction de SEGMENTS_DEN…")
    segments_den = _construire_segments_den(seg_liste)

    # Contours (carte) : en plus des fokontany présents dans les ménages, on peut
    # forcer ceux d'une zone via `codes_geo` — pour afficher les limites d'un
    # district même sans ménage dénombré (mode web « suivi par district »).
    seg_liste_lim = seg_liste
    if codes_geo:
        deja = {r["fktcode"] for r in seg_liste if r.get("fktcode")}
        extra = [{"fktcode": str(c)} for c in codes_geo if str(c) not in deja]
        seg_liste_lim = seg_liste + extra

    mode_lim = (chemins.get("limites_mode") or "integrees").strip().lower()
    user_lim = chemins.get("limites_dossier") or ""
    if mode_lim == "auto":
        log("[5/6] Génération des limites (enveloppe des points GPS des ménages)…")
        limites, limites_commune, limites_district = _limites_auto(menages, log)
    elif mode_lim == "dossier":
        log("[5/6] Lecture des limites fournies par l'utilisateur…")
        limites, limites_commune, limites_district = _limites_dossier(
            seg_liste_lim, user_lim, log)
    else:
        log("[5/6] Lecture des limites intégrées (OCHA 2018)…")
        limites, limites_commune, limites_district = _limites_integrees(
            seg_liste_lim, limites_dir, log)

    # Limites CORRIGÉES fournies par le serveur (web) : elles REMPLACENT OCHA pour
    # les codes concernés (quatre districts, cf. limites_db.py). `update()` fait
    # primer l'override sur ce que le mode a produit. Inerte côté exe (None).
    if contours_override:
        f_ov = contours_override.get("fkt") or {}
        c_ov = contours_override.get("commune") or {}
        d_ov = contours_override.get("district") or {}
        limites.update(f_ov)
        limites_commune.update(c_ov)
        limites_district.update(d_ov)
        log(f"   limites corrigées appliquées : {len(f_ov)} fokontany, "
            f"{len(c_ov)} communes, {len(d_ov)} districts")

    log("[6/6] Assemblage du rapport HTML…")
    meta = {"projet": "RSU 2026", "date_rapport": _date_rapport(menages)}

    with open(head_path, "r", encoding="utf-8") as f:
        head = f.read()
    with open(tail_path, "r", encoding="utf-8") as f:
        tail = f.read()

    # CSS + Chart.js : references externes (web, page legere) ou embarques (exe).
    head = _tete_assets(head, tpl_dir, assets_url)

    os.makedirs(rapport_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head)
        f.write("const META = " + json.dumps(meta, ensure_ascii=False) + ";\n")
        if zones_ref is not None:
            f.write("const ZONES_REF = "
                    + json.dumps(zones_ref, ensure_ascii=False) + ";\n")
        # Mode dashboard multi-pages (web) : une section, un périmètre. Gardé par
        # `typeof ACTIVE_SECTION` côté gabarit -> l'exe (qui n'injecte rien) garde
        # sa navigation SPA d'origine.
        if section is not None:
            f.write("const ACTIVE_SECTION = "
                    + json.dumps(section, ensure_ascii=False) + ";\n")
            f.write("const SCOPE = "
                    + json.dumps(scope or {}, ensure_ascii=False) + ";\n")
            f.write("const NAV_TREE = "
                    + json.dumps(nav_tree or [], ensure_ascii=False) + ";\n")
            f.write("const NAV_BASE = "
                    + json.dumps(nav_base, ensure_ascii=False) + ";\n")
        if alleger:
            # Sections « résumé » (district/commune) : on n'embarque PAS les ménages
            # bruts (des dizaines de milliers) — seulement les AGRÉGATS calculés
            # côté serveur (rapport_core.agrege), prouvés identiques au JS
            # (test_agrege.py). MENAGES/SEGMENTS_DEN vides (globaux du gabarit se
            # construisent à vide) ; pas de LIMITES (pas de carte sur ces pages).
            agg = agrege(menages)
            f.write("const MENAGES = [];\n")
            f.write("const SEGMENTS_DEN = [];\n")
            f.write("const SUMMARY = "
                    + json.dumps(agg["summary"], ensure_ascii=False) + ";\n")
            f.write("const SEGMENTS_AGG = "
                    + json.dumps(agg["segments"], ensure_ascii=False) + ";\n")
        else:
            f.write("const MENAGES = "
                    + json.dumps(menages, ensure_ascii=False) + ";\n")
            f.write("const SEGMENTS_DEN = "
                    + json.dumps(segments_den, ensure_ascii=False) + ";\n")
            f.write("const LIMITES = "
                    + json.dumps(limites, ensure_ascii=False) + ";\n")
            f.write("const LIMITES_COMMUNE = "
                    + json.dumps(limites_commune, ensure_ascii=False) + ";\n")
            f.write("const LIMITES_DISTRICT = "
                    + json.dumps(limites_district, ensure_ascii=False) + ";\n")
        # Indicateurs de couverture (web, page général district/commune) : réalisé
        # vs projection ménages 2025. Gardé par `typeof COUVERTURE` côté gabarit
        # (l'exe n'en injecte pas -> inchangé).
        if menages_attendus:
            cov = couverture(menages, menages_attendus,
                             (scope or {}).get("level", "district"))
            f.write("const COUVERTURE = "
                    + json.dumps(cov, ensure_ascii=False) + ";\n")
        f.write(tail)

    log(f"Rapport genere : {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# CLI de test (chemins par defaut = dossier du script)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    chemins = {
        "data": os.path.join(base, "DATA"),
        "rapport": os.path.join(base, "Rapport"),
        "limites": os.path.join(base, "LimitesFokontany"),
    }
    generer_rapport(chemins, print)
