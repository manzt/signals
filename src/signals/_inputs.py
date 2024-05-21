from __future__ import annotations

import msgspec
from anywidget._descriptor import MimeBundleDescriptor

esm = """
import * as inputs from "https://esm.sh/@observablehq/inputs";

export default {
    render({ model, el }) {
        el.appendChild(inputs.range());
    }
}
"""


class Range:
    _repr_mimebundle_ = MimeBundleDescriptor(_esm=esm)
