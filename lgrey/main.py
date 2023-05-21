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

HERE = os.path.dirname(__file__)
CONFIG_FILEPATH = os.path.join(HERE, "config.json")

# non CLI params
CANDIDATE_INDENTS = {" "*4, "\t"}

class Symbol:
    @staticmethod
    def path_to_hash(path):
        return ".".join(path)

    def __init__(self, path: List[str], indent_level: int, line: int, type: str) -> None:
        self.alias = path[-1]
        self.path = copy.deepcopy(path)
        self.indent_level = indent_level
        self.line = line
        self.type = type
    
    def to_hash(self) -> str:
        return self.path_to_hash(self.path)
    
    def to_name(self):
        return f'{self.type} {".".join(self.path)} L{self.line+1}'

class CallGraph:
    DUPLICATE_ALIAS = None

    def __init__(self, verbose: int):
        self.nx_graph = nx.DiGraph()
        self.symbols = {}
        self.alias_to_unique_symbol = {}
        self.verbose = verbose
        self.duplicated_alias = set()
    
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
            return None
        else:
            return symbol
    
    def path_to_symbol(self, path: List[str]) -> Symbol:
        return self.symbols[Symbol.path_to_hash(path)]
    
    def add_call(self, caller_symbol: Symbol, called_alias: str, line: int):
        called_symbol = self.alias_to_symbol(called_alias)
        if called_symbol is None:
            self.duplicated_alias.add(called_alias)
            return
        caller_hash = caller_symbol.to_name()
        called_hash = called_symbol.to_name()
        kwargs = {}
        if self.verbose > 0:
            data = self.nx_graph.get_edge_data(caller_hash, called_hash, default=None)
            if data is None:
                label = f"L{line+1}({line-caller_symbol.line})"
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
    
    def __del__(self):
        print(f"Found duplicated aliases: {self.duplicated_alias}. As a result, we cannot infer which ones of those occurences are being called.")

def main():
    parser = argparse.ArgumentParser(
        description="Statically analyze a code base and create a call graph",
    )
    parser.add_argument("-i", "--root", type=str, help="Root directory of the code base", required=True)
    parser.add_argument("-t", "--extension", help="File extension to be analyzed", type=str, required=False, default=None)
    parser.add_argument("-v", "--verbose", help="Verbose level of the final graph", type=int, default=2)

    args = parser.parse_args()

    assert os.path.exists(args.root), args.root

    config = json.load(open(CONFIG_FILEPATH, "r"))

    if args.extension is None:
        extension_to_files = {}
        for candidate_extention in config:
            filepaths = glob.glob(os.path.join(args.root, "**", f"*.{candidate_extention}"), recursive=True)
            extension_to_files[candidate_extention] = filepaths
        extension_to_n_files = {key: len(value) for key, value in extension_to_files.items()}
        extension = max(extension_to_n_files, key=extension_to_n_files.get)
        filepaths = glob.glob(os.path.join(args.root, "**", f"*.{extension}"), recursive=True)
        if len(filepaths) == 0:
            raise ValueError(f"Found no file with extension matching one of {list(config.keys())} in {args.root}. Please edit {CONFIG_FILEPATH}.")
        print(f"Infered extenion is '{extension}'.")
    else:
        extension = args.extension
        filepaths = glob.glob(os.path.join(args.root, "**", f"*.{extension}"), recursive=True)
        if len(filepaths) == 0:
            raise ValueError(f"Found no file with extension '{extension}' in {args.root}.")

    if extension in config:
        keywords = config[extension]
    else:
        raise NotImplementedError(f"No available keywords for extension '{extension}'. Please edit {CONFIG_FILEPATH}.")

    call_graph = CallGraph(verbose=args.verbose)
    indent = None
    for phase in range(2):
        for filepath in filepaths:
            if indent is None:
                with open(filepath, "r") as file:
                    file_content = file.read()
                    for candidate_indent in CANDIDATE_INDENTS:
                        if candidate_indent in file_content:
                            indent = candidate_indent
                if indent is None:
                    print(f"Could not infer the indent in {filepath} among '{CANDIDATE_INDENTS}'")
                else:
                    print(f"Infered indent is '{indent}'")

                def n_indents(line: str) -> int:
                    if line.startswith(indent):
                        return 1 + n_indents(line[len(indent):])
                    else:
                        return 0

            with open(filepath, "r") as file:
                # init root symbol
                root_symbol = os.path.basename(filepath)
                symbol = Symbol(
                    path=[root_symbol],
                    indent_level=-1, # the root is kind of defined with an indent level of 0 - 1 == - 1
                    line=0,
                    type="file",
                )
                if phase == 0:
                    call_graph.add_symbol(symbol)
                current_path = [root_symbol]

                for line_idx, line in enumerate(file.readlines()):
                    if len(line.strip()) == 0: # ignore empty lines
                        continue

                    indents = n_indents(line)
                    
                    # take into account reduced indents
                    while (call_graph.path_to_symbol(current_path).indent_level >= indents):
                        current_path.pop(len(current_path) - 1)

                    # is this line defining a new symbol?
                    defining_symbol = None
                    for keyword in keywords:
                        if keyword in line:
                            match = re.match(f".*{keyword} (\w+)[^\w].*", line)
                            if match is not None:
                                new_alias = match.groups()[0]
                                current_path.append(new_alias)
                                new_symbol = Symbol(
                                    path=current_path,
                                    indent_level=indents,
                                    line=line_idx,
                                    type=keyword,
                                )
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

    dot_path = "graph.dot"
    nx.nx_pydot.write_dot(nx_graph, dot_path)
    print(f"Created {dot_path}")

    # nx.draw(nx_graph)
    # plt.show()

if __name__ == "__main__":
    main()
