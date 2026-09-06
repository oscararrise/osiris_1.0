(() => {
    let timer = null;
    let lastSignature = "";

    const selectedSensorId = () =>
        String(document.getElementById("sensor-select")?.value || "").trim();

    const decorate = async () => {
        const cards = [...document.querySelectorAll(".agronomy-saved-card")];
        const sensorId = selectedSensorId();
        if (!cards.length || !sensorId) return;
        const signature = `${sensorId}:${cards.length}`;
        if (signature === lastSignature && cards.every((card) => card.querySelector(".relationship-open-link"))) return;

        try {
            const response = await fetch(`/s2/agronomy?sensor=${encodeURIComponent(sensorId)}`, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) return;
            const payload = await response.json();
            const relationships = payload.relationships || [];
            cards.forEach((card, index) => {
                const relationship = relationships[index];
                if (!relationship || card.querySelector(".relationship-open-link")) return;
                const link = document.createElement("a");
                link.className = "button button-ghost relationship-open-link";
                link.href = `/s2/agronomy/relationships/${relationship.id}/`;
                link.textContent = "Abrir relación";
                link.style.marginTop = "12px";
                link.style.display = "inline-flex";
                card.appendChild(link);
            });
            lastSignature = signature;
        } catch (_error) {
            // The relationship workbench remains usable even if link decoration fails.
        }
    };

    const schedule = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(decorate, 100);
    };

    document.addEventListener("DOMContentLoaded", () => {
        schedule();
        const observer = new MutationObserver(schedule);
        observer.observe(document.body, { childList: true, subtree: true });
        document.getElementById("sensor-select")?.addEventListener("change", () => {
            lastSignature = "";
            schedule();
        });
    });
})();
