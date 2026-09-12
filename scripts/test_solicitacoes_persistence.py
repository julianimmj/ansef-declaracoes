import os
import sys
import json
import sqlite3
import shutil

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import (
    inicializar_banco,
    listar_solicitacoes_aprovadas,
    obter_pdf_solicitacao,
    criar_solicitacao,
    aprovar_solicitacao,
    obter_solicitacao,
    DB_PATH,
    SOLICITACOES_BACKUP_PATH
)
from src.pdf_generator import gerar_pdf_declaracao

def test_persistence():
    print("=== Test 1: Verificar banco inicial e backup JSON ===")
    inicializar_banco()
    
    assert os.path.exists(SOLICITACOES_BACKUP_PATH), "solicitacoes_backup.json deve existir!"
    with open(SOLICITACOES_BACKUP_PATH, "r", encoding="utf-8") as f:
        backup = json.load(f)
    print(f"Total de solicitacoes no backup JSON: {len(backup)}")
    assert len(backup) >= 1, "Deve haver ao menos 1 solicitacao no backup!"
    
    aprovadas = listar_solicitacoes_aprovadas()
    print(f"Total de aprovadas no SQLite: {len(aprovadas)}")
    assert len(aprovadas) >= 1, "Deve haver ao menos 1 solicitacao aprovada!"
    
    sol1 = aprovadas[0]
    print(f"Aprovada #1: {sol1['titular_nome']} | Status: {sol1['status']}")
    assert sol1["status"] == "APROVADO"
    
    # Test PDF generation / retrieval
    pdf = obter_pdf_solicitacao(sol1["id"])
    assert pdf is not None and len(pdf) > 1000, f"PDF deve ter bytes validos! Obtido: {len(pdf) if pdf else 0}"
    print(f"PDF sintetizado e verificado com sucesso: {len(pdf)} bytes")

    print("\n=== Test 2: Simular criacao e aprovacao com sincronizacao automatica ===")
    # Cria solicitacao de teste
    nova_id = criar_solicitacao(
        titular_nome="TESTE PERSISTENCIA TITULAR",
        titular_cpf="11122233344",
        dependentes_json=json.dumps([{"nome": "TESTE PERSISTENCIA TITULAR", "parentesco": "Titular", "valor": 500.0}]),
        mes_ref=2,
        ano_ref=2026,
        data_pagamento="10/02/2026",
        valor_total=500.0
    )
    print(f"Nova solicitacao criada: #{nova_id}")
    
    # Verifica se apareceu no JSON
    with open(SOLICITACOES_BACKUP_PATH, "r", encoding="utf-8") as f:
        backup_pos_criacao = json.load(f)
    ids_no_json = [item["id"] for item in backup_pos_criacao]
    assert nova_id in ids_no_json, f"Solicitacao #{nova_id} deve estar no backup JSON!"
    print("Solicitacao sincronizada no JSON com sucesso!")
    
    # Aprova solicitacao
    pdf_bytes = gerar_pdf_declaracao(
        titular_nome="TESTE PERSISTENCIA TITULAR",
        titular_cpf="11122233344",
        dependentes_json=json.dumps([{"nome": "TESTE PERSISTENCIA TITULAR", "parentesco": "Titular", "valor": 500.0}]),
        mes_referencia=2,
        ano_referencia=2026,
        data_pagamento="10/02/2026",
        valor_total=500.0,
        codigo_validacao=f"ANSEF-2026-{nova_id:06d}"
    )
    aprovar_solicitacao(
        sol_id=nova_id,
        dependentes_json=json.dumps([{"nome": "TESTE PERSISTENCIA TITULAR", "parentesco": "Titular", "valor": 500.0}]),
        valor_total=500.0,
        data_pagamento="10/02/2026",
        mes_ref=2,
        ano_ref=2026,
        pdf_bytes=pdf_bytes
    )
    
    # Verifica status aprovado no JSON
    with open(SOLICITACOES_BACKUP_PATH, "r", encoding="utf-8") as f:
        backup_pos_aprov = json.load(f)
    sol_aprov = next(s for s in backup_pos_aprov if s["id"] == nova_id)
    assert sol_aprov["status"] == "APROVADO", "Status no JSON deve ser APROVADO!"
    print("Aprovacao refletida no backup JSON com sucesso!")

    # Limpeza do teste para deixar banco limpo com dados originais
    with sqlite3.connect(DB_PATH) as c:
        c.execute("DELETE FROM solicitacoes WHERE id = ?", (nova_id,))
    from src.database import _salvar_backup_solicitacoes
    _salvar_backup_solicitacoes()
    print("Item de teste limpo com sucesso.")

    print("\n=== Test 3: Simular Fresh Deploy (Novo banco SQLite vazio) ===")
    import src.database as db_mod
    original_db_path = db_mod.DB_PATH
    test_db_path = os.path.join(os.path.dirname(original_db_path), "test_fresh_db.sqlite")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    try:
        db_mod.DB_PATH = test_db_path
        print(f"Testando com banco virgem: {test_db_path}")
        db_mod.inicializar_banco()
        assert os.path.exists(test_db_path), "Novo banco SQLite deve ter sido criado!"
        
        aprovadas_recriadas = db_mod.listar_solicitacoes_aprovadas()
        print(f"Total de solicitacoes aprovadas restauradas do JSON: {len(aprovadas_recriadas)}")
        assert len(aprovadas_recriadas) >= 1, "Historico de aprovacoes deve ter sido restaurado do JSON!"
        assert any(a["titular_nome"] == "Vera Lucia Damasio Marques e S." for a in aprovadas_recriadas)
        print("Historico de Vera Lucia perfeitamente recuperado no banco virgem!")
    finally:
        db_mod.DB_PATH = original_db_path
        if os.path.exists(test_db_path):
            try:
                os.remove(test_db_path)
            except Exception:
                pass

    print("\n[OK] TODOS OS TESTES DE PERSISTENCIA PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    test_persistence()
