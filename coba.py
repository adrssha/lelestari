from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file
from functools import wraps
import random
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import logging
from datetime import datetime, date
import json
import base64
from io import BytesIO
import traceback
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# ============================================================
# 🔧 1. KONFIGURASI AWAL
# ============================================================
# Setup Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load Environment Variables
if os.environ.get("RAILWAY_ENVIRONMENT") is None:  # atau check env lain
    load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# Inisialisasi Flask & Supabase
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "lelestari-secret-123")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app.ledger_cache = {}
app.accounts_cache = {}
app.accounts_cache_full = {}
app.tb_cache = {}

# ============================================================
# 🛠️ 2. FUNGSI BANTU (HELPER FUNCTIONS)
# ============================================================
# DI KODE ANDA - FUNGSI send_email YANG BARU:
def send_email(recipient, subject, body):
    """Fungsi untuk mengirim email menggunakan SendGrid"""
    try:
        logger.info(f"🔄 Attempting to send email to: {recipient}")
        
        # ✅ GUNAKAN EMAIL_PASSWORD SEBAGAI SENDGRID API KEY
        SENDGRID_API_KEY = os.environ.get("EMAIL_PASSWORD")
        if not EMAIL_SENDER or not SENDGRID_API_KEY:
            logger.error("❌ SendGrid credentials missing!")
            return False
        
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        message = Mail(
            from_email=EMAIL_SENDER,
            to_emails=recipient,
            subject=subject,
            plain_text_content=body
        )
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        if response.status_code in [200, 202]:
            logger.info(f"✅ Email sent successfully to {recipient}")
            return True
        else:
            logger.error(f"❌ SendGrid Error: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ General email error: {e}")
        return False
            
    except Exception as e:
        logger.error(f"❌ General email error: {e}")
        logger.error(traceback.format_exc())
        return False

def generate_invoice(prefix="INV"):
    """Generate nomor invoice"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = random.randint(100, 999)
    return f"{prefix}-{ts}-{rand}"

def today_str():
    """Get today's date in ISO format"""
    return date.today().isoformat()

def format_currency(amount):
    """Format angka menjadi format mata uang Indonesia"""
    if amount is None:
        return "Rp 0"
    try:
        return f"Rp {amount:,.0f}".replace(",", ".")
    except:
        return "Rp 0"

def format_ledger_display(account_type, balance):
    try:
        if balance is None:
            return 0
        
        # Untuk akun debit normal (Aktiva Lancar, Aktiva Tetap, Beban)
        if account_type in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
            return balance
        # Untuk akun kredit normal (Kewajiban, Modal, Pendapatan)  
        else:
            return balance  # Biarkan tetap, karena perhitungan sudah benar di fungsi utama
    
    except Exception as e:
        logger.error(f"❌ Error in format_ledger_display: {e}")
        return balance if balance else 0

# ============================================================
# 🔹 DECORATORS
# ============================================================

def login_required(f):
    """Decorator untuk memproteksi route yang butuh login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator untuk route yang butuh akses admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            return '''
            <div class="message error">
                ❌ Akses Ditolak! Hanya Admin yang bisa mengakses halaman ini.
            </div>
            <a href="/dashboard"><button>Kembali ke Dashboard</button></a>
            ''', 403
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """Decorator untuk route yang butuh akses super admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_super_admin():
            return '''
            <div class="message error">
                ❌ Akses Ditolak! Hanya Super Admin yang bisa mengakses halaman ini.
            </div>
            <a href="/dashboard"><button>Kembali ke Dashboard</button></a>
            ''', 403
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# 🏠 3. HALAMAN SEBELUM LOGIN
# ============================================================

@app.route("/")
def home():
    """Dashboard publik yang bisa diakses semua orang"""
    public_dashboard_html = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lelestari - Kelola Bisnis Lele Anda</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #008DD8, #00C4FF, #FFFFFF, #F8C87A, #E5AD5D);
                min-height: 100vh;
                color: #333;
                overflow-x: hidden;
            }

            .header {
                background: rgba(255, 255, 255, 0.95);
                padding: 15px 30px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            }

            .header-content {
                display: flex;
                justify-content: space-between;
                align-items: center;
                max-width: 1200px;
                margin: 0 auto;
            }

            .logo-section h1 {
                color: #008DD8;
                font-size: 24px;
                font-weight: 700;
            }

            .auth-buttons {
                display: flex;
                gap: 10px;
            }

            .btn-auth {
                background: #008DD8;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                text-decoration: none;
                transition: all 0.3s ease;
            }

            .btn-auth:hover {
                background: #006bb3;
            }

            /* LAYOUT UTAMA - FULL WIDTH */
            .main-container {
                max-width: 100%;
                margin: 0;
                padding: 0;
            }

            /* KOTAK WELCOME - FULL WIDTH */
            .welcome-box {
                background: rgba(255, 255, 255, 0.95);
                padding: 50px 30px;
                margin: 20px 0;
                border-radius: 0;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                border-left: 5px solid #008DD8;
                border-right: 5px solid #F8C87A;
            }

            .welcome-content {
                max-width: 1200px;
                margin: 0 auto;
                display: grid;
                grid-template-columns: 2fr 1fr;
                gap: 40px;
                align-items: center;
            }

            .welcome-text h2 {
                color: #008DD8;
                font-size: 36px;
                margin-bottom: 15px;
                font-weight: 700;
            }

            .welcome-text p {
                color: #666;
                font-size: 18px;
                line-height: 1.6;
            }

            .welcome-stats {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }

            .stat-item {
                text-align: center;
                padding: 15px;
                background: rgba(0, 141, 216, 0.1);
                border-radius: 8px;
                border-left: 3px solid #008DD8;
            }

            .stat-number {
                font-size: 24px;
                font-weight: bold;
                color: #008DD8;
            }

            .stat-label {
                font-size: 12px;
                color: #666;
                margin-top: 5px;
            }

            /* KOTAK RATING - FULL WIDTH */
            .rating-box {
                background: linear-gradient(135deg, #008DD8, #00C4FF);
                padding: 40px 30px;
                margin: 20px 0;
                border-radius: 0;
                color: white;
            }

            .rating-content {
                max-width: 1200px;
                margin: 0 auto;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
                align-items: center;
            }

            .rating-stars {
                text-align: center;
            }

            .stars {
                font-size: 36px;
                color: #FFD700;
                margin-bottom: 10px;
            }

            .rating-text {
                font-size: 20px;
                font-weight: 600;
                margin-bottom: 5px;
            }

            .rating-subtext {
                font-size: 14px;
                opacity: 0.9;
            }

            .rating-features {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }

            .feature-item {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 10px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 5px;
            }

            .feature-icon {
                font-size: 20px;
            }

            /* KOTAK AUTH - FULL WIDTH */
            .auth-box {
                background: rgba(255, 255, 255, 0.95);
                padding: 50px 30px;
                margin: 20px 0;
                border-radius: 0;
                box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
                border-top: 3px solid #F8C87A;
            }

            .auth-content {
                max-width: 1200px;
                margin: 0 auto;
                text-align: center;
            }

            .auth-content h3 {
                color: #008DD8;
                font-size: 32px;
                margin-bottom: 20px;
                font-weight: 700;
            }

            .auth-content p {
                color: #666;
                font-size: 18px;
                margin-bottom: 30px;
                max-width: 600px;
                margin-left: auto;
                margin-right: auto;
            }

            .auth-buttons-large {
                display: flex;
                gap: 20px;
                justify-content: center;
                flex-wrap: wrap;
            }

            .btn-auth-large {
                background: #008DD8;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                text-decoration: none;
                transition: all 0.3s ease;
                min-width: 180px;
            }

            .btn-auth-large:hover {
                background: #006bb3;
                transform: translateY(-2px);
            }

            .btn-register {
                background: #28a745;
            }

            .btn-register:hover {
                background: #218838;
            }

            /* RESPONSIVE */
            @media (max-width: 768px) {
                .header-content {
                    flex-direction: column;
                    gap: 10px;
                    text-align: center;
                }
                
                .welcome-content {
                    grid-template-columns: 1fr;
                    gap: 20px;
                }
                
                .rating-content {
                    grid-template-columns: 1fr;
                    gap: 20px;
                }
                
                .welcome-stats {
                    grid-template-columns: 1fr;
                }
                
                .rating-features {
                    grid-template-columns: 1fr;
                }
                
                .auth-buttons-large {
                    flex-direction: column;
                    align-items: center;
                }
                
                .welcome-text h2 {
                    font-size: 28px;
                }
                
                .auth-content h3 {
                    font-size: 28px;
                }
            }

            @media (max-width: 480px) {
                .welcome-box,
                .rating-box,
                .auth-box {
                    padding: 30px 20px;
                }
                
                .btn-auth-large {
                    padding: 12px 24px;
                    min-width: 160px;
                }
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <div class="header">
            <div class="header-content">
                <div class="logo-section">
                    <h1>🌿 Lelestari</h1>
                </div>
                <div class="auth-buttons">
                    <a href="/login" class="btn-auth">🔐 Masuk</a>
                    <a href="/register" class="btn-auth">📝 Daftar</a>
                </div>
            </div>
        </div>

        <!-- Main Content -->
        <div class="main-container">
            <!-- Kotak Welcome -->
            <div class="welcome-box">
                <div class="welcome-content">
                    <div class="welcome-text">
                        <h2>Dari Kolam Kami untuk Keluarga Anda 🌱🐟</h2>
                        <p>Kami menghadirkan lele segar dengan standar kebersihan tinggi, dipelihara dengan pakan berkualitas dan air kolam yang terjaga setiap hari. Setiap lele dipanen pada waktu terbaik untuk memastikan rasa, tekstur, dan kesegaran yang maksimal.</p>
                    </div>
                    <div class="welcome-stats">
                        <div class="stat-item">
                            <div class="stat-number">2500+</div>
                            <div class="stat-label">Pembeli Puas</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number">99%</div>
                            <div class="stat-label">Lele Segar Setiap Hari</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Kotak Rating -->
            <div class="rating-box">
                <div class="rating-content">
                    <div class="rating-stars">
                        <div class="stars">★★★★★</div>
                        <div class="rating-text">4.6/5 Rating</div>
                        <div class="rating-subtext">2500+ Pembeli Puas</div>
                    </div>
                    <div class="rating-features">
                        <div class="feature-item">
                            <span class="feature-icon">⚡</span>
                            <span>Cepat & Responsif</span>
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">🐟</span>
                            <span>Lele segar</span>
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">🔒</span>
                            <span>Aman & Terpercaya</span>
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">💸</span>
                            <span>Harga Terjangkau</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Kotak Auth -->
            <div class="auth-box">
                <div class="auth-content">
                    <h3>Dapatkan Lele Segar dengan Harga Terbaik! 💸🐟</h3>
                    <p>Masuk dan nikmati akses penuh ke harga terbaik, stok terbaru, dan penawaran spesial yang hanya tersedia untuk pengguna terdaftar. Lele berkualitas tinggal satu klik dari Anda!</p>
                    <div class="auth-buttons-large">
                        <a href="/register" class="btn-auth-large btn-register">📝 Daftar Gratis</a>
                        <a href="/login" class="btn-auth-large">🔐 Masuk</a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return public_dashboard_html

# ============================================================
# 🔐 4. LOGIN / REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    """Halaman registrasi user baru - DIPERBAIKI ERROR HANDLING"""
    message = ""
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        
        logger.info(f"🔄 Registrasi: {name} ({email})")
        
        try:
            # Cek apakah email sudah terdaftar
            result = supabase.table("users").select("email").eq("email", email).execute()
            
            if result.data:
                message = '<div class="message error">❌ Email sudah terdaftar!</div>'
                logger.warning(f"Email {email} sudah terdaftar")
            else:
                otp = str(random.randint(100000, 999999))
                
                # Simpan data di session
                session['register_name'] = name
                session['register_email'] = email
                session['register_password'] = password
                session['register_otp'] = otp
                
                logger.info(f"📧 Kirim OTP {otp} ke {email}")
                
                email_body = f"""
                HALO {name}! 👋

                Kode OTP Verifikasi Lelestari Anda adalah:

                🌿 {otp} 🍃
                Masukkan kode ini di halaman verifikasi untuk menyelesaikan pendaftaran.

                ⚠️ PERHATIAN: 
                - Jangan berikan kode ini kepada siapapun

                Terima kasih,
                🌿 Tim Lelestari 🍃
                """
                
                # Coba kirim email dengan timeout
                email_sent = send_email(email, "🌿 Kode OTP Lelestari", email_body)
                
                if email_sent:
                    logger.info(f"✅ OTP berhasil dikirim ke {email}")
                    return redirect('/verify')
                else:
                    message = '''
                    <div class="message error">
                        ❌ Gagal kirim OTP! 
                        <br><small>Kemungkinan masalah: 
                        <br>- Konfigurasi email server
                        <br>- App Password Gmail belum dibuat
                        <br>- Environment variables belum diset</small>
                    </div>
                    '''
                    logger.error(f"❌ Gagal kirim OTP ke {email}")
                    
        except Exception as e:
            message = f'<div class="message error">⚠ Error sistem: {str(e)}</div>'
            logger.error(f"Database error: {str(e)}")
    
    html = f"""
    <h2>📝 Daftar Akun Baru</h2>
    {message}
    <form method="POST">
        <input type="text" name="name" placeholder="Nama Lengkap" required><br>
        <input type="email" name="email" placeholder="Email" required><br>
        <input type="password" name="password" placeholder="Password" required><br>
        <button type="submit">📝 Daftar & Kirim OTP</button>
    </form>
    
    <div style="margin-top: 20px; padding: 15px; background: #e7f3ff; border-radius: 8px;">
        <h4>💡 Troubleshooting OTP:</h4>
        <ul style="text-align: left;">
            <li>Pastikan email yang dimasukkan valid</li>
            <li>Cek folder <strong>Spam/Promosi</strong> di email Anda</li>
            <li>Jika tidak menerima OTP, kontak administrator</li>
        </ul>
    </div>
    
    <p><a href="/login">Sudah punya akun? Masuk</a></p>
    <a href="/"><button class="btn-secondary">🏠 Kembali ke Dashboard</button></a>
    """
    return render_template_string(base_html, content=html)

@app.route("/verify", methods=["GET", "POST"])
def verify_otp():
    """Halaman verifikasi OTP - SEMUA USER BARU JADI ADMIN"""
    message = ""
    name = session.get('register_name')
    email = session.get('register_email')
    
    if not email:
        return redirect('/register')
    
    logger.info(f"🔄 Verifikasi OTP untuk: {name} ({email})")
    
    if request.method == "POST":
        otp_input = request.form["otp"]
        otp_session = session.get('register_otp')
        
        logger.info(f"📩 OTP input: {otp_input}, OTP session: {otp_session}")
        
        if otp_input == otp_session:
            password = session.get('register_password')
            
            try:
                user_data = {
                    "name": name,
                    "email": email,
                    "password": password,
                    "role": "admin",  # ✅ UBAH INI: SEMUA USER BARU JADI ADMIN
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                result = supabase.table("users").insert(user_data).execute()
                logger.info(f"✅ User {name} ({email}) berhasil disimpan sebagai ADMIN")
                
                welcome_email = f"""
                Selamat datang di Lelestari, {name}! 🎉

                Akun Anda telah berhasil dibuat sebagai **Admin**.

                📋 Informasi Akun:
                • Email: {email}
                • Role: Admin
                • Status: Aktif

                Anda sekarang memiliki akses penuh untuk mengelola sistem Lelestari.

                Terima kasih telah bergabung dengan Lelestari!
                🌿 Tim Lelestari 🍃
                """
                
                send_email(email, "🌿 Selamat Datang di Lelestari!", welcome_email)
                
                session.pop('register_name', None)
                session.pop('register_email', None)
                session.pop('register_password', None)
                session.pop('register_otp', None)
                
                message = '<div class="message success">✅ Akun berhasil dibuat sebagai Admin!</div>'
                html = f"""
                <h2>🎉 Registrasi Berhasil!</h2>
                {message}
                <div class="message info">
                    <strong>Selamat datang {name}!</strong><br>
                    Anda telah terdaftar sebagai <strong>Admin</strong> dan dapat mengakses semua fitur sistem.
                </div>
                <p>Silakan masuk untuk mulai menggunakan sistem!</p>
                <a href="/login"><button class="btn-success">🔐 Masuk Sekarang</button></a>
                """
                return render_template_string(base_html, content=html)
                
            except Exception as e:
                message = f'<div class="message error">❌ Gagal menyimpan ke database: {str(e)}</div>'
                logger.error(f"❌ Error simpan user: {str(e)}")
        else:
            message = '<div class="message error">❌ OTP salah! Coba lagi.</div>'
            logger.warning(f"❌ OTP salah untuk {email}")
    
    html = f"""
    <h2>🔒 Verifikasi OTP</h2>
    <p>Halo <strong>{name}</strong>!</p>
    <p>Kode OTP dikirim ke: <strong>{email}</strong></p>
    <div class="message info">
        💡 Periksa folder <strong>Spam/Promosi</strong> jika tidak ditemukan
    </div>
    {message}
    <form method="POST">
        <input type="text" name="otp" placeholder="Masukkan 6 digit OTP" 
                required maxlength="6" pattern="[0-9]{{6}}"><br>
        <button type="submit">✅ Verifikasi & Daftar sebagai Admin</button>
    </form>
    <a href="/register"><button class="btn-secondary">↩ Kembali</button></a>
    """
    return render_template_string(base_html, content=html)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Halaman login user"""
    if session.get('logged_in'):
        return redirect('/dashboard')
        
    message = ""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        try:
            result = supabase.table("users").select("*").eq("email", email).execute()
            
            if result.data and result.data[0]['password'] == password:
                session['logged_in'] = True
                session['user_email'] = email
                session['user_name'] = result.data[0]['name']
                session['user_id'] = result.data[0]['id']
                session['user_role'] = result.data[0].get('role', 'pembeli')
                logger.info(f"✅ Login berhasil: {result.data[0]['name']} ({email}) sebagai {session['user_role']}")
                return redirect('/dashboard')
            else:
                message = '<div class="message error">❌ Email atau password salah!</div>'
                logger.warning(f"❌ Login gagal: {email}")
                
        except Exception as e:
            message = f'<div class="message error">⚠ Error database: {str(e)}</div>'
            logger.error(f"Database error saat login: {str(e)}")
    
    html = f"""
    <h2>🔐 Masuk ke Akun</h2>
    {message}
    <form method="POST">
        <input type="email" name="email" placeholder="Email" required><br>
        <input type="password" name="password" placeholder="Password" required><br>
        <button type="submit">Masuk</button>
    </form>
    <p><a href="/register">Belum punya akun? Daftar</a></p>
    <a href="/"><button class="btn-secondary">🏠 Kembali ke Dashboard</button></a>
    """
    return render_template_string(base_html, content=html)

@app.route("/logout")
def logout():
    """Logout user"""
    session.clear()
    logger.info("✅ User logged out")
    return redirect('/')

# ============================================================
# 🔹 TEST EMAIL
# ============================================================

@app.route("/test_email")
def test_email():
    """Route untuk testing email di server"""
    try:
        test_recipient = "lelestari.management@gmail.com"
        
        # Test credentials
        credentials_ok = bool(EMAIL_SENDER and EMAIL_PASSWORD)
        
        test_result = {
            "email_sender": EMAIL_SENDER,
            "email_password_set": bool(EMAIL_PASSWORD),
            "credentials_ok": credentials_ok,
            "test_recipient": test_recipient
        }
        
        if credentials_ok:
            # Test send email
            success = send_email(
                test_recipient, 
                "🌿 Test Email dari Lelestari", 
                "Ini adalah email test dari server deployment!"
            )
            test_result["email_sent"] = success
        else:
            test_result["email_sent"] = False
            
        return jsonify(test_result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 🔹 FUNGSI MANAJEMEN ADMIN & AUTH
# ============================================================

def is_super_admin():
    """Cek apakah user saat ini adalah super admin"""
    user_email = session.get('user_email')
    if not user_email:
        return False
    
    try:
        result = supabase.table("users").select("role").eq("email", user_email).execute()
        if result.data and result.data[0].get('role') == 'super_admin':
            return True
    except Exception as e:
        logger.error(f"❌ Error checking super admin: {e}")
    
    return False

def is_admin():
    """Cek apakah user saat ini adalah admin atau super admin - SEMUA USER YANG LOGIN JADI ADMIN"""
    user_email = session.get('user_email')
    if not user_email:
        return False
    
    # SEMUA USER YANG SUDAH LOGIN DAPAT AKSES ADMIN
    return True

def get_user_role():
    """Ambil role user saat ini - SEMUA USER JADI ADMIN"""
    user_email = session.get('user_email')
    if not user_email:
        return 'guest'
    
    try:
        result = supabase.table("users").select("role").eq("email", user_email).execute()
        if result.data:
            role = result.data[0].get('role', 'pembeli')
            # SEMUA USER YANG LOGIN JADI ADMIN, KECUALI SUPER ADMIN TETAP
            if role == 'pembeli':
                return 'admin'  # Ubah pembeli jadi admin
            return role
    except Exception as e:
        logger.error(f"❌ Error getting user role: {e}")
    
    return 'admin'  # Default jadi admin

def create_initial_super_admin():
    """Buat super admin pertama jika belum ada"""
    try:
        result = supabase.table("users").select("email").eq("role", "super_admin").execute()
        
        if not result.data:
            super_admin_email = "lelestari.management@gmail.com"
            super_admin_password = "Lelestari2KN"
            
            super_admin_data = {
                "name": "Super Admin Lelestari",
                "email": super_admin_email,
                "password": super_admin_password,
                "role": "super_admin",
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            }
            
            supabase.table("users").insert(super_admin_data).execute()
            logger.info(f"✅ Super Admin pertama berhasil dibuat! Email: {super_admin_email}")
            
    except Exception as e:
        logger.error(f"❌ Error creating super admin: {e}")

# ============================================================
# 🏢 5. HALAMAN UTAMA / DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    """Dashboard utama setelah login"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Pengguna')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()

    role_badge = ""
    if user_role == "super_admin":
        role_badge = '<span style="background: #dc3545; color: white; padding: 5px 15px; border-radius: 15px; font-size: 14px; margin-left: 10px;">👑 Super Admin</span>'
    elif user_role == "admin":
        role_badge = '<span style="background: #007bff; color: white; padding: 5px 15px; border-radius: 15px; font-size: 14px; margin-left: 10px;">👨‍💼 Admin</span>'

    contact_data = {
        "email": "lelestari.management@gmail.com",
        "phone": "+6282325902097",
        "address": "Desa Tembok, Kec. Limpung, Kabupaten Batang, Jawa Tengah, 51271",
        "whatsapp_link": "https://wa.me/6282325902097",
        "email_link": "mailto:lelestari.management@gmail.com",
        "maps_link": "https://maps.google.com/?q=Desa+Tembok,+Kec.+Limpung,+Kabupaten+Batang,+Jawa+Tengah,+51271"
    }

    content = f"""
    <div class="welcome-section">
        <h2>Selamat datang di Lelestari, {user_name}! 🌿 {role_badge}</h2>
        <div class="welcome-message">
            {"👑 Anda login sebagai Super Admin - Akses penuh ke semua fitur" if user_role == "super_admin" else 
              "👨‍💼 Anda login sebagai Admin - Akses terbatas untuk mengelola sistem" if user_role == "admin" else 
              "👤 Anda login sebagai Pembeli - Silakan berbelanja lele segar kami"}
        </div>
        {"<div class='message info' style='margin-top: 10px;'><a href='/admin/users'>👑 Manage Users</a> | <a href='/reports'>📊 System Reports</a></div>" if user_role == "super_admin" else ""}
    </div>

    <div class="quick-actions">
        <h2>Akses Cepat</h2>
        <div class="actions-grid"> 
            {"".join([f"""
            <a href="/chart_of_account" class="action-card">
                <div class="action-icon">📊</div>
                <div class="action-title">Chart of Account</div>
            </a>
            <a href="/neraca_saldo_awal" class="action-card">
                <div class="action-icon">💰</div>
                <div class="action-title">Neraca Saldo Awal</div>
            </a>
            <a href="/input_transaksi" class="action-card">
                <div class="action-icon">📝</div>
                <div class="action-title">Input Transaksi</div>
            </a>
            <a href="/jurnal_umum" class="action-card">
                <div class="action-icon">📋</div>
                <div class="action-title">Jurnal Umum</div>
            </a>
            <a href="/buku_besar" class="action-card">
                <div class="action-icon">📒</div>
                <div class="action-title">Buku Besar</div>   
            </a>
            <a href="/nssp" class="action-card">
                <div class="action-icon">🗂️</div>
                <div class="action-title">Neraca Saldo Sebelum Penyesuaian</div>   
            </a>
            <a href="/jurnal_penyesuaian" class="action-card">
                <div class="action-icon">📝</div>
                <div class="action-title">Jurnal Penyesuaian</div>
            </a>    
            <a href="/neraca_saldo_setelah_penyesuaian" class="action-card">
                <div class="action-icon">📊</div>
                <div class="action-title">NS setelah Penyesuaian</div>
            </a>   
            <a href="/neraca_lajur" class="action-card">
                <div class="action-icon">📋</div>
                <div class="action-title">Neraca Lajur</div>
            </a>
            <a href="/laporan_laba_rugi" class="action-card">
                <div class="action-icon">📈</div>
                <div class="action-title">Laporan Laba Rugi</div>
            </a>
            <a href="/laporan_perubahan_modal" class="action-card">
                <div class="action-icon">📊</div>
                <div class="action-title">Laporan Perubahan Modal</div>
            </a>
            <a href="/laporan_posisi_keuangan" class="action-card">
                <div class="action-icon">💰</div>
                <div class="action-title">Laporan Posisi Keuangan</div>
            </a>
            <a href="/laporan_arus_kas" class="action-card">
                <div class="action-icon">💸</div>
                <div class="action-title">Laporan Arus Kas</div>
            </a>
            <a href="/jurnal_penutup" class="action-card">
                <div class="action-icon">📒</div>
                <div class="action-title">Jurnal Penutup</div>
            </a>
            <a href="/neraca_saldo_setelah_penutup" class="action-card">
                <div class="action-icon">📊</div>
                <div class="action-title">Neraca Saldo setelah Penutup</div>
            </a>

            """ if user_role in ['admin', 'super_admin'] else ""])}
            
            {"".join([f"""
            <a href="/admin/users" class="action-card">
                <div class="action-icon">👑</div>
                <div class="action-title">Admin Panel</div>
            </a>
            """ if user_role == 'super_admin' else ""])}
        </div>
    </div>

    <div class="quick-actions">
        <h2>📞 Informasi Kontak & Lokasi</h2>
        <div class="actions-grid">
            <a href="{contact_data['email_link']}" class="action-card" target="_blank">
                <div class="action-icon">📧</div>
                <div class="action-title">Email</div>
                <div style="font-size: 14px; margin-top: 5px;">{contact_data['email']}</div>
                <div style="font-size: 12px; color: #666; margin-top: 5px;">Klik untuk mengirim email</div>
            </a>
            
            <a href="{contact_data['whatsapp_link']}" class="action-card" target="_blank">
                <div class="action-icon">📞</div>
                <div class="action-title">Telepon/WhatsApp</div>
                <div style="font-size: 14px; margin-top: 5px;">{contact_data['phone']}</div>
                <div style="font-size: 12px; color: #666; margin-top: 5px;">Klik untuk chat WhatsApp</div>
            </a>
            
            <a href="{contact_data['maps_link']}" class="action-card" target="_blank">
                <div class="action-icon">📍</div>
                <div class="action-title">Alamat</div>
                <div style="font-size: 14px; margin-top: 5px;">{contact_data['address']}</div>
                <div style="font-size: 12px; color: #666; margin-top: 5px;">Klik untuk buka Google Maps</div>
            </a>
            
            <div class="action-card">
                <div class="action-icon">🕒</div>
                <div class="action-title">Jam Operasional</div>
                <div style="font-size: 14px; margin-top: 5px;">Senin - Minggu: 07:00 - 18:00</div>
                <div style="font-size: 12px; color: #666; margin-top: 5px;">Waktu Indonesia Barat</div>
            </div>
        </div>
    </div>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 🔹 TEMPLATE HTML DASHBOARD
# ============================================================

base_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Lelestari</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            background: linear-gradient(135deg, #008DD8, #00C4FF, #FFFFFF, #F8C87A, #E5AD5D); 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 20px;
        }
        .container { 
            background: white; 
            padding: 30px; 
            border-radius: 15px; 
            width: 100%;
            max-width: 800px;
            text-align: center; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.1); 
        }
        input, select { 
            width: 90%; 
            padding: 10px; 
            margin: 8px 0; 
            border: 1px solid #ddd; 
            border-radius: 8px; 
            font-size: 16px;
        }
        button { 
            background: #008DD8;
            color: white; 
            border: none; 
            padding: 12px 24px; 
            border-radius: 8px; 
            cursor: pointer; 
            margin: 5px; 
            font-size: 16px;
            width: 95%;
            transition: background 0.3s ease;
        }
        button:hover {
            background: #006bb3;
        }
        .btn-secondary {
            background: #6c757d;
        }
        .btn-secondary:hover {
            background: #5a6268;
        }
        .btn-success {
            background: #28a745;
        }
        .btn-success:hover {
            background: #218838;
        }
        .btn-warning {
            background: #ffc107;
            color: #212529;
        }
        .btn-warning:hover {
            background: #e0a800;
        }
        .message {
            padding: 12px;
            margin: 10px 0;
            border-radius: 8px;
            font-size: 14px;
        }
        .success { 
            background: #d4ffd4; 
            color: #006600; 
            border: 1px solid #c3e6cb;
        }
        .error { 
            background: #ffd4d4; 
            color: #cc0000; 
            border: 1px solid #f5c6cb;
        }
        .info { 
            background: #d1ecf1; 
            color: #0c5460; 
            border: 1px solid #bee5eb;
        }
        .menu { 
            margin: 15px 0; 
        }
        a {
            text-decoration: none;
            color: #008DD8; 
        }
    </style>
</head>
<body>
    <div class="container">{{ content|safe }}</div>
</body>
</html>
"""

dashboard_html = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lelestari - Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #008DD8, #00C4FF, #FFFFFF, #F8C87A, #E5AD5D);
            min-height: 100vh;
            color: #333;
            display: flex;
            overflow-x: hidden;
        }

        /* Sidebar Styles */
        .sidebar {
            width: 280px;
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            height: 100vh;
            position: fixed;
            left: -280px;
            top: 0;
            transition: left 0.3s ease;
            z-index: 1001;
            box-shadow: 5px 0 25px rgba(0, 0, 0, 0.1);
            border-right: 1px solid rgba(255, 255, 255, 0.2);
            /* ✅ PERBAIKAN: Flexbox untuk layout yang lebih baik */
            display: flex;
            flex-direction: column;
        }

        .sidebar.active {
            left: 0;
        }

        .sidebar-header {
            padding: 25px;
            border-bottom: 1px solid #eee;
            background: linear-gradient(135deg, #008DD8, #00C4FF);
            color: white;
            /* ✅ PERBAIKAN: Header tidak ikut scroll */
            flex-shrink: 0;
        }

        .sidebar-nav {
            padding: 20px 0;
            /* ✅ PERBAIKAN: Scrollable area */
            flex: 1;
            overflow-y: auto;
            max-height: calc(100vh - 80px); /* Sesuaikan dengan tinggi header */
        }

        /* ✅ PERBAIKAN: Style untuk scrollbar yang lebih baik */
        .sidebar-nav::-webkit-scrollbar {
            width: 6px;
        }

        .sidebar-nav::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.05);
            border-radius: 3px;
        }

        .sidebar-nav::-webkit-scrollbar-thumb {
            background: rgba(0, 141, 216, 0.3);
            border-radius: 3px;
        }

        .sidebar-nav::-webkit-scrollbar-thumb:hover {
            background: rgba(0, 141, 216, 0.5);
        }

        /* Style untuk nav items (tetap sama) */
        .nav-item {
            display: flex;
            align-items: center;
            padding: 15px 25px;
            color: #333;
            text-decoration: none;
            transition: all 0.3s ease;
            border-left: 4px solid transparent;
            cursor: pointer;
        }

        .nav-item:hover {
            background: rgba(0, 141, 216, 0.1);
            border-left-color: #008DD8;
            color: #008DD8;
        }

        .nav-item.active {
            background: rgba(0, 141, 216, 0.15);
            border-left-color: #008DD8;
            color: #008DD8;
            font-weight: 600;
        }

        .nav-icon {
            margin-right: 15px;
            font-size: 18px;
            width: 20px;
            text-align: center;
        }

        /* Main Content */
        .main-content {
            flex: 1;
            transition: all 0.3s ease;
            min-height: 100vh;
            width: 100%;
        }

        .main-content.sidebar-open {
            margin-left: 0;
        }

        /* Header Styles */
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 15px 30px;
            box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            z-index: 999;
        }

        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .menu-toggle {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #008DD8;
            padding: 5px;
            border-radius: 5px;
            transition: background 0.3s ease;
            z-index: 1002;
            position: relative;
        }

        .menu-toggle:hover {
            background: rgba(0, 141, 216, 0.1);
        }

        .logo-section h1 {
            color: #008DD8;
            font-size: 24px;
            font-weight: 700;
        }

        .logo-section p {
            color: #666;
            font-size: 12px;
        }

        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .user-details {
            text-align: right;
        }

        .user-name {
            font-weight: 700;
            color: #008DD8;
            font-size: 14px;
        }

        .user-email {
            font-weight: 600;
            color: #666;
            font-size: 12px;
        }

        .user-id {
            font-size: 11px;
            color: #888;
        }

        .btn-logout {
            background: linear-gradient(135deg, #008DD8, #00C4FF);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
        }

        .btn-logout:hover {
            transform: translateY(-1px);
            box-shadow: 0 3px 10px rgba(0, 141, 216, 0.3);
        }

        /* Content Area */
        .content-area {
            padding: 30px;
            position: relative;
            z-index: 1;
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            text-align: center;
            transition: transform 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-2px);
        }

        .stat-card h3 {
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }

        .stat-value {
            font-size: 28px;
            font-weight: 700;
            color: #008DD8;
            margin-bottom: 8px;
        }

        .stat-note {
            font-size: 12px;
            color: #888;
        }

        /* Welcome Section */
        .welcome-section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            text-align: center;
        }

        .welcome-section h2 {
            color: #008DD8;
            font-size: 24px;
            margin-bottom: 10px;
        }

        .welcome-message {
            color: #666;
            line-height: 1.6;
            font-size: 16px;
            margin-bottom: 15px;
        }

        /* Quick Actions */
        .quick-actions {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            margin-bottom: 25px;
        }

        .quick-actions h2 {
            color: #008DD8;
            font-size: 20px;
            margin-bottom: 20px;
        }

        .actions-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
        }

        .action-card {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            text-decoration: none;
            color: #333;
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.3);
            display: block;
        }

        .action-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
            background: linear-gradient(135deg, #008DD8 0%, #00C4FF 100%);
            color: white;
            text-decoration: none;
        }

        .action-icon {
            font-size: 32px;
            margin-bottom: 12px;
        }

        .action-title {
            font-size: 14px;
            font-weight: 600;
        }

    </style>
</head>
<body>
    <!-- Sidebar Navigation -->
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h2>🌿 Lelestari Menu</h2>
        </div>
        <div class="sidebar-nav">
            <a href="/dashboard" class="nav-item active">
                <span class="nav-icon">📊</span>
                <span>Dashboard</span>
            </a>
            
            <!-- HANYA TAMPIL UNTUK ADMIN & SUPER ADMIN -->
            {% if user_role in ['admin', 'super_admin'] %}
            <a href="/chart_of_account" class="nav-item">
                <span class="nav-icon">📶</span>
                <span>Chart of Account</span>
            </a>
            <a href="/neraca_saldo_awal" class="nav-item">
                <span class="nav-icon">💰</span>
                <span>Neraca Saldo Awal</span>
            </a>
            <a href="/input_transaksi" class="nav-item">
                <span class="nav-icon">📝</span>
                <span>Input Transaksi</span>
            </a>
            <a href="/jurnal_umum" class="nav-item">
                <span class="nav-icon">📋</span>
                <span>Jurnal Umum</span>
            </a>
            <a href="/buku_besar" class="nav-item">
                <span class="nav-icon">📒</span>
                <span>Buku Besar</span>   
            </a>
            <a href="/nssp" class="nav-item">
                <span class="nav-icon">🗂️</span>
                <span>Neraca Saldo Sebelum Penyesuaian</span>    
            </a>
            <a href="/jurnal_penyesuaian" class="nav-item">
                <span class="nav-icon">📝</span>
                <span>Jurnal Penyesuaian</span>
            </a>    
            <a href="/neraca_saldo_setelah_penyesuaian" class="nav-item">
                <span class="nav-icon">🗃️</span>
                <span>Neraca Saldo setelah Penyesuaian</span>    
            </a>
            <a href="/neraca_lajur" class="nav-item">
                <span class="nav-icon">📋</span>
                <span>Neraca Lajur</span>    
            </a>
            <a href="/laporan_laba_rugi" class="nav-item">
                <span class="nav-icon">📈</span>
                <span>Laporan Laba Rugi</span>    
            </a>
            <a href="/laporan_perubahan_modal" class="nav-item">
                <span class="nav-icon">📊</span>
                <span>Laporan Perubahan Modal</span>    
            </a>
            <a href="/laporan_posisi_keuangan" class="nav-item">
                <span class="nav-icon">💰</span>
                <span>Laporan Posisi Keuangan</span>    
            </a>
            <a href="/laporan_arus_kas" class="nav-item">
                <span class="nav-icon">💸</span>
                <span>Laporan Arus Kas</span>    
            </a>
            <a href="/jurnal_penutup" class="nav-item">
                <span class="nav-icon">📒</span>
                <span>Jurnal Penutup</span>
            </a>
            <a href="/neraca_saldo_setelah_penutup" class="nav-item">
                <span class="nav-icon">📊</span>
                <span>Neraca Saldo setelah Penutup</span>    
            </a>

            {% endif %}
            
            <!-- HANYA TAMPIL UNTUK SUPER ADMIN -->
            {% if user_role == 'super_admin' %}
            <a href="/admin/users" class="nav-item">
                <span class="nav-icon">👑</span>
                <span>Admin Panel</span>
            </a>
            {% endif %}
        </div>
    </div>

    <!-- Overlay -->
    <div class="overlay" id="overlay"></div>

    <!-- Main Content -->
    <div class="main-content" id="mainContent">
        <!-- Header -->
        <div class="header">
            <div class="header-content">
                <div class="header-left">
                    <button class="menu-toggle" id="menuToggle">☰</button>
                    <div class="logo-section">
                        <h1>Lelestari's Dashboard</h1>
                        <p>Management System for Your Business</p>
                    </div>
                </div>
                <div class="user-info">
                    <div class="user-details">
                        <div class="user-name">{{ user_name }}</div>
                        <div class="user-email">{{ user_email }}</div>
                        <div class="user-id">Role: {{ user_role }} | ID: {{ user_id }}</div>
                    </div>
                    <a href="/logout" class="btn-logout">Log out</a>
                </div>
            </div>
        </div>

        <!-- Content Area -->
        <div class="content-area">
            {{ content|safe }}
        </div>
    </div>

    <script>
        // Sidebar Toggle Functionality
        document.addEventListener('DOMContentLoaded', function() {
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('overlay');
            const menuToggle = document.getElementById('menuToggle');
            const mainContent = document.getElementById('mainContent');

            function toggleSidebar() {
                sidebar.classList.toggle('active');
                overlay.classList.toggle('active');
                mainContent.classList.toggle('sidebar-open');
            }

            if (menuToggle) {
                menuToggle.addEventListener('click', function(e) {
                    e.stopPropagation();
                    toggleSidebar();
                });
            }

            if (overlay) {
                overlay.addEventListener('click', toggleSidebar);
            }

            // Close sidebar when clicking on nav items (mobile)
            document.querySelectorAll('.nav-item').forEach(item => {
                item.addEventListener('click', () => {
                    if (window.innerWidth <= 768) {
                        toggleSidebar();
                    }
                });
            });

            // Add fade-in animation to elements
            const elements = document.querySelectorAll('.stat-card, .action-card');
            elements.forEach((element, index) => {
                element.style.animationDelay = (index * 0.1) + 's';
                element.classList.add('fade-in');
            });

            // Handle escape key to close sidebar
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && sidebar.classList.contains('active')) {
                    toggleSidebar();
                }
            });

            // Close sidebar when clicking outside on desktop
            document.addEventListener('click', (e) => {
                if (window.innerWidth > 768 && 
                    sidebar.classList.contains('active') && 
                    !sidebar.contains(e.target) && 
                    e.target !== menuToggle) {
                    toggleSidebar();
                }
            });
        });
    </script>
</body>
</html>
"""

# ============================================================
# 📊 6. CHART OF ACCOUNT
# ============================================================

@app.route("/chart_of_account")
@admin_required
def chart_of_account():
    """Halaman Chart of Account untuk admin dan super admin"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil data Chart of Account dari database
    accounts = get_chart_of_accounts()
    
    # Kelompokkan akun berdasarkan kategori
    accounts_by_category = {}
    for account in accounts:
        category = account.get('category', 'Other')
        if category not in accounts_by_category:
            accounts_by_category[category] = []
        accounts_by_category[category].append(account)
    
    # Generate HTML untuk Chart of Account
    chart_html = ""
    for category, category_accounts in accounts_by_category.items():
        chart_html += f"""
        <div class="account-category">
            <h3 style="background: #2c3e50; color: white; padding: 10px; border-radius: 5px; margin: 20px 0 10px 0;">
                {category.upper()}
            </h3>
            <div class="account-list">
        """
        
        for account in category_accounts:
            chart_html += f"""
            <div class="account-item" id="account-{account['account_code']}">
                <span class="account-code">{account['account_code']}</span>
                <span class="account-name">{account['account_name']}</span>
                <div class="account-actions">
                    <button class="btn-danger btn-small" onclick="deleteAccount('{account['account_code']}')" title="Hapus Akun">
                        🗑️
                    </button>
                </div>
            </div>
            """
        
        chart_html += "</div></div>"
    
    content = f"""
    <div class="welcome-section">
        <h2>📊 Chart of Account</h2>
        <div class="welcome-message">
            Daftar lengkap kode akun untuk sistem akuntansi Lelestari. Digunakan untuk transaksi dan pelaporan keuangan.
        </div>
    </div>

    <div class="quick-actions">
        <h2>Kelola Chart of Account</h2>
        <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1); margin-bottom: 25px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h3>➕ Tambah Akun Baru</h3>
                    <form id="addAccountForm" onsubmit="addAccount(event)">
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Kode Akun</label>
                            <input type="text" id="accountCode" placeholder="Contoh: 1-1100" required 
                                   style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                        </div>
                        
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Nama Akun</label>
                            <input type="text" id="accountName" placeholder="Contoh: Kas Kecil" required 
                                   style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                        </div>
                        
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Tipe Akun</label>
                            <select id="accountType" required style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                                <option value="">Pilih Tipe Akun</option>
                                <option value="Aktiva Lancar">Aktiva Lancar</option>
                                <option value="Aktiva Tetap">Aktiva Tetap</option>
                                <option value="Aktiva Lainnya">Aktiva Lainnya</option>
                                <option value="Kewajiban">Kewajiban</option>
                                <option value="Modal">Modal</option>
                                <option value="Pendapatan">Pendapatan</option>
                                <option value="Beban">Beban</option>
                            </select>
                        </div>
                        
                        <div style="margin-bottom: 15px;">
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Kategori</label>
                            <select id="accountCategory" required style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                                <option value="">Pilih Kategori</option>
                                <option value="Current Assets">Current Assets</option>
                                <option value="Fixed Assets">Fixed Assets</option>
                                <option value="Other Assets">Other Assets</option>
                                <option value="Current Liabilities">Current Liabilities</option>
                                <option value="Long-term Liabilities">Long-term Liabilities</option>
                                <option value="Equity">Equity</option>
                                <option value="Revenue">Revenue</option>
                                <option value="Cost of Goods Sold">Cost of Goods Sold</option>
                                <option value="Operating Expense">Operating Expense</option>
                                <option value="Other Revenue">Other Revenue</option>
                                <option value="Other Expense">Other Expense</option>
                            </select>
                        </div>
                        
                        <button type="submit" class="btn-success" style="width: 100%;">
                            💾 Tambah Akun
                        </button>
                    </form>
                </div>
                
                <div>
                    <h3>📋 Struktur Kode Akun</h3>
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                        <div class="account-structure">
                            <div class="structure-item">
                                <span class="structure-code">1-XXXX</span>
                                <span class="structure-desc">AKTIVA</span>
                            </div>
                            <div class="structure-item">
                                <span class="structure-code">2-XXXX</span>
                                <span class="structure-desc">KEWAJIBAN</span>
                            </div>
                            <div class="structure-item">
                                <span class="structure-code">3-XXXX</span>
                                <span class="structure-desc">MODAL</span>
                            </div>
                            <div class="structure-item">
                                <span class="structure-code">4-XXXX</span>
                                <span class="structure-desc">PENDAPATAN</span>
                            </div>
                            <div class="structure-item">
                                <span class="structure-code">5-XXXX</span>
                                <span class="structure-desc">BEBAN</span>
                            </div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #e7f3ff; border-radius: 8px;">
                        <h4>💡 Informasi Penting</h4>
                        <ul style="text-align: left; padding-left: 20px; font-size: 14px;">
                            <li>Chart of Account digunakan untuk pencatatan transaksi akuntansi</li>
                            <li>Setiap transaksi harus menggunakan kode akun yang sesuai</li>
                            <li>Kode akun tidak boleh duplikat</li>
                            <li>Hanya admin yang bisa menambah/hapus akun</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="quick-actions">
        <h2>Daftar Akun</h2>
        <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
            <div style="max-height: 600px; overflow-y: auto;">
                {chart_html if chart_html else '<p style="text-align: center; padding: 20px;">Belum ada data akun</p>'}
            </div>
        </div>
    </div>

    <style>
        .account-category {{
            margin-bottom: 30px;
        }}
        
        .account-list {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
        }}
        
        .account-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 15px;
            margin: 8px 0;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #3498db;
            transition: all 0.3s ease;
        }}
        
        .account-item:hover {{
            background: #e3f2fd;
            transform: translateX(5px);
        }}
        
        .account-code {{
            font-weight: bold;
            color: #2c3e50;
            min-width: 80px;
            font-family: 'Courier New', monospace;
        }}
        
        .account-name {{
            flex: 1;
            color: #34495e;
            margin: 0 15px;
        }}
        
        .account-actions {{
            display: flex;
            gap: 5px;
        }}
        
        .btn-small {{
            padding: 5px 10px;
            font-size: 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}
        
        .btn-danger {{
            background: #dc3545;
            color: white;
        }}
        
        .btn-danger:hover {{
            background: #c82333;
        }}
        
        .account-structure {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        
        .structure-item {{
            display: flex;
            justify-content: space-between;
            padding: 10px;
            background: white;
            border-radius: 5px;
            border-left: 3px solid #008DD8;
        }}
        
        .structure-code {{
            font-weight: bold;
            color: #008DD8;
            font-family: 'Courier New', monospace;
        }}
        
        .structure-desc {{
            color: #666;
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > div {{
                grid-template-columns: 1fr;
            }}
            
            .account-item {{
                flex-direction: column;
                align-items: start;
                gap: 10px;
            }}
            
            .account-actions {{
                align-self: end;
            }}
        }}
    </style>

    <script>
        function addAccount(event) {{
            event.preventDefault();
            
            const accountCode = document.getElementById('accountCode').value;
            const accountName = document.getElementById('accountName').value;
            const accountType = document.getElementById('accountType').value;
            const accountCategory = document.getElementById('accountCategory').value;
            
            if (!accountCode || !accountName || !accountType || !accountCategory) {{
                alert('Harap lengkapi semua field!');
                return;
            }}
            
            // Validasi format kode akun
            if (!/^[1-9]-[0-9]{{4}}$/.test(accountCode)) {{
                alert('Format kode akun tidak valid! Gunakan format: X-XXXX (contoh: 1-1100)');
                return;
            }}
            
            fetch('/api/add_account', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    account_code: accountCode,
                    account_name: accountName,
                    account_type: accountType,
                    category: accountCategory
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Akun berhasil ditambahkan!');
                    location.reload();
                }} else {{
                    alert('Error: ' + data.message);
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
                alert('Terjadi kesalahan saat menambah akun');
            }});
        }}
        
        function deleteAccount(accountCode) {{
            if (confirm(`Apakah Anda yakin ingin menghapus akun ${{accountCode}}?`)) {{
                fetch('/api/delete_account', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        account_code: accountCode
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Akun berhasil dihapus!');
                        location.reload();
                    }} else {{
                        alert('Error: ' + data.message);
                    }}
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Terjadi kesalahan saat menghapus akun');
                }});
            }}
        }}
        
        // Auto-fill category based on account type
        document.getElementById('accountType').addEventListener('change', function() {{
            const type = this.value;
            const categorySelect = document.getElementById('accountCategory');
            
            // Clear previous selection
            categorySelect.value = '';
            
            // Map account type to category
            const typeToCategory = {{
                'Aktiva Lancar': 'Current Assets',
                'Aktiva Tetap': 'Fixed Assets',
                'Aktiva Lainnya': 'Other Assets',
                'Kewajiban': 'Current Liabilities',
                'Modal': 'Equity',
                'Pendapatan': 'Revenue',
                'Beban': 'Operating Expense'
            }};
            
            if (typeToCategory[type]) {{
                categorySelect.value = typeToCategory[type];
            }}
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 📖 FUNGSI DATA CHART OF ACCOUNT & REFERENSI
# ============================================================
def get_account_name(account_code):
    """Dapatkan nama akun berdasarkan kode"""
    try:
        result = supabase.table("chart_of_accounts").select("account_name").eq("account_code", account_code).execute()
        if result.data:
            return result.data[0].get('account_name', account_code)
        return account_code
    except Exception as e:
        logger.error(f"❌ Error getting account name: {e}")
        return account_code

def get_chart_of_accounts():
    """Ambil data Chart of Account dari database"""
    try:
        result = supabase.table("chart_of_accounts").select("*").order("account_code").execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"❌ Error getting chart of accounts: {e}")
        return []
    
def get_account_by_code(account_code):
    """Ambil data akun berdasarkan kode"""
    try:
        result = supabase.table("chart_of_accounts").select("*").eq("account_code", account_code).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"❌ Error getting account by code: {e}")
        return None

def add_account_to_chart(account_data):
    """Tambah akun baru ke Chart of Account"""
    try:
        # Cek apakah kode akun sudah ada
        existing = supabase.table("chart_of_accounts").select("account_code").eq("account_code", account_data['account_code']).execute()
        if existing.data:
            return {"success": False, "message": "Kode akun sudah ada"}
        
        result = supabase.table("chart_of_accounts").insert(account_data).execute()
        if result.data:
            logger.info(f"✅ Account added: {account_data['account_code']} - {account_data['account_name']}")
            return {"success": True, "message": "Akun berhasil ditambahkan"}
        else:
            return {"success": False, "message": "Gagal menambahkan akun"}
    except Exception as e:
        logger.error(f"❌ Error adding account: {e}")
        return {"success": False, "message": str(e)}

def delete_account_from_chart(account_code):
    """Hapus akun dari Chart of Account"""
    try:
        result = supabase.table("chart_of_accounts").delete().eq("account_code", account_code).execute()
        if result.data:
            logger.info(f"✅ Account deleted: {account_code}")
            return {"success": True, "message": "Akun berhasil dihapus"}
        else:
            return {"success": False, "message": "Gagal menghapus akun"}
    except Exception as e:
        logger.error(f"❌ Error deleting account: {e}")
        return {"success": False, "message": str(e)}

def initialize_chart_of_accounts():
    """Inisialisasi data Chart of Account default"""
    try:
        # Cek apakah data sudah ada
        existing = supabase.table("chart_of_accounts").select("account_code").limit(1).execute()
        if existing.data:
            logger.info("✅ Chart of Accounts already initialized")
            return
        
        # Data Chart of Account default
        default_accounts = [
            # AKTIVA LANCAR (CURRENT ASSETS)
            {"account_code": "1-1100", "account_name": "Kas Kecil", "account_type": "Aktiva Lancar", "category": "Current Assets"},
            {"account_code": "1-1101", "account_name": "Kas Kecil di OVO", "account_type": "Aktiva Lancar", "category": "Current Assets"},
            {"account_code": "1-1104", "account_name": "Kas di Bank BCA", "account_type": "Aktiva Lancar", "category": "Current Assets"},
            {"account_code": "1-1300", "account_name": "Piutang Usaha", "account_type": "Aktiva Lancar", "category": "Current Assets"},
            {"account_code": "1-1500", "account_name": "Persediaan Barang Dagang", "account_type": "Aktiva Lancar", "category": "Current Assets"},
            
            # AKTIVA TETAP (FIXED ASSETS)
            {"account_code": "1-2100", "account_name": "Tanah", "account_type": "Aktiva Tetap", "category": "Fixed Assets"},
            {"account_code": "1-2200", "account_name": "Gedung", "account_type": "Aktiva Tetap", "category": "Fixed Assets"},
            {"account_code": "1-2300", "account_name": "Mesin & Peralatan", "account_type": "Aktiva Tetap", "category": "Fixed Assets"},
            
            # KEWAJIBAN (LIABILITIES)
            {"account_code": "2-1100", "account_name": "Utang Usaha", "account_type": "Kewajiban", "category": "Current Liabilities"},
            {"account_code": "2-1200", "account_name": "Utang Gaji", "account_type": "Kewajiban", "category": "Current Liabilities"},
            
            # MODAL (EQUITY)
            {"account_code": "3-1100", "account_name": "Modal Saham", "account_type": "Modal", "category": "Equity"},
            {"account_code": "3-1200", "account_name": "Laba Ditahan", "account_type": "Modal", "category": "Equity"},
            
            # PENDAPATAN (REVENUE)
            {"account_code": "4-1100", "account_name": "Penjualan", "account_type": "Pendapatan", "category": "Revenue"},
            
            # HARGA POKOK PENJUALAN (COST OF GOODS SOLD)
            {"account_code": "5-1100", "account_name": "Harga Pokok Penjualan", "account_type": "Beban", "category": "Cost of Goods Sold"},
            
            # BEBAN OPERASIONAL (OPERATING EXPENSE)
            {"account_code": "6-1100", "account_name": "Beban Gaji", "account_type": "Beban", "category": "Operating Expense"},
            {"account_code": "6-1200", "account_name": "Beban Listrik", "account_type": "Beban", "category": "Operating Expense"},
        ]
        
        # Insert data ke database
        result = supabase.table("chart_of_accounts").insert(default_accounts).execute()
        logger.info(f"✅ Chart of Accounts initialized with {len(default_accounts)} accounts")
        
    except Exception as e:
        logger.error(f"❌ Error initializing chart of accounts: {e}")

# ============================================================
# 💰 7. NERACA SALDO AWAL
# ============================================================

@app.route("/neraca_saldo_awal")
@admin_required
def neraca_saldo_awal():
    """Halaman untuk mengelola neraca saldo awal"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil data neraca saldo awal
    opening_balances = get_opening_balances_with_account_info()
    total_summary = calculate_total_opening_balances()
    
    # Ambil data Chart of Account untuk dropdown
    accounts = get_chart_of_accounts()
    account_options = ""
    for account in accounts:
        account_options += f'<option value="{account["account_code"]}">{account["account_code"]} - {account["account_name"]}</option>'
    
    # Generate tabel neraca saldo awal TANPA KOLOM POSISI
    balances_html = ""
    if opening_balances:
        for balance in opening_balances:
            # Tampilkan nilai di kolom yang sesuai - TANPA POSISI
            debit_value = format_currency(balance['amount']) if balance['position'] == 'debit' else "-"
            credit_value = format_currency(balance['amount']) if balance['position'] == 'kredit' else "-"
            
            balances_html += f"""
            <tr>
                <td style="padding: 12px; border: 1px solid #dee2e6; text-align: center; font-weight: bold;">
                    {balance['account_code']}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">
                    {balance['account_name']}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; font-weight: bold; color: #dc3545;">
                    {debit_value}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; font-weight: bold; color: #28a745;">
                    {credit_value}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6;">
                    {balance['description'] or '-'}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6; text-align: center;">
                    <button onclick="deleteOpeningBalance({balance['id']})" 
                            style="background: #dc3545; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;">
                        🗑️ Hapus
                    </button>
                </td>
            </tr>
            """
    else:
        balances_html = """
        <tr>
            <td colspan="6" style="padding: 40px; text-align: center; color: #666;">
                <div style="font-size: 48px; margin-bottom: 20px;">💰</div>
                <h3>Belum Ada Data Neraca Saldo Awal</h3>
                <p>Tambahkan saldo awal untuk akun-akun yang diperlukan</p>
            </td>
        </tr>
        """
    
    # Summary section
    summary_html = f"""
    <div style="background: #e9ecef; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; text-align: center;">
            <div>
                <div style="font-size: 14px; color: #666; margin-bottom: 5px;">Total Debit</div>
                <div style="font-size: 24px; font-weight: bold; color: #dc3545;">{format_currency(total_summary['total_debit'])}</div>
            </div>
            <div>
                <div style="font-size: 14px; color: #666; margin-bottom: 5px;">Total Kredit</div>
                <div style="font-size: 24px; font-weight: bold; color: #28a745;">{format_currency(total_summary['total_credit'])}</div>
            </div>
            <div>
                <div style="font-size: 14px; color: #666; margin-bottom: 5px;">Status</div>
                <div style="font-size: 18px; font-weight: bold; color: {'#28a745' if total_summary['is_balanced'] else '#dc3545'}; 
                     background: {'#d4edda' if total_summary['is_balanced'] else '#f8d7da'}; 
                     padding: 8px; border-radius: 5px;">
                    {'✅ SEIMBANG' if total_summary['is_balanced'] else '❌ TIDAK SEIMBANG'}
                </div>
                {f'<div style="font-size: 12px; color: #dc3545; margin-top: 5px;">Selisih: {format_currency(total_summary["difference"])}</div>' if not total_summary['is_balanced'] else ''}
            </div>
        </div>
    </div>
    """
    
    content = f"""
    <div class="welcome-section">
        <h2>💰 Neraca Saldo Awal</h2>
        <div class="welcome-message">
            Kelola saldo awal untuk setiap akun sebelum memulai pencatatan transaksi. 
            Saldo awal ini akan terintegrasi dengan buku besar sebagai titik mulai perhitungan.
        </div>
    </div>

    {summary_html}

    <div class="quick-actions">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
            <!-- Form Input Saldo Awal -->
            <div>
                <h3>➕ Tambah Saldo Awal</h3>
                <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
                    <form id="openingBalanceForm">
                        <div style="margin-bottom: 20px;">
                            <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #333;">Akun</label>
                            <select id="accountCode" required 
                                    style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 14px;">
                                <option value="">Pilih Akun</option>
                                {account_options}
                            </select>
                        </div>
                        
                        <div style="margin-bottom: 20px;">
                            <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #333;">Posisi</label>
                            <select id="position" required 
                                    style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 14px;">
                                <option value="">Pilih Posisi</option>
                                <option value="debit">Debit</option>
                                <option value="kredit">Kredit</option>
                            </select>
                        </div>
                        
                        <div style="margin-bottom: 20px;">
                            <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #333;">Nominal (Rp)</label>
                            <input type="number" id="amount" required min="1" step="1"
                                   placeholder="Masukkan nominal saldo awal"
                                   style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 14px;">
                        </div>
                        
                        <div style="margin-bottom: 25px;">
                            <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #333;">Keterangan (Opsional)</label>
                            <textarea id="description" rows="3"
                                      placeholder="Deskripsi saldo awal..."
                                      style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 14px; resize: vertical;"></textarea>
                        </div>
                        
                        <button type="button" onclick="addOpeningBalance()" 
                                style="background: #28a745; color: white; border: none; padding: 15px 30px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%;">
                            💾 Simpan Saldo Awal
                        </button>
                    </form>
                </div>
            </div>
            
            <!-- Informasi Panduan -->
            <div>
                <h3>💡 Panduan Neraca Saldo Awal</h3>
                <div style="background: #e7f3ff; padding: 20px; border-radius: 8px;">
                    <h4 style="color: #008DD8; margin-bottom: 15px;">📋 Aturan Saldo Awal</h4>
                    <ul style="text-align: left; color: #666; line-height: 1.6;">
                        <li><strong>Akun Debit Normal:</strong> Aktiva Lancar, Aktiva Tetap, Beban</li>
                        <li><strong>Akun Kredit Normal:</strong> Kewajiban, Modal, Pendapatan</li>
                        <li><strong>Saldo Debit:</strong> Untuk akun dengan saldo normal debit</li>
                        <li><strong>Saldo Kredit:</strong> Untuk akun dengan saldo normal kredit</li>
                        <li><strong>Total Debit harus sama dengan Total Kredit</strong></li>
                    </ul>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #d4edda; border-radius: 5px;">
                        <h4 style="color: #155724; margin-bottom: 10px;">✅ Contoh:</h4>
                        <p style="color: #155724; margin: 5px 0;">• Kas Kecil: <strong>Debit</strong> Rp 5.000.000</p>
                        <p style="color: #155724; margin: 5px 0;">• Modal Saham: <strong>Kredit</strong> Rp 5.000.000</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="quick-actions">
        <h3>📋 Daftar Saldo Awal</h3>
        <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #008DD8; color: white;">
                        <th style="padding: 15px; text-align: center; border: 1px solid #007bff;">Kode Akun</th>
                        <th style="padding: 15px; text-align: left; border: 1px solid #007bff;">Nama Akun</th>
                        <th style="padding: 15px; text-align: right; border: 1px solid #007bff;">Debit</th>
                        <th style="padding: 15px; text-align: right; border: 1px solid #007bff;">Kredit</th>
                        <th style="padding: 15px; text-align: left; border: 1px solid #007bff;">Keterangan</th>
                        <th style="padding: 15px; text-align: center; border: 1px solid #007bff;">Aksi</th>
                    </tr>
                </thead>
                <tbody>
                    {balances_html}
                    
                    <!-- Baris Total -->
                    <tr style="background: #e9ecef; font-weight: bold; border-top: 3px solid #008DD8;">
                        <td colspan="2" style="padding: 15px; border: 1px solid #dee2e6; text-align: center; font-size: 16px;">
                            TOTAL
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-size: 16px;">
                            {format_currency(total_summary['total_debit'])}
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-size: 16px;">
                            {format_currency(total_summary['total_credit'])}
                        </td>
                        <td colspan="2" style="padding: 15px; border: 1px solid #dee2e6;"></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > div {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
        }}
    </style>

    <script>
        function addOpeningBalance() {{
            const accountCode = document.getElementById('accountCode').value;
            const position = document.getElementById('position').value;
            const amount = parseFloat(document.getElementById('amount').value);
            const description = document.getElementById('description').value;
            
            // Validasi form
            if (!accountCode || !position || !amount || amount <= 0) {{
                alert('Harap lengkapi semua field dengan data yang valid!');
                return;
            }}
            
            // Tampilkan loading
            const button = event.target;
            const originalText = button.textContent;
            button.textContent = 'Menyimpan...';
            button.disabled = true;
            
            // Kirim data ke server
            fetch('/api/add_opening_balance', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    account_code: accountCode,
                    position: position,
                    amount: amount,
                    description: description
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Saldo awal berhasil disimpan!');
                    // Reset form
                    document.getElementById('openingBalanceForm').reset();
                    // Reload halaman
                    location.reload();
                }} else {{
                    alert('Error: ' + data.message);
                    // Reset button
                    button.textContent = originalText;
                    button.disabled = false;
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
                alert('Terjadi kesalahan saat menyimpan saldo awal');
                // Reset button
                button.textContent = originalText;
                button.disabled = false;
            }});
        }}
        
        function deleteOpeningBalance(balanceId) {{
            if (confirm('Apakah Anda yakin ingin menghapus saldo awal ini?')) {{
                fetch('/api/delete_opening_balance', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        balance_id: balanceId
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Saldo awal berhasil dihapus!');
                        location.reload();
                    }} else {{
                        alert('Error: ' + data.message);
                    }}
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Terjadi kesalahan saat menghapus saldo awal');
                }});
            }}
        }}
        
        // Auto-focus pada input amount
        document.addEventListener('DOMContentLoaded', function() {{
            document.getElementById('amount').focus();
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 🔹 FUNGSI NERACA SALDO AWAL
# ============================================================

def get_opening_balances():
    """Ambil data neraca saldo awal"""
    try:
        result = supabase.table("opening_balances").select("*, chart_of_accounts(account_name, account_type)").order("created_at").execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"❌ Error getting opening balances: {e}")
        return []

def get_opening_balance_by_account(account_code):
    """Ambil saldo awal untuk akun tertentu"""
    try:
        result = supabase.table("opening_balances").select("*").eq("account_code", account_code).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"❌ Error getting opening balance for {account_code}: {e}")
        return None

def add_opening_balance(account_code, position, amount, description=""):
    """Tambah saldo awal"""
    try:
        # Cek apakah sudah ada saldo untuk akun ini
        existing = get_opening_balance_by_account(account_code)
        
        balance_data = {
            "account_code": account_code,
            "position": position,
            "amount": amount,
            "description": description,
            "created_by": session.get('user_name', 'Admin'),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if existing:
            # Update saldo yang sudah ada
            result = supabase.table("opening_balances").update(balance_data).eq("account_code", account_code).execute()
            action = "updated"
        else:
            # Tambah saldo baru
            result = supabase.table("opening_balances").insert(balance_data).execute()
            action = "added"
        
        if result.data:
            logger.info(f"✅ Opening balance {action} for account {account_code}: {position} {amount}")
            return {"success": True, "message": f"Saldo awal berhasil {'diupdate' if existing else 'ditambahkan'}"}
        else:
            return {"success": False, "message": "Gagal menyimpan saldo awal"}
            
    except Exception as e:
        logger.error(f"❌ Error adding opening balance: {e}")
        return {"success": False, "message": str(e)}

def delete_opening_balance(balance_id):
    """Hapus saldo awal"""
    try:
        result = supabase.table("opening_balances").delete().eq("id", balance_id).execute()
        if result.data:
            logger.info(f"✅ Opening balance {balance_id} deleted")
            return {"success": True, "message": "Saldo awal berhasil dihapus"}
        else:
            return {"success": False, "message": "Gagal menghapus saldo awal"}
    except Exception as e:
        logger.error(f"❌ Error deleting opening balance: {e}")
        return {"success": False, "message": str(e)}

def get_opening_balances_with_account_info():
    """Ambil data neraca saldo awal dengan informasi akun lengkap"""
    try:
        result = supabase.table("opening_balances").select("*, chart_of_accounts(account_name, account_type, category)").execute()
        
        balances = []
        if result.data:
            for balance in result.data:
                account_info = balance.get('chart_of_accounts', {})
                balances.append({
                    'id': balance['id'],
                    'account_code': balance['account_code'],
                    'account_name': account_info.get('account_name', 'Unknown Account'),
                    'account_type': account_info.get('account_type', 'Unknown'),
                    'position': balance['position'],
                    'amount': balance['amount'],
                    'description': balance.get('description', ''),
                    'created_at': balance.get('created_at', ''),
                    'created_by': balance.get('created_by', 'Admin')
                })
        
        return balances
    except Exception as e:
        logger.error(f"❌ Error getting opening balances with account info: {e}")
        return []

def calculate_total_opening_balances():
    """Hitung total debit dan kredit dari neraca saldo awal"""
    try:
        balances = get_opening_balances()
        
        total_debit = sum(balance['amount'] for balance in balances if balance['position'] == 'debit')
        total_credit = sum(balance['amount'] for balance in balances if balance['position'] == 'kredit')
        
        return {
            'total_debit': total_debit,
            'total_credit': total_credit,
            'is_balanced': total_debit == total_credit,
            'difference': abs(total_debit - total_credit)
        }
    except Exception as e:
        logger.error(f"❌ Error calculating opening balances total: {e}")
        return {'total_debit': 0, 'total_credit': 0, 'is_balanced': False, 'difference': 0}

# ============================================================
# 📝 8. INPUT TRANSAKSI
# ============================================================

@app.route("/input_transaksi")
@admin_required
def input_transaksi():
    """Halaman input transaksi untuk jurnal umum"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil data Chart of Account untuk dropdown
    accounts = get_chart_of_accounts()
    
    # Generate options untuk dropdown akun
    account_options = ""
    for account in accounts:
        account_options += f'<option value="{account["account_code"]}">{account["account_code"]} - {account["account_name"]}</option>'
    
    content = f"""
    <div class="welcome-section">
        <h2>📝 Input Transaksi</h2>
        <div class="welcome-message">
            Input transaksi keuangan untuk pencatatan jurnal umum. Transaksi ini akan digunakan untuk perhitungan HPP dan laporan keuangan.
        </div>
    </div>

    <div class="quick-actions">
        <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
            <form id="transactionForm">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; margin-bottom: 5px; font-weight: 600;">📅 Tanggal Transaksi</label>
                        <input type="date" id="transactionDate" required 
                               value="{date.today().isoformat()}"
                               style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                    </div>
                    
                    <div>
                        <label style="display: block; margin-bottom: 5px; font-weight: 600;">📋 Keterangan Transaksi</label>
                        <input type="text" id="transactionDesc" placeholder="Contoh: Pembelian bibit lele" required 
                               style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600;">💳 Detail Akun Transaksi</label>
                    <div id="accountEntries">
                        <!-- Entries akan ditambahkan dinamis di sini -->
                    </div>
                    
                    <button type="button" onclick="addAccountEntry()" 
                            style="background: #28a745; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; margin-top: 10px;">
                        ➕ Tambah Akun
                    </button>
                </div>

                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <h4>⚖️ Balance Check</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div>
                            <strong>Total Debit:</strong>
                            <div id="totalDebit" style="font-size: 18px; color: #dc3545; font-weight: bold;">Rp 0</div>
                        </div>
                        <div>
                            <strong>Total Kredit:</strong>
                            <div id="totalCredit" style="font-size: 18px; color: #28a745; font-weight: bold;">Rp 0</div>
                        </div>
                    </div>
                    <div id="balanceStatus" style="margin-top: 10px; font-weight: bold;"></div>
                </div>

                <button type="button" onclick="submitTransaction()" 
                        style="background: #008DD8; color: white; border: none; padding: 12px 30px; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%;">
                    💾 Simpan Transaksi
                </button>
            </form>
        </div>
    </div>

    <style>
        .account-entry {{
            display: grid;
            grid-template-columns: 100px 1fr 120px 120px 60px;
            gap: 10px;
            padding: 15px;
            margin: 10px 0;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #e9ecef;
            align-items: center;
        }}

        .account-entry select,
        .account-entry input {{
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 5px;
            width: 100%;
        }}

        .remove-btn {{
            background: #dc3545;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px;
            cursor: pointer;
        }}

        .balance-valid {{
            color: #28a745;
            background: #d4ffd4;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }}

        .balance-invalid {{
            color: #dc3545;
            background: #ffd4d4;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }}
    </style>

    <script>
        let entryCount = 0;

        // Tambah entry akun pertama saat halaman dimuat
        document.addEventListener('DOMContentLoaded', function() {{
            addAccountEntry();
            addAccountEntry();
        }});

        function addAccountEntry() {{
            const entriesContainer = document.getElementById('accountEntries');
            const entryId = 'entry-' + entryCount;
            
            const entryHTML = `
                <div class="account-entry" id="${{entryId}}">
                    <select name="position" onchange="updateBalance()" required>
                        <option value="">Posisi</option>
                        <option value="debit">Debit</option>
                        <option value="kredit">Kredit</option>
                    </select>
                    
                    <select name="account_code" required>
                        <option value="">Pilih Akun</option>
                        {account_options}
                    </select>
                    
                    <input type="number" name="amount" placeholder="Jumlah (Rp)" min="1" 
                           onchange="updateBalance()" onkeyup="updateBalance()" required>
                    
                    <input type="text" name="note" placeholder="Keterangan">
                    
                    <button type="button" class="remove-btn" onclick="removeAccountEntry('${{entryId}}')" 
                            ${{entryCount < 2 ? 'disabled' : ''}}>🗑️</button>
                </div>
            `;
            
            entriesContainer.insertAdjacentHTML('beforeend', entryHTML);
            entryCount++;
        }}

        function removeAccountEntry(entryId) {{
            const entry = document.getElementById(entryId);
            if (entry) {{
                entry.remove();
                updateBalance();
            }}
        }}

        function updateBalance() {{
            let totalDebit = 0;
            let totalCredit = 0;
            
            // Hitung total debit dan kredit
            const entries = document.querySelectorAll('.account-entry');
            entries.forEach(entry => {{
                const position = entry.querySelector('select[name="position"]').value;
                const amount = parseFloat(entry.querySelector('input[name="amount"]').value) || 0;
                
                if (position === 'debit') {{
                    totalDebit += amount;
                }} else if (position === 'kredit') {{
                    totalCredit += amount;
                }}
            }});
            
            // Update tampilan total
            document.getElementById('totalDebit').textContent = formatCurrency(totalDebit);
            document.getElementById('totalCredit').textContent = formatCurrency(totalCredit);
            
            // Cek balance
            const balanceStatus = document.getElementById('balanceStatus');
            if (totalDebit === totalCredit && totalDebit > 0) {{
                balanceStatus.innerHTML = '<div class="balance-valid">✅ Balance: DEBIT = KREDIT</div>';
            }} else {{
                balanceStatus.innerHTML = '<div class="balance-invalid">❌ Balance: DEBIT ≠ KREDIT</div>';
            }}
        }}

        function formatCurrency(amount) {{
            return 'Rp ' + amount.toLocaleString('id-ID');
        }}

        function submitTransaction() {{
            // Validasi form
            const transactionDate = document.getElementById('transactionDate').value;
            const transactionDesc = document.getElementById('transactionDesc').value;
            
            if (!transactionDate || !transactionDesc) {{
                alert('Harap lengkapi tanggal dan keterangan transaksi!');
                return;
            }}
            
            // Kumpulkan data entries
            const entries = [];
            const entryElements = document.querySelectorAll('.account-entry');
            
            let isValid = true;
            let totalDebit = 0;
            let totalCredit = 0;
            
            entryElements.forEach((entry, index) => {{
                const position = entry.querySelector('select[name="position"]').value;
                const accountCode = entry.querySelector('select[name="account_code"]').value;
                const amount = parseFloat(entry.querySelector('input[name="amount"]').value) || 0;
                const note = entry.querySelector('input[name="note"]').value;
                
                if (!position || !accountCode || amount <= 0) {{
                    isValid = false;
                    alert(`Entry #${{index + 1}} belum lengkap!`);
                    return;
                }}
                
                if (position === 'debit') {{
                    totalDebit += amount;
                }} else {{
                    totalCredit += amount;
                }}
                
                entries.push({{
                    position: position,
                    account_code: accountCode,
                    amount: amount,
                    note: note
                }});
            }});
            
            if (!isValid) return;
            
            // Validasi balance
            if (totalDebit !== totalCredit) {{
                alert('Total Debit harus sama dengan Total Kredit!');
                return;
            }}
            
            if (entries.length < 2) {{
                alert('Transaksi harus memiliki minimal 2 akun!');
                return;
            }}
            
            // Submit data ke server
            const transactionData = {{
                transaction_date: transactionDate,
                description: transactionDesc,
                total_amount: totalDebit,
                entries: entries
            }};
            
            fetch('/api/save_transaction', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(transactionData)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Transaksi berhasil disimpan!');
                    // Reset form
                    document.getElementById('transactionForm').reset();
                    document.getElementById('accountEntries').innerHTML = '';
                    entryCount = 0;
                    addAccountEntry();
                    addAccountEntry();
                    updateBalance();
                }} else {{
                    alert('Error: ' + data.message);
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
                alert('Terjadi kesalahan saat menyimpan transaksi');
            }});
        }}
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 💰 FUNGSI TRANSAKSI JURNAL
# ============================================================

def get_journal_entries_with_details(start_date=None, end_date=None, limit=None):
    """Ambil data jurnal umum dengan detail entries - OPTIMIZED"""
    try:
        logger.info(f"🔍 Fetching journal entries with details")
        
        # ✅ PERBAIKAN 1: Query dengan JOIN untuk menghindari N+1 query
        query = supabase.table("general_journals").select("*, journal_entries(*)")
        
        if start_date and end_date and start_date != "" and end_date != "":
            query = query.gte('transaction_date', start_date).lte('transaction_date', end_date)
        
        query = query.order("transaction_date", desc=False)
        
        if limit:
            query = query.limit(limit)
            
        result = query.execute()
        journals = result.data if result.data else []
        
        logger.info(f"📊 Found {len(journals)} journals")
        
        # ✅ PERBAIKAN 2: Kurangi processing yang tidak perlu
        formatted_journals = []
        for journal in journals:
            journal_entries = journal.get('journal_entries', [])
            
            # Format minimal yang diperlukan
            formatted_journals.append({
                'id': journal['id'],
                'transaction_number': journal.get('transaction_number', ''),
                'transaction_date': journal.get('transaction_date', ''),
                'description': journal.get('description', 'Transaksi'),
                'total_amount': journal.get('total_amount', 0),
                'created_by': journal.get('created_by', 'System'),
                'journal_entries': journal_entries
            })
        
        return formatted_journals
        
    except Exception as e:
        logger.error(f"❌ Error getting journal entries: {e}")
        return []

def get_general_ledger_entries_grouped_by_account(start_date=None, end_date=None):
    """Ambil data buku besar yang dikelompokkan per akun dengan saldo running - OPTIMIZED VERSION"""
    try:
        logger.info(f"🔍 Fetching optimized ledger data - Date: {start_date} to {end_date}")
        
        # ✅ PERBAIKAN 1: Cache sederhana untuk hasil yang sama (5 menit)
        cache_key = f"ledger_{start_date}_{end_date}"
        if hasattr(app, 'ledger_cache'):
            cache_time, cached_data = app.ledger_cache.get(cache_key, (None, None))
            if cached_data and cache_time and (datetime.now() - cache_time).seconds < 300:  # Cache 5 menit
                logger.info(f"✅ Using cached ledger data (age: {(datetime.now() - cache_time).seconds}s)")
                return cached_data
        
        # ✅ PERBAIKAN 2: Query lebih efisien - single query dengan join
        # Query untuk journals dengan entries dalam satu call
        query = supabase.table("general_journals").select("*, journal_entries(*)")
        
        if start_date and end_date and start_date != "" and end_date != "":
            query = query.gte('transaction_date', start_date).lte('transaction_date', end_date)
        
        query = query.order("transaction_date", desc=False)
        journals_result = query.execute()
        journals = journals_result.data if journals_result.data else []
        
        # ✅ PERBAIKAN 3: Ambil semua data yang diperlukan sekaligus
        # Ambil chart of accounts sekali saja
        accounts_cache_key = "all_accounts_cache"
        if hasattr(app, 'accounts_cache_full'):
            cache_time, all_accounts = app.accounts_cache_full.get(accounts_cache_key, (None, None))
            if not all_accounts or not cache_time or (datetime.now() - cache_time).seconds > 300:
                all_accounts = get_chart_of_accounts()
                app.accounts_cache_full = {accounts_cache_key: (datetime.now(), all_accounts)}
        else:
            all_accounts = get_chart_of_accounts()
            app.accounts_cache_full = {accounts_cache_key: (datetime.now(), all_accounts)}
        
        if not all_accounts:
            logger.error("❌ No accounts found in Chart of Accounts")
            return []
        
        # Ambil opening balances
        opening_result = supabase.table("opening_balances").select("*").execute()
        opening_balances = opening_result.data if opening_result.data else []
        
        logger.info(f"📊 Found {len(journals)} journals, {len(all_accounts)} accounts, {len(opening_balances)} opening balances")
        
        # ✅ PERBAIKAN 4: Struktur data yang lebih efisien
        account_map = {}
        opening_map = {bal['account_code']: bal for bal in opening_balances}
        
        # Inisialisasi semua akun
        for account in all_accounts:
            account_code = account['account_code']
            account_map[account_code] = {
                'account_code': account_code,
                'account_name': account['account_name'],
                'account_type': account['account_type'],
                'entries': [],
                'total_debit': 0,
                'total_credit': 0,
                'initial_balance': 0,
                'final_balance': 0,
                'has_opening_balance': False
            }
            
            # Tambahkan opening balance jika ada
            if account_code in opening_map:
                opening = opening_map[account_code]
                amount = opening['amount']
                position = opening['position']
                
                # Set initial balance berdasarkan tipe akun
                if account['account_type'] in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
                    account_map[account_code]['initial_balance'] = amount if position == 'debit' else -amount
                else:
                    account_map[account_code]['initial_balance'] = amount if position == 'kredit' else -amount
                
                account_map[account_code]['has_opening_balance'] = True
                
                # Tambahkan entry untuk opening balance
                if amount > 0:
                    account_map[account_code]['entries'].append({
                        'date': 'SALDO AWAL',
                        'description': 'NERACA SALDO AWAL',
                        'debit': amount if position == 'debit' else 0,
                        'credit': amount if position == 'kredit' else 0,
                        'is_opening_balance': True,
                        'sort_order': 0
                    })
        
        # ✅ PERBAIKAN 5: Proses semua journals dalam satu pass
        for journal in journals:
            journal_entries = journal.get('journal_entries', [])
            if not journal_entries:
                continue
                
            transaction_date = journal.get('transaction_date', '')
            description = journal.get('description', 'Transaksi')
            
            for entry in journal_entries:
                account_code = entry.get('account_code')
                if not account_code:
                    continue
                
                # Jika akun tidak ada di map, tambahkan
                if account_code not in account_map:
                    account_map[account_code] = {
                        'account_code': account_code,
                        'account_name': get_account_name(account_code),
                        'account_type': 'Unknown',
                        'entries': [],
                        'total_debit': 0,
                        'total_credit': 0,
                        'initial_balance': 0,
                        'final_balance': 0,
                        'has_opening_balance': False
                    }
                
                amount = entry.get('amount', 0)
                if amount <= 0:
                    continue
                    
                position = entry.get('position', 'debit')
                
                # Update totals
                if position == 'debit':
                    account_map[account_code]['total_debit'] += amount
                    debit = amount
                    credit = 0
                else:
                    account_map[account_code]['total_credit'] += amount
                    debit = 0
                    credit = amount
                
                # Tambahkan entry
                account_map[account_code]['entries'].append({
                    'date': transaction_date,
                    'description': description,
                    'debit': debit,
                    'credit': credit,
                    'is_opening_balance': False,
                    'sort_order': 1,
                    'journal_id': journal.get('id'),
                    'entry_id': entry.get('id')
                })
        
        # ✅ PERBAIKAN 6: Hitung final balance dan running balance
        result = []
        for account_code, data in account_map.items():
            # Skip akun tanpa aktivitas sama sekali
            if not data['entries'] and not data['has_opening_balance']:
                continue
            
            # Hitung final balance
            if data['account_type'] in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
                data['final_balance'] = data['initial_balance'] + data['total_debit'] - data['total_credit']
            else:
                data['final_balance'] = data['initial_balance'] + data['total_credit'] - data['total_debit']
            
            # Urutkan entries
            data['entries'].sort(key=lambda x: (x.get('sort_order', 1), x['date']))
            
            # Hitung running balance
            running_balance = data['initial_balance']
            for entry in data['entries']:
                if entry.get('is_opening_balance'):
                    entry['running_balance'] = running_balance
                else:
                    if data['account_type'] in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
                        running_balance += entry['debit'] - entry['credit']
                    else:
                        running_balance += entry['credit'] - entry['debit']
                    entry['running_balance'] = running_balance
            
            result.append(data)
        
        # Urutkan hasil berdasarkan kode akun
        result.sort(key=lambda x: x['account_code'])
        
        logger.info(f"✅ Optimized ledger data prepared: {len(result)} active accounts")
        
        # ✅ PERBAIKAN 7: Simpan ke cache
        if not hasattr(app, 'ledger_cache'):
            app.ledger_cache = {}
        app.ledger_cache[cache_key] = (datetime.now(), result)
        
        # ✅ PERBAIKAN 8: Clean old cache entries (optional)
        # Hapus cache yang lebih dari 10 menit
        current_time = datetime.now()
        expired_keys = []
        for key, (cache_time, _) in app.ledger_cache.items():
            if (current_time - cache_time).seconds > 600:  # 10 menit
                expired_keys.append(key)
        
        for key in expired_keys:
            del app.ledger_cache[key]
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error in optimized ledger function: {e}")
        logger.error(traceback.format_exc())
        return []

def get_journal_summary(start_date=None, end_date=None):
    """Hitung summary jurnal untuk periode tertentu"""
    try:
        journals = get_journal_entries_with_details(start_date, end_date)
        
        total_transactions = len(journals)
        total_amount = sum([journal.get('total_amount', 0) for journal in journals])
        
        # Hitung per akun
        account_summary = {}
        for journal in journals:
            for entry in journal.get('journal_entries', []):
                account_code = entry.get('account_code')
                amount = entry.get('amount', 0)
                position = entry.get('position', 'debit')
                
                if account_code not in account_summary:
                    account_summary[account_code] = {
                        'account_code': account_code,
                        'account_name': get_account_name(account_code),
                        'total_debit': 0,
                        'total_credit': 0
                    }
                
                if position == 'debit':
                    account_summary[account_code]['total_debit'] += amount
                else:
                    account_summary[account_code]['total_credit'] += amount
        
        return {
            'total_transactions': total_transactions,
            'total_amount': total_amount,
            'account_summary': list(account_summary.values())
        }
    except Exception as e:
        logger.error(f"❌ Error getting journal summary: {e}")
        return {'total_transactions': 0, 'total_amount': 0, 'account_summary': []}

def delete_journal_transaction(transaction_id):
    """Hapus transaksi jurnal dan semua entries terkait"""
    try:
        # Hapus journal entries terlebih dahulu
        delete_entries = supabase.table("journal_entries").delete().eq("journal_id", transaction_id).execute()
        
        # Hapus general journal
        delete_journal = supabase.table("general_journals").delete().eq("id", transaction_id).execute()
        
        if delete_journal.data:
            logger.info(f"✅ Journal transaction {transaction_id} deleted successfully")
            return {"success": True, "message": "Transaksi berhasil dihapus"}
        else:
            logger.error(f"❌ Failed to delete journal transaction {transaction_id}")
            return {"success": False, "message": "Gagal menghapus transaksi"}
            
    except Exception as e:
        logger.error(f"❌ Error deleting journal transaction: {e}")
        return {"success": False, "message": f"Terjadi kesalahan: {str(e)}"}

# ============================================================
# 📋 9. JURNAL UMUM
# ============================================================

@app.route("/jurnal_umum")
@admin_required
def jurnal_umum():
    """Halaman untuk melihat jurnal umum dari transaksi yang sudah diinput"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter filter dari URL
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # ✅ PERBAIKAN: Validasi dan log parameter tanggal
    logger.info(f"📅 Jurnal Umum - Requested dates: start={start_date}, end={end_date}")
    
    # Jika tanggal tidak valid, set ke None
    if start_date == "" or end_date == "":
        start_date = None
        end_date = None
        logger.info("ℹ️ Empty dates detected, showing all data")
    
    # Ambil data jurnal umum - URUTKAN DARI TANGGAL TERKECIL
    journals = get_journal_entries_with_details(start_date, end_date, limit=65)
    
    # ✅ DEBUG: Tampilkan info filter di UI
    filter_info = ""
    if start_date and end_date:
        filter_info = f"<div class='message info'>🔍 Menampilkan data dari {start_date} hingga {end_date}</div>"
    else:
        filter_info = "<div class='message info'>🔍 Menampilkan semua data (tanpa filter tanggal)</div>"

    # Ambil data jurnal umum - URUTKAN DARI TANGGAL TERKECIL
    journals = get_journal_entries_with_details(start_date, end_date, limit=100)
    
    # Hitung summary
    summary = get_journal_summary(start_date, end_date)
    
    # Fungsi untuk format tanggal DD/MM/YY
    def format_date_ddmmyy(date_str):
        try:
            if not date_str:
                return ""
            # Konversi dari YYYY-MM-DD ke DD/MM/YY
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d/%m/%y')
        except:
            return date_str
    
    # Generate HTML untuk tabel jurnal
    journals_html = ""
    if journals:
        journals_html = """
        <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 20px;">
            <thead>
                <tr style="background: #008DD8; color: white;">
                    <th style="padding: 12px; text-align: center; border: 1px solid #007bff;">Tanggal</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #007bff;">Akun</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #007bff;">Ref</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #007bff;">Debit</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #007bff;">Kredit</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #007bff;">Aksi</th>
                </tr>
            </thead>
            <tbody>
        """
        
        total_debit = 0
        total_credit = 0
        
        # Loop melalui semua transaksi dan gabung dalam satu tabel - URUTKAN DARI TANGGAL TERKECIL
        for journal in journals:
            journal_entries = journal.get('journal_entries', [])
            
            # Format tanggal ke DD/MM/YY
            formatted_date = format_date_ddmmyy(journal['transaction_date'])
            
            # Tambahkan baris untuk setiap entry dalam transaksi
            for i, entry in enumerate(journal_entries):
                # Ambil nama akun dari chart_of_accounts
                account_name = get_account_name(entry['account_code'])
                
                debit_amount = entry['amount'] if entry['position'] == 'debit' else 0
                credit_amount = entry['amount'] if entry['position'] == 'kredit' else 0
                
                # Update total
                total_debit += debit_amount
                total_credit += credit_amount
                
                # Tentukan style untuk kredit (MENJOROK KE DALAM dengan padding-left)
                if credit_amount > 0:
                    credit_style = "padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold; padding-left: 30px;"
                    # Untuk akun kredit, tambahkan indentasi pada nama akun
                    account_style = "padding: 10px; border: 1px solid #dee2e6; padding-left: 30px;"
                else:
                    credit_style = "padding: 10px; border: 1px solid #dee2e6; text-align: right;"
                    account_style = "padding: 10px; border: 1px solid #dee2e6;"
                
                debit_style = "padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;" if debit_amount > 0 else "padding: 10px; border: 1px solid #dee2e6; text-align: right;"
                
                # Tombol hapus hanya untuk entry pertama dari setiap transaksi (untuk menghindari duplikasi)
                delete_button = ""
                if i == 0:  # Hanya tampilkan tombol hapus di baris pertama setiap transaksi
                    delete_button = f"""
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center;">
                        <button onclick="deleteTransaction('{journal['id']}')" 
                                style="background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;"
                                title="Hapus Transaksi">
                            🗑️ Hapus
                        </button>
                    </td>
                    """
                else:
                    delete_button = "<td style='padding: 10px; border: 1px solid #dee2e6;'></td>"
                
                journals_html += f"""
                <tr>
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center;">{formatted_date}</td>
                    <td style="{account_style}">
                        {account_name}
                    </td>
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center;">
                        <strong>{entry['account_code']}</strong>
                    </td>
                    <td style="{debit_style}">
                        {format_currency(debit_amount) if debit_amount > 0 else ''}
                    </td>
                    <td style="{credit_style}">
                        {format_currency(credit_amount) if credit_amount > 0 else ''}
                    </td>
                    {delete_button}
                </tr>
                """
        
        # Tambahkan baris TOTAL di akhir
        journals_html += f"""
            <tr style="background: #e9ecef; font-weight: bold; border-top: 2px solid #008DD8;">
                <td colspan="3" style="padding: 12px; border: 1px solid #dee2e6; text-align: center;">TOTAL</td>
                <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; color: #dc3545;">
                    {format_currency(total_debit)}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; color: #28a745; padding-left: 30px;">
                    {format_currency(total_credit)}
                </td>
                <td style="padding: 12px; border: 1px solid #dee2e6;"></td>
            </tr>
        """
        
        journals_html += """
            </tbody>
        </table>
        """
        
        # Tambahkan info balance
        balance_status = "✅ BALANCE" if total_debit == total_credit else "❌ TIDAK BALANCE"
        balance_color = "#28a745" if total_debit == total_credit else "#dc3545"
        
        journals_html += f"""
        <div style="margin-top: 20px; padding: 15px; background: {balance_color}; color: white; border-radius: 8px; text-align: center; font-weight: bold;">
            {balance_status} | Total Debit: {format_currency(total_debit)} = Total Kredit: {format_currency(total_credit)}
        </div>
        """
        
    else:
        journals_html = """
        <div style="text-align: center; padding: 40px; color: #666;">
            <div style="font-size: 48px; margin-bottom: 20px;">📋</div>
            <h3>Belum Ada Data Jurnal</h3>
            <p>Belum ada transaksi yang dicatat dalam jurnal umum</p>
            <div style="margin-top: 20px;">
                <a href="/input_transaksi"><button style="margin: 5px;">📝 Input Transaksi Baru</button></a>
                <button onclick="location.reload()" style="margin: 5px;">🔄 Refresh Halaman</button></a>
            </div>
        </div>
        """
    
    # Summary HTML
    summary_html = ""
    if summary['total_transactions'] > 0:
        summary_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <h3>TOTAL TRANSAKSI</h3>
                <div class="stat-value">{summary['total_transactions']}</div>
                <div class="stat-note">Jumlah transaksi</div>
            </div>
            
            <div class="stat-card">
                <h3>TOTAL NILAI</h3>
                <div class="stat-value">{format_currency(summary['total_amount'])}</div>
                <div class="stat-note">Total nilai transaksi</div>
            </div>
            
            <div class="stat-card">
                <h3>TOTAL ENTRIES</h3>
                <div class="stat-value">{sum(len(journal.get('journal_entries', [])) for journal in journals)}</div>
                <div class="stat-note">Jumlah entries</div>
            </div>
        </div>
        """
    
    content = f"""
    <div class="welcome-section">
        <h2>📋 Jurnal Umum</h2>
        <div class="welcome-message">
            Lihat semua transaksi keuangan yang telah dicatat dalam sistem. 
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Filter Jurnal</h3>
        <form method="GET" style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Tanggal Mulai</label>
                <input type="date" name="start_date" value="{start_date if start_date else ''}" 
                       style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
            </div>
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Tanggal Akhir</label>
                <input type="date" name="end_date" value="{end_date if end_date else ''}" 
                       style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                    🔍 Terapkan Filter
                </button>
                {'<a href="/jurnal_umum" style="display: block; margin-top: 5px; text-align: center; font-size: 12px;">Hapus Filter</a>' if start_date or end_date else ''}
            </div>
        </form>
    </div>

    {summary_html}

    <div class="quick-actions">
        <div style="display: flex; justify-content: between; align-items: center; margin-bottom: 20px;">
            <h3 style="margin: 0;">📝 Semua Transaksi Jurnal</h3>
            <a href="/input_transaksi">
                <button style="background: #28a745; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer;">
                    ➕ Input Transaksi Baru
                </button>
            </a>
        </div>
        
        <div style="max-height: 800px; overflow-y: auto;">
            {journals_html}
        </div>
    </div>

    <style>
        /* Style tambahan untuk meningkatkan readability */
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        /* Highlight untuk akun kredit yang menjorok */
        .credit-account {{
            padding-left: 30px !important;
            font-style: italic;
        }}
    </style>

    <script>
        function deleteTransaction(transactionId) {{
            if (confirm('Apakah Anda yakin ingin menghapus transaksi ini? Tindakan ini tidak dapat dibatalkan!')) {{
                // Show loading
                const button = event.target;
                const originalText = button.textContent;
                button.textContent = 'Menghapus...';
                button.disabled = true;
                
                fetch('/api/delete_journal_transaction', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        transaction_id: transactionId
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Transaksi berhasil dihapus!');
                        location.reload();
                    }} else {{
                        alert('Error: ' + data.message);
                        // Reset button
                        button.textContent = originalText;
                        button.disabled = false;
                    }}
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Terjadi kesalahan saat menghapus transaksi: ' + error.message);
                    // Reset button
                    button.textContent = originalText;
                    button.disabled = false;
                }});
            }}
        }}
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 📒 10. BUKU BESAR
# ============================================================

@app.route("/buku_besar")
@admin_required
def buku_besar():
    """Halaman buku besar untuk melihat semua akun dalam tabel terpisah per akun - OPTIMIZED"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # ✅ PERBAIKAN 1: Hanya buat data contoh jika benar-benar kosong (dipindahkan ke fungsi)
    create_sample_ledger_data()
    
    # Ambil parameter dari URL
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    account_filter = request.args.get('account', '')
    
    logger.info(f"📒 Buku Besar Grouped - Filter: start={start_date}, end={end_date}, account={account_filter}")
    
    # ✅ PERBAIKAN 2: Ambil data dengan fungsi yang sudah dioptimasi
    grouped_ledger_data = get_general_ledger_entries_grouped_by_account(start_date, end_date)
    
    # ✅ PERBAIKAN 3: Filter di memory, bukan di query
    if account_filter and account_filter != '-- Semua Akun --':
        grouped_ledger_data = [account for account in grouped_ledger_data if account['account_code'] == account_filter]
    
    # ✅ PERBAIKAN 4: Implementasi pagination untuk mengurangi data yang ditampilkan
    PAGE_SIZE = 15  # Max 15 akun per halaman (dikurangi dari sebelumnya)
    page = int(request.args.get('page', 1))
    
    total_accounts = len(grouped_ledger_data)
    total_pages = (total_accounts + PAGE_SIZE - 1) // PAGE_SIZE if total_accounts > 0 else 1
    
    # Batasi halaman agar valid
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_accounts)
    
    paged_data = grouped_ledger_data[start_idx:end_idx]
    
    # ✅ PERBAIKAN 5: Cache untuk daftar akun (cache 5 menit)
    cache_key_accounts = "all_accounts_list"
    if hasattr(app, 'accounts_cache'):
        cache_time, cached_accounts = app.accounts_cache.get(cache_key_accounts, (None, None))
        if cached_accounts and cache_time and (datetime.now() - cache_time).seconds < 300:  # 5 menit
            logger.info("✅ Using cached accounts list")
            all_accounts = cached_accounts
        else:
            all_accounts = get_chart_of_accounts()
            app.accounts_cache[cache_key_accounts] = (datetime.now(), all_accounts)
    else:
        all_accounts = get_chart_of_accounts()
        app.accounts_cache = {cache_key_accounts: (datetime.now(), all_accounts)}
    
    # Buat dropdown options
    account_options = '<option value="-- Semua Akun --">-- Semua Akun --</option>'
    for account in all_accounts:
        selected = 'selected' if account_filter == account['account_code'] else ''
        account_options += f'<option value="{account["account_code"]}" {selected}>{account["account_code"]} - {account["account_name"]}</option>'
    
    # ✅ PERBAIKAN 6: Batasi jumlah entries per akun yang ditampilkan
    MAX_ENTRIES_PER_ACCOUNT = 50  # Max 50 entries per akun
    
    # Buat HTML untuk setiap akun
    ledger_html = ""
    
    if paged_data:
        for account_data in paged_data:
            account_code = account_data['account_code']
            account_name = account_data['account_name']
            
            # ✅ PERBAIKAN 7: Potong entries jika terlalu banyak
            entries_to_display = account_data['entries']
            if len(entries_to_display) > MAX_ENTRIES_PER_ACCOUNT:
                # Tampilkan entries terbaru saja
                entries_to_display = entries_to_display[-MAX_ENTRIES_PER_ACCOUNT:]
                entry_warning = f"<div style='background: #fff3cd; padding: 5px; text-align: center; font-size: 12px; color: #856404;'>⚠️ Menampilkan {MAX_ENTRIES_PER_ACCOUNT} entries terbaru dari total {len(account_data['entries'])} entries</div>"
            else:
                entry_warning = ""
            
            account_table_html = f"""
            <div class="account-section" style="margin-bottom: 30px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div class="account-header" style="background: #2c3e50; color: white; padding: 15px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h4 style="margin: 0; font-size: 16px; font-weight: bold;">{account_code} - {account_name}</h4>
                            <div style="font-size: 12px; opacity: 0.9; margin-top: 5px;">
                                Total Entries: {len(account_data['entries'])} | Ditampilkan: {len(entries_to_display)}
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 12px;">Total Debit: {format_currency(account_data['total_debit'])}</div>
                            <div style="font-size: 12px;">Total Kredit: {format_currency(account_data['total_credit'])}</div>
                            <div style="font-size: 14px; font-weight: bold; margin-top: 5px; background: {'#28a745' if account_data['final_balance'] >= 0 else '#dc3545'}; padding: 2px 8px; border-radius: 4px;">
                                Saldo: {format_currency(abs(account_data['final_balance']))} {'(Debit)' if account_data['final_balance'] >= 0 else '(Kredit)'}
                            </div>
                        </div>
                    </div>
                </div>
                
                {entry_warning}
                
                <div style="max-height: 400px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background: #008DD8; color: white;">
                                <th style="padding: 10px; text-align: center; border: 1px solid #007bff; width: 100px;">Tanggal</th>
                                <th style="padding: 10px; text-align: left; border: 1px solid #007bff;">Keterangan</th>
                                <th style="padding: 10px; text-align: right; border: 1px solid #007bff; width: 120px;">Debit</th>
                                <th style="padding: 10px; text-align: right; border: 1px solid #007bff; width: 120px;">Kredit</th>
                                <th style="padding: 10px; text-align: right; border: 1px solid #007bff; width: 120px;">Saldo</th>
                            </tr>
                        </thead>
                        <tbody>
            """

            # Tambahkan baris untuk setiap entry
            for entry in entries_to_display:
                # Format saldo untuk display
                display_balance = entry['running_balance']
                balance_color = "#28a745" if display_balance >= 0 else "#dc3545"
                
                # Format tanggal khusus untuk saldo awal
                if entry.get('is_opening_balance'):
                    formatted_date = "SALDO AWAL"
                    date_style = "font-weight: bold; color: #008DD8;"
                    description_style = "font-weight: bold; color: #008DD8; font-style: italic;"
                    row_style = "background-color: #e7f3ff; border-left: 4px solid #008DD8;"
                else:
                    formatted_date = entry['date'] if entry['date'] else '-'
                    date_style = "font-weight: bold;"
                    description_style = ""
                    row_style = ""
                
                account_table_html += f"""
                <tr style="{row_style}">
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: center; {date_style}">
                        {formatted_date}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; {description_style}">
                        {entry['description']}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(entry['debit']) if entry['debit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(entry['credit']) if entry['credit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; font-weight: bold; color: {balance_color};">
                        {format_currency(abs(display_balance))} {'(Debit)' if display_balance >= 0 else '(Kredit)'}
                    </td>
                </tr>
                """

            account_table_html += """
                        </tbody>
                    </table>
                </div>
            </div>
            """
            
            ledger_html += account_table_html
    else:
        ledger_html = """
        <div style="text-align: center; padding: 40px; color: #666;">
            <div style="font-size: 48px; margin-bottom: 20px;">📒</div>
            <h3>Belum Ada Data Transaksi</h3>
            <p>Belum ada transaksi yang tercatat dalam buku besar</p>
            <div style="margin-top: 20px;">
                <a href="/input_transaksi"><button style="margin: 5px;">📝 Input Transaksi Baru</button></a>
                <button onclick="location.reload()" style="margin: 5px;">🔄 Refresh Halaman</button>
            </div>
        </div>
        """
    
    # Hitung total keseluruhan DARI DATA YANG DITAMPILKAN SAJA (paged_data)
    total_all_debit = sum(account['total_debit'] for account in paged_data)
    total_all_credit = sum(account['total_credit'] for account in paged_data)
    
    # ✅ PERBAIKAN 8: Buat pagination controls
    pagination_html = ""
    if total_pages > 1:
        pagination_html = '<div style="margin: 20px 0; text-align: center;">'
        
        # Previous button
        if page > 1:
            prev_params = f"?page={page-1}"
            if start_date: prev_params += f"&start_date={start_date}"
            if end_date: prev_params += f"&end_date={end_date}"
            if account_filter: prev_params += f"&account={account_filter}"
            pagination_html += f'<a href="{prev_params}" style="margin: 0 5px; padding: 8px 12px; background: #6c757d; color: white; border-radius: 4px; text-decoration: none;">← Sebelumnya</a>'
        
        # Page numbers
        for p in range(1, total_pages + 1):
            if p == page:
                pagination_html += f'<span style="margin: 0 5px; padding: 8px 12px; background: #008DD8; color: white; border-radius: 4px;">{p}</span>'
            else:
                page_params = f"?page={p}"
                if start_date: page_params += f"&start_date={start_date}"
                if end_date: page_params += f"&end_date={end_date}"
                if account_filter: page_params += f"&account={account_filter}"
                pagination_html += f'<a href="{page_params}" style="margin: 0 5px; padding: 8px 12px; background: #e9ecef; color: #333; border-radius: 4px; text-decoration: none;">{p}</a>'
        
        # Next button
        if page < total_pages:
            next_params = f"?page={page+1}"
            if start_date: next_params += f"&start_date={start_date}"
            if end_date: next_params += f"&end_date={end_date}"
            if account_filter: next_params += f"&account={account_filter}"
            pagination_html += f'<a href="{next_params}" style="margin: 0 5px; padding: 8px 12px; background: #6c757d; color: white; border-radius: 4px; text-decoration: none;">Selanjutnya →</a>'
        
        pagination_html += f'<div style="margin-top: 10px; font-size: 14px; color: #666;">Halaman {page} dari {total_pages} | Total {total_accounts} akun</div>'
        pagination_html += '</div>'
    
    summary_html = f"""
    <div style="background: #e9ecef; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; text-align: center;">
            <div>
                <strong>Total Akun:</strong> 
                <span style="color: #008DD8; font-weight: bold; font-size: 16px;">{total_accounts}</span>
                <div style="font-size: 12px; color: #666;">Ditampilkan: {len(paged_data)}</div>
            </div>
            <div>
                <strong>Total Debit:</strong> 
                <span style="color: #dc3545; font-weight: bold; font-size: 16px;">{format_currency(total_all_debit)}</span>
            </div>
            <div>
                <strong>Total Kredit:</strong> 
                <span style="color: #28a745; font-weight: bold; font-size: 16px;">{format_currency(total_all_credit)}</span>
            </div>
        </div>
        <div style="text-align: center; margin-top: 10px; padding: 10px; background: {'#d4edda' if total_all_debit == total_all_credit else '#f8d7da'}; border-radius: 5px;">
            <strong>Status:</strong> 
            <span style="color: {'#28a745' if total_all_debit == total_all_credit else '#dc3545'}; font-weight: bold;">
                {'✅ SEIMBANG' if total_all_debit == total_all_credit else '❌ TIDAK SEIMBANG'}
            </span>
            {f'<span style="color: #dc3545; margin-left: 10px;">(Selisih: {format_currency(abs(total_all_debit - total_all_credit))})</span>' if total_all_debit != total_all_credit else ''}
        </div>
    </div>
    """ if paged_data else ""

    content = f"""
    <div class="welcome-section">
        <h2>📒 Buku Besar (General Ledger) - OPTIMIZED</h2>
        <div class="welcome-message">
            Lihat semua pergerakan transaksi untuk setiap akun dalam satu tampilan lengkap. 
            Setiap akun ditampilkan dalam tabel terpisah dengan saldo running.
            <br><strong>💡 Neraca Saldo Awal selalu ditampilkan di baris pertama setiap akun.</strong>
            <br><strong>🚀 OPTIMASI: Pagination + Cache + Limit Entries</strong>
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Filter Periode Buku Besar</h3>
        <form method="GET" id="filterForm" style="display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Tanggal Mulai</label>
                <input type="date" name="start_date" value="{start_date}" 
                       style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
            </div>
            
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Tanggal Akhir</label>
                <input type="date" name="end_date" value="{end_date}" 
                       style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
            </div>
            
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Nama Akun</label>
                <select name="account" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                    {account_options}
                </select>
            </div>
            
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; height: 40px;">
                    🔍 Terapkan Filter
                </button>
                {'<a href="/buku_besar" style="display: block; margin-top: 5px; text-align: center; font-size: 12px;">Hapus Filter</a>' if start_date or end_date or account_filter else ''}
            </div>
        </form>
        
        <!-- Pagination Controls (Top) -->
        {pagination_html if pagination_html else ''}
    </div>

    {summary_html}

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Buku Besar - Dikelompokkan per Akun</h3>
            <div style="display: flex; gap: 10px; align-items: center;">
                <span style="font-size: 12px; color: #666;">
                    Menampilkan: <strong>{len(paged_data)} akun</strong> (halaman {page}/{total_pages})
                </span>
                <a href="/input_transaksi">
                    <button style="background: #28a745; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        ➕ Input Transaksi
                    </button>
                </a>
                <a href="/jurnal_umum">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📋 Lihat Jurnal
                    </button>
                </a>
                <a href="/neraca_saldo_awal">
                    <button style="background: #008DD8; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        💰 Kelola Saldo Awal
                    </button>
                </a>
                <button onclick="clearCache()" style="background: #ffc107; color: #212529; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                    🗑️ Clear Cache
                </button>
            </div>
        </div>
        
        <div style="max-height: 800px; overflow-y: auto; padding: 10px; background: #f8f9fa; border-radius: 8px;">
            {ledger_html if ledger_html else '''
            <div style="text-align: center; padding: 40px; color: #666;">
                <div style="font-size: 48px; margin-bottom: 20px;">📒</div>
                <h3>Tidak Ada Data yang Sesuai Filter</h3>
                <p>Coba ubah periode atau pilih akun yang berbeda</p>
            </div>
            '''}
        </div>
        
        <!-- Pagination Controls (Bottom) -->
        {pagination_html if pagination_html else ''}
    </div>

    <style>
        .account-section {{
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            margin-bottom: 25px;
        }}
        
        .account-section:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .account-header {{
            border-bottom: 2px solid #008DD8;
        }}
        
        /* Style khusus untuk baris saldo awal */
        .opening-balance-row {{
            background-color: #e7f3ff !important;
            border-left: 4px solid #008DD8 !important;
        }}
        
        .opening-balance-row td {{
            font-weight: bold !important;
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            .account-header > div {{
                flex-direction: column;
                text-align: center;
            }}
            
            table {{
                font-size: 11px;
            }}
            
            table th,
            table td {{
                padding: 5px;
            }}
            
            table th:nth-child(1),
            table td:nth-child(1) {{
                width: 80px;
            }}
            
            table th:nth-child(3),
            table th:nth-child(4),
            table th:nth-child(5),
            table td:nth-child(3),
            table td:nth-child(4),
            table td:nth-child(5) {{
                width: 100px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika filter diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const filterInputs = document.querySelectorAll('#filterForm input, #filterForm select');
            filterInputs.forEach(input => {{
                input.addEventListener('change', function() {{
                    document.getElementById('filterForm').submit();
                }});
            }});
        }});

        // Smooth scroll untuk navigasi antar akun
        function scrollToAccount(accountCode) {{
            const element = document.getElementById('account-' + accountCode);
            if (element) {{
                element.scrollIntoView({{
                    behavior: 'smooth',
                    block: 'start'
                }});
                
                // Highlight sementara
                element.style.backgroundColor = '#fff3cd';
                setTimeout(() => {{
                    element.style.backgroundColor = '';
                }}, 2000);
            }}
        }}
        
        // Clear cache function
        function clearCache() {{
            if (confirm('Clear cache? Akan memperlambat load pertama kali setelah clear.')) {{
                fetch('/clear_cache')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('Cache cleared successfully!');
                            location.reload();
                        }} else {{
                            alert('Failed to clear cache');
                        }}
                    }})
                    .catch(error => {{
                        console.error('Error:', error);
                        alert('Error clearing cache');
                    }});
            }}
        }}
        
        // Lazy loading untuk entries yang banyak
        function loadMoreEntries(accountCode) {{
            const button = document.getElementById('load-more-' + accountCode);
            const container = document.getElementById('entries-' + accountCode);
            
            if (button && container) {{
                button.textContent = 'Loading...';
                button.disabled = true;
                
                // Simulasi load lebih banyak data
                setTimeout(() => {{
                    // Dalam implementasi real, ini akan fetch data tambahan dari server
                    alert('Fitur load more akan diimplementasi di versi berikutnya');
                    button.textContent = 'Load More';
                    button.disabled = false;
                }}, 500);
            }}
        }}
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 🔹 FUNGSI BUKU BESAR (GENERAL LEDGER)
# ============================================================

def get_general_ledger_entries(account_code=None, start_date=None, end_date=None):
    """Ambil data buku besar dengan format yang sesuai - DIPERBAIKI TOTAL"""
    try:
        logger.info(f"🔍 Fetching ledger entries - Account: {account_code}, Date: {start_date} to {end_date}")
        
        # METHOD 1: Query manual dengan dua query terpisah (lebih reliable)
        # Pertama, ambil semua general_journals
        journals_query = supabase.table("general_journals").select("*")
        
        # Filter tanggal jika ada
        if start_date and end_date and start_date != "" and end_date != "":
            journals_query = journals_query.gte('transaction_date', start_date).lte('transaction_date', end_date)
        
        journals_result = journals_query.order("transaction_date").execute()
        journals = journals_result.data if journals_result.data else []
        
        # Kedua, ambil semua journal_entries
        entries_query = supabase.table("journal_entries").select("*")
        
        # Filter account code jika ada
        if account_code and account_code != "":
            entries_query = entries_query.eq("account_code", account_code)
        
        entries_result = entries_query.order("created_at").execute()
        all_entries = entries_result.data if entries_result.data else []
        
        logger.info(f"✅ Found {len(journals)} journals and {len(all_entries)} entries")
        
        # Gabungkan data secara manual
        processed_entries = []
        
        if account_code and account_code != "":
            # Untuk single account dengan saldo running
            current_balance = 0
            
            # Tambahkan saldo awal
            processed_entries.append({
                'date': start_date if start_date else 'Saldo Awal',
                'description': 'SALDO AWAL',
                'ref': account_code,
                'debit': 0,
                'credit': 0,
                'balance': current_balance,
                'is_initial': True
            })
            
            # Process entries yang sesuai dengan filter
            for journal in journals:
                # Cari entries untuk journal ini
                journal_entries = [e for e in all_entries if e.get('journal_id') == journal['id']]
                
                for entry in journal_entries:
                    # Skip jika account code tidak match (untuk single account view)
                    if account_code and account_code != "" and entry['account_code'] != account_code:
                        continue
                    
                    debit = entry['amount'] if entry['position'] == 'debit' else 0
                    credit = entry['amount'] if entry['position'] == 'kredit' else 0
                    
                    # Update saldo
                    if entry['position'] == 'debit':
                        current_balance += entry['amount']
                    else:
                        current_balance -= entry['amount']
                    
                    processed_entries.append({
                        'date': journal.get('transaction_date', ''),
                        'description': journal.get('description', 'Transaksi'),
                        'ref': entry['account_code'],
                        'debit': debit,
                        'credit': credit,
                        'balance': current_balance,
                        'is_initial': False
                    })
        else:
            # Untuk semua akun
            for journal in journals:
                # Cari entries untuk journal ini
                journal_entries = [e for e in all_entries if e.get('journal_id') == journal['id']]
                
                for entry in journal_entries:
                    debit = entry['amount'] if entry['position'] == 'debit' else 0
                    credit = entry['amount'] if entry['position'] == 'kredit' else 0
                    
                    # Dapatkan nama akun
                    account_name = get_account_name(entry['account_code'])
                    
                    processed_entries.append({
                        'date': journal.get('transaction_date', ''),
                        'description': journal.get('description', 'Transaksi'),
                        'account_name': account_name,
                        'ref': entry['account_code'],
                        'debit': debit,
                        'credit': credit,
                        'balance': 0,
                        'is_initial': False
                    })
        
        logger.info(f"📊 Processed {len(processed_entries)} entries for display")
        return processed_entries
        
    except Exception as e:
        logger.error(f"❌ Error getting general ledger entries: {e}")
        logger.error(traceback.format_exc())
        return []

def create_sample_ledger_data():
    """Buat data contoh untuk Buku Besar jika belum ada data - OPTIMIZED"""
    try:
        # ✅ PERBAIKAN: Cek apakah sudah ada data transaksi dengan query yang lebih efisien
        journals_count_result = supabase.table("general_journals").select("id", count="exact").limit(1).execute()
        
        # Cek count dari result
        if hasattr(journals_count_result, 'count') and journals_count_result.count > 0:
            logger.info("✅ Ledger data already exists")
            return True
        
        # Jika tidak ada data, cek dengan cara lain
        journals_result = supabase.table("general_journals").select("id").limit(1).execute()
        
        if journals_result.data and len(journals_result.data) > 0:
            logger.info("✅ Ledger data already exists (method 2)")
            return True
        
        logger.info("⚠️ No existing ledger data found, but not creating sample automatically")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error checking ledger data: {e}")
        return False

@app.route("/clear_cache")
@admin_required
def clear_cache():
    """Route untuk clear cache manual"""
    try:
        cache_cleared = []
        
        if hasattr(app, 'ledger_cache'):
            app.ledger_cache.clear()
            cache_cleared.append("ledger_cache")
        
        if hasattr(app, 'accounts_cache'):
            app.accounts_cache.clear()
            cache_cleared.append("accounts_cache")
        
        if hasattr(app, 'accounts_cache_full'):
            app.accounts_cache_full.clear()
            cache_cleared.append("accounts_cache_full")
        
        if hasattr(app, 'tb_cache'):
            app.tb_cache.clear()
            cache_cleared.append("tb_cache")
        
        logger.info(f"✅ Cache cleared: {', '.join(cache_cleared) if cache_cleared else 'No cache found'}")
        return jsonify({
            "success": True, 
            "message": f"Cache cleared: {', '.join(cache_cleared) if cache_cleared else 'No cache to clear'}",
            "cleared": cache_cleared
        })
        
    except Exception as e:
        logger.error(f"❌ Error clearing cache: {e}")
        return jsonify({"success": False, "message": f"Error clearing cache: {str(e)}"})
    
# ============================================================
# 🧪 11. NERACA SALDO SEBELUM PENYESUAIAN (NSSP)
# ============================================================

@app.route("/nssp")
@admin_required
def nssp():
    """Halaman Neraca Saldo Sebelum Penyesuaian - DIPERBAIKI TOTAL"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Buat data contoh jika belum ada transaksi untuk periode ini
    create_sample_transactions_for_period(period)
    
    # Hitung neraca saldo dengan fungsi yang sudah diperbaiki
    trial_balance_data = calculate_trial_balance(period)
    summary = get_trial_balance_summary(trial_balance_data)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel NSSP
    nssp_table_html = ""
    
    if trial_balance_data:
        nssp_table_html = """
        <div style="max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #008DD8; color: white; position: sticky; top: 0;">
                        <th style="padding: 12px; text-align: center; border: 1px solid #007bff; width: 120px;">Kode Akun</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #007bff;">Nama Akun</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #007bff; width: 150px;">Tipe Akun</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #007bff; width: 150px;">Debit</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #007bff; width: 150px;">Kredit</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Tampilkan hanya akun yang memiliki saldo (debit atau kredit > 0)
        accounts_with_balance = [item for item in trial_balance_data if item['debit'] > 0 or item['credit'] > 0]
        
        if not accounts_with_balance:
            # Jika tidak ada akun dengan saldo, tampilkan pesan
            nssp_table_html += f"""
                <tr>
                    <td colspan="5" style="padding: 40px; text-align: center; color: #666;">
                        <div style="font-size: 48px; margin-bottom: 20px;">📊</div>
                        <h3>Belum Ada Transaksi</h3>
                        <p>Belum ada transaksi yang tercatat untuk periode {period}</p>
                        <div style="margin-top: 20px;">
                            <button onclick="createSampleData('{period}')" style="margin: 5px; background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                                🧪 Buat Data Contoh
                            </button>
                            <a href="/input_transaksi">
                                <button style="margin: 5px; background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                                    📝 Input Transaksi Baru
                                </button>
                            </a>
                        </div>
                    </td>
                </tr>
            """
        else:
            for item in accounts_with_balance:
                nssp_table_html += f"""
                <tr>
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; font-family: 'Courier New', monospace; font-weight: bold; background: #f8f9fa;">
                        {item['account_code']}
                    </td>
                    <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">
                        {item['account_name']}
                    </td>
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: #f8f9fa;">
                        <span style="font-size: 12px; color: #666;">{item['account_type']}</span>
                    </td>
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(item['debit']) if item['debit'] > 0 else '-'}
                    </td>
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(item['credit']) if item['credit'] > 0 else '-'}
                    </td>
                </tr>
                """
        
        # Baris TOTAL hanya jika ada data
        if accounts_with_balance:
            nssp_table_html += f"""
                <tr style="background: #e9ecef; font-weight: bold; border-top: 3px solid #008DD8;">
                    <td colspan="3" style="padding: 15px; border: 1px solid #dee2e6; text-align: center; font-size: 16px;">
                        TOTAL NERACA SALDO
                    </td>
                    <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-size: 16px;">
                        {format_currency(summary['total_debit'])}
                    </td>
                    <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-size: 16px;">
                        {format_currency(summary['total_credit'])}
                    </td>
                </tr>
            """
        
        nssp_table_html += """
                </tbody>
            </table>
        </div>
        """
        
        # Status balance
        if accounts_with_balance:
            balance_status = "✅ NERACA SEIMBANG" if summary['is_balanced'] else f"❌ NERACA TIDAK SEIMBANG"
            balance_color = "#28a745" if summary['is_balanced'] else "#dc3545"
            
            nssp_table_html += f"""
            <div style="margin-top: 20px; padding: 20px; background: {balance_color}; color: white; border-radius: 8px; text-align: center; font-weight: bold; font-size: 16px;">
                {balance_status}
                {f'<div style="margin-top: 10px; font-size: 14px;">Selisih: {format_currency(abs(summary["difference"]))}</div>' if not summary['is_balanced'] else ''}
            </div>
            """
    else:
        nssp_table_html = """
        <div style="text-align: center; padding: 60px; color: #666;">
            <div style="font-size: 64px; margin-bottom: 20px;">📊</div>
            <h3>Data Tidak Dapat Dimuat</h3>
            <p>Terjadi kesalahan saat memuat data neraca saldo</p>
            <div style="margin-top: 20px;">
                <button onclick="location.reload()" style="margin: 5px; background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                    🔄 Refresh Halaman
                </button>
            </div>
        </div>
        """
    
    # Summary informasi
    accounts_count = len(trial_balance_data) if trial_balance_data else 0
    active_accounts = len([item for item in trial_balance_data if item['debit'] > 0 or item['credit'] > 0]) if trial_balance_data else 0
    
    summary_html = f"""
    <div style="background: linear-gradient(135deg, #008DD8, #00C4FF); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; text-align: center;">
            <div>
                <div style="font-size: 24px; font-weight: bold;">{active_accounts}</div>
                <div style="font-size: 14px; opacity: 0.9;">Akun Aktif</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_debit'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Debit</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_credit'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Kredit</div>
            </div>
        </div>
    </div>
    """ if trial_balance_data and active_accounts > 0 else ""

    content = f"""
    <div class="welcome-section">
        <h2>📊 Neraca Saldo Sebelum Penyesuaian (NSSP)</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan saldo akhir setiap akun dalam Buku Besar sebelum dilakukan penyesuaian. 
            Digunakan untuk memverifikasi kesamaan total debit dan kredit.
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    {summary_html}

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Neraca Saldo Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <a href="/input_transaksi">
                    <button style="background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        ➕ Input Transaksi
                    </button>
                </a>
                <a href="/jurnal_umum">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📋 Lihat Jurnal
                    </button>
                </a>
                <a href="/buku_besar">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📒 Buku Besar
                    </button>
                </a>
                <button onclick="createSampleData('{period}')" style="background: #ffc107; color: #212529; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                    🧪 Data Contoh
                </button>
            </div>
        </div>
        
        {nssp_table_html}
        
        {f'<div style="margin-top: 15px; text-align: center; color: #666; font-size: 14px;">Menampilkan {active_accounts} dari {accounts_count} akun</div>' if trial_balance_data else ''}
    </div>

    <!-- Informasi Penting -->
    <div class="quick-actions">
        <h3>💡 Informasi Penting</h3>
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4 style="color: #008DD8; margin-bottom: 10px;">📋 Cara Membaca NSSP</h4>
                    <ul style="text-align: left; color: #666;">
                        <li><strong>Akun Debit Normal:</strong> Aktiva Lancar, Aktiva Tetap, Beban</li>
                        <li><strong>Akun Kredit Normal:</strong> Kewajiban, Modal, Pendapatan</li>
                        <li><strong>Saldo Debit:</strong> Jika saldo akhir positif untuk akun debit normal</li>
                        <li><strong>Saldo Kredit:</strong> Jika saldo akhir positif untuk akun kredit normal</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: #28a745; margin-bottom: 10px;">✅ Validasi NSSP</h4>
                    <ul style="text-align: left; color: #666;">
                        <li>Total Debit harus sama dengan Total Kredit</li>
                        <li>Jika tidak balance, periksa kembali transaksi</li>
                        <li>Pastikan semua transaksi menggunakan akun yang valid</li>
                        <li>Verifikasi di menu Jurnal Umum terlebih dahulu</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function createSampleData(period) {{
            if (confirm(`Buat data transaksi contoh untuk periode ${{period}}?`)) {{
                fetch('/api/create_sample_data?period=' + period, {{
                    method: 'POST'
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Data contoh berhasil dibuat!');
                        location.reload();
                    }} else {{
                        alert('Error: ' + data.message);
                    }}
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Terjadi kesalahan saat membuat data contoh');
                }});
            }}
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    this.style.backgroundColor = '';
                }});
            }});
        }});
    </script>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table th {{
            position: sticky;
            top: 0;
            background: #008DD8;
            z-index: 10;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 🔹 FUNGSI NERACA SALDO SEBELUM PENYESUAIAN (NSSP)
# ============================================================

def calculate_trial_balance(period=None):
    """Hitung Neraca Saldo Sebelum Penyesuaian - OPTIMIZED"""
    try:
        # ✅ PERBAIKAN 1: Gunakan cache sederhana
        cache_key = f"trial_balance_{period}"
        if hasattr(app, 'tb_cache'):
            cache_time, cached_data = app.tb_cache.get(cache_key, (None, None))
            if cached_data and cache_time and (datetime.now() - cache_time).seconds < 120:  # 2 menit
                logger.info(f"✅ Using cached trial balance")
                return cached_data
        
        # Parse periode
        year, month = map(int, period.split('-'))
        
        # Tentukan rentang tanggal untuk periode yang diminta
        start_date = f"{year}-{month:02d}-01"
        
        # Hitung akhir bulan dengan benar
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"
        
        logger.info(f"📅 Date range for trial balance: {start_date} to {end_date}")
        
        # Ambil data buku besar yang sudah dikelompokkan per akun
        ledger_data = get_general_ledger_entries_grouped_by_account(start_date, end_date)
        
        if not ledger_data:
            logger.info(f"ℹ️ No ledger data found for period {period}")
            # Return semua akun dengan saldo 0
            accounts = get_chart_of_accounts()
            trial_balance_data = []
            for account in accounts:
                trial_balance_data.append({
                    'account_code': account['account_code'],
                    'account_name': account['account_name'],
                    'account_type': account['account_type'],
                    'debit': 0,
                    'credit': 0,
                    'balance': 0
                })
            return trial_balance_data
        
        # Format data untuk NSSP dari buku besar
        trial_balance_data = []
        
        for account_data in ledger_data:
            account_code = account_data['account_code']
            account_name = account_data['account_name']
            account_type = account_data['account_type']
            
            # Ambil total debit dan kredit dari buku besar
            total_debit = account_data['total_debit']
            total_credit = account_data['total_credit']
            final_balance = account_data['final_balance']
            
            # Untuk NSSP, kita tampilkan total debit dan kredit terpisah
            # dan saldo akhir berdasarkan tipe akun
            if account_type in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
                # Akun debit normal: saldo positif = debit, negatif = kredit
                if final_balance >= 0:
                    debit_display = abs(final_balance)
                    credit_display = 0
                else:
                    debit_display = 0
                    credit_display = abs(final_balance)
            else:
                # Akun kredit normal: saldo positif = kredit, negatif = debit
                if final_balance >= 0:
                    debit_display = 0
                    credit_display = abs(final_balance)
                else:
                    debit_display = abs(final_balance)
                    credit_display = 0
            
            trial_balance_data.append({
                'account_code': account_code,
                'account_name': account_name,
                'account_type': account_type,
                'debit': debit_display,
                'credit': credit_display,
                'balance': final_balance
            })
        
        # Urutkan berdasarkan kode akun
        trial_balance_data.sort(key=lambda x: x['account_code'])
        
        # Log summary
        total_debit = sum(item['debit'] for item in trial_balance_data)
        total_credit = sum(item['credit'] for item in trial_balance_data)
        
        logger.info(f"✅ Trial balance calculated from ledger: {len(trial_balance_data)} accounts")
        logger.info(f"💰 Total Debit: {total_debit:,}")
        logger.info(f"💰 Total Credit: {total_credit:,}")
        logger.info(f"⚖️ Balance Status: {'BALANCED' if abs(total_debit - total_credit) < 0.01 else 'NOT BALANCED'}")

        if not hasattr(app, 'tb_cache'):
            app.tb_cache = {}
        app.tb_cache[cache_key] = (datetime.now(), trial_balance_data)
        
        return trial_balance_data
    
    except Exception as e:
        logger.error(f"❌ Error calculating trial balance: {e}")
        return []
    
def get_trial_balance_summary(trial_balance_data):
    """Hitung summary dari neraca saldo"""
    try:
        total_debit = sum(item['debit'] for item in trial_balance_data)
        total_credit = sum(item['credit'] for item in trial_balance_data)
        difference = total_debit - total_credit
        
        return {
            'total_debit': total_debit,
            'total_credit': total_credit,
            'is_balanced': abs(difference) < 0.01,  # Tolerance for floating point
            'difference': difference
        }
    except Exception as e:
        logger.error(f"❌ Error calculating trial balance summary: {e}")
        return {'total_debit': 0, 'total_credit': 0, 'is_balanced': False, 'difference': 0}

def create_sample_transactions_for_period(period):
    """Buat data transaksi contoh untuk periode tertentu"""
    try:
        year, month = map(int, period.split('-'))
        
        # Cek apakah sudah ada transaksi untuk periode ini
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            end_date = f"{year}-{month+1:02d}-01"
        
        existing_journals = supabase.table("general_journals")\
            .select("id")\
            .gte('transaction_date', start_date)\
            .lt('transaction_date', end_date)\
            .execute()
        
        if existing_journals.data:
            logger.info(f"✅ Sample data already exists for period {period}")
            return True
        
    except Exception as e:
        logger.error(f"❌ Error creating sample transactions: {e}")
        logger.error(traceback.format_exc())
        return False

# ============================================================
# 📝 12. JURNAL PENYESUAIAN
# ============================================================

@app.route("/jurnal_penyesuaian")
@admin_required
def jurnal_penyesuaian():
    """Halaman untuk membuat dan melihat jurnal penyesuaian - VERSI DIPERBAIKI"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # DEBUG: Log untuk memeriksa apakah data ada
    logger.info(f"🔍 Fetching adjusting journals for period: {period}")
    
    # Ambil data jurnal penyesuaian yang sudah ada DENGAN FUNGSI YANG DIPERBAIKI
    adjusting_journals = get_adjusting_journals_with_entries(period)
    summary = get_adjusting_journal_summary(period)
    
    # DEBUG: Log hasil query
    logger.info(f"📊 Found {len(adjusting_journals)} adjusting journals with entries")
    
    # Ambil data Chart of Account untuk dropdown
    accounts = get_chart_of_accounts()
    account_options = ""
    for account in accounts:
        account_options += f'<option value="{account["account_code"]}">{account["account_code"]} - {account["account_name"]}</option>'
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel jurnal penyesuaian yang sudah ada - SEMUA DATA DALAM SATU TABEL
    existing_journals_html = ""
    if adjusting_journals:
        # Header tabel
        existing_journals_html = """
        <div style="background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #008DD8; color: white;">
                        <th style="padding: 12px; text-align: center; border: 1px solid #007bff; width: 100px;">Tanggal</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #007bff; width: 120px;">No. Penyesuaian</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #007bff;">Keterangan</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #007bff; width: 80px;">Ref</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #007bff;">Nama Akun</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #007bff; width: 120px;">Debit</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #007bff; width: 120px;">Kredit</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #007bff; width: 100px;">Aksi</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        total_all_debit = 0
        total_all_credit = 0
        
        # Loop melalui semua jurnal penyesuaian dan gabung dalam satu tabel
        for journal in adjusting_journals:
            entries = journal.get('entries', [])
            
            # Format tanggal DD-MM-YY
            formatted_date = ""
            try:
                if journal['adjustment_date']:
                    date_obj = datetime.strptime(journal['adjustment_date'], '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d-%m-%y')
            except:
                formatted_date = journal['adjustment_date']
            
            # Tambahkan baris untuk setiap entry dalam jurnal
            for i, entry in enumerate(entries):
                # Dapatkan nama akun dari chart_of_accounts jika tidak ada di entry
                account_name = entry.get('account_name') or get_account_name(entry['account_code'])
                
                debit_amount = entry['amount'] if entry['position'] == 'debit' else 0
                credit_amount = entry['amount'] if entry['position'] == 'kredit' else 0
                
                # Update total
                total_all_debit += debit_amount
                total_all_credit += credit_amount
                
                # Tentukan style untuk kredit (MENJOROK KE DALAM dengan padding-left)
                if credit_amount > 0:
                    credit_style = "padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold; padding-left: 30px;"
                    # Untuk akun kredit, tambahkan indentasi pada nama akun
                    account_style = "padding: 8px; border: 1px solid #dee2e6; padding-left: 30px;"
                else:
                    credit_style = "padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;"
                    account_style = "padding: 8px; border: 1px solid #dee2e6;"
                
                debit_style = "padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;" if debit_amount > 0 else "padding: 8px; border: 1px solid #dee2e6; text-align: right;"
                
                # Tombol hapus hanya untuk entry pertama dari setiap jurnal (untuk menghindari duplikasi)
                delete_button = ""
                if i == 0:  # Hanya tampilkan tombol hapus di baris pertama setiap jurnal
                    delete_button = f"""
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: center;">
                        <button onclick="deleteAdjustingJournal('{journal['id']}')" 
                                style="background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;"
                                title="Hapus Jurnal Penyesuaian">
                            🗑️ Hapus
                        </button>
                    </td>
                    """
                else:
                    delete_button = "<td style='padding: 8px; border: 1px solid #dee2e6;'></td>"
                
                # Tampilkan nomor penyesuaian hanya di baris pertama
                adjustment_number_cell = ""
                if i == 0:
                    adjustment_number_cell = f"""
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: center; font-weight: bold;">
                        {journal['adjustment_number']}
                    </td>
                    """
                else:
                    adjustment_number_cell = "<td style='padding: 8px; border: 1px solid #dee2e6;'></td>"
                
                # Tampilkan keterangan hanya di baris pertama
                description_cell = ""
                if i == 0:
                    description_cell = f"""
                    <td style="padding: 8px; border: 1px solid #dee2e6; font-weight: bold;">
                        {journal['description']}
                    </td>
                    """
                else:
                    description_cell = "<td style='padding: 8px; border: 1px solid #dee2e6;'></td>"
                
                existing_journals_html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: center; font-weight: bold;">
                        {formatted_date}
                    </td>
                    {adjustment_number_cell}
                    {description_cell}
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: center;">
                        <strong>{entry['account_code']}</strong>
                    </td>
                    <td style="{account_style}">
                        {account_name}
                    </td>
                    <td style="{debit_style}">
                        {format_currency(debit_amount) if debit_amount > 0 else ''}
                    </td>
                    <td style="{credit_style}">
                        {format_currency(credit_amount) if credit_amount > 0 else ''}
                    </td>
                    {delete_button}
                </tr>
                """
            
            # Tambahkan baris pemisah antar jurnal
            if journal != adjusting_journals[-1]:
                existing_journals_html += """
                <tr>
                    <td colspan="8" style="padding: 5px; background: #f8f9fa;"></td>
                </tr>
                """
        
        # Tambahkan baris TOTAL di akhir
        existing_journals_html += f"""
                </tbody>
                <tfoot>
                    <tr style="background: #e9ecef; font-weight: bold; border-top: 2px solid #008DD8;">
                        <td colspan="5" style="padding: 12px; border: 1px solid #dee2e6; text-align: center;">TOTAL</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; color: #dc3545;">
                            {format_currency(total_all_debit)}
                        </td>
                        <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; color: #28a745;">
                            {format_currency(total_all_credit)}
                        </td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;"></td>
                    </tr>
                </tfoot>
            </table>
        </div>
        """
        
        # Tambahkan info balance
        balance_status = "✅ BALANCE" if total_all_debit == total_all_credit else "❌ TIDAK BALANCE"
        balance_color = "#28a745" if total_all_debit == total_all_credit else "#dc3545"
        
        existing_journals_html += f"""
        <div style="margin-top: 20px; padding: 15px; background: {balance_color}; color: white; border-radius: 8px; text-align: center; font-weight: bold;">
            {balance_status} | Total Debit: {format_currency(total_all_debit)} = Total Kredit: {format_currency(total_all_credit)}
        </div>
        """
        
    else:
        existing_journals_html = """
        <div style="text-align: center; padding: 40px; color: #666;">
            <div style="font-size: 48px; margin-bottom: 20px;">📝</div>
            <h3>Belum Ada Jurnal Penyesuaian</h3>
            <p>Buat jurnal penyesuaian pertama Anda menggunakan form di atas</p>
        </div>
        """
    
    # Summary section
    summary_html = f"""
    <div style="background: linear-gradient(135deg, #008DD8, #00C4FF); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; text-align: center;">
            <div>
                <div style="font-size: 24px; font-weight: bold;">{summary['total_adjustments']}</div>
                <div style="font-size: 14px; opacity: 0.9;">Jumlah Penyesuaian</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_amount'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Nilai</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{len(summary['account_summary'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Akun Terdampak</div>
            </div>
        </div>
    </div>
    """ if summary['total_adjustments'] > 0 else ""

    content = f"""
    <div class="welcome-section">
        <h2>📝 Jurnal Penyesuaian</h2>
        <div class="welcome-message">
            Buat jurnal penyesuaian untuk menyesuaikan saldo akun sebelum penyusunan laporan keuangan. 
            Jurnal ini digunakan untuk mencatat transaksi yang belum tercatat atau perlu penyesuaian.
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Jurnal Penyesuaian</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Jurnal
                </button>
            </div>
        </form>
    </div>

    {summary_html}

    <div class="quick-actions">
        <h3>➕ Buat Jurnal Penyesuaian Baru</h3>
        <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1); margin-bottom: 30px;">
            <form id="adjustingJournalForm">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #333;">Tanggal Penyesuaian</label>
                        <input type="date" id="adjustmentDate" required 
                               value="{date.today().isoformat()}"
                               style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 14px;">
                    </div>
                    
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #333;">Keterangan</label>
                        <input type="text" id="adjustmentDesc" required 
                               placeholder="Contoh: Penyesuaian penyusutan peralatan"
                               style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 14px;">
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 15px; font-weight: 600; color: #333; font-size: 16px;">Detail Akun Penyesuaian</label>
                    <div id="adjustmentEntries">
                        <!-- Entries akan ditambahkan dinamis di sini -->
                    </div>
                    
                    <button type="button" onclick="addAdjustmentEntry()" 
                            style="background: #28a745; color: white; border: none; padding: 12px 20px; border-radius: 8px; cursor: pointer; margin-top: 15px; font-size: 14px; font-weight: bold;">
                        ➕ Tambah Akun
                    </button>
                </div>

                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                    <h4 style="margin-bottom: 15px; color: #333;">⚖️ Balance Check</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                        <div>
                            <strong style="display: block; margin-bottom: 5px;">Total Debit:</strong>
                            <div id="totalAdjustmentDebit" style="font-size: 20px; color: #dc3545; font-weight: bold;">Rp 0</div>
                        </div>
                        <div>
                            <strong style="display: block; margin-bottom: 5px;">Total Kredit:</strong>
                            <div id="totalAdjustmentCredit" style="font-size: 20px; color: #28a745; font-weight: bold;">Rp 0</div>
                        </div>
                    </div>
                    <div id="adjustmentBalanceStatus" style="margin-top: 15px; font-weight: bold; font-size: 16px;"></div>
                </div>

                <button type="button" onclick="submitAdjustingJournal()" 
                        style="background: #008DD8; color: white; border: none; padding: 15px 30px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%;">
                    💾 Simpan Jurnal Penyesuaian
                </button>
            </form>
        </div>
    </div>

    <div class="quick-actions">
        <h3>📋 Jurnal Penyesuaian {period}</h3>
        <div style="max-height: 600px; overflow-y: auto;">
            {existing_journals_html}
        </div>
    </div>

    <style>
        .adjustment-entry {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            border: 1px solid #e9ecef;
        }}

        .adjustment-entry-row {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr auto;
            gap: 15px;
            align-items: end;
            margin-bottom: 15px;
        }}

        .adjustment-entry:last-child .adjustment-entry-row {{
            margin-bottom: 0;
        }}

        .adjustment-entry select,
        .adjustment-entry input {{
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            width: 100%;
            font-size: 14px;
        }}

        .remove-adjustment-btn {{
            background: #dc3545;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }}

        .balance-valid {{
            color: #28a745;
            background: #d4edda;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            font-size: 16px;
        }}

        .balance-invalid {{
            color: #dc3545;
            background: #f8d7da;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            font-size: 16px;
        }}

        .adjusting-journal-card {{
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}

        .adjusting-journal-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }}

        @media (max-width: 768px) {{
            .adjustment-entry-row {{
                grid-template-columns: 1fr;
                gap: 10px;
            }}
            
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>

    <script>
        let adjustmentEntryCount = 0;

        // Tambah entry akun pertama saat halaman dimuat
        document.addEventListener('DOMContentLoaded', function() {{
            addAdjustmentEntry();
            addAdjustmentEntry();
        }});

        function addAdjustmentEntry() {{
            const entriesContainer = document.getElementById('adjustmentEntries');
            const entryId = 'adjustment-entry-' + adjustmentEntryCount;
            
            const entryHTML = `
                <div class="adjustment-entry" id="${{entryId}}">
                    <div class="adjustment-entry-row">
                        <div>
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Posisi</label>
                            <select name="position" onchange="updateAdjustmentBalance()" required>
                                <option value="">Pilih Posisi</option>
                                <option value="debit">Debit</option>
                                <option value="kredit">Kredit</option>
                            </select>
                        </div>
                        
                        <div>
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Akun</label>
                            <select name="account_code" required>
                                <option value="">Pilih Akun</option>
                                {account_options}
                            </select>
                        </div>
                        
                        <div>
                            <label style="display: block; margin-bottom: 5px; font-weight: 600;">Jumlah (Rp)</label>
                            <input type="number" name="amount" placeholder="Masukkan jumlah" min="1" 
                                   onchange="updateAdjustmentBalance()" onkeyup="updateAdjustmentBalance()" required>
                        </div>
                        
                        <div>
                            <button type="button" class="remove-adjustment-btn" onclick="removeAdjustmentEntry('${{entryId}}')" 
                                    ${{adjustmentEntryCount < 2 ? 'disabled' : ''}} title="Hapus Entry">
                                🗑️ Hapus
                            </button>
                        </div>
                    </div>
                    
                    <div>
                        <label style="display: block; margin-bottom: 5px; font-weight: 600;">Keterangan Penyesuaian</label>
                        <input type="text" name="note" placeholder="Masukkan keterangan penyesuaian" style="width: 100%;">
                    </div>
                </div>
            `;
            
            entriesContainer.insertAdjacentHTML('beforeend', entryHTML);
            adjustmentEntryCount++;
        }}

        function removeAdjustmentEntry(entryId) {{
            const entry = document.getElementById(entryId);
            if (entry) {{
                entry.remove();
                updateAdjustmentBalance();
            }}
        }}

        function updateAdjustmentBalance() {{
            let totalDebit = 0;
            let totalCredit = 0;
            
            // Hitung total debit dan kredit
            const entries = document.querySelectorAll('.adjustment-entry');
            entries.forEach(entry => {{
                const position = entry.querySelector('select[name="position"]').value;
                const amount = parseFloat(entry.querySelector('input[name="amount"]').value) || 0;
                
                if (position === 'debit') {{
                    totalDebit += amount;
                }} else if (position === 'kredit') {{
                    totalCredit += amount;
                }}
            }});
            
            // Update tampilan total
            document.getElementById('totalAdjustmentDebit').textContent = formatCurrency(totalDebit);
            document.getElementById('totalAdjustmentCredit').textContent = formatCurrency(totalCredit);
            
            // Cek balance
            const balanceStatus = document.getElementById('adjustmentBalanceStatus');
            if (totalDebit === totalCredit && totalDebit > 0) {{
                balanceStatus.innerHTML = '<div class="balance-valid">✅ Balance: DEBIT = KREDIT</div>';
            }} else if (totalDebit > 0 || totalCredit > 0) {{
                balanceStatus.innerHTML = '<div class="balance-invalid">❌ Tidak Balance: DEBIT ≠ KREDIT</div>';
            }} else {{
                balanceStatus.innerHTML = '<div style="color: #666; text-align: center;">Silakan tambahkan entri akun</div>';
            }}
        }}

        function formatCurrency(amount) {{
            return 'Rp ' + amount.toLocaleString('id-ID');
        }}

        function submitAdjustingJournal() {{
            // Validasi form
            const adjustmentDate = document.getElementById('adjustmentDate').value;
            const adjustmentDesc = document.getElementById('adjustmentDesc').value;
            const period = document.querySelector('select[name="period"]').value;
            
            if (!adjustmentDate || !adjustmentDesc) {{
                alert('Harap lengkapi tanggal dan keterangan penyesuaian!');
                return;
            }}
            
            // Kumpulkan data entries
            const entries = [];
            const entryElements = document.querySelectorAll('.adjustment-entry');
            
            let isValid = true;
            let totalDebit = 0;
            let totalCredit = 0;
            
            entryElements.forEach((entry, index) => {{
                const position = entry.querySelector('select[name="position"]').value;
                const accountCode = entry.querySelector('select[name="account_code"]').value;
                const amount = parseFloat(entry.querySelector('input[name="amount"]').value) || 0;
                const note = entry.querySelector('input[name="note"]').value;
                
                if (!position || !accountCode || amount <= 0) {{
                    isValid = false;
                    alert(`Entry #${{index + 1}} belum lengkap!`);
                    return;
                }}
                
                if (position === 'debit') {{
                    totalDebit += amount;
                }} else {{
                    totalCredit += amount;
                }}
                
                entries.push({{
                    position: position,
                    account_code: accountCode,
                    amount: amount,
                    note: note
                }});
            }});
            
            if (!isValid) return;
            
            // Validasi balance
            if (totalDebit !== totalCredit) {{
                alert('Total Debit harus sama dengan Total Kredit!');
                return;
            }}
            
            if (entries.length < 2) {{
                alert('Jurnal penyesuaian harus memiliki minimal 2 akun!');
                return;
            }}
            
            // Submit data ke server
            const adjustmentData = {{
                adjustment_date: adjustmentDate,
                description: adjustmentDesc,
                period: period,
                total_amount: totalDebit,
                entries: entries
            }};
            
            fetch('/api/save_adjusting_journal', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify(adjustmentData)
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.success) {{
                    alert('Jurnal penyesuaian berhasil disimpan!');
                    // Reset form
                    document.getElementById('adjustingJournalForm').reset();
                    document.getElementById('adjustmentEntries').innerHTML = '';
                    adjustmentEntryCount = 0;
                    addAdjustmentEntry();
                    addAdjustmentEntry();
                    updateAdjustmentBalance();
                    // Reload halaman untuk menampilkan data baru
                    setTimeout(() => location.reload(), 1000);
                }} else {{
                    alert('Error: ' + data.message);
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
                alert('Terjadi kesalahan saat menyimpan jurnal penyesuaian');
            }});
        }}

        function deleteAdjustingJournal(journalId) {{
            if (confirm('Apakah Anda yakin ingin menghapus jurnal penyesuaian ini?')) {{
                fetch('/api/delete_adjusting_journal', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        adjusting_journal_id: journalId
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Jurnal penyesuaian berhasil dihapus!');
                        location.reload();
                    }} else {{
                        alert('Error: ' + data.message);
                    }}
                }})
                .catch(error => {{
                    console.error('Error:', error);
                    alert('Terjadi kesalahan saat menghapus jurnal penyesuaian');
                }});
            }}
        }}

        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 📊 FUNGSI JURNAL PENYESUAIAN
# ============================================================

def get_adjusting_journals(period=None):
    """Ambil data jurnal penyesuaian untuk periode tertentu DENGAN ENTRIES"""
    try:
        # Pertama, ambil header jurnal penyesuaian
        query = supabase.table("adjusting_journals").select("*")
        
        if period:
            # Parse periode menjadi rentang tanggal
            year, month = map(int, period.split('-'))
            start_date = f"{year}-{month:02d}-01"
            if month == 12:
                end_date = f"{year}-12-31"
            else:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                end_date = f"{year}-{month:02d}-{last_day:02d}"
            
            query = query.gte('adjustment_date', start_date).lte('adjustment_date', end_date)
        
        journals_result = query.order("adjustment_date").execute()
        journals = journals_result.data if journals_result.data else []
        
        # Untuk setiap journal, ambil entries-nya
        journals_with_entries = []
        for journal in journals:
            entries = get_adjusting_journal_entries(journal['id'])
            journal_data = {
                **journal,
                'entries': entries,
                'total_debit': sum(entry['amount'] for entry in entries if entry['position'] == 'debit'),
                'total_credit': sum(entry['amount'] for entry in entries if entry['position'] == 'kredit')
            }
            journals_with_entries.append(journal_data)
        
        return journals_with_entries
        
    except Exception as e:
        logger.error(f"❌ Error getting adjusting journals: {e}")
        logger.error(traceback.format_exc())
        return []

def get_adjusting_journal_entries(adjusting_journal_id):
    """Ambil entries untuk jurnal penyesuaian tertentu"""
    try:
        result = supabase.table("adjusting_journal_entries").select("*, chart_of_accounts(account_name, account_type)").eq("adjusting_journal_id", adjusting_journal_id).execute()
        
        entries = []
        if result.data:
            for entry in result.data:
                account_info = entry.get('chart_of_accounts', {})
                entry_data = {
                    'id': entry['id'],
                    'account_code': entry['account_code'],
                    'account_name': account_info.get('account_name', 'Unknown Account'),
                    'account_type': account_info.get('account_type', 'Unknown'),
                    'position': entry['position'],
                    'amount': entry['amount'],
                    'note': entry.get('note', ''),
                    'created_at': entry.get('created_at', '')
                }
                entries.append(entry_data)
        
        return entries
    except Exception as e:
        logger.error(f"❌ Error getting adjusting journal entries: {e}")
        logger.error(traceback.format_exc())
        return []

def save_adjusting_journal(adjustment_data):
    """Simpan jurnal penyesuaian baru"""
    try:
        # Simpan header jurnal penyesuaian
        journal_data = {
            "adjustment_number": generate_invoice("ADJ"),
            "adjustment_date": adjustment_data['adjustment_date'],
            "description": adjustment_data['description'],
            "total_amount": adjustment_data['total_amount'],
            "period": adjustment_data['period'],
            "created_by": session.get('user_name', 'Admin'),
            "created_at": datetime.utcnow().isoformat()
        }
        
        journal_result = supabase.table("adjusting_journals").insert(journal_data).execute()
        journal_id = journal_result.data[0]['id'] if journal_result.data else None
        
        if not journal_id:
            return {"success": False, "message": "Gagal menyimpan header jurnal penyesuaian"}
        
        # Simpan entries
        entries_data = []
        for entry in adjustment_data['entries']:
            entry_data = {
                "adjusting_journal_id": journal_id,
                "account_code": entry['account_code'],
                "position": entry['position'],
                "amount": entry['amount'],
                "note": entry.get('note', ''),
                "created_at": datetime.utcnow().isoformat()
            }
            entries_data.append(entry_data)
        
        entries_result = supabase.table("adjusting_journal_entries").insert(entries_data).execute()
        
        if entries_result.data:
            logger.info(f"✅ Adjusting journal saved: {journal_data['adjustment_number']}")
            return {
                "success": True, 
                "message": f"Jurnal penyesuaian {journal_data['adjustment_number']} berhasil disimpan",
                "adjustment_number": journal_data['adjustment_number']
            }
        else:
            # Rollback jika gagal simpan entries
            supabase.table("adjusting_journals").delete().eq("id", journal_id).execute()
            return {"success": False, "message": "Gagal menyimpan entries jurnal penyesuaian"}
            
    except Exception as e:
        logger.error(f"❌ Error saving adjusting journal: {e}")
        return {"success": False, "message": f"Terjadi kesalahan: {str(e)}"}

def delete_adjusting_journal(adjusting_journal_id):
    """Hapus jurnal penyesuaian"""
    try:
        # Hapus entries terlebih dahulu
        delete_entries = supabase.table("adjusting_journal_entries").delete().eq("adjusting_journal_id", adjusting_journal_id).execute()
        
        # Hapus journal
        delete_journal = supabase.table("adjusting_journals").delete().eq("id", adjusting_journal_id).execute()
        
        if delete_journal.data:
            logger.info(f"✅ Adjusting journal {adjusting_journal_id} deleted")
            return {"success": True, "message": "Jurnal penyesuaian berhasil dihapus"}
        else:
            return {"success": False, "message": "Gagal menghapus jurnal penyesuaian"}
            
    except Exception as e:
        logger.error(f"❌ Error deleting adjusting journal: {e}")
        return {"success": False, "message": f"Terjadi kesalahan: {str(e)}"}

def get_adjusting_journal_summary(period=None):
    """Hitung summary jurnal penyesuaian - VERSI DIPERBAIKI"""
    try:
        journals = get_adjusting_journals_with_entries(period)
        
        total_adjustments = len(journals)
        total_amount = sum(journal.get('total_amount', 0) for journal in journals)
        
        # Hitung per akun
        account_summary = {}
        for journal in journals:
            entries = journal.get('entries', [])
            for entry in entries:
                account_code = entry.get('account_code')
                amount = entry.get('amount', 0)
                position = entry.get('position', 'debit')
                
                if account_code not in account_summary:
                    account_summary[account_code] = {
                        'account_code': account_code,
                        'account_name': get_account_name(account_code),
                        'total_debit': 0,
                        'total_credit': 0
                    }
                
                if position == 'debit':
                    account_summary[account_code]['total_debit'] += amount
                else:
                    account_summary[account_code]['total_credit'] += amount
        
        return {
            'total_adjustments': total_adjustments,
            'total_amount': total_amount,
            'account_summary': list(account_summary.values())
        }
    except Exception as e:
        logger.error(f"❌ Error getting adjusting journal summary: {e}")
        return {'total_adjustments': 0, 'total_amount': 0, 'account_summary': []}

def get_adjusting_journals_with_entries(period=None):
    """Ambil data jurnal penyesuaian dengan entries - VERSI DIPERBAIKI"""
    try:
        logger.info(f"🔍 Fetching adjusting journals with entries for period: {period}")
        
        # Query untuk adjusting_journals
        query = supabase.table("adjusting_journals").select("*")
        
        if period:
            # Parse periode menjadi rentang tanggal
            year, month = map(int, period.split('-'))
            start_date = f"{year}-{month:02d}-01"
            if month == 12:
                end_date = f"{year}-12-31"
            else:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                end_date = f"{year}-{month:02d}-{last_day:02d}"
            
            query = query.gte('adjustment_date', start_date).lte('adjustment_date', end_date)
        
        journals_result = query.order("adjustment_date", desc=True).execute()
        journals = journals_result.data if journals_result.data else []
        
        logger.info(f"📊 Found {len(journals)} adjusting journals")
        
        # Untuk setiap journal, ambil entries-nya
        journals_with_entries = []
        for journal in journals:
            # Ambil entries untuk journal ini
            entries_result = supabase.table("adjusting_journal_entries")\
                .select("*")\
                .eq("adjusting_journal_id", journal['id'])\
                .execute()
            
            journal_entries = entries_result.data if entries_result.data else []
            
            # Format data journal dengan entries
            journal_data = {
                'id': journal['id'],
                'adjustment_number': journal.get('adjustment_number', ''),
                'adjustment_date': journal.get('adjustment_date', ''),
                'description': journal.get('description', 'Penyesuaian'),
                'total_amount': journal.get('total_amount', 0),
                'period': journal.get('period', ''),
                'created_by': journal.get('created_by', 'System'),
                'created_at': journal.get('created_at', ''),
                'entries': journal_entries
            }
            
            journals_with_entries.append(journal_data)
        
        logger.info(f"✅ Adjusting journals with entries fetched: {len(journals_with_entries)} journals")
        return journals_with_entries
        
    except Exception as e:
        logger.error(f"❌ Error getting adjusting journals with entries: {e}")
        logger.error(traceback.format_exc())
        return []

def get_adjusting_journal_entries_with_account_info(adjusting_journal_id):
    """Ambil entries untuk jurnal penyesuaian dengan informasi akun lengkap"""
    try:
        result = supabase.table("adjusting_journal_entries")\
            .select("*, chart_of_accounts(account_name, account_type, account_code)")\
            .eq("adjusting_journal_id", adjusting_journal_id)\
            .execute()
        
        entries = []
        if result.data:
            for entry in result.data:
                account_info = entry.get('chart_of_accounts', {})
                if isinstance(account_info, list) and account_info:
                    account_info = account_info[0]
                
                entry_data = {
                    'id': entry['id'],
                    'account_code': entry['account_code'],
                    'account_name': account_info.get('account_name', 'Unknown Account') if account_info else 'Unknown Account',
                    'account_type': account_info.get('account_type', 'Unknown') if account_info else 'Unknown',
                    'position': entry['position'],
                    'amount': entry['amount'],
                    'note': entry.get('note', ''),
                    'created_at': entry.get('created_at', '')
                }
                entries.append(entry_data)
        
        return entries
    except Exception as e:
        logger.error(f"❌ Error getting adjusting journal entries with account info: {e}")
        logger.error(traceback.format_exc())
        return []

# ============================================================
# 🗃️ 13. NERACA SALDO SETELAH PENYESUAIAN
# ============================================================

def get_adjusted_trial_balance(period=None):
    """Hitung Neraca Saldo Setelah Penyesuaian - PERBAIKAN TANGGAL"""
    try:
        if not period:
            # Default ke bulan berjalan
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating ADJUSTED trial balance for period: {period}")
        
        # Parse periode untuk mendapatkan tanggal akhir periode
        year, month = map(int, period.split('-'))
        
        # Tentukan tanggal akhir periode (bukan tanggal saat ini)
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"
        
        # 1. Ambil neraca saldo SEBELUM penyesuaian
        trial_balance_before = calculate_trial_balance(period)
        
        # 2. Ambil jurnal penyesuaian untuk periode yang sama
        adjusting_journals = get_adjusting_journals_with_entries(period)
        
        # 3. Buat mapping untuk akun-akun
        account_map = {}
        
        # Inisialisasi dengan data sebelum penyesuaian
        for account in trial_balance_before:
            account_code = account['account_code']
            account_map[account_code] = {
                'account_code': account_code,
                'account_name': account['account_name'],
                'account_type': account['account_type'],
                'debit_before': account['debit'],
                'credit_before': account['credit'],
                'debit_after': account['debit'],  # Akan diupdate
                'credit_after': account['credit'],  # Akan diupdate
                'period_end_date': end_date  # ✅ TAMBAHKAN TANGGAL AKHIR PERIODE
            }
        
        # 4. Terapkan penyesuaian (sisa kode tetap sama...)
        for journal in adjusting_journals:
            for entry in journal.get('entries', []):
                account_code = entry['account_code']
                amount = entry['amount']
                position = entry['position']
                
                # Jika akun belum ada di mapping, tambahkan
                if account_code not in account_map:
                    account_name = get_account_name(account_code)
                    account_type = "Unknown"
                    account_map[account_code] = {
                        'account_code': account_code,
                        'account_name': account_name,
                        'account_type': account_type,
                        'debit_before': 0,
                        'credit_before': 0,
                        'debit_after': 0,
                        'credit_after': 0,
                        'period_end_date': end_date  # ✅ TAMBAHKAN TANGGAL AKHIR PERIODE
                    }
                
                # Terapkan penyesuaian berdasarkan posisi
                if position == 'debit':
                    account_map[account_code]['debit_after'] += amount
                else:  # kredit
                    account_map[account_code]['credit_after'] += amount
        
        # 5. Konversi ke list
        adjusted_trial_balance = list(account_map.values())
        
        # 6. Hitung saldo akhir yang benar berdasarkan tipe akun
        for account in adjusted_trial_balance:
            account_type = account['account_type']
            
            # Untuk akun debit normal (Aktiva Lancar, Aktiva Tetap, Beban)
            if account_type in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
                # Saldo = Debit - Credit
                balance = account['debit_after'] - account['credit_after']
                if balance >= 0:
                    account['debit_after'] = balance
                    account['credit_after'] = 0
                else:
                    account['debit_after'] = 0
                    account['credit_after'] = abs(balance)
            # Untuk akun kredit normal (Kewajiban, Modal, Pendapatan)
            else:
                # Saldo = Credit - Debit
                balance = account['credit_after'] - account['debit_after']
                if balance >= 0:
                    account['debit_after'] = 0
                    account['credit_after'] = balance
                else:
                    account['debit_after'] = abs(balance)
                    account['credit_after'] = 0
        
        # Urutkan berdasarkan kode akun
        adjusted_trial_balance.sort(key=lambda x: x['account_code'])
        
        # Log summary
        total_debit_after = sum(item['debit_after'] for item in adjusted_trial_balance)
        total_credit_after = sum(item['credit_after'] for item in adjusted_trial_balance)
        
        logger.info(f"✅ ADJUSTED trial balance calculated: {len(adjusted_trial_balance)} accounts")
        logger.info(f"💰 Total Debit After: {total_debit_after:,}")
        logger.info(f"💰 Total Credit After: {total_credit_after:,}")
        logger.info(f"⚖️ Balance Status: {'BALANCED' if abs(total_debit_after - total_credit_after) < 0.01 else 'NOT BALANCED'}")
        logger.info(f"📅 Period End Date: {end_date}")
        
        return adjusted_trial_balance
        
    except Exception as e:
        logger.error(f"❌ Error calculating ADJUSTED trial balance: {e}")
        logger.error(traceback.format_exc())
        return []

def get_adjusted_trial_balance_summary(adjusted_trial_balance_data):
    """Hitung summary dari neraca saldo SETELAH penyesuaian"""
    try:
        total_debit_before = sum(item['debit_before'] for item in adjusted_trial_balance_data)
        total_credit_before = sum(item['credit_before'] for item in adjusted_trial_balance_data)
        total_debit_after = sum(item['debit_after'] for item in adjusted_trial_balance_data)
        total_credit_after = sum(item['credit_after'] for item in adjusted_trial_balance_data)
        
        difference_before = total_debit_before - total_credit_before
        difference_after = total_debit_after - total_credit_after
        
        return {
            'total_debit_before': total_debit_before,
            'total_credit_before': total_credit_before,
            'total_debit_after': total_debit_after,
            'total_credit_after': total_credit_after,
            'is_balanced_before': abs(difference_before) < 0.01,
            'is_balanced_after': abs(difference_after) < 0.01,
            'difference_before': difference_before,
            'difference_after': difference_after
        }
    except Exception as e:
        logger.error(f"❌ Error calculating ADJUSTED trial balance summary: {e}")
        return {
            'total_debit_before': 0, 
            'total_credit_before': 0,
            'total_debit_after': 0, 
            'total_credit_after': 0,
            'is_balanced_before': False,
            'is_balanced_after': False,
            'difference_before': 0,
            'difference_after': 0
        }

@app.route("/neraca_saldo_setelah_penyesuaian")
@admin_required
def neraca_saldo_setelah_penyesuaian():
    """Halaman Neraca Saldo Setelah Penyesuaian - DIPERBAIKI TANGGAL"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Hitung neraca saldo SETELAH penyesuaian
    adjusted_trial_balance_data = get_adjusted_trial_balance(period)
    summary = get_adjusted_trial_balance_summary(adjusted_trial_balance_data)
    
    # Tentukan tanggal yang benar untuk periode tersebut
    year, month = map(int, period.split('-'))
    if month == 12:
        correct_date = f"{year}-12-31"
    else:
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        correct_date = f"{year}-{month:02d}-{last_day:02d}"
    
    # Format tanggal untuk display (DD/MM/YYYY)
    formatted_correct_date = datetime.strptime(correct_date, '%Y-%m-%d').strftime('%d/%m/%Y')
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel Neraca Saldo SETELAH Penyesuaian - DENGAN TANGGAL YANG BENAR
    adjusted_table_html = ""
    
    if adjusted_trial_balance_data:
        adjusted_table_html = """
        <div style="max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #28a745; color: white;">
                        <th style="padding: 12px; text-align: center; border: 1px solid #218838; width: 120px;">Tanggal</th>
                        <th style="padding: 12px; text-align: center; border: 1px solid #218838; width: 120px;">Kode Akun</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #218838;">Nama Akun</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #218838; width: 150px;">Debit</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #218838; width: 150px;">Kredit</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # ✅ GUNAKAN TANGGAL YANG BENAR (akhir periode, bukan tanggal saat ini)
        formatted_date = formatted_correct_date
        
        # Tampilkan akun yang memiliki saldo SETELAH penyesuaian
        accounts_with_balance = [item for item in adjusted_trial_balance_data if item['debit_after'] > 0 or item['credit_after'] > 0]
        
        for item in accounts_with_balance:
            # Pakai saldo SETELAH penyesuaian
            debit_display = item['debit_after']
            credit_display = item['credit_after']
            
            adjusted_table_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; font-weight: bold;">
                    {formatted_date}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; font-family: 'Courier New', monospace; font-weight: bold; background: #f8f9fa;">
                    {item['account_code']}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">
                    {item['account_name']}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                    {format_currency(debit_display) if debit_display > 0 else '-'}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                    {format_currency(credit_display) if credit_display > 0 else '-'}
                </td>
            </tr>
            """
        
        # Baris TOTAL
        adjusted_table_html += f"""
                </tbody>
                <tfoot>
                    <tr style="background: #e9ecef; font-weight: bold; border-top: 3px solid #28a745;">
                        <td colspan="3" style="padding: 15px; border: 1px solid #dee2e6; text-align: center; font-size: 16px;">
                            TOTAL NERACA SALDO SETELAH PENYESUAIAN
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-size: 16px;">
                            {format_currency(summary['total_debit_after'])}
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-size: 16px;">
                            {format_currency(summary['total_credit_after'])}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
        """
        
        # Status balance SETELAH penyesuaian
        if accounts_with_balance:
            balance_status = "✅ NERACA SEIMBANG" if summary['is_balanced_after'] else f"❌ NERACA TIDAK SEIMBANG"
            balance_color = "#28a745" if summary['is_balanced_after'] else "#dc3545"
            
            adjusted_table_html += f"""
            <div style="margin-top: 20px; padding: 20px; background: {balance_color}; color: white; border-radius: 8px; text-align: center; font-weight: bold; font-size: 16px;">
                {balance_status}
                {f'<div style="margin-top: 10px; font-size: 14px;">Selisih: {format_currency(abs(summary["difference_after"]))}</div>' if not summary['is_balanced_after'] else ''}
            </div>
            """
    else:
        adjusted_table_html = """
        <div style="text-align: center; padding: 60px; color: #666;">
            <div style="font-size: 64px; margin-bottom: 20px;">📊</div>
            <h3>Belum Ada Data</h3>
            <p>Belum ada data neraca saldo setelah penyesuaian untuk periode ini</p>
            <div style="margin-top: 20px;">
                <a href="/jurnal_penyesuaian">
                    <button style="margin: 5px; background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📝 Buat Jurnal Penyesuaian
                    </button>
                </a>
            </div>
        </div>
        """
    
    # Summary informasi
    accounts_count = len(adjusted_trial_balance_data) if adjusted_trial_balance_data else 0
    active_accounts = len([item for item in adjusted_trial_balance_data if item['debit_after'] > 0 or item['credit_after'] > 0]) if adjusted_trial_balance_data else 0
    
    summary_html = f"""
    <div style="background: linear-gradient(135deg, #28a745, #20c997); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; text-align: center;">
            <div>
                <div style="font-size: 24px; font-weight: bold;">{active_accounts}</div>
                <div style="font-size: 14px; opacity: 0.9;">Akun Aktif</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_debit_after'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Debit</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_credit_after'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Kredit</div>
            </div>
        </div>
        <div style="text-align: center; margin-top: 10px; font-size: 14px; opacity: 0.9;">
            Periode: {period} | Tanggal: {formatted_correct_date}
        </div>
    </div>
    """ if adjusted_trial_balance_data and active_accounts > 0 else ""

    content = f"""
    <div class="welcome-section">
        <h2>📊 Neraca Saldo Setelah Penyesuaian</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan saldo akhir setiap akun SETELAH dilakukan penyesuaian. 
            Format tabel sama persis dengan neraca saldo sebelum penyesuaian, hanya perhitungannya yang berbeda.
            <br><strong>📅 Tanggal: {formatted_correct_date} (Akhir Periode)</strong>
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #28a745; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #28a745; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    {summary_html}

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Neraca Saldo Setelah Penyesuaian - Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <a href="/nssp">
                    <button style="background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📊 Lihat Sebelum Penyesuaian
                    </button>
                </a>
                <a href="/jurnal_penyesuaian">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📝 Jurnal Penyesuaian
                    </button>
                </a>
                <button onclick="printReport()" style="background: #ffc107; color: #212529; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                    🖨️ Cetak Laporan
                </button>
            </div>
        </div>
        
        {adjusted_table_html}
        
        {f'<div style="margin-top: 15px; text-align: center; color: #666; font-size: 14px;">Menampilkan {active_accounts} akun | Tanggal: {formatted_correct_date}</div>' if adjusted_trial_balance_data else ''}
    </div>

    <!-- Informasi Penting -->
    <div class="quick-actions">
        <h3>💡 Informasi Penting</h3>
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4 style="color: #008DD8; margin-bottom: 10px;">📅 Penjelasan Tanggal</h4>
                    <ul style="text-align: left; color: #666;">
                        <li><strong>Tanggal {formatted_correct_date}</strong> adalah akhir periode laporan</li>
                        <li>Menunjukkan posisi saldo akun pada akhir periode</li>
                        <li>Bukan tanggal saat laporan dibuat/dicetak</li>
                        <li>Konsisten dengan periode yang dipilih ({period})</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: #28a745; margin-bottom: 10px;">✅ Validasi NSSP</h4>
                    <ul style="text-align: left; color: #666;">
                        <li>Total Debit harus sama dengan Total Kredit</li>
                        <li>Sudah termasuk penyesuaian dari jurnal penyesuaian</li>
                        <li>Digunakan untuk menyusun laporan keuangan</li>
                        <li>Verifikasi di menu Jurnal Penyesuaian terlebih dahulu</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
            
            .welcome-section {{
                display: none;
            }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printReport() {{
            window.print();
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    this.style.backgroundColor = '';
                }});
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 📋 14. NERACA LAJUR
# ============================================================

def get_worksheet_data(period=None):
    """Ambil data untuk neraca lajur - menggabungkan data sebelum dan setelah penyesuaian"""
    try:
        if not period:
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating worksheet data for period: {period}")
        
        # 1. Ambil neraca saldo SEBELUM penyesuaian
        trial_balance_before = calculate_trial_balance(period)
        
        # 2. Ambil jurnal penyesuaian untuk periode yang sama
        adjusting_journals = get_adjusting_journals_with_entries(period)
        
        # 3. Hitung neraca saldo SETELAH penyesuaian
        adjusted_trial_balance = get_adjusted_trial_balance(period)
        
        # 4. Klasifikasikan akun untuk laba rugi dan neraca
        worksheet_data = []
        
        # Mapping untuk data sebelum penyesuaian
        before_map = {item['account_code']: item for item in trial_balance_before}
        
        # Mapping untuk data setelah penyesuaian  
        after_map = {item['account_code']: item for item in adjusted_trial_balance}
        
        # Gabungkan semua akun yang ada
        all_accounts = set(before_map.keys()).union(set(after_map.keys()))
        
        for account_code in sorted(all_accounts):
            # Data sebelum penyesuaian
            before_data = before_map.get(account_code, {
                'debit': 0, 'credit': 0, 'account_name': get_account_name(account_code),
                'account_type': 'Unknown'
            })
            
            # Data setelah penyesuaian
            after_data = after_map.get(account_code, {
                'debit_after': 0, 'credit_after': 0, 'account_name': get_account_name(account_code),
                'account_type': 'Unknown'
            })
            
            # Tentukan apakah akun termasuk laba rugi atau neraca
            account_type = before_data.get('account_type', after_data.get('account_type', 'Unknown'))
            is_income_statement = account_type in ['Pendapatan', 'Beban', 'Harga Pokok Penjualan']
            is_balance_sheet = account_type in ['Aktiva Lancar', 'Aktiva Tetap', 'Kewajiban', 'Modal']
            
            # Hitung untuk kolom laba rugi dan neraca
            if is_income_statement:
                if account_type == 'Pendapatan':
                    # Pendapatan di kredit (positif) di laba rugi
                    laba_rugi_debit = 0
                    laba_rugi_credit = after_data.get('credit_after', 0)
                else:  # Beban atau HPP
                    # Beban dan HPP di debit (positif) di laba rugi
                    laba_rugi_debit = after_data.get('debit_after', 0)
                    laba_rugi_credit = 0
                
                # Untuk akun laba rugi, neraca = 0
                neraca_debit = 0
                neraca_credit = 0
            else:
                # Untuk akun neraca
                laba_rugi_debit = 0
                laba_rugi_credit = 0
                neraca_debit = after_data.get('debit_after', 0)
                neraca_credit = after_data.get('credit_after', 0)
            
            worksheet_data.append({
                'account_code': account_code,
                'account_name': before_data.get('account_name', get_account_name(account_code)),
                'account_type': account_type,
                'neraca_saldo_debit': before_data.get('debit', 0),
                'neraca_saldo_credit': before_data.get('credit', 0),
                'penyesuaian_debit': 0,  # Akan diisi dari jurnal penyesuaian
                'penyesuaian_credit': 0, # Akan diisi dari jurnal penyesuaian
                'nssp_debit': after_data.get('debit_after', 0),
                'nssp_credit': after_data.get('credit_after', 0),
                'laba_rugi_debit': laba_rugi_debit,
                'laba_rugi_credit': laba_rugi_credit,
                'neraca_debit': neraca_debit,
                'neraca_credit': neraca_credit,
                'is_income_statement': is_income_statement,
                'is_balance_sheet': is_balance_sheet
            })
        
        # 5. Isi data penyesuaian dari jurnal penyesuaian
        for journal in adjusting_journals:
            for entry in journal.get('entries', []):
                account_code = entry['account_code']
                amount = entry['amount']
                
                # Cari akun dalam worksheet data
                for item in worksheet_data:
                    if item['account_code'] == account_code:
                        if entry['position'] == 'debit':
                            item['penyesuaian_debit'] += amount
                        else:
                            item['penyesuaian_credit'] += amount
                        break
        
        logger.info(f"✅ Worksheet data calculated: {len(worksheet_data)} accounts")
        return worksheet_data
        
    except Exception as e:
        logger.error(f"❌ Error calculating worksheet data: {e}")
        logger.error(traceback.format_exc())
        return []

def get_worksheet_totals(worksheet_data):
    """Hitung total untuk setiap kolom dalam neraca lajur"""
    try:
        totals = {
            'neraca_saldo_debit': sum(item['neraca_saldo_debit'] for item in worksheet_data),
            'neraca_saldo_credit': sum(item['neraca_saldo_credit'] for item in worksheet_data),
            'penyesuaian_debit': sum(item['penyesuaian_debit'] for item in worksheet_data),
            'penyesuaian_credit': sum(item['penyesuaian_credit'] for item in worksheet_data),
            'nssp_debit': sum(item['nssp_debit'] for item in worksheet_data),
            'nssp_credit': sum(item['nssp_credit'] for item in worksheet_data),
            'laba_rugi_debit': sum(item['laba_rugi_debit'] for item in worksheet_data),
            'laba_rugi_credit': sum(item['laba_rugi_credit'] for item in worksheet_data),
            'neraca_debit': sum(item['neraca_debit'] for item in worksheet_data),
            'neraca_credit': sum(item['neraca_credit'] for item in worksheet_data)
        }
        
        # Hitung laba/rugi
        laba_rugi = totals['laba_rugi_credit'] - totals['laba_rugi_debit']
        if laba_rugi >= 0:
            totals['laba_rugi_credit_final'] = laba_rugi
            totals['laba_rugi_debit_final'] = 0
            totals['neraca_credit_final'] = totals['neraca_credit'] + laba_rugi
            totals['neraca_debit_final'] = totals['neraca_debit']
        else:
            totals['laba_rugi_credit_final'] = 0
            totals['laba_rugi_debit_final'] = abs(laba_rugi)
            totals['neraca_credit_final'] = totals['neraca_credit']
            totals['neraca_debit_final'] = totals['neraca_debit'] + abs(laba_rugi)
        
        # Total akhir setelah laba/rugi
        totals['laba_rugi_debit_total'] = totals['laba_rugi_debit'] + totals['laba_rugi_debit_final']
        totals['laba_rugi_credit_total'] = totals['laba_rugi_credit'] + totals['laba_rugi_credit_final']
        totals['neraca_debit_total'] = totals['neraca_debit'] + totals['laba_rugi_debit_final']
        totals['neraca_credit_total'] = totals['neraca_credit'] + totals['laba_rugi_credit_final']
        
        return totals
        
    except Exception as e:
        logger.error(f"❌ Error calculating worksheet totals: {e}")
        return {}

def correct_worksheet_allocation(account_type, account_name):
    """
    Alokasi yang benar untuk neraca lajur
    Pastikan HPP dan beban penyusutan masuk ke Laporan Laba Rugi, bukan Neraca
    """
    # Akun yang harus di Laba Rugi (Income Statement)
    income_statement_keywords = [
        'Harga Pokok Penjualan', 'HPP',
        'Beban Penyusutan', 'Penyusutan',
        'Beban Gaji', 'Beban Listrik', 'Beban Air', 
        'Beban Obat', 'Beban Pemeliharaan', 'Beban Perlengkapan',
        'Beban Sewa', 'Beban Asuransi', 'Beban Iklan', 'Beban Administrasi',
        'Penjualan', 'Pendapatan'
    ]
    
    # Cek berdasarkan keyword di nama akun
    account_name_upper = account_name.upper()
    for keyword in income_statement_keywords:
        if keyword.upper() in account_name_upper:
            return 'LABA_RUGI'
    
    # Cek berdasarkan tipe akun
    if account_type in ['Pendapatan', 'Beban', 'Harga Pokok Penjualan']:
        return 'LABA_RUGI'
    else:
        return 'NERACA'
def ensure_hpp_and_depreciation_accounts():
    """Pastikan akun HPP dan penyusutan ada di Chart of Accounts"""
    try:
        accounts = get_chart_of_accounts()
        
        # Cek akun HPP
        hpp_exists = any(acc['account_code'] == '5-1100' for acc in accounts)
        if not hpp_exists:
            # Tambahkan akun HPP
            hpp_data = {
                "account_code": "5-1100",
                "account_name": "Harga Pokok Penjualan",
                "account_type": "Beban", 
                "category": "Cost of Goods Sold"
            }
            add_account_to_chart(hpp_data)
            logger.info("✅ HPP account added to Chart of Accounts")
        
        # Cek akun beban penyusutan
        depreciation_exists = any('Penyusutan' in acc['account_name'] for acc in accounts)
        if not depreciation_exists:
            # Tambahkan akun beban penyusutan
            dep_data = {
                "account_code": "5-5100", 
                "account_name": "Beban Penyusutan Kendaraan",
                "account_type": "Beban",
                "category": "Operating Expense"
            }
            add_account_to_chart(dep_data)
            logger.info("✅ Depreciation account added to Chart of Accounts")
            
    except Exception as e:
        logger.error(f"❌ Error ensuring HPP and depreciation accounts: {e}")

def validate_worksheet_allocation(worksheet_data):
    """
    Validasi dan koreksi alokasi worksheet data
    Memastikan HPP dan beban penyusutan tidak salah masuk ke neraca
    """
    corrected_data = []
    
    for item in worksheet_data:
        account_name = item['account_name']
        account_type = item['account_type']
        account_code = item['account_code']
        
        # Tentukan alokasi yang benar
        correct_allocation = correct_worksheet_allocation(account_type, account_name)
        
        # Jika akun seharusnya di laba rugi tapi saat ini di neraca, koreksi
        if correct_allocation == 'LABA_RUGI':
            item['is_income_statement'] = True
            item['is_balance_sheet'] = False
            
            # Untuk akun laba rugi, set neraca = 0
            if account_type == 'Pendapatan':
                item['laba_rugi_debit'] = 0
                item['laba_rugi_credit'] = item['nssp_credit']
                item['neraca_debit'] = 0
                item['neraca_credit'] = 0
            else:  # Beban atau HPP
                item['laba_rugi_debit'] = item['nssp_debit']
                item['laba_rugi_credit'] = 0
                item['neraca_debit'] = 0
                item['neraca_credit'] = 0
                
        else:  # Neraca accounts
            item['is_income_statement'] = False
            item['is_balance_sheet'] = True
            item['laba_rugi_debit'] = 0
            item['laba_rugi_credit'] = 0
            item['neraca_debit'] = item['nssp_debit']
            item['neraca_credit'] = item['nssp_credit']
        
        corrected_data.append(item)
    
    return corrected_data

@app.route("/neraca_lajur")
@admin_required
def neraca_lajur():
    """Halaman Neraca Lajur (Worksheet) dengan format sesuai gambar"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Ambil data untuk neraca lajur
    worksheet_data = get_worksheet_data(period)
    totals = get_worksheet_totals(worksheet_data)
    
    worksheet_data = validate_worksheet_allocation(worksheet_data)
    
    totals = get_worksheet_totals(worksheet_data)

    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel neraca lajur sesuai format gambar
    worksheet_html = ""
    
    if worksheet_data:
        worksheet_html = f"""
        <div style="overflow-x: auto; margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse; font-size: 12px; min-width: 1200px;">
                <thead>
                    <tr style="background: #008DD8; color: white;">
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center; width: 100px;" rowspan="2">No. Akun</th>
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center; width: 150px;" rowspan="2">Nama Akun</th>
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center;" colspan="2">Neraca Saldo</th>
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center;" colspan="2">Penyesuaian</th>
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center;" colspan="2">NS Setelah Penyesuaian</th>
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center;" colspan="2">Laba Rugi</th>
                        <th style="padding: 10px; border: 2px solid #007bff; text-align: center;" colspan="2">Neraca</th>
                    </tr>
                    <tr style="background: #008DD8; color: white;">
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Debit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Kredit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Debit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Kredit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Debit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Kredit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Debit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Kredit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Debit</th>
                        <th style="padding: 8px; border: 1px solid #007bff; text-align: center; width: 120px;">Kredit</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Tampilkan data akun
        for item in worksheet_data:
            # Hanya tampilkan akun yang memiliki saldo di salah satu kolom
            has_balance = (item['neraca_saldo_debit'] > 0 or item['neraca_saldo_credit'] > 0 or
                          item['penyesuaian_debit'] > 0 or item['penyesuaian_credit'] > 0 or
                          item['nssp_debit'] > 0 or item['nssp_credit'] > 0 or
                          item['laba_rugi_debit'] > 0 or item['laba_rugi_credit'] > 0 or
                          item['neraca_debit'] > 0 or item['neraca_credit'] > 0)
            
            if has_balance:
                worksheet_html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: center; font-weight: bold; background: #f8f9fa;">
                        {item['account_code']}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; font-weight: bold;">
                        {item['account_name']}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(item['neraca_saldo_debit']) if item['neraca_saldo_debit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(item['neraca_saldo_credit']) if item['neraca_saldo_credit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(item['penyesuaian_debit']) if item['penyesuaian_debit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(item['penyesuaian_credit']) if item['penyesuaian_credit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(item['nssp_debit']) if item['nssp_debit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(item['nssp_credit']) if item['nssp_credit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(item['laba_rugi_debit']) if item['laba_rugi_debit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(item['laba_rugi_credit']) if item['laba_rugi_credit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                        {format_currency(item['neraca_debit']) if item['neraca_debit'] > 0 else ''}
                    </td>
                    <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                        {format_currency(item['neraca_credit']) if item['neraca_credit'] > 0 else ''}
                    </td>
                </tr>
                """
        
        # Baris JUMLAH
        worksheet_html += f"""
                <tr style="background: #e9ecef; font-weight: bold;">
                    <td colspan="2" style="padding: 12px; border: 2px solid #dee2e6; text-align: center;">
                        Jumlah
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['neraca_saldo_debit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['neraca_saldo_credit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['penyesuaian_debit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['penyesuaian_credit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['nssp_debit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['nssp_credit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['laba_rugi_debit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['laba_rugi_credit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['neraca_debit'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['neraca_credit'])}
                    </td>
                </tr>
        """
        
        # Baris LABA/RUGI
        laba_rugi_text = "Laba" if totals['laba_rugi_credit_final'] > 0 else "Rugi"
        laba_rugi_amount = totals['laba_rugi_credit_final'] if totals['laba_rugi_credit_final'] > 0 else totals['laba_rugi_debit_final']
        
        worksheet_html += f"""
                <tr style="background: #fff3cd; font-weight: bold;">
                    <td colspan="8" style="padding: 12px; border: 2px solid #dee2e6; text-align: center;">
                        {laba_rugi_text}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['laba_rugi_debit_final']) if totals['laba_rugi_debit_final'] > 0 else ''}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['laba_rugi_credit_final']) if totals['laba_rugi_credit_final'] > 0 else ''}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['laba_rugi_debit_final']) if totals['laba_rugi_debit_final'] > 0 else ''}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['laba_rugi_credit_final']) if totals['laba_rugi_credit_final'] > 0 else ''}
                    </td>
                </tr>
        """
        
        # Baris JUMLAH setelah laba/rugi
        worksheet_html += f"""
                <tr style="background: #d4edda; font-weight: bold;">
                    <td colspan="8" style="padding: 12px; border: 2px solid #dee2e6; text-align: center;">
                        Jumlah
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['laba_rugi_debit_total'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['laba_rugi_credit_total'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #dc3545;">
                        {format_currency(totals['neraca_debit_total'])}
                    </td>
                    <td style="padding: 12px; border: 2px solid #dee2e6; text-align: right; color: #28a745;">
                        {format_currency(totals['neraca_credit_total'])}
                    </td>
                </tr>
        """
        
        worksheet_html += """
                </tbody>
            </table>
        </div>
        """
    else:
        worksheet_html = """
        <div style="text-align: center; padding: 60px; color: #666;">
            <div style="font-size: 64px; margin-bottom: 20px;">📊</div>
            <h3>Belum Ada Data Neraca Lajur</h3>
            <p>Belum ada data transaksi untuk periode ini</p>
            <div style="margin-top: 20px;">
                <a href="/input_transaksi">
                    <button style="margin: 5px; background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📝 Input Transaksi
                    </button>
                </a>
                <a href="/jurnal_penyesuaian">
                    <button style="margin: 5px; background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📝 Jurnal Penyesuaian
                    </button>
                </a>
            </div>
        </div>
        """
    
    content = f"""
    <div class="welcome-section">
        <h2>📊 Neraca Lajur (Worksheet)</h2>
        <div class="welcome-message">
            Laporan neraca lajur yang menggabungkan neraca saldo, penyesuaian, dan menghasilkan laporan laba rugi serta neraca.
            Format mengikuti standar akuntansi dengan kolom-kolom lengkap.
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Neraca Lajur</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Neraca Lajur
                </button>
            </div>
        </form>
    </div>

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Neraca Lajur Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <a href="/nssp">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📊 Sebelum Penyesuaian
                    </button>
                </a>
                <a href="/neraca_saldo_setelah_penyesuaian">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📊 Setelah Penyesuaian
                    </button>
                </a>
                <button onclick="printWorksheet()" style="background: #28a745; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                    🖨️ Cetak Laporan
                </button>
            </div>
        </div>
        
        {worksheet_html}
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            table {{
                font-size: 10px;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printWorksheet() {{
            window.print();
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    if (!this.style.backgroundColor.includes('background')) {{
                        this.style.backgroundColor = '';
                    }}
                }});
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 📈 15. LAPORAN LABA RUGI
# ============================================================

@app.route("/laporan_laba_rugi")
@admin_required
def laporan_laba_rugi():
    """Halaman Laporan Laba Rugi"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Ambil data laba rugi
    income_data = get_income_statement_data(period)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel laba rugi
    income_statement_html = ""
    
    if income_data['income_accounts'] or income_data['expense_accounts']:
        income_statement_html = f"""
        <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #008DD8; margin-bottom: 5px;">LAPORAN LABA RUGI</h2>
                <h3 style="color: #666; margin-top: 0;">Periode {period}</h3>
            </div>
            
            <!-- Pendapatan -->
            <div style="margin-bottom: 20px;">
                <h3 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 10px;">PENDAPATAN</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tbody>
        """

        # Tampilkan pendapatan
        for item in income_data['income_accounts']:
            if item['amount'] > 0:
                income_statement_html += f"""
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #28a745; font-weight: bold;">
                                {format_currency(item['amount'])}
                            </td>
                        </tr>
                """

        income_statement_html += f"""
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; border-top: 2px solid #28a745;">Total Pendapatan</td>
                            <td style="padding: 12px; text-align: right; font-weight: bold; border-top: 2px solid #28a745; color: #28a745;">
                                {format_currency(income_data['total_pendapatan'])}
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <!-- HPP -->
            <div style="margin-bottom: 20px;">
                <h3 style="color: #dc3545; border-bottom: 2px solid #dc3545; padding-bottom: 10px;">HARGA POKOK PENJUALAN</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tbody>
        """

        # Tampilkan HPP
        for item in income_data['hpp_accounts']:
            if item['amount'] > 0:
                income_statement_html += f"""
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #dc3545; font-weight: bold;">
                                {format_currency(item['amount'])}
                            </td>
                        </tr>
                """

        income_statement_html += f"""
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; border-top: 2px solid #dc3545;">Total HPP</td>
                            <td style="padding: 12px; text-align: right; font-weight: bold; border-top: 2px solid #dc3545; color: #dc3545;">
                                {format_currency(income_data['total_hpp'])}
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Laba Kotor -->
            <div style="margin-bottom: 20px; background: #e7f3ff; padding: 15px; border-radius: 5px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 16px;">
                    <tbody>
                        <tr>
                            <td style="padding: 12px; font-weight: bold; color: #008DD8;">Laba Kotor</td>
                            <td style="padding: 12px; text-align: right; font-weight: bold; color: #008DD8;">
                                {format_currency(income_data['laba_kotor'])}
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Beban Operasional -->
            <div style="margin-bottom: 20px;">
                <h3 style="color: #ff6b35; border-bottom: 2px solid #ff6b35; padding-bottom: 10px;">BEBAN OPERASIONAL</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tbody>
        """

        # Tampilkan beban operasional
        for item in income_data['expense_accounts']:
            if item['amount'] > 0:
                income_statement_html += f"""
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #ff6b35; font-weight: bold;">
                                {format_currency(item['amount'])}
                            </td>
                        </tr>
                """

        income_statement_html += f"""
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; border-top: 2px solid #ff6b35;">Total Beban Operasional</td>
                            <td style="padding: 12px; text-align: right; font-weight: bold; border-top: 2px solid #ff6b35; color: #ff6b35;">
                                {format_currency(income_data['total_beban'])}
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Laba Rugi Bersih -->
            <div style="background: {'#d4edda' if income_data['is_profit'] else '#f8d7da'}; padding: 20px; border-radius: 8px; text-align: center;">
                <h2 style="color: {'#155724' if income_data['is_profit'] else '#721c24'}; margin: 0;">
                    {'LABA BERSIH' if income_data['is_profit'] else 'RUGI BERSIH'}: {format_currency(abs(income_data['laba_rugi_bersih']))}
                </h2>
            </div>
        </div>
        """
    else:
        income_statement_html = """
        <div style="text-align: center; padding: 60px; color: #666;">
            <div style="font-size: 64px; margin-bottom: 20px;">📊</div>
            <h3>Belum Ada Data Laporan Laba Rugi</h3>
            <p>Belum ada data transaksi untuk periode ini</p>
            <div style="margin-top: 20px;">
                <a href="/input_transaksi">
                    <button style="margin: 5px; background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📝 Input Transaksi
                    </button>
                </a>
            </div>
        </div>
        """

    content = f"""
    <div class="welcome-section">
        <h2>📈 Laporan Laba Rugi</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan kinerja keuangan perusahaan dalam suatu periode. 
            Menampilkan pendapatan, beban, dan laba/rugi bersih.
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Laporan Laba Rugi Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <button onclick="printReport()" style="background: #28a745; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                    🖨️ Cetak Laporan
                </button>
                <a href="/neraca_lajur">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📊 Neraca Lajur
                    </button>
                </a>
            </div>
        </div>
        
        {income_statement_html}
    </div>

    <style>
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
            
            .welcome-section {{
                display: none;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printReport() {{
            window.print();
        }}
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 📊 16. LAPORAN PERUBAHAN MODAL
# ============================================================
@app.route("/laporan_perubahan_modal")
@admin_required
def laporan_perubahan_modal():
    """Halaman Laporan Perubahan Modal - VERSI DIPERBAIKI DENGAN NAMA AKUN"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Ambil data perubahan modal dengan fungsi yang sudah diperbaiki
    equity_data = get_equity_statement_data(period)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel perubahan modal YANG SUDAH DIPERBAIKI
    equity_statement_html = f"""
    <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <h2 style="color: #008DD8; margin-bottom: 5px;">LAPORAN PERUBAHAN MODAL</h2>
            <h3 style="color: #666; margin-top: 0;">Periode {period}</h3>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; font-size: 16px; margin-bottom: 20px;">
            <tbody>
                <tr>
                    <td style="padding: 15px; border-bottom: 2px solid #eee; width: 70%; font-weight: bold; font-size: 18px;">
                        {equity_data['modal_account_name']}
                    </td>
                    <td style="padding: 15px; border-bottom: 2px solid #eee; text-align: right; width: 30%; color: #008DD8; font-weight: bold; font-size: 18px;">
                        {format_currency(equity_data['modal_awal'])}
                    </td>
                </tr>
                
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; width: 70%;">
                        {equity_data['laba_rugi_account_name']}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: {'#28a745' if equity_data['laba_rugi_bersih'] >= 0 else '#dc3545'}; font-weight: bold;">
                        {format_currency(equity_data['laba_rugi_bersih'])}
                    </td>
                </tr>

                {f'''
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; width: 70%;">
                        {equity_data['prive_account_name']}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #dc3545; font-weight: bold;">
                        ({format_currency(equity_data['prive'])})
                    </td>
                </tr>
                ''' if equity_data['prive'] > 0 else ''}

                {f'''
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; width: 70%;">
                        {equity_data['investasi_account_name']}
                    </td>
                    <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #28a745; font-weight: bold;">
                        {format_currency(equity_data['investasi_tambahan'])}
                    </td>
                </tr>
                ''' if equity_data['investasi_tambahan'] > 0 else ''}

                <tr style="background: #e9ecef;">
                    <td style="padding: 20px; font-weight: bold; border-top: 3px solid #008DD8; font-size: 20px;">
                        Modal Akhir
                    </td>
                    <td style="padding: 20px; text-align: right; font-weight: bold; border-top: 3px solid #008DD8; color: #008DD8; font-size: 20px;">
                        {format_currency(equity_data['modal_akhir'])}
                    </td>
                </tr>
            </tbody>
        </table>
        
        <div style="background: #e7f3ff; padding: 15px; border-radius: 8px; margin-top: 20px;">
            <h4 style="color: #008DD8; margin-bottom: 10px;">📝 Rumus Perhitungan:</h4>
            <p style="color: #666; margin: 5px 0;">
                <strong>Modal Akhir = Modal Awal + Laba/Rugi Bersih - Prive + Investasi Tambahan</strong>
            </p>
            <p style="color: #666; margin: 5px 0; font-size: 14px;">
                {format_currency(equity_data['modal_awal'])} + {format_currency(equity_data['laba_rugi_bersih'])} - {format_currency(equity_data['prive'])} + {format_currency(equity_data['investasi_tambahan'])} = {format_currency(equity_data['modal_akhir'])}
            </p>
        </div>
    </div>
    """

    content = f"""
    <div class="welcome-section">
        <h2>📊 Laporan Perubahan Modal</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan perubahan modal perusahaan dalam suatu periode. 
            Menampilkan modal awal, laba/rugi, prive, investasi tambahan, dan modal akhir.
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Laporan Perubahan Modal Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <button onclick="printReport()" style="background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold;">
                    🖨️ Cetak Laporan
                </button>
                <a href="/laporan_laba_rugi?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📈 Laba Rugi
                    </button>
                </a>
                <a href="/laporan_posisi_keuangan?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        💰 Posisi Keuangan
                    </button>
                </a>
            </div>
        </div>
        
        {equity_statement_html}
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
            
            .welcome-section {{
                display: none;
            }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 14px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printReport() {{
            window.print();
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    this.style.backgroundColor = '';
                }});
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 💰 17. LAPORAN POSISI KEUANGAN
# ============================================================
@app.route("/laporan_posisi_keuangan")
@admin_required
def laporan_posisi_keuangan():
    """Halaman Laporan Posisi Keuangan (Neraca)"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Ambil data neraca
    balance_data = get_balance_sheet_data(period)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel neraca dengan akumulasi penyusutan
    balance_sheet_html = ""
    
    balance_sheet_html = f"""
    <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <h2 style="color: #008DD8; margin-bottom: 5px;">LAPORAN POSISI KEUANGAN</h2>
            <h3 style="color: #666; margin-top: 0;">Periode {period}</h3>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
            <!-- AKTIVA -->
            <div>
                <h3 style="color: #008DD8; border-bottom: 2px solid #008DD8; padding-bottom: 10px;">AKTIVA</h3>
                
                <!-- Aktiva Lancar -->
                <div style="margin-bottom: 20px;">
                    <h4 style="color: #0056b3; margin-bottom: 10px;">Aktiva Lancar</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tbody>
    """
    
    # Tampilkan aktiva lancar
    for item in balance_data['aktiva_lancar']:
        if item['amount'] > 0:
            balance_sheet_html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #008DD8; font-weight: bold;">
                                    {format_currency(item['amount'])}
                                </td>
                            </tr>
            """
    
    balance_sheet_html += f"""
                            <tr style="background: #f8f9fa;">
                                <td style="padding: 10px; font-weight: bold;">Total Aktiva Lancar</td>
                                <td style="padding: 10px; text-align: right; font-weight: bold; color: #008DD8;">
                                    {format_currency(balance_data.get('total_aktiva_lancar', sum(item['amount'] for item in balance_data['aktiva_lancar'])))}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Aktiva Tetap -->
                <div style="margin-bottom: 20px;">
                    <h4 style="color: #0056b3; margin-bottom: 10px;">Aktiva Tetap</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tbody>
    """
    
    # Tampilkan aktiva tetap bruto
    for item in balance_data['aktiva_tetap']:
        if item['amount'] > 0:
            balance_sheet_html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #008DD8; font-weight: bold;">
                                    {format_currency(item['amount'])}
                                </td>
                            </tr>
            """
    
    # Tampilkan akumulasi penyusutan sebagai pengurang
    if balance_data.get('akumulasi_penyusutan'):
        balance_sheet_html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; width: 70%;">
                                    <em>Akumulasi Penyusutan:</em>
                                </td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #dc3545; font-weight: bold;">
                                    ({format_currency(balance_data.get('total_akumulasi_penyusutan', 0))})
                                </td>
                            </tr>
        """
        
        # Tampilkan detail akumulasi penyusutan
        for item in balance_data['akumulasi_penyusutan']:
            if item['amount'] > 0:
                balance_sheet_html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; width: 70%; padding-left: 20px; font-size: 12px; color: #666;">
                                    - {item['account_name']}
                                </td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #666; font-size: 12px;">
                                    ({format_currency(item['amount'])})
                                </td>
                            </tr>
                """
    
    # Tampilkan total aktiva tetap neto
    balance_sheet_html += f"""
                            <tr style="background: #f8f9fa;">
                                <td style="padding: 10px; font-weight: bold;">Total Aktiva Tetap (Neto)</td>
                                <td style="padding: 10px; text-align: right; font-weight: bold; color: #008DD8;">
                                    {format_currency(balance_data.get('total_aktiva_tetap_neto', sum(item['amount'] for item in balance_data['aktiva_tetap'])))}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Total Aktiva -->
                <div style="background: #e7f3ff; padding: 15px; border-radius: 5px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 16px;">
                        <tbody>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">TOTAL AKTIVA</td>
                                <td style="padding: 12px; text-align: right; font-weight: bold; color: #008DD8;">
                                    {format_currency(balance_data['total_aktiva'])}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            
            <!-- KEWAJIBAN & MODAL -->
            <div>
                <h3 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 10px;">KEWAJIBAN & MODAL</h3>
                
                <!-- Kewajiban -->
                <div style="margin-bottom: 20px;">
                    <h4 style="color: #218838; margin-bottom: 10px;">Kewajiban</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tbody>
    """
    
    # Tampilkan kewajiban
    for item in balance_data['kewajiban']:
        if item['amount'] > 0:
            balance_sheet_html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #28a745; font-weight: bold;">
                                    {format_currency(item['amount'])}
                                </td>
                            </tr>
            """
    
    balance_sheet_html += f"""
                            <tr style="background: #f8f9fa;">
                                <td style="padding: 10px; font-weight: bold;">Total Kewajiban</td>
                                <td style="padding: 10px; text-align: right; font-weight: bold; color: #28a745;">
                                    {format_currency(balance_data['total_kewajiban'])}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Modal -->
                <div style="margin-bottom: 20px;">
                    <h4 style="color: #218838; margin-bottom: 10px;">Modal</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tbody>
    """
    
    # Tampilkan modal
    for item in balance_data['modal']:
        if item['amount'] > 0:
            balance_sheet_html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; width: 70%;">{item['account_name']}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; width: 30%; color: #28a745; font-weight: bold;">
                                    {format_currency(item['amount'])}
                                </td>
                            </tr>
            """
    
    balance_sheet_html += f"""
                            <tr style="background: #f8f9fa;">
                                <td style="padding: 10px; font-weight: bold;">Total Modal</td>
                                <td style="padding: 10px; text-align: right; font-weight: bold; color: #28a745;">
                                    {format_currency(balance_data['total_modal'])}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- Total Kewajiban & Modal -->
                <div style="background: #e8f5e8; padding: 15px; border-radius: 5px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 16px;">
                        <tbody>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">TOTAL KEWAJIBAN & MODAL</td>
                                <td style="padding: 12px; text-align: right; font-weight: bold; color: #28a745;">
                                    {format_currency(balance_data['total_kewajiban_modal'])}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Status Balance -->
        <div style="margin-top: 20px; padding: 15px; background: {'#d4edda' if balance_data['is_balanced'] else '#f8d7da'}; border-radius: 8px; text-align: center;">
            <h4 style="color: {'#155724' if balance_data['is_balanced'] else '#721c24'}; margin: 0;">
                {'✅ NERACA SEIMBANG' if balance_data['is_balanced'] else '❌ NERACA TIDAK SEIMBANG'}
            </h4>
            {f'<p style="margin: 10px 0 0 0; font-size: 14px;">Selisih: {format_currency(abs(balance_data["total_aktiva"] - balance_data["total_kewajiban_modal"]))}</p>' if not balance_data['is_balanced'] else ''}
        </div>
        
        <!-- Informasi Akumulasi Penyusutan -->
        {f'''
        <div style="margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 8px;">
            <h4 style="color: #856404; margin-bottom: 10px;">💡 Informasi Akumulasi Penyusutan</h4>
            <p style="color: #856404; margin: 5px 0; font-size: 14px;">
                <strong>Aktiva Tetap Bruto:</strong> {format_currency(balance_data.get('total_aktiva_tetap_bruto', 0))}
            </p>
            <p style="color: #856404; margin: 5px 0; font-size: 14px;">
                <strong>Akumulasi Penyusutan:</strong> {format_currency(balance_data.get('total_akumulasi_penyusutan', 0))}
            </p>
            <p style="color: #856404; margin: 5px 0; font-size: 14px;">
                <strong>Aktiva Tetap Neto:</strong> {format_currency(balance_data.get('total_aktiva_tetap_neto', 0))}
            </p>
        </div>
        ''' if balance_data.get('akumulasi_penyusutan') else ''}
    </div>
    """

    content = f"""
    <div class="welcome-section">
        <h2>💰 Laporan Posisi Keuangan (Neraca)</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan posisi keuangan perusahaan pada tanggal tertentu. 
            Menampilkan aktiva, kewajiban, dan modal perusahaan.
            {"<br><strong>📝 Termasuk akumulasi penyusutan pada aktiva tetap</strong>" if balance_data.get('akumulasi_penyusutan') else ""}
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Laporan Posisi Keuangan Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <button onclick="printReport()" style="background: #28a745; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                    🖨️ Cetak Laporan
                </button>
                <a href="/laporan_perubahan_modal?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📊 Perubahan Modal
                    </button>
                </a>
                <a href="/neraca_saldo_setelah_penyesuaian?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📋 NS setelah Penyesuaian
                    </button>
                </a>
            </div>
        </div>
        
        {balance_sheet_html}
    </div>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printReport() {{
            window.print();
        }}
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 💸 18. LAPORAN ARUS KAS
# ============================================================
@app.route("/laporan_arus_kas")
@admin_required
def laporan_arus_kas():
    """Halaman Laporan Arus Kas - SESUAI GAMBAR PERTAMA"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Ambil data arus kas dengan fungsi yang sudah diperbaiki
    cash_flow_data = get_cash_flow_data(period)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    cash_flow_html = f"""
    <div style="background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);">
        <div style="text-align: center; margin-bottom: 30px;">
            <h2 style="color: #008DD8; margin-bottom: 5px;">LAPORAN ARUS KAS</h2>
            <h3 style="color: #666; margin-top: 0;">Periode {period}</h3>
            <p style="color: #888; font-size: 14px; margin-top: 5px;">
                Periode: {cash_flow_data['start_date']} hingga {cash_flow_data['end_date']}
            </p>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 20px;">
            <tbody>
                <!-- Arus Kas dari Aktivitas Operasi -->
                <tr>
                    <td colspan="2" style="padding: 15px; background: #e7f3ff; font-weight: bold; color: #008DD8; border: 1px solid #008DD8;">
                        ARUS KAS DARI AKTIVITAS OPERASI
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px; border: 1px solid #dee2e6; width: 70%;">Penerimaan Kas dari Pelanggan</td>
                    <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; width: 30%; color: #28a745; font-weight: bold;">
                        {format_currency(cash_flow_data['penerimaan_pelanggan'])}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px; border: 1px solid #dee2e6; width: 70%;">Pembayaran kepada Pemasok (persediaan & perlengkapan)</td>
                    <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; width: 30%; color: #dc3545; font-weight: bold;">
                        ({format_currency(cash_flow_data['pembayaran_pemasok'])})
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px; border: 1px solid #dee2e6; width: 70%;">Pembayaran Beban Operasional</td>
                    <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; width: 30%; color: #dc3545; font-weight: bold;">
                        ({format_currency(cash_flow_data['pembayaran_beban_operasional'])})
                    </td>
                </tr>
                <tr style="background: #f8f9fa;">
                    <td style="padding: 15px; border: 1px solid #dee2e6; font-weight: bold; font-size: 16px;">
                        <strong>Kas Bersih Digunakan untuk Aktivitas Operasi</strong>
                    </td>
                    <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; font-weight: bold; font-size: 16px; color: {'#28a745' if cash_flow_data['arus_kas_operasi'] >= 0 else '#dc3545'};">
                        <strong>{format_currency(cash_flow_data['arus_kas_operasi'])}</strong>
                    </td>
                </tr>
                
                <!-- Kas Awal dan Akhir Periode -->
                <tr>
                    <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; border-top: 2px solid #008DD8;">
                        Kas Awal Periode, 1 Des
                    </td>
                    <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; font-weight: bold; border-top: 2px solid #008DD8; color: #008DD8;">
                        {format_currency(cash_flow_data['kas_awal'])}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 12px; border: 1px solid #dee2e6; width: 70%;">Penurunan Kas Bersih</td>
                    <td style="padding: 12px; border: 1px solid #dee2e6; text-align: right; width: 30%; color: #dc3545; font-weight: bold;">
                        ({format_currency(abs(cash_flow_data['penurunan_kas_bersih']))})
                    </td>
                </tr>
                <tr style="background: #d4edda;">
                    <td style="padding: 15px; border: 1px solid #dee2e6; font-weight: bold; font-size: 16px; border-top: 2px solid #28a745;">
                        <strong>Kas Akhir Periode, 31 Des</strong>
                    </td>
                    <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; font-weight: bold; font-size: 16px; border-top: 2px solid #28a745; color: #155724;">
                        <strong>{format_currency(cash_flow_data['kas_akhir'])}</strong>
                    </td>
                </tr>
            </tbody>
        </table>
        
        <!-- Informasi Detail Transaksi -->
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin-top: 20px;">
            <h4 style="color: #008DD8; margin-bottom: 15px;">📊 Detail Analisis Transaksi</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div>
                    <h5 style="color: #28a745; margin-bottom: 10px;">💸 Penerimaan Kas</h5>
                    <p style="margin: 5px 0; font-size: 14px;">
                        <strong>Total Penerimaan dari Pelanggan:</strong><br>
                        {format_currency(cash_flow_data['penerimaan_pelanggan'])}
                    </p>
                    <p style="margin: 5px 0; font-size: 12px; color: #666;">
                        • Dari penjualan lele dan produk lainnya<br>
                        • Semua transaksi kas masuk dari pelanggan
                    </p>
                </div>
                <div>
                    <h5 style="color: #dc3545; margin-bottom: 10px;">🛒 Pengeluaran Kas</h5>
                    <p style="margin: 5px 0; font-size: 14px;">
                        <strong>Pembayaran ke Pemasok:</strong> {format_currency(cash_flow_data['pembayaran_pemasok'])}<br>
                        <strong>Beban Operasional:</strong> {format_currency(cash_flow_data['pembayaran_beban_operasional'])}
                    </p>
                    <p style="margin: 5px 0; font-size: 12px; color: #666;">
                        • Pembelian bibit, pakan, perlengkapan<br>
                        • Beban gaji, listrik, air, obat, perawatan
                    </p>
                </div>
            </div>
        </div>
    </div>
    """

    content = f"""
    <div class="welcome-section">
        <h2>💸 Laporan Arus Kas</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan arus kas masuk dan keluar perusahaan dalam suatu periode. 
            Disusun sesuai format standar dengan fokus pada aktivitas operasi.
            <br><strong>📅 Periode: {cash_flow_data['start_date']} hingga {cash_flow_data['end_date']}</strong>
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Laporan Arus Kas Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <button onclick="printReport()" style="background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold;">
                    🖨️ Cetak Laporan
                </button>
                <a href="/laporan_posisi_keuangan?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        💰 Posisi Keuangan
                    </button>
                </a>
                <a href="/jurnal_umum?start_date={cash_flow_data['start_date']}&end_date={cash_flow_data['end_date']}">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📋 Detail Jurnal
                    </button>
                </a>
            </div>
        </div>
        
        {cash_flow_html}
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid #dee2e6;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
            
            .welcome-section {{
                display: none;
            }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printReport() {{
            window.print();
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    this.style.backgroundColor = '';
                }});
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 🔹  FUNGSI LAPORAN KEUANGAN
# ============================================================

def get_income_statement_data(period=None):
    """Ambil data untuk Laporan Laba Rugi dari neraca lajur - VERSI DIPERBAIKI UNTUK JURNAL PENUTUP"""
    try:
        if not period:
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating income statement for JURNAL PENUTUP - period: {period}")
        
        # Ambil data dari neraca lajur
        worksheet_data = get_worksheet_data(period)
        
        if not worksheet_data:
            logger.warning(f"⚠️ No worksheet data found for period {period}")
            return {
                'period': period,
                'income_accounts': [],
                'hpp_accounts': [],
                'expense_accounts': [],
                'total_pendapatan': 0,
                'total_hpp': 0,
                'total_beban': 0,
                'total_semua_beban': 0,
                'laba_kotor': 0,
                'laba_rugi_bersih': 0,
                'is_profit': True
            }
        
        # Validasi alokasi - PASTIKAN semua akun laba rugi terdeteksi
        worksheet_data = validate_worksheet_allocation(worksheet_data)
        
        # Filter hanya akun laba rugi (Pendapatan, Beban, dan HPP)
        income_accounts = []
        hpp_accounts = []
        expense_accounts = []
        
        logger.info(f"🔍 Processing {len(worksheet_data)} accounts for income statement (JURNAL PENUTUP)")
        
        for item in worksheet_data:
            if item['is_income_statement']:
                account_code = item['account_code']
                account_name = item['account_name']
                account_type = item['account_type']
                laba_rugi_debit = item['laba_rugi_debit']
                laba_rugi_credit = item['laba_rugi_credit']
                
                # ✅ DETEKSI LEBIH AKURAT UNTUK JURNAL PENUTUP
                
                # PENDAPATAN (di credit - harus di DEBIT di jurnal penutup)
                if (account_type == 'Pendapatan' or 
                    'penjualan' in account_name.lower() or 
                    'pendapatan' in account_name.lower()) and laba_rugi_credit > 0:
                    income_accounts.append({
                        'account_code': account_code,
                        'account_name': account_name,
                        'amount': laba_rugi_credit
                    })
                    logger.info(f"💰 Pendapatan untuk Jurnal Penutup: {account_name} - {format_currency(laba_rugi_credit)}")
                
                # HPP (di debit - harus di DEBIT di jurnal penutup)
                elif (account_type == 'Harga Pokok Penjualan' or 
                      'hpp' in account_name.lower() or 
                      'harga pokok' in account_name.lower() or
                      account_code.startswith('5-1')) and laba_rugi_debit > 0:
                    hpp_accounts.append({
                        'account_code': account_code,
                        'account_name': account_name,
                        'amount': laba_rugi_debit
                    })
                    logger.info(f"📦 HPP untuk Jurnal Penutup: {account_name} - {format_currency(laba_rugi_debit)}")
                
                # BEBAN (di debit - harus di DEBIT di jurnal penutup)
                elif (account_type == 'Beban' or 
                      'beban' in account_name.lower() or
                      'biaya' in account_name.lower() or
                      account_code.startswith('5-') or 
                      account_code.startswith('6-')) and laba_rugi_debit > 0:
                    # Exclude HPP yang sudah ditangani
                    if not ('hpp' in account_name.lower() or 'harga pokok' in account_name.lower()):
                        expense_accounts.append({
                            'account_code': account_code,
                            'account_name': account_name,
                            'amount': laba_rugi_debit
                        })
                        logger.info(f"💸 Beban untuk Jurnal Penutup: {account_name} - {format_currency(laba_rugi_debit)}")
        
        # Jika tidak ada data, coba ambil dari neraca saldo setelah penyesuaian
        if not income_accounts and not hpp_accounts and not expense_accounts:
            logger.info("🔍 No data from worksheet, trying from adjusted trial balance...")
            nssp_data = get_adjusted_trial_balance(period)
            
            for item in nssp_data:
                account_name = item['account_name']
                account_type = item['account_type']
                
                # Pendapatan dari NSSP
                if (account_type == 'Pendapatan' or 'penjualan' in account_name.lower()) and item['credit_after'] > 0:
                    income_accounts.append({
                        'account_code': item['account_code'],
                        'account_name': account_name,
                        'amount': item['credit_after']
                    })
                
                # HPP dari NSSP
                elif (account_type == 'Harga Pokok Penjualan' or 'hpp' in account_name.lower()) and item['debit_after'] > 0:
                    hpp_accounts.append({
                        'account_code': item['account_code'],
                        'account_name': account_name,
                        'amount': item['debit_after']
                    })
                
                # Beban dari NSSP
                elif (account_type == 'Beban' or 'beban' in account_name.lower()) and item['debit_after'] > 0:
                    expense_accounts.append({
                        'account_code': item['account_code'],
                        'account_name': account_name,
                        'amount': item['debit_after']
                    })
        
        # Hitung total
        total_pendapatan = sum(item['amount'] for item in income_accounts)
        total_hpp = sum(item['amount'] for item in hpp_accounts)
        total_beban = sum(item['amount'] for item in expense_accounts)
        total_semua_beban = total_hpp + total_beban
        
        # Laba Kotor = Pendapatan - HPP
        laba_kotor = total_pendapatan - total_hpp
        # Laba Bersih = Laba Kotor - Beban Operasional
        laba_rugi_bersih = laba_kotor - total_beban
        
        logger.info(f"✅ Income Statement untuk JURNAL PENUTUP:")
        logger.info(f"   Pendapatan: {len(income_accounts)} akun, Total: {format_currency(total_pendapatan)}")
        logger.info(f"   HPP: {len(hpp_accounts)} akun, Total: {format_currency(total_hpp)}")
        logger.info(f"   Beban: {len(expense_accounts)} akun, Total: {format_currency(total_beban)}")
        logger.info(f"   Laba Kotor: {format_currency(laba_kotor)}")
        logger.info(f"   Laba/Rugi Bersih: {format_currency(laba_rugi_bersih)}")
        
        # Debug detail
        for acc in income_accounts:
            logger.info(f"   📈 Pendapatan: {acc['account_name']} = {format_currency(acc['amount'])}")
        for acc in hpp_accounts:
            logger.info(f"   📦 HPP: {acc['account_name']} = {format_currency(acc['amount'])}")
        for acc in expense_accounts:
            logger.info(f"   💸 Beban: {acc['account_name']} = {format_currency(acc['amount'])}")
        
        return {
            'period': period,
            'income_accounts': income_accounts,
            'hpp_accounts': hpp_accounts,
            'expense_accounts': expense_accounts,
            'total_pendapatan': total_pendapatan,
            'total_hpp': total_hpp,
            'total_beban': total_beban,
            'total_semua_beban': total_semua_beban,
            'laba_kotor': laba_kotor,
            'laba_rugi_bersih': laba_rugi_bersih,
            'is_profit': laba_rugi_bersih >= 0
        }
        
    except Exception as e:
        logger.error(f"❌ Error calculating income statement for JURNAL PENUTUP: {e}")
        logger.error(traceback.format_exc())
        return {
            'period': period,
            'income_accounts': [],
            'hpp_accounts': [],
            'expense_accounts': [],
            'total_pendapatan': 0,
            'total_hpp': 0,
            'total_beban': 0,
            'total_semua_beban': 0,
            'laba_kotor': 0,
            'laba_rugi_bersih': 0,
            'is_profit': True
        }

def get_balance_sheet_data(period=None):
    """Ambil data untuk Laporan Posisi Keuangan - DIPERBAIKI UNTUK AKUMULASI PENYUSUTAN"""
    try:
        if not period:
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating balance sheet for period: {period} with ACCUMULATED DEPRECIATION")
        
        # Ambil data dari neraca saldo SETELAH penyesuaian
        adjusted_trial_balance = get_adjusted_trial_balance(period)
        
        if not adjusted_trial_balance:
            logger.warning(f"⚠️ No adjusted trial balance data found for period {period}")
            return {
                'period': period,
                'aktiva_lancar': [],
                'aktiva_tetap': [],
                'akumulasi_penyusutan': [],
                'kewajiban': [],
                'modal': [],
                'total_aktiva': 0,
                'total_kewajiban': 0,
                'total_modal': 0,
                'total_kewajiban_modal': 0,
                'laba_rugi': 0,
                'is_balanced': True
            }
        
        # Klasifikasikan akun neraca
        aktiva_lancar = []
        aktiva_tetap = []
        akumulasi_penyusutan = []
        kewajiban = []
        modal = []
        
        for item in adjusted_trial_balance:
            account_code = item['account_code']
            account_name = item['account_name']
            account_type = item['account_type']
            
            # Gunakan saldo SETELAH penyesuaian
            debit_amount = item['debit_after']
            credit_amount = item['credit_after']
            
            # ✅ PERBAIKAN: Untuk akumulasi penyusutan, gunakan saldo kredit meskipun kecil
            is_accumulated_depreciation = (
                'akumulasi penyusutan' in account_name.lower() or 
                'accumulated depreciation' in account_name.lower() or
                'penyusutan' in account_name.lower() and 'akumulasi' in account_name.lower()
            )
            
            if is_accumulated_depreciation:
                # ✅ TAMPILKAN MESKIPUN SALDO KECIL - akumulasi penyusutan penting untuk ditampilkan
                amount = credit_amount  # Akumulasi penyusutan selalu di kredit
                account_data = {
                    'account_code': account_code,
                    'account_name': account_name,
                    'amount': amount
                }
                akumulasi_penyusutan.append(account_data)
                logger.info(f"✅ Found accumulated depreciation: {account_name} = {format_currency(amount)}")
                continue  # Skip ke akun berikutnya
            
            # Untuk akun lain, tentukan jumlah berdasarkan tipe akun
            if account_type in ['Aktiva Lancar', 'Aktiva Tetap', 'Beban']:
                # Akun debit normal - gunakan debit amount
                amount = debit_amount
            else:
                # Akun kredit normal - gunakan credit amount  
                amount = credit_amount
            
            # ✅ PERBAIKAN: Tampilkan akun yang memiliki saldo > 0 ATAU akun penting tertentu
            if amount > 0 or is_accumulated_depreciation:
                account_data = {
                    'account_code': account_code,
                    'account_name': account_name,
                    'amount': amount
                }
                
                # Klasifikasikan berdasarkan tipe akun
                if account_type == 'Aktiva Lancar':
                    aktiva_lancar.append(account_data)
                elif account_type == 'Aktiva Tetap':
                    # Pisahkan antara aktiva tetap dan akumulasi penyusutan
                    if not is_accumulated_depreciation:
                        aktiva_tetap.append(account_data)
                elif account_type == 'Kewajiban':
                    kewajiban.append(account_data)
                elif account_type == 'Modal':
                    modal.append(account_data)
        
        # ✅ PERBAIKAN: Jika tidak ada akumulasi penyusutan yang terdeteksi, coba cari manual
        if not akumulasi_penyusutan:
            logger.info("🔍 No accumulated depreciation found in auto-detection, searching manually...")
            for item in adjusted_trial_balance:
                account_name = item['account_name'].lower()
                if any(keyword in account_name for keyword in ['akumulasi', 'penyusutan', 'depreciation']):
                    amount = item['credit_after']
                    if amount > 0:
                        akumulasi_penyusutan.append({
                            'account_code': item['account_code'],
                            'account_name': item['account_name'],
                            'amount': amount
                        })
                        logger.info(f"✅ Manually found accumulated depreciation: {item['account_name']} = {format_currency(amount)}")
        
        # Ambil laba/rugi dari income statement untuk dimasukkan ke modal
        income_data = get_income_statement_data(period)
        laba_rugi_bersih = income_data['laba_rugi_bersih']
        
        # Tambahkan laba/rugi berjalan ke modal
        if laba_rugi_bersih != 0:
            modal.append({
                'account_code': 'LR',
                'account_name': 'Laba (Rugi) Berjalan',
                'amount': abs(laba_rugi_bersih)
            })
        
        # Hitung total dengan memperhitungkan akumulasi penyusutan
        total_aktiva_lancar = sum(item['amount'] for item in aktiva_lancar)
        total_aktiva_tetap_bruto = sum(item['amount'] for item in aktiva_tetap)
        total_akumulasi_penyusutan = sum(item['amount'] for item in akumulasi_penyusutan)
        
        total_aktiva_tetap_neto = total_aktiva_tetap_bruto - total_akumulasi_penyusutan
        total_aktiva = total_aktiva_lancar + total_aktiva_tetap_neto
        
        total_kewajiban = sum(item['amount'] for item in kewajiban)
        total_modal = sum(item['amount'] for item in modal)
        total_kewajiban_modal = total_kewajiban + total_modal
        
        # Log untuk debugging
        logger.info(f"✅ Balance Sheet calculated WITH DEPRECIATION:")
        logger.info(f"   Aktiva Lancar: {len(aktiva_lancar)} accounts, Total: {format_currency(total_aktiva_lancar)}")
        logger.info(f"   Aktiva Tetap (Bruto): {len(aktiva_tetap)} accounts, Total: {format_currency(total_aktiva_tetap_bruto)}")
        logger.info(f"   Akumulasi Penyusutan: {len(akumulasi_penyusutan)} accounts, Total: {format_currency(total_akumulasi_penyusutan)}")
        logger.info(f"   Aktiva Tetap (Neto): {format_currency(total_aktiva_tetap_neto)}")
        logger.info(f"   Total Aktiva: {format_currency(total_aktiva)}")
        
        return {
            'period': period,
            'aktiva_lancar': aktiva_lancar,
            'aktiva_tetap': aktiva_tetap,
            'akumulasi_penyusutan': akumulasi_penyusutan,
            'kewajiban': kewajiban,
            'modal': modal,
            'total_aktiva_lancar': total_aktiva_lancar,
            'total_aktiva_tetap_bruto': total_aktiva_tetap_bruto,
            'total_akumulasi_penyusutan': total_akumulasi_penyusutan,
            'total_aktiva_tetap_neto': total_aktiva_tetap_neto,
            'total_aktiva': total_aktiva,
            'total_kewajiban': total_kewajiban,
            'total_modal': total_modal,
            'total_kewajiban_modal': total_kewajiban_modal,
            'laba_rugi': laba_rugi_bersih,
            'is_balanced': abs(total_aktiva - total_kewajiban_modal) < 0.01
        }
        
    except Exception as e:
        logger.error(f"❌ Error calculating balance sheet: {e}")
        logger.error(traceback.format_exc())
        return {
            'period': period,
            'aktiva_lancar': [],
            'aktiva_tetap': [],
            'akumulasi_penyusutan': [],
            'kewajiban': [],
            'modal': [],
            'total_aktiva': 0,
            'total_kewajiban': 0,
            'total_modal': 0,
            'total_kewajiban_modal': 0,
            'laba_rugi': 0,
            'is_balanced': True
        }

def get_equity_statement_data(period=None):
    """Ambil data untuk Laporan Perubahan Modal - VERSI DIPERBAIKI DENGAN NAMA AKUN"""
    try:
        if not period:
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating equity statement for period: {period}")
        
        # ✅ PERBAIKAN PENTING: Ambil laba/rugi bersih langsung dari Laporan Laba Rugi
        income_data = get_income_statement_data(period)
        laba_rugi_bersih = income_data['laba_rugi_bersih']
        
        logger.info(f"💰 Laba/Rugi Bersih dari Income Statement: {format_currency(laba_rugi_bersih)}")
        
        # Ambil data dari neraca lajur untuk mendapatkan modal awal
        worksheet_data = get_worksheet_data(period)
        
        if not worksheet_data:
            logger.warning(f"⚠️ No worksheet data found for period {period}")
            return {
                'period': period,
                'modal_awal': 0,
                'laba_rugi_bersih': laba_rugi_bersih,
                'laba_rugi_account_name': 'Laba (Rugi) Bersih',  # ✅ TAMBAH INI
                'prive': 0,
                'prive_account_name': 'Prive',  # ✅ TAMBAH INI
                'investasi_tambahan': 0,
                'investasi_account_name': 'Investasi Tambahan',  # ✅ TAMBAH INI
                'modal_akhir': laba_rugi_bersih
            }
        
        # Cari akun modal dari worksheet data
        modal_awal = 0
        modal_account_name = "Modal Awal"
        
        for item in worksheet_data:
            account_name = item['account_name']
            account_type = item['account_type']
            
            # Cari akun modal (Modal Saham, Modal Disetor, dll)
            if (account_type == 'Modal' or 
                'Modal' in account_name or 
                'modal' in account_name.lower()):
                
                # Untuk akun modal, saldo normalnya di kredit
                if item['neraca_credit'] > 0:
                    modal_awal += item['neraca_credit']
                    modal_account_name = account_name
                elif item['neraca_debit'] > 0:
                    modal_awal -= item['neraca_debit']
                    modal_account_name = account_name
                logger.info(f"💰 Found modal account: {account_name} = {format_currency(item['neraca_credit'])}")
        
        # Jika tidak ditemukan modal di worksheet, coba dari neraca saldo
        if modal_awal == 0:
            logger.info("🔍 Modal not found in worksheet, trying trial balance...")
            trial_balance = calculate_trial_balance(period)
            for item in trial_balance:
                if (item['account_type'] == 'Modal' or 
                    'Modal' in item['account_name'] or 
                    'modal' in item['account_name'].lower()):
                    
                    # Akun modal biasanya di kredit
                    if item['credit'] > 0:
                        modal_awal = item['credit']
                        modal_account_name = item['account_name']
                    logger.info(f"💰 Found modal in trial balance: {item['account_name']} = {format_currency(modal_awal)}")
                    break
        
        # Jika masih tidak ditemukan, gunakan nilai default
        if modal_awal == 0:
            logger.warning("⚠️ Modal awal tidak ditemukan, menggunakan nilai 0")
        
        # Asumsi: tidak ada prive atau investasi tambahan untuk sederhananya
        prive = 0
        prive_account_name = "Prive"
        investasi_tambahan = 0
        investasi_account_name = "Investasi Tambahan"
        
        # Cari akun prive jika ada
        for item in worksheet_data:
            if 'prive' in item['account_name'].lower() or 'prive' in item['account_code'].lower():
                prive = abs(item['neraca_debit'] - item['neraca_credit'])
                prive_account_name = item['account_name']
                break
        
        # Hitung modal akhir
        modal_akhir = modal_awal + laba_rugi_bersih - prive + investasi_tambahan
        
        logger.info(f"✅ Equity statement calculated:")
        logger.info(f"   Modal Awal: {format_currency(modal_awal)}")
        logger.info(f"   Laba/Rugi Bersih: {format_currency(laba_rugi_bersih)}")
        logger.info(f"   Prive: {format_currency(prive)}")
        logger.info(f"   Investasi Tambahan: {format_currency(investasi_tambahan)}")
        logger.info(f"   Modal Akhir: {format_currency(modal_akhir)}")
        
        return {
            'period': period,
            'modal_awal': modal_awal,
            'modal_account_name': modal_account_name,  # ✅ TAMBAH INI
            'laba_rugi_bersih': laba_rugi_bersih,
            'laba_rugi_account_name': 'Laba (Rugi) Bersih',  # ✅ TAMBAH INI
            'prive': prive,
            'prive_account_name': prive_account_name,  # ✅ TAMBAH INI
            'investasi_tambahan': investasi_tambahan,
            'investasi_account_name': investasi_account_name,  # ✅ TAMBAH INI
            'modal_akhir': modal_akhir
        }
        
    except Exception as e:
        logger.error(f"❌ Error calculating equity statement: {e}")
        logger.error(traceback.format_exc())
        return {
            'period': period,
            'modal_awal': 0,
            'modal_account_name': 'Modal Awal',
            'laba_rugi_bersih': 0,
            'laba_rugi_account_name': 'Laba (Rugi) Bersih',
            'prive': 0,
            'prive_account_name': 'Prive',
            'investasi_tambahan': 0,
            'investasi_account_name': 'Investasi Tambahan',
            'modal_akhir': 0
        }

def get_cash_flow_data(period=None):
    """Ambil data untuk Laporan Arus Kas - VERSI DIPERBAIKI"""
    try:
        if not period:
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating IMPROVED cash flow statement for period: {period}")
        
        # Parse periode untuk rentang tanggal
        year, month = map(int, period.split('-'))
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"
        
        # 1. ✅ PERBAIKAN: Ambil saldo kas awal dari NERACA SALDO AWAL, bukan setelah penyesuaian
        kas_awal = 0
        opening_balances = get_opening_balances_with_account_info()
        for balance in opening_balances:
            account_name = balance['account_name'].lower()
            if 'kas' in account_name and balance['account_type'] == 'Aktiva Lancar':
                if balance['position'] == 'debit':
                    kas_awal = balance['amount']
                else:
                    kas_awal = -balance['amount']  # Jika somehow kas di kredit
                logger.info(f"💰 Kas awal dari neraca saldo awal: {balance['account_name']} = {format_currency(kas_awal)}")
                break
        
        # Jika tidak ditemukan di neraca saldo awal, coba dari trial balance sebelum penyesuaian
        if kas_awal == 0:
            trial_balance = calculate_trial_balance(period)
            for item in trial_balance:
                if 'kas' in item['account_name'].lower() and item['account_type'] == 'Aktiva Lancar':
                    kas_awal = item['debit']  # Gunakan saldo sebelum penyesuaian
                    logger.info(f"💰 Kas awal dari trial balance: {item['account_name']} = {format_currency(kas_awal)}")
                    break
        
        # 2. ✅ PERBAIKAN: Analisis transaksi yang lebih akurat untuk arus kas operasi
        penerimaan_pelanggan = 0
        pembayaran_pemasok = 0
        pembayaran_beban_operasional = 0
        
        # Ambil semua transaksi jurnal untuk periode ini
        journals = get_journal_entries_with_details(start_date, end_date)
        
        for journal in journals:
            description = journal.get('description', '').lower()
            entries = journal.get('journal_entries', [])
            
            # ✅ PERBAIKAN: Analisis yang lebih komprehensif untuk penerimaan dari pelanggan
            is_penerimaan = any(keyword in description for keyword in [
                'penjualan', 'jual', 'sales', 'pendapatan', 'pelunasan', 'piutang',
                'penerimaan', 'terima', 'diterima', 'pembayaran pelanggan'
            ])
            
            if is_penerimaan:
                for entry in entries:
                    account_name = get_account_name(entry['account_code']).lower()
                    # Penerimaan kas (kas bertambah di debit)
                    if ('kas' in account_name or 'kas' in entry.get('account_code', '').lower()) and entry['position'] == 'debit':
                        penerimaan_pelanggan += entry['amount']
                        logger.info(f"💰 Cash receipt: {format_currency(entry['amount'])} - {description}")
            
            # ✅ PERBAIKAN: Analisis yang lebih komprehensif untuk pembayaran ke pemasok
            is_pembayaran_pemasok = any(keyword in description for keyword in [
                'pembelian', 'beli', 'bahan', 'pemasok', 'persediaan', 'perlengkapan', 
                'pelunasan', 'utang', 'pembayaran', 'bayar', 'dibayar', 'pemasok',
                'bibit', 'pakan', 'perlengkapan', 'peralatan'
            ])
            
            if is_pembayaran_pemasok:
                for entry in entries:
                    account_name = get_account_name(entry['account_code']).lower()
                    # Pengeluaran kas untuk pemasok (kas berkurang di kredit)
                    if ('kas' in account_name or 'kas' in entry.get('account_code', '').lower()) and entry['position'] == 'kredit':
                        pembayaran_pemasok += entry['amount']
                        logger.info(f"💸 Payment to supplier: {format_currency(entry['amount'])} - {description}")
            
            # ✅ PERBAIKAN: Analisis untuk pembayaran beban operasional
            is_beban_operasional = any(keyword in description for keyword in [
                'beban', 'gaji', 'listrik', 'air', 'obat', 'perawatan', 'operasional',
                'biaya', 'pengeluaran', 'administrasi', 'transport', 'pemeliharaan'
            ])
            
            if is_beban_operasional:
                for entry in entries:
                    account_name = get_account_name(entry['account_code']).lower()
                    # Pengeluaran kas untuk beban (kas berkurang di kredit)
                    if ('kas' in account_name or 'kas' in entry.get('account_code', '').lower()) and entry['position'] == 'kredit':
                        pembayaran_beban_operasional += entry['amount']
                        logger.info(f"💸 Expense payment: {format_currency(entry['amount'])} - {description}")

        # 3. Hitung arus kas bersih dari operasi
        arus_kas_operasi = penerimaan_pelanggan - pembayaran_pemasok - pembayaran_beban_operasional
        
        # 4. Hitung penurunan kas bersih dan saldo akhir
        penurunan_kas_bersih = arus_kas_operasi
        kas_akhir = kas_awal + penurunan_kas_bersih
        
        logger.info(f"✅ IMPROVED Cash Flow calculated:")
        logger.info(f"   Kas Awal (dari neraca saldo awal): {format_currency(kas_awal)}")
        logger.info(f"   Penerimaan dari Pelanggan: {format_currency(penerimaan_pelanggan)}")
        logger.info(f"   Pembayaran kepada Pemasok: {format_currency(pembayaran_pemasok)}")
        logger.info(f"   Pembayaran Beban Operasional: {format_currency(pembayaran_beban_operasional)}")
        logger.info(f"   Kas Bersih dari Operasi: {format_currency(arus_kas_operasi)}")
        logger.info(f"   Penurunan Kas Bersih: {format_currency(penurunan_kas_bersih)}")
        logger.info(f"   Kas Akhir: {format_currency(kas_akhir)}")
        
        return {
            'period': period,
            'kas_awal': kas_awal,
            'kas_akhir': kas_akhir,
            'penurunan_kas_bersih': penurunan_kas_bersih,
            'arus_kas_operasi': arus_kas_operasi,
            'penerimaan_pelanggan': penerimaan_pelanggan,
            'pembayaran_pemasok': pembayaran_pemasok,
            'pembayaran_beban_operasional': pembayaran_beban_operasional,
            'start_date': start_date,
            'end_date': end_date
        }
        
    except Exception as e:
        logger.error(f"❌ Error calculating IMPROVED cash flow statement: {e}")
        logger.error(traceback.format_exc())
        return {
            'period': period,
            'kas_awal': 0,
            'kas_akhir': 0,
            'penurunan_kas_bersih': 0,
            'arus_kas_operasi': 0,
            'penerimaan_pelanggan': 0,
            'pembayaran_pemasok': 0,
            'pembayaran_beban_operasional': 0,
            'start_date': '',
            'end_date': ''
        }

# ============================================================
# 💸 19. JURNAL PENUTUP
# ============================================================

@app.route("/jurnal_penutup")
@admin_required
def jurnal_penutup():
    """Halaman Jurnal Penutup - Dihitung otomatis dari data transaksi"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Ambil data jurnal penutup dari fungsi yang sudah ada
    closing_data = get_closing_journal_data(period)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat HTML untuk jurnal penutup
    closing_journal_html = ""
    
    if closing_data['entries']:
        closing_journal_html = f"""
        <div style="overflow-x: auto; margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px; min-width: 800px;">
                <thead>
                    <tr style="background: #008DD8; color: white;">
                        <th style="padding: 12px; text-align: left; border: 2px solid #007bff; width: 40%;">Nama Akun</th>
                        <th style="padding: 12px; text-align: center; border: 2px solid #007bff; width: 15%;">Ref</th>
                        <th style="padding: 12px; text-align: right; border: 2px solid #007bff; width: 22.5%;">Debit</th>
                        <th style="padding: 12px; text-align: right; border: 2px solid #007bff; width: 22.5%;">Kredit</th>
                    </tr>
                </thead>
                <tbody>
        """

        # Untuk setiap entry, tambahkan style khusus untuk akun kredit
        for entry in closing_data['entries']:
            row_style = ""
            
            # Tentukan apakah ini akun debit atau kredit
            is_credit_account = entry['credit'] > 0 and entry['type'] in ['hpp', 'beban', 'ikhtisar_pendapatan', 'modal_laba']
            
            # ✅ PERBAIKAN: Gunakan flag is_indented untuk menentukan indentasi
            if entry.get('is_indented') or is_credit_account:
                # Akun kredit - buat menjorok ke dalam
                account_name_style = "padding-left: 30px; font-style: italic;"
                row_style = "background: #f8f9fa;"
            else:
                # Akun debit - normal
                account_name_style = ""
            
            if entry['type'] in ['ikhtisar_pendapatan', 'ikhtisar_beban']:
                row_style = "background: #e7f3ff; font-weight: bold;"
                account_name_style = ""
            elif entry['type'] in ['tutup_laba', 'tutup_rugi']:
                row_style = "background: #fff3cd; font-weight: bold;"
                account_name_style = ""
            elif entry['type'] in ['modal_laba', 'modal_rugi']:
                row_style = "background: #e8f5e8; font-weight: bold;"
                # ✅ Modal usaha TETAP menjorok meskipun bold
                if entry.get('is_indented'):
                    account_name_style = "padding-left: 30px; font-style: italic;"
            
            debit_display = format_currency(entry['debit']) if entry['debit'] > 0 else ""
            credit_display = format_currency(entry['credit']) if entry['credit'] > 0 else ""
            
            closing_journal_html += f"""
            <tr style="{row_style}">
                <td style="padding: 10px; border: 1px solid #dee2e6; {account_name_style} font-weight: {'bold' if 'bold' in row_style else 'normal'};">
                    {entry['account_name']}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; font-weight: {'bold' if 'bold' in row_style else 'normal'};">
                    {entry['ref']}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: {'bold' if 'bold' in row_style else 'normal'};">
                    {debit_display}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: {'bold' if 'bold' in row_style else 'normal'};">
                    {credit_display}
                </td>
            </tr>
            """
        
        closing_journal_html += f"""
                </tbody>
                <tfoot>
                    <tr style="background: #e9ecef; font-weight: bold; border-top: 3px solid #008DD8;">
                        <td colspan="2" style="padding: 15px; border: 1px solid #dee2e6; text-align: center; font-size: 16px;">
                            JUMLAH
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-size: 16px;">
                            {format_currency(closing_data['total_debit'])}
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-size: 16px;">
                            {format_currency(closing_data['total_credit'])}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
        
        <div style="margin-top: 20px; padding: 20px; background: {'#28a745' if closing_data['is_balanced'] else '#dc3545'}; color: white; border-radius: 8px; text-align: center; font-weight: bold; font-size: 16px;">
            {'✅ JURNAL PENUTUP SEIMBANG' if closing_data['is_balanced'] else '❌ JURNAL PENUTUP TIDAK SEIMBANG'}
        </div>
        
        <div style="margin-top: 15px; padding: 15px; background: {'#d4edda' if closing_data['laba_rugi_bersih'] >= 0 else '#f8d7da'}; border-radius: 8px; text-align: center;">
            <h4 style="margin: 0; color: {'#155724' if closing_data['laba_rugi_bersih'] >= 0 else '#721c24'};">
                {'LABA BERSIH' if closing_data['laba_rugi_bersih'] >= 0 else 'RUGI BERSIH'}: {format_currency(abs(closing_data['laba_rugi_bersih']))}
            </h4>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: {'#155724' if closing_data['laba_rugi_bersih'] >= 0 else '#721c24'};">
                Total Pendapatan: {format_currency(closing_data['total_pendapatan'])} - 
                Total Beban & HPP: {format_currency(closing_data['total_beban_hpp'])} = 
                {format_currency(closing_data['laba_rugi_bersih'])}
            </p>
        </div>
        """
    else:
        closing_journal_html = """
        <div style="text-align: center; padding: 60px; color: #666;">
            <div style="font-size: 64px; margin-bottom: 20px;">📒</div>
            <h3>Belum Ada Data Jurnal Penutup</h3>
            <p>Belum ada data transaksi untuk periode ini atau data tidak dapat dihitung</p>
            <div style="margin-top: 20px;">
                <a href="/jurnal_penutup_manual">
                    <button style="margin: 5px; background: #008DD8; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📋 Lihat Contoh Manual
                    </button>
                </a>
                <a href="/laporan_laba_rugi">
                    <button style="margin: 5px; background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📈 Cek Laporan Laba Rugi
                    </button>
                </a>
            </div>
        </div>
        """

    content = f"""
    <div class="welcome-section">
        <h2>📒 Jurnal Penutup (Otomatis)</h2>
        <div class="welcome-message">
            Jurnal penutup yang dihitung otomatis dari data transaksi periode berjalan.
            <br><strong>💡 Data dihitung berdasarkan Laporan Laba Rugi periode {period}</strong>
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Jurnal Penutup</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #008DD8; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #008DD8; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Hitung Jurnal Penutup
                </button>
            </div>
        </form>
    </div>

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Jurnal Penutup Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <button onclick="printJournal()" style="background: #28a745; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                    🖨️ Cetak Jurnal
                </button>
                <a href="/jurnal_penutup_manual">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📋 Contoh Manual
                    </button>
                </a>
                <a href="/laporan_laba_rugi?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px;">
                        📈 Laporan Laba Rugi
                    </button>
                </a>
            </div>
        </div>
        
        {closing_journal_html}
    </div>

    <!-- Informasi Proses Jurnal Penutup -->
    <div class="quick-actions">
        <h3>💡 Proses Jurnal Penutup</h3>
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4 style="color: #008DD8; margin-bottom: 10px;">📝 Tahapan Jurnal Penutup</h4>
                    <ol style="text-align: left; color: #666; line-height: 1.6;">
                        <li><strong>Penutupan Pendapatan:</strong> Debit akun pendapatan, kredit Ikhtisar Laba Rugi</li>
                        <li><strong>Penutupan Beban & HPP:</strong> Kredit akun beban/HPP, debit Ikhtisar Laba Rugi</li>
                        <li><strong>Penutupan Ikhtisar Laba Rugi:</strong> Tutup selisih ke Modal Usaha</li>
                    </ol>
                </div>
                <div>
                    <h4 style="color: #28a745; margin-bottom: 10px;">✅ Validasi Jurnal Penutup</h4>
                    <ul style="text-align: left; color: #666; line-height: 1.6;">
                        <li>Total debit harus sama dengan total kredit</li>
                        <li>Semua akun nominal (pendapatan & beban) harus tertutup</li>
                        <li>Saldo akhir Ikhtisar Laba Rugi harus NOL</li>
                        <li>Laba/rugi berpindah ke Modal Usaha</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
            
            .welcome-section {{
                display: none;
            }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printJournal() {{
            window.print();
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    this.style.backgroundColor = '';
                }});
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 🔄 FUNGSI JURNAL PENUTUP
# ============================================================

def get_closing_journal_data(period):
    """Ambil data untuk jurnal penutup dari Laporan Laba Rugi - FORMAT DIPERBAIKI"""
    try:
        logger.info(f"🔄 Calculating closing journal data for period: {period}")
        
        # Ambil data dari Laporan Laba Rugi
        income_data = get_income_statement_data(period)
        
        if not income_data:
            logger.warning(f"⚠️ No income statement data found for period {period}")
            return {'entries': [], 'total_debit': 0, 'total_credit': 0, 'is_balanced': False}
        
        closing_entries = []
        total_pendapatan = income_data['total_pendapatan']
        total_beban_hpp = income_data['total_semua_beban']
        laba_rugi_bersih = income_data['laba_rugi_bersih']
        
        # 1. PENUTUPAN PENDAPATAN (Debit pendapatan, kredit ikhtisar laba rugi)
        for income in income_data['income_accounts']:
            if income['amount'] > 0:
                closing_entries.append({
                    'account_name': income['account_name'],
                    'ref': income['account_code'],
                    'debit': income['amount'],
                    'credit': 0,
                    'type': 'pendapatan'
                })
        
        # Kredit ikhtisar laba rugi untuk pendapatan - INI YANG MENJOROK KE DALAM
        if total_pendapatan > 0:
            closing_entries.append({
                'account_name': 'Ikhitsar Laba Rugi',
                'ref': '3-3200',
                'debit': 0,
                'credit': total_pendapatan,
                'type': 'ikhtisar_pendapatan',
                'is_indented': True  # ✅ FLAG BARU UNTUK MENJOROK KE DALAM
            })
        
        # 2. PENUTUPAN BEBAN & HPP (Kredit beban, debit ikhtisar laba rugi)
        # HPP
        for hpp in income_data['hpp_accounts']:
            if hpp['amount'] > 0:
                closing_entries.append({
                    'account_name': hpp['account_name'],
                    'ref': hpp['account_code'],
                    'debit': 0,
                    'credit': hpp['amount'],
                    'type': 'hpp'
                })
        
        # Beban
        for expense in income_data['expense_accounts']:
            if expense['amount'] > 0:
                closing_entries.append({
                    'account_name': expense['account_name'],
                    'ref': expense['account_code'],
                    'debit': 0,
                    'credit': expense['amount'],
                    'type': 'beban'
                })
        
        # Debit ikhtisar laba rugi untuk beban & HPP - INI DI ATAS HPP
        if total_beban_hpp > 0:
            closing_entries.append({
                'account_name': 'Ikhitsar Laba Rugi',
                'ref': '3-3200',
                'debit': total_beban_hpp,
                'credit': 0,
                'type': 'ikhtisar_beban'
            })
        
        # 3. PENUTUPAN IKHTISAR LABA RUGI KE MODAL
        if laba_rugi_bersih >= 0:  # LABA
            closing_entries.append({
                'account_name': 'Ikhitsar Laba Rugi',
                'ref': '3-3200',
                'debit': laba_rugi_bersih,
                'credit': 0,
                'type': 'tutup_laba'
            })
            closing_entries.append({
                'account_name': 'Modal Usaha',
                'ref': '3-3100',
                'debit': 0,
                'credit': laba_rugi_bersih,
                'type': 'modal_laba',
                'is_indented': True  # ✅ FLAG BARU UNTUK MENJOROK KE DALAM
            })
        else:  # RUGI
            closing_entries.append({
                'account_name': 'Ikhitsar Laba Rugi',
                'ref': '3-3200',
                'debit': 0,
                'credit': abs(laba_rugi_bersih),
                'type': 'tutup_rugi'
            })
            closing_entries.append({
                'account_name': 'Modal Usaha',
                'ref': '3-3100',
                'debit': abs(laba_rugi_bersih),
                'credit': 0,
                'type': 'modal_rugi',
                'is_indented': True  # ✅ FLAG BARU UNTUK MENJOROK KE DALAM
            })
        
        # Hitung total
        total_debit = sum(entry['debit'] for entry in closing_entries)
        total_credit = sum(entry['credit'] for entry in closing_entries)
        
        result = {
            'entries': closing_entries,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'is_balanced': abs(total_debit - total_credit) < 0.01,
            'total_pendapatan': total_pendapatan,
            'total_beban_hpp': total_beban_hpp,
            'laba_rugi_bersih': laba_rugi_bersih
        }
        
        logger.info(f"✅ Closing journal data calculated: {len(closing_entries)} entries")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error calculating closing journal data: {e}")
        return {'entries': [], 'total_debit': 0, 'total_credit': 0, 'is_balanced': False}

def get_modal_from_cash_flow(period):
    """Ambil nilai Modal Usaha secara otomatis dari Laporan Arus Kas"""
    try:
        cash_flow_data = get_cash_flow_data(period)
        
        # Dari Laporan Arus Kas, Modal biasanya = Kas Akhir + Penyesuaian
        # Atau bisa dari perhitungan: Modal Awal + Laba/Rugi - Prive + Investasi
        kas_akhir = cash_flow_data.get('kas_akhir', 0)
        
        # Jika ada field khusus untuk modal di cash flow data
        modal_dari_arus_kas = cash_flow_data.get('modal_akhir', 0)
        
        if modal_dari_arus_kas > 0:
            logger.info(f"💰 Modal dari field khusus Laporan Arus Kas: {format_currency(modal_dari_arus_kas)}")
            return modal_dari_arus_kas
        
        # Jika tidak ada field khusus, hitung dari komponennya
        # Ambil data perubahan modal
        equity_data = get_equity_statement_data(period)
        modal_akhir = equity_data.get('modal_akhir', 0)
        
        if modal_akhir > 0:
            logger.info(f"💰 Modal dari Laporan Perubahan Modal: {format_currency(modal_akhir)}")
            return modal_akhir
        
        # Fallback: gunakan kas akhir sebagai dasar (dengan adjustment)
        # Ini logika sederhana, sesuaikan dengan kebutuhan bisnis
        modal_calculated = kas_akhir * 1.0  # Adjust factor sesuai kebutuhan
        
        logger.info(f"💰 Modal dihitung dari Kas Akhir: {format_currency(modal_calculated)}")
        return modal_calculated
        
    except Exception as e:
        logger.error(f"❌ Error getting modal from cash flow: {e}")
        logger.error(traceback.format_exc())
        return 0

def get_post_closing_trial_balance(period=None):
    """Hitung Neraca Saldo Setelah Penutup - DIPERBAIKI UNTUK AKUMULASI PENYUSUTAN DAN MODAL"""
    try:
        if not period:
            current_date = datetime.now()
            period = current_date.strftime("%Y-%m")
        
        logger.info(f"🔄 Calculating POST-CLOSING trial balance for period: {period}")
        
        # 1. Ambil data dari Neraca Lajur - kolom Neraca
        worksheet_data = get_worksheet_data(period)
        
        # 2. Ambil data dari Neraca Saldo Setelah Penyesuaian untuk akumulasi penyusutan
        adjusted_trial_balance = get_adjusted_trial_balance(period)
        
        # ✅ PERBAIKAN: Ambil nilai Modal Usaha SECARA OTOMATIS dari Laporan Arus Kas
        modal_dari_arus_kas = get_modal_from_cash_flow(period)
        
        if not worksheet_data and not adjusted_trial_balance:
            logger.warning(f"⚠️ No data found for period {period}")
            return []
        
        # 3. Siapkan mapping untuk data neraca saldo setelah penutup
        post_closing_data = []
        modal_updated = False
        
        # 4. Ambil data dari kolom Neraca di Neraca Lajur
        for item in worksheet_data:
            # Hanya ambil akun neraca (bukan laba rugi)
            if item.get('is_balance_sheet') and (item['neraca_debit'] > 0 or item['neraca_credit'] > 0):
                
                # ✅ PERBAIKAN: Jika ini akun Modal Usaha, gunakan nilai dari Laporan Arus Kas
                is_modal_account = (
                    item['account_code'] == '3-3100' or 
                    'modal' in item['account_name'].lower() or
                    'modal usaha' in item['account_name'].lower()
                )
                
                if is_modal_account and modal_dari_arus_kas > 0:
                    post_closing_data.append({
                        'account_code': item['account_code'],
                        'account_name': item['account_name'],
                        'account_type': item['account_type'],
                        'debit': 0,
                        'credit': modal_dari_arus_kas  # Gunakan nilai OTOMATIS dari Laporan Arus Kas
                    })
                    modal_updated = True
                    logger.info(f"✅ Modal Usaha diupdate OTOMATIS dari Laporan Arus Kas: {format_currency(modal_dari_arus_kas)}")
                else:
                    # Untuk akun lainnya, gunakan saldo dari kolom Neraca
                    post_closing_data.append({
                        'account_code': item['account_code'],
                        'account_name': item['account_name'],
                        'account_type': item['account_type'],
                        'debit': item['neraca_debit'],
                        'credit': item['neraca_credit']
                    })
        
        # 5. Tambahkan akumulasi penyusutan dari NSSP jika belum ada di neraca lajur
        # Cari akun akumulasi penyusutan di adjusted trial balance
        depreciation_accounts = []
        for item in adjusted_trial_balance:
            account_name = item['account_name'].lower()
            if any(keyword in account_name for keyword in ['akumulasi', 'penyusutan', 'depreciation']):
                # ✅ PERBAIKAN: Untuk akumulasi penyusutan, saldo normalnya di kredit - JANGAN DIUBAH
                if item['credit_after'] > 0:
                    depreciation_accounts.append({
                        'account_code': item['account_code'],
                        'account_name': item['account_name'],
                        'account_type': item['account_type'],
                        'debit': 0,  # ✅ PASTIKAN di debit = 0
                        'credit': item['credit_after']  # ✅ PASTIKAN di kredit
                    })
                    logger.info(f"✅ Found accumulated depreciation: {item['account_name']} = {format_currency(item['credit_after'])} (Kredit)")
        
        # Tambahkan akumulasi penyusutan jika belum ada di post_closing_data
        for dep_account in depreciation_accounts:
            # Cek apakah sudah ada di post_closing_data
            existing = any(item['account_code'] == dep_account['account_code'] for item in post_closing_data)
            if not existing and (dep_account['debit'] > 0 or dep_account['credit'] > 0):
                post_closing_data.append(dep_account)
                logger.info(f"✅ Added depreciation account to post-closing: {dep_account['account_name']} = {format_currency(dep_account['credit'])} (Kredit)")
        
        # Jika tidak menemukan akun modal, tambahkan manually
        if not modal_updated and modal_dari_arus_kas > 0:
            post_closing_data.append({
                'account_code': '3-3100',
                'account_name': 'Modal Usaha',
                'account_type': 'Modal',
                'debit': 0,
                'credit': modal_dari_arus_kas
            })
            logger.info(f"✅ Modal Usaha ditambahkan OTOMATIS: {format_currency(modal_dari_arus_kas)}")
        
        # 6. Validasi dan koreksi saldo berdasarkan tipe akun - PERBAIKAN UNTUK AKUMULASI PENYUSUTAN
        for item in post_closing_data:
            account_code = item['account_code']
            account_name = item['account_name']
            account_type = item['account_type']
            
            # ✅ PERBAIKAN PENTING: JANGAN ubah akun akumulasi penyusutan
            is_accumulated_depreciation = (
                'akumulasi' in account_name.lower() and 
                'penyusutan' in account_name.lower()
            )
            
            if is_accumulated_depreciation:
                # Biarkan akun akumulasi penyusutan tetap di kredit - JANGAN DIUBAH
                logger.info(f"🔒 Akun akumulasi penyusutan dilindungi: {account_name} = {format_currency(item['credit'])} (Kredit)")
                continue
                
            # Untuk akun neraca lainnya, lakukan koreksi normal
            if account_type in ['Aktiva Lancar', 'Aktiva Tetap']:
                # Akun aktiva seharusnya di debit
                if item['credit'] > 0 and item['debit'] == 0:
                    # Koreksi: pindahkan ke debit
                    item['debit'] = item['credit']
                    item['credit'] = 0
                    logger.info(f"🔄 Koreksi akun aktiva: {account_name} dipindahkan ke debit")
            elif account_type in ['Kewajiban', 'Modal']:
                # Akun kewajiban dan modal seharusnya di kredit
                if item['debit'] > 0 and item['credit'] == 0:
                    # Koreksi: pindahkan ke kredit
                    item['credit'] = item['debit']
                    item['debit'] = 0
                    logger.info(f"🔄 Koreksi akun kewajiban/modal: {account_name} dipindahkan ke kredit")
        
        # 7. Urutkan berdasarkan kode akun
        post_closing_data.sort(key=lambda x: x['account_code'])
        
        # 8. Log summary
        total_debit = sum(item['debit'] for item in post_closing_data)
        total_credit = sum(item['credit'] for item in post_closing_data)
        
        # Cari akun modal untuk logging
        modal_accounts = [item for item in post_closing_data if 'modal' in item['account_name'].lower()]
        for modal in modal_accounts:
            logger.info(f"💰 Modal Usaha akhir: {modal['account_name']} = {format_currency(modal['credit'])}")
        
        # Cari akun akumulasi penyusutan untuk logging
        dep_accounts = [item for item in post_closing_data if 'akumulasi' in item['account_name'].lower() and 'penyusutan' in item['account_name'].lower()]
        for dep in dep_accounts:
            logger.info(f"🏗️ Akumulasi Penyusutan: {dep['account_name']} = {format_currency(dep['credit'])} (Kredit)")
        
        logger.info(f"✅ POST-CLOSING trial balance calculated: {len(post_closing_data)} accounts")
        logger.info(f"💰 Total Debit: {total_debit:,}")
        logger.info(f"💰 Total Credit: {total_credit:,}")
        logger.info(f"⚖️ Balance Status: {'BALANCED' if abs(total_debit - total_credit) < 0.01 else 'NOT BALANCED'}")
        
        return post_closing_data
        
    except Exception as e:
        logger.error(f"❌ Error calculating POST-CLOSING trial balance: {e}")
        logger.error(traceback.format_exc())
        return []

def get_post_closing_summary(post_closing_data):
    """Hitung summary dari neraca saldo setelah penutup"""
    try:
        total_debit = sum(item['debit'] for item in post_closing_data)
        total_credit = sum(item['credit'] for item in post_closing_data)
        difference = total_debit - total_credit
        
        # Cari nilai modal usaha
        modal_usaha = 0
        for item in post_closing_data:
            if 'modal' in item['account_name'].lower() and 'usaha' in item['account_name'].lower():
                modal_usaha = item['credit']  # Modal selalu di kredit
                break
        
        # Cari akumulasi penyusutan
        akumulasi_penyusutan = []
        for item in post_closing_data:
            if 'akumulasi' in item['account_name'].lower() and 'penyusutan' in item['account_name'].lower():
                akumulasi_penyusutan.append({
                    'account_name': item['account_name'],
                    'amount': item['credit']  # Akumulasi penyusutan selalu di kredit
                })
        
        return {
            'total_debit': total_debit,
            'total_credit': total_credit,
            'is_balanced': abs(difference) < 0.01,
            'difference': difference,
            'accounts_count': len(post_closing_data),
            'active_accounts': len([item for item in post_closing_data if item['debit'] > 0 or item['credit'] > 0]),
            'modal_usaha': modal_usaha,
            'akumulasi_penyusutan': akumulasi_penyusutan
        }
    except Exception as e:
        logger.error(f"❌ Error calculating post-closing summary: {e}")
        return {
            'total_debit': 0, 
            'total_credit': 0,
            'is_balanced': False,
            'difference': 0,
            'accounts_count': 0,
            'active_accounts': 0,
            'modal_usaha': 0,
            'akumulasi_penyusutan': []
        }

# ============================================================
# 💸 20. NERACA SALDO SETELAH PENUTUP
# ============================================================

@app.route("/neraca_saldo_setelah_penutup")
@admin_required
def neraca_saldo_setelah_penutup():
    """Halaman Neraca Saldo Setelah Penutup"""
    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Admin')
    user_id = session.get('user_id', 'Unknown')
    user_role = get_user_role()
    
    # Ambil parameter periode dari URL
    period = request.args.get('period', datetime.now().strftime("%Y-%m"))
    
    # Hitung neraca saldo SETELAH penutup
    post_closing_data = get_post_closing_trial_balance(period)
    summary = get_post_closing_summary(post_closing_data)
    
    # Generate options untuk dropdown periode
    period_options = ""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    for year in range(current_year - 1, current_year + 1):
        for month in range(1, 13):
            period_value = f"{year}-{month:02d}"
            selected = "selected" if period == period_value else ""
            period_name = datetime(year, month, 1).strftime("%B %Y")
            period_options += f'<option value="{period_value}" {selected}>{period_name}</option>'
    
    # Buat tabel Neraca Saldo SETELAH Penutup
    post_closing_table_html = ""
    
    if post_closing_data:
        post_closing_table_html = """
        <div style="max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 8px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #6f42c1; color: white;">
                        <th style="padding: 12px; text-align: center; border: 1px solid #5a359a; width: 120px;">Kode Akun</th>
                        <th style="padding: 12px; text-align: left; border: 1px solid #5a359a;">Nama Akun</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #5a359a; width: 150px;">Debit</th>
                        <th style="padding: 12px; text-align: right; border: 1px solid #5a359a; width: 150px;">Kredit</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Tampilkan akun yang memiliki saldo SETELAH penutup
        accounts_with_balance = [item for item in post_closing_data if item['debit'] > 0 or item['credit'] > 0]
        
        for item in accounts_with_balance:
            post_closing_table_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; font-family: 'Courier New', monospace; font-weight: bold; background: #f8f9fa;">
                    {item['account_code']}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">
                    {item['account_name']}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-weight: bold;">
                    {format_currency(item['debit']) if item['debit'] > 0 else '-'}
                </td>
                <td style="padding: 10px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-weight: bold;">
                    {format_currency(item['credit']) if item['credit'] > 0 else '-'}
                </td>
            </tr>
            """
        
        # Baris TOTAL
        post_closing_table_html += f"""
                </tbody>
                <tfoot>
                    <tr style="background: #e9ecef; font-weight: bold; border-top: 3px solid #6f42c1;">
                        <td colspan="2" style="padding: 15px; border: 1px solid #dee2e6; text-align: center; font-size: 16px;">
                            TOTAL NERACA SALDO SETELAH PENUTUP
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #dc3545; font-size: 16px;">
                            {format_currency(summary['total_debit'])}
                        </td>
                        <td style="padding: 15px; border: 1px solid #dee2e6; text-align: right; color: #28a745; font-size: 16px;">
                            {format_currency(summary['total_credit'])}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
        """
        
        # Status balance SETELAH penutup
        if accounts_with_balance:
            balance_status = "✅ NERACA SEIMBANG" if summary['is_balanced'] else f"❌ NERACA TIDAK SEIMBANG"
            balance_color = "#28a745" if summary['is_balanced'] else "#dc3545"
            
            post_closing_table_html += f"""
            <div style="margin-top: 20px; padding: 20px; background: {balance_color}; color: white; border-radius: 8px; text-align: center; font-weight: bold; font-size: 16px;">
                {balance_status}
                {f'<div style="margin-top: 10px; font-size: 14px;">Selisih: {format_currency(abs(summary["difference"]))}</div>' if not summary['is_balanced'] else ''}
            </div>
            """
    else:
        post_closing_table_html = """
        <div style="text-align: center; padding: 60px; color: #666;">
            <div style="font-size: 64px; margin-bottom: 20px;">📊</div>
            <h3>Belum Ada Data</h3>
            <p>Belum ada data neraca saldo setelah penutup untuk periode ini</p>
            <div style="margin-top: 20px;">
                <a href="/neraca_lajur">
                    <button style="margin: 5px; background: #6f42c1; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📊 Buat Neraca Lajur
                    </button>
                </a>
                <a href="/jurnal_penutup">
                    <button style="margin: 5px; background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer;">
                        📒 Buat Jurnal Penutup
                    </button>
                </a>
            </div>
        </div>
        """
    
    # Summary informasi
    summary_html = f"""
    <div style="background: linear-gradient(135deg, #6f42c1, #8c68d6); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; text-align: center;">
            <div>
                <div style="font-size: 24px; font-weight: bold;">{summary['active_accounts']}</div>
                <div style="font-size: 14px; opacity: 0.9;">Akun Aktif</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_debit'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Debit</div>
            </div>
            <div>
                <div style="font-size: 24px; font-weight: bold;">{format_currency(summary['total_credit'])}</div>
                <div style="font-size: 14px; opacity: 0.9;">Total Kredit</div>
            </div>
        </div>
    </div>
    """ if post_closing_data and summary['active_accounts'] > 0 else ""

    content = f"""
    <div class="welcome-section">
        <h2>📊 Neraca Saldo Setelah Penutup</h2>
        <div class="welcome-message">
            Laporan yang menunjukkan saldo akhir setiap akun SETELAH dilakukan penutupan akun nominal (pendapatan dan beban).
            Hanya akun neraca (aktiva, kewajiban, modal) yang memiliki saldo setelah proses penutupan.
            <br><strong>💡 Sumber Data: Kolom Neraca dari Neraca Lajur + Akumulasi Penyusutan dari NSSP</strong>
        </div>
    </div>

    <!-- Filter Section -->
    <div class="quick-actions">
        <h3>🔍 Pilih Periode Laporan</h3>
        <form method="GET" id="periodForm" style="display: grid; grid-template-columns: 1fr auto; gap: 15px; align-items: end;">
            <div>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">Periode (Bulan-Tahun)</label>
                <select name="period" style="width: 100%; padding: 12px; border: 2px solid #6f42c1; border-radius: 8px; font-size: 16px;">
                    {period_options}
                </select>
            </div>
            <div>
                <button type="submit" style="background: #6f42c1; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    🔍 Tampilkan Laporan
                </button>
            </div>
        </form>
    </div>

    {summary_html}

    <div class="quick-actions">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
            <h3 style="margin: 0;">Neraca Saldo Setelah Penutup - Periode: {period}</h3>
            <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                <a href="/neraca_saldo_setelah_penyesuaian?period={period}">
                    <button style="background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📊 Sebelum Penutup
                    </button>
                </a>
                <a href="/neraca_lajur?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📋 Neraca Lajur
                    </button>
                </a>
                <a href="/jurnal_penutup?period={period}">
                    <button style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                        📒 Jurnal Penutup
                    </button>
                </a>
                <button onclick="printReport()" style="background: #ffc107; color: #212529; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px;">
                    🖨️ Cetak Laporan
                </button>
            </div>
        </div>
        
        {post_closing_table_html}
        
        {f'<div style="margin-top: 15px; text-align: center; color: #666; font-size: 14px;">Menampilkan {summary["active_accounts"]} dari {summary["accounts_count"]} akun</div>' if post_closing_data else ''}
    </div>

    <!-- Informasi Penting -->
    <div class="quick-actions">
        <h3>💡 Informasi Penting</h3>
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4 style="color: #6f42c1; margin-bottom: 10px;">📊 Sumber Data</h4>
                    <ul style="text-align: left; color: #666;">
                        <li><strong>Kolom Neraca dari Neraca Lajur:</strong> Untuk semua akun neraca</li>
                        <li><strong>Neraca Saldo Setelah Penyesuaian:</strong> Khusus akumulasi penyusutan</li>
                        <li><strong>Akun Nominal Tertutup:</strong> Pendapatan & beban saldo = 0</li>
                        <li><strong>Hanya Akun Riil:</strong> Aktiva, kewajiban, modal yang tersisa</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: #28a745; margin-bottom: 10px;">✅ Karakteristik NSSP</h4>
                    <ul style="text-align: left; color: #666;">
                        <li>Total Debit harus sama dengan Total Kredit</li>
                        <li>Semua akun nominal (pendapatan & beban) saldo = 0</li>
                        <li>Hanya akun neraca yang memiliki saldo</li>
                        <li>Modal sudah termasuk laba/rugi periode berjalan</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        
        table tr:hover {{
            background-color: #f0f8ff;
        }}
        
        .quick-actions {{
            animation: fadeIn 0.5s ease-in-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @media print {{
            .no-print {{
                display: none !important;
            }}
            
            .quick-actions {{
                margin: 0;
                padding: 0;
            }}
            
            .welcome-section {{
                display: none;
            }}
        }}
        
        @media (max-width: 768px) {{
            .quick-actions > div > form {{
                grid-template-columns: 1fr;
            }}
            
            table {{
                font-size: 12px;
            }}
            
            table th,
            table td {{
                padding: 8px 5px;
            }}
            
            h3 {{
                font-size: 18px;
            }}
        }}
    </style>

    <script>
        // Auto-submit form ketika periode diubah
        document.addEventListener('DOMContentLoaded', function() {{
            const periodSelect = document.querySelector('select[name="period"]');
            periodSelect.addEventListener('change', function() {{
                document.getElementById('periodForm').submit();
            }});
        }});

        function printReport() {{
            window.print();
        }}

        // Highlight row on hover
        document.addEventListener('DOMContentLoaded', function() {{
            const tableRows = document.querySelectorAll('tbody tr');
            tableRows.forEach(row => {{
                row.addEventListener('mouseenter', function() {{
                    this.style.backgroundColor = '#f0f8ff';
                }});
                row.addEventListener('mouseleave', function() {{
                    this.style.backgroundColor = '';
                }});
            }});
        }});
    </script>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id=user_id, user_role=user_role)

# ============================================================
# 👑 16. ADMIN PANEL
# ============================================================

@app.route("/admin/users")
@super_admin_required
def admin_users():
    """Halaman super admin untuk mengelola user"""
    try:
        users = supabase.table("users").select("*").order("created_at", desc=True).execute()
        users_data = users.data if users else []
    except Exception as e:
        logger.error(f"❌ Error fetching users: {e}")
        users_data = []

    user_email = session.get('user_email')
    user_name = session.get('user_name', 'Super Admin')
    user_role = get_user_role()
    
    users_html = ""
    for user in users_data:
        role_badge = ""
        if user.get('role') == 'super_admin':
            role_badge = '<span style="background: #dc3545; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px;">Super Admin</span>'
        elif user.get('role') == 'admin':
            role_badge = '<span style="background: #007bff; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px;">Admin</span>'
        else:
            role_badge = '<span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px;">Pembeli</span>'
        
        users_html += f"""
        <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px;">
            <div style="display: flex; justify-content: between; align-items: center;">
                <div>
                    <strong>{user.get('name')}</strong><br>
                    <small>{user.get('email')}</small><br>
                    <small>ID: {user.get('id')}</small>
                </div>
                <div>
                    {role_badge}
                    <br>
                    <small>{user.get('created_at', '').split('T')[0]}</small>
                </div>
            </div>
            <div style="margin-top: 10px;">
                <form method="POST" action="/admin/update_role" style="display: inline;">
                    <input type="hidden" name="user_id" value="{user.get('id')}">
                    <select name="new_role" style="padding: 5px; margin-right: 5px;">
                        <option value="pembeli" {'selected' if user.get('role') == 'pembeli' else ''}>Pembeli</option>
                        <option value="admin" {'selected' if user.get('role') == 'admin' else ''}>Admin</option>
                        {'<option value="super_admin" selected>Super Admin</option>' if user.get('role') == 'super_admin' else ''}
                    </select>
                    <button type="submit" class="btn-warning" style="padding: 5px 10px;">Update Role</button>
                </form>
            </div>
        </div>
        """

    content = f"""
    <div class="welcome-section">
        <h2>👑 Management User</h2>
        <div class="welcome-message">
            Kelola role dan akses user di sistem Lelestari
        </div>
    </div>

    <div class="quick-actions">
        <h2>Daftar User Terdaftar</h2>
        <div style="max-height: 600px; overflow-y: auto;">
            {users_html if users_html else '<p>Tidak ada user terdaftar</p>'}
        </div>
    </div>
    """
    
    return render_template_string(dashboard_html, content=content, user_email=user_email, user_name=user_name, user_id="Super Admin", user_role=user_role)

# ============================================================
# 🔹 ADMIN UPDATE ROLE
# ============================================================

@app.route("/admin/update_role", methods=["POST"])
@super_admin_required
def update_user_role():
    """Update role user oleh super admin"""
    user_id = request.form.get('user_id')
    new_role = request.form.get('new_role')
    
    try:
        supabase.table("users").update({"role": new_role}).eq("id", user_id).execute()
        logger.info(f"✅ Role user {user_id} diupdate menjadi {new_role}")
        
        user_data = supabase.table("users").select("email, name").eq("id", user_id).execute()
        if user_data.data:
            user_email = user_data.data[0]['email']
            user_name = user_data.data[0]['name']
            
            email_body = f"""
            Halo {user_name},

            Akses Anda di sistem Lelestari telah diupdate:

            🔐 Role Baru: {new_role.upper()}
            📧 Email: {user_email}
            🕐 Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M')}

            {"🎉 Selamat! Sekarang Anda memiliki akses admin untuk mengelola sistem." if new_role in ['admin', 'super_admin'] else "📋 Anda sekarang terdaftar."}

            Terima kasih,
            🌿 Tim Lelestari 🍃
            """
            
            send_email(user_email, f"🌿 Update Akses Lelestari - Role {new_role.title()}", email_body)
    
    except Exception as e:
        logger.error(f"❌ Error update role: {e}")
    
    return redirect('/admin/users')

# ============================================================
# 🔹 API ROUTES
# ============================================================

@app.route("/api/save_transaction", methods=["POST"])
@admin_required
def api_save_transaction():
    """API untuk menyimpan transaksi ke jurnal umum"""
    data = request.get_json()
    
    try:
        transaction_date = data.get('transaction_date')
        description = data.get('description')
        total_amount = data.get('total_amount')
        entries = data.get('entries', [])
        
        if not transaction_date or not description or not entries:
            return jsonify({"success": False, "message": "Data transaksi tidak lengkap"})
        
        # Validasi balance
        total_debit = sum([entry['amount'] for entry in entries if entry['position'] == 'debit'])
        total_credit = sum([entry['amount'] for entry in entries if entry['position'] == 'kredit'])
        
        if total_debit != total_credit:
            return jsonify({"success": False, "message": "Total debit dan kredit tidak balance"})
        
        # Generate transaction number
        transaction_number = generate_invoice("JNL")
        
        # Simpan header transaksi
        transaction_data = {
            "transaction_number": transaction_number,
            "transaction_date": transaction_date,
            "description": description,
            "total_amount": total_amount,
            "created_by": session.get('user_name', 'Admin'),
            "created_at": datetime.utcnow().isoformat()
        }
        
        transaction_result = supabase.table("general_journals").insert(transaction_data).execute()
        transaction_id = transaction_result.data[0]['id'] if transaction_result.data else None
        
        if not transaction_id:
            return jsonify({"success": False, "message": "Gagal menyimpan header transaksi"})
        
        # Simpan detail entries
        journal_entries = []
        for entry in entries:
            journal_entry = {
                "journal_id": transaction_id,
                "account_code": entry['account_code'],
                "position": entry['position'],
                "amount": entry['amount'],
                "note": entry.get('note', ''),
                "created_at": datetime.utcnow().isoformat()
            }
            journal_entries.append(journal_entry)
        
        # Simpan semua entries sekaligus
        entries_result = supabase.table("journal_entries").insert(journal_entries).execute()
        
        if entries_result.data:
            logger.info(f"✅ Transaction saved: {transaction_number} with {len(entries)} entries")
            return jsonify({
                "success": True, 
                "message": f"Transaksi {transaction_number} berhasil disimpan",
                "transaction_number": transaction_number
            })
        else:
            # Rollback: hapus header transaksi jika gagal simpan entries
            supabase.table("general_journals").delete().eq("id", transaction_id).execute()
            return jsonify({"success": False, "message": "Gagal menyimpan detail transaksi"})

    except Exception as e:
        logger.error(f"❌ Error saving transaction: {e}")
        return jsonify({"success": False, "message": f"Terjadi kesalahan sistem: {str(e)}"})

@app.route("/api/delete_journal_transaction", methods=["POST"])
@admin_required
def api_delete_journal_transaction():
    """API untuk menghapus transaksi jurnal"""
    data = request.get_json()
    
    try:
        transaction_id = data.get('transaction_id')
        
        if not transaction_id:
            return jsonify({"success": False, "message": "Transaction ID tidak ditemukan"})
        
        result = delete_journal_transaction(transaction_id)
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Error deleting journal transaction: {e}")
        return jsonify({"success": False, "message": f"Terjadi kesalahan sistem: {str(e)}"})

@app.route("/api/save_adjusting_journal", methods=["POST"])
@admin_required
def api_save_adjusting_journal():
    """API untuk menyimpan jurnal penyesuaian"""
    data = request.get_json()
    
    try:
        result = save_adjusting_journal(data)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error saving adjusting journal via API: {e}")
        return jsonify({"success": False, "message": f"Terjadi kesalahan: {str(e)}"})

@app.route("/api/delete_adjusting_journal", methods=["POST"])
@admin_required
def api_delete_adjusting_journal():
    """API untuk menghapus jurnal penyesuaian"""
    data = request.get_json()
    
    try:
        adjusting_journal_id = data.get('adjusting_journal_id')
        result = delete_adjusting_journal(adjusting_journal_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error deleting adjusting journal via API: {e}")
        return jsonify({"success": False, "message": f"Terjadi kesalahan: {str(e)}"})

@app.route("/api/add_account", methods=["POST"])
@admin_required
def api_add_account():
    """API untuk menambah akun baru ke Chart of Account"""
    data = request.get_json()
    
    try:
        account_data = {
            "account_code": data.get('account_code'),
            "account_name": data.get('account_name'),
            "account_type": data.get('account_type'),
            "category": data.get('category'),
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = add_account_to_chart(account_data)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error adding account via API: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/delete_account", methods=["POST"])
@admin_required
def api_delete_account():
    """API untuk menghapus akun dari Chart of Account"""
    data = request.get_json()
    
    try:
        account_code = data.get('account_code')
        result = delete_account_from_chart(account_code)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error deleting account via API: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/add_opening_balance", methods=["POST"])
@admin_required
def api_add_opening_balance():
    """API untuk menambah/mengupdate saldo awal"""
    data = request.get_json()
    
    try:
        account_code = data.get('account_code')
        position = data.get('position')
        amount = data.get('amount')
        description = data.get('description', '')
        
        if not account_code or not position or not amount:
            return jsonify({"success": False, "message": "Data tidak lengkap"})
        
        # Validasi position
        if position not in ['debit', 'kredit']:
            return jsonify({"success": False, "message": "Posisi harus 'debit' atau 'kredit'"})
        
        # Validasi amount
        try:
            amount = float(amount)
            if amount <= 0:
                return jsonify({"success": False, "message": "Nominal harus lebih dari 0"})
        except ValueError:
            return jsonify({"success": False, "message": "Nominal harus berupa angka"})
        
        # Simpan saldo awal
        result = add_opening_balance(account_code, position, amount, description)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error in api_add_opening_balance: {e}")
        return jsonify({"success": False, "message": f"Terjadi kesalahan sistem: {str(e)}"})

@app.route("/api/delete_opening_balance", methods=["POST"])
@admin_required
def api_delete_opening_balance():
    """API untuk menghapus saldo awal"""
    data = request.get_json()
    
    try:
        balance_id = data.get('balance_id')
        
        if not balance_id:
            return jsonify({"success": False, "message": "Balance ID tidak ditemukan"})
        
        result = delete_opening_balance(balance_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error in api_delete_opening_balance: {e}")
        return jsonify({"success": False, "message": f"Terjadi kesalahan sistem: {str(e)}"})

# ============================================================
# 🔹 INISIALISASI SISTEM
# ============================================================
if __name__ == "__main__":
    print("🚀 Lelestari dengan Sistem Inventory Lengkap & Chart of Account Running...")
    print(f"📧 Email Sender: {EMAIL_SENDER}")
    print(f"🔗 Supabase: {SUPABASE_URL}")
    print(f"👑 Super Admin: lelestari.management@gmail.com | Password: Lelestari2KN")
    print("💡 Test: http://localhost:5000")
    print("🔧 Admin Panel: http://localhost:5000/admin/users (Super Admin)")
    print("📊 Reports: http://localhost:5000/reports (Admin/Super Admin)")
    print("📊 Chart of Account: http://localhost:5000/chart_of_account (Admin/Super Admin)")
    print("💰 Neraca Saldo Awal: http://localhost:5000/neraca_saldo_awal (Admin/Super Admin)")
    print("📝 Input Transaksi: http://localhost:5000/input_transaksi (Admin/Super Admin)")
    print("📋 Jurnal Umum: http://localhost:5000/jurnal_umum (Admin/Super Admin)")
    print("📒 Buku Besar: http://localhost:5000/buku_besar (Admin/Super Admin)")
    print("📊 NSSP: http://localhost:5000/nssp (Admin/Super Admin)")
    print("📈 Laporan Laba Rugi: http://localhost:5000/laporan_laba_rugi")
    print("📊 Laporan Perubahan Modal: http://localhost:5000/laporan_perubahan_modal")  
    print("💰 Laporan Posisi Keuangan: http://localhost:5000/laporan_posisi_keuangan")
    print("💸 Laporan Arus Kas: http://localhost:5000/laporan_arus_kas")
    print("📒 Jurnal Penutup: http://localhost:5000/jurnal_penutup (Admin/Super Admin)")
    print("📊 Neraca Saldo Setelah Penutup: http://localhost:5000/neraca_saldo_setelah_penutup (Admin/Super Admin)")
    print("🔍 Test DB: http://localhost:5000/test_db")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)