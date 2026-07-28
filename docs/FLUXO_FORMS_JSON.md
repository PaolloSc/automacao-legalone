# Fluxo: Forms → JSON por email (substitui o scraping do Forms)

Motivo: em 28/07/2026 a UI nova do Forms (`forms.cloud.microsoft`) removeu
"Verificar resultados individuais". O extractor por Playwright dependia dessa
tela — e antes disso já dependia de sessão Microsoft logada (`state.json`, que
expira) e de a UI estar em português. Três dependências frágeis para ler dados
que o próprio Forms sabe entregar estruturados.

Este fluxo entrega a resposta como JSON no corpo de um email. O bot já tem o
caminho pronto (`dados_diretos`, o mesmo do Copilot) — não abre browser.

## O fluxo

**Onde:** https://make.powerautomate.com → Criar → Fluxo de nuvem automatizado

1. **Gatilho:** Microsoft Forms → "Quando uma nova resposta for enviada"
   - Formulário: `Cadastro de processos NOVOS LegalOne trabalhista`
2. **Ação:** Microsoft Forms → "Obter detalhes da resposta"
   - Id da Resposta: `ID da Resposta` (do gatilho)
3. **Ação:** Outlook → "Enviar um email (V2)"
   - **Para:** `paollo.sanchez@carvalhofurtadoadv.com.br`
   - **Assunto:** `LegalOne - Dados Extraidos de Peticao`
     (exato — é assim que `outlook_monitor_graph.py` reconhece o email;
     constante `COPILOT_ASSUNTO`)
   - **Corpo:** só o JSON abaixo, com os campos do formulário arrastados do
     "Obter detalhes da resposta". Use a visualização de código (`</>`) para o
     editor não inserir formatação.

## Corpo do email

```json
{
  "tipo_cadastro": "<Tipo de cadastro>",
  "cnj": "<Número CNJ>",
  "cliente": "<Cliente principal>",
  "contrario": "<Contrário principal>",
  "natureza": "<Natureza do processo>",
  "tribunal": "<Tribunal>",
  "comarca": "<Cidade/Comarca>",
  "instancia": "<Instância>",
  "posicao": "<Posição>",
  "fase": "<Fase>",
  "outros_dados": {
    "valor_causa": "<Valor da causa>",
    "advogado": "<Advogado>",
    "procedimento": "<Procedimento>",
    "objetos": "<Objetos>",
    "descricao_pedidos": "<Descreva todos os pedidos>",
    "contingencia": "<Contingência>",
    "probabilidade": "<Probabilidade>",
    "risco": "<Risco>",
    "vinculo_trabalhista": "<Há pedido de vínculo trabalhista>"
  }
}
```

Regras:
- `cnj` é obrigatório — sem ele o bot descarta e manda email de erro.
- Campo não preenchido: mande `"NAO LOCALIZADO"` (não omita a chave).
- Qualquer campo extra pode entrar em `outros_dados`; `forms_mapping.py`
  e o `LegalOneCadastro` consomem de lá.
- Valores com aspas ou quebra de linha quebram o JSON — no Power Automate use
  a expressão `json(...)`/`replace(...)` nos campos de texto longo, ou o
  conector "Compor" para escapar antes.

## Por que o corpo pode vir com HTML em volta

`_extrair_json_do_corpo` tira as tags, procura do primeiro `{` ao último `}` e
faz o parse — funciona com JSON aninhado e com texto do Outlook em volta
(coberto por `tests/test_json_corpo_email.py`). Ainda assim, quanto mais limpo
o corpo, menos chance de surpresa.

## Como testar

1. Responda o formulário com dados de teste (CNJ fictício `0000001-11.2026.5.03.0001`).
2. `sudo journalctl -u legalone -f` na VM — deve aparecer
   `[COPILOT] Email do Copilot detectado: CNJ=...` e **não** `Extraindo dados do Forms`.

## Desligar o scraping (depois que o fluxo estiver validado)

O monitor ainda aceita o email `Nova resposta de ...` do Forms e tenta raspar.
Quando o fluxo novo estiver de pé, mudar `assunto_filtro` em
`outlook_monitor_graph.py` (ou parar de encaminhar a notificação do Forms)
evita o caminho morto e o email de erro duplicado.
