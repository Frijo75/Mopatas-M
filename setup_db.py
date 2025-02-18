import mysql.connector

def create_tables():
    # Connexion au serveur MySQL
    conn = mysql.connector.connect(
        host='localhost',       # modifiez selon votre configuration
        user='root',            # modifiez selon votre configuration
        password='password'     # modifiez selon votre configuration
    )
    cursor = conn.cursor()

    # Créer la base de données 'mopatas' si elle n'existe pas déjà
    cursor.execute("CREATE DATABASE IF NOT EXISTS mopatas")
    conn.database = 'mopatas'

    # Création de la table users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nom VARCHAR(255) NOT NULL,
            numero VARCHAR(50) UNIQUE NOT NULL,
            pass_word VARCHAR(255) NOT NULL,
            solde DECIMAL(10,2) NOT NULL DEFAULT 0.0
        )
    """)

    # Création de la table transactions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero_envoyeur VARCHAR(50) NOT NULL,
            numero_destinataire VARCHAR(50) NOT NULL,
            montant DECIMAL(10,2) NOT NULL,
            type VARCHAR(50) NOT NULL,
            code_session VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL,
            extra_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Création de la table company
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS company (
            id INT AUTO_INCREMENT PRIMARY KEY,
            solde DECIMAL(10,2) NOT NULL DEFAULT 0.0
        )
    """)

    # Vérifier si la table company est vide et insérer une ligne initiale si nécessaire
    cursor.execute("SELECT COUNT(*) FROM company")
    result = cursor.fetchone()
    if result[0] == 0:
        cursor.execute("INSERT INTO company (solde) VALUES (0.0)")

    conn.commit()
    cursor.close()
    conn.close()
    print("Configuration de la base de données terminée.")

if __name__ == "__main__":
    create_tables()
