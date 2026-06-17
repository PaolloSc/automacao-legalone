"""
Teste isolado: extrai dados do Forms e cadastra SOMENTE os pedidos no LegalOne.
O processo já deve estar cadastrado. Informe o CNJ e o link do Forms.

Uso:
    python teste_pedidos.py --cnj "0010307-23.2026.5.03.0089" --forms "https://forms.office.com/..."
    python teste_pedidos.py --cnj "0010307-23.2026.5.03.0089" --pedidos manual
"""

import argparse
import asyncio
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Importa extrator e cadastro
sys.path.insert(0, os.path.dirname(__file__))
from forms_extractor import FormsExtractor
from legalone_cadastro import LegalOneCadastro


async def extrair_forms(link: str) -> dict:
    extrator = FormsExtractor()
    dados = await extrator.extrair_dados_forms(link)
    logger.info(f"[FORMS] Dados extraídos: {list(dados.keys())}")
    # Loga outros_dados para debug
    outros = dados.get('outros_dados', {}) or {}
    for k, v in outros.items():
        if v:
            logger.info(f"  [{k}] = {str(v)[:120]}")
    return dados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cnj',    required=True,  help='Número CNJ do processo já cadastrado')
    ap.add_argument('--forms',  default='',     help='Link do Microsoft Forms')
    ap.add_argument('--pedidos', default='',    help='Texto de pedidos manual (alternativa ao Forms)')
    ap.add_argument('--contingencia', default='', help='Contingência: Ativa, Passiva ou Sem Contingência')
    ap.add_argument('--data-pedido', default='',  help='Data dos pedidos (dd/mm/yyyy)')
    ap.add_argument('--data-julgamento', default='', help='Data do julgamento (dd/mm/yyyy)')
    args = ap.parse_args()

    # Monta dados_processo
    dados_processo = {'cnj': args.cnj, 'outros_dados': {}}

    # Contingência e datas manuais
    if args.contingencia:
        dados_processo['contingencia'] = args.contingencia
    if args.data_pedido:
        dados_processo['data_distribuicao'] = args.data_pedido
    if args.data_julgamento:
        dados_processo['data_julgamento'] = args.data_julgamento

    if args.forms:
        logger.info(f"[FORMS] Extraindo dados de: {args.forms}")
        dados_forms = asyncio.run(extrair_forms(args.forms))
        dados_processo.update(dados_forms)
        dados_processo['cnj'] = args.cnj  # garante CNJ correto
        # Manter overrides manuais se fornecidos
        if args.contingencia:
            dados_processo['contingencia'] = args.contingencia
        if args.data_pedido:
            dados_processo['data_distribuicao'] = args.data_pedido
        if args.data_julgamento:
            dados_processo['data_julgamento'] = args.data_julgamento
    elif args.pedidos:
        # Permite passar texto de pedidos diretamente
        dados_processo['outros_dados']['Descreva todos os pedidos'] = args.pedidos
        logger.info("[MANUAL] Pedidos fornecidos manualmente.")
    else:
        logger.error("Forneça --forms ou --pedidos")
        sys.exit(1)

    # Log do texto de pedidos que será parseado
    cadastro = LegalOneCadastro(
        username=os.getenv('LEGALONE_USERNAME', ''),
        password=os.getenv('LEGALONE_PASSWORD', ''),
    )
    texto_pedidos = cadastro._extrair_texto_detalhes_pedidos(dados_processo)
    logger.info(f"[PEDIDOS] Texto extraído para parse:\n{texto_pedidos}")

    itens = cadastro._parse_pedidos_detalhados(texto_pedidos)
    if not itens:
        logger.error("[PEDIDOS] Nenhum pedido encontrado após parse. Verifique o formato.")
        logger.info("Formato esperado: <nome> - perda/ possível - R$X.XXX,XX")
        sys.exit(1)

    logger.info(f"[PEDIDOS] {len(itens)} pedido(s) parseado(s):")
    for i, it in enumerate(itens, 1):
        logger.info(f"  {i}. {it['pedido']} | {it['tipo']} | {it['grau']} | R${it['valor']}")

    # Inicializa navegador (já faz login automaticamente se necessário)
    if not cadastro.inicializar_navegador():
        logger.error("Falha ao inicializar navegador")
        sys.exit(1)

    # Verifica se login foi bem-sucedido (sem chamar fazer_login de novo)
    if "signon.thomsonreuters.com" in cadastro.page.url:
        logger.error("Login não completou. Verifique credenciais ou MFA.")
        sys.exit(1)

    logger.info(f"\n[INICIO] Abrindo processo {args.cnj} para cadastrar pedidos...")
    sucesso = cadastro.realizar_acoes_pos_cadastro(dados_processo)

    if sucesso:
        logger.info("\n✅ Pedidos cadastrados com sucesso!")
    else:
        logger.error("\n❌ Falha ao cadastrar pedidos.")


if __name__ == '__main__':
    main()
