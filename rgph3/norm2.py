# -*- coding: utf-8 -*-
"""Normalisation des libelles geographiques malagasy.

Deux pieges traites ici :
  * suffixe ordinal : RSU ecrit « MIARINARIVO » / « MIARINARIVO II » la ou RGPH
    ecrit « MIARINARIVO I » / « MIARINARIVO II ». Absence de suffixe == « I ».
  * doublet malagasy/francais : ATSIMO/SUD, AVARATRA/NORD, ANDREFANA/OUEST,
    ATSINANANA/EST. Substitue seulement si le mot est un token entier.
"""
import unicodedata, re

# Classes d'equivalence : tous les membres d'une classe designent la meme
# orientation. Couvre les variantes orthographiques du malgache lui-meme
# (ATSINANANA / ANTSINANANA) autant que le doublet malgache/francais.
CLASSES = [
    {"ATSIMO", "ANTSIMO", "SUD"},
    {"AVARATRA", "ANTSIMO_N", "NORD"},
    {"ANDREFANA", "OUEST"},
    {"ATSINANANA", "ANTSINANANA", "EST"},
]
EQUIV = {m: c for c in CLASSES for m in c}
SYN = EQUIV
ROMAIN = {"I":1, "II":2, "III":3, "IV":4, "V":5, "VI":6, "VII":7, "VIII":8}

def _tokens(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", " ", s).split()

def decoupe(s):
    """-> (radical_normalise, rang_ordinal). Pas de suffixe == rang 1."""
    t = _tokens(s)
    rang = 1
    if t and t[-1] in ROMAIN:
        rang = ROMAIN[t[-1]]; t = t[:-1]
    elif t and t[-1].isdigit() and 1 <= int(t[-1]) <= 8:
        rang = int(t[-1]); t = t[:-1]
    return "".join(t), rang

def cles(s):
    """Toutes les cles (radical, rang) plausibles pour un meme lieu."""
    rad, rang = decoupe(s)
    out = {(rad, rang)}
    t = _tokens(s)
    if t and (t[-1] in ROMAIN or (t[-1].isdigit() and len(t) > 1)): t = t[:-1]
    for i, w in enumerate(t):
        for alt in EQUIV.get(w, ()):
            out.add(("".join(t[:i] + [alt] + t[i+1:]), rang))
    if len(t) > 1 and t[-1] in EQUIV:
        out.add(("".join(t[:-1]), rang))          # MANAKARA ATSIMO -> MANAKARA
    return out

def cles_syn(s):
    """Doublets malagasy/francais UNIQUEMENT (pas de suppression de suffixe).
    Priorite haute : ne confond jamais EST et OUEST."""
    rad, rang = decoupe(s)
    out = {(rad, rang)}
    t = _tokens(s)
    if t and (t[-1] in ROMAIN or (t[-1].isdigit() and len(t) > 1)): t = t[:-1]
    for i, w in enumerate(t):
        for alt in EQUIV.get(w, ()):
            out.add(("".join(t[:i] + [alt] + t[i+1:]), rang))
    return out
