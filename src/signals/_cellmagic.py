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

from ._core import effect

if typing.TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell


@magics_class
class SignalsMagics(Magics):
    @needs_local_scope
    @magic_arguments()
    @argument(
        "-n",
        "--name",
        type=str,
        default="_last_signals_effect",
        help=(
            "Name the effect. Effects are cleaned up by name. "
            " (default = _last_signals_effect)."
        ),
    )
    @cell_magic
    def effect(self, line, cell, local_ns):
        """Excute code cell as an effect."""
        args = parse_argstring(SignalsMagics.effect, line)

        if args.name in local_ns:
            cleanup, output_widget = local_ns[args.name]
            cleanup()
            output_widget.close()

        output_widget = ipywidgets.Output()

        @output_widget.capture(clear_output=True)
        def run_cell():
            typing.cast("InteractiveShell", self.shell).run_cell(cell)

        local_ns[args.name] = (effect(run_cell), output_widget)
        display(output_widget)
