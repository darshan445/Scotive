# frozen_string_literal: true

class ReplaceArStatusWithChase < ActiveRecord::Migration[8.1]
  def change
    drop_table :invoice_state_transitions
    drop_table :invoice_events

    remove_index :invoices, name: "idx_invoices_status_dates"
    remove_column :invoices, :current_ar_status, :string, null: false, default: "invoiced"
    remove_column :invoices, :active_promise_date, :date
    remove_column :invoices, :disputed_claim_amount, :decimal, precision: 12, scale: 2
    remove_column :invoices, :needs_reply, :boolean, null: false, default: false
    remove_column :invoices, :snoozed_until, :datetime

    add_column :invoices, :books_status, :string, null: false, default: "open"
    add_column :invoices, :chase_status, :string, null: false, default: "watching"
    add_column :invoices, :expected_pay_date, :date
    add_column :invoices, :last_human_inbound_at, :datetime
    add_column :invoices, :last_human_inbound_message_id, :uuid

    add_index :invoices, [ :organization_id, :books_status, :chase_status, :expected_pay_date ],
              name: "idx_invoices_chase_list"
    add_foreign_key :invoices, :messages, column: :last_human_inbound_message_id, on_delete: :nullify

    remove_column :messages, :processed_by_ai, :boolean, null: false, default: false
    add_column :messages, :automatic, :boolean, null: false, default: false

    add_column :outbox_messages, :suggested_wait_date, :date
    add_column :outbox_messages, :suggested_wait_quote, :text

    create_table :invoice_chase_events, id: :uuid do |t|
      t.references :invoice, type: :uuid, null: false, foreign_key: true
      t.uuid :message_id
      t.string :event_type, null: false
      t.string :actor, null: false, default: "system"
      t.text :quote
      t.date :expected_pay_date
      t.datetime :created_at, null: false
    end

    add_foreign_key :invoice_chase_events, :messages, column: :message_id, on_delete: :nullify
    add_index :invoice_chase_events, [ :invoice_id, :created_at ], name: "idx_invoice_chase_events"
  end
end
