# Edição pendente no prompt do agente (regra de agregação do `risco`)

> **Status 09/08/2026:** aplicado.
> - Local: `docs/COPILOT_AGENTE.md`
> - Copilot Studio (Extrator): Instruções salvas em **7962/8000** e publicação
>   disparada (`Forçar a versão mais recente` desmarcado).

Três substituições nas **Instruções** do agente "Extrator de Dados de Petições".
Saldo: **7938 → 7962** caracteres (limite 8000, sobram 38).

Ordem importa pouco, mas faça a 1 antes da 2 — é ela que libera espaço.

---

## 1. Encurtar o parágrafo de jurisprudência (libera 39 caracteres)

**DE:**
```
Para cada pedido, confronte a tese com jurisprudencia consolidada pesquisando em tst.jus.br, stj.jus.br, stf.jus.br e jusbrasil.com.br.
```

**PARA:**
```
Confronte cada tese com jurisprudencia em tst.jus.br, stj.jus.br, stf.jus.br e jusbrasil.com.br.
```

## 2. A regra nova do `risco` (ocupa 65)

**DE:**
```
risco = coluna risco da tabela jurimetria_<tribunal>.md (Conhecimento), pelo assunto de cada pedido. Fora da tabela ou sem lide: Medio. Valor relevante agrava um grau.
```

**PARA:**
```
risco de cada pedido = coluna risco da tabela jurimetria_<tribunal>.md (Conhecimento), pelo assunto. Pedido fora da tabela ou sem lide: escreva "sem base", nunca Medio. risco do PROCESSO = o do pedido de MAIOR valor; empate, o pior.
```

## 3. Levar a tabela por pedido para o registro (libera 2)

**DE:**
```
Envie tambem justificativa_probabilidade: 1 a 3 linhas com as teses e a fonte.
```

**PARA:**
```
Envie justificativa_probabilidade: teses, fonte e a tabela risco por pedido.
```

---

## Por que assim

**"Pior caso" foi descartado com dado, não por gosto.** Dos 12 assuntos mais
frequentes do TRT3, quatro são risco Alto — multa do 477 (195.460 julgados),
aviso prévio (183.564), multa do 467 (145.905) e anotação de CTPS (109.846).
Uma reclamação comum traz os quatro. Com "prevalece o pior", todo processo
trabalhista sairia Alto e o campo pararia de informar — um valor constante com
aparência de medição.

**"Predominante" também não serve:** a moda da tabela dá o mesmo peso a uma
multa de R$ 2 mil e a uma insalubridade de R$ 80 mil.

**Maior exposição financeira** é a regra que sobrou, e ela tem três méritos:
espelha como o caso é lido na prática ("o que decide esse processo é a
insalubridade"); é uma frase, não uma fórmula com pesos, então qualquer um
refaz a conta e chega no mesmo número; e é determinística — média ponderada
com arredondamento oscila na borda, essa não.

**A separação "sem base" vs. Medio** conserta um defeito que já existe: hoje
Medio significa tanto "medido, ficou no meio" quanto "não achei o pedido na
tabela". São coisas opostas saindo com o mesmo rótulo, e quem revisa acaba
desconfiando de todo Medio.

**A tabela por pedido no `justificativa_probabilidade`** existe porque um campo
único é resumo, e resumo sem memória de cálculo não se audita. O campo diz
"Alto", o registro diz por quê — pedido a pedido, com taxa e fonte. Esse campo
já cai em `outros_dados` (`automacao_legalone_completa.py:513`) e chega no
LegalOne sem mudança de código.

---

## Como aplicar

Visão geral → Instruções → **Editar** → as três substituições → **Salvar** →
**Publicar** (sem marcar "forçar a versão mais recente", que derruba conversas
ativas no Teams).

Depois, um teste de regressão que vale a pena: o mesmo caso do TRT3 com valores
por pedido (ex.: insalubridade R$ 80 mil, multa do 477 R$ 2 mil). O `risco` do
processo tem de sair **Médio** — o da insalubridade, que concentra o valor — e
não Alto por causa da multa.
