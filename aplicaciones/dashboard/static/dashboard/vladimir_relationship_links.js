(() => {
    let timer = null;
    let lastSignature = "";

    const selectedSensorId = () =>
        String(document.getElementById("sensor-select")?.value || "").trim();

    const loadRelationships = async (sensorId) => {
        const response = await fetch(`/s2/agronomy?sensor=${encodeURIComponent(sensorId)}`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) return [];
        const payload = await response.json();
        return payload.relationships || [];
    };

    const relationshipIdFromCard = (card) =>
        String(card.querySelector(".agronomy-delete")?.dataset.relationshipId || "").trim();

    const addOpenAction = (card, relationshipId) => {
        if (!relationshipId || card.querySelector(".relationship-open-link")) return;

        const link = document.createElement("a");
        link.className = "button button-primary relationship-open-link";
        link.href = `/s2/agronomy/relationships/${encodeURIComponent(relationshipId)}/`;
        link.textContent = "Abrir análisis y alertas →";
        link.setAttribute("aria-label", "Abrir análisis, gráficos, registros y alertas de la relación");
        link.style.width = "100%";
        link.style.marginTop = "12px";

        const deleteButton = card.querySelector(".agronomy-delete");
        if (deleteButton) {
            card.insertBefore(link, deleteButton);
        } else {
            card.appendChild(link);
        }
    };

    const decorate = async () => {
        const cards = [...document.querySelectorAll(".agronomy-saved-card")];
        const sensorId = selectedSensorId();
        if (!cards.length || !sensorId) return;

        const signature = `${sensorId}:${cards.length}`;
        if (
            signature === lastSignature &&
            cards.every((card) => card.querySelector(".relationship-open-link"))
        ) {
            return;
        }

        const missingIds = cards.some((card) => !relationshipIdFromCard(card));
        let relationships = [];
        if (missingIds) {
            try {
                relationships = await loadRelationships(sensorId);
            } catch (_error) {
                relationships = [];
            }
        }

        cards.forEach((card, index) => {
            const relationshipId = relationshipIdFromCard(card) || relationships[index]?.id;
            addOpenAction(card, relationshipId);
        });

        lastSignature = signature;
    };

    const schedule = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(decorate, 80);
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
