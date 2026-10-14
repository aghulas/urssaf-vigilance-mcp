from __future__ import annotations

from datetime import date

from urssaf_vigilance_mcp.client import normaliser_resultat, reponse_mock
from urssaf_vigilance_mcp.controle import controler, fin_de_validite
from urssaf_vigilance_mcp.modeles import Etablissement, ResultatVerification
from urssaf_vigilance_mcp.pdf import fin_de_mois, lire_attestation


def test_lire_attestation_exemple(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    assert a.code_securite == "MOCKVALIDE00001"
    assert a.siren == "123456789"
    assert a.raison_sociale == "SAS EXEMPLE BTP"
    assert a.organisme_emetteur == "URSSAF ILE DE FRANCE"
    assert a.date_delivrance == date(2026, 10, 5)
    assert a.a_jour_au == date(2026, 8, 31)
    assert a.mois_analyse == "août 2026"
    assert a.effectif == 20 and a.masse_salariale == 53575
    assert a.sirets == ["12345678900012"]


def test_fin_de_validite():
    assert fin_de_validite(date(2026, 8, 31)) == date(2027, 2, 28)
    assert fin_de_validite(date(2026, 12, 3)) == date(2027, 6, 30)  # exemple API Entreprise
    assert fin_de_validite(date(2025, 7, 31)) == date(2026, 1, 31)
    assert fin_de_mois(date(2028, 2, 10)) == date(2028, 2, 29)


def _api_exemple(**kw) -> ResultatVerification:
    base = dict(
        code_securite="MOCKVALIDE00001", statut="valide", nature="AVG_UR", est_attestation_vigilance=True,
        denomination="EXEMPLE BTP", organisme_emetteur="URSSAF ILE DE FRANCE", date_certification="05/10/2026",
        etablissements=[Etablissement("12345678900012", "1 RUE DE L'EXEMPLE 75001 PARIS")],
        derniere_periode_analysee="mois de août 2026", masse_salariale="53575.0", effectif="20",
    )
    base.update(kw)
    return ResultatVerification(**base)


def test_controle_ok(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    c = controler(a, _api_exemple(), siret_attendu="12345678900012", aujourdhui=date(2026, 10, 13))
    assert c.verdict == "OK" and c.conforme, c.anomalies
    assert c.fin_de_validite == date(2027, 2, 28) and c.jours_restants == 138
    assert all(v["ok"] for v in c.verifications)


def test_controle_siret_absent(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    c = controler(a, _api_exemple(), siret_attendu="12345678900099", aujourdhui=date(2026, 10, 13))
    assert c.verdict == "REFUS" and any("SIRET de l'établissement prestataire" in x for x in c.anomalies)


def test_controle_echeance_proche_et_perimee(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    c = controler(a, _api_exemple(), aujourdhui=date(2027, 2, 10))
    assert c.verdict == "ALERTE" and c.jours_restants == 18
    c2 = controler(a, _api_exemple(), aujourdhui=date(2027, 3, 1))
    assert c2.verdict == "REFUS" and "périmée depuis le 28/02/2027" in c2.anomalies[0]


def test_controle_incoherence_effectif_est_avertissement(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    c = controler(a, _api_exemple(effectif="21"), aujourdhui=date(2026, 10, 13))
    assert c.verdict == "ALERTE" and c.conforme and any("Effectif" in x for x in c.avertissements)


def test_controle_siren_different_est_refus(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    api = _api_exemple(etablissements=[Etablissement("98765432100014", "ailleurs")])
    c = controler(a, api, aujourdhui=date(2026, 10, 13))
    assert c.verdict == "REFUS"


def test_controle_code_inconnu_et_perimee_api(pdf_exemple):
    a = lire_attestation(pdf_exemple)
    inc = normaliser_resultat(reponse_mock(["ZZZZZZZZZZZZZZZ"])["verifierCodeSecuriteAttestationGen"][0])
    c = controler(a, inc, aujourdhui=date(2026, 10, 13))
    assert c.verdict == "REFUS" and "FUNC202" in c.anomalies[0]
    per = normaliser_resultat(reponse_mock(["MOCKPERIMEE0001"])["verifierCodeSecuriteAttestationGen"][0])
    c2 = controler(a, per, aujourdhui=date(2026, 10, 13))
    assert c2.verdict == "REFUS" and c2.fin_de_validite == date(2026, 9, 30)


def test_controle_sans_pdf():
    c = controler(None, _api_exemple(), siren_attendu="123456789", aujourdhui=date(2026, 10, 13))
    assert c.verdict == "OK" and c.fin_de_validite == date(2027, 2, 28)
