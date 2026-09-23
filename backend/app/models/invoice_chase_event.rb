# frozen_string_literal: true

class InvoiceChaseEvent < ApplicationRecord
  EVENT_TYPES = %w[
    human_inbound auto_reply_ignored bounce_ignored
    wait_set wait_expired resumed stopped
    books_paid books_voided books_partial
    friendly_sent draft_sent
  ].freeze
  ACTORS = %w[system user].freeze

  self.record_timestamps = false

  belongs_to :invoice
  belongs_to :message, optional: true

  validates :event_type, inclusion: { in: EVENT_TYPES }
  validates :actor, inclusion: { in: ACTORS }
end
