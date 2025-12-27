"""Database setup and models for Cin7 Uploader"""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON, UniqueConstraint, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

db = SQLAlchemy()

# Note: User model is in fireflies.users schema (shared with fireflies-tasks)
# We reference it via foreign keys but don't define it here

class Client(db.Model):
    """Client profiles"""
    __tablename__ = 'client'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    # Note: UserClient no longer references this table - it uses voyager.client_erp_credentials.id directly
    credentials = relationship('ClientCin7Credentials', back_populates='client', uselist=False, cascade='all, delete-orphan')
    csv_mappings = relationship('ClientCsvMapping', back_populates='client', cascade='all, delete-orphan')
    settings = relationship('ClientSettings', back_populates='client', uselist=False, cascade='all, delete-orphan')
    uploads = relationship('SalesOrderUpload', back_populates='client', cascade='all, delete-orphan')


class UserClient(db.Model):
    """Many-to-many: user provisioning to clients/connections
    References voyager.client_erp_credentials.id directly (not cin7_uploader.client.id)"""
    __tablename__ = 'user_client'
    __table_args__ = (
        UniqueConstraint('user_id', 'client_id', name='user_client_user_client_unique'),
        {'schema': 'cin7_uploader'}
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('fireflies.users.id'), nullable=False, index=True)
    # client_id now references voyager.client_erp_credentials.id directly
    # This can be either a client_id (for client-based connections) or credential_id (for standalone)
    client_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # No FK constraint - references voyager.client_erp_credentials.id
    role = Column(String(50), nullable=True)  # e.g., 'admin', 'user' - for future permissions
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # No relationship - we'll query voyager.client_erp_credentials directly when needed


class ClientCin7Credentials(db.Model):
    """Cin7 API credentials per client"""
    __tablename__ = 'client_cin7_credentials'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.client.id'), nullable=False, unique=True, index=True)
    account_id = Column(UUID(as_uuid=True), nullable=False)  # Cin7 account ID
    application_key = Column(Text, nullable=False)  # Cin7 application key - encrypted at rest
    base_url = Column(String(500), default='https://inventory.dearsystems.com/ExternalApi/v2/', nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    client = relationship('Client', back_populates='credentials')


class ClientCsvMapping(db.Model):
    """CSV column mapping templates per client or client_erp_credentials"""
    __tablename__ = 'client_csv_mapping'
    __table_args__ = (
        UniqueConstraint('client_erp_credentials_id', 'mapping_name', name='client_csv_mapping_cred_name_unique'),
        {'schema': 'cin7_uploader'}
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.client.id'), nullable=True, index=True)
    client_erp_credentials_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # References voyager.client_erp_credentials.id
    mapping_name = Column(String(255), nullable=False)  # e.g., 'default', 'wholesale', 'retail'
    is_default = Column(Boolean, default=False, nullable=False)
    column_mapping = Column(JSON, nullable=False)  # Maps CSV columns to Cin7 fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    client = relationship('Client', back_populates='csv_mappings')


class ClientSettings(db.Model):
    """Per-client default settings for sales orders"""
    __tablename__ = 'client_settings'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.client.id'), nullable=False, unique=True, index=True)
    
    # Default values for sales orders
    default_status = Column(String(50), default='DRAFT', nullable=False)
    default_location = Column(UUID(as_uuid=True), nullable=True)  # Warehouse/location UUID
    default_currency = Column(String(10), default='USD', nullable=False)
    tax_inclusive = Column(Boolean, default=False, nullable=False)
    
    # Fulfillment settings
    auto_fulfill = Column(Boolean, default=False, nullable=False)
    default_fulfillment_status = Column(String(50), nullable=True)
    
    # Validation requirements
    require_customer_reference = Column(Boolean, default=False, nullable=False)
    require_invoice_number = Column(Boolean, default=False, nullable=False)
    
    # CSV parsing settings
    date_format = Column(String(50), default='YYYY-MM-DD', nullable=False)
    
    # Batch processing defaults
    default_delay_between_orders = Column(Float, default=0.7, nullable=False)  # seconds
    default_batch_size = Column(Integer, default=50, nullable=False)
    default_batch_delay = Column(Float, default=45.0, nullable=False)  # seconds
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    client = relationship('Client', back_populates='settings')


class SalesOrderUpload(db.Model):
    """Upload history/audit log"""
    __tablename__ = 'sales_order_upload'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('fireflies.users.id'), nullable=True, index=True)  # nullable for webhook uploads
    client_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.client.id'), nullable=True, index=True)  # nullable for webhook uploads
    client_erp_credentials_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.client_erp_credentials.id'), nullable=True, index=True)
    filename = Column(String(500), nullable=False)
    total_rows = Column(Integer, nullable=False)
    successful_orders = Column(Integer, default=0, nullable=False)
    failed_orders = Column(Integer, default=0, nullable=False)
    status = Column(String(50), nullable=False)  # 'pending', 'processing', 'completed', 'failed'
    error_log = Column(JSON, nullable=True)  # Array of errors
    csv_content = Column(Text, nullable=True)  # Base64 encoded CSV content for preview
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    client = relationship('Client', back_populates='uploads')
    results = relationship('SalesOrderResult', back_populates='upload', cascade='all, delete-orphan')


class SalesOrderResult(db.Model):
    """Results for individual sales orders from an upload"""
    __tablename__ = 'sales_order_result'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.sales_order_upload.id', ondelete='CASCADE'), nullable=False, index=True)
    order_key = Column(String(255), nullable=False)  # Unique identifier for the order (e.g., invoice number)
    row_numbers = Column(JSON, nullable=True)  # Array of row numbers from CSV that contributed to this order
    status = Column(String(50), nullable=False)  # 'success', 'failed', 'pending', etc.
    sale_id = Column(UUID(as_uuid=True), nullable=True)  # Cin7 sale ID if created
    sale_order_id = Column(UUID(as_uuid=True), nullable=True)  # Cin7 sale order ID if created
    error_message = Column(Text, nullable=True)  # Error message if failed
    order_data = Column(JSON, nullable=True)  # Full order data that was sent to Cin7
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)  # When the order was processed
    
    # Review tracking
    reviewed = Column(Boolean, default=False, nullable=False, index=True)  # Whether this result has been reviewed
    
    # Task tracking for retries and resolution
    retry_count = Column(Integer, default=0, nullable=False)
    last_retry_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True, index=True)  # When the issue was resolved
    resolved_by = Column(UUID(as_uuid=True), ForeignKey('fireflies.users.id'), nullable=True)  # User who resolved it
    error_type = Column(String(50), nullable=True, index=True)  # Type of error for categorization
    
    # Relationships
    upload = relationship('SalesOrderUpload', back_populates='results')


class Cin7ApiLog(db.Model):
    """Log of API calls to Cin7"""
    __tablename__ = 'cin7_api_log'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NOTE: This column stores credential_id (from voyager.client_erp_credentials.id), NOT client_id
    # It's named client_id in the database for historical reasons, but semantically it's credentials_id
    # TODO: Consider renaming to credentials_id in a future migration
    client_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Actually stores credential_id!
    user_id = Column(UUID(as_uuid=True), ForeignKey('fireflies.users.id'), nullable=True, index=True)
    upload_id = Column(UUID(as_uuid=True), ForeignKey('cin7_uploader.sales_order_upload.id'), nullable=True, index=True)
    
    # Trigger/source of the API call
    trigger = Column(String(50), nullable=True, index=True)  # "validation", "upload", "connection_test", etc.
    
    # API call details
    endpoint = Column(String(500), nullable=False)  # e.g., "/sale", "/saleorder"
    method = Column(String(10), nullable=False)  # "GET", "POST", etc.
    request_url = Column(Text, nullable=False)
    request_headers = Column(JSON, nullable=True)  # Store headers (excluding sensitive keys)
    request_body = Column(JSON, nullable=True)  # Request payload
    response_status = Column(Integer, nullable=True)  # HTTP status code
    response_body = Column(JSON, nullable=True)  # Response data
    error_message = Column(Text, nullable=True)  # Error message if failed
    duration_ms = Column(Integer, nullable=True)  # Request duration in milliseconds
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Note: No relationship to Client because client_id actually stores credential_id
    # Client names are retrieved via raw SQL queries joining through voyager.client_erp_credentials


class PasswordResetToken(db.Model):
    """Password reset tokens - stored in database for persistence"""
    __tablename__ = 'password_reset_token'
    __table_args__ = {'schema': 'cin7_uploader'}
    
    token = Column(String(255), primary_key=True)  # The reset token itself
    email = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CachedCustomer(db.Model):
    """Cached customer data from Cin7 API"""
    __tablename__ = 'cached_customer'
    __table_args__ = (
        UniqueConstraint('client_erp_credentials_id', 'cin7_customer_id', name='cached_customer_cred_customer_unique'),
        {'schema': 'cin7_uploader'}
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_erp_credentials_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # References voyager.client_erp_credentials.id
    cin7_customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CachedProduct(db.Model):
    """Cached product data from Cin7 API"""
    __tablename__ = 'cached_product'
    __table_args__ = (
        UniqueConstraint('client_erp_credentials_id', 'cin7_product_id', name='cached_product_cred_product_unique'),
        {'schema': 'cin7_uploader'}
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_erp_credentials_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # References voyager.client_erp_credentials.id
    cin7_product_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
