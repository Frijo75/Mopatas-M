from flask import Flask, request, jsonify
import mysql.connector
import uuid
import math
import setup_db
app = Flask(__name__)

# --- Connexion à la base de données MySQL ---
def get_db_connection():
    conn = mysql.connector.connect(
        host='localhost',       # modifiez selon votre configuration
        user='root',            # modifiez selon votre configuration
        password='password',    # modifiez selon votre configuration
        database='mopatas'
    )
    return conn

# --- Fonctions utilitaires pour la gestion des utilisateurs ---

def insert_user(nom, numero, pass_word):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (nom, numero, pass_word, solde) VALUES (%s, %s, %s, %s)",
        (nom, numero, pass_word, 0.0)
    )
    conn.commit()
    conn.close()

def get_user_by_number(numero):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE numero = %s", (numero,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_balance(numero, new_balance):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET solde = %s WHERE numero = %s", (new_balance, numero))
    conn.commit()
    conn.close()

# --- Fonction pour mettre à jour le compte entreprise ---
def update_company_balance(amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE company SET solde = solde + %s", (amount,))
    conn.commit()
    conn.close()

# --- Fonction de calcul des frais ---
def calculate_fee(montant):
    if montant <= 20000:
        fee = montant * 0.05
    elif montant <= 100000:
        fee = montant * 0.035
    elif montant <= 200000:
        fee = montant * 0.03
    elif montant <= 1000000:
        fee = montant * 0.015
    else:
        fee = montant * 0.01
    return fee

# --- Génération d'un code de session unique ---
def generate_session_code():
    return str(uuid.uuid4())[:8]

# --- Insertion d'une transaction en attente ---
def insert_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, extra_data=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (numero_envoyeur, numero_destinataire, montant, type, code_session, status, extra_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, 'pending', extra_data))
    conn.commit()
    conn.close()

# --- Exécution de la transaction à la confirmation ---
def complete_transaction(code_session):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM transactions WHERE code_session = %s AND status = %s", (code_session, 'pending'))
    transaction = cursor.fetchone()
    if not transaction:
        conn.close()
        return {'error': 'Transaction non trouvée ou déjà confirmée'}
    
    sender = get_user_by_number(transaction['numero_envoyeur'])
    recipient = get_user_by_number(transaction['numero_destinataire'])
    if not sender or not recipient:
        conn.close()
        return {'error': 'Utilisateur introuvable'}

    montant = transaction['montant']
    trans_type = transaction['type']

    # Pour retrait, liquider, payer : frais s'appliquent
    if trans_type in ['retrait', 'liquider', 'payer']:
        fee = calculate_fee(montant)
        required = montant + fee
        if sender['solde'] < required:
            conn.close()
            return {'error': 'Solde insuffisant pour la transaction avec frais'}

        new_sender_balance = sender['solde'] - required
        # 20% des frais sont crédités au destinataire, 80% vont au compte entreprise
        recipient_credit = montant + (fee * 0.2)
        new_recipient_balance = recipient['solde'] + recipient_credit
        update_user_balance(sender['numero'], new_sender_balance)
        update_user_balance(recipient['numero'], new_recipient_balance)
        update_company_balance(fee * 0.8)
    elif trans_type == 'envoi':
        if sender['solde'] < montant:
            conn.close()
            return {'error': 'Solde insuffisant pour l\'envoi'}
        new_sender_balance = sender['solde'] - montant
        new_recipient_balance = recipient['solde'] + montant
        update_user_balance(sender['numero'], new_sender_balance)
        update_user_balance(recipient['numero'], new_recipient_balance)
    else:
        conn.close()
        return {'error': 'Type de transaction inconnu'}

    # Marquer la transaction comme complétée
    cursor.execute("UPDATE transactions SET status = %s WHERE code_session = %s", ('completed', code_session))
    conn.commit()
    conn.close()
    return {'message': 'Transaction complétée avec succès'}
    
@app.route('/start', methods=['GET'])
def health_check():
    return {"status": "healthy"}, 200

# --- Endpoint d'inscription ---
@app.route('/inscription', methods=['POST'])
def api_inscription():
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

# --- Endpoint de demande de transaction ---
@app.route('/transaction', methods=['POST'])
def api_transaction():
    data = request.get_json()
    numero_envoyeur = data.get('numero_envoyeur')
    montant = data.get('montant')
    pass_word = data.get('pass_word')
    transaction_type = data.get('type')  # retrait, envoi, liquider, payer
    destinataire_field = data.get('destinateur')  # Pour retrait/envoi: numéro; pour liquider/payer: "code_paie;id_paie;destinataire"
    
    if not numero_envoyeur or not montant or not transaction_type:
        return jsonify({'error': 'Tous les champs obligatoires doivent être remplis'}), 400

    try:
        montant = int(montant)
    except ValueError:
        return jsonify({'error': 'Le montant doit être un nombre entier'}), 400

    # Vérifier l'envoyeur et son mot de passe
    sender = get_user_by_number(numero_envoyeur)
    if not sender:
        return jsonify({'error': 'Envoyeur non trouvé'}), 400
    if sender['pass_word'] != pass_word:
        return jsonify({'error': 'Mot de passe incorrect'}), 400

    # Pour retrait et envoi, le destinataire est directement donné
    # Pour liquider et payer, le champ destinateur contient "code_paie;id_paie;destinataire"
    numero_destinataire = None
    extra_data = None
    if transaction_type in ['retrait', 'envoi']:
        numero_destinataire = destinataire_field
    elif transaction_type in ['liquider', 'payer']:
        parts = destinataire_field.split(';')
        if len(parts) != 3:
            return jsonify({'error': 'Pour liquider ou payer, le champ destinateur doit contenir "code_paie;id_paie;destinataire"'}), 400
        code_paie = parts[0].strip()
        id_paie = parts[1].strip()
        numero_destinataire = parts[2].strip()
        extra_data = f"code_paie:{code_paie}; id_paie:{id_paie}"
    else:
        return jsonify({'error': 'Type de transaction inconnu'}), 400

    # Vérifier que le destinataire existe
    recipient = get_user_by_number(numero_destinataire)
    if not recipient:
        return jsonify({'error': 'Destinataire non trouvé'}), 400

    # Générer un code de session unique pour la transaction
    code_session = generate_session_code()

    # Enregistrer la transaction avec statut "pending"
    insert_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, extra_data)

    # Envoyer un message de confirmation au client
    confirmation_message = f"Vous demandez une transaction de {montant} FC vers {recipient['nom']}. " \
                           f"Confirmez-vous ? Votre code de session est: {code_session}"
    return jsonify({'message': confirmation_message}), 200

# --- Endpoint de confirmation de transaction ---
@app.route('/confirm_transaction', methods=['POST'])
def api_confirm_transaction():
    data = request.get_json()
    code_session = data.get('code_session')
    if not code_session:
        return jsonify({'error': 'Le code de session est requis'}), 400

    result = complete_transaction(code_session)
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result), 200

if __name__ == '__main__':
    app.run(debug=True)
