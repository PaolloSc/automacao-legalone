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


if __name__ == "__main__":
    test_classifica_posicao_rotulo_trabalhista()
    test_classifica_posicao_rotulo_civel()
    test_classifica_contrario_principal()
    test_pergunta_sem_mapeamento_cai_em_outros_dados()
    print("ok")
