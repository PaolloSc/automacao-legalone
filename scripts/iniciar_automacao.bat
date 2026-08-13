@echo off
REM Sobe a automacao LegalOne no PC (modo automatico, menu alimentado por stdin).
REM Chamado pela tarefa agendada "LegalOne Automacao" no logon.
cd /d "%~dp0.."
REM LEGALONE_HEADLESS=1 (vindo de fora) roda sem janela; senao, Chrome visivel.
REM Tira espacos: 'set VAR=1 && cmd' deixa o valor como "1 " e a comparacao falha.
set "LEGALONE_HEADLESS=%LEGALONE_HEADLESS: =%"
if "%LEGALONE_HEADLESS%"=="1" (set LEGALONE_HEADED=) else (set LEGALONE_HEADED=1)
echo [modo] LEGALONE_HEADLESS=[%LEGALONE_HEADLESS%] LEGALONE_HEADED=[%LEGALONE_HEADED%]

REM O cadastro usa o Chrome real com o perfil browser_data; outro chrome.exe
REM segurando o lock do perfil faz o Playwright falhar ao abrir.
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 (
  echo [AVISO] Chrome aberto. Feche-o se a automacao falhar ao abrir o perfil.
)

REM Supervisor: se a automacao cair (ou o watchdog matar por travamento),
REM sobe de novo em 30s. Nada de 'pause' aqui: sem console (tarefa agendada)
REM ele travaria pra sempre e a tarefa ficaria "Running" com o robo morto.
:loop
echo [%date% %time%] iniciando automacao...
(echo 1& echo.) | "%~dp0..\venv\Scripts\python.exe" automacao_legalone_completa.py
echo [%date% %time%] automacao encerrou com codigo %errorlevel% - reiniciando em 30s
REM ping em vez de timeout: 'timeout' morre quando stdin nao e console.
ping -n 31 127.0.0.1 >nul
goto loop
