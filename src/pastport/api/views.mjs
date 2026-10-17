/** Safe DOM helpers; package and source text is never executable markup. */
export function node(tag, text = "", attributes = {}) {
  const item = document.createElement(tag);
  item.textContent = text;
  for (const [key, value] of Object.entries(attributes))
    item.setAttribute(key, String(value));
  return item;
}
export function button(text, action, attributes = {}) {
  const item = node("button", text, { type: "button", ...attributes });
  item.addEventListener("click", action);
  return item;
}
export function detail(label, value) {
  const item = node("p");
  item.append(
    node("strong", label + ": "),
    document.createTextNode(String(value ?? "Unavailable")),
  );
  return item;
}
export function localized(game, language, key) {
  return (
    game.locales
      .find((item) => item.locale === language)
      ?.entries.find((item) => item.key === key)?.text ?? `[${key}]`
  );
}
export function latest(run, suffix) {
  return (
    run?.artifacts
      .filter((item) => item.reference.artifact_id.endsWith(":" + suffix))
      .at(-1) ?? null
  );
}
export function safeJSON(value) {
  return JSON.stringify(value, null, 2);
}
export function labeled(text, control) {
  const wrapper = node("label", text);
  wrapper.append(control);
  return wrapper;
}
