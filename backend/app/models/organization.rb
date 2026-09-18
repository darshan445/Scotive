# frozen_string_literal: true

class Organization < ApplicationRecord
  DEFAULT_OFFSETS = [ -3, 0, 7, 9 ].freeze

  has_many :users, dependent: :destroy
  has_many :integrations, dependent: :destroy
  has_many :clients, dependent: :destroy
  has_many :invoices, dependent: :destroy
  has_many :conversations, dependent: :destroy
  has_many :webhook_events, dependent: :destroy
  has_many :outbox_messages, dependent: :destroy

  validates :name, presence: true
  validates :follow_up_interval_days, numericality: { greater_than_or_equal_to: 1, less_than_or_equal_to: 30 }
  validates :daily_digest_hour, numericality: { greater_than_or_equal_to: 0, less_than_or_equal_to: 23 }

  def zone
    Time.find_zone(time_zone).presence || Time.find_zone("UTC")
  end

  def today
    Time.current.in_time_zone(zone).to_date
  end
end
