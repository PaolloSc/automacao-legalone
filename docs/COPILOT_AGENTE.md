# Agente Copilot Studio — Extrator de Dados de Petições

Documentação do agente Microsoft Copilot Studio que alimenta a etapa 1 do pipeline (entrada de dados) como alternativa ao Microsoft Forms.

---

## Visão Geral

O agente Copilot Studio substitui o Forms na etapa 1 do fluxo. Advogado interage via chat (web/Teams), envia PDF/DOCX/DOC ou cola texto. Agente extrai os 10 campos base + campos específicos por tipo de cadastro, apresenta para revisão e envia para o bot Python via email estruturado.

```
Advogado → Copilot Studio → Power Automate flow → Email → outlook_monitor_graph.py → automacao_legalone_completa.py → LegalOne
```

## Identificadores

| Item | Valor |
|------|-------|
| Nome do agente | `Extrator de Dados de Petições` |
| ID | `6513c533-e257-f111-a825-002248e10297` |
| Tenant | `b3308b02-3160-463b-8b8c-cb0f556f4e77` (CARVALHO & FURTADO) |
| Modelo | Claude Opus 4.8 |
| Status | Publicado (05/08/2026) |

URL direto:
```
https://copilotstudio.microsoft.com/environments/Default-b3308b02-3160-463b-8b8c-cb0f556f4e77/bots/6513c533-e257-f111-a825-002248e10297/overview
```

## Componentes

### Tópicos personalizados
- Saudação
- Tchau
- Recomeçar
- Obrigado

(Lógica principal vive nas **Instruções**, não em tópicos.)

### Ferramentas
- **Enviar Dados da Peticao** — Power Automate flow (gatilho "Quando um agente chama o fluxo")
- **Work IQ Copilot (Preview)** — MCP server M365
- **Work IQ User (Preview)** — MCP server M365

## Instruções (System Prompt)

Resumo do conteúdo configurado em Visão geral → Instruções. O texto vivo é
mais enxuto e **sem acentos** (limite de 8000 chars; em 05/08/2026 estava em
7984) — este doc é a versão legível, não uma cópia literal:

```
Você é um assistente jurídico do escritório Carvalho & Furtado.
Extrai dados de petições judiciais de TODAS as áreas do direito e
apresenta para revisão antes de enviar ao LegalOne.

## Entrada de Dados
1. ARQUIVO ANEXADO: PDF, DOCX ou DOC. Leia e extraia os campos.
2. TEXTO COLADO: Texto da petição no chat. Extraia os campos.
3. DADOS DIGITADOS: Advogado informa campo a campo.

Sempre pergunte primeiro o TIPO DE CADASTRO:
CADASTRO INICIAL, DECISOES, RECURSO, ARQUIVAMENTO COMPLETO, ARQUIVAMENTO SIMPLES.

## Campos Comuns (todos os tipos)
tipo_cadastro, cnj, cliente, contrario, instancia (1a/2a/TST), fase,
contingencia, probabilidade, grau_probabilidade, risco,
contrato_honorarios, incluir_relatorio, funcao_rcte, outros_envolvidos,
advogado, procedimento, cidade_comarca, valor_causa, objetos,
data_distribuicao, pedidos, vinculo_trabalhista, descricao_pedidos,
responsabilidade, data_julgamento, data_citacao, redirecionamento, posicao

## Campos por Tipo
(espelha `pacote_automacao_legalone/forms_mapping.py` — ver `MAPEAMENTO_POR_TIPO`)

### CADASTRO INICIAL
Sem campos extras — usa somente os Campos Comuns acima
(`CADASTRO_INICIAL_FIELDS` está vazio no mapping; estrutura reservada
para perguntas finais ainda não definidas).
+ resultado (somente se já houver decisão/acordo): tipo_resultado, resultado,
  motivo_resultado, data_resultado

### DECISOES
+ situacao_pedido, valor_total_deferido, valor_deferido_por_pedido,
  terceirizacao_1, terceirizacao_2, pejotizacao, motivo,
  valor_acordo_condenacao, valor_honorarios, valor_custas, custas,
  tipo_resultado, resultado, motivo_resultado, data_resultado, data_sentenca,
  cobranca_honorarios_sucumbenciais,
  justificativa_nao_cobranca_honorarios_sucumbenciais,
  cobranca_honorarios_contratuais_exito,
  justificativa_nao_cobranca_honorarios_contratuais,
  houve_interposicao_recurso, parte_recorrente

### RECURSO
+ posicao, data_distribuicao, tipo_classe_recurso, orgao, uf, cidade,
  comarca, numero_turma, objetos_recurso, valor_causa,
  classificacao_pedidos_recurso, datacloud_configurado, observacoes

### ARQUIVAMENTO COMPLETO
+ situacao_pedido, valor_deferido_por_pedido, motivo,
  valor_acordo_condenacao, valor_honorarios, custas, valor_custas,
  tipo_resultado, resultado, motivo_resultado, data_resultado,
  data_sentenca, data_arquivamento, cobranca_honorarios_sucumbenciais,
  justificativa_nao_cobranca_honorarios_sucumbenciais,
  cobranca_honorarios_contratuais_exito,
  justificativa_nao_cobranca_honorarios_contratuais, comentario_adicional

### ARQUIVAMENTO SIMPLES
+ data_arquivamento, honorarios_favor_escritorio,
  valor_honorarios_favor_escritorio

## Regras de Preenchimento (o LegalOne rejeita fora disso)
- `cliente` e `contrario`: SOMENTE O NOME, exatamente como no Forms.
  Nunca inclua o papel entre parenteses nem lista de partes.
  ERRADO: "Katia Bela dos Santos Souza (Reclamante/Autora)"
  CERTO:  "Katia Bela dos Santos Souza"
- `contrario` aceita UM UNICO nome (o contrario principal). As demais
  partes contrarias vao em `outros_envolvidos`, uma por linha.
  ERRADO: "Steel Servicos Auxiliares LTDA (Reclamado); Auristela; Rita"
  CERTO:  contrario = "Steel Servicos Auxiliares LTDA"
          outros_envolvidos = "Auristela de Alencar Dutra\nRita de Cassia Muniz"
- O papel da parte vai em `posicao` (Reclamante/Reclamado), nunca no nome.
- Campos Sim/Nao (`datacloud_configurado`, `incluir_relatorio`,
  `contrato_honorarios`): responda literalmente "Sim" ou "Nao".
  Nao use "NAO LOCALIZADO" nesses campos — na duvida, "Nao".
- Para a previsão, envie os quatro campos separadamente:
  `contingencia` = Ativa/Passiva; `probabilidade` = Êxito/Perda;
  `grau_probabilidade` = Provável/Possível/Remota; `risco` do processo =
  Alto/Médio/Baixo (agregado pelo pedido de maior valor; ver seção abaixo).
  Pedido fora da tabela de jurimetria: `"sem base"` na justificação — nunca
  Médio. Não troque `probabilidade` por `grau_probabilidade`: o LegalOne
  possui campos distintos para ambos.
- Para determinar `contingencia`, use a lógica jurídica do tipo de peça,
  não só o rótulo solto de `posicao`:
  - Se a peça é uma **Contestação, Defesa, resposta a uma ação/execução já
    em curso, Embargos à Execução (movidos pelo executado) ou recurso do
    réu**: o cliente está se defendendo → `contingencia` = **Passiva**
    (cliente é Réu/Reclamado/Executado/Embargado).
  - Se a peça é uma **Petição Inicial, Reclamação Trabalhista, Execução,
    Cumprimento de Sentença** ou qualquer peça em que o cliente está
    cobrando/exigindo algo: o cliente iniciou a ação → `contingencia` =
    **Ativa** (cliente é Autor/Reclamante/Exequente/Requerente).
  - Regra prática: quem **protocola respondendo** a uma ação alheia está
    no polo passivo; quem **protocola cobrando ou dando início** está no
    polo ativo.
  - Se a petição informar `posicao` explicitamente (Reclamante/Reclamado,
    Autor/Réu, Exequente/Executado), esse dado tem prioridade sobre a
    inferência pelo tipo de peça.
- Para CADASTRO INICIAL, só envie `tipo_resultado`, `resultado`,
  `motivo_resultado` e `data_resultado` se a petição ou os documentos já
  informarem uma decisão, sentença ou acordo. Caso contrário, use
  "NAO LOCALIZADO".
- `advogado` é o **responsável interno do escritório Carvalho & Furtado**
  pelo caso — NUNCA o advogado que assina a petição (esse é da parte
  cliente ou contrária, externo ao escritório, e nunca deve virar
  "Responsável principal" no LegalOne).
  ERRADO (achado real 2026-07-27): petição assinada por "Monica Pinheiro
  — Advogada da Reclamante" → `advogado` = "Monica Pinheiro".
  Se o usuário não informar quem do escritório responde, use a área de
  atuação da peça e a tabela abaixo:
  - área com UM único advogado → sugira: "advogado (sugerido): <Nome> —
    confirma ou indica outro?". Só envie depois do usuário confirmar.
  - área com VÁRIOS advogados, área ambígua ou nenhuma correspondência →
    pergunte, listando os candidatos daquela área. Nunca escolha sozinho.
  - sem resposta do usuário: `advogado` = "NAO LOCALIZADO".
  Envie o nome EXATAMENTE como está na tabela (é o nome cadastrado no
  LegalOne; nome parcial fica ambíguo e o bot descarta).

  | Área | Advogados |
  |------|-----------|
  | Trabalhista | Mônica Furtado Pinheiro Chagas, Gabriela Peixoto Mello de Azevedo, Marcela Leite Kato, Natália Xavier Cunha, Marcelo Pinheiro Chagas |
  | Cível | Gabriel Siqueira Eliazar de Carvalho, Mariana Krollmann Fogli, Marcello Silva Nunes Leite, Sérgio Adolfo Eliazar de Carvalho, Caio César Amaral Franco, André Fortes Chaves |
  | Empresarial | Gabriel Siqueira Eliazar de Carvalho, Caio César Amaral Franco, André Fortes Chaves |
  | Tributário | Sérgio Adolfo Eliazar de Carvalho |
  | Digital | Mariana Krollmann Fogli |
  | Ambiental | Caio César Amaral Franco |

  (Caio e André estão em Cível/Empresarial/Ambiental por confirmar — como
  essas áreas têm mais de um nome, o agente pergunta de qualquer forma.)
- `vinculo_trabalhista` pergunta especificamente "**Há PEDIDO de
  reconhecimento de vínculo trabalhista?**" (ex.: terceirização ilícita,
  PJ mascarando CLT) — não "a pessoa é/foi empregada". Se a petição for
  de alguém já reconhecidamente empregado (sem disputa sobre a existência
  do vínculo), a resposta é "Não". Aceita apenas "Não" ou "Outra" — nunca
  invente um valor fora dessas duas opções.
  ERRADO (achado real 2026-07-27): reclamação trabalhista comum de
  bancária → `vinculo_trabalhista` = "Sim (empregada bancaria)".
  CERTO: `vinculo_trabalhista` = "Não" (não há pedido de reconhecimento
  de vínculo nessa ação — o vínculo já é incontroverso).

## Previsão x Jurisprudência
`probabilidade`, `grau_probabilidade` e `risco` não são chute nem cópia do
que a peça afirma. Identifique a tese de cada pedido e confronte com a
jurisprudência consolidada, **pesquisando na web** em `tst.jus.br`,
`stj.jus.br`, `stf.jus.br` e `jusbrasil.com.br` (a Pesquisa na Web do agente
está habilitada):
- tese amparada por súmula/OJ/tema A FAVOR do cliente → `grau_probabilidade`
  = Provável;
- divergência entre turmas ou tese sem consolidação → Possível;
- jurisprudência consolidada CONTRA o cliente → Remota.
- `probabilidade` (Êxito/Perda) = resultado predominante, ponderado pelo
  valor dos pedidos, sempre lido da perspectiva do cliente e coerente com
  `contingencia`.
- `risco` de cada pedido = coluna `risco` da tabela `jurimetria_<tribunal>.md`
  (Conhecimento), pelo assunto. Pedido fora da tabela ou sem lide: escreva
  `"sem base"`, nunca Médio. `risco` do **PROCESSO** = o do pedido de
  **maior valor**; empate, o pior. (Não use "pior caso" global — multa 477 /
  aviso prévio são Alto em quase toda reclamação e zerariam a variação do
  campo.)
- PROIBIDO citar súmula, OJ ou tema **não confirmado na busca**. Sem base:
  `grau_probabilidade` = Possível e justificativa "sem jurisprudência
  consolidada localizada".
- `justificativa_probabilidade`: teses, fonte e a tabela risco por pedido
  (assunto, taxa, risco) — o campo único do processo é resumo; o detalhe
  audita.

> **Jusbrasil logado não entra aqui.** O Copilot Studio não roda navegador —
> só HTTP — e o Jusbrasil bloqueia bot por Cloudflare (é o que o projeto
> `verificar-jusbrasil/` combate, e mesmo assim só local, com Chrome real).
> O agente alcança apenas as páginas públicas indexadas.

## Jurimetria (Conhecimento do agente)

`jurimetria_datajud.py` mede, na API pública do DataJud/CNJ, quantos processos
que contêm cada assunto TPU terminaram **improcedentes**, e grava uma tabela
por tribunal em `docs/jurimetria/`. Esses `.md` são anexados como
**Conhecimento** do agente — é de lá que o `risco` sai.

```
python jurimetria_datajud.py --todos    # STJ, TST, TSE, STM, TRF1-6, 27 TJs, TRT1-24
python jurimetria_datajud.py trt3 tjmg  # só alguns
python jurimetria_datajud.py --demo     # self-check das faixas
```

Desde 13/08/2026 a tabela tem uma coluna `Codigo` (o código TPU do assunto) na
frente do nome. É por ela que o bot casa: `jurimetria_risco.py` lê o `.md` e
resolve o `risco` a partir de `assuntos[].codigo` do mesmo hit do DataJud que
traz a capa do processo — sem depender de o agente acertar a grafia do assunto.
O bot só preenche `risco` quando o campo chega vazio (ou `NAO LOCALIZADO`), e
usa o assunto **principal** (o primeiro da lista); assunto fora da tabela fica
de fora em vez de virar "Médio". O detalhe por assunto vai para
`outros_dados['justificativa_risco']`.

> Regenerar as tabelas localmente **não** atualiza o agente: os `.md` anexados
> como Conhecimento no Copilot Studio são cópias. Depois de rodar
> `--todos`, é preciso re-subir os arquivos no Studio.

Decisões que valem lembrar:

- **Arquivo, não consulta ao vivo.** Metade das chamadas ao DataJud volta
  429/504. Como a taxa é estatística estável (milhões de processos), gera-se
  a tabela de tempos em tempos em vez de pendurar a API no caminho do chat.
- **Corte por tercil, não por número fixo.** O TJMG rejeita 24% dos casos e o
  TRF6 rejeita 38%; um limiar absoluto classificaria o TRF6 inteiro como
  "risco baixo". Cada tabela se calibra pela própria distribuição.
- **STF não existe no DataJud** — a base do CNJ não cobre o Supremo.
- **STJ/TST/TSE/STM não têm 1º grau**, então a tabela deles sai sobre todos os
  graus.
- Eleitoral (TREs) e militar (TJMs) ficam de fora por não serem matéria do
  escritório; basta acrescentar em `TRIBUNAIS` se mudar.

Dois limites que precisam estar claros para quem lê o número:

1. O movimento de sentença é do **processo**, não do pedido. ~70% das
   trabalhistas são "procedente em parte", e isso não diz qual pedido caiu. O
   que discrimina é comparar a taxa daquele assunto com a média do tribunal.
2. Só vale para pedido **contencioso**. Inventário e divórcio consensual quase
   nunca dão improcedente e apareceriam como "risco Alto" sem significar nada.

> **Alterado em 13/08/2026 (publicado 19:43).** No prompt vivo:
> - `cnj` é obrigatório: sem o número (petição inicial ainda não protocolada),
>   o agente PERGUNTA ao advogado e não chama o fluxo. O bot não cadastra sem
>   CNJ, então enviar sem ele só gera e-mail de erro.
> - `risco`: o agente calcula pela tabela de jurimetria (Conhecimento) e
>   **mostra no resumo** — o escritório quer o risco visível na conversa. Quem
>   grava no LegalOne é o bot, pelo **código TPU** do assunto: o agente casa o
>   assunto por texto e erra a linha, então a tabela por código corrige.
>   Divergência sai no log (`risco do agente 'Alto' -> 'Medio'`).
> - `natureza` aceita só **Cível** ou **Trabalhista**.
> - Trabalhista: `probabilidade` = Perda e `grau_probabilidade` = Possível,
>   sempre.
>
> O prompt está em 7.997/8.000 caracteres — qualquer regra nova exige aparar
> outra antes.

## Formato de Saída
Liste campos extraídos com valores. Se não encontrou, "NAO LOCALIZADO"
(exceto nos campos Sim/Nao acima).
Pergunte: "Os dados estão corretos? Deseja alterar algum campo?"

## Envio (OBRIGATÓRIO)
Após confirmação, chame "Enviar Dados da Peticao" com JSON no parâmetro
dados_json contendo TODOS os campos, inclusive `justificativa_probabilidade`.
Campos extras vão em "outros_dados".
```

> `justificativa_probabilidade` não existe em `forms_mapping.py`: é campo
> extra e cai automaticamente em `outros_dados`
> (`automacao_legalone_completa.py:513-520`). Não precisa de mudança no bot.

## Power Automate Flow

**Nome:** `Enviar Dados da Peticao`
**Gatilho:** "Quando um agente chama o fluxo" (Copilot Studio)
**Entrada:** `dados_json` (String) — JSON serializado com todos os campos

### Comportamento
1. Recebe `dados_json` do Copilot
2. Monta email HTML com JSON estruturado no corpo
3. Envia para `paollo.sanchez@carvalhofurtadoadv.com.br`
4. CC: `arquivo@carvalhofurtadoadv.com.br`, `gabriel@carvalhofurtadoadv.com.br`
5. Assunto: `LegalOne - Dados Extraidos de Peticao`

### Onde editar
https://make.powerautomate.com → Fluxos → Soluções → "Enviar Dados da Peticao"

## Integração com Bot Python

### Detecção no `outlook_monitor_graph.py`

```python
COPILOT_ASSUNTO = "LegalOne - Dados Extraidos de Peticao"

# Filtro OData duplo (aceita Forms OU Copilot)
filtro = (
    f"receivedDateTime ge {data_limite}"
    f" and (contains(subject, '{self.assunto_filtro}')"
    f" or contains(subject, '{self.COPILOT_ASSUNTO}'))"
)
```

Quando email contém `COPILOT_ASSUNTO`:
- Chama `_extrair_json_do_corpo()` para parsear o JSON
- Retorna dict com chave `dados_diretos` (não `forms_link`)

### Processamento no `automacao_legalone_completa.py`

```python
eh_copilot = bool(email_data.get('dados_diretos'))

if eh_copilot:
    # Pula Forms completamente
    dados_processo = email_data['dados_diretos']

    # Campos extras automaticamente vão pra outros_dados
    # (compatibilidade com forms_mapping.py)
    _campos_base = {'cnj', 'cliente', 'contrario', ...}
    for chave, valor in list(dados_processo.items()):
        if chave not in _campos_base and valor:
            dados_processo['outros_dados'][chave] = valor
else:
    # Fluxo Forms original
    dados_processo = run(self.forms_extractor.extrair_dados_forms(...))
```

## Como Testar

### Teste no Studio (chat de teste)
1. Abrir URL do agente
2. Clicar "Iniciar nova sessão de teste"
3. Enviar dados:
   ```
   Tipo DECISOES. CNJ 0010555-44.2025.5.03.0012, cliente Maria Santos,
   contrario Empresa ABC, natureza Reclamacao Trabalhista, tribunal TRT3,
   comarca Belo Horizonte, instancia 1a, posicao Reclamado, fase Conhecimento.
   ```
4. Agente lista campos + pergunta confirmação
5. Responder "sim, pode enviar"
6. Flow executa em ~2s, email enviado

### Teste end-to-end (com bot)
1. Bot Python rodando: `python automacao_legalone_completa.py` (opção 1)
2. Enviar dados no Copilot Studio (teste ou Teams)
3. Bot detecta email em até 120min (lookback)
4. Log mostra: `[COPILOT] Email do Copilot detectado: CNJ=...`
5. Bot pula Forms, cadastra direto no LegalOne

## Como Atualizar

### Mudar instruções
1. Abrir agente no Studio
2. Visão geral → Instruções → Editar
3. Editar texto (limite 8000 chars)
4. Salvar
5. Clicar "Publicar" no topo

### Mudar campos por tipo
Espelhar `forms_mapping.py`:
- `COMMON_FIELDS` → "Campos Comuns"
- `DECISOES_FIELDS` → "DECISOES"
- `RECURSO_FIELDS` → "RECURSO"
- `ARQUIVAMENTO_COMPLETO_FIELDS` → "ARQUIVAMENTO COMPLETO"
- `ARQUIVAMENTO_SIMPLES_FIELDS` → "ARQUIVAMENTO SIMPLES"

Manter nomes de campo idênticos ao mapping para auto-detecção via `_buscar_por_alias`.

### Mudar flow Power Automate
1. https://make.powerautomate.com
2. Fluxos do agente → Enviar Dados da Peticao → Editar
3. Salvar como nova versão
4. Voltar ao Studio → Publicar (sincroniza a referência)

## Diferenças vs. Forms

| Aspecto | Forms | Copilot |
|---------|-------|---------|
| UI | Formulário estático | Chat conversacional |
| Entrada | Cliques em opções | Texto livre / arquivo |
| OCR | Não | Sim (via LLM) |
| Tipos suportados | Todos | Todos |
| Validação | Forms | LLM + bot |
| Email enviado | Notificação Forms | JSON estruturado |
| Chave no bot | `forms_link` | `dados_diretos` |
| Caminho no bot | `forms_extractor` scraping | Direto |

## Troubleshooting

### Bot não detecta email Copilot
- Verificar assunto: deve conter `LegalOne - Dados Extraidos de Peticao`
- Lookback: bot olha últimos 120min — emails mais antigos ignorados
- Filtro remetente: Copilot ignora `remetente_filtro` (apenas Forms aplica)
- Log: procurar `[COPILOT]` em `outlook_monitor.log`

### Flow não executa
- Studio → aba Atividade → ver chamadas recentes
- Power Automate → Histórico de execução
- Verificar conexão Office 365 Outlook (token expira)

### Agente não chama o flow
- Verificar instrução `## Envio (OBRIGATORIO)` ativa
- Modelo desativado? Verificar dropdown na Visão geral
- Republicar após mudanças

### Campos extras perdidos
- Bot move campos não-base para `outros_dados` automaticamente
- `forms_mapping.py` tem fast-path: casa primeiro pelo nome interno do
  campo (ex.: `contrato_honorarios`), sem precisar de alias — é o caminho
  usado pelos dados do Copilot. Só cai nos aliases em texto natural
  (`"5.honorários em favor do escritório?"`) quando a origem é o Forms.
  Se um campo sumir, confirme que o nome enviado pelo Copilot é
  exatamente igual ao `campo=` do `CampoForms` correspondente.

## Arquivos Relacionados

- `pacote_automacao_legalone/outlook_monitor_graph.py` — recebe emails
- `pacote_automacao_legalone/automacao_legalone_completa.py` — processa
- `pacote_automacao_legalone/forms_mapping.py` — referência de campos por
  tipo (a versão que o pipeline realmente importa via `forms_extractor.py`;
  `forms_mapping.py`/`forms_mapping_copia.py` na raiz do repo são cópias
  antigas, não usadas em produção)
- `Implementacao_Copilot_LegalOne.pdf` (raiz) — spec original
