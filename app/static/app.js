"use strict";

const SEARCH_DELAY_MS = 200;
const TOAST_MS = 4000;

const $ = (id) => document.getElementById(id);

// --- запросы к нашему API ---

async function api(method, url, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("Сервер не отвечает");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error((data && data.detail) || `Ошибка ${response.status}`);
  }
  return data;
}

// --- мелкие помощники ---

// Создаёт элемент. Текст всегда кладём через textContent, поэтому имена из Keitaro
// не могут превратиться в разметку.
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== false && value !== null && value !== undefined) node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

let toastTimer;
function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("is-error", isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, TOAST_MS);
}

// Выполняет действие по кнопке: блокирует её на время запроса и показывает ошибку.
async function run(button, action) {
  if (button) button.disabled = true;
  try {
    await action();
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

// --- автокомплит ---

// input — поле ввода, list — <ul> под ним, searchUrl — наш эндпоинт поиска,
// onSelect — что делать с выбранной записью {id, name}.
function autocomplete(input, list, searchUrl, onSelect) {
  let items = [];
  let activeIndex = -1;
  let timer;
  let requestNumber = 0;

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    activeIndex = -1;
  }

  function choose(item) {
    close();
    onSelect(item);
  }

  function render() {
    list.replaceChildren();
    if (items.length === 0) {
      list.append(el("li", { class: "autocomplete-empty", text: "Ничего не найдено" }));
    }
    items.forEach((item, index) => {
      list.append(el("li", {
        class: "autocomplete-item",
        role: "option",
        "aria-selected": String(index === activeIndex),
        // mousedown, а не click: иначе поле успеет потерять фокус и список закроется
        onmousedown: (event) => { event.preventDefault(); choose(item); },
      }, [el("span", { class: "item-id", text: `#${item.id}` }), item.name]));
    });
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  async function search() {
    const myNumber = ++requestNumber;
    try {
      const found = await api("GET", `${searchUrl}?q=${encodeURIComponent(input.value.trim())}`);
      if (myNumber !== requestNumber) return; // пришёл ответ на устаревший запрос
      items = found;
      activeIndex = -1;
      render();
    } catch (error) {
      close();
      toast(error.message, true);
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(search, SEARCH_DELAY_MS);
  });
  input.addEventListener("focus", search);
  input.addEventListener("blur", close);
  input.addEventListener("keydown", (event) => {
    if (list.hidden) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      activeIndex = (activeIndex + step + items.length) % Math.max(items.length, 1);
      render();
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      choose(items[activeIndex]);
    } else if (event.key === "Escape") {
      close();
    }
  });
}

// --- вкладки ---

function showView(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === name));
  }
  $("view-creator").hidden = name !== "creator";
  $("view-editor").hidden = name !== "editor";
}

// --- создаватор ---

let selectedOffer = null;

// Пишет значение в схему кампании, а если его ещё нет — серую подсказку.
function setBlueprint(id, value, placeholder) {
  const node = $(id);
  node.textContent = value || placeholder;
  node.classList.toggle("is-empty", !value);
}

// Схема справа от формы: показывает, что именно появится в Keitaro.
function updateBlueprint(info) {
  const name = $("create-name").value.trim();
  const prefix = info.campaign_prefix;
  const fullName = name && prefix && !name.startsWith(prefix) ? prefix + name : name;
  const geo = $("create-geo").value.split(",").map((code) => code.trim().toUpperCase()).filter(Boolean);

  setBlueprint("blueprint-name", fullName, `${prefix}название`);
  setBlueprint("blueprint-geo", geo.join(", "), "страны");
  setBlueprint("blueprint-redirect", info.geo_redirect_url, "");
  setBlueprint("blueprint-offer", selectedOffer ? `#${selectedOffer.id} ${selectedOffer.name}` : "", "оффер не выбран");
}

function setupCreator(info) {
  $("create-name-hint").textContent = info.campaign_prefix
    ? `Префикс «${info.campaign_prefix}» добавится сам.`
    : "";
  $("create-defaults").textContent =
    `домен ${info.domain || "—"} · группа ${info.group || "—"} · источник ${info.source || "—"}`;

  const offerInput = $("create-offer");
  autocomplete(offerInput, $("create-offer-list"), "/api/offers", (offer) => {
    selectedOffer = offer;
    offerInput.value = `#${offer.id} ${offer.name}`;
    updateBlueprint(info);
  });
  // Если текст поменяли руками, прежний выбор больше не действует
  offerInput.addEventListener("input", () => { selectedOffer = null; });
  $("create-form").addEventListener("input", () => updateBlueprint(info));
  updateBlueprint(info);

  $("create-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!selectedOffer) {
      toast("Выберите оффер из списка", true);
      offerInput.focus();
      return;
    }
    run($("create-submit"), async () => {
      const campaign = await api("POST", "/api/campaigns", {
        name: $("create-name").value,
        geo: $("create-geo").value,
        offer_id: selectedOffer.id,
      });
      showCreated(campaign);
      $("create-form").reset();
      selectedOffer = null;
      updateBlueprint(info);
      await loadCampaignList();
    });
  });
}

function showCreated(campaign) {
  const box = $("create-result");
  box.replaceChildren(
    el("h2", { text: "Кампания создана" }),
    el("div", { class: "result-title", text: campaign.name }),
    el("div", {}, ["Ссылка: ", el("code", { text: campaign.url || campaign.alias })]),
    el("div", { class: "hint", text: `Потоков: ${campaign.streams.length} · ID в Keitaro: ${campaign.id}` }),
    el("div", { class: "result-actions" }, [
      el("button", { class: "button button-primary", type: "button", text: "Открыть в редакторе", onclick: () => openEditor(campaign) }),
      campaign.keitaro_url
        ? el("a", { class: "button", href: campaign.keitaro_url, target: "_blank", rel: "noopener", text: "Open in KT" })
        : "",
    ]),
  );
  box.hidden = false;
}

async function loadCampaignList() {
  const list = $("campaign-list");
  const campaigns = await api("GET", "/api/campaigns");
  list.replaceChildren();
  if (campaigns.length === 0) {
    list.append(el("li", { class: "hint", text: "Пока пусто: создайте кампанию или откройте существующую в редакторе." }));
  }
  for (const campaign of campaigns) {
    list.append(el("li", {}, [
      el("button", {
        class: "link-button",
        type: "button",
        text: campaign.name,
        onclick: (event) => run(event.currentTarget, () => loadCampaign(campaign.id)),
      }),
      el("span", { class: "tag", text: campaign.created_by_app ? `создана здесь · ${campaign.geo}` : "из Keitaro" }),
    ]));
  }
}

// --- редактор ---

let currentCampaign = null;

function openEditor(campaign) {
  currentCampaign = campaign;
  showView("editor");
  renderCampaign();
}

async function loadCampaign(campaignId) {
  openEditor(await api("GET", `/api/campaigns/${campaignId}`));
}

async function fetchStreams(campaignId) {
  openEditor(await api("POST", `/api/campaigns/${campaignId}/fetch`));
  toast("Потоки обновлены из Keitaro");
}

function setupEditor() {
  const search = $("editor-search");
  autocomplete(search, $("editor-search-list"), "/api/keitaro/campaigns", (campaign) => {
    search.value = "";
    search.blur();
    run(null, async () => {
      await fetchStreams(campaign.id);
      await loadCampaignList();
    });
  });

  $("editor-fetch").addEventListener("click", (event) => {
    const hasUnpublished = currentCampaign.streams.some((stream) => stream.is_dirty);
    if (hasUnpublished && !confirm("Есть неопубликованные изменения. Fetch их сотрёт. Продолжить?")) {
      return;
    }
    run(event.currentTarget, () => fetchStreams(currentCampaign.id));
  });
}

function renderCampaign() {
  const campaign = currentCampaign;
  $("editor-campaign").hidden = false;
  $("editor-name").textContent = campaign.name;
  $("editor-meta").textContent =
    `ID ${campaign.id} · ${campaign.url || campaign.alias} · обновлено ${new Date(campaign.synced_at).toLocaleString("ru-RU")}`;

  const openLink = $("editor-open");
  openLink.hidden = !campaign.keitaro_url;
  if (campaign.keitaro_url) openLink.href = campaign.keitaro_url;

  const container = $("editor-streams");
  container.replaceChildren(...campaign.streams.map(renderStream));
  if (campaign.streams.length === 0) {
    container.append(el("p", { class: "hint", text: "В кампании нет потоков." }));
  }
}

// После любой правки сервер возвращает поток целиком — подменяем его и перерисовываем.
function replaceStream(stream) {
  currentCampaign = {
    ...currentCampaign,
    streams: currentCampaign.streams.map((item) => (item.id === stream.id ? stream : item)),
  };
  renderCampaign();
}

function streamAction(method, url, body) {
  return (event) => run(event.currentTarget, async () => replaceStream(await api(method, url, body)));
}

function renderStream(stream) {
  const base = `/api/streams/${stream.id}`;
  const heading = el("div", { class: "stream-heading" }, [
    el("span", { class: "stream-title", text: stream.name }),
    el("span", { class: "stream-meta", text: `#${stream.position} · stream_id ${stream.id}` }),
  ]);

  // Поток без офферов показываем одной строкой и ничего в нём не редактируем
  if (!stream.has_offers_schema && stream.offers.length === 0) {
    return el("div", { class: "card stream stream-plain" }, [
      el("div", { class: "stream-header" }, [heading, el("span", { class: "tag", text: "без офферов" })]),
    ]);
  }

  const actions = el("div", { class: "stream-actions" });
  if (stream.is_dirty) {
    actions.append(
      el("button", { class: "button button-primary", type: "button", text: "Push to KT", onclick: streamAction("POST", `${base}/push`) }),
      el("button", { class: "button", type: "button", text: "Cancel", onclick: streamAction("POST", `${base}/cancel`) }),
    );
  }

  const rows = stream.offers.map((offer) => renderOffer(stream, offer));
  const table = el("table", { class: "offers" }, [
    el("thead", {}, [el("tr", {}, [
      el("th", { text: "Оффер" }),
      el("th", { class: "col-share", text: "Доля" }),
      el("th", { class: "col-actions" }),
    ])]),
    el("tbody", {}, rows),
  ]);

  const hasActive = stream.offers.some((offer) => offer.state === "active");
  const footer = el("div", { class: "stream-footer" }, [renderAddOffer(stream)]);
  if (hasActive && stream.share_total !== 100) {
    footer.append(el("span", { class: "total-warning", text: `Сумма долей ${stream.share_total}% вместо 100% — поправьте закрепы` }));
  }

  heading.append(stream.is_dirty
    ? el("span", { class: "tag tag-unpublished", text: "не опубликовано" })
    : el("span", { class: "tag tag-synced", text: "как в Keitaro" }));

  // Полоса долей: каждый активный оффер занимает столько ширины, сколько у него процентов
  const shareBar = el("div", { class: "share-bar", "aria-hidden": "true" }, stream.offers
    .filter((offer) => offer.state === "active" && offer.share > 0)
    .map((offer) => {
      const segment = el("div", {
        class: `share-segment${offer.pinned ? " is-pinned" : ""}`,
        title: `${offer.offer_name}: ${offer.share}%`,
      });
      // Через свойство, а не атрибут style: атрибут запрещён нашей Content-Security-Policy
      segment.style.flex = `0 0 ${offer.share}%`;
      return segment;
    }));

  return el("div", { class: `card stream${stream.is_dirty ? " is-dirty" : ""}` }, [
    el("div", { class: "stream-header" }, [heading, actions]),
    shareBar,
    table,
    footer,
  ]);
}

function renderOffer(stream, offer) {
  const base = `/api/streams/${stream.id}/offers/${offer.id}`;
  const isActive = offer.state === "active";

  const name = el("td", { class: "offer-name" }, [
    el("span", { class: "item-id", text: `#${offer.offer_id}` }),
    offer.offer_name,
  ]);
  if (!isActive) name.append(el("span", { class: "offer-note", text: "removed" }));
  if (offer.is_new) name.append(el("span", { class: "offer-note", text: "новый" }));

  const shareCell = el("div", { class: "share-cell" });
  const shareButton = el("button", {
    class: "share-value",
    type: "button",
    text: `${offer.share}%`,
    title: "Задать долю вручную и закрепить",
    disabled: isActive ? null : "",
    onclick: () => editShare(shareCell, base, offer),
  });
  shareCell.append(shareButton);
  if (isActive) {
    shareCell.append(el("button", {
      class: "pin",
      type: "button",
      text: offer.pinned ? "закреплено" : "закрепить",
      "aria-pressed": String(offer.pinned),
      onclick: streamAction("PATCH", base, { pinned: !offer.pinned }),
    }));
  }

  const action = isActive
    ? el("button", { class: "button button-danger", type: "button", text: "Remove", onclick: streamAction("DELETE", base) })
    : el("button", { class: "button", type: "button", text: "Bring back", onclick: streamAction("POST", `${base}/restore`) });

  return el("tr", { class: isActive ? "" : "offer-removed" }, [
    name,
    el("td", { class: "col-share" }, [shareCell]),
    el("td", { class: "col-actions" }, [action]),
  ]);
}

// Клик по доле превращает её в поле ввода: Enter сохраняет и закрепляет, Esc отменяет.
function editShare(cell, base, offer) {
  const input = el("input", { class: "share-input", type: "number", min: "1", max: "100", value: String(offer.share), "aria-label": "Доля в процентах" });
  let finished = false;

  const finish = (save) => {
    if (finished) return;
    finished = true;
    const share = Number(input.value);
    if (!save) {
      renderCampaign();
      return;
    }
    run(null, async () => {
      try {
        replaceStream(await api("PATCH", base, { pinned: true, share }));
      } catch (error) {
        renderCampaign();
        throw error;
      }
    });
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") finish(true);
    if (event.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(false));

  cell.replaceChildren(input, el("span", { class: "hint", text: "% · Enter" }));
  input.focus();
  input.select();
}

function renderAddOffer(stream) {
  const listId = `add-offer-list-${stream.id}`;
  const input = el("input", { type: "text", placeholder: "Добавить оффер: название или ID", role: "combobox", "aria-expanded": "false", "aria-controls": listId, "aria-label": "Добавить оффер" });
  const list = el("ul", { id: listId, class: "autocomplete-list", role: "listbox", hidden: "" });

  autocomplete(input, list, "/api/offers", (offer) => {
    // Поле блокируется на время запроса, чтобы оффер нельзя было добавить дважды
    run(input, async () => {
      replaceStream(await api("POST", `/api/streams/${stream.id}/offers`, { offer_id: offer.id }));
    });
  });
  return el("div", { class: "autocomplete" }, [input, list]);
}

// --- запуск ---

async function start() {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => showView(tab.dataset.view));
  }

  try {
    const info = await api("GET", "/api/info");
    $("config-warning").hidden = info.keitaro_configured;
    setupCreator(info);
    setupEditor();
    await loadCampaignList();
  } catch (error) {
    toast(error.message, true);
  }
}

start();
