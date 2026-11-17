// wg-notifications.js — shared across all pages.
// Notifications are now stored server-side (shared across everyone), with
// read/unread state tracked per logged-in user's email. If nobody is logged
// in, the badge just stays hidden — notifications are tied to an account.
const WG_BACKEND_URL = "http://127.0.0.1:8000";
window.WG_BACKEND_URL = WG_BACKEND_URL;
function wgAuthHeaders() {
  try {
    const user = JSON.parse(localStorage.getItem('wg_user') || 'null');

    return user && user.loggedIn && user.token
      ? { 'Authorization': `Bearer ${user.token}` }
      : {};
  } catch (error) {
    return {};
  }
}

function wgCurrentUserEmail() {
  try {
    const user = JSON.parse(localStorage.getItem('wg_user') || 'null');
    return (user && user.loggedIn && user.email) ? user.email : null;
  } catch (e) { return null; }
}


async function wgGetNotifications(limit = 10, offset = 0) {
  const headers = wgAuthHeaders();

  if (!headers.Authorization) return [];

  try {
    const res = await fetch(
      `${WG_BACKEND_URL}/api/notifications?limit=${limit}&offset=${offset}`,
      { headers }
    );

    if (!res.ok) {
      console.error('Failed to load notifications:', res.status);
      return [];
    }

    return await res.json();
  } catch (error) {
    console.error('Failed to load notifications:', error);
    return [];
  }
}


// For ad-hoc client-triggered notifications (e.g. escalating a risk level).
// Detections don't need this — the backend creates one automatically per detection.
async function wgAddNotification(title, body) {
  try {
    const res = await fetch(
      `${WG_BACKEND_URL}/api/notifications?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`,
      {
        method: 'POST',
        headers: wgAuthHeaders()
      }
    );

    if (!res.ok) {
      console.warn('Notification creation denied:', res.status);
    }
  } catch (e) {
    console.error('Failed to create notification:', e);
  }

  wgUpdateBadge();
}


async function wgMarkNotificationRead(id) {
  const user = JSON.parse(localStorage.getItem('wg_user') || 'null');

  if (!user || !user.loggedIn || !user.token) return false;

  try {
    const res = await fetch(`${window.WG_BACKEND_URL}/api/notifications/${id}/read`, {
      method: 'POST',
      headers: wgAuthHeaders()
    });

    if (!res.ok) return false;

    await wgUpdateBadge();
    return true;
  } catch (e) {
    console.error('Failed to mark notification as read:', e);
    return false;
  }
}



async function wgMarkAllNotificationsRead() {
  const user = JSON.parse(localStorage.getItem('wg_user') || 'null');

  if (!user || !user.loggedIn || !user.token) return false;

  try {
    const res = await fetch(`${window.WG_BACKEND_URL}/api/notifications/read-all`, {
      method: 'POST',
      headers: wgAuthHeaders()
    });

    if (!res.ok) return false;

    await wgUpdateBadge();
    return true;
  } catch (e) {
    console.error('Failed to mark all notifications as read:', e);
    return false;
  }
}


async function wgUpdateBadge() {
  const list = await wgGetNotifications();
  const unread = list.filter(n => !n.read).length;
  document.querySelectorAll('.wg-nav-badge').forEach(function (el) {
    if (unread > 0) {
      el.textContent = unread > 9 ? '9+' : String(unread);
      el.style.display = '';
    } else {
      el.style.display = 'none';
    }
  });
}

// ── Global alert popup — appears on every page automatically ──
// Creates its own small toast element (no page markup required).
function wgShowGlobalAlert(html) {
  let el = document.getElementById('wgGlobalAlert');
  if (!el) {
    el = document.createElement('div');
    el.id = 'wgGlobalAlert';
    el.style.cssText = `
      position: fixed; bottom: 24px; right: 24px; z-index: 99999;
      background: #2D4A2D; color: #fff; padding: 12px 16px; border-radius: 10px;
      font-family: 'Inter', sans-serif; font-size: 13.5px; box-shadow: 0 6px 20px rgba(0,0,0,0.22);
      display: flex; align-items: center; gap: 10px; max-width: 320px;
      transform: translateY(12px); opacity: 0; transition: transform .25s ease, opacity .25s ease;
    `;
    el.innerHTML = `
      <span style="font-size:16px;">🐾</span>
      <span id="wgGlobalAlertText" style="flex:1;"></span>
      <button id="wgGlobalAlertClose" style="background:none;border:none;color:rgba(255,255,255,.7);cursor:pointer;font-size:14px;padding:0;">✕</button>
    `;
    document.body.appendChild(el);
    el.querySelector('#wgGlobalAlertClose').onclick = () => wgHideGlobalAlert();
  }
  el.querySelector('#wgGlobalAlertText').innerHTML = html;
  requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'translateY(0)'; });
  clearTimeout(window._wgGlobalAlertTimer);
  window._wgGlobalAlertTimer = setTimeout(wgHideGlobalAlert, 6000);
}
function wgHideGlobalAlert() {
  const el = document.getElementById('wgGlobalAlert');
  if (!el) return;
  el.style.opacity = '0';
  el.style.transform = 'translateY(12px)';
}

// ── One shared WebSocket per page ──
// Individual pages should NOT open their own '/ws/alerts' connection — instead
// listen for the 'wg-ws-message' event on window, which fires with the same
// parsed data for every message (detections AND escalations). This avoids
// multiple competing sockets per page, which was causing inconsistent delivery.
(function wgInitSharedSocket() {
  try {
    const ws = new WebSocket(WG_BACKEND_URL.replace('http', 'ws') + '/ws/alerts');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'escalation') {
        wgShowGlobalAlert(`<strong>Risk escalated:</strong> ${data.species} → ${data.risk_level} by ${data.escalated_by}`);
      } else {
        wgShowGlobalAlert(`<strong>New detection:</strong> ${data.species} — reported by ${data.reported_by}`);
      }
      wgUpdateBadge();
      window.dispatchEvent(new CustomEvent('wg-ws-message', { detail: data }));
    };
  } catch (e) { /* WebSocket unavailable — no live updates, rest of the app still works */ }
})();
