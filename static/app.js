const form = document.getElementById("shortenForm");
const urlInput = document.getElementById("urlInput");
const resultBox = document.getElementById("resultBox");
const copyBtn = document.getElementById("copyBtn");

let shortLink = "";

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const longUrl = urlInput.value.trim();
  if (!longUrl) {
    resultBox.textContent = "Please enter a valid URL.";
    return;
  }

  try {
    const response = await fetch("/api/shorten", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: longUrl }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Unable to shorten URL.");
    }

    shortLink = data.short_url;
    resultBox.textContent = shortLink;
    copyBtn.hidden = false;
  } catch (error) {
    resultBox.textContent = error.message;
    copyBtn.hidden = true;
  }
});

copyBtn.addEventListener("click", async () => {
  if (!shortLink) {
    return;
  }

  try {
    await navigator.clipboard.writeText(shortLink);
    copyBtn.textContent = "Copied!";
  } catch (error) {
    copyBtn.textContent = "Copy failed";
  }
});
