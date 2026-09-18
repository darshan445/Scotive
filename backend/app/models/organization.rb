# frozen_string_literal: true

class Organization < ApplicationRecord
  has_many :users, dependent: :destroy
  has_many :integrations, dependent: :destroy
  has_many :clients, dependent: :destroy
  has_many :invoices, dependent: :destroy
  has_many :conversations, dependent: :destroy
  has_many :webhook_events, dependent: :destroy
  has_many :outbox_messages, dependent: :destroy

  validates :name, presence: true
end
