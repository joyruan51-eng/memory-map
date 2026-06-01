const palette = {
  coral: "#e85d4f",
  teal: "#0f8b8d",
  sage: "#7b9b6f",
  ink: "#2c4966",
};

const state = {
  user: null,
  memories: [],
  selectedId: "",
  search: "",
  view: "all",
  color: "all",
  focusRecent: false,
  authMode: "login",
  installPrompt: null,
  needsFit: true,
  fitTimer: 0,
  markers: new Map(),
  map: null,
};

const nodes = {
  list: document.querySelector("#memoryList"),
  count: document.querySelector("#memoryCount"),
  search: document.querySelector("#memorySearch"),
  segments: document.querySelectorAll(".segment-control .segment"),
  userNameLabel: document.querySelector("#userNameLabel"),
  detailDate: document.querySelector("#detailDate"),
  detailTitle: document.querySelector("#detailTitle"),
  detailPlace: document.querySelector("#detailPlace"),
  detailStory: document.querySelector("#detailStory"),
  detailTags: document.querySelector("#detailTags"),
  photoStrip: document.querySelector("#photoStrip"),
  mapStatus: document.querySelector("#mapStatus"),
  filterPopover: document.querySelector("#filterPopover"),
  colorFilter: document.querySelector("#colorFilter"),
  focusRecent: document.querySelector("#focusRecent"),
  dialog: document.querySelector("#memoryDialog"),
  form: document.querySelector("#memoryForm"),
  dialogTitle: document.querySelector("#dialogTitle"),
  memoryId: document.querySelector("#memoryId"),
  titleInput: document.querySelector("#titleInput"),
  dateInput: document.querySelector("#dateInput"),
  placeInput: document.querySelector("#placeInput"),
  colorInput: document.querySelector("#colorInput"),
  latInput: document.querySelector("#latInput"),
  lngInput: document.querySelector("#lngInput"),
  tagsInput: document.querySelector("#tagsInput"),
  storyInput: document.querySelector("#storyInput"),
  photoInput: document.querySelector("#photoInput"),
  formPhotoPreview: document.querySelector("#formPhotoPreview"),
  toast: document.querySelector("#toast"),
  authScreen: document.querySelector("#authScreen"),
  authForm: document.querySelector("#authForm"),
  loginModeButton: document.querySelector("#loginModeButton"),
  registerModeButton: document.querySelector("#registerModeButton"),
  usernameInput: document.querySelector("#usernameInput"),
  passwordInput: document.querySelector("#passwordInput"),
  authSubmitButton: document.querySelector("#authSubmitButton"),
  authNote: document.querySelector("#authNote"),
};

boot();

async function boot() {
  initMap();
  wireEvents();
  registerServiceWorker();
  renderSignedOut();

  if (location.protocol === "file:") {
    nodes.authNote.textContent = "当前是 file:// 打开，数据库和账号功能需要通过 server.py 启动后访问 http://127.0.0.1:8765。";
    createIcons();
    return;
  }

  await restoreSession();
  createIcons();
}

function initMap() {
  const center = [32.9, 114.2];
  state.map = L.map("memoryMap", {
    zoomControl: false,
    minZoom: 3,
    maxZoom: 18,
  }).setView(center, 5);

  L.control
    .zoom({
      position: "bottomright",
    })
    .addTo(state.map);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(state.map);

  window.addEventListener("resize", () => {
    fitVisibleMemories(filteredMemories());
  });
}

function wireEvents() {
  nodes.search.addEventListener("input", (event) => {
    state.search = event.target.value.trim();
    state.needsFit = true;
    render();
  });

  nodes.segments.forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      state.needsFit = true;
      render();
    });
  });

  document.querySelector("#addMemoryButton").addEventListener("click", () => {
    if (!requireLogin()) return;
    openDialog();
  });

  document.querySelector("#filterButton").addEventListener("click", () => {
    nodes.filterPopover.hidden = !nodes.filterPopover.hidden;
  });

  document.querySelector("#exportButton").addEventListener("click", exportMemories);
  document.querySelector("#shareButton").addEventListener("click", shareSelected);
  document.querySelector("#installButton").addEventListener("click", installApp);
  document.querySelector("#resetDataButton").addEventListener("click", resetSamples);
  document.querySelector("#logoutButton").addEventListener("click", logout);
  document.querySelector("#flyButton").addEventListener("click", flyToSelected);
  document.querySelector("#editSelectedButton").addEventListener("click", () => {
    const memory = getSelectedMemory();
    if (memory) openDialog(memory);
  });
  document.querySelector("#deleteSelectedButton").addEventListener("click", deleteSelected);

  nodes.colorFilter.addEventListener("change", (event) => {
    state.color = event.target.value;
    state.needsFit = true;
    render();
  });

  nodes.focusRecent.addEventListener("change", (event) => {
    state.focusRecent = event.target.checked;
    state.needsFit = true;
    render();
  });

  nodes.photoInput.addEventListener("change", () => {
    const existingId = nodes.memoryId.value;
    const existing = state.memories.find((memory) => memory.id === existingId)?.photos || [];
    renderFormPhotoPreview(existing);
  });

  document.querySelector("#useCenterButton").addEventListener("click", () => {
    const center = state.map.getCenter();
    nodes.latInput.value = center.lat.toFixed(5);
    nodes.lngInput.value = center.lng.toFixed(5);
  });

  nodes.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (event.submitter?.value === "cancel") {
      nodes.dialog.close();
      return;
    }
    await persistFromForm();
  });

  nodes.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitAuth();
  });

  nodes.loginModeButton.addEventListener("click", () => setAuthMode("login"));
  nodes.registerModeButton.addEventListener("click", () => setAuthMode("register"));

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.installPrompt = event;
  });

  document.addEventListener("click", (event) => {
    const popover = nodes.filterPopover;
    const filterButton = document.querySelector("#filterButton");
    if (!popover.hidden && !popover.contains(event.target) && !filterButton.contains(event.target)) {
      popover.hidden = true;
    }
  });
}

async function restoreSession() {
  try {
    const result = await api("/api/me");
    state.user = result.user;
    nodes.authScreen.hidden = true;
    await loadMemoriesFromServer();
  } catch {
    renderSignedOut();
  }
}

function renderSignedOut() {
  state.user = null;
  state.memories = [];
  state.selectedId = "";
  nodes.authScreen.hidden = false;
  nodes.userNameLabel.textContent = "未登录";
  nodes.mapStatus.textContent = "等待登录";
  render();
}

async function submitAuth() {
  const username = nodes.usernameInput.value.trim();
  const password = nodes.passwordInput.value;
  const endpoint = state.authMode === "register" ? "/api/register" : "/api/login";

  nodes.authSubmitButton.disabled = true;
  nodes.authSubmitButton.textContent = state.authMode === "register" ? "注册中" : "登录中";

  try {
    const result = await api(endpoint, {
      method: "POST",
      body: {
        username,
        password,
      },
    });
    state.user = result.user;
    nodes.authScreen.hidden = true;
    nodes.passwordInput.value = "";
    showToast(state.authMode === "register" ? "注册成功" : "已登录");
    await loadMemoriesFromServer();
  } catch (error) {
    nodes.authNote.textContent = error.message;
  } finally {
    nodes.authSubmitButton.disabled = false;
    nodes.authSubmitButton.textContent = state.authMode === "register" ? "注册并进入" : "登录";
  }
}

function setAuthMode(mode) {
  state.authMode = mode;
  const isRegister = mode === "register";
  nodes.loginModeButton.classList.toggle("active", !isRegister);
  nodes.registerModeButton.classList.toggle("active", isRegister);
  nodes.authSubmitButton.textContent = isRegister ? "注册并进入" : "登录";
  nodes.authNote.textContent = isRegister
    ? "新账号会自动生成一组示例记忆，之后每个账号的数据互不混用。"
    : "账号会话保存在安全 Cookie 中，同一服务可支持多人分别登录。";
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST" });
  } catch {
    // Local sign-out should still clear the UI if the session already expired.
  }
  renderSignedOut();
  showToast("已退出");
}

async function loadMemoriesFromServer() {
  const result = await api("/api/memories");
  state.memories = result.memories;
  state.selectedId = state.memories[0]?.id ?? "";
  state.needsFit = true;
  nodes.userNameLabel.textContent = state.user ? `账号：${state.user.username}` : "未登录";
  render();
}

async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  };

  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  const response = await fetch(path, init);
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};

  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }

  return data;
}

function filteredMemories() {
  let memories = [...state.memories];
  const query = state.search.toLowerCase();

  if (query) {
    memories = memories.filter((memory) => {
      const haystack = [
        memory.title,
        memory.date,
        memory.place,
        memory.story,
        ...(memory.tags || []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }

  if (state.color !== "all") {
    memories = memories.filter((memory) => memory.color === state.color);
  }

  if (state.focusRecent) {
    memories = memories.filter((memory) => Number.parseInt(memory.date, 10) >= 2021);
  }

  if (state.view === "timeline") {
    memories.sort((a, b) => numericDate(b.date) - numericDate(a.date));
  }

  if (state.view === "place") {
    memories.sort((a, b) => a.place.localeCompare(b.place, "zh-CN"));
  }

  return memories;
}

function numericDate(date) {
  return Number(String(date).replace(/[^\d]/g, "").padEnd(6, "0"));
}

function render() {
  const memories = filteredMemories();
  if (!memories.some((memory) => memory.id === state.selectedId)) {
    state.selectedId = memories[0]?.id ?? state.memories[0]?.id ?? "";
  }

  renderSegments();
  renderList(memories);
  renderMarkers(memories);
  if (state.needsFit) {
    fitVisibleMemories(memories);
    state.needsFit = false;
  }
  renderDetail();
  nodes.count.textContent = `${memories.length} 条记忆`;
  nodes.mapStatus.textContent = statusText(memories.length);
  createIcons();
}

function renderSegments() {
  nodes.segments.forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function renderList(memories) {
  nodes.list.innerHTML = "";

  if (!state.user) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "登录后显示你的记忆";
    nodes.list.append(empty);
    return;
  }

  if (!memories.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "没有匹配的记忆";
    nodes.list.append(empty);
    return;
  }

  const fragment = document.createDocumentFragment();

  memories.forEach((memory) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `memory-item ${memory.id === state.selectedId ? "active" : ""}`;
    item.addEventListener("click", () => selectMemory(memory.id, true));

    const pin = document.createElement("span");
    pin.className = "timeline-pin";
    pin.innerHTML = `<span class="${memory.color}"></span>`;

    const copy = document.createElement("span");
    copy.className = "memory-copy";
    copy.innerHTML = `
      <span class="memory-date">${escapeHtml(memory.date)} ${escapeHtml(memory.place)}</span>
      <strong>${escapeHtml(memory.title)}</strong>
      <p>${escapeHtml(memory.story)}</p>
    `;

    item.append(pin, copy);
    fragment.append(item);
  });

  nodes.list.append(fragment);
}

function renderMarkers(memories) {
  const visibleIds = new Set(memories.map((memory) => memory.id));

  state.markers.forEach((marker, id) => {
    if (!visibleIds.has(id)) {
      marker.remove();
      state.markers.delete(id);
    }
  });

  memories.forEach((memory, index) => {
    let marker = state.markers.get(memory.id);
    const icon = makeMarkerIcon(memory, index + 1);

    if (!marker) {
      marker = L.marker([memory.lat, memory.lng], { icon }).addTo(state.map);
      marker.on("click", () => selectMemory(memory.id, false));
      state.markers.set(memory.id, marker);
    } else {
      marker.setLatLng([memory.lat, memory.lng]);
      marker.setIcon(icon);
    }
  });
}

function fitVisibleMemories(memories) {
  window.clearTimeout(state.fitTimer);
  state.fitTimer = window.setTimeout(() => {
    state.map.invalidateSize();

    if (memories.length > 1) {
      const bounds = L.latLngBounds(memories.map((memory) => [memory.lat, memory.lng]));
      if (bounds.isValid()) {
        const compact = window.matchMedia("(max-width: 760px)").matches;
        state.map.fitBounds(bounds.pad(compact ? 0.08 : 0.24), {
          animate: !compact,
          duration: compact ? 0 : 0.6,
          paddingTopLeft: compact ? [24, 126] : [36, 36],
          paddingBottomRight: compact ? [24, 46] : [36, 36],
          maxZoom: compact ? 3 : 6,
        });

        if (compact) {
          const center = bounds.getCenter();
          window.setTimeout(() => {
            state.map.setView([center.lat + 13, center.lng], 3, { animate: false });
          }, 80);
        }
      }
    } else if (memories.length === 1) {
      state.map.setView([memories[0].lat, memories[0].lng], 11, { animate: true });
    }
  }, 160);
}

function makeMarkerIcon(memory, number) {
  return L.divIcon({
    className: "",
    iconSize: [31, 31],
    iconAnchor: [8, 28],
    popupAnchor: [5, -24],
    html: `<div class="memory-marker ${memory.color}" style="background:${palette[memory.color] || palette.teal}"><span>${number}</span></div>`,
  });
}

function renderDetail() {
  const memory = getSelectedMemory();
  nodes.detailTags.innerHTML = "";
  nodes.photoStrip.innerHTML = "";

  if (!memory) {
    nodes.detailDate.textContent = state.user ? "还没有记忆" : "请先登录";
    nodes.detailTitle.textContent = state.user ? "新增第一条记忆" : "账号登录";
    nodes.detailPlace.textContent = state.user ? "点击 + 开始记录" : "多人数据会写入 SQLite";
    nodes.detailStory.textContent = state.user
      ? "你的地图会按当前账号单独保存。"
      : "登录或注册后，每个账号只会看到自己的记忆。";
    return;
  }

  nodes.detailDate.textContent = memory.date;
  nodes.detailTitle.textContent = memory.title;
  nodes.detailPlace.textContent = memory.place;
  nodes.detailStory.textContent = memory.story;

  memory.tags.forEach((tag) => {
    const pill = document.createElement("span");
    pill.className = "tag";
    pill.textContent = tag;
    nodes.detailTags.append(pill);
  });

  if (memory.photos?.length) {
    memory.photos.slice(0, 6).forEach((src, index) => {
      const chip = document.createElement("span");
      chip.className = "photo-chip";
      const img = document.createElement("img");
      img.src = src;
      img.alt = `${memory.title} 照片 ${index + 1}`;
      chip.append(img);
      nodes.photoStrip.append(chip);
    });
    return;
  }

  photoGradients(memory).forEach((gradient) => {
    const chip = document.createElement("span");
    chip.className = "photo-chip";
    chip.style.background = gradient;
    nodes.photoStrip.append(chip);
  });
}

function photoGradients(memory) {
  const base = palette[memory.color] || palette.teal;
  return [
    `linear-gradient(145deg, ${base} 0%, rgba(255,255,255,.2) 44%, #263f3a 100%)`,
    `radial-gradient(circle at 28% 30%, rgba(255,255,255,.92), transparent 18%), linear-gradient(150deg, #eaf2ee, ${base})`,
    `linear-gradient(135deg, rgba(20,33,31,.88), transparent 42%), linear-gradient(45deg, ${base}, #f2f7f4)`,
  ];
}

function selectMemory(id, shouldFly) {
  state.selectedId = id;
  render();
  if (shouldFly) flyToSelected();
}

function getSelectedMemory() {
  return state.memories.find((memory) => memory.id === state.selectedId) || null;
}

function flyToSelected() {
  const memory = getSelectedMemory();
  if (!memory) return;
  state.map.flyTo([memory.lat, memory.lng], 12, {
    duration: 0.9,
  });
}

function openDialog(memory = null) {
  const isEditing = Boolean(memory);
  nodes.dialogTitle.textContent = isEditing ? "编辑记忆" : "新增记忆";
  nodes.memoryId.value = memory?.id || "";
  nodes.titleInput.value = memory?.title || "";
  nodes.dateInput.value =
    memory?.date || `${new Date().getFullYear()}.${String(new Date().getMonth() + 1).padStart(2, "0")}`;
  nodes.placeInput.value = memory?.place || "";
  nodes.colorInput.value = memory?.color || "coral";
  nodes.latInput.value = memory?.lat ?? state.map.getCenter().lat.toFixed(5);
  nodes.lngInput.value = memory?.lng ?? state.map.getCenter().lng.toFixed(5);
  nodes.tagsInput.value = memory?.tags?.join(", ") || "";
  nodes.storyInput.value = memory?.story || "";
  nodes.photoInput.value = "";
  renderFormPhotoPreview(memory?.photos || []);
  nodes.dialog.showModal();
  nodes.titleInput.focus();
  createIcons();
}

async function persistFromForm() {
  const existingId = nodes.memoryId.value;
  const existingMemory = state.memories.find((item) => item.id === existingId);
  const memory = {
    id: existingId || makeId(nodes.titleInput.value),
    title: nodes.titleInput.value.trim(),
    date: nodes.dateInput.value.trim(),
    place: nodes.placeInput.value.trim(),
    color: nodes.colorInput.value,
    lat: Number.parseFloat(nodes.latInput.value),
    lng: Number.parseFloat(nodes.lngInput.value),
    tags: nodes.tagsInput.value
      .split(/[,，]/)
      .map((tag) => tag.trim())
      .filter(Boolean),
    story: nodes.storyInput.value.trim(),
    photos: existingMemory?.photos || [],
    newPhotos: await readSelectedPhotos(),
  };

  if (!Number.isFinite(memory.lat) || !Number.isFinite(memory.lng)) {
    showToast("坐标格式需要是数字");
    return;
  }

  try {
    const result = await api(existingId ? `/api/memories/${encodeURIComponent(existingId)}` : "/api/memories", {
      method: existingId ? "PUT" : "POST",
      body: memory,
    });

    const currentIndex = state.memories.findIndex((item) => item.id === result.memory.id);
    if (currentIndex >= 0) {
      state.memories[currentIndex] = result.memory;
    } else {
      state.memories.unshift(result.memory);
    }

    state.selectedId = result.memory.id;
    state.needsFit = true;
    nodes.dialog.close();
    render();
    flyToSelected();
    showToast("已保存到数据库");
  } catch (error) {
    showToast(error.message);
  }
}

async function readSelectedPhotos() {
  const files = Array.from(nodes.photoInput.files || []);
  const accepted = [];

  if (files.length > 8) {
    showToast("一次最多上传 8 张照片");
  }

  for (const file of files.slice(0, 8)) {
    if (!file.type.startsWith("image/")) {
      showToast("只能上传图片文件");
      continue;
    }

    if (file.size > 5 * 1024 * 1024) {
      showToast(`${file.name} 超过 5MB`);
      continue;
    }

    accepted.push({
      name: file.name,
      type: file.type,
      dataUrl: await fileToDataUrl(file),
    });
  }

  return accepted;
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result));
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsDataURL(file);
  });
}

function renderFormPhotoPreview(existingPhotos = []) {
  nodes.formPhotoPreview.innerHTML = "";
  const fragment = document.createDocumentFragment();

  existingPhotos.slice(0, 8).forEach((src, index) => {
    fragment.append(makeFormPhotoThumb(src, `已有照片 ${index + 1}`));
  });

  Array.from(nodes.photoInput.files || [])
    .slice(0, 8)
    .forEach((file, index) => {
      if (!file.type.startsWith("image/")) return;
      fragment.append(makeFormPhotoThumb(URL.createObjectURL(file), `待上传照片 ${index + 1}`));
    });

  if (!fragment.childNodes.length) {
    const empty = document.createElement("p");
    empty.className = "form-photo-empty";
    empty.textContent = "还没有照片，选择图片后会随记忆一起保存。";
    fragment.append(empty);
  }

  nodes.formPhotoPreview.append(fragment);
}

function makeFormPhotoThumb(src, alt) {
  const thumb = document.createElement("span");
  thumb.className = "form-photo-thumb";
  const img = document.createElement("img");
  img.src = src;
  img.alt = alt;
  thumb.append(img);
  return thumb;
}

async function deleteSelected() {
  const memory = getSelectedMemory();
  if (!memory || !confirm(`删除「${memory.title}」？`)) return;

  try {
    await api(`/api/memories/${encodeURIComponent(memory.id)}`, { method: "DELETE" });
    state.memories = state.memories.filter((item) => item.id !== memory.id);
    state.selectedId = state.memories[0]?.id ?? "";
    state.needsFit = true;
    render();
    showToast("已删除");
  } catch (error) {
    showToast(error.message);
  }
}

function makeId(value) {
  const seed = value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^\w\u4e00-\u9fa5-]/g, "");
  return `${seed || "memory"}-${Date.now().toString(36)}`;
}

async function resetSamples() {
  if (!requireLogin()) return;
  try {
    const result = await api("/api/memories/reset", { method: "POST" });
    state.memories = result.memories;
    state.selectedId = state.memories[0]?.id ?? "";
    state.needsFit = true;
    render();
    showToast("样例已重置");
  } catch (error) {
    showToast(error.message);
  }
}

function exportMemories() {
  if (!requireLogin()) return;
  const blob = new Blob([JSON.stringify(state.memories, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "memory-map.json";
  link.click();
  URL.revokeObjectURL(url);
  showToast("已导出 JSON");
}

async function shareSelected() {
  const memory = getSelectedMemory();
  if (!memory) {
    requireLogin();
    return;
  }
  const text = `${memory.title}｜${memory.date} ${memory.place}\n${memory.story}`;

  try {
    if (navigator.share) {
      await navigator.share({
        title: memory.title,
        text,
      });
    } else {
      await navigator.clipboard.writeText(text);
      showToast("已复制分享文本");
    }
  } catch {
    showToast("分享已取消");
  }
}

async function installApp() {
  if (state.installPrompt) {
    state.installPrompt.prompt();
    await state.installPrompt.userChoice;
    state.installPrompt = null;
    return;
  }

  showToast("手机浏览器菜单里可选择“添加到主屏幕”");
}

function registerServiceWorker() {
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("./sw.js").catch(() => {
      // The app remains usable without offline caching.
    });
  }
}

function requireLogin() {
  if (state.user) return true;
  nodes.authScreen.hidden = false;
  showToast("请先登录");
  return false;
}

function statusText(count) {
  if (!state.user) return "等待登录";
  if (state.search) return `找到 ${count} 条匹配记忆`;
  if (state.color !== "all" || state.focusRecent) return `筛选后显示 ${count} 条记忆`;
  return "已显示全部记忆";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  nodes.toast.textContent = message;
  nodes.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    nodes.toast.classList.remove("show");
  }, 1800);
}

function createIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}
