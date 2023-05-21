import json
from subprocess import call
from typing import List, Union, Tuple
import matplotlib.pyplot as plt
import time
import networkx as nx
import copy
import re
from collections import defaultdict
import glob
import os
import argparse

# non CLI parameters
INDENT = "    "

def n_indents(line: str) -> int:
    if line.startswith(INDENT):
        return 1 + n_indents(line[len(INDENT):])
    else:
        return 0

class Symbol:
    @staticmethod
    def path_to_hash(path):
        return ".".join(path)

    def __init__(self, path: List[str], indent_level: int, line: int) -> None:
        self.alias = path[-1]
        self.path = copy.deepcopy(path)
        self.indent_level = indent_level
        self.line = line
    
    def to_hash(self) -> str:
        return self.path_to_hash(self.path)
    
    def to_name(self):
        return ".".join(self.path) + " L" + str(self.line+1)

class CallGraph:
    DUPLICATE_ALIAS = None

    def __init__(self, verbose: int):
        self.nx_graph = nx.DiGraph()
        self.symbols = {}
        self.alias_to_unique_symbol = {}
        self.verbose = verbose
    
    def add_symbol(self, symbol: Symbol):
        key = symbol.to_hash()
        assert key not in self.symbols, f"A symbol with key '{key}' already exists in {self.symbols}"
        self.symbols[key] = symbol
        if symbol.alias in self.alias_to_unique_symbol:
            self.alias_to_unique_symbol[symbol.alias] = CallGraph.DUPLICATE_ALIAS
        else:
            self.alias_to_unique_symbol[symbol.alias] = symbol
    
    def alias_to_symbol(self, alias: str) -> Union[None, Symbol]:
        symbol = self.alias_to_unique_symbol[alias]
        if symbol is CallGraph.DUPLICATE_ALIAS:
            print(f"Duplicated symbol {alias}")
            return None
        else:
            return symbol
    
    def path_to_symbol(self, path: List[str]) -> Symbol:
        return self.symbols[Symbol.path_to_hash(path)]
    
    def add_call(self, caller_symbol: Symbol, called_alias: str, line: int):
        called_symbol = self.alias_to_symbol(called_alias)
        if called_symbol is not None:
            caller_hash = caller_symbol.to_name()
            called_hash = called_symbol.to_name()
            kwargs = {}
            if self.verbose > 0:
                data = self.nx_graph.get_edge_data(caller_hash, called_hash, default=None)
                if data is None:
                    label = f"L{line}({line-caller_symbol.line})"
                else:
                    label = data["label"]
                    if label.startswith("L"):
                        label = "x2"
                    elif label.startswith("x"):
                        n_calls = int(label[1:])
                        label = f"x{n_calls + 1}"
                    else:
                        assert False, label
                kwargs["label"] = label
            self.nx_graph.add_edge(caller_hash, called_hash, **kwargs)

def main():
    parser = argparse.ArgumentParser(
        description="Statically analyze a code base and create a call graph",
    )
    parser.add_argument("-i", "--root", type=str, help="Root of the code base", required=True)
    parser.add_argument("-t", "--extensions", help="File extensions to be analyzed", nargs="+", required=True)
    parser.add_argument("-k", "--keywords", help="Code specific keywords that create functions (eg 'def' in python)", nargs="+", required=True)
    parser.add_argument("-v", "--verbose", help="Verbose level of the final graph", type=int, default=2)

    args = parser.parse_args()
    print(args.root)
    print(args.extensions)
    print(args.keywords)
    print(args.verbose)

    assert os.path.exists(args.root), args.root

    filepaths = sum([glob.glob(os.path.join(args.root, "**", f"*.{extension}"), recursive=True) for extension in args.extensions], [])

    call_graph = CallGraph(verbose=args.verbose)
    for phase in range(2):
        for filepath in filepaths:
            with open(filepath, "r") as file:
                assert INDENT in file.read()

            with open(filepath, "r") as file:
                # init root symbol
                root_symbol = os.path.basename(filepath)
                symbol = Symbol(
                    path=[root_symbol],
                    indent_level=-1, # the root is kind of defined with an indent level of 0 - 1 == - 1
                    line=0,
                )
                if phase == 0:
                    call_graph.add_symbol(symbol)
                current_path = [root_symbol]

                for line_idx, line in enumerate(file.readlines()):
                    if len(line.strip()) == 0:
                        continue

                    indents = n_indents(line)
                    
                    # take into account reduced indents
                    while (call_graph.path_to_symbol(current_path).indent_level >= indents):
                        current_path.pop(len(current_path) - 1)

                    # is this line defining a new symbol?
                    defining_symbol = None
                    for keyword in args.keywords:
                        if keyword in line:
                            match = re.match(f".*{keyword} (\w+)[^\w].*", line)
                            if match is not None:
                                new_alias = match.groups()[0]
                                current_path.append(new_alias)
                                new_symbol = Symbol(current_path, indents, line_idx)
                                defining_symbol = new_symbol
                                if phase == 0:
                                    call_graph.add_symbol(new_symbol)
                                break

                    if defining_symbol is None:
                        # what is the current symbol?
                        current_symbol = call_graph.path_to_symbol(current_path)
                        
                        # build the call graph
                        if phase == 1:
                            for called_alias in call_graph.alias_to_unique_symbol:
                                match = re.match(f".*[^\w]{called_alias}[^\w].*", line)
                                if match is not None:
                                    call_graph.add_call(current_symbol, called_alias, line_idx)

    # finally log the graoh

    nx_graph = call_graph.nx_graph
    print(nx_graph)

    nx.nx_pydot.write_dot(nx_graph, "graph.dot")

    # nx.draw(nx_graph)
    # plt.show()

if __name__ == "__main__":
    main()
