from flask import Flask, request, jsonify
import sqlite3, uuid, math, os, json
from datetime import datetime, timedelta

app = Flask(__name__)

#####################################
# Base de données SQLite et initialisation
#####################################
def get_db_connection():
    DATABASE = os.path.join(os.getcwd(), "mopatas.db")
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_company_account():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM company_account WHERE id = 1")
    company = cursor.fetchone()
    conn.close()
    return company

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Table des utilisateurs avec colonne codeCompte ajoutée
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        numero TEXT UNIQUE NOT NULL,
        pass_word TEXT NOT NULL,
        solde REAL NOT NULL,
        type_compte TEXT NOT NULL DEFAULT 'standard',
        codeCompte TEXT
      )
    ''')
    # Table des transactions avec timestamp pour expiration de code_session
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_envoyeur TEXT NOT NULL,
        numero_destinataire TEXT NOT NULL,
        montant REAL NOT NULL,
        type TEXT NOT NULL,
        code_session TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL,
        transaction_hash TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    ''')
    # Table des inscriptions en attente avec colonne codeCompte ajoutée
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS pending_registrations (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         code_session TEXT UNIQUE NOT NULL,
         nom TEXT NOT NULL,
         numero TEXT NOT NULL,
         pass_word TEXT NOT NULL,
         type_compte TEXT NOT NULL DEFAULT 'standard',
         solde REAL NOT NULL,
         code_entite TEXT,
         codeCompte TEXT,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    ''')
    # Table du compte d'entreprise avec mot de passe et solde (le float)
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS company_account (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solde REAL NOT NULL,
        pass_word TEXT NOT NULL
      )
    ''')
    cursor.execute("SELECT COUNT(*) as count FROM company_account")
    row = cursor.fetchone()
    if row["count"] == 0:
        # Charger la configuration depuis config.json pour initialiser le compte company
        config_file = os.path.join(os.getcwd(), "config.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                config = json.load(f)
            company_config = config.get("company_account", {})
            company_solde = float(company_config.get("solde", 2000000.0))
            company_password = company_config.get("pass_word", "adminpassword")
        else:
            company_solde = 2000000.0
            company_password = "adminpassword"
        cursor.execute("INSERT INTO company_account (solde, pass_word) VALUES (?, ?)", (company_solde, company_password))
    
    # Table premium_services pour enregistrer les transactions de type liquider/paie
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS premium_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_paiement TEXT NOT NULL,
        id_payeur TEXT NOT NULL,
        transaction_hash TEXT NOT NULL
      )
    ''')
    conn.commit()
    conn.close()

#####################################
# Fonctions utilitaires SQL
#####################################
def insert_user(nom, numero, pass_word, type_compte="standard", solde=0.0, codeCompte=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (nom, numero, pass_word, solde, type_compte, codeCompte) VALUES (?, ?, ?, ?, ?, ?)",
                   (nom, numero, pass_word, solde, type_compte, codeCompte))
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
    """
    Met à jour le solde du compte d'entreprise (float).
    Un montant positif l'augmente, un montant négatif le diminue.
    """
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
        if is_session_expired(transaction["timestamp"]):
            cursor.execute("UPDATE transactions SET status = 'expired' WHERE code_session = ?", (code_session,))
            conn.commit()
            conn.close()
            return None
        cursor.execute("UPDATE transactions SET status = 'completed' WHERE code_session = ?", (code_session,))
        conn.commit()
        conn.close()
        return transaction
    conn.close()
    return None

def generate_session_code():
    return str(uuid.uuid4())[:8]

def insert_pending_registration(code_session, nom, numero, pass_word, type_compte, solde, code_entite, codeCompte):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO pending_registrations (code_session, nom, numero, pass_word, type_compte, solde, code_entite, codeCompte) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (code_session, nom, numero, pass_word, type_compte, solde, code_entite, codeCompte))
    conn.commit()
    conn.close()

def get_pending_registration(code_session):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_registrations WHERE code_session = ?", (code_session,))
    pending = cursor.fetchone()
    conn.close()
    return pending

def delete_pending_registration(code_session):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_registrations WHERE code_session = ?", (code_session,))
    conn.commit()
    conn.close()

def is_session_expired(timestamp_str):
    """
    Vérifie si le timestamp (format 'YYYY-MM-DD HH:MM:SS') est plus vieux de 10 minutes.
    """
    session_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    return datetime.now() > session_time + timedelta(minutes=10)

#####################################
# Calcul des frais (interpolation)
#####################################
def calculate_fees(montant, transaction_type):
    if transaction_type in ['envoi', 'depot']:
        return 0
    fee = 0
    if montant <= 20000:
        fee = montant * 0.05
    elif montant <= 100000:
        rate = 0.05 - (montant - 20000) * ((0.05 - 0.035) / (100000 - 20000))
        fee = montant * rate
    elif montant <= 1000000:
        rate = 0.03 - (montant - 200000) * ((0.03 - 0.015) / (1000000 - 200000))
        fee = montant * rate
    else:
        fee = montant * 0.01
    return fee

#####################################
# Traitement de la transaction
#####################################
def process_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, code_paie=None, id_paie=None):
    sender = get_user_by_number(numero_envoyeur)
    if not sender:
        return {'error': 'Envoyeur non trouvé'}, 400

    sender_balance = sender['solde']
    montant = float(montant)
    montant = round(montant)
    fee = calculate_fees(montant, transaction_type)
    total_debit = montant + fee

    if transaction_type == 'retrait':
        if sender_balance < total_debit:
            return {'error': 'Solde insuffisant pour le retrait'}, 400
        new_sender_balance = sender_balance - total_debit
        update_user_balance(numero_envoyeur, new_sender_balance)
        update_company_account(montant + fee)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET transaction_hash = ? WHERE code_session = ?", (transaction_hash, code_session))
        conn.commit()
        conn.close()
        return {'message': 'Transaction de retrait réussie', 'new_balance': new_sender_balance, 'transaction_hash': transaction_hash}, 200

    elif transaction_type == 'envoi':
        if sender_balance < montant:
            return {'error': 'Solde insuffisant pour l\'envoi'}, 400
        new_sender_balance = sender_balance - montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            new_recipient_balance = recipient['solde'] + montant
            update_user_balance(numero_destinataire, new_recipient_balance)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET transaction_hash = ? WHERE code_session = ?", (transaction_hash, code_session))
        conn.commit()
        conn.close()
        return {'message': 'Envoi réussi', 'new_balance': new_sender_balance, 'transaction_hash': transaction_hash}, 200

    elif transaction_type in ['liquider', 'paie']:
        parts = numero_destinataire.split(';')
        if len(parts) < 3:
            return {'error': 'Format invalide pour liquider/payer'}, 400
        destinataire_phone = parts[0].strip()
        recipient = get_user_by_number(destinataire_phone)
        if not recipient:
            return {'error': 'Destinataire non trouvé'}, 400

        code_paie_received = parts[1].strip()
        id_paie_received = parts[2].strip()
        if code_paie and code_paie != code_paie_received:
            return {'error': 'Code de paiement invalide'}, 400
        if id_paie and id_paie != id_paie_received:
            return {'error': 'ID de paiement invalide'}, 400

        if sender_balance < total_debit:
            return {'error': 'Solde insuffisant pour la transaction'}, 400
        new_sender_balance = sender_balance - total_debit
        update_user_balance(numero_envoyeur, new_sender_balance)
        bonus = fee * 0.2
        new_recipient_balance = recipient['solde'] + bonus
        update_user_balance(destinataire_phone, new_recipient_balance)
        update_company_account(fee - bonus)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET transaction_hash = ? WHERE code_session = ?", (transaction_hash, code_session))
        conn.commit()
        conn.close()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO premium_services (id_paiement, id_payeur, transaction_hash) VALUES (?, ?, ?)",
                       (code_paie_received, id_paie_received, transaction_hash))
        conn.commit()
        conn.close()
        return {'message': 'Transaction de liquider/payer réussie', 'new_balance': new_sender_balance, 'transaction_hash': transaction_hash}, 200

    elif transaction_type == 'depot':
        if sender_balance < montant:
            return {'error': 'Solde insuffisant pour le dépôt'}, 400
        new_sender_balance = sender_balance - montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            new_recipient_balance = recipient['solde'] + montant
            update_user_balance(numero_destinataire, new_recipient_balance)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET transaction_hash = ? WHERE code_session = ?", (transaction_hash, code_session))
        conn.commit()
        conn.close()
        return {'message': 'Dépôt réussi', 'new_balance': new_sender_balance, 'transaction_hash': transaction_hash}, 200

    elif transaction_type == 'depot_pro':
        if sender['type_compte'] not in ['agent', 'premium']:
            return {'error': 'Le compte de l\'envoyeur n\'est pas un agent valide pour depot_pro'}, 400
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT solde FROM company_account WHERE id = 1")
        company = cursor.fetchone()
        conn.close()
        if not company or company["solde"] < montant:
            return {'error': 'Fonds insuffisants dans le compte d\'entreprise pour le dépôt pro'}, 400
        update_company_account(-montant)
        new_sender_balance = sender_balance + montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET transaction_hash = ? WHERE code_session = ?", (transaction_hash, code_session))
        conn.commit()
        conn.close()
        return {'message': 'Dépôt pro réussi', 'new_balance': new_sender_balance, 'transaction_hash': transaction_hash}, 200

    else:
        return {'error': 'Type de transaction inconnu'}, 400

#####################################
# Endpoints
#####################################

# Endpoint de test (n'affiche pas les utilisateurs)
@app.route('/test', methods=['GET'])
def test_endpoint():
    return jsonify({"message": "API is running"}), 200

# Endpoint balance classique (vérifie aussi le codeCompte)
@app.route('/balance', methods=['POST'])
def balance_endpoint():
    data = request.get_json()
    numero = data.get('numero')
    codeCompte_req = data.get('codeCompte')
    user = get_user_by_number(numero)
    if user and data.get('pass_word') == user['pass_word']:
        if user.get('codeCompte') is not None and codeCompte_req != user.get('codeCompte'):
            return jsonify({'error': 'codeCompte invalide'}), 400
        return jsonify([{
            "solde": user['solde'],
            "message": f"Bonjour {user['nom']}, votre solde est de {user['solde']}!"
        }]), 200
    else:
        return jsonify({'error': 'Echec de vérification de solde ou mot de passe incorrect'}), 400

# Endpoint balance_pro pour les comptes premium (vérifie également le codeCompte)
@app.route('/balance_pro', methods=['POST'])
def balance_pro_endpoint():
    data = request.get_json()
    numero = data.get('numero')
    codeCompte_req = data.get('codeCompte')
    user = get_user_by_number(numero)
    if not user or data.get('pass_word') != user['pass_word']:
        return jsonify({'error': 'Utilisateur non trouvé ou mot de passe incorrect'}), 400
    if user.get('codeCompte') is not None and codeCompte_req != user.get('codeCompte'):
        return jsonify({'error': 'codeCompte invalide'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_paiement, id_payeur, transaction_hash FROM premium_services WHERE id_payeur = ?", (user['numero'],))
    premium_services = cursor.fetchall()
    conn.close()
    premium_list = [{"id_paiement": row["id_paiement"], "id_payeur": row["id_payeur"], "transaction_hash": row["transaction_hash"]} for row in premium_services]
    return jsonify({
         "solde": user["solde"],
         "message": f"Bonjour {user['nom']}, votre solde est de {user['solde']}!",
         "premium_services": premium_list
    }), 200

# Inscription avec confirmation et initialisation pour agent
@app.route('/inscription', methods=['POST'])
def inscription_endpoint():
    data = request.get_json()
    confirmation = data.get('confirmation')
    # Si c'est la confirmation d'inscription
    if confirmation == "yes":
        code_session = data.get('code_session')
        if not code_session:
            return jsonify({'error': 'code_session requis pour confirmation'}), 400
        pending = get_pending_registration(code_session)
        if not pending:
            return jsonify({'error': 'Code de session invalide ou déjà confirmé'}), 400
        if is_session_expired(pending["timestamp"]):
            delete_pending_registration(code_session)
            return jsonify({'error': 'Code de session expiré'}), 400
        # Lors de la confirmation, on récupère le codeCompte envoyé par l'utilisateur
        insert_user(pending["nom"], pending["numero"], pending["pass_word"], pending["type_compte"], pending["solde"], pending.get("codeCompte"))
        delete_pending_registration(code_session)
        return jsonify({'message': 'Inscription confirmée', 'numero': pending["numero"], 'type_compte': pending["type_compte"], 'codeCompte': pending.get("codeCompte")}), 201
    else:
        nom = data.get('nom')
        pass_word = data.get('pass_word')
        numero = data.get('numero')
        solde = float(data.get('montant', 0.0))
        type_compte = data.get('type_compte', 'standard')
        code_entite = data.get('code_entite')
        # Vérification des champs obligatoires
        if not nom or not pass_word or not numero:
            return jsonify({'error': 'Tous les champs (nom, pass_word, numero) doivent être remplis'}), 400
        # Si le compte existe déjà et que l'agent souhaite l'initialiser
        if data.get('allready_have'):
            # L'agent fournit son codeCompte
            codeCompte_req = data.get('codeCompte')
            if not codeCompte_req:
                return jsonify({'error': 'codeCompte requis pour initialiser un compte déjà existant'}), 400
            user = get_user_by_number(numero)
            if not user:
                return jsonify({'error': 'Aucun compte existant pour ce numéro'}), 400
            if user['pass_word'] != pass_word:
                return jsonify({'error': 'Mot de passe incorrect'}), 400
            if user.get("codeCompte") != codeCompte_req:
                return jsonify({'error': 'codeCompte invalide'}), 400
            return jsonify({'message': 'Compte initialisé avec succès', 'codeCompte': codeCompte_req, 'nom': user['nom'], 'numero': user['numero'], 'solde': user['solde'], 'type_compte': user['type_compte']}), 200
        # Pour une nouvelle inscription, on vérifie si le compte est de type agent
        if type_compte == 'agent':
            company_pass_input = data.get("company_pass")
            if not company_pass_input:
                return jsonify({'error': 'Le mot de passe du compte company est requis pour inscrire un agent'}), 400
            company = get_company_account()
            if company is None or company_pass_input != company["pass_word"]:
                return jsonify({'error': 'Mot de passe company incorrect'}), 400
            # L'agent doit fournir son codeCompte lors de l'inscription
            agent_codeCompte = data.get('codeCompte')
            if not agent_codeCompte:
                return jsonify({'error': 'codeCompte requis pour l\'inscription d\'un agent'}), 400
        else:
            agent_codeCompte = None
        if get_user_by_number(numero):
            return jsonify({'error': 'Numéro déjà inscrit'}), 400
        code_session = generate_session_code()
        insert_pending_registration(code_session, nom, numero, pass_word, type_compte, solde, code_entite, agent_codeCompte)
        confirmation_message = f"Inscription demandée pour {nom}. Veuillez confirmer avec code_session: {code_session}"
        return jsonify({'message': confirmation_message, 'code_session': code_session}), 200

# Demande de transaction : génère un code de session et enregistre la transaction en attente
@app.route('/transaction', methods=['POST'])
def transaction_endpoint():
    data = request.get_json()
    numero_destinataire = data.get('numero_destinataire')
    numero_envoyeur = data.get('numero_envoyeur')
    montant = data.get('montant')
    pass_word = data.get('pass_word')
    transaction_type = data.get('transaction_type')
    code_paie = data.get('code_paie')  # Pour liquider/payer
    id_paie = data.get('id_paie')      # Pour liquider/payer
    codeCompte_req = data.get('codeCompte')

    if not numero_destinataire or not numero_envoyeur or not montant or not transaction_type:
        return jsonify({'error': 'Tous les champs doivent être remplis'}), 400

    sender = get_user_by_number(numero_envoyeur)
    if not sender or sender['pass_word'] != pass_word:
        return jsonify({'error': 'Mot de passe incorrect ou utilisateur non trouvé'}), 400
    if sender.get("codeCompte") is not None and codeCompte_req != sender.get("codeCompte"):
        return jsonify({'error': 'codeCompte invalide'}), 400

    code_session = generate_session_code()
    insert_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session)

    recipient_name = "Inconnu"
    if transaction_type in ['retrait', 'envoi', 'depot', 'depot_pro']:
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            recipient_name = recipient['nom']
    elif transaction_type in ['liquider', 'paie']:
        parts = numero_destinataire.split(';')
        if len(parts) >= 1:
            destinataire_phone = parts[0].strip()
            recipient = get_user_by_number(destinataire_phone)
            if recipient:
                recipient_name = recipient['nom']

    confirmation_message = f"Vous demandez une transaction de {montant} FC à {recipient_name}. Confirmez-vous ?"
    return jsonify({'message': confirmation_message, 'code_session': code_session}), 200

# Confirmation de transaction
@app.route('/confirm_transaction', methods=['POST'])
def confirm_transaction_endpoint():
    data = request.get_json()
    code_session = data.get('code_session')
    if not code_session:
        return jsonify({'error': 'Le code de session est requis'}), 400
    code_paie = data.get('code_paie')
    id_paie = data.get('id_paie')

    transaction_data = validate_transaction(code_session)
    if transaction_data is None:
        return jsonify({'error': 'Code de session invalide, expiré ou transaction déjà confirmée'}), 400

    numero_envoyeur = transaction_data['numero_envoyeur']
    numero_destinataire = transaction_data['numero_destinataire']
    montant = transaction_data['montant']
    transaction_type = transaction_data['type']

    result, status = process_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, code_paie, id_paie)
    return jsonify(result), status

if __name__ == '__main__':
    init_db()  # Initialise la base de données et crée les tables si nécessaire
    app.run(debug=True)
