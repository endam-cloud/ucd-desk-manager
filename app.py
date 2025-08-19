from flask import Flask, request, render_template, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3
from datetime import datetime
import bcrypt
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '9d7f4a2b8c3e6d1f9e8a7b6c5d4f3e2a1b9c8d7e')  # Secure random key for production
DATABASE = 'desk_data.db'

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

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

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
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD (e.g., 2025-08-19).'}), 400

            c.execute('''UPDATE desks SET occupant = ?, arrival = ?, leaving = ?, location = ?, supervisor = ?, status = ? WHERE desk_id = ?''',
                      (name, arrival_date.isoformat(), leaving_date.isoformat(), location, supervisor, status, desk_id))
            conn.commit()

        return jsonify({'message': f'Added {name} to desk {desk_id} from {arrival} to {leaving}, Location: {location}, Supervisor: {supervisor or "None"}, Status: {status or "None"}.'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number.'}), 400

@app.route('/remove_occupant', methods=['POST'])
@login_required
def remove_occupant():
    try:
        desk_id = int(request.form['desk_id'])
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT occupant, location FROM desks WHERE desk_id = ?', (desk_id,))
            result = c.fetchone()
            if not result:
                return jsonify({'error': f'Desk {desk_id} does not exist.'}), 400
            if not result['occupant']:
                return jsonify({'error': f'Desk {desk_id} is already vacant.'}), 400

            c.execute('UPDATE desks SET occupant = NULL, arrival = NULL, leaving = NULL, supervisor = NULL, status = NULL WHERE desk_id = ?', (desk_id,))
            conn.commit()

        return jsonify({'message': f'Removed {result["occupant"]} from desk {desk_id} ({result["location"] or "Unassigned"}).'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number.'}), 400

@app.route('/set_details', methods=['POST'])
@login_required
def set_details():
    try:
        desk_id = int(request.form['desk_id'])
        location = request.form['location'].strip() or 'Unassigned'
        supervisor = request.form['supervisor'].strip() or None
        status = request.form['status'].strip() or None

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT desk_id FROM desks WHERE desk_id = ?', (desk_id,))
            if not c.fetchone():
                return jsonify({'error': f'Desk {desk_id} does not exist.'}), 400

            c.execute('UPDATE desks SET location = ?, supervisor = ?, status = ? WHERE desk_id = ?',
                      (location, supervisor, status, desk_id))
            conn.commit()

            c.execute('SELECT location, supervisor, status FROM desks WHERE desk_id = ?', (desk_id,))
            result = c.fetchone()
            return jsonify({'message': f'Updated desk {desk_id}: Location: {result["location"] or "Unassigned"}, Supervisor: {result["supervisor"] or "None"}, Status: {result["status"] or "None"}.'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number.'}), 400

@app.route('/add_desk', methods=['POST'])
@login_required
def add_desk():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Find the next available desk_id
            c.execute('SELECT MAX(desk_id) FROM desks')
            max_id = c.fetchone()[0]
            new_desk_id = (max_id or 0) + 1
            # Insert new desk
            c.execute('INSERT INTO desks (desk_id, occupant, arrival, leaving, location, supervisor, status) VALUES (?, NULL, NULL, NULL, ?, NULL, NULL)',
                      (new_desk_id, 'Unassigned'))
            conn.commit()
        return jsonify({'message': f'Added new desk {new_desk_id}.'})
    except Exception as e:
        return jsonify({'error': f'Error adding desk: {str(e)}'}), 500

@app.route('/list_desks')
def list_desks():
    sort_by = request.args.get('sort', 'desk_id')
    order = request.args.get('order', 'asc')
    
    # Validate sort_by to prevent SQL injection
    valid_columns = ['desk_id', 'occupant', 'arrival', 'leaving', 'location', 'supervisor', 'status']
    if sort_by not in valid_columns:
        sort_by = 'desk_id'
    
    # Validate order
    if order not in ['asc', 'desc']:
        order = 'asc'
    
    # Handle nulls in sorting
    sort_column = f'COALESCE({sort_by}, "")' if sort_by in ['occupant', 'location', 'supervisor', 'status'] else sort_by
    query = f'SELECT * FROM desks ORDER BY {sort_column} {order.upper()}, desk_id ASC'
    
    now = datetime.now().date()
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(query)
        desks = c.fetchall()
        desk_list = []
        for desk in desks:
            occupant = desk['occupant'] or 'Vacant'
            arrival = datetime.fromisoformat(desk['arrival']).strftime('%Y-%m-%d') if desk['arrival'] else '-'
            leaving = datetime.fromisoformat(desk['leaving']).strftime('%Y-%m-%d') if desk['leaving'] else '-'
            location = desk['location'] or 'Unassigned'
            supervisor = desk['supervisor'] or '-'
            status = desk['status'] or '-'
            desk_status = 'Vacant'
            if desk['occupant']:
                leaving_date = datetime.fromisoformat(desk['leaving']).date()
                desk_status = 'Occupied' if now < leaving_date else 'Overdue'
            desk_list.append({
                'desk_id': desk['desk_id'],
                'occupant': occupant,
                'arrival': arrival,
                'leaving': leaving,
                'location': location,
                'supervisor': supervisor,
                'status': status,
                'desk_status': desk_status
            })
        return jsonify(desk_list)

@app.route('/find_vacant_desks')
def find_vacant_desks():
    now = datetime.now().date()
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT desk_id, location FROM desks WHERE occupant IS NULL OR datetime(leaving) <= ?', (now.isoformat(),))
        vacant = c.fetchall()
        if vacant:
            message = [{'desk_id': desk['desk_id'], 'location': desk['location'] or 'Unassigned'} for desk in vacant]
        else:
            message = []
        return jsonify({'vacant': message})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)