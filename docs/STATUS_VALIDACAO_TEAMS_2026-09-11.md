# Status — Tarefas pós-cadastro + Validação Teams + Correção (11/09/2026)

Nota de handoff: o que foi construído nesta sessão, o que já está validado,
e o que falta pra considerar tudo pronto pra produção.

## O que foi pedido

1. Depois do cadastro, criar 2 tarefas no LegalOne: Maria Karolyne revisa,
   advogado responsável toma ciência.
2. Notificar o advogado no Teams com botão Validei/Não validei.
3. Só depois que a Maria TAMBÉM validar (card dela, por último), postar
   automaticamente num canal "Processos Validados" — canal onde ninguém
   responde, só o fluxo posta.
4. Se alguém clicar "Não validei" (advogado ou Maria), preencher um motivo
   e criar automaticamente uma tarefa de correção no LegalOne.

## O que está feito

### Código (testado, TDD, todos os testes verdes)

| Arquivo | O que mudou |
|---|---|
| `legalone_cadastro.py` | `_resolver_advogado_responsavel`, `_montar_tarefas_pos_cadastro`, `criar_tarefas_pos_cadastro` (as 2 tarefas pós-cadastro) · `_montar_tarefa_correcao`, `criar_tarefa_correcao` (tarefa quando alguém recusa) |
| `automacao_legalone_completa.py` | `_montar_payload_teams_validacao`, `_notificar_teams_sucesso` (aciona o fluxo do Power Automate) · roteamento de e-mails `dados_correcao` pra `criar_tarefa_correcao`, pulando o cadastro |
| `outlook_monitor_graph.py` | reconhece o assunto `LegalOne - Correcao Necessaria` e extrai o JSON (`CORRECAO_ASSUNTO`) |
| `.env.example` | `TEAMS_VALIDACAO_FLOW_URL` |
| Testes novos | `tests/test_tarefas_pos_cadastro.py`, `tests/test_teams_notificacao.py`, `tests/test_tarefa_correcao.py` — todos passando |

### Infraestrutura Teams / Power Automate (testada ao vivo)

- Fluxo **"Validacao Teams - Cadastro LegalOne"** criado em
  make.powerautomate.com, URL real gravada em `pacote_automacao_legalone/.env`
  (`TEAMS_VALIDACAO_FLOW_URL`).
- Canal **"Processos Validados"** criado no Team "Carvalho & Furtado
  Advogados - geral", com **moderação ativada** (só o Flow bot posta,
  ninguém responde).
- Fluxo completo testado via `curl` + cliques reais no Teams: card do
  advogado (com campo Motivo) → card da Maria → posta no canal quando ela
  valida → e-mail `LegalOne - Correcao Necessaria` quando qualquer um dos
  dois recusa, com o motivo certo no corpo.
- Documentação completa do fluxo (passo a passo pra recriar/ajustar no
  Power Automate): `docs/FLUXO_TEAMS_VALIDACAO.md`.

## O que NÃO está validado ainda

1. **`criar_tarefas_pos_cadastro` e `criar_tarefa_correcao` (lado
   Playwright) nunca rodaram contra o LegalOne de verdade.** Só a lógica
   pura foi testada (quais dados vão em cada tarefa, prazo, etc). O clique
   real em "Adicionar → Nova tarefa" dentro do LegalOne é o ponto mais
   arriscado — uma exploração anterior (10/09) achou esse popover instável
   via automação, e o método `_abrir_nova_tarefa` tem múltiplas estratégias
   de retry sem confirmação de qual (ou se alguma) funciona. Tem um
   `ponytail:` no código apontando isso e o plano B (POST direto no
   endpoint) se o clique continuar falhando.
2. **`_notificar_teams_sucesso` (lado Python) nunca chamou a URL do fluxo de
   verdade em produção** — só testei manualmente via `curl` simulando o
   payload. Precisa rodar um cadastro real (ou um teste dirigido) pra
   confirmar que o Python monta o payload certo e aciona o fluxo.
3. **Ninguém testou o caminho fim-a-fim de verdade**: cadastro real →
   tarefas no LegalOne → card no Teams → validação → canal / correção →
   tarefa de correção no LegalOne.

## Próximos passos sugeridos (quando retomar)

1. Rodar um cadastro de teste real (CNJ de teste, não produção) pelo
   pipeline inteiro e observar os logs — confirmar que
   `criar_tarefas_pos_cadastro` consegue mesmo abrir "Nova tarefa" no
   LegalOne, ou se cai no fallback/falha (e nesse caso, decidir entre
   consertar o clique ou migrar pro POST direto, como já discutido).
2. Confirmar que `_notificar_teams_sucesso` está sendo chamado no ponto
   certo do pipeline (`automacao_legalone_completa.py`, após e-mail de
   sucesso) e que o payload bate com o que o fluxo espera.
3. Depois que os dois acima funcionarem, testar o caminho completo com um
   CNJ de teste real, do cadastro até o canal "Processos Validados".
