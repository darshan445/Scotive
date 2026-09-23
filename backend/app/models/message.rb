# frozen_string_literal: true

class Message < ApplicationRecord
  DIRECTIONS = %w[user_to_client client_to_user].freeze

  self.record_timestamps = false

  belongs_to :conversation

  has_many :invoice_chase_events, dependent: :nullify

  validates :external_message_id, :from_address, :sent_at, presence: true
  validates :direction, inclusion: { in: DIRECTIONS }
end

