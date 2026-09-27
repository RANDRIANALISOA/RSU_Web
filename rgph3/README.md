# RGPH-3 2018 → référentiel RSU

Chaîne reproductible qui recode les deux fichiers SPSS du RGPH-3 2018 (INSTAT,
échantillon au 10 %) dans les codes géographiques de `rsu_local.sqlite`, puis en
dérive des agrégats pour le tableau de bord.

## Dépendances

`pandas` et `pyreadstat` ne sont **pas** dans le venv du projet (le reste de
`rsu-web` n'en a pas besoin). Pour rejouer la chaîne :

    venv/bin/python -m pip install pandas pyreadstat

## Entrées

| Fichier | Provenance |
|---|---|
| `INSTAT_BD_SPSS_MENAGES_10pc_RGPH-3_2018.sav` | INSTAT — 608 235 ménages, 67 variables |
| `INSTAT_BD_SPSS_RESIDENTS_10pc_RGPH-3_2018.sav` | INSTAT — 2 568 303 individus, 124 variables |
| `rsu_local.sqlite` | référentiel du projet (1 704 communes, 120 districts, 23 régions) |

Le fichier RESIDENTS doit être lu avec `encoding="LATIN1"` : l'encodage qu'il
déclare fait échouer readstat (séquence d'octets invalide).

## Étapes

    cd rgph3
    python 01_extraire_geo.py          # -> rgph_geo.csv, rsu_geo.csv
    python 02_apparier.py              # -> map_commune.csv       (1727 lignes)
    python 03_recoder.py               # -> ../rgph3_2018.sqlite  (1 Go, ~3 min)
    python 04_agregats.py              # -> rgph_commune.csv, rgph_pyramide.csv
    python 05_valider.py               # contrôle par les ménages
    python 06_croiser_avec_projet.py   # contrôle contre MENAGES_PAR_COMMUNE_2025.xlsx

Puis, pour charger les agrégats dans la base RSU :

    cd .. && python integrer_agregats_rgph.py

## Le problème résolu

Les deux nomenclatures sont **incompatibles** : mêmes nombres, entités
différentes. Le code région 21 désigne HAUTE MATSIATRA en 2018 et DIANA
aujourd'hui. Une jointure directe sur les codes passe sans erreur et produit des
résultats silencieusement faux.

|  | RGPH-3 2018 | RSU |
|---|---|---|
| Régions | 22 (pré-2021) | 23 (post-2021) |
| Districts | 114, codes 3 chiffres | 120, codes 4 chiffres |
| Communes | 1 727, codes 5 chiffres | 1 704, codes 6 chiffres |

L'appariement se fait donc **par les libellés**, par étapes de la plus sûre à la
plus permissive, chaque commune RSU n'étant attribuée qu'une fois. Voir
`02_apparier.py` pour l'ordre exact et `norm2.py` pour la normalisation
(suffixes ordinaux, doublets malgache/français).

Les 16 correspondances indéductibles des libellés sont dans `exceptions.py`,
chacune avec sa justification.

## Validation

- **1 727 / 1 727** communes appariées, 0 collision, 1 704 / 1 704 communes RSU atteintes
- Corrélation ménages RGPH×10 / `commune.nombreMenage` : **Pearson 0,9989**
- Concordance avec l'appariement préexistant du projet (`commune_POP` de
  `MENAGES_PAR_COMMUNE_2025.xlsx`) : **100 %** sur les 1 704 communes

Attention : le contrôle par `nombreMenage` est **partiellement circulaire**, ces
estimations provenant elles-mêmes d'un appariement de noms comparable. Il établit
que les deux tables désignent les mêmes communes, pas qu'elles sont justes dans
l'absolu.

## Limites connues

- **Pas de pondération de sondage** dans les fichiers INSTAT. Les niveaux
  (ex. 38,1 % d'électricité) peuvent s'écarter des publications officielles. Le
  **classement relatif** des communes, lui, reste valide — c'est ce qui sert au
  ciblage.
- **Pas de niveau fokontany.** Les fichiers ne contiennent aucun libellé de
  fokontany, seulement un numéro d'ordre anonyme (`IDMEN[6:10]`). L'aligner sur
  les fokontany actuels serait une conjecture invérifiable : les comptes diffèrent
  dans 34 % des communes.
- `ANONTSIBE EST` → `ANONTSIBE CENTRE` (district Manja) est le seul appariement
  incertain — les orientations diffèrent. Méthode `flou-large/district`.
- **106 âges manquants** sur 2 568 303. Tout calcul sur `P08` doit filtrer
  `WHERE P08 IS NOT NULL`.

## Structure de IDMEN (26 caractères)

    111 01 1 01 01 …
    │   │  │  │  └── n° d'ordre du fokontany dans la commune (sans libellé)
    │   │  │  └───── constante
    │   │  └──────── strate d'urbanisation (1 grande ville / 2 ville / 3 rural)
    │   └─────────── commune (avec le district : IDMEN[:5])
    └─────────────── district

`IDMEN[:1]`, `[:2]`, `[:3]` reproduisent exactement `PROVINCE`, `REGION`,
`DISTRICT`. La strate en position 6 n'est **pas** la variable `MILIEU` (décret
2015-592), qui est distincte et à deux modalités.
