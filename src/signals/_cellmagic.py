# Copyright (c) 2024 Trevor Manz
from __future__ import annotations

import ast
import os
import typing

from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import DisplayHandle, display

from ._core import Disposer, batch, effect

if typing.TYPE_CHECKING:
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
        exec(code, user_global_ns, user_ns)  # noqa: S102
        return {}

    to_run_exec = nodelist[:-1]
    if to_run_exec:
        exec_code = compile(ast.Module(to_run_exec, []), cell_name, "exec")
        exec(exec_code, user_global_ns, user_ns)  # noqa: S102

    expr_code = compile(ast.Expression(nodelist[-1].value), cell_name, "eval")
    value = eval(expr_code, user_global_ns, user_ns)  # noqa: S307
    return {"value": value}


def prepare_cell_execution(shell: InteractiveShell, raw_code: str) -> Disposer:
    dh = DisplayHandle()
    transformed_code = shell.transform_cell(raw_code)
    cell_name = shell.compile.cache(
        transformed_code=transformed_code,
        number=shell.execution_count,
        raw_code=raw_code,
    )
    code_ast = shell.compile.ast_parse(transformed_code, filename=cell_name)

    def run_cell() -> None:
        try:
            result = run_ast_nodes(
                nodelist=code_ast.body,
                cell_name=cell_name,
                user_global_ns=shell.user_global_ns,
                user_ns=shell.user_ns,
            )
            if "value" in result:
                dh.update(result["value"])
        except Exception:  # noqa: BLE001
            shell.showtraceback()

    dh.display(None)  # create the display
    return effect(lambda: batch(run_cell))


def prepare_cell_execution_ipywidgets(
    shell: InteractiveShell,
    raw_code: str,
) -> Disposer:
    try:
        import ipywidgets  # noqa: PLC0415
    except ImportError:
        msg = "ipywidgets is required for this feature."
        raise ImportError(msg)  # noqa: B904

    import ipywidgets  # noqa: PLC0415

    output_widget = ipywidgets.Output()
    display(output_widget)

    @output_widget.capture(clear_output=True, wait=True)
    def run_cell() -> None:
        shell.run_cell(raw_code)

    cleanup_effect = effect(lambda: batch(run_cell))

    def cleanup() -> None:
        cleanup_effect()
        output_widget.close()

    return cleanup


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
    @argument(
        "--mode",
        type=str,
        default="displayhandle",
        help="The output mode for the effect. Either 'widget' or 'displayhandle'.",
    )
    @cell_magic
    def effect(self, line: str, cell: str) -> None:
        """Excute code cell as an effect.

        Raises
        ------
        ValueError
            If the mode is invalid.
        """
        args = parse_argstring(SignalsMagics.effect, line)
        name = args.name or CELL_ID

        # Cleanup previous effect
        if name in EFFECTS:
            cleanup = EFFECTS.pop(name)
            cleanup()

        shell = typing.cast("InteractiveShell", self.shell)
        mode = os.environ.get("SIGNALS_MODE", args.mode)

        if mode == "widget":
            cleanup = prepare_cell_execution_ipywidgets(shell, cell)
        elif mode == "displayhandle":
            cleanup = prepare_cell_execution(shell, cell)
        else:
            msg = f"Invalid mode: {args.mode}"
            raise ValueError(msg)

        EFFECTS[name] = cleanup

    @cell_magic
    def clear_effects(self, line: str, cell: str) -> None:  # noqa: ARG002, PLR6301
        """Clear all effects."""
        for cleanup in EFFECTS.values():
            cleanup()
        EFFECTS.clear()


def load_ipython_extension(ipython: InteractiveShell) -> None:
    """Load the IPython extension.

    `%load_ext signals` will load the extension and enable the `%%effect` cell magic.

    Parameters
    ----------
    ipython : IPython.core.interactiveshell.InteractiveShell
        The IPython shell instance.
    """

    # Not how else to get the cell id, seems like a hack
    # https://stackoverflow.com/questions/75185964/ipython-cell-magic-access-to-cell-id
    def pre_run_cell(info) -> None:  # noqa: ANN001
        global CELL_ID  # noqa: PLW0603
        CELL_ID = info.cell_id

    ipython.events.register("pre_run_cell", pre_run_cell)
    ipython.register_magics(SignalsMagics)
