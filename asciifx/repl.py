from abc import ABC, abstractmethod
from code import InteractiveConsole
from collections.abc import Iterable, Iterator
from contextlib import redirect_stderr, redirect_stdout
import io
import re
from typing import NamedTuple


class Interaction(NamedTuple):
    prompt: str
    input: str
    output: str


class Repl(ABC):
    """The superclass of REPL implementations."""

    def simulate_all(self, lines: Iterable[str]) -> Iterator[Interaction]:
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


pygments = None
try:
    import pygments
    from pygments.lexers import PythonLexer
    from pygments.formatters import TerminalTrueColorFormatter
    #from pygments.formatters import Terminal256Formatter
    #from pygments.formatters import TerminalFormatter
except ImportError:
    pass


_lexer = PythonLexer()
#tokens = list(lexer.get_tokens(code)) 
style='monokai'  # pygmentize -L styles
#style='github-dark'
#style='solarized-dark'
_formatter = TerminalTrueColorFormatter(style=style)

def highlight(code: str) -> str:
    return pygments.highlight(code, _lexer, _formatter)


BOLDSTART = '\033[1m'
BOLDEND = '\033[0m'
PROMPTSTART = '\033[38;5;238m\033[1m'
PROMPTEND = BOLDEND + '\033[22m'


class PyRepl(Repl):
    """A Python REPL."""

    QUIT_INVOCATION = re.compile(r"^( |\t)*quit\(\)( |:|$)")

    def __init__(self) -> None:
        self._interpreter = InteractiveConsole()
        self._more = False

    def prompt(self) -> str:
        return f"{PROMPTSTART}...{PROMPTEND}" if self._more else f"{PROMPTSTART}>>>{PROMPTEND}"

    def will_terminate(self, line: str) -> bool:
        return self.QUIT_INVOCATION.match(line) is not None

    def eval(self, line: str) -> None:
        self._more = self._interpreter.push(line[:-1])
