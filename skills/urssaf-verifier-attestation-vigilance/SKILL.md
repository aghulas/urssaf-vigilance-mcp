---
name: urssaf-verifier-attestation-vigilance
description: Vérifier une attestation de vigilance URSSAF reçue d'un fournisseur ou sous-traitant (donneur d'ordre) avec le connecteur MCP urssaf-vigilance, la rapprocher du contrat et du tableau de suivi, puis l'archiver.
---

# Vérifier une attestation de vigilance URSSAF

À utiliser dès qu'une attestation de vigilance (« attestation de fourniture des déclarations sociales et de
paiement des cotisations et contributions sociales ») arrive d'un fournisseur, d'un sous-traitant ou d'un
maître d'œuvre, ou quand l'utilisateur demande de contrôler, revoir ou relancer les attestations d'un marché.
Obligation de vigilance du donneur d'ordre : contrat ≥ 5 000 € HT, attestation à la signature puis tous les
6 mois (art. L.8222-1 C. trav., L.243-15 CSS).

> Skill générique livrée avec le connecteur. Adaptez les parties « contexte » et « archivage » à votre
> organisation (noms de dossiers, interlocuteurs, convention de nommage).

## Outils

Connecteur MCP `urssaf-vigilance` (API Urssaf « Attestations Vérification Code Sécurité ») :
- `controler_attestation(fichier, siret_attendu, siren_attendu)` — lit le PDF, interroge l'Urssaf, compare,
  calcule la fin de validité, rend OK / ALERTE / REFUS. **Outil principal pour une attestation reçue.**
- `lire_attestation_pdf(fichier)` — extraction seule, sans réseau.
- `verifier_attestation(code)` / `verifier_attestations(codes)` — quand on n'a que le code (mail, tableau).
- `suivi_lister(seulement_a_verifier=True)` — codes du tableau non encore contrôlés ; `perimees_au_tableau`
  liste les échéances dépassées.
- `suivi_verifier(tous, ecrire)` — contrôle les codes du tableau ; `ecrire=True` écrit la colonne
  Vérification (sauvegarde du classeur avant, classeur fermé dans Excel).
- `suivi_creer_modele(fichier)` — classeur de suivi vierge si l'organisation n'en a pas.
- `etat_connecteur()` — en cas de doute sur la configuration.

Repli si l'API est indisponible : outil web
https://www.urssaf.fr/accueil/outils-documentation/outils/verification-attestation.html ; le captcha est
résolu par l'utilisateur, jamais par Claude.

## Procédure pour une attestation reçue

1. **Identifier le contexte** : entreprise, marché ou lot, SIRET figurant sur le devis ou le contrat
   (pour un sous-traitant : l'acte de sous-traitance / DC4). Si le PDF est dans un mail, l'enregistrer d'abord.
2. **Contrôler** avec `controler_attestation(fichier, siret_attendu=<SIRET du contrat>)`. Lire le verdict et
   toutes les anomalies / avertissements :
   - REFUS « code inconnu » → document suspect : demander à l'entreprise le PDF original téléchargé depuis
     son espace urssaf.fr, ne rien archiver comme valide, informer le responsable du marché.
   - REFUS « périmée » ou « SIRET absent » → attestation à jour à réclamer à l'entreprise ; SIRET absent =
     l'établissement qui réalise la prestation n'est pas couvert par le document.
   - ALERTE → vérifier l'écart signalé (effectif, masse salariale, date) ; échéance < 30 j → prévoir la relance.
   - OK → passer à l'archivage.
3. **Règle de validité** : 6 mois après la date « à jour au » (fin de période analysée), en fin de mois —
   jamais 6 mois après la date d'édition. Exemple : à jour au 31/08 → échéance 28/02. L'Urssaf confirme cette
   règle dans ses réponses « périmée depuis le … ».
4. **Renseigner le tableau de suivi** : date d'attestation, échéance, statut, code de sécurité, et dans la
   colonne Vérification la phrase « Authentique et valide - SIRET … (vérifié par API Urssaf le JJ/MM/AAAA) »
   à la suite de l'historique. Une entreprise présente sur plusieurs lots : mettre à jour toutes ses lignes.
   Ajouter une note datée si la situation change (nouvelle attestation, régularisation, entreprise sortie du
   marché).
5. **Archiver** le PDF avec un nom stable, par exemple `AAAAMMJJ-ENTREPRISE-Attestation de vigilance URSSAF.pdf`
   (date d'édition de l'attestation), dans le dossier administratif du marché ou du lot.
6. **Rendre compte** : entreprise, lot, verdict, SIRET, période analysée, échéance, ce qui reste à réclamer.

## Revue périodique du tableau

- `suivi_verifier(tous=True)` sans écriture d'abord ; lire la liste : statut par code, `perimee_depuis`, SIRET.
- Proposer l'écriture (`ecrire=True`) et la liste des relances : attestations périmées, échéances dans le
  mois, entreprises sans code, sous-traitants nouvellement déclarés absents du tableau.
- Ne pas réclamer de renouvellement à une entreprise qui n'intervient plus (le noter dans le tableau).

## Garde-fous

- Un code valide prouve l'existence du document chez l'Urssaf, pas que l'entreprise est le bon cocontractant
  ni que l'établissement est couvert : toujours rapprocher SIREN/SIRET du contrat.
- Jamais d'identifiants API dans un mail, un document partagé ou un dépôt ; les codes de sécurité et les
  données renvoyées par l'Urssaf restent dans le dossier du marché.
- Le connecteur n'écrit dans le classeur que sur demande explicite (`ecrire=True`), après sauvegarde.
- Une attestation sur l'honneur ou un quitus d'une plateforme privée ne remplace pas l'attestation Urssaf.
