// handles both subscribe forms on the page

const API_URL = "/api/subscribe";

function showStatus(el, type, msg) {
  el.textContent = msg;
  el.className = `form-status ${type}`;
}

function handleForm(formId, emailId, btnId, statusId, nameId = null) {
  const form = document.getElementById(formId);
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const email = document.getElementById(emailId).value.trim();
    const name = nameId ? document.getElementById(nameId)?.value.trim() : "";
    const btn = document.getElementById(btnId);
    const status = document.getElementById(statusId);

    if (!email) return;

    btn.disabled = true;
    btn.textContent = "Subscribing…";
    status.className = "form-status hidden";

    try {
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name }),
      });

      const data = await resp.json();

      if (resp.ok) {
        showStatus(status, "success", "🎉 You're subscribed! Check your inbox for a confirmation.");
        form.reset();
      } else {
        showStatus(status, "error", data.error || "Something went wrong. Try again.");
      }
    } catch (err) {
      showStatus(status, "error", "Network error — please try again.");
    } finally {
      btn.disabled = false;
      btn.textContent = formId === "subscribe-form" ? "Get daily digest →" : "Subscribe free";
    }
  });
}

// hero form
handleForm("subscribe-form", "email-input", "submit-btn", "form-status");

// bottom subscribe form (has optional name field)
handleForm("subscribe-form-2", "email-input-2", "submit-btn-2", "form-status-2", "name-input");
