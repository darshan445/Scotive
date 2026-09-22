# frozen_string_literal: true

class Integration < ApplicationRecord
  CATEGORIES = %w[accounting mailbox].freeze
  ACCOUNTING_PROVIDERS = %w[qbo xero freshbooks].freeze
  MAILBOX_PROVIDERS = %w[gmail outlook].freeze
  PROVIDERS = (ACCOUNTING_PROVIDERS + MAILBOX_PROVIDERS).freeze
  CONNECTION_STATUSES = %w[connected reauth_required error disconnected].freeze

  belongs_to :organization
  has_many :clients, dependent: :destroy
  has_many :invoices, dependent: :destroy
  has_many :conversations, dependent: :destroy
  has_many :webhook_events, dependent: :destroy

  encrypts :access_token, :refresh_token

  validates :category, inclusion: { in: CATEGORIES }
  validates :provider, inclusion: { in: PROVIDERS }
  validates :connection_status, inclusion: { in: CONNECTION_STATUSES }
  validate :provider_matches_category

  scope :accounting, -> { where(category: "accounting") }
  scope :mailbox, -> { where(category: "mailbox") }
  scope :connected, -> { where(connection_status: "connected") }
  scope :for_organization, ->(organization_id) { where(organization_id: organization_id) }

  def accounting?
    category == "accounting"
  end

  def mailbox?
    category == "mailbox"
  end

  def connected?
    connection_status == "connected"
  end

  private

  def provider_matches_category
    allowed = case category
    when "accounting" then ACCOUNTING_PROVIDERS
    when "mailbox" then MAILBOX_PROVIDERS
    else
      []
    end

    return if allowed.include?(provider)

    errors.add(:provider, "is not valid for #{category}")
  end
end
