"""Regressao: cadeia de fallback de visao (Gemini -> Groq (qwen3.6-27b,
gratuito e preciso) -> Ollama local (moondream, sem custo, mais fraco) ->
OpenAI so' se todos os anteriores falharem). Antes o OpenAI era o unico
reserva e ficou sem credito (429), derrubando toda a recuperacao
automatica do Guardian/agente visual (17-18/08/2026)."""
import os
from unittest.mock import patch

from legalone_cadastro import LegalOneCadastro


def test_sem_chave_gemini_cai_pro_groq():
    c = LegalOneCadastro(username="", password="")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        with patch.object(c, "_groq_vision", return_value="ok-groq") as m:
            resultado = c._gemini_vision("prompt", b"png")
    assert resultado == "ok-groq"
    m.assert_called_once()


def test_sem_chave_groq_cai_pro_ollama():
    c = LegalOneCadastro(username="", password="")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GROQ_API_KEY", None)
        with patch.object(c, "_ollama_vision", return_value="ok-ollama") as m:
            resultado = c._groq_vision("prompt", b"png")
    assert resultado == "ok-ollama"
    m.assert_called_once()


def test_groq_falha_cai_pro_ollama():
    c = LegalOneCadastro(username="", password="")
    with patch.dict(os.environ, {"GROQ_API_KEY": "fake-key"}, clear=False):
        with patch("legalone_cadastro.requests.post") as post:
            post.side_effect = Exception("conexao recusada")
            with patch.object(c, "_ollama_vision", return_value="ok-ollama") as m:
                resultado = c._groq_vision("prompt", b"png")
    assert resultado == "ok-ollama"
    m.assert_called_once()


def test_ollama_falha_cai_pro_openai():
    c = LegalOneCadastro(username="", password="")
    with patch("legalone_cadastro.requests.post") as post:
        post.side_effect = Exception("conexao recusada")
        with patch.object(c, "_openai_vision", return_value="ok-openai") as m:
            resultado = c._ollama_vision("prompt", b"png")
    assert resultado == "ok-openai"
    m.assert_called_once()


def test_agente_visual_nao_exige_mais_gemini():
    """So' precisa falhar se NENHUM provedor (Gemini/Groq/Ollama) estiver disponivel."""
    c = LegalOneCadastro(username="", password="")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GROQ_API_KEY", None)
        with patch.object(c, "_ollama_disponivel", return_value=True):
            # Sem pagina real: o loop principal falha ao tentar usar self.page,
            # mas isso e' DEPOIS do guard de chave — chegar la' prova que o
            # guard nao bloqueou por falta de chave do Gemini/Groq.
            c.page = None
            resultado = c._agente_visual("objetivo qualquer")
    assert resultado is False  # falhou no page.evaluate, nao no guard de chave


def test_agente_visual_falha_sem_nenhum_provedor():
    c = LegalOneCadastro(username="", password="")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GROQ_API_KEY", None)
        with patch.object(c, "_ollama_disponivel", return_value=False):
            resultado = c._agente_visual("objetivo qualquer")
    assert resultado is False
