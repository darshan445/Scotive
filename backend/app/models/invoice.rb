# frozen_string_literal: true

class Invoice < ApplicationRecord
  belongs_to :organization
  belongs_to :integration
  belongs_to :client
  has_many :invoice_conversations, dependent: :destroy
  has_many :conversations, through: :invoice_conversations
  has_many :invoice_state_transitions, dependent: :destroy
  has_many :invoice_events, dependent: :destroy
  has_many :outbox_messages, dependent: :destroy
end
