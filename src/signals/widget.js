// @deno-types="npm:@observablehq/inputs@0.10.6";
import * as Inputs from "https://esm.sh/@observablehq/inputs@0.10.6";
// @deno-types="npm:@preact/signals-core@1.6.0"
import * as Signals from "https://esm.sh/@preact/signals-core@1.6.0";

async function fetch_styles() {
	const response = await fetch(
		"https://raw.githubusercontent.com/observablehq/inputs/main/src/style.css",
	);
	return response.text();
}

/**
 * @template T
 * @param {import("npm:@anywidget/types").AnyModel} model
 * @param {string} name
 */
function create_signal(model, name) {
	const value = Signals.signal(/** @type {T} */ (model.get(name)));
	model.on(`change:${name}`, () => {
		value.value = model.get(name);
	});
	return {
		get() {
			return value.value;
		},
		set(/** @type {T} */ update) {
			if (typeof update === "function") {
				update = update(model.get(name));
			}
			model.set(name, update);
			model.save_changes();
		},
	};
}

/**
 * @param {InputKind} kind
 * @param {Record<string, any>} options
 */
function resolve_options(kind, options) {
	switch (kind) {
		case "range":
			return {
				...options,
				// @ts-expect-error - we want to fallback to `undefined` if `options.transform` is not a valid key
				transform: {
					log: Math.log,
					sqrt: Math.sqrt,
				}[options.transform],
			};
		case "select":
		case "radio":
			return {
				...options,
				format: options.format
					? (
						/** @type {unknown} */ _,
						/** @type {number} */ i,
					) => {
						return options.format[i];
					}
					: undefined,
			};
		default:
			return options;
	}
}

/**
 * Remove all nullish values from an object.
 *
 * @param {Record<string, any>} obj
 * @returns {Record<string, any>}
 */
function omit_nullish(obj) {
	return Object.fromEntries(
		Object.entries(obj).filter(([, v]) => v != undefined),
	);
}

/**
 * @template T
 * @typedef {{ get(): T, set(value: T): void }} WebSignal
 */
/** @typedef {"range" | "radio" | "select" | "checkbox" | "toggle"} InputKind */
/**
 * @template SignalT
 * @typedef {{ kind: InputKind, content?: any, options: Record<string, any>, signal: SignalT }} InputData
 */

/**
 * @param {import("npm:@anywidget/types").AnyModel} model
 * @param {InputData<string>} input_data
 * @returns {Promise<InputData<WebSignal<unknown>>>}
 */
async function create_input_data(model, input_data) {
	const { kind, content, options, signal } = input_data;
	const model_id = signal.slice("signal:".length);
	const signal_model = await model.widget_manager.get_model(model_id);
	return {
		kind,
		content,
		options: omit_nullish(resolve_options(kind, options)),
		signal: create_signal(signal_model, "value"),
	};
}

/**
 * @param {InputKind} kind
 * @param {string | undefined} contents
 * @param {Record<string, any>} options
 * @returns {HTMLFormElement}
 */
function create_input(kind, contents, options) {
	return contents ? Inputs[kind](contents, options) : Inputs[kind](options);
}

/**
 * JupyterLab tries to soak up all keyboard events, so we need to stop them
 * from bubbling up to the document.
 */
function stop_propagation(/** @type {HTMLFormElement} */ input) {
	const events = ["keydown", "keypress", "keyup"];
	const listener = (/** @type {Event} */ event) => event.stopPropagation();
	for (const event of events) {
		input.addEventListener(event, listener);
	}
	return () => {
		for (const event of events) {
			input.removeEventListener(event, listener);
		}
	};
}

/**
 * @template T
 * @param {HTMLFormElement} input
 * @param {{ get(): T, set(value: T): void }} signal
 */
function connect_input(input, signal) {
	const dispose = Signals.effect(() => {
		input.value = signal.get();
		input.dispatchEvent(new Event("input", { bubbles: true }));
	});
	const dispose_propagation = stop_propagation(input);
	const listener = (/** @type {Event} */ event) => {
		event.stopPropagation();
		signal.set(input.value);
	};
	input.addEventListener("input", listener);
	return () => {
		dispose();
		dispose_propagation();
		input.removeEventListener("input", listener);
	};
}

export default () => {
	/** @type {Array<InputData<WebSignal<unknown>>>} */
	let data;
	return {
		/** @type {import("npm:@anywidget/types").Initialize} */
		async initialize({ model }) {
			/** @type {Array<InputData<string>>} */
			const entries = model.get("kind") === "form" ? model.get("inputs") : [{
				kind: model.get("kind"),
				content: model.get("content"),
				options: model.get("options"),
				signal: model.get("signal"),
			}];
			data = await Promise.all(
				entries.map((entry) => create_input_data(model, entry)),
			);
		},
		/** @type {import("npm:@anywidget/types").Render} */
		async render({ el }) {
			const root = document.createElement("div");
			el.appendChild(root);

			const shadow = root.attachShadow({ mode: "closed" });

			{
				// apply styles
				const style = document.createElement("style");
				// TODO: bundle these styles into the widget
				style.textContent = await fetch_styles();
				shadow.appendChild(style);
			}

			const inputs = data.map((input) => {
				const el = create_input(
					input.kind,
					input.content,
					input.options,
				);
				const dispose = connect_input(el, input.signal);
				return { el, dispose };
			});
			const form = Inputs.form(inputs.map((d) => d.el));
			shadow.appendChild(form);

			return () => {
				inputs.forEach((d) => d.dispose());
				root.remove();
			};
		},
	};
};
