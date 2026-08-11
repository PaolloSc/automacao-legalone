"""Ficha do processo: campos do Forms -> ids da tela de alteracao.

Os ids vem da tela real (varredura de 11/08/2026 do processo 830), nao de um
stub escrito a mao: id inventado ou sufixo errado (`_Value`/`_Id`/pelado)
quebra o teste, que e' exatamente o bug que ninguem ve em producao — o bot
loga '✓' e o LegalOne nao grava nada.

O fixture guarda so `id -> tinha valor?`, sem nenhum dado de cliente: a
captura em si e' gitignored (LGPD, repo publico). Para regerar depois de uma
varredura nova:  python tests/test_ficha_forms.py --gerar <form_*.html>

O que continua fora do alcance daqui: o clique no lookup/data e' Playwright de
verdade, entao esses dois sao espionados, nao executados.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legalone_cadastro import LegalOneCadastro  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'ficha_ids.json'
PREENCHIDO = 'ja-tinha-valor'


def dom_real():
    """id -> valor. Quem tinha valor na tela recebe um marcador generico."""
    campos = json.loads(FIXTURE.read_text(encoding='utf-8'))['campos']
    return {i: (PREENCHIDO if cheio else '') for i, cheio in campos.items()}


def _gerar(caminho_html: str) -> None:
    """Captura -> fixture anonimo. So a estrutura sobrevive."""
    html = Path(caminho_html).read_text(encoding='utf-8', errors='replace')
    dom = {}
    for tag in re.finditer(r'<(?:input|select)\b([^>]*)>', html, re.I):
        ident = re.search(r'\bid="([^"]+)"', tag.group(1))
        if ident:
            valor = re.search(r'\bvalue="([^"]*)"', tag.group(1))
            dom[ident.group(1)] = bool(valor and valor.group(1).strip())
    for tag in re.finditer(r'<textarea\b([^>]*)>(.*?)</textarea>', html, re.I | re.S):
        ident = re.search(r'\bid="([^"]+)"', tag.group(1))
        if ident:
            dom[ident.group(1)] = bool(tag.group(2).strip())
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps({
        'origem': caminho_html,
        'nota': 'So id -> tem-valor. Nenhum valor real: a captura e gitignored (LGPD).',
        'campos': dict(sorted(dom.items())),
    }, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'{len(dom)} ids -> {FIXTURE}')


class PageFake:
    """So o DOM: os mesmos ids e valores da captura, sem browser."""

    def __init__(self, valores):
        self.valores = dict(valores)

    def evaluate(self, script, arg=None):
        if '_ProcessoEntitySchema_' in script:  # _base_personalizado
            return [i for i in self.valores if i.startswith(f'{arg}_ProcessoEntitySchema_')]
        if 'return (el.value' in script:  # _estado_campo
            if arg not in self.valores:
                return 'ausente'
            return 'preenchido' if str(self.valores[arg]).strip() else 'vazio'
        if 'soVazio' in script:  # _preencher_texto_por_id
            id_campo, val, so_vazio = arg
            if id_campo not in self.valores:
                return 'ausente'
            if so_vazio and str(self.valores[id_campo]).strip():
                return 'ja-preenchido'
            self.valores[id_campo] = val
            return 'ok'
        raise AssertionError(f'script inesperado: {script[:60]}')


def _bot(valores=None):
    bot = LegalOneCadastro.__new__(LegalOneCadastro)
    bot.page = PageFake(dom_real() if valores is None else valores)
    return bot


def test_todo_id_das_tabelas_existe_no_dom_real():
    """O contrato que importa: os ids que o codigo monta existem na tela."""
    dom = dom_real()
    bot = _bot(dom)
    faltando = []

    for base, _ in LegalOneCadastro._FICHA_LOOKUPS:
        faltando += [i for i in (f'{base}Text', f'{base}Id') if i not in dom]
    for id_campo, _ in (LegalOneCadastro._FICHA_TEXTOS
                        + LegalOneCadastro._FICHA_DATAS):
        if id_campo not in dom:
            faltando.append(id_campo)

    for prefixo, _ in LegalOneCadastro._PERSONALIZADOS_LOOKUP:
        base = bot._base_personalizado(prefixo)
        faltando += ([f'{prefixo}(sem base)'] if not base else
                     [i for i in (f'{base}_Value', f'{base}_Id') if i not in dom])
    for prefixo, _ in (LegalOneCadastro._PERSONALIZADOS_TEXTO
                       + LegalOneCadastro._PERSONALIZADOS_DATA):
        base = bot._base_personalizado(prefixo)
        if base not in dom:
            faltando.append(f'{prefixo} -> {base!r}')
    for prefixo, _ in LegalOneCadastro._PERSONALIZADOS_MOEDA:
        base = bot._base_personalizado(prefixo)
        if f'{base}_Value' not in dom:
            faltando.append(f'{prefixo} -> {base!r}_Value')

    assert not faltando, faltando


def test_base_personalizado_resolve_por_prefixo():
    bot = _bot()
    assert bot._base_personalizado('Obra') == 'Obra_ProcessoEntitySchema_p3654_o830'
    # Lookup: `_Value`/`_Id`/`_Lookup` convivem e tem que dar uma base so.
    assert (bot._base_personalizado('SupermercadoLoja')
            == 'SupermercadoLoja_ProcessoEntitySchema_p3650_o830')
    # Outro processo: o `_o<id>` muda e continua resolvendo.
    assert _bot({'Obra_ProcessoEntitySchema_p3654_o1999': ''}) \
        ._base_personalizado('Obra').endswith('_o1999')


def test_base_personalizado_sem_campo_devolve_vazio():
    assert _bot({})._base_personalizado('Obra') == ''


def test_estado_campo_distingue_ausente_de_vazio():
    bot = _bot()
    assert bot._estado_campo('NumeroAntigo') == 'vazio'
    assert bot._estado_campo('DataDistribuicao') == 'preenchido'
    assert bot._estado_campo('CampoQueNaoExiste') == 'ausente'


def test_texto_nao_sobrescreve_valor_existente():
    bot = _bot()
    # NCliente ja veio do cadastro; o Forms nao pode apagar.
    ncliente = 'NCliente_ProcessoEntitySchema_p3652_o830'
    assert bot._preencher_texto_por_id(ncliente, '99') is False
    assert bot.page.valores[ncliente] == PREENCHIDO
    assert bot._preencher_texto_por_id(ncliente, '99', so_se_vazio=False) is True
    assert bot.page.valores[ncliente] == '99'


def test_ficha_so_mexe_no_que_esta_vazio_na_tela():
    """Respostas do Forms para TODO campo mapeado, contra a ficha 830 real."""
    bot = _bot()
    cliques = []
    bot._expandir_painel_do_campo = lambda i: cliques.append(('expandir', i))
    bot._preencher_lookup_por_id = (
        lambda texto, oculto, v: cliques.append(('lookup', oculto, v)) or True)
    bot._preencher_data_por_id = (
        lambda i, v: cliques.append(('data', i, v)) or True)
    bot._preencher_moedas_em_lote = (
        lambda lote: (cliques.append(('moeda', lote)) or (len(lote), [])))

    def responde(*campos):
        return ('1.234,56' if 'valor_adicional_provisao' in campos
                else 'RESPOSTA-FORMS')

    ok, falhas = bot._preencher_ficha_forms(responde)
    assert falhas == [], falhas

    tocados = {c[1] for c in cliques if c[0] != 'moeda'}
    # Vazios na captura: entram.
    assert 'ProcedimentoId' in tocados
    assert bot.page.valores['NumeroAntigo'] == 'RESPOSTA-FORMS'
    assert bot.page.valores['Obra_ProcessoEntitySchema_p3654_o830'] == 'RESPOSTA-FORMS'
    assert 'DataDaCitacao_ProcessoEntitySchema_p3655_o830' in tocados
    # Preenchidos na captura: nao encosta.
    assert 'TipoAcaoId' not in tocados
    assert 'DataDistribuicao' not in tocados
    # Envolvidos: o texto visivel chega vazio no HTML (o JS preenche depois).
    # Quem protege e' o hidden *Id — se o teste passar a olhar o *Text, o bot
    # troca o cliente do processo por uma resposta de memoria.
    for ident in ('Cliente_EnvolvidoId', 'Cliente_PosicaoEnvolvidoId',
                  'Contrario_EnvolvidoId', 'Responsavel_EnvolvidoId', 'ClasseId'):
        assert ident not in tocados, ident
    assert bot.page.valores['NCliente_ProcessoEntitySchema_p3652_o830'] == PREENCHIDO
    # Moeda vai em lote com so_vazio: quem barra a Provisao ja gravada e' a
    # propria rotina de moedas, nao o `alvo()` daqui.
    assert [c[1] for c in cliques if c[0] == 'moeda'] == [
        [{'id': 'Provisao_ProcessoEntitySchema_p3684_o830_Value',
          'num': 1234.56, 'so_vazio': True}]]
    assert ok > 0
    # Todo lookup/data clicado teve o painel expandido antes.
    for tipo, alvo, *_ in cliques:
        if tipo in ('lookup', 'data'):
            assert ('expandir', alvo.replace('Id', 'Text')) in cliques \
                or ('expandir', alvo) in cliques \
                or ('expandir', alvo.replace('_Id', '_Value')) in cliques, alvo


def test_tabelas_nao_tem_id_com_numero_de_processo_chumbado():
    """Id com `_o<num>` fixo so funcionaria no processo onde foi varrido."""
    for tabela in (LegalOneCadastro._FICHA_LOOKUPS,
                   LegalOneCadastro._FICHA_TEXTOS,
                   LegalOneCadastro._FICHA_DATAS,
                   LegalOneCadastro._PERSONALIZADOS_LOOKUP,
                   LegalOneCadastro._PERSONALIZADOS_TEXTO,
                   LegalOneCadastro._PERSONALIZADOS_DATA,
                   LegalOneCadastro._PERSONALIZADOS_MOEDA):
        for alvo, campos in tabela:
            assert not re.search(r'_o\d+', alvo), alvo
            assert campos and all(isinstance(c, str) for c in campos), alvo


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--gerar':
        _gerar(sys.argv[2])
        raise SystemExit(0)
    for nome, fn in sorted(globals().items()):
        if nome.startswith('test_'):
            fn()
            print(f'ok {nome}')
