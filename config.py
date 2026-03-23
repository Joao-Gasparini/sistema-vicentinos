import os

class Config:
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:@localhost/vicentinos'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv('SECRET_KEY')

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'sistemavicentinosrolanida@gmail.com'
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = 'sistemavicentinosrolanida@gmail.com'

    # 🔒 SEGURANÇA DE SESSÃO
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False  # True só em produção (HTTPS)
    SESSION_COOKIE_SAMESITE = 'Lax'