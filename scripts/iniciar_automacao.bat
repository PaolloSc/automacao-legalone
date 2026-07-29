@echo off
REM Sobe a automacao LegalOne no PC (modo automatico, menu alimentado por stdin).
REM Chamado pela tarefa agendada "LegalOne Automacao" no logon.
cd /d "%~dp0.."
REM LEGALONE_HEADLESS=1 (vindo de fora) roda sem janela; senao, Chrome visivel.
if "%LEGALONE_HEADLESS%"=="1" (set LEGALONE_HEADED=) else (set LEGALONE_HEADED=1)

REM O cadastro usa o Chrome real com o perfil browser_data; outro chrome.exe
REM segurando o lock do perfil faz o Playwright falhar ao abrir.
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 (
  echo [AVISO] Chrome aberto. Feche-o se a automacao falhar ao abrir o perfil.
)

echo [%date% %time%] iniciando automacao...
(echo 1& echo.) | "%~dp0..\venv\Scripts\python.exe" automacao_legalone_completa.py
echo [%date% %time%] automacao encerrou com codigo %errorlevel%
pause
