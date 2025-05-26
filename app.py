import os
import uuid
import json
import sqlite3
import math
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from pydantic import BaseModel, validator
from typing import Union, Tuple, List
import re
import random
import string
import psycopg2
from psycopg2.extras import RealDictCursor


# Configuration du logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

# Configuration CORS : autorise toutes les origines (à restreindre en production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

#####################################
# Fonctions de génération
#####################################
def generate_session_code():
    # Renvoie les 8 premiers caractères d'un UUID généré aléatoirement
    return str(uuid.uuid4())[:8]

def generate_token():
    # Renvoie un UUID complet en chaîne de caractères
    return str(uuid.uuid4())

#####################################
# Fonctions de validation
#####################################
def validate_password(pass_word: str):
    # Minimum 6 caractères
    if len(pass_word) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")
    # Refuser certaines suites ou répétitions triviales
    if pass_word in ["123456", "000000", "111111"]:
        raise HTTPException(status_code=400, detail="Mot de passe trop simple")
    # Vous pouvez ajouter d'autres vérifications (majuscules, chiffres, symboles…)
    return True

def validate_phone(numero: str):
    # Vérifie que le numéro comporte exactement 10 chiffres
    if not re.fullmatch(r"\d{10}", numero):
        raise HTTPException(status_code=400, detail="Le numéro doit comporter exactement 10 chiffres")
    return True

#####################################
# Base de données SQLite et initialisation
#####################################

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host="dpg-d0nitoumcj7s73e2giag-a.oregon-postgres.render.com",
            database="kelasi_db",
            user="kelasi_db_user",
            password="gTBHYLXoOf5F5iCQvIzAmL1CCJYMpHCd",
            port=5432,
            cursor_factory=RealDictCursor  # Permet de retourner les résultats comme un dictionnaire
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Erreur PostgreSQL: {e}")
        raise HTTPException(status_code=500, detail="Connexion à la base de données échouée")

def get_company_account():
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM company_account WHERE id = 1")
        company = cursor.fetchone()
    return company

def init_db():
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        # Table des utilisateurs
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            numero TEXT UNIQUE NOT NULL,
            pass_word TEXT NOT NULL,
            solde REAL NOT NULL,
            type_compte TEXT NOT NULL DEFAULT 'standard',
            codeCompte TEXT
          )
        ''')
        # Table des transactions
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS les_transactions (
            id SERIAL PRIMARY KEY,
            numero_envoyeur TEXT NOT NULL,
            numero_destinataire TEXT NOT NULL,
            montant REAL NOT NULL,
            type_trans TEXT NOT NULL,
            code_session TEXT UNIQUE NOT NULL,
            etat TEXT NOT NULL,
            transaction_hash TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
        ''')
        # Table des inscriptions en attente
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS pending_registrations (
             id SERIAL PRIMARY KEY,
             code_session TEXT UNIQUE NOT NULL,
             nom TEXT NOT NULL,
             numero TEXT NOT NULL,
             pass_word TEXT NOT NULL,
             type_compte TEXT NOT NULL DEFAULT 'standard',
             solde REAL NOT NULL,
             code_entite TEXT,
             codeCompte TEXT,
             timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          )
        ''')
        # Table du compte d'entreprise
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS company_account (
            id SERIAL PRIMARY KEY,
            solde REAL NOT NULL,
            pass_word TEXT NOT NULL
          )
        ''')
        # Table premium_services
        cursor.execute('''
          CREATE TABLE IF NOT EXISTS premium_services (
            id SERIAL PRIMARY KEY,
            client TEXT NOT NULL, 
            produit TEXT NOT NULL, 
            percepteur TEXT NOT NULL,
            transaction_hash TEXT NOT NULL
          )
        ''')

        # Insertion du compte d'entreprise s'il n'existe pas
        cursor.execute("SELECT COUNT(*) as count FROM company_account")
        row = cursor.fetchone()
        if row["count"] == 0:
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
            cursor.execute("INSERT INTO company_account (solde, pass_word) VALUES (%s, %s)", 
                           (company_solde, company_password))
        conn.commit()
    conn.close()


#####################################
# Fonctions utilitaires SQL
#####################################
def insert_user(nom, numero, pass_word, type_compte="standard", solde=0.0, codeCompte=None):
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (nom, numero, pass_word, solde, type_compte, codeCompte)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (nom, numero, pass_word, solde, type_compte, codeCompte))
            logger.info("Utilisateur enregistré avec succès !")
            return True
    except psycopg2.IntegrityError:
        logger.error("Erreur : Le numéro est déjà utilisé.")
        return False
    except psycopg2.Error as e:
        logger.error(f"Erreur SQLite : {e}")
        return False
    finally:
        conn.close()

def get_user_by_number(codeCompte):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE numero = %s", (codeCompte,))
        user = cursor.fetchone()
    conn.close()
    
    return user

def update_user_balance(numero, new_balance):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET solde = %s WHERE numero = %s", (new_balance, numero))
    conn.close()

def update_user_code(numero, codeCompte):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET codeCompte = %s WHERE numero = %s", (codeCompte, numero))
    conn.close()

def update_company_account(amount):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE company_account SET solde = solde + %s WHERE id = 1", (amount,))
    conn.close()

def insert_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
          INSERT INTO les_transactions (numero_envoyeur, numero_destinataire, montant, type_trans, code_session, etat)
          VALUES (%s, %s, %s, %s, %s, %s)
        """, (numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, 'pending'))
    conn.close()

def validate_transaction(code_session):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM les_transactions WHERE code_session = %s AND etat = 'pending'", (code_session,))
        transaction = cursor.fetchone()
        if transaction:
            if is_session_expired(transaction["timestamp"]):
                cursor.execute("UPDATE les_transactions SET etat = 'expired' WHERE code_session = %s", (code_session,))
                conn.commit()
                conn.close()
                return None
            cursor.execute("UPDATE les_transactions SET etat = 'completed' WHERE code_session = %s", (code_session,))
            conn.commit()
    conn.close()
    return transaction

def insert_pending_registration(code_session, nom, numero, pass_word, type_compte, solde, code_entite, codeCompte):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pending_registrations (code_session, nom, numero, pass_word, type_compte, solde, code_entite, codeCompte) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                       (code_session, nom, numero, pass_word, type_compte, solde, code_entite, codeCompte))
    conn.close()

def get_pending_registration(code_session):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_registrations WHERE code_session = %s", (code_session,))
        pending = cursor.fetchone()
    conn.close()
    return pending

def delete_pending_registration(code_session):
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_registrations WHERE code_session = %s", (code_session,))
    conn.commit()
    conn.close()

def is_session_expired(timestamp):
    try:
        # Pas besoin de parser, on suppose que c'est déjà un datetime
        if not isinstance(timestamp, datetime):
            timestamp = datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M:%S.%f")
        return datetime.now() - timestamp > timedelta(minutes=15)
    except Exception as e:
        logger.error(f"Erreur de conversion du timestamp '{timestamp}': {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la conversion du timestamp")


def calculate_fees(montant, transaction_type):
    # Pour les les_transactions 'envoi' et 'depot', aucun frais n'est appliqué
    if transaction_type in ['envoi', 'depot']:
        return 0
    fee = 0
    if montant <= 20000:
        fee = montant * 0.05
    elif montant <= 100000:
        # Taux linéaire décroissant de 5% à 3.5%
        rate = 0.05 - (montant - 20000) * ((0.05 - 0.035) / (100000 - 20000))
        fee = montant * rate
    elif montant <= 200000:
        # Pour ce palier, taux fixe de 3%
        fee = montant * 0.03
    elif montant <= 1000000:
        # Taux linéaire décroissant de 3% à 1.5% pour les montants de 200000 à 1000000
        rate = 0.03 - (montant - 200000) * ((0.03 - 0.015) / (1000000 - 200000))
        fee = montant * rate
    else:
        fee = montant * 0.01
    return fee

def process_transaction(numero_envoyeur, numero_destinataire, montant, transaction_type, code_session, code_paie=None, id_paie=None):
    sender = get_user_by_number(numero_envoyeur)
    if not sender:
        return {'detail': 'Utilisateur non trouvé'}, 400

    sender_balance = sender['solde']
    montant = float(montant)
    montant = round(montant)
    fee = calculate_fees(montant, transaction_type)
    total_debit = montant + fee

    if transaction_type == 'retrait':
        recipient = get_user_by_number(numero_destinataire)
        if sender_balance < total_debit:
            return {'detail': 'Solde insuffisant pour le retrait'}, 400
        new_sender_balance = sender_balance - total_debit
        update_user_balance(numero_envoyeur, new_sender_balance)
        update_company_account(montant + fee)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE les_transactions SET transaction_hash = %s WHERE code_session = %s", (transaction_hash, code_session))
            conn.commit()
        conn.close()
        
        return {'detail': f'Le retrait au pres de {recipient["nom"]} effectue avec succes\nVotre solde actuel est '+ new_sender_balance}, 200

    elif transaction_type in ['envoi', 'paie']:
        if sender_balance < montant:
            return {'detail': 'Solde insuffisant pour l\'envoi'}, 400
        new_sender_balance = sender_balance - montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            new_recipient_balance = recipient['solde'] + montant
            update_user_balance(numero_destinataire, new_recipient_balance)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE les_transactions SET transaction_hash = %s WHERE code_session = %s", (transaction_hash, code_session))
            conn.commit()
        conn.close()
        
        return {'detail': f'Trasaction a {recipient["nom"]} effectue avec succes\nVotre solde actuel est '+ new_sender_balance}, 200

    elif transaction_type in ['liquider', 'facturer']:
        parts = numero_destinataire.split(';')
        if len(parts) < 4:
            return {'detail': 'Format invalide pour liquider/payer'}, 400

        destinataire_phone = parts[0].strip()
        recipient = get_user_by_number(destinataire_phone)

        if not recipient:
            return {'detail': 'Destinataire non trouvé'}, 400

        client = parts[1].strip()
        produit = parts[2].strip()
        percepteur = parts[3].strip()

        new_sender_balance = sender_balance - total_debit
        update_user_balance(numero_envoyeur, new_sender_balance)

        bonus = fee * 0.2
        new_recipient_balance = recipient['solde'] + bonus
        update_user_balance(destinataire_phone, new_recipient_balance)

        update_company_account(fee - bonus)

        transaction_hash = str(uuid.uuid4())

        # Mise à jour de la transaction
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE les_transactions SET transaction_hash = %s WHERE code_session = %s",
                (transaction_hash, code_session)
            )
            conn.commit()
        conn.close()

        # Insertion dans premium_services
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO premium_services (client, produit, percepteur, transaction_hash)
                VALUES (%s, %s, %s, %s)
            """, (client, produit, percepteur, transaction_hash))
            conn.commit()
        conn.close()

        return {
            'detail': f"Paiement de facture à {recipient['nom']} effectué avec succès\nVotre solde actuel est {new_sender_balance:.2f}"
        }, 200

    elif transaction_type == 'depot':
        if sender_balance < montant:
            return {'detail': 'Solde insuffisant pour le dépôt'}, 400
        new_sender_balance = sender_balance - montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        recipient = get_user_by_number(numero_destinataire)
        if recipient:
            new_recipient_balance = recipient['solde'] + montant
            update_user_balance(numero_destinataire, new_recipient_balance)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE les_transactions SET transaction_hash = %s WHERE code_session = %s", (transaction_hash, code_session))
            conn.commit()
        conn.close()
        
        return {'detail': f'Le depot a {recipient["nom"]} a ete effectue avec succes\nVotre solde actuel est '+ new_sender_balance}, 200

    elif transaction_type == 'depot_pro':
        if sender['type_compte'] not in ['agent', 'premium']:
            return {'detail': 'Le compte de l\'envoyeur n\'est pas un agent valide pour depot_pro'}, 400
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT solde FROM company_account WHERE id = 1")
            company = cursor.fetchone()
        conn.close()
        if not company or company["solde"] < montant:
            return {'detail': 'Fonds insuffisants dans le compte d\'entreprise pour le dépôt pro'}, 400
        update_company_account(-montant)
        new_sender_balance = sender_balance + montant
        update_user_balance(numero_envoyeur, new_sender_balance)
        transaction_hash = str(uuid.uuid4())
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE les_transactions SET transaction_hash = %s WHERE code_session = %s", (transaction_hash, code_session))
            conn.commit()
        conn.close()
        
        return {'detail': f'Envoi d\'agent a : {recipient["nom"]} effectue avec succes\nVotre solde actuel est '+ new_sender_balance}, 200

    else:
        return {'detail': 'Type de transaction inconnu'}, 400

#####################################
# Endpoints FastAPI
#####################################

@app.get("/test")
def test_endpoint():
    return {"message": "Merci d'utiliser Mopatas"}

#####################################
# Endpoints
#####################################

@app.post("/inscription")
async def inscription_endpoint(data: dict):
    try:
        
        logger.info(f"Requête inscription reçue: {data}")
        
        # Vérifier les champs obligatoires
        nom = data.get('nom')
        pass_word = data.get('pass_word')
        numero = data.get('numero')
        type_compte = data.get('type_compte', 'standard')
        codeCompte = data.get('codeCompte')  # Obligatoire pour non-agent
        code_entite = data.get('code_entite') if type_compte == 'premium' else None

        if not nom or not pass_word or not numero:
            raise HTTPException(status_code=400, detail="Les champs nom, pass_word et numero sont obligatoires")
        
        # Validation du mot de passe
        validate_password(pass_word)
        # Validation du numéro
        validate_phone(numero)
        
        # Vérifier si le numéro existe déjà dans pending_registrations ou dans users
        if get_user_by_number(numero):
            raise HTTPException(status_code=400, detail="Numéro déjà inscrit")
        
        # Déterminer le montant :
        # Si le compte est agent, on prend le montant envoyé, sinon, montant = 0.0
        if type_compte == 'agent':
            try:
                montant = float(data.get("montant", 0.0))
            except:
                raise HTTPException(status_code=400, detail="Montant invalide")
        else:
            montant = 0.0
        
        # Pour les comptes non-agent, codeCompte est obligatoire
        if type_compte != 'agent' and not codeCompte:
            raise HTTPException(status_code=400, detail="codeCompte requis pour ce type de compte")
        
        code_session = generate_session_code()
        insert_pending_registration(code_session, nom, numero, pass_word, type_compte, montant, code_entite, codeCompte)
        confirmation_message = f"Inscription demandée pour {nom}. Veuillez confirmer avec code_session: {code_session}"
        return {"message": confirmation_message, "code_session": code_session}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TransactionRequest(BaseModel):
    num_destinataire: str
    num_envoyeur: str
    montant: Union[float, int, str]
    pass_word: str
    transaction_type: str
    codeCompte: str

    @validator("montant", pre=True)
    def parse_montant(cls, v):
        try:
            return float(v)
        except ValueError:
            raise ValueError("Le champ 'montant' doit être un nombre valide.")

class ConfirmTransactionRequest(BaseModel):
    code_session: str
    confirmation: Union[bool, str]

    @validator("confirmation", pre=True)
    def parse_confirmation(cls, v):
        if isinstance(v, str):
            return v.lower() == "yes"
        return bool(v)

# 2. Confirm_inscription : Confirmation et insertion dans la table users

class ConfirmRequest(BaseModel):
    code_session: str
    codeCompte: str
    confirmation: Union[bool, str]

    @validator("confirmation", pre=True)
    def parse_confirmation(cls, v):
        if isinstance(v, str):
            return v.lower() == "yes"
        return v

##################################
#   Confirmation d'inscription   #
##################################
@app.post("/confirm_inscription")
async def confirm_inscription_endpoint(data: ConfirmRequest):
    try:
        logger.info(f"Requête inscription reçue: {data.dict()}")
        code_session = data.code_session
        confirmation = data.confirmation
        codeCompte   = data.codeCompte

        if not confirmation:
            raise HTTPException(status_code=400, detail="La confirmation doit être vraie")
        if not code_session:
            raise HTTPException(status_code=400, detail="code_session requis pour confirmation")
        
        pending = get_pending_registration(code_session)
        if not pending:
            raise HTTPException(status_code=400, detail="Code de session invalide ou déjà confirmé")
        if is_session_expired(pending["timestamp"]):
            delete_pending_registration(code_session)
            raise HTTPException(status_code=400, detail="Code de session expiré")
        
        # Pour un agent, codeCompte doit être None, sinon on le récupère depuis pending.
        if pending["type_compte"] == "agent":
            codeCompte = None
        else:
            codeCompte = data.codeCompte or pending["codeCompte"]

        # Insertion dans la table users (on suppose que insert_user gère aussi les erreurs)
        insert_user(
            pending["nom"],
            pending["numero"],
            pending["pass_word"],
            pending["type_compte"],
            pending["solde"],
            codeCompte
        )
        delete_pending_registration(code_session)
        
        logger.info(f"Inscription confirmée pour {pending['numero']}")
        return {
            "detail": "Inscription confirmée",
            "numero": pending["numero"],
            "type_compte": pending["type_compte"],
            "codeCompte": codeCompte
        }
    except HTTPException as e:
        logger.error(f"HTTPException: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Erreur lors de la confirmation de l'inscription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))




# 3. Recup_inscription : Récupérer un utilisateur et mettre à jour son codeCompte
@app.post("/recup_inscription")
async def recup_inscription_endpoint(data: Request):
   
    numero = data.get('numero')
    pass_word = data.get('pass_word')
    codeCompte = data.get('codeCompte')
    if not numero or not pass_word or not codeCompte:
        raise HTTPException(status_code=400, detail="numero, pass_word et codeCompte sont requis")
    user = get_user_by_number(numero)
    if not user:
        raise HTTPException(status_code=400, detail="Utilisateur non trouvé")
    if user['pass_word'] != pass_word:
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")
    # Mettre à jour le codeCompte de l'utilisateur
    update_user_code(numero, codeCompte)
    return {
        "message": "Compte mis à jour avec succès",
        "numero": numero,
        "nom":user['pass_word'],
        "solde":user['solde'],
        "codeCompte": codeCompte
    }

class MakeAgentRequest(BaseModel):
    numero: str
    montant: float
    type_compte: str = "agent"
    company_pass: str

class ConfirmRequestAgent(BaseModel):
    code_session: str
    confirmation: bool

class BalanceRequest(BaseModel):
    numero: str
    password: str = None
    codeCompte: str = None
    company_pass: str = None  # Ajout de ce champ


#########################################
# Endpoint: Création d'un agent (/makeagent)
#########################################
@app.post("/makeagent")
async def make_agent_endpoint(data: MakeAgentRequest):
    user = get_user_by_number(data.numero)
    if not user:
        raise HTTPException(status_code=400, detail="Numéro introuvable")
    
    company = get_company_account()
    if not company or data.company_pass != company["pass_word"]:
        raise HTTPException(status_code=400, detail="Mot de passe admin incorrect")
    
    nom, numero, pass_word = user["nom"], user["numero"], user["pass_word"]
    new_balance = user["solde"] + data.montant

    code_session = generate_session_code()
    insert_pending_registration(code_session, nom, numero, pass_word, data.type_compte, new_balance, None, user["codeCompte"])
    
    return {"message": f"Voulez vous faire de {nom} un agent sur Mopatas %s. Confirmez avec code_session: {code_session}", "code_session": code_session}

#########################################
# Endpoint: Confirmation d'inscription (/confirm_inscription)
#########################################
@app.post("/confirm_agent")
async def confirm_inscription_endpoint(data: ConfirmRequestAgent):
    print(f"{data}")
    pending = get_pending_registration(data.code_session)
    if not pending or is_session_expired(pending["timestamp"]):
        delete_pending_registration(data.code_session)
        raise HTTPException(status_code=400, detail="Code session invalide ou expiré")

    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET type_compte = %s, solde = %s, codeCompte = %s WHERE numero = %s",
                       (pending["type_compte"], pending["solde"], pending["codeCompte"], pending["numero"]))
    conn.close()

    delete_pending_registration(data.code_session)
    return {"detail": f"Inscription confirmée pour {pending['nom']}. Compte mis à jour."}

#########################################
# Endpoint: Liste des utilisateurs (/users)
#########################################




@app.post("/users")
async def list_users(data: dict):
    print(f"{data}")
    # Vérifier si le mot de passe est correct
    company = get_company_account()

    if not company or company["company_pass"] != data.get("company_pass"):
        raise HTTPException(status_code=403, detail="Accès refusé, mot de passe incorrect.")

    # Si l'accès est autorisé, récupérer la liste des utilisateurs
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nom, numero, solde, type_compte FROM users")
        users = cursor.fetchall()
    if users :
        # Convertir les résultats en liste de dictionnaires
        users_list = [dict(user) for user in users]
        return {"total_users": len(users_list), "users": users_list}
    else :
        raise HTTPException(status_code=403, detail="Aucun utilisateur disponible !")


#########################################
# Endpoint: Récupérer le solde d'un utilisateur (/balance)
#########################################
@app.post("/balance")
async def get_balance_endpoint(data: BalanceRequest):
    """
    Vérifie si `company_pass` est correct. Si oui, retourne le solde sans vérifier `password` et `codeCompte`.
    Sinon, vérifie normalement les identifiants utilisateur.
    """
    company = get_company_account()
    
    # Vérification du mot de passe admin
    if data.company_pass and company and data.company_pass == company["pass_word"]:
        user = get_user_by_number(data.numero)
        if not user:
            raise HTTPException(status_code=400, detail="Utilisateur introuvable")
        
        return {"solde": user["solde"]}  # Retourne directement le solde
    
    # Si `company_pass` est absent ou incorrect, vérification normale
    user = get_user_by_number(data.numero)
    if not user or data.password != user["pass_word"] or data.codeCompte != user["codeCompte"]:
        raise HTTPException(status_code=400, detail="Identifiants incorrects")
    
    return {"solde": user["solde"], "message": f"Votre solde est de {user['solde']} "}

@app.post("/balance_pro")
async def balance_pro_endpoint(data: dict):
    user = get_user_by_number(data.get('numero'))
    print(f"{data}")
    if user is None or data.get('pass_word') != user["pass_word"]:
        raise HTTPException(
            status_code=400,
            detail="Utilisateur non trouvé ou mot de passe incorrect"
        )
    if user["codeCompte"] is not None and data.get('codeCompte') != user["codeCompte"]:
        raise HTTPException(status_code=400, detail="codeCompte invalide")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
           SELECT 
            p.id_paiement AS paiement_id, 
            u.nom AS nom_payeur, 
            t.montant AS montant_transfere, 
            t.transaction_hash,
            p.client,
            p.percepteur,
            p.produit
        FROM 
            premium_services AS p
        INNER JOIN 
            users AS u ON u.numero = p.id_payeur
        INNER JOIN 
            les_transactions AS t ON t.id = p.id_paiement
        WHERE 
            p.id_payeur = %s
            AND t.etat = 'completed'
            """, (user['numero'],))

    
    premium_services = cursor.fetchall()
    conn.close()
    
    premium_list = [
        {
            "code_transaction": row["transaction_hash"],
            "client": row["client"],
            "percepteur": row["percepteur"],
            "produit": row["produit"],
            "montant": row["montant_transfere"]
        }
        for row in premium_services
    ]

    
    return {
        "solde": user["solde"],
        "message": f"Bonjour {user['nom']}, votre solde est de {user['solde']}!",
        "premium_services": premium_list
    }


#####################################
# Endpoint de création de transaction
#####################################

#####################################
# Endpoint /transaction
#####################################
@app.post("/transaction")
async def create_transaction(data: dict):
    # Vérification des champs attendus
    required_fields = ['num_destinataire', 'montant', 'pass_word', 'transaction_type', 'codeCompte', 'num_envoyeur']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Le champ {field} est requis")
    
    num_envoyeur = data['num_envoyeur']
    pass_word = data['pass_word']
    
    # Vérifier que l'envoyeur existe
    sender = get_user_by_number(num_envoyeur)
    if not sender:
        raise HTTPException(status_code=400, detail="Envoyeur non trouvé")
    
    # Vérifier que le mot de passe correspond
    if sender['pass_word'] != pass_word:
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")
    # Vous pouvez aussi utiliser validate_password(pass_word) si besoin

    # Vérifier le destinataire : si le numéro contient ';' on découpe et on prend la première partie
    num_destinataire = data['num_destinataire']
    if ";" in num_destinataire:
        numero_dest = num_destinataire.split(';')[0].strip()
    else:
        numero_dest = num_destinataire.strip()

    recipient = get_user_by_number(numero_dest)

    if not recipient:
        raise HTTPException(status_code=400, detail="Destinataire non trouvé")
    
    # Vérifier la solvabilité de l'envoyeur (pour un envoi par exemple)
    montant = float(data['montant'])
    if data['transaction_type'] == 'envoi' and sender['solde'] < montant:
        raise HTTPException(status_code=400, detail="Solde insuffisant pour l'envoi")

    # Générer le code de session pour la transaction
    code_session = generate_session_code()

    # Insérer la transaction dans la base avec l'état "pending"
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO les_transactions 
            (numero_envoyeur, numero_destinataire, montant, type_trans, code_session, etat) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (num_envoyeur, num_destinataire, montant, data['transaction_type'], code_session, "pending"))
        conn.commit()
    conn.close()

    confirmation_message = "Transaction en attente de confirmation"
    return {"message": confirmation_message, "code_session": code_session}

#####################################
# Endpoint /confirm_transaction
#####################################
@app.post("/confirm_transaction")
async def confirm_transaction(confirmData: dict):
    # Vérification des champs
    required_fields = ['code_session', 'confirmation']
    for field in required_fields:
        if field not in confirmData:
            raise HTTPException(status_code=400, detail=f"Le champ {field} est requis")
    
    if confirmData['confirmation'] != "yes":
        raise HTTPException(status_code=400, detail="Confirmation invalide")
    
    code_session = confirmData['code_session']
    # Récupérer la transaction en attente par code_session
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM les_transactions WHERE code_session = %s", (code_session,))
        transaction = cursor.fetchone()
    conn.close()
    
    if not transaction:
        raise HTTPException(status_code=400, detail="Code session invalide")
    if transaction['etat'] != "pending":
        raise HTTPException(status_code=400, detail="Transaction déjà confirmée ou annulée")
    
    # Traiter la transaction via la fonction process_transaction
    result, status_code = process_transaction(
        transaction['numero_envoyeur'],
        transaction['numero_destinataire'],
        transaction['montant'],
        transaction['type_trans'],
        code_session
    )
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=result.get('detail'))
    
    # Mettre à jour l'état de la transaction à "completed"
    conn = get_db_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE les_transactions SET etat = %s WHERE code_session = %s", ("completed", code_session))
        conn.commit()
    conn.close()
    
    return {"detail": result.get('detail'), "message": "Transaction confirmee", "transaction_hash": result.get('transaction_hash')}




if __name__ == "__main__":
    init_db()  # Initialise la base de données
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
