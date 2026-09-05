const state = { posts: [], query: "", year: "", tag: "" };

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

const escapeHTML = (s = "") =>
  s.replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));

function formatDate(iso) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric"
  }).format(new Date(iso));
}

function normalizeTag(tag) {
  return tag.replace(/^#/, "").toLowerCase();
}

function linkify(text = "") {
  let safe = escapeHTML(text);
  safe = safe.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener">$1</a>'
  );
  safe = safe.replace(
    /(^|[\s(])#([\p{L}\p{N}_-]+)/gu,
    (_, lead, tag) => `${lead}<a href="?tag=${encodeURIComponent(tag)}" class="inline-tag" data-tag="${escapeHTML(tag)}">#${escapeHTML(tag)}</a>`
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
  state.posts.forEach(post => post.tags.forEach(tag => {
    const key = normalizeTag(tag);
    tagCounts.set(key, (tagCounts.get(key) || 0) + 1);
  }));
  const tags = [...tagCounts.entries()].sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0]));

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
    if (state.tag && !post.tags.some(t => normalizeTag(t) === state.tag)) return false;
    if (!q) return true;
    const haystack = [
      post.number, post.title, post.text, post.thoughts,
      ...(post.tags || [])
    ].join(" ").toLowerCase();
    return haystack.includes(q);
  });
}

function renderCard(post) {
  const frag = template.content.cloneNode(true);
  const card = frag.querySelector(".stat-card");
  frag.querySelector(".stat-number").textContent = post.number ? `#${post.number}` : "#statstab";
  const time = frag.querySelector(".stat-date");
  time.textContent = formatDate(post.created_at);
  time.dateTime = post.created_at;
  frag.querySelector(".stat-title").textContent = post.title || "#statstab";

  const bodyText = post.thoughts || post.body || post.text || "";
  const body = frag.querySelector(".stat-text");
  body.innerHTML = linkify(bodyText.replace(/^\s*Thoughts:\s*/i, ""));

  body.addEventListener("click", (e) => {
    const a = e.target.closest("[data-tag]");
    if (!a) return;
    e.preventDefault();
    state.tag = normalizeTag(a.dataset.tag);
    syncUI();
  });

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

  const resource = frag.querySelector(".resource-link");
  if (post.external_links?.length) {
    resource.href = post.external_links[0];
  } else {
    resource.remove();
  }

  const bsky = frag.querySelector(".bsky-link");
  bsky.href = post.post_url;
  bsky.setAttribute("aria-label", `View statstab ${post.number || ""} on Bluesky`);

  card.dataset.year = post.year;
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
    chip.innerHTML = `<span>${escapeHTML(label)}</span><button type="button" aria-label="Remove ${kind} filter">×</button>`;
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
  document.querySelectorAll(".year-button").forEach(b => b.classList.toggle("active", b.dataset.year === state.year));

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
      (Number(b.number) || 0) - (Number(a.number) || 0) ||
      new Date(b.created_at) - new Date(a.created_at)
    );

    const params = new URLSearchParams(location.search);
    state.year = params.get("year") || "";
    state.tag = normalizeTag(params.get("tag") || "");
    state.query = params.get("q") || "";

    populateControls();
    syncStatus.textContent = data.generated_at
      ? `synced ${formatDate(data.generated_at)}`
      : "archive loaded";
    syncUI();
  } catch (err) {
    console.error(err);
    syncStatus.textContent = "could not load archive";
    cardsEl.innerHTML = `<div class="empty-state"><h3>Archive unavailable</h3><p>The data file could not be loaded.</p></div>`;
  }
}

searchEl.addEventListener("input", e => { state.query = e.target.value; syncUI(); });
tagSelect.addEventListener("change", e => { state.tag = e.target.value; syncUI(); });
$("#clearYear").addEventListener("click", () => { state.year = ""; syncUI(); });
$("#clearTag").addEventListener("click", () => { state.tag = ""; syncUI(); });
$("#resetFilters").addEventListener("click", resetFilters);

init();
