@ECHO OFF
:: Garante que o script saiba onde ele mesmo está localizado
SET BASE_DIR=%~dp0
CD /D %BASE_DIR%

:: Referencia o "ambiente" fixo na rede
SET PYTHON_PORTATIL="U:\softwares\python_313\python.exe"
SET STREAMLIT_PORTATIL="U:\softwares\python_313\Scripts\streamlit.exe"
SET SCRIPT_DASHBOARD="%BASE_DIR%frontend_dashboard\Home.py"

ECHO Iniciando Monitor de Economia IFI...
ECHO Por favor, aguarde o navegador abrir.

:: Executa usando o ambiente da rede
%STREAMLIT_PORTATIL% run %SCRIPT_DASHBOARD%

PAUSE