# Fluxo: Validação no Teams (advogado → Maria → canal)

Motivo: depois do cadastro, o advogado responsável e a Maria Karolyne
(revisão) precisam confirmar que o processo está certo, com um botão de
verdade no Teams — não um e-mail que ninguém responde. Um card com botão
clicável dentro do Teams só funciona sem bot registrado através da ação
nativa do Power Automate **"Postar cartão adaptável e aguardar uma
resposta"**; ela já cuida de postar o card, esperar o clique e devolver a
resposta pro fluxo continuar. Por isso quem posta a mensagem não é o Python
— é esse fluxo.

O bot (`automacao_legalone_completa.py`, método `_notificar_teams_sucesso`)
só faz um POST simples nessa URL depois de um cadastro bem-sucedido, com os
dados do processo, do advogado e da Maria.

## Desenho geral

```
HTTP trigger
  → Card pro advogado (Validei / Não validei + campo Motivo)
    ├─ Validei
    │   → Card pra Maria (Validei / Não validei + campo Motivo)
    │       ├─ Validei  → posta no canal "Processos Validados" (Carvalho & Furtado Advogados - geral)
    │       └─ Não validei → e-mail "LegalOne - Correcao Necessaria" (quem_recusou=maria)
    └─ Não validei
        → avisa a Maria por texto simples
        → e-mail "LegalOne - Correcao Necessaria" (quem_recusou=advogado)
```

O canal "Processos Validados" tem moderação ativada (só o Flow bot posta,
ninguém responde — configurado em Gerenciar canal → Moderação, exige ser
Team owner do "Carvalho & Furtado Advogados - geral").

O e-mail de correção é lido pelo `outlook_monitor_graph.py` (mesmo padrão do
Copilot/Forms — chave `dados_correcao` em vez de `dados_diretos`) e vira uma
tarefa no LegalOne pro advogado responsável via
`legalone_cadastro.criar_tarefa_correcao()`, com o motivo na descrição.

## O fluxo, passo a passo

**Onde:** https://make.powerautomate.com → Criar → Fluxo de nuvem automatizado

1. **Gatilho:** "Quando uma solicitação HTTP for recebida"
   - **"Quem pode acionar o fluxo?" = `Anyone`** (não `Any user in my tenant`,
     que é o padrão). Com `Any user in my tenant` o endpoint exige um token
     OAuth do Azure AD em todo POST (erro `DirectApiAuthorizationRequired`,
     HTTP 401) — o Python manda só um POST simples, sem token, então precisa
     ser `Anyone` (a segurança fica na própria URL, que carrega um `sig=`
     assinado).
   - Copie a URL completa pelo botão de copiar ao lado do campo **depois**
     de salvar com `Anyone` selecionado — só aí ela sai com o `sig=`. Isso
     vai em `TEAMS_VALIDACAO_FLOW_URL` no `.env`.
   - Esquema JSON do corpo:
     ```json
     {
       "type": "object",
       "properties": {
         "cnj": { "type": "string" },
         "pasta": { "type": "string" },
         "cliente": { "type": "string" },
         "contrario": { "type": "string" },
         "advogado_nome": { "type": "string" },
         "advogado_email": { "type": "string" },
         "maria_email": { "type": "string" }
       }
     }
     ```

2. **Ação:** Microsoft Teams → **"Postar cartão adaptável e aguardar uma resposta"** (pro advogado)
   - Postar como: Flow bot · Postar em: Chat com o Flow bot
   - Destinatário: `advogado_email`
   - Card:
     ```json
     {
       "type": "AdaptiveCard",
       "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
       "version": "1.4",
       "body": [
         { "type": "TextBlock", "text": "Processo cadastrado - confirme os dados", "weight": "Bolder", "size": "Medium" },
         { "type": "FactSet", "facts": [
           { "title": "CNJ", "value": "@{triggerBody()?['cnj']}" },
           { "title": "Pasta", "value": "@{triggerBody()?['pasta']}" },
           { "title": "Cliente", "value": "@{triggerBody()?['cliente']}" },
           { "title": "Contrario", "value": "@{triggerBody()?['contrario']}" }
         ]},
         { "type": "Input.Text", "id": "motivo", "placeholder": "Se nao validou, o que precisa ajustar? (opcional)", "isMultiline": true }
       ],
       "actions": [
         { "type": "Action.Submit", "title": "Validei", "data": { "resposta": "Validei" } },
         { "type": "Action.Submit", "title": "Não validei", "data": { "resposta": "Nao validei" } }
       ]
     }
     ```

3. **Condição** — `@{body('Post_adaptive_card_and_wait_for_a_response')?['data']?['resposta']}` **é igual a** `Validei`.

4. **Ramo True (advogado validou):** Microsoft Teams → **"Postar cartão adaptável e aguardar uma resposta"** de novo, agora pra Maria (`maria_email`), mesmo card (troca o texto do topo pra "Advogado validou - sua confirmacao final" e adiciona um fact "Advogado" com `advogado_nome`).

   4.1 **Condição 1** dentro do True — mesma lógica, sobre a resposta *dessa* ação (`Post_adaptive_card_and_wait_for_a_response_1`):
     - **True (Maria validou):** "Postar mensagem em um chat ou canal" → Postar em: **Canal** → Equipe "Carvalho & Furtado Advogados - geral" → Canal "Processos Validados". Mensagem: `✅ Processo validado — CNJ @{triggerBody()?['cnj']} (Pasta @{triggerBody()?['pasta']}) | Cliente: @{triggerBody()?['cliente']} | Advogado: @{triggerBody()?['advogado_nome']} | Conferido por: Maria Karolyne Moraes`
     - **False (Maria não validou):** Office 365 Outlook → "Send an email (V2)" — ver seção **E-mail de correção** abaixo, com `quem_recusou: "maria"` e o motivo vindo de `@{body('Post_adaptive_card_and_wait_for_a_response_1')?['data']?['motivo']}`.

5. **Ramo False (advogado não validou):**
   - "Postar mensagem em um chat ou canal" pra Maria (texto simples, avisando que não validou).
   - Office 365 Outlook → "Send an email (V2)" de correção, com `quem_recusou: "advogado"` e motivo de `@{body('Post_adaptive_card_and_wait_for_a_response')?['data']?['motivo']}`.

## E-mail de correção

Quando alguém clica "Não validei" (advogado ou Maria), o fluxo manda um
e-mail pro Outlook monitorado (mesma caixa do Forms/Copilot) com:

- **Para:** `paollo.sanchez@carvalhofurtadoadv.com.br`
- **Assunto (exato):** `LegalOne - Correcao Necessaria` — é assim que
  `outlook_monitor_graph.py` reconhece (`CORRECAO_ASSUNTO`)
- **Corpo (JSON puro, sem HTML — cole direto, sem usar o editor rich text):**
  ```json
  {
    "cnj": "@{triggerBody()?['cnj']}",
    "pasta": "@{triggerBody()?['pasta']}",
    "advogado_email": "@{triggerBody()?['advogado_email']}",
    "advogado_nome": "@{triggerBody()?['advogado_nome']}",
    "quem_recusou": "advogado ou maria",
    "motivo": "@{body('...')?['data']?['motivo']}"
  }
  ```

O bot detecta esse e-mail (`dados_correcao` em vez de `dados_diretos`),
pula todo o fluxo de cadastro e chama
`self.legalone.criar_tarefa_correcao(dados_correcao)` — cria uma tarefa no
processo (mesmo mecanismo de `criar_tarefas_pos_cadastro`), atribuída ao
`advogado_email`/`advogado_nome` do payload, com o motivo na descrição:
`"Corrigir processo {cnj} — reprovado por {quem}: {motivo}"`.

## Como testar

1. Salve o fluxo e copie a URL do gatilho HTTP pro `.env`
   (`TEAMS_VALIDACAO_FLOW_URL=...`).
2. Dispare um POST de teste (`curl`) e confira se o card chegou no chat do
   advogado no Teams, com o campo de motivo.
3. Clique "Validei" → confere se o card da Maria chegou.
4. Clique "Validei" na Maria → confere se a mensagem apareceu no canal
   "Processos Validados".
5. Repita preenchendo o motivo e clicando "Não validei" (advogado ou Maria)
   → confere se o e-mail "LegalOne - Correcao Necessaria" chegou com o JSON
   certo, e se rodar o bot, se a tarefa de correção foi criada no LegalOne.

**Validado ao vivo em 11/09/2026** (fluxo completo — 2 cards, canal e e-mail
de correção — testado com o próprio usuário em todos os papéis via `curl` +
cliques reais no Teams): card do advogado com campo motivo ok, card da Maria
ok, postagem no canal ok, e-mail de correção chegou com JSON correto
(`quem_recusou`, `motivo` incluídos). A criação da tarefa de correção no
LegalOne (`criar_tarefa_correcao`) ainda não foi testada ao vivo — só a
lógica pura (`_montar_tarefa_correcao`, testada em
`tests/test_tarefa_correcao.py`); a parte Playwright reaproveita
`_criar_uma_tarefa`, que também não foi validada ao vivo (ver
`ponytail:` em `_abrir_nova_tarefa`).

## Por que não a integração antiga (Graph app-only)

Uma versão anterior deste fluxo usava o Graph API direto (`POST
/teams/{id}/channels/{id}/messages`, com as permissões `ChannelMessage.Send`
e `User.Read.All` no app registration). Isso posta texto simples com
@menção, mas não dá pra ter um botão clicável de verdade sem registrar um
bot completo no Bot Framework — trabalho desproporcional pro que era só
"apertar um botão". O Power Automate já resolve isso com autenticação
própria (a conta de quem monta o fluxo), sem precisar desse app registration
nem das permissões extras.
