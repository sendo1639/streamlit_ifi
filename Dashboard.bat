@ECHO OFF
ECHO Hello World! Your first batch file was printed on the screen successfully.
SET PYTHON_EXEC=".\ambiente\Scripts\streamlit.exe"
SET DASHBOARD=".\frontend_dashboard\Home.py" 
START  "PyScript" %PYTHON_EXEC% run %DASHBOARD%
PAUSE 