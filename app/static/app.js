"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { user: null, csrf: "", today: "", status: "all", search: "", offset: 0, limit: 10, orders: [], request: 0, page: "orders" };
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const dateLabel = value => value ? new Date(`${value}T12:00:00`).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
const moneyLabel = value => Number(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
let toastTimer, confirmAction, reportRequest = 0;

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message; node.hidden = false; node.classList.toggle("error", error);
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { node.hidden = true; }, 5000);
}

function showLogin() {
  state.user = null; state.csrf = ""; state.request++;
  $("#workspace").hidden = true; $("#login-screen").hidden = false;
  $$("dialog[open]").forEach(dialog => dialog.close());
}

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin", ...options,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf, ...options.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Не удалось выполнить запрос" }));
    if (response.status === 401 && path !== "/auth/login") showLogin();
    throw new Error(typeof error.detail === "string" ? error.detail : "Проверьте введённые данные");
  }
  return response.status === 204 ? null : response.json();
}

async function submit(form, errorSelector, callback) {
  const button = $("button[type=submit]", form);
  $(errorSelector).textContent = ""; button.disabled = true;
  try { await callback(); } catch (error) { $(errorSelector).textContent = error.message; }
  finally { button.disabled = false; }
}

async function enterWorkspace(data) {
  Object.assign(state, { user: data.user, csrf: data.csrf_token, today: data.today, offset: 0 });
  $("#login-screen").hidden = true; $("#workspace").hidden = false;
  $("#profile-name").textContent = state.user.full_name;
  $("#profile-role").textContent = state.user.role === "admin" ? "Администратор" : "Оператор";
  $$(".admin-only").forEach(node => { node.hidden = state.user.role !== "admin"; });
  $("#current-date").textContent = new Date(`${state.today}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  $("#revenue-form [name=start]").value = `${state.today.slice(0, 8)}01`;
  $("#revenue-form [name=end]").value = state.today;
  await navigate("orders");
}

async function navigate(page) {
  if (page === "users" && state.user.role !== "admin") return;
  state.page = page;
  $$(".page").forEach(node => { node.hidden = node.id !== `page-${page}`; });
  $$("[data-page]").forEach(button => button.classList.toggle("active", button.dataset.page === page));
  try {
    if (page === "orders") await refreshOrders();
    if (page === "users") await loadUsers();
    if (page === "revenue") await loadRevenue();
  } catch (error) { toast(error.message, true); }
}

async function loadDashboard() {
  const data = await api("/dashboard");
  state.today = data.today;
  ["pending", "overdue", "completed"].forEach(key => { $(`#stat-${key}`).textContent = data[key]; });
  $("#stat-revenue").textContent = moneyLabel(data.month_revenue);
}

function statusBadge(order) {
  const kind = order.is_completed ? "completed" : order.is_overdue ? "overdue" : "pending";
  return `<span class="badge ${kind}">${{ completed: "Выполнен", overdue: "Просрочен", pending: "В работе" }[kind]}</span>`;
}

async function loadOrders() {
  const request = ++state.request;
  const params = new URLSearchParams({ status: state.status, search: state.search, offset: state.offset, limit: state.limit });
  const data = await api(`/orders?${params}`);
  if (request !== state.request || !state.user) return;
  if (data.total && state.offset >= data.total) { state.offset = Math.floor((data.total - 1) / state.limit) * state.limit; return loadOrders(); }
  state.orders = data.items;
  $("#order-count").textContent = data.total;
  $("#order-empty").hidden = data.total !== 0;
  $("#order-rows").innerHTML = data.items.map(order => `<tr>
    <td><span class="order-number">№ ${order.id}</span><strong>${escapeHTML(order.item_name)}</strong><small>${escapeHTML(order.brand)}</small></td>
    <td>${escapeHTML(order.owner_name)}<small>${escapeHTML(order.owner_phone)}</small></td>
    <td>Приёмка: ${dateLabel(order.received_on)}<div class="deadline ${order.is_overdue ? "late" : ""}">Выдача: ${dateLabel(order.planned_on)}</div>${order.completed_on ? `<small>Выполнен: ${dateLabel(order.completed_on)}</small>` : ""}</td>
    <td><span class="cost">${moneyLabel(order.cost)}</span></td>
    <td>${statusBadge(order)}</td>
    <td><div class="row-actions"><button class="action-button" data-edit="${order.id}" aria-label="Редактировать заказ ${order.id}">Изменить</button>
    ${order.is_completed ? `<button class="action-button" data-reopen="${order.id}" aria-label="Вернуть в работу заказ ${order.id}">В работу</button>` : `<button class="action-button" data-complete="${order.id}" aria-label="Завершить заказ ${order.id}">Завершить</button>`}
    ${state.user.role === "admin" ? `<button class="action-button danger" data-delete="${order.id}" aria-label="Удалить заказ ${order.id}">Удалить</button>` : ""}</div></td></tr>`).join("");
  $("#page-info").textContent = data.total ? `${state.offset + 1}–${state.offset + data.items.length} из ${data.total} заказов` : "0 заказов";
  $("#prev-page").disabled = state.offset === 0;
  $("#next-page").disabled = state.offset + state.limit >= data.total;
}

async function refreshOrders() { await Promise.all([loadDashboard(), loadOrders()]); }

function openOrder(order = null) {
  const form = $("#order-form"); form.reset(); $("#order-error").textContent = "";
  $("#order-title").textContent = order ? `Заказ № ${order.id}` : "Новый заказ";
  for (const name of ["id", "item_name", "brand", "owner_name", "owner_phone", "cost", "received_on", "planned_on"]) {
    form.elements.namedItem(name).value = order?.[name] ?? (["received_on", "planned_on"].includes(name) ? state.today : "");
  }
  form.elements.received_on.max = state.today;
  form.elements.planned_on.min = form.elements.received_on.value;
  $("#order-dialog").showModal();
}

function confirmDialog(title, message, action, button = "Подтвердить") {
  $("#confirm-title").textContent = title; $("#confirm-message").textContent = message;
  $("#confirm-error").textContent = ""; $("#confirm-submit").textContent = button;
  confirmAction = action; $("#confirm-dialog").showModal();
}

async function loadRevenue() {
  const request = ++reportRequest;
  const form = $("#revenue-form");
  $("#report-result").hidden = true;
  const params = new URLSearchParams(new FormData(form));
  const report = await api(`/reports/revenue?${params}`);
  if (request !== reportRequest || !state.user) return;
  $("#report-total").textContent = moneyLabel(report.total);
  $("#report-count").textContent = report.count;
  $("#report-rows").innerHTML = report.items.length ? report.items.map(order => `<tr><td><span class="order-number">№ ${order.id}</span><strong>${escapeHTML(order.item_name)}</strong><small>${escapeHTML(order.brand)}</small></td><td>${escapeHTML(order.owner_name)}</td><td>${dateLabel(order.completed_on)}</td><td><span class="cost">${moneyLabel(order.cost)}</span></td></tr>`).join("") : '<tr><td colspan="4" class="empty">За этот период выполненных заказов нет.</td></tr>';
  $("#report-result").hidden = false;
}

async function loadUsers() {
  const users = await api("/users");
  $("#user-rows").innerHTML = users.map(user => `<tr><td><strong>${escapeHTML(user.full_name)}</strong></td><td>${escapeHTML(user.username)}</td><td>${user.role === "admin" ? "Администратор" : "Оператор"}</td><td><span class="badge ${user.is_active ? "completed" : "overdue"}">${user.is_active ? "Активен" : "Отключён"}</span></td><td>${user.id === state.user.id ? '<span class="muted">Это вы</span>' : `<button class="secondary" data-user="${user.id}" data-active="${user.is_active}">${user.is_active ? "Отключить" : "Включить"}</button>`}</td></tr>`).join("");
}

$("#login-form").addEventListener("submit", event => {
  event.preventDefault();
  submit(event.target, "#login-error", async () => {
    const data = await api("/auth/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
    event.target.reset(); await enterWorkspace(data);
  });
});
$("#logout").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); showLogin(); }
  catch (error) { toast(error.message, true); }
});
$$("[data-page]").forEach(button => button.addEventListener("click", () => navigate(button.dataset.page)));
$$("[data-close]").forEach(button => button.addEventListener("click", () => $(`#${button.dataset.close}`).close()));
$("#add-order").addEventListener("click", () => openOrder());
$("#order-form [name=received_on]").addEventListener("change", event => { $("#order-form [name=planned_on]").min = event.target.value; });
$$("[data-status]").forEach(button => button.addEventListener("click", async () => {
  state.status = button.dataset.status; state.offset = 0;
  $$("[data-status]").forEach(item => item.classList.toggle("selected", item === button));
  try { await loadOrders(); } catch (error) { toast(error.message, true); }
}));
$("#search-form").addEventListener("submit", async event => {
  event.preventDefault(); state.search = $("#search").value.trim(); state.offset = 0;
  try { await loadOrders(); } catch (error) { toast(error.message, true); }
});
for (const [selector, direction] of [["#prev-page", -1], ["#next-page", 1]]) {
  $(selector).addEventListener("click", async () => {
    state.offset = Math.max(0, state.offset + direction * state.limit);
    try { await loadOrders(); } catch (error) { toast(error.message, true); }
  });
}
$("#order-rows").addEventListener("click", event => {
  const button = event.target.closest("button"); if (!button) return;
  const id = Number(Object.values(button.dataset)[0]);
  const order = state.orders.find(item => item.id === id); if (!order) return;
  if (button.dataset.edit) openOrder(order);
  if (button.dataset.complete) {
    const form = $("#complete-form"); form.elements.id.value = id;
    form.elements.completed_on.value = state.today; form.elements.completed_on.max = state.today;
    form.elements.completed_on.min = order.received_on;
    $("#complete-error").textContent = ""; $("#complete-dialog").showModal();
  }
  if (button.dataset.delete) confirmDialog("Удалить заказ?", `Заказ № ${id} будет удалён без возможности восстановления.`, async () => {
    await api(`/orders/${id}`, { method: "DELETE" }); await refreshOrders(); toast("Заказ удалён");
  }, "Удалить заказ");
  if (button.dataset.reopen) confirmDialog("Вернуть заказ в работу?", "Заказ перестанет учитываться в доходе до повторного выполнения.", async () => {
    await api(`/orders/${id}/reopen`, { method: "POST" }); await refreshOrders(); toast("Заказ возвращён в работу");
  }, "Вернуть в работу");
});
$("#order-form").addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, "#order-error", async () => {
    const data = Object.fromEntries(new FormData(event.target)), id = data.id; delete data.id;
    await api(`/orders${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
    $("#order-dialog").close(); await refreshOrders(); toast(id ? "Заказ обновлён" : "Заказ создан");
  });
});
$("#complete-form").addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, "#complete-error", async () => {
    const { id, completed_on } = Object.fromEntries(new FormData(event.target));
    await api(`/orders/${id}/complete`, { method: "POST", body: JSON.stringify({ completed_on }) });
    $("#complete-dialog").close(); await refreshOrders(); toast("Заказ выполнен и учтён в доходе");
  });
});
$("#confirm-form").addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, "#confirm-error", async () => {
    await confirmAction(); $("#confirm-dialog").close();
  });
});
$("#revenue-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = $("button", event.target); button.disabled = true;
  try { await loadRevenue(); } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
});
$("#add-user").addEventListener("click", () => {
  $("#user-form").reset(); $("#user-error").textContent = ""; $("#user-dialog").showModal();
});
$("#user-form").addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, "#user-error", async () => {
    await api("/users", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
    $("#user-dialog").close(); await loadUsers(); toast("Сотрудник добавлен");
  });
});
$("#user-rows").addEventListener("click", event => {
  const button = event.target.closest("[data-user]"); if (!button) return;
  const active = button.dataset.active === "true";
  confirmDialog(active ? "Отключить сотрудника?" : "Включить сотрудника?", active ? "Все сеансы сотрудника будут завершены. Его заказы сохранятся." : "Сотрудник сможет снова войти со своим паролем.", async () => {
    await api(`/users/${button.dataset.user}`, { method: "PATCH", body: JSON.stringify({ is_active: !active }) });
    await loadUsers(); toast("Доступ сотрудника обновлён");
  });
});
(async () => {
  try { await enterWorkspace(await api("/auth/me")); }
  catch (error) { showLogin(); if (error.message !== "Войдите в систему") $("#login-error").textContent = error.message; }
})();
