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
            "projection RGPH-3 2025, qualité, indicateurs clés.",
            "<strong>Par agent</strong> — production par agent enquêteur.",
            "<strong>Par zone</strong> — résultats par commune / fokontany.",
            "<strong>Carte GPS</strong> — position des ménages dénombrés.",
            "<strong>Capture GPS</strong> — taux de ménages géolocalisés.",
            "<strong>Qualité</strong> — carnet, scan, complétude.",
            "<strong>Historique</strong> — progression dans le temps.",
            "<strong>Segments multiples</strong> — codes de segment répétés dans "
            "un même fokontany (contrôle qualité).",
        ]),
        U.h3("Descendre au niveau commune, puis fokontany"),
        U.p("Sous les sections, un sous-menu <strong>Commune → Fokontany</strong> "
            "permet de préciser le périmètre : cliquez une commune pour la détailler, "
            "puis un fokontany pour le détail le plus fin."),
        U.h3("Exporter le rapport en Excel"),
        U.p("Le bouton <strong>Exporter rapport</strong> (en bas à droite) télécharge "
            "un classeur Excel de votre périmètre, avec quatre feuilles :"),
        U.puces([
            "<strong>Rapport global</strong> — couverture et qualité par commune "
            "et par fokontany ;",
            "<strong>Dénombrement par agent-jour</strong> — un tableau par chef "
            "d'équipe ;",
            "<strong>BaseDenParAgent</strong> — table plate (pour tableau croisé) ;",
            "<strong>segment_multiple</strong> — le rapport des segments multiples.",
        ]),
    ]
    if gps_note:
        corps.append(U.attention(gps_note))
    return ("dashboard", "Le tableau de bord de suivi", "".join(corps))


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
        "<strong>Visite à domicile</strong> — en cours de conception (les données "
        "ne sont pas encore intégrées).",
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
            "qui propose trois activités :"),
        U.puces([
            f"{U.carte('📊 Tableau de bord (suivi)')} — suivre le dénombrement de "
            "votre district ;",
            f"{U.carte('👥 Base Chefs d’Équipe & Agents')} — renseigner qui sont "
            "les chefs d'équipe et les agents ;",
            f"{U.carte('📦 Base de préchargement')} — générer les fichiers de "
            "préchargement pour les visites à domicile.",
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
        U.astuce("Modèles à télécharger directement : "
                 '<a href="/traitement/modele/chef.xlsx">modèle chefs d’équipe</a> · '
                 '<a href="/traitement/modele/agent.xlsx">modèle agents</a>.'),
    ])))

    # Préchargement.
    s.append(("prechargement", "Générer la base de préchargement", "".join([
        U.p("La <strong>base de préchargement</strong> prépare, à partir du "
            "dénombrement, les fichiers utilisés pour les visites à domicile. "
            "L'application la construit pour vous : vous choisissez seulement un "
            "<strong>mode d'affectation</strong> et vous téléchargez le résultat."),
        U.flux([
            ("Ouvrir", "Base de préchargement"),
            ("Choisir", "le mode d'affectation"),
            ("Générer", "l'application calcule"),
            ("Télécharger", "l'archive ZIP"),
        ]),
        U.capture("prechargement.png", "La page de génération du préchargement."),
        U.h3("Les modes d'affectation"),
        U.puces([
            "<strong>Dénombrement</strong> — aucune redistribution : chaque agent "
            "garde les ménages qu'il a dénombrés.",
            "<strong>Équilibré</strong> — répartit la charge (±10 %) en gardant les "
            "agents groupés.",
            "<strong>Équilibré fort</strong> — équilibrage plus poussé : un agent "
            "peut changer de fokontany.",
        ]),
        U.h3("Le résultat"),
        U.p("Vous obtenez une <strong>archive ZIP</strong> contenant deux fichiers :"),
        U.puces([
            "<strong>base_prechargement_…xlsx</strong> — le préchargement lui-même "
            "(3 feuilles : Ensemble, nouveau, e_fokontany) ;",
            "<strong>charge_agents_…xlsx</strong> — le récapitulatif de la charge "
            "par agent (pour contrôler l'équilibrage).",
        ]),
        U.etapes([
            f"Ouvrez {U.carte('📦 Base de préchargement')}.",
            "Choisissez le <strong>mode</strong> adapté.",
            f"Cliquez sur {U.bouton('Générer')} et patientez pendant le calcul.",
            "Téléchargez l'<strong>archive ZIP</strong> proposée.",
        ]),
        U.attention("La base de préchargement se construit à partir des données de "
                    "dénombrement <strong>déjà présentes</strong> pour votre district. "
                    "Si le dénombrement n'a pas encore été transcrit (par l'Expert "
                    "survey), le préchargement sera vide ou incomplet."),
    ])))
    return s


def _r_expert():
    s = []
    s.append(("poste", "Votre poste en bref", "".join([
        U.p("À la connexion, vous arrivez sur la page <strong>Transcription</strong>, "
            "qui propose deux choix :"),
        U.puces([
            f"{U.carte('🏠 Dénombrement')} — intégrer les données du recensement "
            "(disponible) ;",
            f"{U.carte('👣 Visite à domicile')} — en cours de conception.",
        ]),
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

    s.append(("historique", "Suivre mes transcriptions", "".join([
        U.p("En bas de la page figure l'<strong>historique de vos transcriptions</strong> "
            "(date, événement, statut Réussi/Échec, détail). Chaque téléversement et "
            "chaque transcription y sont tracés, réussis comme échoués — utile pour "
            "vérifier ce qui a bien été intégré."),
    ])))
    return s


def _r_superviseur():
    s = [_sec_selection("communes")]
    s.append(_sec_dashboard(
        "Vous voyez l'<strong>agrégat de vos communes</strong> : les vues district "
        "additionnent uniquement les communes dont vous avez la charge.",
        gps_note="La <strong>Carte GPS</strong> n'a pas de vue d'ensemble : elle "
                 "s'ouvre sur l'une de vos communes ; utilisez le sous-menu latéral "
                 "pour passer d'une commune/fokontany à l'autre."))
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


def sections_role(role):
    fabrique = _ROUTEUR.get((role or "").strip())
    if fabrique:
        return fabrique()
    # Rôle inconnu / générique : au moins la sélection + le tableau de bord.
    return [_sec_selection("libre"),
            _sec_dashboard("Vous voyez le district que vous avez choisi.")]
