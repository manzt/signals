import * as Inputs from "https://esm.sh/@observablehq/inputs@0.10.6";

/**
 * @param {() => void} fn
 * @param {number} delay
 * @returns {() => void}
 */
function trailingThrottle(fn, delay) {
	/** @type {ReturnType<typeof setTimeout> | undefined} */
	let timeoutId = undefined;
	return function () {
		if (!timeoutId) {
			timeoutId = setTimeout(() => {
				timeoutId = undefined;
				fn();
			}, delay);
		}
	};
}

/**
 * Make an assertion.
 *
 * @param {unknown} expression - The expression to test.
 * @param {string=} msg - The optional message to display if the assertion fails.
 * @returns {asserts expression}
 * @throws an {@link Error} if `expression` is not truthy.
 */
function assert(expression, msg = "") {
	if (!expression) throw new Error(msg);
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
 * @typedef {import("npm:@anywidget/types").AnyModel<{value: T}>} ValueModel
 */

/** @typedef {"range" | "radio" | "select" | "checkbox" | "toggle"} InputKind */

/**
 * @template T
 * @typedef {{ kind: InputKind, content?: any, options: Record<string, any>, model: T }} InputSource
 */

/**
 * @template T
 * @param {import("npm:@anywidget/types").AnyModel} model
 * @param {InputSource<string>} source
 * @returns {Promise<InputSource<ValueModel<T>>>}
 */
async function resolveInputSource(model, source) {
	return {
		kind: source.kind,
		content: source.content,
		options: omitNullish(resolveOptions(source.kind, source.options)),
		model: await model.widget_manager.get_model(
			source.model.slice("signal:".length),
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

	let Input = Inputs[kind];
	assert(Input, `\`Inputs.${kind}\` does not exist.`);

	/** @type {HTMLFormElement} */
	let input = content ? Input(content, options) : Input(options);

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

	const sync = trailingThrottle(model.save_changes.bind(model), 20);

	input.addEventListener(
		"input",
		(event) => {
			event.stopPropagation();
			model.set("value", input.value);
			sync();
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

export default {
	/** @type {import("npm:@anywidget/types").Render} */
	async render({ model, el }) {
		/** @type {Array<InputSource<string>>} */
		let entries = model.get("kind") === "form" ? model.get("inputs") : [{
			kind: model.get("kind"),
			content: model.get("content"),
			options: model.get("options"),
			model: model.get("model"),
		}];

		let controller = new AbortController();
		let root = document.createElement("div");
		{
			el.appendChild(root);
			controller.signal.addEventListener("abort", () => root.remove());
		}

		let shadow = root.attachShadow({ mode: "closed" });

		// styles
		{
			// TODO: bundle these styles into the widget
			let href =
				"https://raw.githubusercontent.com/observablehq/inputs/main/src/style.css";
			let sheet = new CSSStyleSheet();
			sheet.replaceSync(
				await fetch(href).then((res) => res.text()),
			);
			shadow.adoptedStyleSheets.push(sheet);
		}

		// inputs
		{
			let inputSources = await Promise.all(
				entries.map((entry) => resolveInputSource(model, entry)),
			);
			shadow.appendChild(
				Inputs.form(
					inputSources.map((input) =>
						createConnectedInput(input, {
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
