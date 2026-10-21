from clients.tfl_client import TflError
from configurations.helpers.response_helper import send_answer
from database import save_message


async def tfl_answer(client, arguments) -> str:
    if not isinstance(arguments, dict):
        return "I couldn't understand the TfL request. Try `/tfl status`, `/tfl stops`, or `/tfl journey`."
    try:
        action = arguments.get("action")
        if action == "status":
            return await client.status(arguments.get("line"))
        if action == "stops":
            return await client.stops(arguments.get("stop"))
        if action == "arrivals":
            return await client.arrivals(arguments.get("stop"), arguments.get("line"))
        if action == "journey":
            return await client.journey(arguments.get("origin"), arguments.get("destination"))
        return "Choose TfL status, stops, arrivals, or a journey. Use `/tfl watch` to enable private line alerts."
    except TflError as error:
        return str(error)


async def handle_get_tfl(interaction, function, guild_id, channel_id, user_id):
    answer = await tfl_answer(interaction.client.tfl, function.get("arguments", {}))
    await save_message(guild_id, channel_id, user_id, "assistant", answer)
    await send_answer(interaction, answer)
