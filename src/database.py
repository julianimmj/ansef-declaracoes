"""
Camada de persistência SQLite para o sistema ANSEF/CAS.
Gerencia membros, configuração de valores reajustados, solicitações de declaração
e tabela oficial de faixas etárias e preços (Privativo e Coletivo).
"""
from __future__ import annotations

import sqlite3
import json
import os
import csv
import logging
from typing import Optional, Union, List, Dict, Any
from datetime import datetime, date
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ansef_database.db")
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "integrantes.csv")

TABELA_FAIXAS_PADRAO = [
    ("0 – 18 anos", 0, 18, 350.00, 250.00, 1),
    ("19 – 23 anos", 19, 23, 412.00, 295.00, 2),
    ("24 – 28 anos", 24, 28, 475.00, 340.00, 3),
    ("29 – 33 anos", 29, 33, 515.00, 368.00, 4),
    ("34 – 38 anos", 34, 38, 544.00, 389.00, 5),
    ("39 – 43 anos", 39, 43, 627.00, 448.00, 6),
    ("44 – 48 anos", 44, 48, 857.00, 612.00, 7),
    ("49 – 53 anos", 49, 53, 1183.00, 845.00, 8),
    ("54 – 58 anos", 54, 58, 1554.00, 1110.00, 9),
    ("Acima de 59 anos", 59, 150, 2094.00, 1496.00, 10),
]


@contextmanager
def get_connection():
    """Context manager para conexões SQLite thread-safe."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar_banco():
    """Cria as tabelas, carrega os dados iniciais e atualiza mensalidades com a tabela de faixas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS membros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                titular_nome TEXT NOT NULL,
                beneficiario_nome TEXT NOT NULL,
                grau_parentesco TEXT,
                data_nascimento TEXT,
                cpf TEXT,
                faixa_etaria TEXT,
                tipo_plano TEXT,
                valor_mensalidade REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS config_valores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                beneficiario_nome TEXT UNIQUE NOT NULL,
                valor_atualizado REAL NOT NULL,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS solicitacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_validacao TEXT UNIQUE,
                titular_nome TEXT NOT NULL,
                titular_cpf TEXT NOT NULL,
                dependentes_incluidos TEXT NOT NULL DEFAULT '[]',
                mes_referencia INTEGER NOT NULL,
                ano_referencia INTEGER NOT NULL,
                data_pagamento TEXT NOT NULL,
                valor_total REAL NOT NULL,
                status TEXT DEFAULT 'PENDENTE',
                data_solicitacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_analise TIMESTAMP,
                observacoes_admin TEXT,
                pdf_gerado BLOB
            );

            CREATE TABLE IF NOT EXISTS tabela_faixas_etarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faixa_etaria TEXT NOT NULL,
                idade_min INTEGER NOT NULL,
                idade_max INTEGER NOT NULL,
                valor_privativo REAL NOT NULL,
                valor_coletivo REAL NOT NULL,
                ordem INTEGER NOT NULL
            );
        """)

        # Inicializa a tabela de faixas etárias caso vazia
        count_faixas = conn.execute("SELECT COUNT(*) FROM tabela_faixas_etarias").fetchone()[0]
        if count_faixas == 0:
            for item in TABELA_FAIXAS_PADRAO:
                conn.execute("""
                    INSERT INTO tabela_faixas_etarias
                    (faixa_etaria, idade_min, idade_max, valor_privativo, valor_coletivo, ordem)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, item)

        # Verifica se já existem membros cadastrados
        count_membros = conn.execute("SELECT COUNT(*) FROM membros").fetchone()[0]
        if count_membros == 0:
            _carregar_csv(conn)
        else:
            # Atualiza correções cadastrais conhecidas em bases existentes
            conn.execute("""
                UPDATE membros
                SET titular_nome = 'José Luis Cordeiro Marcheori'
                WHERE titular_nome = 'José Luis Cordeiro Marceori'
            """)
            conn.execute("""
                UPDATE membros
                SET beneficiario_nome = 'José Luis Cordeiro Marcheori'
                WHERE beneficiario_nome = 'José Luis Cordeiro Marceori'
            """)
            conn.execute("""
                UPDATE solicitacoes
                SET titular_nome = 'José Luis Cordeiro Marcheori'
                WHERE titular_nome = 'José Luis Cordeiro Marceori'
            """)

        # Recalcula mensalidades com base na tabela de faixas etárias e idade
        recalcular_mensalidades_membros(conn)
        _sincronizar_csv_com_banco(conn)


def _carregar_csv(conn):
    """Carrega os dados do CSV de integrantes para a tabela membros."""
    if not os.path.exists(CSV_PATH):
        return

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            classificacao = row.get("Classificacao", "").strip()
            if not classificacao:
                continue

            nome = row.get("Nome", "").strip()
            titular = row.get("Titular", "").strip()
            nascimento = row.get("Nascimento", "").strip()
            faixa = row.get("Faixa", "").strip()
            tipo_plano = row.get("Tipo_Plano", "").strip()
            grau = row.get("Grau_Parentesco", "").strip()

            try:
                valor = float(row.get("Valor_Mensalidade", "0").replace(",", "."))
            except (ValueError, TypeError):
                valor = 0.0

            # Converte data DD/MM/AAAA para YYYY-MM-DD
            data_iso = ""
            if nascimento:
                try:
                    dt = datetime.strptime(nascimento, "%d/%m/%Y")
                    data_iso = dt.strftime("%Y-%m-%d")
                except ValueError:
                    data_iso = nascimento

            conn.execute("""
                INSERT INTO membros (tipo, titular_nome, beneficiario_nome,
                    grau_parentesco, data_nascimento, faixa_etaria, tipo_plano,
                    valor_mensalidade)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                classificacao.upper(),
                titular,
                nome,
                grau,
                data_iso,
                faixa,
                tipo_plano,
                valor
            ))


def _sincronizar_csv_com_banco(conn):
    """Atualiza data/integrantes.csv com os valores e dados cadastrais vigentes no banco."""
    try:
        rows = conn.execute("""
            SELECT tipo, beneficiario_nome, titular_nome, data_nascimento,
                   faixa_etaria, tipo_plano, valor_mensalidade, grau_parentesco
            FROM membros
            ORDER BY id
        """).fetchall()

        if not rows:
            return

        with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Classificacao", "Nome", "Titular", "Nascimento",
                "Faixa", "Tipo_Plano", "Valor_Mensalidade", "Grau_Parentesco"
            ])
            for r in rows:
                dt_str = r["data_nascimento"]
                if dt_str and "-" in dt_str:
                    try:
                        dt = datetime.strptime(dt_str, "%Y-%m-%d")
                        dt_br = dt.strftime("%d/%m/%Y")
                    except Exception:
                        dt_br = dt_str
                else:
                    dt_br = dt_str or ""

                tipo_cap = r["tipo"].capitalize() if r["tipo"] else "Titular"
                writer.writerow([
                    tipo_cap,
                    r["beneficiario_nome"],
                    r["titular_nome"],
                    dt_br,
                    r["faixa_etaria"] or "",
                    r["tipo_plano"] or "C",
                    f"{r['valor_mensalidade']:.2f}",
                    r["grau_parentesco"] or ""
                ])
    except Exception as e:
        logger.error(f"Erro ao sincronizar CSV: {e}")


# ─── CÁLCULOS DE IDADE E FAIXA ETÁRIA ────────────────────────────────────────

def calcular_idade(data_nascimento: str | date | None, data_ref: date | None = None) -> int | None:
    """Calcula a idade completa em anos a partir de uma string ou objeto date."""
    if not data_nascimento:
        return None
    if isinstance(data_nascimento, str):
        try:
            data_limpa = data_nascimento.strip()
            if "/" in data_limpa:
                dt = datetime.strptime(data_limpa, "%d/%m/%Y").date()
            else:
                dt = datetime.strptime(data_limpa, "%Y-%m-%d").date()
        except Exception:
            return None
    elif isinstance(data_nascimento, date):
        dt = data_nascimento
    else:
        return None

    if data_ref is None:
        data_ref = date.today()

    return data_ref.year - dt.year - ((data_ref.month, data_ref.day) < (dt.month, dt.day))


def obter_tabela_faixas() -> list[dict]:
    """Retorna todas as faixas etárias da tabela_faixas_etarias ordenadas por ordem crescente."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tabela_faixas_etarias ORDER BY ordem ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def determinar_faixa_etaria(idade: int | None) -> dict | None:
    """Retorna a faixa etária correspondente à idade informada."""
    if idade is None:
        return None
    faixas = obter_tabela_faixas()
    for f in faixas:
        if f["idade_min"] <= idade <= f["idade_max"]:
            return f
    return None


def identificar_faixa_por_rotulo(rotulo: str) -> dict | None:
    """
    Identifica a faixa padrão correspondente a um rótulo cadastral
    (ex: '>59', '54-58', '44-48', '49 - 53', '0-18').
    """
    if not rotulo:
        return None
    rot = rotulo.strip().replace(" ", "")
    faixas = obter_tabela_faixas()
    for f in faixas:
        f_norm = f["faixa_etaria"].replace(" ", "").replace("–", "-")
        if rot.lower() in f_norm.lower() or f_norm.lower() in rot.lower():
            return f
        if f"{f['idade_min']}-{f['idade_max']}" == rot:
            return f
        if (rot in (">59", ">=59") or "acimade59" in rot.lower()) and f["idade_min"] == 59:
            return f
        if rot == "0-18" and f["idade_min"] == 0:
            return f
    return None


def recalcular_mensalidades_membros(conn_existente=None) -> int:
    """
    Recalcula o valor da mensalidade de cada membro conforme sua idade atual,
    seu tipo de plano (P ou C) e os valores vigentes na tabela_faixas_etarias.
    Preserva a isenção de Nestor Padilha (R$ 0,00).
    """
    def _executar(conn):
        faixas = conn.execute(
            "SELECT * FROM tabela_faixas_etarias ORDER BY ordem ASC"
        ).fetchall()
        faixas_lista = [dict(f) for f in faixas]

        membros = conn.execute("SELECT * FROM membros").fetchall()
        count = 0
        for m in membros:
            nome = m["beneficiario_nome"]
            # Regra de isenção: Nestor Padilha permanece R$ 0,00
            if nome.strip().lower() == "nestor padilha":
                conn.execute(
                    "UPDATE membros SET valor_mensalidade = 0.0 WHERE id = ?",
                    (m["id"],)
                )
                continue

            idade = calcular_idade(m["data_nascimento"])
            if idade is None:
                continue

            # Acha a faixa correspondente
            fx_vigente = None
            for fx in faixas_lista:
                if fx["idade_min"] <= idade <= fx["idade_max"]:
                    fx_vigente = fx
                    break

            if fx_vigente:
                tipo = (m["tipo_plano"] or "C").strip().upper()
                novo_valor = (
                    fx_vigente["valor_privativo"] if tipo == "P" else fx_vigente["valor_coletivo"]
                )
                conn.execute(
                    "UPDATE membros SET valor_mensalidade = ? WHERE id = ?",
                    (novo_valor, m["id"])
                )
                count += 1

        return count

    if conn_existente:
        return _executar(conn_existente)
    else:
        with get_connection() as conn:
            atualizados = _executar(conn)
            _sincronizar_csv_com_banco(conn)
            return atualizados


def atualizar_tabela_faixa(faixa_id: int, valor_privativo: float, valor_coletivo: float) -> None:
    """Atualiza os preços de uma faixa etária específica e recalcula as mensalidades dos membros."""
    with get_connection() as conn:
        conn.execute("""
            UPDATE tabela_faixas_etarias
            SET valor_privativo = ?, valor_coletivo = ?
            WHERE id = ?
        """, (valor_privativo, valor_coletivo, faixa_id))
        recalcular_mensalidades_membros(conn)
        _sincronizar_csv_com_banco(conn)


def reajustar_tabela_faixas_percentual(percentual: float) -> int:
    """
    Aplica reajuste percentual sobre todas as faixas na tabela_faixas_etarias
    e recalcula as mensalidades de todos os membros no banco de dados e CSV.
    Retorna o número de membros recalculados.
    """
    with get_connection() as conn:
        faixas = conn.execute("SELECT * FROM tabela_faixas_etarias").fetchall()
        for f in faixas:
            novo_p = round(f["valor_privativo"] * (1 + percentual / 100), 2)
            novo_c = round(f["valor_coletivo"] * (1 + percentual / 100), 2)
            conn.execute("""
                UPDATE tabela_faixas_etarias
                SET valor_privativo = ?, valor_coletivo = ?
                WHERE id = ?
            """, (novo_p, novo_c, f["id"]))

        # Limpa customizações individuais obsoletas para que a tabela vigore
        conn.execute("DELETE FROM config_valores")

        count = recalcular_mensalidades_membros(conn)
        _sincronizar_csv_com_banco(conn)
        return count


# ─── CONSULTAS DE MEMBROS E MIGRAÇÃO ─────────────────────────────────────────

def listar_titulares() -> list[dict]:
    """Retorna lista de todos os titulares distintos, ordenados alfabeticamente."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT titular_nome, data_nascimento, tipo_plano
            FROM membros
            WHERE UPPER(tipo) = 'TITULAR'
            ORDER BY titular_nome
        """).fetchall()
        return [dict(r) for r in rows]


def buscar_grupo_familiar(titular_nome: str) -> list[dict]:
    """
    Retorna todos os membros de um titular enriquecidos com:
    - idade_atual
    - faixa_calculada
    - migrou_faixa (booleano indicando se mudou de faixa etária pela idade)
    - faixa_anterior
    - valor_faixa_anterior
    - valor_faixa_atual
    - tipo_plano_nome
    """
    faixas = obter_tabela_faixas()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.id, m.tipo, m.titular_nome, m.beneficiario_nome, m.grau_parentesco,
                   m.data_nascimento, m.faixa_etaria, m.tipo_plano, m.valor_mensalidade,
                   COALESCE(cv.valor_atualizado, m.valor_mensalidade) AS valor_vigente
            FROM membros m
            LEFT JOIN config_valores cv ON cv.beneficiario_nome = m.beneficiario_nome
            WHERE m.titular_nome = ?
            ORDER BY
                CASE WHEN UPPER(m.tipo) = 'TITULAR' THEN 0 ELSE 1 END,
                m.beneficiario_nome
        """, (titular_nome,)).fetchall()

        resultado = []
        for r in rows:
            d = dict(r)
            idade = calcular_idade(d.get("data_nascimento"))
            d["idade_atual"] = idade

            # Faixa atual pela idade
            fx_atual = None
            if idade is not None:
                for f in faixas:
                    if f["idade_min"] <= idade <= f["idade_max"]:
                        fx_atual = f
                        break

            d["faixa_calculada"] = fx_atual["faixa_etaria"] if fx_atual else (d.get("faixa_etaria") or "N/A")

            # Faixa cadastrada originalmente
            fx_cad = identificar_faixa_por_rotulo(d.get("faixa_etaria", ""))
            tipo_plano = (d.get("tipo_plano") or "C").strip().upper()
            d["tipo_plano_nome"] = "Privativo" if tipo_plano == "P" else "Coletivo"

            if d.get("beneficiario_nome", "").strip().lower() == "nestor padilha":
                d["valor_faixa_atual"] = 0.0
                d["valor_faixa_anterior"] = 0.0
                d["migrou_faixa"] = False
                d["faixa_anterior"] = d.get("faixa_etaria") or ""
            elif fx_atual and fx_cad:
                d["faixa_anterior"] = fx_cad["faixa_etaria"]
                d["valor_faixa_anterior"] = (
                    fx_cad["valor_privativo"] if tipo_plano == "P" else fx_cad["valor_coletivo"]
                )
                d["valor_faixa_atual"] = (
                    fx_atual["valor_privativo"] if tipo_plano == "P" else fx_atual["valor_coletivo"]
                )
                # Migrou se a ordem da faixa atual for estritamente maior que a faixa cadastrada
                d["migrou_faixa"] = fx_atual["ordem"] > fx_cad["ordem"]
            else:
                d["migrou_faixa"] = False
                d["faixa_anterior"] = d.get("faixa_etaria") or ""
                d["valor_faixa_anterior"] = d.get("valor_mensalidade", 0.0)
                d["valor_faixa_atual"] = d.get("valor_mensalidade", 0.0)

            resultado.append(d)

        return resultado


def verificar_migracoes_grupo(titular_nome: str) -> list[dict]:
    """
    Retorna a lista de integrantes do titular informado que tiveram mudança
    de faixa etária pela idade atual.
    """
    grupo = buscar_grupo_familiar(titular_nome)
    return [m for m in grupo if m.get("migrou_faixa")]


def listar_todas_migracoes() -> list[dict]:
    """Retorna todos os integrantes (titulares ou dependentes) que migraram de faixa etária."""
    titulares = listar_titulares()
    todas = []
    for t in titulares:
        migracoes = verificar_migracoes_grupo(t["titular_nome"])
        todas.extend(migracoes)
    return todas


def validar_nascimento_titular(titular_nome: str, data_nascimento: date) -> bool:
    """Verifica se a data de nascimento informada confere com o cadastro do titular."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT data_nascimento FROM membros
            WHERE titular_nome = ? AND UPPER(tipo) = 'TITULAR'
            LIMIT 1
        """, (titular_nome,)).fetchone()

        if not row or not row["data_nascimento"]:
            return False

        dt_cadastro = row["data_nascimento"]
        return dt_cadastro == data_nascimento.strftime("%Y-%m-%d")


# ─── SOLICITAÇÕES ─────────────────────────────────────────────────────────────

def criar_solicitacao(titular_nome: str, titular_cpf: str,
                      dependentes_json: str, mes_ref: int, ano_ref: int,
                      data_pagamento: str, valor_total: float) -> int:
    """Cria uma nova solicitação com status PENDENTE. Retorna o ID."""
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO solicitacoes
                (titular_nome, titular_cpf, dependentes_incluidos,
                 mes_referencia, ano_referencia, data_pagamento, valor_total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (titular_nome, titular_cpf, dependentes_json,
              mes_ref, ano_ref, data_pagamento, valor_total))
        sol_id = cursor.lastrowid

        from src.utils import gerar_codigo_validacao
        codigo = gerar_codigo_validacao(sol_id, ano_ref)
        conn.execute("""
            UPDATE solicitacoes SET codigo_validacao = ? WHERE id = ?
        """, (codigo, sol_id))

        return sol_id


def listar_solicitacoes_titular(titular_nome: str) -> list[dict]:
    """Retorna todas as solicitações de um titular, ordenadas por data desc."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            WHERE titular_nome = ?
            ORDER BY data_solicitacao DESC
        """, (titular_nome,)).fetchall()
        return [dict(r) for r in rows]


def listar_solicitacoes_pendentes() -> list[dict]:
    """Retorna todas as solicitações pendentes de análise."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            WHERE status = 'PENDENTE'
            ORDER BY data_solicitacao ASC
        """).fetchall()
        return [dict(r) for r in rows]


def listar_todas_solicitacoes() -> list[dict]:
    """Retorna todas as solicitações para relatório geral."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            ORDER BY data_solicitacao DESC
        """).fetchall()
        return [dict(r) for r in rows]


def obter_solicitacao(sol_id: int) -> dict | None:
    """Retorna uma solicitação específica pelo ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM solicitacoes WHERE id = ?", (sol_id,)
        ).fetchone()
        return dict(row) if row else None


def aprovar_solicitacao(sol_id: int, dependentes_json: str,
                        valor_total: float, data_pagamento: str,
                        mes_ref: int, ano_ref: int,
                        pdf_bytes: bytes) -> None:
    """Aprova solicitação, salva PDF e registra data de análise."""
    with get_connection() as conn:
        conn.execute("""
            UPDATE solicitacoes
            SET status = 'APROVADO',
                dependentes_incluidos = ?,
                valor_total = ?,
                data_pagamento = ?,
                mes_referencia = ?,
                ano_referencia = ?,
                data_analise = ?,
                pdf_gerado = ?
            WHERE id = ?
        """, (dependentes_json, valor_total, data_pagamento,
              mes_ref, ano_ref,
              datetime.now().isoformat(), pdf_bytes, sol_id))


def rejeitar_solicitacao(sol_id: int, observacoes: str) -> None:
    """Rejeita solicitação com justificativa do administrador."""
    with get_connection() as conn:
        conn.execute("""
            UPDATE solicitacoes
            SET status = 'REJEITADO',
                data_analise = ?,
                observacoes_admin = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), observacoes, sol_id))


def cancelar_aprovacao(sol_id: int, motivo: str = "") -> None:
    """
    Cancela/revoga uma declaração previamente aprovada pelo administrador.
    Altera o status para 'CANCELADO', apaga o PDF gerado e registra observações.
    """
    with get_connection() as conn:
        obs_atual = conn.execute(
            "SELECT observacoes_admin FROM solicitacoes WHERE id = ?", (sol_id,)
        ).fetchone()
        obs_anterior = obs_atual["observacoes_admin"] if obs_atual and obs_atual["observacoes_admin"] else ""

        agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
        novo_obs = f"[CANCELADO EM {agora_str}] {motivo.strip()}".strip()
        if obs_anterior:
            novo_obs = f"{obs_anterior} | {novo_obs}"

        conn.execute("""
            UPDATE solicitacoes
            SET status = 'CANCELADO',
                pdf_gerado = NULL,
                observacoes_admin = ?
            WHERE id = ?
        """, (novo_obs, sol_id))


def listar_solicitacoes_aprovadas() -> list[dict]:
    """Retorna todas as declarações com status 'APROVADO', ordenadas pela mais recente."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            WHERE status = 'APROVADO'
            ORDER BY data_analise DESC, id DESC
        """).fetchall()
        return [dict(r) for r in rows]


def atualizar_solicitacao_campos(sol_id: int, **kwargs) -> None:
    """Atualiza campos arbitrários de uma solicitação."""
    if not kwargs:
        return
    campos = ", ".join(f"{k} = ?" for k in kwargs)
    valores = list(kwargs.values()) + [sol_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE solicitacoes SET {campos} WHERE id = ?", valores)


# ─── REAJUSTE DE VALORES E MEMBROS ───────────────────────────────────────────

def listar_todos_membros() -> list[dict]:
    """Retorna todos os membros com seus dados de idade, plano e valores vigentes."""
    faixas = obter_tabela_faixas()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.id, m.tipo, m.titular_nome, m.beneficiario_nome,
                   m.grau_parentesco, m.data_nascimento, m.faixa_etaria,
                   m.tipo_plano, m.valor_mensalidade,
                   COALESCE(cv.valor_atualizado, m.valor_mensalidade) AS valor_vigente,
                   cv.data_atualizacao
            FROM membros m
            LEFT JOIN config_valores cv ON cv.beneficiario_nome = m.beneficiario_nome
            ORDER BY m.titular_nome, 
                     CASE WHEN UPPER(m.tipo) = 'TITULAR' THEN 0 ELSE 1 END,
                     m.beneficiario_nome
        """).fetchall()

        resultado = []
        for r in rows:
            d = dict(r)
            idade = calcular_idade(d.get("data_nascimento"))
            d["idade_atual"] = idade

            fx_atual = None
            if idade is not None:
                for f in faixas:
                    if f["idade_min"] <= idade <= f["idade_max"]:
                        fx_atual = f
                        break
            d["faixa_calculada"] = fx_atual["faixa_etaria"] if fx_atual else (d.get("faixa_etaria") or "N/A")

            fx_cad = identificar_faixa_por_rotulo(d.get("faixa_etaria", ""))
            tipo_plano = (d.get("tipo_plano") or "C").strip().upper()
            d["tipo_plano_nome"] = "Privativo" if tipo_plano == "P" else "Coletivo"

            if d.get("beneficiario_nome", "").strip().lower() == "nestor padilha":
                d["migrou_faixa"] = False
            elif fx_atual and fx_cad:
                d["migrou_faixa"] = fx_atual["ordem"] > fx_cad["ordem"]
            else:
                d["migrou_faixa"] = False

            resultado.append(d)

        return resultado


def atualizar_valor_membro(beneficiario_nome: str, novo_valor: float) -> None:
    """Atualiza o valor vigente de um membro específico na tabela de reajustes."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO config_valores (beneficiario_nome, valor_atualizado, data_atualizacao)
            VALUES (?, ?, ?)
            ON CONFLICT(beneficiario_nome)
            DO UPDATE SET valor_atualizado = excluded.valor_atualizado,
                          data_atualizacao = excluded.data_atualizacao
        """, (beneficiario_nome, novo_valor, datetime.now().isoformat()))


def reajustar_valores_lote(percentual: float) -> int:
    """
    Aplica reajuste percentual sobre todos os membros na tabela config_valores.
    (Para reajuste da tabela de faixas oficial, utilize reajustar_tabela_faixas_percentual).
    """
    membros = listar_todos_membros()
    count = 0
    for m in membros:
        valor_atual = m["valor_vigente"] or m["valor_mensalidade"] or 0.0
        if valor_atual > 0:
            novo_valor = round(valor_atual * (1 + percentual / 100), 2)
            atualizar_valor_membro(m["beneficiario_nome"], novo_valor)
            count += 1
    return count


# ─── MÉTRICAS ─────────────────────────────────────────────────────────────────

def contar_solicitacoes_por_status() -> dict:
    """Retorna contagem de solicitações por status."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT status, COUNT(*) as total FROM solicitacoes GROUP BY status
        """).fetchall()
        resultado = {"PENDENTE": 0, "APROVADO": 0, "REJEITADO": 0, "CANCELADO": 0}
        for r in rows:
            resultado[r["status"]] = r["total"]
        return resultado


def contar_aprovadas_mes_atual() -> int:
    """Retorna total de solicitações aprovadas no mês corrente."""
    agora = datetime.now()
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as total FROM solicitacoes
            WHERE status = 'APROVADO'
              AND strftime('%Y-%m', data_analise) = ?
        """, (agora.strftime("%Y-%m"),)).fetchone()
        return row["total"] if row else 0
