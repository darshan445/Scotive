# frozen_string_literal: true

class InvoiceConversation < ApplicationRecord
  self.primary_key = [ :invoice_id, :conversation_id ]
  self.record_timestamps = false

  belongs_to :invoice
  belongs_to :conversation
end
