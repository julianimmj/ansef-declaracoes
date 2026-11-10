# 🧠 Memória Técnica — ANSEF Declarações

> **Finalidade deste documento:**  
> Registro técnico consolidado (Single Source of Truth) da arquitetura, modelo de dados, fluxos de emissão e segurança do sistema **ANSEF Declarações**.  
> **Última Atualização:** 10 de Novembro de 2026 (Blindagem Definitiva da Tabela de Preços, Integrantes e Banco SQLite Runtime)  
> **Status Operacional Geral:** 🟢 100% Operacional e Auditado (Repositório Público Compatível com Streamlit Cloud + Autenticação Exclusiva via Secrets/Env + Zero Hardcoded Secrets)

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
   - Todas as senhas e credenciais em texto claro ou hashes estáticos foram removidas do código-fonte (`src/auth.py`, `app.py`, `README.md`, `.streamlit/secrets.toml.example`).
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

## 4. Histórico de Segurança e Disponibilidade

* **10/11/2026 — Blindagem Definitiva de Persistência (Tabela de Preços e Integrantes):**
  - **Causa raiz identificada:** Em produção no Streamlit Community Cloud, o banco de execução (`DB_PATH`) apontava diretamente para `data/ansef_database.db` (dentro da árvore Git em modo WAL). Ao aplicar reajuste percentual na tabela, dois commits assíncronos (`data/integrantes.csv` e `data/config_precos.json`) faziam o Streamlit Cloud atualizar o diretório do repositório com arquivos `-wal`/`-shm` ativos, disparando `recuperar_banco_corrompido()` -> `inicializar_banco()`. Como `conn.executescript()` comitava imediatamente as tabelas vazias (`CREATE TABLE`) e `conn.commit()` só ocorria após a síntese síncrona de dezenas de PDFs (`_garantir_pdfs_solicitacoes_aprovadas`), uma interrupção de rerun do Streamlit (`RerunException`/`StopException`) revertia os `INSERT`s de `tabela_faixas_etarias` e `membros`, deixando as tabelas com 0 registros. Além disso, `_banco_integro()` verificava apenas a existência das tabelas no `sqlite_master` (sem `COUNT(*) > 0`), e os widgets `st.number_input` (`fx_p_*`, `fx_c_*`) mantinham valores antigos em `st.session_state` após `st.rerun()`.
  - **Solução definitiva implementada:**
    1. Isolamento real do banco SQLite de runtime em diretório temporário fora da árvore Git (`_caminho_db_runtime_padrao()`), semeado automaticamente a partir de `REPO_DB_SEED_PATH` (`_semear_banco_runtime()`).
    2. Commits transacionais imediatos por etapa em `inicializar_banco()` (garantindo que `tabela_faixas_etarias` e `membros` sejam comitados antes de qualquer síntese de PDF) e commit incremental por PDF.
    3. Validação de cardinalidade mínima em `_banco_integro()` (`tabela_faixas_etarias >= 10` e `membros > 0`) e tratamento de `locked`/`busy` como estado transitório (não-corrupção).
    4. Autorrecuperação instantânea (`_garantir_faixas_populada` e `_garantir_membros_populados`) em todas as leituras e escritas de faixas e integrantes, proteção contra gravação de tabela vazia em `_salvar_backup_precos`, atualização em lote atômica (`atualizar_tabela_faixas_lote`) e limpeza de `st.session_state` (`fx_p_*`, `fx_c_*`) no `app.py` após reajustes.
* **29/10/2026 — Restauração de Disponibilidade no Streamlit Cloud:**
  - Conversão de visibilidade do repositório `julianimmj/ansef-declaracoes` de volta para **PÚBLICO** no GitHub, resolvendo o bloqueio de leitura (`status: 10 / USER_ERROR`) no Streamlit Community Cloud (`declara-ansef.streamlit.app`, que fora provisionado sem deploy key SSH e sujeito ao limite de 1 app privado por conta) e reativando a execução gratuita/ilimitada do `keep_alive.yml` no GitHub Actions.
  - Remoção de constante de hash em `src/auth.py` para evitar falso-positivo heurístico do GitGuardian (`Generic Password` sobre o identificador `_ADMIN_PWD_SHA256`), mantendo autenticação 100% via `st.secrets` e variáveis de ambiente.
* **26/10/2026 — Higienização de Código:**
  - Remoção de credenciais fixas em texto claro em `src/auth.py`, `app.py`, `README.md` e `.streamlit/secrets.toml.example`.
  - Implementação de `.env` local (ignorado pelo Git) e `.env.example` com placeholders.
