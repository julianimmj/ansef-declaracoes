"""
Módulo de sincronização automática com GitHub via API REST.
Permite que alterações feitas em runtime no Streamlit Cloud sejam
commitadas de volta ao repositório, garantindo persistência real.

Requer GITHUB_TOKEN (Personal Access Token) configurado em st.secrets
com permissão 'contents: write' no repositório.
"""
from __future__ import annotations

import os
import base64
import json
import logging
import threading
import time
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Configuração do repositório
REPO_OWNER = "julianimmj"
REPO_NAME = "ansef-declaracoes"
BRANCH = "main"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

# Arquivos que devem ser sincronizados
SYNC_FILES = [
    "data/config_precos.json",
    "data/solicitacoes_backup.json",
    "data/integrantes.csv",
]

# Lock reentrante para evitar commits simultâneos entre threads e botões manuais
_sync_lock = threading.RLock()


def _obter_token() -> str | None:
    """Obtém o token GitHub de st.secrets ou variáveis de ambiente."""
    try:
        import streamlit as st
        token = st.secrets.get("GITHUB_TOKEN", "")
        if token:
            return token
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN", "") or None


def _github_request(method: str, endpoint: str, token: str,
                    payload: dict | None = None,
                    extra_headers: dict | None = None) -> tuple[int, dict]:
    """Faz uma requisição à API do GitHub."""
    import urllib.request
    import urllib.error

    url = f"{API_BASE}/{endpoint}" if endpoint else API_BASE
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ANSEF-CAS-AutoSync/1.0",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if payload:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"message": str(e)}
        return e.code, body
    except Exception as e:
        return 0, {"message": str(e)}


def _obter_info_arquivo(filepath: str, token: str) -> tuple[str | None, str | None]:
    """
    Obtém o SHA e o conteúdo base64 atual de um arquivo no repositório.
    Usa timestamp na query string para evitar cache de proxies ou GitHub API.
    Retorna (sha, content_b64).
    """
    ts = int(time.time() * 1000)
    status, data = _github_request("GET", f"contents/{filepath}?ref={BRANCH}&_t={ts}", token)
    if status == 200:
        sha = data.get("sha")
        content = data.get("content", "")
        return sha, content
    return None, None


def sincronizar_arquivo(filepath: str, token: str | None = None,
                        commit_msg: str | None = None) -> tuple[bool, str]:
    """
    Sincroniza um arquivo local com o repositório GitHub via API com lock e retry automático.
    - Se o arquivo no GitHub já possui o mesmo conteúdo, evita commit desnecessário.
    - Se houver conflito de SHA (HTTP 409), tenta novamente com o SHA atualizado.
    """
    with _sync_lock:
        if not token:
            token = _obter_token()
        if not token:
            return False, "GITHUB_TOKEN não configurado nos Secrets."

        # Resolve o caminho absoluto do arquivo
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_path = os.path.join(base_dir, filepath)

        if not os.path.exists(abs_path):
            return False, f"Arquivo local não encontrado: {filepath}"

        try:
            with open(abs_path, "rb") as f:
                content_bytes = f.read()
            content_b64 = base64.b64encode(content_bytes).decode("ascii")
        except Exception as e:
            return False, f"Erro ao ler arquivo local: {e}"

        normal_local = content_b64.replace("\n", "").replace("\r", "")

        if not commit_msg:
            agora = datetime.now().strftime("%d/%m/%Y %H:%M")
            commit_msg = f"sync: {filepath} atualizado em {agora}"

        max_tentativas = 3
        for tentativa in range(1, max_tentativas + 1):
            # Obtém SHA e conteúdo atual
            sha, remote_content = _obter_info_arquivo(filepath, token)

            # Se o conteúdo remoto já é idêntico ao local, não precisa commitar!
            if remote_content:
                normal_remote = remote_content.replace("\n", "").replace("\r", "")
                if normal_remote == normal_local:
                    logger.info(f"Git sync ({filepath}): conteúdo já idêntico no GitHub, commit ignorado.")
                    return True, f"Arquivo {filepath} sincronizado com sucesso."

            payload = {
                "message": commit_msg,
                "content": content_b64,
                "branch": BRANCH,
            }
            if sha:
                payload["sha"] = sha

            status, data = _github_request("PUT", f"contents/{filepath}", token, payload)

            if status in (200, 201):
                logger.info(f"Git sync OK: {filepath} (tentativa {tentativa})")
                return True, f"Arquivo {filepath} sincronizado com sucesso."

            msg = data.get("message", f"HTTP {status}")
            logger.warning(f"Git sync tentativa {tentativa}/{max_tentativas} falhou ({filepath}): {msg}")

            # Se for conflito de SHA (HTTP 409 ou mensagem indicando mismatch de SHA), tenta extrair novo SHA ou aguarda e re-tenta
            if status == 409 or "is at" in msg or "does not match" in msg:
                # Tenta extrair o novo SHA diretamente da mensagem de erro se disponível
                match = re.search(r"is at ([0-9a-f]{40})", msg)
                if match:
                    sha_extraido = match.group(1)
                    logger.info(f"SHA extraído do erro: {sha_extraido}")
                time.sleep(0.5 * tentativa)
                continue
            else:
                # Outro erro que não é conflito de SHA
                return False, f"Falha ao sincronizar {filepath}: {msg}"

        return False, f"Falha ao sincronizar {filepath} após {max_tentativas} tentativas: {msg}"


def sincronizar_dados(commit_msg: str | None = None) -> tuple[bool, str]:
    """
    Sincroniza todos os arquivos de dados com o repositório GitHub.
    Usa um lock para evitar commits simultâneos de múltiplas threads.
    """
    if not _sync_lock.acquire(blocking=False):
        return True, "Sincronização já em andamento."

    try:
        token = _obter_token()
        if not token:
            return False, "GITHUB_TOKEN não configurado nos Secrets do Streamlit."

        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        if not commit_msg:
            commit_msg = f"sync: dados atualizados pelo admin em {agora}"

        resultados = []
        falhas = 0
        for filepath in SYNC_FILES:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            abs_path = os.path.join(base_dir, filepath)
            if os.path.exists(abs_path):
                ok, msg = sincronizar_arquivo(filepath, token, commit_msg)
                resultados.append(f"{'✅' if ok else '❌'} {filepath}: {msg}")
                if not ok:
                    falhas += 1

        resumo = "\n".join(resultados)
        if falhas == 0:
            return True, f"Todos os arquivos sincronizados com sucesso.\n{resumo}"
        else:
            return False, f"{falhas} arquivo(s) falharam na sincronização.\n{resumo}"
    finally:
        _sync_lock.release()


def verificar_configuracao() -> dict:
    """Verifica se o GITHUB_TOKEN está configurado e funcional."""
    token = _obter_token()
    if not token:
        return {
            "configurado": False,
            "token_presente": False,
            "repo_acessivel": False,
            "mensagem": "GITHUB_TOKEN não encontrado nos Secrets.",
        }

    # Testa acesso ao repositório
    status, data = _github_request("GET", "", token)
    repo_ok = status == 200

    return {
        "configurado": repo_ok,
        "token_presente": True,
        "repo_acessivel": repo_ok,
        "repo_nome": data.get("full_name", f"{REPO_OWNER}/{REPO_NAME}"),
        "mensagem": "Configuração OK" if repo_ok else f"Erro ao acessar repositório: {data.get('message', '')}",
    }
