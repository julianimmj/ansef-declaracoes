"""
Módulo de autenticação e validação de acesso.
- Associados: validação por data de nascimento do titular.
- Administrador: validação por senha com fallback para secrets.toml.
"""
import streamlit as st
from datetime import date
from src.database import validar_nascimento_titular


def autenticar_associado(titular_nome: str, data_nascimento: date) -> bool:
    """
    Valida o acesso do associado comparando a data de nascimento
    informada com o cadastro do titular no banco de dados.
    """
    return validar_nascimento_titular(titular_nome, data_nascimento)


def login_associado(titular_nome: str, data_nascimento: date) -> bool:
    """
    Realiza login do associado e salva na sessão.
    Retorna True se autenticado com sucesso.
    """
    if autenticar_associado(titular_nome, data_nascimento):
        st.session_state["authenticated_user"] = titular_nome
        st.session_state["user_logged"] = True
        return True
    return False


def logout_associado():
    """Remove dados de sessão do associado."""
    for key in ["authenticated_user", "user_logged"]:
        if key in st.session_state:
            del st.session_state[key]


def is_associado_logado() -> bool:
    """Verifica se há um associado autenticado na sessão."""
    return st.session_state.get("user_logged", False)


def get_associado_logado() -> str | None:
    """Retorna o nome do titular autenticado ou None."""
    if is_associado_logado():
        return st.session_state.get("authenticated_user")
    return None


# ─── ADMINISTRADOR ────────────────────────────────────────────────────────────

def autenticar_admin(senha: str) -> bool:
    """
    Valida a senha do administrador.
    Prioriza st.secrets; caso não configurado, usa fallback fixo.
    """
    try:
        senha_correta = st.secrets.get("ADMIN_PASSWORD", "mbj172007")
    except Exception:
        senha_correta = "mbj172007"
    return senha == senha_correta


def login_admin(senha: str) -> bool:
    """Realiza login do administrador e salva na sessão."""
    if autenticar_admin(senha):
        st.session_state["admin_logged"] = True
        return True
    return False


def logout_admin():
    """Remove dados de sessão do administrador."""
    if "admin_logged" in st.session_state:
        del st.session_state["admin_logged"]


def is_admin_logado() -> bool:
    """Verifica se o administrador está autenticado na sessão."""
    return st.session_state.get("admin_logged", False)
