"""
ANSEF/CAS — Sistema de Declarações de Pagamento
Ponto de entrada da aplicação Streamlit.
"""
import json
import os
import io
import base64
from datetime import date, datetime

import streamlit as st
import pandas as pd

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
    listar_todos_membros,
    atualizar_valor_membro,
    reajustar_valores_lote,
    contar_solicitacoes_por_status,
    contar_aprovadas_mes_atual,
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
from src.email_service import notificar_administrador_nova_solicitacao
from src.pdf_generator import gerar_pdf_declaracao
from src.utils import (
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
    initial_sidebar_state="expanded",
)

# Inicializa o banco de dados na primeira execução
inicializar_banco()

# ─── CSS CUSTOM ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 10px 0 5px 0;
    }
    .main-header h2 {
        color: #1B3A6B;
        font-size: 1.3rem;
        margin: 0;
        font-weight: 700;
    }
    .main-header h3 {
        color: #1B3A6B;
        font-size: 1.1rem;
        margin: 0;
        font-weight: 600;
    }
    .main-header p {
        color: #666;
        font-size: 0.85rem;
        margin: 2px 0 0 0;
    }
    .status-pendente {
        background: #FFF3CD;
        color: #856404;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-aprovado {
        background: #D4EDDA;
        color: #155724;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-rejeitado {
        background: #F8D7DA;
        color: #721C24;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    div[data-testid="stMetric"] {
        background: #f0f4fa;
        border-radius: 10px;
        padding: 12px 16px;
        border-left: 4px solid #1B3A6B;
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
    st.markdown("### 📋 Navegação")
    modulo = st.radio(
        "Selecione o módulo:",
        ["🏠 Área do Associado", "🔒 Área Restrita (Administração)"],
        label_visibility="collapsed",
    )


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
        st.markdown(f"### 👤 Portal do Associado: **{titular_logado}**")

        col_logout, _ = st.columns([1, 4])
        with col_logout:
            if st.button("🚪 Sair", use_container_width=True):
                logout_associado()
                st.rerun()

        tab_nova, tab_historico = st.tabs(["📝 Nova Solicitação", "📄 Histórico e Downloads"])

        # ── ABA 1: NOVA SOLICITAÇÃO ─────────────────────────────────────────
        with tab_nova:
            st.markdown("#### Nova Solicitação de Declaração de Pagamento")

            grupo = buscar_grupo_familiar(titular_logado)
            if not grupo:
                st.warning("Grupo familiar não encontrado no cadastro.")
                st.stop()

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
                col_check, col_nome, col_parent, col_valor = st.columns([0.5, 3, 2, 2])

                m_id = membro.get("id", i)
                with col_check:
                    checked = st.checkbox(
                        "Incluir",
                        value=True,
                        key=f"check_m_{m_id}_{i}",
                        label_visibility="collapsed",
                    )

                with col_nome:
                    st.markdown(f"**{membro['beneficiario_nome']}**")

                with col_parent:
                    st.caption(membro.get("grau_parentesco", ""))

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
                    )

                if checked:
                    selecionados.append({
                        "nome": membro["beneficiario_nome"],
                        "parentesco": membro.get("grau_parentesco", ""),
                        "valor": valor_edit,
                    })
                    valor_soma += valor_edit

            st.markdown("---")

            valor_total = st.number_input(
                "💰 Valor Total Declarado (R$)",
                value=float(valor_soma),
                min_value=0.0,
                step=0.01,
                format="%.2f",
                help="Calculado automaticamente pela soma dos selecionados. Ajuste manualmente se necessário.",
            )

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
                        notificar_administrador_nova_solicitacao(
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

                        if status == "APROVADO" and sol.get("pdf_gerado"):
                            st.download_button(
                                label="📥 Baixar Declaração (PDF)",
                                data=sol["pdf_gerado"],
                                file_name=f"Declaracao_ANSEF_{titular_logado}_{mes_ext}_{sol['ano_referencia']}.pdf",
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True,
                                key=f"dl_pdf_assoc_{sol['id']}",
                            )

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

        col_adm_logout, _ = st.columns([1, 4])
        with col_adm_logout:
            if st.button("🚪 Sair da Administração", use_container_width=True):
                logout_admin()
                st.rerun()

        # Métricas no topo
        metricas = contar_solicitacoes_por_status()
        aprovadas_mes = contar_aprovadas_mes_atual()

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("⏳ Pendentes", metricas.get("PENDENTE", 0))
        col_m2.metric("✅ Aprovadas (Total)", metricas.get("APROVADO", 0))
        col_m3.metric("📅 Aprovadas no Mês", aprovadas_mes)
        col_m4.metric("📊 Total Emitidas",
                       sum(metricas.values()))

        st.divider()

        tab_pend, tab_reajuste, tab_relatorio = st.tabs([
            "📋 Fila de Pendentes",
            "💰 Reajuste de Valores",
            "📊 Histórico Geral",
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

                            col_c, col_n, col_p, col_v = st.columns([0.5, 3, 2, 2])
                            with col_c:
                                inc = st.checkbox(
                                    "Incl.",
                                    value=estava_incluido,
                                    key=f"adm_inc_{sol['id']}_{j}",
                                    label_visibility="collapsed",
                                )
                            with col_n:
                                st.markdown(f"**{nome_m}**")
                            with col_p:
                                st.caption(membro.get("grau_parentesco", ""))
                            with col_v:
                                val_base = dep_original["valor"] if dep_original else (
                                    membro.get("valor_vigente") or membro.get("valor_mensalidade") or 0.0
                                )
                                val_adm = st.number_input(
                                    "R$",
                                    value=float(val_base),
                                    min_value=0.0,
                                    step=0.01,
                                    format="%.2f",
                                    key=f"adm_val_{sol['id']}_{j}",
                                    label_visibility="collapsed",
                                )

                            if inc:
                                deps_editados.append({
                                    "nome": nome_m,
                                    "parentesco": membro.get("grau_parentesco", ""),
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

        # ── ABA 2: REAJUSTE DE VALORES ──────────────────────────────────────
        with tab_reajuste:
            st.markdown("#### 💰 Tabela de Mensalidades e Reajustes")

            membros = listar_todos_membros()

            # Reajuste em lote
            st.markdown("##### Reajuste em Lote")
            col_perc, col_btn_lote = st.columns([2, 1])
            with col_perc:
                percentual = st.number_input(
                    "Percentual de Reajuste (%)",
                    value=0.0,
                    step=0.1,
                    format="%.2f",
                    help="Positivo para aumento, negativo para redução.",
                )
            with col_btn_lote:
                st.markdown("")
                st.markdown("")
                if st.button("📈 Aplicar Reajuste em Lote", use_container_width=True):
                    if percentual == 0:
                        st.warning("Informe um percentual diferente de zero.")
                    else:
                        count = reajustar_valores_lote(percentual)
                        st.success(
                            f"✅ Reajuste de {percentual:+.2f}% aplicado a "
                            f"{count} membro(s)."
                        )
                        st.rerun()

            st.markdown("---")
            st.markdown("##### Valores Individuais")
            st.caption("Pesquise e altere valores individualmente. As alterações são imediatas.")

            # Filtro de busca
            busca = st.text_input("🔍 Buscar por nome:", placeholder="Digite para filtrar...")

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
                    col_t, col_n, col_p, col_v_atual, col_v_novo, col_salvar = st.columns(
                        [2, 3, 1.5, 1.5, 1.5, 1]
                    )
                    with col_t:
                        st.caption(f"Grupo: {m['titular_nome']}")
                    with col_n:
                        st.markdown(f"**{m['beneficiario_nome']}**")
                    with col_p:
                        st.caption(m.get("grau_parentesco", ""))
                    with col_v_atual:
                        st.metric("Vigente", formatar_moeda(m.get("valor_vigente", 0)))
                    with col_v_novo:
                        novo_val = st.number_input(
                            "Novo (R$)",
                            value=float(m.get("valor_vigente", 0) or 0),
                            min_value=0.0,
                            step=0.01,
                            format="%.2f",
                            key=f"reaj_{k}",
                            label_visibility="collapsed",
                        )
                    with col_salvar:
                        st.markdown("")
                        if st.button("💾", key=f"save_reaj_{k}", help="Salvar novo valor"):
                            atualizar_valor_membro(m["beneficiario_nome"], novo_val)
                            st.toast(
                                f"Valor de {m['beneficiario_nome']} atualizado para "
                                f"{formatar_moeda(novo_val)}",
                                icon="✅",
                            )
                            st.rerun()

        # ── ABA 3: HISTÓRICO GERAL ──────────────────────────────────────────
        with tab_relatorio:
            st.markdown("#### 📊 Histórico Geral de Declarações")

            todas = listar_todas_solicitacoes()

            if not todas:
                st.info("Nenhuma solicitação registrada no sistema.")
            else:
                # Filtros
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    filtro_status = st.multiselect(
                        "Filtrar por status:",
                        ["PENDENTE", "APROVADO", "REJEITADO"],
                        default=["PENDENTE", "APROVADO", "REJEITADO"],
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
                            file_name="relatorio_ansef_declaracoes.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="btn_export_csv",
                        )
                    with col_exp2:
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                            df.to_excel(writer, index=False, sheet_name="Declarações")
                        st.download_button(
                            "📥 Exportar Excel",
                            data=buffer.getvalue(),
                            file_name="relatorio_ansef_declaracoes.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="btn_export_excel",
                        )
                else:
                    st.info("Nenhuma solicitação encontrada com os filtros aplicados.")
