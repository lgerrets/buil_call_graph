.\env\Scripts\python.exe .\lgrey\main.py -i .\lgrey\ -k def class -t py

"C:\Program Files\Graphviz\bin\dot.exe" -Tpng .\graph.dot -o graph_dot.png

call graph_dot.png
