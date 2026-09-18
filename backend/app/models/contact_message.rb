# frozen_string_literal: true

class ContactMessage < ApplicationRecord
  STATUSES = %w[new read].freeze

  validates :email, :message, presence: true
  validates :status, inclusion: { in: STATUSES }
end
