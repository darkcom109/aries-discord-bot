tfl_tool = {
    "type": "function",
    "function": {
        "name": "get_tfl",
        "description": "Get current London TfL status, stop IDs, live arrivals, or journeys departing now. Prefer this over web_search for TfL. Ask for missing locations; never invent stop IDs. This only reads data, not alerts or bookings.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "stops", "arrivals", "journey"]},
                "line": {"type": "string", "description": "Optional rail line for status, or route filter for arrivals."},
                "stop": {"type": "string", "description": "Stop/station name or TfL stop ID; required for stops and arrivals."},
                "origin": {"type": "string", "description": "Journey origin: station, postcode or coordinates."},
                "destination": {"type": "string", "description": "Journey destination: station, postcode or coordinates."},
            },
            "required": ["action"],
        },
    },
}
