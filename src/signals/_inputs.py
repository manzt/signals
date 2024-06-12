from __future__ import annotations

import pathlib
import typing
import weakref

from anywidget._descriptor import (
    MimeBundleDescriptor,  # noqa: PLC2701
    _comm_for,  # noqa: PLC2701
)

from ._core import Signal

COMMS = weakref.WeakKeyDictionary()


def signal_comm(
    signal: Signal,
    serialize=lambda x: x,
    deserialize=lambda x: x,
):
    if signal in COMMS:
        return COMMS[signal]

    comm = _comm_for(signal)

    def send_state(update):
        state = {"value": serialize(update)}
        comm.send(
            data={"method": "update", "state": state, "buffer_paths": []}, buffers=[]
        )

    def handle_msg(msg) -> None:
        data = msg["content"]["data"]
        if data["method"] == "update":
            if "state" in data:
                signal.value = deserialize(data["state"]["value"])
        elif data["method"] == "request_state":
            send_state(signal.peek())
        else:
            raise ValueError(f"Unrecognized method: {data['method']}.")

    comm.on_msg(handle_msg)
    send_state(signal.peek())
    signal.subscribe(send_state)

    COMMS[signal] = comm
    return comm


T = typing.TypeVar("T")


class Input(typing.Generic[T]):
    """A base class for inputs.

    Attributes
    ----------
    value: T | Signal[T]
        The current value of the input.
    label: str
        A label for the input.
    disabled: bool | Signal[bool]
        Whether the input is disabled.
    """

    _repr_mimebundle_ = MimeBundleDescriptor(
        _esm=pathlib.Path(__file__).parent / "widget.js", autodetect_observer=False
    )

    def __init__(
        self,
        value: T | Signal[T],
        *,
        label: str | None,
        disabled: bool | Signal[bool],
    ):
        self._value = value if isinstance(value, Signal) else Signal(value)
        self._disabled = disabled if isinstance(disabled, Signal) else Signal(disabled)
        self.label = label

    @property
    def value(self):
        return self._value.value

    @value.setter
    def value(self, update):
        self._value.value = update

    @property
    def disabled(self):
        return self._disabled.value

    @disabled.setter
    def disabled(self, update):
        self._disabled.value = update

    def _get_anywidget_state(self, include) -> dict[str, typing.Any]:
        return {
            "signal": f"signal:{signal_comm(self._value).comm_id}",
            "options": {
                "label": self.label,
                "value": self.value,
                "disabled": self.disabled,
            },
        }


class Toggle(Input):
    """A toggle input.

    Attributes
    ----------
    value: bool | Signal[bool]
        The current value of the input (default: False).
    values: tuple[typing.Any, typing.Any]
        The two values to toggle between.
    label: str
        A label for the input.
    """

    def __init__(
        self,
        *,
        value: bool | Signal[bool] = False,
        values: tuple[typing.Any, typing.Any] = (True, False),
        label: str | None = None,
        disabled: bool | Signal[bool] = False,
    ):
        super().__init__(value, label=label, disabled=disabled)
        self._values = values

    @property
    def value(self):
        idx = 0 if self._value.value is True else 1
        return self._values[idx]

    @value.setter
    def value(self, update):
        idx = self._values.index(update)
        assert idx != -1, f"Value must be one of {self._values}."
        self._value.value = self._values.index(update) == 0

    def _get_anywidget_state(self, include):
        state = super()._get_anywidget_state(include)
        state["kind"] = "toggle"
        return state


class Range(Input):
    """A range input.

    Attributes
    ----------
    extent: tuple[float, float]
        The range of the input.
    value: float | Signal[float]
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
    ):
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

    def _get_anywidget_state(self, include):
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
    value: T | Signal[T]
        The current value of the input.
    label: str
        A label for the input.
    format: Callable[[T], str]
        A function to format the value.
    disabled: bool | Signal[bool]
        Whether the input is disabled.
    """

    def __init__(  # noqa: PLR0913
        self,
        options: list[T] | dict[str, T],
        *,
        value: T | Signal[T] = None,
        label: str | None = None,
        format: typing.Callable[[T], str] | None = None,
        disabled: bool | Signal[bool] = False,
    ):
        if isinstance(options, dict):
            keys = list(options.keys())
            options = list(options.values())
            format = lambda x: keys[options.index(x)]  # noqa: A001, E731
        super().__init__(
            value if value is not None else options[0], label=label, disabled=disabled
        )
        self.options = options
        self.format = format
        self.label = label

    def _get_anywidget_state(self, include):
        state = super()._get_anywidget_state(include)
        state["kind"] = "radio"
        state["content"] = self.options
        state["options"].update(
            {"format": list(map(self.format, self.options)) if self.format else None}
        )
        return state


class Select(Radio):
    """A select input.

    options: list
        The options to choose from.
    value: T | Signal[T]
        The current value of the input.
    label: str
        A label for the input.
    format: Callable[[T], str]
        A function to format the value.
    disabled: bool | Signal[bool]
        Whether the input is disabled.
    """

    def _get_anywidget_state(self, include):
        state = super()._get_anywidget_state(include)
        state["kind"] = "select"
        return state


class Text(Input[str]):
    """A text input.

    value: str | Signal[str]
        The current value of the input.
    label: str
        A label for the input.
    placeholder: str
        A placeholder string for when the input is empty.
    disabled: bool | Signal[bool]
        Whether the input is disabled.
    """

    def __init__(
        self,
        *,
        value: str | Signal[str] = "",
        label: str | None = None,
        placeholder: str | None = None,
        disabled: bool | Signal[bool] = False,
    ):
        super().__init__(value, label=label, disabled=disabled)
        self.placeholder = placeholder

    def _get_anywidget_state(self, include):
        state = super()._get_anywidget_state(include)
        state["kind"] = "text"
        state["options"].update({"placeholder": self.placeholder})
        return state


class Color(Input[str]):
    """A color input.

    value: str | Signal[str]
        The current value of the input.
    label: str
        A label for the input.
    disabled: bool | Signal[bool]
        Whether the input is disabled.
    """

    def __init__(
        self,
        *,
        value: str | Signal[str] = "#000000",
        label: str | None = None,
        disabled: bool | Signal[bool] = False,
    ):
        super().__init__(value, label=label, disabled=disabled)

    def _get_anywidget_state(self, include):
        state = super()._get_anywidget_state(include)
        state["kind"] = "color"
        return state


class Form:
    _repr_mimebundle_ = MimeBundleDescriptor(
        _esm=pathlib.Path(__file__).parent / "widget.js",
        autodetect_observer=False,
    )

    def __init__(self, *inputs):
        self.inputs = inputs

    def _get_anywidget_state(self, include):
        return {
            "kind": "form",
            "inputs": [i._get_anywidget_state(include) for i in self.inputs],
        }


class SignalProperty:
    def __init__(self, signal):
        self.signal = signal

    def __get__(self, instance, owner):
        return self.signal.value

    def __set__(self, instance, value):
        self.signal.value = value


def form(*args, **kwargs):
    """Dynamically create a form from a set of inputs."""
    if args and kwargs:
        raise ValueError("Cannot mix positional and keyword arguments.")
    if args:
        # If the first argument is a class, assume it's a custom form.
        return Form(*args)

    class CustomForm:
        _repr_mimebundle_ = MimeBundleDescriptor(
            _esm=pathlib.Path(__file__).parent / "widget.js",
            autodetect_observer=False,
        )

        def __init__(self, **kwargs):
            self._inner = Form(*kwargs.values())

        def _get_anywidget_state(self, include):
            return self._inner._get_anywidget_state(include)

    # Add make the inputs properties of the form.
    for key, input_ in kwargs.items():
        if not input_.label:
            input_.label = key
        setattr(CustomForm, key, SignalProperty(input_))

    return CustomForm(**kwargs)
