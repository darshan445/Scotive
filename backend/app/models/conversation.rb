# frozen_string_literal: true

class Conversation < ApplicationRecord
  belongs_to :organization
  belongs_to :integration
  has_many :messages, dependent: :destroy
  has_many :invoice_conversations, dependent: :destroy
  has_many :invoices, through: :invoice_conversations

  validates :external_thread_id, presence: true
end
