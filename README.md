# urssaf-vigilance-mcp

Serveur [MCP](https://modelcontextprotocol.io) pour **vérifier les attestations de vigilance Urssaf** que vous
recevez de vos fournisseurs et sous-traitants, et tenir votre tableau de suivi.

En France, tout donneur d'ordre qui conclut un contrat d'au moins 5 000 € HT doit obtenir de son
cocontractant une attestation de vigilance Urssaf à la signature, puis tous les six mois, et **en vérifier
l'authenticité** (art. L.8222-1 et D.8222-5 du Code du travail, L.243-15 du Code de la sécurité sociale). À
défaut, il peut être tenu solidairement des cotisations et pénalités du sous-traitant en cas de travail dissimulé.

La vérification se fait normalement à la main sur urssaf.fr, code par code, derrière un captcha. Ce connecteur
s'appuie sur l'API officielle de l'Urssaf **« Attestations Vérification Code Sécurité »**, qui rend le même
service sans captcha et permet de vérifier jusqu'à 100 attestations en un appel. Il ajoute la lecture du PDF
reçu, le rapprochement champ à champ, le calcul de la fin de validité et la mise à jour d'un classeur Excel.

> Ce projet n'est pas affilié à l'Urssaf. L'API et ses conditions d'utilisation sont décrites sur le
> [Portail API Urssaf](https://portailapi.urssaf.fr/fr/catalogue-api/prd/avcs).

## Sommaire

1. [Ce que fait le connecteur](#ce-que-fait-le-connecteur)
2. [Obtenir ses identifiants API Urssaf](#obtenir-ses-identifiants-api-urssaf)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Tableau de suivi Excel](#tableau-de-suivi-excel)
6. [Règles métier](#règles-métier)
7. [Sécurité et engagements](#sécurité-et-engagements)
8. [Développement](#développement)

## Ce que fait le connecteur

| Outil MCP | Rôle |
|---|---|
| `verifier_attestation(code, domaine?)` | Vérifie un code de sécurité (15 caractères) auprès de l'Urssaf. Renvoie un statut normalisé — `valide`, `perimee` (avec la date), `inconnue`, `incomplete`, `erreur` — et, pour une attestation valide : nature, dénomination, organisme émetteur, date de certification, SIREN, SIRET des établissements, dernière période analysée, effectif, masse salariale. |
| `verifier_attestations(codes)` | Même chose pour une liste de codes (lots de 100 par appel API). |
| `lire_attestation_pdf(fichier)` | Extrait les données d'un PDF d'attestation Urssaf (code, SIREN, raison sociale, dates, effectif, masse salariale, SIRET). Sans réseau. |
| `controler_attestation(fichier, siret_attendu?, siren_attendu?)` | Contrôle complet d'une attestation reçue : PDF + API + cohérence champ à champ + cocontractant attendu + fin de validité → verdict `OK` / `ALERTE` / `REFUS`. |
| `suivi_lister(fichier?, seulement_a_verifier?)` | Lit le tableau Excel de suivi : lignes, codes uniques, attestations dont l'échéance est dépassée. |
| `suivi_verifier(fichier?, tous?, ecrire?)` | Vérifie les codes du tableau (non encore vérifiés, ou tous) et, si demandé, écrit le résultat dans la colonne « Vérification ». |
| `suivi_creer_modele(fichier)` | Crée un classeur de suivi vierge au bon format. |
| `etat_connecteur()` | Configuration courante, sans secrets. |

Natures d'attestation reconnues : vigilance (`AVG_UR`, `AVG_RSI`), mais aussi CSG/CRDS, formation
professionnelle, employeur de personnel de maison, frontalier suisse, chiffre d'affaires micro-entrepreneur,
artistes-auteurs — l'API couvre toutes les attestations à code de sécurité émises par l'Urssaf.

## Obtenir ses identifiants API Urssaf

L'API est **gratuite** et ouverte à toute personne physique ou morale, sous réserve de validation par l'Urssaf
(« accès public et libre, tout demandeur est éligible »). Comptez 1 à 2 jours ouvrés.

1. **Créer un compte** sur le Portail API Urssaf : <https://portailapi.urssaf.fr/fr/inscription>
   (adresse e-mail professionnelle, SIRET de votre organisation).
2. **Souscrire à l'API** « Attestations Vérification Code Sécurité » :
   <https://portailapi.urssaf.fr/fr/catalogue-api/prd/avcs/souscription-formulaire>. Le formulaire demande
   l'usage prévu (vérification des attestations de vigilance de vos fournisseurs en tant que donneur d'ordre)
   et l'acceptation des [CGU de l'API](https://portailapi.urssaf.fr/fr/catalogue-api/prd/avcs/conditions-generales-utilisation).
3. **Recevoir les identifiants.** L'équipe « Secteur API » de l'Urssaf Caisse nationale envoie un e-mail avec
   une archive protégée par mot de passe (le mot de passe arrive dans un second e-mail). Elle contient :
   - `client-id` et `client-secret` (UUID) ;
   - le scope : `attn.codes_securite` ;
   - l'URL d'obtention du jeton : `https://api.urssaf.fr/api/oauth/v1/token` ;
   - l'hôte des ressources : `https://api.urssaf.fr`.
   Un accès dit « sandbox » (`api-edi.urssaf.fr`) peut être fourni avant la production.
4. **Renseigner** `URSSAF_CLIENT_ID` et `URSSAF_CLIENT_SECRET` dans la configuration du serveur (ci-dessous),
   avec `URSSAF_ENV=production`.

Support : questions techniques via le [centre de services ACOSS (JIRA)](https://acoss-dsi.atlassian.net/servicedesk/customer/portal/2),
autres questions via le [formulaire du portail](https://portailapi.urssaf.fr/fr/centre-assistance/contactez-nous).
Documentation technique de l'API (PDF ACOSS v1.2) et changelog : onglets « Documentation » et « Changelog » de la
[page de l'API](https://portailapi.urssaf.fr/fr/catalogue-api/prd/avcs).

## Installation

Python 3.11 ou plus récent.

```bash
git clone https://github.com/aghulas/urssaf-vigilance-mcp.git
cd urssaf-vigilance-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

Le paquet installe la commande `urssaf-vigilance-mcp` (serveur MCP sur stdio).

Sans identifiants, vous pouvez tester le connecteur en mode simulé : `URSSAF_MOCK=1`. Les codes
`MOCKVALIDE00001`, `MOCKPERIMEE0001`, `MOCKMANQUANT001` renvoient respectivement une attestation valide,
périmée et incomplète ; tout autre code est inconnu.

## Configuration

Toute la configuration passe par des variables d'environnement — **aucun secret dans un fichier versionné**.

| Variable | Rôle |
|---|---|
| `URSSAF_CLIENT_ID`, `URSSAF_CLIENT_SECRET` | Identifiants OAuth2 reçus de l'Urssaf. |
| `URSSAF_ENV` | `production` (`api.urssaf.fr`) ou `sandbox` (`api-edi.urssaf.fr`, défaut). |
| `URSSAF_MOCK` | `1` : réponses simulées, sans réseau ni identifiants. |
| `URSSAF_DOMAINE` | `URSSAF` (défaut : employeurs et toutes catégories) ou `ISU` (artisans, commerçants, indépendants). |
| `URSSAF_FICHIER_SUIVI` | Chemin du classeur Excel de suivi utilisé par défaut par `suivi_*`. |
| `URSSAF_FEUILLE_SUIVI` | Nom de la feuille ; sinon la première feuille contenant les en-têtes attendus est utilisée. |
| `URSSAF_ECRITURE` | `1` pour autoriser `suivi_verifier(ecrire=True)` à modifier le classeur. Désactivé par défaut. |
| `URSSAF_TIMEOUT` | Délai HTTP en secondes (30). |

Le jeton OAuth2 (client_credentials, validité 1 h) est mis en cache et renouvelé automatiquement deux minutes
avant expiration, conformément aux recommandations du portail.

### Claude Desktop

Dans `claude_desktop_config.json` (macOS : `~/Library/Application Support/Claude/`, Windows :
`%APPDATA%\Claude\`), ajoutez :

```json
"urssaf-vigilance": {
  "command": "/chemin/vers/urssaf-vigilance-mcp/.venv/bin/urssaf-vigilance-mcp",
  "env": {
    "URSSAF_ENV": "production",
    "URSSAF_CLIENT_ID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "URSSAF_CLIENT_SECRET": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "URSSAF_FICHIER_SUIVI": "/chemin/vers/Suivi des attestations.xlsx",
    "URSSAF_ECRITURE": "1"
  }
}
```

Sous Windows, remplacez `command` par `C:\\chemin\\vers\\.venv\\Scripts\\urssaf-vigilance-mcp.exe`. Redémarrez
Claude Desktop après modification.

### Autres clients MCP

Tout client compatible MCP (Claude Code, Cursor, etc.) peut lancer `urssaf-vigilance-mcp` sur stdio avec les mêmes
variables d'environnement. Exemple en ligne de commande :

```bash
URSSAF_MOCK=1 .venv/bin/urssaf-vigilance-mcp
```

## Tableau de suivi Excel

Le connecteur lit et met à jour un classeur Excel ordinaire — le vôtre, ou celui que crée `suivi_creer_modele`.
Il ne dépend pas des lettres de colonnes mais des **en-têtes** (recherche insensible à la casse et aux retours à
la ligne), ce qui permet d'ajouter vos propres colonnes (assurances, PPSPS, contacts…). Colonnes reconnues :

| En-tête (motif) | Usage |
|---|---|
| `Opération` | Libre (chantier, marché, service). |
| `Lot` | Libre ; **une ligne sans Lot ou sans Entreprise est ignorée** (notes de bas de tableau). |
| `Entreprise` | Obligatoire. |
| `URSSAF … date` | Date de l'attestation. |
| `URSSAF … échéance` | Fin de validité (mise à jour quand l'Urssaf signale une attestation périmée). |
| `Statut` | Libre. |
| `Code de sécurité URSSAF` | Obligatoire : le code à 15 caractères. Une entreprise présente sur plusieurs lots partage son code ; il n'est vérifié qu'une fois et le résultat est reporté sur chaque ligne. |
| `Vérification URSSAF` | Obligatoire : le connecteur y écrit « Authentique et valide - SIRET … (vérifié par API Urssaf le JJ/MM/AAAA) », ou la mention périmée / code inconnu, **à la suite** du texte existant (l'historique est conservé ; une mention « code à vérifier » est retirée). |

Un code est considéré « à vérifier » tant que sa cellule Vérification ne mentionne pas un contrôle effectué.

L'écriture dans le classeur n'a lieu que si l'appel demande `ecrire=True` **et** que `URSSAF_ECRITURE=1` ; faites
une sauvegarde avant, et fermez le fichier dans Excel (en particulier sur un lecteur synchronisé).

## Règles métier

- **Validité** : une attestation de vigilance est valable six mois à compter de la **fin de la période
  analysée** (la date « à jour au » du document), pas de sa date d'édition. Le connecteur arrondit à la fin du
  mois : à jour au 31/08 → échéance 28/02 (29 en année bissextile). L'Urssaf applique la même règle dans ses
  réponses « attestation périmée depuis le … ». Une alerte est émise à 30 jours de l'échéance.
- **Un code valide ne suffit pas.** Il prouve que le document existe chez l'Urssaf, pas que l'entreprise est
  votre cocontractant ni que l'établissement qui travaille pour vous est couvert. `controler_attestation`
  vérifie donc aussi : nature = attestation de vigilance ; SIREN et SIRET du PDF égaux à ceux renvoyés par
  l'Urssaf ; présence du `siret_attendu` (celui du devis ou du contrat) dans la liste des établissements.
- **Verdicts** : code inconnu, attestation périmée, SIREN différent ou SIRET attendu absent → `REFUS` ;
  écarts d'effectif, de masse salariale ou de date de certification, échéance proche → `ALERTE` ; sinon `OK`.
- Une attestation sur l'honneur, un quitus d'une plateforme privée ou une capture d'écran ne remplacent pas
  l'attestation Urssaf. En cas de code inconnu, demandez à l'entreprise le PDF original téléchargé depuis son
  espace urssaf.fr.

## Sécurité et engagements

En souscrivant à l'API, vous acceptez les CGU de l'Urssaf, qui imposent notamment : n'utiliser l'API que pour
vérifier des attestations (jamais pour obtenir des informations sur des comptes cotisants) ; ne divulguer ni
les identifiants ni les données retournées ; signaler toute faille de sécurité à `contact.api@urssaf.fr` sous
48 heures ; respecter les quotas (HTTP 429 en cas de dépassement). Repli en cas d'indisponibilité : l'outil web
<https://www.urssaf.fr/accueil/outils-documentation/outils/verification-attestation.html>.

Le connecteur ne stocke rien : pas de base de données, pas de journal des codes vérifiés ; les identifiants ne
sont lus que dans l'environnement du processus.

## Développement

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q        # tests sans réseau (respx)
python tests/fixtures/generer_fixture.py   # régénère le PDF d'exemple (données fictives)
```

Le dossier `skills/` contient une skill Claude générique décrivant la procédure de vérification d'une attestation
reçue et la revue périodique du tableau ; adaptez-la à votre organisation (dossiers d'archivage, interlocuteurs).

Les contributions sont bienvenues : ouvrez une issue ou une pull request.

## Licence

MIT — voir [LICENSE](LICENSE).
