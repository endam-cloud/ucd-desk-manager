from flask import Flask, request, render_template, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from psycopg_pool import ConnectionPool
from datetime import datetime
import bcrypt
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '9d7f4a2b8c3e6d1f9e8a7b6c5d4f3e2a1b9c8d7e')

# PostgreSQL connection pool
db_pool = None
def init_db_pool():
    global db_pool
    try:
        db_pool = ConnectionPool(
            conninfo=f"dbname={os.environ.get('PG_DBNAME')} user={os.environ.get('PG_USER')} password={os.environ.get('PG_PASSWORD')} host={os.environ.get('PG_HOST')} port={os.environ.get('PG_PORT')}",
            min_size=1,
            max_size=20
        )
        print("Database pool initialized successfully")
    except Exception as e:
        print(f"Database pool initialization error: {e}")

# Initialize database schema
def init_db():
    try:
        conn = db_pool.connection()
        with conn.cursor() as c:
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
            # Initialize 40 desks
            for i in range(1, 41):
                c.execute('INSERT INTO desks (desk_id, occupant, arrival, leaving, location, supervisor, status) VALUES (%s, NULL, NULL, NULL, %s, NULL, NULL) ON CONFLICT DO NOTHING', (i, 'Unassigned'))
            # Create users table
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )''')
            # Add default admin user
                hashed_password = bcrypt.hashpw('ucd2025'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            c.execute('INSERT INTO users (username, password) VALUES (%s, %s) ON CONFLICT DO NOTHING', ('admin', hashed_password))
            conn.commit()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")

# Initialize database at startup
init_db_pool()
init_db()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    try:
        conn = db_pool.connection()
        with conn.cursor() as c:
            c.execute('SELECT username FROM users WHERE username = %s', (username,))
            user = c.fetchone()
            if user:
                return User(username)
            return None
    except Exception as e:
        print(f"User load error: {e}")
        return None

def get_db_connection():
    try:
        conn = db_pool.connection()
        return conn
    except Exception as e:
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
            conn = get_db_connection()
            with conn.cursor() as c:
                c.execute('SELECT password FROM users WHERE username = %s', (username,))
                user = c.fetchone()
            if user and bcrypt.checkpw(password.encode('utf-8'), user[0].encode('utf-8')):
                user_obj = User(username)
                login_user(user_obj)
                flash('Logged in successfully.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password.', 'error')
        except Exception as e:
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

        conn = get_db_connection()
        with conn.cursor() as c:
            c.execute('SELECT desk_id, occupant FROM desks WHERE desk_id = %s', (desk_id,))
            result = c.fetchone()
            if not result:
                conn.close()
                return jsonify({'error': f'Desk {desk_id} does not exist.'}), 400
            if result[1]:
                conn.close()
                return jsonify({'error': f'Desk {desk_id} is already occupied by {result[1]}.'}), 400

            # Validate dates
            try:
                arrival_date = datetime.strptime(arrival, '%Y-%m-%d')
                leaving_date = datetime.strptime(leaving, '%Y-%m-%d')
                if arrival_date > leaving_date:
                    conn.close()
                    return jsonify({'error': 'Leaving date must be after Arrival date.'}), 400
            except ValueError:
                conn.close()
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD (e.g., 2025-09-10).'}), 400

            c.execute('''UPDATE desks SET occupant = %s, arrival = %s, leaving = %s, location = %s, supervisor = %s, status = %s WHERE desk_id = %s''',
                      (name, arrival_date.isoformat(), leaving_date.isoformat(), location, supervisor, status, desk_id))
            conn.commit()
        conn.close()
        return jsonify({'message': f'Added {name} to desk {desk_id} from {arrival} to {leaving}, Location: {location}, Supervisor: {supervisor or "None"}, Status: {status or "None"}.'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number.'}), 400
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500

@app.route('/remove_occupant', methods=['POST'])
@login_required
def remove_occupant():
    try:
        desk_id = int(request.form['desk_id'])
        conn = get_db_connection()
        with conn.cursor() as c:
            c.execute('SELECT occupant, location FROM desks WHERE desk_id = %s', (desk_id,))
            result = c.fetchone()
            if not result:
                conn.close()
                return jsonify({'error': f'Desk {desk_id} does not exist.'}), 400
            if not result[0]:
                conn.close()
                return jsonify({'error': f'Desk {desk_id} is already vacant.'}), 400

            c.execute('UPDATE desks SET occupant = NULL, arrival = NULL, leaving = NULL, supervisor = NULL, status = NULL WHERE desk_id = %s', (desk_id,))
            conn.commit()
        conn.close()
        return jsonify({'message': f'Removed {result[0]} from desk {desk_id} ({result[1] or "Unassigned"}).'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number.'}), 400
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500

@app.route('/set_details', methods=['POST'])
@login_required
def set_details():
    try:
        desk_id = int(request.form['desk_id'])
        location = request.form['location'].strip() or 'Unassigned'
        supervisor = request.form['supervisor'].strip() or None
        status = request.form['status'].strip() or None

        conn = get_db_connection()
        with conn.cursor() as c:
            c.execute('SELECT desk_id FROM desks WHERE desk_id = %s', (desk_id,))
            if not c.fetchone():
                conn.close()
                return jsonify({'error': f'Desk {desk_id} does not exist.'}), 400

            c.execute('UPDATE desks SET location = %s, supervisor = %s, status = %s WHERE desk_id = %s',
                      (location, supervisor, status, desk_id))
            conn.commit()

            c.execute('SELECT location, supervisor, status FROM desks WHERE desk_id = %s', (desk_id,))
            result = c.fetchone()
        conn.close()
        return jsonify({'message': f'Updated desk {desk_id}: Location: {result[0] or "Unassigned"}, Supervisor: {result[1] or "None"}, Status: {result[2] or "None"}.'})
    except ValueError:
        return jsonify({'error': 'Invalid Desk ID. Enter a valid number.'}), 400
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500

@app.route('/add_desk', methods=['POST'])
@login_required
def add_desk():
    try:
        conn = get_db_connection()
        with conn.cursor() as c:
            # Find the next available desk_id
            c.execute('SELECT MAX(desk_id) FROM desks')
            max_id = c.fetchone()[0]
            new_desk_id = (max_id or 0) + 1
            # Insert new desk
            c.execute('INSERT INTO desks (desk_id, occupant, arrival, leaving, location, supervisor, status) VALUES (%s, NULL, NULL, NULL, %s, NULL, NULL)',
                      (new_desk_id, 'Unassigned'))
            conn.commit()
        return jsonify({'message': f'Added new desk {new_desk_id}.'})
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500

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
    sort_column = f'COALESCE({sort_by}, '')' if sort_by in ['occupant', 'location', 'supervisor', 'status'] else sort_by
    query = f'SELECT * FROM desks ORDER BY {sort_column} {order.upper()}, desk_id ASC'
    
    try:
        now = datetime.now().date()
        conn = get_db_connection()
        with conn.cursor() as c:
            c.execute(query)
            desks = c.fetchall()
        conn.close()
        desk_list = []
        for desk in desks:
            occupant = desk[1] or 'Vacant'
            arrival = datetime.fromisoformat(desk[2]).strftime('%Y-%m-%d') if desk[2] else '-'
            leaving = datetime.fromisoformat(desk[3]).strftime('%Y-%m-%d') if desk[3] else '-'
            location = desk[4] or 'Unassigned'
            supervisor = desk[5] or '-'
            status = desk[6] or '-'
            desk_status = 'Vacant'
            if desk[1]:
                leaving_date = datetime.fromisoformat(desk[3]).date()
                desk_status = 'Occupied' if now < leaving_date else 'Overdue'
            desk_list.append({
                'desk_id': desk[0],
                'occupant': occupant,
                'arrival': arrival,
                'leaving': leaving,
                'location': location,
                'supervisor': supervisor,
                'status': status,
                'desk_status': desk_status
            })
        return jsonify(desk_list)
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500

@app.route('/find_vacant_desks')
def find_vacant_desks():
    try:
        now = datetime.now().date()
        conn = get_db_connection()
        with conn.cursor() as c:
            c.execute('SELECT desk_id, location FROM desks WHERE occupant IS NULL OR leaving <= %s', (now.isoformat(),))
            vacant = c.fetchall()
        conn.close()
        if vacant:
            message = [{'desk_id': desk[0], 'location': desk[1] or 'Unassigned'} for desk in vacant]
        else:
            message = []
        return jsonify({'vacant': message})
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)