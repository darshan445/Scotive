# frozen_string_literal: true

class InvoiceStateTransition < ApplicationRecord
  belongs_to :invoice
  belongs_to :triggered_by_message, class_name: "Message", optional: true
end
