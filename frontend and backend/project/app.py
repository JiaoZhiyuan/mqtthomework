from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from flask_mqtt import Mqtt
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from flask_caching import Cache
from flask_socketio import SocketIO, emit
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json
from random import randint

app = Flask(__name__)

# Flask Session Configuration
app.secret_key = 'your_secret_key'

# MQTT Configuration
app.config['MQTT_BROKER_URL'] = 'broker.hivemq.com'
app.config['MQTT_BROKER_PORT'] = 1883
app.config['MQTT_USERNAME'] = ''
app.config['MQTT_PASSWORD'] = ''
app.config['MQTT_KEEPALIVE'] = 60
app.config['MQTT_TLS_ENABLED'] = False

mqtt = Mqtt(app)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///health_data.db'
db = SQLAlchemy(app)

# JWT Configuration
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret_key'
jwt = JWTManager(app)

# Cache Configuration
app.config['CACHE_TYPE'] = 'RedisCache'
app.config['CACHE_REDIS_HOST'] = 'localhost'
app.config['CACHE_REDIS_PORT'] = 6379
app.config['CACHE_REDIS_DB'] = 0
app.config['CACHE_REDIS_URL'] = 'redis://localhost:6379/0'
cache = Cache(app)

# SocketIO Initialization
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow all origins for development

# User Model (for authentication)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Health Data Model
class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    topic = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.String(200), nullable=False)

# Function to generate random health data
def generate_random_data():
    heartbeat = randint(60, 120)
    pulse = randint(60, 120)
    blood_pressure = f"{randint(110, 130)}/{randint(70, 90)}"
    return {
        'heartbeat': heartbeat,
        'pulse': pulse,
        'blood_pressure': blood_pressure
    }

# Function to initialize dummy health data
def init_data():
    for _ in range(50):
        data = generate_random_data()
        health_data = HealthData(
            topic='health/monitor',
            payload=json.dumps(data)
        )
        db.session.add(health_data)
    db.session.commit()

# Routes

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('choose'))
    else:
        return render_template('index.html')

@app.route('/choose')
def choose():
    if 'username' in session:
        return render_template('choose.html', username=session['username'])
    else:
        return redirect(url_for('index'))

@app.route('/data')
@cache.cached(timeout=60)
@jwt_required()
def get_data():
    data = HealthData.query.order_by(HealthData.timestamp.desc()).all()
    return render_template('index.html', username=session['username'])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'username' in session:
        return redirect(url_for('choose'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return 'Username already exists!'
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        session['username'] = username
        return redirect(url_for('choose'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('choose'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['username'] = username
            return redirect(url_for('choose'))
        else:
            return 'Invalid username or password'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

# MQTT Handling

@mqtt.on_connect()
def handle_connect(client, userdata, flags, rc):
    mqtt.subscribe('health/#')

@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    data = HealthData(topic=message.topic, payload=message.payload.decode())
    db.session.add(data)
    db.session.commit()
    socketio.emit('mqtt_message', {
        'timestamp': data.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'topic': data.topic,
        'payload': data.payload
    })

# SocketIO Events

@socketio.on('connect')
def handle_connect_socketio():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect_socketio():
    print('Client disconnected')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_data()
    socketio.run(app, debug=True, port=5001, host='0.0.0.0', use_reloader=False, allow_unsafe_werkzeug=True)

