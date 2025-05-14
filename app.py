import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
from urllib.parse import quote
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'votre_cle_secrete_complexe_ici'

# Configuration GitHub
GITHUB_OWNER = "LAKRADHicham"
REPO_NAME = "Documentation"
BRANCH = "main"

# Dossiers à explorer
CATEGORIES = ['Gammes operatoires', 'Procedures maintenance', 'REX']

def get_file_url(file_path):
    """Retourne l'URL raw pour accéder au fichier"""
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{REPO_NAME}/{BRANCH}/{quote(file_path)}"

def get_directory_contents(path):
    """Récupère le contenu d'un dossier via l'API GitHub"""
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPO_NAME}/contents/{quote(path)}?ref={BRANCH}"
    headers = {}
    
    if os.getenv('GITHUB_TOKEN'):
        headers['Authorization'] = f"token {os.getenv('GITHUB_TOKEN')}"
    
    response = requests.get(api_url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    
    app.logger.error(f"Erreur {response.status_code} pour {path}: {response.text}")
    return None

def lister_fichiers_recursivement(chemin):
    """Liste récursive des fichiers PDF/DOC"""
    fichiers = []
    contents = get_directory_contents(chemin)
    
    if contents:
        for item in contents:
            if item['type'] == 'file':
                if item['name'].lower().endswith(('.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png')):
                    fichiers.append({
                        "name": item['name'],
                        "download_url": get_file_url(item['path']),
                        "path": item['path'],
                        "category": chemin.split('/')[0] if '/' in chemin else chemin
                    })
            elif item['type'] == 'dir':
                fichiers.extend(lister_fichiers_recursivement(item['path']))
    return fichiers

# Configuration Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    users = {
        "admin": {"password": generate_password_hash("admin123")},
        "technicien": {"password": generate_password_hash("tech123")}
    }
    if username not in users:
        return None
    user = User()
    user.id = username
    return user

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = {
            "admin": {"password": generate_password_hash("admin123")},
            "technicien": {"password": generate_password_hash("tech123")}
        }
        
        if username in users and check_password_hash(users[username]['password'], password):
            user = User()
            user.id = username
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Identifiant ou mot de passe incorrect', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    results = []
    message = ""
    search_term = ""
    
    if request.method == 'POST':
        search_term = request.form.get('search', '').strip()
        if not search_term:
            message = "Veuillez renseigner la barre de recherche."
        else:
            results = rechercher_documents(search_term)
            if not results:
                message = "Aucun document trouvé pour cette recherche."
    
    return render_template('index.html', 
                         results=results, 
                         message=message, 
                         search_term=search_term,
                         current_user=current_user)

def rechercher_documents(term):
    """Recherche insensible à la casse"""
    results = []
    for dossier in CATEGORIES:
        fichiers = lister_fichiers_recursivement(dossier)
        for fichier in fichiers:
            if term.lower() in fichier['name'].lower():
                results.append(fichier)
    return sorted(results, key=lambda x: x['name'])

@app.route('/view/<path:file_path>')
@login_required
def view_file(file_path):
    """Affiche le fichier directement dans le navigateur"""
    # Protection contre les attaques par traversal
    if '..' in file_path or file_path.startswith('/'):
        flash("Chemin de fichier non autorisé", 'error')
        return redirect(url_for('index'))

    content_url = get_file_url(file_path)
    filename = os.path.basename(file_path)
    
    # Détermination du type MIME
    file_ext = os.path.splitext(filename)[1].lower()
    mime_types = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png'
    }
    mimetype = mime_types.get(file_ext, 'application/octet-stream')

    try:
        # Timeout après 10 secondes
        response = requests.get(content_url, stream=True, timeout=10)
        
        if response.status_code == 200:
            return Response(
                response.iter_content(chunk_size=1024),
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'inline; filename="{filename}"',
                    'X-Content-Type-Options': 'nosniff'
                }
            )
        else:
            app.logger.error(f"Erreur {response.status_code} pour {content_url}")
            flash(f"Le fichier n'a pas pu être chargé (erreur {response.status_code})", 'error')
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erreur de connexion pour {content_url}: {str(e)}")
        flash("Erreur de connexion au serveur GitHub", 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)