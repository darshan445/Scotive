# frozen_string_literal: true

class CreateInvoiceEvents < ActiveRecord::Migration[8.1]
  def change
    create_table :invoice_events, id: :uuid do |t|
      t.references :invoice, type: :uuid, null: false, foreign_key: true
      t.uuid :message_id
      t.string :event_type, null: false
      t.string :sender, null: false
      t.text :quote
      t.jsonb :event_data, null: false, default: {}
      t.decimal :confidence, precision: 3, scale: 2
      t.datetime :created_at, null: false
    end

    add_foreign_key :invoice_events, :messages, column: :message_id, on_delete: :nullify
    add_index :invoice_events, [ :invoice_id, :created_at ], name: "idx_invoice_events_invoice"
  end
end
