from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from datetime import datetime
from PIL import Image, UnidentifiedImageError
from email_validator import validate_email, EmailNotValidError
from phonenumbers import NumberParseException
from flask_wtf.csrf import CSRFProtect
from functools import wraps

import phonenumbers
import time
import re
import os

from config import Config
from models import db, Vicentino



app = Flask(__name__)
app.config.from_object(Config)

# Inicialize a proteção CSRF
csrf = CSRFProtect(app)

db.init_app(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

app.config['UPLOAD_FOLDER_USUARIO'] = os.path.join(app.root_path, 'static', 'fotos_perfil')
os.makedirs(app.config['UPLOAD_FOLDER_USUARIO'], exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

@app.errorhandler(413)
def arquivo_muito_grande(e):
    flash('Arquivo muito grande! Máximo permitido: 5MB.', 'danger')
    return redirect(request.referrer or url_for('home'))

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

def telefone_para_input(telefone_e164):
    if not telefone_e164:
        return ''

    # remove +55
    telefone = telefone_e164.replace('+55', '')

    return telefone  # retorna só números (ex: 11999998888)

def cpf_valido(cpf):
    cpf = re.sub(r'\D', '', cpf)  # remove tudo que não for número

    if len(cpf) != 11:
        return False

    # elimina CPFs inválidos tipo 11111111111
    if cpf == cpf[0] * 11:
        return False

    # valida 1º dígito
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    if resto == 10:
        resto = 0
    if resto != int(cpf[9]):
        return False

    # valida 2º dígito
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    if resto == 10:
        resto = 0
    if resto != int(cpf[10]):
        return False

    return True

def gerar_token(email, salt):
    return serializer.dumps(email, salt=salt)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'vicentino_id' not in session:
            return redirect(url_for('login'))

        usuario = Vicentino.query.get(session['vicentino_id'])

        if usuario.tipo != 'admin':
            flash('Acesso restrito.', 'danger')
            return redirect(url_for('home'))

        return f(*args, **kwargs)
    return decorated_function

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
    cpf_input = ''  # valor padrão vazio

    if request.method == 'POST':
        cpf_input = request.form.get('cpf', '').strip()
        senha = request.form.get('senha', '')

        # Remove máscara do CPF
        cpf = re.sub(r'\D', '', cpf_input)

        # Validação básica
        if not cpf or not senha:
            flash('Informe CPF e senha.', 'danger')
            return render_template('login.html', cpf_input=cpf_input)

        # Validação de CPF real
        if not cpf_valido(cpf):
            flash('CPF inválido.', 'danger')
            return render_template('login.html', cpf_input=cpf_input)

        # Busca no banco
        vicentino = Vicentino.query.filter_by(cpf=cpf).first()

        if not vicentino or not check_password_hash(vicentino.senha_hash, senha):
            flash('CPF ou senha incorretos.', 'danger')
            return render_template('login.html', cpf_input=cpf_input)

        # Login bem-sucedido
        session['vicentino_id'] = vicentino.id
        session['vicentino_nome'] = vicentino.nome
        session['vicentino_email'] = vicentino.email
        session['vicentino_foto'] = vicentino.foto if hasattr(vicentino, 'foto') else None
        session['tipo'] = vicentino.tipo

        flash('Login realizado com sucesso.', 'success')
        return redirect(url_for('dashboard'))

    # GET: envia cpf_input vazio
    return render_template('login.html', cpf_input='')

@app.route('/admin/cadastrar_vicentino', methods=['GET', 'POST'])
@admin_required
def cadastrar_vicentino():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        cpf_input = request.form.get('cpf', '').strip()
        # remove máscara
        cpf = re.sub(r'\D', '', cpf_input)
        email_informado = request.form.get('email', '').strip()
        telefone = request.form.get('telefone', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')
        foto = request.files.get('foto')
        conselho = request.form.get('conselho', '').strip()
        conferencia = request.form.get('conferencia', '').strip()

        if email_informado == '':
            email = None
        else:
            email = email_valido(email_informado)
            if not email:
                flash('Informe um e-mail válido.', 'danger')
                return redirect(url_for('cadastrar_vicentino'))

        if not nome or not sobrenome or not senha or not confirmar_senha:
            flash('Preencha todos os campos obrigatórios.', 'danger')
            return redirect(url_for('cadastrar_vicentino'))

        if not apenas_letras(nome) or not apenas_letras(sobrenome):
            flash('Nome e sobrenome devem conter apenas letras.', 'danger')
            return redirect(url_for('cadastrar_vicentino'))

        if cpf:
            if not cpf_valido(cpf):
                flash('CPF inválido.', 'danger')
                return redirect(url_for('cadastrar_vicentino'))

            # verifica se já existe
            if Vicentino.query.filter_by(cpf=cpf).first():
                flash('Já existe um usuário com esse CPF.', 'danger')
                return redirect(url_for('cadastrar_vicentino'))

        if len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
            return redirect(url_for('cadastrar_vicentino'))

        if senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return redirect(url_for('cadastrar_vicentino'))

        if email:
            usuario_email = Vicentino.query.filter_by(email=email).first()
            if usuario_email:
                flash('Já existe um vicentino cadastrado com este e-mail.', 'danger')
                return redirect(url_for('cadastrar_vicentino'))

        # 👉 AQUI MUDA A LÓGICA
        if email:
            status = 'pendente'
            email_confirmado = False
        else:
            status = 'ativo'
            email_confirmado = True

        novo_vicentino = Vicentino(
            nome=nome,
            sobrenome=sobrenome,
            cpf=cpf if cpf else None,
            email=email,
            telefone=telefone,
            senha_hash=generate_password_hash(senha),
            status=status,
            email_confirmado=email_confirmado,
            tipo='vicentino',
            foto=None,
            conselho=conselho if conselho else None,
            conferencia=conferencia if conferencia else None
        )

        db.session.add(novo_vicentino)
        db.session.commit()

        if email:
            try:
                enviar_email_confirmacao(novo_vicentino)
                flash('Vicentino cadastrado! E-mail de confirmação enviado.', 'success')
            except Exception as e:
                flash('Vicentino cadastrado, mas erro ao enviar e-mail.', 'warning')
        else:
            flash('Vicentino cadastrado com sucesso!', 'success')

        return redirect(url_for('dashboard'))

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
    agora = int(time.time())
    tempo_espera = 50

    # -------------------------
    # Usuário logado
    # -------------------------
    if 'vicentino_id' in session:
        usuario = Vicentino.query.get(session['vicentino_id'])
        if not usuario:
            flash('Usuário não encontrado. Faça login novamente.', 'danger')
            return redirect(url_for('login'))

    # -------------------------
    # Usuário deslogado
    # -------------------------
    else:
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Informe seu e-mail.', 'danger')
            return redirect(url_for('login'))

        usuario = Vicentino.query.filter_by(email=email).first()
        if not usuario:
            flash('Se o e-mail estiver cadastrado, um novo link será enviado.', 'info')
            return redirect(url_for('login'))

    # -------------------------
    # Já confirmado
    # -------------------------
    if usuario.email_confirmado:
        session.pop('email_pendente_confirmacao', None)
        session.pop('ultimo_envio_confirmacao', None)
        msg = 'Seu e-mail já está confirmado.'
        flash(msg, 'info')
        return redirect(url_for('editar_perfil')) if 'vicentino_id' in session else redirect(url_for('login'))

    # -------------------------
    # Controle de tempo entre envios
    # -------------------------
    ultimo_envio = session.get('ultimo_envio_confirmacao', 0)
    if agora - ultimo_envio < tempo_espera:
        restantes = tempo_espera - (agora - ultimo_envio)
        flash(f'Aguarde {restantes} segundos para reenviar o e-mail.', 'warning')
        return redirect(url_for('editar_perfil')) if 'vicentino_id' in session else redirect(url_for('login'))

    # -------------------------
    # Envio do e-mail
    # -------------------------
    try:
        enviar_email_confirmacao(usuario)
        session['email_pendente_confirmacao'] = usuario.email
        session['ultimo_envio_confirmacao'] = agora
        flash('E-mail de confirmação reenviado com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro ao reenviar e-mail: {str(e)}', 'danger')

    # -------------------------
    # Redirecionamento final
    # -------------------------
    return redirect(url_for('editar_perfil')) if 'vicentino_id' in session else redirect(url_for('login'))

# =========================================================
# RECUPERAÇÃO DE SENHA
# =========================================================
@app.route('/esqueci_senha', methods=['GET', 'POST'])
def esqueci_senha():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        agora = int(time.time())
        tempo_espera = 50

        # ==========================
        # Usuário logado altera senha direto
        # ==========================
        if 'vicentino_id' in session and nova_senha and confirmar_senha:
            vicentino = Vicentino.query.get(session['vicentino_id'])
            if not vicentino:
                flash('Usuário não encontrado. Faça login novamente.', 'danger')
                return redirect(url_for('login'))

            if nova_senha != confirmar_senha:
                flash('As senhas não coincidem.', 'danger')
                return redirect(url_for('esqueci_senha'))

            vicentino.senha_hash = generate_password_hash(nova_senha)
            db.session.commit()
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('dashboard'))

        # ==========================
        # Usuário deslogado pede link de redefinição ou usuário logado sem nova senha
        # ==========================
        # Se não passou e-mail (apenas necessário para deslogado)
        if not email and 'vicentino_id' not in session:
            flash('Informe seu e-mail.', 'danger')
            return redirect(url_for('esqueci_senha'))

        # Pega usuário correto
        if 'vicentino_id' in session:
            vicentino = Vicentino.query.get(session['vicentino_id'])
            if not vicentino:
                flash('Usuário não encontrado. Faça login novamente.', 'danger')
                return redirect(url_for('login'))
        else:
            vicentino = Vicentino.query.filter_by(email=email).first()

        # Se existe usuário
        if vicentino:
            if not vicentino.email_confirmado:
                flash('E-mail ainda não confirmado. Solicite ativação ou contate o administrador.', 'warning')
                return redirect(url_for('login'))

            # Controle de tempo entre envios
            ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
            if agora - ultimo_envio < tempo_espera:
                restantes = tempo_espera - (agora - ultimo_envio)
                flash(f'Aguarde {restantes} segundos para reenviar o e-mail de redefinição.', 'warning')
                return redirect(url_for('esqueci_senha'))

            # Envia e-mail de redefinição
            try:
                enviar_email_redefinicao(vicentino)
                session['email_pendente_redefinicao'] = vicentino.email
                session['ultimo_envio_redefinicao'] = int(time.time())
                flash('Se o e-mail estiver cadastrado e confirmado, você receberá um link para redefinir a senha.', 'info')
            except Exception as e:
                flash(f'Erro ao enviar e-mail: {str(e)}', 'danger')
                return redirect(url_for('esqueci_senha'))
        else:
            # Caso usuário não exista, apenas registra o e-mail na sessão para controle de tempo
            session['email_pendente_redefinicao'] = email
            session['ultimo_envio_redefinicao'] = int(time.time())
            flash('Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha.', 'info')

        return redirect(url_for('esqueci_senha'))

    # ==========================
    # GET - CONTROLE DE TEMPO PARA REENVIO
    # ==========================
    email_pendente = session.get('email_pendente_redefinicao')
    ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
    agora = int(time.time())

    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if email_pendente else 0

    # Limpa sessão se tempo expirou
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
    extensoes_permitidas = {'jpg', 'jpeg', 'png', 'webp'}
    agora = int(time.time())
    ultimo_envio = session.get('ultimo_envio_confirmacao', 0)
    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if usuario.email and not usuario.email_confirmado else 0

    if request.method == 'POST':

        # =========================
        # REENVIAR CONFIRMAÇÃO
        # =========================
        if 'reenviar_confirmacao' in request.form:
            if not usuario.email:
                flash('Você não possui e-mail cadastrado.', 'warning')
                return render_template(
                    'editar_perfil.html',
                    usuario=usuario,
                    erros=erros,
                    telefone_input=telefone_para_input(usuario.telefone),
                    tempo_restante=0
                )

            if usuario.email_confirmado:
                flash('Seu e-mail já está confirmado.', 'info')
                return render_template(
                    'editar_perfil.html',
                    usuario=usuario,
                    erros=erros,
                    telefone_input=telefone_para_input(usuario.telefone),
                    tempo_restante=0
                )

            if tempo_restante > 0:
                flash(f'Aguarde {tempo_restante} segundos para reenviar o e-mail.', 'warning')
                return render_template(
                    'editar_perfil.html',
                    usuario=usuario,
                    erros=erros,
                    telefone_input=telefone_para_input(usuario.telefone),
                    tempo_restante=tempo_restante
                )

            try:
                enviar_email_confirmacao(usuario)
                session['ultimo_envio_confirmacao'] = int(time.time())
                flash('E-mail de confirmação reenviado com sucesso.', 'success')
                tempo_restante = 50
            except Exception as e:
                flash(f'Erro ao reenviar e-mail: {str(e)}', 'danger')

            return render_template(
                'editar_perfil.html',
                usuario=usuario,
                erros=erros,
                telefone_input=telefone_para_input(usuario.telefone),
                tempo_restante=tempo_restante
            )

        # =========================
        # CAMPOS DO FORMULÁRIO
        # =========================
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        telefone = request.form.get('telefone', '').strip()
        conselho = request.form.get('conselho', '').strip()
        conferencia = request.form.get('conferencia', '').strip()

        senha_atual = request.form.get('senha_atual', '').strip()
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        # =========================
        # VALIDAÇÕES
        # =========================
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
            telefone_numeros = re.sub(r'\D', '', telefone)
            if telefone_numeros.startswith('55') and len(telefone_numeros) > 10:
                telefone_numeros = telefone_numeros[2:]
            telefone_formatado = telefone_valido_br(telefone_numeros)
            if not telefone_formatado:
                erros['telefone'] = 'Telefone inválido.'

        # =========================
        # FOTO
        # =========================
        foto = request.files.get('foto')
        imagem = None
        if foto and foto.filename:
            nome_foto = secure_filename(foto.filename)
            extensao = nome_foto.rsplit('.', 1)[-1].lower() if '.' in nome_foto else ''
            if extensao not in extensoes_permitidas:
                erros['foto'] = 'Formato de arquivo não suportado. Envie jpg, jpeg, png ou webp.'
            else:
                try:
                    foto.stream.seek(0)
                    imagem = Image.open(foto)
                    if imagem.mode in ('RGBA', 'P'):
                        imagem = imagem.convert('RGB')
                    imagem = imagem.resize((400, 400), Image.Resampling.LANCZOS)
                except UnidentifiedImageError:
                    erros['foto'] = 'Arquivo inválido. Envie apenas imagens.'
                except Exception:
                    erros['foto'] = 'Não foi possível processar a imagem.'

        # =========================
        # SENHA
        # =========================
        if any([senha_atual, nova_senha, confirmar_senha]):
            if not usuario.email:
                flash('Você não possui email cadastrado. Procure a secretaria.', 'warning')
                return render_template(
                    'editar_perfil.html',
                    usuario=usuario,
                    erros=erros,
                    telefone_input=telefone_para_input(usuario.telefone),
                    tempo_restante=tempo_restante
                )

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

        # =========================
        # SE HOUVER ERROS
        # =========================
        if erros:
            for campo, mensagem in erros.items():
                flash(mensagem, 'danger')
            return render_template(
                'editar_perfil.html',
                usuario=usuario,
                erros=erros,
                telefone_input=telefone_para_input(usuario.telefone),
                tempo_restante=tempo_restante
            )

        # =========================
        # ATUALIZA DADOS
        # =========================
        usuario.nome = nome
        usuario.sobrenome = sobrenome
        usuario.telefone = telefone_formatado if telefone else None
        if usuario.tipo == 'admin':
            usuario.conselho = conselho if conselho else None
            usuario.conferencia = conferencia if conferencia else None
        db.session.commit()

        # =========================
        # SALVAR FOTO
        # =========================
        if imagem:
            try:
                nome_arquivo = f'vicentino_{usuario.id}.jpg'
                caminho_foto = os.path.join(app.config['UPLOAD_FOLDER_USUARIO'], nome_arquivo)
                if usuario.foto:
                    caminho_antigo = os.path.join(app.config['UPLOAD_FOLDER_USUARIO'], usuario.foto)
                    if os.path.exists(caminho_antigo):
                        os.remove(caminho_antigo)
                imagem.save(caminho_foto, quality=90)
                usuario.foto = nome_arquivo
                db.session.commit()
            except Exception:
                flash('Perfil atualizado, mas houve erro ao salvar a imagem.', 'warning')

        # =========================
        # ATUALIZA SESSÃO
        # =========================
        session['vicentino_nome'] = usuario.nome
        session['vicentino_email'] = usuario.email
        session['vicentino_foto'] = usuario.foto if usuario.foto else None

        flash('Perfil atualizado com sucesso!', 'success')
        return render_template(
            'editar_perfil.html',
            usuario=usuario,
            erros={},
            telefone_input=telefone_para_input(usuario.telefone),
            tempo_restante=tempo_restante
        )

    # =========================
    # GET - RENDERIZA PÁGINA
    # =========================
    return render_template(
        'editar_perfil.html',
        usuario=usuario,
        erros=erros,
        telefone_input=telefone_para_input(usuario.telefone),
        tempo_restante=tempo_restante
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)