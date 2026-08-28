# -*- coding: utf-8 -*-
"""
logistique.py — Espace « Logistique & Finances » des Responsables Logistiques.

Rôles concernés (cf. utilisateurs.py) : **Logistique District** (niveau district)
et **Logistique Inter-Communale** (1 à 5 communes d'un district). Ces rôles n'accèdent PAS au
tableau de bord des données : ils disposent d'un espace dédié, construit à partir
du manuel de formation « FORMATIONLOG ».

Cette première version est un GUIDE + SUIVI (pas de base de données finances/pièces
pour l'instant) :
  - accueil (affectation + accès aux sections),
  - tâches par étape (check-lists avant/pendant/après formation, collecte),
  - procédure de paiement Mvola (3 étapes) + règles,
  - pièces à gérer,
  - budget de référence.
Les OUTILS transactionnels (paiement réel, téléversement des scans) sont affichés
« en cours de conception » (comme la Visite à domicile).

Charte visuelle reprise de admin.py (_STYLE).
"""
import html

import admin

ESC = html.escape

# Sections de l'espace (clé -> libellé de menu).
SECTIONS = (
    ("accueil", "Accueil"),
    ("taches", "Mes tâches"),
    ("paiement", "Paiement (Mvola)"),
    ("pieces", "Pièces à gérer"),
    ("budget", "Budget de référence"),
)


_CSS = """
<style>
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;
  margin-top:14px}
.ca{display:block;text-decoration:none;color:inherit;background:#fff;
  border:1.5px solid #e2e8f0;border-radius:14px;padding:18px;transition:.15s}
.ca:hover{border-color:#2563eb;box-shadow:0 12px 26px rgba(37,99,235,.14);
  transform:translateY(-2px)}
.ca .ic{font-size:26px;margin-bottom:8px}
.ca .t{font-weight:700;font-size:15px;margin-bottom:4px}
.ca .d{font-size:12.5px;color:#64748b;line-height:1.5}
.etape{background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;margin:12px 0;
  overflow:hidden}
.etape>summary{cursor:pointer;padding:13px 16px;font-weight:700;font-size:14px;
  background:#f8fafc;list-style:none}
.etape>summary::-webkit-details-marker{display:none}
.etape>summary:before{content:"▸ ";color:#2563eb}
.etape[open]>summary:before{content:"▾ "}
.etape ul{margin:6px 0 12px;padding:0 18px 0 16px;list-style:none}
.etape li{padding:6px 0 6px 4px;font-size:13.5px;line-height:1.5;
  border-top:1px solid #f1f5f9;display:flex;gap:9px;align-items:flex-start}
.etape li:first-child{border-top:none}
.etape li input{margin-top:3px;flex:none;width:16px;height:16px}
.steps{counter-reset:s;margin-top:12px}
.step{background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:14px 16px 14px 54px;
  position:relative;margin:10px 0}
.step:before{counter-increment:s;content:counter(s);position:absolute;left:14px;top:14px;
  width:28px;height:28px;border-radius:50%;background:#2563eb;color:#fff;font-weight:800;
  display:flex;align-items:center;justify-content:center;font-size:14px}
.step .t{font-weight:700;margin-bottom:4px}
.step .d{font-size:13px;color:#475569;line-height:1.55}
.ruban{display:inline-block;font-size:11px;font-weight:700;color:#8a5a00;
  background:#fff4d6;border:1px solid #f0d38a;border-radius:999px;padding:3px 11px}
.avenir{background:#fff8e6;border:1px dashed #f0d38a;border-radius:10px;padding:12px 14px;
  font-size:13px;margin:12px 0}
.tag{display:inline-block;font-size:11px;font-weight:700;color:#334155;background:#eef2f7;
  border-radius:6px;padding:2px 8px;margin:2px 4px 2px 0}
</style>"""


def _entete(actif, contexte) -> str:
    lien = lambda k, t: (f'<a href="/logistique/{k}" style="color:#fff;font-weight:600">{t}</a>'
                         if k == actif else f'<a href="/logistique/{k}">{t}</a>')
    if actif == "accueil":
        lien = lambda k, t: (f'<a href="/logistique" style="color:#fff;font-weight:600">{t}</a>'
                             if k == "accueil" else
                             (f'<a href="/logistique/{k}">{t}</a>'))
    liens = "".join(lien(k, t) for k, t in SECTIONS)
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Logistique & Finances — RSU</title>'
            f'<style>{admin._STYLE}</style>{_CSS}</head>'
            f'<body><div class="bar"><b>📦 Logistique &amp; Finances</b>'
            f'{liens}<span class="sp"></span></div>'  # deconnexion = bandeau (haut droite)
            f'<div class="wrap">')


def _bloc_affectation(contexte) -> str:
    role = ESC(contexte.get("role", ""))
    dist = ESC(contexte.get("district_txt", "—"))
    communes = contexte.get("communes", [])
    if communes:
        tags = "".join(f'<span class="tag">{ESC(c)}</span>' for c in communes)
        zone = (f'District <b>{dist}</b> — communes : {tags}')
    else:
        zone = f'District <b>{dist}</b> (niveau district)'
    return (f'<div class="note"><b>{role}</b><br>{zone}</div>')


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_accueil(contexte) -> str:
    cartes = "".join(
        f'<a class="ca" href="/logistique/{k}"><div class="ic">{ic}</div>'
        f'<div class="t">{t}</div><div class="d">{d}</div></a>'
        for k, t, ic, d in (
            ("taches", "Mes tâches par étape", "✅",
             "Ce qu'il faut faire avant, pendant et après la formation, puis "
             "pendant la collecte."),
            ("paiement", "Paiement (Mvola)", "💳",
             "La procédure de paiement en 3 étapes et les règles à respecter."),
            ("pieces", "Pièces à gérer", "🗂️",
             "Les documents à préparer, faire signer, scanner et archiver."),
            ("budget", "Budget de référence", "📊",
             "Les lignes de dépenses et montants unitaires de référence.")))
    return (_entete("accueil", contexte)
            + '<h1>Espace Logistique &amp; Finances</h1>'
            + _bloc_affectation(contexte)
            + '<div class="cards">' + cartes + '</div>'
            + '<div class="avenir">ℹ️ Les <b>outils transactionnels</b> '
              '(exécution des paiements, téléversement des pièces scannées) sont '
              '<b>en cours de conception</b>. Cet espace fournit pour l’instant le '
              '<b>guide de travail</b> et le <b>suivi</b> de vos tâches.</div>'
            + '</div></body></html>')


def _etape(titre, items, ouvert=False) -> str:
    lis = "".join(f'<li><input type="checkbox">{ESC(x)}</li>' for x in items)
    return (f'<details class="etape"{" open" if ouvert else ""}>'
            f'<summary>{ESC(titre)}</summary><ul>{lis}</ul></details>')


def page_taches(contexte) -> str:
    h = [_entete("taches", contexte), '<h1>Mes tâches par étape</h1>',
         '<div class="note">Cochez au fur et à mesure (aide-mémoire, non enregistré). '
         'Tiré du manuel de formation des Responsables Logistiques.</div>']
    h.append(_etape("① Avant la formation", [
        "Préparer à l'avance la salle de formation.",
        "Faire émarger les autorités locales réunies, scanner la fiche de présence "
        "et l'envoyer sur le Drive.",
        "Constituer/tenir la liste des candidats retenus dans Excel.",
        "Se coordonner pour convoquer toute l'équipe à la formation.",
        "Recueillir pour chaque candidat : nom et prénom, CIN, numéro de téléphone "
        "avec compte Mvola (rappeler d'ouvrir un compte Mvola si absent).",
        "Préparer tout le matériel nécessaire à la formation.",
    ], ouvert=True))
    h.append(_etape("② Pendant la formation", [
        "Vérifier chaque jour la présence de tous les participants.",
        "Compiler dans Excel et envoyer la liste avec les informations des candidats.",
        "Vérifier Nom, CIN et numéro Mvola et les saisir dans Excel.",
        "Expliquer l'argent et le matériel prévus pour la formation et le travail.",
        "Contrôler les entrées/sorties de l'équipe en formation.",
        "Scanner les fiches de présence et les archiver dans le dossier prévu.",
        "Envoyer l'Excel des participants jusqu'à la fin (indemnité de formation "
        "seulement pour ceux qui terminent).",
        "Préparer dans Excel la liste des personnes retenues pour le travail.",
    ]))
    h.append(_etape("③ Après la formation / avant le début du travail", [
        "Lire et bien expliquer le contenu du contrat.",
        "Faire signer le contrat aux membres retenus.",
        "Scanner le contrat et l'archiver dans le dossier prévu.",
        "Envoyer le scan du contrat + l'Excel des travailleurs + l'indemnité 60%.",
        "Distribuer le matériel à chaque équipe et tenir le compte avec une fiche "
        "de décharge.",
    ]))
    h.append(_etape("④ Pendant la collecte de données", [
        "Suivre l'utilisation du véhicule et du carburant (fiche de bord).",
        "Vérifier le paiement des Chefs Fokontany et guides locaux (avec fiche de "
        "présence).",
        "Compter par commune les fiches de consentement : utilisées, abîmées, "
        "restantes en main, chaque jour.",
        "Signaler à temps les équipes qui ne travaillent pas ou ont abandonné.",
        "Rassembler et remettre les pièces au chef-lieu du district (présences, "
        "contrats, factures).",
        "Récupérer tout le matériel prêté à la fin du travail (souches de fiches "
        "de consentement, OM…).",
    ]))
    h.append('</div></body></html>')
    return "".join(h)


def page_paiement(contexte) -> str:
    h = [_entete("paiement", contexte),
         '<h1>Paiement <span style="font-weight:400">(Mobile Money — Mvola)</span></h1>',
         '<div class="avenir"><span class="ruban">En cours de conception</span> '
         '&nbsp;L\'<b>exécution des paiements dans l\'application</b> et le '
         '<b>téléversement des justificatifs</b> ne sont pas encore disponibles. '
         'Voici la procédure et les règles à appliquer (manuel).</div>',
         '<h2>Règles à respecter</h2>',
         '<div class="etape" open><ul style="list-style:none;padding:8px 16px 14px">']
    regles = [
        "Le paiement se fait UNIQUEMENT via un compte Mobile Money (Mvola) certifié.",
        "La liste Excel des participants doit être prête au plus tard 2 jours après "
        "le début de la formation, et envoyée au 4e jour pour paiement.",
        "Toujours disposer des pièces justificatives AVANT d'exécuter un paiement.",
        "Scanner les justificatifs dès leur réception et les ranger aussitôt.",
        "Nommer le fichier scanné au nom de la personne concernée, ou au nom de la "
        "commune/du district si la pièce concerne plusieurs personnes.",
        "Vérifier le contenu avant tout envoi ; ne pas attendre la dernière minute.",
        "Note de frais, facture et tableau de bord doivent être contre-signés par le "
        "binôme (Superviseur Technique) ou certifiés par le supérieur.",
        "Ranger : papiers dans chemise/classeur ; fichiers Excel et scans dans un "
        "dossier de l'ordinateur ET sur le Drive.",
        "Compléter un district entier avant de lancer le paiement de ce district.",
    ]
    h.append("".join(f'<li style="padding:6px 0;border-top:1px solid #f1f5f9;'
                     f'font-size:13.5px;line-height:1.5">• {ESC(x)}</li>'
                     for x in regles))
    h.append('</ul></div>')
    h.append('<h2>Procédure en 3 étapes</h2><div class="steps">')
    for t, d in (
        ("Constituer le fichier source",
         "Saisie 1 : liste issue de l'évaluation des dossiers (CE ou AE). "
         "Saisie 2 : mises à jour lors des convocations / de la formation. "
         "Saisie 3 : mise au format du modèle."),
        ("Préparer le paiement",
         "Copier-coller (en valeurs) les éléments du fichier source vers le fichier "
         "modèle. Saisir tous les montants correspondants. Répercuter les éventuelles "
         "modifications sur la liste."),
        ("Envoyer à l'UGP",
         "Transmettre la liste à l'UGP avec le scan des pièces justificatives "
         "(scanner les pièces, nommer au nom de la personne ou de la commune si "
         "plusieurs personnes figurent sur la pièce).")):
        h.append(f'<div class="step"><div class="t">{ESC(t)}</div>'
                 f'<div class="d">{ESC(d)}</div></div>')
    h.append('</div>')
    h.append('<h2>Format Excel (rappel)</h2>'
             '<div class="etape" open><ul style="list-style:none;padding:8px 16px 14px">'
             '<li style="padding:6px 0;font-size:13.5px">• Noms et prénoms en '
             '<b>MAJUSCULES</b> (fonction <code>MAJUSCULE()</code>).</li>'
             '<li style="padding:6px 0;border-top:1px solid #f1f5f9;font-size:13.5px">'
             '• CIN et numéro Mvola en <b>format texte</b>, sans espace, avec une '
             'apostrophe devant le nombre à la saisie.</li>'
             '<li style="padding:6px 0;border-top:1px solid #f1f5f9;font-size:13.5px">'
             '• Objectif : <b>zéro doublon</b>.</li></ul></div>')
    h.append('</div></body></html>')
    return "".join(h)


def page_pieces(contexte) -> str:
    pieces = [
        ("Ordre de Mission (OM)", "Autorise un agent à effectuer une mission et en "
         "précise l'objet, le lieu et la durée."),
        ("Fiche de présence", "Émargement (formation, réunions) ; à scanner et "
         "archiver."),
        ("Contrat", "Accord écrit employeur/employé : travail, rémunération, durée, "
         "lieu et conditions."),
        ("Note de frais", "Dépenses engagées ; contre-signée par le binôme / "
         "certifiée par le supérieur."),
        ("Carte d'Identité Nationale (CIN)", "Pièce d'identité du bénéficiaire "
         "(paiement)."),
        ("Facture", "Justificatif d'achat / de dépense."),
        ("Tableau de bord", "Suivi (dont carburant du véhicule) ; contre-signé."),
        ("Scan de pièce", "Version numérisée d'une pièce, nommée au nom de la "
         "personne ou de la commune."),
        ("Photo pour archive", "Preuve photographique à conserver."),
        ("Fiche de consentement", "Consentement du ménage ; comptée par commune "
         "(utilisée / abîmée / restante)."),
        ("Fiche de décharge", "Remise/retour de matériel à une équipe."),
    ]
    rows = "".join(f'<tr><td><b>{ESC(n)}</b></td><td>{ESC(d)}</td></tr>'
                   for n, d in pieces)
    return (_entete("pieces", contexte)
            + '<h1>Pièces à gérer</h1>'
            + '<div class="avenir"><span class="ruban">En cours de conception</span> '
              '&nbsp;Le <b>téléversement des pièces scannées</b> dans l\'application '
              'n\'est pas encore disponible. En attendant : scanner, nommer '
              'correctement et ranger sur l\'ordinateur et le Drive.</div>'
            + '<table><tr><th>Pièce</th><th>Rôle / description</th></tr>'
            + rows + '</table>'
            + '</div></body></html>')


# Lignes de budget de référence (manuel) : (libellé, durée, unité, montant/unité Ar).
_BUDGET = [
    ("Indemnité du comité d'évaluation des dossiers CE (3 personnes)", "7", "j", "37 500"),
    ("Location des salles au niveau district (salle, sono, projecteur, groupe)", "6", "j", "100 000"),
    ("Indemnités des chefs d'équipe pendant la formation", "6", "j", "10 000"),
    ("DATA pendant la formation des chefs d'équipe", "6", "j", "1 000"),
    ("Indemnité des chefs d'équipe", "36", "j", "45 000"),
    ("DATA des chefs d'équipe pendant la formation AE", "6", "j", "1 000"),
    ("Indemnité tablette des chefs d'équipe", "36", "j", "15 000"),
    ("Crédit de communication pour les CE", "", "fft", "30 000"),
    ("DATA pour les CE pendant la collecte", "36", "j", "3 000"),
    ("Déplacement des chefs d'équipe vers les communes (aller-retour)", "", "fft", "70 000"),
    ("Indemnité du comité d'évaluation des dossiers AE (4 personnes)", "10", "j", "37 500"),
    ("Location des salles au niveau commune", "6", "j", "100 000"),
    ("Indemnités de formation des AE", "6", "j", "10 000"),
    ("DATA pendant la formation des AE", "6", "j", "1 000"),
    ("Déploiement des chefs d'équipe inter-fokontany", "23", "j", "20 000"),
    ("Location salle quartier général CE/AE", "23", "j", "2 000"),
    ("Indemnité journalière des AE", "23", "j", "35 000"),
    ("DATA envoi des données pendant la collecte AE (incl. MAJ appli)", "23", "j", "1 000"),
    ("Indemnité tablette et data AE", "23", "j", "15 000"),
    ("Crédit de communication pour les AE", "", "fft", "10 000"),
    ("Déploiement des enquêteurs vers les fokontany", "", "fft", "20 000"),
    ("Frais de guide (Komity loharano, AC…)", "3", "j", "10 000"),
    ("Coordination chef fokontany (réunion CAA / communautaire)", "", "j", "10 000"),
    ("Petite caisse (en cas de besoin)", "", "", ""),
]


def page_budget(contexte) -> str:
    rows = "".join(
        f'<tr><td>{ESC(lib)}</td><td style="text-align:center">{ESC(d)}</td>'
        f'<td style="text-align:center">{ESC(u)}</td>'
        f'<td style="text-align:right">{ESC(m)}{" Ar" if m else ""}</td></tr>'
        for lib, d, u, m in _BUDGET)
    return (_entete("budget", contexte)
            + '<h1>Budget de référence</h1>'
            + '<div class="note">Montants unitaires de référence (manuel). '
              '<b>fft</b> = forfait ; <b>j</b> = par jour. Montants en Ariary.</div>'
            + '<table><tr><th>Ligne de dépense</th><th>Durée</th><th>Unité</th>'
              '<th style="text-align:right">Montant / unité</th></tr>'
            + rows + '</table>'
            + '</div></body></html>')
