"""
Serviço de notificação por e-mail via SMTP (Gmail).
Dispara notificação ao administrador quando uma nova solicitação é submetida.
Tratamento resiliente: não interrompe a aplicação em caso de falha.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import streamlit as st

from src.utils import formatar_cpf, formatar_moeda, mes_por_extenso

logger = logging.getLogger(__name__)


def _obter_config_smtp() -> dict | None:
    """Obtém configuração SMTP dos secrets do Streamlit."""
    try:
        return {
            "server": st.secrets.get("SMTP_SERVER", "smtp.gmail.com"),
            "port": int(st.secrets.get("SMTP_PORT", 587)),
            "user": st.secrets.get("SMTP_USER", ""),
            "password": st.secrets.get("SMTP_PASSWORD", ""),
            "admin_email": st.secrets.get("ADMIN_EMAIL", "juliani.mmj@gmail.com"),
        }
    except Exception as e:
        logger.warning(f"Configuração SMTP não disponível: {e}")
        return None


def notificar_administrador_nova_solicitacao(
    titular_nome: str,
    titular_cpf: str,
    mes_referencia: int,
    ano_referencia: int,
    dependentes: list[dict],
    valor_total: float,
    data_pagamento: str,
) -> bool:
    """
    Envia e-mail HTML ao administrador notificando nova solicitação.
    Retorna True se enviado com sucesso, False caso contrário (sem quebrar a app).
    """
    config = _obter_config_smtp()
    if not config or not config["user"] or not config["password"]:
        logger.warning(
            "Credenciais SMTP não configuradas. "
            "A notificação por e-mail foi ignorada. "
            "Configure SMTP_USER e SMTP_PASSWORD no secrets.toml."
        )
        return False

    try:
        # Monta lista de dependentes para o corpo do e-mail
        deps_html = ""
        if dependentes:
            deps_rows = ""
            for d in dependentes:
                deps_rows += f"""
                <tr>
                    <td style="padding:6px 12px;border:1px solid #ddd;">{d.get('nome', '')}</td>
                    <td style="padding:6px 12px;border:1px solid #ddd;">{d.get('parentesco', '')}</td>
                    <td style="padding:6px 12px;border:1px solid #ddd;text-align:right;">
                        {formatar_moeda(d.get('valor', 0))}
                    </td>
                </tr>"""
            deps_html = f"""
            <h3 style="color:#1B3A6B;">Beneficiários incluídos:</h3>
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
                <p>Uma nova solicitação de declaração de pagamento foi submetida
                   e aguarda sua aprovação.</p>

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
                        <td style="padding:6px 0;color:#1B3A6B;font-weight:bold;">
                            {formatar_moeda(valor_total)}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;font-weight:bold;">Data/Hora da Solicitação:</td>
                        <td style="padding:6px 0;">{agora}</td>
                    </tr>
                </table>

                {deps_html}

                <div style="margin-top:25px;padding:15px;background:#e8f0fe;border-radius:8px;">
                    <p style="margin:0;">
                        <strong>🔒 Acesse a Área Restrita</strong> do sistema para
                        revisar e aprovar esta solicitação.
                    </p>
                </div>
            </div>
            <div style="background:#eee;padding:10px;text-align:center;font-size:12px;color:#888;">
                ANSEF/CAS - Associação dos Servidores da Polícia Federal em Campinas/SP<br>
                Este é um e-mail automático do sistema de declarações.
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"[ANSEF/CAS] Nova Solicitação de Declaração de Pagamento - {titular_nome}"
        )
        msg["From"] = config["user"]
        msg["To"] = config["admin_email"]
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        with smtplib.SMTP(config["server"], config["port"], timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["user"], config["password"])
            server.send_message(msg)

        logger.info(f"E-mail de notificação enviado para {config['admin_email']}")
        return True

    except Exception as e:
        logger.error(f"Falha ao enviar e-mail de notificação: {e}")
        return False
