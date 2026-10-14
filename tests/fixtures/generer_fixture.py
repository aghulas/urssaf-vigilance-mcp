"""Génère une attestation de vigilance fictive reproduisant le texte des attestations Urssaf.

Valeurs entièrement inventées (SIREN 123 456 789, code MOCKVALIDE00001). À relancer si le gabarit change :
    python tests/fixtures/generer_fixture.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE1 = """URSSAF ILE DE FRANCE
93518 Montreuil Cedex
Nous contacter
Courriel: depuis votre espace urssaf.fr
Tel.: 3957
Références
N°SIREN 123456789
Page 1/2
MONTREUIL, le 5 Octobre 2026
SAS EXEMPLE BTP
1 RUE DE L'EXEMPLE
75001 PARIS
Objet : attestation de fourniture des déclarations sociales et paiement des
cotisations et contributions sociales.
CODE DE SÉCURITÉ
MOCKVALIDE00001
La vérification de l'authenticité et de la
validité de ce document s'effectue sur
urssaf.fr/portail/home/utile-et-pratique/veri
fication-attestation.html
Madame, Monsieur,
Je vous adresse votre attestation de fourniture des déclarations sociales et de paiement des
cotisations et contributions sociales.
En votre qualité d'employeur, cette attestation vous est délivrée pour les établissements dont la
liste figure au verso.
Cordialement,
CADRE LÉGAL
Article L.243-15 du code de la Sécurité sociale."""

PAGE2 = """CODE DE SÉCURITÉ
MOCKVALIDE00001
ATTESTATION DE FOURNITURE DES DÉCLARATIONS SOCIALES ET DE
PAIEMENT DES COTISATIONS ET CONTRIBUTIONS
Article L.243-15 du code de la Sécurité sociale 2/2
SAS EXEMPLE BTP
1 RUE DE L'EXEMPLE
75001 PARIS
En votre qualité d'employeur, la présente attestation vous est délivrée :
- pour un effectif moyen mensuel de 20 salariés,
- pour une masse salariale de 53575 euros,
- au titre du mois de août 2026,
- et au titre du (des) établissement(s) suivant(s) :
ATTESTATION DE L'UNION DE RECOUVREMENT
Le Directeur soussigné certifie qu'au titre du (des) établissement(s) ci-dessus désigné(s), l'entreprise est à
jour de ses obligations en matière de cotisations de Sécurité sociale et d'allocations familiales, de
contributions d'assurance chômage, de cotisations AGS*, et d'obligation d'emploi des travailleurs
handicapés** à la date du 31/08/2026.
Fait à : MONTREUIL
le : 05/10/2026
ÉTABLISSEMENTS CONCERNÉS NUMÉRO SIRET
1 RUE DE L'EXEMPLE
75001 PARIS
12345678900012"""


def generer(dest: Path) -> None:
    c = canvas.Canvas(str(dest), pagesize=A4)
    for page in (PAGE1, PAGE2):
        y = 800
        c.setFont("Helvetica", 9)
        for ligne in page.splitlines():
            c.drawString(40, y, ligne)
            y -= 13
        c.showPage()
    c.save()


if __name__ == "__main__":
    generer(Path(__file__).with_name("attestation_exemple.pdf"))
