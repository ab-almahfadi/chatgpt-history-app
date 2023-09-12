from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import openai
import toml
from markdown import markdown
from collections import defaultdict
import statistics

from history import load_conversations
from utils import time_group, human_readable_time
from llms import load_create_embeddings, search_similar, TYPE_CONVERSATION, TYPE_MESSAGE


# Initialize FastAPI app
app = FastAPI()
api_app = FastAPI(title="API")

conversations = load_conversations('data/conversations.json')

try:
    SECRETS = toml.load("data/secrets.toml")
    OPENAI_ENABLED = True
except:
    print("-- No secrets found. Not able to access the OpenAI API.")
    OPENAI_ENABLED = False

if OPENAI_ENABLED:
    openai.organization = SECRETS["openai"]["organization"]
    openai.api_key = SECRETS["openai"]["api_key"]

    embeddings, embeddings_ids, embeddings_index = load_create_embeddings("data/embeddings.db", conversations)


# All conversation items
@api_app.get("/conversations")
def get_conversations():
    conversations_data = [{
        "group": time_group(conv.created),
        "id": conv.id, 
        "title": conv.title_str,
        "created": conv.created_str,
        } for conv in conversations]
    return JSONResponse(content=conversations_data)


# All messages from a specific conversation by its ID
@api_app.get("/conversations/{conv_id}/messages")
def get_messages(conv_id: str):
    conversation = next((conv for conv in conversations if conv.id == conv_id), None)
    if not conversation:
        return JSONResponse(content={"error": "Invalid conversation ID"}, status_code=404)

    messages = [{"text": markdown(msg.text),
                 "role": msg.role, 
                 "created": msg.created_str
                 } for msg in conversation.messages if msg]
    response = {
        "conversation_id": conversation.id,
        "messages": messages
    }
    return JSONResponse(content=response)


@api_app.get("/activity")
def get_activity():
    activity_by_day = defaultdict(int)

    for conversation in conversations:
        for message in conversation.messages:
            day = message.created.date()
            activity_by_day[day] += 1
    
    activity_by_day = {str(k): v for k, v in sorted(dict(activity_by_day).items())}

    return JSONResponse(content=activity_by_day)


@api_app.get("/statistics")
def get_statistics():
    # Calculate the min, max, and average lengths
    lengths = []
    for conv in conversations:
        start_time = conv.created
        end_time = max(msg.created for msg in conv.messages) if conv.messages else start_time
        length = end_time - start_time
        lengths.append((length.total_seconds(), conv.id))

    # Sort conversations by length
    lengths.sort(reverse=True)

    if lengths:
        min_threshold_seconds = 1
        filtered_min_lengths = [l for l in lengths if l[0] >= min_threshold_seconds]
        min_length = human_readable_time(min(filtered_min_lengths)[0])
        max_length = human_readable_time(max(lengths)[0])
        avg_length = human_readable_time(statistics.mean([l[0] for l in lengths]))
    else:
        min_length = max_length = avg_length = "N/A"

    # Generate links for the top 3 longest conversations
    top_3_links = "".join([f"<a href='https://chat.openai.com/c/{l[1]}' target='_blank'>Chat {chr(65 + i)}</a><br/>" 
                   for i, l in enumerate(lengths[:3])])

    return JSONResponse(content={
        "Last chat message": max(conv.created for conv in conversations).strftime('%Y-%m-%d'),
        "First chat message": min(conv.created for conv in conversations).strftime('%Y-%m-%d'),
        "Shortest conversation": min_length,
        "Longest conversation": max_length,
        "Average chat length": avg_length,
        "Top longest chats": top_3_links
    })


# Search conversations and messages
@api_app.get("/search")
def search_conversations(query: str = Query(..., min_length=3, description="Search query")):

    def add_search_result(search_results, result_type, conv, msg):
        search_results.append({
            "type": result_type,
            "id": conv.id,
            "title": conv.title_str,
            "text": markdown(msg.text),
            "role": msg.role,
            "created": conv.created_str if result_type == "conversation" else msg.created_str,
        })

    def find_conversation_by_id(conversations, id):
        return next((conv for conv in conversations if conv.id == id), None)

    def find_message_by_id(messages, id):
        return next((msg for msg in messages if msg.id == id), None)

    search_results = []

    if query.startswith('"') and query.endswith('"'):
        query = query[1:-1]
        query_exact = True
    else:
        query_exact = False

    if OPENAI_ENABLED and not query_exact:
        for _id in search_similar(query, embeddings_ids, embeddings_index):
            conv = find_conversation_by_id(conversations, embeddings[_id]["conv_id"])            
            if conv:
                result_type = embeddings[_id]["type"]
                if result_type == TYPE_CONVERSATION:
                    msg = conv.messages[0]
                else:
                    msg = find_message_by_id(conv.messages, _id)
                
                if msg:
                    add_search_result(search_results, result_type, conv, msg)
    else:
        for conv in conversations:
            query_lower = query.lower()
            if (conv.title or "").lower().find(query_lower) != -1:
                add_search_result(search_results, "conversation", conv, conv.messages[0])

            for msg in conv.messages:
                if msg and msg.text.lower().find(query_lower) != -1:
                    add_search_result(search_results, "message", conv, msg)

            if len(search_results) >= 10:
                break

    return JSONResponse(content=search_results)


app.mount("/api", api_app)
app.mount("/", StaticFiles(directory="static", html=True), name="Static")
