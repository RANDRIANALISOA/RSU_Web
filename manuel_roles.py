# -*- coding: utf-8 -*-
"""manuel_roles.py — Contenu du manuel PROPRE À CHAQUE RÔLE.

Expose :
    intro_role(role)    -> phrase d'accroche (bandeau bleu) ;
    sections_role(role) -> [(id, titre, html), …] sections spécifiques au poste.

Les briques de rendu et illustrations viennent de manuel_ui (U). Le contenu est
volontairement détaillé et concret (étapes, encadrés, maquettes) pour que chaque
utilisateur comprenne son flux de travail sans formation préalable.
"""

import manuel_ui as U
import utilisateurs          # groupes de rôles (source de vérité)


# ===========================================================================
# Briques réutilisées par plusieurs rôles
# ===========================================================================
def _sec_dashboard(perimetre, gps_note=None):
    """Section « Le tableau de bord » commune aux rôles qui suivent le dénombrement.
    `perimetre` décrit ce que la personne voit (district / ses communes…)."""
    corps = [
        U.p("Le tableau de bord affiche le suivi du <strong>dénombrement</strong> "
            f"sous forme de pages. {perimetre}"),
        U.illus_dashboard(),
        U.h3("Naviguer entre les sections"),
        U.p("La barre de gauche liste les sections. Un clic ouvre la page "
            "correspondante :"),
        U.puces([
            "<strong>Vue générale</strong> — couverture du dénombrement vs "
            "projection RGPH-3 2025, indicateurs clés dont la <strong>taille "
            "moyenne des ménages</strong>, son <strong>écart-type</strong> et son "
            "<strong>coefficient de variation</strong>.",
            "<strong>Par agent</strong> — production par agent enquêteur et, au niveau du district, l'<strong>écart entre ce que l'agent déclare et ce qui arrive au serveur</strong>.",
            "<strong>Par zone</strong> — résultats par commune / fokontany.",
            "<strong>Carte GPS</strong> — position des ménages dénombrés.",
            "<strong>Capture GPS</strong> — taux de ménages géolocalisés.",
            "<strong>Qualité</strong> — présence des ménages, taille des ménages "
            "(moyenne, écart-type et coefficient de variation), électrification, "
            "statut des segments, complétude.",
            "<strong>Historique</strong> — progression dans le temps.",
            "<strong>Segments multiples</strong> — un même agent qui dénombre "
            "plusieurs fois le même code de segment dans un même fokontany "
            "(contrôle qualité). Deux agents différents sur le même code ne "
            "sont pas un doublon : c'est un partage de travail.",
        ]),
        U.h3("Descendre au niveau commune, puis fokontany"),
        U.p("Sous les sections, un sous-menu <strong>Commune → Fokontany</strong> "
            "permet de préciser le périmètre : cliquez une commune pour la détailler, "
            "puis un fokontany pour le détail le plus fin."),
        U.h3("Exporter le rapport en Excel"),
        U.p("Le bouton <strong>Exporter rapport</strong> (en bas à droite) télécharge "
            "un classeur Excel de votre périmètre, avec <strong>cinq feuilles</strong> :"),
        U.puces([
            "<strong>Rapport global</strong> — couverture par commune, puis la "
            "<em>structure des ménages</em> par commune et par fokontany : ménages "
            "dénombrés, personnes dénombrées, <strong>taille moyenne</strong>, "
            "<strong>écart-type de la taille</strong>, <strong>coefficient de "
            "variation</strong>, % de ménages présents, % GPS ;",
            "<strong>Dénombrement par agent-jour</strong> — un tableau par chef "
            "d'équipe ;",
            "<strong>BaseDenParAgent</strong> — table plate (pour tableau croisé) ;",
            "<strong>segment_multiple</strong> — le rapport des segments multiples ;",
            "<strong>Écart par agent</strong> — un agent, une ligne : jours "
            "déclarés, ménages <em>déclarés</em>, ménages <em>reçus au serveur</em>, "
            "écart et % du déclaré, le plus gros écart d'abord (mêmes chiffres que "
            "la page « Par agent » du tableau de bord) ;",
            "<strong>Écart déclaration-serveur</strong> — le détail par date de la "
            "feuille précédente, pour chaque agent, par chef d'équipe.",
        ]),
        U.astuce("Le <strong>coefficient de variation</strong> (CV) est "
                 "l'écart-type rapporté à la moyenne, en pourcentage. C'est une "
                 "dispersion <strong>relative</strong> : elle se compare d'une "
                 "commune à l'autre, alors que l'écart-type seul ne le permet pas "
                 "(un écart-type de 1,4 ne se lit pas pareil sur une taille moyenne "
                 "de 2,3 ou de 5,0). Plus le CV est élevé, plus les tailles de "
                 "ménages sont <strong>hétérogènes</strong> dans la zone."),
        U.info("Les anciennes colonnes du <strong>carnet e-Fokontany</strong> "
               "(avec / sans carnet, carnet scanné) ont été <strong>retirées</strong> : "
               "la question ne figure plus au questionnaire depuis septembre 2026 et "
               "ces colonnes n'affichaient plus que « n/d ». Elles sont remplacées par "
               "la taille des ménages et le taux de ménages présents."),
    ]
    if gps_note:
        corps.append(U.attention(gps_note))
    return ("dashboard", "Le tableau de bord de suivi", "".join(corps))


def _sec_dashboard_vad(perimetre):
    """Section « Tableau de bord VAD » — rôles qui suivent la visite à domicile."""
    return ("vad", "Le tableau de bord « Visite à domicile »", "".join([
        U.p("La <strong>VAD</strong> (visite à domicile) est la 2ᵉ phase du RSU : "
            "après le dénombrement, les agents retournent dans les ménages pour "
            "l'entretien complet — composition du ménage, habitation, biens, eau "
            "et assainissement. Elle a son <strong>propre tableau de bord</strong>, "
            f"distinct de celui du dénombrement. {perimetre}"),
        U.p(f"Vous l'ouvrez par la carte "
            f"{U.carte('🏠 Tableau de bord — Visite à domicile')} de votre espace."),
        U.h3("Les sections"),
        U.puces([
            "<strong>Vue globale</strong> — avancement quotidien, couverture par "
            "rapport aux ménages dénombrés, statut des interviews, consentements, "
            "récapitulatif par commune et par fokontany ;",
            "<strong>Démographie</strong> — pyramide des âges, rapport de "
            "masculinité, ratio de dépendance, chef de ménage, état matrimonial, "
            "niveau scolaire, activité, papiers d'identité ;",
            "<strong>Habitation</strong> — murs, sol, toit, éclairage, statut "
            "d'occupation, nombre de pièces et peuplement ;",
            "<strong>Biens &amp; actifs</strong> — taux de possession des 29 biens "
            "suivis (ils servent au score de bien-être) ;",
            "<strong>Eau &amp; assainissement</strong> — source d'eau, toilettes, "
            "ordures, et part des installations « améliorées » ;",
            "<strong>Carte GPS</strong> — position de chaque ménage interviewé et "
            "qualité de la capture ;",
            "<strong>Erreurs ménage</strong> et <strong>Erreurs individus</strong> "
            "— les anomalies de saisie, ménage par ménage et membre par membre ;",
            "<strong>Test de qualité</strong> — les tests statistiques de "
            "cohérence, agent par agent (voir plus bas) ;",
            "<strong>Par agent</strong> — d'abord la <strong>couverture par "
            "agent</strong> : ménages affectés par la base de préchargement, "
            "affectés interviewés (détaillés par statut : approuvé, rejeté, en "
            "cours…), taux de couverture, non affectés interviewés ; "
            "<strong>cliquez sur un agent</strong> pour la liste des ménages qui "
            "lui sont affectés et qu'il n'a pas encore interviewés. Suivent les "
            "ménages interviewés plusieurs fois, puis la production, durée "
            "moyenne d'entretien et anomalies de chaque enquêteur, et "
            "l'<strong>écart entre ce que "
            "l'agent déclare avoir interviewé et ce qui arrive au serveur</strong> "
            "(un agent, une ligne). Le classeur Excel reprend le tout : feuilles "
            "<em>Couverture par agent</em>, <em>Reste à interviewer</em>, "
            "<em>Doubles interviews</em> et <em>Écart par agent</em>.",
        ]),
        U.h3("Lire le tableau « Test de qualité »"),
        U.p("La section <strong>Test de qualité</strong> affiche un "
            "<strong>tableau de tous vos agents</strong> : une ligne par "
            "enquêteur, avec son <strong>chef d'équipe</strong> en première "
            "colonne, puis une colonne par test. Vous n'avez personne à "
            "choisir au départ — vous voyez d'emblée qui pose problème."),
        U.p("Les colonnes sont groupées par <strong>niveau</strong> : le "
            "<strong>niveau 1</strong> (6 tests) suit le travail de terrain — "
            "productivité, durée d'entretien, complétude, règles de validation, "
            "recours à « Hafa », non-réponse « Tsy mahalala ». Le "
            "<strong>niveau 2</strong> (9 tests) contrôle la "
            "<strong>cohérence démographique</strong> et répond à la question "
            "« les âges et le nombre de membres sont-ils remplis au jugé ? » : "
            "indices de Whipple et de Myers (arrondis d'âge sur 0 et 5, puis sur "
            "chacun des dix chiffres), indice ONU de précision âge-sexe, χ² du "
            "chiffre terminal, effet-agent sur le nombre de membres, "
            "Kolmogorov-Smirnov sur la distribution des âges, rapport de "
            "masculinité, et deux contrôles du lien au chef de ménage. Le "
            "<strong>niveau 3</strong> (14 colonnes) vérifie la "
            "<strong>cohérence entre les modules</strong> : treize règles "
            "logiques — le roster correspond-il au nombre de membres déclaré, "
            "n'y a-t-il qu'un seul chef de ménage, l'âge concorde-t-il avec "
            "l'année de naissance, une CIN n'est-elle déclarée que pour un "
            "majeur, le module emploi n'est-il rempli que pour les plus de "
            "15 ans… — puis un <strong>score composite d'incohérence</strong> "
            "qui les résume toutes en un seul nombre. Le "
            "<strong>niveau 4</strong> (6 colonnes) porte sur le "
            "<strong>logement</strong> : dans une même zone, les matériaux et "
            "les infrastructures varient peu d'un ménage à l'autre — un agent "
            "dont les réponses s'écartent de celles de sa zone, ou qui répond "
            "presque toujours la même chose, est donc repérable. Le "
            "<strong>niveau 5</strong> (5 colonnes) porte sur les "
            "<strong>29 biens du ménage</strong>, ceux qui servent à "
            "construire l'indice de bien-être : un agent qui coche en bloc "
            "au lieu d'observer casse la hiérarchie attendue entre les biens "
            "(on ne possède pas une moto sans posséder de natte) et dégrade "
            "l'échelle de mesure — ce qui se voit."),
        U.astuce("La colonne <strong>5.2 — score composite</strong> est la "
                 "plus utile pour démarrer : elle agrège les treize règles, "
                 "donc elle se calcule bien plus tôt que chacune prise "
                 "séparément, et elle désigne les agents nettement au-dessus "
                 "de leurs collègues."),
        U.p("Chaque case est <strong>colorée</strong> selon le résultat :"),
        U.puces([
            "<strong>rouge</strong> — seuil d'alerte franchi : à traiter en "
            "priorité, c'est le seuil de la documentation technique RSU ;",
            "<strong>orange</strong> — à surveiller : un palier intermédiaire "
            "est dépassé, sans être encore une alerte ;",
            "<strong>vert</strong> — conforme, rien à signaler sur ce test ;",
            "<strong>nd</strong> (gris) — <strong>non calculé</strong> : cet "
            "agent n'a pas encore assez de ménages pour que le test ait un "
            "sens. Ce n'est pas une erreur, et ce n'est pas un bon résultat "
            "non plus : c'est une absence de réponse.",
        ]),
        U.astuce("Le champ de recherche filtre sur le chef d'équipe ou le code "
                 "de l'agent, et la case <strong>« Alertes seulement »</strong> "
                 "ne garde que les lignes qui ont au moins une case rouge. "
                 "Survolez une case pour voir l'effectif et la conclusion du "
                 "test ; <strong>cliquez la ligne</strong> pour la fiche "
                 "complète de l'agent (principe, formule, calcul, seuils)."),
        U.attention("Les cases du tableau portent sur <strong>l'agent seul</strong>. "
                    "La fiche détaillée, elle, peut remonter au chef d'équipe ou à "
                    "la commune quand l'agent a trop peu de ménages : elle "
                    "l'indique alors en toutes lettres, et ce résultat décrit "
                    "l'équipe, <strong>pas l'agent</strong>."),
        U.h3("Lire les listings d'erreurs de saisie"),
        U.p("Ce sont les sections à ouvrir en premier quand on encadre la "
            "collecte : <strong>Erreurs ménage</strong> et <strong>Erreurs "
            "individus</strong>. Elles reprennent les contrôles du listing "
            "d'erreurs de l'INSTAT, dans sa forme d'origine — "
            "<strong>une colonne par contrôle</strong> :"),
        U.puces([
            "une <strong>ligne</strong> = un ménage (ou une personne) qui "
            "présente au moins une anomalie ;",
            "une <strong>colonne</strong> = un contrôle ; la cellule porte le "
            "<strong>message de correction</strong> quand l'anomalie est "
            "présente, et reste <strong>vide</strong> sinon ;",
            "la colonne <strong>Nb</strong> compte les anomalies de la ligne : "
            "triez dessus pour traiter les ménages les plus abîmés d'abord.",
        ]),
        U.astuce("Les filtres (district, commune, fokontany, chef d'équipe, "
                 "agent, dates, anomalie) servent à découper le travail : "
                 "choisissez une anomalie pour traiter un seul type d'erreur "
                 "sur tout le périmètre, ou un agent pour préparer un "
                 "rappel."),
        U.info("Le bouton <strong>Exporter</strong> reprend ces deux tableaux "
               "à l'identique dans le classeur Excel, feuilles <strong>« Erreur "
               "ménage »</strong> et <strong>« Erreur Individu »</strong> : "
               "mêmes lignes, mêmes colonnes de contrôle, filtre automatique et "
               "colonnes d'identification figées. En bas de chaque feuille, une "
               "<strong>légende</strong> donne, pour chaque contrôle, son code, "
               "son message et ce qu'il vérifie — c'est le document à envoyer "
               "aux équipes pour corriger."),
        U.attention("La légende liste aussi les contrôles "
                    "<strong>non calculables</strong> sur cet export, faute de "
                    "la variable dans les données (sources de revenu, "
                    "superficies, CIN…). Ils ne sont <strong>ni réussis ni "
                    "échoués</strong> : ils n'ont pas pu être évalués. Une "
                    "colonne absente ne veut pas dire « rien à corriger »."),
        U.attention("Les classements « <strong>eau améliorée</strong> » et "
                    "« <strong>assainissement amélioré</strong> » suivent les "
                    "définitions JMP (OMS/UNICEF). Ce sont des <strong>propositions"
                    "</strong>, à faire valider par les statisticiens du RSU : "
                    "elles ne viennent pas du questionnaire."),
        U.info("Si le tableau de bord annonce « aucune donnée », c'est que "
               "l'<strong>Expert Traitement</strong> du district n'a pas encore "
               "téléversé et transcrit l'export de la VAD."),
        U.info("En début de collecte, la quasi-totalité du tableau « Test de "
               "qualité » est en <strong>nd</strong> : les tests demandent de 5 "
               "à 30 observations par agent. Les couleurs apparaissent au fur "
               "et à mesure que les agents accumulent des ménages."),
    ]))


def _sec_journal_ecriture():
    """Section « Mon journal de bord » — rôles qui ÉCRIVENT leurs activités."""
    return ("journal", "Mon journal de bord", "".join([
        U.p("Chaque jour, vous consignez dans l'application les "
            "<strong>activités que vous avez réalisées</strong>. Les Coordonnateurs "
            "les lisent et s'en servent pour le rapport de mission — c'est la trace "
            "officielle de votre travail sur le terrain."),
        U.flux([
            ("Ouvrir", "Mon journal de bord"),
            ("Écrire", "les activités du jour"),
            ("Joindre", "photos / fichiers"),
            ("Enregistrer", "l'entrée est datée"),
        ]),
        U.p("Une <strong>bulle de rappel</strong> apparaît sur vos pages tant que "
            "vous n'avez rien écrit pour la journée en cours."),
        U.h3("Écrire l'entrée du jour"),
        U.etapes([
            f"Ouvrez {U.carte('📓 Mon journal de bord')} depuis votre espace.",
            "Vérifiez la <strong>date</strong> (par défaut, aujourd'hui ; vous "
            "pouvez saisir un jour passé, jamais un jour futur).",
            "Décrivez vos <strong>activités</strong> dans la zone de texte.",
            "Ajoutez si besoin des <strong>photos</strong> et des "
            "<strong>fichiers</strong> (voir ci-dessous).",
            f"Cliquez sur {U.bouton('Enregistrer dans mon journal')}.",
        ]),
        U.p("Votre nom, votre fonction et votre zone sont "
            "<strong>pré-remplis</strong> : rien à saisir."),
        U.h3("Joindre des photos et des fichiers"),
        U.p("Deux champs séparés : un pour les <strong>photos / images</strong>, un "
            "pour les <strong>autres fichiers</strong> (Word, Excel, PDF…). Vous "
            "pouvez cliquer <strong>plusieurs fois</strong> pour en ajouter d'autres : "
            "les fichiers déjà choisis restent dans la liste, et la petite croix "
            "à côté d'un nom le retire avant l'envoi."),
        U.attention("Un fichier ne doit pas dépasser <strong>25 Mo</strong>. "
                    "Les photos s'affichent ensuite en <strong>vignettes</strong> "
                    "dans votre journal ; les autres fichiers en liens "
                    "à télécharger."),
        U.h3("Modifier une entrée : corriger le texte, retirer ou ajouter des pièces"),
        U.p("Vous pouvez revenir sur <strong>vos</strong> entrées (personne d'autre "
            "ne le peut). La date de création reste figée ; la date de dernière "
            "modification est affichée."),
        U.etapes([
            "Dans la liste de vos entrées, cliquez sur "
            f"{U.bouton('✏️ Modifier')} sur celle à corriger.",
            "Corrigez la <strong>date</strong> et/ou le <strong>texte</strong>.",
            "Pour <strong>retirer</strong> une photo ou un fichier déjà envoyé : "
            "cochez sa case <strong>« Retirer »</strong> sous son aperçu.",
            "Pour <strong>ajouter</strong> d'autres photos ou fichiers : utilisez "
            "les champs d'ajout, comme à la création.",
            f"Cliquez sur {U.bouton('Enregistrer les modifications')}.",
        ]),
        U.info("Tout est appliqué <strong>en une seule fois</strong> : le texte, les "
               "retraits et les ajouts. Le message de confirmation indique combien de "
               "pièces jointes ont été ajoutées et combien retirées. Une pièce "
               "retirée est <strong>définitivement supprimée</strong> (base et "
               "serveur de fichiers) : elle ne peut pas être récupérée."),
        U.astuce("Tant que vous n'avez pas cliqué sur Enregistrer, rien n'est "
                 "appliqué : vous pouvez décocher une case « Retirer » si vous "
                 "changez d'avis."),
    ]))


def _sec_journal_lecture(perimetre, acces=None, par_adresse=False):
    """Section « Journaux des équipes » — rôles qui LISENT (Coordonnateurs, Admin).

    `acces`       : comment la personne ouvre la page (carte de son menu par défaut) ;
    `par_adresse` : True pour un espace SANS cartes (Admin) -> on donne les adresses."""
    ouvrir = acces or f"Ouvrez {U.carte('📓 Journaux des équipes')} depuis votre menu."

    def _page(carte_txt, adresse):
        """Désignation d'une page : sa carte de menu, ou son adresse (Admin)."""
        return (f"La page <code>{adresse}</code>" if par_adresse
                else U.carte(carte_txt))
    return ("journal", "Lire les journaux des équipes", "".join([
        U.p("Les équipes techniques de terrain consignent chaque jour leurs "
            f"activités. Vous les lisez {perimetre}"),
        U.h3("Consulter les journaux"),
        U.etapes([
            ouvrir,
            "Filtrez par <strong>district</strong>, <strong>fonction</strong>, "
            "<strong>nom</strong> ou <strong>date</strong>.",
            "Les <strong>photos</strong> jointes apparaissent en vignettes, les "
            "autres fichiers en liens à télécharger.",
        ]),
        U.h3("Savoir qui a écrit — et qui n'a pas écrit"),
        U.p(f"{_page('🗓️ Suivi des rapports journaliers', '/journal/suivi')} montre, "
            "pour chaque jour de mission, qui a rédigé son journal et qui ne l'a pas "
            "fait, par poste (et par axe pour les Superviseurs / Logistiques "
            "Inter-Communales)."),
        U.h3("Compiler un rapport de mission"),
        U.p(f"{_page('📄 Rapport de mission', '/rapport-mission')} rassemble les "
            "journaux d'une période en un rapport structuré (district / fonction / "
            "personne), imprimable."),
        U.h3("Les pièces jointes"),
        U.p("Les auteurs peuvent <strong>retirer</strong> une photo ou un fichier "
            "et en <strong>ajouter</strong> d'autres en modifiant leur entrée. Une "
            "pièce retirée est définitivement supprimée : si une photo vous semble "
            "manquer par rapport à ce que vous aviez vu, demandez-la à son auteur."),
        U.astuce("Vous <strong>lisez</strong> les journaux : vous n'en écrivez pas, "
                 "et vous ne pouvez pas modifier ceux des autres — chaque entrée "
                 "n'est modifiable que par son auteur."),
    ]))


def _sec_selection(mode):
    """Section « Choisir la zone » selon le type de périmètre du rôle.
    mode ∈ {'libre', 'multi', 'communes', 'impose'}."""
    if mode == "libre":
        corps = [
            U.p("Vous couvrez <strong>toute la zone</strong>. À la connexion, "
                "l'application vous demande de choisir un district à suivre :"),
            U.etapes([
                "Choisissez la <strong>Province</strong>.",
                "Choisissez la <strong>Région</strong> (la liste se met à jour).",
                "Choisissez le <strong>District</strong>.",
                "Choisissez le <strong>type de suivi</strong> (voir ci-dessous).",
                f"Cliquez sur {U.bouton('Continuer')}.",
            ]),
        ]
    elif mode == "multi":
        corps = [
            U.p("Vous êtes affecté à <strong>plusieurs districts</strong> (1 à 5). "
                "Vous les consultez <strong>un à la fois</strong> :"),
            U.etapes([
                "Choisissez un <strong>district</strong> dans la liste (limitée à "
                "vos affectations).",
                "Choisissez le <strong>type de suivi</strong>.",
                f"Cliquez sur {U.bouton('Continuer')}.",
            ]),
            U.astuce("Pour changer de district, revenez à la sélection via "
                     "« Mon espace » dans le bandeau."),
        ]
    elif mode == "communes":
        corps = [
            U.p("Votre district est <strong>déjà fixé</strong> par votre affectation, "
                "et vous suivez <strong>vos communes</strong>. Il ne reste qu'à "
                "choisir le type de suivi, puis à valider."),
        ]
    else:  # impose
        corps = [
            U.p("Votre district est <strong>déjà fixé</strong> par votre affectation. "
                "Vous n'avez pas de zone à choisir : validez simplement pour ouvrir "
                "le suivi."),
        ]
    corps.append(U.h3("Le type de suivi"))
    corps.append(U.puces([
        "<strong>Dénombrement</strong> — le suivi du recensement des ménages "
        "(disponible).",
        "<strong>Visite à domicile</strong> — le suivi des interviews au domicile "
        "des ménages (disponible) : il ouvre le <strong>tableau de bord VAD</strong> "
        "du district choisi.",
    ]))
    corps.append(U.capture("selection.png", "La page de sélection de la zone."))
    return ("selection", "Choisir la zone et le type de suivi", "".join(corps))


# ===========================================================================
# Introductions par rôle
# ===========================================================================
_INTROS = {
    "Traitement":
        "Vous préparez les données : vous suivez le dénombrement, vous remplissez "
        "la base des Chefs d'Équipe et des Agents, et vous générez la base de "
        "préchargement pour les visites à domicile.",
    "Expert survey":
        "Vous intégrez (« transcrivez ») dans l'application les données de "
        "dénombrement collectées sur le terrain pour votre district.",
    "Superviseur Technique":
        "Vous suivez la qualité et l'avancement du dénombrement sur les communes "
        "dont vous avez la charge.",
    "Coordonnateur Nationale":
        "Vous supervisez l'ensemble du pays : suivi du dénombrement de n'importe "
        "quel district, et fiche de l'équipe technique par district.",
    "Coordonnateur régionale":
        "Vous suivez le dénombrement des districts de votre région (jusqu'à cinq), "
        "consultés un à la fois.",
    "Comités Techniques":
        "Vous suivez le dénombrement des districts qui vous sont affectés "
        "(jusqu'à cinq), consultés un à la fois.",
    "Logistique District":
        "Vous disposez d'un espace dédié à la logistique et aux finances de votre "
        "district : tâches, paiements Mvola, pièces, budget.",
    "Logistique Inter-Communale":
        "Vous disposez d'un espace dédié à la logistique et aux finances de vos "
        "communes : tâches, paiements Mvola, pièces, budget.",
    "Admin":
        "Vous administrez l'application : comptes utilisateurs, affectations, "
        "journal des connexions et suivi des transcriptions.",
}


def intro_role(role):
    return _INTROS.get(role,
                       "Ce guide explique comment utiliser l'application RSU 2026 "
                       "au quotidien, selon votre poste.")


# ===========================================================================
# Sections par rôle
# ===========================================================================
def _r_traitement():
    s = []
    s.append(("poste", "Votre poste en bref", "".join([
        U.p("À la connexion, vous arrivez sur l'<strong>Espace Traitement</strong>, "
            "qui propose :"),
        U.puces([
            f"{U.carte('📊 Tableau de bord (suivi)')} — suivre le dénombrement de "
            "votre district ;",
            f"{U.carte('👔 Équipe technique')} — l'encadrement affecté à votre "
            "district ;",
            f"{U.carte('👥 Base Chefs d’Équipe & Agents')} — renseigner qui sont "
            "les chefs d'équipe et les agents ;",
            f"{U.carte('📈 Tableau de bord — Visite à domicile')} — suivre la VAD "
            "de votre district ;",
            f"{U.carte('📦 Base de préchargement')} — générer les fichiers de "
            "préchargement pour les visites à domicile ;",
            f"{U.carte('📓 Mon journal de bord')} — vos activités du jour.",
        ]),
        U.p("Cliquez une carte pour ouvrir l'activité correspondante."),
        U.capture("traitement_accueil.png", "L'accueil de l'espace Traitement."),
    ])))

    # Dashboard (district entier pour Traitement).
    s.append(_sec_dashboard(
        "Vous voyez <strong>votre district en entier</strong> (toutes ses communes)."))

    # Base CE / Agents — avec maquettes Excel.
    s.append(("equipes", "Remplir la base Chefs d'Équipe & Agents", "".join([
        U.p("Cette base relie chaque <strong>agent enquêteur</strong> à son "
            "<strong>chef d'équipe</strong>. Elle sert ensuite à afficher les noms "
            "(au lieu des codes) dans les rapports et à construire la base de "
            "préchargement. Vous fournissez <strong>deux fichiers Excel</strong> : "
            "un pour les chefs, un pour les agents."),
        U.flux([
            ("Télécharger", "les 2 modèles Excel"),
            ("Remplir", "chefs, puis agents"),
            ("Téléverser", "les 2 fichiers"),
            ("Vérifier", "le bilan affiché"),
        ]),
        U.capture("traitement_equipes.png",
                  "La page de la base Chefs d'Équipe & Agents."),
        U.h3("1. Le fichier des Chefs d'Équipe"),
        U.p("Deux colonnes : le <strong>code du chef</strong> et son "
            "<strong>nom et prénom</strong>."),
        U.tableur(
            ["login_ce", "nom_prenom_ce"],
            [["CE_MPKN_001", "RAKOTO Jean"],
             ["CE_MPKN_002", "RASOA Marie"],
             ["CE_MPKN_003", "RABE Paul"]],
            note="login_ce = identifiant unique du chef (sans espace). "
                 "nom_prenom_ce = son nom complet."),
        U.h3("2. Le fichier des Agents"),
        U.p("Trois colonnes : le <strong>code de l'agent</strong>, son "
            "<strong>nom et prénom</strong>, et le <strong>code de son chef "
            "d'équipe</strong> (qui doit exister dans le fichier des chefs)."),
        U.tableur(
            ["login_ae", "nom_prenom_ae", "login_ce"],
            [["EQ_MPKN_0001", "RANDRIA Koto", "CE_MPKN_001"],
             ["EQ_MPKN_0002", "RAVELO Soa", "CE_MPKN_001"],
             ["EQ_MPKN_0003", "RAKOTOARISOA Lala", "CE_MPKN_002"]],
            note="login_ce doit correspondre à un chef du 1er fichier "
                 "(c'est le lien agent → chef)."),
        U.attention("Respectez EXACTEMENT les noms de colonnes de la 1re ligne "
                    "(<code>login_ce</code>, <code>nom_prenom_ce</code>, "
                    "<code>login_ae</code>, <code>nom_prenom_ae</code>). "
                    "Téléchargez les modèles pour partir sur la bonne structure."),
        U.h3("Téléverser"),
        U.etapes([
            f"Ouvrez {U.carte('👥 Base Chefs d’Équipe & Agents')}.",
            "Téléchargez les deux modèles (liens <em>modèle chefs</em> et "
            "<em>modèle agents</em>) et remplissez-les.",
            "Sélectionnez d'abord le fichier des <strong>chefs</strong>, puis "
            "celui des <strong>agents</strong>.",
            f"Cliquez sur {U.bouton('Transcrire')} et lisez le <strong>bilan</strong> "
            "(ajouts / modifications).",
        ]),
        U.info("La transcription est <strong>additive</strong> : elle ajoute les "
               "nouveaux, met à jour les modifiés, et ne supprime rien. Vous pouvez "
               "la relancer autant de fois que nécessaire."),
        U.astuce("Cette base est la <strong>seule source</strong> des noms d'agents "
                 "et de chefs d'équipe dans toute l'application : rapports, export "
                 "Excel, et déclarations saisies par les Superviseurs Techniques. "
                 "Un agent dont le nom n'est pas encore renseigné s'affiche par son "
                 "<em>code</em> ; dès que vous le remplissez ici, son nom apparaît "
                 "partout, sans rien ressaisir ailleurs."),
        U.astuce("Modèles à télécharger directement : "
                 '<a href="/traitement/modele/chef.xlsx">modèle chefs d’équipe</a> · '
                 '<a href="/traitement/modele/agent.xlsx">modèle agents</a>.'),
    ])))

    # Préchargement.
    s.append(("prechargement", "Générer la base de préchargement", "".join([
        U.p("La <strong>base de préchargement</strong> prépare, à partir du "
            "dénombrement, les fichiers utilisés pour les visites à domicile. "
            "Chaque génération est une <strong>sortie (un lot)</strong> : les "
            "ménages qu'elle contient sont <strong>enregistrés dans la base</strong>, "
            "et <strong>un ménage préchargé une fois n'est jamais renvoyé</strong>."),
        U.flux([
            ("Ouvrir", "Base de préchargement"),
            ("Choisir", "les fokontany et le mode"),
            ("Générer", "le lot est enregistré"),
            ("Envoyer", "le ZIP aux Experts Survey"),
        ]),
        U.capture("prechargement.png", "La page de génération du préchargement."),
        U.h3("Les compteurs en haut de page"),
        U.puces([
            "<strong>Ménages préchargeables</strong> — les ménages du dénombrement "
            "de votre district dont l'interview est <strong>terminée ou "
            "approuvée</strong> ;",
            "<strong>Déjà préchargés</strong> — ceux qui figurent dans une sortie "
            "précédente ;",
            "<strong>Reste à précharger</strong> — ce que la prochaine sortie peut "
            "contenir.",
        ]),
        U.h3("Choisir les fokontany"),
        U.p("Par défaut, <strong>tous les fokontany</strong> sont retenus. Pour "
            "n'envoyer que certains fokontany (par exemple ceux dont le "
            "dénombrement est terminé), cochez <em>« Choisir des fokontany »</em> : "
            "les fokontany s'affichent <strong>par commune</strong>, avec le nombre "
            "de ménages restant à précharger. <em>« Toute la commune »</em> coche "
            "tous ses fokontany d'un coup. Un fokontany déjà entièrement préchargé "
            "est grisé. Les fokontany non choisis restent disponibles pour une "
            "prochaine sortie."),
        U.h3("Les modes d'affectation"),
        U.puces([
            "<strong>Dénombrement</strong> — aucune redistribution : chaque agent "
            "garde les ménages qu'il a dénombrés.",
            "<strong>Équilibré</strong> — répartit la charge (±10 %) en gardant les "
            "agents groupés.",
            "<strong>Équilibré fort</strong> — équilibrage plus poussé : un agent "
            "peut changer de fokontany.",
        ]),
        U.p("L'équilibrage ne porte que sur les ménages de la sortie en cours."),
        U.h3("Le résultat"),
        U.p("Le téléchargement d'une <strong>archive ZIP</strong> démarre "
            "aussitôt ; elle contient deux fichiers :"),
        U.puces([
            "<strong>base_prechargement_…xlsx</strong> — le préchargement lui-même "
            "(3 feuilles : Ensemble, nouveau, e_fokontany) ;",
            "<strong>charge_agents_…xlsx</strong> — le récapitulatif de la charge "
            "par agent (pour contrôler l'équilibrage).",
        ]),
        U.etapes([
            f"Ouvrez {U.carte('📦 Base de préchargement')}.",
            "Choisissez <strong>tous les fokontany</strong> ou cochez ceux à "
            "précharger.",
            "Choisissez le <strong>mode</strong> adapté.",
            f"Cliquez sur {U.bouton('Générer, enregistrer et télécharger (ZIP)')}.",
            "<strong>Envoyez</strong> l'archive aux Experts Survey Solutions : "
            "chaque sortie générée doit être envoyée.",
        ]),
        U.attention("Seules les interviews <strong>terminées ou approuvées</strong> "
                    "sont préchargées. Une interview <strong>rejetée</strong> n'est "
                    "pas perdue : une fois corrigée et approuvée, ses ménages "
                    "apparaîtront dans une sortie suivante."),
        U.h3("Retrouver les sorties déjà faites"),
        U.p("Le tableau <em>« Préchargements déjà enregistrés »</em> liste chaque "
            "lot (date, auteur, mode, fokontany, nombre de ménages). Vous pouvez "
            "<strong>retélécharger</strong> le ZIP de n'importe quel lot, ou le "
            "<strong>fichier total</strong> de tous les ménages déjà préchargés. "
            "Il n'y a <strong>plus rien à téléverser</strong> pour éviter les "
            "doublons : l'application s'en souvient."),
        U.attention("Seul le <strong>dernier</strong> lot peut être "
                    "<strong>annulé</strong> : ses ménages redeviennent « à "
                    "précharger ». N'annulez un lot que si son fichier n'a "
                    "<strong>pas</strong> été envoyé sur le terrain."),
        U.astuce("Le message « <em>AUCUN NOUVEAU MÉNAGE</em> » signifie que tous "
                 "les ménages (du district ou des fokontany choisis) ont déjà été "
                 "préchargés : il n'y a rien à envoyer aujourd'hui."),
        U.h3("La feuille « e_fokontany » est vide — c'est normal"),
        U.p("Le questionnaire en cours ne collecte plus le <strong>scan du carnet "
            "e-Fokontany</strong>. Tous les ménages partent donc en "
            "<strong>nouveau</strong>, la feuille <strong>e_fokontany</strong> ne "
            "contient que son en-tête, et <strong>Ensemble = nouveau</strong>. "
            "Ce n'est pas un défaut de génération."),
    ])))
    return s


def _r_expert():
    s = []
    s.append(("poste", "Votre poste en bref", "".join([
        U.p("À la connexion, vous arrivez sur votre <strong>espace Expert "
            "survey</strong>. Vous y intégrez les données des <strong>deux "
            "phases</strong> de la collecte, et vous consultez les tableaux de bord "
            "qui en découlent :"),
        U.puces([
            f"{U.carte('📋 Transcription — Dénombrement')} — le recensement des "
            "ménages (1ʳᵉ phase) ;",
            f"{U.carte('🏠 Transcription — Visite à domicile')} — l'entretien "
            "complet dans les ménages (2ᵉ phase) ;",
            f"{U.carte('📊 Tableau de bord — Dénombrement')} — le suivi du "
            "recensement de votre district ;",
            f"{U.carte('📈 Tableau de bord — Visite à domicile')} — le suivi de "
            "la VAD de votre district ;",
            f"{U.carte('👔 Équipe technique')} et "
            f"{U.carte('📓 Mon journal de bord')}.",
        ]),
        U.info("Les deux tableaux de bord sont bornés à <strong>votre "
               "district</strong> : vous voyez exactement le périmètre dont vous "
               "transcrivez les données. C'est le meilleur moyen de vérifier "
               "qu'une transcription est bien arrivée."),
        U.p("« Transcrire » signifie <strong>charger dans l'application</strong> les "
            "fichiers de données du terrain, pour qu'ils alimentent les rapports."),
        U.capture("transcription_accueil.png", "L'accueil de la Transcription."),
    ])))

    s.append(("preparer", "Préparer le dossier de dénombrement", "".join([
        U.p("Les données arrivent sous forme de fichiers <strong>.dta</strong> "
            "(format Stata). Rassemblez-les dans <strong>un seul dossier</strong> "
            "sur votre ordinateur. Trois fichiers sont <strong>obligatoires à la "
            "racine</strong> du dossier :"),
        U.arbre([
            "Dossier_de_mon_district/",
            "├── interview__diagnostics.dta   ← obligatoire",
            "├── DEN_MENAGE.dta               ← obligatoire",
            "├── segment_roster.dta           ← obligatoire",
            "└── Questionnaire/               ← sous-dossiers conservés (facultatif)",
            "    └── …",
        ]),
        U.attention("Les <strong>trois</strong> fichiers <code>.dta</code> doivent "
                    "être présents et placés <strong>directement</strong> dans le "
                    "dossier (pas dans un sous-dossier). Les autres fichiers et "
                    "sous-dossiers (ex. <code>Questionnaire/</code>) sont conservés."),
    ])))

    s.append(("transcrire", "Téléverser et transcrire", "".join([
        U.flux([
            ("Choisir", "le dossier complet"),
            ("Téléverser", "vers l'application"),
            ("Vérifier", "l'aperçu (contrôle)"),
            ("Transcrire", "intégration en base"),
        ]),
        U.capture("transcription_denombrement.png",
                  "La page de transcription du dénombrement."),
        U.etapes([
            f"Ouvrez {U.carte('🏠 Dénombrement')}.",
            "Cliquez pour <strong>choisir le dossier</strong> (le navigateur "
            "téléverse tout le dossier, sous-dossiers compris).",
            "L'application <strong>vérifie</strong> : les 3 fichiers requis sont "
            "présents, et les données correspondent bien à <strong>votre "
            "district</strong>.",
            "Consultez l'<strong>aperçu</strong> (ce qui sera ajouté ou modifié).",
            f"Cliquez sur {U.bouton('Transcrire')} pour intégrer les données.",
        ]),
        U.info("La transcription est <strong>incrémentale</strong> : elle ajoute les "
               "nouvelles lignes, met à jour celles qui ont changé, et ne supprime "
               "rien. Vous pouvez donc transcrire plusieurs vagues de données."),
        U.attention("Si les données ne correspondent pas à votre district affecté, "
                    "l'application <strong>refuse</strong> l'opération et n'écrit rien. "
                    "Vérifiez alors le dossier téléversé."),
    ])))

    # Ingestion des données VAD (2e phase de la collecte).
    s.append(("vadingest", "Transcrire les données de la Visite à domicile",
              "".join([
        U.p("Après le dénombrement vient la <strong>visite à domicile</strong> : "
            "l'entretien complet dans chaque ménage. C'est <strong>vous</strong> "
            "qui intégrez ces données dans l'application, comme pour le dénombrement, à partir de l'export "
            "Survey Solutions du questionnaire <strong>RSUe</strong>."),
        U.flux([
            ("Exporter", "depuis Survey Solutions"),
            ("Téléverser", "le dossier entier"),
            ("Vérifier", "l'aperçu affiché"),
            ("Transcrire", "vers la base"),
        ]),
        U.h3("1. Ce que doit contenir le dossier"),
        U.puces([
            "le fichier des <strong>ménages</strong> "
            "(<code>rsuefkt_…_pil.dta</code>) ;",
            "le fichier des <strong>membres</strong> (<code>RMen.dta</code>) ;",
            "les <strong>diagnostics</strong> "
            "(<code>interview__diagnostics.dta</code>), qui portent l'agent, le "
            "statut et la durée de chaque interview.",
        ]),
        U.info("Le nom du fichier des ménages contient la <strong>version du "
               "questionnaire</strong> : il changera à la prochaine version. "
               "L'application le reconnaît aussi <strong>à ses colonnes</strong> "
               "(<code>interview__key</code>, <code>CQ7</code>, <code>CQ9</code>, "
               "<code>nbmembre</code>) — un export renommé passe donc quand même."),
        U.h3("2. Téléverser puis transcrire"),
        U.etapes([
            f"Depuis l'accueil, ouvrez "
            f"{U.carte('🏠 Transcription — Visite à domicile')}.",
            "Choisissez le <strong>DOSSIER</strong> d'export (pas les fichiers un "
            "par un) et cliquez sur "
            f"{U.bouton('Téléverser et vérifier')}.",
            "Lisez l'<strong>aperçu</strong> : fichiers reconnus, nombre de lignes, "
            "districts présents, période de collecte, nombre d'agents.",
            f"Si tout est conforme, cliquez sur "
            f"{U.bouton('Transcrire vers la base de données')}.",
        ]),
        U.attention("Les ménages d'un <strong>autre district</strong> que le vôtre "
                    "sont <strong>écartés</strong> et signalés dans l'aperçu : le "
                    "reste du dossier est transcrit normalement. Le dossier est "
                    "refusé seulement si <em>rien</em> ne concerne votre district."),
        U.info("La transcription est <strong>additive</strong> : elle ajoute les "
               "nouvelles interviews, met à jour celles qui ont changé et ne "
               "supprime rien. Vous pouvez la relancer à chaque nouvel export."),
        U.astuce("Une fois la transcription faite, le "
                 "<strong>tableau de bord VAD</strong> s'ouvre pour l'Expert "
                 "Traitement, les Superviseurs Techniques et les Coordonnateurs. "
                 "Tant que vous n'avez pas transcrit, ils voient « aucune "
                 "donnée »."),
    ])))

    s.append(_sec_dashboard(
        "Vous voyez <strong>votre district en entier</strong> — le même périmètre "
        "que celui dont vous transcrivez les données."))

    s.append(("historique", "Suivre mes transcriptions", "".join([
        U.p("En bas de la page figure l'<strong>historique de vos transcriptions</strong> "
            "(date, événement, statut Réussi/Échec, détail). Chaque téléversement et "
            "chaque transcription y sont tracés, réussis comme échoués — utile pour "
            "vérifier ce qui a bien été intégré."),
    ])))
    return s


def _r_superviseur():
    s = []
    carte_decl = U.carte("📝 Déclaration des nombres de ménages dénombrés / "
                         "interviewés par les Agents")
    s.append(("poste", "Votre poste en bref", "".join([
        U.p("À la connexion, vous arrivez sur <strong>votre menu</strong>, qui "
            "propose :"),
        U.puces([
            f"{U.carte('📊 Tableau de bord — Dénombrement')} — le suivi de vos "
            "communes ;",
            f"{U.carte('🏠 Tableau de bord — Visite à domicile')} — à venir "
            "(données VAD pas encore intégrées) ;",
            f"{U.carte('👔 Équipe technique')} — l'encadrement affecté à votre "
            "district ;",
            f"{carte_decl} — la saisie des déclarations de vos agents ;",
            f"{U.carte('📓 Mon journal de bord')} — vos activités du jour.",
        ]),
    ])))
    s.append(_sec_selection("communes"))
    s.append(_sec_dashboard(
        "Vous voyez l'<strong>agrégat de vos communes</strong> : les vues district "
        "additionnent uniquement les communes dont vous avez la charge.",
        gps_note="La <strong>Carte GPS</strong> n'a pas de vue d'ensemble : elle "
                 "s'ouvre sur l'une de vos communes ; utilisez le sous-menu latéral "
                 "pour passer d'une commune/fokontany à l'autre."))

    # Déclarations des agents : propre au Superviseur Technique.
    s.append(("declaration",
              "Saisir les déclarations des agents (ménages dénombrés / interviewés)",
              "".join([
        U.p("Chaque agent <strong>déclare</strong> le nombre de ménages qu'il dit "
            "avoir dénombrés (phase de dénombrement) ou interviewés (VAD), jour par "
            "jour. <strong>C'est vous qui saisissez ces déclarations</strong> dans "
            "l'application, à partir d'un classeur Excel bâti sur le modèle fourni."),
        U.info("À quoi ça sert : l'application compare ce qui est "
               "<strong>déclaré</strong> et ce qui <strong>arrive réellement au "
               "serveur</strong>, <strong>pour les deux phases</strong>. "
               "Dénombrement : page <em>Par agent</em> du tableau de bord (un "
               "agent, une ligne ; cliquez sur une ligne pour le détail jour par "
               "jour) et feuilles <em>Écart par agent</em> et <em>Écart "
               "déclaration-serveur</em> du rapport Excel. Visite à domicile : "
               "page <em>Par agent</em> du tableau de bord VAD et feuille "
               "<em>Écart par agent</em> de son classeur. Un écart positif signale "
               "des données non synchronisées — ou une sur-déclaration."),
        U.flux([
            ("Ouvrir", "Déclaration des agents"),
            ("Choisir", "Dénombrement ou VAD"),
            ("Télécharger", "le modèle Excel"),
            ("Remplir", "puis téléverser"),
        ]),
        U.h3("1. Choisir la phase"),
        U.p("Après avoir ouvert la carte "
            f"{U.carte('📝 Déclaration des nombres de ménages…')}, choisissez :"),
        U.puces([
            f"{U.carte('🏠 Dénombrement')} — ménages <strong>dénombrés</strong> ;",
            f"{U.carte('🗣️ Visite à domicile (VAD)')} — ménages "
            "<strong>interviewés</strong>.",
        ]),
        U.h3("2. Le modèle Excel"),
        U.p("Téléchargez le modèle depuis la page : il est <strong>déjà rempli avec "
            "les codes de vos agents</strong> et les dates observées. Sa structure "
            "est simple — <strong>colonne 1 : le code de l'agent</strong> ; "
            "<strong>colonnes 2 à n : une date par colonne</strong> ; dans chaque "
            "cellule, le nombre déclaré."),
        U.tableur(
            ["code_agent", "05/09/2026", "06/09/2026", "07/09/2026"],
            [["EQ_MPKN_0001", "28", "31", "26"],
             ["EQ_MPKN_0002", "", "19", "22"],
             ["EQ_MPKN_0003", "17", "24", ""]],
            note="Une cellule VIDE = aucune déclaration ce jour-là. Ce n'est PAS "
                 "un zéro : rien n'est écrit en base pour cette date."),
        U.attention("Le classeur ne demande <strong>que le code</strong> de l'agent. "
                    "Son nom et son chef d'équipe sont déjà dans la base des agents "
                    "(remplie par l'Expert Traitement) : la déclaration s'y rattache "
                    "par ce code. La page de téléversement rappelle la correspondance "
                    "<em>code → agent → chef d'équipe</em> de vos agents, dans un "
                    "bloc « Vos agents » à déplier."),
        U.h3("3. Téléverser"),
        U.etapes([
            "Indiquez le <strong>classeur Excel</strong> rempli.",
            f"Cliquez sur {U.bouton('Transcrire vers la base de données')}.",
            "Lisez le <strong>bilan</strong> : déclarations ajoutées, mises à jour, "
            "inchangées, et la liste des <strong>cellules ignorées</strong>.",
        ]),
        U.info("La transcription est <strong>additive</strong> : elle ajoute les "
               "nouvelles déclarations, met à jour celles qui ont changé et ne "
               "supprime rien. Vous pouvez la relancer autant de fois que nécessaire "
               "— par exemple chaque semaine, avec les nouvelles colonnes de dates."),
        U.attention("Seuls les agents de <strong>votre périmètre</strong> sont "
                    "acceptés. Un code inconnu de la base, ou rattaché à d'autres "
                    "communes, est refusé <strong>ligne par ligne</strong> et "
                    "signalé dans le bilan : le reste du fichier passe quand même."),
        U.astuce("Vous pouvez ajouter ou retirer des colonnes de dates dans le "
                 "modèle. Les dates sont reconnues en date Excel, "
                 "<code>05/09/2026</code> ou <code>2026-09-05</code>."),
    ])))
    return s


def _r_coord_nationale():
    s = [_sec_selection("libre")]
    s.append(("equipe", "Le suivi « Équipe technique »", "".join([
        U.p("En plus de <em>Dénombrement</em> et <em>Visite à domicile</em>, vous "
            "disposez d'un troisième choix : <strong>Équipe technique</strong>."),
        U.p("En le choisissant pour un district, l'application affiche la "
            "<strong>fiche de l'encadrement affecté à ce district</strong> — et non "
            "les agents de terrain — groupé par rôle :"),
        U.puces([
            "Coordonnateur régionale (qui couvre le district) ;",
            "Superviseur Technique ;",
            "Traitement ;",
            "Expert survey.",
        ]),
        U.p("Chaque personne est présentée avec son nom, son téléphone, son e-mail "
            "et, le cas échéant, ses communes."),
        U.etapes([
            "Choisissez Province → Région → District.",
            f"Sélectionnez {U.carte('👥 Équipe technique')}.",
            f"Cliquez sur {U.bouton('Continuer')} : la fiche s'affiche.",
        ]),
    ])))
    s.append(_sec_dashboard(
        "Vous voyez le <strong>district choisi en entier</strong>."))
    return s


def _r_multi():
    s = [_sec_selection("multi")]
    s.append(_sec_dashboard(
        "Vous voyez le <strong>district sélectionné en entier</strong>."))
    return s


def _r_logistique(niveau):
    perimetre = ("votre district" if niveau == "district" else "vos communes")
    return [
        ("poste", "Votre poste en bref", "".join([
            U.p("À la connexion, vous arrivez sur l'<strong>Espace Logistique & "
                "Finances</strong>. C'est un <strong>guide</strong> tiré du manuel de "
                "formation, organisé en pages. Il n'y a pas de tableau de bord de "
                "dénombrement pour votre poste."),
            U.p(f"Votre périmètre : <strong>{perimetre}</strong>, rappelé sur la "
                "page d'accueil."),
            U.capture("logistique_accueil.png",
                      "L'accueil de l'espace Logistique & Finances."),
        ])),
        ("pages", "Les pages de l'espace logistique", "".join([
            U.puces([
                f"{U.carte('✅ Mes tâches par étape')} — les check-lists avant, "
                "pendant et après la formation et la collecte ;",
                f"{U.carte('💳 Paiement (Mvola)')} — la procédure de paiement en "
                "3 étapes et les règles à respecter ;",
                f"{U.carte('🗂️ Pièces à gérer')} — les pièces justificatives à "
                "réunir et à contrôler ;",
                f"{U.carte('📊 Budget de référence')} — le budget indicatif.",
            ]),
            U.p("Naviguez d'une page à l'autre par le menu en haut de l'espace."),
            U.info("Les <strong>outils transactionnels</strong> (exécution réelle "
                   "des paiements, téléversement des pièces scannées) sont affichés "
                   "« en cours de conception » : l'espace sert pour l'instant de "
                   "guide et de référence."),
        ])),
    ]


def _r_admin():
    s = []
    s.append(("poste", "Votre poste en bref", "".join([
        U.p("À la connexion, vous arrivez sur l'<strong>Espace Admin</strong>. Vous "
            "y gérez les comptes, les affectations et vous surveillez l'activité."),
    ])))
    s.append(("tableau", "Tableau de bord & journal", "".join([
        U.p("La page d'accueil de l'admin présente :"),
        U.puces([
            "le nombre de comptes par rôle et les personnes connectées ;",
            "le <strong>journal des connexions</strong> (qui, quel rôle, durée) et "
            "les <strong>tentatives échouées</strong> ;",
            "les <strong>transcriptions récentes</strong> (date, personne, district, "
            "événement, statut) ;",
            "la <strong>couverture des affectations</strong> (districts/communes "
            "sans responsable).",
        ]),
    ])))
    s.append(("utilisateurs", "Gérer les utilisateurs", "".join([
        U.p("La gestion des comptes se fait en trois pages :"),
        U.h3("Lister"),
        U.p("La liste affiche chaque compte, son rôle, ses coordonnées et un bouton "
            f"{U.bouton('Modifier')}. Vous pouvez activer/désactiver, réinitialiser "
            "ou supprimer un compte, et exporter la liste en CSV."),
        U.h3("Ajouter"),
        U.p("Le formulaire d'ajout saisit le nom, le rôle, les coordonnées, "
            "l'identifiant, le mot de passe et l'<strong>affectation</strong> "
            "(le formulaire s'adapte au rôle : district unique, plusieurs districts, "
            "ou district + communes). Les mots de passe sont hachés à l'insertion."),
        U.flux([
            ("Nom & rôle", "informations de base"),
            ("Coordonnées", "tél. / CIN / e-mail"),
            ("Identifiants", "login + mot de passe"),
            ("Affectation", "selon le rôle"),
        ]),
        U.h3("Import Excel"),
        U.p("Vous pouvez aussi créer plusieurs comptes d'un coup en important un "
            "fichier Excel (un modèle est fourni). L'ordre des colonnes du modèle "
            "correspond au formulaire d'ajout."),
        U.h3("Modifier"),
        U.p("Le bouton <strong>Modifier</strong> ouvre un formulaire pré-rempli. "
            "L'identifiant (login) n'est pas modifiable ; laissez le mot de passe "
            "vide pour ne pas le changer. L'affectation courante est pré-sélectionnée."),
        U.astuce("Pensez à changer le compte d'amorçage initial (RSU/RSU) dès la "
                 "mise en service, pour la sécurité."),
    ])))
    return s


# ===========================================================================
# Aiguillage
# ===========================================================================
_ROUTEUR = {
    "Traitement": _r_traitement,
    "Expert survey": _r_expert,
    "Superviseur Technique": _r_superviseur,
    "Coordonnateur Nationale": _r_coord_nationale,
    "Coordonnateur régionale": _r_multi,
    "Comités Techniques": _r_multi,
    "Logistique District": lambda: _r_logistique("district"),
    "Logistique Inter-Communale": lambda: _r_logistique("communes"),
    "Admin": _r_admin,
}


# Rôles disposant du tableau de bord VAD, et périmètre qu'il leur montre
# (source de vérité du routage : serveur_app._ROLES_VAD).
_ROLES_VAD = ("Coordonnateur Nationale", "Coordonnateur régionale",
              "Traitement", "Superviseur Technique", "Expert survey",
              "Comités Techniques", "Admin")
_PERIMETRE_VAD = {
    "Coordonnateur Nationale": "Vous voyez <strong>tous les districts</strong>.",
    "Coordonnateur régionale": "Vous voyez <strong>vos districts</strong>.",
    "Traitement": "Vous voyez <strong>votre district</strong>.",
    "Superviseur Technique": "Vous voyez <strong>vos communes</strong>.",
    "Expert survey": "Vous voyez <strong>votre district</strong>.",
    "Comités Techniques": "Vous voyez <strong>le district que vous avez "
                          "choisi</strong>, parmi vos districts.",
    "Admin": "Vous voyez <strong>le district que vous avez choisi</strong> "
             "(vous n'avez aucune restriction de zone).",
}

# Périmètre de LECTURE des journaux, par rôle (phrase insérée dans la section).
_PERIMETRE_JOURNAL_LECTURE = {
    "Coordonnateur Nationale": "pour <strong>tous les districts</strong>.",
    "Coordonnateur régionale": "pour <strong>vos districts</strong>.",
    "Admin": "pour <strong>tous les districts</strong>.",
}


def sections_role(role):
    """Sections du manuel d'un poste : les siennes, puis le JOURNAL DE BORD.

    Le journal est ajouté ICI, une seule fois, à partir des groupes de rôles de
    `utilisateurs` — ainsi aucun poste ne peut l'oublier, et un rôle déplacé d'un
    groupe à l'autre voit automatiquement la bonne version (écriture ou lecture)."""
    role = (role or "").strip()
    fabrique = _ROUTEUR.get(role)
    if fabrique:
        s = fabrique()
    else:
        # Rôle inconnu / générique : au moins la sélection + le tableau de bord.
        s = [_sec_selection("libre"),
             _sec_dashboard("Vous voyez le district que vous avez choisi.")]
    # Tableau de bord VAD : les rôles qui suivent la visite à domicile.
    if role in _ROLES_VAD:
        s.append(_sec_dashboard_vad(_PERIMETRE_VAD.get(role, "")))
    if role in utilisateurs.ROLES_JOURNAL_ECRITURE:
        s.append(_sec_journal_ecriture())
    elif role in utilisateurs.ROLES_JOURNAL_LECTURE:
        # L'Admin n'a pas de carte « Journaux des équipes » dans son espace : sa
        # barre porte « Journal », qui est le journal des CONNEXIONS (audit). On le
        # dit, sinon il cherchera au mauvais endroit.
        acces = None
        if role == "Admin":
            acces = ("Ouvrez l'adresse <code>/journal</code> de l'application. "
                     "(Le menu <strong>Journal</strong> de votre barre "
                     "d'administration est un AUTRE outil : le journal des "
                     "<em>connexions</em>.)")
        s.append(_sec_journal_lecture(
            _PERIMETRE_JOURNAL_LECTURE.get(role, "sur votre périmètre."),
            acces, par_adresse=(role == "Admin")))
    return s
