(() => {
    "use strict";

    const dialog = document.getElementById("satellite-image-dialog");
    const viewerImage = document.getElementById("satellite-viewer-image");
    const viewerTitle = document.getElementById("satellite-viewer-title");
    const viewerSubtitle = document.getElementById("satellite-viewer-subtitle");
    const viewerOverlay = document.getElementById("satellite-viewer-overlay");
    const viewerPolygon = document.getElementById("satellite-viewer-polygon");
    const viewerLabel = document.getElementById("satellite-viewer-label");

    function activateView(button) {
        const product = button.closest(".satellite-image-product");
        const targetId = button.dataset.viewTarget;
        if (!product || !targetId) {
            return;
        }

        product.querySelectorAll(".js-satellite-view-toggle").forEach((candidate) => {
            const active = candidate === button;
            candidate.classList.toggle("is-active", active);
            candidate.setAttribute("aria-pressed", active ? "true" : "false");
        });

        product.querySelectorAll(".satellite-view-panel").forEach((panel) => {
            panel.hidden = panel.id !== targetId;
        });
    }

    function openViewer(button) {
        if (!dialog || !viewerImage || !viewerTitle || !viewerSubtitle) {
            return;
        }

        const imageUrl = button.dataset.imageUrl || "";
        const title = button.dataset.title || "Imagen satelital";
        const subtitle = button.dataset.subtitle || "";
        const overlayPoints = button.dataset.overlayPoints || "";

        viewerImage.src = imageUrl;
        viewerImage.alt = title;
        viewerTitle.textContent = title;
        viewerSubtitle.textContent = subtitle;

        if (viewerOverlay && viewerPolygon && viewerLabel) {
            viewerPolygon.setAttribute("points", overlayPoints);
            const hasOverlay = Boolean(overlayPoints.trim());
            viewerOverlay.hidden = !hasOverlay;
            viewerLabel.hidden = !hasOverlay;
        }

        if (typeof dialog.showModal === "function") {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "");
        }
    }

    document.addEventListener("click", (event) => {
        const toggle = event.target.closest(".js-satellite-view-toggle");
        if (toggle) {
            activateView(toggle);
            return;
        }

        const viewerButton = event.target.closest(".js-open-satellite-viewer");
        if (viewerButton) {
            openViewer(viewerButton);
        }
    });

    if (dialog) {
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) {
                dialog.close();
            }
        });
    }
})();
