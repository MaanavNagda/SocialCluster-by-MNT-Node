"""Snapchat (web) unread-chat DOM scraper.

STATUS: experimental. Snapchat's web client DOM structure has not been
inspected in this environment at all (no live selectors confirmed, unlike
WhatsApp). This uses broad, generic heuristics (aria-label/class name
containing "unread", nearest list-like ancestor, nearest img[alt] for a
sender name) as a starting point only. Expect this to need a live
verification/refinement pass (same iterative process used for WhatsApp)
once there is an actual unread Snapchat conversation to test against.
Until then the app's fallback "you have activity" notification covers
this service if these selectors don't match anything.

NOTE: an earlier version of this selector also matched `[class*="badge" i]`,
which is far too generic -- it matched persistent, always-present UI chrome
(streak counters, verification/story badges, etc.) unrelated to unread
messages, causing a permanent false-positive unread count on every load
regardless of actual activity. Removed in favor of "unread"-only matches,
which are far more likely to correlate with genuine unread state.
"""

NAME = "Snapchat"
STATUS = "experimental"

SCRIPT = r"""
(function() {
    try {
        var items = [];
        var debug = [];
        var badgeEls = document.querySelectorAll('[aria-label*="unread" i], [class*="unread" i]');
        for (var i = 0; i < Math.min(badgeEls.length, 10); i++) {
            var badge = badgeEls[i];
            var row = badge.closest('li, [role="listitem"], [role="button"]') || badge.parentElement;
            if (!row) continue;

            var avatar = row.querySelector('img[alt]');
            var sender = avatar ? avatar.getAttribute('alt') : (row.getAttribute('aria-label') || 'Snapchat');

            var labelText = badge.getAttribute('aria-label') || badge.textContent || '';
            var countMatch = labelText.match(/\d+/);
            var count = countMatch ? countMatch[0] : '1';

            items.push({ sender: sender, count: count, preview: '' });
            debug.push(row.outerHTML.slice(0, 800));
        }
        return JSON.stringify({ items: items, debug: debug });
    } catch (e) {
        return JSON.stringify({ error: String(e) });
    }
})();
"""
