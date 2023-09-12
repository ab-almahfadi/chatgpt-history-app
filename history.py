import json
import sys
from typing import List, Union, Optional
from collections import OrderedDict
from datetime import datetime
from pydantic.v1 import BaseModel # v2 throws warnings


class Author(BaseModel):
    role: str


class Content(BaseModel):
    content_type: str
    parts: Optional[List[Union[str, OrderedDict[str, Union[str, float, bool]]]]]
    text: Optional[str]


# class MessageMetadata(BaseModel):
#     model_slug: Optional[str]
#     parent_id: Optional[str]


class Message(BaseModel):
    id: str
    author: Author
    create_time: Optional[float]
    update_time: Optional[float]
    content: Optional[Content]
#    metadata: MessageMetadata

    @property
    def text(self) -> str:
        if self.content:
            if self.content.text:
                return self.content.text
            elif self.content.parts:
                return " ".join(str(part) for part in self.content.parts)
        return ""
    
    @property
    def role(self) -> str:
        return self.author.role

    @property
    def created(self) -> datetime:
        return datetime.fromtimestamp(self.create_time)

    @property
    def created_str(self) -> str:
        return self.created.strftime('%Y-%m-%d %H:%M:%S')


class MessageMapping(BaseModel):
    id: str
    message: Optional[Message]


class Conversation(BaseModel):
    id: str
    title: Optional[str]
    create_time: float
    update_time: float
    mapping: OrderedDict[str, MessageMapping]

    @property
    def messages(self) -> List:
        return [msg.message for k, msg in self.mapping.items() if msg.message and msg.message.text]

    @property
    def created(self) -> datetime:
        return datetime.fromtimestamp(self.create_time)#.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def created_str(self) -> str:
        return self.created.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def updated(self) -> datetime:
        return datetime.fromtimestamp(self.update_time)

    @property
    def updated_str(self) -> str:
        return self.updated.strftime('%Y-%m-%d %H:%M:%S')


def load_conversations(path: str) -> List[Conversation]:
    with open(path, 'r') as f:
        conversations_json = json.load(f)

    # Load the JSON data into these models
    try:
        conversations = [Conversation(**conv) for conv in conversations_json]
        success = True
    except Exception as e:
        print(str(e))
        sys.exit(1)

    print(f"Successfully loaded {len(conversations)} conversations")
    return conversations