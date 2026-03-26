from app import app
from models import db, Vicentino  # 👈 ajuste se seu arquivo tiver outro nome
from werkzeug.security import generate_password_hash

with app.app_context():
    admin_existente = Vicentino.query.filter_by(email='admin@email.com').first()

    if admin_existente:
        print("Admin já existe!")
    else:
        admin = Vicentino(
            nome='Admin',
            sobrenome='Sistema',
            cpf='12345678901',
            email='admin@email.com',
            senha_hash=generate_password_hash('123456'),
            tipo='admin',
            status='ativo',
            email_confirmado=True
        )

        db.session.add(admin)
        db.session.commit()

        print("Admin criado com sucesso!")