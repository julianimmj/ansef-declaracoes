import os
import sys
import tempfile
import shutil
import pandas as pd
from datetime import date

# Configura ambiente de teste isolado para não afetar o banco e CSV de produção
test_dir = tempfile.mkdtemp()
test_db = os.path.join(test_dir, "test_ansef.db")
test_precos = os.path.join(test_dir, "test_precos.json")
test_solic = os.path.join(test_dir, "test_solic.json")
test_csv = os.path.join(test_dir, "test_integrantes.csv")

prod_db = os.path.join(os.path.dirname(__file__), "..", "data", "ansef_database.db")
if os.path.exists(prod_db):
    shutil.copyfile(prod_db, test_db)

prod_csv = os.path.join(os.path.dirname(__file__), "..", "data", "integrantes.csv")
if os.path.exists(prod_csv):
    shutil.copyfile(prod_csv, test_csv)

os.environ["ANSEF_DB_PATH"] = test_db
os.environ["ANSEF_CONFIG_PRECOS_PATH"] = test_precos
os.environ["ANSEF_SOLICITACOES_BACKUP_PATH"] = test_solic
os.environ["ANSEF_CSV_PATH"] = test_csv

# Ensure src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import (
    inicializar_banco,
    adicionar_titular,
    adicionar_dependente,
    excluir_membro,
    excluir_grupo_familiar,
    listar_todos_membros,
    buscar_grupo_familiar,
    calcular_idade,
    determinar_faixa_etaria,
    CSV_PATH
)

def run_tests():
    inicializar_banco()
    excluir_grupo_familiar("Teste Titular Automacao")
    print("--- 1. Testing Age & Faixa Enquadramento ---")
    d1 = "1980-05-15"
    idade1 = calcular_idade(d1)
    fx1 = determinar_faixa_etaria(idade1)
    assert fx1 is not None, "Faixa etária não encontrada!"
    faixa1 = fx1["faixa_etaria"]
    p1 = fx1["valor_privativo"]
    c1 = fx1["valor_coletivo"]
    print(f"Nascimento {d1} -> Idade {idade1} anos -> Faixa: {faixa1}, P: R$ {p1:.2f}, C: R$ {c1:.2f}")
    assert p1 > 0 and c1 > 0, "Valores de mensalidade inválidos!"

    d2 = "2015-10-20"
    idade2 = calcular_idade(d2)
    fx2 = determinar_faixa_etaria(idade2)
    assert fx2 is not None
    faixa2 = fx2["faixa_etaria"]
    p2 = fx2["valor_privativo"]
    c2 = fx2["valor_coletivo"]
    print(f"Nascimento {d2} -> Idade {idade2} anos -> Faixa: {faixa2}, P: R$ {p2:.2f}, C: R$ {c2:.2f}")
    assert "0 – 18" in faixa2, f"Esperado 0-18, obtido {faixa2}"
    assert p2 == 350.0 and c2 == 250.0

    print("\n--- 2. Testing Inclusão de Novo Titular ---")
    nome_titular_input = "TESTE TITULAR AUTOMACAO"
    nome_titular_esperado = "Teste Titular Automacao"
    cpf_titular = "999.888.777-66"
    sucesso, msg, mid = adicionar_titular(
        nome=nome_titular_input,
        data_nascimento=d1,
        cpf=cpf_titular,
        tipo_plano="P"
    )
    print(f"Resultado adicionar_titular: sucesso={sucesso}, msg='{msg}', id={mid}")
    assert sucesso, f"Falha ao adicionar titular: {msg}"
    assert mid is not None

    todos = listar_todos_membros()
    membro_inserido = next((m for m in todos if m["id"] == mid), None)
    assert membro_inserido is not None, "Titular não encontrado por ID!"
    assert membro_inserido["beneficiario_nome"] == nome_titular_esperado, f"Esperado {nome_titular_esperado}, obtido {membro_inserido['beneficiario_nome']}"
    assert membro_inserido["tipo_plano"] == "P"
    assert membro_inserido["grau_parentesco"] == "Titular"
    assert membro_inserido["faixa_etaria"] == faixa1
    assert float(membro_inserido["valor_mensalidade"]) == p1
    print(f"Titular verificado com sucesso: Faixa={membro_inserido['faixa_etaria']}, Valor=R$ {membro_inserido['valor_mensalidade']}")

    print("\n--- 3. Testing Inclusão de Dependente ---")
    nome_dep_input = "TESTE DEPENDENTE FILHO"
    nome_dep_esperado = "Teste Dependente Filho"
    cpf_dep = "999.888.777-55"
    sucesso_dep, msg_dep, mid_dep = adicionar_dependente(
        titular_nome=nome_titular_esperado,
        nome=nome_dep_input,
        grau_parentesco="Filho(a)",
        data_nascimento=d2,
        cpf=cpf_dep
    )
    print(f"Resultado adicionar_dependente: sucesso={sucesso_dep}, msg='{msg_dep}', id={mid_dep}")
    assert sucesso_dep, f"Falha ao adicionar dependente: {msg_dep}"
    assert mid_dep is not None

    todos = listar_todos_membros()
    dep_inserido = next((m for m in todos if m["id"] == mid_dep), None)
    assert dep_inserido is not None, "Dependente não encontrado por ID!"
    assert dep_inserido["beneficiario_nome"] == nome_dep_esperado
    assert dep_inserido["tipo_plano"] == "P" # Herdado do titular
    assert dep_inserido["grau_parentesco"] == "Filho(a)"
    assert dep_inserido["faixa_etaria"] == faixa2
    assert float(dep_inserido["valor_mensalidade"]) == p2
    print(f"Dependente verificado com sucesso: Faixa={dep_inserido['faixa_etaria']}, Valor=R$ {dep_inserido['valor_mensalidade']}")

    print("\n--- 4. Testing CSV Synchronization ---")
    csv_path = test_csv
    df_csv = pd.read_csv(csv_path)
    nomes_col = [c for c in df_csv.columns if c.upper() == "NOME"][0]
    assert nome_titular_esperado in df_csv[nomes_col].values, "Titular não encontrado no CSV!"
    assert nome_dep_esperado in df_csv[nomes_col].values, "Dependente não encontrado no CSV!"
    print("CSV contém o titular e o dependente recém inseridos!")

    print("\n--- 5. Testing Exclusão de Dependente ---")
    sucesso_exc_dep, msg_exc_dep = excluir_membro(mid_dep)
    print(f"Resultado excluir_membro: sucesso={sucesso_exc_dep}, msg='{msg_exc_dep}'")
    assert sucesso_exc_dep, f"Falha ao excluir dependente: {msg_exc_dep}"

    todos_apos_exc = listar_todos_membros()
    assert not any(m["id"] == mid_dep for m in todos_apos_exc), "Dependente ainda existe após exclusão!"

    df_csv_dep = pd.read_csv(csv_path)
    assert nome_dep_esperado not in df_csv_dep[nomes_col].values, "Dependente ainda consta no CSV após exclusão!"
    print("Dependente excluído e CSV atualizado com sucesso!")

    print("\n--- 6. Testing Inclusão de Segundo Dependente e Exclusão do Grupo Inteiro ---")
    adicionar_dependente(
        titular_nome=nome_titular_esperado,
        nome=nome_dep_input,
        grau_parentesco="Filho(a)",
        data_nascimento=d2,
        cpf=cpf_dep
    )
    sucesso_grupo, msg_grupo, total_removidos = excluir_grupo_familiar(nome_titular_esperado)
    print(f"Resultado excluir_grupo_familiar: sucesso={sucesso_grupo}, msg='{msg_grupo}', removidos={total_removidos}")
    assert sucesso_grupo, f"Falha ao excluir grupo familiar: {msg_grupo}"
    assert total_removidos == 2, f"Esperado 2 membros removidos, obtido {total_removidos}"

    todos_apos_grupo = listar_todos_membros()
    assert not any(m["beneficiario_nome"] == nome_titular_esperado for m in todos_apos_grupo), "Titular ainda existe após excluir grupo!"
    assert not any(m["beneficiario_nome"] == nome_dep_esperado for m in todos_apos_grupo), "Dependente ainda existe após excluir grupo!"

    df_csv_final = pd.read_csv(csv_path)
    assert nome_titular_esperado not in df_csv_final[nomes_col].values, "Titular ainda consta no CSV!"
    assert nome_dep_esperado not in df_csv_final[nomes_col].values, "Dependente ainda consta no CSV!"
    print("Grupo familiar completamente removido do banco e CSV!")

    print("\n[OK] TODOS OS TESTES PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    try:
        run_tests()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
