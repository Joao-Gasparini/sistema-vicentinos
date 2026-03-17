from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from models import db, Vicentino

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)


class Config:
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:@localhost/vicentinos'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'vicentinos_sistema_2026_seguro'

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'sistemavicentinosrolandia@gmail.com'
    MAIL_PASSWORD = 'cfki zlyu ibqx ritu'
    MAIL_DEFAULT_SENDER = 'sistemavicentinosrolandia@gmail.com'


@app.route('/')
def home():
    if 'vicentino_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo', '').strip()
        cpf = request.form.get('cpf', '').strip()
        email = request.form.get('email', '').strip().lower()
        telefone = request.form.get('telefone', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not nome_completo or not email or not senha or not confirmar_senha:
            flash('Preencha todos os campos obrigatórios.', 'danger')
            return redirect(url_for('cadastro'))

        if senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return redirect(url_for('cadastro'))

        usuario_email = Vicentino.query.filter_by(email=email).first()
        if usuario_email:
            flash('Já existe um vicentino cadastrado com este e-mail.', 'danger')
            return redirect(url_for('cadastro'))

        if cpf:
            usuario_cpf = Vicentino.query.filter_by(cpf=cpf).first()
            if usuario_cpf:
                flash('Já existe um vicentino cadastrado com este CPF.', 'danger')
                return redirect(url_for('cadastro'))

        senha_hash = generate_password_hash(senha)

        novo_vicentino = Vicentino(
            nome_completo=nome_completo,
            cpf=cpf if cpf else None,
            email=email,
            telefone=telefone if telefone else None,
            senha_hash=senha_hash,
            status='ativo'
        )

        db.session.add(novo_vicentino)
        db.session.commit()

        flash('Cadastro realizado com sucesso. Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('cadastro_vicentino.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        if not email or not senha:
            flash('Informe e-mail e senha.', 'danger')
            return redirect(url_for('login'))

        vicentino = Vicentino.query.filter_by(email=email).first()

        if not vicentino:
            flash('E-mail ou senha inválidos.', 'danger')
            return redirect(url_for('login'))

        if vicentino.status != 'ativo':
            flash('Usuário inativo. Entre em contato com o administrador.', 'warning')
            return redirect(url_for('login'))

        if check_password_hash(vicentino.senha_hash, senha):
            session['vicentino_id'] = vicentino.id
            session['vicentino_nome'] = vicentino.nome_completo
            session['vicentino_email'] = vicentino.email

            flash('Login realizado com sucesso.', 'success')
            return redirect(url_for('dashboard'))

        flash('E-mail ou senha inválidos.', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'vicentino_id' not in session:
        flash('Faça login para acessar o sistema.', 'warning')
        return redirect(url_for('login'))

    return render_template('dashboard.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)