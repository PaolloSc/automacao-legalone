# Todo: Agente de Teste E2E — Copilot Studio → Cadastro no LegalOne

> Plano completo em `tasks/plan.md`. Sem ambiente de homologação do
> LegalOne — Nível C escreve em produção, por isso é sempre manual/gated.

## Fase 1 — Fixtures (fundação)
- [ ] Task 1: `tests/fixtures/copilot_payloads.py` com 5 payloads (um por
  tipo_cadastro), CNJ/nomes prefixados `TESTE-E2E-AGENTE`, incluindo casos
  sujos (papel colado no nome/posição, CNPJ colado no contrário)

**Checkpoint Fase 1:** fixtures importam, revisão humana do conteúdo.

## Fase 2 — Nível A: pipeline mockado (sem rede, sem browser)
- [ ] Task 2b: extrair classificação `_campos_base` de
  `automacao_legalone_completa.py` pra função pura testável (refactor sem
  mudar comportamento)
- [ ] Task 2: testar que `dados_diretos` → `dados_processo` classifica
  campos base vs. `outros_dados` corretamente, pras 5 fixtures
- [ ] Task 3: fake `Page`/`Locator` do Playwright que grava (não digita de
  verdade) o que `legalone_cadastro.py` preencheria — provar que os campos
  sujos (posição/cliente/contrário) saem limpos antes de "chegar" no
  formulário

**Checkpoint Fase 2:** `pytest tests/ -q` 100% verde, zero rede/browser,
cobre os 3 bugs reais já corrigidos como teste de regressão.

## Fase 3 — Nível B: Copilot Studio real (para antes do LegalOne)
- [ ] Task 4: subagent `.claude/agents/e2e-copilot-legalone.md` que abre o
  chat de teste do Copilot Studio, manda petição fixture, captura a
  extração final
- [ ] Task 5: confirmar que o email com o JSON chega certo (reusa
  `OutlookMonitorGraph` real)

**Checkpoint Fase 3:** execução manual, nunca CI; revisão humana antes de
decidir se a Fase 4 roda.

## Fase 4 — Nível C: cadastro real no LegalOne (opt-in, gated)
- [ ] Task 6: handoff do email real pro bot real (Playwright real, login
  real), só com prefixo de teste + confirmação humana explícita

**Checkpoint Fase 4:** nunca automático; checklist de limpeza manual
pós-teste (sem API de exclusão configurada).

## Perguntas em aberto (ver plan.md)
- [ ] Existe homologação do LegalOne que eu não achei?
- [ ] Já existe convenção de "processo de teste" no escritório?
- [ ] Quem vai disparar o subagent de Nível B/C no dia a dia?
- [ ] Task 2b (extrair função) pode tocar `automacao_legalone_completa.py`,
  ou prefere manter inline e mockar mais pesado no teste?
