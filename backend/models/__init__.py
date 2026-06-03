"""
JUALIN.AI — Models Package
Import all models here so SQLAlchemy can discover them
"""
from models.database import Base
from models.user import User, UserTier, UserRole
from models.product import Product
from models.conversation import Conversation, Message, MessageRole
from models.order import Order, OrderStatus
from models.customer_memory import CustomerMemory

__all__ = [
    "Base",
    "User", "UserTier", "UserRole",
    "Product",
    "Conversation", "Message", "MessageRole",
    "Order", "OrderStatus",
    "CustomerMemory",
]
