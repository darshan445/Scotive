# frozen_string_literal: true

class CreateIntegrationsAndArDomain < ActiveRecord::Migration[8.1]
  def change
    create_table :integrations, id: :uuid do |t|
      t.references :organization, type: :uuid, null: false, foreign_key: true
      t.string :category, null: false
      t.string :provider, null: false
      t.string :external_account_id
      t.string :account_name
      t.text :access_token
      t.text :refresh_token
      t.datetime :token_expires_at
      t.string :sync_cursor
      t.datetime :last_synced_at
      t.string :webhook_subscription_id
      t.datetime :webhook_expires_at
      t.string :connection_status, null: false, default: "connected"
      t.timestamps
    end

    add_index :integrations, [ :organization_id, :provider, :external_account_id ],
              unique: true, name: "uq_integrations_org_provider_account"
    add_index :integrations, [ :organization_id, :category, :connection_status ],
              name: "idx_integrations_active"

    create_table :clients, id: :uuid do |t|
      t.references :organization, type: :uuid, null: false, foreign_key: true
      t.references :integration, type: :uuid, null: false, foreign_key: true
      t.string :external_id, null: false
      t.string :name, null: false
      t.string :primary_email
      t.string :domain
      t.jsonb :associated_emails, null: false, default: []
      t.timestamps
    end

    add_index :clients, [ :integration_id, :external_id ], unique: true, name: "uq_clients_integration_external"
    add_index :clients, [ :organization_id, :domain ], name: "idx_clients_domain"
    add_index :clients, [ :organization_id, :primary_email ], name: "idx_clients_primary_email"

    create_table :invoices, id: :uuid do |t|
      t.references :organization, type: :uuid, null: false, foreign_key: true
      t.references :integration, type: :uuid, null: false, foreign_key: true
      t.references :client, type: :uuid, null: false, foreign_key: true
      t.string :external_id, null: false
      t.string :invoice_number, null: false
      t.date :issue_date, null: false
      t.date :due_date, null: false
      t.string :currency, null: false, default: "USD"
      t.decimal :total_amount, precision: 12, scale: 2, null: false
      t.decimal :balance_remaining, precision: 12, scale: 2, null: false
      t.string :pay_link_token
      t.jsonb :cc_emails, null: false, default: []
      t.jsonb :bcc_emails, null: false, default: []
      t.string :current_ar_status, null: false, default: "invoiced"
      t.date :active_promise_date
      t.decimal :disputed_claim_amount, precision: 12, scale: 2
      t.boolean :needs_reply, null: false, default: false
      t.datetime :snoozed_until
      t.timestamps
    end

    add_index :invoices, [ :integration_id, :external_id ], unique: true, name: "uq_invoices_integration_external"
    add_index :invoices, [ :organization_id, :current_ar_status, :due_date ], name: "idx_invoices_status_dates"
    add_index :invoices, [ :organization_id, :pay_link_token ], name: "idx_invoices_token",
              where: "pay_link_token IS NOT NULL"
    add_index :invoices, [ :organization_id, :invoice_number ], name: "idx_invoices_number"

    create_table :conversations, id: :uuid do |t|
      t.references :organization, type: :uuid, null: false, foreign_key: true
      t.references :integration, type: :uuid, null: false, foreign_key: true
      t.string :external_thread_id, null: false
      t.text :subject
      t.string :status, null: false, default: "active"
      t.timestamps
    end

    add_index :conversations, [ :integration_id, :external_thread_id ],
              unique: true, name: "uq_conversations_integration_thread"

    create_table :messages, id: :uuid do |t|
      t.references :conversation, type: :uuid, null: false, foreign_key: true
      t.string :external_message_id, null: false
      t.string :direction, null: false
      t.string :from_address, null: false
      t.jsonb :to_addresses, null: false, default: []
      t.jsonb :cc_addresses, null: false, default: []
      t.datetime :sent_at, null: false
      t.text :clean_body
      t.boolean :is_anchor, null: false, default: false
      t.boolean :processed_by_ai, null: false, default: false
      t.datetime :created_at, null: false
    end

    add_index :messages, [ :conversation_id, :external_message_id ],
              unique: true, name: "uq_messages_conversation_ext_id"
    add_index :messages, [ :conversation_id, :sent_at ], name: "idx_messages_sent_at"

    create_table :invoice_conversations, primary_key: [ :invoice_id, :conversation_id ] do |t|
      t.uuid :invoice_id, null: false
      t.uuid :conversation_id, null: false
      t.boolean :is_primary, null: false, default: false
      t.datetime :created_at, null: false
    end

    add_foreign_key :invoice_conversations, :invoices
    add_foreign_key :invoice_conversations, :conversations
    add_index :invoice_conversations, :conversation_id, name: "idx_invoice_conversations_conv"

    create_table :invoice_state_transitions, id: :uuid do |t|
      t.references :invoice, type: :uuid, null: false, foreign_key: true
      t.string :from_status
      t.string :to_status, null: false
      t.string :trigger_source, null: false
      t.uuid :triggered_by_message_id
      t.date :promise_date
      t.decimal :disputed_amount, precision: 12, scale: 2
      t.boolean :needs_reply, null: false, default: false
      t.text :reason_quote
      t.boolean :is_reverted, null: false, default: false
      t.datetime :created_at, null: false
    end

    add_foreign_key :invoice_state_transitions, :messages, column: :triggered_by_message_id, on_delete: :nullify
    add_index :invoice_state_transitions, [ :invoice_id, :created_at ],
              order: { created_at: :desc }, name: "idx_state_transitions_audit"
  end
end
