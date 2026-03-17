class Config:
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:@localhost/vicentinos'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'vicentinos_sistema_2026_seguro'

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'sistemavicentinosrolandia@gmail.com'
    MAIL_PASSWORD = 'cfkizlyuibqxritu'
    MAIL_DEFAULT_SENDER = 'sistemavicentinosrolandia@gmail.com'
