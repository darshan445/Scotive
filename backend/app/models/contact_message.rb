# frozen_string_literal: true

class ContactMessage < ApplicationRecord
  validates :email, :message, presence: true
end
