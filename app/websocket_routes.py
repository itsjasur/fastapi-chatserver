from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.websockets import WebSocketDisconnect
from websocket_manager import manager
from app.utils import get_user_info
from firebase_instance import database
from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore
import datetime

router = APIRouter()


@router.websocket("/ws/{access_token}")
async def websocket_endpoint(websocket: WebSocket, access_token: str):
    await websocket.accept()
    try:
        user_info = get_user_info(access_token)
        is_retailer = user_info["is_retailer"]
        print(user_info)
    except Exception as e:
        await websocket.close(code=1008, reason=str(e))
        # raise HTTPException(status_code=401, detail=str(e))
        return

    identifiers = [user_info["username"]] if is_retailer else user_info["agent_codes"]
    for identifier in identifiers:
        await manager.connect(websocket, identifier)

    # return fll chat rooms total_unread_counts for retailer and admin
    total_unread_count = 0
    search_field = "partner_code" if is_retailer else "agent_code"
    rooms_ref = database.collection("chat_rooms").where(filter=FieldFilter(search_field, "in", identifiers)).get()
    for room_ref in rooms_ref:
        room = room_ref.to_dict()
        total_unread_count += room.get("partner_unread_count", 0)
    print(f"total count: {total_unread_count}")
    await manager.active_connections[identifier].send_json({"type": "total_count", "total_unread_count": total_unread_count})

    try:
        while True:
            response = await websocket.receive_json()
            print(response)
            action = response.get("action")

            # disconnnect emitted from client side
            if action == "disconnect":
                manager.disconnect(identifier)
                await websocket.close(code=1008, reason="Client disconnected")

            if action == "join_room":
                if is_retailer:
                    agent_code = response.get("agentCode")
                    partner_code = user_info.get("username")
                    partner_name = user_info.get("name")

                    # chat_room_ref = database.collection("chat_rooms").document(room_id)
                    chat_rooms_ref = (
                        database.collection("chat_rooms")
                        .where(filter=FieldFilter("partner_code", "==", partner_code))
                        .where(filter=FieldFilter("agent_code", "==", agent_code))
                        .limit(1)
                        .get()
                    )

                    if len(chat_rooms_ref) > 0:
                        room_id = chat_rooms_ref[0].id

                    # creating or updating a room if room not found
                    else:
                        timestampt, doc_ref = database.collection("chat_rooms").add(
                            {
                                "agent_code": agent_code,
                                "partner_code": partner_code,
                                "partner_name": partner_name,
                                "agent_unread_count": 0,
                                "partner_unread_count": 0,
                            },
                        )
                        room_id = doc_ref.id

                    chats = getRoomChats(room_id)
                    print(chats)

                    await websocket.send_json({"type": "chats", "chats": chats, "room_id": room_id})

                    # chat_room_ref = database.collection("chat_rooms").document(room_id)
                    # chat_room_ref.update({"partner_unread_count": 0})

                else:
                    room_id = response.get("roomId")
                    print(room_id)
                    chats = getRoomChats(room_id)
                    await websocket.send_json({"type": "chats", "chats": chats})

                    # chat_room_ref = database.collection("chat_rooms").document(room_id)
                    # chat_room_ref.update({"agent_unread_count": 0})

            # when partner sends a new message
            if action == "new_message":
                room_id = response.get("roomId")
                text = response["text"]
                attachment_paths = response["attachmentPaths"]

                new_chat = {
                    "room_id": room_id,  # unique firestore id
                    "sender": partner_code,  # createdBy
                    "receiver": agent_code,  # admin code IK, SJ
                    "is_retailer": is_retailer,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "text": text,
                    "attachment_paths": attachment_paths,
                }

                database.collection("chats").add(new_chat)
                new_chat["timestamp"] = new_chat["timestamp"].isoformat()

                await manager.active_connections[identifier].send_json({"type": "new_chat", "new_chat": new_chat})

                # update agent unread count when partner sends a message
                chat_room_ref = database.collection("chat_rooms").document(room_id)

                print(chat_room_ref.get().to_dict())

                # chat_room_ref.update({"agent_unread_count": firestore.Increment(1)})

            # if admin
            if action == "get_chat_rooms":
                rooms = []
                search_text = response.get("searchText", None)

                rooms_ref = database.collection("chat_rooms").where(filter=FieldFilter("agent_code", "in", identifiers)).get()

                for room_ref in rooms_ref:
                    room_id = room_ref.id
                    room = room_ref.to_dict()
                    room["room_id"] = room_id
                    rooms.append(room)

                if search_text and search_text not in ["", " "] != "":
                    rooms = [room for room in rooms if search_text.lower() in room["partner_name"].lower()]

                await manager.active_connections[identifier].send_json({"type": "chat_rooms", "rooms": rooms})

    except WebSocketDisconnect:
        for identifier in identifiers:
            manager.disconnect(identifier)
        await manager.broadcast(f"User {user_info['name']} left the chat")


def getRoomChats(room_id: str):
    chats_ref = (
        database.collection("chats")
        .where(filter=FieldFilter("room_id", "==", room_id))
        .order_by("timestamp", direction=firestore.Query.ASCENDING)
        .get()
    )

    chats = []
    for chat_ref in chats_ref:
        chat_id = chat_ref.id
        chat = chat_ref.to_dict()
        chat["chat_id"] = chat_id  # chat.id is being added as dict param too
        chat["timestamp"] = chat["timestamp"].isoformat()
        chats.append(chat)

    # print(chats)
    return chats
