# app/api/endpoints.py
from fastapi import APIRouter, Request
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uuid
from app.models import SMSData
from app.utils import get_user_info, send_single_sms
from firebase_instance import database, bucket
from firebase_admin import messaging
from google.cloud.firestore_v1.base_query import FieldFilter


router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Hi there"}


@router.post("/get-room-count")
async def get_room_info(request: Request):
    data = await request.json()
    access_token = data["accessToken"]
    agent_code = data["agentCode"]

    user_info = get_user_info(access_token)
    partner_code = user_info["username"]

    if agent_code is not None and partner_code is not None:
        chat_rooms_ref = (
            database.collection("chat_rooms")
            .where(filter=FieldFilter("partner_code", "==", partner_code))
            .where(filter=FieldFilter("agent_code", "==", agent_code))
            .limit(1)
            .get()
        )

        if len(chat_rooms_ref) > 0:
            room_info = chat_rooms_ref[0].to_dict()
            return JSONResponse(content={"unread_count": room_info["partner_unread_count"]})

    return JSONResponse(content={"unread_count": 0})


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File has no filename")

    try:
        # generates a unique filename
        filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"

        # creates a blob in the bucket and upload the file data
        blob = bucket.blob("attachments/" + filename)

        # reads the file content
        content = await file.read()

        # uploads the file to Firebase Storage
        blob.upload_from_string(content, content_type=file.content_type)

        # makes the blob publicly accessible (optional)
        blob.make_public()

        return JSONResponse(content={"filename": filename, "path": blob.public_url}, status_code=200)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/send-single-sms")
def send_sms(sms_data: SMSData):
    # async def send_sms(request: Request):

    sign_data_ref = database.collection("sign_data").document()
    doc_id = sign_data_ref.id

    sign_data_ref.set(
        {
            "partner_code": sms_data.partner_code,
            "sign_data": None,
            "seal_data": None,
        }
    )

    try:
        full_message = f"{sms_data.message}\n\n{sms_data.base_url}{doc_id}"

        send_single_sms(
            receiver_phone_number=sms_data.receiver_phone_number,
            title=sms_data.title,
            message=full_message,
        )

        return JSONResponse(
            content={
                "message": "Message sent",
                "success": True,
                "key": doc_id,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/save-sign")
async def save_sign(request: Request):
    data = await request.json()

    key = data.get("key")
    sign_data = data.get("sign")
    seal_data = data.get("seal")

    fail_response = JSONResponse(
        content={
            "message": "서명이 완료되지 않았습니다",
            "success": False,
        }
    )

    if key is None or key == "":
        return fail_response

    sign_seal_data_ref = database.collection("sign_data").document(key)
    sign_seal_data = sign_seal_data_ref.get().to_dict()

    if sign_seal_data is not None:
        sign_seal_data_ref.set({"sign_data": sign_data, "seal_data": seal_data})
        return JSONResponse(
            content={
                "message": "서명 완료",
                "success": True,
            }
        )

    return fail_response


@router.post("/check-sign")
async def check_sign(request: Request):
    data = await request.json()
    key = data.get("key")

    fail_response = JSONResponse(
        content={
            "message": "서명이 완료되지 않았습니다",
            "success": False,
        }
    )

    if key is None or key == "":
        return fail_response

    sign_seal_data_ref = database.collection("sign_data").document(key)

    if sign_seal_data_ref.get().exists:
        sign_seal_data = sign_seal_data_ref.get().to_dict()

        if sign_seal_data is not None:
            sign_data = sign_seal_data["sign_data"]
            seal_data = sign_seal_data["seal_data"]

            if sign_data is not None and seal_data is not None:
                sign_seal_data_ref.delete()

                return JSONResponse(
                    content={
                        "message": "서명 완료",
                        "success": True,
                        "sign_data": sign_data,
                        "seal_data": seal_data,
                    }
                )

    return fail_response


def send_multiple_notifications(fcm_tokens, title, body, chat_room_id):
    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data={
            # "room": room,
            "chat_room_id": chat_room_id,
        },
        tokens=fcm_tokens,
    )

    try:
        response = messaging.send_multicast(message)
        return f"Successfully sent messages: {response.success_count} successful, {response.failure_count} failed"
    except Exception as e:
        return f"Error sending messages: {e}"
