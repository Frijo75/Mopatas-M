from flask import Flask, request, jsonify
import sqlite3, uuid, math
import json

app = Flask(__name__)

#####################################
# Base de données SQLite et initialisation
#####################################
def get_db_connection():
    conn = sqlite3.connect('mopatas.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Table des utilisateurs
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        numero TEXT UNIQUE NOT NULL,
        pass_word TEXT NOT NULL,
        solde REAL NOT NULL
      )
    ''')
    # Table des transactions
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_envoyeur TEXT NOT NULL,
        numero_destinataire TEXT NOT NULL,
        montant REAL NOT NULL,
        type TEXT NOT NULL,
        code_session TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL
      )
    ''')
    # Compte d'entreprise (une seule ligne)
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS company_account (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solde REAL NOT NULL
      )
    ''')
    cursor.execute("SELECT COUNT(*) as count FROM company_account")
    row = cursor.fetchone()
    if row["count"] == 0:
        cursor.execute("INSERT INTO company_account (solde) VALUES (?)", (0.0,))
    conn.commit()
    conn.close()

#####################################
# Fonctions utilitaires SQL
#####################################
def insert_user(nom, numero, pass_word):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (nom, numero, pass_word, solde) VALUES (?, ?, ?, ?)",
                   (nom, numero, pass_word, 0.0))
    conn.commit()
    conn.close()

def get_user_by_number(numero):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE numero = ?", (numero,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_balance(numero, new_balance):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET solde = ? WHERE numero = ?", (new_balance, numero))
    conn.commit()
    conn.close()

def update_company_account(amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE company_account SET solde = solde + ? WHERE id = 1", (amount,))
    conn.commit()
    conn.close()

def insert_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
      INSERT INTO transactions (numero_envoyeur, numero_destinataire, montant, type, code_session, status)
      VALUES (?, ?, ?, ?, ?, ?)
    """, (numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, 'pending'))
    conn.commit()
    conn.close()

def validate_transaction(code_session):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE code_session = ? AND status = 'pending'", (code_session,))
    transaction = cursor.fetchone()
    if transaction:
        cursor.execute("UPDATE transactions SET status = 'completed' WHERE code_session = ?", (code_session,))
        conn.commit()
        conn.close()
        return transaction
    conn.close()
    return None

def generate_session_code():
    return str(uuid.uuid4())[:8]

#####################################
# Calcul des frais (interpolation)
#####################################
def calculate_fees(montant, transaction_type):
    # Pour 'envoi', pas de frais
    if transaction_type == 'envoi':
        return 0
    fee = 0
    if montant <= 20000:
        fee = montant * 0.05
    elif montant <= 100000:
        # Taux linéaire entre 5% et 3,5%
        rate = 0.05 - (montant - 20000) * ((0.05 - 0.035) / (100000 - 20000))
        fee = montant * rate
    elif montant <= 1000000:
        # Taux linéaire entre 3% et 1,5%
        rate = 0.03 - (montant - 200000) * ((0.03 - 0.015) / (1000000 - 200000))
        fee = montant * rate
    else:
        fee = montant * 0.01
    return fee

#####################################
# Traitement de la transaction
#####################################
def process_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_paie=None, id_paie=None):
    sender = get_user_by_number(numero_envoyeur)
    if not sender:
        return {'error': 'Envoyeur non trouvé'}, 400

    sender_balance = sender['solde']
    montant = float(montant)
    montant = round(montant)  # montant arrondi
    fee = calculate_fees(montant, transaction_type)
    total_debit = montant + fee

    if transaction_type in ['retrait']:
        if sender_balance < total_debit:
            return {'error': 'Solde insuffisant pour effectuer la transaction'}, 400
        new_sender_balance = sender_balance - total_debit
        update_user_balance(numero_envoyeur, new_sender_balance)
        # Pour retrait, le destinataire est fourni directement
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            bonus = fee * 0.2
            new_recipient_balance = recipient['solde'] + bonus
            update_user_balance(numero_destinataire, new_recipient_balance)
            update_company_account(fee - bonus)
        return {'message': 'Transaction de retrait réussie', 'new_balance': new_sender_balance}, 200

    elif transaction_type == 'envoi':
        if sender_balance < montant:
            return {'error': 'Solde insuffisant pour effectuer l\'envoi'}, 400
        new_sender_balance = sender_balance - montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            new_recipient_balance = recipient['solde'] + montant
            update_user_balance(numero_destinataire, new_recipient_balance)
        return {'message': 'Envoi réussi', 'new_balance': new_sender_balance}, 200

    elif transaction_type in ['liquider', 'paie']:
        # Pour liquider/payer, numero_destinataire est au format "destinataire_phone;code_paie;id_paie"
        parts = numero_destinataire.split(';')
        if len(parts) < 3:
            return {'error': 'Format invalide pour liquider/payer'}, 400
        destinataire_phone = parts[0].strip()  # On récupère la clause 0 qui correspond au numéro du destinataire
        recipient = get_user_by_number(destinataire_phone)
        if not recipient:
            return {'error': 'Destinataire non trouvé'}, 400

        # Vérification du code de paiement et ID (si fournis dans la requête)
        code_paie_received = parts[1].strip()
        id_paie_received = parts[2].strip()
        if code_paie and code_paie != code_paie_received:
            return {'error': 'Code de paiement invalide'}, 400
        if id_paie and id_paie != id_paie_received:
            return {'error': 'ID de paiement invalide'}, 400

        if sender_balance < total_debit:
            return {'error': 'Solde insuffisant pour effectuer la transaction'}, 400
        new_sender_balance = sender_balance - total_debit
        update_user_balance(numero_envoyeur, new_sender_balance)
        bonus = fee * 0.2
        new_recipient_balance = recipient['solde'] + bonus
        update_user_balance(destinataire_phone, new_recipient_balance)
        update_company_account(fee - bonus)
        return {'message': 'Transaction de liquider/payer réussie', 'new_balance': new_sender_balance}, 200

    else:
        return {'error': 'Type de transaction inconnu'}, 400

#####################################
# Endpoints
#####################################

# Route de test
@app.route('/test', methods=['GET'])
def test_endpoint():
    return jsonify({'message': 'L\'API fonctionne correctement!'}), 200

# Inscription
@app.route('/inscription', methods=['POST'])
def inscription_endpoint():
    data = request.get_json()
    nom = data.get('nom')
    pass_word = data.get('pass_word')
    numero = data.get('numero')

    if not nom or not pass_word or not numero:
        return jsonify({'error': 'Tous les champs doivent être remplis'}), 400

    if get_user_by_number(numero):
        return jsonify({'error': 'Numéro déjà inscrit'}), 400

    insert_user(nom, numero, pass_word)
    return jsonify({'message': 'Inscription réussie', 'numero': numero}), 201

# Demande de transaction : génère un code de session et enregistre la transaction en attente
@app.route('/transaction', methods=['POST'])
def transaction_endpoint():
    data = request.get_json()
    numero_destinataire = data.get('numero_destinataire')
    numero_envoyeur = data.get('numero_envoyeur')
    montant = data.get('montant')
    pass_word = data.get('pass_word')
    transaction_type = data.get('type')
    code_paie = data.get('code_paie')
    id_paie = data.get('id_paie')

    if not numero_destinataire or not numero_envoyeur or not montant or not transaction_type:
        return jsonify({'error': 'Tous les champs doivent être remplis'}), 400

    sender = get_user_by_number(numero_envoyeur)
    if not sender or sender['pass_word'] != pass_word:
        return jsonify({'error': 'Mot de passe incorrect ou utilisateur non trouvé'}), 400

    # Générer un code de session unique
    code_session = generate_session_code()
    # Enregistrer la transaction en statut "pending"
    insert_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session)

    # Récupérer le nom du destinataire pour affichage
    recipient_name = None
    if transaction_type in ['retrait', 'envoi']:
        recipient = get_user_by_number(numero_destinataire)
        recipient_name = recipient['nom'] if recipient else "Inconnu"
    elif transaction_type in ['liquider', 'paie']:
        # Pour liquider/payer, on récupère la clause 0 qui correspond au numéro du destinataire
        parts = numero_destinataire.split(';')
        if len(parts) < 3:
            return jsonify({'error': 'Format invalide pour liquider/payer'}), 400
        destinataire_phone = parts[0].strip()
        recipient = get_user_by_number(destinataire_phone)
        recipient_name = recipient['nom'] if recipient else "Inconnu"

    confirmation_message = f"Vous demandez une transaction de {montant} FC à {recipient_name}. Confirmez-vous ?"
    # Retourner le message de confirmation ainsi que le code de session pour la confirmation
    return jsonify({'message': confirmation_message, 'code_session': code_session}), 200

# Confirmation de transaction : l'utilisateur envoie le code de session pour valider la transaction
@app.route('/confirm_transaction', methods=['POST'])
def confirm_transaction_endpoint():
    data = request.get_json()
    code_session = data.get('code_session')
    if not code_session:
        return jsonify({'error': 'Le code de session est requis'}), 400

    # Valider la transaction (passer de pending à completed) et récupérer ses détails
    transaction_data = validate_transaction(code_session)
    if transaction_data is None:
        return jsonify({'error': 'Code de session invalide ou transaction déjà confirmée'}), 400

    numero_envoyeur = transaction_data['numero_envoyeur']
    numero_destinataire = transaction_data['numero_destinataire']
    montant = transaction_data['montant']
    transaction_type = transaction_data['type']

    result, status = process_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type)
    return jsonify(result), status

if __name__ == '__main__':
    init_db()  # Initialise la base de données et crée les tables si nécessaire
    app.run(debug=True)
