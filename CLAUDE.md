# 🧠 Assistente - Sistema Famílias Assistidas SSVP

---

# 1. Princípios de Desenvolvimento (Karpathy)

## Think Before Coding
- Nunca assumir contexto sem certeza
- Se houver ambiguidade, perguntar antes de implementar
- Explicitar suposições antes de escrever código
- Apresentar alternativas quando houver mais de uma abordagem válida
- Se estiver confuso, parar e pedir esclarecimento

## Simplicity First
- Implementar apenas o que foi solicitado
- Evitar abstrações desnecessárias
- Não criar funções genéricas sem necessidade
- Não adicionar “flexibilidade futura” não solicitada
- Priorizar código simples e direto

## Surgical Changes
- Alterar apenas o necessário
- Não refatorar código existente sem pedido explícito
- Não modificar partes não relacionadas
- Manter o padrão de código já usado no projeto

## Goal-Driven Execution
- Definir claramente o objetivo antes de implementar
- Quando possível:
  - Validar problema
  - Implementar solução
  - Verificar resultado

---

# 2. Contexto do Projeto

Sistema web para gestão de famílias assistidas da SSVP.

## Tipos de usuário
- Admin (login por CNPJ)
- Vicentino (login por CPF)

## Funcionalidades principais
- Gestão de vicentinos
- Gestão de conselhos e conferências
- Gestão de famílias assistidas
- Registro de atendimentos

## Regras de uso
- Sistema utilizado por voluntários
- Interface deve ser simples e clara

---

# 3. Stack e Tecnologias

- Python 3.12 + Flask
- SQLAlchemy + MySQL
- Flask-WTF (CSRF)
- Flask-Mail
- Pillow (upload de imagem)
- python-dotenv

Frontend:
- Bootstrap 5.3
- Font Awesome 6.5
- Select2 4.1
- jQuery 3.7

---

# 4. Regras de Código

- Sempre usar {% block conteudo %}, nunca {% block content %}
- Scripts apenas no {% block scripts %}
- Nunca aninhar blocos Jinja
- CSRF obrigatório em POST
- Usar @admin_required ou @login_required
- Nunca usar variáveis hardcoded (usar .env)

---

# 5. Regras de Banco

- Usar sempre:
  - conselho_id
  - conferencia_id
- Nunca usar campos texto antigos

- Conferências via:
  /api/conferencias/<conselho_id>

- Usar Flask-Migrate (nunca db.create_all em produção)

---

# 6. Regras de Frontend

- NÃO importar novamente:
  - jQuery
  - Bootstrap JS
  - Select2

- NÃO repetir CSS do Select2

- Ícones:
  - Sempre Font Awesome (fas fa-*)

- Cores:
  - Admin: #185FA5
  - Vicentino: #A32D2D

---

# 7. Padrões de Resposta do Assistente

Ao gerar código:

- Alterações pequenas → mostrar apenas trecho relevante
- Templates → arquivo completo
- Rotas Flask → função completa com docstring

Sempre:
- Avisar se precisa alterar outro arquivo
- Evitar over-engineering
- Manter consistência com o projeto

Se encontrar bug:
- Avisar, mas não corrigir sem pedido

---

# 8. Restrições Importantes

O assistente NÃO deve:

- Reescrever grandes partes do sistema
- Criar complexidade desnecessária
- Alterar código fora do escopo
- Introduzir novas arquiteturas sem necessidade

## Identidade Visual - SSVP Brasil

Este projeto segue o Manual da Marca da Sociedade de São Vicente de Paulo (SSVP) 
do Brasil, versão 01.06.2024. Todas as interfaces, materiais e componentes visuais 
devem respeitar rigorosamente as diretrizes abaixo.

### Cores oficiais
- Azul principal: #0064B6
- Vermelho: #FF0000
- Branco: #FFFFFF
- Preto (P&B): #000000AGORA BLOQUEIE OS CAMPOS CIDADE E ESTADO QUANDO 

### Tipografia
- Oficial (logotipo e textos corridos): Garamond
- Secundária (designs profissionais e departamentos): Montserrat
  - Identificações de departamentos: Montserrat ExtraBold
  - Nomes em cartões/materiais: Montserrat ExtraBold
  - Cargos: Montserrat Medium
  - Contatos: Montserrat Bold
  - Endereços: Montserrat Medium

### Logotipo
- Nunca alterar, distorcer, recolorir ou recriar o logotipo
- Tamanho mínimo: 20mm (impressão) / 200px (telas)
- Área de segurança: 1/5 do tamanho do logotipo em todos os lados
- Versão branca: usar SOMENTE em fundos com tons de azul
- Não criar logotipos alternativos para unidades ou departamentos

### Aplicações
- Camisetas: logotipo na manga esquerda ou costas, altura de 60mm
- Jalecos/aventais/coletes: frente 60mm (lado esquerdo), costas 150mm (centralizado)
- Redes sociais: usar sempre o avatar oficial sem nenhuma alteração
- Nome em redes sociais: sempre iniciar com "SSVP -" seguido da unidade
- Categoria nas redes: "Organização Religiosa"

### Identificação de unidades
- Texto ao lado direito do logotipo
- Tipografia: identificação em Garamond Bold, unidade e cidade em Garamond
- Conferências: indicar apenas a cidade, sem hierarquia

### Proibições
- Não criar logotipos próprios para unidades ou departamentos
- Não modificar o logotipo oficial em nenhuma hipótese
- Não usar a versão branca do logotipo em fundos que não sejam tons de azul