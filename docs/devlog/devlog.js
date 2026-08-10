(async () => {
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

  const latestTrigger = document.querySelector("[data-latest-demo-manifest]");
  if (latestTrigger) {
    const status = document.querySelector("#latest-demo-status");
    try {
      const response = await fetch(latestTrigger.dataset.latestDemoManifest, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`latest demo manifest returned ${response.status}`);
      }
      const latest = await response.json();
      if (latest.status !== "verified" || !latest.video_path || !latest.poster_path) {
        throw new Error("latest demo manifest is not verified");
      }
      latestTrigger.dataset.videoSrc = latest.video_path;
      latestTrigger.dataset.videoPoster = latest.poster_path;
      latestTrigger.dataset.videoTitle = `${latest.phase.toUpperCase()} - ${latest.change_name}`;
      latestTrigger.dataset.videoMeta = `${latest.focus} / ${latest.duration_seconds} s / source ${latest.source_commit}`;
      const phase = document.querySelector("#latest-demo-phase");
      const focus = document.querySelector("#latest-demo-focus");
      const poster = document.querySelector("#latest-demo-poster");
      if (phase) phase.textContent = latest.phase.toUpperCase();
      if (focus) focus.textContent = latest.focus;
      if (poster) {
        poster.src = latest.poster_path;
        poster.alt = `${latest.phase.toUpperCase()} latest demo poster`;
      }
      if (status) status.textContent = "再生確認済み";
    } catch (error) {
      latestTrigger.disabled = true;
      if (status) status.textContent = "最新デモを読み込めません";
      console.warn("Latest demo manifest could not be loaded", error);
    }
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
