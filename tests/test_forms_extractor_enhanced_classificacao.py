"""EnhancedFormsExtractor era natureza-agnostico e nao classificava
'Posicao'/'Contrario' -- campos que TODAS as naturezas (trabalhista e
civel) perguntam, so' com rotulos ligeiramente diferentes ('Posicao nos
autos do Cliente Principal' no civel, 'Posicao cliente principal' no
trabalhista). Sem essas duas entradas no mapeamento generico, o fallback
Enhanced nunca preenchia posicao/contrario -- caiam direto em
outros_dados com a pergunta crua como chave, que _merge_enhanced_data
nunca casava de volta com o campo canonico (31/08/2026)."""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# _classify_and_store e' puro matching de string, nao usa NLP de verdade --
# mas o modulo importa spacy no topo do arquivo, e o venv compartilhado do
# monorepo tem a stack do spacy quebrada (thinc com extensao compilada
# ausente). Mocka antes do import pra nao depender de um venv saudavel.
if "spacy" not in sys.modules:
    fake_spacy = types.ModuleType("spacy")
    fake_spacy.load = MagicMock(side_effect=OSError("mock: modelo nao instalado"))
    sys.modules["spacy"] = fake_spacy

from forms_extractor_enhanced import EnhancedFormsExtractor


def _classificar(pergunta: str, resposta: str) -> dict:
    extrator = EnhancedFormsExtractor.__new__(EnhancedFormsExtractor)
    data: dict = {}
    extrator._classify_and_store(pergunta, resposta, data)
    return data


def test_classifica_posicao_rotulo_trabalhista():
    data = _classificar("Posição cliente principal", "Reclamado")
    assert data.get("posicao") == "Reclamado"


def test_classifica_posicao_rotulo_civel():
    data = _classificar("Posição nos autos do Cliente Principal", "Autor")
    assert data.get("posicao") == "Autor"


def test_classifica_contrario_principal():
    data = _classificar("Contrário principal", "Empresa X Ltda")
    assert data.get("contrario") == "Empresa X Ltda"


def test_pergunta_sem_mapeamento_cai_em_outros_dados():
    data = _classificar("Alguma pergunta especifica sem mapeamento", "resposta")
    assert data.get("outros_dados", {}).get("Alguma pergunta especifica sem mapeamento") == "resposta"


def test_outros_envolvidos_nao_e_classificado_como_posicao():
    """Regressao achada pelo /ultrareview na PR: 'posição' sozinho tambem
    casava com 'Outros envolvidos e posição nos autos' (testemunha/
    terceiro, forms_mapping.py:166), e como essa pergunta vem DEPOIS da
    real 'Posição cliente principal' no DOM do civel
    (forms_mapping_civel.py:374 vs 384), sobrescrevia o valor certo
    (Autor/Reu) com nome de testemunha."""
    data = _classificar("Outros envolvidos e posição nos autos", "Testemunha Fulano")
    assert data.get("posicao") is None
    assert data.get("outros_dados", {}).get("Outros envolvidos e posição nos autos") == "Testemunha Fulano"

    data_civel = _classificar(
        "Outros envolvidos (se houver) e sua posição nos autos", "Testemunha Ciclana"
    )
    assert data_civel.get("posicao") is None


def test_ordem_no_dom_nao_sobrescreve_posicao_com_outros_envolvidos():
    """Simula a ordem real do formulario civel: pergunta de Posicao (linha
    374) vem antes de Outros envolvidos (linha 384) -- o valor certo tem
    que sobreviver ate' o fim do scan."""
    extrator = EnhancedFormsExtractor.__new__(EnhancedFormsExtractor)
    data: dict = {}
    extrator._classify_and_store("Posição nos autos do Cliente Principal", "Autor", data)
    extrator._classify_and_store("Outros envolvidos (se houver) e sua posição nos autos", "Testemunha", data)
    assert data.get("posicao") == "Autor"


if __name__ == "__main__":
    test_classifica_posicao_rotulo_trabalhista()
    test_classifica_posicao_rotulo_civel()
    test_classifica_contrario_principal()
    test_pergunta_sem_mapeamento_cai_em_outros_dados()
    test_outros_envolvidos_nao_e_classificado_como_posicao()
    test_ordem_no_dom_nao_sobrescreve_posicao_com_outros_envolvidos()
    print("ok")
