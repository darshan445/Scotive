# frozen_string_literal: true

class InvoiceEvent < ApplicationRecord
  self.record_timestamps = false

  belongs_to :invoice
  belongs_to :message, optional: true
end
