from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Vicentino(db.Model):
    __tablename__ = 'vicentinos'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    sobrenome = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), unique=True)
    email = db.Column(db.String(150), unique=True, nullable=True)
    telefone = db.Column(db.String(25))
    senha_hash = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default='vicentino')
    status = db.Column(db.String(10), default='pendente')
    email_confirmado = db.Column(db.Boolean, default=False)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    data_confirmacao = db.Column(db.DateTime, nullable=True)
    foto = db.Column(db.String(255), nullable=True)
    conselho = db.Column(db.String(150), nullable=True)
    conferencia = db.Column(db.String(150), nullable=True)

    familias = db.relationship('Familia', backref='vicentino', lazy=True)
    atendimentos = db.relationship('Atendimento', backref='vicentino', lazy=True)

class Familia(db.Model):
    __tablename__ = 'familias'

    id = db.Column(db.Integer, primary_key=True)
    nome_responsavel = db.Column(db.String(150), nullable=False)
    cpf_responsavel = db.Column(db.String(14), unique=True)
    telefone_principal = db.Column(db.String(25))
    telefone_secundario = db.Column(db.String(25))
    endereco = db.Column(db.String(150), nullable=False)
    numero = db.Column(db.String(20), nullable=False)
    complemento = db.Column(db.String(100))
    bairro = db.Column(db.String(100), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    cep = db.Column(db.String(10))
    ponto_referencia = db.Column(db.String(150))
    quantidade_moradores = db.Column(db.Integer)
    observacoes = db.Column(db.Text)
    status = db.Column(db.String(10), default='ativa')
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)

    vicentino_id = db.Column(db.Integer, db.ForeignKey('vicentinos.id'), nullable=False)

    atendimentos = db.relationship('Atendimento', backref='familia', lazy=True)


class Atendimento(db.Model):
    __tablename__ = 'atendimentos'

    id = db.Column(db.Integer, primary_key=True)
    familia_id = db.Column(db.Integer, db.ForeignKey('familias.id'), nullable=False)
    vicentino_id = db.Column(db.Integer, db.ForeignKey('vicentinos.id'), nullable=False)
    data_atendimento = db.Column(db.Date, nullable=False)
    tipo_atendimento = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    observacoes = db.Column(db.Text)
    data_registro = db.Column(db.DateTime, default=datetime.utcnow)