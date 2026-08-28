#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lire_dta.py
===========

Lecteur de fichiers Stata `.dta` (formats 117/118/119) en **Python pur** —
uniquement la bibliotheque standard (`struct`), aucune dependance externe
(remplace pandas/pyreadstat, voir CLAUDE.md §7).

Ce module fournit tout ce dont le portage du dofile RSU a besoin :
  - lecture des variables numeriques (byte/int/long/float/double) avec gestion
    correcte des valeurs manquantes Stata (`.`, `.a`..`.z`) -> None ;
  - lecture des chaines fixes (str#) et longues (strL) en UTF-8 ;
  - lecture des VALUE LABELS, pour "decoder" region/district/commune/fokontany
    (equivalent du `decode` Stata / `apply_value_formats` pyreadstat).

Utilisation :
    from lire_dta import lire_dta
    d = lire_dta("DATA/DEN_MENAGE.dta")
    d.nobs                       # nombre d'observations
    d.varnames                   # liste des noms de variables
    d.col("num_fkt")             # colonne brute (valeurs numeriques / None)
    d.col_decoded("region")      # colonne avec labels appliques (texte)
    for ligne in d.rows():       # iteration ligne par ligne (dict {var: valeur})
        ...

Test rapide :
    python lire_dta.py DATA/DEN_MENAGE.dta
"""

from __future__ import annotations

import struct
import sys


# ---------------------------------------------------------------------------
# Codes de type Stata (format 117+)
# ---------------------------------------------------------------------------
T_STRL = 32768
T_DOUBLE = 65526
T_FLOAT = 65527
T_LONG = 65528   # int32
T_INT = 65529    # int16
T_BYTE = 65530   # int8

# Seuils au-dela desquels une valeur numerique est une valeur manquante Stata.
MISS_BYTE = 100
MISS_INT = 32740
MISS_LONG = 2147483620
MISS_FLOAT = 2.0 ** 127     # `.` float = 0x7F000000
MISS_DOUBLE = 2.0 ** 1023   # `.` double = 0x7FE0000000000000

# Largeur des champs "nom"/"format"/"label" selon la release.
# (117 : noms 33, formats 49, labels variables 81 ; 118/119 : 129/57/321)
FIELD_WIDTHS = {
    117: {"name": 33, "fmt": 49, "vlabel": 81},
    118: {"name": 129, "fmt": 57, "vlabel": 321},
    119: {"name": 129, "fmt": 57, "vlabel": 321},
}


class Dta:
    """Contenu d'un fichier .dta, stocke en colonnes."""

    def __init__(self) -> None:
        self.release: int = 0
        self.byteorder: str = "<"       # "<" (LSF) ou ">" (MSF)
        self.nvar: int = 0
        self.nobs: int = 0
        self.varnames: list[str] = []
        self.types: list[int] = []      # codes de type bruts
        self.val_label_names: list[str] = []   # nom du jeu de labels par variable
        self.value_labels: dict[str, dict[int, str]] = {}
        self._cols: dict[str, list] = {}       # nom -> colonne (valeurs post-traitees)

    # -- Acces aux colonnes ---------------------------------------------------
    def col(self, name: str) -> list:
        """Colonne BRUTE (nombres/None pour manquant, ou chaines)."""
        return self._cols[name]

    def col_decoded(self, name: str) -> list:
        """
        Colonne avec VALUE LABELS appliques (texte), comme `decode` en Stata.
        Si la variable n'a pas de jeu de labels, renvoie la colonne brute.
        Une valeur numerique sans label correspondant est conservee telle
        quelle (comportement de pyreadstat.apply_value_formats).
        """
        idx = self.varnames.index(name)
        setname = self.val_label_names[idx]
        raw = self._cols[name]
        if not setname or setname not in self.value_labels:
            return raw
        mapping = self.value_labels[setname]
        out = []
        for v in raw:
            if v is None:
                out.append(None)
            elif v in mapping:
                out.append(mapping[v])
            else:
                out.append(v)
        return out

    def rows(self):
        """Iterateur : une ligne = dict {nom_variable: valeur brute}."""
        cols = [self._cols[n] for n in self.varnames]
        for i in range(self.nobs):
            yield {n: cols[j][i] for j, n in enumerate(self.varnames)}


# ---------------------------------------------------------------------------
# Fonctions internes de lecture
# ---------------------------------------------------------------------------
def _between(buf: bytes, tag: str) -> bytes:
    """Contenu entre <tag> et </tag> dans buf (tags aux extremites)."""
    ouvrant = ("<" + tag + ">").encode("ascii")
    fermant = ("</" + tag + ">").encode("ascii")
    if not buf.startswith(ouvrant) or not buf.endswith(fermant):
        raise ValueError(f"Section <{tag}> mal formee.")
    return buf[len(ouvrant):len(buf) - len(fermant)]


def _decode_str(raw: bytes) -> str:
    """Chaine fixe Stata : coupe au premier octet nul, decode UTF-8."""
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


def _num_missing(value, code: int):
    """Renvoie None si `value` est une valeur manquante Stata pour ce type."""
    if code == T_BYTE:
        return None if value > MISS_BYTE else value
    if code == T_INT:
        return None if value > MISS_INT else value
    if code == T_LONG:
        return None if value > MISS_LONG else value
    if code == T_FLOAT:
        return None if (value != value or value >= MISS_FLOAT) else value
    if code == T_DOUBLE:
        return None if (value != value or value >= MISS_DOUBLE) else value
    return value


def lire_dta(path: str) -> Dta:
    """Lit entierement un fichier .dta (format 117/118/119) et renvoie un Dta."""
    with open(path, "rb") as f:
        data = f.read()

    d = Dta()

    # --- En-tete : release, byteorder, K (nb variables), N (nb obs) ---
    rel = data[data.find(b"<release>") + 9: data.find(b"</release>")]
    d.release = int(rel)
    if d.release not in FIELD_WIDTHS:
        raise ValueError(f"Release .dta non geree : {d.release}")
    W = FIELD_WIDTHS[d.release]

    bo = data[data.find(b"<byteorder>") + 11: data.find(b"</byteorder>")]
    d.byteorder = "<" if bo == b"LSF" else ">"
    en = d.byteorder

    kpos = data.find(b"<K>") + 3
    d.nvar = struct.unpack_from(en + "H", data, kpos)[0]

    npos = data.find(b"<N>") + 3
    if d.release == 117:
        d.nobs = struct.unpack_from(en + "I", data, npos)[0]
    else:  # 118 / 119 : N sur 8 octets
        d.nobs = struct.unpack_from(en + "Q", data, npos)[0]

    # --- Table <map> : 14 offsets (uint64) vers chaque section ---
    mpos = data.find(b"<map>") + 5
    offs = struct.unpack_from(en + "14Q", data, mpos)
    (_o_dta, _o_map, o_types, o_varnames, o_sortlist, o_formats,
     o_vlblnames, o_varlabels, o_char, o_data, o_strls, o_vallabels,
     _o_end, _o_eof) = offs

    # --- Types des variables ---
    blob = _between(data[o_types:o_varnames], "variable_types")
    d.types = list(struct.unpack_from(en + f"{d.nvar}H", blob, 0))

    # --- Noms des variables ---
    blob = _between(data[o_varnames:o_sortlist], "varnames")
    w = W["name"]
    d.varnames = [_decode_str(blob[i * w:(i + 1) * w]) for i in range(d.nvar)]

    # --- Noms des jeux de value labels par variable ---
    blob = _between(data[o_vlblnames:o_varlabels], "value_label_names")
    d.val_label_names = [_decode_str(blob[i * w:(i + 1) * w])
                         for i in range(d.nvar)]

    # --- Chaines longues (strL) : dictionnaire (v, o) -> texte ---
    strls = _lire_strls(data[o_strls:o_vallabels], en, d.release)

    # --- Donnees : disposition fixe des lignes ---
    d._cols = _lire_donnees(
        _between(data[o_data:o_strls], "data"),
        en, d.nvar, d.nobs, d.types, d.varnames, strls, d.release)

    # --- Value labels ---
    d.value_labels = _lire_value_labels(
        data[o_vallabels:_o_end], en, W["name"])

    return d


def _taille_type(code: int) -> int:
    """Largeur en octets d'un champ selon son type."""
    if code == T_BYTE:
        return 1
    if code == T_INT:
        return 2
    if code in (T_LONG, T_FLOAT):
        return 4
    if code == T_DOUBLE:
        return 8
    if code == T_STRL:
        return 8
    if 1 <= code <= 2045:   # str#
        return code
    raise ValueError(f"Type Stata inconnu : {code}")


_STRUCT_CODE = {T_BYTE: "b", T_INT: "h", T_LONG: "i",
                T_FLOAT: "f", T_DOUBLE: "d"}


def _lire_donnees(blob, en, nvar, nobs, types, varnames, strls, release):
    """Decoupe la section <data> en colonnes post-traitees."""
    # Construit un format struct pour une ligne complete.
    fmt = en
    for code in types:
        if code in _STRUCT_CODE:
            fmt += _STRUCT_CODE[code]
        elif code == T_STRL:
            fmt += "8s"
        else:                     # str#
            fmt += f"{code}s"
    ligne = struct.Struct(fmt)
    rowsize = ligne.size

    cols = [[] for _ in range(nvar)]
    off = 0
    unpack = ligne.unpack_from
    for _ in range(nobs):
        valeurs = unpack(blob, off)
        off += rowsize
        for j, code in enumerate(types):
            v = valeurs[j]
            if code in _STRUCT_CODE:
                cols[j].append(_num_missing(v, code))
            elif code == T_STRL:
                cols[j].append(_resoudre_strl(v, en, release, strls))
            else:                 # str#
                cols[j].append(_decode_str(v))
    return {varnames[j]: cols[j] for j in range(nvar)}


def _resoudre_strl(ref8: bytes, en: str, release: int, strls: dict) -> str:
    """Resout une reference strL (8 octets) vers son texte via le dico strls."""
    if ref8 == b"\x00" * 8:
        return ""
    if release == 117:
        v, o = struct.unpack_from(en + "II", ref8, 0)
    else:  # 118/119 : v sur 2 octets, o sur 6 octets
        v = struct.unpack_from(en + "H", ref8, 0)[0]
        o = int.from_bytes(ref8[2:8], "little" if en == "<" else "big")
    return strls.get((v, o), "")


def _lire_strls(section: bytes, en: str, release: int) -> dict:
    """Lit la section <strls> -> dict {(v, o): texte}."""
    out: dict = {}
    if not section:
        return out
    body = _between(section, "strls")
    i = 0
    n = len(body)
    while i + 3 <= n and body[i:i + 3] == b"GSO":
        i += 3
        v = struct.unpack_from(en + "I", body, i)[0]
        i += 4
        o = struct.unpack_from(en + "Q", body, i)[0]
        i += 8
        t = body[i]
        i += 1
        length = struct.unpack_from(en + "I", body, i)[0]
        i += 4
        contenu = body[i:i + length]
        i += length
        if t == 130:   # texte (ASCII/UTF-8, se termine par un octet nul)
            texte = contenu.split(b"\x00", 1)[0].decode("utf-8", "replace")
        else:          # 129 = binaire : on decode au mieux
            texte = contenu.decode("utf-8", "replace")
        out[(v, o)] = texte
    return out


def _lire_value_labels(section: bytes, en: str, namew: int) -> dict:
    """Lit la section <value_labels> -> {nom_jeu: {valeur: texte}}."""
    out: dict = {}
    if not section:
        return out
    body = _between(section, "value_labels")
    i = 0
    n = len(body)
    while i + 5 <= n and body[i:i + 5] == b"<lbl>":
        i += 5
        length = struct.unpack_from(en + "I", body, i)[0]
        i += 4
        labname = _decode_str(body[i:i + namew])
        i += namew
        i += 3   # padding
        table = body[i:i + length]
        i += length
        # fin de bloc : </lbl>
        if body[i:i + 6] == b"</lbl>":
            i += 6
        # Decodage de la table
        nval = struct.unpack_from(en + "I", table, 0)[0]
        txtlen = struct.unpack_from(en + "I", table, 4)[0]
        p = 8
        offsets = struct.unpack_from(en + f"{nval}i", table, p)
        p += 4 * nval
        valeurs = struct.unpack_from(en + f"{nval}i", table, p)
        p += 4 * nval
        pool = table[p:p + txtlen]
        mapping: dict[int, str] = {}
        for k in range(nval):
            debut = offsets[k]
            fin = pool.find(b"\x00", debut)
            if fin < 0:
                fin = txtlen
            mapping[valeurs[k]] = pool[debut:fin].decode("utf-8", "replace")
        out[labname] = mapping
    return out


# ---------------------------------------------------------------------------
# Test en ligne de commande : python lire_dta.py <fichier.dta>
# ---------------------------------------------------------------------------
def _main(argv) -> int:
    if len(argv) < 2:
        print("Usage : python lire_dta.py <fichier.dta> [nom_variable_a_decoder]")
        return 1
    d = lire_dta(argv[1])
    print(f"Fichier   : {argv[1]}")
    print(f"Release   : {d.release}   byteorder : "
          f"{'LSF' if d.byteorder == '<' else 'MSF'}")
    print(f"Variables : {d.nvar}     Observations : {d.nobs}")
    print("-" * 60)
    for name, code, lbl in zip(d.varnames, d.types, d.val_label_names):
        ttxt = {T_BYTE: "byte", T_INT: "int", T_LONG: "long", T_FLOAT: "float",
                T_DOUBLE: "double", T_STRL: "strL"}.get(code, f"str{code}")
        lblinfo = f"  [labels: {lbl}]" if lbl else ""
        print(f"  {name:32} {ttxt:8}{lblinfo}")
    print("-" * 60)
    print(f"Jeux de value labels : {len(d.value_labels)}")

    if len(argv) >= 3:
        var = argv[2]
        vals = d.col_decoded(var)
        distinct = sorted({str(v) for v in vals if v is not None})[:15]
        print(f"\n{var} : {len(distinct)} valeurs distinctes (echantillon) :")
        for v in distinct:
            print("   ", v)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
