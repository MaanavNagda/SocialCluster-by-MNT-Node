"""WhatsApp Web unread-chat DOM scraper.

Selectors below were confirmed live during development against
web.whatsapp.com by sending a real message and inspecting the resulting
unread chat row: the "icon-unread-count" badge, its ancestor
"cell-frame-container" row, the row's title span, and the
"last-msg-status" preview text all matched real markup.
"""

NAME = "WhatsApp"
STATUS = "verified"

SCRIPT = r"""
(function() {
    try {
        var items = [];
        var badges = document.querySelectorAll('[data-testid="icon-unread-count"]');
        for (var i = 0; i < badges.length; i++) {
            var badge = badges[i];
            var countText = badge.textContent.trim();
            var row = badge.closest('div[data-testid="cell-frame-container"]');
            if (!row) continue;

            var titleEl = row.querySelector('span[dir="auto"][title]');
            var sender = titleEl ? titleEl.getAttribute('title') : null;
            if (!sender) continue;

            var previewEl = row.querySelector('[data-testid="last-msg-status"] span[dir="ltr"]');
            var preview = previewEl ? previewEl.textContent.trim() : '';

            items.push({ sender: sender, count: countText, preview: preview });
        }
        return JSON.stringify({ items: items });
    } catch (e) {
        return JSON.stringify({ error: String(e) });
    }
})();
"""
