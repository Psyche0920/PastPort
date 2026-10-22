/** DOM view reference. The host owns dispatch, persistence, and story progress. */
export function mount(root, host) {
  let selected = null;
  let paused = false;
  let disposed = false;
  const render = () => {
    if (disposed) return;
    const state = host.readState();
    const fragment = document.createDocumentFragment();
    for (const side of ["left", "right"]) {
      const column = document.createElement("div");
      for (const pair of host.config.pairs) {
        const control = document.createElement("button");
        control.type = "button";
        control.textContent = pair[side + "_text"];
        control.disabled = paused || (side === "left" && state.matched_left_ids.includes(pair.left_id));
        control.setAttribute("aria-pressed", String(side === "left" && selected === pair.left_id));
        control.addEventListener("click", () => {
          if (paused || disposed) return;
          if (side === "left") { selected = pair.left_id; render(); return; }
          if (selected !== null) {
            const left = selected;
            selected = null;
            host.dispatch({ type: "select_pair", left_id: left, right_id: pair.right_id }).catch(host.reportError);
          }
        });
        column.append(control);
      }
      fragment.append(column);
    }
    root.replaceChildren(fragment);
  };
  const unsubscribe = host.subscribe(render);
  render();
  return {
    pause() { paused = true; selected = null; render(); },
    resume() { paused = false; render(); },
    dispose() { if (!disposed) { disposed = true; unsubscribe(); root.replaceChildren(); } },
  };
}
