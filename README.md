Sistema Famílias Assistidas SSVP

Sistema web desenvolvido em Flask para gerenciamento de vicentinos, com funcionalidades de cadastro, autenticação, edição de perfil e envio de e-mails.

🚀 Funcionalidades
Cadastro de usuários (vicentinos)
Login e logout com sessão
Confirmação de e-mail
Recuperação de senha
Edição de perfil
Upload de foto de perfil
Validação de dados (nome, telefone, e-mail)
Envio de e-mails via SMTP (Gmail)
🛠️ Tecnologias Utilizadas
Python 3
Flask
Flask-Mail
Flask-SQLAlchemy
MySQL
HTML + Bootstrap
JavaScript
Pillow (tratamento de imagens)
python-dotenv (variáveis de ambiente)
📁 Estrutura do Projeto
sistema-vicentinos/
│
├── app.py
├── config.py
├── models.py
├── requirements.txt
├── .env (não versionado)
│
├── static/
│   └── fotos_perfil/
│
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── cadastro_vicentino.html
│   ├── dashboard.html
│   ├── perfil.html
│   ├── editar_perfil.html
│   └── ...
⚙️ Instalação
1. Clonar o repositório
git clone https://github.com/seu-usuario/sistema-vicentinos.git
cd sistema-vicentinos
2. Criar ambiente virtual
python -m venv .venv

Ativar:

Windows:

.venv\Scripts\activate

Linux/Mac:

source .venv/bin/activate
3. Instalar dependências
pip install -r requirements.txt
🔐 Configuração do .env

Crie um arquivo .env na raiz do projeto:

SECRET_KEY=sua_chave_secreta
MAIL_PASSWORD=sua_senha_de_app_do_gmail

⚠️ Nunca compartilhe esse arquivo.

🗄️ Banco de Dados

Configure a conexão em config.py:

SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://usuario:senha@localhost/nome_do_banco'
▶️ Execução
python app.py

Acesse:

http://127.0.0.1:5000
📧 Configuração de E-mail

O sistema utiliza SMTP do Gmail.

Ative verificação em duas etapas
Gere uma senha de app
Configure no .env
🔒 Segurança
Senhas criptografadas com hash
Uso de variáveis de ambiente (.env)
Validação de dados no backend e frontend
Proteção de sessão
📈 Melhorias Futuras
Deploy em ambiente cloud (AWS)
Armazenamento de imagens em serviço externo (S3)
Sistema de permissões e níveis de acesso
Monitoramento e logs
👨‍💻 Autor

João Otávio Gasparini

📄 Licença

Todos os direitos reservados. Este software é de uso privado e não deve ser distribuído sem autorização.
