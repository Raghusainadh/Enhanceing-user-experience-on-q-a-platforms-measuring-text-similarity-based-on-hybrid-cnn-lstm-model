🧠 Question Similarity Checker (Multilingual AI-Powered)
This project is a Flask-based web application that allows users to compare two questions and determine their semantic similarity using AI/ML models (Sentence-BERT and BERT). It supports multilingual input (including Telugu) and provides an intuitive UI with authentication, search history, and email verification.

🚀 Features
🔐 User Authentication with secure password hashing

✉️ Email verification system using Gmail SMTP

🌍 Multilingual support via Google Translate (e.g., Telugu → English)

🧠 Dual-model comparison:

Sentence-BERT (paraphrase-xlm-r-multilingual-v1)

BERT Classification (bert-base-uncased)

📊 Cosine similarity scoring

💡 Dark mode UI

🕓 Search history logging (SQLite)

🌐 Public access via Ngrok

🛠️ Tech Stack
Backend: Python, Flask

AI Models: SentenceTransformer, transformers, torch, BERT

Frontend: HTML, Bootstrap 5

Database: SQLite

Other: bcrypt, smtplib, deep_translator, pyngrok

📸 Screenshots
Login/Register pages 
![WhatsApp Image 2025-06-12 at 10 31 54_cdf15042](https://github.com/user-attachments/assets/6311ad76-cf86-435c-b61f-d918ad483f8a)


light/dark mode

Home dashboard and feature cards

Similarity result page with Google Search integration

Search history table

📂 Project Structure
bash
Copy
Edit
.
├── cnn &lstm.py          # Main application code
├── templates/            # HTML templates (inline in code)
├── static/               # Static assets like images (referenced in code)
├── project.db            # User credentials DB
└── your_database.db      # Search history DB
🔧 Setup Instructions
Clone the repo:

bash
Copy
Edit
git clone https://github.com/yourusername/question-similarity-checker.git
cd question-similarity-checker
Install requirements:

bash
Copy
Edit
pip install -r requirements.txt
Add your Ngrok auth token:

python
Copy
Edit
ngrok.set_auth_token("YOUR_AUTHTOKEN")
Update Gmail credentials in send_verification_email:

python
Copy
Edit
gmail_user = 'your_email@gmail.com'
gmail_app_password = 'your_app_password'  # Enable 2FA and use App Password
Run the app:

bash
Copy
Edit
python "cnn &lstm.py"
Access app via:

Localhost: http://localhost:5001

Ngrok URL: (shown in terminal)

✅ Default Admin
Username	Password
admin	admin123

🛡️ Security Notes
Replace all placeholder secrets before deployment (app.secret_key, Gmail password, etc.)

Consider using environment variables for credentials

📜 License
MIT License

Would you like me to also generate a requirements.txt file based on the imports in your script?







Is this conversation helpful so far?





