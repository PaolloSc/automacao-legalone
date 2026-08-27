# Prompt de Refatoração Estrutural — Fluxo Sequencial de Cadastro no Legal One

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

### FASE 1: Tela de Novo Cadastro (Capa Inicial)
Preencher exclusivamente os seguintes campos iniciais da capa:
1. **Ativar o monitoramento** (Checkbox/Switch)
2. **Título** (Input text)
3. **Cliente principal** (Combobox / Autocomplete)
4. **Posição** (Combobox)
5. **Contrário principal** (Combobox / Autocomplete)
6. **Responsável principal** (Combobox)
7. **Negociação de contrato de honorários:**
   * *Regra de Negócio:* Caso o campo esteja vazio/ausente nos dados de entrada, selecionar a opção **"Pro Bono"**, mas emitir um log de alerta (`WARNING`) e registrar no objeto da execução que a alteração posterior é necessária.
8. **Tipo de ação** (Combobox / Autocomplete)
9. **Centro de custo** (Combobox)
10. **Datacloud configurado?** (Campo de confirmação/status)
11. **Você cadastrou o Centro de Custo** (Confirmação visual/checagem)

➡️ **Ação de Transição:** Executar o salvamento inicial da capa (para desbloquear e consolidar as abas/seções dependentes no Legal One).

---

### FASE 2: Dados Processuais & Localização
Preencher a estrutura processual e localização na ordem:
1. **Órgão**
2. **Procedimento**
3. **Fase**
4. **Instância**
5. **Comarca / Foro**
6. **Vara / Turma**
7. **Pedidos**
8. **Vínculos** (preencher somente se houver dados informados)

---

### FASE 3: Previsão, Resultado, Risco & Regras de Honorários
Preencher a seção financeira e de valoração de risco do processo:
1. **Contingência**
2. **Probabilidade atual**
3. **Risco**
4. **Responsabilidade** (Direta, Subsidiária ou Solidária)
5. **Cobrança de Honorários Sucumbenciais?** (Sim/Não)
   * *Regra:* Se a resposta for **Não**, preencher obrigatoriamente a **Justificativa da não cobrança de honorários sucumbenciais**.
6. **Cobrança de Honorários Contratuais de Êxito?** (Sim/Não)
   * *Regra:* Se a resposta for **Não**, preencher obrigatoriamente a **Justificativa da não cobrança de honorários contratuais de êxito**.

➡️ **Ação de Transição:** Clicar no botão **Salvar e Fechar** e aguardar o modal/formulário fechar completamente.

---

### FASE 4: Finalização & Notificação
1. Validar se o formulário foi salvo com sucesso (sem mensagens de erro do Legal One no DOM).
2. Disparar a mensagem/e-mail de **confirmação de cadastro concluído** com o resumo dos dados cadastrados e o alerta de "Pro Bono" (se aplicável).

---

## 🛠️ Requisitos Técnicos de Implementação para o Codebase

1. **Tratamento de Combobox / Autocomplete:**
   * Garantir que todo preenchimento de lista suspensa use a função resiliente do `legalone_field_resolver.py`:
     * Focar no campo -> Limpar -> Digitar pausadamente com `press_sequentially(texto, delay=100)`.
     * Aguardar explicitamente a visibilidade do container da lista no DOM (`wait_for_selector`).
     * Enviar as teclas `ArrowDown` + `Enter` e finalizar com `Tab` (blur) para forçar o registro do objeto no frontend do Legal One.

2. **Separação em Funções/Módulos Limpos:**
   * Refatorar a função principal de cadastro dividindo-a em subfunções puras:
     * `preencher_fase1_capa(page, dados)`
     * `preencher_fase2_processual(page, dados)`
     * `preencher_fase3_risco_honorarios(page, dados)`
     * `salvar_e_fechar_cadastro(page)`
     * `notificar_conclusao(dados)`

3. **Mantenha os Testes e Mapeamentos Atualizados:**
   * Atualize a suíte de testes em `tests/` (ex: `test_e2e_mock_pipeline.py`) para validar que a nova sequência modular é executada sem falhas silenciosas.

---
*Por favor, aplique esta refatoração mantendo a compatibilidade com a arquitetura do projeto já existente.*
