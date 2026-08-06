(() => {
  const dialog = document.querySelector("#video-modal");
  const player = document.querySelector("#video-modal-player");
  const title = document.querySelector("#video-modal-title");
  const meta = document.querySelector("#video-modal-meta");
  const directLink = document.querySelector("#video-modal-link");
  const closeButton = dialog?.querySelector(".video-modal-close");
  let activeTrigger = null;

  if (!dialog || !player || !title || !meta || !directLink || !closeButton) {
    return;
  }

  const closeDialog = () => {
    if (dialog.open) {
      dialog.close();
    }
  };

  document.querySelectorAll("[data-video-src]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      activeTrigger = trigger;
      const source = trigger.dataset.videoSrc;
      player.src = source;
      player.poster = trigger.dataset.videoPoster || "";
      title.textContent = trigger.dataset.videoTitle || "実行動画";
      meta.textContent = trigger.dataset.videoMeta || "";
      directLink.href = source;
      dialog.showModal();
      document.body.classList.add("video-modal-open");
      player.play().catch(() => {
        // The controls remain available when a browser declines autoplay.
      });
      closeButton.focus();
    });
  });

  closeButton.addEventListener("click", closeDialog);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && dialog.open) {
      event.preventDefault();
      closeDialog();
    }
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      closeDialog();
    }
  });
  dialog.addEventListener("close", () => {
    player.pause();
    player.removeAttribute("src");
    player.load();
    document.body.classList.remove("video-modal-open");
    activeTrigger?.focus();
    activeTrigger = null;
  });
})();
