"""
FastAPI endpoint para Opção B — recebe PDF de petição via webhook,
extrai campos com Azure Document Intelligence + OpenAI,
e aciona o cadastro no LegalOne.

Também aceita JSON direto (mesmos 10 campos do Copilot Studio).
"""

import asyncio
import hashlib
import hmac
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Header, UploadFile
from pydantic import BaseModel

load_dotenv()

from config_azure import CAMPOS_OBRIGATORIOS, PETICAO_API_CONFIG, TIPOS_CADASTRO_VALIDOS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('peticao_api.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LegalOne Petição API",
    description="Recebe PDFs de petições, extrai campos e cadastra no LegalOne",
    version="1.0.0",
)

# ── Lazy-loaded singletons ──────────────────────────────────────────
_extractor = None
_legalone = None
_brain = None
_async_loop = None


def _get_extractor():
    """Lazy init do PeticaoExtractor (só carrega se Azure configurado)."""
    global _extractor
    if _extractor is None:
        try:
            from peticao_extractor import PeticaoExtractor
            _extractor = PeticaoExtractor()
        except Exception as e:
            logger.warning(f"PeticaoExtractor indisponível: {e}")
    return _extractor


def _get_legalone():
    """Lazy init do LegalOneCadastro com sessão Playwright persistente."""
    global _legalone, _async_loop
    if _legalone is None:
        try:
            from legalone_cadastro import LegalOneCadastro
            _legalone = LegalOneCadastro()
            # Event loop persistente para Playwright
            _async_loop = asyncio.new_event_loop()
            t = threading.Thread(target=_async_loop.run_forever, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"LegalOneCadastro indisponível: {e}")
    return _legalone


def _get_brain():
    """Lazy init do Claude Brain."""
    global _brain
    if _brain is None:
        try:
            from claude_brain import ClaudeBrain
            _brain = ClaudeBrain()
            logger.info("[API] Claude Brain ativo")
        except Exception as e:
            logger.warning(f"Claude Brain indisponível: {e}")
    return _brain


# ── Models ──────────────────────────────────────────────────────────

class CadastroRequest(BaseModel):
    """Aceita JSON direto com campos já extraídos (sem OCR)."""
    cnj: str
    cliente: str
    contrario: str
    natureza: str
    tribunal: str
    comarca: str
    instancia: str
    posicao: str
    fase: str
    tipo_cadastro: str


class ApiResponse(BaseModel):
    status: str
    mensagem: str
    campos: Optional[dict] = None
    classificacao: Optional[dict] = None
    timestamp: str


def _verificar_webhook_secret(signature: Optional[str], body: bytes = b""):
    """Verifica assinatura HMAC do webhook se secret configurado."""
    secret = PETICAO_API_CONFIG.get('webhook_secret', '')
    if not secret:
        return
    if not signature:
        raise HTTPException(status_code=401, detail="Assinatura ausente")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Assinatura inválida")


# ── Endpoints ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "extractor": _extractor is not None,
        "legalone": _legalone is not None,
        "brain": _brain is not None,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/peticao/upload", response_model=ApiResponse)
async def upload_peticao(
    arquivo: UploadFile = File(...),
    x_webhook_signature: Optional[str] = Header(None),
):
    """Upload de PDF/DOCX/DOC → OCR/extração → campos → Claude Brain → cadastro LegalOne."""
    extractor = _get_extractor()
    if not extractor:
        raise HTTPException(status_code=503, detail="Extrator não configurado")

    extensoes_validas = ('.pdf', '.docx', '.doc')
    nome = (arquivo.filename or '').lower()
    if not any(nome.endswith(ext) for ext in extensoes_validas):
        raise HTTPException(status_code=400, detail=f"Formatos aceitos: {', '.join(extensoes_validas)}")

    pdf_bytes = await arquivo.read()
    if len(pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo excede 20MB")

    _verificar_webhook_secret(x_webhook_signature, pdf_bytes)

    logger.info(f"[UPLOAD] Recebido: {arquivo.filename} ({len(pdf_bytes)} bytes)")

    try:
        campos = extractor.processar_arquivo_bytes(pdf_bytes, arquivo.filename)
    except Exception as e:
        logger.error(f"[UPLOAD] Erro na extração: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na extração: {str(e)}")

    # Claude Brain classifica
    classificacao = _classificar_com_brain(campos)

    # Cadastra no LegalOne
    cadastro_ok = _acionar_legalone(campos)

    return ApiResponse(
        status="sucesso" if cadastro_ok else "extraido_sem_cadastro",
        mensagem="Campos extraídos e cadastro acionado" if cadastro_ok else "Campos extraídos, cadastro pendente",
        campos=campos,
        classificacao=classificacao,
        timestamp=datetime.now().isoformat(),
    )


@app.post("/api/peticao/json", response_model=ApiResponse)
async def cadastrar_json(
    dados: CadastroRequest,
    x_webhook_signature: Optional[str] = Header(None),
):
    """Recebe JSON com campos já extraídos → Claude Brain → cadastro direto no LegalOne."""
    campos = dados.model_dump()
    logger.info(f"[JSON] Recebido: CNJ={campos.get('cnj')}, Cliente={campos.get('cliente')}")

    tipo = campos.get('tipo_cadastro', '')
    if tipo.upper() not in [t.upper() for t in TIPOS_CADASTRO_VALIDOS]:
        raise HTTPException(
            status_code=400,
            detail=f"tipo_cadastro inválido: '{tipo}'. Válidos: {TIPOS_CADASTRO_VALIDOS}",
        )

    # Claude Brain classifica
    classificacao = _classificar_com_brain(campos)

    # Cadastra no LegalOne
    cadastro_ok = _acionar_legalone(campos)

    return ApiResponse(
        status="sucesso" if cadastro_ok else "cadastro_pendente",
        mensagem="Cadastro acionado" if cadastro_ok else "Cadastro pendente — LegalOne indisponível",
        campos=campos,
        classificacao=classificacao,
        timestamp=datetime.now().isoformat(),
    )


# ── Lógica interna ─────────────────────────────────────────────────

def _classificar_com_brain(campos: dict) -> Optional[dict]:
    """Usa Claude Brain pra classificar processo (tipo, prioridade, recomendações)."""
    brain = _get_brain()
    if not brain:
        return None
    try:
        classificacao = brain.classificar_processo(campos)
        tipo = classificacao.get('tipo_tarefa', 'GENERICO')
        prioridade = classificacao.get('prioridade', 'MEDIA')
        confianca = classificacao.get('confianca', 0)
        logger.info(f"[BRAIN] Tipo: {tipo} | Prioridade: {prioridade} | Confiança: {confianca:.0%}")
        campos['tipo_tarefa_identificada'] = tipo
        campos['classificacao_ia'] = classificacao
        return classificacao
    except Exception as e:
        logger.warning(f"[BRAIN] Erro: {e}")
        return None


def _acionar_legalone(campos: dict) -> bool:
    """Aciona LegalOneCadastro com os campos extraídos."""
    legalone = _get_legalone()
    if not legalone:
        logger.warning("[LEGALONE] Indisponível — campos extraídos mas não cadastrados")
        return False
    try:
        # Garante campos no formato esperado
        campos.setdefault('outros_dados', {})

        sucesso = legalone.cadastrar_processo(campos)
        if sucesso:
            logger.info(f"[LEGALONE] Cadastro OK: CNJ={campos.get('cnj')}")
            _salvar_log('processos_cadastrados.log', campos, 'SUCESSO')
        else:
            logger.error(f"[LEGALONE] Falha: CNJ={campos.get('cnj')}")
            motivo = getattr(legalone, 'last_error_reason', None)
            if motivo:
                logger.error(f"[LEGALONE] Motivo: {motivo}")
                campos['motivo_falha'] = motivo
            _salvar_log('processos_erro.log', campos, 'ERRO')
        return sucesso
    except Exception as e:
        logger.error(f"[LEGALONE] Exceção: {e}")
        _salvar_log('processos_erro.log', campos, f'ERRO: {e}')
        return False


def _salvar_log(arquivo: str, campos: dict, status: str):
    """Salva log de processamento."""
    try:
        with open(arquivo, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"Data: {datetime.now().isoformat()}\n")
            f.write(f"Fonte: API Webhook\n")
            f.write(f"CNJ: {campos.get('cnj', 'N/A')}\n")
            f.write(f"Cliente: {campos.get('cliente', 'N/A')}\n")
            f.write(f"Contrário: {campos.get('contrario', 'N/A')}\n")
            f.write(f"Tipo: {campos.get('tipo_cadastro', 'N/A')}\n")
            f.write(f"Status: {status}\n")
            f.write(f"{'='*80}\n")
    except Exception as e:
        logger.error(f"Erro ao salvar log: {e}")


if __name__ == "__main__":
    logger.info("Iniciando Petição API (Opção B)...")
    logger.info(f"Host: {PETICAO_API_CONFIG['host']}:{PETICAO_API_CONFIG['port']}")
    uvicorn.run(
        "peticao_api:app",
        host=PETICAO_API_CONFIG['host'],
        port=PETICAO_API_CONFIG['port'],
        reload=False,
    )
