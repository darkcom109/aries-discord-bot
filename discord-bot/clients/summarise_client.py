import base64

from configurations.prompts.summarise_prompt import get_summarise_prompt
from clients.ollama_client import ollama_request

async def summarise_response(history, prompt, image_data: bytes | None = None):
    messages = [
        {"role": "system", "content": get_summarise_prompt()}
    ]

    messages.extend(
        {"role": message.role, "content": message.content}
        for message in history
    )

    user_message = {
        "role": "user",
        "content": prompt
    }

    if image_data is not None:
        user_message["images"] = [
            base64.b64encode(image_data).decode("ascii")
        ]

    messages.append(user_message)

    return await ollama_request(messages)
