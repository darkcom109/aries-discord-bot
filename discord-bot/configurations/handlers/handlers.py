from .poll_handler import handle_create_poll
from .reminder_handler import handle_create_reminder
from .web_search_handler import handle_web_search

handlers = {
    "create_poll": handle_create_poll,
    "create_reminder": handle_create_reminder,
    "web_search": handle_web_search
}
