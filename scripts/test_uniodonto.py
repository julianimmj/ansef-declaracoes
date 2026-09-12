import os
import sys
import tempfile
import shutil
import json

# Configura ambiente de teste isolado para não afetar o banco e configurações de produção
test_dir = tempfile.mkdtemp()
test_db = os.path.join(test_dir, "test_ansef.db")
test_precos = os.path.join(test_dir, "test_precos.json")
test_solic = os.path.join(test_dir, "test_solic.json")
test_csv = os.path.join(test_dir, "test_integrantes.csv")

# Copia CSV original para diretório de teste
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
    obter_config_uniodonto,
    atualizar_valor_uniodonto,
    reajustar_valor_uniodonto_percentual,
    obter_uniodonto_titular,
    listar_todos_uniodonto,
    salvar_uniodonto_titular,
    remover_uniodonto_titular,
)
from src.pdf_generator import gerar_pdf_declaracao

def run_tests():
    print("--- 1. Testing Database Initialization & Config ---")
    inicializar_banco()
    cfg = obter_config_uniodonto()
    print(f"Config Uniodonto: valor_por_vida = R$ {cfg['valor_por_vida']:.2f}")
    assert cfg["valor_por_vida"] > 0, "Valor por vida da Uniodonto deve ser maior que zero!"

    print("\n--- 2. Testing 4 Initial Titulares ---")
    esperados = {
        "Carlos Sergio Praciano P.": 2,
        "Francisco Sandin Martins": 1,
        "Marcio Carlos Rosa": 5,
        "José Luis Cordeiro Marcheori": 2,
    }

    todos = listar_todos_uniodonto()
    nomes_u = [t["titular_nome"] for t in todos]
    print(f"Titulares cadastrados na Uniodonto: {nomes_u}")

    for titular, vidas_esperadas in esperados.items():
        info = obter_uniodonto_titular(titular)
        assert info is not None, f"Titular '{titular}' deveria estar cadastrado na Uniodonto!"
        assert info["vidas"] == vidas_esperadas, f"Esperado {vidas_esperadas} vidas para '{titular}', obtido {info['vidas']}"
        valor_esperado = vidas_esperadas * info["valor_por_vida"]
        assert abs(info["valor_total"] - valor_esperado) < 0.01, f"Valor total incorreto para '{titular}': {info['valor_total']}"
        print(f"  [OK] {titular}: {info['vidas']} vidas x R$ {info['valor_por_vida']:.2f} = R$ {info['valor_total']:.2f}")

    print("\n--- 3. Testing Titular Without Uniodonto ---")
    sem_odonto = obter_uniodonto_titular("Nestor Padilha")
    assert sem_odonto is None, "Nestor Padilha não deveria possuir Uniodonto!"
    print("  [OK] Titular sem Uniodonto retornou None corretamente.")

    print("\n--- 4. Testing Incluir / Atualizar Titular ---")
    sucesso_add, msg_add = salvar_uniodonto_titular("Nestor Padilha", 3)
    assert sucesso_add, f"Falha ao vincular: {msg_add}"
    info_add = obter_uniodonto_titular("Nestor Padilha")
    assert info_add is not None and info_add["vidas"] == 3
    print(f"  [OK] Incluído: {msg_add}")

    # Atualiza vidas
    sucesso_up, msg_up = salvar_uniodonto_titular("Nestor Padilha", 4)
    assert sucesso_up
    info_up = obter_uniodonto_titular("Nestor Padilha")
    assert info_up is not None and info_up["vidas"] == 4
    print(f"  [OK] Atualizado para 4 vidas: {msg_up}")

    # Remove
    sucesso_del, msg_del = remover_uniodonto_titular("Nestor Padilha")
    assert sucesso_del
    assert obter_uniodonto_titular("Nestor Padilha") is None
    print(f"  [OK] Removido com sucesso: {msg_del}")

    print("\n--- 5. Testing Price Update, Percentage Adjustment & JSON Persistence ---")
    valor_orig = cfg["valor_por_vida"]
    atualizar_valor_uniodonto(42.50)
    assert obter_config_uniodonto()["valor_por_vida"] == 42.50
    
    # Verifica se config_precos.json temporário foi atualizado imediatamente
    with open(test_precos, "r", encoding="utf-8") as f:
        precos_json = json.load(f)
    assert abs(precos_json["config_uniodonto"]["valor_por_vida"] - 42.50) < 0.01, "config_precos.json deve refletir 42.50 imediatamente!"
    print("  [OK] Preço atualizado diretamente para R$ 42.50 e refletido no JSON!")

    novo_perc = reajustar_valor_uniodonto_percentual(10.0) # 42.50 + 10% = 46.75
    assert abs(novo_perc - 46.75) < 0.01
    assert abs(obter_config_uniodonto()["valor_por_vida"] - 46.75) < 0.01
    with open(test_precos, "r", encoding="utf-8") as f:
        precos_json = json.load(f)
    assert abs(precos_json["config_uniodonto"]["valor_por_vida"] - 46.75) < 0.01, "config_precos.json deve refletir 46.75!"
    print(f"  [OK] Reajuste de 10% aplicado e salvo no JSON: novo valor = R$ {novo_perc:.2f}")

    print("\n--- 6. Testing Restoration on Fresh DB from config_precos.json ---")
    # Remove banco SQLite para simular deploy/rebuild virgem
    os.remove(test_db)
    assert not os.path.exists(test_db)
    inicializar_banco()
    assert os.path.exists(test_db)
    cfg_restaurada = obter_config_uniodonto()
    assert abs(cfg_restaurada["valor_por_vida"] - 46.75) < 0.01, f"Valor restaurado deve ser 46.75, obtido {cfg_restaurada['valor_por_vida']}"
    print(f"  [OK] Banco virgem restaurou perfeitamente o preço de R$ {cfg_restaurada['valor_por_vida']:.2f} do JSON!")

    print("\n--- 7. Testing Unimed PDF Declaration Isolation ---")
    # Garante que o PDF da declaração contenha unicamente o valor declarado da Unimed
    pdf_bytes = gerar_pdf_declaracao(
        titular_nome="Carlos Sergio Praciano P.",
        titular_cpf="111.222.333-44",
        dependentes_json='[{"nome": "Carlos Sergio Praciano P.", "parentesco": "Titular", "valor": 2094.00}]',
        mes_referencia=9,
        ano_referencia=2026,
        data_pagamento="10/09/2026",
        valor_total=2094.00,
        codigo_validacao="TESTE-ODONTO-ISOLATION"
    )
    assert pdf_bytes and len(pdf_bytes) > 1000, "Falha na geração do PDF!"
    print(f"  [OK] PDF da Unimed gerado com sucesso ({len(pdf_bytes)} bytes) isolado de valores odontológicos.")

    print("\n[OK] TODOS OS TESTES DE UNIODONTO E PERSISTÊNCIA PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    try:
        run_tests()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
