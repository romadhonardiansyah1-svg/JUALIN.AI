"""
JUALIN.AI — Models Package
Import all models here so SQLAlchemy can discover them for create_all().

IMPORTANT: Every new model MUST be imported here, otherwise
SQLAlchemy won't create its table on startup.
"""
from models.database import Base
from models.user import User, UserTier, UserRole
from models.product import Product
from models.conversation import Conversation, Message, MessageRole
from models.order import Order, OrderStatus
from models.order_status_history import OrderStatusHistory
from models.customer_memory import CustomerMemory
from models.chat_analytics import ChatAnalytics

__all__ = [
    "Base",
    "User", "UserTier", "UserRole",
    "Product",
    "Conversation", "Message", "MessageRole",
    "Order", "OrderStatus",
    "OrderStatusHistory",
    "CustomerMemory",
    "ChatAnalytics",
]
