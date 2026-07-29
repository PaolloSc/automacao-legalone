"""Segura o PC acordado por alguns minutos, para a automacao completar um ciclo.

A tarefa "LegalOne Despertar" desperta a maquina de tempos em tempos; sem isso
o Windows voltaria a dormir antes dos 300s do proximo ciclo do monitor.

Uso: python manter_acordado.py [minutos]   (padrao: 7)
"""
import ctypes
import sys
import time
from datetime import datetime

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

minutos = float(sys.argv[1]) if len(sys.argv) > 1 else 7.0

ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
print(f"[{datetime.now():%d/%m %H:%M:%S}] acordado por {minutos:g} min")
try:
    time.sleep(minutos * 60)
finally:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    print(f"[{datetime.now():%d/%m %H:%M:%S}] liberado para dormir")
