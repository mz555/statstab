const state = { posts: [], query: "", year: "", tag: "" };
const SOURCE_LABELS = { x: "X", bluesky: "Bluesky", mastodon: "Mastodon" };

const $ = (sel) => document.querySelector(sel);
const cardsEl = $("#cards");
const template = $("#cardTemplate");
const searchEl = $("#search");
const tagSelect = $("#tagSelect");
const yearFilters = $("#yearFilters");
const resultCount = $("#resultCount");
const resultHeading = $("#resultHeading");
const syncStatus = $("#syncStatus");
const activeFilters = $("#activeFilters");
const emptyState = $("#emptyState");
const numberFootnote = $("#numberFootnote");

const escapeHTML = (s = "") =>
  String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));

function formatDate(iso) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric"
  }).format(new Date(iso));
}

function normalizeTag(tag) {
  return String(tag || "").replace(/^#/, "").toLowerCase();
}

function linkify(text = "") {
  let safe = escapeHTML(text);
  safe = safe.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener">$1</a>'
  );
  return safe;
}

function populateControls() {
  const years = [...new Set(state.posts.map(p => String(p.year)))].sort((a,b) => b.localeCompare(a));
  const counts = Object.fromEntries(years.map(y => [y, state.posts.filter(p => String(p.year) === y).length]));

  yearFilters.innerHTML = "";
  years.forEach(year => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "year-button";
    b.dataset.year = year;
    b.innerHTML = `<span>${year}</span><span>${counts[year]}</span>`;
    b.addEventListener("click", () => {
      state.year = state.year === year ? "" : year;
      syncUI();
    });
    yearFilters.appendChild(b);
  });

  const tagCounts = new Map();
  state.posts.forEach(post => (post.tags || []).forEach(tag => {
    const key = normalizeTag(tag);
    tagCounts.set(key, (tagCounts.get(key) || 0) + 1);
  }));

  const tags = [...tagCounts.entries()].sort((a,b) =>
    a[0].localeCompare(b[0], undefined, { sensitivity: "base" })
  );

  tagSelect.innerHTML = '<option value="">All tags</option>';
  tags.forEach(([tag, count]) => {
    const opt = document.createElement("option");
    opt.value = tag;
    opt.textContent = `#${tag} (${count})`;
    tagSelect.appendChild(opt);
  });
}

function filteredPosts() {
  const q = state.query.trim().toLowerCase();
  return state.posts.filter(post => {
    if (state.year && String(post.year) !== state.year) return false;
    if (state.tag && !(post.tags || []).some(t => normalizeTag(t) === state.tag)) return false;
    if (!q) return true;
    const sourceText = Object.values(post.sources || {}).flat().map(s => s.text || "").join(" ");
    const haystack = [
      post.display_number, post.title, post.body, sourceText, ...(post.tags || [])
    ].join(" ").toLowerCase();
    return haystack.includes(q);
  });
}

function sourceRows(post) {
  const rows = [];
  ["x", "bluesky", "mastodon"].forEach(source => {
    const items = post.sources?.[source] || [];
    items.forEach(item => rows.push({ source, ...item }));
  });
  rows.sort((a,b) => new Date(a.created_at) - new Date(b.created_at));
  return rows;
}

function renderCard(post) {
  const frag = template.content.cloneNode(true);

  const suffix = post.number_issue ? "*" : "";
  const numberText = post.display_number != null ? `#${post.display_number}${suffix}` : `#?${suffix || "*"}`;
  frag.querySelector(".stat-number").textContent = numberText;

  const time = frag.querySelector(".stat-date");
  time.textContent = formatDate(post.first_published);
  time.dateTime = post.first_published;

  frag.querySelector(".stat-title").textContent = post.title || "#statstab";
  frag.querySelector(".stat-text").innerHTML = linkify(post.body || "");

  if (post.title_duplicate && (post.previously_shared || []).length) {
    const previous = post.previously_shared
      .map(item => item.display_number != null ? `#${item.display_number}` : "an earlier post")
      .join(", ");
    const note = document.createElement("p");
    note.className = "duplicate-note";
    note.textContent = `Previously shared as ${previous}`;
    frag.querySelector(".stat-title").insertAdjacentElement("afterend", note);
  }

  const tags = frag.querySelector(".tags");
  (post.tags || []).forEach(tag => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tag";
    b.textContent = `#${tag.replace(/^#/, "")}`;
    b.addEventListener("click", () => {
      state.tag = normalizeTag(tag);
      syncUI();
    });
    tags.appendChild(b);
  });

  const resourceRow = frag.querySelector(".resource-row");
  (post.external_links || []).slice(0, 3).forEach((url, i) => {
    const a = document.createElement("a");
    a.className = "resource-link";
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = i === 0 ? "Open resource ↗" : `Resource ${i + 1} ↗`;
    resourceRow.appendChild(a);
  });
  if (!resourceRow.children.length) resourceRow.remove();

  const sourceLinks = frag.querySelector(".source-links");
  ["x", "bluesky", "mastodon"].forEach(source => {
    const items = post.sources?.[source] || [];
    if (!items.length) return;
    const a = document.createElement("a");
    a.className = `source-link source-${source}`;
    a.href = items[0].url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = SOURCE_LABELS[source];
    sourceLinks.appendChild(a);
  });

  const detailList = frag.querySelector(".source-detail-list");
  sourceRows(post).forEach(item => {
    const row = document.createElement("div");
    row.className = "source-detail";
    const historicalNumber = item.number != null ? ` · #${item.number}` : " · no number detected";
    row.innerHTML = `<b>${escapeHTML(SOURCE_LABELS[item.source])}</b><span>${escapeHTML(formatDate(item.created_at))}${escapeHTML(historicalNumber)}</span>`;
    detailList.appendChild(row);
  });

  if (!post.number_issue && sourceRows(post).length <= 1) {
    frag.querySelector(".source-details").remove();
  }

  return frag;
}

function renderActiveFilters() {
  activeFilters.innerHTML = "";
  const chips = [];
  if (state.year) chips.push(["year", state.year]);
  if (state.tag) chips.push(["tag", `#${state.tag}`]);
  if (state.query) chips.push(["query", `“${state.query}”`]);

  chips.forEach(([kind, label]) => {
    const chip = document.createElement("span");
    chip.className = "active-chip";
    chip.innerHTML = `<span>${escapeHTML(label)}</span><button type="button">×</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      if (kind === "year") state.year = "";
      if (kind === "tag") state.tag = "";
      if (kind === "query") state.query = "";
      syncUI();
    });
    activeFilters.appendChild(chip);
  });
}

function updateURL() {
  const p = new URLSearchParams();
  if (state.year) p.set("year", state.year);
  if (state.tag) p.set("tag", state.tag);
  if (state.query) p.set("q", state.query);
  history.replaceState(null, "", p.toString() ? `?${p}` : location.pathname);
}

function syncUI() {
  searchEl.value = state.query;
  tagSelect.value = state.tag;
  document.querySelectorAll(".year-button").forEach(
    b => b.classList.toggle("active", b.dataset.year === state.year)
  );

  const posts = filteredPosts();
  cardsEl.innerHTML = "";
  posts.forEach(post => cardsEl.appendChild(renderCard(post)));

  resultCount.textContent = `${posts.length} ${posts.length === 1 ? "tab" : "tabs"}`;
  resultHeading.textContent = state.year
    ? `#statstab in ${state.year}`
    : state.tag
      ? `Tagged #${state.tag}`
      : "All #statstabs";

  emptyState.hidden = posts.length !== 0;
  numberFootnote.hidden = !state.posts.some(p => p.number_issue);
  renderActiveFilters();
  updateURL();
}

function resetFilters() {
  state.query = ""; state.year = ""; state.tag = "";
  syncUI();
}

async function init() {
  try {
    const res = await fetch("data/statstabs.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.posts = (data.posts || []).sort((a,b) =>
      new Date(b.first_published) - new Date(a.first_published) ||
      (Number(b.display_number) || 0) - (Number(a.display_number) || 0)
    );

    const params = new URLSearchParams(location.search);
    state.year = params.get("year") || "";
    state.tag = normalizeTag(params.get("tag") || "");
    state.query = params.get("q") || "";

    populateControls();
    const parts = [];
    if (data.source_counts?.x) parts.push(`${data.source_counts.x} X`);
    if (data.source_counts?.bluesky) parts.push(`${data.source_counts.bluesky} Bluesky`);
    if (data.source_counts?.mastodon) parts.push(`${data.source_counts.mastodon} Mastodon`);
    syncStatus.textContent = data.generated_at
      ? `synced ${formatDate(data.generated_at)}${parts.length ? ` · ${parts.join(" · ")}` : ""}`
      : "archive loaded";
    syncUI();
  } catch (err) {
    console.error(err);
    syncStatus.textContent = "could not load archive";
  }
}

searchEl.addEventListener("input", e => { state.query = e.target.value; syncUI(); });
tagSelect.addEventListener("change", e => { state.tag = e.target.value; syncUI(); });
$("#clearYear").addEventListener("click", () => { state.year = ""; syncUI(); });
$("#clearTag").addEventListener("click", () => { state.tag = ""; syncUI(); });
$("#resetFilters").addEventListener("click", resetFilters);

init();
