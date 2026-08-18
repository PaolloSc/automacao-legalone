# Glossário — pacote_automacao_legalone

## Campos da tela de recurso/cadastro do LegalOne (Novajus)

Três campos que o Forms/Copilot às vezes não preenche bem e que o
DataJud/CNJ pode complementar — são conceitos distintos, não sinônimos:

- **Órgão** (`OrgaoText`/`OrgaoId`): o **tribunal** em si (ex. "Tribunal de
  Justiça do Estado de Minas Gerais"). Catálogo guarda o nome por extenso,
  nunca a sigla ("TJMG"). Diferente de "Vara/Turma".
- **Vara/Turma** (`VaraText`/`NumeroVaraTurma`): o **órgão julgador
  específico** dentro do tribunal (ex. "3ª Câmara Cível"). Já preenchido
  pelo DataJud via `orgaoJulgador.nome` quando vazio.
- **Ação** / "Tipo de recurso" (`TipoAcaoText`): a classe processual (ex.
  "Agravo de instrumento"). Já preenchido pelo DataJud via `classe.nome`
  quando vazio — funcionando (100% de semelhança nos testes de 17/08/2026).
- **Assunto (CNJ)**: taxonomia TPU do processo. Já preenchido pelo DataJud
  via `assuntos[0].nome` quando vazio.

## Regra de preenchimento via DataJud

Campos de "capa do processo" (`_DATAJUD_CAMPOS` em `legalone_cadastro.py`)
só são preenchidos pelo DataJud quando o campo **já chegou vazio** do
Forms/Copilot — nunca sobrescreve uma resposta existente, mesmo que ela
esteja errada ou não resolva no catálogo. Roda nos três fluxos: cadastro
inicial, recurso cível e decisão (via `_aplicar_valores_monetarios` →
`_enriquecer_dados_datajud`).

## Derivação do tribunal a partir do CNJ

`jurimetria_datajud.alias_do_cnj(cnj)` deriva o tribunal **direto dos
dígitos J.TR do número do CNJ** (regex, sem chamada de rede) — mais
confiável que depender de um hit do DataJud existir. Usado pra resolver o
índice de busca do DataJud (`api_publica_tjmg` etc.) e, desde 17/08/2026,
por `LegalOneCadastro._orgao_do_cnj` pra alimentar o campo Órgão do
LegalOne: TJs sempre "Tribunal de Justiça do Estado de \<Estado\>", TRTs
sempre "Tribunal Regional do Trabalho da \<N\>ª Região" — validado ao vivo
contra o catálogo real, sem exceção nos 9 tribunais testados. `orgao`
entrou em `_DATAJUD_CAMPOS`, então segue a mesma regra "só preenche se
vazio" dos outros campos.

## Cadeia de fallback de visão (Guardian/agente visual)

`legalone_cadastro.py` tem um agente de visão (`_agente_visual`) usado
quando os seletores normais falham: marca elementos clicáveis com número,
manda o screenshot pra um modelo de visão, recebe de volta qual número
clicar. Cadeia de reserva (18/08/2026): Gemini (primário, precisa de
GOOGLE_API_KEY/GEMINI_API_KEY) → Groq (`qwen/qwen3.6-27b`, gratuito,
rápido, preciso — leu corretamente texto denso de uma tela real do
LegalOne) → Ollama local (moondream, sem custo de API, sem chave, mas
alucinou na mesma tela real — só entra se Groq também falhar) → OpenAI
GPT-4o (último recurso, precisa de OPENAI_API_KEY com crédito). A ordem
existe porque o OpenAI ficou sem crédito e travava toda recuperação
automática. Testado ao vivo: `avil/UI-TARS` (tentativa inicial) não tem o
mmproj embutido no pacote da comunidade — não aceita imagem;
`kimi-k2.7-code:cloud` exige assinatura paga do Ollama Cloud; Groq exige o
modelo exato `qwen/qwen3.6-27b` (roda em modo "thinking" — precisa de
max_tokens folgado, ~1024, senão corta antes do JSON final). Isso é diferente do
Visual Guardian
(visual_guardian.py), que usa claude_brain.py/Claude Sonnet pra
recuperação de erros de cadastro — os dois sistemas de visão são
independentes.

## Structured output do claude_brain.py (LangChain)

`ClaudeBrain.classificar_processo` tinha parse manual de JSON dentro de
bloco ```` ```json ```` na resposta em texto livre — falhava
silenciosamente e caía num fallback genérico. Desde 18/08/2026 usa
`with_structured_output` (LangChain) quando há um provedor com chave
estática configurado (`langchain_deepseek.ChatDeepSeek` para
DEEPSEEK_API_KEY, `langchain_anthropic.ChatAnthropic` para
ANTHROPIC_API_KEY); sem chave estática (fluxo OAuth puro, sem integração
pronta no LangChain pro access_token com refresh desta classe) cai pro
parse legado. Achado ao vivo: `deepseek-v4-pro` (modelo padrão) roda em
"thinking mode" e recusa `tool_choice` forçado — a chamada estruturada
usa `deepseek-chat` especificamente por isso (`_chat_model_langchain` em
`claude_brain.py`). Escopo deliberadamente pequeno: só
`classificar_processo` mudou; `send_message`/`ask` (usados pelo Guardian)
continuam no cliente HTTP cru de sempre.
