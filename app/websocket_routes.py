from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.websockets import WebSocketDisconnect
from websocket_manager import manager
from app.utils import get_user_info, send_multiple_notifications
from firebase_instance import database
from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore
import datetime
import sys
from starlette.websockets import WebSocketState

router = APIRouter()


@router.websocket("/ws/{access_token}")
async def websocket_endpoint(websocket: WebSocket, access_token: str):
    await websocket.accept()

    try:
        if access_token is None or access_token == "null" or access_token == "":
            print("Access token invalid error")
            sys.stdout.flush()
            raise Exception("Access token invalid error")

        user_info = get_user_info(access_token)
        is_retailer = user_info["is_retailer"]
        # print(user_info)
        sys.stdout.flush()
    # print(user_info)

    except Exception as e:
        print(e)
        await websocket.close(code=1008, reason=str(e))
        return

    identifier = user_info["username"] if is_retailer else user_info["agent_code"]
    await manager.connect(websocket, identifier)

    # sending total count when initial connectin established
    total_count = get_total_unread_count(is_retailer, identifier)
    await websocket.send_json({"type": "total_count", "total_unread_count": total_count})

    try:
        while True:

            response = await websocket.receive_json()
            action = response.get("action")
            # print(response)
            # print(action)
            # print("connection active")

            if action == "update_fcm_token":
                print("update_fcm_token called!")
                fcm_token = response.get("fcmToken", None)
                agent_ref = database.collection("users").document(identifier)
                agent_ref.set({"fcm_tokens": firestore.ArrayUnion([fcm_token])}, merge=True)

                print(fcm_token)

            # disconnnect emitted from client side
            if action == "disconnect":
                manager.disconnect(identifier)
                await websocket.close(code=1008, reason="Client disconnected")

            if action == "get_chat_rooms":
                rooms = []
                search_text = response.get("searchText", None)

                search_field = "partner_code" if is_retailer else "agent_code"

                rooms_ref = database.collection("chat_rooms").where(filter=FieldFilter(search_field, "==", identifier)).get()

                for room_ref in rooms_ref:
                    room_id = room_ref.id
                    room = room_ref.to_dict()
                    room["room_id"] = room_id
                    rooms.append(room)

                # search is available for admin only
                if not is_retailer and search_text and search_text not in ["", " "] != "":
                    rooms = [room for room in rooms if search_text.lower() in room["partner_name"].lower()]

                await manager.send_json_to_identifier({"type": "chat_rooms", "rooms": rooms}, identifier)

            if action == "join_new_room":
                if is_retailer:  # partner
                    agent_code = response.get("agentCode")
                    partner_code = user_info.get("username")
                    partner_name = user_info.get("name")

                else:  # admin
                    agent_code = user_info.get("agent_code")
                    partner_code = response.get("partnerCode", None)
                    partner_name = response.get("partnerName", None)

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
                    # room_id = chat_rooms_ref[0].id
                    room_info = chat_rooms_ref[0].to_dict()
                    room_id = chat_rooms_ref[0].id

                # creating a room if room not found
                else:
                    room_id, room_info = await add_new_room(agent_code=agent_code, partner_code=partner_code, partner_name=partner_name)

                chats = get_room_chats(room_id)
                await websocket.send_json({"type": "room_chats", "chats": chats, "room_id": room_id, "room_info": room_info})

            if action == "join_room":
                room_id = response.get("roomId", None)

                chats = get_room_chats(room_id)
                await websocket.send_json({"type": "room_chats", "chats": chats, "room_id": room_id, "room_info": None})

            if action == "reset_room_unread_count":
                room_id = response.get("roomId")
                # print(room_id)
                chat_room_ref = database.collection("chat_rooms").document(room_id)
                update_field = "partner_unread_count" if is_retailer else "agent_unread_count"
                chat_room_ref.update({update_field: 0})

                # emitting room unread_count
                chat_room = chat_room_ref.get().to_dict()

                # emit room modified after each new chat
                await manager.send_json_to_identifier(
                    content={"type": "room_modified", "modified_room": chat_room}, identifier=chat_room["agent_code"]
                )
                await manager.send_json_to_identifier(
                    content={"type": "room_modified", "modified_room": chat_room}, identifier=chat_room["partner_code"]
                )

                # whenever room unread count reset total unread count also reset
                total_count = get_total_unread_count(is_retailer, identifier)
                await manager.send_json_to_identifier(content={"type": "total_count", "total_unread_count": total_count}, identifier=identifier)

            # when partner sends a new message
            if action == "new_message":
                room_id = response.get("roomId")

                text = response["text"]
                attachment_paths = response["attachmentPaths"]

                # first getting room details by room id and then creating a new message
                chat_room_ref = database.collection("chat_rooms").document(room_id)
                room_details = chat_room_ref.get().to_dict()
                # print(room_details)

                agent_code = room_details["agent_code"]
                partner_code = room_details["partner_code"]

                new_chat = {
                    "room_id": room_id,
                    "sender": partner_code if is_retailer else agent_code,
                    "receiver": agent_code if is_retailer else partner_code,
                    "is_retailer": is_retailer,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "sender_agent_info": None,
                    "text": text,
                    "attachment_paths": attachment_paths,
                }

                if not is_retailer:
                    new_chat["sender_agent_info"] = {
                        "code": user_info["username"],
                        "name": user_info["name"],
                    }

                database.collection("chats").add(new_chat)
                new_chat["timestamp"] = new_chat["timestamp"].isoformat()

                # emitting new chat to both sender and receiver
                await manager.send_json_to_identifier(content={"type": "new_chat", "new_chat": new_chat}, identifier=partner_code)
                await manager.send_json_to_identifier(content={"type": "new_chat", "new_chat": new_chat}, identifier=agent_code)

                # update unread count of receiver
                update_field = "agent_unread_count" if is_retailer else "partner_unread_count"
                chat_room_ref.update({update_field: firestore.Increment(1)})

                # need to get room details again after changes
                chat_room = chat_room_ref.get().to_dict()
                # print(chat_room)

                # after each new message emit total_count
                await manager.send_json_to_identifier(
                    content={"type": "total_count", "total_unread_count": chat_room["partner_unread_count"]}, identifier=partner_code
                )

                await manager.send_json_to_identifier(
                    content={"type": "total_count", "total_unread_count": chat_room["agent_unread_count"]}, identifier=agent_code
                )

                # emit room modified after each new chat
                await manager.send_json_to_identifier(content={"type": "room_modified", "modified_room": chat_room}, identifier=agent_code)
                await manager.send_json_to_identifier(content={"type": "room_modified", "modified_room": chat_room}, identifier=partner_code)

                if is_retailer:
                    # notification is sent here
                    if agent_code is not None:
                        # when partner sends message, agent receives notification
                        agent_ref = database.collection("users").document(agent_code).get()
                        if agent_ref.exists:
                            fcm_tokens = agent_ref.to_dict()["fcm_tokens"]
                            name = user_info["name"]
                            if len(fcm_tokens) > 0:
                                send_multiple_notifications(
                                    fcm_tokens=fcm_tokens,
                                    title=f"{name}이 메시지를 보냈어요!",
                                    body=text,
                                    chat_room_id=room_id,
                                )

                else:
                    # notification is sent here
                    if partner_code is not None:
                        # when agent sends message, partner receives notification
                        partner_ref = database.collection("users").document(partner_code).get()
                        if partner_ref.exists:
                            fcm_tokens = partner_ref.to_dict()["fcm_tokens"]
                            if len(fcm_tokens) > 0:
                                send_multiple_notifications(
                                    fcm_tokens=fcm_tokens,
                                    title=f"메시지를 받았습니다",
                                    body=text,
                                    chat_room_id=room_id,
                                )

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for {identifier}")
    except Exception as e:
        print(f"Error in websocket: {str(e)}")
        await websocket.send_json({"type": "error", "message": "Internal server error"})
    finally:
        if identifier:
            manager.disconnect(websocket, identifier)
        # await websocket.close()
        if not websocket.client_state == WebSocketState.DISCONNECTED:
            await websocket.close()


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


def get_total_unread_count(is_retailer: bool, identifier: str):
    # return fll chat rooms total_unread_counts of given identifier (agent code or partner code)
    total_unread_count = 0

    search_field = "partner_code" if is_retailer else "agent_code"
    find_field = "partner_unread_count" if is_retailer else "agent_unread_count"

    rooms_ref = database.collection("chat_rooms").where(filter=FieldFilter(search_field, "==", identifier)).get()
    for room_ref in rooms_ref:
        room = room_ref.to_dict()
        total_unread_count += room.get(find_field, 0)

    print(total_unread_count)

    return total_unread_count


async def add_new_room(agent_code: str, partner_code: str, partner_name: str = None) -> str:
    # creates a new document reference without adding data
    doc_ref = database.collection("chat_rooms").document()
    # get the generated ID
    room_id = doc_ref.id

    # create the new room dictionary with the room_id
    new_room = {
        "agent_code": agent_code,
        "partner_code": partner_code,
        "partner_name": partner_name,
        "agent_unread_count": 0,
        "partner_unread_count": 0,
        "room_id": room_id,
    }

    # set the data for the document
    doc_ref.set(new_room)

    # emitting new room to both sender and receiver
    await manager.send_json_to_identifier(content={"type": "room_added", "new_room": new_room}, identifier=partner_code)
    await manager.send_json_to_identifier(content={"type": "room_added", "new_room": new_room}, identifier=agent_code)

    # return new_room
    return room_id, new_room
