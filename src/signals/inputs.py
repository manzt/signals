# Copyright (c) 2024 Trevor Manz
"""Simple input widgets for use in Jupyter.

Note: Inputs are experimental and likely will end up in a separate package.
"""

from __future__ import annotations

import pathlib
import typing
import weakref

from ._core import Signal

try:
    from anywidget._descriptor import (
        MimeBundleDescriptor,  # noqa: PLC2701
        open_comm,  # noqa: PLC2701
    )
except ImportError as e:
    msg = (
        "anywidget is required to use the signals.inputs. "
        "Please install it with `pip install anywidget`."
    )
    raise ImportError(msg) from e

if typing.TYPE_CHECKING:
    from comm.base_comm import BaseComm

__all__ = [
    "Color",
    "Form",
    "Radio",
    "Range",
    "Select",
    "Text",
    "Toggle",
]

COMMS = weakref.WeakKeyDictionary()


def _signal_comm(
    signal: Signal[T],
    serialize: typing.Callable = lambda x: x,
    deserialize: typing.Callable = lambda x: x,
) -> BaseComm:
    if signal in COMMS:
        return COMMS[signal]

    comm = open_comm(
        # need anywidget comms need `_esm` to resolve
        initial_state={"_esm": "export default {}", "value": serialize(signal.peek())}
    )

    def send_state_update(update: T) -> None:
        comm.send(
            data={
                "method": "update",
                "state": {"value": serialize(update)},
                "buffer_paths": [],
            },
            buffers=[],
        )

    def handle_comm_message(message: dict[str, typing.Any]) -> None:
        data = message["content"]["data"]
        if data["method"] == "update":
            if "state" in data:
                value = deserialize(data["state"]["value"])
                signal.set(value)
        elif data["method"] == "request_state":
            send_state_update(signal.peek())
        else:
            msg = f"Unrecognized comm message. Method: {data['method']}."
            raise ValueError(msg)

    # deferred because we already sent initial state when opening comm
    dispose = signal.subscribe(send_state_update, defer=True)
    comm.on_msg(handle_comm_message)

    weakref.finalize(signal, dispose)
    COMMS[signal] = comm
    return comm


def _ensure_signal(value: T | Signal[T]) -> Signal[T]:
    return value if isinstance(value, Signal) else Signal(value)


T = typing.TypeVar("T")


class Input(typing.Generic[T]):
    """A base class for inputs.

    Attributes
    ----------
    value: Signal[T]
        The current value of the input.
    label: str
        A label for the input.
    disabled: Signal[bool]
        Whether the input is disabled.
    """

    _repr_mimebundle_ = MimeBundleDescriptor(
        _esm=pathlib.Path(__file__).parent / "widget.js",
        autodetect_observer=False,
    )

    def __init__(
        self,
        value: T | Signal[T],
        *,
        label: str | None,
        disabled: bool | Signal[bool],
    ) -> None:
        self._value = _ensure_signal(value)
        self.disabled = _ensure_signal(disabled)
        self.label = label

    def __call__(self) -> T:
        """Get the current value of the input.

        An alias for `get`.

        Returns
        -------
        T
            The current value of the input.
        """
        return self.get()

    def get(self) -> T:
        """Get the current value of the input.

        Returns
        -------
        T
            The current value of the input.
        """
        return self._value.get()

    def set(self, update: T) -> None:
        """Set the current value of the input.

        Parameters
        ----------
        update : T
            The new value of the input.
        """
        self._value.set(update)

    def peek(self) -> T:
        """Get the current value of the input without subscribing.

        Returns
        -------
        T
            The current value of the input.
        """
        return self._value.peek()

    def _get_anywidget_state(self, include: set[str] | None) -> dict:  # noqa: ARG002
        return {
            "model": f"signal:{_signal_comm(self._value).comm_id}",
            "options": {
                "label": self.label,
                "value": self._value.peek(),
                "disabled": self.disabled.peek(),
            },
        }


class Toggle(Input[bool]):
    """A toggle input.

    Attributes
    ----------
    value: Signal[bool]
        The current value of the input (default: False).
    label: str
        A label for the input.
    disabled: Signal[bool]
    """

    def __init__(
        self,
        *,
        value: bool | Signal[bool] = False,
        label: str | None = None,
        disabled: bool | Signal[bool] = False,
    ) -> None:
        super().__init__(value, label=label, disabled=disabled)

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        state = super()._get_anywidget_state(include)
        state["kind"] = "toggle"
        return state


class Range(Input[float]):
    """A range input.

    Attributes
    ----------
    extent: tuple[float, float]
        The range of the input.
    value: Signal[float]
        The current value of the input (default: min +  max / 2).
    step: float
        The interval between adjacent values.
    placeholder: str
        A placeholder string for when the input is empty.
    transform: Literal["linear", "log", "sqrt"]
        The transform method (default: "linear").
    width: int
        The width of the input (not including label).
    label: str
        A label for the input.
    disabled: bool | Signal[bool]
        Whether the input is disabled.
    """

    def __init__(  # noqa: PLR0913
        self,
        extent: tuple[float, float],
        *,
        value: float | Signal[float] | None = None,
        step: float | None = None,
        placeholder: str | None = None,
        transform: typing.Literal["linear", "log", "sqrt"] | None = None,
        width: int | None = None,
        label: str | None = None,
        disabled: bool | Signal[bool] = False,
    ) -> None:
        super().__init__(
            value if value is not None else extent[0] + extent[1] / 2,
            label=label,
            disabled=disabled,
        )
        self.extent = extent
        self.step = step
        self.format = format
        self.placeholder = placeholder
        self.transform = transform
        self.width = width

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        state = super()._get_anywidget_state(include)
        state["kind"] = "range"
        state["content"] = self.extent
        state["options"].update(
            {
                "step": self.step,
                "placeholder": self.placeholder,
                "transform": self.transform,
                "width": self.width,
            }
        )
        return state


class Radio(Input[T]):
    """A radio input.

    options: list
        The options to choose from.
    value: Signal[T]
        The current value of the input.
    label: str
        A label for the input.
    format: Callable[[T], str]
        A function to format the value.
    disabled: Signal[bool]
        Whether the input is disabled.
    """

    def __init__(
        self,
        options: list[T] | dict[str, T],
        *,
        value: T | Signal[T] = None,
        label: str | None = None,
        format: typing.Callable[[T], str] | None = None,  # noqa: A002
        disabled: bool | Signal[bool] = False,
    ) -> None:
        if isinstance(options, dict):
            keys = list(options.keys())
            options = list(options.values())
            format = lambda x: keys[options.index(x)]  # noqa: A001, E731
        super().__init__(
            value if value is not None else options[0],
            label=label,
            disabled=disabled,
        )
        self.options = options
        self.format = format
        self.label = label

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        state = super()._get_anywidget_state(include)
        state["kind"] = "radio"
        state["content"] = self.options
        state["options"].update(
            {
                "format": list(map(self.format, self.options)) if self.format else None,
            }
        )
        return state


class Select(Radio):
    """A select input.

    options: list
        The options to choose from.
    value: Signal[T]
        The current value of the input.
    label: str
        A label for the input.
    format: Callable[[T], str]
        A function to format the value.
    disabled: Signal[bool]
        Whether the input is disabled.
    """

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        state = super()._get_anywidget_state(include)
        state["kind"] = "select"
        return state


class Text(Input[str]):
    """A text input.

    value: Signal[str]
        The current value of the input.
    label: str
        A label for the input.
    placeholder: str
        A placeholder string for when the input is empty.
    disabled: Signal[bool]
        Whether the input is disabled.
    """

    def __init__(
        self,
        *,
        value: str | Signal[str] = "",
        label: str | None = None,
        placeholder: str | None = None,
        disabled: bool | Signal[bool] = False,
    ) -> None:
        super().__init__(value, label=label, disabled=disabled)
        self.placeholder = placeholder

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        state = super()._get_anywidget_state(include)
        state["kind"] = "text"
        state["options"].update({"placeholder": self.placeholder})
        return state


class Color(Input[str]):
    """A color input.

    value: Signal[str]
        The current value of the input.
    label: str
        A label for the input.
    disabled: Signal[bool]
        Whether the input is disabled.
    """

    def __init__(
        self,
        *,
        value: str | Signal[str] = "#000000",
        label: str | None = None,
        disabled: bool | Signal[bool] = False,
    ) -> None:
        super().__init__(value, label=label, disabled=disabled)

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        state = super()._get_anywidget_state(include)
        state["kind"] = "color"
        return state


class Form:
    """A form input."""

    _repr_mimebundle_ = MimeBundleDescriptor(
        _esm=pathlib.Path(__file__).parent / "widget.js",
        autodetect_observer=False,
    )

    @typing.overload
    def __init__(self, *inputs: Input) -> None: ...

    @typing.overload
    def __init__(self, **inputs: Input) -> None: ...

    def __init__(self, *args: Input, **kwargs: Input):
        if args and kwargs:
            msg = "Cannot mix positional and keyword arguments."
            raise ValueError(msg)
        self._inputs = tuple(kwargs.values()) if len(args) == 0 else args

        # if we have inputs as keyword arguments, set them as attributes
        if kwargs:
            for key, input_ in kwargs.items():
                if not input_.label:
                    input_.label = key
                setattr(self, input_.label, input_)

    def _get_anywidget_state(self, include: set[str] | None) -> dict:
        return {
            "kind": "form",
            "inputs": [i._get_anywidget_state(include) for i in self._inputs],  # noqa: SLF001
        }
