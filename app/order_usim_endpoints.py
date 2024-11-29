import datetime
import sys
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from firebase_instance import database
from app.utils import format_date, get_user_info
from google.cloud.firestore_v1.base_query import FieldFilter


router = APIRouter()


from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from fastapi import HTTPException, APIRouter


router = APIRouter()


class OrderItem(BaseModel):
    agent_code: str
    carrier_type_code: str
    mvno_code: str
    usim_count: int


class UsimOrderModel(BaseModel):
    order_id: str | None = None
    access_token: str
    receiver_name: str
    phone_number: str
    address: str
    address_details: str
    receiver_comment: Optional[str] = None
    order_items: list[OrderItem]

    @field_validator("order_items")
    def validate_order_items(cls, v):
        if len(v) < 1:
            raise ValueError("주문 항목은 비어 있을 수 없습니다.")
        return v


@router.post("/create-or-update-order", response_model=dict)
async def create_or_update_order(data: UsimOrderModel):
    try:
        # userinfo
        user_info = get_user_info(data.access_token)
        current_time = datetime.now()

        # determins if this is an update or create operation
        is_update = data.order_id is not None

        if is_update:
            # Get existing order reference
            order_ref = database.collection("usim_orders").document(data.order_id)
            order_doc = order_ref.get()

            if not order_doc.exists:
                raise HTTPException(status_code=404, detail={"message": "Order not found", "success": False})

            # verfy user owns this order
            if order_doc.to_dict()["username"] != user_info["username"]:
                raise HTTPException(status_code=403, detail={"message": "Unauthorized to modify this order", "success": False})
        else:
            # creates new order reference
            order_ref = database.collection("usim_orders").document()

        # srepares order data
        order_data = {
            "status": "confirmed" if not is_update else order_doc.to_dict()["status"],
            "sender_comment": "" if not is_update else order_doc.to_dict()["sender_comment"],
            "username": user_info["username"],
            "receiver_name": data.receiver_name,
            "phone_number": data.phone_number,
            "address": data.address,
            "address_details": data.address_details,
            "receiver_comment": data.receiver_comment,
            "created_at": current_time if not is_update else order_doc.to_dict()["created_at"],
            "last_updated_at": current_time,
            "last_status_updated_at": (current_time if not is_update else order_doc.to_dict()["last_status_updated_at"]),
        }

        # starts batch operation
        batch = database.batch()

        # sets or update the main order
        batch.set(order_ref, order_data, merge=True)

        # delete existing items if udpate
        if is_update:
            existing_items = database.collection("usim_order_items").where("usim_order_id", "==", data.order_id).stream()
            for item in existing_items:
                batch.delete(item.reference)

        # creates new order items
        for item in data.order_items:
            new_item_ref = database.collection("usim_order_items").document()
            item_data = {
                "usim_order_id": order_ref.id,
                "agent_code": item.agent_code,
                "carrier_type_code": item.carrier_type_code,
                "mvno_code": item.mvno_code,
                "usim_count": item.usim_count,
                "created_at": current_time,
            }
            batch.set(new_item_ref, item_data)

        # commits all changes
        batch.commit()

        return {"message": "주문이 성공적으로 처리되었습니다", "success": True, "id": order_ref.id, "action": "updated" if is_update else "created"}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error processing order: {str(e)}")
        raise HTTPException(status_code=500, detail={"message": "An error occurred while processing your order", "success": False})


class GetUsimOrdersModel(BaseModel):
    access_token: str
    page_number: Optional[int] = 1
    per_page: Optional[int] = 100


@router.post("/get-orders", response_model=dict)
async def get_orders(data: GetUsimOrdersModel):
    try:

        # Get user info with error handling
        user_info = get_user_info(data.access_token)
        username = user_info.get("username")

        # base query
        query = database.collection("usim_orders").where(filter=FieldFilter("username", "==", username))

        total_count = query.count().get()[0][0].value or 0

        try:
            usim_orders_ref = query.offset((data.page_number - 1) * data.per_page).limit(data.per_page).get()
        except Exception as e:
            raise HTTPException(status_code=500, detail={"message": "Failed to fetch orders", "success": False})

        usim_orders = []

        # collects all order IDs for batch query
        order_ids = [order_ref.id for order_ref in usim_orders_ref]

        # batch query for order items
        order_items_map = {}
        if order_ids:
            order_items_query = database.collection("usim_order_items").where(filter=FieldFilter("usim_order_id", "in", order_ids)).get()

            # group order items by order ID
            for item_ref in order_items_query:
                item_data = item_ref.to_dict()
                order_id = item_data.get("usim_order_id")
                if order_id:
                    if order_id not in order_items_map:
                        order_items_map[order_id] = []
                    item_data["created_at"] = format_date(item_data.get("created_at"))
                    order_items_map[order_id].append(item_data)

        # build final response
        for order_ref in usim_orders_ref:
            try:
                order_data = order_ref.to_dict()
                order_data["created_at"] = format_date(order_data.get("created_at"))
                order_data["last_status_updated_at"] = format_date(order_data.get("last_status_updated_at"))
                order_data["order_items"] = order_items_map.get(order_ref.id, [])
                usim_orders.append(order_data)
                order_data["order_id"] = order_ref.id

            except Exception as e:
                continue  # skips malformed orders instead of failing completely

        return {
            "message": "Data sent successfully",
            "success": True,
            "usim_orders": usim_orders,
            "total_count": total_count,
        }

    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        # logs the full error for debugging
        print(f"Error fetching orders: {str(e)}")
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail={"message": "An error occurred while fetching orders", "success": False})


class OrderRequest(BaseModel):
    access_token: str
    order_id: str


@router.post("/get-order", response_model=dict)
async def get_order(data: OrderRequest):
    try:

        # user info
        user_info = get_user_info(data.access_token)
        order_ref = database.collection("usim_orders").document(data.order_id)

        print(order_ref.get().to_dict())

        order = order_ref.get().to_dict()

        if order["username"] != user_info["username"]:
            raise HTTPException(status_code=500, detail={"message": "This order doesn't belong to you", "success": False})

        order["last_status_updated_at"] = format_date(order.get("last_status_updated_at"))
        order["created_at"] = format_date(order.get("created_at"))

        order_items_ref = database.collection("usim_order_items").where(filter=FieldFilter("usim_order_id", "==", order_ref.id)).get()

        order_items = []
        for order_item_ref in order_items_ref:
            order_item = order_item_ref.to_dict()
            order_item["created_at"] = format_date(order_item.get("created_at"))

            order_items.append(order_item)

        order["order_items"] = order_items

        return order

    except HTTPException as http_error:
        raise http_error
