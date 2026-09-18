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
end
