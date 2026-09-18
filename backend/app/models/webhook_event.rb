# frozen_string_literal: true

class WebhookEvent < ApplicationRecord
  self.record_timestamps = false

  STATUSES = %w[pending processed failed].freeze

  belongs_to :organization, optional: true
  belongs_to :integration, optional: true

  validates :provider, :external_event_id, :payload, presence: true
  validates :status, inclusion: { in: STATUSES }
end
