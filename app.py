from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from datetime import datetime
from PIL import Image, UnidentifiedImageError
from email_validator import validate_email, EmailNotValidError
from phonenumbers import NumberParseException

import phonenumbers
import time
import re
import os

from config import Config
from models import db, Vicentino

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

app.config['UPLOAD_FOLDER_USUARIO'] = os.path.join(app.root_path, 'static', 'fotos_perfil')
os.makedirs(app.config['UPLOAD_FOLDER_USUARIO'], exist_ok=True)


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================
def apenas_letras(texto):
    return re.fullmatch(r"[A-Za-zÀ-ÿ\s]+", texto) is not None


def email_valido(email):
    try:
        valid = validate_email(email, check_deliverability=False)
        return valid.normalized
    except EmailNotValidError:
        return None


def telefone_valido_br(telefone):
    try:
        numero = phonenumbers.parse(telefone, 'BR')

        if phonenumbers.is_valid_number(numero):
            return phonenumbers.format_number(
                numero,
                phonenumbers.PhoneNumberFormat.E164
            )

        return None

    except NumberParseException:
        return None


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
        subject='Confirmação de cadastro - Famílias Asistidas SSVP',
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
        subject='Redefinição de senha - Famílias Asistidas SSVP',
        recipients=[vicentino.email]
    )

    msg.body = f'''Olá, {vicentino.nome}!

Recebemos uma solicitação para redefinir sua senha.

Para cadastrar uma nova senha, clique no link abaixo:

{link}

Se você não solicitou essa alteração, ignore este e-mail.
'''

    mail.send(msg)


# =========================================================
# ROTAS PÚBLICAS / INICIAIS
# =========================================================
@app.route('/')
def home():
    if 'vicentino_id' in session:
        return redirect(url_for('dashboard'))
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

            if 'ultimo_envio_confirmacao' not in session:
                session['ultimo_envio_confirmacao'] = int(time.time())

            flash('Sua conta ainda não foi confirmada por e-mail.', 'warning')
            return redirect(url_for('login'))

        session.pop('email_pendente_confirmacao', None)
        session.pop('ultimo_envio_confirmacao', None)

        session['vicentino_id'] = vicentino.id
        session['vicentino_nome'] = vicentino.nome
        session['vicentino_email'] = vicentino.email
        session['vicentino_foto'] = vicentino.foto if hasattr(vicentino, 'foto') else None

        flash('Login realizado com sucesso.', 'success')
        return redirect(url_for('dashboard'))

    email_pendente = session.get('email_pendente_confirmacao')
    ultimo_envio = session.get('ultimo_envio_confirmacao', 0)
    agora = int(time.time())

    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if email_pendente else 0

    if email_pendente:
        vicentino = Vicentino.query.filter_by(email=email_pendente).first()

        if vicentino and vicentino.email_confirmado and vicentino.status == 'ativo':
            session.pop('email_pendente_confirmacao', None)
            session.pop('ultimo_envio_confirmacao', None)
            email_pendente = None
            tempo_restante = 0

        elif tempo_restante == 0:
            session.pop('email_pendente_confirmacao', None)
            session.pop('ultimo_envio_confirmacao', None)
            email_pendente = None

    return render_template(
        'login.html',
        email_pendente=email_pendente,
        tempo_restante=tempo_restante
    )


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        cpf = request.form.get('cpf', '').strip()
        email_informado = request.form.get('email', '').strip()
        telefone = request.form.get('telefone', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')
        foto = request.files.get('foto')
        conselho = request.form.get('conselho', '').strip()
        conferencia = request.form.get('conferencia', '').strip()

        email = email_valido(email_informado)
        if not email:
            flash('Informe um e-mail válido.', 'danger')
            return redirect(url_for('cadastro'))

        if not nome or not sobrenome or not email or not senha or not confirmar_senha:
            flash('Preencha todos os campos obrigatórios.', 'danger')
            return redirect(url_for('cadastro'))

        if not apenas_letras(nome) or not apenas_letras(sobrenome):
            flash('Nome e sobrenome devem conter apenas letras.', 'danger')
            return redirect(url_for('cadastro'))

        if len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
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
            telefone_formatado = telefone_valido_br(telefone)

            if not telefone_formatado:
                flash('Informe um telefone válido.', 'danger')
                return redirect(url_for('cadastro'))

        nome_arquivo_foto = None

        if foto and foto.filename:
            extensoes_permitidas = {'jpg', 'jpeg', 'png', 'webp'}

            nome_seguro = secure_filename(foto.filename)
            extensao = nome_seguro.rsplit('.', 1)[-1].lower() if '.' in nome_seguro else ''

            if extensao not in extensoes_permitidas:
                flash('Formato de imagem inválido. Envie jpg, jpeg, png ou webp ', 'danger')
                return redirect(url_for('cadastro'))

            try:
                foto.stream.seek(0)
                imagem = Image.open(foto)

                if imagem.mode in ('RGBA', 'P'):
                    imagem = imagem.convert('RGB')

                nome_arquivo_foto = f'vicentino_{int(time.time())}.jpg'
                caminho_foto = os.path.join(app.config['UPLOAD_FOLDER_USUARIO'], nome_arquivo_foto)

                imagem = imagem.resize((400, 400), Image.Resampling.LANCZOS)
                imagem.save(caminho_foto, quality=90)

            except UnidentifiedImageError:
                flash('Arquivo de imagem inválido.', 'danger')
                return redirect(url_for('cadastro'))
            except Exception:
                flash('Não foi possível salvar a foto de perfil.', 'danger')
                return redirect(url_for('cadastro'))

        novo_vicentino = Vicentino(
            nome=nome,
            sobrenome=sobrenome,
            cpf=cpf if cpf else None,
            email=email,
            telefone=telefone_formatado,
            senha_hash=generate_password_hash(senha),
            status='pendente',
            email_confirmado=False,
            foto=nome_arquivo_foto,
            conselho=conselho if conselho else None,
            conferencia=conferencia if conferencia else None
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


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))


# =========================================================
# CONFIRMAÇÃO DE E-MAIL
# =========================================================
@app.route('/confirmar_email/<token>')
def confirmar_email(token):
    email = validar_token(token, 'confirmar-email', 86400)

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


# =========================================================
# RECUPERAÇÃO DE SENHA
# =========================================================
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

    if email_pendente and tempo_restante == 0:
        session.pop('email_pendente_redefinicao', None)
        session.pop('ultimo_envio_redefinicao', None)
        email_pendente = None

    return render_template(
        'esqueci_senha.html',
        email_pendente=email_pendente,
        tempo_restante=tempo_restante
    )


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


@app.route('/redefinir_senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    email = validar_token(token, 'redefinir-senha', 900)

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


# =========================================================
# ÁREA LOGADA
# =========================================================
@app.route('/dashboard')
def dashboard():
    if 'vicentino_id' not in session:
        flash('Faça login para acessar o sistema.', 'warning')
        return redirect(url_for('login'))

    return render_template('dashboard.html')


@app.route('/perfil')
def perfil():
    if 'vicentino_id' not in session:
        return redirect(url_for('login'))

    usuario = Vicentino.query.get(session['vicentino_id'])
    return render_template('perfil.html', usuario=usuario)


@app.route('/editar_perfil', methods=['GET', 'POST'])
def editar_perfil():
    if 'vicentino_id' not in session:
        flash('Faça login para acessar seu perfil.', 'warning')
        return redirect(url_for('login'))

    usuario = Vicentino.query.get(session['vicentino_id'])

    if not usuario:
        session.clear()
        flash('Usuário não encontrado. Faça login novamente.', 'danger')
        return redirect(url_for('login'))

    erros = {}
    extensoes_permitidas = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'jfif'}

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        telefone = request.form.get('telefone', '').strip()
        conselho = request.form.get('conselho', '').strip()
        conferencia = request.form.get('conferencia', '').strip()

        senha_atual = request.form.get('senha_atual', '').strip()
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        if not nome:
            erros['nome'] = 'Informe o nome.'
        elif not apenas_letras(nome):
            erros['nome'] = 'O nome deve conter apenas letras.'

        if not sobrenome:
            erros['sobrenome'] = 'Informe o sobrenome.'
        elif not apenas_letras(sobrenome):
            erros['sobrenome'] = 'O sobrenome deve conter apenas letras.'

        telefone_formatado = None
        if telefone:
            telefone_formatado = telefone_valido_br(telefone)
            if not telefone_formatado:
                erros['telefone'] = 'Telefone inválido.'

        foto = request.files.get('foto')

        if foto and foto.filename:
            nome_foto = secure_filename(foto.filename)
            extensao = nome_foto.rsplit('.', 1)[-1].lower() if '.' in nome_foto else ''

            if extensao not in extensoes_permitidas:
                erros['foto'] = 'Formato de arquivo não suportado. Envie apenas imagens.'
            else:
                try:
                    foto.stream.seek(0)
                    imagem = Image.open(foto)

                    if imagem.mode in ('RGBA', 'P'):
                        imagem = imagem.convert('RGB')

                    imagem = imagem.resize((400, 400), Image.Resampling.LANCZOS)

                    nome_arquivo = f'vicentino_{usuario.id}.jpg'
                    caminho_foto = os.path.join(app.config['UPLOAD_FOLDER_USUARIO'], nome_arquivo)

                    imagem.save(caminho_foto, quality=90)
                    usuario.foto = nome_arquivo

                except UnidentifiedImageError:
                    erros['foto'] = 'Arquivo inválido. Envie apenas imagens.'
                except Exception:
                    erros['foto'] = 'Não foi possível salvar a imagem.'

        if senha_atual or nova_senha or confirmar_senha:
            if not senha_atual:
                erros['senha_atual'] = 'Informe a senha atual.'

            if not nova_senha:
                erros['nova_senha'] = 'Informe a nova senha.'

            if not confirmar_senha:
                erros['confirmar_senha'] = 'Confirme a nova senha.'

            if senha_atual and not check_password_hash(usuario.senha_hash, senha_atual):
                erros['senha_atual'] = 'Senha atual incorreta.'

            if nova_senha and confirmar_senha and nova_senha != confirmar_senha:
                erros['confirmar_senha'] = 'A confirmação da senha não coincide.'

            if nova_senha and len(nova_senha) < 6:
                erros['nova_senha'] = 'A nova senha deve ter pelo menos 6 caracteres.'

            if 'senha_atual' not in erros and 'nova_senha' not in erros and 'confirmar_senha' not in erros:
                usuario.senha_hash = generate_password_hash(nova_senha)

        if erros:
            for campo, mensagem in erros.items():
                flash(mensagem, 'danger')

            return render_template('editar_perfil.html', usuario=usuario, erros=erros)

        usuario.nome = nome
        usuario.sobrenome = sobrenome
        usuario.telefone = telefone_formatado
        usuario.conselho = conselho if conselho else None
        usuario.conferencia = conferencia if conferencia else None

        db.session.commit()

        session['vicentino_nome'] = usuario.nome
        session['vicentino_email'] = usuario.email
        session['vicentino_foto'] = usuario.foto if usuario.foto else None

        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('editar_perfil'))

    return render_template('editar_perfil.html', usuario=usuario, erros=erros)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)