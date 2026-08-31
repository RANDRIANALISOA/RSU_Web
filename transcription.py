# -*- coding: utf-8 -*-
"""
transcription.py — Rendu de la page « Transcription » de l'Expert survey.

L'Expert téléverse le dossier de données (récupéré depuis Survey Solutions sur son
ordinateur) ; le serveur range TOUS les fichiers du dossier sous
DATA_serveur/<code_district>/ (le dossier doit inclure au moins les 3 .dta requis)
puis fait la transcription incrémentale sur ces 3 tables (upsert maj_db : ajoute /
modifie, ne supprime rien).

Trois états d'affichage : saisie (choix du dossier) → aperçu (dry-run) → bilan.
Charte visuelle reprise de admin.py (_STYLE).
"""
import html

import admin

ESC = html.escape


def _entete() -> str:
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Transcription — RSU</title><style>{admin._STYLE}</style></head>'
            f'<body><div class="bar"><b>⬆ Transcription des données</b>'
            # Pas de lien « Application » : l'Expert survey n'a accès qu'à cette
            # page (le dashboard et /choix lui sont fermés, cf. serveur_app).
            f'<span class="sp"></span></div>'  # deconnexion = bandeau (haut droite)
            f'<div class="wrap">')


def _table_bilan(tables, titres) -> str:
    a, m, i = titres
    rows = "".join(
        f'<tr><td>{ESC(t["table"])}</td>'
        f'<td>{"reçu" if t["present"] else "absent"}</td>'
        f'<td>+{t["ajoutes"]}</td><td>~{t["modifies"]}</td>'
        f'<td>={t["inchanges"]}</td></tr>' for t in tables)
    return ('<table><tr><th>Table</th><th>Fichier</th>'
            f'<th>{a}</th><th>{m}</th><th>{i}</th></tr>' + rows + '</table>')


def _table_historique(historique) -> str:
    """Tableau de l'historique des transcriptions (date+heure, événement, statut)."""
    if not historique:
        return ('<p><small>Aucune opération enregistrée pour l’instant.</small></p>')
    rows = "".join(
        f'<tr><td>{ESC(x["quand_court"])}</td>'
        f'<td>{ESC(x["evenement"])}</td>'
        f'<td><span class="pill {"ok" if x["statut"] == "Réussi" else "ko"}">'
        f'{ESC(x["statut"])}</span></td>'
        f'<td>{ESC(x["detail"])}</td></tr>' for x in historique)
    return ('<table><tr><th>Date &amp; heure</th><th>Opération</th>'
            '<th>Statut</th><th>Détail</th></tr>' + rows + '</table>')


_CSS_CHOIX = """
<style>
.choix{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  gap:16px;margin-top:16px}
.ca{display:block;text-decoration:none;color:inherit;background:#fff;
  border:1.5px solid #e2e8f0;border-radius:14px;padding:20px 20px 18px;
  transition:.15s;position:relative}
.ca:hover{border-color:#2563eb;box-shadow:0 12px 26px rgba(37,99,235,.14);
  transform:translateY(-2px)}
.ca .ic{font-size:30px;line-height:1;margin-bottom:10px}
.ca .t{font-weight:700;font-size:16px;margin-bottom:6px}
.ca .d{font-size:13px;color:#64748b;line-height:1.5}
.ca .go{margin-top:12px;font-weight:700;color:#2563eb;font-size:13px}
.ca.off{cursor:not-allowed;background:#fafbfc}
.ca.off:hover{border-color:#f0d38a;box-shadow:none;transform:none}
.ruban{display:inline-block;margin-top:12px;font-size:11px;font-weight:700;
  color:#8a5a00;background:#fff4d6;border:1px solid #f0d38a;border-radius:999px;
  padding:3px 11px}
</style>"""


def page_choix_transcription(district_txt) -> str:
    """Choix de l'Expert survey : transcription Dénombrement ou Visite à domicile."""
    h = [_entete(), _CSS_CHOIX, '<h1>Transcription des données</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>. '
         'Choisissez le type de données à transcrire.</div>',
         '<div class="choix">',
         '<a class="ca" href="/transcription/denombrement">'
         '<div class="ic">📋</div><div class="t">Transcription — Dénombrement</div>'
         '<div class="d">Téléverser puis transcrire les fichiers .dta du '
         'dénombrement (DEN_MENAGE, segment_roster, interview__diagnostics).</div>'
         '<div class="go">Ouvrir →</div></a>',
         '<a class="ca off" href="/transcription/vad">'
         '<div class="ic">🏠</div><div class="t">Transcription — Visite à domicile</div>'
         '<div class="d">Transcription des données de visite à domicile (VAD).</div>'
         '<span class="ruban">En cours de conception</span></a>',
         '<a class="ca" href="/equipe">'
         '<div class="ic">👔</div><div class="t">Équipe technique</div>'
         '<div class="d">Consulter l’encadrement (Coordonnateur régional, '
         'Superviseurs Techniques par axe, Traitement, Expert survey) affecté à '
         'votre district.</div><div class="go">Ouvrir →</div></a>',
         '<a class="ca" href="/journal">'
         '<div class="ic">📓</div><div class="t">Mon journal de bord</div>'
         '<div class="d">Consigner les activités que vous avez réalisées dans la '
         'journée.</div><div class="go">Ouvrir →</div></a>',
         '</div>', '</div></body></html>']
    return "".join(h)


def page_vad_transcription(district_txt) -> str:
    """Page « Visite à domicile : pas encore disponible » (structure BD VAD absente)."""
    h = [_entete(),
         '<h1>Transcription — Visite à domicile</h1>',
         '<div class="note" style="background:#fff4d6;border-color:#f0d38a">'
         '<b>Pas encore disponible.</b> La structure de la base de données pour la '
         'visite à domicile n’est <b>pas encore définie</b> : cette transcription '
         'est en cours de conception et sera activée quand les données VAD '
         'existeront.</div>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>.</div>',
         '<p><a href="/transcription">← Retour au choix</a></p>',
         '</div></body></html>']
    return "".join(h)


def page_transcription(district_txt, apercu=None, resultat=None,
                       message=None, erreur=None, historique=None) -> str:
    h = [_entete(),
         '<p style="margin:0 0 6px"><a href="/transcription">← Choix du type de '
         'transcription</a></p>',
         '<h1>Transcription de la base de dénombrement</h1>',
         f'<div class="note">District d’affectation : <b>{ESC(district_txt)}</b>. '
         f'Les fichiers seront rangés côté serveur sous ce district.</div>']
    if message:
        h.append(f'<div class="msg">{ESC(message)}</div>')
    if erreur:
        h.append(f'<div class="err">{erreur}</div>')      # HTML autorisé (listes)

    if resultat:
        h.append('<h2>Bilan de la transcription</h2>')
        h.append(_table_bilan(resultat["tables"], ("Ajoutées", "Modifiées", "Inchangées")))
        t = resultat["total"]
        h.append(f'<p><b>Total : +{t["ajoutes"]} ajoutées · ~{t["modifies"]} '
                 f'modifiées · ={t["inchanges"]} inchangées.</b></p>')
        h.append('<p><a href="/transcription/denombrement">↻ Nouvelle transcription</a></p>')
    elif apercu:
        h.append('<h2>Aperçu — rien n’est encore écrit</h2>')
        h.append(f'<div class="note">Fichiers reçus : '
                 f'<b>{ESC(", ".join(apercu.get("fichiers", [])))}</b></div>')
        h.append(_table_bilan(apercu["tables"], ("À ajouter", "À modifier", "Inchangées")))
        h.append('<form method="post" action="/transcription/transcrire" '
                 'style="margin-top:14px">'
                 '<button>Transcrire (appliquer)</button> '
                 '<a href="/transcription/denombrement" style="margin-left:12px">Recommencer</a></form>')
    else:
        h.append('<h2>1. Sélectionner le dossier des données</h2>')
        h.append(
            '<form method="post" action="/transcription/upload" '
            'enctype="multipart/form-data" class="grid-form">'
            '<div><label>Dossier des données du dénombrement (contenant au moins '
            'DEN_MENAGE.dta, segment_roster.dta et interview__diagnostics.dta)</label>'
            '<input type="file" name="fichiers" webkitdirectory multiple required></div>'
            '<div style="align-self:end"><button>Téléverser</button></div></form>')
        h.append('<div class="note">Choisissez le <b>dossier</b> sur votre ordinateur : '
                 '<b>tous les fichiers et sous-dossiers</b> qu’il contient sont '
                 'téléversés côté serveur (y compris un éventuel dossier '
                 '<b>Questionnaire</b>), en conservant leur arborescence. Le dossier '
                 'doit inclure au moins les 3 fichiers .dta requis, à sa racine. Vous '
                 'verrez ensuite un aperçu avant d’appliquer. La transcription '
                 '<b>ajoute</b> les nouveaux enregistrements, <b>met à jour</b> les '
                 'modifiés et <b>ne supprime rien</b>.</div>')

    # Historique des opérations de CET expert (téléversements + transcriptions,
    # réussis ou non), le plus récent d'abord.
    h.append('<h2>Historique de mes transcriptions</h2>')
    h.append(_table_historique(historique))
    h.append('</div></body></html>')
    return "".join(h)
