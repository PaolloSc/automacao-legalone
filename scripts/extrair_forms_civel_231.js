() => {
    const clean = (s) => (s || '').replace(/\n/g, ' ').trim();
    const containers = document.querySelectorAll('[data-automation-id="questionContent"], [data-automation-id="QuestionItem"]');
    const resultado = [];
    containers.forEach((container, idx) => {
        let titulo = '';
        const titleEl = container.querySelector('[data-automation-id="questionTitle"], [data-automation-id="QuestionText"], [data-automation-id="QuestionTitle"], [role="heading"]');
        if (titleEl) titulo = clean(titleEl.innerText);

        let subtitulo = '';
        const subEl = container.querySelector('[data-automation-id="questionSubtitle"], [data-automation-id="questionDescription"]');
        if (subEl) subtitulo = clean(subEl.innerText);

        let resposta_texto = '';
        const inputs = container.querySelectorAll('input[type="text"], input[type="date"], input[type="number"], textarea');
        for (const inp of inputs) {
            const val = (inp.value || '').trim();
            if (val) { resposta_texto = val; break; }
        }

        const marcadas = [];
        const opcoes = [];
        const choices = container.querySelectorAll('[data-automation-id="questionChoiceOptionContainer"]');
        for (const ch of choices) {
            const textEl = ch.querySelector('[data-automation-id="choiceText"]');
            const texto = clean(textEl ? textEl.innerText : ch.innerText);
            if (texto) opcoes.push(texto);
            const input = ch.querySelector('input');
            const checked = input ? input.checked : (ch.getAttribute('aria-checked') === 'true');
            if (checked && texto) marcadas.push(texto);
        }

        resultado.push({
            indice: idx + 1,
            pergunta: titulo,
            subtitulo: subtitulo,
            resposta_texto: resposta_texto,
            marcadas: marcadas,
            opcoes: opcoes,
            texto_completo: clean(container.innerText),
        });
    });
    return resultado;
}
