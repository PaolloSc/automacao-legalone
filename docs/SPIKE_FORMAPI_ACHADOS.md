# Spike — API interna do Microsoft Forms (formapi): achados

## TL;DR para quem for implementar (Tasks 1-3 do plano)

- **Host:** `https://forms.cloud.microsoft` (não `forms.office.com` — esse dá 401 "701 Required
  user login" sempre, mesmo com sessão válida).
- **`tenantId`/`userId`** entram no path e são fixos por conta (não mudam por formulário nem por
  chamada). Descobrir uma vez — ver `GET /formapi/api/userInfo` (chamada #0 capturada) ou o path de
  qualquer chamada real feita pela própria página.
- **Definição do formulário:**
  `GET /formapi/api/{tenantId}/users/{userId}/light/forms('{formId}')?$select=...&$expand=questions($expand=choices)`
  → JSON com `questions: [{id, title, type, required, choices: [{displayText, ...}]}]`.
- **Respostas (com paginação confirmada):**
  `GET /formapi/api/{tenantId}/users/{userId}/light/forms('{formId}')/responses?$expand=comments&$top=50&$skip=0`
  → `{"value": [{id, startDate, submitDate, responder, responderName, answers: "<JSON string>"}]}`.
  **`$top`/`$skip` funcionam** — dá pra pedir só as respostas novas (`$skip=<ultimo_processado>`)
  em vez de andar resposta a resposta com a seta. `id` é inteiro sequencial, mesmo papel do
  contador atual (`ultimo_processo.txt`).
- **`answers` vem como STRING JSON-encoded**, não array nativo — precisa `json.loads()` antes de
  usar. Cada item: `{"answer1": "<valor>", "questionId": "<id da pergunta>"}`. Resposta vazia =
  `answer1: ""`.
- **Autenticação:** NÃO é `Authorization: Bearer` (vem vazio). É cookies (do `state.json`) + um
  header `__requestverificationtoken` cujo valor é **exatamente o valor do cookie
  `__RequestVerificationToken`** do mesmo `state.json` (dupla submissão CSRF — não precisa de
  navegador pra gerar, é leitura direta do arquivo). Os headers `x-usersessionid`/`x-ms-form-muid`
  são só telemetria, valores arbitrários funcionam.
- **Sessão precisa estar "fresca"** — mesma barra que o scraper Playwright atual já exige
  (`scripts/capturar_sessao_forms.py`). Sinal de sessão velha: `401` com corpo
  `{"error":{"code":"701"|"711", "message":"Required user login[. The token is expired.]"}}`.
- **NÃO confirmado:** o formato exato de `answer1` pra perguntas de múltipla escolha (multi-select)
  — a fixture assume valores separados por `;`, mas isso é uma SUPOSIÇÃO, não foi observado numa
  resposta real com múltipla escolha marcada. Quem implementar o conversor (Task 2) deve tratar
  isso como um risco conhecido e, se possível, validar contra uma resposta real de múltipla escolha
  antes de fechar essa lógica.

---

Data: 2026-08-20 (executado contra a conta real, `browser_data/state.json` gerado por
`scripts/capturar_sessao_forms.py`).

## Resultado: cookies puros (sem navegador) NÃO autenticam na formapi

Rodando `scripts/spike_formapi.py` a partir da raiz de `pacote_automacao_legalone/`:

```
https://forms.office.com 401 application/json; charset=utf-8
https://forms.cloud.microsoft 401 application/json; charset=utf-8
https://forms.office.com/formapi/api/forms('<id>')/responses 401
https://forms.office.com/formapi/api/forms/<id>/responses 404
https://forms.cloud.microsoft/formapi/api/forms('<id>')/responses 401
```

Nenhum host/URL retornou 200. Nenhum `debug_formapi_*.json` foi gerado.

Corpo do 401 (`GET /formapi/api/forms('<id>')?$expand=questions`, host `forms.office.com`):

```json
{"error":{"code":"701","message":"Required user login.","@ms.form.error.type":"ExpectedFailure"}}
```

**Esse é exatamente o erro "701: Required user login." documentado na thread do Microsoft Tech
Community** (`techcommunity.microsoft.com/.../api-to-access-ms-forms/.../replies/3254687`) para
tentativas de autenticar com Azure AD app registration / service principal. A diferença é que aqui
usamos cookies de uma sessão de USUÁRIO real, capturados por login interativo — e ainda assim a API
recusou.

## Diagnóstico

Os headers da resposta confirmam que a chamada chegou ao serviço real (routing headers
`x-officecluster`, `x-usersessionid`, etc. — não é um proxy/CDN rejeitando antes de rotear). Ou
seja, os cookies de `state.json` sozinhos (replay via `httpx.Cookies`, sem executar JS) não bastam
para autenticar nesta API. Hipóteses mais prováveis, em ordem:

1. A API espera um **header `Authorization: Bearer <token>`** obtido via um fluxo de silent-SSO em
   JavaScript (iframe MSAL) que só roda dentro do navegador — os cookies de sessão (`AADAuth.forms`,
   `OIDCAuth.forms`, `esctx-*`) servem para o navegador RENOVAR esse token silenciosamente, não para
   autenticar a chamada REST diretamente.
2. Padrão anti-CSRF de "double submit": o cookie `__RequestVerificationToken` provavelmente precisa
   ser ecoado também como header (`X-RequestVerificationToken` ou similar) — não testado neste spike
   porque a mensagem "Required user login" (não "Invalid CSRF token") aponta mais para (1).
3. Algum outro header específico do Forms setado por JS antes do XHR (não documentado publicamente).

Não investigamos further (interceptar as chamadas XHR reais do navegador via DevTools/CDP para
copiar os headers exatos) porque isso está fora do escopo deste spike e do "sem tocar em Power
Automate" que o usuário pediu — abrir essa investigação praticamente reintroduziria a necessidade de
um navegador (ainda que só para roubar um token, não para navegar o Forms inteiro), o que anula boa
parte do ganho de velocidade que motivou este plano.

## Decisão de continuidade (Task 0, Step 5 do plano)

**Nenhum host/URL respondeu 200. Por definição do plano, a spike PARA aqui.** As Tasks 1-4 (cliente
HTTP, conversor, integração no `FormsExtractor`, rollout) dependem de uma API que responda — sem
isso, não fazem sentido como especificadas. Achado reportado ao usuário, que pediu para investigar
mais fundo antes de desistir — ver seção seguinte.

## Investigação adicional (autorizada pelo usuário): capturando os headers reais via Playwright

Interceptamos, via `page.on("request")` num Chromium do Playwright aberto com o `state.json` real
(navegando para a página de Design do formulário Cível), a chamada real que a própria UI do Forms
faz. Dois achados importantes:

1. **A URL real é totalmente diferente da documentada/testada no spike inicial:**
   ```
   https://forms.cloud.microsoft/formapi/api/{tenantId}/users/{userId}/light/forms('{formId}')
       ?$select=...&$expand=permissions,permissionTokens,questions($expand=choices)
   ```
   Não é `forms.office.com/formapi/api/forms('{id}')` como a thread do Tech Community e o `MAPEAMENTO_FORMS_CIVEL.md`
   sugeriam — o caminho carrega `tenantId` e `userId` do usuário logado (`b3308b02-.../users/5fd503f6-...`),
   valores que só aparecem depois do login, não são deriváveis do link público do formulário sozinho.

2. **A autenticação não é via header `Authorization` (que vem vazio `""`).** Depende de:
   - Cookies da sessão (enviados automaticamente pelo browser);
   - Um header `__requestverificationtoken` — dupla submissão do cookie `__RequestVerificationToken` (padrão anti-CSRF ASP.NET);
   - Vários headers customizados: `x-usersessionid`, `x-ms-form-request-ring`, `x-ms-form-muid`, `x-ms-form-request-source`, `odata-version`, `referer`.

**Testamos replicar exatamente esses headers via `httpx`** (cookies do `state.json` + o
`__requestverificationtoken` capturado + os headers `x-ms-form-*`) contra a mesma URL, poucos
minutos depois da captura:

```
STATUS 401
{"error":{"code":"711","message":"Required user login. The token is expired."}}
```

Note que o código do erro mudou de `701` ("Required user login") para `711` ("...The token is
expired") — ou seja, os headers estavam estruturalmente corretos (o servidor reconheceu o token,
só recusou por expiração), mas o `__requestverificationtoken` tem TTL curto (expirou em poucos
minutos, possivelmente menos) e é amarrado ao carregamento daquela página específica — não é um
valor capturável uma vez e reutilizável por um processo de longa duração.

## Conclusão

Um cliente HTTP standalone (sem navegador) contra a formapi exigiria, no mínimo: (a) descobrir
`tenantId`/`userId` dinamicamente, (b) obter um `__requestverificationtoken` fresco — o que, pelo
TTL curto observado, provavelmente exige carregar a página do Forms de novo a cada handful de
chamadas (ou por chamada). Isso não elimina a dependência de browser, só muda o formato: em vez de
"navegar clicando em cada resposta", vira "recarregar a página do Design para colher um token novo
antes de cada rajada de chamadas à API". Pode ainda ser mais rápido que o scraping atual (que abre
o Forms, navega resposta a resposta com sleeps), mas é bem mais frágil e complexo do que o desenho
original do plano (cliente HTTP puro reutilizando cookies indefinidamente) — e o ganho de
velocidade real é incerto sem medir o TTL exato do token, o que exigiria mais instrumentação.

**Reportado ao usuário, que pediu para medir o TTL do token antes de desistir — ver seção seguinte.**

## Medição do TTL (autorizada pelo usuário) — resultado: NÃO é o token que expira rápido

Capturamos cookies+headers uma vez (via Playwright, contexto mantido aberto) e reusamos o MESMO
snapshot em checkpoints crescentes via `httpx` puro, sem tocar o navegador de novo:

```
t=5.4s   -> status=200
t=10.0s  -> status=200
t=30.0s  -> status=200
t=60.0s  -> status=200
t=120.0s -> status=200
t=240.0s -> status=200
```

**O token durou pelo menos 240s sem cair.** A hipótese de TTL curto (seção anterior) estava errada —
o 401/711 anterior foi porque o teste comparou um `__requestverificationtoken` capturado agora
contra cookies **antigas** do `state.json` salvo em disco (arquivo desatualizado), não porque o
token expira em segundos.

## Teste decisivo: reconstrução 100% sem navegador

Com um `state.json` **recém-salvo** (`ctx.storage_state()` logo após o page load), montamos um
cliente `httpx` puro que:
- carrega os cookies do arquivo;
- lê o cookie `__RequestVerificationToken` e o ecoa como header `__requestverificationtoken`
  (dupla submissão CSRF — não precisa de navegador, é leitura direta do arquivo);
- manda os headers `x-ms-form-*`/`x-usersessionid` com **valores arbitrários** (não capturados de
  lugar nenhum — UUID aleatório e uma string de zeros).

Resultado: **`STATUS 200`**, corpo JSON real do formulário (`createdBy`,
`collectionId`, etc.). Ou seja, `x-usersessionid`/`x-ms-form-muid` são só telemetria — não são
validados pelo servidor. O único requisito real é cookies + o cookie CSRF ecoado como header.

**Teste de durabilidade:** repetimos a mesma reconstrução contra o `state.json` **antigo** (o
arquivo que já existia em disco antes desta investigação, não o recém-salvo) — mesmo token CSRF
(valor idêntico), mas voltou a dar `401`/`711 "The token is expired"`. Ou seja, alguma OUTRA
cookie de sessão (não o CSRF) precisa estar "fresca" — a mesma dependência de sessão que o scraper
Playwright já tem hoje (por isso existe `scripts/capturar_sessao_forms.py` e o fluxo de renovar
`state.json`). Não é uma fragilidade nova introduzida pela API.

## Conclusão final

**A abordagem é viável.** Um cliente HTTP puro (sem Playwright, sem `sync_playwright`/`async_playwright`
em tempo de execução, só `httpx` + o `state.json` já existente) autentica e lê dados reais do Forms,
desde que a sessão salva esteja "fresca" — mesma barra que o scraper atual já exige. Os achados
originais desta seção (host correto = `forms.cloud.microsoft`, URL com `tenantId`/`userId`, header
`__requestverificationtoken` derivado do cookie) são as correções que as Tasks 1-3 do plano
(`forms_api_cliente.py`, `forms_api_conversor.py`, integração no `FormsExtractor`) precisam
incorporar em vez do formato originalmente assumido (`forms.office.com/formapi/api/forms('id')`
com `Authorization` bearer). O plano original (Tasks 1-4) pode ser retomado com esse formato
corrigido.

`tenantId`/`userId` confirmados nesta conta: `b3308b02-3160-463b-8b8c-cb0f556f4e77` /
`5fd503f6-bf9f-4c2c-b305-a33259dc8147` — precisam ser descobertos uma vez por conta (não mudam),
não por chamada.
