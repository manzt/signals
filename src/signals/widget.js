// @ts-check
import * as Inputs from "https://esm.sh/@observablehq/inputs@0.10.6";
import { createEffect, createSignal } from "https://esm.sh/solid-js@1.8.17";

/**
 * @param {HTMLFormElement} input
 */
function eventof(input) {
	switch (input.type) {
		case "button":
		case "submit":
			return "click";
		case "file":
			return "change";
		default:
			return "input";
	}
}

/**
 * @template T
 * @param {import("npm:@anywidget/types").AnyModel} model
 * @param {string} name
 */
function create_signal(model, name) {
	const [value, set_value] = createSignal(/** @type {T} */ (model.get(name)));
	model.on(`change:${name}`, () => {
		set_value(model.get(name));
	});
	return [
		value,
		(/** @type {T} */ update) => {
			if (typeof update === "function") {
				update = update(model.get(name));
			}
			model.set(name, update);
			model.save_changes();
		},
	];
}

/**
 * @param {string} kind
 * @param {Record<string, any>} options
 */
function resolve_options(kind, options) {
	switch (kind) {
		case "range":
			return {
				...options,
				// @ts-expect-error - we want to fallback to `undefined` if `options.transform` is not a valid key
				transform: { log: Math.log, sqrt: Math.sqrt }[options.transform],
			};
		case "radio":
			return {
				...options,
				format: options.format
					? (/** @type{unknown}*/ _, /** @type{number} */ i) =>
						options.format[i]
					: undefined,
			};
		default:
			return options;
	}
}

/** @typedef {"range" | "radio" | "select" | "checkbox" | "toggle"} InputKind */

/**
 * @param {InputKind} kind
 * @param {string | undefined} contents
 * @param {Record<string, any>} options
 * @returns {HTMLFormElement}
 */
function resolve_input(kind, contents, options) {
	options = resolve_options(kind, options);
	console.log(kind, contents, options);
	return contents ? Inputs[kind](contents, options) : Inputs[kind](options);
}

export default () => {
	/** @type{import("npm:solid-js").Accessor<any>} */
	let value;
	/** @type{import("npm:solid-js").Setter<any>} */
	let set_value;
	return {
		/** @type {import("npm:@anywidget/types").Initialize} */
		async initialize({ model }) {
			const model_id = model.get("signal").slice("signal:".length);
			const signal_model = await model.widget_manager.get_model(model_id);
			[value, set_value] = create_signal(signal_model, "value");
		},
		/** @type {import("npm:@anywidget/types").Render} */
		render({ model, el }) {
			const input = resolve_input(
				model.get("kind"),
				model.get("content"),
				model.get("options"),
			);
			createEffect(() => {
				input.value = value();
				input.dispatchEvent(new Event(eventof(input), { bubbles: true }));
			});
			input.addEventListener(eventof(input), () => {
				set_value(input.value);
			});
			el.appendChild(input);
		},
	};
};
