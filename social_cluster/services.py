DEFAULT_SERVICES = [
    {"name": "Facebook", "url": "https://www.facebook.com"},
    {"name": "Instagram", "url": "https://www.instagram.com"},
    {"name": "WhatsApp", "url": "https://web.whatsapp.com"},
    {"name": "YouTube", "url": "https://www.youtube.com"},
    {"name": "TikTok", "url": "https://www.tiktok.com"},
    {"name": "WeChat", "url": "https://web.wechat.com"},
    {"name": "Facebook Messenger", "url": "https://www.messenger.com"},
    {"name": "Telegram", "url": "https://web.telegram.org"},
    {"name": "LinkedIn", "url": "https://www.linkedin.com"},
    {"name": "Snapchat", "url": "https://web.snapchat.com"},
    {"name": "Reddit", "url": "https://www.reddit.com"},
    {"name": "Douyin", "url": "https://www.douyin.com"},
    {"name": "Kuaishou", "url": "https://www.kuaishou.com"},
    {"name": "Sina Weibo", "url": "https://weibo.com"},
    {"name": "Pinterest", "url": "https://www.pinterest.com"},
    {"name": "X", "url": "https://x.com"},
    {"name": "Tencent QQ", "url": "https://im.qq.com/index"},
    {"name": "Qzone", "url": "https://qzone.qq.com"},
    {"name": "Threads", "url": "https://www.threads.net"},
    {"name": "Quora", "url": "https://www.quora.com"},
    {"name": "Bilibili", "url": "https://www.bilibili.com"},
    {"name": "Xiaohongshu", "url": "https://www.xiaohongshu.com"},
    {"name": "JOSH", "url": "https://www.myjosh.in"},
    {"name": "Microsoft Teams", "url": "https://teams.microsoft.com"},
    {"name": "Baidu Tieba", "url": "https://tieba.baidu.com"},
    {"name": "Viber", "url": "https://www.viber.com"},
    {"name": "Discord", "url": "https://discord.com/channels/@me"},
    {"name": "imo", "url": "https://www.imo.im"},
    {"name": "Twitch", "url": "https://www.twitch.tv"},
    {"name": "Line", "url": "https://line.me"},
    {"name": "Slack", "url": "https://slack.com"},
    {"name": "Zoom", "url": "https://zoom.us"},
    {"name": "Google Workspace", "url": "https://workspace.google.com"},
    {"name": "Webex", "url": "https://www.webex.com"},
    {"name": "Asana", "url": "https://app.asana.com"},
    {"name": "Monday.com", "url": "https://monday.com"},
    {"name": "Trello", "url": "https://trello.com"},
    {"name": "Basecamp", "url": "https://basecamp.com"},
    {"name": "ClickUp", "url": "https://app.clickup.com"},
    {"name": "Notion", "url": "https://www.notion.so"},
    {"name": "Gmail", "url": "https://mail.google.com"},
    {"name": "Outlook", "url": "https://outlook.live.com"},
    {"name": "Yahoo Mail", "url": "https://mail.yahoo.com"},
    {"name": "Apple iCloud Mail", "url": "https://www.icloud.com/mail"},
    {"name": "ProtonMail", "url": "https://mail.proton.me"},
    {"name": "Zoho Mail", "url": "https://mail.zoho.com"},
    {"name": "AOL Mail", "url": "https://mail.aol.com"},
    {"name": "GMX Mail", "url": "https://www.gmx.com"},
    {"name": "Yandex Mail", "url": "https://mail.yandex.com"},
    {"name": "Mail.com", "url": "https://www.mail.com"},
]


def get_default_services():
    return [dict(s) for s in DEFAULT_SERVICES]


def get_service_by_name(name):
    for s in DEFAULT_SERVICES:
        if s["name"] == name:
            return dict(s)
    return None
