# ANSEF/CAS — Sistema de Declarações de Pagamento

Sistema web para emissão de **Declarações de Pagamento** da Associação dos Servidores da Polícia Federal em Campinas/SP (**ANSEF/CAS**), desenvolvido em **Streamlit** e hospedado no **Streamlit Community Cloud**.

## 🏛️ Sobre o Sistema

Este sistema permite que integrantes do plano de saúde/benefícios da ANSEF/CAS solicitem declarações de pagamento para fins de ressarcimento e dedução fiscal, com:

- **Validação cadastral** por data de nascimento do titular
- **Fluxo de aprovação** restrito para administração
- **Geração automática de PDF** com assinatura digital
- **Notificações por e-mail** ao administrador
- **Histórico de declarações** com download direto

## 🚀 Instalação Local

### Pré-requisitos
- Python 3.10+
- pip

### Passos

```bash
# Clonar o repositório
git clone https://github.com/julianimmj/ansef-declaracoes.git
cd ansef-declaracoes

# Instalar dependências
pip install -r requirements.txt

# Configurar secrets (copiar o modelo e preencher)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Editar .streamlit/secrets.toml com suas credenciais SMTP

# Executar
streamlit run app.py
```

## ☁️ Deploy no Streamlit Cloud

1. Faça push do repositório para o GitHub (`julianimmj/ansef-declaracoes`)
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Selecione o repositório e o arquivo `app.py`
4. Em **Settings > Secrets**, adicione o conteúdo de `secrets.toml.example` com as credenciais reais
5. Clique em **Deploy**

### Configuração de Secrets no Streamlit Cloud

```toml
ADMIN_PASSWORD = "mbj172007"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "juliani.mmj@gmail.com"
SMTP_PASSWORD = "sua_senha_de_app_do_google"
ADMIN_EMAIL = "juliani.mmj@gmail.com"
```

> **Nota:** Para o Gmail, é necessário gerar uma **Senha de App** em [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

## 📋 Funcionalidades

### Área do Associado
- Login por nome do titular + data de nascimento
- Solicitação de nova declaração com seleção de dependentes
- Valores pré-preenchidos e editáveis
- Histórico completo com download de PDFs aprovados

### Área do Administrador
- Painel com métricas de solicitações
- Revisão e edição completa de solicitações pendentes
- Aprovação com geração imediata do PDF oficial
- Rejeição com justificativa
- Reajuste de valores (individual ou em lote)
- Relatórios com exportação para CSV/Excel

## 📄 Estrutura do Projeto

```
ansef-declaracoes/
├── .streamlit/          # Configuração do Streamlit
├── assets/              # Logo e assinatura digital
├── data/                # CSV de integrantes e banco SQLite
├── src/                 # Módulos Python (database, auth, pdf, email, utils)
├── templates/           # Template HTML da declaração
├── app.py               # Aplicação principal
├── packages.txt         # Dependências do sistema (Streamlit Cloud)
├── requirements.txt     # Dependências Python
└── README.md            # Este arquivo
```

## 👤 Administrador

**MARCELO MARTINS JULIANI**  
Vice Presidente da ANSEF/CAMPINAS  
📧 juliani.mmj@gmail.com

---

*Desenvolvido para a ANSEF/CAS — Associação dos Servidores da Polícia Federal em Campinas/SP*
