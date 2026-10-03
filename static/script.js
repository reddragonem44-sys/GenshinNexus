const characterSelect = document.getElementById("characterSelect");
const profileLoading = document.getElementById("profileLoading");
const characterImage = document.getElementById("characterImage");
const imageFallback = document.getElementById("imageFallback");
const characterName = document.getElementById("characterName");
const characterRegion = document.getElementById("characterRegion");
const characterDescription = document.getElementById("characterDescription");
const elementValue = document.getElementById("elementValue");
const weaponValue = document.getElementById("weaponValue");
const rarityValue = document.getElementById("rarityValue");
const profileMaterials = document.getElementById("profileMaterials");
const catalogPanel = document.getElementById("catalogPanel");
const catalogTitle = document.getElementById("catalogTitle");
const catalogDescription = document.getElementById("catalogDescription");
const catalogSearch = document.getElementById("catalogSearch");
const catalogStatus = document.getElementById("catalogStatus");
const catalogResults = document.getElementById("catalogResults");
const archiveSearch = document.getElementById("archiveSearch");
const characterGrid = document.getElementById("characterGrid");
const archiveStatus = document.getElementById("archiveStatus");
const archiveCount = document.getElementById("archiveCount");
const bannersPanel = document.getElementById("bannersPanel");
const theaterPanel = document.getElementById("theaterPanel");
const abyssPanel = document.getElementById("abyssPanel");
const abyssScrim = document.getElementById("abyssScrim");
const abyssFloorSelector = document.getElementById("abyssFloorSelector");
const abyssDataStatus = document.getElementById("abyssDataStatus");
const abyssTeamGrid = document.getElementById("abyssTeamGrid");
const theaterSeason = document.getElementById("theaterSeason");
const theaterStatus = document.getElementById("theaterStatus");
const theaterLocks = document.getElementById("theaterLocks");
const theaterOpeningCast = document.getElementById("theaterOpeningCast");
const theaterGuests = document.getElementById("theaterGuests");
const theaterActs = document.getElementById("theaterActs");
const velocityAlert = document.getElementById("velocityAlert");
const velocityChallengeLink = document.getElementById("velocityChallengeLink");
const velocityAlertClose = document.getElementById("velocityAlertClose");
const bannerPhases = document.getElementById("bannerPhases");
const bannerCountdown = document.getElementById("bannerCountdown");
const bannerCountdownLabel = document.getElementById("bannerCountdownLabel");
const bannerUpdated = document.getElementById("bannerUpdated");
const abyssCycle = document.getElementById("abyssCycle");
const abyssBlessingName = document.getElementById("abyssBlessingName");
const abyssBlessingText = document.getElementById("abyssBlessingText");
const leylineGrid = document.getElementById("leylineGrid");
const chamberGrid = document.getElementById("chamberGrid");

const generatePlanBtn = document.getElementById("generatePlanBtn");
const summaryTitle = document.getElementById("summaryTitle");
const summaryText = document.getElementById("summaryText");
const materialList = document.getElementById("materialList");
const shortenForm = document.getElementById("shortenForm");
const planUrlInput = document.getElementById("planUrlInput");
const shortLinkCard = document.getElementById("shortLinkCard");
const shortLink = document.getElementById("shortLink");
const copyShareBtn = document.getElementById("copyShareBtn");
const shareError = document.getElementById("shareError");

const ELEMENTS_BY_SLUG = {
  albedo: "Geo", alhaitham: "Dendro", aloy: "Cryo", amber: "Pyro", "arataki-itto": "Geo", arlecchino: "Pyro", ayaka: "Cryo", ayato: "Hydro", baizhu: "Dendro", barbara: "Hydro", beidou: "Electro", bennett: "Pyro", candace: "Hydro", charlotte: "Cryo", chevreuse: "Pyro", chiori: "Geo", chongyun: "Cryo", clorinde: "Electro", collei: "Dendro", cyno: "Electro", dehya: "Pyro", diluc: "Pyro", diona: "Cryo", dori: "Electro", emilie: "Dendro", eula: "Cryo", faruzan: "Anemo", fischl: "Electro", freminet: "Cryo", furina: "Hydro", gaming: "Pyro", ganyu: "Cryo", gorou: "Geo", heizou: "Anemo", "hu-tao": "Pyro", jean: "Anemo", kachina: "Geo", kaeya: "Cryo", kaveh: "Dendro", kazuha: "Anemo", keqing: "Electro", kinich: "Dendro", kirara: "Dendro", klee: "Pyro", kokomi: "Hydro", "kuki-shinobu": "Electro", layla: "Cryo", lisa: "Electro", lynette: "Anemo", lyney: "Pyro", mika: "Cryo", mona: "Hydro", mualani: "Hydro", nahida: "Dendro", navia: "Geo", neuvillette: "Hydro", nilou: "Hydro", ningguang: "Geo", noelle: "Geo", qiqi: "Cryo", raiden: "Electro", razor: "Electro", rosaria: "Cryo", sara: "Electro", sayu: "Anemo", sethos: "Electro", shenhe: "Cryo", sucrose: "Anemo", tartaglia: "Hydro", thoma: "Pyro", tighnari: "Dendro", "traveler-anemo": "Anemo", venti: "Anemo", wanderer: "Anemo", xiangling: "Pyro", xianyun: "Anemo", xiao: "Anemo", xingqiu: "Hydro", xinyan: "Pyro", yanfei: "Pyro", yaoyao: "Dendro", "yae-miko": "Electro", yelan: "Hydro", yoimiya: "Pyro", "yun-jin": "Geo", zhongli: "Geo",
};

const CATEGORY_DETAILS = {
  characters: ["Characters", "Search the live character index. ", "Choose a record to open its profile."],
  weapons: ["Weapons", "Cloud-indexed weapon records. ", "Weapon details are served by JMP Blue."],
  artifacts: ["Artifacts", "Cloud-indexed artifact records. ", "Artifact details are served by JMP Blue."],
  materials: ["Materials", "Cloud-indexed material records. ", "Material details are served by JMP Blue."],
  enemies: ["Enemies", "Live enemy catalog records.", "Enemy portraits are served by JMP Blue."],
  food: ["Food", "Cloud-indexed food records. ", "Food details are served by JMP Blue."],
  builds: ["Featured Builds", "Open the ascension and build planner below."],
  teams: ["Teams", "Team planning shortcut. Select a character to start a build."],
  tierlist: ["Live Tier List", "Tier lists are community maintained; character specifications below remain cloud sourced."],
  tcg: ["Genius Invokation TCG", "Open the TCG directory."],
  "tcg-best-decks": ["TCG Best Decks", "Browse deck ideas in the TCG directory."],
  banners: ["Banners", "Browse event banner history."],
  leaderboard: ["Leaderboard", "Community leaderboard directory."],
  "spiral-abyss": ["Spiral Abyss", "Open the Spiral Abyss guide."],
  "imaginarium-theater": ["Imaginarium Theater", "Open the current Theater season."],
  onslaught: ["Onslaught", "Open the combat challenge guide."],
};

let characters = [];
let selectedCharacter = null;
let profileRequestId = 0;
let currentShortLink = "";
let activeElement = "all";
let archiveCharacters = [];
let catalogItems = [];
let catalogCategory = "characters";
let bannerTransitionEpoch = null;
let bannerTransitionReloaded = false;
let abyssCloseTimeout = null;
let abyssFloors = [];
let abyssTeams = [];

const TEAM_PORTRAIT_SLUGS = {
  "Kamisato Ayaka": "ayaka",
  "Raiden Shogun": "raiden",
};

function characterSlug(name) {
  return name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[()]/g, " ").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function getElement(character) {
  return character.element && character.element !== "Unknown"
    ? character.element
    : ELEMENTS_BY_SLUG[character.slug] || "Unknown";
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 429 || response.status === 403) {
      showVelocityAlert(data.challenge_url);
    }
    const error = new Error(data.detail || `Request failed (${response.status}).`);
    error.status = response.status;
    error.challengeUrl = data.challenge_url;
    throw error;
  }
  return data;
}

function showVelocityAlert(challengeUrl) {
  if (!velocityAlert) return;
  if (challengeUrl && challengeUrl.startsWith("/security/challenge/")) {
    velocityChallengeLink.href = challengeUrl;
    velocityChallengeLink.classList.remove("hidden");
  } else {
    velocityChallengeLink?.classList.add("hidden");
  }
  velocityAlert.classList.add("is-visible");
  velocityAlert.setAttribute("aria-hidden", "false");
}

function hideVelocityAlert() {
  velocityAlert?.classList.remove("is-visible");
  velocityAlert?.setAttribute("aria-hidden", "true");
}

async function getCharacterMappings() {
  const data = await fetchJson("/api/characters");
  characters = Array.isArray(data) ? data : [];
  return characters;
}

function populateCharacterSelect(preferredSlug) {
  if (!characterSelect) return;
  characterSelect.replaceChildren();
  characters.forEach((character) => {
    const option = document.createElement("option");
    option.value = character.slug || characterSlug(character.name);
    option.textContent = character.name;
    characterSelect.appendChild(option);
  });
  const target = characters.some((character) => character.slug === preferredSlug)
    ? preferredSlug
    : characters[0]?.slug;
  if (target) characterSelect.value = target;
}

function setProfileLoading(isLoading) {
  if (profileLoading) profileLoading.classList.toggle("hidden", !isLoading);
  document.getElementById("characterCard")?.classList.toggle("is-loading", isLoading);
}

function renderProfileMaterials(character) {
  if (!profileMaterials) return;
  profileMaterials.replaceChildren();
  const levelTwenty = character.ascension_materials?.level_20 || [];
  levelTwenty.slice(0, 4).forEach((material) => {
    const badge = document.createElement("span");
    badge.textContent = `${material.name} ×${material.value}`;
    profileMaterials.appendChild(badge);
  });
  if (profileMaterials.childElementCount === 0 && character.specialty) {
    const badge = document.createElement("span");
    badge.textContent = character.specialty;
    profileMaterials.appendChild(badge);
  }
}

function renderCharacterProfile(character) {
  if (!characterName) return;
  characterName.textContent = character.name || "Traveler";
  characterRegion.textContent = String(character.region || character.nation || "TEYVAT").toUpperCase();
  characterDescription.textContent = character.description || `${character.element || "Element unknown"} · ${character.weapon || "Weapon unknown"}`;
  elementValue.textContent = character.element || character.vision || "Unknown";
  weaponValue.textContent = character.weapon || "Unknown";
  rarityValue.textContent = character.rarity ? `${character.rarity} ★` : "Cloud profile";
  if (characterImage) {
    characterImage.alt = `${character.name || "Character"} icon`;
    characterImage.onerror = () => {
      characterImage.removeAttribute("src");
      if (imageFallback) imageFallback.hidden = false;
    };
    if (imageFallback) imageFallback.hidden = true;
    characterImage.src = character.icon_url || `https://genshin.jmp.blue/characters/${character.slug}/icon`;
  }
  renderProfileMaterials(character);
}

async function loadCharacterProfile(slug) {
  if (!slug || !characterName) return;
  const requestId = ++profileRequestId;
  const mapping = characters.find((character) => character.slug === slug);
  setProfileLoading(true);
  if (mapping) {
    characterName.textContent = mapping.name;
    elementValue.textContent = getElement(mapping);
    weaponValue.textContent = mapping.weapon || "Loading";
    if (characterImage) characterImage.src = mapping.icon_url || `https://genshin.jmp.blue/characters/${slug}/icon`;
  }

  try {
    const character = await fetchJson(`/characters/${encodeURIComponent(slug)}`);
    if (requestId !== profileRequestId) return;
    selectedCharacter = character;
    renderCharacterProfile(character);
  } catch (error) {
    if (requestId !== profileRequestId) return;
    selectedCharacter = mapping || { slug, name: slug.replace(/-/g, " ") };
    renderCharacterProfile(selectedCharacter);
    if (summaryText) summaryText.textContent = error.message;
  } finally {
    if (requestId === profileRequestId) setProfileLoading(false);
  }
}

function createCatalogItem(item, category) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "catalog-item";
  const image = document.createElement("img");
  image.alt = "";
  image.loading = "lazy";
  image.src = item.icon_url || `https://genshin.jmp.blue/${category}/${encodeURIComponent(item.slug)}/icon`;
  image.onerror = () => image.remove();
  const label = document.createElement("span");
  label.textContent = item.name;
  button.append(image, label);
  if (category === "characters") {
    button.addEventListener("click", () => {
      if (characterSelect) characterSelect.value = item.slug;
      loadCharacterProfile(item.slug);
      document.getElementById("profile")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  } else {
    button.addEventListener("click", () => {
      catalogStatus.textContent = `${item.name} is available in the cloud index.`;
    });
  }
  return button;
}

function appendTextElement(parent, tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

function updateBannerCountdown() {
  if (!bannerCountdown || !bannerTransitionEpoch) return;
  const seconds = Math.max(0, bannerTransitionEpoch - Math.floor(Date.now() / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  bannerCountdown.textContent = `${days}d ${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m ${String(remainder).padStart(2, "0")}s`;
  if (seconds === 0 && !bannerTransitionReloaded) {
    bannerTransitionReloaded = true;
    openBannerPanel();
  }
}

function renderBannerPhase(phase) {
  const card = document.createElement("article");
  card.className = `banner-phase${phase.status === "active" ? " is-active" : ""}`;
  const heading = document.createElement("div");
  heading.className = "banner-phase-top";
  appendTextElement(heading, "h3", "", phase.label);
  appendTextElement(heading, "span", `phase-badge${phase.status === "active" ? " is-active" : ""}`, phase.status === "active" ? "Active Now" : phase.status === "upcoming" ? "Upcoming Phase" : "Ended");
  card.appendChild(heading);
  appendTextElement(card, "p", "phase-dates", `${new Date(phase.starts_at).toLocaleDateString()} – ${new Date(phase.ends_at).toLocaleDateString()}`);

  const featured = document.createElement("div");
  featured.className = "banner-featured";
  phase.characters.forEach((name) => {
    const slug = characterSlug(name);
    const item = document.createElement("div");
    item.className = "banner-character";
    const image = document.createElement("img");
    image.loading = "lazy";
    image.alt = "";
    image.src = `https://genshin.jmp.blue/characters/${slug}/icon`;
    image.onerror = () => image.remove();
    item.appendChild(image);
    appendTextElement(item, "strong", "", name);
    featured.appendChild(item);
  });
  card.appendChild(featured);
  if (phase.featured_four_stars.length) {
    appendTextElement(card, "p", "banner-subheading", "Featured 4-Star Rate-Ups");
    const fourStars = document.createElement("div");
    fourStars.className = "banner-chip-row";
    phase.featured_four_stars.forEach((name) => appendTextElement(fourStars, "span", "banner-chip", name));
    card.appendChild(fourStars);
  }
  appendTextElement(card, "p", "banner-subheading", "Promotional Weapon Wish");
  const weapons = document.createElement("div");
  weapons.className = "banner-chip-row";
  phase.weapons.forEach((name) => appendTextElement(weapons, "span", "banner-chip", name));
  card.appendChild(weapons);
  return card;
}

async function openBannerPanel() {
  if (!bannersPanel) return;
  closeAbyssDrawer();
  catalogPanel?.classList.add("hidden");
  theaterPanel?.classList.add("hidden");
  bannersPanel.classList.remove("hidden");
  bannerPhases.replaceChildren();
  appendTextElement(bannerPhases, "p", "catalog-status", "Loading live banner schedule…");
  try {
    const data = await fetchJson("/api/banners/live");
    bannerPhases.replaceChildren();
    const phases = [data.active, data.upcoming].filter(Boolean);
    phases.forEach((phase) => bannerPhases.appendChild(renderBannerPhase(phase)));
    const current = data.active;
    bannerCountdownLabel.textContent = current ? "Active phase ends in" : "Next phase begins in";
    bannerTransitionEpoch = data.transition_epoch;
    bannerTransitionReloaded = false;
    bannerUpdated.textContent = current ? `${current.label} · Active Now` : "No active phase";
    updateBannerCountdown();
  } catch (error) {
    bannerPhases.replaceChildren();
    appendTextElement(bannerPhases, "p", "catalog-empty", error.message);
  }
}

function appendTheaterCast(container, names) {
  container.replaceChildren();
  names.forEach((entry) => {
    const character = typeof entry === "string" ? { name: entry } : entry;
    const chip = document.createElement("span");
    chip.className = "theater-cast-chip";
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.src = character.icon_url || `https://genshin.jmp.blue/characters/${character.slug || characterSlug(character.name)}/icon`;
    image.onerror = () => image.remove();
    appendTextElement(chip, "span", "", character.name || "Unknown");
    chip.prepend(image);
    container.appendChild(chip);
  });
}

function renderTheater(data) {
  theaterSeason.textContent = data.season || data.season_name || "Current Season";
  theaterStatus.textContent = data.updated_at ? `Feed updated ${new Date(data.updated_at).toLocaleString()}` : "Current data from configured season feed";
  theaterLocks.replaceChildren();
  (data.active_element_locks || data.active_elements || []).forEach((element) => {
    appendTextElement(theaterLocks, "span", "theater-lock", element.name || element);
  });
  appendTheaterCast(theaterOpeningCast, data.opening_cast || []);
  appendTheaterCast(theaterGuests, data.special_guest_stars || []);
  theaterActs.replaceChildren();
  (data.act_buffs || []).forEach((buff, index) => {
    const card = document.createElement("article");
    card.className = "theater-act";
    appendTextElement(card, "h3", "", `${buff.act || buff.number || index + 1} · ${buff.name || "Act effect"}`);
    appendTextElement(card, "p", "", buff.description || buff.effect || "Season modifier");
    theaterActs.appendChild(card);
  });
}

async function openTheaterPanel() {
  closeAbyssDrawer();
  catalogPanel?.classList.add("hidden");
  bannersPanel?.classList.add("hidden");
  theaterPanel?.classList.remove("hidden");
  theaterStatus.textContent = "Connecting to the season feed…";
  try {
    renderTheater(await fetchJson("/api/theater/current"));
  } catch (error) {
    theaterStatus.textContent = error.message;
    theaterSeason.textContent = "Season feed unavailable";
  }
}

function renderAbyss(data) {
  abyssCycle.textContent = `${data.cycle} · Floor ${data.floor}`;
  abyssBlessingName.textContent = data.blessing.name;
  abyssBlessingText.textContent = data.blessing.description;
  abyssDataStatus.textContent = data.data_status || "Rotation data";
  abyssFloorSelector.replaceChildren();
  abyssFloors.forEach((floor) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "abyss-floor-button";
    button.setAttribute("aria-pressed", String(floor.floor === data.floor));
    button.setAttribute("aria-label", `Floor ${floor.floor}: ${floor.label || "tactical layout"}`);
    const image = document.createElement("img");
    image.src = floor.layout_image_url;
    image.alt = "";
    image.loading = "lazy";
    image.onerror = () => image.remove();
    appendTextElement(button, "span", "", String(floor.floor).padStart(2, "0"));
    button.prepend(image);
    button.addEventListener("click", () => renderAbyss(floor));
    abyssFloorSelector.appendChild(button);
  });
  leylineGrid.replaceChildren();
  data.halves.forEach((half) => {
    const card = document.createElement("article");
    card.className = "leyline-half";
    appendTextElement(card, "h3", "", half.name);
    half.disorders.forEach((disorder) => appendTextElement(card, "p", "", disorder));
    const tags = document.createElement("div");
    tags.className = "recommended-row";
    half.recommended_elements.forEach((element) => appendTextElement(tags, "span", "", element));
    card.appendChild(tags);
    leylineGrid.appendChild(card);
  });

  chamberGrid.replaceChildren();
  const enemyImages = new Map((data.enemy_assets || []).map((enemy) => [enemy.name, enemy.image_url]));
  data.chambers.forEach((chamber) => {
    const card = document.createElement("article");
    card.className = "chamber-card";
    appendTextElement(card, "h3", "", `Chamber ${chamber.number}`);
    [["First Half", chamber.first_half_enemies], ["Second Half", chamber.second_half_enemies]].forEach(([label, enemies]) => {
      const half = document.createElement("div");
      half.className = "chamber-half";
      appendTextElement(half, "strong", "", label);
      const enemyList = document.createElement("div");
      enemyList.className = "enemy-list";
      enemies.forEach((name) => {
        const enemy = document.createElement("div");
        enemy.className = "enemy-entry";
        const icon = document.createElement("span");
        icon.className = "enemy-icon";
        appendTextElement(icon, "span", "enemy-fallback", name.slice(0, 1));
        const imageUrl = enemyImages.get(name);
        if (imageUrl) {
          const image = document.createElement("img");
          image.src = imageUrl;
          image.alt = "";
          image.loading = "lazy";
          image.onerror = () => image.remove();
          icon.prepend(image);
        }
        appendTextElement(enemy, "span", "enemy-name", name);
        enemy.prepend(icon);
        enemyList.appendChild(enemy);
      });
      half.appendChild(enemyList);
      card.appendChild(half);
    });
    appendTextElement(card, "p", "chamber-strategy", chamber.strategy);
    const recommended = document.createElement("div");
    recommended.className = "recommended-row";
    chamber.recommended_elements.forEach((element) => appendTextElement(recommended, "span", "", element));
    card.appendChild(recommended);
    Object.entries(chamber.recommended_teams || {}).forEach(([half, team]) => {
      const teamLine = document.createElement("p");
      teamLine.className = "team-line";
      teamLine.textContent = `${half === "first_half" ? "First" : "Second"} half team: ${team.join(" · ")}`;
      card.appendChild(teamLine);
    });
    chamberGrid.appendChild(card);
  });
  renderTeamRecommendations(data.teams || abyssTeams);
}

function renderTeamRecommendations(teams) {
  abyssTeamGrid.replaceChildren();
  teams.forEach((team) => {
    const card = document.createElement("article");
    card.className = "abyss-team-card";
    appendTextElement(card, "h4", "", team.name || `Floor ${team.floor} recommendation`);
    appendTextElement(card, "p", "team-best-for", (team.matched_elements || []).join(" · ") || "Element-match recommendation");
    const members = document.createElement("div");
    members.className = "team-members";
    (team.members || []).forEach((memberData) => {
      const name = typeof memberData === "string" ? memberData : memberData.name;
      const member = document.createElement("span");
      member.className = "team-member";
      const image = document.createElement("img");
      image.alt = "";
      image.loading = "lazy";
      const slug = TEAM_PORTRAIT_SLUGS[name] || memberData.slug || characterSlug(name);
      image.src = memberData.icon_url || `https://genshin.jmp.blue/characters/${slug}/icon`;
      image.onerror = () => image.remove();
      appendTextElement(member, "span", "", name);
      member.prepend(image);
      members.appendChild(member);
    });
    card.appendChild(members);
    (team.resonances || []).forEach((resonance) => {
      appendTextElement(card, "p", "team-description", `${resonance.element} resonance · ${resonance.effect}`);
    });
    if (team.reaction_chain) appendTextElement(card, "p", "team-description", team.reaction_chain);
    abyssTeamGrid.appendChild(card);
  });
}

function closeAbyssDrawer() {
  if (abyssCloseTimeout) window.clearTimeout(abyssCloseTimeout);
  abyssPanel?.classList.remove("is-open");
  abyssScrim?.classList.add("hidden");
  abyssCloseTimeout = window.setTimeout(() => {
    if (!abyssPanel?.classList.contains("is-open")) abyssPanel?.classList.add("hidden");
  }, 260);
}

async function openAbyssPanel() {
  if (!abyssPanel) return;
  if (abyssCloseTimeout) window.clearTimeout(abyssCloseTimeout);
  catalogPanel?.classList.add("hidden");
  bannersPanel?.classList.add("hidden");
  theaterPanel?.classList.add("hidden");
  abyssPanel.classList.remove("hidden");
  abyssScrim?.classList.remove("hidden");
  abyssPanel.classList.add("is-open");
  try {
    const matrix = await fetchJson("/api/abyss");
    abyssFloors = matrix.floors || [];
    abyssTeams = matrix.teams || [];
    const activeFloor = abyssFloors.find((floor) => floor.floor === 12) || abyssFloors[0];
    if (activeFloor) renderAbyss(activeFloor);
  } catch (error) {
    abyssCycle.textContent = "Spiral Abyss";
    abyssDataStatus.textContent = error.message;
    abyssBlessingName.textContent = "Rotation data unavailable";
    abyssBlessingText.textContent = "Connect an Abyss feed to load current floors and tactical recommendations.";
    abyssFloorSelector.replaceChildren();
    leylineGrid.replaceChildren();
    chamberGrid.replaceChildren();
    abyssTeamGrid.replaceChildren();
  }
}

function filterCatalog() {
  if (!catalogResults) return;
  const query = (catalogSearch?.value || "").trim().toLowerCase();
  const visible = catalogItems.filter((item) => item.name.toLowerCase().includes(query));
  catalogResults.replaceChildren();
  visible.forEach((item) => catalogResults.appendChild(createCatalogItem(item, catalogCategory)));
  if (visible.length === 0) {
    const empty = document.createElement("p");
    empty.className = "catalog-empty";
    empty.textContent = query ? "No matching entries." : "This section has no cloud records yet.";
    catalogResults.appendChild(empty);
  }
}

async function openCategory(category) {
  if (category === "banners") {
    await openBannerPanel();
    return;
  }
  if (category === "spiral-abyss") {
    await openAbyssPanel();
    return;
  }
  if (category === "imaginarium-theater") {
    await openTheaterPanel();
    return;
  }
  if (!catalogPanel) {
    document.getElementById("profile")?.scrollIntoView({ behavior: "smooth" });
    return;
  }
  closeAbyssDrawer();
  bannersPanel?.classList.add("hidden");
  theaterPanel?.classList.add("hidden");
  catalogCategory = category;
  bannersPanel?.classList.add("hidden");
  const details = CATEGORY_DETAILS[category] || [category, "Browse the Teyvat portal."];
  catalogPanel.classList.remove("hidden");
  catalogTitle.textContent = details[0];
  catalogDescription.textContent = details[1];
  catalogStatus.textContent = "Connecting to the cloud index…";
  catalogItems = [];
  catalogResults.replaceChildren();
  catalogPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const response = await fetchJson(`/api/catalog/${encodeURIComponent(category)}`);
    catalogItems = response.items || [];
    if (category === "characters") {
      characters = catalogItems;
      populateCharacterSelect(characterSelect?.value);
    }
    catalogStatus.textContent = `${catalogItems.length} ${details[0].toLowerCase()} indexed · ${response.source || "portal"}`;
    filterCatalog();
    if (category === "builds") document.getElementById("profile")?.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    catalogStatus.textContent = error.message;
  }
}

function setupPortal() {
  document.addEventListener("click", (event) => {
    const shortcut = event.target.closest("[data-category]");
    if (!shortcut) return;
    if (shortcut.tagName === "A") event.preventDefault();
    openCategory(shortcut.dataset.category);
  });
  catalogSearch?.addEventListener("input", filterCatalog);
  document.querySelectorAll("[data-close-panel]").forEach((button) => {
    button.addEventListener("click", () => {
      bannersPanel?.classList.add("hidden");
      theaterPanel?.classList.add("hidden");
      closeAbyssDrawer();
    });
  });
  abyssScrim?.addEventListener("click", closeAbyssDrawer);
  velocityAlertClose?.addEventListener("click", hideVelocityAlert);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAbyssDrawer();
  });

  if (characterSelect) {
    characterSelect.addEventListener("change", (event) => {
      const selectedSlug = event.currentTarget.value;
      loadCharacterProfile(selectedSlug);
    });
  }

  getCharacterMappings().then(async () => {
    const pendingSlug = localStorage.getItem("selectedCharacterSlug");
    const pendingName = localStorage.getItem("selectedCharacterName");
    const selected = characters.find((character) => character.slug === pendingSlug || character.name === pendingName);
    populateCharacterSelect(selected?.slug);
    if (selected) {
      localStorage.removeItem("selectedCharacterSlug");
      localStorage.removeItem("selectedCharacterName");
    }
    if (characterSelect?.value) await loadCharacterProfile(characterSelect.value);
  }).catch((error) => {
    if (characterSelect) characterSelect.innerHTML = "<option value=''>Cloud archive unavailable</option>";
    if (profileLoading) {
      profileLoading.textContent = error.message;
      profileLoading.classList.remove("hidden");
    }
  });

  window.setInterval(updateBannerCountdown, 1000);
}

function renderPlanMaterials(materials) {
  if (!materialList) return;
  materialList.replaceChildren();
  const entries = [...(materials || [])];
  entries.forEach((material) => {
    const badge = document.createElement("span");
    badge.textContent = `${material.name} ×${material.amount}`;
    materialList.appendChild(badge);
  });
}

function setupPlanner() {
  generatePlanBtn?.addEventListener("click", async () => {
    if (!characterSelect?.value) {
      summaryTitle.textContent = "Choose a character first";
      return;
    }
    summaryTitle.textContent = "Calculating from cloud data…";
    summaryText.textContent = "Paimon is checking ascension materials.";
    materialList.replaceChildren();
    try {
      const data = await fetchJson("/api/build-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          character: characterSelect.value,
          current_level: Number(document.getElementById("currentLevel").value),
          target_level: Number(document.getElementById("targetLevel").value),
          talent_goals: {
            normal: Number(document.getElementById("normalTalent").value),
            skill: Number(document.getElementById("skillTalent").value),
            burst: Number(document.getElementById("burstTalent").value),
          },
        }),
      });
      summaryTitle.textContent = `${data.character} ascension plan`;
      summaryText.textContent = `${data.summary} Mora: ${Number(data.mora).toLocaleString()}.`;
      renderPlanMaterials(data.required_materials);
    } catch (error) {
      summaryTitle.textContent = "Calculation unavailable";
      summaryText.textContent = error.message;
    }
  });
}

function setupShortener() {
  shortenForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    shareError.textContent = "";
    const longUrl = planUrlInput.value.trim();
    if (!/^https?:\/\//i.test(longUrl)) {
      shareError.textContent = "Enter a valid http:// or https:// URL.";
      return;
    }
    try {
      const data = await fetchJson("/shorten", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: longUrl }),
      });
      currentShortLink = data.short_url;
      shortLink.textContent = currentShortLink;
      shortLink.href = currentShortLink;
      shortLinkCard.classList.remove("hidden");
      copyShareBtn.textContent = "Copy";
    } catch (error) {
      shareError.textContent = error.message;
    }
  });
  copyShareBtn?.addEventListener("click", async () => {
    if (!currentShortLink) return;
    try {
      await navigator.clipboard.writeText(currentShortLink);
      copyShareBtn.textContent = "Copied";
    } catch (error) {
      copyShareBtn.textContent = "Copy failed";
    }
  });
}

function filterArchive() {
  if (!characterGrid) return;
  const query = (archiveSearch?.value || "").trim().toLowerCase();
  const visible = archiveCharacters.filter((character) => {
    const element = getElement(character);
    const matchesElement = activeElement === "all" || element === activeElement;
    return matchesElement && character.name.toLowerCase().includes(query);
  });
  characterGrid.replaceChildren();
  visible.forEach((character, index) => {
    const element = getElement(character);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "archive-card";
    card.style.animationDelay = `${Math.min(index * 14, 180)}ms`;
    const art = document.createElement("div");
    art.className = "archive-art";
    const image = document.createElement("img");
    image.loading = "lazy";
    image.alt = `${character.name} icon`;
    image.src = character.icon_url || `https://genshin.jmp.blue/characters/${character.slug}/icon`;
    image.onerror = () => image.remove();
    const fallback = document.createElement("span");
    fallback.textContent = "✦";
    const elementLabel = document.createElement("span");
    elementLabel.className = "element-label";
    elementLabel.textContent = element;
    art.append(image, fallback, elementLabel);
    const body = document.createElement("div");
    body.className = "archive-card-body";
    const name = document.createElement("h2");
    name.textContent = character.name;
    const weapon = document.createElement("p");
    weapon.textContent = character.weapon && character.weapon !== "Unknown" ? character.weapon : "Character dossier";
    body.append(name, weapon);
    card.append(art, body);
    card.addEventListener("click", () => {
      localStorage.setItem("selectedCharacterSlug", character.slug);
      localStorage.setItem("selectedCharacterName", character.name);
      window.location.assign("/#profile");
    });
    characterGrid.appendChild(card);
  });
  archiveCount.textContent = `${visible.length} / ${archiveCharacters.length} characters`;
  archiveStatus.textContent = visible.length ? "Select a dossier to continue to the build companion." : "No characters match this filter.";
}

async function setupArchive() {
  try {
    archiveCharacters = await getCharacterMappings();
    filterArchive();
  } catch (error) {
    archiveStatus.textContent = error.message;
    archiveCount.textContent = "Archive offline";
  }
  archiveSearch?.addEventListener("input", filterArchive);
  document.getElementById("elementFilters")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-element]");
    if (!button) return;
    activeElement = button.dataset.element;
    document.querySelectorAll(".filter-chip").forEach((chip) => chip.classList.toggle("active", chip === button));
    filterArchive();
  });
}

if (document.body.dataset.page === "archive") {
  setupArchive();
} else {
  setupPortal();
  setupPlanner();
  setupShortener();
}
