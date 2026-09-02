# -*- coding: utf-8 -*-
"""contexte_rsu.py — CONTEXTE GÉNÉRAL de référence du programme RSU / e-Fokontany.

Ce texte est un CADRAGE INSTITUTIONNEL du programme (note conceptuelle) — PAS des
données de mission. Il est injecté dans le prompt du rapport de mission rédigé par
IA (`rapport_mission.synthese_ia_iter`) afin que les sections « cadrées »
(introduction, concept/justification, objectifs, gouvernance, mandat de l'INSTAT,
historique, résultats attendus) s'appuient sur des FAITS réels du programme, et non
sur du texte générique.

⚠️ RÈGLE : ce contexte sert au CADRAGE uniquement. Le DÉROULEMENT de la mission et
tous les chiffres/faits de terrain proviennent EXCLUSIVEMENT des journaux de bord ;
l'IA ne doit jamais présenter les éléments ci-dessous comme des faits observés
pendant la période rapportée (ex. l'historique des phases n'est PAS la mission en
cours).
"""

CONTEXTE_RSU = """\
CONTEXTE GÉNÉRAL DU PROGRAMME — Registre Social Unique (RSU) et e-Fokontany (Madagascar)

1. Contexte et justification
Les politiques publiques efficaces (protection sociale, gouvernance digitale) reposent
sur des systèmes d'information fiables, inclusifs et interopérables. Le RSU et le
e-Fokontany sont deux piliers complémentaires du système national d'information sociale
et administrative. Le RSU centralise et harmonise les données socioéconomiques et de
vulnérabilité des ménages et des individus pour améliorer le ciblage, la coordination et
l'efficacité des programmes sociaux. Le e-Fokontany est un dispositif numérique de
proximité d'enregistrement, de structuration et de validation des données administratives
au niveau local. L'intégration des deux répond aux défis d'absence/insuffisance de
documents d'état civil et d'identification (acte de naissance, Carte Nationale d'Identité),
de fragmentation des bases et de doublons ; elle fiabilise et harmonise les données en
amont, prépare l'identification nationale (Numéro Unique d'Identification — NUI — et
enrôlement biométrique) et renforce l'inclusion sociale.

2. Cadre général du RSU
Système d'information national centralisé regroupant des données démographiques,
socio-économiques et de vulnérabilité des ménages et individus ; outil d'aide à la décision.
Il permet : identification et ciblage objectif des ménages vulnérables (ex. Proxy-Means-Test,
PMT) ; réduction des erreurs d'inclusion et d'exclusion ; coordination des interventions
(ministères, collectivités, partenaires techniques et financiers) ; optimisation des
ressources publiques et transparence. Registre de référence conçu pour être interopérable
(dont e-Fokontany et bases d'identification administrative).

3. Le e-Fokontany
Système d'information numérique au niveau du Fokontany (entité administrative de proximité).
Il digitalise le carnet Fokontany et structure les informations sur les ménages/individus.
Le carnet Fokontany n'est PAS une pièce d'identification officielle : le e-Fokontany ne
remplace pas les documents légaux (acte de naissance, CNI) mais fiabilise les données en
amont. Il permet : enregistrement et mise à jour des données démographiques/sociales ;
identification des personnes sans documents officiels ; détection/réduction des doublons ;
préparation et facilitation de l'enrôlement biométrique.

4. Articulation RSU / e-Fokontany (chaîne de valeur des données)
Le e-Fokontany est la porte d'entrée locale des données (enregistrement, validation, mise à
jour régulière) ; le RSU est le registre national de référence (consolidation des données
validées, exploitation pour ciblage et suivi). Cette intégration prépare l'attribution du
NUI et facilite l'enrôlement biométrique grâce à des données fiables et structurées en amont.

6. Principes directeurs
Harmonisation des concepts, définitions et outils ; validation progressive et contrôlée des
données ; inclusion de l'ensemble des ménages et de la population (dont personnes sans
documents officiels) ; sécurité, confidentialité et protection des données personnelles ;
interopérabilité avec les systèmes d'identité nationale et sectoriels.

7. Gouvernance et rôles des acteurs
- Niveau central : orientation stratégique, gestion du RSU, normes, coordination
  interinstitutionnelle (INSTAT, ministères sectoriels).
- Niveau régional et district : supervision technique, contrôle de qualité, appui aux
  opérations de terrain.
- Niveau Fokontany : enregistrement, validation et mise à jour via le e-Fokontany, interaction
  directe avec les ménages.
Les partenaires techniques et financiers appuient techniquement, financent et renforcent les
capacités.

Rôle et mandat de l'INSTAT (RSU/e-Fokontany, financement STATCAP II)
Le rôle de l'INSTAT s'inscrit dans son mandat légal (Loi n°2018-004 sur l'organisation et la
réglementation des activités statistiques). Autorité statistique principale (Art. 47) et
responsable de la coordination, production et diffusion des statistiques publiques (Art. 48 et
50), l'INSTAT est habilité à collecter des données individuelles auprès des ménages et
personnes physiques (Art. 2 et 9), y compris sociales et démographiques, à des fins
statistiques (recensement ou enquête, Art. 16). L'usage des données individuelles est
strictement encadré par le SECRET STATISTIQUE (Art. 29 à 31) : usage limité à des fins
statistiques, interdiction de toute utilisation à des fins de poursuite ou de répression.
Dans le RSU, l'INSTAT est garant méthodologique, producteur et validateur des données
(notamment le calcul du score PMT), en veillant à leur protection. L'exploitation des
informations individuelles par d'autres acteurs à des fins opérationnelles doit être encadrée
par des dispositions réglementaires et protocoles garantissant la conformité au secret
statistique et à la protection des données personnelles.

8. Résultats attendus
Base de données sociale et administrative validée ; meilleure préparation et coût réduit de
l'enrôlement biométrique ; amélioration du ciblage et de l'efficacité des programmes sociaux ;
suivi plus précis des progrès vers l'identification universelle.

9. Historique du RSU à Madagascar (phases — CADRAGE, ne pas confondre avec la mission en cours)
- Sept.–oct. 2023 : RSU uniquement, Pilote — districts Betioky-Atsimo, Ampanihy.
- Janv.–févr. et juil.–août 2024 : RSU uniquement, Pilote — Vondrozo, Befotaka, Midongy Atsimo.
- Févr.–mars 2025 : RSU et e-Fokontany, Pré-pilote — commune Ambohitrambo (district Arivonimamo).
- Mai–juin 2025 : RSU et e-Fokontany, Pilote — district Arivonimamo.
- Août–sept.–oct. 2025 : RSU et e-Fokontany, Mise à l'échelle nationale — Ambanja,
  Ambatondrazaka, Amparafaravola, Andapa, Andilamena, Andramasina, Antananarivo Atsimondrano,
  Antsirabe I, Antsiranana II, Belo-sur-Tsiribihina, Fenoarivobe, Ikalamavony, Mahajanga II,
  Mampikony, Manjakandriana, Miandrivazo, Port-Bergé (Boriziny Vaovao), Sambava,
  Soanierana Ivongo, Vohémar.
Ces phases ont renforcé la qualité et la fiabilité des données, amélioré les outils et
procédures de collecte/validation, et consolidé l'articulation RSU / e-Fokontany, base de
l'extension nationale.

10. Conclusion (cadre)
L'intégration du RSU et du e-Fokontany est un levier de gouvernance sociale et digitale :
fiabilisation des données en amont, facilitation de l'identification nationale, meilleur
ciblage des programmes sociaux, inclusion de l'ensemble de la population.
"""
