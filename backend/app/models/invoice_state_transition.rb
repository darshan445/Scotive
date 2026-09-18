# frozen_string_literal: true

class InvoiceStateTransition < ApplicationRecord
  self.record_timestamps = false

  TRIGGER_SOURCES = %w[ai_reader books_sync books_webhook clock_cron mailbox_match manual_user].freeze

  belongs_to :invoice
  belongs_to :triggered_by_message, class_name: "Message", optional: true

  validates :to_status, :trigger_source, presence: true
  validates :trigger_source, inclusion: { in: TRIGGER_SOURCES }
end
