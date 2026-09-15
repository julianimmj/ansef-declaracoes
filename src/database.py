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
import threading
from typing import Optional, Union, List, Dict, Any
from datetime import datetime, date
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("ANSEF_DB_PATH") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ansef_database.db")
CSV_PATH = os.environ.get("ANSEF_CSV_PATH") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "integrantes.csv")
SOLICITACOES_BACKUP_PATH = os.environ.get("ANSEF_SOLICITACOES_BACKUP_PATH") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "solicitacoes_backup.json")
CONFIG_PRECOS_PATH = os.environ.get("ANSEF_CONFIG_PRECOS_PATH") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "config_precos.json")

def _obter_db_path() -> str:
    return os.environ.get("ANSEF_DB_PATH") or DB_PATH

def _obter_csv_path() -> str:
    return os.environ.get("ANSEF_CSV_PATH") or CSV_PATH

def _obter_solicitacoes_backup_path() -> str:
    return os.environ.get("ANSEF_SOLICITACOES_BACKUP_PATH") or SOLICITACOES_BACKUP_PATH

def _obter_config_precos_path() -> str:
    return os.environ.get("ANSEF_CONFIG_PRECOS_PATH") or CONFIG_PRECOS_PATH

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
    conn = sqlite3.connect(_obter_db_path(), check_same_thread=False)
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


def _git_sync_background(*filepaths: str) -> None:
    """Sincroniza arquivos com o GitHub em background (não bloqueia a UI)."""
    def _sync():
        try:
            try:
                from src.git_sync import sincronizar_arquivo, _obter_token
            except ImportError:
                from git_sync import sincronizar_arquivo, _obter_token
            token = _obter_token()
            if not token:
                return
            agora = datetime.now().strftime("%d/%m/%Y %H:%M")
            for fp in filepaths:
                sincronizar_arquivo(fp, token, f"sync: {fp} ({agora})")
        except Exception as e:
            logger.debug(f"Git sync background ignorado: {e}")
    threading.Thread(target=_sync, daemon=True).start()


def padronizar_nome(nome: str) -> str:
    """
    Padroniza um nome próprio para Title Case profissional em português:
    - Preposições e conjunções em minúsculas (de, da, do, das, dos, e, d.).
    - Iniciais e abreviações com ponto mantidas em maiúsculas (ex: P., S., R., Jr.).
    - Remove espaços duplicados e trata strings vazias.
    """
    if not nome or not isinstance(nome, str):
        return ""

    minusculas = {"de", "da", "do", "das", "dos", "e", "d."}
    partes = nome.strip().split()
    partes_formatadas = []

    for i, p in enumerate(partes):
        p_clean = p.strip()
        if not p_clean:
            continue

        if i > 0 and p_clean.lower() in minusculas:
            partes_formatadas.append(p_clean.lower())
        elif len(p_clean) <= 2 and p_clean.endswith("."):
            partes_formatadas.append(p_clean.upper())
        elif p_clean.lower() in ["jr.", "jr"]:
            partes_formatadas.append("Jr." if "." in p_clean else "Jr")
        elif p_clean.lower() in ["filho", "filha", "neto", "neta", "sobrinho", "sobrinha"]:
            partes_formatadas.append(p_clean.capitalize())
        else:
            partes_formatadas.append(p_clean.capitalize())

    return " ".join(partes_formatadas)


def padronizar_todos_nomes_banco(conn) -> None:
    """
    Varre e padroniza todos os nomes em membros, solicitacoes,
    uniodonto_titulares e config_valores no padrão Title Case limpo.
    """
    try:
        # 1. Membros
        membros = conn.execute("SELECT id, titular_nome, beneficiario_nome FROM membros").fetchall()
        for m in membros:
            n_tit = padronizar_nome(m["titular_nome"])
            n_ben = padronizar_nome(m["beneficiario_nome"])
            if n_tit != m["titular_nome"] or n_ben != m["beneficiario_nome"]:
                conn.execute(
                    "UPDATE membros SET titular_nome = ?, beneficiario_nome = ? WHERE id = ?",
                    (n_tit, n_ben, m["id"])
                )

        # 2. Uniodonto
        unio = conn.execute("SELECT id, titular_nome FROM uniodonto_titulares").fetchall()
        for u in unio:
            n_tit = padronizar_nome(u["titular_nome"])
            if n_tit != u["titular_nome"]:
                conn.execute(
                    "UPDATE uniodonto_titulares SET titular_nome = ? WHERE id = ?",
                    (n_tit, u["id"])
                )

        # 3. Config Valores
        cfgs = conn.execute("SELECT id, beneficiario_nome FROM config_valores").fetchall()
        for c in cfgs:
            n_ben = padronizar_nome(c["beneficiario_nome"])
            if n_ben != c["beneficiario_nome"]:
                conn.execute(
                    "UPDATE config_valores SET beneficiario_nome = ? WHERE id = ?",
                    (n_ben, c["id"])
                )

        # 4. Solicitações
        sols = conn.execute("SELECT id, titular_nome, dependentes_incluidos FROM solicitacoes").fetchall()
        for s in sols:
            n_tit = padronizar_nome(s["titular_nome"])
            deps_raw = s["dependentes_incluidos"] or "[]"
            changed = False
            try:
                deps = json.loads(deps_raw)
                for d in deps:
                    if "nome" in d:
                        n_d = padronizar_nome(d["nome"])
                        if n_d != d["nome"]:
                            d["nome"] = n_d
                            changed = True
                novo_deps_raw = json.dumps(deps, ensure_ascii=False) if changed else deps_raw
            except Exception:
                novo_deps_raw = deps_raw
                changed = False

            if n_tit != s["titular_nome"] or changed:
                conn.execute(
                    "UPDATE solicitacoes SET titular_nome = ?, dependentes_incluidos = ? WHERE id = ?",
                    (n_tit, novo_deps_raw, s["id"])
                )
    except Exception as e:
        logger.warning(f"Aviso ao padronizar nomes no banco: {e}")


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

            CREATE TABLE IF NOT EXISTS config_uniodonto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                valor_por_vida REAL NOT NULL DEFAULT 35.00,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS uniodonto_titulares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titular_nome TEXT UNIQUE NOT NULL,
                vidas INTEGER NOT NULL DEFAULT 1,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Inicializa o valor por vida da Uniodonto caso tabela vazia e não exista backup JSON
        count_cfg_u = conn.execute("SELECT COUNT(*) FROM config_uniodonto").fetchone()[0]
        caminho_precos = _obter_config_precos_path()
        if count_cfg_u == 0 and not os.path.exists(caminho_precos):
            conn.execute("INSERT INTO config_uniodonto (valor_por_vida) VALUES (35.00)")
        elif count_cfg_u > 1:
            # Limpa registros duplicados acumulados — mantém apenas o mais recente
            ultimo = conn.execute("SELECT id FROM config_uniodonto ORDER BY id DESC LIMIT 1").fetchone()
            if ultimo:
                conn.execute("DELETE FROM config_uniodonto WHERE id != ?", (ultimo["id"],))

        # Inicializa os titulares com Uniodonto caso tabela vazia e não exista backup JSON
        count_u_tit = conn.execute("SELECT COUNT(*) FROM uniodonto_titulares").fetchone()[0]
        if count_u_tit == 0 and not os.path.exists(caminho_precos):
            titulares_iniciais_uniodonto = [
                ("Carlos Sergio Praciano P.", 2),
                ("Francisco Sandin Martins", 1),
                ("Marcio Carlos Rosa", 5),
                ("José Luis Cordeiro Marcheori", 2),
            ]
            for t_nome, vidas in titulares_iniciais_uniodonto:
                conn.execute(
                    "INSERT OR IGNORE INTO uniodonto_titulares (titular_nome, vidas) VALUES (?, ?)",
                    (t_nome, vidas)
                )

        # Carrega a lista autoritativa de membros vigentes de data/integrantes.csv
        _carregar_csv(conn)

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

        # Padroniza todos os nomes para Title Case profissional
        padronizar_todos_nomes_banco(conn)

        # Restaura reajustes de preços e configurações vigentes
        _carregar_backup_precos(conn)

        # Recalcula mensalidades com base na tabela de faixas etárias e idade
        recalcular_mensalidades_membros(conn)
        _sincronizar_csv_com_banco(conn, sync_git=False)

        # Sincroniza solicitações com backup JSON permanente (sempre mescla antes de salvar)
        _carregar_backup_solicitacoes(conn)
        _salvar_backup_solicitacoes(conn, sync_git=False)

        # Garante que o arquivo config_precos.json esteja sincronizado localmente
        _salvar_backup_precos(conn, sync_git=False)

        # Política de retenção: remove registros com mais de 5 anos
        _limpar_registros_antigos(conn)

        # Assegura que solicitações aprovadas sem PDF tenham o PDF gerado
        _garantir_pdfs_solicitacoes_aprovadas(conn)


def _carregar_csv(conn):
    """Carrega os dados do CSV de integrantes para a tabela membros, garantindo sincronia total com o repositório."""
    if not os.path.exists(CSV_PATH):
        return

    # Limpa a tabela membros para refletir fielmente o CSV sincronizado no repositório
    conn.execute("DELETE FROM membros")

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


def _sincronizar_csv_com_banco(conn, sync_git: bool = True):
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
    else:
        if sync_git:
            _git_sync_background("data/integrantes.csv")


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
        _salvar_backup_precos(conn)


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
        _salvar_backup_precos(conn)
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


# ─── BACKUP E PERSISTÊNCIA DE SOLICITAÇÕES ────────────────────────────────────

def _salvar_backup_solicitacoes(conn=None, sync_git: bool = True) -> None:
    """
    Exporta todas as solicitações para um arquivo JSON permanente.
    Permite restaurar o histórico completo caso o contêiner efêmero seja recriado.
    O campo binário do PDF não é incluído no JSON para manter o arquivo leve e versionável no Git.
    """
    caminho = _obter_solicitacoes_backup_path()
    try:
        def _exec(c):
            rows = c.execute("SELECT * FROM solicitacoes ORDER BY id ASC").fetchall()
            data = []
            for r in rows:
                item = dict(r)
                item.pop("pdf_gerado", None)
                data.append(item)
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        if conn:
            _exec(conn)
        else:
            with get_connection() as c:
                _exec(c)
    except Exception as e:
        logger.warning(f"Erro ao salvar backup de solicitacoes: {e}")
    else:
        if sync_git:
            _git_sync_background("data/solicitacoes_backup.json")


def _carregar_backup_solicitacoes(conn) -> int:
    """
    Restaura solicitações a partir do arquivo JSON permanente caso existam e não estejam no banco.
    """
    caminho = _obter_solicitacoes_backup_path()
    if not os.path.exists(caminho):
        return 0

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data or not isinstance(data, list):
            return 0

        total_restaurados = 0
        for item in data:
            cod = item.get("codigo_validacao")
            iid = item.get("id")
            existe = conn.execute(
                "SELECT id FROM solicitacoes WHERE id = ? OR (codigo_validacao = ? AND codigo_validacao IS NOT NULL)",
                (iid, cod)
            ).fetchone()
            if not existe:
                conn.execute("""
                    INSERT INTO solicitacoes (
                        id, codigo_validacao, titular_nome, titular_cpf, dependentes_incluidos,
                        mes_referencia, ano_referencia, data_pagamento, valor_total,
                        status, data_solicitacao, data_analise, observacoes_admin, pdf_gerado
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("id"),
                    item.get("codigo_validacao"),
                    item.get("titular_nome"),
                    item.get("titular_cpf"),
                    item.get("dependentes_incluidos", "[]"),
                    item.get("mes_referencia"),
                    item.get("ano_referencia"),
                    item.get("data_pagamento"),
                    item.get("valor_total"),
                    item.get("status", "PENDENTE"),
                    item.get("data_solicitacao"),
                    item.get("data_analise"),
                    item.get("observacoes_admin"),
                    None
                ))
                total_restaurados += 1
            else:
                # Se já existe no banco, atualiza status, análise, observações e sincroniza pdf_gerado a partir do backup JSON
                st_item = item.get("status", "PENDENTE")
                conn.execute("""
                    UPDATE solicitacoes SET
                        status = ?,
                        data_analise = ?,
                        observacoes_admin = ?,
                        valor_total = COALESCE(?, valor_total),
                        pdf_gerado = CASE WHEN ? = 'APROVADO' THEN pdf_gerado ELSE NULL END
                    WHERE id = ? OR (codigo_validacao = ? AND codigo_validacao IS NOT NULL)
                """, (
                    st_item,
                    item.get("data_analise"),
                    item.get("observacoes_admin"),
                    item.get("valor_total"),
                    st_item,
                    iid,
                    cod
                ))

        if total_restaurados > 0:
            logger.info(f"Restauradas {total_restaurados} solicitacoes do backup JSON.")
        return total_restaurados
    except Exception as e:
        logger.warning(f"Erro ao carregar backup de solicitacoes: {e}")
        return 0


def _garantir_pdfs_solicitacoes_aprovadas(conn) -> None:
    """
    Garante que qualquer solicitação com status APROVADO que não possua
    o BLOB do PDF gerado tenha seu PDF sintetizado e salvo no banco.
    """
    try:
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            WHERE status = 'APROVADO' AND (pdf_gerado IS NULL OR LENGTH(pdf_gerado) < 100)
        """).fetchall()

        if not rows:
            return

        try:
            from src.pdf_generator import gerar_pdf_declaracao
        except ImportError:
            from pdf_generator import gerar_pdf_declaracao

        for r in rows:
            sol = dict(r)
            try:
                novo_pdf = gerar_pdf_declaracao(
                    titular_nome=sol["titular_nome"],
                    titular_cpf=sol["titular_cpf"],
                    dependentes_json=sol.get("dependentes_incluidos", "[]"),
                    mes_referencia=sol["mes_referencia"],
                    ano_referencia=sol["ano_referencia"],
                    data_pagamento=sol["data_pagamento"],
                    valor_total=sol["valor_total"],
                    codigo_validacao=sol.get("codigo_validacao") or f"ANSEF-{sol['ano_referencia']}-{sol['id']:04d}",
                )
                conn.execute(
                    "UPDATE solicitacoes SET pdf_gerado = ? WHERE id = ?",
                    (novo_pdf, sol["id"])
                )
            except Exception as ex:
                logger.error(f"Erro ao sintetizar PDF para solicitacao aprovada #{sol['id']}: {ex}")
    except Exception as e:
        logger.warning(f"Erro ao verificar PDFs de solicitacoes aprovadas: {e}")


def obter_pdf_solicitacao(sol_id: int) -> bytes | None:
    """
    Retorna os bytes do PDF de uma solicitação aprovada.
    Caso o registro não tenha os bytes salvos, sintetiza dinamicamente e persiste.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM solicitacoes WHERE id = ?", (sol_id,)).fetchone()
        if not row:
            return None
        sol = dict(row)
        pdf_bytes = sol.get("pdf_gerado")
        if pdf_bytes and len(pdf_bytes) > 100:
            return pdf_bytes

        if sol.get("status") == "APROVADO":
            try:
                from src.pdf_generator import gerar_pdf_declaracao
            except ImportError:
                from pdf_generator import gerar_pdf_declaracao

            try:
                novo_pdf = gerar_pdf_declaracao(
                    titular_nome=sol["titular_nome"],
                    titular_cpf=sol["titular_cpf"],
                    dependentes_json=sol.get("dependentes_incluidos", "[]"),
                    mes_referencia=sol["mes_referencia"],
                    ano_referencia=sol["ano_referencia"],
                    data_pagamento=sol["data_pagamento"],
                    valor_total=sol["valor_total"],
                    codigo_validacao=sol.get("codigo_validacao") or f"ANSEF-{sol['ano_referencia']}-{sol['id']:04d}",
                )
                conn.execute("UPDATE solicitacoes SET pdf_gerado = ? WHERE id = ?", (novo_pdf, sol_id))
                return novo_pdf
            except Exception as e:
                logger.error(f"Erro ao sintetizar PDF sob demanda para #{sol_id}: {e}")
                return None
        return None


def exportar_backup_json() -> str:
    """Retorna o JSON completo de todas as solicitações para download de segurança."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM solicitacoes ORDER BY id ASC").fetchall()
        data = []
        for r in rows:
            item = dict(r)
            item.pop("pdf_gerado", None)
            data.append(item)
        return json.dumps(data, ensure_ascii=False, indent=2)


def importar_backup_json(conteudo_json: str) -> tuple[bool, str, int]:
    """Importa e mescla solicitações a partir de um JSON de backup fornecido pelo admin."""
    try:
        data = json.loads(conteudo_json)
        if not isinstance(data, list):
            return False, "O conteúdo do arquivo deve ser uma lista de solicitações em JSON.", 0

        restaurados = 0
        with get_connection() as conn:
            for item in data:
                cod = item.get("codigo_validacao")
                iid = item.get("id")
                existe = conn.execute(
                    "SELECT id FROM solicitacoes WHERE id = ? OR (codigo_validacao = ? AND codigo_validacao IS NOT NULL)",
                    (iid, cod)
                ).fetchone()
                if not existe:
                    conn.execute("""
                        INSERT INTO solicitacoes (
                            id, codigo_validacao, titular_nome, titular_cpf, dependentes_incluidos,
                            mes_referencia, ano_referencia, data_pagamento, valor_total,
                            status, data_solicitacao, data_analise, observacoes_admin, pdf_gerado
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item.get("id"),
                        item.get("codigo_validacao"),
                        item.get("titular_nome"),
                        item.get("titular_cpf"),
                        item.get("dependentes_incluidos", "[]"),
                        item.get("mes_referencia"),
                        item.get("ano_referencia"),
                        item.get("data_pagamento"),
                        item.get("valor_total"),
                        item.get("status", "PENDENTE"),
                        item.get("data_solicitacao"),
                        item.get("data_analise"),
                        item.get("observacoes_admin"),
                        None
                    ))
                    restaurados += 1

            _salvar_backup_solicitacoes(conn)
            _garantir_pdfs_solicitacoes_aprovadas(conn)

        return True, f"{restaurados} solicitação(ões) importada(s) com sucesso!", restaurados
    except Exception as e:
        return False, f"Erro ao processar backup JSON: {str(e)}", 0


# ─── BACKUP E PERSISTÊNCIA DE PREÇOS E CONFIGURAÇÕES ─────────────────────────

def _salvar_backup_precos(conn=None, sync_git: bool = True) -> bool:
    """
    Exporta toda a configuração de preços vigentes para o arquivo JSON permanente data/config_precos.json:
    - Valor unitário por vida do plano Uniodonto (e data de atualização)
    - Titulares e vidas do plano Uniodonto
    - Tabela de faixas etárias da Unimed (valores privativo e coletivo)
    - Valores customizados de membros (config_valores)
    Garante que qualquer alteração feita pelo administrador seja gravada imediatamente em arquivo permanente.
    Retorna True se houve modificação real nos dados e o arquivo foi gravado, False caso contrário.
    """
    caminho_precos = _obter_config_precos_path()
    salvou = False
    try:
        def _exec(c) -> bool:
            # 1. Uniodonto config
            row_u = c.execute("SELECT valor_por_vida, data_atualizacao FROM config_uniodonto ORDER BY id DESC LIMIT 1").fetchone()
            cfg_uniodonto = {
                "valor_por_vida": float(row_u["valor_por_vida"]) if row_u else 35.00,
                "data_atualizacao": str(row_u["data_atualizacao"]) if row_u else datetime.now().isoformat()
            }

            # 2. Uniodonto titulares
            rows_ut = c.execute("SELECT titular_nome, vidas, data_atualizacao FROM uniodonto_titulares ORDER BY titular_nome ASC").fetchall()
            titulares_u = [
                {
                    "titular_nome": r["titular_nome"],
                    "vidas": int(r["vidas"]),
                    "data_atualizacao": str(r["data_atualizacao"])
                }
                for r in rows_ut
            ]

            # 3. Tabela de faixas etárias Unimed
            rows_fx = c.execute("SELECT * FROM tabela_faixas_etarias ORDER BY ordem ASC").fetchall()
            faixas = [
                {
                    "id": r["id"],
                    "faixa_etaria": r["faixa_etaria"],
                    "idade_min": r["idade_min"],
                    "idade_max": r["idade_max"],
                    "valor_privativo": float(r["valor_privativo"]),
                    "valor_coletivo": float(r["valor_coletivo"]),
                    "ordem": r["ordem"]
                }
                for r in rows_fx
            ]

            # 4. Config valores individuais
            rows_cv = c.execute("SELECT beneficiario_nome, valor_atualizado, data_atualizacao FROM config_valores ORDER BY beneficiario_nome ASC").fetchall()
            config_valores = [
                {
                    "beneficiario_nome": r["beneficiario_nome"],
                    "valor_atualizado": float(r["valor_atualizado"]),
                    "data_atualizacao": str(r["data_atualizacao"])
                }
                for r in rows_cv
            ]

            existing_data = None
            if os.path.exists(caminho_precos):
                try:
                    with open(caminho_precos, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception:
                    existing_data = None

            dados_mudaram = True
            ultima_att = datetime.now().isoformat()
            if existing_data and isinstance(existing_data, dict):
                if (existing_data.get("config_uniodonto") == cfg_uniodonto and
                    existing_data.get("uniodonto_titulares") == titulares_u and
                    existing_data.get("tabela_faixas_etarias") == faixas and
                    existing_data.get("config_valores") == config_valores):
                    dados_mudaram = False
                    ultima_att = existing_data.get("ultima_atualizacao", ultima_att)

            if not dados_mudaram and os.path.exists(caminho_precos):
                return False

            payload = {
                "ultima_atualizacao": ultima_att,
                "config_uniodonto": cfg_uniodonto,
                "uniodonto_titulares": titulares_u,
                "tabela_faixas_etarias": faixas,
                "config_valores": config_valores,
            }

            os.makedirs(os.path.dirname(caminho_precos), exist_ok=True)
            with open(caminho_precos, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return True

        if conn:
            salvou = _exec(conn)
        else:
            with get_connection() as c:
                salvou = _exec(c)
    except Exception as e:
        logger.warning(f"Erro ao salvar backup de preços: {e}")
        return False
    else:
        if sync_git and salvou:
            _git_sync_background("data/config_precos.json")
        return salvou


def _carregar_backup_precos(conn) -> bool:
    """
    Restaura os preços e configurações salvos em data/config_precos.json para o banco de dados.
    Usa comparação de timestamps: só sobrescreve o banco se o JSON tiver dados mais recentes,
    garantindo que ajustes feitos pelo administrador nunca sejam perdidos.
    """
    caminho_precos = _obter_config_precos_path()
    if not os.path.exists(caminho_precos):
        _salvar_backup_precos(conn)
        return False

    try:
        with open(caminho_precos, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data or not isinstance(data, dict):
            return False

        json_ultima_att = data.get("ultima_atualizacao", "")

        # 1. Restaura Uniodonto valor por vida (com comparação de timestamp)
        cfg_u = data.get("config_uniodonto", {})
        if "valor_por_vida" in cfg_u:
            val_u = float(cfg_u["valor_por_vida"])
            dt_json_u = cfg_u.get("data_atualizacao", "")
            row_last = conn.execute(
                "SELECT valor_por_vida, data_atualizacao FROM config_uniodonto ORDER BY id DESC LIMIT 1"
            ).fetchone()

            deve_atualizar = False
            if not row_last:
                deve_atualizar = True
            elif abs(float(row_last["valor_por_vida"]) - val_u) > 0.001:
                # Só atualiza se o JSON for mais recente que o banco
                dt_db_str = str(row_last["data_atualizacao"]) if row_last["data_atualizacao"] else ""
                deve_atualizar = dt_json_u > dt_db_str if (dt_json_u and dt_db_str) else True

            if deve_atualizar:
                if row_last:
                    conn.execute(
                        "UPDATE config_uniodonto SET valor_por_vida = ?, data_atualizacao = ? WHERE id = (SELECT id FROM config_uniodonto ORDER BY id DESC LIMIT 1)",
                        (val_u, dt_json_u or datetime.now().isoformat())
                    )
                else:
                    conn.execute(
                        "INSERT INTO config_uniodonto (valor_por_vida, data_atualizacao) VALUES (?, ?)",
                        (val_u, dt_json_u or datetime.now().isoformat())
                    )

        # 2. Restaura Uniodonto titulares e vidas (com comparação de timestamp)
        tit_u_list = data.get("uniodonto_titulares", [])
        if tit_u_list:
            for item in tit_u_list:
                t_nome = padronizar_nome(item.get("titular_nome", ""))
                v_vidas = int(item.get("vidas", 1))
                dt_tut = item.get("data_atualizacao", "")
                if not t_nome:
                    continue
                row_db = conn.execute(
                    "SELECT vidas, data_atualizacao FROM uniodonto_titulares WHERE LOWER(titular_nome) = LOWER(?)",
                    (t_nome,)
                ).fetchone()
                if not row_db:
                    conn.execute("""
                        INSERT INTO uniodonto_titulares (titular_nome, vidas, data_atualizacao)
                        VALUES (?, ?, ?)
                    """, (t_nome, v_vidas, dt_tut or datetime.now().isoformat()))
                else:
                    dt_db_str = str(row_db["data_atualizacao"]) if row_db["data_atualizacao"] else ""
                    if dt_tut and dt_tut > dt_db_str:
                        conn.execute("""
                            UPDATE uniodonto_titulares SET vidas = ?, data_atualizacao = ?
                            WHERE LOWER(titular_nome) = LOWER(?)
                        """, (v_vidas, dt_tut, t_nome))

        # 3. Restaura Tabela de faixas etárias Unimed (com comparação de timestamp)
        faixas_list = data.get("tabela_faixas_etarias", [])
        if faixas_list:
            for fx in faixas_list:
                fx_id = fx.get("id")
                vp = float(fx.get("valor_privativo", 0.0))
                vc = float(fx.get("valor_coletivo", 0.0))
                faixa_etaria = fx.get("faixa_etaria")
                if fx_id:
                    row_db = conn.execute(
                        "SELECT valor_privativo, valor_coletivo FROM tabela_faixas_etarias WHERE id = ?",
                        (fx_id,)
                    ).fetchone()
                    if row_db:
                        # Só sobrescreve se valores diferirem e o JSON for mais recente
                        vals_differ = (abs(float(row_db["valor_privativo"]) - vp) > 0.001 or
                                       abs(float(row_db["valor_coletivo"]) - vc) > 0.001)
                        if vals_differ and json_ultima_att:
                            conn.execute("""
                                UPDATE tabela_faixas_etarias
                                SET valor_privativo = ?, valor_coletivo = ?
                                WHERE id = ?
                            """, (vp, vc, fx_id))
                elif faixa_etaria:
                    conn.execute("""
                        UPDATE tabela_faixas_etarias
                        SET valor_privativo = ?, valor_coletivo = ?
                        WHERE faixa_etaria = ?
                    """, (vp, vc, faixa_etaria))

        # 4. Restaura config_valores se houver (com comparação de timestamp)
        cv_list = data.get("config_valores", [])
        if cv_list:
            for cv in cv_list:
                b_nome = padronizar_nome(cv.get("beneficiario_nome", ""))
                v_at = float(cv.get("valor_atualizado", 0.0))
                dt_cv = cv.get("data_atualizacao", "")
                if not b_nome:
                    continue
                row_db = conn.execute(
                    "SELECT valor_atualizado, data_atualizacao FROM config_valores WHERE beneficiario_nome = ?",
                    (b_nome,)
                ).fetchone()
                if not row_db:
                    conn.execute("""
                        INSERT INTO config_valores (beneficiario_nome, valor_atualizado, data_atualizacao)
                        VALUES (?, ?, ?)
                    """, (b_nome, v_at, dt_cv or datetime.now().isoformat()))
                else:
                    dt_db_str = str(row_db["data_atualizacao"]) if row_db["data_atualizacao"] else ""
                    if dt_cv and dt_cv > dt_db_str:
                        conn.execute("""
                            UPDATE config_valores SET valor_atualizado = ?, data_atualizacao = ?
                            WHERE beneficiario_nome = ?
                        """, (v_at, dt_cv, b_nome))

        return True
    except Exception as e:
        logger.warning(f"Erro ao carregar backup de preços: {e}")
        return False


def exportar_backup_precos_json() -> str:
    """Retorna o JSON completo da configuração de preços e faixas para download."""
    with get_connection() as conn:
        _salvar_backup_precos(conn, sync_git=False)
    caminho_precos = _obter_config_precos_path()
    if os.path.exists(caminho_precos):
        with open(caminho_precos, "r", encoding="utf-8") as f:
            return f.read()
    return "{}"


def importar_backup_precos_json(conteudo_json: str) -> tuple[bool, str]:
    """Importa e aplica a configuração de preços a partir de um JSON fornecido pelo admin."""
    try:
        data = json.loads(conteudo_json)
        if not isinstance(data, dict):
            return False, "O conteúdo do arquivo deve ser um objeto JSON válido de configuração de preços."
        caminho_precos = _obter_config_precos_path()
        os.makedirs(os.path.dirname(caminho_precos), exist_ok=True)
        with open(caminho_precos, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with get_connection() as conn:
            _carregar_backup_precos(conn)
            recalcular_mensalidades_membros(conn)
            _sincronizar_csv_com_banco(conn)
        return True, "Configuração de preços e faixas restaurada com sucesso!"
    except Exception as e:
        return False, f"Erro ao restaurar configuração de preços: {e}"


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

        try:
            from src.utils import gerar_codigo_validacao
        except ImportError:
            from utils import gerar_codigo_validacao
        codigo = gerar_codigo_validacao(sol_id, ano_ref)
        conn.execute("""
            UPDATE solicitacoes SET codigo_validacao = ? WHERE id = ?
        """, (codigo, sol_id))

        _salvar_backup_solicitacoes(conn)
        return sol_id


def listar_solicitacoes_titular(titular_nome: str) -> list[dict]:
    """Retorna todas as solicitações de um titular, ordenadas por data desc, sincronizando antes do backup JSON."""
    nome_limpo = padronizar_nome(titular_nome).strip()
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            WHERE LOWER(TRIM(titular_nome)) = LOWER(TRIM(?))
            ORDER BY data_solicitacao DESC
        """, (nome_limpo,)).fetchall()
        return [dict(r) for r in rows]


def listar_solicitacoes_pendentes() -> list[dict]:
    """Retorna todas as solicitações pendentes de análise, sincronizando antes do backup JSON."""
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            WHERE status = 'PENDENTE'
            ORDER BY data_solicitacao ASC
        """).fetchall()
        return [dict(r) for r in rows]


def listar_todas_solicitacoes() -> list[dict]:
    """Retorna todas as solicitações para relatório geral, sincronizando antes do backup JSON."""
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        rows = conn.execute("""
            SELECT * FROM solicitacoes
            ORDER BY data_solicitacao DESC
        """).fetchall()
        return [dict(r) for r in rows]


def obter_solicitacao(sol_id: int) -> dict | None:
    """Retorna uma solicitação específica pelo ID, sincronizando antes do backup JSON."""
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
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
        _salvar_backup_solicitacoes(conn)


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
        _salvar_backup_solicitacoes(conn)


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
        _salvar_backup_solicitacoes(conn)


def listar_solicitacoes_aprovadas() -> list[dict]:
    """Retorna todas as declarações com status 'APROVADO', ordenadas pela mais recente."""
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
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
        _salvar_backup_solicitacoes(conn)


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
        _salvar_backup_precos(conn)


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
    """Retorna contagem de solicitações por status filtrada pelo ano corrente.
    Os balões do painel admin exibem apenas dados do ano vigente.
    O histórico completo (até 5 anos) permanece armazenado no banco e no backup JSON.
    Sincroniza com o backup permanente para refletir solicitações recém-enviadas.
    """
    ano_atual = datetime.now().year
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        rows = conn.execute("""
            SELECT status, COUNT(*) as total
            FROM solicitacoes
            WHERE ano_referencia = ?
            GROUP BY status
        """, (ano_atual,)).fetchall()
        resultado = {"PENDENTE": 0, "APROVADO": 0, "REJEITADO": 0, "CANCELADO": 0}
        for r in rows:
            resultado[r["status"]] = r["total"]
        return resultado


def contar_aprovadas_mes_atual() -> int:
    """Retorna total de solicitações aprovadas no mês corrente do ano corrente."""
    agora = datetime.now()
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        row = conn.execute("""
            SELECT COUNT(*) as total FROM solicitacoes
            WHERE status = 'APROVADO'
              AND ano_referencia = ?
              AND strftime('%Y-%m', data_analise) = ?
        """, (agora.year, agora.strftime("%Y-%m"))).fetchone()
        return row["total"] if row else 0


def _limpar_registros_antigos(conn) -> int:
    """Remove solicitações fora da janela de retenção de 5 anos.
    Mantém sempre os 5 anos mais recentes (ano corrente + 4 anteriores).
    Ex: em 2026 mantém 2022–2026 e descarta 2021 e anteriores.
    O backup JSON é atualizado após a limpeza para manter consistência.
    Retorna o número de registros removidos.
    """
    ano_atual = datetime.now().year
    ano_limite = ano_atual - 4  # mantém [ano_atual-4 .. ano_atual] = 5 anos
    try:
        cursor = conn.execute("""
            DELETE FROM solicitacoes
            WHERE ano_referencia < ?
        """, (ano_limite,))
        removidos = cursor.rowcount
        if removidos > 0:
            logger.info(
                f"Retenção: {removidos} solicitação(ões) anteriores a {ano_limite} removidas. "
                f"Janela ativa: {ano_limite}–{ano_atual}."
            )
            _salvar_backup_solicitacoes(conn)
        return removidos
    except Exception as e:
        logger.warning(f"Erro na limpeza de registros antigos: {e}")
        return 0


def obter_anos_disponiveis() -> list[int]:
    """Retorna lista ordenada (desc) dos anos de referência com solicitações no banco."""
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        rows = conn.execute("""
            SELECT DISTINCT ano_referencia FROM solicitacoes
            ORDER BY ano_referencia DESC
        """).fetchall()
        return [r["ano_referencia"] for r in rows if r["ano_referencia"]]


def contar_solicitacoes_por_status_ano(ano: int) -> dict:
    """Retorna contagem de solicitações por status para um ano específico."""
    with get_connection() as conn:
        _carregar_backup_solicitacoes(conn)
        rows = conn.execute("""
            SELECT status, COUNT(*) as total
            FROM solicitacoes
            WHERE ano_referencia = ?
            GROUP BY status
        """, (ano,)).fetchall()
        resultado = {"PENDENTE": 0, "APROVADO": 0, "REJEITADO": 0, "CANCELADO": 0}
        for r in rows:
            resultado[r["status"]] = r["total"]
        return resultado


# ─── GESTÃO DE INTEGRANTES E GRUPOS FAMILIARES (CRUD ADMIN) ───────────────────

def adicionar_titular(
    nome: str,
    data_nascimento: str | date,
    cpf: str = "",
    tipo_plano: str = "C",
) -> tuple[bool, str, Optional[int]]:
    """
    Cadastra um novo titular (criando um novo grupo familiar).
    Calcula a idade, enquadra na faixa etária e define a mensalidade automaticamente.
    Sincroniza com data/integrantes.csv.
    """
    nome_limpo = padronizar_nome(nome)
    if not nome_limpo:
        return False, "Nome do titular é obrigatório.", None

    tipo_plano_norm = (tipo_plano or "C").strip().upper()
    if tipo_plano_norm not in ("P", "C"):
        tipo_plano_norm = "C"

    # Converte data de nascimento para ISO YYYY-MM-DD
    if isinstance(data_nascimento, date):
        data_iso = data_nascimento.strftime("%Y-%m-%d")
    else:
        dt_str = str(data_nascimento).strip()
        if "/" in dt_str:
            try:
                data_iso = datetime.strptime(dt_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                return False, "Data de nascimento inválida (use o formato DD/MM/AAAA).", None
        else:
            data_iso = dt_str

    idade = calcular_idade(data_iso)
    if idade is None:
        return False, "Não foi possível calcular a idade a partir da data informada.", None

    faixa = determinar_faixa_etaria(idade)
    if not faixa:
        return False, f"Nenhuma faixa etária cadastrada para a idade de {idade} anos.", None

    valor_mensal = faixa["valor_privativo"] if tipo_plano_norm == "P" else faixa["valor_coletivo"]

    # Higieniza CPF
    import re
    cpf_limpo = re.sub(r"\D", "", str(cpf))

    with get_connection() as conn:
        # Verifica duplicidade de nome
        existe = conn.execute(
            "SELECT id FROM membros WHERE LOWER(beneficiario_nome) = LOWER(?)",
            (nome_limpo,)
        ).fetchone()
        if existe:
            return False, f"Já existe um integrante cadastrado com o nome '{nome_limpo}'.", None

        cursor = conn.execute("""
            INSERT INTO membros (
                tipo, titular_nome, beneficiario_nome, grau_parentesco,
                data_nascimento, cpf, faixa_etaria, tipo_plano, valor_mensalidade
            ) VALUES ('TITULAR', ?, ?, 'Titular', ?, ?, ?, ?, ?)
        """, (
            nome_limpo,
            nome_limpo,
            data_iso,
            cpf_limpo,
            faixa["faixa_etaria"],
            tipo_plano_norm,
            valor_mensal,
        ))
        novo_id = cursor.lastrowid
        _sincronizar_csv_com_banco(conn)

    msg_sucesso = (
        f"Titular {nome_limpo} cadastrado com sucesso! "
        f"Idade: {idade} anos | Faixa: {faixa['faixa_etaria']} | "
        f"Plano: {'Privativo' if tipo_plano_norm == 'P' else 'Coletivo'} | "
        f"Valor: R$ {valor_mensal:.2f}"
    )
    return True, msg_sucesso, novo_id


def adicionar_dependente(
    titular_nome: str,
    nome: str,
    grau_parentesco: str,
    data_nascimento: str | date,
    cpf: str = "",
) -> tuple[bool, str, Optional[int]]:
    """
    Adiciona um dependente ou agregado a um grupo familiar existente.
    Herda o tipo de plano do titular, enquadra automaticamente na faixa e mensalidade.
    Sincroniza com data/integrantes.csv.
    """
    titular_limpo = padronizar_nome(titular_nome)
    nome_limpo = padronizar_nome(nome)
    grau_limpo = padronizar_nome(grau_parentesco) or "Dependente"

    if not titular_limpo:
        return False, "Selecione o titular responsável pelo grupo.", None
    if not nome_limpo:
        return False, "Nome do dependente é obrigatório.", None

    with get_connection() as conn:
        # Busca o titular para herdar o tipo de plano
        titular_row = conn.execute(
            "SELECT tipo_plano FROM membros WHERE titular_nome = ? AND UPPER(tipo) = 'TITULAR' LIMIT 1",
            (titular_limpo,)
        ).fetchone()

        if not titular_row:
            return False, f"Titular '{titular_limpo}' não encontrado no cadastro.", None

        tipo_plano = titular_row["tipo_plano"] or "C"

        # Verifica duplicidade
        existe = conn.execute(
            "SELECT id FROM membros WHERE LOWER(beneficiario_nome) = LOWER(?)",
            (nome_limpo,)
        ).fetchone()
        if existe:
            return False, f"Já existe um integrante cadastrado com o nome '{nome_limpo}'.", None

    # Converte data de nascimento
    if isinstance(data_nascimento, date):
        data_iso = data_nascimento.strftime("%Y-%m-%d")
    else:
        dt_str = str(data_nascimento).strip()
        if "/" in dt_str:
            try:
                data_iso = datetime.strptime(dt_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                return False, "Data de nascimento inválida (use o formato DD/MM/AAAA).", None
        else:
            data_iso = dt_str

    idade = calcular_idade(data_iso)
    if idade is None:
        return False, "Não foi possível calcular a idade a partir da data informada.", None

    faixa = determinar_faixa_etaria(idade)
    if not faixa:
        return False, f"Nenhuma faixa etária cadastrada para a idade de {idade} anos.", None

    valor_mensal = faixa["valor_privativo"] if tipo_plano.upper() == "P" else faixa["valor_coletivo"]

    # Classificação
    tipo_membro = "AGREGADO" if "agregado" in grau_limpo.lower() else "DEPENDENTE"

    import re
    cpf_limpo = re.sub(r"\D", "", str(cpf))

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO membros (
                tipo, titular_nome, beneficiario_nome, grau_parentesco,
                data_nascimento, cpf, faixa_etaria, tipo_plano, valor_mensalidade
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tipo_membro,
            titular_limpo,
            nome_limpo,
            grau_limpo,
            data_iso,
            cpf_limpo,
            faixa["faixa_etaria"],
            tipo_plano,
            valor_mensal,
        ))
        novo_id = cursor.lastrowid
        _sincronizar_csv_com_banco(conn)

    msg_sucesso = (
        f"{tipo_membro.capitalize()} {nome_limpo} ({grau_limpo}) incluído(a) no grupo de {titular_limpo}! "
        f"Idade: {idade} anos | Faixa: {faixa['faixa_etaria']} | Valor: R$ {valor_mensal:.2f}"
    )
    return True, msg_sucesso, novo_id


def excluir_membro(membro_id: int) -> tuple[bool, str]:
    """
    Exclui um dependente/agregado específico do sistema pelo ID.
    Se for um titular, orienta a exclusão do grupo inteiro ou executa a exclusão.
    Sincroniza com data/integrantes.csv.
    """
    with get_connection() as conn:
        membro = conn.execute(
            "SELECT id, tipo, titular_nome, beneficiario_nome FROM membros WHERE id = ?",
            (membro_id,)
        ).fetchone()

        if not membro:
            return False, "Integrante não encontrado no banco de dados."

        nome = membro["beneficiario_nome"]
        tipo = membro["tipo"].upper()
        titular = membro["titular_nome"]

        if tipo == "TITULAR":
            # Conta se há dependentes vinculados
            deps_count = conn.execute(
                "SELECT COUNT(*) FROM membros WHERE titular_nome = ? AND id != ?",
                (titular, membro_id)
            ).fetchone()[0]

            if deps_count > 0:
                return False, f"O titular '{nome}' possui {deps_count} dependente(s) vinculado(s). Utilize a opção 'Excluir Grupo Familiar Completo' para remover o titular e seus dependentes."

        conn.execute("DELETE FROM membros WHERE id = ?", (membro_id,))
        conn.execute("DELETE FROM config_valores WHERE beneficiario_nome = ?", (nome,))
        _sincronizar_csv_com_banco(conn)
        _salvar_backup_precos(conn)

    return True, f"Integrante '{nome}' removido com sucesso do sistema."


def excluir_grupo_familiar(titular_nome: str) -> tuple[bool, str, int]:
    """
    Exclui um titular e TODOS os seus dependentes/agregados vinculados.
    Sincroniza com data/integrantes.csv.
    """
    titular_limpo = titular_nome.strip()
    with get_connection() as conn:
        membros = conn.execute(
            "SELECT id, beneficiario_nome FROM membros WHERE titular_nome = ?",
            (titular_limpo,)
        ).fetchall()

        if not membros:
            return False, f"Nenhum integrante encontrado para o titular '{titular_limpo}'.", 0

        total = len(membros)
        nomes = [m["beneficiario_nome"] for m in membros]

        conn.execute("DELETE FROM membros WHERE titular_nome = ?", (titular_limpo,))
        for n in nomes:
            conn.execute("DELETE FROM config_valores WHERE beneficiario_nome = ?", (n,))
        conn.execute("DELETE FROM uniodonto_titulares WHERE LOWER(titular_nome) = LOWER(?)", (titular_limpo,))

        _sincronizar_csv_com_banco(conn)
        _salvar_backup_precos(conn)

    return True, f"Grupo familiar de '{titular_limpo}' ({total} integrante(s)) excluído com sucesso.", total


# ─── GESTÃO DO PLANO ODONTOLÓGICO (UNIODONTO) ───────────────────────────────

def obter_config_uniodonto() -> dict:
    """Retorna a configuração vigente do plano Uniodonto (valor por vida)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT valor_por_vida, data_atualizacao FROM config_uniodonto ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return {
                "valor_por_vida": float(row["valor_por_vida"]),
                "data_atualizacao": str(row["data_atualizacao"]),
            }
        return {"valor_por_vida": 35.00, "data_atualizacao": ""}


def atualizar_valor_uniodonto(novo_valor: float) -> None:
    """Atualiza o valor por vida do plano Uniodonto e sincroniza com o arquivo permanente."""
    with get_connection() as conn:
        # Usa UPDATE no registro existente ao invés de INSERT append-only
        row = conn.execute("SELECT id FROM config_uniodonto ORDER BY id DESC LIMIT 1").fetchone()
        agora = datetime.now().isoformat()
        if row:
            conn.execute("""
                UPDATE config_uniodonto SET valor_por_vida = ?, data_atualizacao = ?
                WHERE id = ?
            """, (round(float(novo_valor), 2), agora, row["id"]))
        else:
            conn.execute("""
                INSERT INTO config_uniodonto (valor_por_vida, data_atualizacao)
                VALUES (?, ?)
            """, (round(float(novo_valor), 2), agora))
        _salvar_backup_precos(conn)


def reajustar_valor_uniodonto_percentual(percentual: float) -> float:
    """Aplica reajuste percentual sobre o valor vigente da Uniodonto e retorna o novo valor."""
    atual = obter_config_uniodonto()["valor_por_vida"]
    novo_valor = round(atual * (1 + percentual / 100), 2)
    atualizar_valor_uniodonto(novo_valor)
    return novo_valor


def obter_uniodonto_titular(titular_nome: str) -> dict | None:
    """
    Retorna os dados de Uniodonto para o titular informado.
    Retorna None se o titular não possuir o plano.
    """
    cfg = obter_config_uniodonto()
    valor_por_vida = cfg["valor_por_vida"]
    titular_limpo = padronizar_nome(titular_nome)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, titular_nome, vidas, data_atualizacao FROM uniodonto_titulares WHERE LOWER(titular_nome) = LOWER(?)",
            (titular_limpo,)
        ).fetchone()
        if not row:
            return None
        vidas = int(row["vidas"])
        return {
            "id": row["id"],
            "titular_nome": row["titular_nome"],
            "vidas": vidas,
            "valor_por_vida": valor_por_vida,
            "valor_total": round(vidas * valor_por_vida, 2),
            "data_atualizacao": str(row["data_atualizacao"]),
        }


def listar_todos_uniodonto() -> list[dict]:
    """Retorna todos os titulares com plano Uniodonto ativo com seus respectivos valores calculados."""
    cfg = obter_config_uniodonto()
    valor_por_vida = cfg["valor_por_vida"]

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, titular_nome, vidas, data_atualizacao FROM uniodonto_titulares ORDER BY titular_nome ASC"
        ).fetchall()
        resultado = []
        for r in rows:
            vidas = int(r["vidas"])
            resultado.append({
                "id": r["id"],
                "titular_nome": r["titular_nome"],
                "vidas": vidas,
                "valor_por_vida": valor_por_vida,
                "valor_total": round(vidas * valor_por_vida, 2),
                "data_atualizacao": str(r["data_atualizacao"]),
            })
        return resultado


def salvar_uniodonto_titular(titular_nome: str, vidas: int) -> tuple[bool, str]:
    """Inclui ou atualiza o titular no plano Uniodonto com o número de vidas informadas."""
    titular_limpo = padronizar_nome(titular_nome)
    if not titular_limpo:
        return False, "Nome do titular é obrigatório."
    if vidas <= 0:
        return False, "O número de vidas cobertas deve ser de no mínimo 1."

    cfg = obter_config_uniodonto()
    valor_total = round(vidas * cfg["valor_por_vida"], 2)

    with get_connection() as conn:
        # Verifica se titular existe na base de membros
        membro = conn.execute(
            "SELECT titular_nome FROM membros WHERE LOWER(titular_nome) = LOWER(?) LIMIT 1",
            (titular_limpo,)
        ).fetchone()
        nome_oficial = membro["titular_nome"] if membro else titular_limpo

        conn.execute("""
            INSERT INTO uniodonto_titulares (titular_nome, vidas, data_atualizacao)
            VALUES (?, ?, ?)
            ON CONFLICT(titular_nome) DO UPDATE SET
                vidas = excluded.vidas,
                data_atualizacao = excluded.data_atualizacao
        """, (nome_oficial, vidas, datetime.now().isoformat()))
        _salvar_backup_precos(conn)

    return True, f"Titular '{nome_oficial}' atualizado na Uniodonto com {vidas} vida(s) (Total: R$ {valor_total:.2f})."


def remover_uniodonto_titular(titular_nome: str) -> tuple[bool, str]:
    """Remove o titular do plano Uniodonto."""
    titular_limpo = titular_nome.strip()
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM uniodonto_titulares WHERE LOWER(titular_nome) = LOWER(?)",
            (titular_limpo,)
        )
        if cursor.rowcount == 0:
            return False, f"Titular '{titular_limpo}' não encontrado no cadastro da Uniodonto."
        _salvar_backup_precos(conn)
    return True, f"Titular '{titular_limpo}' removido com sucesso do plano Uniodonto."


