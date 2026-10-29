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

R = importlib.import_module(os.environ.get("REGLES_MODULE", "regles_rendez_vous"))

EXPORT = datetime(2026, 11, 20, 18, 0)  # instant de l'export de la base


def dt(texte):
    return datetime.strptime(texte, "%Y-%m-%d %H:%M")


class OutilsTest(unittest.TestCase):
    def assertRefus(self, res, code, message):
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
