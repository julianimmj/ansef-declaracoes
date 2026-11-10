"""
Script de testes para validação da tabela de faixas etárias, recálculo e migrações.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.database import (
    inicializar_banco,
    obter_tabela_faixas,
    buscar_grupo_familiar,
    listar_todas_migracoes,
    verificar_migracoes_grupo,
    atualizar_tabela_faixa,
    atualizar_tabela_faixas_lote,
    reajustar_tabela_faixas_percentual,
    recalcular_mensalidades_membros,
    listar_todos_membros,
    listar_titulares,
)


class TestFaixasEtarias(unittest.TestCase):
    def setUp(self):
        inicializar_banco()

    def test_tabela_faixas_carregada(self):
        faixas = obter_tabela_faixas()
        self.assertEqual(len(faixas), 10)
        
        precos_esperados = {
            "0 – 18 anos": (350.0, 250.0),
            "19 – 23 anos": (412.0, 295.0),
            "24 – 28 anos": (475.0, 340.0),
            "29 – 33 anos": (515.0, 368.0),
            "34 – 38 anos": (544.0, 389.0),
            "39 – 43 anos": (627.0, 448.0),
            "44 – 48 anos": (857.0, 612.0),
            "49 – 53 anos": (1183.0, 845.0),
            "54 – 58 anos": (1554.0, 1110.0),
            "Acima de 59 anos": (2094.0, 1496.0),
        }
        for f in faixas:
            nome = f["faixa_etaria"]
            self.assertIn(nome, precos_esperados)
            exp_p, exp_c = precos_esperados[nome]
            self.assertEqual(f["valor_privativo"], exp_p)
            self.assertEqual(f["valor_coletivo"], exp_c)

    def test_membros_migrados(self):
        migs = listar_todas_migracoes()
        nomes_migrados = {m["beneficiario_nome"]: m for m in migs}
        
        self.assertIn("Fabio de Paula Guerra", nomes_migrados)
        self.assertEqual(nomes_migrados["Fabio de Paula Guerra"]["idade_atual"], 49)
        self.assertEqual(nomes_migrados["Fabio de Paula Guerra"]["faixa_calculada"], "49 – 53 anos")
        self.assertEqual(nomes_migrados["Fabio de Paula Guerra"]["valor_faixa_atual"], 845.0)

        self.assertIn("Ivan Esteves Ribeiro Filho", nomes_migrados)
        self.assertEqual(nomes_migrados["Ivan Esteves Ribeiro Filho"]["idade_atual"], 54)
        self.assertEqual(nomes_migrados["Ivan Esteves Ribeiro Filho"]["faixa_calculada"], "54 – 58 anos")
        self.assertEqual(nomes_migrados["Ivan Esteves Ribeiro Filho"]["valor_faixa_atual"], 1110.0)

        self.assertIn("Danilo Soares Rosa", nomes_migrados)
        self.assertEqual(nomes_migrados["Danilo Soares Rosa"]["idade_atual"], 24)
        self.assertEqual(nomes_migrados["Danilo Soares Rosa"]["faixa_calculada"], "24 – 28 anos")
        self.assertEqual(nomes_migrados["Danilo Soares Rosa"]["valor_faixa_atual"], 340.0)

        self.assertIn("Renan Marçal Rodrigues", nomes_migrados)
        self.assertEqual(nomes_migrados["Renan Marçal Rodrigues"]["idade_atual"], 60)
        self.assertEqual(nomes_migrados["Renan Marçal Rodrigues"]["faixa_calculada"], "Acima de 59 anos")
        self.assertEqual(nomes_migrados["Renan Marçal Rodrigues"]["valor_faixa_atual"], 2094.0)

    def test_isencao_nestor_padilha(self):
        grupo = buscar_grupo_familiar("Ivan Esteves Ribeiro Filho")
        nestor = next(m for m in grupo if m["beneficiario_nome"] == "Nestor Padilha")
        self.assertEqual(nestor["valor_mensalidade"], 0.0)
        self.assertFalse(nestor["migrou_faixa"])

    def test_verificar_migracao_grupo(self):
        # Grupo com migração
        migs_fabio = verificar_migracoes_grupo("Fabio de Paula Guerra")
        self.assertEqual(len(migs_fabio), 1)
        self.assertEqual(migs_fabio[0]["beneficiario_nome"], "Fabio de Paula Guerra")

        # Grupo sem migração
        migs_carlos = verificar_migracoes_grupo("Carlos Sergio Praciano P.")
        self.assertEqual(len(migs_carlos), 0)

    def test_autorrecuperacao_tabelas_vazias_e_reajuste(self):
        import shutil
        import sqlite3
        import tempfile

        tmpdir = tempfile.mkdtemp(prefix="ansef_test_reaj_")
        try:
            tmp_db = os.path.join(tmpdir, "test.db")
            tmp_csv = os.path.join(tmpdir, "integrantes.csv")
            tmp_precos = os.path.join(tmpdir, "config_precos.json")
            base_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            shutil.copy2(os.path.join(base_data, "integrantes.csv"), tmp_csv)
            shutil.copy2(os.path.join(base_data, "config_precos.json"), tmp_precos)

            old_db = os.environ.get("ANSEF_DB_PATH")
            old_csv = os.environ.get("ANSEF_CSV_PATH")
            old_precos = os.environ.get("ANSEF_CONFIG_PRECOS_PATH")
            os.environ["ANSEF_DB_PATH"] = tmp_db
            os.environ["ANSEF_CSV_PATH"] = tmp_csv
            os.environ["ANSEF_CONFIG_PRECOS_PATH"] = tmp_precos
            try:
                inicializar_banco()
                # Simula esvaziamento acidental das tabelas (rollback de inicialização interrompida)
                conn = sqlite3.connect(tmp_db)
                conn.execute("DELETE FROM tabela_faixas_etarias")
                conn.execute("DELETE FROM membros")
                conn.commit()
                conn.close()

                # Verifica que obter_tabela_faixas e listar_titulares se autorrecuperam imediatamente
                faixas_rec = obter_tabela_faixas()
                self.assertEqual(len(faixas_rec), 10)
                titulares_rec = listar_titulares()
                self.assertEqual(len(titulares_rec), 17)
                membros_rec = listar_todos_membros()
                self.assertEqual(len(membros_rec), 35)

                # Testa reajuste percentual em lote sem perda de registros
                recalc_cnt = reajustar_tabela_faixas_percentual(4.22)
                self.assertEqual(recalc_cnt, 34)  # 35 membros menos 1 isento (Nestor Padilha)
                faixas_pos = obter_tabela_faixas()
                self.assertEqual(len(faixas_pos), 10)
                self.assertAlmostEqual(faixas_pos[0]["valor_privativo"], 364.77, places=2)
                self.assertAlmostEqual(faixas_pos[0]["valor_coletivo"], 260.55, places=2)

                # Testa atualização em lote de volta aos valores originais
                lote = {fx["id"]: (350.0, 250.0) for fx in faixas_pos[:1]}
                atualizar_tabela_faixas_lote(lote)
                self.assertAlmostEqual(obter_tabela_faixas()[0]["valor_privativo"], 350.0, places=2)
            finally:
                for k, v in (
                    ("ANSEF_DB_PATH", old_db),
                    ("ANSEF_CSV_PATH", old_csv),
                    ("ANSEF_CONFIG_PRECOS_PATH", old_precos),
                ):
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
