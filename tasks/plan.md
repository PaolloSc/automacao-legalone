# Plano: Agente de Teste E2E — Copilot Studio → Cadastro no LegalOne

## Overview

O pipeline hoje tem 5 sistemas em série, cada um pouco testável isoladamente:

```
Copilot Studio (chat/LLM)
    → Power Automate ("Enviar Dados da Peticao")
        → Email (JSON no corpo)
            → outlook_monitor_graph.py (Graph API, detecta e parseia)
                → automacao_legalone_completa.py (classifica campos)
                    → legalone_cadastro.py (Playwright, preenche formulário real)
                        → qa_validator.py (audita o preenchimento)
```

Não existe hoje nenhum teste que atravesse essa cadeia inteira. Os testes
atuais (`tests/*.py`, 38 casos) cobrem funções puras isoladas
(`forms_mapping.py`, `qa_validator._limpar_esperado`, normalização de nomes),
mas nunca simulam o payload de ponta a ponta nem tocam o Copilot Studio real
ou o LegalOne real.

**Restrição crítica que molda todo o plano:** não existe ambiente de
homologação/sandbox do LegalOne (`grep` por `homolog`/`sandbox` no `.env` e
no código não encontrou nada — `legalone_cadastro.py:351` só tem a flag
`--no-sandbox` do Chromium, não relacionada). Qualquer teste que realmente
"cadastre o processo" escreve no LegalOne de **produção** do escritório.
Por isso o agente é desenhado em **3 níveis de risco crescente**, e só o
Nível A roda sozinho/repetidamente sem supervisão.

## Architecture Decisions

- **3 níveis, não 1 teste monolítico.** Nível A (mock total, sem rede) é a
  base que roda em todo commit. Nível B (Copilot Studio real, para no
  email) valida o LLM de verdade sem tocar produção do LegalOne. Nível C
  (cadastro real) é opt-in manual, nunca automático — é o único jeito de
  não arriscar sujar dados de produção do escritório sem querer.
- **Reusar em vez de reimplementar.** O bug do `qa_validator.py` (sessão
  anterior) veio de um validador paralelo com seletores próprios que
  divergiam do código real. O agente de teste vai chamar os mesmos métodos
  que o bot usa em produção (`OutlookMonitorGraph._extrair_json_do_corpo`,
  a lógica de `_campos_base` de `automacao_legalone_completa.py`,
  `LegalOneCadastro._ler_valor_campo_formulario`), não reescrever a
  extração/validação do zero.
- **Fixtures cobrindo os 5 tipos de cadastro**, com nomes/CNPJ com
  parênteses de propósito (`"Fulano (Reclamante)"`) — é exatamente o
  formato que já causou os dois bugs reais encontrados nesta sessão
  (posição/contingência coladas, cliente com papel no nome).
- **CNJ e nomes de teste com prefixo inconfundível** (`"TESTE-E2E-AGENTE"`)
  em qualquer cenário que toque o LegalOne real, pra nunca confundir com
  processo real e facilitar limpeza manual depois.
- **"Agente" = subagent Claude Code + scripts pytest**, não um serviço
  novo rodando 24h. O Nível A vira `pytest`; Níveis B/C viram um subagent
  definido em `.claude/agents/e2e-copilot-legalone.md` que um humano aciona
  quando quiser rodar o teste pesado, nunca em CI.

## Dependency Graph

```
Fixtures de payload (Fase 1)
    │
    ├── Nível A: pipeline mockado (Fase 2)
    │       │
    │       └── Checkpoint A (roda em qualquer commit, zero rede)
    │
    ├── Nível B: Copilot Studio real → email real (Fase 3)
    │       │  (depende das fixtures pra saber o que mandar/conferir)
    │       └── Checkpoint B (revisão humana antes de habilitar C)
    │
    └── Nível C: handoff pro bot real → LegalOne real (Fase 4)
            (depende do e-mail capturado no Nível B)
            └── Checkpoint C (gate manual, nunca automático)
```

## Task List

### Fase 1: Fixtures (fundação — tudo depende disso)

- [ ] **Task 1: Fixtures de payload Copilot por tipo de cadastro**
  - **Descrição:** Criar `tests/fixtures/copilot_payloads.py` com um dict
    JSON de exemplo por tipo (`CADASTRO INICIAL`, `DECISOES`, `RECURSO`,
    `ARQUIVAMENTO COMPLETO`, `ARQUIVAMENTO SIMPLES`), usando exatamente os
    nomes de campo do prompt publicado no Copilot Studio hoje
    (`docs/COPILOT_AGENTE.md`). Incluir de propósito os formatos "sujos"
    que já causaram bug: `cliente` com `" (Reclamante)"`, `contrario` com
    `" (CNPJ ...)"`, `posicao` com `" (Ativo)"`.
  - **Acceptance criteria:**
    - [ ] 5 fixtures, uma por tipo_cadastro, todas com CNJ/nomes prefixados
      `TESTE-E2E-AGENTE`
    - [ ] Pelo menos 1 fixture cobre cada bug já corrigido nesta sessão
      (posição colada, cliente com papel, contrário com CNPJ)
  - **Verification:**
    - [ ] `python -c "from tests.fixtures.copilot_payloads import PAYLOADS; assert len(PAYLOADS)==5"`
  - **Dependencies:** None
  - **Files:** `tests/fixtures/copilot_payloads.py` (novo)
  - **Estimated scope:** XS (1 arquivo)

### Checkpoint: Fase 1
- [ ] Fixtures importam sem erro, 5 tipos presentes, revisão humana do
  conteúdo (nomes/CNJ de teste corretos) antes de seguir pra Fase 2.

---

### Fase 2: Nível A — pipeline mockado (sem rede, sem browser)

- [ ] **Task 2: Simular a chegada do email e a classificação de campos**
  - **Descrição:** Para cada fixture da Task 1, montar o `email_data` no
    formato que `outlook_monitor_graph.py` produz (`dados_diretos=<payload>`,
    `subject=COPILOT_ASSUNTO`) e rodar a mesma lógica de classificação
    `_campos_base` que `AutomacaoLegalOne.processar_email` usa (extrair
    essa lógica pra uma função testável se ainda estiver inline — ver Task
    2b) para obter `dados_processo`.
  - **Acceptance criteria:**
    - [ ] Campos base (`cnj`, `cliente`, `contrario`, `natureza`, `tribunal`,
      `comarca`, `instancia`, `posicao`, `fase`, `tipo_cadastro`) ficam
      top-level em `dados_processo`
    - [ ] Todo campo fora dessa lista cai em `dados_processo['outros_dados']`
      sem se perder
  - **Verification:**
    - [ ] `pytest tests/test_e2e_mock_pipeline.py::test_classificacao_campos -v`
  - **Dependencies:** Task 1
  - **Files:** `tests/test_e2e_mock_pipeline.py` (novo)
  - **Estimated scope:** S (1-2 arquivos)

- [ ] **Task 2b (pré-requisito da 2, se necessário): extrair a classificação de campos para uma função testável**
  - **Descrição:** Hoje o bloco `_campos_base` vive inline dentro de
    `AutomacaoLegalOne.processar_email` (`automacao_legalone_completa.py`
    linhas ~487-500). Extrair para uma função de módulo
    `classificar_dados_copilot(dados_diretos: dict) -> dict` pura,
    chamada por `processar_email` E pelo teste. **Refactor comportamental
    zero** — só move o código, não muda a lógica.
  - **Acceptance criteria:**
    - [ ] `processar_email` continua funcionando idêntico (nenhum teste
      existente quebra)
    - [ ] Função nova é importável e testável sem instanciar
      `AutomacaoLegalOne` (sem Playwright, sem Outlook)
  - **Verification:**
    - [ ] `pytest tests/ -q` (38 testes atuais + novos, todos verdes)
  - **Dependencies:** None (pode rodar antes ou junto da Task 2)
  - **Files:** `automacao_legalone_completa.py`
  - **Estimated scope:** S (1 arquivo)

- [ ] **Task 3: Dublê de página (fake Playwright `Page`) pra conferir o que seria digitado no LegalOne**
  - **Descrição:** Criar um objeto `FakePage`/`FakeLocator` mínimo (só o
    suficiente pra `LegalOneCadastro._ler_valor_campo_formulario` e
    `preencher_campo_autocomplete` não quebrarem) que **grava** em vez de
    **digitar de verdade** — permite rodar
    `preencher_campos_obrigatorios(dados_processo)` inteiro sem abrir
    Chrome nem logar no LegalOne, e depois inspecionar quais
    label→valor teriam sido preenchidos.
  - **Acceptance criteria:**
    - [ ] Para a fixture "suja" (posição="Reclamante (Ativo)"), o valor
      **gravado** pro campo Posição é `"Reclamante"` (limpo), confirmando
      que a limpeza roda antes do preenchimento — sem precisar de
      LegalOne real pra provar isso
    - [ ] Idem para `cliente`/`contrario` com papel/CNPJ colado
  - **Verification:**
    - [ ] `pytest tests/test_e2e_mock_pipeline.py::test_preenchimento_limpa_campos_sujos -v`
  - **Dependencies:** Task 1, Task 2
  - **Files:** `tests/test_e2e_mock_pipeline.py`, possível pequeno ajuste
    em `legalone_cadastro.py` só se algum ponto acessar API do Playwright
    que o fake não cobre (ex.: `page.evaluate`) — mapear ao implementar
  - **Estimated scope:** M (pode tocar 2-3 arquivos se o fake precisar
    crescer pra cobrir `page.evaluate`/`page.locator` usados por
    `_ler_valor_campo_formulario`)

### Checkpoint: Fase 2 (Nível A completo)
- [ ] `pytest tests/ -q` — tudo verde, **zero chamada de rede, zero
  browser**, roda em segundos
- [ ] Esse checkpoint é o que passa a rodar sempre que algo em
  `forms_mapping.py`/`automacao_legalone_completa.py`/`legalone_cadastro.py`
  mudar — é o "agente" no sentido de suite automática
- [ ] Revisão humana: os 3 bugs reais desta sessão (posição colada, cliente
  com papel, contrário com CNPJ) estão coberto por teste que FALHARIA se
  a limpeza fosse removida de novo (teste de regressão de verdade, não só
  feliz-caminho)

---

### Fase 3: Nível B — Copilot Studio real, para antes do LegalOne

- [ ] **Task 4: Subagent que dirige o chat de teste do Copilot Studio**
  - **Descrição:** Criar `.claude/agents/e2e-copilot-legalone.md` (subagent
    com acesso a browser/claude-in-chrome) que: abre a URL de teste do
    agente (já documentada em `COPILOT_AGENTE.md`), envia um texto de
    petição fixo e conhecido (fixture de texto, não payload já pronto —
    tem que testar a EXTRAÇÃO de verdade), confirma quando o bot pergunta,
    e captura a resposta final antes do envio do flow.
  - **Acceptance criteria:**
    - [ ] Roda contra o agente real publicado (o que só existe porque a
      sessão anterior corrigiu e publicou o prompt)
    - [ ] Extrai os mesmos campos que a fixture da Task 1 esperaria pra
      aquele texto de petição
  - **Verification:**
    - [ ] Execução manual documentada com screenshot/log da conversa
    - [ ] Comparação campo-a-campo do que o bot mostrou vs. esperado
  - **Dependencies:** Task 1 (fixtures como "gabarito" de comparação)
  - **Files:** `.claude/agents/e2e-copilot-legalone.md` (novo)
  - **Estimated scope:** M

- [ ] **Task 5: Confirmar que o email chega com o JSON esperado**
  - **Descrição:** Reusar `OutlookMonitorGraph` (mesma classe de produção)
    apontada pro mesmo mailbox, com um filtro adicional de assunto+janela
    de tempo curta, pra pegar o email que a Task 4 acabou de gerar e
    validar o JSON via `_extrair_json_do_corpo` (o parser real).
  - **Acceptance criteria:**
    - [ ] Email aparece em até 2 minutos
    - [ ] JSON parseia sem erro e bate com os campos extraídos na Task 4
  - **Verification:**
    - [ ] Execução manual: log mostrando `[COPILOT] Email do Copilot
      detectado: CNJ=TESTE-E2E-AGENTE-...`
  - **Dependencies:** Task 4
  - **Files:** `.claude/agents/e2e-copilot-legalone.md` (mesma definição,
    passo adicional)
  - **Estimated scope:** S

### Checkpoint: Fase 3 (Nível B completo)
- [ ] **Rodar manualmente, nunca em CI** (custa tempo real, depende de
  serviço externo, e paga pelo uso do modelo no Copilot Studio)
- [ ] Revisão humana obrigatória do resultado antes de decidir se a Fase 4
  roda naquele dia — o e-mail capturado aqui é o input real da Fase 4

---

### Fase 4: Nível C — handoff real pro bot, cadastro real no LegalOne (opt-in, gated)

- [ ] **Task 6: Handoff do email capturado pro bot real, com prefixo de teste**
  - **Descrição:** Passar o `email_data` da Task 5 pro
    `AutomacaoLegalOne.processar_email` de verdade (Playwright real,
    login real no LegalOne de produção). Só roda se o CNJ/cliente tiver o
    prefixo `TESTE-E2E-AGENTE` (checagem defensiva no próprio script do
    subagent, não no bot — não queremos mexer no bot de produção só pra
    isso) e se o humano confirmar explicitamente.
  - **Acceptance criteria:**
    - [ ] Processo é criado no LegalOne com CNJ/nome de teste reconhecível
    - [ ] `qa_validator.py` não reporta nenhum warning falso (valida a
      correção da sessão anterior em condição real)
  - **Verification:**
    - [ ] Busca manual no LegalOne pelo CNJ de teste confirmando os campos
    - [ ] Humano apaga/arquiva o processo de teste depois (não existe API
      de exclusão configurada — é manual)
  - **Dependencies:** Task 5, aprovação humana explícita a cada execução
  - **Files:** `.claude/agents/e2e-copilot-legalone.md`
  - **Estimated scope:** M

### Checkpoint: Fase 4 (Nível C completo)
- [ ] **Nunca automático.** Cada execução exige o humano digitar
  confirmação explícita (o subagent deve perguntar, não assumir)
- [ ] Checklist de limpeza pós-teste documentado e seguido

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Nível C cria processo de teste em produção do LegalOne sem querer | Alto | CNJ/nome com prefixo `TESTE-E2E-AGENTE`; gate de confirmação explícita; nunca rodar em CI |
| Copilot Studio muda de resposta entre execuções (LLM não é determinístico) | Médio | Nível B compara campo-a-campo com tolerância, não string exata; falhas de Nível B não bloqueiam Nível A |
| Fake Playwright Page da Task 3 diverge do real e mascara bugs reais | Médio | Fake cobre só os métodos realmente chamados por `preencher_campos_obrigatorios`; qualquer método não coberto deve falhar alto (`NotImplementedError`), não silenciar |
| Extração da Task 2b introduzir regressão no bot de produção | Médio | Refactor "zero comportamento novo" + suíte completa (`pytest tests/ -q`) verde antes/depois |
| Sem API de exclusão no LegalOne, testes de Nível C acumulam lixo | Baixo | Checklist manual de limpeza no checkpoint da Fase 4; considerar registrar CNJs de teste criados num arquivo pra facilitar limpeza em lote depois |

## Open Questions

1. **Existe algum ambiente de homologação do LegalOne que eu não encontrei
   no grep (talvez outro subdomínio/tenant)?** Se existir, o Nível C vira
   muito mais barato de rodar com frequência.
2. **Convenção de "processo de teste" já existe no escritório** (algum
   cliente fictício de sandbox, algum CNJ reservado)? Se sim, usar essa
   convenção em vez de inventar `TESTE-E2E-AGENTE`.
3. **Quem vai rodar o Nível B/C na prática** — só você, ou outro
   advogado/estagiário também vai disparar esse subagent? Afeta quanto
   detalhe de instrução colocar no `.md` do subagent.
4. **Task 2b (extrair `_campos_base` pra função)** é um refactor pequeno
   mas toca código de produção — tudo bem fazer isso, ou prefere manter a
   lógica inline e o teste chamar `processar_email` inteiro com mocks
   pesados (Outlook, Playwright) em vez de extrair a função pura?
