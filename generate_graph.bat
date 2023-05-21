@echo off

set rootdir=%1

.\env\Scripts\python.exe .\lgrey\main.py -i %rootdir%

if %errorlevel% neq 0 exit /b %errorlevel%

set output=graph_dot.png
"C:\Program Files\Graphviz\bin\dot.exe" -Tpng .\graph.dot -o %output%
if %errorlevel% neq 0 exit /b %errorlevel%

call %output%
