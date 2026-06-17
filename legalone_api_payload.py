"""Funções puras que montam o POST de Lawsuit a partir de `dados` extraídos."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def _normalize(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def parse_valor_brl(value) -> Optional[float]:
    """Converte 'R$ 1.234,56' em 1234.56; retorna None se vazio/inválido."""
    if not value:
        return None
    match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", str(value))
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def _doc_cliente(dados: dict) -> str:
    return (
        dados.get("cpf_cliente")
        or dados.get("cnpj_cliente")
        or dados.get("documento_cliente")
        or ""
    )


def _doc_contrario(dados: dict) -> str:
    return (
        dados.get("cpf_contrario")
        or dados.get("cnpj_contrario")
        or dados.get("documento_contrario")
        or ""
    )


def build_claims(pedidos: list[dict]) -> list[dict]:
    claims = []
    for pedido in pedidos or []:
        tipo = _normalize(pedido.get("tipo") or "Exito")
        is_loss = tipo == "perda"
        claim = {
            "Claim": {"description": pedido.get("pedido", "")},
            "probabilityType": "Loss" if is_loss else "Success",
            "contingency": "Passive" if is_loss else "Active",
            "probability": {"description": pedido.get("grau", "Possivel")},
        }
        amount = parse_valor_brl(pedido.get("valor"))
        if amount is not None:
            claim["claimAmount"] = {"value": amount}
        claims.append(claim)
    return claims


def build_participants(dados: dict, resolver) -> list[dict]:
    participants: list[dict] = []

    doc_cliente = _doc_cliente(dados)
    if dados.get("cliente") and doc_cliente:
        contact_id = resolver.resolve_contact_id(doc_cliente)
        if contact_id:
            participant = {
                "contactId": contact_id,
                "isMainParticipant": True,
                "type": "Customer",
            }
            position_id = resolver.resolve_posicao(dados.get("posicao") or "")
            if position_id:
                participant["positionId"] = position_id
            participants.append(participant)

    doc_contrario = _doc_contrario(dados)
    if dados.get("contrario") and doc_contrario:
        contact_id = resolver.resolve_contact_id(doc_contrario)
        if contact_id:
            participants.append({
                "contactId": contact_id,
                "isMainParticipant": False,
                "type": "OtherParty",
            })

    return participants


def build_lawsuit_payload(
    dados: dict,
    resolver,
    pedidos: Optional[list[dict]] = None,
    default_status_id: Optional[int] = None,
    default_area_id: Optional[int] = None,
) -> dict:
    payload: dict = {
        "identifierNumber": dados.get("cnj", ""),
        "type": dados.get("tipo") or "Judicial",
    }

    if dados.get("titulo"):
        payload["title"] = dados["titulo"]

    nature_id = resolver.resolve_natureza(dados.get("natureza") or "")
    if nature_id:
        payload["natureId"] = nature_id

    area_name = dados.get("responsavel") or dados.get("advogado_responsavel") or ""
    area_id = resolver.resolve_area(area_name) or default_area_id
    if area_id:
        payload["responsibleAreaId"] = area_id
        payload["originAreaId"] = area_id

    outros = dados.get("outros_dados") if isinstance(dados.get("outros_dados"), dict) else {}
    tipo_acao_nome = dados.get("tipo_acao") or outros.get("Tipo de ação") or outros.get("Tipo de acao") or ""
    action_type_id = resolver.resolve_tipo_acao(tipo_acao_nome)
    if action_type_id:
        payload["actionTypeId"] = action_type_id

    status_id = None
    if dados.get("status_processo") and hasattr(resolver, "resolve_status"):
        status_id = resolver.resolve_status(dados.get("status_processo"))
    status_id = status_id or default_status_id
    if status_id:
        payload["statusId"] = status_id

    if dados.get("fase") and hasattr(resolver, "resolve_fase"):
        phase_id = resolver.resolve_fase(dados.get("fase"))
        if phase_id:
            payload["phaseId"] = phase_id

    amount = parse_valor_brl(dados.get("valor_causa"))
    if amount is not None:
        payload["MonetaryAmountType"] = "Determined"
        payload["monetaryAmount"] = {"value": amount}

    participants = build_participants(dados, resolver)
    if participants:
        payload["participants"] = participants

    claims = build_claims(pedidos or [])
    if claims:
        payload["claims"] = claims

    return payload
