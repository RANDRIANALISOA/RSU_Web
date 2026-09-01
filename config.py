# -*- coding: utf-8 -*-
"""
config.py — Chemins et réglages de l'application web RSU.

UN SEUL endroit pour les chemins. En développement, les gros dossiers de données
(DATA, contours) restent dans le projet .exe voisin (RSU_Rapport) et sont
RÉFÉRENCÉS ici, pas dupliqués. En production, on surchargera via des variables
d'environnement (aucune modification de code).

Variables d'environnement reconnues (toutes optionnelles) :
    RSU_EXE_DIR   dossier du projet .exe (défaut : ..\\RSU_Rapport)
    RSU_DATA      dossier des .dta pour la simulation (défaut : <RSU_EXE_DIR>\\DATA)
    RSU_LIMITES   dossier des contours (défaut : <RSU_EXE_DIR>\\LimitesFokontany)
    RSU_DB_URL    base PostgreSQL (ex. postgresql://user:mdp@hote:5432/rsu).
                  Absent -> SQLite local (db_source.connect()).
"""

import os

# Racine du projet web (ce dossier).
BASE = os.path.dirname(os.path.abspath(__file__))

# Préfixe d'URL : toute l'application est servie sous ce chemin (ex. /rsu/choix,
# /rsu/login, /rsu/admin, /rsu/vue/...). Une URL sans préfixe est redirigée vers la
# version préfixée. Modifiable par variable d'environnement.
PREFIXE = os.environ.get("RSU_PREFIXE", "/rsu").rstrip("/")

# Date de début de la mission (AAAA-MM-JJ). Sert au SUIVI des rapports journaliers
# (colonnes de dates = du début de mission à aujourd'hui, pour voir les jours
# manqués). Modifiable par variable d'environnement.
DATE_DEBUT_MISSION = os.environ.get("RSU_DATE_DEBUT_MISSION", "2026-08-27")

# Projet .exe voisin (source des gros fichiers partagés en développement).
_DEFAUT_EXE = os.path.normpath(os.path.join(BASE, "..", "RSU_Rapport"))
EXE_DIR = os.environ.get("RSU_EXE_DIR", _DEFAUT_EXE)

# Gabarits : copie LOCALE (source du rendu, embarquée avec l'app web).
TEMPLATES_DIR = os.path.join(BASE, "templeteHtml")

# Assets du rapport (CSS + Chart.js) sortis du gabarit pour alléger les pages.
# Servis en statique sous /assets (voir serveur_app.py) et mis en cache par le
# navigateur ; Chart.js est une copie locale -> graphiques lisibles hors-ligne.
ASSETS_DIR = os.path.join(BASE, "assets")

# Images et médias (bannière de la page de connexion, etc.).
IMAGES_DIR = os.path.join(BASE, "images")

# Dossier serveur où l'Expert survey TÉLÉVERSE ses .dta, en sous-dossiers par code
# district : UPLOAD_DIR/<code_district>/DEN_MENAGE.dta, … Puis transcription (maj_db).
# Distinct de DATA_DIR (les .dta de simulation du projet exe).
UPLOAD_DIR = os.environ.get("RSU_UPLOAD_DIR", os.path.join(BASE, "DATA_serveur"))

# Données de simulation (.dta) : référencées dans le projet .exe par défaut.
# En production, l'app lira la base de données, pas ce dossier.
DATA_DIR = os.environ.get("RSU_DATA", os.path.join(EXE_DIR, "DATA"))

# Contours des fokontany : référencés dans le projet .exe par défaut (108 Mo,
# non dupliqués). Mettre RSU_LIMITES pour pointer ailleurs, ou vide pour s'en passer.
LIMITES_DIR = os.environ.get("RSU_LIMITES", os.path.join(EXE_DIR, "LimitesFokontany"))

# Limites CORRIGÉES (shapefiles Admin2/3/4) de quatre districts (AMBOHIDRATRIMO,
# ANTANANARIVO AVARADRANO, FENERIVE EST, VAVATENINA) qui REMPLACENT OCHA. Chargées
# en base par limites_db.py (tables limite_district/commune/fokontany liées à
# `zones`), puis injectées à la place d'OCHA au rendu du rapport.
LIMITES_QUATRE_DIR = os.environ.get(
    "RSU_LIMITES_QUATRE", os.path.join(BASE, "LimitesQuatreDistrict"))
