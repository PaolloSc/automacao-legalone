"""Regressao: classificar_processo tinha parse manual de JSON dentro de
```json``` que podia falhar silenciosamente e cair num fallback generico.
Agora usa tool-calling forcado do LangChain (structured output) quando ha'
um provedor com chave estatica configurado; sem isso (fluxo OAuth puro),
cai pro parse legado (18/08/2026).

Achado ao vivo: deepseek-v4-pro roda em "thinking mode" e recusa
tool_choice forcado — a chamada estruturada usa deepseek-chat
especificamente por isso."""
from unittest.mock import MagicMock, patch

from claude_brain import ClaudeBrain, ClassificacaoProcesso


def test_usa_structured_output_quando_ha_deepseek_key():
    b = ClaudeBrain.__new__(ClaudeBrain)
    b._deepseek_key = "fake-key"
    b._api_key = "fake-key"
    b.model = "deepseek-v4-pro"
    b.temperature = 0.3

    resultado_fake = ClassificacaoProcesso(
        tipo_tarefa="RECURSO", prioridade="ALTA", classificacao="teste",
        campos_obrigatorios_faltando=[], recomendacoes=[], confianca=0.9,
    )
    modelo_mock = MagicMock()
    modelo_mock.with_structured_output.return_value.invoke.return_value = resultado_fake

    with patch.object(ClaudeBrain, "_chat_model_langchain", return_value=modelo_mock):
        r = b.classificar_processo({"cnj": "123"})

    assert r["tipo_tarefa"] == "RECURSO"
    assert r["confianca"] == 0.9
    assert "raw_response" not in r


def test_cai_pro_legado_quando_structured_falha():
    b = ClaudeBrain.__new__(ClaudeBrain)
    b._deepseek_key = "fake-key"
    b._api_key = "fake-key"
    b.model = "deepseek-v4-pro"
    b.temperature = 0.3
    b.max_tokens = 4096

    modelo_mock = MagicMock()
    modelo_mock.with_structured_output.return_value.invoke.side_effect = Exception(
        "Thinking mode does not support this tool_choice")

    with patch.object(ClaudeBrain, "_chat_model_langchain", return_value=modelo_mock), \
         patch.object(ClaudeBrain, "ask", return_value='{"tipo_tarefa": "GENERICO", '
                      '"prioridade": "MEDIA", "classificacao": "x", '
                      '"campos_obrigatorios_faltando": [], "recomendacoes": [], '
                      '"confianca": 0.5}'):
        r = b.classificar_processo({"cnj": "123"})

    assert r["tipo_tarefa"] == "GENERICO"


def test_deepseek_chat_usado_para_evitar_thinking_mode():
    b = ClaudeBrain.__new__(ClaudeBrain)
    b._deepseek_key = "fake-key"
    b._api_key = "fake-key"
    b.model = "deepseek-v4-pro"
    b.temperature = 0.3

    with patch("langchain_deepseek.ChatDeepSeek") as MockChatDeepSeek:
        b._chat_model_langchain()
    assert MockChatDeepSeek.call_args.kwargs["model"] == "deepseek-chat"
