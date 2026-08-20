"""Converte o JSON da API interna do Forms (formapi) para o formato
perguntas_forms que forms_mapping.py / forms_mapping_civel.py ja consomem.
"""
from __future__ import annotations

_SEPARADOR_MULTIPLA_ESCOLHA = ";"  # NAO CONFIRMADO — ver docs/SPIKE_FORMAPI_ACHADOS.md


def _indice_perguntas_por_id(definicao: dict) -> dict:
    return {q["id"]: q for q in definicao.get("questions", [])}


def converter_resposta_para_perguntas_forms(definicao: dict, resposta: dict) -> list[dict]:
    perguntas_por_id = _indice_perguntas_por_id(definicao)
    resultado = []

    respostas_por_pergunta = resposta.get("answers", [])
    for answer in respostas_por_pergunta:
        questao = perguntas_por_id.get(answer.get("questionId"))
        if not questao:
            continue

        titulo = (questao.get("title") or "").strip()
        valor = answer.get("answer1") or ""

        opcoes = [c.get("displayText", "") for c in questao.get("choices", [])]
        marcadas = []
        if opcoes and valor:
            candidatas = [v.strip() for v in valor.split(_SEPARADOR_MULTIPLA_ESCOLHA) if v.strip()]
            opcoes_norm = {o.strip().lower() for o in opcoes}
            # so' trata como "marcadas" (multipla escolha) se TODO pedaco do
            # separador bater com uma opcao conhecida — senao e' provavelmente
            # texto livre que por acaso contem ';'
            if candidatas and all(c.strip().lower() in opcoes_norm for c in candidatas):
                marcadas = candidatas

        # mesma convencao do extractor Playwright legado (forms_extractor.py):
        # quando ha' marcadas, 'resposta' e' o join por ", " — nao o valor cru
        # com o separador original — pra bater com o que forms_mapping.py ja'
        # espera receber.
        resposta_final = ", ".join(marcadas) if marcadas else valor

        resultado.append({
            "pergunta": titulo,
            "resposta": resposta_final,
            "resposta_texto": valor,
            "opcoes": opcoes,
            "marcadas": marcadas,
            "texto_completo": f"{titulo} {valor}".strip(),
        })

    return resultado
