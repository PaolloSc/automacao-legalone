# Mapeamento — Microsoft Forms "Cível - cadastro LegalOne"

## 1. Metadados

| Item | Valor |
|---|---|
| Título do formulário | `Cível - cadastro LegalOne` |
| URL de design | `https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?origin=NeoPortalPage&subpage=design&collectionid=pcw1ysb1cz90qkh33eucr9&id=Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u&analysis=true` |
| Form id (parâmetro `id`) | `Aosws2AxO0aLjMsPVW9Od_YD1V-fvyxMswWjMlncgUdUNFY0WTIySFRQVDJNMllXSjYxSk1FRU9JWi4u` |
| Collection id | `pcw1ysb1cz90qkh33eucr9` |
| Data da coleta | 2026-08-04 |
| Total de perguntas | **190** |
| Total de seções | 9 |
| Respostas acumuladas | 230 |
| Método de coleta | leitura do DOM da página de design (`read_page` + `innerText`) e da definição do formulário retornada por `GET /formapi/api/forms('<id>')?$expand=questions` (somente leitura; nada foi editado, salvo ou enviado) |

> **Atenção:** este formulário é **muito** maior que o trabalhista e tem escopo diferente:
> ele cobre também **cadastro de pessoa jurídica** e **cadastro de pessoa física** (contatos/partes),
> não só o cadastro processual. O ramo "Processo" é o único comparável ao Forms trabalhista.

Convenções da tabela:
- **Tipo**: `texto` = Texto de linha única · `texto_multilinha` = Texto Multilinha · `opcao_unica` = Opção única · `opcao_multipla` = Múltipla escolha · `data` = Data · `upload` = Carregar Arquivo.
- **Obrig.**: `Sim` quando o Forms exibe "Requer resposta".
- **+Outra**: a pergunta tem campo livre "Outra resposta" além das opções listadas.
- Não há perguntas de escala/Likert neste formulário.

---

## 2. Tabela completa das perguntas

### Seção 1 (sem título)

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 1 | Tipo de cadastro | opcao_unica | Sim | Pessoa jurídica · Pessoa física · Processo | `tipo_entidade` |

### Seção 2 — PESSOA JURÍDICA

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 2 | CNPJ | texto | Sim | — | `cnpj` |
| 3 | Grupos | opcao_unica **+Outra** | Não | Autoridade · Cliente · Colaborador · Correspondente · Ministério Público · Parceiro · Perito · Potencial cliente · Potencial fornecedor · Potencial parceiro · Sindicato | `grupos` |
| 4 | Endereço alternativo *(subtítulo: Residencial e/ou Comercial)* | texto | Não | — | `endereco_alternativo` |
| 5 | Contato telefônico *(subtítulo: Residencial, pessoal, comercial e/ou celular)* | texto | Não | — | `telefone` |
| 6 | Endereço eletrônico *(subtítulo: Pessoal e/ou Comercial)* | texto | Não | — | `email` |
| 7 | Data da fundação | data | Não | — | `data_fundacao` |
| 8 | Grupo empresarial | texto | Não | — | `grupo_empresarial` |
| 9 | Origem da prospecção | texto | Não | — | `origem_prospeccao` |
| 10 | Categoria de cliente | texto | Não | — | `categoria_cliente` |
| 11 | Rede social | texto | Não | — | `rede_social` |

### Seção 3 — PESSOA FÍSICA

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 12 | Nome | texto | Sim | — | `nome` |
| 13 | Título de eleitor | texto | Não | — | `titulo_eleitor` |
| 14 | CPF | texto | Sim | — | `cpf` |
| 15 | Data de nascimento | data | Não | — | `data_nascimento` |
| 16 | Sexo | opcao_unica | Sim | Feminino · Masculino | `sexo` |
| 17 | N° da CTPS | texto | Não | — | `ctps` |
| 18 | Profissão | texto | Não | — | `profissao` |
| 19 | Identidade profissional | texto | Não | — | `identidade_profissional` |
| 20 | NIT/PIS/PASEP | texto | Não | — | `nit_pis_pasep` |
| 21 | RG | texto | Não | — | `rg` |
| 22 | Grupos | opcao_multipla **+Outra** | Sim | Autoridade · Cliente · Colaborador · Correspondente · Ministério Público · Parceiro · Perito · Potencial cliente · Potencial fornecedor · Potencial parceiro · Sindicato | `grupos` |
| 23 | Classificações | opcao_unica **+Outra** | Não | Ativo · Inativo | `classificacoes` |
| 24 | Contato Telefônico *(subtítulo: Residêncial, pessoal, comercial e/ou celular)* | texto | Não | — | `telefone` |
| 25 | Endereço Eletrônico *(subtítulo: Pessoal e/ou comercial)* | texto | Não | — | `email` |
| 26 | Endereço Alternativo *(subtítulo: Residencial e/ou comercial)* | texto | Não | — | `endereco_alternativo` |
| 27 | Data de admissão | data | Não | — | `data_admissao` |
| 28 | Data de desligamento | data | Não | — | `data_desligamento` |
| 29 | Responsável pela prospecção | texto | Não | — | `responsavel_prospeccao` |
| 30 | Origem da prospecção | texto | Não | — | `origem_prospeccao` |
| 31 | Empresa que a pessoa possui vínculo | texto | Não | — | `empresa_vinculo` |
| 32 | Categoria de cliente | texto | Não | — | `categoria_cliente` |
| 33 | Rede social | texto | Não | — | `rede_social` |

### Seção 4 — PROCESSO

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 34 | Tipo de cadastro | opcao_unica | Sim | Cadastro inicial · Decisões · Recurso · Arquivamento · Incidente | `tipo_cadastro` |

> Observação técnica: na definição do formulário a opção "Recurso" está gravada com **espaço inicial**
> (`" Recurso"` / `"&nbsp;Recurso"`). A normalização por alias deve fazer `strip()` antes de comparar.

### Seção 5 — CADASTRO INICIAL

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 35 | Nome do cliente | texto | Sim | — | `cliente` |
| 36 | Negociação do contrato de honorários | texto | Sim | — | `contrato_honorarios` |
| 37 | Contrato | upload | Não | Limite: 10 arquivos · 1 GB por arquivo · Word, Excel, PPT, PDF, Imagem, Vídeo, Áudio | `contrato_arquivo` |
| 38 | Tipo | opcao_unica | Sim | Judicial · Administrativo · Arbitral | `tipo_processo` |
| 39 | Número do processo *(subtítulo: CNJ de preferência. Se for outro número indicar o tipo - AI, BO, Ofício, Ordem ou TRT antigo)* | texto | Sim | — | `cnj` |
| 40 | Sistema do processo eletrônico | texto | Não | — | `sistema_eletronico` |
| 41 | Ação | opcao_unica | Sim | ver "Lista de opções — Ação (cadastro inicial)" abaixo (79 opções) | `acao` |
| 42 | Procedimento | opcao_unica | Sim | Administrativo · Especial · Ordinário · Sumário · Sumaríssimo | `procedimento` |
| 43 | Natureza | opcao_unica | Sim | Administrativo · Ambiental · Cível · Constitucional · Criminal · Empresarial · Família · Sucessões · Trabalhista · Tributária | `natureza` |
| 44 | Fase Processual | opcao_unica | Sim | Arquivado · Conciliatória · Conhecimento · Cumprimento de Sentença · Decisória · Encerrado · Executória · Extinto · Inicial · Instrutória · Julgamento · Liquidação · Recursal | `fase` |
| 45 | Cidade/Comarca | texto | Sim | — | `cidade_comarca` |
| 46 | Pesquisa RTOnline *(subtítulo: Objeto/mérito da ação para pesquisas)* | texto | Não | — | `pesquisa_rtonline` |
| 47 | Cliente principal | texto | Sim | — | `cliente` |
| 48 | Posição nos autos do Cliente Principal | texto | Sim | — | `posicao` |
| 49 | Contrário principal | texto | Sim | — | `contrario` |
| 50 | Advogado responsável pelo processo | texto | Sim | — | `advogado` |
| 51 | Magistrado *(subtítulo: Juiz ou Desembargador Relator)* | texto | Sim | — | `magistrado` |
| 52 | Outros envolvidos (se houver) e sua posição nos autos | texto_multilinha | Não | — | `outros_envolvidos` |
| 53 | Vínculo | texto | Não | — | `vinculo` |
| 54 | Tipo de vínculo | opcao_unica | Não | Cautelar · Conexo · Consulta · Cumprimento de Sentença · Embargos à execução · Embargos de terceiros · Execução · Execução Provisória · Habeas corpus · Habilitação de crédito · Inventário · Liquidação · Mandado de segurança · Negociação do contrato de honorário · Parecer · Processo Administrativo · Reclamação Constitucional · Recuperação Judicial | `tipo_vinculo` |
| 55 | Objeto do processo *(subtítulo: Não se trata da Ação, tipo de procedimento e/ou pedido – indicar a matéria)* | texto_multilinha | Sim | — | `objeto_processo` |
| 56 | Pedidos e objetos dos pedidos | texto_multilinha | Sim | — | `pedidos` |
| 57 | Classificação de cada pedido ( Probabilidade atual de êxito ou perda - remota, possível, provável) e os valores de provisão para cada pedido (remota, possível, provável) | texto_multilinha | Sim | — | `classificacao_pedidos` |
| 58 | Valor da causa | texto | Sim | — | `valor_causa` |
| 59 | Centro de custo | opcao_multipla **+Outra** | Sim | Cível · Tributário · Trabalhista · Ambiental · Administrativo · Família · Relações governamentais · Pastas sigilosas · Penal | `centro_custo` |
| 60 | Contigência *(grafia do formulário)* | opcao_unica | Sim | Ativa · Passiva | `contingencia` |
| 61 | Risco do processo | opcao_unica | Sim | Médio · Alto · Baixo | `risco` |
| 62 | Probabilidade atual | opcao_unica | Sim | Êxito · Perda | `probabilidade` |
| 63 | Faixa de probabilidade atual | opcao_unica | Sim | Provável · Possível · Remota | `grau_probabilidade` |
| 64 | Observações | texto_multilinha | Não | — | `observacoes` |
| 65 | Supermercado Loja | texto | Não | — | `supermercado_loja` |
| 66 | Centro de custo do cliente | texto | Não | — | `centro_custo_cliente` |
| 67 | N° do cliente | texto | Não | — | `numero_cliente` |
| 68 | Residencial | texto | Não | — | `residencial` |
| 69 | Obra | texto | Não | — | `obra` |
| 70 | Data da citação | data | Não | — | `data_citacao` |
| 71 | Prescrição Bienal | texto | Não | — | `prescricao_bienal` |
| 72 | Prescrição quinquenal | texto | Não | — | `prescricao_quinquenal` |
| 73 | Cobrança de Honorários de Sucumbenciais? *(subtítulo: Incluir justificativa)* | texto | Não | — | `cobranca_honorarios_sucumbenciais` |
| 74 | Honorários de êxito | texto | Não | — | `honorarios_exito` |
| 75 | Dívidas não tributárias | texto | Não | — | `dividas_nao_tributarias` |
| 76 | Data do pagamento | data | Não | — | `data_pagamento` |
| 77 | Valor adicional de provisão | texto | Não | — | `valor_adicional_provisao` |
| 78 | Fase Processual *(2ª ocorrência da mesma pergunta na seção)* | opcao_unica | Sim | mesma lista da #44 | `fase_2` |

### Seção 6 — INCIDENTE

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 79 | Nome do cliente | texto | Sim | — | `cliente` |
| 80 | Negociação do contrato de honorários | texto | Sim | — | `contrato_honorarios` |
| 81 | Tipo | opcao_unica | Sim | Judicial · Administrativo · Arbitral | `tipo_processo` |
| 82 | Número do processo *(mesmo subtítulo da #39)* | texto | Sim | — | `cnj` |
| 83 | Procedimento | opcao_unica | Sim | Administrativo · Especial · Ordinário · Sumário · Sumaríssimo | `procedimento` |
| 84 | Ação | opcao_unica | Sim | ver "Lista de opções — Ação (incidente)" abaixo (20 opções) | `acao` |
| 85 | Natureza | opcao_unica | Sim | mesma lista da #43 | `natureza` |
| 86 | Fase Processual | opcao_unica | Sim | mesma lista da #44 | `fase` |
| 87 | Cidade/Comarca | texto | Sim | — | `cidade_comarca` |
| 88 | Pesquisa RTOnline *(subtítulo: Objeto/mérito da ação para pesquisas)* | texto | Não | — | `pesquisa_rtonline` |
| 89 | Cliente principal | texto | Sim | — | `cliente` |
| 90 | Posição nos autos do Cliente Principal | texto | Sim | — | `posicao` |
| 91 | Contrário principal | texto | Sim | — | `contrario` |
| 92 | Advogado responsável pelo processo | texto | Sim | — | `advogado` |
| 93 | Magistrado *(subtítulo: Juiz ou Desembargador Relator)* | texto | Sim | — | `magistrado` |
| 94 | Outros envolvidos (se houver) e sua posição nos autos | texto_multilinha | Não | — | `outros_envolvidos` |
| 95 | Vínculo | texto | Não | — | `vinculo` |
| 96 | Tipo de vínculo | opcao_unica | Não | mesma lista da #54 **+ Requerimento de Efeito Suspensivo** (19 opções) | `tipo_vinculo` |
| 97 | Objeto do processo *(mesmo subtítulo da #55)* | texto_multilinha | Sim | — | `objeto_processo` |
| 98 | Pedidos e objetos dos pedidos | texto_multilinha | Sim | — | `pedidos` |
| 99 | Classificação de cada pedido ( Probabilidade atual de êxito ou perda - remota, possível, provável) e os valores de provisão para cada pedido (remota, possível, provável) | texto_multilinha | Sim | — | `classificacao_pedidos` |
| 100 | Valor da causa | texto | Sim | — | `valor_causa` |
| 101 | Centro de custo | opcao_multipla **+Outra** | Sim | mesma lista da #59 | `centro_custo` |
| 102 | Contigência | opcao_unica | Sim | Ativa · Passiva | `contingencia` |
| 103 | Risco do processo | opcao_unica | Sim | Médio · Alto · Baixo | `risco` |
| 104 | Probabilidade atual | opcao_unica | Sim | Êxito · Perda | `probabilidade` |
| 105 | Faixa de probabilidade atual | opcao_unica | Sim | Provável · Possível · Remota | `grau_probabilidade` |
| 106 | Observações | texto_multilinha | Não | — | `observacoes` |
| 107 | Supermercado Loja | texto | Não | — | `supermercado_loja` |
| 108 | Centro de custo do cliente | texto | Não | — | `centro_custo_cliente` |
| 109 | N° do cliente | texto | Não | — | `numero_cliente` |
| 110 | Residencial | texto | Não | — | `residencial` |
| 111 | Obra | texto | Não | — | `obra` |
| 112 | Data da citação | data | Não | — | `data_citacao` |
| 113 | Prescrição Bienal | texto | Não | — | `prescricao_bienal` |
| 114 | Prescrição quinquenal | texto | Não | — | `prescricao_quinquenal` |
| 115 | Cobrança de Honorários de Sucumbenciais? *(subtítulo: Incluir justificativa)* | texto | Não | — | `cobranca_honorarios_sucumbenciais` |
| 116 | Honorários de êxito | texto | Não | — | `honorarios_exito` |
| 117 | Dívidas não tributárias | texto | Não | — | `dividas_nao_tributarias` |
| 118 | Data do pagamento | data | Não | — | `data_pagamento` |
| 119 | Valor adicional de provisão | texto | Não | — | `valor_adicional_provisao` |

### Seção 7 — DECISÕES

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 120 | Número CNJ | texto | Sim | — | `cnj` |
| 121 | Cliente principal | texto | Sim | — | `cliente` |
| 122 | Contrário principal | texto | Sim | — | `contrario` |
| 123 | Instância | opcao_unica **+Outra** | Não | 1ª instância · 2ª instância | `instancia` |
| 124 | Situação do pedido | opcao_unica **+Outra** | Não | Deferido · Extinto · Indeferido · Parcialmente deferido · Suspenso · Acordo | `situacao_pedido` |
| 125 | Valor deferido | texto | Não | — | `valor_deferido` |
| 126 | Motivo | opcao_unica **+Outra** | Não | Ausência de concreta fundamentação · Ausência de provas · Danos constatados · Falta de documentos · Precedentes jurisprudenciais · **Provas produzidas pelo réu** · **Provas produzidas pelo autor** | `motivo` |
| 127 | Valor do acordo/condenção *(grafia do formulário)* | texto | Não | — | `valor_acordo_condenacao` |
| 128 | Valor de honorários | texto | Não | — | `valor_honorarios` |
| 129 | Valor custas | texto | Não | — | `valor_custas` |
| 130 | Custas | opcao_unica | Não | Favorável · Desfavorável · Sem posição | `custas` |
| 131 | Tipo de resultado | opcao_unica **+Outra** | Não | Acórdão · Acordo · Decisão · Sentença | `tipo_resultado` |
| 132 | Resultado | opcao_unica **+Outra** | Não | Êxito total · Acordo · Êxito Parcial · Extinto · Perda | `resultado` |
| 133 | Motivo do resultado | texto_multilinha | Não | — | `motivo_resultado` |
| 134 | Data do resultado | data | Não | — | `data_resultado` |
| 135 | Data da sentença | data | Não | — | `data_sentenca` |
| 136 | Cobrança de honorários sucumbenciais? | opcao_unica | Não | Sim · Não | `cobranca_honorarios_sucumbenciais` |
| 137 | Justifique a não cobrança de honorários sucumbenciais | opcao_unica **+Outra** | Não | Sem previsão legal | `justificativa_nao_cobranca_honorarios_sucumbenciais` |
| 138 | Cobrança de honorários contratuais de êxito? | opcao_unica | Não | Sim · Não | `cobranca_honorarios_contratuais_exito` |
| 139 | Justifique a não cobrança de honorários contratuais de êxito | opcao_unica **+Outra** | Não | Sem previsão contratual | `justificativa_nao_cobranca_honorarios_contratuais` |
| 140 | Contingência | opcao_unica | Não | Ativa · Passiva | `contingencia` |
| 141 | Probabilidade atual | opcao_unica | Não | Êxito · Perda | `probabilidade` |
| 142 | Faixa de probabilidade atual | opcao_unica | Não | Provável · Possível · Remota | `grau_probabilidade` |
| 143 | Risco | opcao_unica | Não | Alto · Médio · Baixo | `risco` |
| 144 | Vínculo (se houver - processo ou serviço) | texto | Não | — | `vinculo` |
| 145 | Tipo de vínculo | opcao_unica **+Outra** | Não | Liminar · Incidentes · Embargos à execução · Execução · Cumprimento de sentença · Carta precatória · Recurso | `tipo_vinculo` |
| 146 | Observações | texto_multilinha | Não | — | `observacoes` |

### Seção 8 — RECURSOS

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 147 | Número de CNJ | texto | Sim | — | `cnj` |
| 148 | Número antigo | texto | Não | — | `numero_antigo` |
| 149 | Cliente principal | texto | Sim | — | `cliente` |
| 150 | Posição cliente principal | texto | Sim | — | `posicao` |
| 151 | Contrário principal | texto | Sim | — | `contrario` |
| 152 | Advogado responsável | texto | Sim | — | `advogado` |
| 153 | Data de distribuição do recurso | data | Sim | — | `data_distribuicao` |
| 154 | Tipo de procedimento | opcao_unica | Sim | Judicial · Administrativo · Arbitral | `tipo_processo` |
| 155 | Tipo de recurso | opcao_unica | Sim | ver "Lista de opções — Tipo de recurso" abaixo (20 opções) | `tipo_classe_recurso` |
| 156 | Vínculo (se houver - processo ou serviço) | texto | Não | — | `vinculo` |
| 157 | Tipo de vínculo | opcao_unica **+Outra** | Sim | Liminar · Incidentes · Embargos à execução · Execução · Cumprimento de sentença · Carta precatória · Recurso | `tipo_vinculo` |
| 158 | Natureza | opcao_unica **+Outra** | Sim | Cível · Trabalhista · Tributário | `natureza` |
| 159 | Órgão | texto | Sim | — | `orgao` |
| 160 | UF | texto | Sim | — | `uf` |
| 161 | Cidade | texto | Sim | — | `cidade` |
| 162 | Comarca | texto | Sim | — | `comarca` |
| 163 | Instância | opcao_unica **+Outra** | Sim | 1° Grau · 2º Grau · STJ | `instancia` |
| 164 | N° Turma | texto | Sim | — | `numero_turma` |
| 165 | Nome da vara/turma | texto | Não | — | `nome_vara_turma` |
| 166 | Objeto do recurso | texto_multilinha | Sim | — | `objetos_recurso` |
| 167 | Classificação de cada pedido ( Probabilidade atual de êxito ou perda - remota, possível, provável) e os valores de provisão para cada pedido (remota, possível, provável) | texto_multilinha | Sim | — | `classificacao_pedidos_recurso` |
| 168 | Observações | texto_multilinha | Não | — | `observacoes` |

### Seção 9 — ARQUIVAMENTO

| # | Pergunta (texto exato) | Tipo | Obrig. | Opções | Campo interno sugerido |
|---|---|---|---|---|---|
| 169 | Número CNJ | texto | Sim | — | `cnj` |
| 170 | Cliente principal | texto | Sim | — | `cliente` |
| 171 | Contrário principal | texto | Sim | — | `contrario` |
| 172 | Instância | opcao_unica **+Outra** | Sim | 1ª instância · 2ª instância | `instancia` |
| 173 | Situação do pedido | opcao_unica **+Outra** | Sim | Deferido · Extinto · Indeferido · Parcialmente deferido · Suspenso · Acordo | `situacao_pedido` |
| 174 | Valor deferido | texto_multilinha | Sim | — | `valor_deferido_por_pedido` |
| 175 | Motivo | opcao_unica **+Outra** | Sim | Ausência de concreta fundamentação · Ausência de provas · Danos constatados · Falta de documentos · Precedentes jurisprudenciais · **Provas produzidas pela Empresa** · **Provas produzidas pelo RCTE** | `motivo` |
| 176 | Valor do acordo/condenção *(grafia do formulário)* | texto | Sim | — | `valor_acordo_condenacao` |
| 177 | Valor de honorários | texto | Não | — | `valor_honorarios` |
| 178 | Custas | opcao_unica | Sim | Favorável · Desfavorável · Sem posição | `custas` |
| 179 | Valor custas | texto | Sim | — | `valor_custas` |
| 180 | Tipo de resultado | opcao_unica **+Outra** | Sim | Acórdão · Acordo · Decisão · Sentença | `tipo_resultado` |
| 181 | Resultado | opcao_unica **+Outra** | Sim | Êxito total · Acordo · Êxito Parcial · Extinto · Perda | `resultado` |
| 182 | Motivo do resultado | texto_multilinha | Sim | — | `motivo_resultado` |
| 183 | Data do resultado | data | Sim | — | `data_resultado` |
| 184 | Data da sentença | data | Sim | — | `data_sentenca` |
| 185 | Data de arquivamento | data | Sim | — | `data_arquivamento` |
| 186 | Cobrança de honorários sucumbenciais? | opcao_unica | Sim | Sim · Não | `cobranca_honorarios_sucumbenciais` |
| 187 | Justifique a não cobrança de honorários sucumbenciais | opcao_unica **+Outra** | Sim | Sem previsão legal | `justificativa_nao_cobranca_honorarios_sucumbenciais` |
| 188 | Cobrança de honorários contratuais de êxito? | opcao_unica | Sim | Sim · Não | `cobranca_honorarios_contratuais_exito` |
| 189 | Justifique a não cobrança de honorários contratuais de êxito | opcao_unica **+Outra** | Sim | Sem previsão contratual | `justificativa_nao_cobranca_honorarios_contratuais` |
| 190 | Observações | texto_multilinha | Não | — | `observacoes` |

---

## 3. Listas de opções longas

### Lista de opções — Ação (pergunta 41, CADASTRO INICIAL) — 79 opções

Abertura, registro, reconhecimento, aprovação e cumprimento de testamento · Ação Civil Coletiva ·
Ação Civil Pública · Ação de Divisão e Demarcação de Terras · Ação de Divórcio · Ação de Exigir Contas ·
Ação de Improbidade Administrativa · Ação de Regresso · Ação Ordinária · Ação Pauliana · Ação Penal ·
Ação Rescisória · Ação Revisional · Adjudicação Compulsória · Alienação Judicial · Alimentos ·
Anulatória · Auto de Infração · Cautelar de Arrolamento de Bens · Cautelar de Busca e Apreensão ·
Cautelar de Protestos, Notificações e Interpelações · Cautelar Inominada · Cobrança ·
Consignação em Pagamento · Cumprimento de Sentença · Cumprimento Provisório de Sentença ·
Declaratória · Desapropriação · Despejo · Dissolução de Sociedade · Embargos à Execução ·
Embargos à Execução Fiscal · Embargos de Terceiro · Execução · Execução Fiscal · Execução Provisória ·
Falência · Habeas Corpus · Habeas Data · Homologação da Transação Extrajudicial ·
Homologação de Decisão Estrangeira · Homologação do Penhor Legal · Indenizatória · Inquérito Policial ·
Interdição · Interdito Proibitório · Inventário · Investigação de Paternidade · Liquidação ·
Liquidação Provisória · Mandado de Segurança · Monitória · Notificação Administrativa ·
Obrigação de Fazer · Oposição · Precatório · Produção Antecipada de Prova · Queixa-Crime ·
Reclamação Administrativa · Reclamação Constitucional · Reclamação Trabalhista ·
Reconhecimento e Extinção de União Estável · Recuperação Judicial ·
Recurso Ordinário – Rito Sumaríssimo · Recurso Ordinário Trabalhista · Registro de Marca e Patente ·
Regulação de Avaria Grossa · Reintegração e Manutenção de Posse · Reivindicatória ·
Renovatória de Locação · Repetição de Indébito · Requisição de Pequeno Valor · Rescisória ·
Restauração de Autos · Restituição · Separação Consensual · Separação Litigiosa ·
Tutelas de Urgência Antecipada e Cautelar Requeridas em Caráter Antecedente · Usucapião

### Lista de opções — Ação (pergunta 84, INCIDENTE) — 20 opções

Arguição de Falsidade Documental · Carta de Ordem Cível · Carta Precatória · Carta Rogatória ·
Conflito de Competência · Desconsideração da Personalidade Jurídica · Exceção de Incompetência ·
Exceção de Pré-Executividade · Habilitação de Crédito · Impugnação à Assistência Gratuita ·
Impugnação ao Valor da Causa · Impugnação de Crédito · Incidente de Apresentação de Contas ·
Incidente de Arguição de Inconstitucionalidade · Incidente de Assunção de Competência ·
Incidente de Resolução de Demandas Repetitivas · Incidente de Uniformização de Jurisprudência ·
Inquérito Policial · Requerimento de Efeito Suspensivo · Suspeição e Impedimento

### Lista de opções — Tipo de recurso (pergunta 155) — 20 opções

Agravo de Instrumento · Agravo de Instrumento em Agravo de Petição ·
Agravo de Instrumento em Recurso de Revista · Agravo de Instrumento em Recurso Ordinário ·
Agravo de Petição · Agravo em Recurso Especial · Agravo em Recurso Extraordinário ·
Agravo Interno · Agravo Regimental · Apelação · Embargos de Declaração · Embargos de Divergência ·
Embargos Infringentes · Recurso Administrativo · Recurso de Revista · Recurso em Sentido Estrito ·
Recurso Especial · Recurso Extraordinário · Recurso Inominado · Recurso Ordinário

> Lista confirmada contra a definição do formulário (`questionInfo.Choices`): exatamente 20 opções,
> sem campo "Outra". O primeiro rótulo vem com espaço final (`"Agravo de Instrumento "`).

---

## 4. Lógica de ramificação

Confirmada pela definição do formulário (`questionInfo.Choices[].BranchInfo.TargetQuestionId`),
com os alvos resolvidos pela posição das seções no DOM da página de design.
Só existem **duas** perguntas com ramificação; todas as demais seguem em sequência.

```
Q1  "Tipo de cadastro"
    ├─ Pessoa jurídica ──► Seção 2  PESSOA JURÍDICA   (Q2  … Q11)
    ├─ Pessoa física   ──► Seção 3  PESSOA FÍSICA     (Q12 … Q33)
    └─ Processo        ──► Seção 4  PROCESSO          (Q34)

Q34 "Tipo de cadastro"  (dentro da Seção 4)
    ├─ Cadastro inicial ─► Seção 5  CADASTRO INICIAL  (Q35  … Q78)
    ├─ Decisões        ──► Seção 7  DECISÕES          (Q120 … Q146)
    ├─ Recurso         ──► Seção 8  RECURSOS          (Q147 … Q168)
    ├─ Arquivamento    ──► Seção 9  ARQUIVAMENTO      (Q169 … Q190)
    └─ Incidente       ──► Seção 6  INCIDENTE         (Q79  … Q119)
```

Consequências práticas para o extrator:
- A pergunta "Tipo de cadastro" **aparece duas vezes** (Q1 e Q34) com listas de opções diferentes.
  O extrator atual casa por título normalizado (`tipo de cadastro`) e pegaria a primeira ocorrência.
  É preciso desambiguar: Q1 define **entidade** (PJ/PF/Processo) e Q34 define **tipo de tarefa**.
- Sem ramificação configurada nas seções, o respondente que escolhe "Cadastro inicial" percorre
  a Seção 5 e, ao final dela, o Forms continua para a **Seção 6 (INCIDENTE)** — não há salto de
  saída configurado no fim das seções.
  **NÃO CONFIRMADO:** não foi possível abrir o editor de ramificação de seção (somente leitura),
  então o comportamento de "fim de seção" não foi verificado na interface.

---

## 5. Comparativo com o Forms TRABALHISTA (`forms_mapping.py`)

### 5.1 Perguntas iguais — campo interno reaproveitável direto

| Campo interno (trabalhista) | Pergunta no cível | Nº no cível |
|---|---|---|
| `tipo_cadastro` | Tipo de cadastro | 34 |
| `cnj` | Número CNJ / Número de CNJ / Número do processo | 39, 82, 120, 147, 169 |
| `cliente` | Cliente principal / Nome do cliente | 35, 47, 79, 89, 121, 149, 170 |
| `contrario` | Contrário principal | 49, 91, 122, 151, 171 |
| `instancia` | Instância | 123, 163, 172 |
| `fase` | Fase Processual | 44, 78, 86 |
| `contingencia` | Contingência / Contigência | 60, 102, 140 |
| `probabilidade` | Probabilidade atual | 62, 104, 141 |
| `grau_probabilidade` | Faixa de probabilidade atual | 63, 105, 142 |
| `risco` | Risco / Risco do processo | 61, 103, 143 |
| `contrato_honorarios` | Negociação do contrato de honorários | 36, 80 |
| `outros_envolvidos` | Outros envolvidos (se houver) e sua posição nos autos | 52, 94 |
| `advogado` | Advogado responsável (pelo processo) | 50, 92, 152 |
| `procedimento` | Procedimento | 42, 83 |
| `cidade_comarca` | Cidade/Comarca | 45, 87 |
| `valor_causa` | Valor da causa | 58, 100 |
| `data_citacao` | Data da citação | 70, 112 |
| `situacao_pedido` | Situação do pedido | 124, 173 |
| `motivo` | Motivo | 126, 175 |
| `valor_acordo_condenacao` | Valor do acordo/condenção | 127, 176 |
| `valor_honorarios` | Valor de honorários | 128, 177 |
| `valor_custas` | Valor custas | 129, 179 |
| `custas` | Custas | 130, 178 |
| `tipo_resultado` | Tipo de resultado | 131, 180 |
| `resultado` | Resultado | 132, 181 |
| `motivo_resultado` | Motivo do resultado | 133, 182 |
| `data_resultado` | Data do resultado | 134, 183 |
| `data_sentenca` | Data da sentença | 135, 184 |
| `data_arquivamento` | Data de arquivamento | 185 |
| `cobranca_honorarios_sucumbenciais` | Cobrança de honorários sucumbenciais? | 136, 186 |
| `justificativa_nao_cobranca_honorarios_sucumbenciais` | Justifique a não cobrança de honorários sucumbenciais | 137, 187 |
| `cobranca_honorarios_contratuais_exito` | Cobrança de honorários contratuais de êxito? | 138, 188 |
| `justificativa_nao_cobranca_honorarios_contratuais` | Justifique a não cobrança de honorários contratuais de êxito | 139, 189 |
| `posicao` | Posição cliente principal / Posição nos autos do Cliente Principal | 48, 90, 150 |
| `data_distribuicao` | Data de distribuição do recurso | 153 |
| `tipo_classe_recurso` | Tipo de recurso | 155 |
| `orgao` / `uf` / `cidade` / `comarca` / `numero_turma` | Órgão / UF / Cidade / Comarca / N° Turma | 159–164 |
| `objetos_recurso` | Objeto do recurso | 166 |
| `classificacao_pedidos_recurso` | Classificação de cada pedido (…) | 167 |
| `observacoes` | Observações | 64, 106, 146, 168, 190 |
| `valor_deferido_por_pedido` | Valor deferido | 125, 174 |
| `vinculo` / `tipo_vinculo` | Vínculo / Tipo de vínculo | 53/54, 95/96, 144/145, 156/157 |

**Atenção às divergências de domínio (mesmo campo, opções diferentes):**

| Campo | Trabalhista | Cível |
|---|---|---|
| `motivo` (decisões) | …Provas produzidas pela Empresa / pelo RCTE | Q126: **Provas produzidas pelo réu / pelo autor** (Q175, no arquivamento, mantém Empresa/RCTE) |
| `instancia` | 1ª instância, 2ª instância, TST, 1º grau, 2º grau | Q123/172: 1ª/2ª instância · Q163: **1° Grau, 2º Grau, STJ** |
| `fase` | lista trabalhista | 13 fases cíveis (Arquivado…Recursal) |
| `risco` | Alto, Médio, Baixo | Q61/103: **Médio, Alto, Baixo** (ordem invertida); Q143: Alto, Médio, Baixo |
| `tipo_cadastro` | Cadastro inicial, Decisões, Recurso, Arquivamento completo, Arquivamento simples | Cadastro inicial, Decisões, Recurso, **Arquivamento** (único), **Incidente** |
| `tipo_vinculo` | — | 3 domínios distintos: 18 opções (Q54), 19 (Q96), 7 (Q145/157) |

### 5.2 Perguntas NOVAS / exclusivas do cível

**Blocos inteiramente novos** (não existem no trabalhista):
- Todo o cadastro de **Pessoa Jurídica** (Q2–Q11) e **Pessoa Física** (Q12–Q33) — CNPJ, CPF, RG,
  título de eleitor, CTPS, NIT/PIS/PASEP, sexo, datas de nascimento/admissão/desligamento,
  grupos, classificações, contatos, endereços, prospecção, rede social, grupo empresarial.
- Toda a seção **INCIDENTE** (Q79–Q119) — o trabalhista não tem esse tipo de cadastro.

**Perguntas novas no ramo Processo:**

| Pergunta | Nº | Campo interno sugerido |
|---|---|---|
| Tipo de cadastro (entidade: PJ/PF/Processo) | 1 | `tipo_entidade` |
| Contrato (upload de arquivo) | 37 | `contrato_arquivo` |
| Tipo (Judicial/Administrativo/Arbitral) | 38, 81 | `tipo_processo` |
| Tipo de procedimento (Judicial/Administrativo/Arbitral) | 154 | `tipo_processo` |
| Sistema do processo eletrônico | 40 | `sistema_eletronico` |
| Ação | 41, 84 | `acao` |
| Natureza | 43, 85, 158 | `natureza` |
| Pesquisa RTOnline | 46, 88 | `pesquisa_rtonline` |
| Magistrado | 51, 93 | `magistrado` |
| Objeto do processo | 55, 97 | `objeto_processo` |
| Pedidos e objetos dos pedidos | 56, 98 | `pedidos` |
| Classificação de cada pedido (…) no cadastro inicial | 57, 99 | `classificacao_pedidos` |
| Centro de custo | 59, 101 | `centro_custo` |
| Supermercado Loja | 65, 107 | `supermercado_loja` |
| Centro de custo do cliente | 66, 108 | `centro_custo_cliente` |
| N° do cliente | 67, 109 | `numero_cliente` |
| Residencial | 68, 110 | `residencial` |
| Obra | 69, 111 | `obra` |
| Prescrição Bienal | 71, 113 | `prescricao_bienal` |
| Prescrição quinquenal | 72, 114 | `prescricao_quinquenal` |
| Honorários de êxito | 74, 116 | `honorarios_exito` |
| Dívidas não tributárias | 75, 117 | `dividas_nao_tributarias` |
| Data do pagamento | 76, 118 | `data_pagamento` |
| Valor adicional de provisão | 77, 119 | `valor_adicional_provisao` |
| Número antigo | 148 | `numero_antigo` |
| Nome da vara/turma | 165 | `nome_vara_turma` |

### 5.3 Perguntas do trabalhista que NÃO existem no cível

| Campo (trabalhista) | Pergunta |
|---|---|
| `funcao_rcte` | Função exercida pelo RCTE |
| `incluir_relatorio` | Incluir no relatório do LegalOne de horas trabalhadas? |
| `objetos` | Objetos (Contrato de trabalho / Outra) |
| `vinculo_trabalhista` | Há pedido de vínculo trabalhista? |
| `descricao_pedidos` | Descreva todos os pedidos com as respectivas informações… |
| `terceirizacao_1` / `terceirizacao_2` | Terceirização (duas ocorrências) |
| `pejotizacao` | Pejotização |
| `valor_total_deferido` | Valor total deferido |
| `valor_deferido_por_pedido` (título "Valor deferido para cada pedido") | no cível é só "Valor deferido" |
| `data_julgamento` | Data do julgamento |
| `responsabilidade` | Responsabilidade |
| `redirecionamento` | Redirecionamento da execução |
| `houve_interposicao_recurso` | Houve a interposição de recurso? Se sim, qual? |
| `parte_recorrente` | Parte recorrente |
| `datacloud_configurado` | Cadastrar no DataCloud? |
| `honorarios_favor_escritorio` / `valor_honorarios_favor_escritorio` | Honorários em favor do escritório? / Valor |
| `comentario_adicional` | Comentário adicional |
| `data_distribuicao` (cadastro inicial) | Data de distribuição — só existe para recurso no cível |
| — | "Arquivamento simples" não existe: o cível tem um único "Arquivamento" |

---

## 6. Bloco Python sugerido (apenas referência — não aplicado a `forms_mapping.py`)

> Este código **não** foi gravado em nenhum `.py`. É um rascunho no mesmo estilo do
> `forms_mapping.py` para os campos novos/alterados do cível. Sugestão de organização:
> um módulo `forms_mapping_civel.py` separado, porque os domínios de opções divergem
> do trabalhista e sobrescrevê-los quebraria o mapeamento existente.

```python
"""Rascunho: mapeamento do Microsoft Forms "Cível - cadastro LegalOne" (coleta 2026-08-04)."""

from forms_mapping import CampoForms

TIPOS_ENTIDADE_CIVEL = ("PESSOA JURIDICA", "PESSOA FISICA", "PROCESSO")

TIPOS_CADASTRO_CIVEL = (
    "CADASTRO INICIAL",
    "DECISOES",
    "RECURSO",
    "ARQUIVAMENTO",
    "INCIDENTE",
)

TIPO_ALIAS_CIVEL = {
    "pessoa juridica": "PESSOA JURIDICA",
    "pessoa fisica": "PESSOA FISICA",
    "processo": "PROCESSO",
    "cadastro inicial": "CADASTRO INICIAL",
    "decisoes": "DECISOES",
    "decisões": "DECISOES",
    "recurso": "RECURSO",
    "arquivamento": "ARQUIVAMENTO",
    "incidente": "INCIDENTE",
}

TIPO_TAREFA_POR_CADASTRO_CIVEL = {
    "CADASTRO INICIAL": "CADASTRO_INICIAL",
    "DECISOES": "DECISAO",
    "RECURSO": "RECURSO",
    "ARQUIVAMENTO": "ARQUIVAMENTO",
    "INCIDENTE": "INCIDENTE",
}


# ── Seção 1: qual entidade está sendo cadastrada ──────────────────────────────
ENTIDADE_FIELDS = (
    CampoForms(
        campo="tipo_entidade",
        pergunta="Tipo de cadastro",
        aliases=("1.tipo de cadastro",),
        obrigatorio=True,
        tipo_resposta="opcao_unica",
        opcoes=("Pessoa jurídica", "Pessoa física", "Processo"),
        observacao="Pergunta 1. Ramifica para as seções PJ / PF / PROCESSO. "
                   "NÃO confundir com a pergunta 34, que também se chama 'Tipo de cadastro'.",
    ),
)


# ── Seção 2: PESSOA JURÍDICA (perguntas 2 a 11) ───────────────────────────────
PESSOA_JURIDICA_FIELDS = (
    CampoForms(campo="cnpj", pergunta="CNPJ", aliases=("2.cnpj",),
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(
        campo="grupos", pergunta="Grupos", aliases=("3.grupos",),
        tipo_resposta="opcao_unica",
        opcoes=("Autoridade", "Cliente", "Colaborador", "Correspondente",
                "Ministério Público", "Parceiro", "Perito", "Potencial cliente",
                "Potencial fornecedor", "Potencial parceiro", "Sindicato", "Outra"),
    ),
    CampoForms(campo="endereco_alternativo", pergunta="Endereço alternativo",
               aliases=("4.endereço alternativo",), tipo_resposta="texto",
               observacao="Subtítulo: Residencial e/ou Comercial."),
    CampoForms(campo="telefone", pergunta="Contato telefônico",
               aliases=("5.contato telefônico",), tipo_resposta="texto",
               observacao="Subtítulo: Residencial, pessoal, comercial e/ou celular."),
    CampoForms(campo="email", pergunta="Endereço eletrônico",
               aliases=("6.endereço eletrônico",), tipo_resposta="texto",
               observacao="Subtítulo: Pessoal e/ou Comercial."),
    CampoForms(campo="data_fundacao", pergunta="Data da fundação",
               aliases=("7.data da fundação",), tipo_resposta="data"),
    CampoForms(campo="grupo_empresarial", pergunta="Grupo empresarial",
               aliases=("8.grupo empresarial",), tipo_resposta="texto"),
    CampoForms(campo="origem_prospeccao", pergunta="Origem da prospecção",
               aliases=("9.origem da prospecção", "30.origem da prospecção"),
               tipo_resposta="texto"),
    CampoForms(campo="categoria_cliente", pergunta="Categoria de cliente",
               aliases=("10.categoria de cliente", "32.categoria de cliente"),
               tipo_resposta="texto"),
    CampoForms(campo="rede_social", pergunta="Rede social",
               aliases=("11.rede social", "33.rede social"), tipo_resposta="texto"),
)


# ── Seção 3: PESSOA FÍSICA (perguntas 12 a 33) ────────────────────────────────
PESSOA_FISICA_FIELDS = (
    CampoForms(campo="nome", pergunta="Nome", aliases=("12.nome",),
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="titulo_eleitor", pergunta="Título de eleitor",
               aliases=("13.título de eleitor",), tipo_resposta="texto"),
    CampoForms(campo="cpf", pergunta="CPF", aliases=("14.cpf",),
               obrigatorio=True, tipo_resposta="texto"),
    CampoForms(campo="data_nascimento", pergunta="Data de nascimento",
               aliases=("15.data de nascimento",), tipo_resposta="data"),
    CampoForms(campo="sexo", pergunta="Sexo", aliases=("16.sexo",),
               obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=("Feminino", "Masculino")),
    CampoForms(campo="ctps", pergunta="N° da CTPS", aliases=("17.n° da ctps", "17.no da ctps"),
               tipo_resposta="texto"),
    CampoForms(campo="profissao", pergunta="Profissão", aliases=("18.profissão",),
               tipo_resposta="texto"),
    CampoForms(campo="identidade_profissional", pergunta="Identidade profissional",
               aliases=("19.identidade profissional",), tipo_resposta="texto"),
    CampoForms(campo="nit_pis_pasep", pergunta="NIT/PIS/PASEP",
               aliases=("20.nit/pis/pasep",), tipo_resposta="texto"),
    CampoForms(campo="rg", pergunta="RG", aliases=("21.rg",), tipo_resposta="texto"),
    CampoForms(
        campo="grupos", pergunta="Grupos", aliases=("22.grupos",),
        obrigatorio=True, tipo_resposta="opcao_multipla",
        opcoes=("Autoridade", "Cliente", "Colaborador", "Correspondente",
                "Ministério Público", "Parceiro", "Perito", "Potencial cliente",
                "Potencial fornecedor", "Potencial parceiro", "Sindicato", "Outra"),
    ),
    CampoForms(campo="classificacoes", pergunta="Classificações",
               aliases=("23.classificações",), tipo_resposta="opcao_unica",
               opcoes=("Ativo", "Inativo", "Outra")),
    CampoForms(campo="telefone", pergunta="Contato Telefônico",
               aliases=("24.contato telefônico",), tipo_resposta="texto"),
    CampoForms(campo="email", pergunta="Endereço Eletrônico",
               aliases=("25.endereço eletrônico",), tipo_resposta="texto"),
    CampoForms(campo="endereco_alternativo", pergunta="Endereço Alternativo",
               aliases=("26.endereço alternativo",), tipo_resposta="texto"),
    CampoForms(campo="data_admissao", pergunta="Data de admissão",
               aliases=("27.data de admissão",), tipo_resposta="data"),
    CampoForms(campo="data_desligamento", pergunta="Data de desligamento",
               aliases=("28.data de desligamento",), tipo_resposta="data"),
    CampoForms(campo="responsavel_prospeccao", pergunta="Responsável pela prospecção",
               aliases=("29.responsável pela prospecção",), tipo_resposta="texto"),
    CampoForms(campo="empresa_vinculo", pergunta="Empresa que a pessoa possui vínculo",
               aliases=("31.empresa que a pessoa possui vínculo",), tipo_resposta="texto"),
)


# ── Campos novos do ramo PROCESSO (comuns a CADASTRO INICIAL e INCIDENTE) ──────
PROCESSO_FIELDS_NOVOS = (
    CampoForms(
        campo="tipo_cadastro", pergunta="Tipo de cadastro",
        aliases=("34.tipo de cadastro",), obrigatorio=True, tipo_resposta="opcao_unica",
        opcoes=("Cadastro inicial", "Decisões", "Recurso", "Arquivamento", "Incidente"),
        observacao="Pergunta 34. A opção 'Recurso' vem com espaço inicial na definição do Forms.",
    ),
    CampoForms(campo="contrato_arquivo", pergunta="Contrato",
               aliases=("37.contrato",), tipo_resposta="upload",
               observacao="Até 10 arquivos, 1GB cada; Word/Excel/PPT/PDF/Imagem/Vídeo/Áudio."),
    CampoForms(campo="tipo_processo", pergunta="Tipo",
               aliases=("38.tipo", "81.tipo", "tipo de procedimento", "154.tipo de procedimento"),
               obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=("Judicial", "Administrativo", "Arbitral")),
    CampoForms(campo="sistema_eletronico", pergunta="Sistema do processo eletrônico",
               aliases=("40.sistema do processo eletrônico",), tipo_resposta="texto"),
    CampoForms(campo="acao", pergunta="Ação", aliases=("41.ação", "84.ação"),
               obrigatorio=True, tipo_resposta="opcao_unica",
               observacao="79 opções na seção CADASTRO INICIAL e 20 opções na seção INCIDENTE "
                          "— ver MAPEAMENTO_FORMS_CIVEL.md, seção 3."),
    CampoForms(campo="natureza", pergunta="Natureza",
               aliases=("43.natureza", "85.natureza", "158.natureza"),
               obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=("Administrativo", "Ambiental", "Cível", "Constitucional", "Criminal",
                       "Empresarial", "Família", "Sucessões", "Trabalhista", "Tributária"),
               observacao="Na seção RECURSOS (pergunta 158) o domínio é só "
                          "Cível/Trabalhista/Tributário + Outra."),
    CampoForms(campo="pesquisa_rtonline", pergunta="Pesquisa RTOnline",
               aliases=("46.pesquisa rtonline", "88.pesquisa rtonline"), tipo_resposta="texto",
               observacao="Subtítulo: Objeto/mérito da ação para pesquisas."),
    CampoForms(campo="magistrado", pergunta="Magistrado",
               aliases=("51.magistrado", "93.magistrado"), obrigatorio=True,
               tipo_resposta="texto", observacao="Subtítulo: Juiz ou Desembargador Relator."),
    CampoForms(campo="objeto_processo", pergunta="Objeto do processo",
               aliases=("55.objeto do processo", "97.objeto do processo"),
               obrigatorio=True, tipo_resposta="texto_multilinha"),
    CampoForms(campo="pedidos", pergunta="Pedidos e objetos dos pedidos",
               aliases=("56.pedidos e objetos dos pedidos", "98.pedidos e objetos dos pedidos"),
               obrigatorio=True, tipo_resposta="texto_multilinha",
               observacao="No cível é texto livre, não múltipla escolha como no trabalhista."),
    CampoForms(
        campo="classificacao_pedidos",
        pergunta="Classificação de cada pedido ( Probabilidade atual de êxito ou perda - remota, "
                 "possível, provável) e os valores de provisão para cada pedido "
                 "(remota, possível, provável)",
        aliases=("57.classificação de cada pedido", "99.classificação de cada pedido"),
        obrigatorio=True, tipo_resposta="texto_multilinha",
    ),
    CampoForms(
        campo="centro_custo", pergunta="Centro de custo",
        aliases=("59.centro de custo", "101.centro de custo"),
        obrigatorio=True, tipo_resposta="opcao_multipla",
        opcoes=("Cível", "Tributário", "Trabalhista", "Ambiental", "Administrativo",
                "Família", "Relações governamentais", "Pastas sigilosas", "Penal", "Outra"),
    ),
    CampoForms(campo="supermercado_loja", pergunta="Supermercado Loja",
               aliases=("65.supermercado loja", "107.supermercado loja"), tipo_resposta="texto"),
    CampoForms(campo="centro_custo_cliente", pergunta="Centro de custo do cliente",
               aliases=("66.centro de custo do cliente", "108.centro de custo do cliente"),
               tipo_resposta="texto"),
    CampoForms(campo="numero_cliente", pergunta="N° do cliente",
               aliases=("67.n° do cliente", "109.n° do cliente"), tipo_resposta="texto"),
    CampoForms(campo="residencial", pergunta="Residencial",
               aliases=("68.residencial", "110.residencial"), tipo_resposta="texto"),
    CampoForms(campo="obra", pergunta="Obra", aliases=("69.obra", "111.obra"),
               tipo_resposta="texto"),
    CampoForms(campo="prescricao_bienal", pergunta="Prescrição Bienal",
               aliases=("71.prescrição bienal", "113.prescrição bienal"), tipo_resposta="texto"),
    CampoForms(campo="prescricao_quinquenal", pergunta="Prescrição quinquenal",
               aliases=("72.prescrição quinquenal", "114.prescrição quinquenal"),
               tipo_resposta="texto"),
    CampoForms(campo="honorarios_exito", pergunta="Honorários de êxito",
               aliases=("74.honorários de êxito", "116.honorários de êxito"),
               tipo_resposta="texto"),
    CampoForms(campo="dividas_nao_tributarias", pergunta="Dívidas não tributárias",
               aliases=("75.dívidas não tributárias", "117.dívidas não tributárias"),
               tipo_resposta="texto"),
    CampoForms(campo="data_pagamento", pergunta="Data do pagamento",
               aliases=("76.data do pagamento", "118.data do pagamento"), tipo_resposta="data"),
    CampoForms(campo="valor_adicional_provisao", pergunta="Valor adicional de provisão",
               aliases=("77.valor adicional de provisão", "119.valor adicional de provisão"),
               tipo_resposta="texto"),
    CampoForms(
        campo="fase", pergunta="Fase Processual",
        aliases=("44.fase processual", "78.fase processual", "86.fase processual"),
        obrigatorio=True, tipo_resposta="opcao_unica",
        opcoes=("Arquivado", "Conciliatória", "Conhecimento", "Cumprimento de Sentença",
                "Decisória", "Encerrado", "Executória", "Extinto", "Inicial", "Instrutória",
                "Julgamento", "Liquidação", "Recursal"),
        observacao="Aparece 2x na seção CADASTRO INICIAL (perguntas 44 e 78).",
    ),
    CampoForms(
        campo="procedimento", pergunta="Procedimento",
        aliases=("42.procedimento", "83.procedimento"),
        obrigatorio=True, tipo_resposta="opcao_unica",
        opcoes=("Administrativo", "Especial", "Ordinário", "Sumário", "Sumaríssimo"),
    ),
    CampoForms(
        campo="tipo_vinculo", pergunta="Tipo de vínculo",
        aliases=("54.tipo de vínculo", "96.tipo de vínculo",
                 "145.tipo de vínculo", "157.tipo de vínculo"),
        tipo_resposta="opcao_unica",
        observacao="Três domínios distintos: 18 opções (Q54), 19 (Q96, inclui 'Requerimento de "
                   "Efeito Suspensivo') e 7 (Q145/Q157: Liminar, Incidentes, Embargos à execução, "
                   "Execução, Cumprimento de sentença, Carta precatória, Recurso + Outra).",
    ),
)


# ── Campos novos da seção RECURSOS ────────────────────────────────────────────
RECURSO_CIVEL_FIELDS_NOVOS = (
    CampoForms(campo="numero_antigo", pergunta="Número antigo",
               aliases=("148.número antigo",), tipo_resposta="texto"),
    CampoForms(campo="nome_vara_turma", pergunta="Nome da vara/turma",
               aliases=("165.nome da vara/turma",), tipo_resposta="texto"),
    CampoForms(campo="instancia", pergunta="Instância", aliases=("163.instância",),
               obrigatorio=True, tipo_resposta="opcao_unica",
               opcoes=("1° Grau", "2º Grau", "STJ", "Outra"),
               observacao="Domínio diferente das perguntas 123 e 172 (1ª/2ª instância)."),
)


# ── Ajustes de domínio para DECISÕES no cível ─────────────────────────────────
DECISOES_CIVEL_OVERRIDES = (
    CampoForms(
        campo="motivo", pergunta="Motivo", aliases=("126.motivo",),
        tipo_resposta="opcao_unica",
        opcoes=("Ausência de concreta fundamentação", "Ausência de provas", "Danos constatados",
                "Falta de documentos", "Precedentes jurisprudenciais",
                "Provas produzidas pelo réu", "Provas produzidas pelo autor", "Outra"),
        observacao="No cível (decisões) as duas últimas opções são réu/autor, não Empresa/RCTE. "
                   "Na seção ARQUIVAMENTO (pergunta 175) volta a ser Empresa/RCTE.",
    ),
    CampoForms(campo="valor_deferido", pergunta="Valor deferido",
               aliases=("125.valor deferido", "174.valor deferido"),
               tipo_resposta="texto",
               observacao="Pergunta 174 (ARQUIVAMENTO) é multilinha e obrigatória."),
)


MAPEAMENTO_CIVEL_POR_SECAO = {
    "PESSOA JURIDICA": ENTIDADE_FIELDS + PESSOA_JURIDICA_FIELDS,
    "PESSOA FISICA": ENTIDADE_FIELDS + PESSOA_FISICA_FIELDS,
    "CADASTRO INICIAL": PROCESSO_FIELDS_NOVOS,
    "INCIDENTE": PROCESSO_FIELDS_NOVOS,
    "DECISOES": DECISOES_CIVEL_OVERRIDES,
    "RECURSO": RECURSO_CIVEL_FIELDS_NOVOS,
    "ARQUIVAMENTO": (),
}
```

---

## 7. Itens NÃO CONFIRMADOS

1. **Comportamento de fim de seção** — não foi possível abrir o editor de ramificação de seção
   (a UI só o oferece dentro do modo de edição). O salto entre a última pergunta de uma seção e
   a próxima seção não foi verificado visualmente; só as ramificações das perguntas 1 e 34
   estão confirmadas pela definição do formulário.
2. **Perguntas 137/139/187/189** aparecem com **uma única** opção listada
   ("Sem previsão legal" / "Sem previsão contratual") mais o campo "Outra resposta".
   Isso confere com o que a página exibe, mas é um domínio incomum — vale confirmar com a área
   se faltou opção cadastrada.
3. **Espaços em branco nos títulos** — algumas perguntas têm espaço final no título
   (ex.: "Contato telefônico ", "Contrário principal ", "Cobrança de honorários contratuais de êxito? ").
   A normalização por `strip()` já resolve, mas o texto exato no Forms tem o espaço.
