"""O salto exponencial acha a ultima resposta do Forms sem andar de uma em uma.

04/08: contador em #1 e ultima resposta em #828 — a seta leva ~2,2s por resposta,
ou seja meia hora so de navegacao antes de comecar o cadastro.

Reproduz a mesma aritmetica do laco de forms_extractor._ir_para_ultima_resposta,
com um Forms falso que trunca qualquer numero acima do total.
"""


def achar_ultima(total: int) -> tuple[int, int]:
    """Devolve (posicao_encontrada, quantidade_de_saltos)."""
    atual, passo, saltos = 1, 64, 0
    while passo:
        saltos += 1
        novo = min(atual + passo, total)  # o Forms para na ultima
        if novo > atual:
            atual = novo
            passo *= 2
        else:
            passo //= 2
    return atual, saltos


def test_acha_a_ultima_resposta():
    for total in (1, 2, 65, 100, 828, 5000):
        pos, _ = achar_ultima(total)
        assert pos == total, f"total={total} parou em {pos}"


def test_gasta_poucos_saltos_onde_a_seta_gastaria_827():
    _, saltos = achar_ultima(828)
    assert saltos < 30, saltos


if __name__ == "__main__":
    test_acha_a_ultima_resposta()
    test_gasta_poucos_saltos_onde_a_seta_gastaria_827()
    print("ok")
