from dotenv import load_dotenv
import chainlit as cl
import asyncio
import re
import json

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

def extract_json_from_response(text):
    # Regex pattern to find JSON block enclosed in ```json ... ```
    json_pattern = r'```json(.*?)```'
    
    # Search for the JSON block in the response
    json_match = re.search(json_pattern, text, re.DOTALL)
    
    if json_match:
        json_str = json_match.group(1).strip()  # Extract the JSON block
        try:
            parsed_json = json.loads(json_str)  # Parse the JSON block
            #print(f"Parsed JSON: {parsed_json}")
            return parsed_json
        except json.JSONDecodeError as e:
            #print(f"Error parsing JSON: {e}")
            return None
    else:
        return None

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
async def call_function(function_json):
    if function_json["function_name"] == "get_now_playing_movies":
        response = get_now_playing_movies()
    elif function_json["function_name"] == "get_showtimes":
        response = get_showtimes(function_json["params"]["title"], function_json["params"]["location"])
    elif function_json["function_name"] == "buy_ticket":
        theater = function_json["params"]["theater"]
        title = function_json["params"]["title"]
        showtime = function_json["params"]["showtime"]
        
        # Call the confirmation function instead of buying directly
        response = await confirm_ticket_purchase(theater, title, showtime)
    elif function_json["function_name"] == "confirm_ticket_purchase":
        # Confirm ticket purchase
        theater = function_json["params"]["theater"]
        title = function_json["params"]["title"]
        showtime = function_json["params"]["showtime"]
        
        # Assume this function returns a message about the ticket purchase
        response = buy_ticket(theater, title, showtime)
    elif function_json["function_name"] == "get_reviews":
        response = get_reviews()
    else:
        response = "Invalid function"
    
    return response

@observe
async def confirm_ticket_purchase(theater, title, showtime):
    # This function generates the confirmation message
    confirmation_message = (
        f"Please confirm your ticket purchase:\n"
        f"Theater: {theater}\n"
        f"Movie: {title}\n"
        f"Showtime: {showtime}\n"
        "Type 'yes' to confirm or 'no' to cancel."
    )
    # Respond with the confirmation message as JSON
    return {
        "function_name": "confirm_ticket_purchase",
        "params": {
            "theater": theater,
            "title": title,
            "showtime": showtime,
            "confirmation_message": confirmation_message
        }
    }

@observe
async def generate_response(client, message_history, gen_kwargs):
    response = await client.chat.completions.create(messages=message_history, **gen_kwargs)
    response_text = response.choices[0].message.content

    return response_text

async def get_user_confirmation(message_history):
    # Assume the user is prompted to confirm their purchase
    # Wait for the next message from the user after the confirmation prompt
    user_confirmation = cl.user_session.get("latest_user_message", "")
    
    while not user_confirmation:
        # Wait for a short duration and check again for user input
        await asyncio.sleep(1)
        user_confirmation = cl.user_session.get("latest_user_message", "")

    # Clear the latest user message after capturing it
    cl.user_session.set("latest_user_message", "")
    
    return user_confirmation

@cl.on_message
@observe
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    response_text = await generate_response(client, message_history, gen_kwargs)
    
    while True:
        parsed_json = extract_json_from_response(response_text)

        if parsed_json and "function_name" in parsed_json and parsed_json["function_name"] in function_names:
            matched_function = parsed_json["function_name"]
            print(f"Matched function: {matched_function}")

            if matched_function == "confirm_ticket_purchase":
                confirmation_message = parsed_json["params"]["confirmation_message"]
                await print_response(confirmation_message)

                # Wait for user confirmation
                user_response = await get_user_confirmation(message_history)

                if user_response.lower() == 'yes':
                    # Call the buy_ticket function if confirmed
                    function_response = await call_function(parsed_json)
                else:
                    function_response = "Ticket purchase canceled."
            else:
                function_response = await call_function(parsed_json)

            message_history.append({"role": "system", "content": function_response})
            response_text = await generate_response(client, message_history, gen_kwargs)
        else:
            break

    response_message = await print_response(response_text)
    message_history.append({"role": "assistant", "content": response_text})
    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()
