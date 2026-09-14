"""
ANSEF/CAS — Sistema de Declarações de Pagamento
Ponto de entrada da aplicação Streamlit.
"""
from __future__ import annotations

import sys
import os

# Garante que o diretório raiz da aplicação e src estejam sempre em sys.path (indispensável no Streamlit Cloud)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")

# No Streamlit Cloud (/mount/src/ansef-declaracoes), o Python pode carregar '/mount/src'
# como namespace package 'src', mascarando o pacote local. Removemos qualquer 'src' externo:
if "src" in sys.modules:
    mod = sys.modules["src"]
    mod_file = getattr(mod, "__file__", None) or ""
    mod_paths = getattr(mod, "__path__", [])
    if not str(mod_file).startswith(BASE_DIR) and not any(str(p).startswith(BASE_DIR) for p in mod_paths):
        del sys.modules["src"]

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import json
import io
import base64
from datetime import date, datetime

import streamlit as st
import pandas as pd

try:
    from src.database import (
        inicializar_banco,
        listar_titulares,
        buscar_grupo_familiar,
        criar_solicitacao,
        listar_solicitacoes_titular,
        listar_solicitacoes_pendentes,
        listar_todas_solicitacoes,
        obter_solicitacao,
        aprovar_solicitacao,
        rejeitar_solicitacao,
        cancelar_aprovacao,
        listar_solicitacoes_aprovadas,
        listar_todos_membros,
        atualizar_valor_membro,
        reajustar_valores_lote,
        contar_solicitacoes_por_status,
        contar_aprovadas_mes_atual,
        obter_anos_disponiveis,
        contar_solicitacoes_por_status_ano,
        obter_tabela_faixas,
        atualizar_tabela_faixa,
        reajustar_tabela_faixas_percentual,
        recalcular_mensalidades_membros,
        verificar_migracoes_grupo,
        listar_todas_migracoes,
        calcular_idade,
        determinar_faixa_etaria,
        adicionar_titular,
        adicionar_dependente,
        excluir_membro,
        excluir_grupo_familiar,
        obter_config_uniodonto,
        atualizar_valor_uniodonto,
        reajustar_valor_uniodonto_percentual,
        obter_uniodonto_titular,
        listar_todos_uniodonto,
        salvar_uniodonto_titular,
        remover_uniodonto_titular,
        obter_pdf_solicitacao,
        exportar_backup_json,
        importar_backup_json,
        exportar_backup_precos_json,
        importar_backup_precos_json,
        CONFIG_PRECOS_PATH,
        DB_PATH,
    )
    from src.auth import (
        login_associado,
        logout_associado,
        is_associado_logado,
        get_associado_logado,
        login_admin,
        logout_admin,
        is_admin_logado,
    )
    from src.email_service import (
        notificar_administrador_nova_solicitacao,
        notificar_administrador_migracao_faixa,
        verificar_status_smtp,
        enviar_email_teste,
    )
    from src.pdf_generator import gerar_pdf_declaracao
    from src.utils import (
        formatar_cpf,
        formatar_moeda,
        validar_cpf,
        limpar_cpf,
        mes_por_extenso,
        MESES_OPCOES,
    )
except ImportError:
    from database import (
        inicializar_banco,
        listar_titulares,
        buscar_grupo_familiar,
        criar_solicitacao,
        listar_solicitacoes_titular,
        listar_solicitacoes_pendentes,
        listar_todas_solicitacoes,
        obter_solicitacao,
        aprovar_solicitacao,
        rejeitar_solicitacao,
        cancelar_aprovacao,
        listar_solicitacoes_aprovadas,
        listar_todos_membros,
        atualizar_valor_membro,
        reajustar_valores_lote,
        contar_solicitacoes_por_status,
        contar_aprovadas_mes_atual,
        obter_anos_disponiveis,
        contar_solicitacoes_por_status_ano,
        obter_tabela_faixas,
        atualizar_tabela_faixa,
        reajustar_tabela_faixas_percentual,
        recalcular_mensalidades_membros,
        verificar_migracoes_grupo,
        listar_todas_migracoes,
        calcular_idade,
        determinar_faixa_etaria,
        adicionar_titular,
        adicionar_dependente,
        excluir_membro,
        excluir_grupo_familiar,
        obter_config_uniodonto,
        atualizar_valor_uniodonto,
        reajustar_valor_uniodonto_percentual,
        obter_uniodonto_titular,
        listar_todos_uniodonto,
        salvar_uniodonto_titular,
        remover_uniodonto_titular,
        obter_pdf_solicitacao,
        exportar_backup_json,
        importar_backup_json,
        exportar_backup_precos_json,
        importar_backup_precos_json,
        CONFIG_PRECOS_PATH,
        DB_PATH,
    )
    from auth import (
        login_associado,
        logout_associado,
        is_associado_logado,
        get_associado_logado,
        login_admin,
        logout_admin,
        is_admin_logado,
    )
    from email_service import (
        notificar_administrador_nova_solicitacao,
        notificar_administrador_migracao_faixa,
        verificar_status_smtp,
        enviar_email_teste,
    )
    from pdf_generator import gerar_pdf_declaracao
    from utils import (
        formatar_cpf,
        formatar_moeda,
        validar_cpf,
        limpar_cpf,
        mes_por_extenso,
        MESES_OPCOES,
    )

# ─── INICIALIZAÇÃO ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ANSEF/CAS - Declarações de Pagamento",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="auto",
)

# Inicializa o banco de dados na primeira execução
inicializar_banco()

# ─── CSS CUSTOM (RESPONSIVO PARA CELULAR & DESKTOP) ──────────────────────────────

st.markdown("""
<style>
    /* Tipografia institucional fluida e adaptável */
    .main-header {
        text-align: center;
        padding: 10px 0 5px 0;
    }
    .main-header h2 {
        color: #1B3A6B;
        font-size: clamp(1.05rem, 3.8vw, 1.35rem);
        margin: 0;
        font-weight: 700;
        line-height: 1.35;
    }
    .main-header h3 {
        color: #1B3A6B;
        font-size: clamp(0.95rem, 3vw, 1.15rem);
        margin: 4px 0 0 0;
        font-weight: 600;
    }
    .main-header p {
        color: #555;
        font-size: clamp(0.8rem, 2.4vw, 0.9rem);
        margin: 4px 0 0 0;
    }

    /* Badges de Status */
    .status-pendente {
        background: #FFF3CD;
        color: #856404;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        margin-bottom: 6px;
    }
    .status-aprovado {
        background: #D4EDDA;
        color: #155724;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        margin-bottom: 6px;
    }
    .status-rejeitado {
        background: #F8D7DA;
        color: #721C24;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        margin-bottom: 6px;
    }
    .status-cancelado {
        background: #F1F5F9;
        color: #475569;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
        margin-bottom: 6px;
        border: 1px solid #CBD5E1;
    }

    /* Badges de Modalidade do Plano e Faixa */
    .badge-plano {
        color: white;
        padding: 5px 14px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.88rem;
        display: inline-block;
        margin-bottom: 10px;
    }
    .badge-plano-p {
        background: #1B3A6B;
    }
    .badge-plano-c {
        background: #0284C7;
    }
    .tag-migracao-destaque {
        background: #FEF3C7;
        color: #92400E;
        font-size: 0.78rem;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 700;
        border: 1px solid #FCD34D;
        display: inline-block;
    }

    /* Cartões de Métricas */
    div[data-testid="stMetric"] {
        background: #f0f4fa;
        border-radius: 10px;
        padding: 12px 16px;
        border-left: 4px solid #1B3A6B;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    /* Otimizações para Dispositivos Móveis (Smartphones <= 768px) */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }

        /* Alvos de toque com altura mínima para facilitar uso com dedos */
        .stButton button, .stDownloadButton button {
            min-height: 46px !important;
            font-size: 0.98rem !important;
            border-radius: 8px !important;
        }

        /* Inputs e seletores confortáveis para toque no celular */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stSelectbox select {
            min-height: 42px !important;
            font-size: 0.95rem !important;
        }

        /* Métricas do painel administrativo em grade 2x2 no celular */
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) {
            flex-wrap: wrap !important;
            gap: 10px !important;
        }
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) > div {
            flex: 1 1 calc(50% - 10px) !important;
            min-width: 130px !important;
        }

        /* Expander com margem confortável */
        div[data-testid="stExpander"] {
            margin-bottom: 10px !important;
        }
    }

    /* ═══════════════════════════════════════════════════════════════
       SIDEBAR & BOTÕES DE NAVEGAÇÃO EXECUTIVOS
       ═══════════════════════════════════════════════════════════════ */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }

    /* Card da Marca Institucional na Sidebar */
    .sidebar-brand-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 12px 14px 12px;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .sidebar-brand-title {
        color: #1B3A6B;
        font-weight: 800;
        font-size: 0.96rem;
        letter-spacing: 0.5px;
        margin-top: 6px;
        margin-bottom: 2px;
    }
    .sidebar-brand-subtitle {
        color: #64748B;
        font-size: 0.76rem;
        font-weight: 500;
        margin-bottom: 10px;
    }
    .sidebar-status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #ECFDF5;
        color: #065F46;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 20px;
        border: 1px solid #A7F3D0;
    }
    .sidebar-status-dot {
        width: 7px;
        height: 7px;
        background: #10B981;
        border-radius: 50%;
        box-shadow: 0 0 6px #10B981;
    }

    .sidebar-nav-header {
        font-size: 0.72rem;
        font-weight: 700;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 10px;
        padding-left: 4px;
    }

    /* Oculta os círculos de radio padrão na sidebar */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }

    /* Transforma as opções do radio em cartões de navegação profissionais */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label {
        background: #FFFFFF !important;
        border: 1.5px solid #E2E8F0 !important;
        border-radius: 10px !important;
        padding: 13px 16px !important;
        margin-bottom: 10px !important;
        cursor: pointer !important;
        transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        border-left: 4px solid #CBD5E1 !important;
    }

    /* Hover no card não selecionado */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
        border-color: #1B3A6B !important;
        border-left-color: #0284C7 !important;
        background: #F1F5F9 !important;
        transform: translateX(3px) !important;
        box-shadow: 0 4px 12px rgba(27, 58, 107, 0.08) !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] > label p {
        font-size: 0.92rem !important;
        font-weight: 600 !important;
        color: #334155 !important;
        margin: 0 !important;
        line-height: 1.3 !important;
        transition: color 0.2s ease !important;
    }

    /* Estado Ativo / Selecionado */
    section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
        background: linear-gradient(135deg, #1B3A6B 0%, #1E40AF 100%) !important;
        border-color: #1B3A6B !important;
        border-left: 4px solid #FCD34D !important;
        box-shadow: 0 4px 14px rgba(27, 58, 107, 0.25) !important;
        transform: translateX(3px) !important;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
    }

    /* Rodapé institucional na Sidebar */
    .sidebar-footer-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 12px;
        margin-top: 28px;
        font-size: 0.74rem;
        color: #64748B;
        line-height: 1.45;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    .sidebar-footer-card strong {
        color: #1B3A6B;
    }
</style>
""", unsafe_allow_html=True)


# ─── CABEÇALHO ─────────────────────────────────────────────────────────────────

def render_header():
    """Renderiza o cabeçalho institucional da aplicação com o símbolo centralizado acima do título."""
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo_ansef.png")
    logo_b64 = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")

    img_html = (
        f'<div style="text-align: center; margin-bottom: 12px;">'
        f'<img src="data:image/png;base64,{logo_b64}" alt="Brasão ANSEF/CAS" style="display: inline-block; width: 95px; height: auto;" />'
        f'</div>'
        if logo_b64 else ""
    )

    st.markdown(f"""
    <div class="main-header">
        {img_html}
        <h2>ASSOCIAÇÃO DOS SERVIDORES DA POLÍCIA FEDERAL EM CAMPINAS/SP</h2>
        <h3>ANSEF/CAS</h3>
        <p>Sistema de Emissão de Declarações de Pagamento</p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()


render_header()

# ─── SIDEBAR ───────────────────────────────────────────────────────────────────

with st.sidebar:
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo_ansef.png")
    logo_b64 = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")

    img_side_html = (
        f'<img src="data:image/png;base64,{logo_b64}" style="width: 58px; height: auto; margin-bottom: 4px;" alt="Logo ANSEF" />'
        if logo_b64 else ""
    )

    st.markdown(f"""
    <div class="sidebar-brand-card">
        {img_side_html}
        <div class="sidebar-brand-title">ANSEF / CAS</div>
        <div class="sidebar-brand-subtitle">Campinas/SP • Declarações e Benefícios</div>
        <div class="sidebar-status-pill">
            <span class="sidebar-status-dot"></span>
            Sistema Online
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-nav-header">Navegação do Portal</div>', unsafe_allow_html=True)

    modulo = st.radio(
        "Selecione o módulo:",
        [
            "🏠 Área do Associado",
            "🔒 Área Restrita (Administração)"
        ],
        label_visibility="collapsed",
        key="nav_modulo_principal"
    )

    st.markdown(f"""
    <div class="sidebar-footer-card">
        <strong>ANSEF Campinas/CAS</strong><br>
        Associação dos Servidores da PF<br>
        CNPJ: <code>19.010.380/0001-73</code><br>
        <span style="color: #0284C7;">🔒 Conexão Criptografada SSL</span>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  ÁREA DO ASSOCIADO
# ═══════════════════════════════════════════════════════════════════════════════

if modulo == "🏠 Área do Associado":

    if not is_associado_logado():
        # ── TELA DE LOGIN DO ASSOCIADO ──────────────────────────────────────
        st.markdown("### 🔐 Acesso do Associado")
        st.info(
            "Selecione o titular do plano e informe a data de nascimento "
            "para acessar o portal."
        )

        titulares = listar_titulares()
        nomes_titulares = [t["titular_nome"] for t in titulares]

        if not nomes_titulares:
            st.warning("Nenhum titular cadastrado no sistema.")
            st.stop()

        titular_sel = st.selectbox(
            "Titular do Plano:",
            options=nomes_titulares,
            index=None,
            placeholder="Selecione o titular...",
        )

        data_nasc = st.date_input(
            "Data de Nascimento do Titular:",
            value=None,
            min_value=date(1900, 1, 1),
            max_value=date.today(),
            format="DD/MM/YYYY",
        )

        if st.button("🔓 Acessar Portal do Integrante", type="primary", use_container_width=True):
            if not titular_sel:
                st.error("Selecione um titular.")
            elif not data_nasc:
                st.error("Informe a data de nascimento.")
            elif login_associado(titular_sel, data_nasc):
                st.success(f"Bem-vindo(a), {titular_sel}!")
                st.rerun()
            else:
                st.error(
                    "❌ Data de nascimento não confere com os registros do titular "
                    "selecionado. Verifique os dados ou contate a administração."
                )

    else:
        # ── PAINEL DO ASSOCIADO LOGADO ──────────────────────────────────────
        titular_logado = get_associado_logado()
        grupo = buscar_grupo_familiar(titular_logado)
        if not grupo:
            st.warning("Grupo familiar não encontrado no cadastro.")
            st.stop()

        tipo_plano_grupo = grupo[0].get("tipo_plano_nome", "Coletivo")
        sigla_plano = (grupo[0].get("tipo_plano") or "C").upper()
        classe_badge = "badge-plano-p" if sigla_plano == "P" else "badge-plano-c"

        col_tit_info, col_logout = st.columns([3.5, 1])
        with col_tit_info:
            st.markdown(f"### 👤 Portal do Associado: **{titular_logado}**")
            st.markdown(
                f'<span class="badge-plano {classe_badge}">📋 Modalidade do Grupo: Plano {tipo_plano_grupo} ({sigla_plano})</span>',
                unsafe_allow_html=True,
            )
        with col_logout:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            if st.button("🚪 Sair do Portal", use_container_width=True, key="btn_logout_assoc"):
                logout_associado()
                st.rerun()

        # ── DESTAQUE DE REAJUSTE POR MUDANÇA DE FAIXA ETÁRIA ───────────────
        migracoes_grupo = [m for m in grupo if m.get("migrou_faixa")]
        if migracoes_grupo:
            itens_mig_html = "".join([
                f"<li style='margin-bottom: 6px;'>"
                f"<strong>{m['beneficiario_nome']}</strong> ({m['grau_parentesco']}): "
                f"completou <strong>{m['idade_atual']} anos</strong> e mudou da faixa <em>{m['faixa_anterior']}</em> "
                f"({formatar_moeda(m['valor_faixa_anterior'])}) para a faixa <strong>{m['faixa_calculada']}</strong>. "
                f"Novo valor mensal: <strong style='color:#B94A48;'>{formatar_moeda(m['valor_faixa_atual'])}</strong> (Plano {m['tipo_plano_nome']})."
                f"</li>"
                for m in migracoes_grupo
            ])
            st.markdown(f"""
            <div style="background-color: #FFF3CD; border: 2px solid #FCD34D; border-left: 6px solid #D97706; border-radius: 8px; padding: 14px 18px; margin: 12px 0 16px 0;">
                <h4 style="color: #92400E; margin: 0 0 6px 0; display: flex; align-items: center; gap: 8px;">
                    ⚠️ <span>Atenção: Reajuste por Mudança de Faixa Etária Identificado</span>
                </h4>
                <p style="color: #92400E; font-size: 0.93rem; margin-bottom: 8px;">
                    Identificamos que integrante(s) do seu grupo familiar completaram idade correspondente a uma nova faixa etária. O valor da mensalidade foi atualizado conforme a tabela oficial de preços:
                </p>
                <ul style="color: #92400E; font-size: 0.92rem; margin-bottom: 8px; padding-left: 20px;">
                    {itens_mig_html}
                </ul>
                <small style="color: #92400E;">Os valores correspondentes foram devidamente atualizados no seu perfil e já constam no formulário abaixo.</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background-color: #ECFDF5; border: 1px solid #A7F3D0; border-left: 5px solid #10B981; border-radius: 8px; padding: 10px 14px; margin: 10px 0 16px 0;">
                <span style="color: #065F46; font-weight: 600;">✅ Regularidade de Faixa Etária:</span>
                <span style="color: #065F46; font-size: 0.92rem;"> Todos os integrantes do grupo familiar estão na faixa etária correspondente à sua idade no Plano {tipo_plano_grupo}.</span>
            </div>
            """, unsafe_allow_html=True)

        # Dados bancários ANSEF Campinas para pagamento / Pix
        with st.expander("🏦 Dados Bancários para Transferência / PIX (Conta PJ ANSEF Campinas)", expanded=True):
            col_b1, col_b2 = st.columns([2, 1.5])
            with col_b1:
                st.markdown("""
                - **Favorecido:** Associação S P F E C Sp
                - **Banco:** 341 - Itaú Unibanco S.A.
                - **Agência:** 1370
                - **Conta Corrente:** 46177-2
                - **CNPJ:** `19.010.380/0001-73`
                """)
            with col_b2:
                st.markdown("**🔑 Chave PIX (CNPJ):**")
                st.code("19.010.380/0001-73", language="text")
                st.caption("Utilize a chave Pix acima para realizar o pagamento mensal à ANSEF Campinas.")

            st.markdown("""
            <div style="background-color: #FFFBEB; border-left: 3px solid #D97706; padding: 6px 10px; border-radius: 4px; margin-top: 8px; font-size: 0.82rem; color: #92400E;">
                ⏰ <strong>Vencimento:</strong> O pagamento efetuado pela ANSEF ocorre <strong>todo dia 10</strong> (ou dia útil subsequente). O depósito deve ser feito em tempo hábil para que haja saldo na conta da Associação.
            </div>
            """, unsafe_allow_html=True)

        # Resumo dos integrantes e valores vigentes
        with st.expander("👥 Integrantes do Grupo e Valores Vigentes por Faixa Etária", expanded=False):
            dados_tabela = []
            for m in grupo:
                dt_nasc_exib = m.get("data_nascimento", "")
                if dt_nasc_exib and "-" in dt_nasc_exib:
                    try:
                        dt_nasc_exib = datetime.strptime(dt_nasc_exib, "%Y-%m-%d").strftime("%d/%m/%Y")
                    except Exception:
                        pass
                dados_tabela.append({
                    "Beneficiário": m["beneficiario_nome"],
                    "Parentesco": m["grau_parentesco"],
                    "Nascimento": dt_nasc_exib,
                    "Idade": f"{m.get('idade_atual', '-')} anos",
                    "Faixa Etária": m.get("faixa_calculada", "-"),
                    "Modalidade": m.get("tipo_plano_nome", tipo_plano_grupo),
                    "Mensalidade": formatar_moeda(m.get("valor_vigente", 0.0)),
                    "Situação Faixa": "⚠️ Reajustada" if m.get("migrou_faixa") else "Regular",
                })
            st.dataframe(pd.DataFrame(dados_tabela), use_container_width=True, hide_index=True)

            # Detalhamento do Plano Odontológico Uniodonto (compacto)
            uniodonto_grupo = obter_uniodonto_titular(titular_logado)
            if uniodonto_grupo:
                st.markdown(f"""
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 3px solid #0284C7; border-radius: 4px; padding: 6px 12px; margin-top: 8px; font-size: 0.84rem; color: #1E293B; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
                    <div>
                        🦷 <strong>Plano Odontológico (Uniodonto):</strong>
                        <span style="color: #0369A1; font-weight: 600;">{uniodonto_grupo['vidas']} vida(s)</span>
                        <span style="color: #64748B;">({formatar_moeda(uniodonto_grupo['valor_por_vida'])}/vida)</span>
                    </div>
                    <div>
                        <span style="color: #64748B; font-size: 0.80rem;">Mensalidade Odonto:</span>
                        <strong style="color: #0F172A; font-size: 0.90rem;">{formatar_moeda(uniodonto_grupo['valor_total'])}</strong>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="color: #94A3B8; font-size: 0.80rem; margin-top: 6px;">
                    🦷 <em>Plano Odontológico (Uniodonto): Não contratado para este grupo.</em>
                </div>
                """, unsafe_allow_html=True)

        tab_nova, tab_historico = st.tabs(["📝 Nova Solicitação", "📄 Histórico e Downloads"])

        # ── ABA 1: NOVA SOLICITAÇÃO ─────────────────────────────────────────
        with tab_nova:
            st.markdown("#### Nova Solicitação de Declaração de Pagamento")

            # CPF do titular
            cpf_input = st.text_input(
                "CPF do Titular *",
                placeholder="000.000.000-00",
                max_chars=14,
                help="Informe o CPF do titular para constar na declaração.",
            )

            col_mes, col_ano = st.columns(2)
            with col_mes:
                mes_sel = st.selectbox(
                    "Mês de Referência (incidência) *",
                    options=list(MESES_OPCOES.keys()),
                    index=None,
                    placeholder="Selecione o mês...",
                )
            with col_ano:
                ano_atual = date.today().year
                ano_sel = st.selectbox(
                    "Ano de Referência *",
                    options=list(range(ano_atual, ano_atual - 5, -1)),
                )

            data_pag = st.date_input(
                "Data Efetiva do Pagamento *",
                value=None,
                format="DD/MM/YYYY",
            )

            st.markdown("---")
            st.markdown("##### 👥 Integrantes do Grupo Familiar")
            st.caption("Marque os beneficiários que devem constar na declaração e ajuste os valores se necessário.")

            # Tabela interativa com checkboxes e valores editáveis
            selecionados = []
            valor_soma = 0.0

            for i, membro in enumerate(grupo):
                col_membro, col_valor = st.columns([3, 1.8])

                m_id = membro.get("id", i)
                parentesco = membro.get("grau_parentesco", "Titular")
                idade_txt = f"{membro.get('idade_atual')} anos" if membro.get("idade_atual") is not None else ""
                faixa_txt = membro.get("faixa_calculada", "")
                aviso_mig = " ⚠️ [Faixa Reajustada]" if membro.get("migrou_faixa") else ""

                with col_membro:
                    label_box = f"**{membro['beneficiario_nome']}** ({parentesco}) — {idade_txt} | {faixa_txt}{aviso_mig}"
                    checked = st.checkbox(
                        label_box,
                        value=True,
                        key=f"check_m_{m_id}_{i}",
                    )

                with col_valor:
                    valor_base = membro.get("valor_vigente", 0.0) or membro.get("valor_mensalidade", 0.0) or 0.0
                    valor_edit = st.number_input(
                        "Valor (R$)",
                        value=float(valor_base),
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key=f"valor_m_{m_id}_{i}",
                        label_visibility="collapsed",
                        help=f"Valor de {membro['beneficiario_nome']}",
                    )

                if checked:
                    selecionados.append({
                        "nome": membro["beneficiario_nome"],
                        "parentesco": parentesco,
                        "valor": valor_edit,
                    })
                    valor_soma += valor_edit

            st.markdown("---")

            # Campos de valores lado a lado (proporcionais e harmoniosos)
            col_tot_unimed, col_tot_odonto = st.columns(2)
            with col_tot_unimed:
                valor_total = st.number_input(
                    "💰 Valor Total Declarado — UNIMED (R$)",
                    value=float(valor_soma),
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    help="Calculado pela soma dos selecionados. Constará na Declaração de Pagamento oficial da Unimed.",
                )

            with col_tot_odonto:
                uniodonto_tit = obter_uniodonto_titular(titular_logado)
                if uniodonto_tit:
                    vidas_odonto = uniodonto_tit["vidas"]
                    valor_odonto = uniodonto_tit["valor_total"]
                    valor_por_vida = uniodonto_tit["valor_por_vida"]
                    st.text_input(
                        "🦷 Plano Odontológico — UNIODONTO",
                        value=f"{formatar_moeda(valor_odonto)} ({vidas_odonto} vidas)",
                        disabled=True,
                        help=f"Plano Odontológico: {vidas_odonto} vida(s) x {formatar_moeda(valor_por_vida)}. Faturado via ANSEF (não entra na declaração Unimed).",
                    )
                else:
                    valor_odonto = 0.0
                    vidas_odonto = 0
                    st.text_input(
                        "🦷 Plano Odontológico — UNIODONTO",
                        value="Não contratado (R$ 0,00)",
                        disabled=True,
                        help="Este grupo familiar não possui plano odontológico.",
                    )

            if uniodonto_tit and valor_odonto > 0:
                montante_transferencia = valor_total + valor_odonto
                st.markdown(f"""
                <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 4px solid #1E40AF; border-radius: 6px; padding: 8px 12px; margin: 4px 0 10px 0; font-size: 0.86rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div>
                        💳 <strong>Total p/ Transferência / PIX:</strong>
                        <span style="font-size: 1.05rem; font-weight: 700; color: #1E3A8A; margin-left: 4px;">{formatar_moeda(montante_transferencia)}</span>
                        <span style="color: #64748B; font-size: 0.80rem; margin-left: 4px;">(Unimed: {formatar_moeda(valor_total)} + Odonto: {formatar_moeda(valor_odonto)})</span>
                    </div>
                    <div style="font-size: 0.80rem; color: #334155;">
                        Chave Pix: <strong>19.010.380/0001-73</strong>
                    </div>
                </div>
                <div style="font-size: 0.78rem; color: #64748B; margin: -6px 0 10px 4px;">
                    ℹ️ <em>Apenas o valor da UNIMED ({formatar_moeda(valor_total)}) constará na Declaração emitida. Vencimento na ANSEF: dia 10.</em>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("")

            if st.button(
                "📨 Enviar para Análise e Emissão",
                type="primary",
                use_container_width=True,
            ):
                # Validações
                erros = []
                if not cpf_input or not validar_cpf(cpf_input):
                    erros.append("CPF inválido. Informe 11 dígitos.")
                if not mes_sel:
                    erros.append("Selecione o mês de referência.")
                if not data_pag:
                    erros.append("Informe a data de pagamento.")
                if valor_total <= 0:
                    erros.append("O valor total deve ser maior que zero.")
                if not selecionados:
                    erros.append("Selecione pelo menos um beneficiário.")

                if erros:
                    for e in erros:
                        st.error(e)
                else:
                    mes_num = MESES_OPCOES[mes_sel]
                    cpf_limpo = limpar_cpf(cpf_input)
                    data_pag_str = data_pag.strftime("%d/%m/%Y")
                    deps_json = json.dumps(selecionados, ensure_ascii=False)

                    with st.spinner("Registrando solicitação..."):
                        sol_id = criar_solicitacao(
                            titular_nome=titular_logado,
                            titular_cpf=cpf_limpo,
                            dependentes_json=deps_json,
                            mes_ref=mes_num,
                            ano_ref=ano_sel,
                            data_pagamento=data_pag_str,
                            valor_total=valor_total,
                        )

                        # Tenta enviar e-mail (não bloqueia se falhar)
                        sucesso_email, msg_email = notificar_administrador_nova_solicitacao(
                            titular_nome=titular_logado,
                            titular_cpf=cpf_limpo,
                            mes_referencia=mes_num,
                            ano_referencia=ano_sel,
                            dependentes=selecionados,
                            valor_total=valor_total,
                            data_pagamento=data_pag_str,
                        )

                    st.success(
                        f"✅ Sua solicitação **#{sol_id}** foi enviada com sucesso!\n\n"
                        "Aguarde a aprovação do administrador em até **3 dias úteis**.\n\n"
                        "Você pode acompanhar o andamento e baixar sua declaração "
                        "diretamente nesta página, na aba **Histórico e Downloads**, "
                        "acessando com seu nome e data de nascimento."
                    )
                    if sucesso_email:
                        st.caption("📧 Notificação enviada por e-mail para a administração.")
                    st.balloons()

        # ── ABA 2: HISTÓRICO ────────────────────────────────────────────────
        with tab_historico:
            st.markdown("#### 📄 Histórico de Solicitações")

            solicitacoes = listar_solicitacoes_titular(titular_logado)

            if not solicitacoes:
                st.info("Nenhuma solicitação registrada até o momento.")
            else:
                for sol in solicitacoes:
                    status = sol["status"]
                    if status == "PENDENTE":
                        badge = '<span class="status-pendente">⏳ PENDENTE</span>'
                    elif status == "APROVADO":
                        badge = '<span class="status-aprovado">✅ APROVADO</span>'
                    elif status == "CANCELADO":
                        badge = '<span class="status-cancelado">🚫 CANCELADO PELA ADMINISTRAÇÃO</span>'
                    else:
                        badge = '<span class="status-rejeitado">❌ REJEITADO</span>'

                    mes_ext = mes_por_extenso(sol["mes_referencia"]).capitalize()
                    data_sol = sol["data_solicitacao"][:10] if sol["data_solicitacao"] else ""

                    with st.expander(
                        f"Solicitação #{sol['id']} — {mes_ext}/{sol['ano_referencia']} — "
                        f"{formatar_moeda(sol['valor_total'])} — {status}"
                    ):
                        st.markdown(badge, unsafe_allow_html=True)
                        st.markdown(f"**Data da Solicitação:** {data_sol}")
                        st.markdown(
                            f"**Referência:** {mes_ext} de {sol['ano_referencia']}"
                        )
                        st.markdown(
                            f"**Valor Declarado:** {formatar_moeda(sol['valor_total'])}"
                        )
                        st.markdown(
                            f"**CPF:** {formatar_cpf(sol['titular_cpf'])}"
                        )

                        if status == "APROVADO":
                            pdf_data = sol.get("pdf_gerado") or obter_pdf_solicitacao(sol["id"])
                            if pdf_data:
                                st.download_button(
                                    label="📥 Baixar Declaração (PDF)",
                                    data=pdf_data,
                                    file_name=f"Declaracao_ANSEF_{titular_logado}_{mes_ext}_{sol['ano_referencia']}.pdf",
                                    mime="application/pdf",
                                    type="primary",
                                    use_container_width=True,
                                    key=f"dl_pdf_assoc_{sol['id']}",
                                )
                            else:
                                st.info("O PDF está sendo processado pela administração.")
                        elif status == "CANCELADO":
                            st.warning(
                                "⚠️ **Esta aprovação foi cancelada/revogada pela administração.** "
                                "O documento não está mais disponível para download."
                            )
                            if sol.get("observacoes_admin"):
                                st.info(f"**Observações da Administração:** {sol['observacoes_admin']}")

                        if status == "REJEITADO" and sol.get("observacoes_admin"):
                            st.error(f"**Motivo da recusa:** {sol['observacoes_admin']}")

                        if sol.get("codigo_validacao"):
                            st.caption(f"Código de autenticidade: {sol['codigo_validacao']}")


# ═══════════════════════════════════════════════════════════════════════════════
#  ÁREA RESTRITA DO ADMINISTRADOR
# ═══════════════════════════════════════════════════════════════════════════════

elif modulo == "🔒 Área Restrita (Administração)":

    if not is_admin_logado():
        # ── LOGIN DO ADMIN ──────────────────────────────────────────────────
        st.markdown("### 🔒 Área Restrita — Administração")
        st.info("Acesso exclusivo para o administrador do sistema ANSEF/CAS.")

        senha = st.text_input("Senha de Administrador:", type="password")

        if st.button("🔑 Entrar", type="primary", use_container_width=True):
            if login_admin(senha):
                st.success("Acesso concedido!")
                st.rerun()
            else:
                st.error("❌ Senha incorreta.")

    else:
        # ── PAINEL ADMINISTRATIVO ───────────────────────────────────────────
        st.markdown("### 🛡️ Painel de Administração — ANSEF/CAS")

        _, col_adm_logout = st.columns([4, 1])
        with col_adm_logout:
            if st.button("🚪 Sair da Administração", use_container_width=True):
                logout_admin()
                st.rerun()

        # Métricas no topo — exibem apenas o ano corrente
        from datetime import datetime as _dt
        _ano_corrente = _dt.now().year
        metricas = contar_solicitacoes_por_status()
        aprovadas_mes = contar_aprovadas_mes_atual()

        st.caption(f"📆 Declarações — Ano de referência: **{_ano_corrente}**  ·  Retenção: 5 anos")

        col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
        col_m1.metric("⏳ Pendentes", metricas.get("PENDENTE", 0))
        col_m2.metric("✅ Aprovadas", metricas.get("APROVADO", 0))
        col_m3.metric("❌ Recusadas", metricas.get("REJEITADO", 0))
        col_m4.metric("🚫 Canceladas", metricas.get("CANCELADO", 0))
        col_m5.metric("📅 Aprovadas no Mês", aprovadas_mes)
        col_m6.metric(f"📊 Total {_ano_corrente}", sum(metricas.values()))

        st.divider()

        # ── ALERTA DE MIGRAÇÃO DE FAIXA ETÁRIA (NOTIFICAÇÃO ADMINISTRATIVA) ──
        migracoes_admin = listar_todas_migracoes()
        if migracoes_admin:
            with st.container():
                st.markdown(f"""
                <div style="background-color: #FFFBEB; border: 2px solid #FCD34D; border-left: 6px solid #D97706; border-radius: 8px; padding: 14px 18px; margin: 10px 0 16px 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                        <div>
                            <h4 style="color: #92400E; margin: 0; font-size: 1.05rem;">
                                🔔 Notificação: {len(migracoes_admin)} Integrante(s) com Mudança de Faixa Etária
                            </h4>
                            <p style="color: #92400E; margin: 4px 0 0 0; font-size: 0.9rem;">
                                Foram identificados associados/dependentes que atingiram idade de transição de faixa etária. Seus valores de mensalidade já foram recalculados pela tabela oficial de preços.
                            </p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_btn_mail, _ = st.columns([2.2, 2.8])
                with col_btn_mail:
                    if st.button("📧 Enviar Relatório de Faixas por E-mail ao Administrador", key="btn_send_mail_faixas_top", use_container_width=True):
                        with st.spinner("Enviando e-mail de notificação ao administrador..."):
                            ok_mail, msg_mail = notificar_administrador_migracao_faixa(migracoes_admin)
                            if ok_mail:
                                st.success("✅ E-mail enviado com sucesso ao administrador!")
                            else:
                                st.error(f"❌ Falha ao enviar e-mail: {msg_mail}")

                with st.expander(f"📋 Visualizar Tabela dos {len(migracoes_admin)} Integrantes com Reajuste por Faixa", expanded=False):
                    df_migs = pd.DataFrame([
                        {
                            "Titular": m["titular_nome"],
                            "Beneficiário": m["beneficiario_nome"],
                            "Parentesco": m["grau_parentesco"],
                            "Idade": f"{m['idade_atual']} anos",
                            "Faixa Anterior": m["faixa_anterior"],
                            "Nova Faixa": m["faixa_calculada"],
                            "Plano": m["tipo_plano_nome"],
                            "Valor Anterior": formatar_moeda(m["valor_faixa_anterior"]),
                            "Novo Valor": formatar_moeda(m["valor_faixa_atual"]),
                        }
                        for m in migracoes_admin
                    ])
                    st.dataframe(df_migs, use_container_width=True, hide_index=True)

        tab_pend, tab_aprovadas, tab_reajuste, tab_gestao_grupos, tab_uniodonto, tab_relatorio, tab_config_email = st.tabs([
            "📋 Fila de Pendentes",
            "📄 Declarações Aprovadas",
            "💰 Tabela de Preços e Reajustes",
            "👥 Gestão de Integrantes & Grupos",
            "🦷 Plano Odontológico (Uniodonto)",
            "📊 Histórico Geral",
            "⚙️ Configuração de E-mail",
        ])

        # ── ABA 1: FILA DE PENDENTES ────────────────────────────────────────
        with tab_pend:
            pendentes = listar_solicitacoes_pendentes()

            if not pendentes:
                st.success("✅ Nenhuma solicitação pendente no momento.")
            else:
                st.markdown(f"**{len(pendentes)}** solicitação(ões) aguardando análise:")

                for sol in pendentes:
                    mes_ext = mes_por_extenso(sol["mes_referencia"]).capitalize()
                    header = (
                        f"#{sol['id']} — {sol['titular_nome']} — "
                        f"{mes_ext}/{sol['ano_referencia']} — "
                        f"{formatar_moeda(sol['valor_total'])}"
                    )

                    with st.expander(header, expanded=False):
                        st.markdown(f"**Titular:** {sol['titular_nome']}")
                        st.markdown(f"**CPF:** {formatar_cpf(sol['titular_cpf'])}")
                        st.markdown(f"**Data da Solicitação:** {sol['data_solicitacao'][:19]}")

                        try:
                            deps = json.loads(sol["dependentes_incluidos"])
                        except (json.JSONDecodeError, TypeError):
                            deps = []

                        st.markdown("---")
                        st.markdown("##### ✏️ Revisão e Edição dos Dados")

                        # Campos editáveis
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            meses_lista = list(MESES_OPCOES.keys())
                            idx_mes = sol["mes_referencia"] - 1
                            mes_edit = st.selectbox(
                                "Mês de Referência",
                                options=meses_lista,
                                index=idx_mes if 0 <= idx_mes < 12 else 0,
                                key=f"adm_mes_{sol['id']}",
                            )
                        with col_e2:
                            ano_edit = st.number_input(
                                "Ano de Referência",
                                value=sol["ano_referencia"],
                                min_value=2020,
                                max_value=2030,
                                key=f"adm_ano_{sol['id']}",
                            )

                        data_pag_edit = st.text_input(
                            "Data de Pagamento (DD/MM/AAAA)",
                            value=sol["data_pagamento"],
                            key=f"adm_dpag_{sol['id']}",
                        )

                        st.markdown("##### 👥 Beneficiários na Declaração")
                        st.caption("Marque/desmarque para incluir/excluir. Ajuste os valores individuais.")

                        # Carrega grupo familiar completo para permitir inclusão
                        grupo_completo = buscar_grupo_familiar(sol["titular_nome"])
                        nomes_deps = {d["nome"] for d in deps}

                        deps_editados = []
                        valor_soma_adm = 0.0

                        for j, membro in enumerate(grupo_completo):
                            nome_m = membro["beneficiario_nome"]
                            # Verifica se estava na solicitação original
                            dep_original = next((d for d in deps if d["nome"] == nome_m), None)
                            estava_incluido = dep_original is not None

                            parentesco_m = membro.get("grau_parentesco", "Titular")
                            col_info_adm, col_v = st.columns([3, 1.8])
                            with col_info_adm:
                                inc = st.checkbox(
                                    f"**{nome_m}** ({parentesco_m})",
                                    value=estava_incluido,
                                    key=f"adm_inc_{sol['id']}_{j}",
                                )
                            with col_v:
                                val_base = dep_original["valor"] if dep_original else (
                                    membro.get("valor_vigente") or membro.get("valor_mensalidade") or 0.0
                                )
                                val_adm = st.number_input(
                                    "Valor (R$)",
                                    value=float(val_base),
                                    min_value=0.0,
                                    step=0.01,
                                    format="%.2f",
                                    key=f"adm_val_{sol['id']}_{j}",
                                    label_visibility="collapsed",
                                    help=f"Valor de {nome_m}",
                                )

                            if inc:
                                deps_editados.append({
                                    "nome": nome_m,
                                    "parentesco": parentesco_m,
                                    "valor": val_adm,
                                })
                                valor_soma_adm += val_adm

                        st.markdown("---")
                        valor_total_adm = st.number_input(
                            "💰 Valor Total Final (R$)",
                            value=float(valor_soma_adm),
                            min_value=0.0,
                            step=0.01,
                            format="%.2f",
                            key=f"adm_vtotal_{sol['id']}",
                        )

                        st.markdown("")
                        col_aprovar, col_rejeitar = st.columns(2)

                        with col_aprovar:
                            if st.button(
                                "✅ Aprovar e Gerar Declaração",
                                type="primary",
                                use_container_width=True,
                                key=f"aprovar_{sol['id']}",
                            ):
                                with st.spinner("Gerando PDF da declaração..."):
                                    mes_num_adm = MESES_OPCOES[mes_edit]
                                    deps_json_adm = json.dumps(deps_editados, ensure_ascii=False)

                                    # Gera o PDF
                                    pdf_bytes = gerar_pdf_declaracao(
                                        titular_nome=sol["titular_nome"],
                                        titular_cpf=sol["titular_cpf"],
                                        dependentes_json=deps_json_adm,
                                        mes_referencia=mes_num_adm,
                                        ano_referencia=ano_edit,
                                        data_pagamento=data_pag_edit,
                                        valor_total=valor_total_adm,
                                        codigo_validacao=sol.get("codigo_validacao", ""),
                                    )

                                    aprovar_solicitacao(
                                        sol_id=sol["id"],
                                        dependentes_json=deps_json_adm,
                                        valor_total=valor_total_adm,
                                        data_pagamento=data_pag_edit,
                                        mes_ref=mes_num_adm,
                                        ano_ref=ano_edit,
                                        pdf_bytes=pdf_bytes,
                                    )

                                st.success(
                                    f"✅ Solicitação #{sol['id']} aprovada! "
                                    "PDF gerado e salvo com sucesso."
                                )
                                st.download_button(
                                    label="📥 Baixar PDF Gerado",
                                    data=pdf_bytes,
                                    file_name=(
                                        f"Declaracao_ANSEF_{sol['titular_nome']}_"
                                        f"{mes_edit}_{ano_edit}.pdf"
                                    ),
                                    mime="application/pdf",
                                    key=f"dl_adm_{sol['id']}",
                                )
                                st.rerun()

                        with col_rejeitar:
                            motivo = st.text_area(
                                "Motivo da recusa (obrigatório para rejeitar):",
                                key=f"motivo_{sol['id']}",
                                placeholder="Ex: Valor não confere com o demonstrativo bancário...",
                            )
                            if st.button(
                                "❌ Rejeitar Solicitação",
                                use_container_width=True,
                                key=f"rejeitar_{sol['id']}",
                            ):
                                if not motivo.strip():
                                    st.error("Informe o motivo da rejeição.")
                                else:
                                    rejeitar_solicitacao(sol["id"], motivo.strip())
                                    st.warning(f"Solicitação #{sol['id']} rejeitada.")
                                    st.rerun()

        # ── ABA 2: DECLARAÇÕES APROVADAS & GESTÃO ───────────────────────────
        with tab_aprovadas:
            st.markdown("#### 📄 Declarações Aprovadas & Gestão")
            st.caption(
                "Consulte todas as declarações emitidas pela administração. "
                "Você pode baixar e imprimir o PDF oficial a qualquer momento, "
                "ou cancelar/revogar a aprovação caso entenda necessário."
            )

            aprovadas = listar_solicitacoes_aprovadas()

            if not aprovadas:
                st.info("Nenhuma declaração aprovada no momento.")
            else:
                st.markdown(f"**{len(aprovadas)}** declaração(ões) aprovada(s) ativas:")

                # Busca rápida por titular
                busca_aprov = st.text_input(
                    "🔍 Filtrar por nome do titular:",
                    placeholder="Digite para filtrar...",
                    key="busca_aprovadas_input",
                )
                if busca_aprov:
                    aprovadas = [a for a in aprovadas if busca_aprov.lower() in a["titular_nome"].lower()]

                for sol_ap in aprovadas:
                    mes_ap_ext = mes_por_extenso(sol_ap["mes_referencia"]).capitalize()
                    data_an_str = sol_ap["data_analise"][:10] if sol_ap.get("data_analise") else ""

                    with st.expander(
                        f"#{sol_ap['id']} — {sol_ap['titular_nome']} — {mes_ap_ext}/{sol_ap['ano_referencia']} — {formatar_moeda(sol_ap['valor_total'])}",
                        expanded=False,
                    ):
                        col_ap1, col_ap2 = st.columns(2)
                        with col_ap1:
                            st.markdown(f"**Titular:** {sol_ap['titular_nome']}")
                            st.markdown(f"**CPF:** {formatar_cpf(sol_ap['titular_cpf'])}")
                            st.markdown(f"**Referência:** {mes_ap_ext} de {sol_ap['ano_referencia']}")
                        with col_ap2:
                            st.markdown(f"**Data de Quitação:** {sol_ap['data_pagamento']}")
                            st.markdown(f"**Valor Total:** {formatar_moeda(sol_ap['valor_total'])}")
                            st.markdown(f"**Código de Autenticidade:** `{sol_ap.get('codigo_validacao', 'N/A')}`")

                        # Dependentes
                        deps_ap = json.loads(sol_ap.get("dependentes_incluidos", "[]"))
                        if deps_ap:
                            st.markdown("##### 👥 Beneficiários Cobertos:")
                            for d in deps_ap:
                                st.write(f"- **{d.get('nome')}** ({d.get('parentesco', 'Titular')}) — {formatar_moeda(d.get('valor', 0))}")

                        st.markdown("---")
                        col_print, col_cancel = st.columns([1.5, 2])

                        with col_print:
                            pdf_admin = sol_ap.get("pdf_gerado") or obter_pdf_solicitacao(sol_ap["id"])
                            if pdf_admin:
                                st.download_button(
                                    label="🖨️ Baixar / Imprimir PDF",
                                    data=pdf_admin,
                                    file_name=f"Declaracao_ANSEF_{sol_ap['titular_nome']}_{mes_ap_ext}_{sol_ap['ano_referencia']}.pdf",
                                    mime="application/pdf",
                                    type="primary",
                                    use_container_width=True,
                                    key=f"adm_dl_ap_{sol_ap['id']}",
                                )
                            else:
                                st.caption("PDF não encontrado no banco.")

                        with col_cancel:
                            with st.popover("🚫 Cancelar Aprovação", use_container_width=True):
                                st.markdown("##### ⚠️ Revogar Declaração")
                                st.warning(
                                    "Ao cancelar esta aprovação, o associado **não terá mais acesso** "
                                    "a este documento no portal de declarações."
                                )
                                motivo_canc = st.text_input(
                                    "Motivo do cancelamento (opcional):",
                                    placeholder="Ex: Erro no valor, duplicidade...",
                                    key=f"motivo_canc_{sol_ap['id']}",
                                )
                                if st.button(
                                    "Confirmar Cancelamento",
                                    type="primary",
                                    key=f"btn_canc_{sol_ap['id']}",
                                    use_container_width=True,
                                ):
                                    cancelar_aprovacao(sol_ap["id"], motivo_canc)
                                    st.success(f"Declaração #{sol_ap['id']} cancelada com sucesso!")
                                    st.rerun()

        # ── ABA 3: TABELA DE PREÇOS E REAJUSTES ─────────────────────────────
        with tab_reajuste:
            st.markdown("#### 💰 Tabela Oficial de Faixas Etárias e Reajustes")

            subtab_faixas, subtab_membros = st.tabs([
                "📊 Tabela de Preços por Faixa Etária",
                "👥 Mensalidades Vigentes por Integrante",
            ])

            with subtab_faixas:
                st.markdown("##### 🏷️ Preços por Faixa Etária (Planos Privativo e Coletivo)")
                st.caption(
                    "Esta tabela define os valores base por faixa etária. "
                    "Qualquer correção salva aqui recalcula automaticamente as mensalidades de todos os associados e dependentes."
                )

                # Reajuste geral da tabela em percentual
                with st.expander("📈 Aplicar Reajuste Percentual Geral na Tabela (%)", expanded=False):
                    col_p_in, col_p_btn = st.columns([2, 1.2])
                    with col_p_in:
                        perc_tab = st.number_input(
                            "Percentual de Reajuste da Tabela (%)",
                            value=0.0,
                            step=0.1,
                            format="%.2f",
                            key="perc_reaj_tabela_geral",
                            help="Aplica o percentual em todas as faixas (Privativo e Coletivo) e recalcula todos os membros da base.",
                        )
                    with col_p_btn:
                        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                        if st.button("Aplicar na Tabela", type="primary", key="btn_reaj_tabela_geral", use_container_width=True):
                            if perc_tab == 0:
                                st.warning("Informe um percentual diferente de zero.")
                            else:
                                tot_recalc = reajustar_tabela_faixas_percentual(perc_tab)
                                st.success(f"✅ Reajuste de {perc_tab:+.2f}% aplicado a todas as faixas! {tot_recalc} integrante(s) recalculados.")
                                st.rerun()

                faixas_atuais = obter_tabela_faixas()

                st.markdown("---")
                st.markdown("##### ✏️ Edição dos Valores por Faixa Etária")

                valores_editados = {}
                for fx in faixas_atuais:
                    col_fx_nome, col_fx_p, col_fx_c = st.columns([2.5, 2, 2])
                    with col_fx_nome:
                        idade_limite = f"{fx['idade_min']} a {fx['idade_max']} anos" if fx["idade_max"] < 120 else "A partir de 59 anos"
                        st.markdown(
                            f"**{fx['faixa_etaria']}**<br><small style='color:#666;'>{idade_limite}</small>",
                            unsafe_allow_html=True,
                        )
                    with col_fx_p:
                        novo_p = st.number_input(
                            "Valor Privativo (R$)",
                            value=float(fx["valor_privativo"]),
                            min_value=0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"fx_p_{fx['id']}",
                        )
                    with col_fx_c:
                        novo_c = st.number_input(
                            "Valor Coletivo (R$)",
                            value=float(fx["valor_coletivo"]),
                            min_value=0.0,
                            step=1.0,
                            format="%.2f",
                            key=f"fx_c_{fx['id']}",
                        )
                    valores_editados[fx["id"]] = (novo_p, novo_c)

                st.markdown("")
                if st.button("💾 Salvar Alterações na Tabela e Recalcular Todos os Integrantes", type="primary", use_container_width=True, key="btn_save_all_faixas"):
                    for fx_id, (vp, vc) in valores_editados.items():
                        atualizar_tabela_faixa(fx_id, vp, vc)
                    st.success("✅ Tabela de faixas atualizada com sucesso! Todos os membros foram recalculados.")
                    st.rerun()

            with subtab_membros:
                membros = listar_todos_membros()

                st.markdown("##### Mensalidades Vigentes por Integrante")
                st.caption("Valores calculados com base na idade atual e no plano de cada titular (C ou P).")

                # Filtro de busca
                busca = st.text_input("🔍 Buscar por nome do titular ou dependente:", placeholder="Digite para filtrar...")

                membros_filtrados = membros
                if busca:
                    busca_lower = busca.lower()
                    membros_filtrados = [
                        m for m in membros
                        if busca_lower in m["beneficiario_nome"].lower()
                        or busca_lower in m["titular_nome"].lower()
                    ]

                if not membros_filtrados:
                    st.info("Nenhum membro encontrado.")
                else:
                    for k, m in enumerate(membros_filtrados):
                        parentesco_desc = m.get("grau_parentesco", "Titular")
                        val_atual = float(m.get("valor_vigente", 0) or 0)
                        idade_str = f"{m['idade_atual']} anos" if m.get("idade_atual") is not None else "N/A"
                        faixa_str = m.get("faixa_calculada", "N/A")
                        aviso_mig_tag = " [⚠️ FAIXA REAJUSTADA]" if m.get("migrou_faixa") else ""

                        with st.expander(
                            f"👤 {m['beneficiario_nome']} ({parentesco_desc}) — {formatar_moeda(val_atual)}{aviso_mig_tag}",
                            expanded=False,
                        ):
                            st.caption(
                                f"**Titular do Grupo:** {m['titular_nome']} | "
                                f"**Idade:** {idade_str} | "
                                f"**Faixa Etária:** {faixa_str} | "
                                f"**Modalidade:** Plano {m.get('tipo_plano_nome', 'Coletivo')} ({m.get('tipo_plano', 'C')})"
                            )
                            col_reaj_val, col_reaj_btn = st.columns([3, 1.2])
                            with col_reaj_val:
                                novo_val = st.number_input(
                                    "Ajuste Manual da Mensalidade (R$):",
                                    value=val_atual,
                                    min_value=0.0,
                                    step=0.01,
                                    format="%.2f",
                                    key=f"reaj_{k}",
                                )
                            with col_reaj_btn:
                                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                                if st.button("💾 Salvar Ajuste", key=f"save_reaj_{k}", use_container_width=True):
                                    atualizar_valor_membro(m["beneficiario_nome"], novo_val)
                                    st.toast(
                                        f"Valor de {m['beneficiario_nome']} atualizado para {formatar_moeda(novo_val)}",
                                        icon="✅",
                                    )
                                    st.rerun()

        # ── ABA 4: GESTÃO DE INTEGRANTES E GRUPOS FAMILIARES ────────────────
        with tab_gestao_grupos:
            st.markdown("#### 👥 Gestão de Integrantes e Grupos Familiares")
            st.caption(
                "Cadastre novos titulares, adicione dependentes com enquadramento automático na tabela de preços oficial, "
                "ou gerencie e exclua integrantes e grupos familiares existentes."
            )

            subtab_cad_titular, subtab_cad_dependente, subtab_gerenciar_grupos = st.tabs([
                "➕ Novo Titular (Criar Grupo)",
                "➕ Adicionar Dependente",
                "📋 Gerenciar / Excluir Grupos e Integrantes",
            ])

            # ── SUB-ABA 1: NOVO TITULAR ─────────────────────────────────────
            with subtab_cad_titular:
                st.markdown("##### ➕ Cadastro de Novo Titular")
                st.info("O titular é o responsável pelo grupo familiar. A idade e a mensalidade são enquadradas automaticamente pela data de nascimento.")

                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    novo_tit_nome = st.text_input("Nome Completo do Titular *", placeholder="Ex: João da Silva", key="cad_tit_nome")
                    novo_tit_cpf = st.text_input("CPF do Titular", placeholder="000.000.000-00", max_chars=14, key="cad_tit_cpf")

                with col_t2:
                    novo_tit_nasc = st.date_input(
                        "Data de Nascimento *",
                        value=None,
                        min_value=date(1910, 1, 1),
                        max_value=date.today(),
                        format="DD/MM/YYYY",
                        key="cad_tit_nasc",
                    )
                    novo_tit_plano = st.selectbox(
                        "Modalidade do Plano *",
                        ["Plano Coletivo (C)", "Plano Privativo (P)"],
                        index=0,
                        key="cad_tit_plano",
                    )

                sigla_novo_plano = "P" if "Privativo" in novo_tit_plano else "C"

                # Prévia do Enquadramento em Tempo Real
                if novo_tit_nasc:
                    idade_prev = calcular_idade(novo_tit_nasc)
                    fx_prev = determinar_faixa_etaria(idade_prev)
                    if fx_prev:
                        val_prev = fx_prev["valor_privativo"] if sigla_novo_plano == "P" else fx_prev["valor_coletivo"]
                        st.markdown(f"""
                        <div style="background:#EBF8FF;border-left:4px solid #0284C7;padding:10px 14px;border-radius:6px;margin:12px 0;">
                            <strong>🔍 Enquadramento Automático em Tempo Real:</strong><br>
                            • Idade Calculada: <strong>{idade_prev} anos</strong><br>
                            • Faixa Etária: <strong>{fx_prev['faixa_etaria']}</strong><br>
                            • Mensalidade Prevista: <strong style="color:#0284C7;">{formatar_moeda(val_prev)}</strong> ({novo_tit_plano})
                        </div>
                        """, unsafe_allow_html=True)

                if st.button("Cadastrar Novo Titular", type="primary", use_container_width=True, key="btn_cad_novo_titular"):
                    if not novo_tit_nome.strip():
                        st.error("Informe o nome completo do titular.")
                    elif not novo_tit_nasc:
                        st.error("Informe a data de nascimento do titular.")
                    else:
                        sucesso_tit, msg_tit, n_id = adicionar_titular(
                            nome=novo_tit_nome,
                            data_nascimento=novo_tit_nasc,
                            cpf=novo_tit_cpf,
                            tipo_plano=sigla_novo_plano,
                        )
                        if sucesso_tit:
                            st.success(f"✅ {msg_tit}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg_tit}")

            # ── SUB-ABA 2: ADICIONAR DEPENDENTE ─────────────────────────────
            with subtab_cad_dependente:
                st.markdown("##### ➕ Inclusão de Dependente ou Agregado")
                titulares_atuais = listar_titulares()
                if not titulares_atuais:
                    st.warning("Nenhum titular cadastrado no sistema.")
                else:
                    nomes_tits = [t["titular_nome"] for t in titulares_atuais]
                    tit_selecionado = st.selectbox(
                        "Selecione o Titular Responsável *",
                        options=nomes_tits,
                        key="cad_dep_titular_sel",
                    )

                    grupo_tit = buscar_grupo_familiar(tit_selecionado)
                    plano_tit_nome = grupo_tit[0].get("tipo_plano_nome", "Coletivo") if grupo_tit else "Coletivo"
                    sigla_plano_tit = (grupo_tit[0].get("tipo_plano") or "C").upper() if grupo_tit else "C"

                    st.caption(f"Modalidade herdada do titular: **Plano {plano_tit_nome} ({sigla_plano_tit})**")

                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        dep_nome = st.text_input("Nome Completo do Dependente *", placeholder="Ex: Maria da Silva", key="cad_dep_nome")
                        dep_parentesco = st.selectbox(
                            "Grau de Parentesco *",
                            ["Cônjuge", "Filho(a)", "Pai/Mãe", "Sogro(a)", "Agregado(a)", "Outro"],
                            key="cad_dep_parentesco",
                        )

                    with col_d2:
                        dep_nasc = st.date_input(
                            "Data de Nascimento *",
                            value=None,
                            min_value=date(1910, 1, 1),
                            max_value=date.today(),
                            format="DD/MM/YYYY",
                            key="cad_dep_nasc",
                        )
                        dep_cpf = st.text_input("CPF do Dependente", placeholder="000.000.000-00", max_chars=14, key="cad_dep_cpf")

                    # Prévia do Enquadramento
                    if dep_nasc:
                        idade_dep_prev = calcular_idade(dep_nasc)
                        fx_dep_prev = determinar_faixa_etaria(idade_dep_prev)
                        if fx_dep_prev:
                            val_dep_prev = fx_dep_prev["valor_privativo"] if sigla_plano_tit == "P" else fx_dep_prev["valor_coletivo"]
                            st.markdown(f"""
                            <div style="background:#EBF8FF;border-left:4px solid #0284C7;padding:10px 14px;border-radius:6px;margin:12px 0;">
                                <strong>🔍 Enquadramento Automático em Tempo Real:</strong><br>
                                • Idade Calculada: <strong>{idade_dep_prev} anos</strong><br>
                                • Faixa Etária: <strong>{fx_dep_prev['faixa_etaria']}</strong><br>
                                • Mensalidade: <strong style="color:#0284C7;">{formatar_moeda(val_dep_prev)}</strong> (Plano {plano_tit_nome})
                            </div>
                            """, unsafe_allow_html=True)

                    if st.button("Adicionar Dependente ao Grupo", type="primary", use_container_width=True, key="btn_cad_novo_dependente"):
                        if not dep_nome.strip():
                            st.error("Informe o nome completo do dependente.")
                        elif not dep_nasc:
                            st.error("Informe a data de nascimento do dependente.")
                        else:
                            sucesso_dep, msg_dep, d_id = adicionar_dependente(
                                titular_nome=tit_selecionado,
                                nome=dep_nome,
                                grau_parentesco=dep_parentesco,
                                data_nascimento=dep_nasc,
                                cpf=dep_cpf,
                            )
                            if sucesso_dep:
                                st.success(f"✅ {msg_dep}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_dep}")

            # ── SUB-ABA 3: GERENCIAR E EXCLUIR GRUPOS E INTEGRANTES ──────────
            with subtab_gerenciar_grupos:
                st.markdown("##### 📋 Grupos Familiares e Integrantes Cadastrados")
                busca_grupo = st.text_input("🔍 Filtrar grupo por nome do titular ou dependente:", placeholder="Digite para filtrar...", key="busca_gestao_grupos")

                titulares_todos = listar_titulares()
                if not titulares_todos:
                    st.info("Nenhum titular cadastrado.")
                else:
                    for idx_tit, t_info in enumerate(titulares_todos):
                        t_nome = t_info["titular_nome"]
                        grupo_membros = buscar_grupo_familiar(t_nome)

                        if busca_grupo:
                            termo = busca_grupo.lower()
                            nomes_grupo = [m["beneficiario_nome"].lower() for m in grupo_membros]
                            if not any(termo in n for n in nomes_grupo) and termo not in t_nome.lower():
                                continue

                        plano_tipo = grupo_membros[0].get("tipo_plano_nome", "Coletivo") if grupo_membros else "Coletivo"
                        total_vidas = len(grupo_membros)
                        soma_mensal = sum(m.get("valor_vigente", 0.0) for m in grupo_membros)

                        with st.expander(
                            f"👤 {t_nome} — Plano {plano_tipo} ({total_vidas} vida(s) — Total: {formatar_moeda(soma_mensal)})",
                            expanded=False,
                        ):
                            col_info_g, col_del_g = st.columns([3, 1.2])
                            with col_info_g:
                                st.caption(f"Modalidade: **Plano {plano_tipo}** | Total do Grupo: **{formatar_moeda(soma_mensal)}/mês**")
                            with col_del_g:
                                with st.popover("🚨 Excluir Grupo Completo", use_container_width=True):
                                    st.error(f"Deseja realmente excluir **{t_nome}** e todos os seus {total_vidas} integrantes?")
                                    st.caption("Esta ação removerá o titular e todos os dependentes associados.")
                                    if st.button("Sim, Excluir Grupo Inteiro", type="primary", key=f"btn_del_grupo_{idx_tit}", use_container_width=True):
                                        ok_g, msg_g, tot_g = excluir_grupo_familiar(t_nome)
                                        if ok_g:
                                            st.success(f"✅ {msg_g}")
                                            st.rerun()
                                        else:
                                            st.error(f"❌ {msg_g}")

                            st.markdown("---")
                            st.markdown("**Integrantes do Grupo:**")

                            for m in grupo_membros:
                                c_m1, c_m2, c_m3, c_m4, c_m5 = st.columns([3, 1.5, 2, 1.8, 1.2])
                                is_tit = m["tipo"].upper() == "TITULAR"
                                with c_m1:
                                    tag_papel = "👑 **Titular**" if is_tit else f"👤 {m['grau_parentesco']}"
                                    st.markdown(f"**{m['beneficiario_nome']}**<br><small>{tag_papel}</small>", unsafe_allow_html=True)
                                with c_m2:
                                    st.markdown(f"{m.get('idade_atual', '-')} anos")
                                with c_m3:
                                    st.markdown(f"{m.get('faixa_calculada', '-')}")
                                with c_m4:
                                    st.markdown(f"**{formatar_moeda(m.get('valor_vigente', 0.0))}**")
                                with c_m5:
                                    if not is_tit:
                                        with st.popover("🗑️ Excluir", use_container_width=True):
                                            st.warning(f"Remover {m['beneficiario_nome']}?")
                                            if st.button("Confirmar", key=f"del_dep_{m['id']}", type="primary", use_container_width=True):
                                                ok_d, msg_d = excluir_membro(m["id"])
                                                if ok_d:
                                                    st.toast(f"✅ {msg_d}")
                                                    st.rerun()
                                                else:
                                                    st.error(msg_d)
                                    else:
                                        st.caption("(Titular)")
                                st.markdown("<div style='border-bottom: 1px dashed #eee; margin: 4px 0;'></div>", unsafe_allow_html=True)

        # ── ABA: PLANO ODONTOLÓGICO (UNIODONTO) ──────────────────────────────
        with tab_uniodonto:
            st.markdown("#### 🦷 Gestão do Plano Odontológico (Uniodonto Campinas)")
            st.caption(
                "Gerencie os titulares que possuem plano odontológico e o valor mensal por vida. "
                "O plano não possui escalonamento por faixa etária e **não consta** nas declarações de saúde da UNIMED."
            )

            cfg_uniodonto = obter_config_uniodonto()
            valor_vida_atual = cfg_uniodonto["valor_por_vida"]
            lista_uniodonto = listar_todos_uniodonto()

            total_titulares_u = len(lista_uniodonto)
            total_vidas_u = sum(item["vidas"] for item in lista_uniodonto)
            total_mensal_u = sum(item["valor_total"] for item in lista_uniodonto)

            col_mu1, col_mu2, col_mu3, col_mu4 = st.columns(4)
            col_mu1.metric("👥 Titulares no Plano", total_titulares_u)
            col_mu2.metric("🦷 Total de Vidas Cobertas", total_vidas_u)
            col_mu3.metric("💵 Valor Vigente por Vida", formatar_moeda(valor_vida_atual))
            col_mu4.metric("💰 Faturamento Mensal", formatar_moeda(total_mensal_u))

            st.divider()

            # BLOCO 1: ALTERAÇÃO DE PREÇO POR VIDA
            st.markdown("##### 💵 Configuração de Preço por Vida")
            st.caption("Altere o valor digitando o novo valor ou informando uma porcentagem de correção. O novo valor é mantido no sistema até nova correção.")
            data_att_u = cfg_uniodonto.get("data_atualizacao", "")
            if data_att_u:
                try:
                    dt_u_obj = datetime.fromisoformat(data_att_u.replace("Z", ""))
                    data_u_fmt = dt_u_obj.strftime("%d/%m/%Y às %H:%M")
                except Exception:
                    data_u_fmt = data_att_u[:16]
                st.caption(f"🕒 **Última atualização registrada:** `{data_u_fmt}` — 🛡️ *Persistência ativa em `data/config_precos.json`*")
            else:
                st.caption("🛡️ *Persistência permanente ativa: qualquer reajuste é gravado imediatamente no banco e no arquivo permanente (`data/config_precos.json`).*")

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                with st.form("form_alterar_preco_uniodonto"):
                    st.markdown("**1. Digitar Novo Valor Unitário (R$)**")
                    novo_preco_u = st.number_input(
                        "Novo valor por vida (R$):",
                        value=float(valor_vida_atual),
                        min_value=0.01,
                        step=1.00,
                        format="%.2f",
                        key="input_novo_preco_uniodonto",
                    )
                    btn_salvar_preco = st.form_submit_button("💾 Salvar Novo Preço por Vida", type="primary", use_container_width=True)
                    if btn_salvar_preco:
                        atualizar_valor_uniodonto(novo_preco_u)
                        st.success(f"✅ Valor por vida da Uniodonto atualizado para {formatar_moeda(novo_preco_u)}!")
                        st.rerun()

            with col_p2:
                with st.form("form_reajuste_perc_uniodonto"):
                    st.markdown("**2. Reajuste por Porcentagem (%)**")
                    perc_u = st.number_input(
                        "Porcentagem de correção (%):",
                        value=0.0,
                        step=0.5,
                        format="%.2f",
                        help="Ex: 10.00 para reajuste de 10%, ou -5.00 para redução de 5%",
                        key="input_perc_uniodonto",
                    )
                    btn_reajuste_perc = st.form_submit_button("📈 Aplicar Correção Percentual", use_container_width=True)
                    if btn_reajuste_perc:
                        if perc_u != 0.0:
                            novo_val = reajustar_valor_uniodonto_percentual(perc_u)
                            st.success(f"✅ Reajuste de {perc_u:+.2f}% aplicado! Novo valor por vida: {formatar_moeda(novo_val)}.")
                            st.rerun()
                        else:
                            st.info("Informe um percentual diferente de 0%.")

            st.divider()

            # BLOCO 2: INCLUIR OU ATUALIZAR TITULAR
            st.markdown("##### ➕ Incluir ou Atualizar Titular no Uniodonto")
            st.caption("Selecione o titular e indique a quantidade total de vidas cobertas no plano odontológico.")

            titulares_cadastrados = [t["titular_nome"] for t in listar_titulares()]
            titulares_cadastrados = sorted(list(set(titulares_cadastrados)))

            with st.form("form_vincular_uniodonto"):
                col_v1, col_v2, col_v3 = st.columns([2.5, 1, 1.5])
                with col_v1:
                    titular_u_sel = st.selectbox(
                        "Titular do Grupo Familiar:",
                        options=titulares_cadastrados,
                        index=None,
                        placeholder="Selecione o titular...",
                    )
                with col_v2:
                    vidas_u_input = st.number_input(
                        "Total de Vidas:",
                        min_value=1,
                        max_value=30,
                        value=1,
                        step=1,
                    )
                with col_v3:
                    valor_prev = vidas_u_input * valor_vida_atual
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    st.markdown(f"**Total Mensal:** `{formatar_moeda(valor_prev)}`")

                btn_vincular = st.form_submit_button("💾 Salvar Vínculo no Uniodonto", type="primary", use_container_width=True)
                if btn_vincular:
                    if not titular_u_sel:
                        st.error("Selecione um titular.")
                    else:
                        sucesso_u, msg_u = salvar_uniodonto_titular(titular_u_sel, int(vidas_u_input))
                        if sucesso_u:
                            st.success(msg_u)
                            st.rerun()
                        else:
                            st.error(msg_u)

            st.divider()

            # BLOCO 3: LISTA DE TITULARES VINCULADOS
            st.markdown(f"##### 📋 Titulares com Plano Uniodonto Ativo ({len(lista_uniodonto)})")

            if not lista_uniodonto:
                st.info("Nenhum titular cadastrado no plano Uniodonto até o momento.")
            else:
                for item_u in lista_uniodonto:
                    with st.container():
                        col_u_nome, col_u_vidas, col_u_total, col_u_acoes = st.columns([3, 1.2, 1.5, 1.2])
                        with col_u_nome:
                            st.markdown(f"**{item_u['titular_nome']}**")
                            st.caption(f"Atualizado em: {item_u['data_atualizacao'][:10] if item_u.get('data_atualizacao') else 'N/A'}")
                        with col_u_vidas:
                            st.markdown(f"🦷 **{item_u['vidas']} vida(s)**")
                            st.caption(f"{formatar_moeda(item_u['valor_por_vida'])}/vida")
                        with col_u_total:
                            st.markdown(f"**{formatar_moeda(item_u['valor_total'])}** /mês")
                        with col_u_acoes:
                            with st.popover("🗑️ Excluir"):
                                st.write(f"Remover **{item_u['titular_nome']}** do Uniodonto?")
                                if st.button("Confirmar Exclusão", key=f"del_u_{item_u['id']}", type="primary", use_container_width=True):
                                    sucesso_del, msg_del = remover_uniodonto_titular(item_u["titular_nome"])
                                    if sucesso_del:
                                        st.success(msg_del)
                                        st.rerun()
                                    else:
                                        st.error(msg_del)
                        st.markdown("<div style='border-bottom: 1px dashed #E2E8F0; margin: 4px 0 8px 0;'></div>", unsafe_allow_html=True)


        # ── ABA 5: HISTÓRICO GERAL ──────────────────────────────────────────
        with tab_relatorio:
            st.markdown("#### 📊 Histórico Geral de Declarações")

            todas = listar_todas_solicitacoes()

            if not todas:
                st.info("Nenhuma solicitação registrada no sistema.")
            else:
                # ── Seletor de ano e métricas do ano selecionado ──────────
                anos_disponiveis = obter_anos_disponiveis()
                ano_corrente = datetime.now().year
                if not anos_disponiveis:
                    anos_disponiveis = [ano_corrente]

                col_ano_sel, col_ano_info = st.columns([1, 3])
                with col_ano_sel:
                    ano_selecionado = st.selectbox(
                        "📆 Ano de referência:",
                        options=anos_disponiveis,
                        index=0,
                        key="sel_ano_historico",
                    )
                with col_ano_info:
                    st.caption(
                        f"Exibindo dados de **{ano_selecionado}**. "
                        f"Dados armazenados por 5 anos (desde {ano_corrente - 5})."
                    )

                # Métricas resumo do ano selecionado
                metricas_ano = contar_solicitacoes_por_status_ano(ano_selecionado)
                total_ano = sum(metricas_ano.values())

                col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns(5)
                col_h1.metric("⏳ Pendentes", metricas_ano.get("PENDENTE", 0))
                col_h2.metric("✅ Aprovadas", metricas_ano.get("APROVADO", 0))
                col_h3.metric("❌ Recusadas", metricas_ano.get("REJEITADO", 0))
                col_h4.metric("🚫 Canceladas", metricas_ano.get("CANCELADO", 0))
                col_h5.metric(f"📊 Total {ano_selecionado}", total_ano)

                st.divider()

                # Filtros adicionais (status e titular)
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    filtro_status = st.multiselect(
                        "Filtrar por status:",
                        ["PENDENTE", "APROVADO", "CANCELADO", "REJEITADO"],
                        default=["PENDENTE", "APROVADO", "CANCELADO", "REJEITADO"],
                    )
                with col_f2:
                    filtro_titular = st.text_input(
                        "Filtrar por titular:",
                        placeholder="Nome do titular...",
                        key="filtro_titular_hist",
                    )

                dados_filtrados = [
                    s for s in todas
                    if s["status"] in filtro_status
                    and s.get("ano_referencia") == ano_selecionado
                    and (not filtro_titular or filtro_titular.lower() in s["titular_nome"].lower())
                ]

                if dados_filtrados:
                    # Monta DataFrame para exibição
                    df_data = []
                    for s in dados_filtrados:
                        df_data.append({
                            "ID": s["id"],
                            "Titular": s["titular_nome"],
                            "CPF": formatar_cpf(s["titular_cpf"]),
                            "Mês/Ano": f"{mes_por_extenso(s['mes_referencia']).capitalize()}/{s['ano_referencia']}",
                            "Valor Total": formatar_moeda(s["valor_total"]),
                            "Status": s["status"],
                            "Data Solicitação": s["data_solicitacao"][:10] if s["data_solicitacao"] else "",
                            "Data Análise": s["data_analise"][:10] if s.get("data_analise") else "",
                            "Código": s.get("codigo_validacao", ""),
                        })

                    df = pd.DataFrame(df_data)
                    st.dataframe(df, use_container_width=True, hide_index=True)

                    # Exportação
                    st.markdown("---")
                    col_exp1, col_exp2 = st.columns(2)
                    with col_exp1:
                        csv_data = df.to_csv(index=False).encode("utf-8-sig")
                        st.download_button(
                            "📥 Exportar CSV",
                            data=csv_data,
                            file_name=f"relatorio_ansef_{ano_selecionado}.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="btn_export_csv",
                        )
                    with col_exp2:
                        try:
                            buffer = io.BytesIO()
                            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                                df.to_excel(writer, index=False, sheet_name=f"Declarações {ano_selecionado}")
                            st.download_button(
                                "📥 Exportar Excel",
                                data=buffer.getvalue(),
                                file_name=f"relatorio_ansef_{ano_selecionado}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key="btn_export_excel",
                            )
                        except Exception as e:
                            st.caption("Exportação para Excel requer openpyxl (disponível no Streamlit Cloud). Utilize o botão de CSV ao lado.")
                else:
                    st.info(f"Nenhuma solicitação encontrada para {ano_selecionado} com os filtros aplicados.")

            # ── GESTÃO DE BACKUP & PERSISTÊNCIA ──────────────────────────────
            st.markdown("---")
            with st.expander("💾 Gestão de Backup & Persistência do Histórico", expanded=False):
                st.markdown("##### 🛡️ Salvaguarda Permanente de Dados")
                st.caption(
                    "O sistema mantém todas as solicitações e aprovações sincronizadas com o arquivo "
                    "`data/solicitacoes_backup.json` e o banco `data/ansef_database.db`. "
                    "Baixe cópias de segurança periódicas ou restaure dados a qualquer momento."
                )

                col_bk1, col_bk2, col_bk3 = st.columns(3)
                with col_bk1:
                    backup_json_str = exportar_backup_json()
                    st.download_button(
                        label="📥 Baixar Solicitações (JSON)",
                        data=backup_json_str.encode("utf-8"),
                        file_name=f"backup_ansef_solicitacoes_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json",
                        use_container_width=True,
                        key="btn_dl_backup_json",
                    )

                with col_bk2:
                    backup_precos_str = exportar_backup_precos_json()
                    st.download_button(
                        label="📥 Baixar Preços & Config (JSON)",
                        data=backup_precos_str.encode("utf-8"),
                        file_name=f"backup_ansef_precos_config_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json",
                        use_container_width=True,
                        key="btn_dl_backup_precos_json",
                    )

                with col_bk3:
                    if os.path.exists(DB_PATH):
                        with open(DB_PATH, "rb") as f_db:
                            db_bytes = f_db.read()
                        st.download_button(
                            label="📥 Baixar Banco (.db)",
                            data=db_bytes,
                            file_name=f"ansef_database_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                            mime="application/x-sqlite3",
                            use_container_width=True,
                            key="btn_dl_backup_db",
                        )

                st.markdown("---")
                col_up1, col_up2 = st.columns(2)
                with col_up1:
                    st.markdown("##### 📤 Restaurar Solicitações")
                    arquivo_upload = st.file_uploader(
                        "Envie um arquivo JSON de solicitações:",
                        type=["json"],
                        key="uploader_backup_json",
                    )
                    if arquivo_upload is not None:
                        if st.button("Confirmar Restauração de Declarações", type="primary", key="btn_confirm_restore"):
                            conteudo = arquivo_upload.read().decode("utf-8")
                            sucesso_res, msg_res, qtd = importar_backup_json(conteudo)
                            if sucesso_res:
                                st.success(f"✅ {msg_res}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_res}")

                with col_up2:
                    st.markdown("##### 📤 Restaurar Preços & Configurações")
                    arquivo_upload_precos = st.file_uploader(
                        "Envie um arquivo JSON de preços e faixas:",
                        type=["json"],
                        key="uploader_backup_precos_json",
                    )
                    if arquivo_upload_precos is not None:
                        if st.button("Confirmar Restauração de Preços", type="primary", key="btn_confirm_restore_precos"):
                            conteudo_p = arquivo_upload_precos.read().decode("utf-8")
                            sucesso_resp, msg_resp = importar_backup_precos_json(conteudo_p)
                            if sucesso_resp:
                                st.success(f"✅ {msg_resp}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg_resp}")

        # ── ABA 4: CONFIGURAÇÃO DE E-MAIL ──────────────────────────────────
        with tab_config_email:
            st.markdown("#### ⚙️ Notificações Automáticas por E-mail (Gmail)")
            st.caption("O sistema envia notificações para o administrador sempre que um associado submete uma nova solicitação.")

            status_smtp = verificar_status_smtp()

            if status_smtp["configurado"]:
                st.success("✅ **Credenciais SMTP configuradas no sistema!**")
            else:
                st.warning("⚠️ **Credenciais SMTP não configuradas ou incompletas no Streamlit Secrets.**")

            col_inf1, col_inf2 = st.columns(2)
            with col_inf1:
                st.markdown(f"**Servidor SMTP:** `{status_smtp['server']}:{status_smtp['port']}`")
                st.markdown(f"**E-mail Remetente (`SMTP_USER`):** `{status_smtp['user']}`")
            with col_inf2:
                pass_display = f"•••••••••••••••• ({status_smtp['password_len']} caracteres)" if status_smtp["has_password"] else "❌ Não configurada"
                st.markdown(f"**Senha de Aplicativo (`SMTP_PASSWORD`):** {pass_display}")
                st.markdown(f"**Destinatário das Notificações:** `{status_smtp['admin_email']}`")

            st.markdown("---")
            st.markdown("##### 🧪 Testar Conexão e Disparo de E-mail")
            st.caption("Envie um e-mail de teste real para o seu endereço para verificar se as credenciais estão válidas e se a entrega está funcionando.")

            if st.button("📨 Enviar E-mail de Teste Agora", type="primary", key="btn_teste_email"):
                with st.spinner("Conectando ao servidor SMTP do Google e enviando teste..."):
                    sucesso_t, msg_t = enviar_email_teste()
                    if sucesso_t:
                        st.success(
                            f"🎉 **E-mail de teste enviado com sucesso para {status_smtp['admin_email']}!**\n\n"
                            "Por favor, verifique a sua **Caixa de Entrada** e também a pasta de **Spam / Lixo Eletrônico** do Gmail."
                        )
                    else:
                        st.error(f"❌ **Falha ao enviar e-mail de teste:**\n\n{msg_t}")

            st.markdown("---")
            with st.expander("📖 Passo a Passo: Como gerar a Senha de Aplicativo do Gmail"):
                st.markdown("""
                Para que o Gmail autorize o envio automático pelo Streamlit Cloud, o Google **não aceita** a sua senha comum de login. É necessário gerar uma **Senha de App**:

                1. Acesse: **[myaccount.google.com/security](https://myaccount.google.com/security)**.
                2. Certifique-se de que a **Verificação em duas etapas** está **ATIVADA**.
                3. Acesse diretamente: **[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)**.
                4. Em *Nome do app*, digite `ANSEF` e clique em **Criar**.
                5. O Google exibirá um código de **16 letras** (exemplo: `abcd efgh ijkl mnop`).
                6. Copie esse código de 16 letras.
                7. No **Streamlit Cloud** ([share.streamlit.io](https://share.streamlit.io)):
                   - Abra o seu app e clique no botão **Manage app** (canto inferior direito).
                   - Clique nos três pontinhos **⋮** > **Settings** > **Secrets**.
                   - Cole o seguinte bloco com o seu e-mail e a senha de 16 letras:
                   ```toml
                   ADMIN_PASSWORD = "mbj172007"
                   SMTP_SERVER = "smtp.gmail.com"
                   SMTP_PORT = 587
                   SMTP_USER = "juliani.mmj@gmail.com"
                   SMTP_PASSWORD = "sua_senha_de_16_letras_aqui"
                   ADMIN_EMAIL = "juliani.mmj@gmail.com"
                   ```
                   - Clique em **Save**. A aplicação recarregará instantaneamente já com o envio de e-mails habilitado!
                """)
