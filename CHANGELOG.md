# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado
- Opção A: agente Copilot Studio para entrada de dados via chat (PDF/DOCX/texto)
- Opção B: webhook FastAPI com OCR (Azure Document Intelligence) + extração via Groq
- Suporte aos 5 tipos de cadastro com campos específicos (`forms_mapping.py`)
- Detecção dupla de fonte de email (Forms + Copilot) no monitor Graph API
- Documentação do agente Copilot em `docs/COPILOT_AGENTE.md`
- CI com ruff + pytest

### Alterado
- Chaves de API movidas para variáveis de ambiente (Firecrawl, DataJud)
- Lookback do monitor de emails ampliado de 30min para 120min

### Segurança
- Remoção de credenciais e dados pessoais hardcoded do código-fonte
