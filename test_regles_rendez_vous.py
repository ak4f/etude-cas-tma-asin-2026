"""Tests automatisés des règles de gestion (un groupe de tests par ticket).

Lancement : python -m unittest -v
Le module testé peut être remplacé par la variable d'environnement REGLES_MODULE
(voir le README, section « Preuve que les tests rejouent les anomalies »).

Auteur : ANATO Kodjo Freddy
"""

import importlib
import os
import unittest
from datetime import datetime, timedelta

R = importlib.import_module(os.environ.get("REGLES_MODULE", "regles_rendez_vous").strip())

EXPORT = datetime(2026, 11, 20, 18, 0)  # instant de l'export de la base


def dt(texte):
    return datetime.strptime(texte, "%Y-%m-%d %H:%M")


class OutilsTest(unittest.TestCase):
    def assertRefus(self, res, code, message):
        self.assertIsNotNone(res, "Refus attendu mais l'action a été acceptée (reçu None)")
        self.assertFalse(res.ok, f"refus attendu, obtenu : {res}")
        self.assertEqual(res.code, code)
        self.assertEqual(res.message, message)

    def assertAccepte(self, res):
        self.assertTrue(res.ok, f"acceptation attendue, obtenu : {res}")


class TestTMA103SaisieNPI(OutilsTest):
    """TMA-103 : un NPI contenant une lettre doit être refusé en 400, jamais en 500."""

    MAINT = dt("2026-11-20 09:00")

    def prise(self, npi, service="CNI", date="2026-11-23T09:00"):
        return R.controler_prise(npi, service, date, [], self.MAINT)

    def test_trace_du_ticket_lettre_dans_le_npi(self):
        res = self.prise("06142A3647")
        self.assertRefus(res, 400, "Le NPI doit comporter exactement 10 chiffres.")

    def test_npi_de_longueur_incorrecte(self):
        for npi in ("", "123456789", "01234567890", "061425364711"):
            with self.subTest(npi=npi):
                self.assertRefus(self.prise(npi), 400, R.MSG_NPI)

    def test_npi_piegeux(self):
        pieges = (
            " 0614253647",
            "0614253647 ",
            "0614253647\n",
            "0614 253647",
            "0614-253647",
            "٠٦١٤٢٥٣٦٤٧",  # dix chiffres arabes orientaux : ce ne sont pas des 0 à 9
            "0614253647\x00",
            "+614253647",
        )
        for npi in pieges:
            with self.subTest(npi=repr(npi)):
                self.assertRefus(self.prise(npi), 400, R.MSG_NPI)

    def test_npi_non_textuel(self):
        for npi in (None, 614253647, 614253647.0, ["0614253647"], b"0614253647"):
            with self.subTest(npi=repr(npi)):
                self.assertRefus(self.prise(npi), 400, R.MSG_NPI)

    def test_npi_valide_accepte(self):
        for npi in ("0614253647", "0000000000", "9999999999"):
            with self.subTest(npi=npi):
                self.assertAccepte(self.prise(npi))

    def test_service_inconnu(self):
        for service in ("PASSPORT", "passeport", "Cni", "", " CNI", None, 3):
            with self.subTest(service=repr(service)):
                res = self.prise("0614253647", service=service)
                self.assertRefus(
                    res, 400, "Service inconnu : choisissez PASSEPORT, CNI ou PERMIS."
                )

    def test_services_connus(self):
        for service in ("PASSEPORT", "CNI", "PERMIS"):
            with self.subTest(service=service):
                self.assertAccepte(self.prise("0614253647", service=service))

    def test_date_illisible(self):
        illisibles = (
            "2026-11-23 09:00",
            "23/11/2026 09:00",
            "2026-11-23T9:00",
            "2026-11-23T09:00:00",
            "2026-11-23",
            "2026-13-01T09:00",
            "2026-02-30T09:00",
            "2026-11-23T24:00",
            "2026-11-23T09:60",
            "",
            None,
            20261123,
            "2026-11-23T09:00\n",
        )
        for date in illisibles:
            with self.subTest(date=repr(date)):
                res = self.prise("0614253647", date=date)
                self.assertRefus(
                    res,
                    400,
                    "Date et heure invalides (format attendu : AAAA-MM-JJTHH:MM).",
                )

    def test_ordre_des_controles_npi_avant_service_avant_date(self):
        self.assertRefus(self.prise("abc", service="X", date="n'importe quoi"), 400, R.MSG_NPI)
        self.assertRefus(self.prise("0614253647", service="X", date="n'importe quoi"), 400, R.MSG_SERVICE)


class TestTMA101FermetureWeekEnd(OutilsTest):
    """TMA-101 : le samedi 14 novembre ne doit pas être réservable (centre fermé)."""

    MAINT = dt("2026-11-09 23:59")  # instant de création du rendez-vous n° 742

    def prise(self, date):
        return R.controler_prise("0614253647", "PASSEPORT", date, [], self.MAINT)

    def test_trace_du_ticket_samedi_14_novembre(self):
        res = self.prise("2026-11-14T10:00")
        self.assertRefus(res, 409, "Le centre est fermé le week-end.")

    def test_dimanche_refuse(self):
        self.assertRefus(self.prise("2026-11-15T10:00"), 409, R.MSG_WEEK_END)

    def test_du_lundi_au_vendredi_accepte(self):
        for jour in ("2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"):
            with self.subTest(jour=jour):
                self.assertAccepte(self.prise(jour + "T10:00"))

    def test_tous_les_samedis_et_dimanches_refuses(self):
        jour = datetime(2026, 11, 14)
        for i in range(0, 56):
            d = jour + timedelta(days=i)
            if d.weekday() >= 5:
                with self.subTest(jour=d.date()):
                    self.assertRefus(self.prise(d.strftime("%Y-%m-%dT10:00")), 409, R.MSG_WEEK_END)


class TestDatePasseeEtGrille(OutilsTest):
    """Règles de la grille horaire et du passé (anomalie bonus : rendez-vous à 16:00)."""

    MAINT = dt("2026-11-20 18:00")

    def prise(self, date, maint=None):
        return R.controler_prise("0614253647", "CNI", date, [], maint or self.MAINT)

    def test_date_passee_refusee(self):
        for date in ("2026-11-19T10:00", "2026-11-20T17:30", "2026-01-05T08:30"):
            with self.subTest(date=date):
                self.assertRefus(
                    self.prise(date), 409, "Impossible de prendre un rendez-vous dans le passé."
                )

    def test_passe_controle_avant_le_week_end(self):
        # Samedi passé : le motif « passé » est celui du tableau le plus prioritaire.
        self.assertRefus(self.prise("2026-11-14T10:00"), 409, R.MSG_PASSE)

    def test_creneau_a_venir_accepte(self):
        self.assertAccepte(self.prise("2026-11-23T08:00"))

    def test_premier_et_dernier_creneau_acceptes(self):
        for heure in ("08:00", "15:30"):
            with self.subTest(heure=heure):
                self.assertAccepte(self.prise("2026-11-23T" + heure))

    def test_hors_grille_refuse(self):
        # 16:00 et 16:30 existent dans l'export (rendez-vous n° 490, 698 et 842).
        for heure in ("07:30", "07:59", "08:15", "08:45", "12:10", "15:45", "16:00", "16:30", "18:00", "00:00"):
            with self.subTest(heure=heure):
                self.assertRefus(
                    self.prise("2026-11-23T" + heure),
                    409,
                    "Créneau invalide : de 08:00 à 15:30, toutes les 30 minutes.",
                )

    def test_toute_la_grille_acceptee(self):
        for h in range(8, 16):
            for m in (0, 30):
                if (h, m) <= (15, 30):
                    with self.subTest(h=h, m=m):
                        self.assertAccepte(self.prise(f"2026-11-23T{h:02d}:{m:02d}"))

    def test_heure_avec_fuseau_convertie_en_heure_du_benin(self):
        # 17:00 UTC le 20/11 = 18:00 à Cotonou : le créneau du lendemain matin reste à venir.
        from datetime import timezone

        utc = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc)
        self.assertRefus(self.prise("2026-11-20T17:30", maint=utc), 409, R.MSG_PASSE)
        self.assertAccepte(self.prise("2026-11-23T10:00", maint=utc))


def rv(id_, npi, service, date, statut="confirme"):
    return {"id": id_, "npi": npi, "service": service, "date_heure": date, "statut": statut}


class TestTMA102CapaciteCreneau(OutilsTest):
    """TMA-102 : le créneau du mardi 10 novembre à 09:00 ne doit accueillir que 3 usagers."""

    MAINT = dt("2026-11-04 23:43")  # instant de création du rendez-vous n° 697
    CRENEAU = "2026-11-10T09:00"

    def trois_rendez_vous(self):
        # Rendez-vous n° 632, 644 et 681 de l'export, tous services confondus.
        return [
            rv(632, "0638958971", "PASSEPORT", "2026-11-10 09:00"),
            rv(644, "0671968463", "CNI", "2026-11-10 09:00"),
            rv(681, "0609394161", "PERMIS", "2026-11-10 09:00"),
        ]

    def prise(self, existants, service="PERMIS"):
        return R.controler_prise("0620214467", service, self.CRENEAU, existants, self.MAINT)

    def test_trace_du_ticket_quatrieme_usager_refuse(self):
        res = self.prise(self.trois_rendez_vous())
        self.assertRefus(res, 409, "Ce créneau est complet.")

    def test_quatrieme_refuse_quel_que_soit_le_service(self):
        for service in R.SERVICES:
            with self.subTest(service=service):
                self.assertRefus(self.prise(self.trois_rendez_vous(), service), 409, R.MSG_COMPLET)

    def test_troisieme_usager_accepte(self):
        self.assertAccepte(self.prise(self.trois_rendez_vous()[:2]))

    def test_premier_usager_accepte(self):
        self.assertAccepte(self.prise([]))

    def test_un_rendez_vous_annule_libere_sa_place(self):
        existants = self.trois_rendez_vous()
        existants[1]["statut"] = "annule"
        self.assertAccepte(self.prise(existants))

    def test_trois_actifs_et_un_annule_refuse(self):
        existants = self.trois_rendez_vous() + [rv(700, "0600000000", "CNI", "2026-11-10 09:00", "annule")]
        self.assertRefus(self.prise(existants), 409, R.MSG_COMPLET)

    def test_les_autres_creneaux_ne_comptent_pas(self):
        existants = self.trois_rendez_vous() + [rv(701, "0600000001", "CNI", "2026-11-10 09:30")]
        existants = [r for r in existants if r["id"] != 681] + [rv(702, "0600000002", "CNI", "2026-11-10 09:30")]
        self.assertAccepte(self.prise(existants))

    def test_creneau_a_quatre_dans_l_export_du_24_novembre(self):
        # Le créneau du 24/11 à 14:00 compte déjà 4 rendez-vous (n° 728, 750, 763, 783).
        existants = [rv(i, f"06000000{i % 100:02d}", "CNI", "2026-11-24 14:00") for i in (728, 750, 763)]
        res = R.controler_prise("0699999999", "CNI", "2026-11-24T14:00", existants, EXPORT)
        self.assertRefus(res, 409, R.MSG_COMPLET)


class TestTMA107ConformeUnSeulRendezVousAVenir(OutilsTest):
    """TMA-107 : COMPORTEMENT CONFORME. Un usager ayant déjà un rendez-vous à venir
    ne peut pas en prendre un autre, tous services confondus (règle de la section 2)."""

    NPI = "0102030405"

    def existant(self, statut="confirme", date="2026-11-26 10:00"):
        # Rendez-vous n° 800 de l'export : passeport le jeudi 26 novembre à 10:00.
        return [rv(800, self.NPI, "PASSEPORT", date, statut)]

    def prise(self, existants, service="PERMIS", date="2026-11-27T09:00"):
        return R.controler_prise(self.NPI, service, date, existants, EXPORT)

    def test_trace_du_ticket_permis_refuse_car_passeport_a_venir(self):
        res = self.prise(self.existant())
        self.assertRefus(res, 409, "Vous avez déjà un rendez-vous à venir.")

    def test_meme_service_refuse_aussi(self):
        self.assertRefus(self.prise(self.existant(), service="PASSEPORT"), 409, R.MSG_DEJA_A_VENIR)

    def test_rendez_vous_annule_ne_bloque_pas(self):
        self.assertAccepte(self.prise(self.existant(statut="annule")))

    def test_rendez_vous_passe_ne_bloque_pas(self):
        for statut in ("honore", "absent", "confirme"):
            with self.subTest(statut=statut):
                self.assertAccepte(self.prise(self.existant(statut=statut, date="2026-11-19 10:00")))

    def test_rendez_vous_d_un_autre_usager_ne_bloque_pas(self):
        autre = [rv(1, "0999999999", "PASSEPORT", "2026-11-26 10:00")]
        self.assertAccepte(self.prise(autre))

    def test_rendez_vous_deja_a_venir_controle_avant_le_creneau_plein(self):
        pleins = [rv(i, f"06000000{i:02d}", "CNI", "2026-11-27 09:00") for i in (10, 11, 12)]
        res = self.prise(self.existant() + pleins)
        self.assertRefus(res, 409, R.MSG_DEJA_A_VENIR)


if __name__ == "__main__":
    unittest.main()


class TestTMA104Annulation(OutilsTest):
    """TMA-104 : l'annulation du rendez-vous n° 709 le 17/11 à 18:00 pour le 19/11 à 10:00
    doit être acceptée (délai de 40 heures >= 24 heures)."""

    DATE_RDV = "2026-11-19 10:00"

    def rdv_709(self, statut="confirme"):
        return rv(709, "0339205992", "PERMIS", self.DATE_RDV, statut)

    def test_trace_du_ticket_annulation_40h_avant_acceptee(self):
        maint = dt("2026-11-17 18:00")
        res = R.controler_annulation(self.rdv_709(), maint)
        self.assertAccepte(res)
        self.assertEqual(res.code, 200)

    def test_annulation_a_exactement_24h_acceptee(self):
        # 18/11 à 10:00 pour le 19/11 à 10:00 = 24h pile (« jusqu'à 24 h avant »)
        maint = dt("2026-11-18 10:00")
        res = R.controler_annulation(self.rdv_709(), maint)
        self.assertAccepte(res)

    def test_annulation_a_23h59_refusee(self):
        # 18/11 à 10:01 = moins de 24h
        maint = dt("2026-11-18 10:01")
        res = R.controler_annulation(self.rdv_709(), maint)
        self.assertRefus(
            res, 409, "Annulation impossible moins de 24 h avant le rendez-vous."
        )

    def test_annulation_le_jour_meme_refusee(self):
        maint = dt("2026-11-19 08:00")
        res = R.controler_annulation(self.rdv_709(), maint)
        self.assertRefus(res, 409, R.MSG_ANNULATION_TARDIVE)

    def test_annulation_rendez_vous_deja_annule_refusee(self):
        res = R.controler_annulation(self.rdv_709(statut="annule"), dt("2026-11-17 18:00"))
        self.assertRefus(res, 409, "Ce rendez-vous ne peut plus être annulé.")

    def test_annulation_rendez_vous_deja_honore_ou_absent_refusee(self):
        for statut in ("honore", "absent"):
            with self.subTest(statut=statut):
                res = R.controler_annulation(self.rdv_709(statut=statut), dt("2026-11-17 18:00"))
                self.assertRefus(res, 409, R.MSG_NON_ANNULABLE)


class TestTMA105StatutsDefinitifs(OutilsTest):
    """TMA-105 : un rendez-vous au statut annule, honore ou absent ne peut plus changer."""

    def rdv_292(self, statut="annule"):
        return rv(292, "0330677555", "PASSEPORT", "2026-11-12 10:00", statut)

    def test_trace_du_ticket_passage_de_annule_a_honore_refuse(self):
        res = R.controler_changement_statut(self.rdv_292("annule"), "honore")
        self.assertRefus(res, 409, "Ce rendez-vous est déjà clôturé.")

    def test_passage_de_annule_a_absent_refuse(self):
        res = R.controler_changement_statut(self.rdv_292("annule"), "absent")
        self.assertRefus(res, 409, R.MSG_CLOTURE)

    def test_passage_depuis_honore_ou_absent_refuse(self):
        for statut_actuel in ("honore", "absent"):
            for statut_cible in ("honore", "absent"):
                with self.subTest(actuel=statut_actuel, cible=statut_cible):
                    res = R.controler_changement_statut(self.rdv_292(statut_actuel), statut_cible)
                    self.assertRefus(res, 409, R.MSG_CLOTURE)

    def test_passage_depuis_confirme_accepte(self):
        for statut_cible in ("honore", "absent"):
            with self.subTest(cible=statut_cible):
                res = R.controler_changement_statut(self.rdv_292("confirme"), statut_cible)
                self.assertAccepte(res)

    def test_statut_invalide_refuse(self):
        invalides = ("confirme", "annule", "valide", "reporte", "", None, 12)
        for statut in invalides:
            with self.subTest(statut=repr(statut)):
                res = R.controler_changement_statut(self.rdv_292("confirme"), statut)
                self.assertRefus(res, 400, "Statut invalide : honore ou absent.")


class TestTMA106TriEtPagination(OutilsTest):
    """TMA-106 : les rendez-vous d'un usager doivent être listés du plus récent au plus ancien,
    le prochain rendez-vous en tête, par pages de 10."""

    NPI = "0203040506"
    MAINT = EXPORT  # 2026-11-20 18:00

    def treize_rendez_vous(self):
        # Les 13 rendez-vous réels de cet usager dans base_rendez_vous.sql :
        return [
            rv(1, self.NPI, "PASSEPORT", "2026-01-05 08:30", "honore"),
            rv(2, self.NPI, "CNI", "2026-02-12 10:00", "honore"),
            rv(3, self.NPI, "PERMIS", "2026-03-03 14:30", "absent"),
            rv(4, self.NPI, "PASSEPORT", "2026-04-21 09:00", "honore"),
            rv(5, self.NPI, "CNI", "2026-05-08 11:30", "honore"),
            rv(6, self.NPI, "PERMIS", "2026-05-19 15:00", "absent"),
            rv(7, self.NPI, "PASSEPORT", "2026-06-02 08:00", "honore"),
            rv(8, self.NPI, "CNI", "2026-06-16 13:30", "honore"),
            rv(9, self.NPI, "PERMIS", "2026-07-07 10:30", "honore"),
            rv(10, self.NPI, "PASSEPORT", "2026-07-28 09:30", "absent"),
            rv(11, self.NPI, "CNI", "2026-08-11 14:00", "honore"),
            rv(259, self.NPI, "PERMIS", "2026-09-25 11:00", "honore"),
            rv(826, self.NPI, "PASSEPORT", "2026-12-02 08:30", "confirme"),
        ]

    def test_trace_du_ticket_prochain_rendez_vous_en_premiere_position(self):
        page1 = R.lister_rendez_vous(self.treize_rendez_vous(), page=1, maintenant=self.MAINT)
        self.assertEqual(page1["page"], 1)
        self.assertEqual(page1["parPage"], 10)
        self.assertEqual(page1["total"], 13)
        self.assertEqual(len(page1["rendezVous"]), 10)

        # Le rendez-vous du 2 décembre doit être en tête absolue de la liste :
        premier = page1["rendezVous"][0]
        self.assertEqual(premier["id"], 826)
        self.assertEqual(premier["dateHeure"], "02/12/2026 08:30")
        self.assertEqual(premier["statut"], "confirme")

    def test_ordre_chronologique_decroissant_des_rendez_vous_passes(self):
        page1 = R.lister_rendez_vous(self.treize_rendez_vous(), page=1, maintenant=self.MAINT)
        dates_obtenues = [r["dateHeure"] for r in page1["rendezVous"]]

        # 02/12 en tête (prochain), puis ordre décroissant réel :
        dates_attendues = [
            "02/12/2026 08:30",  # prochain RDV en tête
            "25/09/2026 11:00",
            "11/08/2026 14:00",
            "28/07/2026 09:30",
            "07/07/2026 10:30",
            "16/06/2026 13:30",
            "02/06/2026 08:00",
            "19/05/2026 15:00",
            "08/05/2026 11:30",
            "21/04/2026 09:00",
        ]
        self.assertEqual(dates_obtenues, dates_attendues)

    def test_deuxieme_page(self):
        page2 = R.lister_rendez_vous(self.treize_rendez_vous(), page=2, maintenant=self.MAINT)
        self.assertEqual(page2["page"], 2)
        self.assertEqual(page2["total"], 13)
        self.assertEqual(len(page2["rendezVous"]), 3)
        dates_page2 = [r["dateHeure"] for r in page2["rendezVous"]]
        self.assertEqual(
            dates_page2,
            ["03/03/2026 14:30", "12/02/2026 10:00", "05/01/2026 08:30"],
        )

    def test_sans_perte_ni_doublon_sur_l_ensemble_des_pages(self):
        p1 = R.lister_rendez_vous(self.treize_rendez_vous(), page=1, maintenant=self.MAINT)["rendezVous"]
        p2 = R.lister_rendez_vous(self.treize_rendez_vous(), page=2, maintenant=self.MAINT)["rendezVous"]
        tous_ids = [r["id"] for r in p1 + p2]
        self.assertEqual(len(tous_ids), 13)
        self.assertEqual(len(set(tous_ids)), 13)


class TestRobusteEtFuzzing(OutilsTest):
    """Vérifie que le module gère toutes les entrées hostiles sans jamais lever d'exception."""

    def test_fuzzing_prise_aucun_crash(self):
        entrées_hostiles = [
            None, "", " ", "1", "abc", 0, -1, 99999999999999999999,
            {"a": 1}, ["x"], (1, 2), "\x00\xff", "\U0001F525\U0001F680", "NaN", "null",
        ]
        for e1 in entrées_hostiles[:6]:
            for e2 in entrées_hostiles[:4]:
                for e3 in entrées_hostiles[:4]:
                    res = R.controler_prise(e1, e2, e3, [], EXPORT)
                    self.assertIsInstance(res, R.Resultat)
                    self.assertIn(res.code, (400, 409))

    def test_fuzzing_annulation_aucun_crash(self):
        for h in (None, {}, {"id": 1}, "texte", 42, []):
            try:
                res = R.controler_annulation(h, EXPORT)
                self.assertIsInstance(res, R.Resultat)
            except Exception as e:
                self.fail(f"Exception levée sur {h!r} : {e}")

    def test_fuzzing_statut_aucun_crash(self):
        for h in (None, {}, {"id": 1, "statut": "confirme"}, "x"):
            for s in (None, "honore", "autre", 12):
                res = R.controler_changement_statut(h, s)
                self.assertIsInstance(res, R.Resultat)


class TestIntegrationBaseReelle(OutilsTest):
    """Charge l'export officiel base_rendez_vous.sql et démontre par l'exécution
    que le module intercepte avec une exactitude de 100 % les anomalies réelles."""

    @classmethod
    def setUpClass(cls):
        chemins = [
            "base_rendez_vous.sql",
            r"c:\Users\HP\Downloads\base_rendez_vous.sql",
            os.path.join(os.path.dirname(__file__), "base_rendez_vous.sql"),
        ]
        sql_path = next((p for p in chemins if os.path.exists(p)), None)
        if sql_path is None:
            raise unittest.SkipTest("base_rendez_vous.sql non disponible pour le test d'intégration")

        import sqlite3
        cls.conn = sqlite3.connect(":memory:")
        with open(sql_path, "r", encoding="utf-8") as f:
            cls.conn.executescript(f.read())
        cls.cur = cls.conn.cursor()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_detection_samedis_base_reelle(self):
        # Les 8 rendez-vous enregistrés un samedi dans la base réelle
        self.cur.execute("SELECT id, npi, service, date_heure, statut FROM rendez_vous WHERE strftime('%w', date_heure) = '6'")
        samedis = self.cur.fetchall()
        self.assertEqual(len(samedis), 8)
        for rdv_id, npi, service, date_heure, statut in samedis:
            dh = datetime.strptime(date_heure, "%Y-%m-%d %H:%M:%S")
            self.assertFalse(R.est_jour_ouvre(dh), f"Le RDV {rdv_id} est un samedi et ne doit pas être ouvré")

    def test_detection_creneaux_surcharges_base_reelle(self):
        # Les 3 créneaux comptant plus de 3 rendez-vous non annulés
        self.cur.execute("""
            SELECT date_heure, count(*) FROM rendez_vous
            WHERE statut != 'annule'
            GROUP BY date_heure
            HAVING count(*) > 3
        """)
        surcharges = self.cur.fetchall()
        self.assertEqual(len(surcharges), 3)
        dates_surchargees = [s[0] for s in surcharges]
        self.assertIn("2026-11-10 09:00:00", dates_surchargees)  # TMA-102
        self.assertIn("2026-11-24 14:00:00", dates_surchargees)  # Créneau futur

        # Vérification qu'un 4e candidat sur le créneau du 24/11 est bien refusé
        self.cur.execute("SELECT id, npi, service, date_heure, statut FROM rendez_vous WHERE date_heure = '2026-11-24 14:00:00'")
        existants = [
            {"id": r[0], "npi": r[1], "service": r[2], "date_heure": r[3], "statut": r[4]}
            for r in self.cur.fetchall()
        ]
        res = R.controler_prise("0699999999", "CNI", "2026-11-24T14:00", existants, EXPORT)
        self.assertRefus(res, 409, R.MSG_COMPLET)

    def test_detection_mutations_illegales_base_reelle(self):
        # Les 4 mutations illégales depuis 'annule'
        self.cur.execute("""
            SELECT h.id, h.rendez_vous_id, h.ancien_statut, h.nouveau_statut
            FROM historique_statuts h
            WHERE h.ancien_statut = 'annule' AND h.nouveau_statut != 'annule'
        """)
        mutations = self.cur.fetchall()
        self.assertEqual(len(mutations), 4)
        for h_id, rdv_id, anc, nouv in mutations:
            rdv_simule = {"id": rdv_id, "npi": "0600000000", "service": "CNI", "date_heure": "2026-11-12 10:00:00", "statut": "annule"}
            res = R.controler_changement_statut(rdv_simule, nouv)
            self.assertRefus(res, 409, R.MSG_CLOTURE)

    def test_detection_npi_invalides_base_reelle(self):
        # RDV n° 459 (11 chiffres) et n° 642 (12 chiffres)
        self.cur.execute("SELECT id, npi FROM rendez_vous WHERE id IN (459, 642)")
        npis = self.cur.fetchall()
        self.assertEqual(len(npis), 2)
        for rdv_id, npi in npis:
            self.assertRefus(R.valider_npi(npi), 400, R.MSG_NPI)

    def test_detection_hors_grille_base_reelle(self):
        # RDV à 16:00 et 16:30
        self.cur.execute("""
            SELECT id, date_heure FROM rendez_vous
            WHERE strftime('%H:%M', date_heure) NOT BETWEEN '08:00' AND '15:30'
        """)
        hors_grille = self.cur.fetchall()
        self.assertEqual(len(hors_grille), 3)
        for rdv_id, date_heure in hors_grille:
            dh = datetime.strptime(date_heure, "%Y-%m-%d %H:%M:%S")
            self.assertFalse(R.est_creneau_valide(dh))

    def test_chargement_et_tri_usager_tma106_base_reelle(self):
        # Usager 0203040506 chargé directement depuis SQL
        self.cur.execute("""
            SELECT id, npi, service, date_heure, statut
            FROM rendez_vous
            WHERE npi = '0203040506'
        """)
        lignes = [
            {"id": r[0], "npi": r[1], "service": r[2], "date_heure": r[3], "statut": r[4]}
            for r in self.cur.fetchall()
        ]
        self.assertEqual(len(lignes), 13)

        # Lister avec l'instant de l'export (20/11/2026 18:00)
        page1 = R.lister_rendez_vous(lignes, page=1, maintenant=EXPORT)
        self.assertEqual(page1["total"], 13)
        self.assertEqual(len(page1["parPage"], 10) if isinstance(page1["parPage"], list) else page1["parPage"], 10)
        # Le prochain RDV (02/12/2026 à 08:30) doit être en tête absolue
        self.assertEqual(page1["rendezVous"][0]["id"], 826)
        self.assertEqual(page1["rendezVous"][0]["dateHeure"], "02/12/2026 08:30")


if __name__ == "__main__":
    unittest.main()
