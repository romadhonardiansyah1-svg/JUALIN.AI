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
from models.prompt_registry import PromptVersion
from models.inbox_extras import InboxThreadLabel, InboxInternalNote, CannedReply
from models.usage_event import UsageEvent
from models.daily_metrics import DailySellerMetric
from models.template import Template
from models.onboarding import SellerOnboarding
from models.storefront import Storefront, StorefrontSection
from models.campaign_recommendation import CampaignRecommendation
from models.referral import ReferralCode, ReferralEvent, ResellerProfile, CommissionRule, CommissionEvent
from models.lead import LeadForm, LeadSubmission
from models.playbook import SalesPlaybook, SalesPlaybookRule
from models.customer_score import CustomerScore
from models.offer import Offer, OfferRecommendation, OfferRedemption
from models.knowledge import KnowledgeSource, KnowledgeChunk
from models.qa_review import QAReviewItem
from models.experiment import Experiment, ExperimentVariant, ExperimentAssignment, ExperimentEvent

# Market Acceptance models
from models.template_install import TemplatePackInstall
from models.trust_profile import StoreTrustProfile
from models.growth_link import GrowthLink
from models.wa_template import WhatsAppMessageTemplate
from models.concierge_checklist import ConciergeChecklist

# JUALIN OS models
from models.agent_os import AgentPolicy, AgentRun, AgentApproval, NegotiationState
from models.llm_settings import LLMSettings  # noqa: F401

# Payment recovery safety foundation
from models.payment_recovery import (
    PaymentAttempt,
    PaymentRecoveryControl,
    ContactSubject,
    ContactSubjectFingerprint,
    ContactPermission,
    ContactSuppression,
    RevenueOpportunity,
    OutboundDispatch,
    OutcomeEvent,
    AttributionAssessment,
    RecipientContactWindow,
)

__all__ = [
    "Base",
    "User",
    "UserTier",
    "UserRole",
    "Product",
    "Conversation",
    "Message",
    "MessageRole",
    "Order",
    "OrderStatus",
    "OrderStatusHistory",
    "CustomerMemory",
    "ChatAnalytics",
    "IntegrationAccount",
    "WebhookEvent",
    "BackgroundJob",
    "AuditLog",
    "Channel",
    "ChannelContact",
    "InboxThread",
    "InboxMessage",
    "Customer",
    "CustomerProfile",
    "CustomerEvent",
    "CustomerTag",
    "AITrace",
    "AIToolCall",
    "AIRetrievalLog",
    "AIFeedback",
    "AIEvalCase",
    "AIEvalRun",
    "Campaign",
    "CampaignRecipient",
    "CampaignMessage",
    "AutomationRule",
    "AutomationRun",
    "AutomationRunStep",
    "Plan",
    "Subscription",
    "UsageCounter",
    "BillingEvent",
    "SystemHeartbeat",
    "ProductImportBatch",
    "PromptVersion",
    "InboxThreadLabel",
    "InboxInternalNote",
    "CannedReply",
    "UsageEvent",
    "DailySellerMetric",
    "Template",
    "SellerOnboarding",
    "Storefront",
    "StorefrontSection",
    "CampaignRecommendation",
    "ReferralCode",
    "ReferralEvent",
    "ResellerProfile",
    "CommissionRule",
    "CommissionEvent",
    "LeadForm",
    "LeadSubmission",
    "SalesPlaybook",
    "SalesPlaybookRule",
    "CustomerScore",
    "Offer",
    "OfferRecommendation",
    "OfferRedemption",
    "KnowledgeSource",
    "KnowledgeChunk",
    "QAReviewItem",
    "Experiment",
    "ExperimentVariant",
    "ExperimentAssignment",
    "ExperimentEvent",
    "AgentPolicy",
    "AgentRun",
    "AgentApproval",
    "NegotiationState",
    "PaymentAttempt",
    "PaymentRecoveryControl",
    "ContactSubject",
    "ContactSubjectFingerprint",
    "ContactPermission",
    "ContactSuppression",
    "RevenueOpportunity",
    "OutboundDispatch",
    "OutcomeEvent",
    "AttributionAssessment",
    "RecipientContactWindow",
]

