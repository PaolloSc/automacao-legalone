# Spec: Embargos de terceiro — vínculo com processo antigo + pedido de penhora

## Problem Statement

Quando um Cadastro Inicial cível no Forms responde "Embargos de terceiros"
no campo "Tipo de vínculo" (já existente na lista `TIPOS_VINCULO_CADASTRO_INICIAL`
de `forms_mapping_civel.py`), a automação hoje **ignora completamente** o
vínculo — o campo "Vínculo"/"Tipo de vínculo" da tela do LegalOne nunca é
preenchido, porque o mecanismo genérico de preenchimento da ficha
(`_FICHA_LOOKUPS` em `legalone_cadastro.py`) não tem entrada nenhuma para
esses campos. Toda a lógica de vínculo que existe no código hoje é
exclusiva do fluxo de Recurso cível (`_fluxo_recurso_civel`), que serve a
um propósito diferente (achar e reabrir a pasta do processo de origem —
não é o caso aqui: Embargos de terceiro gera um CNJ novo, processo
totalmente separado, e o vínculo é só informativo).

Separadamente, quando a peça de Embargos de terceiro pede "liberação de
penhora de imóveis" como pedido, esse texto não bate com nenhum item do
catálogo de pedidos do LegalOne — o catálogo já tem "Penhora de imóvel"
cadastrado, e criar um pedido novo em vez de reaproveitar o existente
gera duplicidade e pode não resolver no lookup (mesma classe de bug já
vista hoje com pedidos que não batem no catálogo).

## Solution

1. Preencher o campo "Vínculo" (tipo + texto/CNJ do processo antigo) na
   tela de Cadastro Inicial do LegalOne, usando o mesmo mecanismo genérico
   de preenchimento de ficha já usado para Justiça/UF/Instância/Órgão etc.
   — mas com o preenchimento **restrito a quando `tipo_vinculo` for
   "Embargos de terceiros"** (não os outros tipos da mesma lista, que
   ficam de fora por enquanto).
2. Adicionar um alias em `PEDIDOS_ALIASES_CATALOGO` mapeando
   "liberação de penhora de imóveis" (e variações de texto livre
   equivalentes) para o pedido já existente no catálogo, "Penhora de
   imóvel" — sem criar pedido novo.

## User Stories

1. Como usuário do pipeline de automação, quero que uma resposta do
   Forms com "Tipo de vínculo = Embargos de terceiros" preencha o campo
   Vínculo na tela do LegalOne, para que o processo novo fique
   corretamente referenciado ao processo antigo de origem.
2. Como usuário do pipeline, quero que o vínculo só seja preenchido
   quando o Forms realmente respondeu "Embargos de terceiros", para que
   os outros tipos de vínculo (Cautelar, Conexo, Execução etc.) não
   sejam afetados por essa mudança nem corram o risco de um
   preenchimento incorreto ainda não validado.
3. Como usuário do pipeline, quero que o campo Vínculo só seja
   preenchido quando estiver vazio na tela (mesma regra "só-se-vazio" já
   usada em todos os outros campos da ficha), para nunca sobrescrever um
   valor que já esteja lá.
4. Como usuário do pipeline, quero que um pedido de "liberação de
   penhora de imóveis" (ou variações de texto) case automaticamente com
   o item "Penhora de imóvel" já existente no catálogo do LegalOne, para
   que o cadastro do pedido não falhe por falta de correspondência nem
   crie duplicidade no catálogo.
5. Como usuário do pipeline, quero que, se o campo Vínculo não existir
   na tela (painel fechado, layout diferente) ou o preenchimento falhar,
   isso seja registrado como falha isolada no log da ficha — sem
   derrubar o resto do cadastro (mesmo contrato que `_preencher_ficha_forms`
   já garante para os outros campos).
6. Como usuário do pipeline, quero que o texto do CNJ/processo antigo
   informado no Forms para o vínculo seja normalizado da mesma forma que
   os outros campos de texto livre da ficha, para reduzir divergência de
   formatação entre o que o Forms manda e o que fica gravado no LegalOne.

## Implementation Decisions

- **Módulo principal alterado**: `legalone_cadastro.py`.
  - `_FICHA_LOOKUPS`/`_FICHA_TEXTOS` (ou um novo par de tuplas dedicado,
    a decidir na implementação) ganham a entrada de Vínculo, mas o
    preenchimento é condicionado — não basta adicionar à tupla genérica,
    porque isso vale pra qualquer processo com resposta em `tipo_vinculo`.
    A decisão de implementação é fazer esse preenchimento **gated**: só
    chama `_preencher_lookup_por_id`/`_preencher_texto_por_id` pros
    campos de Vínculo quando `obter('tipo_vinculo')` normalizado for
    igual a "embargos de terceiros".
  - Reaproveita os helpers já existentes: `_preencher_lookup_por_id`
    (mesmo mecanismo de fuzzy-match/lookup usado em Justiça/UF/Órgão) e
    `_estado_campo`/`_texto_do_campo` (gate "só-se-vazio").
  - Não reaproveita `_abrir_novo_recurso_da_pasta`/`_pesquisar_processos`
    — confirmado que Embargos de terceiro **não busca nem reabre** a
    pasta do processo antigo; o vínculo é preenchimento direto de campo,
    não navegação/busca.
- **Catálogo de pedidos**: `PEDIDOS_ALIASES_CATALOGO` (topo de
  `legalone_cadastro.py`) ganha a entrada
  `"liberacao de penhora de imoveis": "Penhora de imóvel"` (chave
  normalizada via `_normalizar_pedido`, mesmo padrão das entradas
  existentes). Nome exato do lado direito precisa ser confirmado contra
  o catálogo real do LegalOne antes de commitar (mesma cautela usada
  hoje para os nomes de tribunal — não assumir grafia sem checar ao
  vivo).
- **Identificação do campo/valor "Embargos de terceiros"**: a
  comparação deve ser normalizada (acentos/caixa) — o Forms já lista o
  valor como `"Embargos de terceiros"` (plural) em
  `TIPOS_VINCULO_CADASTRO_INICIAL`; usar a mesma função de normalização
  (`_normalizar_pedido` ou equivalente) já usada em outras comparações
  de texto do arquivo, não uma comparação exata frágil.
- **Escopo explícito**: nenhum outro tipo de vínculo da lista
  (`TIPOS_VINCULO_CADASTRO_INICIAL`/`TIPOS_VINCULO_INCIDENTE`) é afetado
  por essa mudança. A seção "INCIDENTE" do Forms (que também lista
  "Embargos de terceiros" como opção de vínculo) fica fora do escopo
  desse spec — só Cadastro Inicial é coberto.

## Testing Decisions

- Testes devem validar comportamento observável (o campo Vínculo é
  preenchido/não-preenchido conforme o valor de `tipo_vinculo`), não
  detalhes de implementação internos.
- Módulos a testar:
  - `legalone_cadastro.py`: teste unitário do preenchimento condicional
    do Vínculo (mock de `page`/`_preencher_lookup_por_id`, verificando
    que só é chamado quando `tipo_vinculo` == "Embargos de terceiros" e
    que não é chamado para outros valores, ex. "Cautelar").
  - `legalone_cadastro.py`: teste de `_resolver_pedido_catalogo` (ou
    `_parse_pedidos_detalhados`) confirmando que "liberação de penhora
    de imóveis" resolve para "Penhora de imóvel" — mesmo padrão dos
    testes de alias já existentes (`PEDIDOS_ALIASES_CATALOGO`).
- Prior art no repo: `tests/test_identidade_plural_lookup.py` e
  `tests/test_parse_pedidos_bullet.py` (criados hoje) são o padrão de
  teste de unidade recente para esse arquivo — mock leve, sem browser
  real, focado no comportamento de uma função isolada.
- Fora do escopo de teste automatizado: validação ao vivo contra o
  catálogo real do LegalOne (nome exato do tribunal/pedido) — isso é
  verificação manual/scriptada pontual antes do commit, como já foi
  feito hoje para Órgão, não um teste de regressão permanente.

## Out of Scope

- Os demais tipos de vínculo da mesma lista (Cautelar, Conexo,
  Consulta, Cumprimento de Sentença, Embargos à execução, Execução,
  Execução Provisória, Habeas corpus, Habilitação de crédito,
  Inventário, Liquidação, Mandado de segurança, Parecer, Processo
  Administrativo, Reclamação Constitucional, Recuperação Judicial) —
  ficam com o mesmo comportamento atual (vínculo ignorado) até uma
  decisão explícita de estender o escopo.
- A seção "INCIDENTE" do Forms (que também lista "Embargos de
  terceiros" como tipo de vínculo).
- Qualquer mecanismo de busca/abertura automática da pasta do processo
  antigo — confirmado que não se aplica a Embargos de terceiro.
- Alterações no Microsoft Forms em si — a opção "Embargos de terceiros"
  já existe no Forms, nenhuma mudança é necessária lá.

## Further Notes

- **Implementado e validado ao vivo em 18/08/2026** (`legalone_cadastro.py`):
  - Nome do catálogo confirmado pelo usuário: "Penhora de Imóvel" (não
    "Penhora de imóvel"). Alias adicionado em `PEDIDOS_ALIASES_CATALOGO`.
  - A seção "Vínculos" do Cadastro Inicial é uma linha por GUID (mesmo
    padrão de Pedidos/Assuntos), não um par simples de campos como no
    Recurso. Campos reais mapeados ao vivo:
    `Vinculos_<guid>__TipoVinculoText/Id`,
    `Vinculos_<guid>__VinculadoAId` (select: ""/"0"=Processo/"1"=Serviço),
    `Vinculos_<guid>__ProcessoVinculoText/Id`. Achado importante: os
    inputs usam o GUID com `_` no lugar de `-`, mas o `<select>`
    `VinculadoAId` usa o MESMO guid com `-` original — inconsistência já
    vista nos ids de Pedidos/Assuntos, tratada por `_base_vinculo()`
    (retorna as duas variantes).
  - Teste ao vivo (read-only, sem salvar) confirmou 100% de semelhança
    em Tipo de vínculo ("Embargos de terceiros") e no processo antigo
    encontrado pelo CNJ (resolveu para "Proc - 0004433" com os dados
    corretos do processo).
- Esse gap (vínculo ignorado fora do fluxo de Recurso) provavelmente se
  repete para os outros tipos de vínculo listados em "Out of Scope" —
  documentado aqui para uma decisão futura, não implementado agora por
  decisão explícita do usuário (menor escopo, menor risco).
