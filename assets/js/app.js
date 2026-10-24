// Filtering for the home page. Everything is rendered by Hugo; this only shows and hides rows.
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const search = $("#q");
  if (!search) return; // text pages have no list

  const groups = $$(".group");
  const cats = $$(".cat");
  const chips = $("#chips");
  const status = $("#status");
  const empty = $("#empty");
  const title = $("#title");
  const lede = $("#lede");
  const total = $$(".item").length;
  const state = { cat: "all", sub: "", q: "", filter: "all" };

  const readHash = () => {
    const id = decodeURIComponent(location.hash.slice(1));
    return groups.some((g) => g.dataset.cat === id) ? id : "all";
  };

  function renderChips(group) {
    const subs = group ? group.dataset.subs.split("|").filter(Boolean) : [];
    if (subs.length < 2) { chips.hidden = true; chips.innerHTML = ""; return; }
    const counts = {};
    $$(".item", group).forEach((li) => { counts[li.dataset.sub] = (counts[li.dataset.sub] || 0) + 1; });
    const button = (value, label, n) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.dataset.sub = value;
      b.setAttribute("aria-pressed", String(state.sub === value));
      b.textContent = label;
      if (n) { const s = document.createElement("span"); s.className = "n"; s.textContent = n; b.append(s); }
      return b;
    };
    chips.replaceChildren(button("", "All"), ...subs.filter((s) => counts[s]).map((s) => button(s, s, counts[s])));
    chips.hidden = false;
  }

  function apply() {
    const terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    let shown = 0;
    groups.forEach((g) => {
      const inCat = state.cat === "all" || g.dataset.cat === state.cat;
      let n = 0;
      $$(".item", g).forEach((li) => {
        const ok = inCat &&
          (!state.sub || li.dataset.sub === state.sub) &&
          (state.filter === "all" || li.hasAttribute("data-" + state.filter)) &&
          terms.every((t) => li.dataset.s.includes(t));
        li.hidden = !ok;
        if (ok) n++;
      });
      $$(".subgroup", g).forEach((sg) => {
        const visible = $$(".item", sg).filter((li) => !li.hidden).length;
        sg.hidden = visible === 0;
        const c = $(".subcount", sg);
        if (c) c.textContent = visible;
      });
      g.hidden = n === 0;
      const count = $(".count", g);
      if (count) count.textContent = n;
      shown += n;
    });

    const group = groups.find((g) => g.dataset.cat === state.cat);
    title.textContent = state.q ? `Results for “${state.q}”` : group ? group.dataset.name : "All resources";
    lede.textContent = group && !state.q ? group.dataset.desc : lede.dataset.default;
    const narrowed = state.q || state.sub || state.filter !== "all" || state.cat !== "all";
    status.textContent = narrowed && shown ? `Showing ${shown} of ${total}` : "";
    empty.hidden = shown > 0;
    cats.forEach((a) => a.setAttribute("aria-current", String(a.dataset.cat === state.cat)));
  }

  function setCategory(cat) {
    state.cat = cat;
    state.sub = "";
    renderChips(groups.find((g) => g.dataset.cat === cat));
    apply();
  }

  window.addEventListener("hashchange", () => { setCategory(readHash()); window.scrollTo({ top: 0 }); });

  search.addEventListener("input", () => { state.q = search.value.trim(); apply(); });
  search.addEventListener("keydown", (e) => { if (e.key === "Escape") { search.value = ""; state.q = ""; apply(); search.blur(); } });

  chips.addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    state.sub = b.dataset.sub;
    $$(".chip", chips).forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
    apply();
  });

  $$(".segmented button").forEach((b) => b.addEventListener("click", () => {
    state.filter = b.dataset.filter;
    $$(".segmented button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    apply();
  }));

  document.addEventListener("keydown", (e) => {
    const typing = /^(input|textarea|select)$/i.test(document.activeElement?.tagName || "");
    if ((e.key === "/" && !typing) || (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey))) {
      e.preventDefault();
      search.focus();
      search.select();
    }
  });

  setCategory(readHash());
})();
