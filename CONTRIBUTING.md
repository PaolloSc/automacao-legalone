# Contribuindo

Obrigado pelo interesse em contribuir! Este guia cobre o básico.

## Fluxo de trabalho

1. Faça um fork e crie uma branch a partir de `master`:
   ```bash
   git checkout -b feat/minha-feature
   ```
2. Instale as dependências de desenvolvimento:
   ```bash
   pip install -r requirements.txt
   pip install ruff pytest
   playwright install chromium
   ```
3. Faça suas alterações com testes.
4. Rode lint e testes localmente:
   ```bash
   ruff check .
   pytest
   ```
5. Abra um Pull Request descrevendo a mudança.

## Padrões de código

- **Python 3.12+**
- Lint com [ruff](https://github.com/astral-sh/ruff)
- Nomes de variáveis e comentários em português (consistente com o código existente)
- Segredos sempre via `os.getenv` — nunca hardcoded

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: adiciona suporte a cadastro de recurso
fix: corrige timeout no login do LegalOne
docs: atualiza README com instruções de setup
test: cobre extração de campos de decisão
```

## Segurança

- **Nunca** commite `.env`, logs, screenshots ou `browser_data/`
- Dados de processos contêm informação de clientes (LGPD) — não inclua em commits
- Reportou uma vulnerabilidade? Abra uma issue privada ou contate o mantenedor diretamente.
