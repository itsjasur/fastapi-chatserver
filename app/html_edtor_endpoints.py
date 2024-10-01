# app/api/endpoints.py
import datetime
from fastapi import APIRouter, Request
from fastapi import File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import uuid
from app.utils import format_date, get_user_info
from firebase_instance import database, bucket

# from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore

router = APIRouter()


@router.post("/get-htmls")
async def get_htmls(request: Request):
    try:
        data = await request.json()
        page_number = data.get("pageNumber", 1)
        per_page = data.get("perPage", 10)

        collection_ref = (
            database.collection("htmls")
            .limit(per_page)
            .offset((page_number - 1) * per_page)
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .get()
        )
        htmls = []
        total_count = len(database.collection("htmls").get())

        num = (page_number - 1) * per_page

        for doc_ref in collection_ref:
            num = num + 1
            html = doc_ref.to_dict()
            html["updatedAt"] = format_date(html["updatedAt"])
            html["createdAt"] = format_date(html["createdAt"])
            html["num"] = num
            htmls.append(html)

        return JSONResponse(content={"htmls": htmls, "total_count": total_count}, status_code=200)

    except Exception as e:

        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/save-html-string")
async def save_html_string(request: Request):

    try:
        data = await request.json()
        id = data.get("id")
        title = data.get("title")
        html_string = data.get("htmlString")
        access_token = data.get("accessToken")

        has_access, user_name = check_role(access_token)

        if not has_access:
            return JSONResponse(content={"success": False, "message": "Access not granted"}, status_code=200)

        if not html_string:
            raise HTTPException(status_code=400, detail="HTML string is required")

        html_data_ref = database.collection("htmls").document(id)
        html_data = html_data_ref.get().to_dict()

        new_html_content = {
            "id": html_data_ref.id,
            "title": title,
            "creator": user_name,
            "content": html_string,
            "updatedAt": datetime.datetime.now(),
            # "timestamp": firestore.SERVER_TIMESTAMP,
        }

        if html_data:
            # update current document

            # if created user and updated users are not same, returns access error
            if user_name != html_data.get("creator", None):
                return JSONResponse(content={"success": False, "message": "Access not granted to update content"}, status_code=200)

            html_data_ref.update(new_html_content)
            message = "HTML string updated successfully"

        else:
            # create new document
            new_html_content["createdAt"] = datetime.datetime.now()
            html_data_ref.set(new_html_content)
            message = "New HTML string document created successfully"

        return JSONResponse(
            content={"message": message, "success": True, "id": html_data_ref.id},
            status_code=200,
        )

    except Exception as e:
        print(e)
        return JSONResponse(
            content={
                "message": f"HTML string saving failed: {str(e)}",
                "success": False,
            },
            status_code=500,
        )


@router.post("/delete-html")
async def delete_html(request: Request):

    try:
        data = await request.json()
        access_token = data.get("accessToken")

        id = data.get("id", None)
        has_access, user_name = check_role(access_token)

        if not has_access:
            return JSONResponse(content={"success": False, "message": "Access not granted"}, status_code=200)

        html_data_ref = database.collection("htmls").document(id)
        html_data = html_data_ref.get().to_dict()

        if user_name != html_data.get("creator", None):
            return JSONResponse(content={"success": False, "message": "Access not granted to delete content"}, status_code=200)

        doc_ref = database.collection("htmls").document(id)
        doc_ref.delete()

        return JSONResponse(content={"success": True, "message": "Content deleted"}, status_code=200)

    except Exception as e:
        return JSONResponse(
            content={
                "message": f"HTML string deleting failed: {str(e)}",
                "success": False,
            },
            status_code=500,
        )


@router.post("/upload-html-image")
async def upload_html_image(file: UploadFile = File(..., max_size=1024 * 1024 * 10)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File has no filename")
    try:
        # generates a unique filename
        filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"

        # creates a blob in the bucket and upload the file data
        blob = bucket.blob("html_images/" + filename)

        # reads the file content
        content = await file.read()

        # uploads the file to Firebase Storage
        blob.upload_from_string(content, content_type=file.content_type)

        # makes the blob publicly accessible (optional)
        blob.make_public()

        return JSONResponse(content={"filename": filename, "path": blob.public_url}, status_code=200)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/get-html")
async def get_html(request: Request):
    data = await request.json()
    id = data.get("id", None)
    # print(id)

    try:
        doc_ref = database.collection("htmls").document(id).get()

        if doc_ref:
            html = doc_ref.to_dict()
            html["updatedAt"] = html["updatedAt"].strftime("%Y-%m-%d %H:%M")
            html["createdAt"] = html["createdAt"].strftime("%Y-%m-%d %H:%M")
            return JSONResponse(content={"html": html}, status_code=200)

        else:
            return JSONResponse(content={"html": None, "message": "Content not found"}, status_code=400)

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


def check_role(access_token: str):
    try:
        user_info = get_user_info(access_token)
        user_name = user_info.get("username", None)

        roles = user_info.get("roles", [])
        required_roles = ["ROLE_SUPER", "ROLE_ADMIN", "ROLE_MANAGER", "ROLE_OPEN_ADMIN", "ROLE_OPEN_MANAGER", "ROLE_AGENCY_ADMIN"]
        has_access = any(item in roles for item in required_roles)
        return has_access, user_name

    except:
        return False, None
