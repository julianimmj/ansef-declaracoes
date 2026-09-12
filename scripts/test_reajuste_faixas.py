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
    reajustar_tabela_faixas_percentual,
    recalcular_mensalidades_membros,
    listar_todos_membros,
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


if __name__ == "__main__":
    unittest.main()
