"""
Camada de persistência SQLite para o sistema ANSEF/CAS.
Gerencia membros, configuração de valores reajustados e solicitações de declaração.
"""
import sqlite3
import json
import os
import csv
from datetime import datetime, date
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ansef_database.db")
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "integrantes.csv")


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
    """Cria as tabelas e carrega os dados iniciais do CSV, se necessário."""
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
        """)

        # Verifica se já existem membros cadastrados
        count = conn.execute("SELECT COUNT(*) FROM membros").fetchone()[0]
        if count == 0:
            _carregar_csv(conn)
        else:
            # Atualiza correções cadastrais em bases existentes
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


# ─── CONSULTAS DE MEMBROS ────────────────────────────────────────────────────

def listar_titulares() -> list[dict]:
    """Retorna lista de todos os titulares distintos, ordenados alfabeticamente."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT titular_nome, data_nascimento
            FROM membros
            WHERE UPPER(tipo) = 'TITULAR'
            ORDER BY titular_nome
        """).fetchall()
        return [dict(r) for r in rows]


def buscar_grupo_familiar(titular_nome: str) -> list[dict]:
    """Retorna todos os membros (titular + dependentes/agregados) de um titular."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.id, m.tipo, m.beneficiario_nome, m.grau_parentesco,
                   m.data_nascimento, m.valor_mensalidade,
                   COALESCE(cv.valor_atualizado, m.valor_mensalidade) AS valor_vigente
            FROM membros m
            LEFT JOIN config_valores cv ON cv.beneficiario_nome = m.beneficiario_nome
            WHERE m.titular_nome = ?
            ORDER BY
                CASE WHEN UPPER(m.tipo) = 'TITULAR' THEN 0 ELSE 1 END,
                m.beneficiario_nome
        """, (titular_nome,)).fetchall()
        return [dict(r) for r in rows]


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
        # Compara no formato ISO YYYY-MM-DD
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

        # Gera e salva o código de validação
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
    Altera o status para 'CANCELADO', apaga o PDF gerado (para impedir downloads pelo titular),
    e registra a data e motivo do cancelamento nas observações administrativas.
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


# ─── REAJUSTE DE VALORES ─────────────────────────────────────────────────────

def listar_todos_membros() -> list[dict]:
    """Retorna todos os membros com seus valores vigentes (reajustados ou base)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.id, m.tipo, m.titular_nome, m.beneficiario_nome,
                   m.grau_parentesco, m.valor_mensalidade,
                   COALESCE(cv.valor_atualizado, m.valor_mensalidade) AS valor_vigente,
                   cv.data_atualizacao
            FROM membros m
            LEFT JOIN config_valores cv ON cv.beneficiario_nome = m.beneficiario_nome
            ORDER BY m.titular_nome, 
                     CASE WHEN UPPER(m.tipo) = 'TITULAR' THEN 0 ELSE 1 END,
                     m.beneficiario_nome
        """).fetchall()
        return [dict(r) for r in rows]


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
    Aplica reajuste percentual sobre todos os membros.
    Retorna o número de membros atualizados.
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
