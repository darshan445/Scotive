# frozen_string_literal: true

class OutboxMessage < ApplicationRecord
  STATUSES = %w[scheduled draft sent cancelled].freeze

  belongs_to :organization
  belongs_to :invoice
  belongs_to :conversation, optional: true

  validates :to_address, :subject, :body, :scheduled_send_at, presence: true
  validates :status, inclusion: { in: STATUSES }

  scope :pending, -> { where(status: %w[scheduled draft]) }
  scope :due_to_send, -> { where(status: "scheduled").where("scheduled_send_at <= ?", Time.current) }

  def self.cancel_pending_for!(invoice, reason)
    pending.where(invoice_id: invoice.id, organization_id: invoice.organization_id).find_each do |row|
      row.update!(status: "cancelled", cancellation_reason: reason)
    end
  end
end
