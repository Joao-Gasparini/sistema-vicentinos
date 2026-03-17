from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from datetime import datetime
import time
import re

from config import Config
from models import db, Vicentino

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
mail = Mail(app)

serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

def apenas_letras(texto):
    return re.fullmatch(r"[A-Za-zÀ-ÿ\s]+", texto) is not None

def email_valido(email):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None

def senha_forte(senha):
    return re.fullmatch(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$', senha) is not None

def gerar_token(email, salt):
    return serializer.dumps(email, salt=salt)


def validar_token(token, salt, expiracao):
    try:
        email = serializer.loads(token, salt=salt, max_age=expiracao)
        return email
    except SignatureExpired:
        return None
    except BadSignature:
        return None


def enviar_email_confirmacao(vicentino):
    token = gerar_token(vicentino.email, 'confirmar-email')
    link = url_for('confirmar_email', token=token, _external=True)

    msg = Message(
        subject='Confirmação de cadastro - Sistema Vicentinos',
        recipients=[vicentino.email]
    )

    msg.body = f'''Olá, {vicentino.nome}!

Seu cadastro foi realizado com sucesso.

Para confirmar seu e-mail e ativar sua conta, clique no link abaixo:

{link}

Se você não solicitou este cadastro, ignore este e-mail.
'''

    mail.send(msg)


def enviar_email_redefinicao(vicentino):
    token = gerar_token(vicentino.email, 'redefinir-senha')
    link = url_for('redefinir_senha', token=token, _external=True)

    msg = Message(
        subject='Redefinição de senha - Sistema Vicentinos',
        recipients=[vicentino.email]
    )

    msg.body = f'''Olá, {vicentino.nome}!

Recebemos uma solicitação para redefinir sua senha.

Para cadastrar uma nova senha, clique no link abaixo:

{link}

Se você não solicitou essa alteração, ignore este e-mail.
'''

    mail.send(msg)


@app.route('/')
def home():
    if 'vicentino_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        cpf = request.form.get('cpf', '').strip()
        email = request.form.get('email', '').strip().lower()
        telefone = request.form.get('telefone', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        telefone_numeros = re.sub(r'\D', '', telefone)

        if not nome or not sobrenome or not email or not senha or not confirmar_senha:
            flash('Preencha todos os campos obrigatórios.', 'danger')
            return redirect(url_for('cadastro'))

        if not apenas_letras(nome) or not apenas_letras(sobrenome):
            flash('Nome e sobrenome devem conter apenas letras.', 'danger')
            return redirect(url_for('cadastro'))

        if not email_valido(email):
            flash('E-mail inválido.', 'danger')
            return redirect(url_for('cadastro'))

        if telefone and len(telefone_numeros) not in [10, 11]:
            flash('Informe um telefone válido com DDD.', 'danger')
            return redirect(url_for('cadastro'))

        if not senha_forte(senha):
            flash('A senha deve conter maiúscula, minúscula, número, símbolo e no mínimo 8 caracteres.', 'danger')
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

        telefone_formatado = None

        if telefone:
            if len(telefone_numeros) == 11:
                telefone_formatado = f'({telefone_numeros[:2]}) {telefone_numeros[2:7]}-{telefone_numeros[7:]}'
            elif len(telefone_numeros) == 10:
                telefone_formatado = f'({telefone_numeros[:2]}) {telefone_numeros[2:6]}-{telefone_numeros[6:]}'

        novo_vicentino = Vicentino(
            nome=nome,
            sobrenome=sobrenome,
            cpf=cpf if cpf else None,
            email=email,
            telefone=telefone_formatado,
            senha_hash=generate_password_hash(senha),
            status='pendente',
            email_confirmado=False
        )

        db.session.add(novo_vicentino)
        db.session.commit()

        try:
            enviar_email_confirmacao(novo_vicentino)
            session['email_pendente_confirmacao'] = novo_vicentino.email
            session['ultimo_envio_confirmacao'] = int(time.time())
            flash('Cadastro realizado com sucesso. Verifique seu e-mail para confirmar a conta.', 'success')
        except Exception as e:
            flash(f'Cadastro realizado, mas houve erro ao enviar o e-mail de confirmação: {str(e)}', 'warning')

        return redirect(url_for('login'))

    return render_template('cadastro_vicentino.html')

@app.route('/confirmar_email/<token>')
def confirmar_email(token):
    email = validar_token(token, 'confirmar-email', 86400)  # 24 horas

    if not email:
        flash('Link de confirmação inválido ou expirado.', 'danger')
        return redirect(url_for('login'))

    vicentino = Vicentino.query.filter_by(email=email).first()

    if not vicentino:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('login'))

    if vicentino.email_confirmado:
        flash('Este e-mail já foi confirmado. Faça login.', 'info')
        return redirect(url_for('login'))

    vicentino.email_confirmado = True
    vicentino.status = 'ativo'
    vicentino.data_confirmacao = datetime.utcnow()
    db.session.commit()

    flash('E-mail confirmado com sucesso. Agora você já pode fazer login.', 'success')
    return redirect(url_for('login'))


@app.route('/reenviar_confirmacao', methods=['POST'])
def reenviar_confirmacao():
    email = request.form.get('email', '').strip().lower()

    if not email:
        email = session.get('email_pendente_confirmacao', '').strip().lower()

    if not email:
        flash('Informe seu e-mail.', 'danger')
        return redirect(url_for('login'))

    vicentino = Vicentino.query.filter_by(email=email).first()

    if not vicentino:
        flash('Se o e-mail estiver cadastrado, um novo link será enviado.', 'info')
        return redirect(url_for('login'))

    if vicentino.email_confirmado:
        session.pop('email_pendente_confirmacao', None)
        session.pop('ultimo_envio_confirmacao', None)
        flash('Este e-mail já foi confirmado. Faça login.', 'info')
        return redirect(url_for('login'))

    ultimo_envio = session.get('ultimo_envio_confirmacao', 0)
    agora = int(time.time())

    if agora - ultimo_envio < 50:
        restantes = 50 - (agora - ultimo_envio)
        flash(f'Aguarde {restantes} segundos para reenviar o e-mail.', 'warning')
        return redirect(url_for('login'))

    try:
        enviar_email_confirmacao(vicentino)
        session['email_pendente_confirmacao'] = vicentino.email
        session['ultimo_envio_confirmacao'] = int(time.time())
        flash('E-mail de confirmação reenviado com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro ao reenviar e-mail: {str(e)}', 'danger')

    return redirect(url_for('login'))


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

        if not check_password_hash(vicentino.senha_hash, senha):
            flash('E-mail ou senha inválidos.', 'danger')
            return redirect(url_for('login'))

        if not vicentino.email_confirmado or vicentino.status != 'ativo':
            session['email_pendente_confirmacao'] = vicentino.email

            # só define o tempo se ainda não existir
            if 'ultimo_envio_confirmacao' not in session:
                session['ultimo_envio_confirmacao'] = int(time.time())

            flash('Sua conta ainda não foi confirmada por e-mail.', 'warning')
            return redirect(url_for('login'))

        session.pop('email_pendente_confirmacao', None)
        session.pop('ultimo_envio_confirmacao', None)

        session['vicentino_id'] = vicentino.id
        session['vicentino_nome'] = f'{vicentino.nome} {vicentino.sobrenome}'
        session['vicentino_email'] = vicentino.email

        flash('Login realizado com sucesso.', 'success')
        return redirect(url_for('dashboard'))

    email_pendente = session.get('email_pendente_confirmacao')
    ultimo_envio = session.get('ultimo_envio_confirmacao', 0)
    agora = int(time.time())

    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if email_pendente else 0

    if email_pendente:
        vicentino = Vicentino.query.filter_by(email=email_pendente).first()

        # se já confirmou, limpa tudo
        if vicentino and vicentino.email_confirmado and vicentino.status == 'ativo':
            session.pop('email_pendente_confirmacao', None)
            session.pop('ultimo_envio_confirmacao', None)
            email_pendente = None
            tempo_restante = 0

        # se passou o tempo e ainda não confirmou, limpa a mensagem antiga
        elif tempo_restante == 0:
            session.pop('email_pendente_confirmacao', None)
            session.pop('ultimo_envio_confirmacao', None)
            email_pendente = None

    return render_template(
        'login.html',
        email_pendente=email_pendente,
        tempo_restante=tempo_restante
    )

@app.route('/esqueci_senha', methods=['GET', 'POST'])
def esqueci_senha():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Informe seu e-mail.', 'danger')
            return redirect(url_for('esqueci_senha'))

        ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
        agora = int(time.time())

        if agora - ultimo_envio < 50:
            restantes = 50 - (agora - ultimo_envio)
            flash(f'Aguarde {restantes} segundos para reenviar o e-mail de redefinição.', 'warning')
            return redirect(url_for('esqueci_senha'))

        vicentino = Vicentino.query.filter_by(email=email).first()

        if vicentino:
            try:
                enviar_email_redefinicao(vicentino)
            except Exception as e:
                flash(f'Erro ao enviar e-mail: {str(e)}', 'danger')
                return redirect(url_for('esqueci_senha'))

        session['email_pendente_redefinicao'] = email
        session['ultimo_envio_redefinicao'] = int(time.time())

        flash('Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha.', 'info')
        return redirect(url_for('esqueci_senha'))

    email_pendente = session.get('email_pendente_redefinicao')
    ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
    agora = int(time.time())

    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if email_pendente else 0

    # se já passou o tempo, limpa a info antiga para não ficar aparecendo sempre
    if email_pendente and tempo_restante == 0:
        session.pop('email_pendente_redefinicao', None)
        session.pop('ultimo_envio_redefinicao', None)
        email_pendente = None

    return render_template(
        'esqueci_senha.html',
        email_pendente=email_pendente,
        tempo_restante=tempo_restante
    )

@app.route('/redefinir_senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    email = validar_token(token, 'redefinir-senha', 3600)  # 1 hora

    if not email:
        flash('Link inválido ou expirado.', 'danger')
        return redirect(url_for('login'))

    vicentino = Vicentino.query.filter_by(email=email).first()

    if not vicentino:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')

        if not senha or not confirmar_senha:
            flash('Preencha os dois campos de senha.', 'danger')
            return redirect(url_for('redefinir_senha', token=token))

        if senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return redirect(url_for('redefinir_senha', token=token))

        vicentino.senha_hash = generate_password_hash(senha)
        db.session.commit()

        session.pop('email_pendente_redefinicao', None)
        session.pop('ultimo_envio_redefinicao', None)
        session.pop('email_pendente_confirmacao', None)
        session.pop('ultimo_envio_confirmacao', None)

        flash('Senha redefinida com sucesso. Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('redefinir_senha.html', token=token)

@app.route('/reenviar_redefinicao', methods=['POST'])
def reenviar_redefinicao():
    email = request.form.get('email', '').strip().lower()

    if not email:
        email = session.get('email_pendente_redefinicao', '').strip().lower()

    if not email:
        flash('Informe seu e-mail.', 'danger')
        return redirect(url_for('esqueci_senha'))

    ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
    agora = int(time.time())

    if agora - ultimo_envio < 50:
        restantes = 50 - (agora - ultimo_envio)
        flash(f'Aguarde {restantes} segundos para reenviar o e-mail de redefinição.', 'warning')
        return redirect(url_for('esqueci_senha'))

    vicentino = Vicentino.query.filter_by(email=email).first()

    if vicentino:
        try:
            enviar_email_redefinicao(vicentino)
            session['email_pendente_redefinicao'] = email
            session['ultimo_envio_redefinicao'] = int(time.time())
            flash('E-mail de redefinição reenviado com sucesso.', 'success')
        except Exception as e:
            flash(f'Erro ao reenviar e-mail: {str(e)}', 'danger')
            return redirect(url_for('esqueci_senha'))
    else:
        session['email_pendente_redefinicao'] = email
        session['ultimo_envio_redefinicao'] = int(time.time())
        flash('Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha.', 'info')

    return redirect(url_for('esqueci_senha'))

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


@app.route('/teste_email')
def teste_email():
    try:
        msg = Message(
            subject='Teste de envio de e-mail',
            recipients=['SEUEMAIL@gmail.com'],
            body='Se você recebeu este e-mail, o Flask-Mail está funcionando corretamente.'
        )
        mail.send(msg)
        return 'E-mail enviado com sucesso!'
    except Exception as e:
        return f'Erro ao enviar e-mail: {str(e)}'


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)