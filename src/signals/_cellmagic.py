from __future__ import annotations

import typing

from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import clear_output, display

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
            cleanup = EFFECTS.pop(name)
            cleanup()

        display_handle = display(None, display_id=name)
        assert display_handle, "Failed to create display handle."
        shell = typing.cast("InteractiveShell", self.shell)

        shell.run_cell(cell, cell_id=name)
        clear_output()

        def run_cell():
            result = shell.run_cell(cell)
            display_handle.update(result.result)

        EFFECTS[name] = effect(run_cell)

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
