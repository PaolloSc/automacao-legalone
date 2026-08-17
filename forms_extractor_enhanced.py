"""
Forms Extractor aprimorado com BeautifulSoup e Spacy
"""

import asyncio
import os
from typing import Dict, Optional
from datetime import datetime
import re

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import spacy
from pydantic import BaseModel, Field

import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Mesma variavel usada em forms_extractor.py: FORMS_HEADLESS=1 roda sem janela.
FORMS_HEADLESS = os.getenv("FORMS_HEADLESS", "0").strip().lower() in ("1", "true", "yes", "y", "sim")

# Carregar modelo NLP para português
try:
    nlp = spacy.load("pt_core_news_sm")
except Exception:
    logger.warning("Modelo Spacy não encontrado, instale com: python -m spacy download pt_core_news_sm")
    nlp = None


class FormsResponse(BaseModel):
    """Modelo Pydantic para validação de dados"""
    cnj: Optional[str] = None
    tipo_cadastro: Optional[str] = None
    fase: Optional[str] = None
    instancia: Optional[str] = None
    cliente: Optional[str] = None
    contrario: Optional[str] = None
    advogado: Optional[str] = None
    comarca: Optional[str] = None
    valor_causa: Optional[str] = None
    procedimento: Optional[str] = None
    data_distribuicao: Optional[str] = None
    risco: Optional[str] = None
    probabilidade: Optional[str] = None
    outros_dados: Dict[str, str] = Field(default_factory=dict)


class EnhancedFormsExtractor:
    """Extrator aprimorado com múltiplas técnicas"""

    def __init__(self):
        self.soup_parser = "lxml"
        self.nlp = nlp

    async def extract_with_playwright_soup(self, url: str) -> Dict:
        """Combina Playwright com BeautifulSoup"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=FORMS_HEADLESS)
            page = await browser.new_page()

            await page.goto(url)
            await page.wait_for_selector("body")

            html_content = await page.content()

            soup = BeautifulSoup(html_content, self.soup_parser)
            structured_data = self._extract_structured(soup)

            await browser.close()
            return structured_data

    def _extract_structured(self, soup: BeautifulSoup) -> Dict:
        """Extrai dados estruturados do HTML"""
        data: Dict[str, str] = {}

        question_selectors = [
            ".office-form-question",
            ".question-title",
            "[role=\"heading\"]",
            "div[data-automation-id=\"QuestionText\"]",
        ]

        for selector in question_selectors:
            questions = soup.select(selector)
            for q in questions:
                question_text = q.get_text(strip=True)
                if not question_text:
                    continue

                answer = self._find_associated_answer(q)
                if answer:
                    self._classify_and_store(question_text, answer, data)

        return data

    def _find_associated_answer(self, question_element) -> Optional[str]:
        """Encontra resposta associada à pergunta"""
        parent = question_element.parent
        if parent:
            answer_selectors = [
                ".office-form-question-content",
                ".answer-text",
                "input[type=\"text\"]",
                "textarea",
                ".selected-option",
            ]

            for selector in answer_selectors:
                answer_elem = parent.select_one(selector)
                if answer_elem:
                    return answer_elem.get_text(strip=True) or answer_elem.get("value")

        return None

    def _classify_and_store(self, question: str, answer: str, data: Dict):
        """Classifica e armazena dados usando NLP simples"""
        q = question.lower()

        mapping = {
            "cnj": ["cnj", "número processo", "processo"],
            "tipo_cadastro": ["tipo cadastro", "cadastro"],
            "cliente": ["cliente principal", "cliente"],
            "advogado": ["advogado responsável", "advogado"],
            "comarca": ["comarca", "cidade"],
            "valor_causa": ["valor causa", "valor"],
            "fase": ["fase"],
            "instancia": ["instância", "instancia"],
            "procedimento": ["procedimento"],
        }

        for field, keywords in mapping.items():
            if any(k in q for k in keywords):
                data[field] = answer
                return

        data.setdefault("outros_dados", {})[question] = answer


async def teste_extrator_enhanced():
    url = input("Cole a URL do Forms: ").strip()
    if not url:
        logger.error("URL não fornecida")
        return

    extrator = EnhancedFormsExtractor()
    dados = await extrator.extract_with_playwright_soup(url)

    logger.info("\n" + "=" * 60)
    logger.info("RESULTADO ENHANCED:")
    logger.info("=" * 60)
    for k, v in dados.items():
        logger.info(f"{k}: {v}")


if __name__ == "__main__":
    asyncio.run(teste_extrator_enhanced())
