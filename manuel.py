# -*- coding: utf-8 -*-
"""manuel.py — Manuel d'utilisation intégré, ADAPTÉ AU RÔLE de l'utilisateur.

Chaque poste (Traitement, Expert survey, Superviseur Technique, Coordonnateur…)
voit un guide qui lui est propre : où il arrive après connexion, ce qu'il peut
faire, étape par étape, avec des illustrations (schémas de flux, maquettes des
fichiers Excel façon tableur, arborescence du dossier à téléverser).

Découpage :
    manuel_ui.py     -> briques de rendu, illustrations, styles (réutilisables) ;
    manuel_roles.py  -> intro + sections propres à chaque rôle ;
    manuel.py (ici)  -> sections communes à tous + assemblage de la page.

Point d'entrée : `page_manuel(role)` -> HTML complet, servi par serveur_app via
`_html()` (bandeau + « no-store » injectés là ; liens href="/…" préfixés).
"""

import html as _h

import manuel_ui as U
from manuel_roles import intro_role, sections_role


# ===========================================================================
# Sections communes (tous les rôles)
# ===========================================================================
def _sections_communes():
    s = []

    s.append(("connexion", "Se connecter à l'application", "".join([
        U.p("L'application s'ouvre dans un <strong>navigateur web</strong> "
            "(Chrome, Firefox, Edge…) : rien à installer. Vous y accédez par "
            "l'adresse fournie par l'administrateur."),
        U.etapes([
            "Ouvrez l'adresse de l'application dans votre navigateur.",
            "Saisissez votre <strong>identifiant</strong> et votre "
            "<strong>mot de passe</strong>, communiqués par l'administrateur.",
            f"Cliquez sur {U.bouton('Se connecter')}.",
        ]),
        U.capture("login.png", "La page de connexion."),
        U.p("Après la connexion, vous arrivez directement sur "
            "<strong>votre espace de travail</strong> (il dépend de votre rôle)."),
        U.attention("Vos identifiants sont <strong>personnels</strong>. Ne les "
                    "partagez pas : toutes vos actions sont journalisées à votre nom."),
    ])))

    s.append(("bandeau", "Le bandeau (en haut à droite)", "".join([
        U.p("Une fois connecté, un bandeau apparaît en haut à droite de "
            "<strong>chaque page</strong>. Il rappelle qui vous êtes et donne "
            "les raccourcis essentiels :"),
        U.capture("bandeau.png",
                  "Le bandeau, en haut à droite de chaque page.",
                  U.illus_bandeau()),
        U.puces([
            "<strong>Mon espace</strong> — revient à votre page principale.",
            "<strong>Mot de passe</strong> — changer votre mot de passe.",
            "<strong>Manuel</strong> — ouvre ce guide.",
            "<strong>Déconnexion</strong> — ferme votre session en sécurité.",
        ]),
    ])))

    s.append(("motdepasse", "Changer mon mot de passe", "".join([
        U.p("Vous pouvez modifier votre mot de passe à tout moment, sans passer "
            "par l'administrateur."),
        U.etapes([
            f"Dans le bandeau, cliquez sur {U.bouton('🔑 Mot de passe')}.",
            "Saisissez votre <strong>mot de passe actuel</strong>.",
            "Saisissez le <strong>nouveau mot de passe</strong> (au moins "
            "6 caractères) puis <strong>confirmez-le</strong>.",
            f"Cliquez sur {U.bouton('Enregistrer')}.",
        ]),
        U.capture("motdepasse.png", "Le formulaire de changement de mot de passe."),
        U.astuce("Le nouveau mot de passe sera demandé à votre prochaine "
                 "connexion. Choisissez-en un que vous êtes seul à connaître."),
    ])))

    s.append(("securite", "Session & confidentialité", "".join([
        U.p("Les données du RSU sont <strong>nominatives</strong> (noms, adresses, "
            "positions GPS de ménages). Leur protection est une priorité."),
        U.puces([
            "Votre session se <strong>ferme automatiquement</strong> après "
            "30 minutes d'inactivité : vous devrez vous reconnecter.",
            "Terminez toujours par <strong>Déconnexion</strong> sur un poste "
            "partagé.",
            "Ne diffusez jamais de captures ou d'exports contenant des données "
            "de ménages hors du cadre de votre mission.",
        ]),
    ])))

    s.append(("aide", "Besoin d'aide ?", "".join([
        U.p("En cas de difficulté (identifiant oublié, accès à une zone, "
            "comportement inattendu), contactez <strong>l'administrateur</strong> "
            "de l'application, qui peut vérifier votre compte, votre affectation "
            "et le journal des connexions."),
    ])))

    return s


# ===========================================================================
# Assemblage de la page
# ===========================================================================
def page_manuel(role):
    """HTML complet du manuel pour un rôle donné (libellé de responsabilité)."""
    role = (role or "").strip()
    intro = intro_role(role)
    propres = sections_role(role)
    sections = propres + _sections_communes()
    n_role = len(propres)

    # Ancre du groupe « Généralités » = 1re section commune (pas de double id).
    id_gen = sections[n_role][0] if n_role < len(sections) else "top"
    toc = ['<h3>Sommaire</h3>', '<a class="grp" href="#top">Votre poste</a>']
    corps = []
    for i, (sid, titre, html_sec) in enumerate(sections):
        if i == n_role:
            toc.append(f'<a class="grp" href="#{id_gen}">'
                       'Généralités (tous les rôles)</a>')
        toc.append(f'<a href="#{sid}">{_h.escape(titre)}</a>')
        corps.append(
            f'<section class="man-sec" id="{sid}">'
            f'<h2><span class="n">{i + 1}</span>{_h.escape(titre)}</h2>'
            f'{html_sec}</section>')

    page = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RSU 2026 — Manuel d'utilisation</title>
<style>__CSS__</style></head><body>
<div class="man-wrap">
  <nav class="man-toc">__TOC__</nav>
  <div class="man-main" id="top">
    <div class="man-tete">
      <span class="ruban">Manuel d'utilisation · __ROLE__</span>
      <h1>Guide de l'application RSU 2026</h1>
      <p>__INTRO__</p>
    </div>
    <div class="man-toolbar">
      <button type="button" class="man-btn p" onclick="window.print()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round"
          stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/>
          <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
          <rect x="6" y="14" width="12" height="8"/></svg>
        Imprimer / Enregistrer en PDF</button>
      <a class="man-btn" href="/">← Retour à mon espace</a>
    </div>
    __CORPS__
    <div class="man-actions"><a href="/">← Retour à mon espace</a></div>
  </div>
</div></body></html>"""
    return (page
            .replace("__CSS__", U.CSS)
            .replace("__TOC__", "".join(toc))
            .replace("__ROLE__", _h.escape(role or "Utilisateur"))
            .replace("__INTRO__", intro)
            .replace("__CORPS__", "".join(corps)))
