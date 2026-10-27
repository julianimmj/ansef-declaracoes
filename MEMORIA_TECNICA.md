# 🧠 Memória Técnica — ANSEF Declarações

> **Finalidade deste documento:**  
> Registro técnico consolidado (Single Source of Truth) da arquitetura, modelo de dados, fluxos de emissão e segurança do sistema **ANSEF Declarações**.  
> **Última Atualização:** 26 de Outubro de 2026 (Auditoria Completa de Segurança & Conversão para Repositório Privado)  
> **Status Operacional Geral:** 🟢 100% Operacional e Auditado (Repositório Privado + Autenticação via Variáveis de Ambiente / Secrets + Zero Hardcoded Secrets)

---

## 1. Visão Geral & Regras de Negócio

Aplicação web em Streamlit para gerenciamento e emissão automatizada de Declarações de Pagamento de Plano de Saúde da **ANSEF/CAS** (Associação dos Servidores da Polícia Federal em Campinas/SP).

### 1.1. Perfis de Acesso
- **Associados:** Autenticação via Nome do Titular e Data de Nascimento (comparado contra `data/ansef_database.db`). Solicitação de declaração mensal ou anual com seleção de beneficiários.
- **Administrador:** Autenticação por senha restrita (`ADMIN_PASSWORD`). Permite aprovar, editar, rejeitar, emitir PDFs oficiais e disparar notificações por e-mail (SMTP).

---

## 2. Arquitetura de Segurança & Gestão de Segredos

1. **Repositório Privado:**
   - O repositório `julianimmj/ansef-declaracoes` é estritamente **PRIVADO** (`visibility: PRIVATE`).
2. **Eliminação de Senhas Hardcoded:**
   - Todas as senhas e credenciais foram removidas do código-fonte (`src/auth.py`, `app.py`, `README.md`, `.streamlit/secrets.toml.example`).
   - Resolução de credenciais do Administrador: `st.secrets["ADMIN_PASSWORD"]` -> `os.environ["ADMIN_PASSWORD"]` (via `.env`).
3. **Proteção no Git:**
   - O arquivo `.gitignore` bloqueia estritamente `.streamlit/secrets.toml`, `.env`, `.env.*`.
   - Um arquivo de modelo `.env.example` e `.streamlit/secrets.toml.example` contém apenas valores fictícios.
4. **Notificações SMTP:**
   - Envio resiliente via Gmail (App Password) sem interrupção de fluxo em caso de indisponibilidade de rede.

---

## 3. Estrutura de Arquivos

| Arquivo / Diretório | Responsabilidade |
|---|---|
| `app.py` | Interface principal Streamlit (Área do Associado + Painel Administrativo). |
| `src/auth.py` | Autenticação de associados e administrador (via secrets/.env). |
| `src/database.py` | Gestão de dados SQLite (`data/ansef_database.db`), tabelas de titulares e dependentes. |
| `src/email_service.py` | Disparo de e-mails formatados em HTML via SMTP. |
| `src/pdf_generator.py` | Renderização do PDF oficial da declaração com brasão e assinatura digital. |
| `templates/` | Template HTML da declaração. |
| `data/` | Banco de dados SQLite persistido e arquivos de backup. |

---

## 4. Histórico de Segurança (26/10/2026)

* **Conversão de Visibilidade:** Repositório alterado de público para **PRIVADO** no GitHub.
* **Higienização de Código:** Remoção de credenciais fixas em `src/auth.py` e textos de instruções.
* **Isolamento de Ambiente:** Implementação de `.env` local e `.env.example` com placeholders.
* **Auditoria de Conformidade:** Verificação com 0 erros de sintaxe e aprovação em todos os testes de carga e autenticação.
