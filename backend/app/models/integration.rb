# frozen_string_literal: true

class Integration < ApplicationRecord
  belongs_to :organization
  has_many :clients, dependent: :destroy
  has_many :invoices, dependent: :destroy
  has_many :conversations, dependent: :destroy
end
