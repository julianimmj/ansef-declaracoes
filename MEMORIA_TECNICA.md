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

* **10/11/2026 — Correção Definitiva do Reajuste Percentual da Tabela de Preços e Sincronização:**
  - **Causa raiz da não aplicação do reajuste percentual:**
    1. **Comportamento assíncrono de `st.number_input` sem `st.form`:** No frontend do Streamlit, quando o usuário digitava o percentual (ex: `4.22`) no campo de entrada e clicava diretamente no botão sem antes pressionar Enter ou desfocar o campo (blur), o evento de clique era despachado com o valor anterior do widget (`0.0`). Como consequência, o backend avaliava `abs(perc_tab) < 1e-6` e não executava `reajustar_tabela_faixas_percentual()`.
    2. **Ausência de visualização tabular direta:** A aba continha apenas 20 campos de entrada individuais de edição manual, sem uma tabela formatada de consulta imediata dos valores vigentes, gerando incerteza visual sobre quais valores estavam ativos.
    3. **Ambiguidade de base de cálculo (cumulativa vs. contratual):** O recálculo percentual aplicava o fator linearmente sobre os valores gravados no banco. Caso a tabela já estivesse com valores reajustados, uma nova tentativa aplicava juros compostos indesejados.
    4. **Dessincronização entre arquivos de runtime e sementes do repositório:** `_semear_arquivos_runtime()` só copiava sementes do repositório quando o arquivo em runtime não existia; se o repositório recebia commits mais novos via Git, o arquivo de runtime persistia com dados antigos.
  - **Solução implementada:**
    1. **Encapsulamento atômico em `st.form`:** O formulário de reajuste percentual agora utiliza `st.form("form_reajuste_tabela_geral_v{tab_v}")` com `st.form_submit_button()`, garantindo que o valor digitado seja despachado de forma 100% confiável e atômica para o servidor Streamlit.
    2. **Tabela oficial de visualização imediata (`st.dataframe`):** Exibição clara e destacada de todas as 10 faixas etárias formatadas em moeda (R$ Privativo e Coletivo).
    3. **Seletor de base de cálculo com idempotência:** Opção de aplicar o percentual sobre a **Tabela Padrão Contratual (R$ 350 a R$ 2.094)** [Recomendado] ou sobre os **Valores Atualmente Vigentes**. Com a base padrão, aplicar 4,22% resulta deterministicamente em R$ 364,77 / R$ 260,55 até R$ 2.182,37 / R$ 1.559,13.
    4. **Sincronização bidirecional runtime ↔ repositório:** Gravação simultânea no runtime e na semente do repositório, com comparação de timestamps mais recentes em `_semear_arquivos_runtime()` e `_carregar_backup_precos()`.
    5. **Isolamento de formulários:** A edição manual por faixa foi separada em um `st.form` próprio dentro de expander, impossibilitando conflitos entre reajuste geral e edições pontuais.

* **10/11/2026 — Resolução Completa da Falha em Cascata & Desbloqueio no Streamlit Cloud:**
  - **Causa raiz dos problemas em cascata:**
    1. **Bloqueio de `git pull` na plataforma:** O contêiner do Streamlit Community Cloud mantinha arquivos modificados em seu diretório de trabalho local (`/mount/src/ansef-declaracoes/data/`). Sempre que novos commits em `origin/main` tocavam nesses mesmos caminhos com SHAs distintos, o Git abortava o pull (`error: Your local changes to the following files would be overwritten by merge`). O contêiner permanecia congelado no commit `c661213` e nunca ativava as correções enviadas ao GitHub.
    2. **Truncamento de arquivos e ausência de semente embarcada para membros:** Ao contrário da tabela de faixas (que possuía `TABELA_FAIXAS_PADRAO` embarcada em Python), a tabela de membros dependia exclusivamente da leitura de `data/integrantes.csv`. Caso o CSV em disco fosse truncado por reloads simultâneos ou interrupção de escrita, `_carregar_csv()` executava `DELETE FROM membros` e lia 0 linhas, esvaziando a lista de titulares (`Nenhum titular cadastrado no sistema`).
    3. **Cache de módulos no Python (`sys.modules`) e `st.cache_resource`:** Hot-reloads do Streamlit sem recriação do contêiner mantinham módulos antigos e funções cacheadas na memória da sessão, não refletindo alterações de lógica e caminhos.
  - **Solução arquitetural definitiva implementada:**
    1. **Alinhamento limpo da árvore `data/` com o commit base `c661213`:** Os arquivos versionados em `data/` foram restaurados para os mesmos blob SHAs de `c661213`, permitindo que o `git pull` do Streamlit Cloud avance via fast-forward sem conflito de merge.
    2. **Isolamento de todos os arquivos de runtime fora da árvore Git:** `ansef_database.db`, `integrantes.csv`, `config_precos.json`, `solicitacoes_backup.json`, `declaracoes_anuais_backup.json` e `emails_pagamentos_backup.json` agora operam exclusivamente em diretório isolado de execução (`_caminho_runtime_dir()`), nunca sujando `/mount/src/ansef-declaracoes/data/`.
    3. **Sementes autoritativas embarcadas em Python:** Inclusão de `MEMBROS_PADRAO` (todos os 35 integrantes: 17 titulares + 18 dependentes/agregados), `TABELA_FAIXAS_PADRAO` (10 faixas: R$ 350/250 a R$ 2094/1496) e `SOLICITACOES_RECENTES_SEED` (solicitações #84 a #93 de Renan Marçal Rodrigues).
    4. **Escrita atômica em disco (`_escrever_texto_atomico`):** Todas as gravações de CSV e JSON utilizam arquivo temporário + `os.replace`, eliminando qualquer risco de arquivo truncado por interrupção de thread.
    5. **Carga transacional de membros segura:** `_carregar_csv()` valida a leitura completa antes de qualquer exclusão na tabela `membros`. Se o arquivo em disco estiver ausente ou com cardinalidade inferior à base mínima, recorre imediatamente a `MEMBROS_PADRAO`.
    6. **Invalidação proativa de cache no boot:** `app.py` expira referências obsoletas em `sys.modules`, sincroniza `_TARGET_SCHEMA_VERSION = '2026-11-10-v4'` no `@st.cache_resource` e executa limpeza automática de arquivos residuais no working tree do contêiner.
    7. **Síntese assíncrona de PDFs:** Geração pesada de PDFs em lote transferida para thread daemon em background, reduzindo o tempo de inicialização do banco para milissegundos e blindando contra `RerunException`.
* **10/11/2026 — Blindagem Inicial de Persistência (Tabela de Preços e Integrantes):**
  - Isolamento inicial do banco SQLite de runtime, commits transacionais por etapa em `inicializar_banco()`, validação de cardinalidade mínima e autorrecuperação de faixas etárias.
* **29/10/2026 — Restauração de Disponibilidade no Streamlit Cloud:**
  - Conversão de visibilidade do repositório `julianimmj/ansef-declaracoes` de volta para **PÚBLICO** no GitHub, resolvendo o bloqueio de leitura (`status: 10 / USER_ERROR`) no Streamlit Community Cloud (`declara-ansef.streamlit.app`, que fora provisionado sem deploy key SSH e sujeito ao limite de 1 app privado por conta) e reativando a execução gratuita/ilimitada do `keep_alive.yml` no GitHub Actions.
  - Remoção de constante de hash em `src/auth.py` para evitar falso-positivo heurístico do GitGuardian (`Generic Password` sobre o identificador `_ADMIN_PWD_SHA256`), mantendo autenticação 100% via `st.secrets` e variáveis de ambiente.
* **26/10/2026 — Higienização de Código:**
  - Remoção de credenciais fixas em texto claro em `src/auth.py`, `app.py`, `README.md` e `.streamlit/secrets.toml.example`.
  - Implementação de `.env` local (ignorado pelo Git) e `.env.example` com placeholders.
