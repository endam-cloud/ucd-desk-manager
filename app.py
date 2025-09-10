from flask import Flask, request, render_template, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3
from datetime import datetime
import bcrypt
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '9d7f4a2b8c3e6d1f9e8a7b6c5d4f3e2a1b9c8d7e')
DATABASE = os.environ.get('DATABASE_PATH', 'desk_data.db')

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT username FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if user:
            return User(username)
        return None

def init_db():
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            # Create desks table
            c.execute('''CREATE TABLE IF NOT EXISTS desks (
                desk_id INTEGER PRIMARY KEY,
                occupant TEXT,
                arrival TEXT,
                leaving TEXT,
                location TEXT,
                supervisor TEXT,
                status TEXT
            )''')
            # Initialize 40 desks if not already present
            for i in range(1, 41):
                c.execute('INSERT OR IGNORE INTO desks (desk_id, occupant, arrival, leaving, location, supervisor, status) VALUES (?, NULL, NULL, NULL, ?, NULL, NULL)', (i, 'Unassigned'))
            # Create users table
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )''')
            # Add default admin user if not exists
            hashed_password = bcrypt.hashpw('ucd2025'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            c.execute('INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)', ('admin', hashed_password))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database initialization error: {e}")

# Initialize database at startup
init_db()

def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        raise

@app.route('/')
def index():
    return render_template('index.html', authenticated=current_user.is_authenticated)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT password FROM users WHERE username = ?', (username,))
                user = c.fetchone()
                if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                    user_obj = User(username)
                    login_user(user_obj)
                    flash('Logged in successfully.', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Invalid username or password.', 'error')
        except sqlite3.Error as e:
            flash(f'Database error during login: {e}', 'error')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/add_occupant', methods=['POST'])
@login_required
def add_occupant():
    try:
        desk_id = int(request.form['desk_id'])
        name = request.form['name'].strip() or None
        arrival = request.form['arrival'].strip() or None
        leaving = request.form['leaving'].strip() or None
        location = request.form['location'].strip() or 'Unassigned'
        supervisor = request.form['supervisor'].strip() or None
        status = request.form['status'].strip() or None

        if not name or not arrival or not leaving:
            return jsonify({'error': 'Occupant Name, Arrival, and Leaving dates are required.'}), 400

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT desk_id, occupant FROM desks WHERE desk_id = ?', (desk_id,))
            result = c.fetchone()
            if not result:
                return jsonify({'error': f'Desk {desk_id} does not exist.'}), 400
            if result['occupant']:
                return jsonify({'error': f'Desk {desk_id} is already occupied by {result["occupant"]}.'}), 400

            # Validate dates
            try:
                arrival_date = datetime.strptime(arrival, '%Y-%m-%d')
                leaving_date = datetime.strptime(leaving, '%Y-%m-%d')
                if arrival_date > leaving_date:
                    return jsonify({'error': 'Leaving date must be after Arrival date.'}), 400
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD (e.g., 2025-09-10).'}), 400

            c.execute('''UPDATE desks SET occupant = ?, arrival = ?, leaving = ?, location = ?, supervisor = ?, status = ? WHERE desk_id = ?''',
                      (name, arrival_date.isoformat(), leaving_date.isoformat(), location, supervisor, status, desk_id))
            conn.commit()

        return jsonify({'message': f'Added {name} to desk {desk_id} from {arrival} to {leaving}, Location: {location}, Supervisor: {supervisor or "None"}, Status: {status or "None"}.'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number