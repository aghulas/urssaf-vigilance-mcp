# urssaf-vigilance-mcp

Serveur MCP pour vérifier les **attestations de vigilance Urssaf** reçues des fournisseurs et
sous-traitants (obligation de vigilance du donneur d'ordre, art. L.8222-1 C. trav. / L.243-15 CSS),
et tenir le tableau Excel de suivi.

Il s'appuie sur l'API Urssaf **« Attestations Vérification Code Sécurité »** (AVCS), équivalent
programmatique de l'outil web [verification-attestation](https://www.urssaf.fr/accueil/outils-documentation/outils/verification-attestation.html),
sans captcha et avec vérification en masse (100 codes par appel).

- Catalogue : <https://portailapi.urssaf.fr/fr/catalogue-api/prd/avcs> (accès public et libre, souscription gratuite)
- Doc technique ACOSS v1.2 (PDF) et CGU v2 du 30/01/2025 : liens sur la page du catalogue

## Outils

| Outil | Rôle |
|---|---|
| `verifier_attestation(code, domaine?)` | Vérifie un code de sécurité (15 caractères). Statut `valide` / `perimee` (+ `perimee_depuis`) / `inconnue` / `incomplete` / `erreur`, nature, dénomination, organisme, SIREN, SIRET, période analysée, effectif, masse salariale. |
| `verifier_attestations(codes)` | Même chose pour une liste (découpage automatique par 100). |
| `lire_attestation_pdf(fichier)` | Extrait les données du PDF Urssaf (code, SIREN, raison sociale, dates, effectif, masse salariale, SIRET). Sans réseau. |
| `controler_attestation(fichier, siret_attendu?, siren_attendu?)` | PDF + API + cohérence champ à champ + fin de validité → verdict `OK` / `ALERTE` / `REFUS`. |
| `suivi_lister(fichier?, seulement_a_verifier?)` | Lit le tableau Excel de suivi (lignes, codes uniques, attestations périmées). |
| `suivi_verifier(fichier?, tous?, ecrire?)` | Vérifie les codes du tableau (non vérifiés, ou tous) et écrit les résultats dans la colonne « Vérification » si `ecrire=True` **et** `URSSAF_ECRITURE=1`. |
| `etat_connecteur()` | Configuration courante, sans secrets. |

### Règles métier codées

- **Validité** : 6 mois après la date de fin de période analysée (« à jour au »), arrondi à la fin du mois
  (à jour au 31/08/2026 → échéance 28/02/2027). Alerte à 30 jours de l'échéance.
- **Un code valide ne suffit pas** : le contrôle vérifie aussi que la nature est bien une attestation de
  vigilance (`AVG_UR` / `AVG_RSI`), que le SIREN/SIRET du PDF correspond à ceux renvoyés par l'Urssaf,
  et que le SIRET de l'établissement prestataire attendu est dans la liste.
- Écarts d'effectif / masse salariale / date de certification = avertissement (ALERTE) ; code inconnu,
  périmée, SIREN ou SIRET absent = REFUS.

## Installation

```bash
cd ~/dev/urssaf-vigilance-mcp
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Configuration

Variables d'environnement (jamais dans le dépôt) :

| Variable | Rôle |
|---|---|
| `URSSAF_CLIENT_ID`, `URSSAF_CLIENT_SECRET` | Identifiants OAuth2 reçus après souscription sur portailapi.urssaf.fr |
| `URSSAF_ENV` | `sandbox` (défaut, hôte `api-edi.urssaf.fr`) ou `production` (`api.urssaf.fr`) |
| `URSSAF_MOCK` | `1` : réponses simulées sans réseau (codes `MOCKVALIDE00001`, `MOCKPERIMEE0001`, `MOCKMANQUANT001`, autre = inconnue) |
| `URSSAF_DOMAINE` | `URSSAF` (défaut, employeurs) ou `ISU` (artisans, commerçants, indépendants) |
| `URSSAF_FICHIER_SUIVI` | Chemin par défaut du classeur « Suivi des attestations par entreprise.xlsx » |
| `URSSAF_ECRITURE` | `1` pour autoriser `suivi_verifier(ecrire=True)` à modifier le classeur |

Jeton : `POST https://{hote}/api/oauth/v1/token`, `grant_type=client_credentials`, scope `attn.codes_securite`,
validité 1 h, mis en cache et renouvelé 2 min avant expiration.

### Claude Desktop (`claude_desktop_config.json`)

```json
"urssaf-vigilance": {
  "command": "/Users/remi/dev/urssaf-vigilance-mcp/.venv/bin/python",
  "args": ["-m", "urssaf_vigilance_mcp.server"],
  "env": {
    "URSSAF_ENV": "production",
    "URSSAF_CLIENT_ID": "…",
    "URSSAF_CLIENT_SECRET": "…",
    "URSSAF_FICHIER_SUIVI": "/Users/remi/Library/CloudStorage/…/Inspection du travail/Suivi des attestations par entreprise.xlsx",
    "URSSAF_ECRITURE": "1"
  }
}
```

## Tableau de suivi attendu

Feuille « Suivi attestations », une ligne d'en-têtes détectée automatiquement (dans les 10 premières lignes)
contenant au moins **Entreprise**, **Code de sécurité URSSAF** et **Vérification URSSAF** ; colonnes repérées
par leur titre, pas par leur lettre. Les lignes sans Lot ou sans Entreprise (notas) sont ignorées. Une
entreprise présente sur plusieurs lots partage son code : la vérification est faite une fois et reportée
sur chaque ligne. L'historique de la colonne Vérification est conservé (le texte est ajouté, la mention
« code à vérifier sur urssaf.fr » est retirée).

## Engagements (CGU de l'API)

Usage réservé à la vérification d'attestations ; ne pas détourner l'API pour obtenir des informations sur
des comptes cotisants ; confidentialité des identifiants et des données retournées ; signalement de toute
faille sous 48 h à `contact.api@urssaf.fr`. Repli manuel en cas d'indisponibilité : l'outil web urssaf.fr.
