# frozen_string_literal: true

class OutboxMessage < ApplicationRecord
  belongs_to :organization
  belongs_to :invoice
  belongs_to :conversation, optional: true
end
