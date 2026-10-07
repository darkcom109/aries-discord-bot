from configurations.handlers import handle_create_poll, handle_create_reminder, handle_web_search

handlers = {
    "create_poll": handle_create_poll,
    "create_reminder": handle_create_reminder,
    "web_search": handle_web_search
}