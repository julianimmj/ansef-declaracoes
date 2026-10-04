"""
Teste abrangente da funcionalidade de Declaração Anual de Pagamento.
Testa:
- Criação de solicitação anual (PENDENTE)
- Listagem por titular e pendentes
- Formatação de meses (normalizar, descrever, abreviar)
- Geração de código de autenticidade anual
- Geração do documento PDF anual com template Jinja2/xhtml2pdf
- Aprovação pela administração
- Obtenção do PDF
- Cancelamento/revogação da aprovação
- Rejeição com justificativa
- Exportação e importação de backup JSON
"""
import sys
import os
import json
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)

from src.database import (
    inicializar_banco,
    criar_declaracao_anual,
    listar_declaracoes_anuais_titular,
    listar_declaracoes_anuais_pendentes,
    listar_declaracoes_anuais_aprovadas,
    listar_todas_declaracoes_anuais,
    contar_declaracoes_anuais_pendentes,
    aprovar_declaracao_anual,
    rejeitar_declaracao_anual,
    cancelar_declaracao_anual,
    obter_pdf_declaracao_anual,
    exportar_backup_anuais_json,
    importar_backup_anuais_json,
)
from src.pdf_generator import gerar_pdf_declaracao_anual
from src.utils import (
    normalizar_meses,
    descrever_meses,
    abreviar_meses,
    gerar_codigo_validacao_anual,
)

class TestDeclaracaoAnual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inicializar_banco()

    def test_utils_meses(self):
        # Normalização
        self.assertEqual(normalizar_meses([1, 2, 3]), [1, 2, 3])
        self.assertEqual(normalizar_meses("[4, 5, 6]"), [4, 5, 6])
        self.assertEqual(normalizar_meses([12, 1, 5, 1]), [1, 5, 12])
        self.assertEqual(normalizar_meses(["1", "2"]), [1, 2])

        # Descrição por extenso
        self.assertEqual(descrever_meses(list(range(1, 13))), "janeiro a dezembro")
        self.assertEqual(descrever_meses([1, 2, 3]), "janeiro a março")
        self.assertEqual(descrever_meses([1, 2, 3, 7]), "janeiro a março e julho")
        self.assertEqual(descrever_meses([2, 5]), "fevereiro e maio")

        # Abreviação
        self.assertEqual(abreviar_meses(list(range(1, 13))), "Ano completo (12 meses)")
        self.assertEqual(abreviar_meses([1, 2, 3]), "Jan–Mar")
        self.assertEqual(abreviar_meses([1, 3, 5]), "Jan, Mar, Mai")

    def test_codigo_validacao_anual(self):
        cod = gerar_codigo_validacao_anual(99, 2026)
        self.assertTrue(cod.startswith("ANSEF-A2026-"))
        self.assertEqual(len(cod), len("ANSEF-A2026-") + 8)

    def test_fluxo_completo_declaracao_anual(self):
        titular = "ASSOCIADO TESTE ANUAL SILVA"
        cpf = "12345678901"
        ano = 2025
        meses = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        beneficiarios = [
            {
                "nome": titular,
                "parentesco": "Titular",
                "valor_mensal": 650.00,
                "qtd_meses": 12,
                "valor_total": 7800.00,
            },
            {
                "nome": "DEPENDENTE TESTE ANUAL SILVA",
                "parentesco": "Filho(a)",
                "valor_mensal": 320.00,
                "qtd_meses": 12,
                "valor_total": 3840.00,
            },
        ]
        valor_total = 7800.00 + 3840.00

        # 1. Criação
        dec_id = criar_declaracao_anual(
            titular_nome=titular,
            titular_cpf=cpf,
            ano_ref=ano,
            meses_json=json.dumps(meses),
            beneficiarios_json=json.dumps(beneficiarios),
            valor_total=valor_total,
        )
        self.assertGreater(dec_id, 0)

        # 2. Listagem de pendentes
        pendentes = listar_declaracoes_anuais_pendentes()
        ids_pend = [p["id"] for p in pendentes]
        self.assertIn(dec_id, ids_pend)

        # 3. Listagem por titular
        do_titular = listar_declaracoes_anuais_titular(titular)
        self.assertTrue(any(d["id"] == dec_id for d in do_titular))
        reg = next(d for d in do_titular if d["id"] == dec_id)
        self.assertEqual(reg["status"], "PENDENTE")
        self.assertEqual(reg["ano_referencia"], ano)
        self.assertEqual(reg["valor_total"], valor_total)

        # 4. Geração do PDF
        cod_val = reg["codigo_validacao"]
        pdf_bytes = gerar_pdf_declaracao_anual(
            titular_nome=titular,
            titular_cpf=cpf,
            beneficiarios_json=json.dumps(beneficiarios),
            meses_json=json.dumps(meses),
            ano_referencia=ano,
            valor_total=valor_total,
            codigo_validacao=cod_val,
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # 5. Aprovação
        aprovar_declaracao_anual(
            dec_id=dec_id,
            ano_ref=ano,
            meses_json=json.dumps(meses),
            beneficiarios_json=json.dumps(beneficiarios),
            valor_total=valor_total,
            pdf_bytes=pdf_bytes,
        )

        # 6. Verifica aprovadas
        aprovadas = listar_declaracoes_anuais_aprovadas()
        ids_aprov = [a["id"] for a in aprovadas]
        self.assertIn(dec_id, ids_aprov)

        # 7. Obtenção do PDF
        pdf_salvo = obter_pdf_declaracao_anual(dec_id)
        self.assertIsNotNone(pdf_salvo)
        self.assertEqual(len(pdf_salvo), len(pdf_bytes))

        # 8. Cancelamento
        cancelar_declaracao_anual(dec_id, motivo="Cancelamento de teste unitário")
        pdf_apos_canc = obter_pdf_declaracao_anual(dec_id)
        self.assertIsNone(pdf_apos_canc)

        todos_reg = listar_todas_declaracoes_anuais()
        reg_canc = next(d for d in todos_reg if d["id"] == dec_id)
        self.assertEqual(reg_canc["status"], "CANCELADO")
        self.assertIn("Cancelamento de teste unitário", reg_canc["observacoes_admin"])

    def test_rejeicao_declaracao_anual(self):
        titular = "ASSOCIADO REJEICAO TESTE"
        cpf = "99988877766"
        dec_id = criar_declaracao_anual(
            titular_nome=titular,
            titular_cpf=cpf,
            ano_ref=2024,
            meses_json=json.dumps([1, 2]),
            beneficiarios_json=json.dumps([{"nome": titular, "parentesco": "Titular", "valor_mensal": 500, "qtd_meses": 2, "valor_total": 1000}]),
            valor_total=1000.0,
        )
        rejeitar_declaracao_anual(dec_id, observacoes="Valores divergentes do extrato")
        decs = listar_declaracoes_anuais_titular(titular)
        reg = next(d for d in decs if d["id"] == dec_id)
        self.assertEqual(reg["status"], "REJEITADO")
        self.assertEqual(reg["observacoes_admin"], "Valores divergentes do extrato")

    def test_backup_export_import_anuais(self):
        json_str = exportar_backup_anuais_json()
        self.assertTrue(isinstance(json_str, str))
        dados = json.loads(json_str)
        self.assertTrue(isinstance(dados, list))
        # Testa importação (idempotente)
        ok, msg, qtd = importar_backup_anuais_json(json_str)
        self.assertTrue(ok)
        self.assertEqual(qtd, 0) # Já existiam no banco

    @classmethod
    def tearDownClass(cls):
        from src.database import get_connection, _salvar_backup_anuais
        with get_connection() as conn:
            conn.execute("DELETE FROM declaracoes_anuais WHERE titular_nome LIKE '%TESTE%'")
            _salvar_backup_anuais(conn, sync_git=False)

if __name__ == "__main__":
    unittest.main()

