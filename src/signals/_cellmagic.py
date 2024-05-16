import typing

import ipywidgets
from IPython.core.magic import (
    Magics,
    cell_magic,
    magics_class,
    needs_local_scope,
)
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import display

from ._signals import effect as _effect

if typing.TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell


@magics_class
class SignalMagics(Magics):
    @needs_local_scope
    @magic_arguments()
    @argument(
        "-n",
        "--name",
        type=str,
        default="_last_signal_effect",
        help=("Name of the signal effect widget. " " (default = _last_signal_effect)."),
    )
    @argument(
        "-c",
        "--cleanup",
        action="store_true",
        default=False,
        help="Destroy the previous effect before creating a new one.",
    )
    @cell_magic
    def effect(self, line, cell, local_ns):
        """Excute code in a cell as an effect."""
        args = parse_argstring(SignalMagics.effect, line)

        if args.cleanup and args.name in local_ns:
            cleanup, widget = local_ns[args.name]
            cleanup()
            widget.close()

        output = ipywidgets.Output()

        @output.capture(clear_output=True)
        def run():
            typing.cast("InteractiveShell", self.shell).run_cell(cell)

        local_ns[args.name] = (_effect(run), output)
        display(output)


def load_ipython_extension(ipython):
    """Use `%load_ext signals`."""
    ipython.register_magics(SignalMagics)
