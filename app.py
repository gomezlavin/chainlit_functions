from dotenv import load_dotenv
import chainlit as cl
import asyncio
import re

load_dotenv()

from langfuse.decorators import observe
from langfuse.openai import AsyncOpenAI
from prompts import SYSTEM_PROMPT
from movie_functions import (
    get_now_playing_movies,
    get_showtimes,
    buy_ticket,
    get_reviews
)
function_names = ["get_now_playing_movies", "get_showtimes", "buy_ticket", "get_reviews"]
 
client = AsyncOpenAI()

gen_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.2,
    "max_tokens": 500
}

@observe
@cl.on_chat_start
def on_chat_start():    
    message_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    cl.user_session.set("message_history", message_history)

@observe
async def get_response(client, message_history, gen_kwargs):
    response_string = ""
    stream = await client.chat.completions.create(messages=message_history, stream=True, **gen_kwargs)
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            response_string += token

    return [response_string,stream]

@observe
async def print_response(response_text):
    tokens = re.split(r'(\s+)', response_text)  # Splitting while keeping whitespace

    response_message = cl.Message(content="")
    await response_message.send()

    for token in tokens:
        await response_message.stream_token(token)
        await asyncio.sleep(0.02)  # Delay of x seconds between each token

    await response_message.update()

    return response_message

@observe
async def call_function(function_name):
    if function_name == "get_now_playing_movies":
        response = get_now_playing_movies()
    elif function_name == "get_showtimes":
        response = get_showtimes()
    elif function_name == "buy_ticket":
        response = buy_ticket()
    elif function_name == "get_reviews":
        response = get_reviews()
    else:
        response = "Invalid function"
    
    return response

@observe
async def generate_response(client, message_history, gen_kwargs):
    response = await client.chat.completions.create(messages=message_history, **gen_kwargs)
    response_text = response.choices[0].message.content

    return response_text

@cl.on_message
@observe
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    response_text = await generate_response(client, message_history, gen_kwargs)

    if response_text in function_names:
        function_response = await call_function(response_text.lower())
        message_history.append({"role": "system", "content": function_response})
        response_text = await generate_response(client, message_history, gen_kwargs)

    response_message = await print_response(response_text)
    message_history.append({"role": "assistant", "content": response_text})
    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()
