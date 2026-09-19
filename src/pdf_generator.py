"""
Motor de geração de PDF para declarações de pagamento da ANSEF/CAS.
Renderiza o template HTML com Jinja2 e converte para PDF usando xhtml2pdf.
Compatível com Streamlit Cloud e ambiente local Windows.
"""
from __future__ import annotations

import os
import io
import base64
import json
import logging
from datetime import date, datetime

from jinja2 import Template

try:
    from src.utils import (
        formatar_cpf,
        formatar_moeda,
        mes_por_extenso,
        data_por_extenso,
        valor_por_extenso,
    )
except ImportError:
    from utils import (
        formatar_cpf,
        formatar_moeda,
        mes_por_extenso,
        data_por_extenso,
        valor_por_extenso,
    )

logger = logging.getLogger(__name__)

# Caminhos dos assets e templates
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "declaracao_template.html")
LOGO_PATH = os.path.join(BASE_DIR, "assets", "logo_ansef.png")
ASSINATURA_PATH = os.path.join(BASE_DIR, "assets", "assinatura.png")


def _img_to_data_uri(filepath: str) -> str:
    """Converte imagem local para data URI base64 para embutir no HTML."""
    if not os.path.exists(filepath):
        logger.warning(f"Imagem não encontrada: {filepath}")
        return ""
    with open(filepath, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(filepath)[1].lower().replace(".", "")
    mime = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "gif") else "image/png"
    return f"data:{mime};base64,{data}"


def _carregar_template() -> str:
    """Carrega o template HTML da declaração."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def gerar_pdf_declaracao(
    titular_nome: str,
    titular_cpf: str,
    dependentes_json: str,
    mes_referencia: int,
    ano_referencia: int,
    data_pagamento: str,
    valor_total: float,
    codigo_validacao: str,
) -> bytes:
    """
    Gera o PDF da declaração de pagamento com todos os dados aprovados.
    Retorna os bytes do PDF gerado.
    """
    # Parse dos dependentes
    try:
        dependentes = json.loads(dependentes_json) if dependentes_json else []
    except (json.JSONDecodeError, TypeError):
        dependentes = []

    # Verifica se o titular foi selecionado (presente no JSON de selecionados)
    titular_selecionado = any(
        d.get("nome", "").upper() == titular_nome.upper() for d in dependentes
    )

    # Separa dependentes (exclui o titular da lista de dependentes para o texto de introdução)
    deps_lista = [d for d in dependentes if d.get("nome", "").upper() != titular_nome.upper()]

    # Todos os beneficiários para a tabela — apenas os efetivamente selecionados
    todos = []

    if titular_selecionado:
        # Titular foi selecionado: incluí-lo na tabela
        titular_valor = 0.0
        for d in dependentes:
            if d.get("nome", "").upper() == titular_nome.upper():
                titular_valor = d.get("valor", 0.0)
                break
        todos.append({
            "nome": titular_nome.upper(),
            "parentesco": "Titular",
            "valor_formatado": formatar_moeda(titular_valor),
        })

    for d in deps_lista:
        todos.append({
            "nome": d.get("nome", "").upper(),
            "parentesco": d.get("parentesco", ""),
            "valor_formatado": formatar_moeda(d.get("valor", 0.0)),
        })

    # Data de pagamento formatada
    try:
        dt_pag = datetime.strptime(data_pagamento, "%d/%m/%Y").date()
    except ValueError:
        try:
            dt_pag = datetime.strptime(data_pagamento, "%Y-%m-%d").date()
        except ValueError:
            dt_pag = date.today()

    data_emissao = date.today()

    # Contexto do template Jinja2
    context = {
        "logo_path": _img_to_data_uri(LOGO_PATH),
        "assinatura_path": _img_to_data_uri(ASSINATURA_PATH),
        "titular_nome": titular_nome.upper(),
        "titular_cpf": formatar_cpf(titular_cpf),
        "dependentes": deps_lista,
        "todos_beneficiarios": todos,
        "mes_referencia_extenso": mes_por_extenso(mes_referencia),
        "data_pagamento_extenso": data_por_extenso(dt_pag),
        "valor_total_formatado": formatar_moeda(valor_total),
        "valor_por_extenso": valor_por_extenso(valor_total),
        "data_emissao_extenso": data_por_extenso(data_emissao),
        "codigo_validacao": codigo_validacao,
    }

    # Renderiza o template
    template_html = _carregar_template()
    template = Template(template_html)
    html_renderizado = template.render(**context)

    # Converte HTML para PDF com xhtml2pdf
    pdf_bytes = _html_to_pdf(html_renderizado)
    return pdf_bytes


def _html_to_pdf(html: str) -> bytes:
    """Converte HTML renderizado para bytes PDF usando xhtml2pdf."""
    try:
        from xhtml2pdf import pisa

        buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(
            io.StringIO(html),
            dest=buffer,
            encoding="utf-8",
        )
        if pisa_status.err:
            logger.error(f"xhtml2pdf retornou erros: {pisa_status.err}")
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    except ImportError:
        logger.error("xhtml2pdf não instalado. Tentando reportlab como fallback.")
        return _fallback_reportlab_pdf(html)


def _fallback_reportlab_pdf(html: str) -> bytes:
    """Fallback minimalista com reportlab caso xhtml2pdf não esteja disponível."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("DECLARAÇÃO DE PAGAMENTO - ANSEF/CAS", styles["Title"]),
            Spacer(1, 20),
            Paragraph(
                "Este PDF foi gerado em modo de compatibilidade. "
                "Instale xhtml2pdf para o layout completo.",
                styles["Normal"],
            ),
        ]
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
    except Exception as e:
        logger.error(f"Fallback reportlab também falhou: {e}")
        return b""
