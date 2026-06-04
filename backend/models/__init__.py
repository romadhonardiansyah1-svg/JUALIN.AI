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
from models.scale_core import IntegrationAccount, WebhookEvent, BackgroundJob, AuditLog
from models.inbox import Channel, ChannelContact, InboxThread, InboxMessage
from models.crm import Customer, CustomerProfile, CustomerEvent, CustomerTag
from models.ai_quality import AITrace, AIToolCall, AIRetrievalLog, AIFeedback, AIEvalCase, AIEvalRun
from models.campaign import Campaign, CampaignRecipient, CampaignMessage
from models.workflow import AutomationRule, AutomationRun, AutomationRunStep
from models.billing import Plan, Subscription, UsageCounter, BillingEvent
from models.system_heartbeat import SystemHeartbeat
from models.product_import import ProductImportBatch

__all__ = [
    "Base",
    "User", "UserTier", "UserRole",
    "Product",
    "Conversation", "Message", "MessageRole",
    "Order", "OrderStatus",
    "OrderStatusHistory",
    "CustomerMemory",
    "ChatAnalytics",
    "IntegrationAccount", "WebhookEvent", "BackgroundJob", "AuditLog",
    "Channel", "ChannelContact", "InboxThread", "InboxMessage",
    "Customer", "CustomerProfile", "CustomerEvent", "CustomerTag",
    "AITrace", "AIToolCall", "AIRetrievalLog", "AIFeedback", "AIEvalCase", "AIEvalRun",
    "Campaign", "CampaignRecipient", "CampaignMessage",
    "AutomationRule", "AutomationRun", "AutomationRunStep",
    "Plan", "Subscription", "UsageCounter", "BillingEvent",
    "SystemHeartbeat",
    "ProductImportBatch",
]

