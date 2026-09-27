# -*- coding: utf-8 -*-
"""Exceptions explicites : renommages reels et cas indeductibles des libelles.
Codes VERIFIES dans rgph_geo.csv / rsu_geo.csv. Partie auditable de la table.
"""
EXCEPTIONS = {
    "53101": ("620327", "FORT DAUPHIN -> TOLAGNARO (renommage officiel)"),
    "61101": ("210301", "COMMUNE URBAINE DE DIEGO SUAREZ -> ANTSIRANANA (renommage)"),
    "31203": ("530614", "MAHAVELONA (FOULPOINTE) -> FOULPOINTE (nom entre parentheses retenu)"),
    "52408": ("610403", "BETANTY (FAUX CAP) -> FAUX CAP (idem)"),
    "22109": ("310208", "AMBOSITRA II -> AMBOSITRA BANLIEUE (peripherie urbaine)"),
    "32101": ("520106", "FENERIVE EST (commune) -> FENERIVE VILLE"),
    "25404": ("320306", "MALIORANO -> ZARA EX-MALIORANO"),
    "42206": ("440107", "ANKARAMIBE -> ANKARAMY"),
    "43104": ("410219", "BERIVOTRA -> BERIVOTRA 5/5"),
    "52305": ("610308", "MAHENY -> MAHAENEGNE"),
    "61311": ("210208", "ANJIABE AMBONY -> ANJIABE HAUT (ambony = haut)"),
    "31310": ("530216", "VOHIPENO RAZANAKA -> RAZANAKA"),
    "23324": ("350248", "NAMORONA : district MANANJARY (2018) -> MANAKARA (actuel)"),
    "21615": ("330616", "ANJANOMANANA -> ANJANOMANONA TSIMIAVAKA"),
    "52111": ("610521", "ANDOHARANO AMBINAGNY -> ANDOHARANO (Antanimora Sud, pas Vondrozo)"),
    "54308": ("640115", "ANTSAKOAMALINIKA -> DELTA (par elimination dans Belo sur Tsiribihina)"),
}
