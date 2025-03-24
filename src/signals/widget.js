import * as Inputs from "https://esm.sh/@observablehq/inputs@0.10.6";
/** @import { RenderProps, InitializeProps, AnyModel } from 'npm:@anywidget/types' */

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
 * @typedef {AnyModel<{value: T}>} ValueModel
 */

/** @typedef {"range" | "radio" | "select" | "checkbox" | "toggle"} InputKind */

/**
 * @template T
 * @typedef {{ kind: InputKind, content?: any, options: Record<string, any>, model: T }} InputSource
 */

/**
 * @param {AnyModel} model
 * @param {InputSource<string>} source
 * @returns {Promise<InputSource<AnyModel<{value: unknown}>>>}
 */
async function resolveInputSource(model, source) {
	let { kind, content, options, model: signal } = source;
	return {
		kind,
		content,
		options: omitNullish(resolveOptions(kind, options)),
		model: await model.widget_manager.get_model(
			signal.slice("signal:".length),
		),
	};
}

/**
 * @template T
 * @param {InputSource<ValueModel<T>>} source
 * @param {Object} options
 * @param {AbortSignal} options.signal
 * @param {(a: T, b: T) => boolean} options.equals
 *
 * @returns {HTMLFormElement}
 */
function createConnectedInput(source, { signal, equals }) {
	let { kind, content, options, model } = source;
	console.log({kind, content, options, model})

	/** @type {HTMLFormElement} */
	let input = content ? Inputs[kind](content, options) : Inputs[kind](options);

	if (signal.aborted) {
		return input;
	}

	function update() {
		let current = model.get("value");
		if (!equals(input.value, current)) {
			input.value = current;
			input.dispatchEvent(new Event("input", { bubbles: true }));
		}
	}

	model.on("change:value", update);
	signal.addEventListener("abort", () => {
		model.off("change:value", update);
	});

	input.addEventListener(
		"input",
		(event) => {
			event.stopPropagation();
			model.set("value", input.value);
			model.save_changes();
		},
		{ signal },
	);

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

	update();
	return input;
}

export default () => {
	/** @type {Array<InputSource<ValueModel<unknown>>>} */
	let sources;
	return {
		/** @param {InitializeProps} props */
		async initialize({ model }) {
			/** @type {Array<InputSource<string>>} */
			let entries = model.get("kind") === "form" ? model.get("inputs") : [{
				kind: model.get("kind"),
				content: model.get("content"),
				options: model.get("options"),
				model: model.get("signal"),
			}];
			sources = await Promise.all(
				entries.map((entry) => resolveInputSource(model, entry)),
			);
		},
		/** @param {RenderProps} props */
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
							createConnectedInput(source, {
								equals: Object.is,
								signal: controller.signal,
							})
						),
					),
				);
			}

			return () => controller.abort();
		},
	};
};
