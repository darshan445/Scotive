# frozen_string_literal: true

class Client < ApplicationRecord
  belongs_to :organization
  belongs_to :integration
  has_many :invoices, dependent: :destroy

  validates :name, :external_id, presence: true
end
