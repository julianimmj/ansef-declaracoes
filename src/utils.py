"""
Utilitários de formatação: CPF, moeda BRL, datas por extenso, valor por extenso.
"""
import re
from datetime import date, datetime

# Meses por extenso em português
MESES_EXTENSO = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

MESES_OPCOES = {v.capitalize(): k for k, v in MESES_EXTENSO.items()}


def formatar_cpf(cpf: str) -> str:
    """Formata CPF para o padrão 000.000.000-00."""
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return cpf
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def validar_cpf(cpf: str) -> bool:
    """Valida se o CPF possui 11 dígitos numéricos."""
    digits = re.sub(r"\D", "", cpf)
    return len(digits) == 11


def limpar_cpf(cpf: str) -> str:
    """Remove formatação do CPF, retornando apenas dígitos."""
    return re.sub(r"\D", "", cpf)


def formatar_moeda(valor: float) -> str:
    """Formata valor para R$ 1.234,56."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_data_nascimento(data_str: str) -> date | None:
    """Converte string de data DD/MM/AAAA ou YYYY-MM-DD para date."""
    if not data_str:
        return None
    data_str = str(data_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            continue
    return None


def data_por_extenso(dt: date) -> str:
    """Retorna data no formato '11 de abril de 2017'."""
    mes = MESES_EXTENSO.get(dt.month, str(dt.month))
    return f"{dt.day} de {mes} de {dt.year}"


def mes_por_extenso(mes: int) -> str:
    """Retorna nome do mês por extenso."""
    return MESES_EXTENSO.get(mes, str(mes))


def valor_por_extenso(valor: float) -> str:
    """
    Converte valor numérico em BRL por extenso.
    Exemplo: 3134.00 → 'três mil cento e trinta e quatro reais'
    """
    try:
        from num2words import num2words
        reais = int(valor)
        centavos = round((valor - reais) * 100)
        partes = []
        if reais > 0:
            txt_reais = num2words(reais, lang='pt_BR')
            partes.append(f"{txt_reais} {'real' if reais == 1 else 'reais'}")
        if centavos > 0:
            txt_centavos = num2words(centavos, lang='pt_BR')
            partes.append(f"{txt_centavos} {'centavo' if centavos == 1 else 'centavos'}")
        if not partes:
            return "zero reais"
        return " e ".join(partes)
    except ImportError:
        return formatar_moeda(valor)


def gerar_codigo_validacao(solicitacao_id: int, ano: int) -> str:
    """Gera código alfanumérico de autenticidade para a declaração."""
    import hashlib
    seed = f"ANSEF-{solicitacao_id}-{ano}-SALT2026"
    h = hashlib.sha256(seed.encode()).hexdigest()[:8].upper()
    return f"ANSEF-{ano}-{h}"
