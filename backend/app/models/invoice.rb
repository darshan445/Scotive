# frozen_string_literal: true

class Invoice < ApplicationRecord
  AR_STATUSES = %w[
    unmatched invoiced overdue promised broken_promise
    disputed paid_unconfirmed partially_paid paid voided
  ].freeze

  belongs_to :organization
  belongs_to :integration
  belongs_to :client
  has_many :invoice_conversations, dependent: :destroy
  has_many :conversations, through: :invoice_conversations
  has_many :invoice_state_transitions, dependent: :destroy
  has_many :invoice_events, dependent: :destroy
  has_many :outbox_messages, dependent: :destroy

  validates :external_id, :invoice_number, :issue_date, :due_date, presence: true
  validates :current_ar_status, inclusion: { in: AR_STATUSES }
end
