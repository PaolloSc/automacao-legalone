# Prompt de Refatoração Estrutural — Fluxo Sequencial de Cadastro no Legal One

## ✅ Status: implementado em 27/08/2026 (branch `refactor/legalone-fase-sequencial`, mergeada em `master` @ `271939f`)

Investigação prévia mostrou que quase todos os campos já eram preenchidos hoje — só fora de ordem, com uma chamada duplicada/insegura e dois pontos sem a regra de negócio pedida. Em vez de reescrever tudo do zero, o refactor **reorganizou/extraiu** a lógica já validada em produção e só criou o que realmente faltava. Plano completo com investigação e decisões: `docs/superpowers/plans/2026-08-27-legalone-fase-refactor.md` (repo `Codigo`).

O que foi feito, commit a commit:
- `7c3a1e8` — extraído `salvar_e_fechar_cadastro()` do bloco duplicado dentro de `realizar_acoes_pos_cadastro`
- `8720fe2` — **bug real corrigido**: removido `_preencher_lookups_edicao`, que sobrescrevia Órgão/Procedimento/Fase sem checar se já vieram preenchidos do tribunal (causa provável da "perda de valores em comboboxes" citada no objetivo acima)
- `8ea8a34`/`2a0c268` — removida chamada no-op de preenchimento de Fase 2/3 antes do save da capa (mantida a mesma chamada no branch de rascunho, não verificado)
- `aaf9a2a` — regra **Pro Bono** implementada (Fase 1, item 7)
- `2e07ab0` — validação condicional de **justificativa obrigatória** implementada (Fase 3, itens 5-6)
- `67755cf` — wrappers `preencher_fase1_capa`/`preencher_fase2_processual`/`preencher_fase3_risco_honorarios` adicionados, orquestrando os métodos acima na ordem pedida
- `271939f` — corrigido um `@staticmethod` órfão (efeito colateral da remoção do `8720fe2`) achado pela review final, que quebrava 4 call sites em runtime; adicionado teste de guarda genérico contra essa classe de bug

**Desvios deliberados do texto abaixo** (ver seção "Requisitos Técnicos" para detalhes):
- **"Tipo de ação" não pôde ficar na Fase 1** — o elemento não existe no DOM da tela de capa antes do save; já é coberto por `preencher_fase2_processual`.
- **`legalone_field_resolver.py` não tem/não é a função resiliente de combobox** — esse módulo é um resolver HTTP nome→ID usado só pelo pipeline REST alternativo (`legalone_api_cadastro.py`), nunca importado pelo fluxo Playwright deste arquivo. O padrão real e já validado em produção é `preencher_campo_autocomplete` (bento-combobox) e `_preencher_lookup_por_id` (jQuery lookup) — ver "Requisitos Técnicos" abaixo.
- **`notificar_conclusao(dados)` não foi criado** — já existe como `_enviar_email_sucesso` em `automacao_legalone_completa.py`, já consome o canal `_qa_warnings` que agora carrega os alertas de Pro Bono e de justificativa.
- **`salvar_e_fechar_cadastro`** ficou como método de instância (`self.salvar_e_fechar_cadastro()`), não função `(page)` solta — segue o padrão do resto da classe.

Os 3 wrappers de fase existem e são testados, mas **não substituem** as chamadas diretas dentro de `cadastrar_processo`/`realizar_acoes_pos_cadastro` (que continuam chamando os métodos de origem diretamente) — decisão deliberada para não trocar uma sequência de chamadas já validada em produção por uma nova e não testada em campo, minimizando risco à automação ao vivo.

### 🐛 Correções adicionais (31/08/2026, `fix/code-review-27-08` → `master` @ `3ff48ef`)

Depois do refactor acima, um `/code-review` sobre o pacote inteiro achou 8 bugs em código que este plano não tocou (não são parte da sequência de fases, mas afetam o mesmo fluxo de cadastro). 6 foram corrigidos, revisados e mergeados:

- **`_parse_moeda_br`** (`legalone_cadastro.py`) — `"150.000"` (formato BR sem vírgula) virava `150.0` em vez de `150000.0`: undercount de 1000x em valor de causa/acordo/honorários/custas. Corrigido: ponto sem vírgula em grupos de 3 dígitos agora é reconhecido como separador de milhar.
- **`_CUSTAS_TIPO`** (`legalone_cadastro.py`, extraído para `_resolver_custas_tipo`) — `"Desfavorável"` escolhia `CostsType='0'` (Favorável) em vez de `'1'` (Desfavorável), porque `'favoravel'` é substring de `'desfavoravel'` nos dois sentidos do match antigo. Corrigido: match unidirecional, ordenado por tamanho decrescente.
- **`rotulos_email_sucesso`** (`automacao_legalone_completa.py`) — recurso cível (`RECURSO_CIVEL`, mapeado por `forms_mapping_civel.py`) caía no e-mail genérico `[OK CADASTRO]` em vez de `[OK RECURSO]`; mesmo buraco no log de console equivalente. Ambos corrigidos.
- **`_preencher_ficha_forms`** (`legalone_cadastro.py`) — o retorno `(ok, falhas)` era descartado nos dois pontos de chamada; falhas ao preencher Responsabilidade/Cobrança de Honorários (campos movidos pro `_PERSONALIZADOS_*` durante o refactor de fases) sumiam sem nenhum aviso. Agora entram no log/aviso de falhas.
- **`_capturar_numero_pasta`** (`legalone_cadastro.py`) — um fallback fraco aceitava qualquer título de página com menos de 80 caracteres, incluindo títulos genéricos tipo "Editar processo", como se fosse o número da pasta. Restrito ao campo "Pasta" do formulário.
- **Código morto** em `_preencher_pedidos_recurso` (`legalone_cadastro.py`) — `logger.info`/`return` inalcançáveis após um `return` anterior, referenciando uma variável `ok` nunca definida. Removido.

Não corrigidos (julgamento documentado, review concordou que é razoável adiar):
- **Fallback do `FormsExtractor Enhanced`** (`automacao_legalone_completa.py`) continua agnóstico de natureza (Cível vs. Trabalhista) — não recebe `modulo_mapeamento`, então pode perder/sobrescrever campos específicos quando dispara para Cível. Corrigir de verdade exige dar ao extrator NLP consciência de natureza — mudança maior que cabia nesta rodada. Mitigado com `logger.warning` explícito em vez de falha silenciosa.
- **Lista de stopwords** hand-maintained pra desambiguar nome de tribunal (`legalone_cadastro.py`) — observação de manutenibilidade (cada novo par de tribunais parecidos exige mais uma entrada manual), não um bug concreto. Não mexido.

535 testes passando (1 falha pré-existente e não relacionada: módulo `langchain_deepseek` ausente no venv compartilhado do monorepo).

---

## 🎯 Objetivo
Refatorar o fluxo de automação de cadastro no **Legal One** (localizado no repositório/pasta do projeto) para que a execução siga estritamente uma sequência determinística de 4 fases funcionais. Atualmente, os campos estão misturados no código, gerando falhas de concorrência, perda de valores em dropdowns/comboboxes e envios prematuros de confirmação.

---

## 🏗️ Nova Estrutura Arquitetural do Fluxo

Reorganize e refatore o script de cadastro principal (ex: `legalone_cadastro.py` / `automacao_legalone_completa.py`) e os seus arquivos auxiliares de mapeamento para obedecer a seguinte ordem de execução:

```
[ INÍCIO ]
   │
   ├──▶ FASE 1: Tela de Novo Cadastro (Capa do Processo)
   │       └── [ Ação: Salvar Capa / Gravação Inicial ]
   │
   ├──▶ FASE 2: Dados Processuais, Localização & Pedidos
   │
   ├──▶ FASE 3: Previsão, Resultado, Risco & Regras de Honorários
   │       └── [ Ação: Salvar e Fechar Formulário ]
   │
   └──▶ FASE 4: Validação Pós-Gravação & Notificação de Sucesso
           └── [ Envio de Confirmação ]
```

---

## 📋 Detalhamento das Etapas de Preenchimento

### FASE 1: Tela de Novo Cadastro (Capa Inicial) — ✅ `preencher_fase1_capa` (legalone_cadastro.py)
Preencher exclusivamente os seguintes campos iniciais da capa:
1. ✅ **Ativar o monitoramento** (Checkbox/Switch) — `_configurar_monitoramento_se_disponivel`
2. ✅ **Título** (Input text)
3. ✅ **Cliente principal** (Combobox / Autocomplete)
4. ✅ **Posição** (Combobox)
5. ✅ **Contrário principal** (Combobox / Autocomplete)
6. ✅ **Responsável principal** (Combobox)
7. ✅ **Negociação de contrato de honorários:**
   * *Regra de Negócio:* Caso o campo esteja vazio/ausente nos dados de entrada, selecionar a opção **"Pro Bono"**, mas emitir um log de alerta (`WARNING`) e registrar no objeto da execução que a alteração posterior é necessária. — implementado em `aaf9a2a` (`_qa_warnings` + `logger.warning`)
8. ⚠️ **Tipo de ação** (Combobox / Autocomplete) — **não é possível na Fase 1**: o campo não existe no DOM da tela de capa antes do save (só aparece na tela de edição pós-save). Coberto por `preencher_fase2_processual` via `_FICHA_LOOKUPS['TipoAcao']`.
9. ✅ **Centro de custo** (Combobox)
10. ✅ **Datacloud configurado?** (Campo de confirmação/status)
11. ✅ **Você cadastrou o Centro de Custo** (Confirmação visual/checagem)

➡️ **Ação de Transição:** ✅ já existia (`clicar_salvar()`, chamado logo após esta fase em `cadastrar_processo`) — não precisou ser criada, só limpa de chamadas de Fase 2/3 prematuras (removidas em `8ea8a34`/`2a0c268`).

---

### FASE 2: Dados Processuais & Localização — ✅ `preencher_fase2_processual` (legalone_cadastro.py)
Preencher a estrutura processual e localização na ordem:
1. ✅ **Órgão** — `_FICHA_LOOKUPS`, com guard só-se-vazio (o duplicado inseguro `_preencher_lookups_edicao` foi removido em `8720fe2`)
2. ✅ **Procedimento** — idem
3. ✅ **Fase** — idem
4. ✅ **Instância**
5. ✅ **Comarca / Foro**
6. ✅ **Vara / Turma**
7. ✅ **Pedidos** — `_preencher_pedidos_forms`
8. ✅ **Vínculos** (preencher somente se houver dados informados) — já condicionado a `if valor:`

---

### FASE 3: Previsão, Resultado, Risco & Regras de Honorários — ✅ `preencher_fase3_risco_honorarios` (legalone_cadastro.py)
Preencher a seção financeira e de valoração de risco do processo:
1. ✅ **Contingência** — `_preencher_previsao_e_resultado`
2. ✅ **Probabilidade atual** — por linha de pedido (campo do LegalOne, não do painel), em `_preencher_classificacoes_pedidos`
3. ✅ **Risco** — `_preencher_previsao_e_resultado`
4. ✅ **Responsabilidade** (Direta, Subsidiária ou Solidária) — `_PERSONALIZADOS_LOOKUP`
5. ✅ **Cobrança de Honorários Sucumbenciais?** (Sim/Não)
   * *Regra:* Se a resposta for **Não**, preencher obrigatoriamente a **Justificativa da não cobrança de honorários sucumbenciais**. — implementado em `2e07ab0` (`_validar_justificativas_honorarios`, avisa via `_qa_warnings` quando falta)
6. ✅ **Cobrança de Honorários Contratuais de Êxito?** (Sim/Não)
   * *Regra:* Se a resposta for **Não**, preencher obrigatoriamente a **Justificativa da não cobrança de honorários contratuais de êxito**. — idem

➡️ **Ação de Transição:** ✅ `salvar_e_fechar_cadastro()` (extraído em `7c3a1e8` do bloco que antes vivia duplicado inline).

---

### FASE 4: Finalização & Notificação — ✅ já existia
1. ✅ Validar se o formulário foi salvo com sucesso (sem mensagens de erro do Legal One no DOM). — `_confirmar_no_acervo`
2. ✅ Disparar a mensagem/e-mail de **confirmação de cadastro concluído** com o resumo dos dados cadastrados e o alerta de "Pro Bono" (se aplicável). — `_enviar_email_sucesso` (`automacao_legalone_completa.py`), já lê `_qa_warnings`, que agora carrega os alertas de Pro Bono e de justificativa.

---

## 🛠️ Requisitos Técnicos de Implementação para o Codebase

1. ⚠️ **Tratamento de Combobox / Autocomplete — premissa corrigida:**
   * `legalone_field_resolver.py` **não** tem essa função e **não é usado** no fluxo Playwright deste arquivo — é um resolver HTTP nome→ID usado só pelo pipeline REST alternativo (`legalone_api_cadastro.py`). Confirmado por grep: zero imports desse módulo em `legalone_cadastro.py`.
   * A função resiliente real, já usada consistentemente em produção, é `preencher_campo_autocomplete` (bento-combobox da tela de capa: foca → digita → espera dropdown → extrai opções via JS → fuzzy match → clica) e `_preencher_lookup_por_id` (jQuery lookup da tela de edição: `#<base>Text`/`#<base>Id`). `press_sequentially` existe no arquivo mas só em 3 pontos pontuais, não é o mecanismo geral.

2. ✅ **Separação em Funções/Módulos Limpos** — implementado como orquestradores finos sobre a lógica já existente (não reescrita do zero, para não arriscar comportamento validado em produção):
   * ✅ `preencher_fase1_capa(self, dados)` — `67755cf`
   * ✅ `preencher_fase2_processual(self, dados)` — `67755cf`
   * ✅ `preencher_fase3_risco_honorarios(self, dados)` — `67755cf`
   * ✅ `salvar_e_fechar_cadastro(self)` — `7c3a1e8` (método de instância, não função `(page)` solta — segue o padrão do resto da classe)
   * ⚠️ `notificar_conclusao(dados)` — não criado; já existe como `_enviar_email_sucesso` em `automacao_legalone_completa.py`, sem necessidade de duplicar

3. ✅ **Mantenha os Testes e Mapeamentos Atualizados:**
   * Testes novos por task: `test_salvar_e_fechar_cadastro.py`, `test_lookups_edicao_nao_sobrescreve.py`, `test_negociacao_pro_bono.py`, `test_justificativa_honorarios.py`, `test_nenhum_metodo_de_instancia_virou_staticmethod.py` (guarda genérica contra bug de `@staticmethod` órfão), mais 3 métodos novos em `test_superficie_legalone_cadastro.py`. Seguem o padrão do repo (`inspect.getsource()`/introspecção estática, sem mocks pesados de `Page` do Playwright) em vez de reescrever `test_e2e_mock_pipeline.py` (que mocka `cadastrar_processo` inteiro e não exercita lógica interna de fase).

---
*Por favor, aplique esta refatoração mantendo a compatibilidade com a arquitetura do projeto já existente.*
