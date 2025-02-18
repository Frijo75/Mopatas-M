# Mopatas

Mopatas est une application de gestion de portefeuille et de transactions financières développée dans le but de faciliter les paiements mobiles en République Démocratique du Congo. Mopatas permet aux utilisateurs d'envoyer, de retirer de l'argent, et de payer des factures de manière sécurisée. Elle offre également des solutions de paiement pour les entreprises et réduit les risques liés à la gestion d'argent liquide.

## Fonctionnalités principales

- **Envoi d'argent** : Permet à l'utilisateur d'envoyer de l'argent à d'autres utilisateurs en utilisant leur numéro de téléphone.
- **Retrait d'argent** : Permet à l'utilisateur de retirer de l'argent de son compte Mopatas vers un point de retrait physique ou un autre utilisateur.
- **Paiement de factures** : Permet à l'utilisateur de payer des factures telles que celles de la SNEL ou Canal+.
- **Gestion des transactions** : Offre la possibilité de visualiser l'historique des transactions, et d'effectuer des paiements directs en utilisant le solde du portefeuille.
- **QR Code** : Génère un QR code pour chaque utilisateur, facilitant ainsi l'envoi et la réception de paiements sans saisie manuelle du numéro.

## Architecture

L'application est développée en **Flutter** pour les applications mobiles, et intègre des services backend pour la gestion des utilisateurs et des transactions via une API.

- **Frontend** : Flutter
- **Backend** : Python (Flask) avec MySQL pour la gestion des données.
- **API** : Fournit des services pour la gestion des utilisateurs, des transactions, et du solde.

## Installation

### Pré-requis

- Flutter installé sur votre machine pour le développement mobile.
- Python 3.x et MySQL pour le backend.
- Compte sur une plateforme de cloud (ex. Render) pour déployer l'API.

### Configuration du backend

1. Clonez le repository et accédez au dossier du backend.
2. Créez un environnement virtuel et installez les dépendances :

```bash
python -m venv venv
source venv/bin/activate  # Pour Linux/Mac
venv\Scripts\activate  # Pour Windows
pip install -r requirements.txt
