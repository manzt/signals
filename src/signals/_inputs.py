from __future__ import annotations

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


esm = """
import * as Inputs from "https://esm.sh/@observablehq/inputs";
import { createSignal, createEffect } from "https://esm.sh/solid-js";

function eventof(input) {
  switch (input.type) {
    case "button":
    case "submit": return "click";
    case "file": return "change";
    default: return "input";
  }
}

function create_signal(model, name) {
  let [value, set_value] = createSignal(model.get(name));
  model.on(`change:${name}`, () => {
    set_value(model.get(name));
  });
  return [
      value,
      (update) => {
        if (typeof update === "function") {
          update = update(model.get(name));
        }
        model.set(name, update);
        model.save_changes();
      }
  ];
}

function resolve_options(kind, options) {
  switch (kind) {
    case "range":
      return {
        ...options,
        transform: { "log": Math.log, "sqrt": Math.sqrt }[options.transform]
    }
    default:
        return options;
  }
}
export default () => {
  let value;
  let set_value;
  return {
      async initialize({ model }) {
          let model_id = model.get("signal").slice("signal:".length);
          [value, set_value] = create_signal(
              await model.widget_manager.get_model(model_id),
              "value",
          );
      },
      async render({ model, el }) {
        let kind = model.get("kind");
        let contents = model.get("content");
        let options = resolve_options(kind, model.get("options"));
        let input = contents ? Inputs[kind](contents, options) : Inputs[kind](options);
        createEffect(() => {
          input.value = value()
          input.dispatchEvent(new Event("input", { bubbles: true }));
        })
        input.addEventListener(eventof(input), (event) => {
            set_value(input.value);
        });
        el.appendChild(input);
      }
  }
}
"""


T = typing.TypeVar("T")


class Input(typing.Generic[T]):
    """A base class for inputs."""

    _repr_mimebundle_ = MimeBundleDescriptor(_esm=esm, autodetect_observer=False)

    def __init__(self, value: T | Signal[T]):
        self._value = value if isinstance(value, Signal) else Signal(value)

    @property
    def value(self):
        return self._value.value

    @value.setter
    def value(self, update):
        self._value.value = update

    def _get_anywidget_state(self, include) -> dict[str, typing.Any]:
        return {
            "signal": f"signal:{signal_comm(self._value).comm_id}",
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
        label: str = "",
        values: tuple[typing.Any, typing.Any] = (True, False),
    ):
        super().__init__(value)
        self.label = label
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
        state["options"] = {"label": self.label, "value": self.value}
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
    label: str
        A label for the input.
    placeholder: str
        A placeholder string for when the input is empty.
    transform: Literal["linear", "log", "sqrt"]
        The transform method (default: "linear").
    width: int
        The width of the input (not including label).
    """

    def __init__(  # noqa: PLR0913
        self,
        extent: tuple[float, float],
        *,
        value: float | Signal[float] | None = None,
        step: float | None = None,
        label: str | None = None,
        placeholder: str | None = None,
        transform: typing.Literal["linear", "log", "sqrt"] | None = None,
        width: int | None = None,
    ):
        super().__init__(value if value is not None else extent[0] + extent[1] / 2)
        self.extent = extent
        self.label = label
        self.step = step
        self.format = format
        self.placeholder = placeholder
        self.transform = transform
        self.width = width

    def _get_anywidget_state(self, include):
        state = super()._get_anywidget_state(include)
        state["kind"] = "range"
        state["content"] = self.extent
        state["options"] = {
            "label": self.label,
            "step": self.step,
            "value": self.value,
            "placeholder": self.placeholder,
            "transform": self.transform,
            "width": self.width,
        }
        for key in list(state["options"]):
            if state["options"][key] is None:
                del state["options"][key]
        return state
