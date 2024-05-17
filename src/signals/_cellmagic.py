from __future__ import annotations

import typing

import ipywidgets
from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import display

from ._core import effect

if typing.TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell

EFFECTS = {}
CELL_ID = None


@magics_class
class SignalsMagics(Magics):
    @magic_arguments()
    @argument(
        "-n",
        "--name",
        type=str,
        default=None,
        help="Name the effect. Effects are cleaned up by name. default is the cell id.",
    )
    @cell_magic
    def effect(self, line, cell):
        """Excute code cell as an effect."""
        args = parse_argstring(SignalsMagics.effect, line)
        name = args.name or CELL_ID

        # Cleanup previous effect
        if name in EFFECTS:
            cleanup, output_widget = EFFECTS.pop(name)
            cleanup()
            output_widget.close()

        output_widget = ipywidgets.Output()

        @output_widget.capture(clear_output=True, wait=True)
        def run_cell():
            typing.cast("InteractiveShell", self.shell).run_cell(cell)

        EFFECTS[name] = (effect(run_cell), output_widget)
        display(output_widget)

    @cell_magic
    def clear_effects(self, line, cell):  # noqa: PLR6301
        """Clear all effects."""
        for cleanup, output_widget in EFFECTS.values():
            cleanup()
            output_widget.close()
        EFFECTS.clear()


def load_ipython_extension(ipython):
    """Load the IPython extension.

    `%load_ext signals` will load the extension and enable the `%%effect` cell magic.

    Parameters
    ----------
    ipython : IPython.core.interactiveshell.InteractiveShell
        The IPython shell instance.
    """

    # Not how else to get the cell id, seems like a hack
    # https://stackoverflow.com/questions/75185964/ipython-cell-magic-access-to-cell-id
    def pre_run_cell(info):
        global CELL_ID  # noqa: PLW0603
        CELL_ID = info.cell_id

    ipython.events.register("pre_run_cell", pre_run_cell)
    ipython.register_magics(SignalsMagics)
