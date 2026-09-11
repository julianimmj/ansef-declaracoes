"""
Serviço de notificação por e-mail via SMTP (Gmail).
Dispara notificação ao administrador quando uma nova solicitação é submetida.
Tratamento resiliente: não interrompe a aplicação em caso de falha.
Inclui ferramentas de diagnóstico e teste para o painel administrativo.
"""
from __future__ import annotations

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import streamlit as st

try:
    from src.utils import formatar_cpf, formatar_moeda, mes_por_extenso
except ImportError:
    from utils import formatar_cpf, formatar_moeda, mes_por_extenso

logger = logging.getLogger(__name__)


def obter_config_smtp() -> dict:
    """
    Obtém configuração SMTP de st.secrets ou variáveis de ambiente de forma segura.
    Retorna dicionário padronizado com os valores higienizados.
    """
    server = "smtp.gmail.com"
    port = 587
    user = ""
    password = ""
    admin_email = "juliani.mmj@gmail.com"

    # Tenta ler do st.secrets
    try:
        if hasattr(st, "secrets"):
            server = st.secrets.get("SMTP_SERVER", server)
            port = int(st.secrets.get("SMTP_PORT", port))
            user = st.secrets.get("SMTP_USER", user)
            password = st.secrets.get("SMTP_PASSWORD", password)
            admin_email = st.secrets.get("ADMIN_EMAIL", admin_email)
    except Exception as e:
        logger.debug(f"st.secrets não disponível ou incompleto: {e}")

    # Fallback para variáveis de ambiente
    if not user:
        user = os.environ.get("SMTP_USER", "")
    if not password:
        password = os.environ.get("SMTP_PASSWORD", "")
    if not admin_email or admin_email == "juliani.mmj@gmail.com":
        admin_email = os.environ.get("ADMIN_EMAIL", admin_email)

    # Limpa a senha (Google App Passwords são geradas com espaços "abcd efgh ijkl mnop")
    password_limpa = str(password).strip().replace(" ", "") if password else ""

    return {
        "server": str(server).strip(),
        "port": int(port),
        "user": str(user).strip(),
        "password": password_limpa,
        "admin_email": str(admin_email).strip(),
    }


def verificar_status_smtp() -> dict:
    """Retorna diagnóstico amigável do status de configuração do SMTP."""
    cfg = obter_config_smtp()
    user_ok = bool(cfg["user"] and "@" in cfg["user"])
    pass_ok = bool(cfg["password"])
    pass_len = len(cfg["password"])

    return {
        "configurado": user_ok and pass_ok,
        "server": cfg["server"],
        "port": cfg["port"],
        "user": cfg["user"] if user_ok else "Não configurado",
        "has_password": pass_ok,
        "password_len": pass_len,
        "admin_email": cfg["admin_email"],
    }


def _conectar_e_enviar(config: dict, msg: MIMEMultipart) -> tuple[bool, str]:
    """Conecta ao servidor SMTP com suporte a portas 465 (SSL) e 587 (STARTTLS)."""
    if not config["user"]:
        return False, "E-mail de envio (SMTP_USER) não configurado no Streamlit Secrets."
    if not config["password"]:
        return False, "Senha de Aplicativo (SMTP_PASSWORD) não configurada no Streamlit Secrets."

    try:
        server_host = config["server"]
        server_port = config["port"]

        if server_port == 465:
            with smtplib.SMTP_SSL(server_host, server_port, timeout=20) as server:
                server.login(config["user"], config["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(server_host, server_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(config["user"], config["password"])
                server.send_message(msg)

        logger.info(f"E-mail enviado com sucesso para {msg['To']}")
        return True, "E-mail enviado com sucesso."

    except smtplib.SMTPAuthenticationError as e:
        erro_msg = (
            f"Erro de autenticação Google SMTP ({e.smtp_code}): "
            "Usuário ou senha rejeitados pelo Gmail.\n\n"
            "⚠️ O Google exige o uso de uma **Senha de App de 16 caracteres** "
            "(gerada em myaccount.google.com/apppasswords com a Verificação em Duas Etapas ativa), "
            "e NÃO a senha comum de login do Gmail."
        )
        logger.error(erro_msg)
        return False, erro_msg

    except Exception as e:
        erro_msg = f"Falha na conexão SMTP ({type(e).__name__}): {str(e)}"
        logger.error(erro_msg)
        return False, erro_msg


def notificar_administrador_nova_solicitacao(
    titular_nome: str,
    titular_cpf: str,
    mes_referencia: int,
    ano_referencia: int,
    dependentes: list[dict],
    valor_total: float,
    data_pagamento: str,
) -> tuple[bool, str]:
    """
    Envia e-mail HTML ao administrador notificando nova solicitação.
    Retorna (sucesso, mensagem).
    """
    config = obter_config_smtp()
    if not config["user"] or not config["password"]:
        msg_aviso = (
            "Credenciais SMTP não configuradas. "
            "Configure SMTP_USER e SMTP_PASSWORD nos Secrets do Streamlit."
        )
        logger.warning(msg_aviso)
        return False, msg_aviso

    try:
        deps_html = ""
        if dependentes:
            deps_rows = ""
            for d in dependentes:
                deps_rows += f"""
                <tr>
                    <td style="padding:8px 12px;border:1px solid #ddd;">{d.get('nome', '')}</td>
                    <td style="padding:8px 12px;border:1px solid #ddd;">{d.get('parentesco', '')}</td>
                    <td style="padding:8px 12px;border:1px solid #ddd;text-align:right;">
                        {formatar_moeda(d.get('valor', 0))}
                    </td>
                </tr>"""
            deps_html = f"""
            <h3 style="color:#1B3A6B;margin-top:20px;">👥 Beneficiários incluídos:</h3>
            <table style="border-collapse:collapse;width:100%;font-size:14px;">
                <tr style="background:#1B3A6B;color:white;">
                    <th style="padding:8px 12px;text-align:left;">Beneficiário</th>
                    <th style="padding:8px 12px;text-align:left;">Parentesco</th>
                    <th style="padding:8px 12px;text-align:right;">Valor (R$)</th>
                </tr>
                {deps_rows}
            </table>"""

        mes_ext = mes_por_extenso(mes_referencia).capitalize()
        agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

        corpo_html = f"""
        <html>
        <body style="font-family:Arial,Helvetica,sans-serif;color:#333;max-width:600px;margin:auto;">
            <div style="background:#1B3A6B;padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">
                    ANSEF/CAS - Sistema de Declarações
                </h1>
            </div>
            <div style="padding:20px;background:#f9f9f9;">
                <h2 style="color:#1B3A6B;">📋 Nova Solicitação de Declaração</h2>
                <p>Uma nova solicitação de declaração de pagamento foi submetida e aguarda sua revisão e aprovação.</p>

                <table style="width:100%;font-size:14px;margin:15px 0;">
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;width:180px;">Titular:</td>
                        <td style="padding:6px 0;">{titular_nome}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;">CPF:</td>
                        <td style="padding:6px 0;">{formatar_cpf(titular_cpf)}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;">Mês/Ano de Referência:</td>
                        <td style="padding:6px 0;">{mes_ext} de {ano_referencia}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;">Data de Pagamento:</td>
                        <td style="padding:6px 0;">{data_pagamento}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;">Valor Total Declarado:</td>
                        <td style="padding:6px 0;color:#1B3A6B;font-weight:bold;font-size:16px;">
                            {formatar_moeda(valor_total)}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;">Data/Hora do Envio:</td>
                        <td style="padding:6px 0;">{agora}</td>
                    </tr>
                </table>

                {deps_html}

                <div style="margin-top:25px;padding:15px;background:#e8f0fe;border-radius:8px;border-left:4px solid #1B3A6B;">
                    <p style="margin:0;">
                        <strong>🔒 Acesse a Área Restrita</strong> do sistema para revisar, aprovar e emitir a declaração assinada.
                    </p>
                </div>
            </div>
            <div style="background:#eee;padding:12px;text-align:center;font-size:12px;color:#777;">
                ANSEF/CAS — Associação dos Servidores da Polícia Federal em Campinas/SP<br>
                Este é um e-mail automático gerado pelo sistema.
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[ANSEF/CAS] Nova Solicitação de Declaração - {titular_nome}"
        msg["From"] = config["user"]
        msg["To"] = config["admin_email"]
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        return _conectar_e_enviar(config, msg)

    except Exception as e:
        logger.error(f"Erro inesperado ao montar e-mail: {e}")
        return False, str(e)


def enviar_email_teste() -> tuple[bool, str]:
    """
    Envia um e-mail de teste para validar o funcionamento do SMTP.
    Retorna (sucesso, mensagem).
    """
    config = obter_config_smtp()
    if not config["user"] or not config["password"]:
        return False, "Credenciais SMTP_USER ou SMTP_PASSWORD não configuradas no Streamlit Secrets."

    agora = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    corpo_html = f"""
    <html>
    <body style="font-family:Arial,Helvetica,sans-serif;color:#333;max-width:600px;margin:auto;">
        <div style="background:#1B3A6B;padding:20px;text-align:center;">
            <h1 style="color:white;margin:0;font-size:20px;">ANSEF/CAS — Teste de Notificação</h1>
        </div>
        <div style="padding:20px;background:#f9f9f9;">
            <h2 style="color:#155724;">✅ Conexão SMTP Validada com Sucesso!</h2>
            <p>Se você está lendo este e-mail, o sistema de envio automático da ANSEF/CAS está configurado e funcionando perfeitamente.</p>
            <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
            <table style="width:100%;font-size:14px;">
                <tr>
                    <td style="padding:4px 0;font-weight:bold;width:150px;">Data e Hora:</td>
                    <td style="padding:4px 0;">{agora}</td>
                </tr>
                <tr>
                    <td style="padding:4px 0;font-weight:bold;">Servidor SMTP:</td>
                    <td style="padding:4px 0;">{config['server']}:{config['port']}</td>
                </tr>
                <tr>
                    <td style="padding:4px 0;font-weight:bold;">E-mail de Envio:</td>
                    <td style="padding:4px 0;">{config['user']}</td>
                </tr>
                <tr>
                    <td style="padding:4px 0;font-weight:bold;">Destinatário:</td>
                    <td style="padding:4px 0;">{config['admin_email']}</td>
                </tr>
            </table>
        </div>
        <div style="background:#eee;padding:10px;text-align:center;font-size:12px;color:#777;">
            ANSEF/CAS — Associação dos Servidores da Polícia Federal em Campinas/SP
        </div>
    </body>
    </html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ANSEF/CAS] ✅ Teste de Notificação por E-mail ({agora})"
    msg["From"] = config["user"]
    msg["To"] = config["admin_email"]
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    return _conectar_e_enviar(config, msg)


def notificar_administrador_migracao_faixa(migracoes: list[dict]) -> tuple[bool, str]:
    """
    Envia e-mail em formato HTML ao administrador informando sobre todos os integrantes
    que mudaram de faixa etária e tiveram seus valores reajustados.
    Retorna (sucesso, mensagem).
    """
    if not migracoes:
        return True, "Nenhuma migração para notificar."

    config = obter_config_smtp()
    if not config["user"] or not config["password"]:
        msg_aviso = (
            "Credenciais SMTP não configuradas. "
            "Configure SMTP_USER e SMTP_PASSWORD nos Secrets do Streamlit."
        )
        logger.warning(msg_aviso)
        return False, msg_aviso

    try:
        agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
        total_migs = len(migracoes)

        linhas_tabela = ""
        for m in migracoes:
            parentesco = m.get("grau_parentesco", "Titular")
            val_ant = formatar_moeda(m.get("valor_faixa_anterior", 0))
            val_novo = formatar_moeda(m.get("valor_faixa_atual", 0))
            linhas_tabela += f"""
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:10px 12px;"><strong>{m.get('beneficiario_nome', '')}</strong><br>
                    <small style="color:#666;">Titular: {m.get('titular_nome', '')}</small>
                </td>
                <td style="padding:10px 12px;text-align:center;">{parentesco}</td>
                <td style="padding:10px 12px;text-align:center;font-weight:bold;color:#1B3A6B;">
                    {m.get('idade_atual', '-')} anos
                </td>
                <td style="padding:10px 12px;text-align:center;">
                    <span style="color:#777;text-decoration:line-through;">{m.get('faixa_anterior', '-')}</span><br>
                    <strong style="color:#d9534f;">➔ {m.get('faixa_calculada', '-')}</strong>
                </td>
                <td style="padding:10px 12px;text-align:center;">{m.get('tipo_plano_nome', 'Coletivo')}</td>
                <td style="padding:10px 12px;text-align:right;color:#777;">{val_ant}</td>
                <td style="padding:10px 12px;text-align:right;font-weight:bold;color:#28a745;">{val_novo}</td>
            </tr>"""

        corpo_html = f"""
        <html>
        <body style="font-family:Arial,Helvetica,sans-serif;color:#333;max-width:700px;margin:auto;">
            <div style="background:#1B3A6B;padding:20px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:20px;">
                    ANSEF/CAS — Sistema de Gestão do Plano de Saúde
                </h1>
                <p style="color:#E0E8F5;margin:6px 0 0 0;font-size:14px;">
                    Notificação de Reajuste por Mudança de Faixa Etária
                </p>
            </div>
            <div style="padding:22px;background:#f9f9f9;">
                <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:12px 16px;border-radius:4px;margin-bottom:20px;">
                    <strong style="color:#856404;font-size:15px;">
                        ⚠️ Atenção: {total_migs} integrante(s) migraram de faixa etária
                    </strong>
                    <p style="color:#856404;margin:6px 0 0 0;font-size:13px;">
                        Com base na data de nascimento cadastrada, os seguintes associados/dependentes atingiram nova faixa etária e seus valores mensais foram recalculados pela tabela oficial de preços.
                    </p>
                </div>

                <table style="width:100%;border-collapse:collapse;font-size:13px;background:white;border-radius:6px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background:#1B3A6B;color:white;text-align:left;">
                            <th style="padding:10px 12px;">Beneficiário</th>
                            <th style="padding:10px 12px;text-align:center;">Grau</th>
                            <th style="padding:10px 12px;text-align:center;">Idade</th>
                            <th style="padding:10px 12px;text-align:center;">Transição de Faixa</th>
                            <th style="padding:10px 12px;text-align:center;">Plano</th>
                            <th style="padding:10px 12px;text-align:right;">Valor Ant.</th>
                            <th style="padding:10px 12px;text-align:right;">Novo Valor</th>
                        </tr>
                    </thead>
                    <tbody>
                        {linhas_tabela}
                    </tbody>
                </table>

                <div style="margin-top:22px;padding:14px;background:#e8f0fe;border-radius:6px;border-left:4px solid #1B3A6B;font-size:13px;">
                    <p style="margin:0;">
                        📌 <strong>Painel Administrativo:</strong> Acesse a aba <em>💰 Reajuste e Tabela de Preços</em> no sistema para conferir a tabela completa de preços ou aplicar reajustes gerais.
                    </p>
                </div>

                <p style="font-size:12px;color:#888;margin-top:20px;">
                    Data do processamento: {agora}
                </p>
            </div>
            <div style="background:#eee;padding:12px;text-align:center;font-size:12px;color:#777;">
                ANSEF/CAS — Associação dos Servidores da Polícia Federal em Campinas/SP<br>
                E-mail automático gerado pelo Sistema de Declarações e Gestão de Planos.
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[ANSEF/CAS] 🔔 Reajuste: {total_migs} integrante(s) mudaram de faixa etária"
        msg["From"] = config["user"]
        msg["To"] = config["admin_email"]
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        return _conectar_e_enviar(config, msg)

    except Exception as e:
        logger.error(f"Erro ao gerar e-mail de migração de faixa: {e}")
        return False, str(e)

