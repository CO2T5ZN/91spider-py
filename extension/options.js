const input = document.getElementById("server");
const saved = document.getElementById("saved");

chrome.storage.sync.get({ server: "http://127.0.0.1:8765" }, ({ server }) => {
  input.value = server;
});

document.getElementById("save").addEventListener("click", () => {
  const v = input.value.trim().replace(/\/+$/, "");
  chrome.storage.sync.set({ server: v || "http://127.0.0.1:8765" }, () => {
    saved.textContent = "已保存";
    setTimeout(() => (saved.textContent = ""), 2000);
  });
});
