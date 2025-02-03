#!/usr/bin/env python3
"""
asciifx.repl
"""
import ast
import io
import os
import pexpect
import re
import sys
import time
from abc import ABC, abstractmethod
from code import InteractiveConsole
from collections.abc import Iterable, Iterator
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import NamedTuple

jupytext = None
IPython = None
try:
    import IPython
    import jupytext
except ImportError:
    pass

pygments = None
try:
    import pygments
    from pygments.lexers import PythonLexer, MarkdownLexer, BashLexer
    from pygments.formatters import TerminalTrueColorFormatter
    #from pygments.formatters import Terminal256Formatter
    #from pygments.formatters import TerminalFormatter
except ImportError:
    pass


class PygmentsConfig:
    def __getattribute__(self):
        raise ImportError("ImportError: pygments; pip install pygments")


if pygments:
    class PygmentsConfig:
        _lexer_python = PythonLexer()
        _lexer_markdown = MarkdownLexer()
        _lexer_shell = BashLexer()
        _lexers = {
            'python': _lexer_python,
            'markdown': _lexer_markdown,
            'shell': _lexer_shell,
        }

        #!pygmentize -L styles
        style='monokai'
        #style='github-dark'
        #style='solarized-dark'

        _formatter = TerminalTrueColorFormatter(style=style)


# Highlight a line of python code with pygments
# This is called for every character of every line
def highlight(code: str) -> str:
    return pygments.highlight(code, PygmentsConfig._lexer_python, PygmentsConfig._formatter)


def highlight_any(code: str, fmt: str) -> str:
    _lexer = PygmentsConfig._lexers.get(fmt)
    if _lexer is None:
        raise ValueError(('No _lexer for fmt found', ('fmt', fmt)))
    return pygments.highlight(code, _lexer, PygmentsConfig._formatter)


class Interaction(NamedTuple):
    prompt: str
    input: str
    output: str


class Repl(ABC):
    """The superclass of REPL implementations."""

    def simulate_all(self, lines: Iterable[str]) -> Iterator[Interaction]:
        """Process lines and simulate a terminal interaction
        
        simulate_all is called by perform.perform()
        """
        for line in lines:
            if self.will_terminate(line):
                yield Interaction(f"{self.prompt()} ", line, "")
                return

            yield self.simulate(line)

    def simulate(self, line: str) -> Interaction:
        """
        Simulate operation of the REPL on the given line. This method returns
        a triple with the prompt, the input (line), and some oracle's output.
        """
        prompt = self.prompt()

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            with redirect_stdout(buffer):
                self.eval(line)

        return Interaction(f"{prompt} ", self.format_python_code(line), buffer.getvalue())

    def format_python_code(self, output:str) -> str:
        return highlight(output) 

    @abstractmethod
    def prompt(self) -> str:
        ...

    @abstractmethod
    def will_terminate(self, line: str) -> bool:
        ...

    @abstractmethod
    def eval(self, line: str) -> None:
        ...




BOLDSTART = '\033[1m'
BOLDEND = '\033[0m'
PROMPTSTART = '\033[38;5;238m\033[1m'
PROMPTEND = BOLDEND + '\033[22m'


class PyRepl(Repl):
    """A Python REPL."""

    QUIT_INVOCATION = re.compile(r"^( |\t)*quit\(\)( |:|$)")

    #DEFAULT__FILE__ = "<string>"          # !python -c 'raise Exception()'
    #DEFAULT__FILE__ = "<stdin>"           # !echo 'raise Exception()' | python
    #DEFAULT__FILE__ = "<python-input-0>"  # !python < 'raise Exception()'
    #DEFAULT__FILE__ = '<python-input-{cell_n}-{hex(id(?todo))}>.py'  # IPython '
    DEFAULT__FILE__ = '_input.cast.py'
    # Python filenames with extra dots will not `import` like a normal .py

    def __init__(self, *, cwd: str = None, _file: str = None) -> None:
        """
        Kwargs:
            cwd (str): Current working directory for the interpreter
            _file: value to set ``__file__`` to in initializing the interpreter
        """
        if cwd is None:
            if _file is not None:
                cwd = Path(_file).parent
            else:
                cwd = Path('.')
        os.chdir(cwd)

        if _file is None:
            _file = self.DEFAULT__FILE__

        self.initialize_interpreter(_file=str(Path(cwd)/_file))
        self._more = False

    @staticmethod
    def escape_str_for_python(filestr):
        """
        >>> escape_str_for_python("file\n'\"name.json")
        'file\n\'"name.json'
        """
        return ast.unparse(ast.Constant(filestr))

    def initialize_interpreter(self, _file):
        self._interpreter = InteractiveConsole()
        self._interpreter.push('__file__ = {0}'.format(
            self.escape_str_for_python(_file)))

    def prompt(self) -> str:
        return f"{PROMPTSTART}...{PROMPTEND}" if self._more else f"{PROMPTSTART}>>>{PROMPTEND}"

    def will_terminate(self, line: str) -> bool:
        return self.QUIT_INVOCATION.match(line) is not None

    def eval(self, line: str) -> None:
        self._more = self._interpreter.push(line[:-1])


# class PyIpyRepl(PyRepl):

#     def initialize_interpreter(self):
#         PyRepl.initialize_interpreter(self)
#         self._interpreter.push('from IPython import display')
#         self._interpreter.push('from IPython import get_ipython')
#         # exit()
#         # quit()
#         # jupyter notebook also initializes TODO '_IPython' ?

class PexpectRepl(Repl):
    """A pexpect REPL."""
    command = None  # command to pexpect.spawn

    expect_pattern = '\n'

    QUIT_INVOCATION = re.compile(r"^( |\t)*quit\(\)( |:|$)")
    #QUIT_INVOCATION = re.compile(r"Do you really want to exit \(\[y\]/n\)\?")

    def __init__(self) -> None:
        self.proc = pexpect.spawn(self.command, encoding='utf8')
        self.proc.logfile_read = sys.stdout
        #self.proc.logfile_send = sys.stdout
        self._more = False

    def prompt(self) -> str:
        return "..." if self._more else ">>>"

    def will_terminate(self, line: str) -> bool:
        return self.QUIT_INVOCATION.match(line) is not None

    def eval(self, line: str) -> None:
        #print(('line', line), file=sys.stderr)
        for char in line:
            self.proc.send(line)
            time.sleep(0.1)  #TODO
        self.proc.expect(self.expect_pattern)
        self._more = '\n'.join((self.proc.before, self.proc.after))  # TODO: ?
        #print(('_more', self._more, self.proc.before, self.expect_pattern, self.proc.after), file=sys.stderr)
        #breakpoint()


class PexpectRepl2(PexpectRepl):
    expect_pattern = r'^In \[\d+\]: '


class IPyRepl(PexpectRepl):
    command = 'ipython'
    #expect_pattern = '.*'
    expect_pattern = '\n'
    #expect_pattern = r'In \[\d+\]:$'  # TODO: prompt regex?


class IPythonRepl(Repl):
    def __init__(self) -> None:
        self.proc = IPython.start_ipython()
        pexpect.spawn(self.command, encoding='utf8')
        self.proc.logfile_read = sys.stdout
        #self.proc.logfile_send = sys.stdout
        self._more = False

    def prompt(self) -> str:
        return "..." if self._more else ">>>"

    def will_terminate(self, line: str) -> bool:
        return self.QUIT_INVOCATION.match(line) is not None

    def eval(self, line: str) -> None:
        konsole.debug(('line', line))
        for char in line:
            self.proc.send(line)
            time.sleep(0.1)
        self.proc.expect(self.expect_pattern)
        self._more = '\n'.join((self.proc.before, self.proc.after))  # TODO: ?
        konsole.debug(('_more', self._more, self.proc.before, self.expect_pattern, self.proc.after))
        #breakpoint()


class JupytextRepl(PyRepl):

    def simulate_all(self, lines: Iterable[str], fmt: str = 'py:percent', syntax: str = 'python') -> Interaction[Interaction]:
        """Process lines with jupytext.reads() and simulate a notebook interaction with IPython
        
        - Called by perform.perform()
        """
        if jupytext is None:
            raise Exception("jupytext must be installed: $ pip install jupytext")

        self.nb = nb = jupytext.reads("\n".join(lines), fmt, config=None)
        assert nb['metadata']['jupytext']['main_language'] == 'python'
        assert nb['metadata']['jupytext']['text_representation'] == {
            'extension': '.py',
            'format_name': 'percent',
        }
        for cell in nb['cells']:
            print(('cell', cell), file=sys.stderr)
            breakpoint()
            # if self.will_terminate(cell['source']):
            #     yield Interaction(f"{self.prompt()} ", cell['source'], "")
            #     return
            yield self.simulate(cell, nb)

        self._interpreter.keep_running = False

    def simulate(self, cell:dict, nb:dict) -> Interaction:
        """
        Simulate operation of the REPL on the given line. This method returns
        a triple with the prompt, the input (line), and some oracle's output.
        """
        prompt = self.prompt()

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            with redirect_stdout(buffer):
                self.eval(cell['source'])

        breakpoint()

        return Interaction(
            f"{prompt} ",
            cell['source'],
            #self.highlight_any(cell['source'], cell['cell_type']),
            buffer.getvalue())

    def initialize_interpreter(self, _file):
        self.buffer = io.StringIO()
        with redirect_stderr(self.buffer):
            with redirect_stdout(self.buffer):
                # IPython.TerminalInteractiveShell mainloop()
                from IPython.terminal.interactiveshell import TerminalInteractiveShell
                #IPython.start_ipython(
                self._interpreter = TerminalInteractiveShell(
                    argv=None,
                    user_ns=dict(__file__=_file))
                #self._interpreter.mainloop()
                
    def eval(self, text: str) -> None:
        breakpoint()
        print(('text', text))
        self._interpreter.run_cell(text, store_history=True)
        breakpoint()
        #result.sucess
        #self._more = False  # TODO