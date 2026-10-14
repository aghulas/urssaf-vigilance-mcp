---
name: "urssaf-verifier-attestation-vigilance"
description: "Vérifier une attestation de vigilance URSSAF reçue d'un fournisseur ou sous-traitant de l'OGEC Sainte-Marie via le connecteur urssaf-vigilance, la rapprocher du devis et du tableau de suivi, puis l'archiver."
---

# Vérifier une attestation de vigilance URSSAF

À utiliser dès qu'une attestation de vigilance (« attestation de fourniture des déclarations sociales et de paiement des cotisations ») arrive — par mail, par la maîtrise d'œuvre (FreRo) ou en PDF déposé — ou quand Rémi demande de contrôler, revoir ou relancer les attestations d'un chantier. Obligation de vigilance du donneur d'ordre : contrat ≥ 5 000 € HT, attestation à la signature puis tous les 6 mois (art. L.8222-1 C. trav., L.243-15 CSS).

## Outils

Connecteur MCP `urssaf-vigilance` (dépôt `~/dev/urssaf-vigilance-mcp`, API Urssaf « Attestations Vérification Code Sécurité », production, identifiants OGEC) :
- `controler_attestation(fichier, siret_attendu, siren_attendu)` — lit le PDF, interroge l'Urssaf, compare, calcule la fin de validité, rend OK / ALERTE / REFUS. **Outil principal pour une attestation reçue.**
- `lire_attestation_pdf(fichier)` — extraction seule, sans réseau.
- `verifier_attestation(code)` / `verifier_attestations(codes)` — quand on n'a que le code (mail, tableau).
- `suivi_lister(seulement_a_verifier=True)` — codes du tableau de suivi non encore contrôlés ; `perimees_au_tableau` liste les échéances dépassées.
- `suivi_verifier(tous, ecrire)` — contrôle les codes du tableau ; `ecrire=True` écrit la colonne Vérification (sauvegarde datée du classeur avant, classeur fermé dans Excel).
- `etat_connecteur()` — en cas de doute sur la configuration.

Repli si l'API est indisponible : outil web https://www.urssaf.fr/accueil/outils-documentation/outils/verification-attestation.html dans le navigateur intégré ; le captcha (hCaptcha) est résolu par Rémi, jamais par Claude.

## Procédure pour une attestation reçue

1. **Identifier le contexte** : entreprise, lot (répartition des lots du chantier, DC4 pour un sous-traitant), SIRET figurant sur le devis ou le marché. Si le PDF est dans un mail, l'enregistrer d'abord dans le dossier du chantier.
2. **Contrôler** avec `controler_attestation(fichier, siret_attendu=<SIRET du devis>)`. Lire le verdict et toutes les anomalies / avertissements :
   - REFUS « code inconnu » → document suspect : demander à l'entreprise le PDF original téléchargé depuis son espace urssaf.fr, ne rien archiver comme valide, informer la maîtrise d'œuvre.
   - REFUS « périmée » ou « SIRET absent » → attestation à jour à réclamer à l'entreprise (copie maîtrise d'œuvre) ; SIRET absent = l'établissement qui travaille sur le chantier n'est pas couvert.
   - ALERTE → vérifier l'écart signalé (effectif, masse salariale, date) ; échéance < 30 j → prévoir la relance.
   - OK → passer à l'archivage.
3. **Règle de validité** : 6 mois après la date « à jour au » (fin de période analysée), en fin de mois — jamais 6 mois après la date d'édition. Exemple : à jour au 31/08/2026 → échéance 28/02/2027. L'Urssaf confirme cette règle dans ses réponses « périmée depuis le … ».
4. **Renseigner le tableau** « Suivi des attestations par entreprise.xlsx » (Marchés/Inspection du travail, feuille « Suivi attestations ») : colonnes D date attestation, E échéance réelle, I statut, L code de sécurité, M vérification (phrase « Authentique et valide - SIRET … (vérifié par API Urssaf le JJ/MM/AAAA) », en conservant l'historique de la cellule). Une entreprise présente sur plusieurs lots : mettre à jour toutes ses lignes. Compléter le sous-titre (dates de vérification) et ajouter un nota daté en bas de feuille si la situation change (nouvelle attestation, régularisation, entreprise sortie du chantier).
5. **Archiver** le PDF sous le nom `AAAAMMJJ-ENTREPRISE-Attestation de vigilance URSSAF.pdf` (date d'édition de l'attestation) dans `Marchés/Inspection du travail` et dans le sous-dossier `ADMIN` du lot concerné (deux copies).
6. **Rendre compte** à Rémi : entreprise, lot, verdict, SIRET, période analysée, échéance, ce qui reste à réclamer.

## Revue périodique du tableau

- `suivi_verifier(tous=True)` sans écriture d'abord ; lire la liste : statut par code, `perimee_depuis`, SIRET.
- Proposer à Rémi l'écriture (`ecrire=True`) et la liste des relances : attestations périmées, échéances dans le mois, entreprises sans code (ex. IBC) ou absentes du tableau (sous-traitants nouvellement déclarés).
- Ne pas réclamer de renouvellement à une entreprise qui n'intervient plus (statut noté dans le tableau).

## Garde-fous

- Un code valide prouve l'existence du document chez l'Urssaf, pas que l'entreprise est le bon cocontractant ni que l'établissement est couvert : toujours rapprocher SIREN/SIRET du devis.
- Jamais d'identifiants API ni de code de sécurité dans un mail ou un document partagé hors du dossier chantier ; les identifiants restent dans `local/urssaf-avcs.env` et `claude_desktop_config.json`.
- Le connecteur n'écrit dans le classeur que sur demande explicite (`ecrire=True`), après sauvegarde datée ; toute autre modification du tableau (sous-titre, nota, statut) se fait avec openpyxl sur le Mac en conservant la mise en forme.
- Une attestation « sur l'honneur » ou un quitus d'une plateforme privée (Attestation Légale, e-Attestations) ne remplace pas l'attestation Urssaf.