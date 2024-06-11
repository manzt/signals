from __future__ import annotations

import ast
import typing

from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import display

from ._core import effect

if typing.TYPE_CHECKING:
    from IPython.core.display import DisplayHandle
    from IPython.core.interactiveshell import InteractiveShell

EFFECTS = {}
CELL_ID = None


def run_ast_nodes(
    nodelist: list,
    cell_name: str,
    user_global_ns: dict,
    user_ns: dict,
) -> dict:
    """Run a list of AST nodes.

    Parameters
    ----------
    nodelist : list
        List of AST nodes.
    cell_name : str
        The name of the cell.
    user_global_ns : dict
        The global namespace.
    user_ns : dict
        The user namespace.

    Returns
    -------
    dict
        A dictionary with the value of the last expression in the cell.
    """
    # If the last node is not an expression, run everything
    if not isinstance(nodelist[-1], ast.Expr):
        code = compile(ast.Module(nodelist, []), cell_name, "exec")
        exec(code)
        return {}

    to_run_exec = nodelist[:-1]
    if to_run_exec:
        exec_code = compile(ast.Module(to_run_exec, []), cell_name, "exec")
        exec(exec_code, user_global_ns, user_ns)

    expr_code = compile(ast.Expression(nodelist[-1].value), cell_name, "eval")
    value = eval(expr_code, user_global_ns, user_ns)
    return {"value": value}


def prepare_cell_execution(
    shell: InteractiveShell, raw_code: str, display_handle: DisplayHandle
):
    transformed_code = shell.transform_cell(raw_code)
    cell_name = shell.compile.cache(
        transformed_code=transformed_code,
        number=shell.execution_count,
        raw_code=raw_code,
    )
    code_ast = shell.compile.ast_parse(transformed_code, filename=cell_name)

    def run_cell():
        try:
            result = run_ast_nodes(
                nodelist=code_ast.body,
                cell_name=cell_name,
                user_global_ns=shell.user_global_ns,
                user_ns=shell.user_ns,
            )
            if "value" in result:
                display_handle.update(result["value"])
        except Exception:
            shell.showtraceback()

    return run_cell


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

        display_handle = display(None, display_id=True)
        assert display_handle, "Failed to create display handle."
        shell = typing.cast("InteractiveShell", self.shell)
        run_cell = prepare_cell_execution(shell, cell, display_handle)
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
