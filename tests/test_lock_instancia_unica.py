"""Sem guarda de instancia unica, o supervisor do iniciar_automacao.bat sobe
uma instancia nova sempre que a anterior morre -- e nada impedia uma segunda
instancia (manual ou reexecucao da tarefa agendada) rodar em paralelo com
ela. Achado ao vivo 11/09/2026: duas instancias processando o mesmo email ao
mesmo tempo -> 'abre duas telas / salva duas vezes' no LegalOne.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import automacao_legalone_completa as m


def _com_lock_temporario(tmp_path, fn):
    original = m.LOCK_FILE
    m.LOCK_FILE = str(tmp_path / "automacao.lock")
    try:
        fn()
    finally:
        m.LOCK_FILE = original


def test_recusa_segunda_instancia_com_pid_vivo(tmp_path):
    def cenario():
        with open(m.LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))  # nosso proprio PID esta' garantidamente vivo
        assert m._adquirir_lock_unico() is False
    _com_lock_temporario(tmp_path, cenario)


def test_assume_lock_de_pid_morto(tmp_path):
    def cenario():
        with open(m.LOCK_FILE, "w") as f:
            f.write("999999999")  # PID que quase certamente nao existe
        assert m._adquirir_lock_unico() is True
        assert open(m.LOCK_FILE).read().strip() == str(os.getpid())
    _com_lock_temporario(tmp_path, cenario)


def test_libera_lock_proprio_ao_sair(tmp_path):
    def cenario():
        assert m._adquirir_lock_unico() is True
        m._liberar_lock_unico()
        assert not os.path.exists(m.LOCK_FILE)
    _com_lock_temporario(tmp_path, cenario)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_recusa_segunda_instancia_com_pid_vivo(p)
        test_assume_lock_de_pid_morto(p)
        test_libera_lock_proprio_ao_sair(p)
    print("ok")
