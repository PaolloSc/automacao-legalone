"""
Cadastra a resposta ridx=231 do Forms cível no LegalOne.
Usa a sessão salva em browser_data/state.json (Forms) e browser_data (LegalOne).
"""
import asyncio
import json
import os

import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from legalone_cadastro import LegalOneCadastro
import forms_mapping_civel as civel


def extrair_valor(item: dict) -> str:
    """Extrai a resposta limpa de um item do Forms."""
    if item.get("resposta_texto"):
        return item["resposta_texto"].strip()
    if item.get("marcadas"):
        return ", ".join(item["marcadas"]).strip()
    tc = item.get("texto_completo", "")
    pergunta = item.get("pergunta", "")
    if tc.startswith(pergunta):
        resposta = tc[len(pergunta):].strip()
    else:
        resposta = tc
    for suffix in [
        "No answer provided.",
        "Required to answer.",
        "Single choice.",
        "Single line text.",
        "Date.",
        "Multi Line Text.",
    ]:
        resposta = resposta.replace(suffix, "")
    return resposta.strip()


def converter_data_us_br(data_str: str) -> str:
    """Converte 8/13/2026 -> 13/08/2026."""
    data_str = data_str.strip()
    if not data_str:
        return data_str
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(data_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return data_str


def main():
    json_path = os.path.join(RAIZ, "debug_perguntas_231.json")
    with open(json_path, "r", encoding="utf-8") as f:
        perguntas_raw = json.load(f)

    perguntas = []
    for item in perguntas_raw:
        resposta = extrair_valor(item)
        perguntas.append(
            {
                "pergunta": item["pergunta"],
                "resposta": resposta,
                "marcadas": item.get("marcadas", []),
                "opcoes": item.get("opcoes", []),
                "texto_completo": item.get("texto_completo", ""),
            }
        )

    mapeamento = civel.mapear_formulario({"perguntas_forms": perguntas})
    campos = mapeamento.get("campos", {})

    # Ajusta data de distribuição
    data_distribuicao = campos.get("data_distribuicao")
    if data_distribuicao:
        campos["data_distribuicao"] = converter_data_us_br(data_distribuicao)

    dados_processo = {
        **campos,
        "tipo_tarefa_identificada": mapeamento.get("tipo_tarefa_identificada", "RECURSO"),
        "tipo_cadastro_canonico": mapeamento.get("tipo_cadastro"),
        "natureza": campos.get("natureza", "Cível"),
        "outros_dados": {
            "Mapeamento Forms - Campos": dict(campos),
        },
    }

    # a troca cnj↔vinculo do RECURSO agora mora em forms_mapping_civel
    if campos.get("cnj_recurso"):
        print(f"[INFO] RECURSO cível: processo de origem {campos['cnj']} "
              f"(recurso: {campos['cnj_recurso']})")

    print("Dados que serão cadastrados:")
    print(json.dumps(dados_processo, indent=2, ensure_ascii=False))

    legalone = LegalOneCadastro(
        username=os.getenv("LEGALONE_USERNAME", ""),
        password=os.getenv("LEGALONE_PASSWORD", ""),
    )
    sucesso = legalone.cadastrar_processo(dados_processo)
    if sucesso:
        print("\n[OK] Cadastro realizado com sucesso!")
    else:
        print("\n[ERRO] Falha no cadastro. Verifique os logs.")


if __name__ == "__main__":
    main()
