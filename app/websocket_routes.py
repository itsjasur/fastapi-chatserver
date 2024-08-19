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
        # print(user_info)

    except Exception as e:
        await websocket.close(code=1008, reason=str(e))
        return

    identifiers = [user_info["username"]] if is_retailer else user_info["agent_codes"]
    for identifier in identifiers:
        await manager.connect(websocket, identifier)

    # sending total count when initial connectin established
    total_count = get_total_unread_count(is_retailer, identifiers)
    await websocket.send_json({"type": "total_count", "total_unread_count": total_count})

    try:
        while True:
            response = await websocket.receive_json()
            # print(response)
            action = response.get("action")

            print("connection active")

            # disconnnect emitted from client side
            if action == "disconnect":
                manager.disconnect(identifier)
                await websocket.close(code=1008, reason="Client disconnected")

            if action == "join_room":
                if is_retailer:
                    agent_code = response.get("agentCode")
                    partner_code = user_info.get("username")
                    partner_name = user_info.get("name")

                    if not agent_code or not partner_code:
                        manager.disconnect(identifier)
                        return

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

                    chats = get_room_chats(room_id)
                    # print(chats)
                    await websocket.send_json({"type": "chats", "chats": chats, "room_id": room_id})

                    # when user joins a chatroom, unread_count is reset to 0
                    # chat_room_ref = database.collection("chat_rooms").document(room_id)
                    # chat_room_ref.update({"partner_unread_count": 0})

                else:
                    room_id = response.get("roomId")
                    chats = get_room_chats(room_id)
                    await websocket.send_json({"type": "chats", "chats": chats})

            if action == "reset_room_unread_count":
                room_id = response.get("roomId")
                print(room_id)

                chat_room_ref = database.collection("chat_rooms").document(room_id)

                update_field = "partner_unread_count" if is_retailer else "agent_unread_count"
                chat_room_ref.update({update_field: 0})

                # whenever room unread count reset total unread count also reset
                total_count = get_total_unread_count(is_retailer, identifiers)
                await manager.send_json_to_identifiers(content={"type": "total_count", "total_unread_count": total_count}, identifiers=identifiers)

            # when partner sends a new message
            if action == "new_message":
                room_id = response.get("roomId")

                text = response["text"]
                attachment_paths = response["attachmentPaths"]

                # first getting room details by room id and then creating a new message
                chat_room_ref = database.collection("chat_rooms").document(room_id)
                room_details = chat_room_ref.get().to_dict()

                print(room_details)

                agent_code = room_details["agent_code"]
                partner_code = room_details["partner_code"]

                new_chat = {
                    "room_id": room_id,
                    "sender": partner_code if is_retailer else agent_code,
                    "receiver": agent_code if is_retailer else partner_code,
                    "is_retailer": is_retailer,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "text": text,
                    "attachment_paths": attachment_paths,
                }

                database.collection("chats").add(new_chat)
                new_chat["timestamp"] = new_chat["timestamp"].isoformat()

                # emitting new chat to both sender and receiver
                await manager.send_json_to_identifiers(content={"type": "new_chat", "new_chat": new_chat}, identifiers=[partner_code, agent_code])

                # update unread count of receiver
                update_field = "agent_unread_count" if is_retailer else "partner_unread_count"
                chat_room_ref.update({update_field: firestore.Increment(1)})

                # after each new message emit total_count
                await manager.send_json_to_identifier(
                    content={"type": "total_count", "total_unread_count": room_details["partner_unread_count"]},
                    identifier=room_details["partner_code"],
                )
                await manager.send_json_to_identifier(
                    content={"type": "total_count", "total_unread_count": room_details["agent_unread_count"]},
                    identifier=room_details["agent_code"],
                )

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


def get_room_chats(room_id: str):
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


def get_total_unread_count(is_retailer: bool, identifiers: str):
    # return fll chat rooms total_unread_counts of given identifiers (agent codes or partner code)
    total_unread_count = 0

    search_field = "partner_code" if is_retailer else "agent_code"
    find_field = "partner_unread_count" if is_retailer else "agent_unread_count"

    rooms_ref = database.collection("chat_rooms").where(filter=FieldFilter(search_field, "in", identifiers)).get()
    for room_ref in rooms_ref:
        room = room_ref.to_dict()
        total_unread_count += room.get(find_field, 0)

    print(total_unread_count)

    return total_unread_count
