import tensorflow as tf
import pandas as pd
from flask import Flask, request, render_template, render_template_string, redirect, url_for, session, make_response
from tensorflow.keras.layers import ( # type: ignore
    Embedding, Conv1D, LSTM, Dense, Input,
    Concatenate, Dropout, BatchNormalization
)
from tensorflow.keras.models import Model # type: ignore
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
from sklearn.model_selection import train_test_split
import re
import sqlite3
import bcrypt
from pyngrok import ngrok

ngrok.set_auth_token("YOUR_AUTHTOKEN")

import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from deep_translator import GoogleTranslator
from pyngrok import ngrok
from sentence_transformers import SentenceTransformer
import torch
from transformers import BertTokenizer, BertForSequenceClassification
from sklearn.metrics.pairwise import cosine_similarity
import urllib.parse

app = Flask(__name__)  # ✅ Correct

app.secret_key = 'your_secure_secret_key_here'  # Replace in production

model = SentenceTransformer('paraphrase-xlm-r-multilingual-v1')

# Initialize databases
def init_databases():
    # User database
    conn = sqlite3.connect('project.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME,
        is_verified BOOLEAN DEFAULT FALSE,
        verification_token TEXT,
        verification_expiry DATETIME,
        password_reset_token TEXT,
        password_reset_expiry DATETIME
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Create admin user if not exists
    hashed_password = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
    cursor.execute('''
    INSERT OR IGNORE INTO users 
        (username, email, password_hash, role, is_verified)
    VALUES (?, ?, ?, ?, ?)
    ''', ('admin', 'admin@example.com', hashed_password, 'admin', True))
    
    conn.commit()
    conn.close()

    # Search history database
    conn = sqlite3.connect('your_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        query TEXT NOT NULL,
        similarity_score REAL NOT NULL,
        date DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_databases()

def initialize_database():
    conn = sqlite3.connect('your_database.db')
    cursor = conn.cursor()
    
    # Create users table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT
        )
    ''')
    
    # Create search_history with proper user_id foreign key
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            query TEXT,
            similarity_score REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Call this function once
initialize_database()

# ------------------------- Authentication Routes -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect('project.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, password_hash, is_verified 
                FROM users 
                WHERE username = ?
            ''', (username,))
            user = cursor.fetchone()

            if not user or not bcrypt.checkpw(password.encode('utf-8'), user[1]):
                return render_template_string(login_html, error="Invalid credentials")

            if not user[2]:
                return render_template_string(login_html, error="Account not verified")

            # Update last login
            cursor.execute('''
                UPDATE users 
                SET last_login = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (user[0],))
            
            conn.commit()
            
            # Set session
            session['user_id'] = user[0]
            session['username'] = username
            session['logged_in'] = True

            return redirect(url_for('home'))

        except Exception as e:
            print(f"Login error: {e}")
            return render_template_string(login_html, error="Login failed")
        finally:
            conn.close()

    return render_template_string(login_html)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            return render_template_string(register_html, error="Passwords don't match")

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        verification_token = secrets.token_urlsafe(32)

        conn = sqlite3.connect('project.db')
        cursor = conn.cursor()
        
        try:
          cursor.execute('''
                INSERT INTO users (
                    username, 
                    email, 
                    password_hash, 
                    verification_token,
                    verification_expiry
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                username,
                email,
                hashed_password,
                verification_token,
                expiry_time := datetime.now() + timedelta(days=1)  # Token valid for 1 day
            ))

            # Send verification email
          send_verification_email(email, verification_token)

          conn.commit()
            
          return render_template_string(register_html, 
                success="Registration successful! Check your email to verify.")
            
        except sqlite3.IntegrityError:
            return render_template_string(register_html, error="Username/email already exists")
        except Exception as e:
            print(f"Registration error: {e}")
            return render_template_string(register_html, error="Registration failed")
        finally:
            conn.close()

    return render_template_string(register_html)


from flask import url_for

def send_verification_email(email, token):
    verification_link = url_for('verify_email', token=token, _external=True)

    msg = EmailMessage()
    msg.set_content(f"Click the link to verify your email: {verification_link}")
    
    msg['Subject'] = 'Verify your email'
    msg['From'] = 'your_email@gmail.com'
    msg['To'] = email
    
    msg.set_content("Click the link to verify your email.")  # plain text fallback

    msg.add_alternative(f"""
    <html>
        <body>
            Click <a href="{verification_link}">verify</a> to confirm your email.
        </body>
    </html>
""", subtype='html')


    # Replace with your Gmail and the App Password
    gmail_user = 'imuday070@gmail.com'
    gmail_app_password = 'hazpckuhyhqgtcdq'

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg)
        print(f"Verification email sent to {email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


@app.route('/verify/<token>')
def verify_email(token):
    conn = sqlite3.connect('project.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE users 
            SET is_verified = TRUE 
            WHERE verification_token = ? 
            AND verification_expiry > ?
        ''', (token, datetime.now()))
        
        if cursor.rowcount == 0:
            return "Invalid or expired verification token"
            
        conn.commit()
        return "Email verified successfully. You can now log in."
    finally:
        conn.close()

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

# ------------------------- Core Application Routes -------------------------

@app.route("/")
@app.route("/home")
def home():
    return render_template_string(home_html, logged_in='user_id' in session)

# ... [Keep all your existing routes for compare, history, etc. exactly as provided] ...


# Root route

# Initialize the tokenizer and model for the transformer
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
transformer_model = BertForSequenceClassification.from_pretrained('bert-base-uncased', num_labels=2)

# Function to process the questions using the Transformer model
def process_questions(question1, question2):
    # Tokenize the questions using the BERT tokenizer
    inputs = tokenizer([question1, question2], padding=True, truncation=True, return_tensors="pt")

    # Get the model's predictions
    with torch.no_grad():
        outputs = transformer_model(**inputs)
        logits = outputs.logits

    # Convert logits to similarity score (you can adjust this as needed)
    similarity_score = torch.nn.functional.softmax(logits, dim=-1).numpy()

    return similarity_score[0][1]

# Compare route

# Telugu regex pattern
telugu_pattern = re.compile('[\u0C00-\u0C7F]+')

def maybe_translate_to_english(text):
    """
    If 'text' contains Telugu characters, translate it to English using deep_translator.
    Otherwise, return it as-is.
    """
    if not isinstance(text, str):
        text = str(text)
    if telugu_pattern.search(text):  # If Telugu text is detected
        try:
            return GoogleTranslator(source='auto', target='en').translate(text)
        except Exception as e:
            print("Translation error:", e)
            return text
    return text

def get_similarity_score(question1, question2):
    # Generate embeddings for both questions
    embeddings = model.encode([question1, question2])

    # Calculate cosine similarity between the two embeddings
    sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return round(sim, 4)

@app.route("/compare", methods=["GET", "POST"])
def compare():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        question1 = request.form.get('question1')
        question2 = request.form.get('question2')

        if not question1 or not question2:
            return "Both questions are required.", 400

        # Translate questions to English if they contain Telugu text
        question1 = maybe_translate_to_english(question1)
        question2 = maybe_translate_to_english(question2)

        # Using Sentence-BERT model to compare the questions
        similarity_score = get_similarity_score(question1, question2)
        formatted_score = f"{similarity_score:.4f}"

        search_url = None
        if similarity_score > 0.75:
            query = urllib.parse.quote(f"{question1} OR {question2}")
            search_url = f"https://www.google.com/search?q={query}"

        # Save to search history
        try:
          project_conn = sqlite3.connect('project.db')
          cursor = project_conn.cursor()
          cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
          user = cursor.fetchone()
            
          if user:
              user_id = user[0]
                
                # Correct IST time
              ist_now = datetime.now() + timedelta(hours=5, minutes=30)

                # Save to your_database.db
              yourdb_conn = sqlite3.connect('your_database.db')
              cursor = yourdb_conn.cursor()
                
              cursor.execute("""
                    INSERT INTO search_history (user_id, query, similarity_score, date) 
                    VALUES (?, ?, ?, ?)
                """, (
                    user_id,
                    f"{question1} vs {question2}",
                    float(similarity_score),
                    ist_now.strftime('%Y-%m-%d %H:%M:%S')  # Save the current IST timestamp
                ))
                
              yourdb_conn.commit()
        except Exception as e:
            print(f"Error saving to history: {e}")
        finally:
            if 'project_conn' in locals(): project_conn.close()
            if 'yourdb_conn' in locals(): yourdb_conn.close()

        return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Comparison Result</title>
  <link rel="icon" href="{{ url_for('static', filename='nobg.png') }}" type="image/png">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <style>
    body {
      background-color: #f8f9fa;
      color: #212529;
    }

    .card {
      background-color: white;
    }

    body.dark-mode {
      background-color: #121212;
      color: #f0f0f0;
    }

    body.dark-mode .card {
      background-color: #2c2c2c;
      color: white;
      border: none;
    }

    body.dark-mode .btn-outline-primary {
      color: #6e8efb;
      border-color: #6e8efb;
    }

    body.dark-mode .btn-outline-primary:hover {
      background-color: #5a7df4;
      color: white;
    }

    .dark-mode-toggle {
      position: fixed;
      top: 15px;
      right: 15px;
      cursor: pointer;
      background: #444;
      color: white;
      padding: 8px 12px;
      border-radius: 6px;
      z-index: 999;
    }

    .dark-mode-toggle:hover {
      background: #666;
    }
  </style>
</head>
<body>
  <div class="dark-mode-toggle" onclick="toggleDarkMode()">🌓</div>
  <h1 class="text-center my-4">Comparison Result</h1>
  <div class="container">
    <div class="row justify-content-center">
      <div class="col-md-8">
        <div class="card p-4 shadow-lg rounded">
          <h3 class="text-center mb-3">Results</h3>
          <div class="mb-3">
            <strong>Question 1:</strong>
            <p class="text-primary">{{ question1 }}</p>
          </div>
          <div class="mb-3">
            <strong>Question 2:</strong>
            <p class="text-primary">{{ question2 }}</p>
          </div>
          <div class="mb-3">
            <strong>Similarity Score:</strong>
            <p class="display-6 text-primary">{{ similarity_score }}</p>
          </div>
          {% if search_url %}
          <div class="mt-4 text-center">
            <a href="{{ search_url }}" target="_blank" class="btn btn-outline-primary btn-lg">Search on Google</a>
          </div>
          {% else %}
          <div class="mt-4 text-center">
            <p>No relevant search results found.</p>
          </div>
          {% endif %}
          <div class="mt-4 text-center">
            <a href="/compare" class="btn btn-primary">Compare Another</a>
            <a href="/history" class="btn btn-secondary">View History</a>
          </div>
        </div>
      </div>
    </div>
  </div>
  <script>
    function toggleDarkMode() {
      const body = document.body;
      const newTheme = body.classList.contains("dark-mode") ? "light" : "dark";
      body.classList.toggle("dark-mode");
      localStorage.setItem('mode', newTheme);
    }
    window.onload = function () {
      const mode = localStorage.getItem('mode');
      if (mode === 'dark') {
        document.body.classList.add('dark-mode');
      }
    };
  </script>
</body>
</html>
""", question1=question1, question2=question2, similarity_score=formatted_score, search_url=search_url)

    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Compare Questions</title>
  <link rel="icon" href="{{ url_for('static', filename='nobg.png') }}" type="image/png">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <style>
    body {
      background-color: #f8f9fa;
      color: #212529;
    }

    .form-container {
      background-color: #ffffff;
    }

    body.dark-mode {
      background-color: #121212;
      color: #f0f0f0;
    }

    body.dark-mode .form-container {
      background-color: #2c2c2c;
      color: white;
      border: none;
    }

    .form-label {
      font-weight: 500;
    }

    body.dark-mode .form-label {
      color: #f0f0f0;
    }

    body.dark-mode .form-control {
      background-color: #3b3b3b;
      color: white;
      border: 1px solid #555;
    }

    .dark-mode-toggle {
      position: fixed;
      top: 15px;
      right: 15px;
      cursor: pointer;
      background: #444;
      color: white;
      padding: 8px 12px;
      border-radius: 6px;
      z-index: 999;
    }

    .dark-mode-toggle:hover {
      background: #666;
    }
  </style>
</head>
<body>
  <div class="dark-mode-toggle" onclick="toggleDarkMode()">🌓</div>
  <h1 class="text-center my-4">Compare Questions</h1>
  <div class="container">
    <div class="row justify-content-center">
      <div class="col-md-6">
        <form method="POST" class="form-container border p-4 rounded shadow">
          <div class="mb-3">
            <label for="question1" class="form-label">Question 1:</label>
            <input type="text" class="form-control" id="question1" name="question1" required>
          </div>
          <div class="mb-3">
            <label for="question2" class="form-label">Question 2:</label>
            <input type="text" class="form-control" id="question2" name="question2" required>
          </div>
          <div class="d-flex justify-content-center">
            <button type="submit" class="btn btn-primary btn-lg">Compare</button>
          </div>
        </form>
      </div>
    </div>
  </div>
  <script>
    function toggleDarkMode() {
      const body = document.body;
      const newTheme = body.classList.contains("dark-mode") ? "light" : "dark";
      body.classList.toggle("dark-mode");
      localStorage.setItem('mode', newTheme);
    }
    window.onload = function () {
      const mode = localStorage.getItem('mode');
      if (mode === 'dark') {
        document.body.classList.add('dark-mode');
      }
    };
  </script>
</body>
</html>
""")

def fix_database():
    try:
        conn = sqlite3.connect('your_database.db')
        cursor = conn.cursor()
        
        # Add temporary column
        cursor.execute("ALTER TABLE search_history ADD COLUMN new_score REAL")
        
        # Copy and convert data
        cursor.execute("""
            UPDATE search_history 
            SET new_score = CAST(similarity_score AS REAL)
            WHERE typeof(similarity_score) != 'real'
        """)
        
        # Remove old column and rename
        cursor.execute("ALTER TABLE search_history DROP COLUMN similarity_score")
        cursor.execute("ALTER TABLE search_history RENAME COLUMN new_score TO similarity_score")
        
        conn.commit()
        print("Database fixed successfully")
    except Exception as e:
        print(f"Error fixing database: {e}")
    finally:
        if conn:
            conn.close()

# Call this function once
fix_database()

# ------------------------- HTML Templates -------------------------

# [Keep all your existing HTML template strings exactly as provided]
# login_html = ...
# register_html = ...
# home_html = ...
# compare_html_content = ...
# history_html = ...
home_html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Question Similarity Checker</title>
    <link rel="icon" href="{{ url_for('static', filename='nobg.png') }}" type="image/png">


    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body {
        background-color: #ffffff;
        color: #000000;
        transition: background-color 0.3s, color 0.3s;
      }

      .hero-section {
        background: linear-gradient(135deg, #6e8efb, #a777e3);
        color: white;
        padding: 5rem 0;
        margin-bottom: 3rem;
        border-radius: 0 0 20px 20px;
        transition: background 0.3s;
      }

      .feature-card {
        border: none;
        border-radius: 15px;
        transition: transform 0.3s, background-color 0.3s, color 0.3s;
        margin-bottom: 20px;
        height: 100%;
      }

      .feature-card:hover {
        transform: translateY(-10px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
      }

      .btn-primary {
        background-color: #6e8efb;
        border: none;
        padding: 10px 25px;
      }

      .btn-primary:hover {
        background-color: #5a7df4;
      }

      .navbar-brand {
        font-weight: bold;
      }

      .dark-mode {
        background-color: #121212 !important;
        color: #ffffff !important;
      }

      .dark-mode .hero-section {
        background: linear-gradient(135deg, #333333, #555555);
        color: #ffffff;
      }

      .dark-mode .navbar {
        background-color: #222222 !important;
      }

      .dark-mode .navbar .nav-link,
      .dark-mode .navbar .navbar-brand {
        color: #ffffff !important;
      }

      .dark-mode .card {
        background-color: #1e1e1e;
        color: #ffffff;
      }

      .dark-mode .footer-content {
        background-color: #333333;
        color: #ffffff;
      }

      .dark-mode-toggle {
        color: white;
        border: none;
        padding: 5px 15px;
        border-radius: 20px;
        margin-left: 15px;
        transition: background-color 0.3s;
      }
    </style>
  </head>
  <body>
    <nav class="navbar navbar-expand-lg navbar-light bg-light">
      <div class="container">
        <a class="navbar-brand" href="#">QSimilarity</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
          <ul class="navbar-nav ms-auto align-items-center">
  <li class="nav-item">
    <a class="nav-link active" href="/home">Home</a>
  </li>
  <li class="nav-item">
    <a class="nav-link" href="/compare">Compare</a>
  </li>
  {% if logged_in %}
    <li class="nav-item">
      <a class="nav-link" href="/logout">Logout</a>
    </li>
    <a href="{{ url_for('history') }}" class="btn btn-primary">Search History</a>
  {% else %}
    <li class="nav-item">
      <a class="nav-link" href="/login">Login</a>
    </li>
  {% endif %}
  <li class="nav-item">
    <button id="toggleMode" class="dark-mode-toggle">🌙</button>
  </li>
</ul>

        </div>
      </div>
    </nav>

    <div class="hero-section text-center">
      <div class="container">
        <h1 class="display-4">Question Similarity Checker</h1>
        <p class="lead">Advanced AI-powered tool to compare questions in multiple languages</p>
        <a href="/compare" class="btn btn-primary btn-lg mt-3">Try It Now</a>
      </div>
    </div>

    <div class="container">
      <div class="row">
        <div class="col-md-4">
          <div class="card feature-card">
            <div class="card-body text-center">
              <h5 class="card-title">Multilingual Support</h5>
              <p class="card-text">Compare questions in English, Telugu, and many other languages with our advanced models.</p>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card feature-card">
            <div class="card-body text-center">
              <h5 class="card-title">Dual AI Models</h5>
              <p class="card-text">Choose between our custom LSTM model or powerful Transformer approach.</p>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card feature-card">
            <div class="card-body text-center">
              <h5 class="card-title">Instant Results</h5>
              <p class="card-text">Get similarity scores in seconds with our optimized machine learning models.</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <footer class="text-center text-lg-start mt-5">
      <div class="text-center p-3 footer-content">
        © 2025 Question Similarity Checker
      </div>
    </footer>

    <script>
      const toggleButton = document.getElementById('toggleMode');
      const body = document.body;

      function updateToggleButtonIconAndStyle(isDark) {
        if (isDark) {
          toggleButton.textContent = '☀';
          toggleButton.style.backgroundColor = '#ffcc00';
        } else {
          toggleButton.textContent = '🌙';
          toggleButton.style.backgroundColor = '#000000';
        }
      }

      toggleButton.addEventListener('click', () => {
        body.classList.toggle('dark-mode');
        const isDark = body.classList.contains('dark-mode');
        localStorage.setItem('mode', isDark ? 'dark' : 'light');
        updateToggleButtonIconAndStyle(isDark);
      });

      window.onload = () => {
        const savedMode = localStorage.getItem('mode');
        const isDark = savedMode === 'dark';
        if (isDark) body.classList.add('dark-mode');
        updateToggleButtonIconAndStyle(isDark);
      };
    </script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>

"""
login_html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Login - QSimilarity</title>
    <link rel="icon" href="{{ url_for('static', filename='nobg.png') }}" type="image/png">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body {
        background: #f8f9fa;
        color: #333;
      }

      body.dark-mode {
        background-color: #121212;
        color: #f0f0f0;
      }

      .login-container {
        max-width: 400px;
        margin: 50px auto;
        padding: 30px;
        background: white;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
      }

      body.dark-mode .login-container {
        background-color: #333;
        color: #fff;
      }

      .login-header {
        text-align: center;
        margin-bottom: 30px;
      }

      .login-header h3, .login-header p, .register-link p {
        color: inherit;
      }

      .form-control {
        margin-bottom: 20px;
      }

      .btn-login {
        width: 100%;
        padding: 10px;
        background: #6e8efb;
        border: none;
      }

      .btn-login:hover {
        background: #5a7df4;
      }

      .register-link {
        text-align: center;
        margin-top: 20px;
      }

      .dark-mode-toggle {
        position: fixed;
        top: 15px;
        right: 15px;
        cursor: pointer;
        background: #444;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        z-index: 999;
      }

      .dark-mode-toggle:hover {
        background: #666;
      }
    </style>
  </head>
  <body>
    <div class="dark-mode-toggle" onclick="toggleDarkMode()">🌓</div>
    <div class="container">
      <div class="login-container">
        <div class="login-header">
          <h3>Login</h3>
          <p class="text-primary">Welcome back to QSimilarity!</p>
        </div>
        <form method="POST" action="/login">
          <div class="mb-3">
            <input type="text" class="form-control" name="username" placeholder="Username" required>
          </div>
          <div class="mb-3">
            <input type="password" class="form-control" name="password" placeholder="Password" required>
          </div>
          <button type="submit" class="btn btn-primary btn-login">Login</button>
        </form>
        <div class="register-link">
          <p class="text-primary">Don't have an account? <a href="/register">Create one</a></p>
        </div>
      </div>
    </div>

    <script>
      function toggleDarkMode() {
        const body = document.body;
        const newTheme = body.classList.contains("dark-mode") ? "light" : "dark";
        body.classList.toggle("dark-mode");
        localStorage.setItem('mode', newTheme); // Store in localStorage
      }

      window.onload = function() {
        const savedMode = localStorage.getItem('mode');
        const isDark = savedMode === 'dark';
        if (isDark) {
          document.body.classList.add("dark-mode");
        }
      };
    </script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
"""

register_html = """

<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Register - QSimilarity</title>
    <link rel="icon" href="{{ url_for('static', filename='nobg.png') }}" type="image/png">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body {
        background: #f8f9fa;
        color: #333;
      }

      body.dark-mode {
        background-color: #121212;
        color: #f0f0f0;
      }

      .register-container {
        max-width: 400px;
        margin: 50px auto;
        padding: 30px;
        background: white;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
      }

      body.dark-mode .register-container {
        background-color: #333; /* Light black or dark gray background */
        color: #fff; /* Light text color */
      }

      .register-header {
        text-align: center;
        margin-bottom: 30px;
      }

      .form-control {
        margin-bottom: 20px;
      }

      .btn-register {
        width: 100%;
        padding: 10px;
        background: #6e8efb;
        border: none;
      }

      .btn-register:hover {
        background: #5a7df4;
      }

      .login-link {
        text-align: center;
        margin-top: 20px;
      }

      .dark-mode-toggle {
        position: fixed;
        top: 15px;
        right: 15px;
        cursor: pointer;
        background: #444;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        z-index: 999;
      }

      .dark-mode-toggle:hover {
        background: #666;
      }
    </style>
  </head>
  <body>
    <div class="dark-mode-toggle" onclick="toggleDarkMode()">🌓</div>
    <div class="container">
      <div class="register-container">
        <div class="register-header">
          <h3>Create an Account</h3>
          <p class="text-primary">Join QSimilarity to start comparing questions</p>
        </div>
        <form method="POST" action="/register">
          <div class="mb-3">
            <input type="text" class="form-control" name="username" placeholder="Username" required>
          </div>
          <div class="mb-3">
            <input type="email" class="form-control" name="email" placeholder="Email" required>
          </div>
          <div class="mb-3">
            <input type="password" class="form-control" name="password" placeholder="Password" required>
          </div>
          <div class="mb-3">
            <input type="password" class="form-control" name="confirm_password" placeholder="Confirm Password" required>
          </div>
          <button type="submit" class="btn btn-primary btn-register">Register</button>
        </form>
        <div class="login-link">
          <p class="text-primary">Already have an account? <a href="/login">Login</a></p>
        </div>
      </div>
    </div>

    <script>
      function toggleDarkMode() {
        const body = document.body;
        const newTheme = body.classList.contains("dark-mode") ? "light" : "dark";
        body.classList.toggle("dark-mode");
        localStorage.setItem('mode', newTheme); // Store in localStorage
      }

      window.onload = function() {
        const savedMode = localStorage.getItem('mode');
        const isDark = savedMode === 'dark';
        if (isDark) {
          document.body.classList.add("dark-mode");
        }
      };
    </script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
"""

@app.route("/history")
def history():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        # First get the user ID from project.db
        project_conn = sqlite3.connect('project.db')
        project_cursor = project_conn.cursor()
        project_cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
        user = project_cursor.fetchone()
        
        if not user:
            return "User not found", 404
            
        user_id = user[0]
        
        # Now get history from your_database.db
        yourdb_conn = sqlite3.connect('your_database.db')
        yourdb_cursor = yourdb_conn.cursor()
        
        # Modified to include date and keep all entries (not grouping)
        yourdb_cursor.execute("""
            SELECT query, similarity_score, date 
            FROM search_history 
            WHERE user_id = ? 
            ORDER BY date DESC
            LIMIT 50  
        """, (user_id,))
        
        history_data = []
        for row in yourdb_cursor.fetchall():
            try:
                # Convert score to float and format date (but exclude from display)
                score = float(row[1]) if row[1] is not None else 0.0
                history_data.append({
                    'query': row[0],  # Only keep the query text
                    # 'similarity_score': score,  # Removed
                    # 'date': datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S').strftime('%b %d, %Y %I:%M %p')  # Removed
                })
            except (ValueError, TypeError) as e:
                print(f"Error processing history entry: {e}")
                continue
    except Exception as e:
        print(f"Database error: {e}")
        history_data = []
    finally:
        project_conn.close()
        yourdb_conn.close()
    
    return render_template_string(history_html, history=history_data)

history_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Search History</title>
    <link rel="icon" href="{{ url_for('static', filename='nobg.png') }}" type="image/png">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
            color: #212529;
        }
        
        body.dark-mode {
            background-color: #121212;
            color: #f0f0f0;
        }
        
        .container {
            margin-top: 50px;
        }
        
        table {
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        
        body.dark-mode table {
            background-color: #2c2c2c;
            color: white;
            border: 1px solid #444;
        }
        
        th, td {
            padding: 12px;
            vertical-align: middle;
        }
        
        body.dark-mode th,
        body.dark-mode td {
            border-bottom: 1px solid #444;
        }
        
        th {
            background-color: #f8f9fa;
            font-weight: bold;
            text-align: center;
        }
        
        body.dark-mode th {
            background-color: #333;
            color: white;
        }
        
        tr:hover {
            background-color: #f8f9fa;
        }
        
        body.dark-mode tr:hover {
            background-color: #333;
        }
        
        .btn-back {
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            text-decoration: none;
            margin-bottom: 20px;
            display: inline-block;
        }
        
        .btn-back:hover {
            background-color: #0056b3;
        }
        
        h2 {
            text-align: center;
            color: #343a40;
            margin-bottom: 30px;
        }
        
        body.dark-mode h2 {
            color: #f0f0f0;
        }
        
        .no-history {
            text-align: center;
            padding: 20px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        
        body.dark-mode .no-history {
            background-color: #2c2c2c;
            color: white;
        }
        
        .dark-mode-toggle {
            position: fixed;
            top: 15px;
            right: 15px;
            cursor: pointer;
            background: #444;
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            z-index: 999;
        }
        
        .dark-mode-toggle:hover {
            background: #666;
        }
    </style>
</head>
<body>
    <div class="dark-mode-toggle" onclick="toggleDarkMode()">🌓</div>
    <div class="container">
        <h2>Your Search History</h2>
        <a href="{{ url_for('home') }}" class="btn btn-primary mb-4">Back to Home</a>
        <a href="{{ url_for('compare') }}" class="btn btn-success mb-4 ml-2">New Comparison</a>

        {% if history %}
        <div class="table-responsive">
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>Search Query</th> <!-- Removed date and score columns -->
                    </tr>
                </thead>
                <tbody>
                    {% for entry in history %}
                    <tr>
                        <td>{{ entry.query }}</td> <!-- Only display query -->
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="no-history">
            <p>No search history found.</p>
        </div>
        {% endif %}
    </div>

    <script>
        function toggleDarkMode() {
            const body = document.body;
            const newTheme = body.classList.contains("dark-mode") ? "light" : "dark";
            body.classList.toggle("dark-mode");
            localStorage.setItem('mode', newTheme);
        }
        
        window.onload = function() {
            const mode = localStorage.getItem('mode');
            if (mode === 'dark') {
                document.body.classList.add('dark-mode');
            }
        };
    </script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

    
# Define the HTML content for compare.html

compare_html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Compare Questions</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body.dark-mode {
            background-color: #121212;
            color: #f0f0f0;
        }

        .result-box.dark-mode {
            background-color: #333;
            color: #fff;
        }

        .dark-mode-toggle {
            position: fixed;
            top: 15px;
            right: 15px;
            cursor: pointer;
            background: #444;
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            z-index: 999;
        }

        .dark-mode-toggle:hover {
            background: #666;
        }
    </style>
</head>
<body>
    <div class="dark-mode-toggle" onclick="toggleDarkMode()">🌓</div>

    <div class="container mt-5">
        <h1 class="mb-4">Compare Question Similarity</h1>
        <form method="POST" action="/compare">
            <div class="mb-3">
                <label for="question1" class="form-label"><strong>Question 1:</strong></label>
                <textarea id="question1" name="question1" rows="4" class="form-control" required></textarea>
            </div>
            <div class="mb-3">
                <label for="question2" class="form-label"><strong>Question 2:</strong></label>
                <textarea id="question2" name="question2" rows="4" class="form-control" required></textarea>
            </div>
            <button type="submit" class="btn btn-success">Compare</button>
        </form>

        {% if result %}
            <div class="result-box mt-4 p-3 rounded {{ 'dark-mode' if request.cookies.get('theme') == 'dark' else '' }}">
                <h3>Comparison Result:</h3>
                <p><strong>Question 1:</strong> {{ result.q1 }}</p>
                <p><strong>Question 2:</strong> {{ result.q2 }}</p>
                <p><strong>Similarity Score:</strong> {{ result.score }}%</p>
                <p><strong>Verdict:</strong> {{ result.verdict }}</p>
                {% if result.google_link %}
                    <p><a href="{{ result.google_link }}" target="_blank">Search this question on Google</a></p>
                {% endif %}
            </div>
        {% endif %}
    </div>

    <script>
        function toggleDarkMode() {
            const body = document.body;
            const newTheme = body.classList.contains("dark-mode") ? "light" : "dark";
            body.classList.toggle("dark-mode");
            document.cookie = "theme=" + newTheme + "; path=/";
        }

        window.onload = function() {
            const theme = document.cookie.replace(/(?:(?:^|.;\\s)theme\\s*=\\s*([^;]).$)|^.*$/, "$1");
            if (theme === "dark") {
                document.body.classList.add("dark-mode");
            }
        };
    </script>
</body>
</html>
"""

# HTML for the transformer comparison form
transformer_html = '''
    <form method="POST">
        <input type="text" name="question1" placeholder="Enter Question 1">
        <input type="text" name="question2" placeholder="Enter Question 2">
        <button type="submit">Compare</button>
    </form>
'''
if __name__ == "__main__":
 # Replace 5000 with your app port
   

    app.run(host='0.0.0.0', port=5001, debug=False)