import xml.sax.saxutils as saxutils


def render_tray_icon(badge_count=0, primary_color="#9b59b6"):
    badge = ""
    if badge_count != 0:
        badge = f'<circle cx="48" cy="16" r="12" fill="#ff3b30" />\n  '
        if badge_count > 0:
            text = str(badge_count) if badge_count < 100 else "99+"
            badge += f'<text x="48" y="20" font-size="10" fill="#ffffff" text-anchor="middle" font-family="sans-serif" font-weight="bold">{saxutils.escape(text)}</text>'
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="{saxutils.escape(primary_color)}"/>
  <text x="32" y="40" font-size="22" fill="#ffffff" text-anchor="middle" font-family="sans-serif" font-weight="bold">SC</text>
  {badge}
</svg>"""
    return svg
