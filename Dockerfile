# Image minimale officielle ultra-legere (Python 3.12 Alpine ~50 Mo)
FROM python:3.12-alpine

WORKDIR /app

# Copie des fichiers metier, de tests, de base et des requetes d'exploitation
COPY regles_rendez_vous.py test_regles_rendez_vous.py version_boguee.py requetes.sql base_rendez_vous.sql ./

# Commande par defaut : execution de la suite de 58 tests automatises
CMD ["python", "-m", "unittest", "-v", "test_regles_rendez_vous.py"]
