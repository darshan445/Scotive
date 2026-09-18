# frozen_string_literal: true

class InvoiceEvent < ApplicationRecord
  belongs_to :invoice
  belongs_to :message, optional: true
end
