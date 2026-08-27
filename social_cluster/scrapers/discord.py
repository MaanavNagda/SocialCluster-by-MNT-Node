"""Discord (web) unread-DM DOM scraper.

STATUS: experimental. Discord's DOM uses hashed, build-specific CSS class
names that this scraper deliberately avoids, relying instead on the more
stable `data-list-item-id` attribute (used by Discord's own accessibility
tree and long relied upon by third-party Discord tooling) plus aria-label
text. None of this has been confirmed against a live unread Discord DM in
this environment yet -- it has not been tested. If it does not fire real
notifications, the app's fallback "you have activity" notification still
applies (see main.py's fallback poll), so this is safe to ship as-is, but
selectors likely need one round of live verification/refinement (the same
process used to nail down WhatsApp's selectors: run the app, get a real
unread DM, and inspect what "debug" reports).
"""

NAME = "Discord"
STATUS = "experimental"

SCRIPT = r"""
(function() {
    try {
        var items = [];
        var debug = [];
        var rows = document.querySelectorAll('[data-list-item-id^="private-channels___"]');
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var badge = row.querySelector('[aria-label*="unread" i], [aria-label*="mention" i], [class*="numberBadge" i]');
            if (!badge) continue;

            var labelText = badge.getAttribute('aria-label') || badge.textContent || '';
            var countMatch = labelText.match(/\d+/);
            var count = countMatch ? countMatch[0] : '1';

            var avatar = row.querySelector('img[alt]');
            var sender = avatar ? avatar.getAttribute('alt') : (row.getAttribute('aria-label') || 'Discord');

            var previewEl = row.querySelector('[class*="subtext" i]');
            var preview = previewEl ? previewEl.textContent.trim() : '';

            items.push({ sender: sender, count: count, preview: preview });
            debug.push(row.outerHTML.slice(0, 800));
        }
        return JSON.stringify({ items: items, debug: debug });
    } catch (e) {
        return JSON.stringify({ error: String(e) });
    }
})();
"""
