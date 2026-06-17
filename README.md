# Automação LegalOne

Pipeline de automação para cadastro de processos no **LegalOne** (Thomson Reuters / Novajus) a partir de petições judiciais. Recebe dados via Microsoft Forms ou agente Copilot Studio, classifica com IA e cadastra automaticamente via navegador (Playwright) ou API REST.

> Projeto interno do escritório Carvalho & Furtado. As credenciais ficam em `.env` (nunca versionado).

## Arquitetura

```
Entrada → Monitor → Extração → Classificação IA → Cadastro
```

1. **Entrada** — Microsoft Forms **ou** agente Copilot Studio (chat aceita PDF/DOCX/DOC/texto)
2. **Monitor** — `outlook_monitor_graph.py` lê emails via Microsoft Graph API
3. **Extração** — `forms_extractor.py` (Forms) ou JSON direto (Copilot)
4. **Classificação** — `claude_brain.py` identifica tipo de tarefa
5. **Cadastro** — `legalone_cadastro.py` (Playwright) ou `legalone_api_cadastro.py` (REST)

## Tipos de Cadastro

Suporta 5 tipos, cada um com campos específicos (ver `forms_mapping.py`):

- `CADASTRO INICIAL`
- `DECISOES`
- `RECURSO`
- `ARQUIVAMENTO COMPLETO`
- `ARQUIVAMENTO SIMPLES`

## Duas Opções de Entrada

### Opção A — Copilot Studio (recomendada)
Agente extrai campos via LLM, advogado revisa no chat, Power Automate envia email estruturado para o bot. Ver [`docs/COPILOT_AGENTE.md`](docs/COPILOT_AGENTE.md).

### Opção B — Webhook OCR
`peticao_api.py` (FastAPI) recebe PDF/DOCX/DOC → Azure Document Intelligence (OCR) → Groq Llama (extração) → cadastro direto. Elimina dependência de email.

## Setup

```bash
# 1. Instalar dependências
pip install -r requirements.txt
playwright install chromium

# 2. Configurar credenciais
cp .env.example .env
# editar .env com seus valores

# 3. Rodar
python automacao_legalone_completa.py
```

## Variáveis de Ambiente

Ver `.env.example`. Principais:

| Variável | Uso |
|----------|-----|
| `LEGALONE_USERNAME` / `LEGALONE_PASSWORD` | Login LegalOne |
| `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` | Graph API (emails) |
| `GROQ_API_KEY` | Extração via LLM (grátis) |
| `FIRECRAWL_API_KEY` | Scraping Forms (opcional) |
| `AZURE_DOC_INTELLIGENCE_*` | OCR Opção B |
| `DATAJUD_API_KEY` | Override da chave pública do CNJ (opcional) |

## Testes

```bash
pytest
```

## Estrutura

```
automacao_legalone_completa.py   # Orquestrador principal
outlook_monitor_graph.py         # Monitor de emails (Graph API)
forms_extractor.py               # Extração do Microsoft Forms
forms_mapping.py                 # Mapeamento de campos por tipo
claude_brain.py                  # Classificação por IA
legalone_cadastro.py             # Cadastro via Playwright
legalone_api_cadastro.py         # Cadastro via API REST
peticao_api.py                   # Webhook OCR (Opção B)
peticao_extractor.py             # OCR + extração (Opção B)
config_azure.py                  # Config Azure
docs/COPILOT_AGENTE.md           # Doc do agente Copilot Studio
```

## Segurança / LGPD

- `.env`, logs e screenshots **nunca** são versionados (ver `.gitignore`)
- Dados de processos contêm informação de clientes — não commitar
- Sessões do navegador (`browser_data/`) contêm login autenticado — não commitar
