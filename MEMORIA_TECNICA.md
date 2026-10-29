# 🧠 Memória Técnica — ANSEF Declarações

> **Finalidade deste documento:**  
> Registro técnico consolidado (Single Source of Truth) da arquitetura, modelo de dados, fluxos de emissão e segurança do sistema **ANSEF Declarações**.  
> **Última Atualização:** 29 de Outubro de 2026 (Restauração de Compatibilidade com Streamlit Community Cloud & Proteção SHA-256)  
> **Status Operacional Geral:** 🟢 100% Operacional e Auditado (Repositório Público Compatível com Streamlit Cloud + Autenticação via Secrets/SHA-256 + Zero Hardcoded Secrets)

---

## 1. Visão Geral & Regras de Negócio

Aplicação web em Streamlit para gerenciamento e emissão automatizada de Declarações de Pagamento de Plano de Saúde da **ANSEF/CAS** (Associação dos Servidores da Polícia Federal em Campinas/SP).

### 1.1. Perfis de Acesso
- **Associados:** Autenticação via Nome do Titular e Data de Nascimento (comparado contra `data/ansef_database.db`). Solicitação de declaração mensal ou anual com seleção de beneficiários.
- **Administrador:** Autenticação por senha restrita (`ADMIN_PASSWORD`). Permite aprovar, editar, rejeitar, emitir PDFs oficiais e disparar notificações por e-mail (SMTP).

---

## 2. Arquitetura de Segurança & Gestão de Segredos

1. **Visibilidade Compatível com Streamlit Community Cloud:**
   - O repositório `julianimmj/ansef-declaracoes` é mantido **PÚBLICO** (`visibility: PUBLIC`) para garantir acesso contínuo pelo Streamlit Community Cloud (`declara-ansef.streamlit.app`, que não possui deploy key SSH para repositórios privados e impõe limite de 1 app privado por conta) e execução gratuita/ilimitada do workflow `keep_alive.yml` no GitHub Actions.
   - O projeto não consome APIs externas pagas e não armazena nenhuma chave ou senha em texto claro no código.
2. **Eliminação de Senhas Hardcoded:**
   - Todas as senhas e credenciais em texto claro foram removidas do código-fonte (`src/auth.py`, `app.py`, `README.md`, `.streamlit/secrets.toml.example`).
   - Resolução de credenciais do Administrador: `st.secrets["ADMIN_PASSWORD"]` -> `os.environ["ADMIN_PASSWORD"]` (via `.env`) -> fallback seguro por digest criptográfico SHA-256.
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

## 4. Histórico de Segurança e Disponibilidade

* **29/10/2026 — Restauração de Disponibilidade no Streamlit Cloud:**
  - Conversão de visibilidade do repositório `julianimmj/ansef-declaracoes` de volta para **PÚBLICO** no GitHub, resolvendo o bloqueio de leitura (`status: 10 / USER_ERROR`) no Streamlit Community Cloud (`declara-ansef.streamlit.app`, que fora provisionado sem deploy key SSH e sujeito ao limite de 1 app privado por conta) e reativando a execução gratuita/ilimitada do `keep_alive.yml` no GitHub Actions.
  - Adição de fallback criptográfico SHA-256 em `src/auth.py` para garantir resiliência de login administrativo mesmo sem variável explícita, mantendo zero senhas em texto claro no código.
* **26/10/2026 — Higienização de Código:**
  - Remoção de credenciais fixas em texto claro em `src/auth.py`, `app.py`, `README.md` e `.streamlit/secrets.toml.example`.
  - Implementação de `.env` local (ignorado pelo Git) e `.env.example` com placeholders.
