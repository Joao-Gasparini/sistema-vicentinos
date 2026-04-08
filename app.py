from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
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
from models import db, Vicentino, Conselho, Conferencia

# =========================================================
# INICIALIZAÇÃO DA APLICAÇÃO
# =========================================================

app = Flask(__name__)
app.config.from_object(Config)

# Inicializa a proteção CSRF em todos os formulários
csrf = CSRFProtect(app)

db.init_app(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Define e cria o diretório para armazenar as fotos de perfil dos usuários
app.config['UPLOAD_FOLDER_USUARIO'] = os.path.join(app.root_path, 'static', 'fotos_perfil')
os.makedirs(app.config['UPLOAD_FOLDER_USUARIO'], exist_ok=True)

# Limite máximo de upload: 5MB
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024


@app.errorhandler(413)
def arquivo_muito_grande(e):
    """Captura o erro 413 (arquivo maior que o limite) e exibe mensagem amigável ao usuário."""
    flash('Arquivo muito grande! Máximo permitido: 5MB.', 'danger')
    return redirect(request.referrer or url_for('home'))


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def apenas_letras(texto):
    """Verifica se o texto contém apenas letras (incluindo acentuadas) e espaços."""
    return re.fullmatch(r"[A-Za-zÀ-ÿ\s]+", texto) is not None


def email_valido(email):
    """
    Valida e normaliza um endereço de e-mail.
    Retorna o e-mail normalizado se válido, ou None se inválido.
    """
    try:
        valid = validate_email(email, check_deliverability=False)
        return valid.normalized
    except EmailNotValidError:
        return None


def telefone_valido_br(telefone):
    """
    Valida um número de telefone brasileiro e o retorna no formato E.164 (+55...).
    Retorna None se o número for inválido.
    """
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
    """
    Converte um telefone no formato E.164 (+55...) para apenas os dígitos locais,
    removendo o código do país (+55). Usado para preencher campos de formulário.
    """
    if not telefone_e164:
        return ''

    # Remove o prefixo +55
    telefone = telefone_e164.replace('+55', '')

    return telefone  # Retorna só os números (ex: 11999998888)

# =========================================================
# DOCUMENTOS (CPF / CNPJ)
# =========================================================

def limpar_numero(valor):
    """Remove qualquer caractere que não seja número."""
    return re.sub(r'\D', '', valor)


def cpf_valido(cpf):
    """
    Valida um CPF brasileiro verificando:
    - Se possui 11 dígitos
    - Se não é sequência repetida
    - Se os dígitos verificadores são válidos
    """
    cpf = limpar_numero(cpf)

    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    # 1º dígito
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    resto = 0 if resto == 10 else resto
    if resto != int(cpf[9]):
        return False

    # 2º dígito
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    resto = 0 if resto == 10 else resto
    if resto != int(cpf[10]):
        return False

    return True


def cnpj_valido(cnpj):
    """
    Valida um CNPJ brasileiro verificando:
    - Se possui 14 dígitos
    - Se não é sequência repetida
    - Se os dígitos verificadores são válidos
    """
    cnpj = limpar_numero(cnpj)

    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    pesos1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    pesos2 = [6] + pesos1

    soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
    dig1 = 11 - (soma % 11)
    dig1 = dig1 if dig1 < 10 else 0

    soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
    dig2 = 11 - (soma % 11)
    dig2 = dig2 if dig2 < 10 else 0

    return cnpj[-2:] == f"{dig1}{dig2}"


def documento_valido(documento, tipo_usuario):
    """
    Valida CPF ou CNPJ dependendo do tipo do usuário.
    - admin → CNPJ
    - vicentino → CPF
    """
    documento = limpar_numero(documento)

    if not documento:
        return False

    if tipo_usuario == 'admin':
        return cnpj_valido(documento)
    else:
        return cpf_valido(documento)

def gerar_token(email, salt):
    """Gera um token seguro e com tempo de expiração baseado no e-mail e em um salt específico."""
    return serializer.dumps(email, salt=salt)


def admin_required(f):
    """
    Decorator que protege rotas de acesso exclusivo a administradores.
    Redireciona para o login se o usuário não estiver autenticado,
    ou para a home se não for admin.
    """

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
    """
    Valida um token seguro e retorna o e-mail contido nele.
    Retorna None se o token estiver expirado ou for inválido.
    """
    try:
        email = serializer.loads(token, salt=salt, max_age=expiracao)
        return email
    except SignatureExpired:
        return None
    except BadSignature:
        return None


def enviar_email_confirmacao(vicentino):
    """
    Gera um token de confirmação e envia um e-mail ao vicentino
    com o link para ativar sua conta.
    """
    token = gerar_token(vicentino.email, 'confirmar-email')
    link = url_for('confirmar_email', token=token, _external=True)

    msg = Message(
        subject='Confirmação de cadastro - Famílias Assistidas SSVP',
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
    """
    Gera um token de redefinição e envia um e-mail ao vicentino
    com o link para cadastrar uma nova senha.
    """
    token = gerar_token(vicentino.email, 'redefinir-senha')
    link = url_for('redefinir_senha', token=token, _external=True)

    msg = Message(
        subject='Redefinição de senha - Famílias Assistidas SSVP',
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
    """Redireciona para o dashboard se logado, ou para o login se não autenticado."""
    if 'vicentino_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Exibe e processa o formulário de login.
    Valida o CPF e a senha, e inicia a sessão do usuário autenticado.
    """
    cpf_input = ''  # Valor padrão para manter o campo preenchido em caso de erro

    if request.method == 'POST':
        cpf_input = request.form.get('cpf', '').strip()
        senha = request.form.get('senha', '')

        # Remove a máscara do CPF (pontos e traço)
        cpf = re.sub(r'\D', '', cpf_input)

        # Validação básica dos campos
        if not cpf or not senha:
            flash('Informe CPF e senha.', 'danger')
            return render_template('login.html', cpf_input=cpf_input)

        # Validação do formato do CPF
        if not cpf_valido(cpf):
            flash('CPF inválido.', 'danger')
            return render_template('login.html', cpf_input=cpf_input)

        # Busca o usuário no banco e verifica a senha
        vicentino = Vicentino.query.filter_by(cpf=cpf).first()

        if not vicentino or not check_password_hash(vicentino.senha_hash, senha):
            flash('CPF ou senha incorretos.', 'danger')
            return render_template('login.html', cpf_input=cpf_input)

        # Login bem-sucedido: armazena dados na sessão
        session['vicentino_id'] = vicentino.id
        session['vicentino_nome'] = vicentino.nome
        session['vicentino_email'] = vicentino.email
        session['vicentino_foto'] = vicentino.foto if hasattr(vicentino, 'foto') else None
        session['tipo'] = vicentino.tipo

        flash('Login realizado com sucesso.', 'success')
        return redirect(url_for('dashboard'))

    # GET: renderiza o formulário com o campo CPF vazio
    return render_template('login.html', cpf_input='')

@app.route('/api/conferencias/<int:conselho_id>')
@admin_required
def api_conferencias(conselho_id):
    conferencias = Conferencia.query.filter_by(conselho_id=conselho_id).order_by(Conferencia.nome).all()
    return jsonify([{'id': c.id, 'nome': c.nome} for c in conferencias])

@app.route('/admin/cadastrar_vicentino', methods=['GET', 'POST'])
@admin_required
def cadastrar_vicentino():
    conselhos = Conselho.query.all()
    conferencias = Conferencia.query.all()

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        cpf_input = request.form.get('cpf', '').strip()
        cpf = re.sub(r'\D', '', cpf_input)
        email_informado = request.form.get('email', '').strip()
        telefone = request.form.get('telefone', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')
        foto = request.files.get('foto')

        # ← agora vêm como IDs numéricos
        conselho_id = request.form.get('conselho_id') or None
        conferencia_id = request.form.get('conferencia_id') or None

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
            if Vicentino.query.filter_by(email=email).first():
                flash('Já existe um vicentino cadastrado com este e-mail.', 'danger')
                return redirect(url_for('cadastrar_vicentino'))

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
            conselho_id=conselho_id,       # ← FK
            conferencia_id=conferencia_id  # ← FK
        )

        db.session.add(novo_vicentino)
        db.session.commit()

        if email:
            try:
                enviar_email_confirmacao(novo_vicentino)
                flash('Vicentino cadastrado! E-mail de confirmação enviado.', 'success')
            except Exception:
                flash('Vicentino cadastrado, mas erro ao enviar e-mail.', 'warning')
        else:
            flash('Vicentino cadastrado com sucesso!', 'success')

        return redirect(url_for('dashboard'))

    return render_template(
        'cadastro_vicentino.html',
        conselhos=conselhos,
        conferencias=conferencias
    )


@app.route('/logout')
def logout():
    """Encerra a sessão do usuário e redireciona para a página de login."""
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))


# =========================================================
# CONFIRMAÇÃO DE E-MAIL
# =========================================================

@app.route('/confirmar_email/<token>')
def confirmar_email(token):
    """
    Valida o token de confirmação de e-mail recebido por link.
    Ativa a conta do usuário se o token for válido e ainda não tiver sido confirmado.
    """
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

    # Ativa a conta e registra a data de confirmação
    vicentino.email_confirmado = True
    vicentino.status = 'ativo'
    vicentino.data_confirmacao = datetime.utcnow()
    db.session.commit()

    flash('E-mail confirmado com sucesso. Agora você já pode fazer login.', 'success')
    return redirect(url_for('login'))


@app.route('/reenviar_confirmacao', methods=['POST'])
def reenviar_confirmacao():
    """
    Reenvia o e-mail de confirmação de conta para o usuário.
    Funciona tanto para usuários logados quanto deslogados.
    Aplica controle de tempo (cooldown de 50 segundos) entre reenvios.
    """
    agora = int(time.time())
    tempo_espera = 50

    # Identifica o usuário logado ou pelo e-mail informado no formulário
    if 'vicentino_id' in session:
        usuario = Vicentino.query.get(session['vicentino_id'])
        if not usuario:
            flash('Usuário não encontrado. Faça login novamente.', 'danger')
            return redirect(url_for('login'))
    else:
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Informe seu e-mail.', 'danger')
            return redirect(url_for('login'))

        usuario = Vicentino.query.filter_by(email=email).first()
        if not usuario:
            # Mensagem genérica para evitar enumeração de e-mails
            flash('Se o e-mail estiver cadastrado, um novo link será enviado.', 'info')
            return redirect(url_for('login'))

    # Verifica se o e-mail já está confirmado
    if usuario.email_confirmado:
        session.pop('email_pendente_confirmacao', None)
        session.pop('ultimo_envio_confirmacao', None)
        flash('Seu e-mail já está confirmado.', 'info')
        return redirect(url_for('editar_perfil')) if 'vicentino_id' in session else redirect(url_for('login'))

    # Aplica cooldown entre reenvios
    ultimo_envio = session.get('ultimo_envio_confirmacao', 0)
    if agora - ultimo_envio < tempo_espera:
        restantes = tempo_espera - (agora - ultimo_envio)
        flash(f'Aguarde {restantes} segundos para reenviar o e-mail.', 'warning')
        return redirect(url_for('editar_perfil')) if 'vicentino_id' in session else redirect(url_for('login'))

    # Realiza o envio e atualiza o controle de tempo na sessão
    try:
        enviar_email_confirmacao(usuario)
        session['email_pendente_confirmacao'] = usuario.email
        session['ultimo_envio_confirmacao'] = agora
        flash('E-mail de confirmação reenviado com sucesso.', 'success')
    except Exception as e:
        flash(f'Erro ao reenviar e-mail: {str(e)}', 'danger')

    return redirect(url_for('editar_perfil')) if 'vicentino_id' in session else redirect(url_for('login'))


# =========================================================
# RECUPERAÇÃO DE SENHA
# =========================================================

@app.route('/esqueci_senha', methods=['GET', 'POST'])
def esqueci_senha():
    """
    Gerencia a recuperação e alteração de senha.
    - Usuário logado: pode alterar a senha diretamente ou solicitar link por e-mail.
    - Usuário deslogado: solicita link de redefinição via e-mail.
    Aplica cooldown de 50 segundos entre envios de e-mail.
    """
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        agora = int(time.time())
        tempo_espera = 50

        # Alteração direta de senha para usuário logado
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

        # Solicita link por e-mail (usuário deslogado sem e-mail informado)
        if not email and 'vicentino_id' not in session:
            flash('Informe seu e-mail.', 'danger')
            return redirect(url_for('esqueci_senha'))

        # Busca o vicentino correto conforme o contexto (logado ou não)
        if 'vicentino_id' in session:
            vicentino = Vicentino.query.get(session['vicentino_id'])
            if not vicentino:
                flash('Usuário não encontrado. Faça login novamente.', 'danger')
                return redirect(url_for('login'))
        else:
            vicentino = Vicentino.query.filter_by(email=email).first()

        if vicentino:
            # Bloqueia redefinição se o e-mail ainda não foi confirmado
            if not vicentino.email_confirmado:
                flash('E-mail ainda não confirmado. Solicite ativação ou contate o administrador.', 'warning')
                return redirect(url_for('login'))

            # Aplica cooldown entre envios
            ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
            if agora - ultimo_envio < tempo_espera:
                restantes = tempo_espera - (agora - ultimo_envio)
                flash(f'Aguarde {restantes} segundos para reenviar o e-mail de redefinição.', 'warning')
                return redirect(url_for('esqueci_senha'))

            # Envia e-mail de redefinição e registra na sessão
            try:
                enviar_email_redefinicao(vicentino)
                session['email_pendente_redefinicao'] = vicentino.email
                session['ultimo_envio_redefinicao'] = int(time.time())
                flash('Se o e-mail estiver cadastrado e confirmado, você receberá um link para redefinir a senha.',
                      'info')
            except Exception as e:
                flash(f'Erro ao enviar e-mail: {str(e)}', 'danger')
                return redirect(url_for('esqueci_senha'))
        else:
            # Resposta genérica para evitar enumeração de e-mails
            session['email_pendente_redefinicao'] = email
            session['ultimo_envio_redefinicao'] = int(time.time())
            flash('Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha.', 'info')

        return redirect(url_for('esqueci_senha'))

    # GET: verifica tempo restante do cooldown e renderiza a página
    email_pendente = session.get('email_pendente_redefinicao')
    ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
    agora = int(time.time())

    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if email_pendente else 0

    # Limpa os dados de sessão se o cooldown já expirou
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
    """
    Reenvia o e-mail de redefinição de senha.
    O e-mail pode vir do formulário ou da sessão ativa.
    Aplica cooldown de 50 segundos entre reenvios.
    """
    email = request.form.get('email', '').strip().lower()

    # Usa o e-mail da sessão como fallback
    if not email:
        email = session.get('email_pendente_redefinicao', '').strip().lower()

    if not email:
        flash('Informe seu e-mail.', 'danger')
        return redirect(url_for('esqueci_senha'))

    ultimo_envio = session.get('ultimo_envio_redefinicao', 0)
    agora = int(time.time())

    # Verifica o cooldown antes de reenviar
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
        # Resposta genérica para evitar enumeração de e-mails
        session['email_pendente_redefinicao'] = email
        session['ultimo_envio_redefinicao'] = int(time.time())
        flash('Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha.', 'info')

    return redirect(url_for('esqueci_senha'))


@app.route('/redefinir_senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token):
    """
    Exibe e processa o formulário de redefinição de senha via token.
    Valida o token, verifica os campos e atualiza a senha no banco.
    Limpa os dados de sessão relacionados à redefinição após o sucesso.
    """
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

        # Atualiza a senha e limpa os dados de sessão relacionados
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
    """
    Exibe o painel principal do sistema.
    Redireciona para o login se o usuário não estiver autenticado.
    """
    if 'vicentino_id' not in session:
        flash('Faça login para acessar o sistema.', 'warning')
        return redirect(url_for('login'))

    return render_template('dashboard.html')

@app.route('/perfil')
def perfil():
    """Exibe a página de perfil do usuário logado."""
    if 'vicentino_id' not in session:
        return redirect(url_for('login'))

    usuario = Vicentino.query.get(session['vicentino_id'])
    return render_template('perfil.html', usuario=usuario)


@app.route('/editar_perfil', methods=['GET', 'POST'])
def editar_perfil():
    """
    Exibe e processa o formulário de edição de perfil do usuário logado.
    Permite atualizar nome, sobrenome, telefone, foto de perfil e senha.
    Administradores também podem editar conselho e conferência.
    Inclui reenvio de e-mail de confirmação com controle de cooldown.
    """
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

    # Calcula o tempo restante do cooldown de reenvio de confirmação
    tempo_restante = max(0, 50 - (agora - ultimo_envio)) if usuario.email and not usuario.email_confirmado else 0

    if request.method == 'POST':

        # ── Reenvio de confirmação de e-mail ──────────────────────────────
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

        # ── Leitura dos campos do formulário ──────────────────────────────
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        telefone = request.form.get('telefone', '').strip()
        conselho = request.form.get('conselho', '').strip()
        conferencia = request.form.get('conferencia', '').strip()
        cpf_input = request.form.get('cpf', '').strip()
        documento = limpar_numero(cpf_input)
        senha_atual = request.form.get('senha_atual', '').strip()
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        # ── Validação dos campos de texto ─────────────────────────────────
        if not nome:
            erros['nome'] = 'Informe o nome.'
        elif not apenas_letras(nome):
            erros['nome'] = 'O nome deve conter apenas letras.'

        if not sobrenome:
            erros['sobrenome'] = 'Informe o sobrenome.'
        elif not apenas_letras(sobrenome):
            erros['sobrenome'] = 'O sobrenome deve conter apenas letras.'

        # Valida o telefone removendo a máscara antes
        telefone_formatado = None
        if telefone:
            telefone_numeros = re.sub(r'\D', '', telefone)
            if telefone_numeros.startswith('55') and len(telefone_numeros) > 10:
                telefone_numeros = telefone_numeros[2:]
            telefone_formatado = telefone_valido_br(telefone_numeros)
            if not telefone_formatado:
                erros['telefone'] = 'Telefone inválido.'

        # ── Validação e processamento da foto de perfil ───────────────────
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
                    # Converte para RGB se necessário (ex: PNG com transparência)
                    if imagem.mode in ('RGBA', 'P'):
                        imagem = imagem.convert('RGB')
                    # Redimensiona para 400x400 px
                    imagem = imagem.resize((400, 400), Image.Resampling.LANCZOS)
                except UnidentifiedImageError:
                    erros['foto'] = 'Arquivo inválido. Envie apenas imagens.'
                except Exception:
                    erros['foto'] = 'Não foi possível processar a imagem.'

        # ── Validação e atualização de senha ──────────────────────────────
        if any([senha_atual, nova_senha, confirmar_senha]):
            # Troca de senha só é permitida para usuários com e-mail cadastrado
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
            # Aplica a nova senha apenas se todas as validações passaram
            if 'senha_atual' not in erros and 'nova_senha' not in erros and 'confirmar_senha' not in erros:
                usuario.senha_hash = generate_password_hash(nova_senha)

        # ── Retorna com erros se houver problemas de validação ────────────
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

        # ── Atualiza os dados no banco ────────────────────────────────────
        usuario.nome = nome
        usuario.sobrenome = sobrenome
        usuario.telefone = telefone_formatado if telefone else None

        # Campos exclusivos para administradores
        if usuario.tipo == 'admin':
            usuario.conselho = conselho if conselho else None
            usuario.conferencia = conferencia if conferencia else None
            usuario.cnpj = documento if documento else None
            usuario.cpf = None
        else:
            usuario.cpf = documento if documento else None

        db.session.commit()

        # ── Salva a foto de perfil no disco ──────────────────────────────
        if imagem:
            try:
                nome_arquivo = f'vicentino_{usuario.id}.jpg'
                caminho_foto = os.path.join(app.config['UPLOAD_FOLDER_USUARIO'], nome_arquivo)

                # Remove a foto anterior se existir
                if usuario.foto:
                    caminho_antigo = os.path.join(app.config['UPLOAD_FOLDER_USUARIO'], usuario.foto)
                    if os.path.exists(caminho_antigo):
                        os.remove(caminho_antigo)

                imagem.save(caminho_foto, quality=90)
                usuario.foto = nome_arquivo
                db.session.commit()
            except Exception:
                flash('Perfil atualizado, mas houve erro ao salvar a imagem.', 'warning')

        # ── Atualiza os dados da sessão ───────────────────────────────────
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

    # GET: renderiza a página com os dados atuais do usuário
    return render_template(
        'editar_perfil.html',
        usuario=usuario,
        erros=erros,
        telefone_input=telefone_para_input(usuario.telefone),
        tempo_restante=tempo_restante
    )

# =============================
@app.route('/admin/vicentinos')
@admin_required
def listar_vicentinos():
    conselho_id = request.args.get('conselho_id')
    conferencia_id = request.args.get('conferencia_id')

    query = Vicentino.query

    if conselho_id:
        query = query.filter_by(conselho_id=conselho_id)

    if conferencia_id:
        query = query.filter_by(conferencia_id=conferencia_id)

    vicentinos = query.all()

    conselhos = Conselho.query.all()
    conferencias = Conferencia.query.all()

    return render_template(
        'admin_vicentinos.html',
        vicentinos=vicentinos,
        conselhos=conselhos,
        conferencias=conferencias
    )

@app.route('/admin/editar_vicentino/<int:id>', methods=['GET', 'POST'])
@admin_required
def editar_vicentino_admin(id):
    usuario = Vicentino.query.get_or_404(id)

    conselhos = Conselho.query.all()
    conferencias = Conferencia.query.all()

    erros = {}

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        sobrenome = request.form.get('sobrenome', '').strip()
        telefone = request.form.get('telefone', '').strip()

        conselho_id = request.form.get('conselho_id') or None
        conferencia_id = request.form.get('conferencia_id') or None

        # =============================
        # VALIDAÇÕES
        # =============================

        if not nome or not apenas_letras(nome):
            erros['nome'] = 'Nome inválido.'

        if not sobrenome or not apenas_letras(sobrenome):
            erros['sobrenome'] = 'Sobrenome inválido.'

        # Telefone
        telefone_formatado = None
        if telefone:
            telefone_numeros = re.sub(r'\D', '', telefone)

            if telefone_numeros.startswith('55') and len(telefone_numeros) > 10:
                telefone_numeros = telefone_numeros[2:]

            telefone_formatado = telefone_valido_br(telefone_numeros)

            if not telefone_formatado:
                erros['telefone'] = 'Telefone inválido.'

        # =============================
        # SE TIVER ERRO
        # =============================
        if erros:
            for msg in erros.values():
                flash(msg, 'danger')

            return render_template(
                'admin_editar_vicentino.html',
                usuario=usuario,
                conselhos=conselhos,
                conferencias=conferencias
            )

        # =============================
        # ATUALIZAÇÃO
        # =============================
        usuario.nome = nome
        usuario.sobrenome = sobrenome
        usuario.telefone = telefone_formatado if telefone else None
        usuario.conselho_id = conselho_id
        usuario.conferencia_id = conferencia_id

        db.session.commit()

        flash('Vicentino atualizado com sucesso!', 'success')
        return redirect(url_for('listar_vicentinos'))

    return render_template(
        'admin_editar_vicentino.html',
        usuario=usuario,
        conselhos=conselhos,
        conferencias=conferencias
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)