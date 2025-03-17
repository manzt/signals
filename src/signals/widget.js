// @deno-types="npm:@observablehq/inputs@0.10.6";
import * as Inputs from "https://esm.sh/@observablehq/inputs@0.10.6";
// @deno-types="npm:@preact/signals-core@1.6.0"
import * as Signals from "https://esm.sh/@preact/signals-core@1.6.0";

/**
 * @template T
 * @param {import("npm:@anywidget/types").AnyModel} model
 * @param {string} name
 */
function createSignal(model, name) {
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
function resolveOptions(kind, options) {
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
function omitNullish(obj) {
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
 * @typedef {{ kind: InputKind, content?: any, options: Record<string, any>, signal: SignalT }} InputSource
 */

/**
 * @param {import("npm:@anywidget/types").AnyModel} model
 * @param {InputSource<string>} inputSource
 * @returns {Promise<InputSource<WebSignal<unknown>>>}
 */
async function resolveInputSource(model, inputSource) {
	let { kind, content, options, signal } = inputSource;
	let modelId = signal.slice("signal:".length);
	let signalModel = await model.widget_manager.get_model(modelId);
	return {
		kind,
		content,
		options: omitNullish(resolveOptions(kind, options)),
		signal: createSignal(signalModel, "value"),
	};
}

/**
 * @template T
 * @param {InputSource<WebSignal<unknown>>} source
 * @param {Object} options
 * @param {AbortSignal} options.signal
 *
 * @returns {HTMLFormElement}
 */
function createConnectedInput(source, { signal }) {
	let { kind, content, options, signal: state } = source;

	/** @type {HTMLFormElement} */
	let input = content ? Inputs[kind](content, options) : Inputs[kind](options);

	if (signal.aborted) {
		return input;
	}

	let dispose = Signals.effect(() => {
		input.value = state.get();
		input.dispatchEvent(new Event("input", { bubbles: true }));
	});

	signal.addEventListener("abort", () => dispose());

	/**
	 * JupyterLab tries to soak up all keyboard events, so we need to stop them
	 * from bubbling up to the document.
	 */
	for (const event of /** @type {const} */ (["keydown", "keypress", "keyup"])) {
		input.addEventListener(
			event,
			(event) => event.stopPropagation(),
			{ signal },
		);
	}

	input.addEventListener(
		"input",
		(event) => {
			event.stopPropagation();
			state.set(input.value);
		},
		{ signal },
	);

	return input;
}

export default () => {
	/** @type {Array<InputSource<WebSignal<unknown>>>} */
	let sources;
	return {
		/** @type {import("npm:@anywidget/types").Initialize} */
		async initialize({ model }) {
			/** @type {Array<InputSource<string>>} */
			let entries = model.get("kind") === "form" ? model.get("inputs") : [{
				kind: model.get("kind"),
				content: model.get("content"),
				options: model.get("options"),
				signal: model.get("signal"),
			}];
			sources = await Promise.all(
				entries.map((entry) => resolveInputSource(model, entry)),
			);
		},
		/** @type {import("npm:@anywidget/types").Render} */
		render({ el }) {
			let controller = new AbortController();
			let root = document.createElement("div");

			{
				el.appendChild(root);
				controller.signal.addEventListener("abort", () => root.remove());
			}

			let shadow = root.attachShadow({ mode: "closed" });

			{
				// TODO: bundle these styles into the widget
				shadow.appendChild(
					Object.assign(document.createElement("link"), {
						rel: "stylesheet",
						href:
							"https://raw.githubusercontent.com/observablehq/inputs/main/src/style.css",
					}),
				);
				shadow.appendChild(
					Inputs.form(
						sources.map((source) =>
							createConnectedInput(source, { signal: controller.signal })
						),
					),
				);
			}

			return () => controller.abort();
		},
	};
};
