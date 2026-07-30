"""Guarda contra mojibake (UTF-8 salvo como cp1252) voltar pro codigo.

Bug real de producao (2026-07-27, CNJ 0000283-33.2024.5.08.0002): o literal
"capturado no orgao" estava gravado corrompido no fonte (o 'ó' virou dois
caracteres), entao nunca casava com o texto acentuado da tela,
`_opcao_exige_adicao_manual` retornava False, o bot clicava no contato
"Capturado no orgao" do Itau e o LegalOne desabilitava o Salvar.

(este arquivo nao pode conter exemplos literais de mojibake — ele se
escanearia a si mesmo e falharia)
"""
import re
from pathlib import Path

from legalone_cadastro import LegalOneCadastro

RAIZ = Path(__file__).resolve().parent.parent
IGNORAR = {'venv', '.venv', '__pycache__', 'browser_data', 'browser_data_fallback'}
RUN_NAO_ASCII = re.compile(r'[^\x00-\x7f]+')


def _mojibake(texto: str) -> list[str]:
    """Runs nao-ASCII que decodificam como UTF-8 -> eram bytes UTF-8 lidos como cp1252.

    Acento portugues legitimo nunca cai aqui: 'ção' -> 'çã' = 0xE7 0xE3, que
    nao e' UTF-8 valido (continuacao precisa estar em 0x80-0xBF).
    """
    achados = []
    for run in RUN_NAO_ASCII.findall(texto):
        try:
            if run.encode('cp1252').decode('utf-8') != run:
                achados.append(run)
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return achados


def _arquivos_py():
    yield from RAIZ.glob('*.py')
    for d in RAIZ.iterdir():
        if d.is_dir() and d.name not in IGNORAR:
            yield from (p for p in d.rglob('*.py') if not IGNORAR & set(p.parts))


def test_nenhum_arquivo_py_tem_mojibake():
    sujos = {}
    for py in sorted(set(_arquivos_py())):
        achados = _mojibake(py.read_text(encoding='utf-8-sig', errors='replace'))
        if achados:
            sujos[str(py.relative_to(RAIZ))] = sorted(set(achados))[:5]
    assert not sujos, f"mojibake de volta no codigo: {sujos}"


def test_deteccao_captura_orgao_casa_com_o_texto_real_da_tela():
    """O texto exato que o LegalOne mostra (screenshot de 2026-07-27)."""
    cad = object.__new__(LegalOneCadastro)
    alerta = ("O contato selecionado foi capturado no órgão e deve ser "
              "adicionado manualmente.")

    assert cad._texto_indica_captura_orgao(alerta) is True
    assert cad._opcao_exige_adicao_manual(
        {"nome": "Itau Unibanco S.A", "origem": "Capturado no órgão"}
    ) is True
    # nao pode dar falso positivo num contato normal
    assert cad._opcao_exige_adicao_manual(
        {"nome": "Itaú Unibanco S.A.", "origem": "Existente na base"}
    ) is False


def test_acento_legitimo_nao_e_confundido_com_mojibake():
    for ok in ("DECISÃO", "EXECUÇÃO FISCAL", "NÃO consta", "Contrário Principal",
               "órgão", "Posição", "sumaríssimo", "réu"):
        assert _mojibake(ok) == [], f"falso positivo em {ok!r}"
