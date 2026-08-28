# RSU_Web — Démarrage rapide

Application web du rapport RSU 2026 (voir `CLAUDE.md` pour la conception complète).

## Prérequis
- Python 3.12 (déjà installé sur la machine).
- Le projet exe voisin `..\RSU_Rapport\` présent (fournit les données `.dta` et les
  contours pour la simulation — voir `config.py`).

## 1. Simuler « données en base de données » (rien à installer)
```
python simuler_db.py
```
Transcrit les `.dta` dans une base SQLite locale, génère le rapport **depuis la
base**, et vérifie qu'il est **identique** au rapport issu des `.dta`.

## 2. Lancer l'application web (pilotée par la base) — RECOMMANDÉ
```
python serveur_app.py
```
Ouvre `http://127.0.0.1:8000/` : un **menu Commune → Fokontany**. En cliquant sur un
fokontany, le serveur ne charge QUE ce fokontany (page ~150 Ko au lieu de 25 Mo). Le
tableau de bord complet (KPI, graphiques, carte) s'affiche instantanément.
⚠️ Prototype local, sans login — ne pas exposer sur internet.

### (ancien) Prototype par upload de fichiers
```
python serveur_web.py
```
Variante où l'on téléverse les 3 `.dta` au lieu de lire la base. Gardé en référence.

## 3. Basculer sur PostgreSQL (plus tard)
```
pip install "psycopg[binary]"
set RSU_DB_URL=postgresql://utilisateur:motdepasse@hote:5432/rsu
python simuler_db.py
```

## Où changer les chemins ?
Tout est dans **`config.py`** (dossier des `.dta`, dossier des contours, base de
données). En production, on les redéfinit par variables d'environnement, sans
toucher au code.
```
```
